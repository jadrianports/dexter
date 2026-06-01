# External Integrations

**Analysis Date:** 2026-06-01

## APIs & External Services

**Discord:**
- Discord API (via discord.py 2.3.0+) - Bot presence, slash commands, voice channel management, member info, guild state
  - Client: discord.py built-in
  - Auth: DISCORD_TOKEN environment variable
  - Intents: message_content, voice_states, members, guilds (all required)
  - Rate limit: Standard Discord 429 handling (backoff + retry)

**YouTube:**
- YouTube content platform - Music search, metadata extraction, audio streaming
  - SDK/Client: yt-dlp (YoutubeDL class)
  - Auth: None required (scrapes publicly available data)
  - Implementation: `services/youtube.py`
    - Search: 5 results returned via `YouTubeService.search()` (SEARCH_OPTS)
    - Extract: Full metadata + duration validation via `YouTubeService.extract()`
    - Playlist: Up to 50 songs extracted via `YouTubeService.extract_playlist()` (PLAYLIST_OPTS)
    - Download: Audio to `.opus` cache via FFmpeg post-processor (DOWNLOAD_OPTS)
  - Failure handling: Daily auto-update at 4am, retry on failure, fallback to stream, error logging

**Gemini API:**
- Google Generative AI - Chat responses (/ask), music recommendations (auto-queue), image generation (/imagine)
  - SDK/Client: google-genai (genai.Client)
  - Auth: GEMINI_API_KEY environment variable
  - Models:
    - `gemini-2.5-flash` - Chat and text generation (15 RPM limit, shared global)
    - `gemini-2.5-flash-image` - Image generation via Imagen (also 15 RPM limit)
  - Implementation: `services/gemini.py`
    - Rate limiter: `_RateLimiter` class with priority support (user=1, background=2)
    - Chat: `GeminiService.chat()` with system prompt + conversation history
    - Image: `GeminiService.generate_image()` with prompt
  - Exceptions: GeminiRateLimitError (429), GeminiAPIError, GeminiRefusalError
  - Async: `aio.models.generate_content()` for non-blocking API calls

**Genius (Lyrics) - Planned Phase 3:**
- Genius.com lyrics - Song lyric fetching and display
  - SDK/Client: Custom HTTP (not yet implemented)
  - Auth: GENIUS_TOKEN environment variable (required)
  - Implementation: `services/lyrics.py` (file does not exist yet; planned)
  - Fallback: AZLyrics web scrape if Genius fails

## Data Storage

**Databases:**
- SQLite (local file-based)
  - Connection: `data/dexter.db` (auto-created)
  - Client: aiosqlite (async)
  - Schema:
    - `user_profiles` - User ID, username, total songs queued, first/last seen
    - `song_history` - Per-guild/user song logs with skip status and auto-queue flag
    - `user_artist_counts` - Artist play counts per user (for taste tracking)
    - `image_generation_log` - Image generation audit (user, prompt, timestamp)
    - `bot_daily_stats` - Daily command counts, mood system state
  - Implementation: `database.py` (async query helpers)

**File Storage:**
- Local filesystem cache only (no cloud storage)
  - Directory: `data/cache/`
  - Format: opus audio files (`{video_id}.opus`)
  - Management: Hourly cleanup (oldest-first eviction when > 2GB)
  - Implementation: `services/audio.py:67-89`

**Caching:**
- None (no Redis/Memcached; only in-memory state and file cache)

## Authentication & Identity

**Auth Provider:**
- Discord token-based (no OAuth; bot uses long-lived token)
  - Implementation: `bot.py:26` loads DISCORD_TOKEN from .env
  - Scopes: Implicit from intents (message_content, voice_states, members, guilds)

**User Identification:**
- Discord user IDs (snowflake format, string in database)
- Server/Guild IDs for multi-server isolation
- Owner ID: `config.py:53` (OWNER_ID env var, required for /sync command)

## Monitoring & Observability

**Error Tracking:**
- Discord error log channel (optional)
  - Channel ID: ERROR_LOG_CHANNEL_ID environment variable
  - Implementation: `utils/logger.py` (log_to_discord function)
  - Logged errors: yt-dlp failures, Gemini API errors, rate limit hits, disconnects, unhandled exceptions
  - Format: Discord embed with error type, traceback, timestamp

**Logs:**
- File-based logging
  - Location: `logs/` directory (auto-created)
  - Files:
    - `dexter.log`: INFO+ level, daily rotation, 14-day retention
    - `error.log`: ERROR+ level, weekly rotation, 30-day retention
  - Implementation: `utils/logger.py` (log.info, log.error, exc_info=True)
  - Format: Structured logging with component names

## CI/CD & Deployment

**Hosting:**
- Oracle Cloud free tier ARM VM (always-on)
- Command execution: Python 3.11+ interpreter, FFmpeg binary

**CI Pipeline:**
- None (not detected in codebase)
- Deployment: Manual push to production
- Command sync: `--first-run --guild` flag or `/sync` owner slash command for syncing commands

## Environment Configuration

**Required env vars:**
- `DISCORD_TOKEN` - Bot authentication (required; exits if missing)
- `GEMINI_API_KEY` - Gemini API key (optional; AI features disabled if missing)

**Optional env vars:**
- `GENIUS_TOKEN` - Genius API key for lyrics (Phase 3, not used yet)
- `OWNER_ID` - Bot owner Discord user ID (optional, defaults to "0")
- `ERROR_LOG_CHANNEL_ID` - Discord channel for error logging (optional)

**Secrets location:**
- `.env` file (git-ignored, not in repo)
- Loaded via python-dotenv at bot startup
- Never committed; template would be `.env.example` (if present)

## Rate Limiting & Quotas

**Gemini API:**
- Hard limit: 15 requests per minute (shared across /ask and /imagine)
- Soft limit: If rate limiter calculates wait > 10s for priority 2 (background), error is raised instead
- Implementation: Hybrid sliding-window in `services/gemini.py:34-86`

**Discord API:**
- Standard Discord rate limits (enforced by discord.py)
- Slash command cooldowns (per-user, configured in cogs):
  - /play: 2s
  - /ask: 5s
  - /imagine: 30s

**yt-dlp:**
- YouTube rate limiting (handled by yt-dlp internally)
- Download timeout: 10 seconds (fallback to stream if exceeded)

**Image Generation:**
- Daily cap: 10 images per user per day (enforced in cogs/imagine.py)

## Webhooks & Callbacks

**Incoming:**
- None (slash commands only, no webhook endpoints)

**Outgoing:**
- None (no outbound webhook notifications)

## Data Flow: Request Paths

**Music Playback (/play):**
1. User slash command → `cogs/music.py` (interaction handler)
2. URL detection → `services/youtube.py:57-59` (is_url check)
3. If URL: `youtube.py:91-114` (extract metadata)
4. If search: `youtube.py:66-89` (search YouTube, return 5 results)
5. User selects song → Duration validation → Cache check → `audio.py:43-66` (get source)
6. Download or stream → FFmpeg audio source → Discord voice playback
7. Logging: `database.py:70-101` (song_history, user_profiles, user_artist_counts)

**AI Chat (/ask):**
1. User slash command → `cogs/ai.py` (defer interaction)
2. Context gathering: message buffer (last 10), user profile, mood, seasonal
3. Build system prompt → `personality/prompts.py`
4. Call `services/gemini.py:99-160` (rate-limited chat)
5. Post response → Update message buffer
6. Log: `database.py:120-138` (daily command count)

**Image Generation (/imagine):**
1. User slash command → `cogs/imagine.py` (defer interaction)
2. Check: cooldown, daily cap
3. Call `services/gemini.py:162-201` (rate-limited image generation)
4. Extract image bytes → Send to Discord
5. Log: `database.py:171-184` (image_generation_log)

---

*Integration audit: 2026-06-01*
