# Technology Stack

**Analysis Date:** 2026-06-01

## Languages

**Primary:**
- Python 3.11+ - Core bot implementation, all services and cogs

## Runtime

**Environment:**
- Python 3.11+ (required for async/await, type hints, pathlib)

**Package Manager:**
- pip (PyPI packages)
- Lockfile: requirements.txt (pinned major versions)

## Frameworks

**Core:**
- discord.py 2.3.0+ - Discord bot framework, slash commands, voice client, audio playback
- asyncio - Built-in Python async I/O library for event loop management

**Audio:**
- FFmpeg (external binary) - Audio codec processing (opus encoding at 192kbps), stream handling
- yt-dlp - YouTube video search, metadata extraction, audio download
- davey - DAVE voice encryption for secure Discord voice transmission

**Database:**
- aiosqlite - Async SQLite client, single-file database at `data/dexter.db`

**AI/APIs:**
- google-genai (Google GenAI SDK) - Gemini 2.5-flash API for chat and Imagen 3 image generation

**Utilities:**
- python-dotenv - Load `.env` file for environment variables (DISCORD_TOKEN, GEMINI_API_KEY, GENIUS_TOKEN)
- PyNaCl - Cryptographic library (dependency for discord.py voice)

**Testing:**
- pytest - Test runner
- pytest-asyncio - Pytest plugin for async test support

## Key Dependencies

**Critical:**
- discord.py 2.3.0+ - Foundation for all Discord interactions, slash commands, voice playback, permissions
- yt-dlp - YouTube integration; actively maintained, subject to breakage requiring auto-update (daily at 4am)
- aiosqlite - User tracking, song history, mood state, image generation logging
- google-genai - AI chat responses, music recommendations, image generation

**Infrastructure:**
- FFmpeg (external) - Audio transcoding to opus; must be installed and in system PATH
- asyncio - Python's native async runtime; all services are async-first

## Configuration

**Environment:**
- `.env` file (git-ignored) — loads at bot startup via `load_dotenv()` in `bot.py:25`
- Location: `C:\Users\James\Desktop\Projects\dexter\.env`
- Critical variables:
  - `DISCORD_TOKEN` - Bot authentication token (required, exits if missing)
  - `GEMINI_API_KEY` - Google Gemini API key for /ask and /imagine (optional; AI features disabled if missing)
  - `GENIUS_TOKEN` - Genius API key for lyrics (future Phase 3)
  - `OWNER_ID` - Discord user ID of bot owner (parsed in `config.py:53`)
  - `ERROR_LOG_CHANNEL_ID` - Discord channel for error logging (parsed in `config.py:50`)

**Build:**
- `config.py` - Single file, no database config, loaded at runtime
  - All configurable constants: music limits, cache size, cooldowns, AI models, logging levels
  - Path objects for cache and logs directories
  - No secrets stored (only `.env` references)

## Platform Requirements

**Development:**
- Python 3.11+ interpreter
- FFmpeg installed and in system PATH
- pip and git for dependency management
- Discord Developer Portal: bot token, slash commands enabled, intents configured (message_content, voice_states, members, guilds)

**Production:**
- Oracle Cloud free tier ARM VM (always-on hosting)
- Python 3.11+ runtime
- FFmpeg binary
- 2GB minimum for audio cache (`AUDIO_CACHE_MAX_MB = 2048`)
- `/var/log/dexter/` directory for file logging (if hosting on Linux)

## Async Architecture

**Event Loop Model:**
- Single-threaded async event loop (discord.py, asyncio)
- Blocking operations (yt-dlp, database, FFmpeg) run in thread pool via `run_in_executor()`
- No background processes; tasks via `@tasks.loop()` in `cogs/events.py`

**Rate Limiting:**
- Gemini API: 15 requests per minute (RPM), global rate limiter in `services/gemini.py:34-86`
- Priority-based: user commands (priority 1) wait for slot, background tasks (priority 2) error if wait > 10s

## Data Persistence

**SQLite:**
- File: `data/dexter.db` (auto-created on first run)
- Schema: 6 tables (user_profiles, song_history, user_artist_counts, image_generation_log, bot_daily_stats)
- Async operations via aiosqlite; row factory for dict-like access

**File Cache:**
- Directory: `data/cache/` (opus audio files `{video_id}.opus`)
- Max size: 2GB, cleanup by oldest last-access time (hourly)

**Logging:**
- File logs: `logs/dexter.log` (INFO+, daily rotation, 14-day retention), `logs/error.log` (ERROR+, weekly, 30-day retention)
- Discord error channel: private channel for API errors, disconnects, unhandled exceptions

---

*Stack analysis: 2026-06-01*
