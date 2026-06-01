<!-- refreshed: 2026-06-01 -->
# Architecture

**Analysis Date:** 2026-06-01

## System Overview

```text
┌─────────────────────────────────────────────────────────────────┐
│           Discord Bot (discord.py commands.Bot)                 │
│                      `bot.py`                                   │
├──────────────┬──────────────┬──────────────┬────────────────────┤
│   Music Cog  │   AI Cog     │ Imagine Cog  │  Events Cog        │
│ `cogs/music` │ `cogs/ai.py` │`cogs/imagine`│ `cogs/events.py`   │
│ /play, /skip │ /ask, auto-q │ /imagine     │ message_buffer     │
│ /queue, etc  │              │              │ listeners          │
└────┬─────────┴──────┬───────┴──────┬───────┴────────┬───────────┘
     │                │              │                │
     ▼                ▼              ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Models & State                             │
│  `models/queue.py`  `models/server_state.py`                   │
│  MusicQueue         ServerState (per-guild mood, auto-queue)   │
│  (per-server)       `models/message_buffer.py` (in-memory)     │
│                     `models/user_profile.py` (DB readers)      │
└────┬─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Services (I/O & External APIs)                  │
│  `services/youtube.py`  - yt-dlp wrapper (search, extract)     │
│  `services/audio.py`    - FFmpeg audio sources, cache mgmt      │
│  `services/gemini.py`   - Gemini API + rate limiter (chat, gen) │
│  `services/lyrics.py`   - Genius API wrapper                    │
└────┬─────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│              Personality & Utility Layers                       │
│  `personality/prompts.py` - System prompts for Gemini           │
│  `personality/responses.py` - Message templates                 │
│  `personality/seasonal.py` - Date-aware context                 │
│  `utils/embeds.py` - Discord embed builders                     │
│  `utils/formatters.py` - Duration, progress bars               │
│  `utils/logger.py` - File + Discord logging                     │
└──────────────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│              Persistent Storage                                 │
│  SQLite (aiosqlite) - `data/dexter.db`                          │
│  Audio cache - `data/cache/{video_id}.opus`                     │
│  Logs - `logs/dexter.log`, `logs/error.log`                     │
└─────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| MusicCog | Music commands, playback engine, queue management | `cogs/music.py` |
| AICog | /ask command, auto-queue logic, Gemini interaction | `cogs/ai.py` |
| ImagineCog | /imagine command, image generation, daily caps | `cogs/imagine.py` |
| EventsCog | Message listeners, context buffer feeding | `cogs/events.py` |
| MusicQueue | Queue state, loop modes, shuffle, track tracking | `models/queue.py` |
| ServerState | Per-guild mood, auto-queue round tracking | `models/server_state.py` |
| MessageBuffer | In-memory 10-message-per-channel conversation history | `models/message_buffer.py` |
| YouTubeService | Search, extract metadata, download, playlist handling | `services/youtube.py` |
| AudioService | Cache management, FFmpeg source creation, fallback streaming | `services/audio.py` |
| GeminiService | API calls, rate limiter, chat, image generation | `services/gemini.py` |
| Database | Schema, user profiles, song history, stats logging | `database.py` |

## Pattern Overview

**Overall:** Cog-based Discord.py architecture with layered services.

**Key Characteristics:**
- **Cog-based command organization**: Each major feature area (music, AI, events) is a separate cog loaded at startup
- **Service layer decoupling**: YouTube, Gemini, and audio functionality isolated in services with predictable APIs
- **Per-server queue model**: Each guild maintains its own MusicQueue instance for independent playback state
- **In-memory state for performance**: MessageBuffer (chat history) and ServerState (mood, auto-queue tracking) stored in bot memory, not persisted
- **Database as append-only log**: SQLite captures user behavior (song history, profiles, stats) for personality context
- **Async/await throughout**: All I/O (Discord, API calls, FFmpeg, database) is async to prevent blocking
- **Generation counters for race prevention**: _play_generation incremented on each track start to invalidate stale after-callbacks

## Layers

**Discord Interaction Layer (Cogs):**
- Purpose: Handle slash commands, manage user interactions, coordinate features
- Location: `cogs/` (music.py, ai.py, imagine.py, help.py, events.py)
- Contains: Command handlers, UI views (select menus, paginated buttons), event listeners
- Depends on: Models (queue, server_state, message_buffer), Services, Personality, Utils
- Used by: Discord.py framework; entry point for all user interactions

**Model Layer (In-Memory State):**
- Purpose: Represent domain objects (queue, user profile context, conversation history)
- Location: `models/` (queue.py, server_state.py, message_buffer.py, user_profile.py)
- Contains: Dataclasses, enum (LoopMode), state management logic
- Depends on: Config, Database (for user_profile queries)
- Used by: Cogs (to drive business logic)

**Service Layer (I/O & External APIs):**
- Purpose: Encapsulate external integrations and handle complex logic
- Location: `services/` (youtube.py, audio.py, gemini.py, lyrics.py)
- Contains: API wrappers, rate limiting, download/streaming logic, caching
- Depends on: Config, Logger, external libraries (yt-dlp, google.genai, aiosqlite)
- Used by: Cogs, other services (e.g., audio service uses youtube service)

**Database Layer:**
- Purpose: Persist user behavior and bot telemetry
- Location: `database.py`
- Contains: Schema definition, query helpers (log_song, update_user_profile, get_recent_songs, etc.)
- Depends on: aiosqlite, config
- Used by: Cogs, services (for context injection)

**Personality & Utility Layers:**
- Purpose: Consistent voice (prompts, response templates, seasonal context) and common helpers
- Location: `personality/` (prompts.py, responses.py, seasonal.py), `utils/` (embeds.py, formatters.py, logger.py)
- Contains: Prompt templates, message pools, formatting functions, embed builders
- Depends on: Config, external APIs (for prompt building)
- Used by: Cogs (to craft responses)

**Bot Orchestration:**
- Purpose: Service wiring, cog loading, background tasks, error handling
- Location: `bot.py`
- Contains: Bot initialization, on_ready handler, background loops (idle_check, cache_cleanup)
- Depends on: All layers
- Used by: Main entry point

## Data Flow

### Music Pipeline (Primary Request Path)

1. **User invokes /play** (`cogs/music.py:play()`)
   - Check user is in voice channel
   - Defer interaction (shows "thinking...")
   - Remember text channel for future messages

2. **Input validation** (`cogs/music.py:play()`)
   - If URL: extract directly OR handle playlist
   - If text: search YouTube via `YouTubeService.search()`
   - Return 5 results as Discord select menu

3. **User selects song** (SongSelect callback → `_queue_from_selection()`)
   - Extract metadata via `YouTubeService.async_extract()`
   - Validate duration ≤ 15 min, reject livestreams
   - Create Track object

4. **Add to queue** (`MusicQueue.add()`)
   - Append to `queue.tracks`
   - Return position for UI feedback

5. **Log to database** (`_log_track()`)
   - Insert into `song_history` table
   - Increment `user_artist_counts` for this artist
   - Upsert `user_profiles` record
   - Increment daily command/song count in `bot_daily_stats`

6. **Start playback if idle** (`_play_track()`)
   - Get audio source:
     1. Check `AudioService` cache (opus file exists?)
     2. Download via yt-dlp to cache (timeout 10s)
     3. Fallback: stream via re-extracted URL with FFmpeg
   - Increment `queue._play_generation` (invalidates old callbacks)
   - Create after-callback (advances to next track when this one ends)
   - Call `voice_client.play(source, after=callback)`

7. **Playback ends** (`after_callback` → `_on_track_end()`)
   - Check generation still matches (ignore stale callbacks)
   - Track if auto-queued song was played (not skipped)
   - Advance to next track via `queue.advance()` (respects SINGLE loop)
   - Edit existing now-playing embed or send new one
   - If queue empty + humans in voice: trigger auto-queue

### AI Pipeline (Chat & Auto-Queue)

#### /ask Command

1. **User invokes /ask** (`cogs/ai.py:ask()`)
   - Defer interaction
   - Gather context:
     - Mood from `bot_daily_stats` (normal/tired/exhausted/fumes)
     - User summary from `get_user_summary()` (top artists, repeat songs)
     - Seasonal context from `get_seasonal_context()`
     - Last 10 messages from `MessageBuffer` (per channel)

2. **Build system prompt** (`personality/prompts.py:build_chat_prompt()`)
   - Inject mood context
   - Inject user taste summary
   - Inject seasonal context (e.g., "it's December, you hate Christmas music")
   - Use template from `DEXTER_SYSTEM_PROMPT`

3. **Send to Gemini** (`GeminiService.chat()`)
   - Acquire rate limiter slot (priority 1 = user command, waits if needed)
   - Call `google.genai.chat()` with system prompt + conversation history
   - Handle rate limit errors, API errors

4. **Post response** (`cogs/ai.py:ask()`)
   - Send response to Discord
   - Add response to `MessageBuffer` for future context
   - Increment daily AI query count

#### Auto-Queue (When queue empties)

1. **Queue exhausted** (`cogs/music.py:_on_track_end()`)
   - Check if humans still in voice
   - Call `AICog.try_auto_queue(guild)`

2. **Gather recommendations** (`cogs/ai.py:try_auto_queue()`)
   - Fetch last 10-15 songs from this guild's session
   - Build JSON request with `build_recommendation_prompt()`
   - Send to Gemini with priority 2 (auto-queue can be rejected if wait > 10s)
   - Parse JSON response: 3 song suggestions (title, artist)
   - Mark ServerState round counter + cap at 3 rounds

3. **Search & queue** 
   - For each suggestion: search YouTube, get first result
   - Create Track with `was_auto_queued=True`
   - Add to queue
   - Track play/skip outcomes in ServerState for next auto-queue

4. **Resume playback**
   - Start playing first auto-queued song
   - If skipped: silently advance, show skip summary
   - If played: track outcome, reference on next auto-queue

### State Management

**Persistent (SQLite):**
- `user_profiles`: User ID, username, total songs queued, first/last seen
- `song_history`: Guild, user, title, artist, URL, duration, queued_at, skip flag, auto_queue flag
- `user_artist_counts`: Per-user artist play counts (for taste summary)
- `image_generation_log`: Image generation requests (tracking daily cap)
- `bot_daily_stats`: Daily aggregates (command count, mood lookup)

**In-Memory (bot.memory, not persisted):**
- `bot.server_states: dict[guild_id, ServerState]` — per-guild mood lookup, auto-queue round tracking
- `bot.message_buffer: MessageBuffer` — last 10 messages per channel, cleared on bot restart
- `MusicQueue` per guild — queue state, loop mode, current index, generation counter

## Key Abstractions

**Track:**
- Purpose: Immutable representation of a queued song
- Examples: `models/queue.py` line 17-27
- Pattern: Dataclass with video_id, title, artist, URL, duration, requested_by, was_auto_queued flag, thumbnail

**MusicQueue:**
- Purpose: Per-server queue state with loop logic (OFF, SINGLE, QUEUE)
- Examples: `models/queue.py` line 30-114
- Pattern: Stateful model with index math, advance/skip semantics, persistent message ID tracking

**LoopMode (Enum):**
- Purpose: Type-safe loop states
- Examples: `models/queue.py` line 10-13
- Pattern: Enum for OFF, SINGLE, QUEUE

**GeminiService:**
- Purpose: Unified Gemini API layer with hybrid rate limiter
- Examples: `services/gemini.py`
- Pattern: Service wrapper with priority-based rate limiting (priority 1 waits, priority 2 rejects)

**AudioService:**
- Purpose: Cache-first audio source strategy with fallback
- Examples: `services/audio.py`
- Pattern: Deterministic source selection (cache → download → stream)

**YouTubeService:**
- Purpose: Unified yt-dlp interface with separate opts for search/playlist/extract/download
- Examples: `services/youtube.py`
- Pattern: URL detection, search/extract/download with distinct YoutubeDL configs

## Entry Points

**Bot Entry:**
- Location: `bot.py:main()`
- Triggers: `python bot.py` or `python bot.py --first-run [--guild GUILD_ID]`
- Responsibilities: Parse args, start bot or sync commands and exit

**First Run:**
- Location: `bot.py:first_run()`
- Triggers: `--first-run` flag
- Responsibilities: Load cogs, sync slash commands, exit

**Service Initialization:**
- Location: `bot.py:on_ready()`
- Triggers: Bot connected to Discord
- Responsibilities: Create database connection, wire services, load cogs, start background tasks

**Music Command:**
- Location: `cogs/music.py:play()`, `skip()`, `pause()`, `resume()`, `stop()`, `queue()`, etc.
- Triggers: Slash command invocation
- Responsibilities: Validate input, trigger playback/queue operations, send embeds

**AI Command:**
- Location: `cogs/ai.py:ask()`
- Triggers: `/ask` slash command
- Responsibilities: Gather context, call Gemini, post response

**Image Command:**
- Location: `cogs/imagine.py:imagine()`
- Triggers: `/imagine` slash command
- Responsibilities: Check daily cap, call Gemini image gen, post image

**Message Events:**
- Location: `cogs/events.py:on_message()`
- Triggers: Any non-bot message in Discord
- Responsibilities: Add message to channel's MessageBuffer

## Architectural Constraints

- **Threading:** Single-threaded event loop (discord.py). Blocking I/O (yt-dlp, FFmpeg) offloaded to thread pool via asyncio.run_in_executor() or built-in async methods. after-callbacks run in bot event loop thread via asyncio.run_coroutine_threadsafe().

- **Global state:** 
  - `bot.queues: dict[guild_id, MusicQueue]` — mutable per-guild queue state, shared across cogs
  - `bot.server_states: dict[guild_id, ServerState]` — mutable per-guild mood/auto-queue state
  - `bot.message_buffer: MessageBuffer` — mutable in-memory message history, shared across cogs
  - `GeminiService._RateLimiter` — global shared rate limiter (asyncio.Lock + deque)

- **Circular imports:** None detected. Cogs import services; services do not import cogs. Models used throughout; no circular dependencies.

- **Rate limiting:** Global Gemini rate limiter enforces 15 RPM (configured via GEMINI_RPM_LIMIT). Priority 1 (user commands) waits for a slot; priority 2 (auto-queue) rejects if wait > 10s.

- **Database transactions:** All writes are auto-committed (aiosqlite default). No multi-statement transactions in code.

- **Concurrency safety:** MessageBuffer and ServerState dict access is not explicitly locked; assumes single-threaded event loop. MusicQueue access is per-guild and cog-internal (safe by design).

## Anti-Patterns

### Direct YouTube Search Before URL Check

**What happens:** Earlier versions might have searched for every query without checking if it's a URL first.
**Why it's wrong:** Wasting API calls on obvious URLs; slower user experience.
**Do this instead:** Always call `YouTubeService.is_url()` first (`services/youtube.py` line 57-59); only search if not a URL.

### Using `extract_flat: True` in Search Opts

**What happens:** Setting extract_flat=True (used for playlist extraction) in general search options breaks pagination.
**Why it's wrong:** yt-dlp returns flat entries without webpage_url for individual search results.
**Do this instead:** Use SEARCH_OPTS without extract_flat (`services/youtube.py` line 17-22) for search; reserve PLAYLIST_OPTS with extract_flat=True for playlist extraction only.

### Calling `voice_client.stop()` Before `_play_track()`

**What happens:** The old after-callback fires immediately after stop, before _play_generation increments, causing double-play race.
**Why it's wrong:** Old callback sees new generation already incremented; it plays the wrong track or replays current.
**Do this instead:** Let _play_track() handle stopping internally. It increments generation first, then stops, then plays. See `cogs/music.py` line 187-191.

### Not Respecting HTTP 3s Interaction Timeout

**What happens:** Long-running operations complete after interaction.response.defer() expires, causing followup send to fail silently.
**Why it's wrong:** User sees "thinking..." forever; response never arrives.
**Do this instead:** Always defer immediately (`interaction.response.defer()`), then use `interaction.followup.send()` for async work. See `cogs/music.py` line 327, `cogs/ai.py` line 53.

## Error Handling

**Strategy:** Layered error handling with graceful degradation.

**Patterns:**
- **yt-dlp failures:** Log warning, attempt auto-update, retry, fallback to stream, then raise if unrecoverable. Skipped tracks summarized in single message.
- **Gemini rate limit:** Reject priority 2 requests immediately with GeminiRateLimitError; show personality error message to user.
- **Gemini API error:** Log error, post personality error message to Discord, also send embed to error log channel (if configured).
- **Audio source unavailable:** Silently skip track, recurse to next; post skip summary at end.
- **FFmpeg process orphans:** Explicit `voice_client.stop()` before disconnect ensures cleanup.
- **Interaction response failures:** Retry with fallback message if first attempt fails; catch and log exceptions.

## Cross-Cutting Concerns

**Logging:** 
- File logging via `utils/logger.py`: daily rotation, 14-day retention, INFO level default
- Discord error channel: posts critical errors, rate limits, API failures (if ERROR_LOG_CHANNEL_ID configured)
- All I/O operations and commands logged with context (guild, user, track, etc.)

**Validation:**
- Duration cap: reject songs > 900s (15 min)
- Livestreams: reject (no duration returned by yt-dlp)
- Playlist import: truncate to 50 tracks
- Gemini rate limit: 15 RPM global, priority-based queuing
- Image generation daily cap: 10 per user per day
- User input: sanitized in Discord embeds, no injection risks

**Authentication:**
- Discord token: env var DISCORD_TOKEN, checked on startup
- Gemini API key: env var GEMINI_API_KEY, optional (AI features disabled if missing)
- Genius token: env var GENIUS_TOKEN (for future /lyrics feature)

---

*Architecture analysis: 2026-06-01*
