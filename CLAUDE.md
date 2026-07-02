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
- **Long-term memory (RAG):** `pgvector` on the same Neon Postgres + `gemini-embedding-001` @ 768d on a **separate** 60 RPM limiter (Phase 11 — zero new infra/cost)
- **Database:** PostgreSQL 16 via `asyncpg` 0.31.0 — migrated from SQLite in Phase 4; `vector` extension enabled in Phase 11
- **Containerization:** Docker + Docker Compose (bot image only; DB is **Neon serverless Postgres**, not a colocated container — the Oracle-era `postgres:16-alpine` service was dropped in Phase 6)
- **Lyrics:** Genius API via `lyricsgenius` (primary), AZLyrics scrape via `beautifulsoup4` (fallback), LRCLIB `/api/search` (third fallback, Phase 12)
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
│   ├── music.py                   # Music slash commands + /seek /previous /jump /filter /autolyrics (Phases 6/7)
│   ├── ai.py                      # /ask, /roast, AI auto-queue logic
│   ├── imagine.py                 # /imagine
│   ├── help.py                    # /help
│   ├── ops.py                     # /leaderboard, /skips, /stats (Phases 8/12)
│   ├── library.py                 # /favorite(s), /playlist group, /jam group (Phases 7/12)
│   └── events.py                  # Unprompted roasts, reactions, mood, status, idle
├── logic/                         # Phase 10: pure, mock-free decision logic (TDD seam)
│   ├── playback.py                # TrackEndAction enum + 5 keyword-only playback fns
│   ├── health.py                  # determine_health_status + assemble_degraded_reasons
│   ├── roasts.py                  # decide_ambient_roast + cooldown_elapsed
│   ├── autoqueue.py               # token-set-containment hallucination validator (Phase 12)
│   └── skip_stats.py              # /skips rate computation (Phase 12)
├── services/
│   ├── youtube.py                 # yt-dlp: search, download, metadata extraction, resolution cache, self-heal
│   ├── gemini.py                  # Gemini API: chat, music recs, image gen, embed() (RAG)
│   ├── memory.py                  # Phase 11: RAG long-term memory (recall/remember/dedup/decay)
│   ├── metrics.py                 # Phase 6: PerfMetrics rolling aggregates for /stats
│   ├── lyrics.py                  # Genius + AZLyrics + LRCLIB
│   ├── queue_persistence.py       # Phase 4: persist/restore queues (guild_queues JSONB), smart-rejoin
│   └── audio.py                   # FFmpeg audio source management (opus-copy / filter transcode)
├── models/
│   ├── queue.py                   # Per-server queue (loop, shuffle, 500 cap, _play_generation counter)
│   ├── user_profile.py            # User taste tracking
│   ├── memory.py                  # Phase 11: MemoryFact dataclass
│   ├── server_state.py            # Per-server runtime state
│   └── message_buffer.py          # Rolling 10-message context per channel
├── personality/
│   ├── prompts.py                 # Gemini system prompts (+ memory-context slot)
│   ├── responses.py               # Templated music command responses
│   ├── roasts.py                  # Unprompted roast logic
│   └── seasonal.py                # Date-aware personality
├── utils/
│   ├── embeds.py                  # Discord embed builders
│   ├── formatters.py              # Duration, progress bars, etc.
│   ├── tasks.py                   # Phase 9: make_task — fire-and-forget with failure surfacing
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
Phase 4 added the `guild_queues` table for queue persistence; Phase 6 added `resolution_cache`;
Phase 7 added `user_favorites` + `user_playlists`; Phase 8 added `bot_daily_stats.total_errors`;
Phase 11 enabled the `vector` extension + `user_memories`; Phase 12 added `guild_jams`.

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

-- Phase 6: resolution cache (skip YouTube re-search on repeat queries; TTL-expired)
CREATE TABLE IF NOT EXISTS resolution_cache (
    query_key  TEXT PRIMARY KEY,
    video_id   TEXT NOT NULL,
    title      TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

-- Phase 7: per-user favorites (25 cap) and named playlist snapshots
CREATE TABLE IF NOT EXISTS user_favorites (
    user_id          TEXT NOT NULL,
    video_id         TEXT NOT NULL,
    title            TEXT NOT NULL,
    artist           TEXT,
    url              TEXT NOT NULL,
    duration_seconds INTEGER,
    thumbnail        TEXT,
    added_at         TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, video_id)
);
CREATE TABLE IF NOT EXISTS user_playlists (
    user_id    TEXT NOT NULL,
    name       TEXT NOT NULL,
    snapshot   JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, name)
);

-- Phase 8: central error counter
ALTER TABLE bot_daily_stats ADD COLUMN IF NOT EXISTS total_errors INTEGER DEFAULT 0;

-- Phase 12: per-server shared "jam" mixtapes (distinct from per-user favorites)
CREATE TABLE IF NOT EXISTS guild_jams (
    guild_id   TEXT NOT NULL,
    name       TEXT NOT NULL,
    snapshot   JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (guild_id, name)
);

-- Phase 11: RAG long-term memory. Requires `CREATE EXTENSION IF NOT EXISTS vector;`
-- (run FIRST in SCHEMA_SQL) + per-connection pgvector codec via create_pool(init=...).
CREATE TABLE IF NOT EXISTS user_memories (
    id               BIGSERIAL PRIMARY KEY,
    user_id          TEXT NOT NULL,
    guild_id         TEXT,
    kind             TEXT,               -- milestone|late_night|repeat_song|auto_queue_ignored|daily_batch
    fact             TEXT NOT NULL,
    embedding        vector(768) NOT NULL,  -- gemini-embedding-001 @ 768d
    salience         REAL DEFAULT 0,
    hit_count        INTEGER DEFAULT 1,
    created_at       TIMESTAMPTZ DEFAULT now(),
    last_seen_at     TIMESTAMPTZ DEFAULT now(),
    last_surfaced_at TIMESTAMPTZ,
    surface_count    INTEGER DEFAULT 0,
    expires_at       TIMESTAMPTZ         -- daily decay sweep evicts low-salience expired facts
);
```

---

## Configuration

All in `config.py`. Single file. Phases 2–12 settings are now implemented — the block below shows the Phase 1 core; the full current set follows it. `config.py` is always the authoritative list.

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
DB_POOL_MIN = 2; DB_POOL_MAX = 5
MAX_QUEUE_SIZE_PER_GUILD = 500                     # enforced in MusicQueue.add()
MESSAGE_BUFFER_TTL_HOURS = 24
HEALTHCHECK_URL = os.getenv("HEALTHCHECK_URL", "") # Healthchecks.io dead-man switch

# Neon pool tuning (Phase 5 / K-04)
DB_MAX_INACTIVE_CONN_LIFETIME = 240                # recycle before Neon scale-to-zero
DB_STATEMENT_CACHE_SIZE = 0                        # disable prepared stmts for PgBouncer tx-mode

# Speed & caching (Phase 6)
PREFETCH_TIMEOUT_SECONDS = 45; RES_CACHE_TTL_DAYS = 14; PERF_ROLLING_WINDOW = 50
SPONSORBLOCK_CATEGORIES = frozenset({"sponsor","selfpromo","intro","outro","interaction","music_offtopic"})

# Player UX & filters (Phase 7)
FFMPEG_FILTERS = {"bassboost","nightcore","slowed+reverb","8d"}  # name → -af chain; "off" = passthrough
FAVORITES_MAX_PER_USER = 25; PLAYLISTS_MAX_PER_USER = 25; PLAYLIST_NAME_MAX_LENGTH = 60
SEEK_COOLDOWN_SECONDS = 2; FILTER_COOLDOWN_SECONDS = 5; FAVORITE_COOLDOWN_SECONDS = 2

# Social & ops (Phases 8/12)
LEADERBOARD_TOP_N = 5; ROAST_COOLDOWN_SECONDS = 30
JAMS_PER_GUILD_MAX = 25; SKIP_STATS_MIN_PLAYS = 5; AUTO_QUEUE_SEARCH_CANDIDATES = 3

# Reliability & ops hardening (Phase 9)
HEALTH_STRICT_STATUS = True         # 503 when degraded (strict) vs legacy 200; env-overridable
DB_COMMAND_TIMEOUT_SECONDS = 30; INIT_WATCHDOG_TIMEOUT_SECONDS = 120; SYNC_TIMEOUT_SECONDS = 30
TASK_ERROR_CHANNEL_COOLDOWN_SECONDS = 300          # dedup window per (task_name, exc_type)
YTDLP_RETRY_BACKOFF_SECONDS = 1.0; YTDLP_MAX_QUICK_RETRIES = 2; HEALTH_DB_PROBE_TIMEOUT = 3.0

# RAG long-term memory (Phase 11) — embeddings on a SEPARATE 60 RPM limiter, never the 15 RPM chat budget
EMBEDDING_MODEL = "gemini-embedding-001"; EMBED_DIM = 768; EMBED_RPM_LIMIT = 60
MEMORY_TOP_K = 8; MEMORY_SIMILARITY_FLOOR = 0.70; MEMORY_DEDUP_THRESHOLD = 0.92
MEMORY_INJECT_CAP = 3; MEMORY_MAX_PER_USER = 150; MEMORY_DECAY_DAYS = 90
MEMORY_CALLBACK_CHANCE = 0.35; MEMORY_DISTILL_BATCH_HOUR = 3   # + rerank weights + salience base weights
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
| `/seek` | `<position>` | 2s |
| `/previous` | — | — |
| `/jump` | `<index>` | — |
| `/filter` | `[bassboost\|nightcore\|slowed+reverb\|8d\|off]` | 5s |
| `/autolyrics` | `[on\|off]` | — |

> Now-playing embed also carries a persistent 5-button control view (play/pause, skip, loop, shuffle, stop) — Phase 7.

### AI
| Command | Args | Cooldown |
|---------|------|----------|
| `/ask` | `<question>` | 5s |
| `/roast` | `@user` | 30s |

### Image
| Command | Args | Cooldown |
|---------|------|----------|
| `/imagine` | `<prompt>` | 30s |

### Library (Phases 7/12)
| Command | Args | Cooldown |
|---------|------|----------|
| `/favorite` | — (save now-playing) | 2s |
| `/favorites` | — (view + queue) | 2s |
| `/playlist save\|load\|list\|delete` | `[name]` | — |
| `/jam save\|add\|load\|list\|delete` | `[name]` | — |

### Ops (Phases 8/12)
| Command | Args | Cooldown |
|---------|------|----------|
| `/leaderboard` | — (per-guild songs/streaks/skips) | — |
| `/skips` | — (skip-rate analytics) | — |
| `/stats` | — (owner-only) | — |

### Utility
| Command | Args | Cooldown |
|---------|------|----------|
| `/help` | — | 5s |

> `/health` is an aiohttp HTTP endpoint on `0.0.0.0:8000` (not a slash command) — returns degraded-503 when MusicCog fails to load (Phases 5/8/9).

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
3. Cache cleanup (every hour) — LFU by `song_history` play count, protects in-use tracks (Phase 6)
4. yt-dlp update check (daily 4am)
5. Daily stats reset (midnight)
6. Memory distill batch (daily 03:00 UTC — background message-buffer → RAG facts, Phase 11)
7. Memory decay sweep (evicts low-salience expired `user_memories`, Phase 11)

> Fire-and-forget tasks are launched via `utils/tasks.py::make_task` (Phase 9) — a done-callback surfaces exceptions to `dexter.log` + the error channel instead of vanishing silently. Next-track prefetch (`_prefetch_next_track`) is generation-guarded to avoid racing skip/stop teardown (Phase 6).

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
DATABASE_URL=            # Neon Postgres DSN (sanitized to strip channel_binding/sslmode)
OWNER_ID=               # owner-only commands (/stats, /sync)
DEXTER_CHANNEL_ID=      # designated ambient/response channel
ERROR_LOG_CHANNEL_ID=   # private error-log channel
HEALTHCHECK_URL=        # optional Healthchecks.io / UptimeRobot dead-man switch
STREAK_TIMEZONE=        # optional IANA tz override (default America/New_York)
HEALTH_STRICT_STATUS=   # optional; "false" reverts /health to legacy 200
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

### Phase 5 — Ship It Live ✅ CODE COMPLETE (24/7 deploy PARKED)
1. Deploy substrate re-targeted **Oracle A1 → Koyeb WEB + Neon serverless Postgres** (the Oracle attempt is archived under `.planning/phases/05-ship-it-live/oracle-attempt/`)
2. Neon-tuned asyncpg pool (`ssl='require'`, `statement_cache_size=0`, 240s lifetime), `sanitize_database_url`, aiohttp `/health` on `0.0.0.0:8000`, de-Oracle'd Dockerfile, stdout logging
3. `clear_persisted()` gap closure on idle-leave / reconnect-failure (DEPLOY-06), reconnect-race hardening (DEPLOY-04), TZ-correct late-night roast via `ZoneInfo(STREAK_TIMEZONE)` (D-06)
4. `docs/DEPLOY-KOYEB.md` + a 22-check live-UAT runbook — **24/7 deploy PARKED behind the YouTube datacenter-IP block; bot runs on the user's PC (residential IP) → Neon Singapore on demand**

### Phase 6 — Speed & Caching ✅ COMPLETE
Generation-guarded next-track prefetch (zero inter-song gap), Postgres `resolution_cache` (URL-bypass), 3-PP SponsorBlock→FFmpegExtractAudio→ModifyChapters chain + codec-path logging, download-timeout→stream fallback, LFU cache eviction (protects in-use), `PerfMetrics` in `/stats`.

### Phase 7 — Player UX & Filters ✅ COMPLETE
Persistent 5-button `NowPlayingView`, `/seek` `/previous` `/jump`, four `/filter` presets (opus-passthrough preserved for non-filtered tracks), `user_favorites` + JSONB `user_playlists`.

### Phase 8 — Social & Ops ✅ COMPLETE
`/roast @user` (Gemini-personalized, template fallback, `AllowedMentions.none()`), per-guild `/leaderboard`, owner-only `/stats`, degraded-but-always-200 `/health`, `total_errors` tracking.

### Phase 9 — Reliability & Ops Hardening ✅ COMPLETE
Truthful `/health` (degraded-503, `_ready_done`-guarded), fire-and-forget failure surfacing via `make_task`, un-wedgeable `on_ready` watchdog + `_sync_retry_active`-guarded startup-sync recovery, config-driven DB query timeouts, bounded YouTube search/extract self-heal. *(Live-runtime UAT parked behind the host.)*

### Phase 10 — Critical-Path Test Coverage ✅ COMPLETE
Extracted decision logic into pure `logic/` modules (`playback`, `health`, `roasts`, later `autoqueue`/`skip_stats`) locked by ~83 mock-free unit tests with three named scar regressions; full-suite-green + clean-boot regression gate.

### Phase 11 — RAG Long-Term Memory ✅ COMPLETE
`pgvector` on Neon + `gemini-embedding-001` @ 768d on a separate 60 RPM limiter; full read (recall/rerank/floor) + write (remember/dedup/cap-evict) halves, sensitivity/PII + numbers-from-SQL accuracy firewall, callback roasts at four surfaces, daily decay sweep. **Zero new infra.** *(Live-runtime UAT parked behind the host.)*

### Phase 12 — Richer Music/UX ✅ COMPLETE
Per-server `/jam` shared playlists, `/skips` analytics, LRCLIB third lyrics fallback, token-set auto-queue hallucination validation (`logic/autoqueue.py`).

> **Milestone status:** v1.0 (Phases 1–4), v1.1 "Live & Lethal" (Phases 5–8), and v1.2 "Sharper & Smarter" (Phases 9–12) all shipped (code) & archived — tags `v1.0`/`v1.1`/`v1.2`. Next: **v1.3 (planning)**. The 24/7 live deploy + the Phase 03–06/09/11 live-runtime UAT tail remain **parked** behind an always-on residential host. See `.planning/PROJECT.md` + `.planning/STATE.md` for authoritative current state.

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
10. **Cache cleanup must run — unchecked cache will fill the host's ephemeral disk (512MB cap, LFU eviction)**
11. **Embeddings use the SEPARATE 60 RPM limiter — never the shared 15 RPM chat budget (RAG memory must not starve `/ask`)**
12. **Memory is roast ammo, not a number source — hard numbers in output come from live SQL, never from embedded facts (accuracy firewall)**

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

**Phases 9–12 (reliability, tests, RAG memory, richer UX):**
- **`/health` degraded check is guarded by `_ready_done`** — without it the endpoint reports false-degraded during legitimate startup before MusicCog loads (Pitfall 3). `HEALTH_STRICT_STATUS` env-toggles 503-vs-200 so a deploy can opt out without a code change (D-01)
- **`asyncio.TimeoutError` must be caught BEFORE generic `except Exception`** in `on_ready`/DB handlers — in Python 3.11+ `TimeoutError` is a subclass of `Exception`; asyncpg client-side timeout raises `TimeoutError`, not `QueryCanceledError` (REL-04)
- **`_sync_retry_active` module-level bool** guards against multiple READY shards spawning concurrent sync-retry chains; `first_run` sync failure logs + closes (no running loop to retry into) (Pitfall 5 / REL-03)
- **`_play_track` create_task calls stay bare `asyncio.create_task`** — they handle failures internally; a `make_task` callback there would double-log track errors (Pitfall 4). Use `make_task` only for genuine fire-and-forget (prefetch, auto-queue, auto-lyrics)
- **YouTube self-heal reuses the existing `update_ytdlp()` + `_UPDATE_THROTTLE_SECONDS`** path — no second update path; `_is_transient_ytdlp_error` returns False only for `ExtractorError.expected=True` (conservative: treat unknown errors as transient) (D-08)
- **`logic/` is the pure-logic seam** — Discord/process glue dispatches on the returned enum/verdict (e.g. `TrackEndAction`); do NOT mirror the branch logic back in the caller (D-02). Phase 11's rerank/dedup follow the same clock-injectable, keyword-only, mock-free convention
- **pgvector codec registers per-connection via `create_pool(init=...)`** — a per-connection codec, NOT a prepared statement, so `statement_cache_size=0` is a verified non-issue. `CREATE EXTENSION IF NOT EXISTS vector;` must run FIRST in `SCHEMA_SQL` (extension-first boot)
- **Accuracy firewall (Phase 11):** never embed SQL-known numbers (counts/streaks); the distillation gate strips sensitive/PII content, and hard numbers in a roast come from live SQL — memory supplies the *episode*, SQL supplies the *number* (Critical Rules 5/12)
- **Memory callback cadence gate is per-surface** (`random.random() < MEMORY_CALLBACK_CHANCE`) — an occasional stat×episode payoff, not every roast; `guild_id=''` is safe in `_build_roast_line` because ANN recall scopes to `user_id` only (D-04)
- **`strip_lrc_headers` runs BEFORE `sanitize_lyrics`** for LRCLIB — sanitize only handles HTML/@mentions, not LRC metadata lines; use LRCLIB `/api/search` (not `/api/get`) — robust to missing duration, returns a relevance-sorted array (Phase 12 Pitfalls 1/2)
- **Auto-queue hallucination check uses token-set containment, not `difflib`** — YouTube titles are longer than clean names, so a subset check is the semantically correct rejection test for a hallucinated track (`logic/autoqueue.py`, D-12)
