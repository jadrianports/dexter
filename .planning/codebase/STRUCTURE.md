# Codebase Structure

**Analysis Date:** 2026-06-01

## Directory Layout

```
dexter/
├── bot.py                         # Entry point, bot setup, cog loading, background tasks
├── config.py                      # Centralized configuration and settings
├── database.py                    # SQLite schema, initialization, query helpers
│
├── cogs/                          # Command handlers (plugins)
│   ├── __init__.py
│   ├── music.py                   # /play, /skip, /pause, /resume, /stop, /queue, /shuffle, /loop, /nowplaying, /replay
│   ├── ai.py                      # /ask command, auto-queue logic
│   ├── imagine.py                 # /imagine command (image generation)
│   ├── help.py                    # /help command
│   └── events.py                  # Voice event listeners, message reactions, unprompted roasts
│
├── models/                        # Domain objects and in-memory state
│   ├── __init__.py
│   ├── queue.py                   # MusicQueue, Track, LoopMode (per-server playback state)
│   ├── server_state.py            # ServerState (per-guild mood, auto-queue tracking)
│   ├── message_buffer.py          # MessageBuffer (rolling 10-message chat history per channel)
│   └── user_profile.py            # get_user_summary() (read-only DB queries for taste summary)
│
├── services/                      # External API wrappers and I/O
│   ├── __init__.py
│   ├── youtube.py                 # YouTubeService (yt-dlp wrapper: search, extract, download, playlist)
│   ├── audio.py                   # AudioService (FFmpeg sources, cache management, cleanup)
│   ├── gemini.py                  # GeminiService (Google Gemini API + rate limiter)
│   └── lyrics.py                  # LyricsService (Genius + AZLyrics scraper, not Phase 1)
│
├── personality/                   # Bot voice and context injection
│   ├── __init__.py
│   ├── prompts.py                 # System prompts for Gemini (/ask, auto-queue, recommendations)
│   ├── responses.py               # Response template pools (error messages, roasts, announcements)
│   ├── seasonal.py                # Seasonal context injection (holidays, date-aware personality)
│   └── roasts.py                  # Unprompted roast logic (join/leave, repeat songs, streaks)
│
├── utils/                         # Utilities and helpers
│   ├── __init__.py
│   ├── embeds.py                  # Discord embed builders (now_playing, song_queued, queue_list, etc.)
│   ├── formatters.py              # Formatters (duration, progress bar, etc.)
│   ├── cooldowns.py               # Per-user cooldown tracking (if implemented separately)
│   └── logger.py                  # File + Discord logging setup
│
├── data/                          # Runtime data
│   ├── dexter.db                  # SQLite database (auto-created on first run)
│   └── cache/                     # Audio file cache ({video_id}.opus files)
│
├── logs/                          # Log files (auto-created)
│   ├── dexter.log                 # Main log (daily rotation, 14-day retention)
│   └── error.log                  # Error log (if separate handler configured)
│
├── tests/                         # Unit and integration tests
│   ├── __init__.py
│   ├── test_queue.py              # MusicQueue logic (skip, advance, shuffle, etc.)
│   ├── test_youtube.py            # YouTubeService (search, extract, URL detection)
│   ├── test_audio.py              # AudioService (cache, cleanup)
│   ├── test_message_buffer.py     # MessageBuffer (add, history, formatting)
│   ├── test_database.py           # Database queries (log_song, update_profile, etc.)
│   ├── test_gemini.py             # GeminiService (rate limiter, API calls)
│   ├── test_prompts.py            # Prompt building logic
│   ├── test_responses.py          # Response template selection
│   ├── test_formatters.py         # Duration/progress formatters
│   ├── test_server_state.py       # ServerState mood calculations
│   ├── test_seasonal.py           # Seasonal context injection
│   ├── test_user_profile.py       # User summary generation
│   ├── test_rate_limiter.py       # Rate limiter priority logic
│   ├── test_ai_helpers.py         # AI context gathering helpers
│   └── test_database_phase2.py    # Phase 2 schema tests
│
├── .env.example                   # Example environment variables (template)
├── requirements.txt               # Python dependencies (discord.py, yt-dlp, aiosqlite, etc.)
├── .gitignore                     # Git ignore patterns
├── .gitattributes                 # Git attributes
├── README.md                      # Project overview
├── CLAUDE.md                      # Build spec and implementation requirements
├── dexter-architecture.md         # Detailed design document (personality samples, rationale)
│
├── .claude/                       # Claude project metadata
│   ├── settings.local.json
│   └── ...
│
├── .planning/
│   └── codebase/                  # GSD codebase analysis documents
│       ├── ARCHITECTURE.md        # This file: system design, data flows, patterns
│       ├── STRUCTURE.md           # This file: directory layout, file locations
│       ├── CONVENTIONS.md         # Coding style and naming patterns
│       ├── TESTING.md             # Test structure and patterns
│       ├── STACK.md               # Tech stack and versions
│       ├── INTEGRATIONS.md        # External APIs and services
│       └── CONCERNS.md            # Technical debt and issues
│
└── .git/                          # Git repository
```

## Directory Purposes

**`bot.py`:**
- Purpose: Discord bot entry point and orchestrator
- Entry point for the application
- Contains: Bot creation, intents configuration, service wiring, cog loading, background tasks (idle check, cache cleanup)
- Key functions: `create_bot()`, `on_ready()`, `on_close()`, `sync_commands()`, `idle_check()`, `cache_cleanup()`, `main()`

**`config.py`:**
- Purpose: Single source of truth for all configuration
- Contains: Path definitions, music settings, cooldowns, rate limits, mood thresholds, logging config
- Pattern: All settings imported from here; no hardcoded values in cogs or services
- Key exports: `BASE_DIR`, `AUDIO_CACHE_DIR`, `LOG_DIR`, `MAX_SONG_DURATION_SECONDS`, `MOOD_*_THRESHOLD`, etc.

**`database.py`:**
- Purpose: SQLite schema initialization and async query helpers
- Contains: `SCHEMA_SQL` (CREATE TABLE statements), helper functions (`log_song()`, `update_user_profile()`, `get_mood()`, `get_recent_songs()`, etc.)
- Pattern: Pure async functions; no ORM; parameterized queries
- Initialized on bot startup via `on_ready()` → `init_db()`

**`cogs/music.py`:**
- Purpose: All music playback commands and the playback engine
- Commands: `/play`, `/skip`, `/pause`, `/resume`, `/stop`, `/queue`, `/shuffle`, `/loop`, `/nowplaying`, `/replay`, `/history`, `/lyrics`
- Classes: `MusicCog` (main cog), `SongSelect` (dropdown UI), `SongSelectView` (view wrapper), `QueuePageView` (pagination UI)
- Key methods:
  - `play()`: Slash command handler
  - `_queue_from_selection()`: Add song to queue after user picks from search results
  - `_play_track()`: Start audio playback with after-callback for track advancement
  - `_on_track_end()`: Handle track natural end, advance queue, trigger auto-queue if needed
  - `_ensure_voice()`: Validate user is in voice and connect bot if needed
  - `_get_text_channel()`: Locate text channel for bot messages
- State: Maintains per-guild `self.queues: dict[guild_id, MusicQueue]`

**`cogs/ai.py`:**
- Purpose: AI chat command and auto-queue logic
- Commands: `/ask`
- Classes: `AICog` (main cog)
- Key methods:
  - `ask()`: /ask command handler with context gathering
  - `try_auto_queue()`: Auto-queue logic when queue empties and humans in voice
  - `_log_error()`: Post error embeds to Discord error channel

**`cogs/imagine.py`:**
- Purpose: Image generation command
- Commands: `/imagine`
- Classes: `ImagineCog`
- Key methods: `imagine()` slash command handler, daily cap checking

**`cogs/help.py`:**
- Purpose: Help command
- Commands: `/help`
- Shows command list with descriptions

**`cogs/events.py`:**
- Purpose: Voice event listeners and unprompted behavior
- Listeners:
  - `on_voice_state_update()`: Voice join/leave events (trigger roasts)
  - `on_message()`: Add messages to MessageBuffer, emoji reactions
- Event patterns: 30% roast on join (5-min cooldown per user), special behavior at 1-5am, "goodnight" reactions, bot mention reactions

**`models/queue.py`:**
- Purpose: Per-server music queue state
- Classes:
  - `LoopMode(Enum)`: OFF, SINGLE, QUEUE
  - `Track`: Dataclass representing a queued song
  - `MusicQueue`: Stateful queue with playback logic
- Key methods: `add()`, `get_current()`, `skip()`, `advance()`, `previous()`, `shuffle()`, `clear()`
- State fields: `tracks` list, `current_index`, `loop_mode`, `is_playing`, `is_paused`, `_play_generation`, `_text_channel_id`, `_now_playing_message_id`

**`models/server_state.py`:**
- Purpose: Per-guild runtime state (not persisted)
- Classes: `ServerState` dataclass
- Fields: `guild_id`, `auto_queue_rounds`, `auto_queue_results` (track play/skip outcomes)
- Functions: `get_server_state()` (create-on-access), `get_mood()` (query DB to determine mood from command count)

**`models/message_buffer.py`:**
- Purpose: Rolling in-memory conversation history for AI context
- Classes: `MessageBuffer`
- Methods: `add()`, `get_history()`, `get_gemini_history()` (format for Gemini API), `clear()`
- Pattern: Dict of channel_id → deque (max 10 messages per channel)
- Not persisted to disk; cleared on bot restart

**`models/user_profile.py`:**
- Purpose: User taste summary generation (read-only queries)
- Functions: `get_user_summary()` (returns natural language summary from database)
- Used by: AI cog for context injection into system prompt

**`services/youtube.py`:**
- Purpose: yt-dlp wrapper for YouTube operations
- Classes: `YouTubeService`
- Methods:
  - `is_url()`: Check if query is URL
  - `search()`: YouTube search, return 5 results with metadata
  - `extract()`: Full metadata for single video
  - `extract_playlist()`: Extract entries from playlist (truncate to 50)
  - `download()`: Download audio to cache as opus file
  - `async_search()`, `async_extract()`, `async_download()`, `async_extract_playlist()`: Async wrappers using thread pool
- Options configs:
  - `SEARCH_OPTS`: For search queries (no extract_flat)
  - `PLAYLIST_OPTS`: For playlist extraction (extract_flat=True)
  - `EXTRACT_OPTS`: For single video metadata
  - `DOWNLOAD_OPTS`: For audio download (FFmpeg postprocessor for opus)

**`services/audio.py`:**
- Purpose: FFmpeg audio source management and cache cleanup
- Classes: `AudioService`
- Methods:
  - `get_source()`: 3-tier strategy (cache → download → stream fallback)
  - `cache_path()`: Compute cache file path
  - `is_cached()`: Check if file in cache
  - `cleanup_cache()`: Delete oldest files if total > 2GB
- Returns: `discord.AudioSource` objects (FFmpegOpusAudio or FFmpegPCMAudio)

**`services/gemini.py`:**
- Purpose: Google Gemini API wrapper with rate limiter
- Classes:
  - `GeminiService`: Main service class
  - `_RateLimiter`: Hybrid sliding-window rate limiter with priority support
- Exceptions:
  - `GeminiRateLimitError`: Priority 2 request rejected (wait > 10s)
  - `GeminiAPIError`: Network/API error
  - `GeminiRefusalError`: Content filtered
- Methods:
  - `chat()`: Send conversation to Gemini, acquire rate limit slot (priority-based)
  - `generate_image()`: Image generation via Imagen
- Rate limit: 15 RPM globally; priority 1 waits, priority 2 rejects if wait > 10s

**`services/lyrics.py`:**
- Purpose: Lyrics fetching (Genius API + AZLyrics fallback)
- Status: Not implemented in Phase 1
- Will contain: `LyricsService` class with Genius API wrapper and scraper

**`personality/prompts.py`:**
- Purpose: System prompt templates for Gemini
- Constants:
  - `DEXTER_SYSTEM_PROMPT`: Main chat system prompt (with placeholders for mood, user context, seasonal)
  - `MUSIC_RECOMMENDATION_PROMPT`: Prompt for auto-queue JSON response
  - `MOOD_CONTEXTS`: Dict mapping mood string → context text
- Functions: `build_chat_prompt()`, `build_recommendation_prompt()`

**`personality/responses.py`:**
- Purpose: Response template pools (error messages, roasts, announcements)
- Constants:
  - `RATE_LIMIT_MESSAGES`: Pool of rate limit error messages
  - `ERROR_MESSAGES`: Pool of general error messages
  - `AI_EMPTY_RESPONSE`: Pool of empty response fallbacks
  - `AUTO_QUEUE_ANNOUNCE`: Pool of auto-queue announcements
  - And more...
- Functions: `pick_random()` (select random from pool)

**`personality/seasonal.py`:**
- Purpose: Date-aware personality context
- Functions: `get_seasonal_context()` (check month/day, return seasonal message or empty string)
- Examples: Hates Christmas in Dec, reluctantly tolerates Halloween in Oct, roasts loneliness on Feb 14

**`personality/roasts.py`:**
- Purpose: Unprompted roast logic
- Status: Not yet implemented; design in CLAUDE.md
- Will contain: Functions for join roasts, repeat song roasts, milestone roasts, streak tracking

**`utils/embeds.py`:**
- Purpose: Discord embed builders
- Functions:
  - `now_playing()`: Embed for current track (title, artist, duration, progress, requested by, loop mode, thumbnail)
  - `song_queued()`: Embed for song added to queue (title, artist, duration, position)
  - `queue_list()`: Paginated queue list embed (10 tracks per page)
  - `error()`: Error embed (red, with error message)
  - And more...
- Pattern: Pure functions; return `discord.Embed` objects ready to send

**`utils/formatters.py`:**
- Purpose: String formatting utilities
- Functions:
  - `format_duration()`: Convert seconds to "MM:SS" or "HH:MM:SS"
  - `progress_bar()`: Elapsed/total progress bar (visual)
  - And more...

**`utils/logger.py`:**
- Purpose: Logging configuration
- Functions: `setup_logger()` (configure and return logger), `log_to_discord()` (post error embeds to Discord)
- Configuration: File handler (daily rotation, 14-day retention), console handler (development)
- Exported: `log` instance (used throughout codebase)

**`data/`:**
- Purpose: Runtime data storage
- Files:
  - `dexter.db`: SQLite database (auto-created on first startup via `init_db()`)
  - `cache/`: Audio file cache directory; files named `{video_id}.opus`
- Not committed to git (in `.gitignore`)

**`logs/`:**
- Purpose: Application logs
- Files: `dexter.log` (main), `error.log` (errors only if configured)
- Rotation: Daily, 14-day retention (default)
- Not committed to git

**`tests/`:**
- Purpose: Unit and integration tests
- Framework: pytest + pytest-asyncio
- Coverage: Models, services, utilities, personality, database
- Run: `pytest` or `pytest -v` or `pytest tests/test_queue.py` for specific test

## Key File Locations

**Entry Points:**
- `bot.py`: Main entry point (run with `python bot.py`)
- `bot.py:main()`: CLI argument parsing and startup
- `bot.py:on_ready()`: Service initialization (first call after bot connects)

**Configuration:**
- `config.py`: All settings (paths, timeouts, limits, API keys via env vars)
- `.env`: Runtime secrets (DISCORD_TOKEN, GEMINI_API_KEY, GENIUS_TOKEN)
- `.env.example`: Template for `.env`

**Core Logic:**
- `cogs/music.py`: Playback engine, queue management
- `cogs/ai.py`: Chat logic, auto-queue
- `services/youtube.py`: YouTube search/download
- `services/audio.py`: Audio playback, cache management
- `services/gemini.py`: AI API, rate limiting

**Database:**
- `database.py`: Schema and query helpers
- `data/dexter.db`: SQLite file (auto-created)

**Testing:**
- `tests/`: All test files (mirrors module structure)
- Run: `pytest` from project root

**Documentation:**
- `CLAUDE.md`: Build spec and implementation requirements
- `dexter-architecture.md`: Detailed design (personality, rationale, gotchas)
- `.planning/codebase/`: GSD analysis documents (ARCHITECTURE.md, STRUCTURE.md, etc.)

## Naming Conventions

**Files:**
- Module files: `snake_case.py` (e.g., `music.py`, `youtube.py`)
- Test files: `test_*.py` (e.g., `test_queue.py`)
- Config files: `config.py`, `.env`

**Directories:**
- Package directories: `lowercase` (e.g., `cogs`, `models`, `services`)
- Data directories: `lowercase` (e.g., `data`, `logs`, `cache`)
- Test directory: `tests`

**Python:**
- Classes: `PascalCase` (e.g., `MusicQueue`, `YouTubeService`, `MessageBuffer`)
- Functions: `snake_case` (e.g., `log_song()`, `get_recent_songs()`, `build_chat_prompt()`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `MAX_SONG_DURATION_SECONDS`, `MOOD_CONTEXTS`)
- Private: Leading underscore (e.g., `_play_track()`, `_RateLimiter`, `_idle_seconds`)

**Discord:**
- Slash commands: lowercase (e.g., `/play`, `/skip`, `/ask`, `/imagine`)
- Cog classes: `{Feature}Cog` (e.g., `MusicCog`, `AICog`)

## Where to Add New Code

**New Slash Command:**
1. Create handler in appropriate cog file (`cogs/{feature}.py`)
2. If new feature area, create `cogs/{feature}.py` with class `{Feature}Cog`
3. Add `@app_commands.command()` decorator
4. Load cog in `bot.py:on_ready()` → `await bot.load_extension(f"cogs.{feature}")`
5. Add tests in `tests/test_{feature}.py`

**New Service:**
1. Create file `services/{service}.py`
2. Define class `{Service}Service` with async methods
3. Instantiate and attach to bot in `bot.py:on_ready()` → `bot.{service}_service = ...`
4. Import in cogs and use via `self.bot.{service}_service`
5. Add tests in `tests/test_{service}.py`

**New Model:**
1. Create file `models/{model}.py`
2. Define dataclass or class
3. Import in cogs/services as needed
4. Add tests in `tests/test_{model}.py`

**Personality Content:**
1. Response templates/error messages: `personality/responses.py`
2. System prompts: `personality/prompts.py`
3. Seasonal logic: `personality/seasonal.py`
4. Roast logic: `personality/roasts.py` (when implemented)

**Utilities:**
1. Embed builders: `utils/embeds.py`
2. Formatters: `utils/formatters.py`
3. Cooldown tracking: `utils/cooldowns.py`
4. Logging setup: `utils/logger.py`

**Database:**
1. Schema: Update `SCHEMA_SQL` in `database.py` (CREATE TABLE statements)
2. Query helpers: Add async functions in `database.py` (e.g., `async def query_thing(...) -> ...`)
3. Tests: Add tests in `tests/test_database*.py`

**Configuration:**
1. New settings: Add to `config.py` (top-level constants)
2. Source from env vars if secrets (e.g., `int(os.getenv("VAR_NAME", "default"))`)
3. Reference in code as `config.SETTING_NAME`

## Special Directories

**`data/`:**
- Purpose: Runtime data (database, audio cache)
- Generated: Yes, on first run
- Committed: No (in `.gitignore`)
- Structure: `dexter.db`, `cache/{video_id}.opus`

**`logs/`:**
- Purpose: Application logs
- Generated: Yes, on first log message
- Committed: No (in `.gitignore`)
- Retention: 14 days (configurable via config.LOG_RETENTION_DAYS)

**`tests/`:**
- Purpose: Unit/integration tests
- Committed: Yes
- Pattern: `test_{module}.py` mirrors `{module}.py`

**`.planning/codebase/`:**
- Purpose: GSD analysis documents
- Generated: By gsd-map-codebase
- Committed: Yes
- Documents: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, STACK.md, INTEGRATIONS.md, CONCERNS.md

**`.claude/`:**
- Purpose: Claude project metadata and configuration
- Committed: Yes (`.claude/settings.local.json`, scripts, agents)
- Not for production use

---

*Structure analysis: 2026-06-01*
