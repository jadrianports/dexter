# Dexter Phase 2 — Personality + AI Design Spec

## Overview

Phase 2 adds AI chat, image generation, personality, and supporting infrastructure to the Dexter Discord bot. Built on top of the Phase 1 music MVP.

**Build stages:**
1. AI/Personality — Gemini integration, /ask, prompts, mood, user profiling, auto-queue
2. Image Generation — /imagine with Imagen via Gemini
3. Infrastructure — cooldowns (global error handler), Discord error log channel

**Architecture approach:** Layered orchestration. Each module has one job. Cogs orchestrate: gather context -> prompt builder -> Gemini service -> post result. Matches the existing Phase 1 pattern where cogs orchestrate services.

---

## Decisions Made

| Decision | Choice | Alternatives (future reference) |
|----------|--------|---------------------------------|
| Channel strategy | Reply in channel where command was used (C) | Per-server designated channel via `/setchannel` + SQLite `server_config` table (B) |
| Rate limiter | Hybrid sliding window (C) | Strict queue (A): all requests wait in line; Optimistic with backoff (B): send immediately, catch 429s and retry |
| Auto-queue cap | 3 consecutive rounds / 9 songs (B) | No limit (A); Cap then ask in chat (C) |
| Rate limiter priority | User commands first (B) | FIFO (A) |
| Error log channel | Environment variable (A) | Future multi-server: A for bot-wide errors (always), C via `/seterrorlog` + SQLite for per-server admin notifications |
| Ignored memory | In-memory per session | Could reconstruct from `song_history` (`was_auto_queued` + `was_skipped`) if persistence needed later |
| Image captions | Static pool from responses.py | Could use Gemini API call for contextual captions (costs 1 RPM per image) |

---

## New Files

```
cogs/ai.py              # /ask command, auto-queue logic
cogs/imagine.py          # /imagine command
cogs/events.py           # on_message listener (message buffer), future Phase 3 events
services/gemini.py       # Gemini API wrapper + rate limiter
models/user_profile.py   # User taste summary queries
models/message_buffer.py # Rolling 10-message context per channel
models/server_state.py   # Per-server runtime state (mood lookup, auto-queue tracking)
personality/prompts.py   # System prompts, mood contexts, prompt builders
personality/responses.py # Static personality response pools
personality/seasonal.py  # Date-aware personality context
```

## Modified Files

```
bot.py                   # Wire new services/cogs, global error handler
config.py                # Add AI/image/mood/roast settings
database.py              # New query helpers
cogs/music.py            # Auto-queue trigger in _on_track_end, skip tracking
cogs/help.py             # Add /ask and /imagine to help text
requirements.txt         # Add google-genai
```

---

## Component Designs

### 1. Gemini Service (`services/gemini.py`)

Thin wrapper around the `google-genai` SDK. Two public methods:

```python
class GeminiService:
    async def chat(self, system_prompt: str, conversation: list[dict], priority: int = 1) -> str
    async def generate_image(self, prompt: str, priority: int = 1) -> bytes | None
```

- `chat()` takes a fully-assembled system prompt and conversation history, sends to Gemini, returns the text response. Truncates to `MAX_AI_RESPONSE_LENGTH` (500 chars).
- `generate_image()` takes a prompt, calls Imagen 3 via the Gemini API, returns image bytes or `None` if refused/empty.
- Both go through the rate limiter before calling the API.
- Both raise typed exceptions:
  - `GeminiRateLimitError` — 429 or sliding window full
  - `GeminiAPIError` — network/server errors
  - `GeminiRefusalError` — content filtered or empty response

**Rate limiter** (`_RateLimiter`, private class):
- Sliding window: `collections.deque` of timestamps, max 15 entries
- `async def acquire(priority: int)` — priority 1 = user commands, priority 2 = auto-queue/background
- Under limit: record timestamp, return immediately
- At limit: calculate wait time until oldest timestamp exits the 60s window
  - Priority 1: wait (up to 60s max)
  - Priority 2: if wait > 10s, raise `GeminiRateLimitError` instead of blocking
- Uses `asyncio.Lock` to prevent race conditions on concurrent acquire calls

**Wiring:** Created in `bot.py on_ready()`, attached as `bot.gemini_service`.

### 2. Personality Prompts (`personality/prompts.py`)

Pure functions. No API calls, no database access.

```python
DEXTER_SYSTEM_PROMPT = """..."""  # Full template from architecture doc
MUSIC_RECOMMENDATION_PROMPT = """..."""  # JSON format template
MOOD_CONTEXTS = { "normal": "...", "tired": "...", "exhausted": "...", "fumes": "..." }

def build_chat_prompt(mood: str, user_summary: str | None, seasonal: str) -> str
def build_recommendation_prompt(recent_songs: list[dict]) -> str
def build_image_caption_prompt(original_prompt: str) -> str
```

- `build_chat_prompt()` fills the `DEXTER_SYSTEM_PROMPT` template with mood context, user taste summary, and seasonal context.
- `build_recommendation_prompt()` fills the `MUSIC_RECOMMENDATION_PROMPT` template with recent songs.
- `build_image_caption_prompt()` reserved for future use (static captions for now).

### 3. Personality Responses (`personality/responses.py`)

Static string pools for non-AI personality responses. Each pool is a list; callers pick one at random.

```python
RATE_LIMIT_MESSAGES: list[str]        # "google is throttling me again. give me a sec."
AUTO_QUEUE_ANNOUNCE: list[str]        # "fine. since nobody else is stepping up..."
AUTO_QUEUE_CAP_REACHED: list[str]     # "i've been carrying this voice channel for 9 songs..."
IMAGE_REFUSAL_MESSAGES: list[str]     # "yeah no. i'm not doing that."
IMAGE_CAP_MESSAGES: list[str]         # "you've used up all your imagination for today."
ERROR_MESSAGES: list[str]             # Generic personality errors
AI_EMPTY_RESPONSE: list[str]          # "i had a thought but it left. try again."
```

### 4. Seasonal Context (`personality/seasonal.py`)

```python
def get_seasonal_context() -> str
```

Pure function. Returns seasonal context string based on current month/day. Returns empty string if no seasonal context applies. Covers: December (Christmas dread), October (Halloween), Feb 14, Jan 1, Apr 1.

### 5. Message Buffer (`models/message_buffer.py`)

In-memory rolling context per channel.

```python
class MessageBuffer:
    def add(self, channel_id: int, role: str, author: str, content: str) -> None
    def get_history(self, channel_id: int) -> list[dict]
    def clear(self, channel_id: int) -> None
```

- Internal storage: `dict[int, deque[dict]]` — channel ID to deque with `maxlen=10`
- Each entry: `{"role": "user"|"model", "author": "display_name", "content": "...", "timestamp": datetime}`
- `get_history()` returns entries formatted for the google-genai SDK conversation format (verify exact format via context7 during implementation)
- Created in `bot.py on_ready()`, attached as `bot.message_buffer`
- Fed by `events.py` `on_message` listener (non-bot messages) and `ai.py` (bot responses after /ask)

### 6. User Profile (`models/user_profile.py`)

Read-only query module. Generates taste summaries from existing tables.

```python
async def get_user_summary(db, user_id: str) -> str | None
```

- Queries `user_profiles`, `user_artist_counts`, `song_history`
- Returns natural language summary: top 5 artists, total songs, most repeated song, skip rate
- Returns `None` if user has no history

### 7. Server State (`models/server_state.py`)

Per-server runtime state.

```python
class ServerState:
    guild_id: int
    auto_queue_rounds: int = 0
    auto_queue_results: dict  # {"played": 0, "skipped": 0}

async def get_mood(db) -> str
async def get_daily_command_count(db) -> int
```

- `get_mood()` queries `bot_daily_stats` for today's `total_commands`, maps to mood string via config thresholds
- `ServerState` stored in `bot.server_states: dict[int, ServerState]`, initialized as empty dict in `bot.py on_ready()`
- `get_server_state(guild_id)` helper function creates on access (same pattern as `MusicCog.get_queue()`)
- `auto_queue_rounds` resets to 0 when a human uses `/play`
- `auto_queue_results` tracks skip rate for "ignored" memory feedback

### 8. `/ask` Command (`cogs/ai.py`)

```
/ask <question>  — 5s cooldown
```

Flow:
1. `await interaction.response.defer()`
2. Gather context: mood, user summary, seasonal, message buffer history
3. `build_chat_prompt(mood, user_summary, seasonal)` -> system prompt
4. `await gemini_service.chat(system_prompt, conversation, priority=1)`
5. `await interaction.followup.send(response)`
6. Add response to message buffer
7. Increment daily stats (`total_commands`, `total_ai_queries`)

Error handling:
- `GeminiRateLimitError` -> random message from `RATE_LIMIT_MESSAGES`
- `GeminiAPIError` -> random `ERROR_MESSAGES` + log to error channel
- Empty response -> random `AI_EMPTY_RESPONSE`

### 9. Auto-Queue (`cogs/ai.py`)

Triggered by `music.py` `_on_track_end()` at the exact point where `queue.advance()` returns `None` (no next track) — before setting `is_playing = False`. Conditions: humans still in voice channel AND `auto_queue_rounds < 3`.

Flow:
1. Query last 10 songs from `song_history` for this guild
2. `build_recommendation_prompt(recent_songs)`
3. `await gemini_service.chat(prompt, [], priority=2)` — low priority
4. Parse JSON response (strip markdown fences, `json.loads()`)
5. For each of 3 suggestions: search YouTube, build Track with `was_auto_queued=True`
6. Add to queue, start playback
7. Post personality announcement (check previous `auto_queue_results` for "ignored" memory commentary)
8. Increment `auto_queue_rounds`

JSON parse failure: log error, post personality message, let idle timeout take over.

Cap reached (round 3 done, no human interaction): post cap message from `AUTO_QUEUE_CAP_REACHED`, stop auto-queuing.

`auto_queue_rounds` resets to 0 when any human uses `/play`.

### 10. `/imagine` Command (`cogs/imagine.py`)

```
/imagine <prompt>  — 30s cooldown
```

Flow:
1. Check daily cap: query `image_generation_log` for user today. If >= 10, reject with `IMAGE_CAP_MESSAGES`.
2. `await interaction.response.defer()`
3. `await gemini_service.generate_image(prompt, priority=1)`
4. If `None`: post random `IMAGE_REFUSAL_MESSAGES`
5. If bytes: create `discord.File` from bytes, pick caption from static pool, post
6. Log to `image_generation_log`
7. Increment daily stats (`total_images_generated`, `total_commands`)

### 11. Cooldowns (Global Error Handler in `bot.py`)

```python
@bot.tree.error
async def on_app_command_error(interaction, error):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"slow down. try again in {error.retry_after:.0f}s.",
            ephemeral=True
        )
```

Single handler covers all commands. No per-command cooldown code.

### 12. Error Log Channel (`utils/logger.py`)

```python
async def log_to_discord(bot, embed: discord.Embed) -> None
```

- Reads `ERROR_LOG_CHANNEL_ID` from config (sourced from `.env`)
- If not set or channel not found: silently skips
- Called from: Gemini errors, yt-dlp failures, unhandled exceptions

### 13. Events Cog (`cogs/events.py`)

Minimal for Phase 2 — just the `on_message` listener for the message buffer:

```python
@commands.Cog.listener()
async def on_message(self, message):
    if message.author.bot:
        return
    self.bot.message_buffer.add(
        channel_id=message.channel.id,
        role="user",
        author=message.author.display_name,
        content=message.content,
    )
```

Phase 3 will add voice event roasts, reactions, idle messages, etc. to this cog.

---

## Database Changes

No new tables. New query helpers in `database.py`:

```python
async def mark_song_skipped(db, guild_id: str, url: str) -> None
    # Marks the most recent song_history entry matching guild_id + url as skipped.
    # Uses most recent queued_at to find the right row (no song_id needed from caller).

async def get_recent_songs(db, guild_id: str, limit: int = 10) -> list[dict]
    # Returns last N songs for a guild, ordered by queued_at DESC.
    # Used by auto-queue to build recommendation prompt.

async def get_images_today(db, user_id: str) -> int
    # Counts image_generation_log entries for user where generated_at is today.
    # Used by /imagine for daily cap check.

async def get_daily_command_count(db) -> int
    # Returns total_commands from bot_daily_stats for today's date.
    # Returns 0 if no row exists yet. Used by mood system.
```

---

## Config Additions (`config.py`)

```python
# --- AI ---
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_RPM_LIMIT = 15
MAX_AI_RESPONSE_LENGTH = 500
ASK_COOLDOWN_SECONDS = 5

# --- Image Generation ---
IMAGINE_COOLDOWN_SECONDS = 30
MAX_IMAGES_PER_USER_PER_DAY = 10

# --- Mood System ---
MOOD_NORMAL_THRESHOLD = 15
MOOD_TIRED_THRESHOLD = 30
MOOD_EXHAUSTED_THRESHOLD = 50

# --- Auto-Queue ---
AUTO_QUEUE_MAX_ROUNDS = 3
AUTO_QUEUE_SONGS_PER_ROUND = 3

# --- Error Logging ---
ERROR_LOG_CHANNEL_ID = int(os.getenv("ERROR_LOG_CHANNEL_ID", "0")) or None
```

## .env Additions

```
GEMINI_API_KEY=
ERROR_LOG_CHANNEL_ID=
```

## requirements.txt Addition

```
google-genai
```

---

## Cross-Cog Communication

```
music.py _on_track_end()
  -> bot.cogs.get("AICog")
  -> if AICog exists and conditions met: trigger auto-queue
  -> if AICog not loaded (no Gemini key): silently skip

music.py /skip
  -> if current track has was_auto_queued=True:
     -> calls mark_song_skipped(db, guild_id, url)
     -> increments ServerState.auto_queue_results["skipped"]

music.py /play
  -> resets ServerState.auto_queue_rounds to 0

events.py on_message
  -> feeds bot.message_buffer
```

---

## Epiphanies & Implementation Warnings

1. **`was_skipped` column exists but nothing writes to it.** Phase 1's `/skip` command never updates `song_history.was_skipped`. Phase 2 must add a `mark_song_skipped()` helper and call it from `/skip` for auto-queued tracks. Without this, "ignored" memory has no data.

2. **Cross-cog auto-queue trigger.** `music.py`'s `_on_track_end` calls `bot.cogs.get("AICog")` — same pattern as `idle_check` calling `bot.cogs.get("MusicCog")`. Must handle the case where `AICog` isn't loaded (missing Gemini key) by silently skipping.

3. **google-genai SDK conversation format.** The SDK uses `{"role": "user"|"model", "parts": [{"text": "..."}]}`, NOT `{"role": ..., "content": ...}` like OpenAI. Verify exact format via context7 during implementation.

4. **`on_message` listener ordering.** The `events.py` cog will have an `on_message` listener for the message buffer. Since we use slash commands (not prefix commands), there's no conflict with discord.py's internal message processing. But verify during implementation.

5. **Auto-queue JSON parsing.** Gemini may return markdown-wrapped JSON (` ```json ... ``` `), extra commentary, or malformed output. Always strip fences and handle parse failures gracefully.

---

## Build Stages

### Stage 1: AI/Personality Core
- `services/gemini.py` (API wrapper + rate limiter)
- `personality/prompts.py` (system prompts, mood contexts)
- `personality/responses.py` (static response pools)
- `personality/seasonal.py` (date context)
- `models/message_buffer.py` (rolling context)
- `models/user_profile.py` (taste summaries)
- `models/server_state.py` (mood, auto-queue state)
- `cogs/events.py` (on_message for buffer)
- `cogs/ai.py` (/ask command)
- `database.py` additions (new query helpers)
- `config.py` additions (AI settings)
- `bot.py` changes (wire new services/cogs)
- Tests for all new modules

### Stage 2: Image Generation
- `cogs/imagine.py` (/imagine command)
- `services/gemini.py` addition (generate_image method)
- `config.py` additions (image settings)
- `bot.py` changes (load imagine cog)
- Tests for imagine flow

### Stage 3: Infrastructure
- `bot.py` global cooldown error handler
- `utils/logger.py` addition (log_to_discord)
- `config.py` additions (error channel)
- `cogs/music.py` changes (auto-queue trigger, skip tracking)
- `cogs/help.py` update (add /ask, /imagine)
- Wire error logging into all error paths
- Tests for error handling

---

## Testing Strategy

### Unit Tests (pytest)
- `tests/test_prompts.py` — prompt builders produce correct output with various inputs
- `tests/test_seasonal.py` — seasonal context returns correct strings for various dates
- `tests/test_message_buffer.py` — buffer respects maxlen, formats for SDK correctly
- `tests/test_user_profile.py` — taste summary generation from mock DB data
- `tests/test_server_state.py` — mood mapping, auto-queue round tracking
- `tests/test_rate_limiter.py` — sliding window logic, priority handling
- `tests/test_responses.py` — response pools are non-empty, pick_random works
- `tests/test_database_phase2.py` — new query helpers (mark_skipped, recent_songs, images_today, daily_count)
- `tests/test_gemini.py` — service with mocked API calls, error handling
- `tests/test_imagine.py` — daily cap check, refusal handling

### Manual Tests (for user)
- `/ask` with various questions — verify personality, mood awareness, seasonal context
- `/ask` rapidly to trigger rate limiter — verify personality rate limit message
- Play songs, then `/ask "what have I been listening to"` — verify user taste context
- Let queue empty with people in voice — verify auto-queue fires, posts message
- Let auto-queue run 3 rounds — verify cap message, auto-queue stops
- Skip all auto-queued songs, trigger auto-queue again — verify "ignored" memory comment
- `/play` during auto-queue streak — verify `auto_queue_rounds` resets
- `/imagine` with normal prompt — verify image + caption
- `/imagine` with inappropriate prompt — verify refusal message
- `/imagine` 11 times in a day — verify daily cap rejection
- Rapid command spam — verify cooldown messages are personality-flavored
- Check error log channel receives errors (disconnect Gemini key temporarily)
- `/ask` a genuinely sad/emotional question — verify sarcasm dials back
- Run bot across midnight — verify mood resets with new day
