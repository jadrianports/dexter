# Dexter Phase 1 MVP — Design Spec

**Date:** 2026-04-12
**Scope:** Phase 1 of 4 — Music bot MVP with core playback, queue management, and database tracking.

---

## Overview

Rearchitect the existing "Bobbert" prefix-command music bot into "Dexter" — a slash-command-driven Discord music bot with a layered architecture, persistent database, audio caching, and a clean foundation for Phase 2 (AI/personality) and beyond.

**What Phase 1 delivers:** A fully functional music bot with YouTube search/playback, per-server queues, audio caching, database tracking, and slash commands. No AI, no personality, no roasts — just solid music infrastructure.

**What Phase 1 does NOT deliver:** Gemini AI chat, image generation, personality system, unprompted roasts, lyrics, status rotation, /history command. These come in Phases 2-3.

---

## Architecture Decisions

These were decided during brainstorming and apply across all phases:

1. **Structure: Grow into the spec** — Only create files each phase actually uses. The CLAUDE.md structure is the north star but files earn their place.
2. **Service wiring: Bot attributes** — Services initialized in `bot.py`, attached as `bot.youtube_service`, `bot.audio_service`, etc. Cogs access via `self.bot`.
3. **Commands: Pure slash commands** — `app_commands` only. No prefix commands, no hybrid. Guild sync during dev, owner `/sync` command for production.
4. **Channel behavior: Respond anywhere** — No designated channel restriction. Admin config option to restrict comes later.
5. **SDK: `google-genai`** — The new SDK (not deprecated `google-generativeai`). Free tier confirmed. Used starting Phase 2.
6. **Image gen: Gemini native** — `gemini-2.5-flash-image` with `response_modalities=['IMAGE']`. Phase 2.
7. **Lyrics: `lyricsgenius`** — Primary lyrics source via Genius API. Phase 3.
8. **No `/volume` command** — Discord's per-user volume slider covers this. Enables FFmpegOpusAudio passthrough for cached files (less CPU).
9. **Deployment: Local during Phases 1-3** — Oracle Cloud free tier deployment deferred to Phase 4 or whenever ready to go 24/7.

---

## File Structure

```
dexter/
├── bot.py                    # Entry point, bot init, service wiring, cog loading
├── config.py                 # All settings (music, cooldowns, cache, etc.)
├── database.py               # SQLite init, schema creation, query helpers
├── cogs/
│   ├── music.py              # All music slash commands
│   └── help.py               # /help command
├── services/
│   ├── youtube.py            # yt-dlp wrapper: search, download, metadata
│   └── audio.py              # FFmpeg audio source, cache management
├── models/
│   └── queue.py              # Per-server MusicQueue + Track dataclasses
├── utils/
│   ├── embeds.py             # Now playing, queue, error embed builders
│   ├── formatters.py         # Duration formatting, progress bars
│   └── logger.py             # File logging setup
├── tests/
│   ├── test_queue.py         # MusicQueue unit tests
│   ├── test_youtube.py       # YouTubeService tests (mocked yt-dlp)
│   ├── test_audio.py         # AudioService cache logic tests
│   ├── test_database.py      # Schema + query tests (in-memory SQLite)
│   └── test_formatters.py    # Pure function tests
├── data/
│   └── cache/                # Downloaded audio files ({video_id}.opus)
├── logs/                     # Log files (created at runtime)
├── requirements.txt
├── .env.example              # Template: DISCORD_TOKEN (only key needed for Phase 1)
└── .gitignore
```

14 production files + 5 test files. Every file has a job.

---

## Bot Entry Point (`bot.py`)

Responsibilities:
1. Load `.env` via `python-dotenv`
2. Create `commands.Bot` with required intents
3. Initialize services (`YouTubeService`, `AudioService`)
4. Attach services as bot attributes
5. Initialize database (create tables if not exist)
6. Load cogs (`music`, `help`)
7. Start background tasks (idle voice check, cache cleanup)
8. Owner-only `/sync` command for slash command registration

### Intents (Phase 1)

- `guilds` — server info
- `voice_states` — voice join/leave detection, auto-leave logic
- `message_content` — not used in Phase 1 but enabled now. This is a privileged intent that requires Discord approval if the bot goes public (75+ servers). Applying for it at bot creation is trivial; adding it later means waiting on Discord review.

### First-Run Sync

Slash commands don't exist until synced. The `/sync` command is itself a slash command. To solve this chicken-and-egg problem:

- `bot.py` accepts a `--first-run` CLI flag with an optional `--guild <ID>` argument
- On first run with `--guild`: syncs to that guild (instant, for dev). Without `--guild`: syncs globally (up to 1hr propagation).
- After syncing, the bot exits. Every subsequent boot: no auto-sync, use `/sync` command manually.

During development: sync to the test guild (instant). In production: global sync via `/sync` (up to 1 hour propagation).

---

## Configuration (`config.py`)

All settings in one file. No database config.

```python
# Music
MAX_SONG_DURATION_SECONDS = 900       # 15 min
MAX_PLAYLIST_IMPORT = 50
AUDIO_QUALITY = "192"                 # kbps opus
AUDIO_CACHE_DIR = "data/cache"
AUDIO_CACHE_MAX_MB = 2048            # 2GB
IDLE_TIMEOUT_SECONDS = 600           # 10 min before auto-leave
DOWNLOAD_TIMEOUT_SECONDS = 10
SEARCH_RESULTS_COUNT = 5

# Logging
LOG_DIR = "logs"                     # Relative to project root. Change to /var/log/dexter/ on Oracle VM.
LOG_LEVEL = "INFO"
LOG_RETENTION_DAYS = 14

# Cooldowns
PLAY_COOLDOWN_SECONDS = 2
SKIP_COOLDOWN_SECONDS = 2
HELP_COOLDOWN_SECONDS = 5
```

Config values that exist in CLAUDE.md but aren't needed until later phases (AI, roasts, mood, image gen) are NOT included here. They'll be added when their features are built.

---

## Database (`database.py`)

SQLite via `aiosqlite`. Schema created on startup.

### Phase 1 Tables

```sql
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    total_songs_queued INTEGER DEFAULT 0,
    first_seen_at TEXT DEFAULT (datetime('now')),
    last_active_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS song_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT,
    url TEXT NOT NULL,
    duration_seconds INTEGER,
    queued_at TEXT DEFAULT (datetime('now')),
    was_skipped BOOLEAN DEFAULT 0,
    was_auto_queued BOOLEAN DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_history_guild ON song_history(guild_id, queued_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_user ON song_history(user_id, queued_at DESC);

CREATE TABLE IF NOT EXISTS user_artist_counts (
    user_id TEXT NOT NULL,
    artist TEXT NOT NULL,
    play_count INTEGER DEFAULT 1,
    PRIMARY KEY (user_id, artist)
);

CREATE TABLE IF NOT EXISTS bot_daily_stats (
    date TEXT PRIMARY KEY,
    total_commands INTEGER DEFAULT 0,
    total_songs_played INTEGER DEFAULT 0,
    total_ai_queries INTEGER DEFAULT 0,
    total_images_generated INTEGER DEFAULT 0
);
```

### Design Notes

- `user_artist_counts` is denormalized (derivable from `song_history` via GROUP BY). Kept for fast "top N artists" queries that will fire on every `/ask` in Phase 2.
- `bot_daily_stats` tracks counters that feed the mood system in Phase 2. We start incrementing `total_commands` and `total_songs_played` now so there's data when mood is implemented.
- `image_generation_log` table is NOT created in Phase 1. Added with `/imagine` in Phase 2.
- `datetime('now')` is SQLite-specific. Acceptable for now since we're staying on SQLite through Phase 3. If the PostgreSQL migration in Phase 4 needs it, we'll handle defaults in application code at that point.
- `artist` field is best-effort from YouTube metadata (unreliable). Extraction strategy: check `artist` field first, fall back to `uploader`, fall back to `None`.

### Query Helpers

`database.py` exposes async helper functions, not raw SQL in cogs:
- `log_song(guild_id, user_id, title, artist, url, duration)`
- `update_artist_count(user_id, artist)`
- `update_user_profile(user_id, username)`
- `increment_daily_stat(field_name)`
- `get_db()` for direct access when helpers aren't enough

---

## Queue Model (`models/queue.py`)

```python
@dataclass
class Track:
    video_id: str              # YouTube video ID (cache key)
    title: str
    artist: str | None         # best-effort from metadata
    url: str                   # permanent YouTube URL (NOT stream URL)
    duration_seconds: int
    requested_by: int          # Discord user ID
    was_auto_queued: bool      # always False in Phase 1

class LoopMode(Enum):
    OFF = "off"
    SINGLE = "single"
    QUEUE = "queue"

class MusicQueue:
    guild_id: int
    tracks: list[Track]
    current_index: int         # position in tracks list
    loop_mode: LoopMode
    is_playing: bool
    is_paused: bool
```

### Key Design Choices

- **`current_index` instead of popping** — enables `/replay` (reset index), `/previous` (decrement), loop modes (wrap around), and future `/history` (look behind current_index).
- **`Track.url` is the permanent YouTube URL**, not a stream URL. Stream URLs expire after hours. The actual playable source (cached file or fresh stream URL) is resolved at play time by `AudioService`, not at queue time.
- **Queue logic lives in `MusicQueue` methods** — `add()`, `skip()`, `previous()`, `shuffle()`, `clear()`, `get_current()`, `get_next()`. Cogs call these methods; the model handles index math and loop wrapping.

### Skip + Loop Interaction

Skip ALWAYS advances to the next track regardless of loop mode. `LoopMode.SINGLE` only re-triggers on natural song end (FFmpeg `after` callback), not on manual skip. This matches the expected UX of every major music bot.

### Shuffle Scope

`shuffle()` only shuffles tracks after `current_index`. Already-played tracks and the current track are untouched. "Shuffle what's coming up."

---

## Services

### YouTubeService (`services/youtube.py`)

Wraps yt-dlp. Three core methods:

**`search(query, count=5)`**
- Text search, returns lightweight result objects (title, video_id, url, duration, thumbnail)
- Uses `extract_flat: True` for fast results (sub-second vs 3-5 seconds without it)
- No full metadata extraction — just enough for the select menu

**`extract(url)`**
- Full metadata extraction for a single video
- Returns everything needed to build a `Track`
- Detects livestreams (duration is None) and rejects them

**`download(video_id, url)`**
- Downloads audio to `data/cache/{video_id}.opus`
- Uses FFmpeg postprocessor: extract audio, opus codec, 192kbps
- 10-second timeout. Returns file path on success, None on failure.

```python
SEARCH_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'extract_flat': True,
    'default_search': 'ytsearch5',
}

DOWNLOAD_OPTS = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'opus',
        'preferredquality': '192',
    }],
    'outtmpl': 'data/cache/%(id)s.%(ext)s',
    'quiet': True,
    'no_warnings': True,
    'noplaylist': True,
}
```

### AudioService (`services/audio.py`)

Manages FFmpeg playback and audio cache. Depends on `YouTubeService` (passed at init for download and stream URL re-extraction).

**`get_source(track)`**
- Check cache: `data/cache/{video_id}.opus`
- Cache hit: return `FFmpegOpusAudio` (opus passthrough, no re-encoding, low CPU)
- Cache miss: attempt download via `YouTubeService.download()`
  - Download succeeds: return `FFmpegOpusAudio` from cached file
  - Download fails/timeout: call `YouTubeService.extract()` for fresh stream URL, return `FFmpegPCMAudio` (stream fallback)

**`cleanup_cache()`**
- Check total size of `data/cache/`
- If over `AUDIO_CACHE_MAX_MB`: delete files by oldest last-access time until under limit
- Runs hourly as background task

### Audio Format Strategy

- **Cached files → `FFmpegOpusAudio`**: Opus passthrough. No decode/re-encode. Minimal CPU. Possible because we download as opus and Discord voice uses opus internally.
- **Stream fallback → `FFmpegPCMAudio`**: Stream URLs aren't pre-encoded opus, so FFmpeg must decode. Slightly more CPU, but this path is the exception.
- **No `PCMVolumeTransformer`**: `/volume` was removed. Discord's per-user volume slider handles volume client-side.

---

## Music Pipeline

```
/play <query or URL>
  → defer() immediately
  → Is input a URL? (starts with http/youtube.com/youtu.be)
    → YES: extract info directly, skip to validation
    → NO: search YouTube via yt-dlp (5 results, extract_flat)
      → Post Select menu (discord.py View with dropdown)
      → User picks from dropdown (3-min timeout)
      → Timeout: dismiss with message
  → Validate: reject if duration > 15 min OR livestream (no duration)
  → Create Track (stores permanent URL, NOT stream URL)
  → Add to server's MusicQueue
  → Bot not in voice? → join requesting user's voice channel
  → Bot in different channel? → stay put, queue the song, play from current channel
  → Nothing playing? → start playback:
    → AudioService.get_source(track) — resolves cached file or stream
    → FFmpeg → Discord voice
    → Register after-callback for auto-advance
  → Post now playing embed
  → Log to database (song_history, user_artist_counts, user_profiles, bot_daily_stats)
```

### Playback Chain

When a track ends naturally (FFmpeg `after` callback):
1. Check loop mode:
   - `SINGLE`: replay same track (re-resolve source, restart)
   - `QUEUE`: increment index, wrap to 0 if at end
   - `OFF`: increment index, stop if at end
2. If next track exists: `AudioService.get_source()` → play
3. If queue exhausted: post "end of queue" message, remain in voice (idle timer handles leave)

---

## Slash Commands

| Command | Args | Cooldown | Notes |
|---------|------|----------|-------|
| `/play` | `query: str` | 2s | Two-step with select menu for text searches. Direct queue for URLs. |
| `/skip` | — | 2s | Advances regardless of loop mode. |
| `/pause` | — | — | — |
| `/resume` | — | — | — |
| `/stop` | — | — | Clears queue, leaves voice. |
| `/queue` | — | 2s | Paginated embed (10 per page, Previous/Next buttons). |
| `/shuffle` | — | 2s | Shuffles upcoming tracks only. |
| `/loop` | `mode: off\|single\|queue` | — | Discord shows choices as dropdown. |
| `/nowplaying` | — | 2s | Shows current song embed. |
| `/replay` | — | 2s | Restarts current track from beginning. |
| `/help` | — | 5s | Lists all commands with descriptions. |
| `/sync` | `guild_id: str (optional)` | — | Owner-only. Hidden from /help. |

---

## Now Playing Embed

Persistent message — edited when the song changes. If edit fails (rate limit), send a new one.

```
+--------------------------------------+
| Now Playing                          |
|                                      |
| Blinding Lights - The Weeknd         |
| Duration: 3:20                       |
| --------- 1:45 / 3:20               |
|                                      |
| Requested by: jake                   |
| Loop: Off                            |
+--------------------------------------+
| [thumbnail]                          |
+--------------------------------------+
```

Fields: title, artist, duration, progress bar, requested by, loop mode, YouTube thumbnail.

Lyrics snippet and `/lyrics` footer come in Phase 3 when lyrics are implemented.

---

## Edge Cases

| Case | Handling |
|------|----------|
| Bot disconnects mid-song | Catch via `on_voice_state_update`. Reconnect to same channel, restart current track from beginning. 3 attempts, then post error and clear. No position resume in Phase 1. |
| Song > 15 min | Reject at queue time with message. |
| Livestream URL | Detect via `duration is None`. Reject with message. |
| Voice channel empties | 10-min idle timer. Bot alone for 10 min → auto-leave, clear queue, post farewell. |
| Same song 3+ times/day | Logged in song_history. Roast trigger comes Phase 3. |
| Playlist URL > 50 songs | Truncate to 50, inform user how many were cut. |
| yt-dlp download fails | Retry once → fall back to stream URL → stream fails → post error. |
| FFmpeg process orphan | Explicit `voice_client.cleanup()` on skip/stop/error/leave. |
| User not in voice | Reject with message. |
| Bot in different channel | Stay put, queue the song, play from current channel. |
| Select menu timeout | 3-minute timeout. Dismiss message. |
| Paused and abandoned | Counts as idle. 10-min timer still applies. If user is still in channel, bot stays. |

---

## Background Tasks

| Task | Interval | Behavior |
|------|----------|----------|
| Idle voice check | 60s | Per guild: if bot is alone in voice OR nothing playing and no users, increment idle counter. At 10 min → auto-leave, clear queue, post farewell. Any user activity resets timer. |
| Cache cleanup | 1 hour | Check `data/cache/` total size. If over 2GB, delete by oldest last-access time until under limit. |

Not in Phase 1: status rotation (Phase 3), yt-dlp auto-update (Phase 3), daily stats reset (Phase 2).

---

## Logging

File logging only. Discord error channel comes Phase 2.

- Python `logging` module, configured in `utils/logger.py`
- Output: `{LOG_DIR}/dexter.log` (default `logs/dexter.log`, configurable for Oracle deploy)
- Level: INFO
- Format: `[2026-04-12 14:30:00] [INFO] [music] User jake queued "Blinding Lights" in guild 123456`
- Daily rotation, 14-day retention
- Errors also print to console during development

---

## Testing Strategy

### Automated (pytest + pytest-asyncio)

| Layer | What's tested | Approach |
|-------|--------------|----------|
| MusicQueue model | add, skip, previous, shuffle, loop wrapping, clear, empty queue edge cases | Pure unit tests, no IO |
| YouTubeService | Search result parsing, extract field handling, duration filtering | Mock yt-dlp responses |
| AudioService | Cache hit/miss logic, cleanup threshold, path construction | Mock filesystem |
| Database | Schema creation, all query helpers, constraint enforcement | Real SQLite in-memory (`:memory:`) |
| Formatters | Duration formatting, progress bar rendering | Pure function assertions |

Cogs are NOT unit tested. Mocking Discord interactions is brittle and low-value. Manual testing covers the integration layer.

### Manual (friend's server)

Phase 1 checklist:
- [ ] `/play` with YouTube URL — queues and plays immediately
- [ ] `/play` with search text — shows 5 results, selection works
- [ ] `/play` select menu timeout (wait 3 min) — dismissed gracefully
- [ ] `/skip` during playback — advances to next track
- [ ] `/skip` with loop SINGLE — still advances (doesn't re-loop)
- [ ] `/pause` and `/resume` — work correctly
- [ ] `/stop` — clears queue, bot leaves voice
- [ ] `/queue` — shows correct list
- [ ] `/queue` with 10+ songs — pagination works
- [ ] `/shuffle` — upcoming tracks randomized, current keeps playing
- [ ] `/loop off/single/queue` — all three modes behave correctly
- [ ] `/nowplaying` — shows current song embed
- [ ] `/replay` — restarts current track from beginning
- [ ] `/help` — shows all commands
- [ ] Play a 20-min video — rejected
- [ ] Paste a livestream URL — rejected
- [ ] Everyone leaves voice — bot leaves after ~10 min
- [ ] Playlist URL — queues up to 50, truncation message shown
- [ ] Play from different voice channel than bot — bot stays, song queues
- [ ] `/play` while not in any voice channel — rejected
- [ ] Cache: play same song twice — second time uses cache (faster)
- [ ] `/sync` as non-owner — rejected or hidden

---

## Requirements

```
discord.py>=2.3.0
yt-dlp
aiosqlite
python-dotenv
pytest
pytest-asyncio
```

FFmpeg must be installed separately and on PATH.

---

## Environment Variables

`.env.example`:
```
DISCORD_TOKEN=
# GEMINI_API_KEY=     # Phase 2
# GENIUS_TOKEN=       # Phase 3
```

Only `DISCORD_TOKEN` is required for Phase 1.

---

## What Comes Next

- **Phase 2 (Personality + AI):** Gemini `/ask`, personality system prompts, user taste tracking, mood system, AI auto-queue, `/imagine`, cooldowns on all commands.
- **Phase 3 (Alive):** Unprompted roasts, voice event reactions, seasonal awareness, status rotation, `/lyrics`, `/history`, streak tracking, milestones.
- **Phase 4 (Scale):** Multi-server hardening, SQLite → PostgreSQL, sharding, Oracle Cloud deployment, queue persistence.

Each phase gets its own brainstorming → spec → plan → build → test cycle.
