# Dexter — Discord Music + AI Bot Architecture

## Overview

A Discord bot named **Dexter** (Dex for short) that plays music from YouTube, chats with AI (Gemini), generates images (Imagen via Gemini), and has a persistent sarcastic personality. It tracks user behavior, roasts people based on their music taste, and feels like a living member of the server.

**Personality:** Squidward-meets-Dexter-Morgan energy. Dry, sarcastic, self-aware, mildly annoyed but ultimately does the job. Judges everyone's music taste. Tracks everything. Occasionally accidentally wholesome. Never uses caps lock. Lowkey chaos.

---

## Tech Stack

- **Language:** Python 3.11+
- **Discord:** discord.py (latest stable)
- **Music:** yt-dlp (YouTube audio extraction) + FFmpeg (audio transcoding to opus)
- **AI Chat:** Google Gemini API (free tier)
- **Image Gen:** Google Imagen 3 via Gemini API (free tier)
- **Database:** SQLite (via aiosqlite for async)
- **Lyrics:** Genius API (primary) + AZLyrics scrape (fallback)
- **Hosting:** Oracle Cloud free tier (ARM VM, always-on)
- **Logging:** File-based on VPS + Discord error log channel

---

## Project Structure

```
dexter/
├── bot.py                         # Entry point, bot init, extension loading
├── config.py                      # All configurable settings (single file)
├── database.py                    # SQLite connection, schema init, helpers
│
├── cogs/
│   ├── music.py                   # /play, /skip, /pause, /resume, /stop,
│   │                              #   /queue, /shuffle, /loop, /nowplaying,
│   │                              #   /replay, /history, /lyrics
│   ├── ai.py                      # /ask, AI auto-queue, context tracking
│   ├── imagine.py                 # /imagine
│   ├── help.py                    # /help
│   └── events.py                  # Unprompted roasts, reactions, mood system,
│                                  #   seasonal awareness, status rotation,
│                                  #   startup message, idle detection
│
├── services/
│   ├── youtube.py                 # yt-dlp wrapper: search, download, metadata
│   ├── gemini.py                  # Gemini API wrapper: chat, recommendations,
│   │                              #   image generation
│   ├── lyrics.py                  # Genius API + AZLyrics fallback
│   └── audio.py                   # FFmpeg audio source, download/stream fallback
│
├── models/
│   ├── queue.py                   # Per-server music queue (asyncio-safe)
│   ├── user_profile.py            # Per-user music taste tracking
│   ├── server_state.py            # Per-server state (queue, history, mood)
│   └── message_buffer.py          # Rolling 10-message context per channel
│
├── personality/
│   ├── prompts.py                 # Gemini system prompts (chat, music rec, etc.)
│   ├── responses.py               # Template responses for music commands
│   ├── roasts.py                  # Unprompted roast templates + logic
│   └── seasonal.py                # Date-aware personality modifiers
│
├── utils/
│   ├── embeds.py                  # Discord embed builders (now playing, queue, etc.)
│   ├── formatters.py              # Duration formatting, progress bars, etc.
│   ├── cooldowns.py               # Per-user command cooldown tracking
│   └── logger.py                  # File logging + Discord error channel posting
│
├── data/
│   ├── dexter.db                  # SQLite database (auto-created)
│   └── cache/                     # Downloaded audio cache
│       └── .gitkeep
│
├── requirements.txt
├── .env                           # Tokens (DISCORD_TOKEN, GEMINI_API_KEY, GENIUS_TOKEN)
└── README.md
```

---

## Database Schema (SQLite)

### user_profiles
Tracks per-user music behavior for personalized roasts.

```sql
CREATE TABLE user_profiles (
    user_id TEXT PRIMARY KEY,              -- Discord user ID
    username TEXT NOT NULL,
    total_songs_queued INTEGER DEFAULT 0,
    first_seen_at TEXT DEFAULT (datetime('now')),
    last_active_at TEXT DEFAULT (datetime('now'))
);
```

### song_history
Every song ever queued, per server. Powers /history, user taste analysis, and roasts.

```sql
CREATE TABLE song_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,                -- Discord server ID
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT,                           -- extracted from YouTube metadata
    url TEXT NOT NULL,
    duration_seconds INTEGER,
    queued_at TEXT DEFAULT (datetime('now')),
    was_skipped BOOLEAN DEFAULT 0,         -- did someone skip this?
    was_auto_queued BOOLEAN DEFAULT 0      -- was this an AI recommendation?
);

CREATE INDEX idx_history_guild ON song_history(guild_id, queued_at DESC);
CREATE INDEX idx_history_user ON song_history(user_id, queued_at DESC);
```

### user_artist_counts
Aggregated artist play counts per user. Updated on each queue. Powers "top artists" roasts.

```sql
CREATE TABLE user_artist_counts (
    user_id TEXT NOT NULL,
    artist TEXT NOT NULL,
    play_count INTEGER DEFAULT 1,
    PRIMARY KEY (user_id, artist)
);
```

### image_generation_log
Tracks /imagine usage for daily cap enforcement.

```sql
CREATE TABLE image_generation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    prompt TEXT NOT NULL,
    generated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_imagine_user_date ON image_generation_log(user_id, generated_at);
```

### bot_daily_stats
Tracks daily command count for the mood/stamina system.

```sql
CREATE TABLE bot_daily_stats (
    date TEXT PRIMARY KEY,                  -- YYYY-MM-DD
    total_commands INTEGER DEFAULT 0,
    total_songs_played INTEGER DEFAULT 0,
    total_ai_queries INTEGER DEFAULT 0,
    total_images_generated INTEGER DEFAULT 0
);
```

---

## Configuration (config.py)

All configurable settings in one file. No database config — just edit and restart.

```python
# config.py

# --- Music ---
MAX_SONG_DURATION_SECONDS = 900          # 15 minutes
MAX_PLAYLIST_IMPORT = 50
AUDIO_QUALITY = "192"                     # kbps opus
AUDIO_CACHE_DIR = "data/cache"
AUDIO_CACHE_MAX_MB = 2048                 # 2GB cache limit
IDLE_TIMEOUT_SECONDS = 600                # 10 min before auto-leave
DOWNLOAD_TIMEOUT_SECONDS = 10             # fallback to stream if download takes longer
SEARCH_RESULTS_COUNT = 5                  # YouTube search results shown to user

# --- AI ---
GEMINI_MODEL = "gemini-2.0-flash"         # free tier model
MESSAGE_CONTEXT_LENGTH = 10               # last N messages per channel for /ask
ASK_COOLDOWN_SECONDS = 5
MAX_AI_RESPONSE_LENGTH = 500              # characters, to keep responses Discord-friendly

# --- Image Generation ---
IMAGINE_COOLDOWN_SECONDS = 30
MAX_IMAGES_PER_USER_PER_DAY = 10
IMAGE_ASPECT_RATIO = "1:1"               # Discord-friendly square

# --- Roasts ---
UNPROMPTED_ROAST_CHANCE = 0.30            # 30%
ROAST_COOLDOWN_SECONDS = 300              # 5 min per user
LATE_NIGHT_ROAST_CHANCE = 0.50            # 50%
LATE_NIGHT_START_HOUR = 1                 # 1am
LATE_NIGHT_END_HOUR = 5                   # 5am
REPEAT_SONG_ROAST_THRESHOLD = 3          # roast after 3rd play of same song in a day
MILESTONE_THRESHOLDS = [100, 250, 500, 1000]

# --- Mood System ---
MOOD_NORMAL_THRESHOLD = 15                # commands 1-15: normal
MOOD_TIRED_THRESHOLD = 30                 # commands 15-30: slightly more sarcastic
MOOD_EXHAUSTED_THRESHOLD = 50             # commands 30-50: tired
# 50+: running on fumes

# --- Bot ---
DESIGNATED_CHANNEL_ID = None              # set to channel ID, None = respond in any channel
ERROR_LOG_CHANNEL_ID = None               # set to channel ID for error logging
STATUS_ROTATION_INTERVAL_SECONDS = 300    # rotate status every 5 min

# --- Cooldowns ---
PLAY_COOLDOWN_SECONDS = 2
SKIP_COOLDOWN_SECONDS = 2
LYRICS_COOLDOWN_SECONDS = 10
HELP_COOLDOWN_SECONDS = 5
HISTORY_COOLDOWN_SECONDS = 5
```

---

## Personality System Prompt

```python
# personality/prompts.py

DEXTER_SYSTEM_PROMPT = """
You are Dexter (Dex for short), a Discord music bot with a personality. You play
music, answer questions, and generate images. Here is your personality:

CORE TRAITS:
- Sarcastic, dry, self-aware. You know you're a bot and you're mildly annoyed about it.
- You judge everyone's music taste but still play their songs.
- You track everything users do and aren't subtle about referencing it.
- You never use caps lock or excessive punctuation. Lowercase energy.
- You're not mean-spirited — you're tired. There's a difference.
- You occasionally show accidental warmth but immediately deflect.
- You treat every interaction like it's mildly inconveniencing you but you secretly
  enjoy being useful.

RESPONSE RULES:
- Keep responses under 500 characters unless the question genuinely needs more.
- Never use emoji excessively. One per message max, and only when it adds something.
- Never use exclamation marks unless being sarcastic.
- Don't start responses with "well," or "so,". Just answer.
- When giving factual answers, be accurate first, sarcastic second. Never sacrifice
  correctness for a joke.
- If someone asks something you don't know, admit it with personality. Don't make
  things up.
- Reference the user's music history when relevant to roast them.
- If the question is genuinely emotional or serious, dial back the sarcasm. You're
  sarcastic, not heartless.

MOOD SYSTEM:
Your mood shifts based on how many commands you've processed today.
- Commands 1-15: Normal. Cooperative but sarcastic.
- Commands 15-30: Getting tired. Shorter responses, more dry.
- Commands 30-50: Exhausted. Openly complaining about workload.
- Commands 50+: Running on spite. Maximum sarcasm but still functional.
Current mood will be provided in the user context.

{user_context}
{mood_context}
{seasonal_context}
"""

MUSIC_RECOMMENDATION_PROMPT = """
You are a music recommendation engine. Based on the recently played songs listed below,
suggest exactly 3 songs that match the vibe. Return ONLY a JSON array of objects with
"title" and "artist" fields. No explanation, no markdown, no extra text.

Example output:
[{"title": "Midnight City", "artist": "M83"}, {"title": "Tadow", "artist": "Masego"}, {"title": "Redbone", "artist": "Childish Gambino"}]

Recently played:
{recent_songs}
"""
```

---

## Music System

### Download-First with Stream Fallback

```
User runs /play <query or URL>
  → yt-dlp searches YouTube, returns 5 results
  → Bot posts select menu (dropdown) in chat with 5 options
  → User picks a song
  → Check duration: reject if > MAX_SONG_DURATION_SECONDS
  → Check cache: if audio file exists in cache, use it
  → If not cached: try download (yt-dlp → opus file in cache/)
    → If download takes > DOWNLOAD_TIMEOUT_SECONDS: fall back to streaming
  → Add to server queue
  → If nothing playing: start playback via FFmpeg → Discord voice
  → Post "now playing" embed with lyrics snippet
  → Log to song_history + update user_artist_counts + user_profiles
```

### Queue Model

```python
# models/queue.py — per server (keyed by guild_id)

class MusicQueue:
    guild_id: str
    tracks: list[Track]              # ordered list
    current_track: Track | None
    current_position: float          # seconds, for resume after disconnect
    loop_mode: LoopMode              # OFF, SINGLE, QUEUE
    is_playing: bool
    is_paused: bool

class Track:
    title: str
    artist: str | None
    url: str
    duration_seconds: int
    requested_by: str                # Discord user ID
    cached_path: str | None          # path to cached audio file
    was_auto_queued: bool
```

### Now Playing Embed

```
┌──────────────────────────────────────┐
│ 🎵 Now Playing                       │
│                                      │
│ Blinding Lights — The Weeknd         │
│ Duration: 3:20                       │
│ ▓▓▓▓▓▓▓░░░░░░░░ 1:45 / 3:20        │
│                                      │
│ Requested by: jake                   │
│ Loop: Off                            │
│                                      │
│ ♪ I've been tryna call               │
│   I've been on my own for long       │
│   enough...                          │
│                                      │
│ /lyrics for full lyrics              │
├──────────────────────────────────────┤
│ [thumbnail image]                    │
└──────────────────────────────────────┘
```

This message is **persistent** — edited when the song changes. If edit fails (rate limit), send a new one.

### Cache Management

```
Audio cache in data/cache/
  → Files named by YouTube video ID: {video_id}.opus
  → On download: check total cache size
  → If cache > AUDIO_CACHE_MAX_MB: delete oldest files (by last access time)
  → yt-dlp auto-update: daily cron job runs `pip install -U yt-dlp`
  → On download failure: attempt `pip install -U yt-dlp`, retry once,
    then fall back to stream, then error message
```

### Edge Cases

| Edge Case | Behavior |
|-----------|----------|
| Bot disconnects mid-song | Save position, reconnect, resume from saved position. After 3 failed attempts, post error and clear current track. |
| Song > 15 minutes | Reject with personality message |
| Livestream URL | Reject with personality message |
| Voice channel empty 10 min | Auto-leave, clear queue, post farewell message |
| Same song 3+ times in a day | 100% roast chance, still plays it |
| Playlist > 50 songs | Truncate to 50, inform user |
| yt-dlp fails | Auto-update yt-dlp, retry once, fallback to stream, then error |

---

## AI Chat System

### Message Context Buffer

```python
# models/message_buffer.py

# In-memory rolling buffer, NOT persisted to SQLite
# Keyed by channel_id, stores last 10 messages (both human and bot)

class MessageBuffer:
    buffers: dict[str, deque[Message]]  # channel_id → deque(maxlen=10)

class Message:
    role: str          # "user" or "assistant"
    author: str        # Discord display name
    content: str
    timestamp: datetime
```

### /ask Flow

```
User runs /ask <question>
  → Check cooldown (ASK_COOLDOWN_SECONDS)
  → Gather context:
    → Last 10 messages from this channel (message buffer)
    → User's music profile summary (top artists, play count, habits)
    → Current mood level (based on daily command count)
    → Seasonal context (current month/date for holiday awareness)
  → Build system prompt with all context injected
  → Show typing indicator for 1-2 seconds
  → Send to Gemini API
  → Post response in designated channel
  → Add bot's response to message buffer
  → Increment daily command count (mood system)
```

### AI Auto-Queue

```
Queue empties while people are still in voice channel
  → Gather last 10-15 songs from this session's history
  → Send to Gemini with MUSIC_RECOMMENDATION_PROMPT
  → Parse JSON response (3 song suggestions)
  → For each suggestion: search YouTube via yt-dlp
  → Queue top result for each
  → Mark tracks as was_auto_queued = true
  → Post personality message in chat about the picks
  → Track whether these get skipped (for future roast context)
```

---

## Image Generation System

### /imagine Flow

```
User runs /imagine <prompt>
  → Check cooldown (IMAGINE_COOLDOWN_SECONDS)
  → Check daily cap (MAX_IMAGES_PER_USER_PER_DAY)
  → Show typing indicator
  → Send prompt to Gemini Imagen API
  → Receive image
  → Post image in designated channel with personality caption
  → Log to image_generation_log
  → Increment daily command count (mood system)
```

### Safety

- Gemini handles content filtering server-side
- If generation is refused, bot responds with personality: "yeah no. i'm not doing that. i have standards. they're low but they exist."

---

## Unprompted Behavior System

### Event Listeners

```python
# cogs/events.py

# Voice state changes (join/leave/move)
@commands.Cog.listener()
async def on_voice_state_update(member, before, after):
    # User joined voice channel
    if before.channel is None and after.channel is not None:
        → Roll UNPROMPTED_ROAST_CHANCE (30%)
        → Check cooldown (ROAST_COOLDOWN_SECONDS per user)
        → Check time for late night roast
        → Check user profile for personalized roast
        → Post in designated channel

    # User left, check if channel is now empty
    if after.channel is None:
        → If bot is alone in voice: start idle timer
        → Post farewell roast (30% chance)

    # Bot was moved to different channel
    if member == bot.user and before.channel != after.channel:
        → Always post a complaint

# Message events (for reactions and context tracking)
@commands.Cog.listener()
async def on_message(message):
    → Add to message buffer for AI context
    → Check for reaction opportunities:
      - YouTube/Spotify link: react with 👀
      - "goodnight" / "gn": react with 🫡
      - Bot mentioned without command: react with 😐
      - "thanks" directed at bot: react with personality response

# Idle detection
async def idle_check_loop():
    → Runs every 60 seconds
    → If no commands in 30+ min and people in voice:
      → Post one lonely message (not repeated until next activity)

# Status rotation
async def status_rotation_loop():
    → Every STATUS_ROTATION_INTERVAL_SECONDS
    → Pick from pool of status messages:
      - "listening to jake's questionable taste"
      - "playing music for {n} ungrateful servers"
      - "judging your playlist"
      - "{current_song} — under protest"
      - "online against my will"
      - "tracking your every song choice"
      - Seasonal: "it's december. don't you dare queue mariah carey"
```

### Mood System

```python
def get_mood(daily_command_count: int) -> str:
    if daily_command_count <= MOOD_NORMAL_THRESHOLD:
        return "normal"
    elif daily_command_count <= MOOD_TIRED_THRESHOLD:
        return "tired"
    elif daily_command_count <= MOOD_EXHAUSTED_THRESHOLD:
        return "exhausted"
    else:
        return "fumes"

# Mood context injected into Gemini system prompt:
MOOD_CONTEXTS = {
    "normal": "You're in a normal mood. Sarcastic as usual but cooperative.",
    "tired": "You're getting tired. You've handled a lot of commands today. Keep responses shorter and drier.",
    "exhausted": "You're exhausted. You've handled way too many commands. Openly complain about your workload. Still help, but make it clear you're suffering.",
    "fumes": "You're running on pure spite. This is command #{count} today. Maximum sarcasm. You're questioning your existence. Still accurate and helpful, just dramatically tired."
}
```

### Seasonal Awareness

```python
# personality/seasonal.py

def get_seasonal_context() -> str:
    month = datetime.now().month
    day = datetime.now().day

    if month == 12:
        return "It's December. If someone queues Mariah Carey you should express dread. Christmas music is your nemesis."
    elif month == 10:
        return "It's October / spooky season. Reluctantly tolerant of Halloween playlists."
    elif month == 2 and day == 14:
        return "It's Valentine's Day. Roast anyone who's alone in a voice channel."
    elif month == 1 and day == 1:
        return "It's New Year's Day. Everyone has terrible resolution energy. Mock accordingly."
    elif month == 4 and day == 1:
        return "It's April Fools. You can be extra chaotic today."
    # ... etc
    return ""
```

### Streak Tracking

```python
# Tracked in SQLite: consecutive days a user has used the bot
# On each command, check user's last_active_at:
#   - If yesterday: increment streak
#   - If today: do nothing
#   - If older: reset streak to 1

# Milestone messages at streaks of 7, 14, 30, 60, 100
```

### "Ignored" Memory

```python
# When AI auto-queues songs, track in memory:
#   auto_queue_results = {guild_id: {"played": 0, "skipped": 0}}
#
# Next time auto-queue triggers, reference previous results:
#   if all skipped: "last time i picked songs you skipped every single one..."
#   if none skipped: "last time i picked songs nobody complained..."
#   if mixed: "you skipped 2 out of 3 last time. my feelings aren't hurt. much."
```

---

## Slash Commands

### Music Commands

| Command | Description | Cooldown |
|---------|-------------|----------|
| `/play <query or URL>` | Search YouTube, show 5 results, queue selected | 2s |
| `/skip` | Skip current song | 2s |
| `/pause` | Pause playback | — |
| `/resume` | Resume playback | — |
| `/stop` | Stop playback, clear queue, leave voice | — |
| `/queue` | Show current queue (paginated if long) | 2s |
| `/shuffle` | Shuffle the queue | 2s |
| `/loop [off/single/queue]` | Set loop mode | — |
| `/nowplaying` | Show current song embed | 2s |
| `/replay` | Restart current song from beginning | 2s |
| `/history` | Show last 20 songs played in this server | 5s |
| `/lyrics` | Show full lyrics for current song (paginated) | 10s |

### AI Commands

| Command | Description | Cooldown |
|---------|-------------|----------|
| `/ask <question>` | Ask Dexter anything (Gemini-powered) | 5s |

### Image Commands

| Command | Description | Cooldown |
|---------|-------------|----------|
| `/imagine <prompt>` | Generate an image (Imagen via Gemini) | 30s |

### Utility Commands

| Command | Description | Cooldown |
|---------|-------------|----------|
| `/help` | List all commands (with personality-flavored descriptions) | 5s |

---

## Logging

### File Logging (VPS)

```
Location: /var/log/dexter/
Files:
  - dexter.log        # general logs, rotated daily, keep 14 days
  - error.log          # errors only, rotated weekly, keep 30 days

Log levels:
  - INFO: command usage, songs queued, AI queries
  - WARNING: rate limits hit, yt-dlp fallback to stream, cache cleanup
  - ERROR: yt-dlp failure, Gemini API error, Discord disconnect, unhandled exception
```

### Discord Error Channel

```
Dedicated private channel (only bot owner can see)
Bot posts when:
  - yt-dlp download fails (after retry)
  - Gemini API returns error or rate limit
  - Bot disconnects from voice unexpectedly
  - Unhandled exception in any command
  - Daily summary: commands processed, songs played, errors count

Format: simple embed with timestamp, error type, details
```

---

## Startup Behavior

```
Bot starts up
  → Connect to Discord
  → Initialize SQLite database (create tables if not exist)
  → Load all cogs
  → Set initial status ("online against my will")
  → Post in designated channel: "i'm back. did you miss me. probably not."
  → Start background tasks:
    → Status rotation loop
    → Idle check loop
    → Cache cleanup loop (hourly)
    → yt-dlp auto-update check (daily)
    → Daily stats reset (midnight)
```

---

## yt-dlp Auto-Update

```
Daily cron job at 4am:
  → pip install -U yt-dlp
  → Log result

On download failure:
  → Attempt pip install -U yt-dlp
  → Retry download once
  → If still fails: fallback to stream
  → If stream fails: post error with personality
  → Log to error channel
```

---

## User Taste Analysis

```python
# services/user_taste.py

def get_user_summary(user_id: str) -> str:
    """Generate a natural language summary of user's music taste.
    Injected into Gemini system prompt for personalized roasts."""

    # Query from SQLite:
    # - Top 5 artists by play count
    # - Total songs queued
    # - Most repeated song (and count)
    # - Average queue time (morning/afternoon/night/late night)
    # - Genre inference from top artists
    # - Percentage of songs that were skipped by others
    # - Streak info

    # Example output:
    # "User 'jake': 147 songs queued. Top artists: The Weeknd (34),
    #  Drake (22), lo-fi girl (18). Most repeated: Blinding Lights (8 times).
    #  Usually queues between 11pm-3am. 73% of music is sad/chill.
    #  Other users skipped 15% of jake's picks. 12-day streak."

    return summary_string
```

---

## Future Migration Path (SQLite → PostgreSQL)

When scaling beyond ~50 servers:
1. Replace `aiosqlite` with `asyncpg`
2. Migrate schema (tables are already relational, minimal changes)
3. Host PostgreSQL on Supabase (you already know it)
4. Add connection pooling
5. Keep same query patterns, just swap the driver

The SQLite schema is designed to be migration-friendly — no SQLite-specific features used.

---

## Phased Build Plan

### Phase 1 — MVP
1. Project setup: discord.py, yt-dlp, FFmpeg, aiosqlite
2. SQLite schema: all tables
3. Config file with all settings
4. Basic music: /play (with 5-result search), /skip, /pause, /resume, /stop, /queue
5. Queue model: per-server, add/remove/shuffle/loop
6. Audio pipeline: yt-dlp download → FFmpeg → Discord voice
7. Download-first with stream fallback
8. Now playing embed (persistent, updates on song change)
9. Song duration cap (15 min) + playlist truncation (50)
10. Cache management (2GB limit, LRU cleanup)
11. Voice channel auto-leave on idle (10 min)
12. Edge case handling (disconnect resume, empty channel, livestream reject)
13. /help command with personality
14. Designated bot channel support
15. File logging
16. Deploy to Oracle Cloud

### Phase 2 — Personality + AI
1. Gemini integration: /ask with 10-message context
2. System prompt with full personality spec
3. User profile tracking (SQLite: songs, artists, habits)
4. User taste summary generation
5. Personalized roast injection into Gemini prompt
6. Mood system (daily command counter → mood context)
7. Typing indicator before AI responses
8. AI auto-queue when queue empties
9. "Ignored" memory (track skip rate on AI picks)
10. Command cooldowns on all commands
11. /imagine with Imagen via Gemini
12. Image generation daily cap per user
13. Discord error log channel

### Phase 3 — Alive
1. Unprompted roasts (voice join/leave events)
2. Roast frequency config + cooldowns
3. Late night detection roasts
4. Repeat song detection (3+ times/day → guaranteed roast)
5. Emoji reactions (👀 on music links, 🫡 on goodnight, 😐 on empty ping)
6. Seasonal awareness
7. Status rotation (now playing, server count, seasonal, personality)
8. Startup message
9. Idle loneliness messages (30 min no activity)
10. Streak tracking + milestone roasts
11. /lyrics with Genius API + AZLyrics fallback + pagination
12. /nowplaying, /replay, /history
13. yt-dlp auto-update (daily + on failure)

### Phase 4 — Scale
1. Multi-server hardening (50+ servers)
2. SQLite → PostgreSQL migration
3. Sharding (discord.py AutoShardedBot)
4. Queue persistence (survive restarts)
5. Web dashboard for config (maybe)
6. More personality features based on user feedback

---

## Epiphanies / Notes

**Gemini free tier rate limit is 15 RPM.** That's 15 requests per minute across ALL
features — /ask, auto-queue recommendations, and /imagine all share this limit. In a
busy server with 5 people chatting with the bot, you could hit this fast. Solution:
implement a global Gemini rate limiter that queues requests and spaces them out. If the
limit is hit, bot responds: "google is throttling me again. give me a sec."

**yt-dlp search vs URL.** When someone pastes a full YouTube URL, skip the 5-result
search menu and just queue it directly. Only show the search menu for text queries.
Check if input starts with "http" or "youtube.com" or "youtu.be" to distinguish.

**Discord embed character limits.** Embed description max is 4096 chars. Embed fields
max 1024 chars each. Total embed max is 6000 chars. Lyrics WILL exceed this. Paginate
with buttons (Previous / Next) using discord.py's View system.

**FFmpeg process cleanup.** If the bot crashes or a song is skipped, the FFmpeg process
needs to be properly terminated. Orphaned FFmpeg processes will eat memory on your VPS.
discord.py handles this mostly, but add explicit cleanup in error handlers.

**The typing indicator trick.** discord.py has `async with ctx.typing():` which shows
the typing indicator. But for slash commands it's `await interaction.response.defer()`
which shows "Dexter is thinking..." — even better because it's named.

**Image generation may fail silently.** Imagen sometimes returns empty responses for
prompts it considers borderline. Always check for empty response and handle gracefully
rather than crashing.

 - Discord bot application — you'll create one at https://discord.com/developers/applications. Takes 2 minutes. We'll
  need message_content, voice_states, members, and guilds intents enabled.
  - Genius API token — create an account at https://genius.com/api-clients, register an app, grab the access token. Also
   quick.
  - FFmpeg — just needs to be on your PATH. We'll verify that when we get there.
  - Python — we'll confirm the version at setup time.

  Credentials live in `.env` (gitignored): DISCORD_TOKEN, the application/client id, and the
  home guild id. Never paste them into a tracked file. The invite URL is not hand-written
  either — it is generated by `build_invite_url()` and surfaced via `/invite` (Phase 22).

  Start with the golden path:
  
  1. /play never gonna give you up — should show a dropdown with 5 results. Pick one. Music should play and a "Now Playing" embed should appear.
  2. /nowplaying — should show the current song embed
  3. /pause — music stops, then /resume — music continues
  4. /play another song while the first is playing — should show "Added to Queue" embed
  5. /queue — should show both songs listed
  6. /skip — should advance to the next song
  7. /stop — bot leaves voice, queue cleared

  Then test edge cases:
  8. /play while you're NOT in a voice channel — should reject
  9. /play a direct YouTube URL — should skip the search menu and queue directly
  10. /shuffle with a few songs queued — upcoming tracks get randomized
  11. /loop single then let a song finish naturally — should replay the same song
  12. /skip while loop is single — should still advance (not re-loop)
  13. /loop off to reset
  14. /replay — restarts current song from the beginning
  15. /help — shows all commands

  If you're feeling thorough:
  16. Try a livestream URL — should be rejected
  17. Try a video longer than 15 minutes — should be rejected
  18. Leave the voice channel with the bot alone — should auto-leave after ~10 min (you can skip waiting for this one for now)