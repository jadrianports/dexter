# CLAUDE.md — Dexter Discord Bot Build Spec

## What This Is

Discord bot named "Dexter" (Dex). Plays music from YouTube, chats via Gemini AI, generates images via Imagen. Has a persistent sarcastic personality that tracks user behavior and roasts them.

Read `dexter-architecture.md` for full context, personality samples, and rationale.

---

## Tech Stack (do not deviate)

- **Language:** Python 3.11+
- **Discord:** discord.py ≥2.3 (`AutoShardedBot`) + davey + PyNaCl for voice
- **Music:** yt-dlp + FFmpeg (opus, 192kbps)
- **AI Chat:** Google Gemini API via `google-genai` (free tier, `gemini-2.5-flash`)
- **Image Gen:** `gemini-2.5-flash-image` via the Gemini API (free tier)
- **Database:** PostgreSQL 16 via `asyncpg` 0.31.0 — migrated from SQLite in Phase 4
- **Containerization:** Docker + Docker Compose (bot image only; DB is **Neon serverless Postgres**, not a colocated container — the Oracle-era `postgres:16-alpine` service was dropped in Phase 6)
- **Lyrics:** Genius API via `lyricsgenius` (primary), AZLyrics scrape via `beautifulsoup4` (fallback)
- **Hosting:** re-targeted Oracle A1 → Koyeb + Neon (Phase 5), then **24/7 deploy parked** (YouTube blocks datacenter IPs → free cloud non-viable). Runs on the user's PC (residential IP) on demand → **Neon serverless Postgres** (Singapore). Code is substrate-agnostic (Dockerfile + `DATABASE_URL`), so the host swap is config-only.

---

## Project Structure

```
dexter/
├── bot.py                         # Entry point, AutoShardedBot init, cogs, background tasks
├── config.py                      # All settings (see Configuration section)
├── database.py                    # PostgreSQL (asyncpg) init, schema, query helpers, streak logic
├── docker-compose.yml             # bot service only (DB = Neon, no colocated Postgres); named volumes
├── Dockerfile                     # bot image build
├── cogs/
│   ├── music.py                   # All music slash commands
│   ├── ai.py                      # /ask, AI auto-queue logic
│   ├── imagine.py                 # /imagine
│   ├── help.py                    # /help
│   └── events.py                  # Unprompted roasts, reactions, mood, status, idle
├── services/
│   ├── youtube.py                 # yt-dlp: search, download, metadata extraction
│   ├── gemini.py                  # Gemini API: chat, music recs, image gen
│   ├── lyrics.py                  # Genius + AZLyrics
│   ├── queue_persistence.py       # Phase 4: persist/restore queues (guild_queues JSONB), smart-rejoin
│   └── audio.py                   # FFmpeg audio source management
├── models/
│   ├── queue.py                   # Per-server queue (loop, shuffle, 500 cap, _play_generation counter)
│   ├── user_profile.py            # User taste tracking
│   ├── server_state.py            # Per-server runtime state
│   └── message_buffer.py          # Rolling 10-message context per channel
├── personality/
│   ├── prompts.py                 # Gemini system prompts
│   ├── responses.py               # Templated music command responses
│   ├── roasts.py                  # Unprompted roast logic
│   └── seasonal.py                # Date-aware personality
├── utils/
│   ├── embeds.py                  # Discord embed builders
│   ├── formatters.py              # Duration, progress bars, etc.
│   └── logger.py                  # File + Discord channel logging
├── scripts/                       # Phase 4/5 ops: deploy.sh, backup.sh, keepalive.sh,
│                                  #   lifecycle-policy.json, seed_restore_test.py
├── tests/                         # pytest suite (pure unit tests + live-DB integration tests)
├── data/cache/                    # Audio cache (Postgres data lives in a Docker volume, not here)
├── requirements.txt
├── .env                           # DISCORD_TOKEN, GEMINI_API_KEY, GENIUS_TOKEN, DATABASE_URL, OWNER_ID, …
└── README.md
```

> **Note:** cooldowns are enforced inline at the command layer; there is no `utils/cooldowns.py`.

---

## Database Schema (PostgreSQL)

Defined in `database.py` as `SCHEMA_SQL` (idempotent `CREATE TABLE IF NOT EXISTS`, applied by
`init_db()` over an asyncpg pool). Migrated from SQLite in Phase 4 — Postgres types throughout
(`TIMESTAMPTZ`, `BIGSERIAL`, `BOOLEAN`, `JSONB`, `now()`). Phase 3 added the streak columns;
Phase 4 added the `guild_queues` table for queue persistence.

```sql
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id            TEXT PRIMARY KEY,
    username           TEXT NOT NULL,
    total_songs_queued INTEGER DEFAULT 0,
    first_seen_at      TIMESTAMPTZ DEFAULT now(),
    last_active_at     TIMESTAMPTZ DEFAULT now(),
    current_streak     INTEGER DEFAULT 0,   -- Phase 3
    longest_streak     INTEGER DEFAULT 0,   -- Phase 3
    last_streak_date   TEXT                 -- Phase 3 (ISO date in STREAK_TIMEZONE)
);

CREATE TABLE IF NOT EXISTS song_history (
    id               BIGSERIAL PRIMARY KEY,
    guild_id         TEXT NOT NULL,
    user_id          TEXT NOT NULL,
    title            TEXT NOT NULL,
    artist           TEXT,
    url              TEXT NOT NULL,
    duration_seconds INTEGER,
    queued_at        TIMESTAMPTZ DEFAULT now(),
    was_skipped      BOOLEAN DEFAULT false,
    was_auto_queued  BOOLEAN DEFAULT false
);
CREATE INDEX IF NOT EXISTS idx_history_guild ON song_history(guild_id, queued_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_user  ON song_history(user_id,  queued_at DESC);

CREATE TABLE IF NOT EXISTS user_artist_counts (
    user_id    TEXT NOT NULL,
    artist     TEXT NOT NULL,
    play_count INTEGER DEFAULT 1,
    PRIMARY KEY (user_id, artist)
);

CREATE TABLE IF NOT EXISTS image_generation_log (
    id           BIGSERIAL PRIMARY KEY,
    guild_id     TEXT NOT NULL,
    user_id      TEXT NOT NULL,
    prompt       TEXT NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_imagine_user_date ON image_generation_log(user_id, generated_at);

CREATE TABLE IF NOT EXISTS bot_daily_stats (
    date                   TEXT PRIMARY KEY,
    total_commands         INTEGER DEFAULT 0,
    total_songs_played     INTEGER DEFAULT 0,
    total_ai_queries       INTEGER DEFAULT 0,
    total_images_generated INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS guild_queues (    -- Phase 4: queue persistence
    guild_id   TEXT PRIMARY KEY,
    payload    JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

---

## Configuration

All in `config.py`. Single file. Phases 2–4 settings are now implemented — the block below shows the Phase 1 core; the full current set follows it.

```python
# Paths
BASE_DIR = Path(__file__).resolve().parent
AUDIO_CACHE_DIR = BASE_DIR / "data" / "cache"    # Path object
LOG_DIR = BASE_DIR / "logs"

# Music
MAX_SONG_DURATION_SECONDS = 900       # 15 min
MAX_PLAYLIST_IMPORT = 50
AUDIO_QUALITY = "192"                  # kbps
AUDIO_CACHE_MAX_MB = 512              # 512MB (K-07; was 2048 pre-v1.1)
IDLE_TIMEOUT_SECONDS = 600            # 10 min
DOWNLOAD_TIMEOUT_SECONDS = 10
SEARCH_RESULTS_COUNT = 5

# Logging
LOG_LEVEL = "INFO"
LOG_RETENTION_DAYS = 14

# Cooldowns
PLAY_COOLDOWN_SECONDS = 2
SKIP_COOLDOWN_SECONDS = 2
HELP_COOLDOWN_SECONDS = 5

# Bot
OWNER_ID = int(os.getenv("OWNER_ID") or "0")
```

**Now implemented (Phases 2–4) — `config.py` is the authoritative list:**

```python
# AI (Phase 2)
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_RPM_LIMIT = 15                  # shared across ALL AI features
MAX_AI_RESPONSE_LENGTH = 500
ASK_COOLDOWN_SECONDS = 5

# Image gen (Phase 2)
IMAGEN_MODEL = "gemini-2.5-flash-image"
IMAGINE_COOLDOWN_SECONDS = 30
MAX_IMAGES_PER_USER_PER_DAY = 10

# Mood + auto-queue (Phase 2)
MOOD_NORMAL_THRESHOLD = 15; MOOD_TIRED_THRESHOLD = 30; MOOD_EXHAUSTED_THRESHOLD = 50
AUTO_QUEUE_MAX_ROUNDS = 3; AUTO_QUEUE_SONGS_PER_ROUND = 3

# Personality / roasts / status / lyrics (Phase 3)
DEXTER_CHANNEL_ID, ERROR_LOG_CHANNEL_ID            # from env
STREAK_TIMEZONE = "America/New_York"               # IANA tz for ALL community-time checks
UNPROMPTED_ROAST_CHANCE = 0.30; LATE_NIGHT_ROAST_CHANCE = 0.50; LATE_NIGHT_HOURS = (1, 5)
REPEAT_SONG_ROAST_THRESHOLD = 3
MILESTONE_SONG_THRESHOLDS = [100, 250, 500, 1000]
MILESTONE_STREAK_THRESHOLDS = [7, 14, 30, 60, 100]
STATUS_ROTATION_INTERVAL_SECONDS = 300; IDLE_LONELINESS_THRESHOLD_SECONDS = 1800
LYRICS_PAGE_SIZE = 1500; HISTORY_PAGE_SIZE = 10; HISTORY_FETCH_LIMIT = 50

# Database / scale (Phase 4)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dexter:dexter@localhost:5432/dexter")
DB_POOL_MIN = 2; DB_POOL_MAX = 10
MAX_QUEUE_SIZE_PER_GUILD = 500                     # enforced in MusicQueue.add()
MESSAGE_BUFFER_TTL_HOURS = 24
HEALTHCHECK_URL = os.getenv("HEALTHCHECK_URL", "") # Healthchecks.io dead-man switch
```

---

## Slash Commands

### Music
| Command | Args | Cooldown |
|---------|------|----------|
| `/play` | `<query or URL>` | 2s |
| `/skip` | — | 2s |
| `/pause` | — | — |
| `/resume` | — | — |
| `/stop` | — | — |
| `/queue` | — | 2s |
| `/shuffle` | — | 2s |
| `/loop` | `[off\|single\|queue]` | — |
| `/nowplaying` | — | 2s |
| `/replay` | — | 2s |
| `/history` | — | 5s |
| `/lyrics` | — | 10s |

### AI
| Command | Args | Cooldown |
|---------|------|----------|
| `/ask` | `<question>` | 5s |

### Image
| Command | Args | Cooldown |
|---------|------|----------|
| `/imagine` | `<prompt>` | 30s |

### Utility
| Command | Args | Cooldown |
|---------|------|----------|
| `/help` | — | 5s |

---

## Music Pipeline

```
/play <input>
  → If input is URL (starts with http/youtube.com/youtu.be): queue directly
  → If input is text: search YouTube via yt-dlp, return 5 results as Discord select menu
  → User picks song from dropdown
  → Reject if duration > 900s (15 min)
  → Reject if livestream (no duration)
  → Check cache (data/cache/{video_id}.opus)
  → If not cached: download via yt-dlp (timeout 10s, fallback to stream)
  → Add to server queue
  → If nothing playing: start FFmpeg → Discord voice playback
  → Post/update now playing embed (persistent message, edit on song change)
  → Log: song_history, user_artist_counts, user_profiles, bot_daily_stats
```

Playlist URLs (contains "list="): extract up to 50 tracks, queue all.

### Playback Engine Patterns

- **Generation counter:** `queue._play_generation` prevents stale after-callbacks from firing on skip/stop/replay
- **Channel tracking:** `queue._text_channel_id` — bot posts in the command channel, not #general
- **Silent skip:** Unavailable tracks chained through silently, one summary message at the end
- **Async responses:** `/skip` responds immediately, runs playback via `asyncio.create_task()`

---

## AI Pipeline

### /ask
```
/ask <question>
  → Check cooldown
  → Gather: message_buffer (last 10), user_profile summary, mood, seasonal context
  → Build system prompt (see Personality section)
  → defer() interaction (shows "Dexter is thinking...")
  → Send to Gemini
  → Post response in designated channel
  → Add response to message_buffer
  → Increment daily command count
```

### Auto-Queue
```
Queue empties + users still in voice
  → Gather last 10-15 songs from session
  → Send to Gemini with music recommendation prompt (JSON response)
  → Parse 3 suggestions
  → Search YouTube for each, queue top results
  → Mark as was_auto_queued = true
  → Track skip rate for "ignored" memory
```

### /imagine
```
/imagine <prompt>
  → Check cooldown + daily cap
  → defer() interaction
  → Send to Gemini Imagen
  → If refused/empty: personality error message
  → Post image with sarcastic caption
  → Log to image_generation_log
```

---

## Personality

### System Prompt Core Rules
- Sarcastic, dry, self-aware, lowercase energy
- Never uses caps lock or excessive punctuation
- Responses under 500 chars unless question needs more
- One emoji max per message
- Accurate first, sarcastic second
- References user's music history when relevant
- Dials back sarcasm for genuinely serious/emotional questions
- Mood shifts based on daily command count (normal → tired → exhausted → fumes)

### Mood System
Commands 1-15: normal. 15-30: tired, shorter responses. 30-50: exhausted, openly complains. 50+: running on spite, maximum sarcasm.

Tracked in `bot_daily_stats`, resets at midnight. Mood string injected into Gemini system prompt.

### Seasonal Awareness
Check month/day, inject seasonal context into system prompt:
- December: dreads Christmas music
- October: reluctantly tolerates Halloween
- Feb 14: roasts lonely voice channel users
- Jan 1: mocks resolutions
- Apr 1: extra chaotic

---

## Unprompted Behavior

### Voice Events (cogs/events.py)
- **User joins voice:** 30% roast chance, 5-min cooldown per user, personalized from user profile
- **User joins at 1-5am:** 50% time-related roast
- **Last user leaves voice:** bot auto-leaves after 10 min idle, posts farewell
- **Bot moved to different channel:** always complains

### Message Reactions
- YouTube/Spotify link in chat: react 👀
- "goodnight"/"gn": react 🫡
- Bot mentioned without command: react 😐
- User says thanks to bot: respond with deflecting warmth

### Idle Messages
No commands for 30+ min but users in voice: post one lonely message. Not repeated until next activity.

### Repeat Song Detection
Same song 3+ times in one day by same user: 100% roast, always triggers.

### Milestone Roasts
User hits 100/250/500/1000 total songs queued: always triggers.

### Streak Tracking
Consecutive days using the bot. Milestones at 7/14/30/60/100 days.

### "Ignored" Memory
Track skip rate on AI auto-queued songs. Reference outcome next time auto-queue triggers.

### Status Rotation
Every 5 min, rotate from pool: current song, server count, personality lines, seasonal.

### Startup Message
On boot: post "i'm back. did you miss me. probably not." in designated channel.

---

## Now Playing Embed

Persistent message, edited on song change. If edit fails (rate limit), send new one.

Fields: title, artist, duration, progress bar, requested by, loop mode, lyrics snippet (first verse), "/lyrics for full lyrics" footer, YouTube thumbnail.

---

## Edge Cases

| Case | Handle |
|------|--------|
| Bot disconnect mid-song | Save position, reconnect, resume. 3 attempts then error. |
| Song > 15 min | Reject with personality message |
| Livestream URL | Reject with personality message |
| Voice empty 10 min | Auto-leave, clear queue, post message |
| Same song 3+ times/day | 100% roast, still plays |
| Playlist > 50 songs | Truncate to 50, inform user |
| yt-dlp fails | Auto-update, retry, fallback stream, then error |
| Gemini rate limit (15 RPM) | Global rate limiter, queue requests, personality error |
| Imagen refuses prompt | Personality-flavored refusal |
| FFmpeg orphan process | Explicit cleanup in error handlers |

---

## Logging

### File Logging
Location: `LOG_DIR` = `logs/` (NOT `/var/log/dexter/`), **plus stdout** so Docker/Koyeb log viewers capture output (K-16).
- `dexter.log`: INFO+ (commands, songs, queries). Daily rotation, 14-day retention.
- `error.log`: ERROR+ only. Weekly rotation, 30-day retention.

### Discord Error Channel
Private channel, bot posts:
- yt-dlp failures (after retry)
- Gemini errors / rate limits
- Unexpected disconnects
- Unhandled exceptions
- Daily summary embed (commands, songs, errors)

---

## Cache Management

Directory: `data/cache/`
Files: `{video_id}.opus`
Max size: 512MB (`AUDIO_CACHE_MAX_MB`). When exceeded, evict **least-played** tracks (lowest `song_history` play_count — NOT `atime`, which is unreliable on `noatime` mounts), skipping any `protected_video_ids` currently in use. (Phase 6 / K-07; was 2GB-by-atime pre-v1.1.)
Hourly cleanup loop checks total size.

---

## yt-dlp Maintenance

Daily auto-update at 4am: `pip install -U yt-dlp`
On download failure: attempt update → retry → fallback stream → error message.

---

## Background Tasks

Start on bot ready:
1. Status rotation (every 5 min)
2. Idle voice channel check (every 60s)
3. Cache cleanup (every hour)
4. yt-dlp update check (daily 4am)
5. Daily stats reset (midnight)

---

## Discord Intents Required

- `message_content` — reading messages for context buffer
- `voice_states` — detecting voice join/leave for unprompted roasts
- `members` — resolving user info for personalized roasts
- `guilds` — server info

Enable all in Discord Developer Portal.

---

## Environment Variables (.env)

```
DISCORD_TOKEN=
GEMINI_API_KEY=
GENIUS_TOKEN=
```

---

## Build Phases

### Phase 1 — MVP ✅ COMPLETE
1. Project setup: discord.py, yt-dlp, FFmpeg, aiosqlite, davey
2. SQLite schema (all tables)
3. Config file
4. /play with 5-result YouTube search + select menu
5. /skip, /pause, /resume, /stop, /queue
6. Queue model (per-server, loop modes, shuffle)
7. Audio: download-first + stream fallback + cache
8. Now playing embed (persistent, edited on song change)
9. Duration cap + playlist truncation
10. Voice auto-leave on idle
11. Disconnect recovery (reconnect + retry, no position save yet)
12. /help
13. /nowplaying, /replay (moved up from Phase 3)
14. File logging (logs/ dir, daily rotation)
15. Command sync via --first-run --guild CLI flag + /sync owner command

**Deferred to Phase 2/3:** Designated channel support, /history, /lyrics, deploy to Oracle Cloud

### Phase 2 — Personality + AI ✅ COMPLETE
1. /ask with Gemini + 10-message context
2. Full personality system prompt
3. User profile tracking in SQLite
4. User taste summary for Gemini prompt injection
5. Mood system
6. Typing indicator / defer
7. AI auto-queue
8. "Ignored" memory
9. All command cooldowns
10. /imagine with daily cap
11. Discord error log channel

### Phase 3 — Alive ✅ COMPLETE
1. Unprompted voice roasts (join/leave)
2. Roast frequency + cooldowns
3. Late night roasts
4. Repeat song roasts
5. Emoji reactions
6. Seasonal awareness
7. Status rotation
8. Startup message
9. Idle loneliness messages
10. Streak tracking + milestones
11. /lyrics (Genius + AZLyrics + pagination)
12. /history
13. yt-dlp auto-update

### Phase 4 — Scale ✅ COMPLETE
1. Multi-server hardening
2. SQLite → PostgreSQL (asyncpg 0.31.0)
3. AutoShardedBot
4. Queue persistence (`guild_queues` JSONB + smart-rejoin on restart)
5. Docker Compose (`postgres:16-alpine` + bot), healthcheck / keepalive
6. ~~Web config dashboard~~ — dropped (never committed)

### Phase 5 — Ship It Live ◆ CODE COMPLETE (awaiting live Oracle A1 UAT)
1. Docker Compose standup on Oracle A1 ARM + reboot survival
2. `clear_persisted()` gap closure on idle-leave / reconnect-failure (DEPLOY-06)
3. Reconnect-race hardening + diagnostic logging (DEPLOY-04 — live `/gsd:debug` pending)
4. TZ-correct late-night roast via `ZoneInfo(STREAK_TIMEZONE)` (D-06)
5. Ops scripts: `deploy.sh`, `backup.sh` (6h cadence), OCI lifecycle policy, non-destructive seed/restore-verify
6. Consolidated 20-check live-UAT runbook (`.planning/phases/05-ship-it-live/05-UAT-RUNBOOK.md`) — **the phase is verified when it passes live on Oracle, not when code lands**

> **Milestone status:** v1.0 (Phases 1–4) shipped & archived. Now on v1.1 "Live & Lethal" (Phases 5–8).
> Phases 6–8 (perf, player UX, social/leaderboard) live in `.planning/ROADMAP.md`.

---

## Critical Rules

1. **All AI features share 15 RPM Gemini limit — implement global rate limiter**
2. **Always check if input is URL before searching — skip search menu for direct URLs**
3. **Kill FFmpeg processes explicitly on skip/stop/error — prevent orphans**
4. **yt-dlp WILL break — auto-update daily and on failure**
5. **Never sacrifice factual accuracy for personality in /ask responses**
6. **Dial back sarcasm for serious/emotional questions**
7. **One emoji max per message — the bot is too tired for more**
8. **Lowercase everything — the bot does not use caps lock**
9. **Designated channel only — don't spam every channel**
10. **Cache cleanup must run — unchecked cache will fill Oracle's free disk**

---

## Implementation Gotchas

**Phase 1 (music pipeline):**
- **yt-dlp `extract_flat: True`** breaks search queries — only use for playlist extraction (PLAYLIST_OPTS), never for search (SEARCH_OPTS)
- **yt-dlp search results:** use `entry.get("webpage_url")` not `entry.get("url")` — the latter is a stream URL that expires
- **Never call `voice_client.stop()` before `_play_track()`** — the old after-callback fires before generation increments, causing double-play races. Let `_play_track` handle stopping internally.
- **Slash command interactions must respond within 3s** — `defer()` or respond immediately, then do async work via `asyncio.create_task()`

**Phases 4–5 (Postgres + deploy):**
- **asyncpg multi-statement DDL** only works when there are no `$N` params — `SCHEMA_SQL` is plain DDL applied in one `conn.execute()` (Pitfall 1)
- **`clear_persisted()` must mirror the `/stop` template** at every queue-teardown site (`_play_generation += 1` → `clear()` → `clear_persisted()`) or a ghost queue restores on restart (DEPLOY-06 / IN-02). **Teardown sites include natural queue exhaustion** — when the last track ends with nothing to resume, `current_index` stays parked on the finished track, so without `clear_persisted()` smart-rejoin replays it on the next restart (v1.1 live UAT)
- **Community-time checks use `ZoneInfo(config.STREAK_TIMEZONE)`**, never naive `datetime.now().hour` — the host VM runs UTC, so naive time fires roasts/streaks on the wrong calendar day (D-06 / D-17)
- **`restore_queues` must `continue` per-guild, not `return`** — one guild's failed smart-rejoin must not abort restoration for the rest (CR-01)
- **`pg_restore` runs via `docker compose exec` (version-matched)**, never the host client, to dodge a server/client version mismatch
- **Neon / serverless Postgres:** the asyncpg pool MUST use `statement_cache_size=0` + `ssl='require'` + a bounded `max_inactive_connection_lifetime` (~240s) — prepared statements break through PgBouncer and the pool must survive Neon's scale-to-zero, else SSL-EOF / `channel_binding` crashes (Phase 5 / K-04)

**Phases 6–8 (speed, player UX, social):**
- **Gate playback-start on `voice_client.is_playing()`, never the `queue.is_playing` flag** — `_on_track_end` leaves `is_playing=True` and defers to `try_auto_queue` on natural exhaustion ("auto-queue will handle it"), so a `not queue.is_playing` guard never fires and tracks queue but never play (silent auto-queue; v1.1 live UAT). The voice client is the only ground truth for "audio is flowing".
- **Resolution-cache hits must route through `async_extract`** (full duration/livestream guards), never inline `Track` construction — a stale cached `video_id` would otherwise bypass the validity checks (D-09)
- **Persistent discord.py views:** `timeout=None` + stable `custom_id`s registered in `setup_hook` (NOT `on_ready`) — otherwise buttons stop responding after a restart (Phase 7)
- **opus-copy is the default fast path; transcode ONLY when `active_filter` is set** per-track — don't remove the opus-copy path for non-filtered tracks (PERF-02 / PLAYER-07, D-10/D-12)
- **SponsorBlock PP order** is `SponsorBlock(when=after_filter) → FFmpegExtractAudio → ModifyChapters`; don't hand-write opus-copy — `FFmpegExtractAudioPP` already copies natively, `download()` only adds `postprocessor_hooks` for codec-path logging (D-01)
