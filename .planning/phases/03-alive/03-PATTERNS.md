# Phase 3: Alive - Pattern Map

**Mapped:** 2026-06-11
**Files analyzed:** 9 (2 create, 7 modify)
**Analogs found:** 9 / 9

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `personality/roasts.py` (CREATE) | utility / content pool | transform | `personality/responses.py` | exact |
| `services/lyrics.py` (CREATE) | service | request-response | `services/gemini.py` | role-match |
| `personality/prompts.py` (MODIFY) | utility / prompt builder | transform | self (rewrite in-place) | self |
| `personality/seasonal.py` (MODIFY) | utility | transform | self (additive) | self |
| `cogs/events.py` (MODIFY) | cog / event listener | event-driven | `cogs/music.py` listener block (lines 604-650+) | role-match |
| `cogs/music.py` (MODIFY) | cog / slash commands + UI views | request-response | self — `QueuePageView` (lines 71-94), `queue_cmd` (lines 533-545) | exact |
| `database.py` (MODIFY) | data layer | CRUD | self — `init_db()` (lines 63-71), `get_recent_songs()` (lines 159-172), `update_user_profile()` (lines 108-122) | exact |
| `bot.py` (MODIFY) | entry point / background tasks | event-driven | self — `idle_check` (lines 180-215), `cache_cleanup` (lines 218-228) | exact |
| `config.py` (MODIFY) | config | — | self — `ERROR_LOG_CHANNEL_ID` (line 50), existing numeric constants (lines 12-53) | exact |

---

## Pattern Assignments

---

### `personality/roasts.py` (CREATE — utility, transform)

**Analog:** `personality/responses.py` (entire file — 65 lines, read in full above)

**Imports pattern** (copy from `personality/responses.py` lines 1-11):
```python
"""Roast template pools for unprompted Dexter personality moments.

Use pick_random() from personality.responses to select one at random.
"""

import random


def pick_random(pool: list[str]) -> str:
    """Pick a random string from a response pool."""
    return random.choice(pool)
```
Note: `pick_random` is already defined in `responses.py`. The planner must decide whether to import it from there or redeclare it. Recommend importing: `from personality.responses import pick_random`.

**Core pool pattern** (copy structure from `personality/responses.py` lines 14-64):
```python
# Each pool is a List[str] module-level constant.
# Convention: ALL_CAPS_SNAKE_CASE name, type annotation list[str].

VOICE_JOIN_ROASTS: list[str] = [
    "oh good. {name} is here. the bar was already low.",
    ...
]

VOICE_LEAVE_ROASTS: list[str] = [
    "finally.",
    ...
]
```

**Pools to create** (per CONTEXT.md D-07, PERS-02/03/07/08/09):
- `VOICE_JOIN_ROASTS` — join event (30% trigger, ambient ceiling)
- `VOICE_LEAVE_ROASTS` — leave event (30%, ambient ceiling)
- `LATE_NIGHT_ROASTS` — join between 1–5am hour (50%, ambient ceiling)
- `BOT_MOVED_COMPLAINTS` — always fires when bot is moved to different channel
- `IDLE_LONELINESS_MESSAGES` — after 30+ min silence with humans in voice (once per window)
- `STARTUP_MESSAGES` — on bot boot; arrogant, NOT self-deprecating (D-02/D-03; see CONTEXT.md specifics — use "i'm back. the queue fell apart without me, obviously." pattern, not "did you miss me. probably not.")
- `STATUS_LINES` — static personality status strings for rotation pool (supplement current song / server count)
- `REPEAT_SONG_ROAST_TEMPLATES` — fallback for Gemini-backed repeat-song roast (D-08)
- `MILESTONE_SONG_TEMPLATES` — fallback for song-count milestones (D-08)
- `MILESTONE_STREAK_TEMPLATES` — fallback for streak-day milestones (D-08)
- `NO_LYRICS_FOUND` — personality error if neither Genius nor AZLyrics returns lyrics

**Voice register rules** (hard constraints, write into docstring):
- Contempt aimed outward at user data, never inward at self (D-02)
- Mild swearing only: damn, hell, crap, ass, screw — no f-bombs (D-03)
- Lowercase, ≤500 chars, one emoji max (D-05)
- Humor from specific recall of tracked behavior, not generic quips (D-01)
- Templates that take a `{name}` or `{title}` placeholder use `.format()` at call site

---

### `services/lyrics.py` (CREATE — service, request-response)

**Analog:** `services/gemini.py` lines 1-50 (class structure, import pattern, `__init__`, graceful degradation)

**Imports pattern** (model on `services/gemini.py` lines 1-14):
```python
"""Lyrics fetching service: Genius primary, AZLyrics fallback."""

from __future__ import annotations

import asyncio
import re

import aiohttp
from bs4 import BeautifulSoup
from lyricsgenius import Genius

import config
from utils.logger import log
```

**Class init pattern** (model on `services/gemini.py` — service takes token in `__init__`, stores as private, graceful degradation if missing):
```python
class LyricsService:
    def __init__(self, genius_token: str | None) -> None:
        if genius_token:
            self._genius = Genius(
                genius_token,
                verbose=False,
                remove_section_headers=True,
                retries=1,
            )
        else:
            self._genius = None
            log.warning("GENIUS_TOKEN not set — Genius lyrics disabled")
```

**Core method pattern** (async, wraps sync lib in `asyncio.to_thread` per RESEARCH.md Pattern 4):
```python
async def get_lyrics(self, title: str, artist: str | None) -> str | None:
    """Fetch lyrics: Genius first, AZLyrics fallback. Returns None if both fail."""
    lyrics = await self._get_genius(title, artist)
    if lyrics:
        return lyrics
    return await self._get_azlyrics(title, artist)
```

**Wiring in `bot.py`** (copy from `bot.py` lines 78-84 — conditional init pattern for optional services):
```python
# In on_ready(), after existing service init:
genius_token = os.getenv("GENIUS_TOKEN")
from services.lyrics import LyricsService
bot.lyrics_service = LyricsService(genius_token)
log.info("Lyrics service initialized")
```
Access from cog via `self.bot.lyrics_service` (same as `self.bot.gemini_service` pattern).

**Error handling pattern** (copy from `services/gemini.py` — all external calls wrapped in try/except, return None on failure, log warning):
```python
try:
    ...
except Exception as e:
    log.warning(f"Genius fetch failed: {e}")
    return None
```

---

### `personality/prompts.py` (MODIFY — rewrite `DEXTER_SYSTEM_PROMPT`)

**File:** `personality/prompts.py` — read in full above (90 lines).

**Current structure to preserve** (lines 38-90 are NOT changing):
- `MUSIC_RECOMMENDATION_PROMPT` (lines 38-48) — do not touch
- `MOOD_CONTEXTS` dict (lines 50-64) — do not touch
- `build_chat_prompt(mood, user_summary, seasonal)` function (lines 67-80) — do not touch; it already formats `DEXTER_SYSTEM_PROMPT` with `{max_length}`, `{mood_context}`, `{user_context}`, `{seasonal_context}` placeholders
- `build_recommendation_prompt()` (lines 83-89) — do not touch

**What changes:** Only `DEXTER_SYSTEM_PROMPT` (lines 3-36) — rewrite to embed few-shot exemplars per D-06.

**Current problem (lines 3-36):** The prompt is an adjective list (`"Sarcastic, dry, self-aware"`, `"not mean-spirited — you're tired"`) with zero examples. LLMs imitate examples far better than descriptions.

**Required rewrite pattern:**
1. Open with the "Squidward-meets-Dexter-Morgan WITHOUT fourth-wall self-reference" identity statement
2. Add the three BANNED modes explicitly (D-02): no bot-self-awareness, no pop-psych, no self-deprecation
3. Embed 4-6 few-shot `USER:` / `DEXTER:` example pairs from `03-DISCUSSION-LOG.md` "Voice samples" section (the locked canonical register — read that file before writing)
4. Preserve the existing `{max_length}`, `{mood_context}`, `{user_context}`, `{seasonal_context}` format-string placeholders — `build_chat_prompt()` depends on them

**Canonical formula line** (from CONTEXT.md specifics — embed this in few-shot section):
> `marcus. back with the drake. forty-seven plays last week. one artist, one emotion, zero growth. impressive commitment to being boring.`

**Build function signature** (lines 67-68 — MUST remain unchanged):
```python
def build_chat_prompt(mood: str, user_summary: str | None, seasonal: str) -> str:
```

---

### `personality/seasonal.py` (MODIFY — additive expansion)

**File:** `personality/seasonal.py` — read in full above (28 lines).

**Pattern to copy:** The existing `if month == X:` / `if month == X and day == Y:` chain (lines 15-28). Add new `elif` branches before the final `return ""`.

**Current entries** (lines 15-27):
- `month == 12` → December / Christmas dread
- `month == 10` → October / Halloween
- `month == 2 and day == 14` → Valentine's Day
- `month == 1 and day == 1` → New Year's Day
- `month == 4 and day == 1` → April Fools

**Add new branches in the same format** (Claude's discretion on which dates per CONTEXT.md). Suggested additions:
- `month == 11 and day >= 20` → Thanksgiving week (USA)
- `month == 3 and day == 17` → St. Patrick's Day
- `month == 7 and day == 4` → Fourth of July
- `month == 5` → last Sunday → Mother's Day (or simplify: skip if tricky)
- Summer months (June–August) → generic "everyone's outside, why are you in discord" line

**Return type:** all branches return a short English string (same format as existing lines — sentence fragments, not JSON).

---

### `cogs/events.py` (MODIFY — add `on_voice_state_update`, reaction listeners)

**File:** `cogs/events.py` — read in full above (33 lines).

**Current structure to preserve** (lines 11-33):
- `EventsCog.__init__(self, bot)` (lines 14-15)
- `on_message` listener (lines 17-28) — extend, do not replace
- `setup(bot)` function (lines 32-33) — do not touch

**Add to `__init__`** (ambient cooldown dict per RESEARCH.md Pattern 2):
```python
def __init__(self, bot: commands.Bot) -> None:
    self.bot = bot
    # Per-user ambient roast cooldown (join + leave + late-night combined)
    self._ambient_roast_times: dict[int, float] = {}
    self._idle_loneliness_posted: bool = False  # reset on any command activity
```

**Add new listener** (copy decorator pattern from `cogs/music.py` lines 604-607):
```python
@commands.Cog.listener()
async def on_voice_state_update(
    self,
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
```
Event discrimination logic: RESEARCH.md Pattern 1 (lines 228-263). Critical: `if member.bot: return` at top EXCEPT for bot-move detection which uses `member == self.bot.user and before.channel != after.channel`.

**Extend existing `on_message`** (lines 17-28 — add reaction logic after the buffer-feeding block):
```python
# After existing buffer-feeding block:
await self._handle_message_reactions(message)
```
Reactions: `message.add_reaction('👀')` for YouTube/Spotify URLs, `message.add_reaction('🫡')` for goodnight/gn, `message.add_reaction('😐')` for bare bot mention, `channel.send()` for thanks.

**Channel resolution helper** (D-09/D-10 fallback chain):
```python
async def _get_ambient_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
    """Resolve the channel to post ambient roasts per D-09/D-10 fallback chain."""
    # 1. DEXTER_CHANNEL_ID (config)
    # 2. queue._text_channel_id (last music channel)
    # 3. guild.system_channel
    # 4. first writable text channel
```

**Imports to add** to `cogs/events.py` (copy style from `cogs/music.py` lines 1-16):
```python
import random
import discord
from discord.ext import commands
import config
from personality import roasts
from utils.logger import log
```

---

### `cogs/music.py` (MODIFY — add `/lyrics` and `/history` commands + new page views)

**File:** `cogs/music.py` — key sections read above.

**New UI views** (insert after `QueuePageView` class, lines 71-94 — copy exact structure):

`LyricsPageView` — same `discord.ui.View` + `Previous`/`Next` pattern but takes `list[str]` (pre-chunked pages) not a `MusicQueue`:
```python
class LyricsPageView(discord.ui.View):
    def __init__(self, pages: list[str], title: str, timeout: float = 120.0) -> None:
        super().__init__(timeout=timeout)
        self.pages = pages
        self.title = title
        self.page = 0

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = max(0, self.page - 1)
        embed = self._build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = min(len(self.pages) - 1, self.page + 1)
        embed = self._build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        # Also edit the message to visually show disabled state (RESEARCH.md pitfall Q3)
        # Requires storing the message reference: self.message = await interaction.original_response()
```

`HistoryPageView` — same pattern, takes `list[dict]` rows (10 per page):
```python
class HistoryPageView(discord.ui.View):
    def __init__(self, rows: list[dict], timeout: float = 120.0) -> None:
        ...
```

**`/lyrics` command** (copy decorator pattern from `queue_cmd` lines 533-545):
```python
@app_commands.command(name="lyrics", description="Show lyrics for the current song")
@app_commands.checks.cooldown(1, 10.0)
async def lyrics(self, interaction: discord.Interaction) -> None:
    queue = self.get_queue(interaction.guild.id)
    track = queue.get_current()
    if not track or not queue.is_playing:
        return await interaction.response.send_message(
            embed=embeds.error("nothing is playing."), ephemeral=True
        )
    await interaction.response.defer()
    lyrics_text = await self.bot.lyrics_service.get_lyrics(track.title, track.artist)
    if not lyrics_text:
        from personality.roasts import pick_random, NO_LYRICS_FOUND
        return await interaction.followup.send(pick_random(NO_LYRICS_FOUND))
    pages = chunk_lyrics(lyrics_text)
    view = LyricsPageView(pages, title=track.title)
    await interaction.followup.send(embed=..., view=view)
```

**`/history` command** (copy pattern from `queue_cmd`; uses `get_recent_songs()` from `database.py`):
```python
@app_commands.command(name="history", description="Show recently queued songs")
@app_commands.checks.cooldown(1, 5.0)
async def history(self, interaction: discord.Interaction) -> None:
    rows = await get_recent_songs(self.db, guild_id=str(interaction.guild.id), limit=50)
    if not rows:
        return await interaction.response.send_message(
            embed=embeds.error("No history yet."), ephemeral=True
        )
    view = HistoryPageView(rows)
    await interaction.response.send_message(embed=..., view=view)
```

**Repeat-song detection** (trigger during post-queue logging path in `MusicCog` — add after `log_song` call, NOT in `EventsCog`):
- Add a `get_repeat_song_count(db, guild_id, user_id, title)` helper to `database.py` (see database.py section below)
- Call it after `log_song()`; if count >= `config.REPEAT_SONG_ROAST_THRESHOLD` → post roast to `queue._text_channel_id`

**Pure helper functions** (add as module-level functions in `cogs/music.py` or `services/lyrics.py`):
```python
def chunk_lyrics(lyrics: str, page_size: int = 1500) -> list[str]:
    ...  # RESEARCH.md Pattern 8 — unit-testable pure function
```

**Imports to add:**
```python
from database import get_recent_songs
from services.lyrics import LyricsService  # accessed via self.bot.lyrics_service
```

---

### `database.py` (MODIFY — additive streak migration + new query helpers)

**File:** `database.py` — read in full above (211 lines).

**`SCHEMA_SQL`** (lines 11-60) — add streak columns directly to `user_profiles` table definition for clean fresh installs (RESEARCH.md Pitfall 4):
```sql
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    total_songs_queued INTEGER DEFAULT 0,
    first_seen_at TEXT DEFAULT (datetime('now')),
    last_active_at TEXT DEFAULT (datetime('now')),
    current_streak INTEGER DEFAULT 0,
    longest_streak INTEGER DEFAULT 0,
    last_streak_date TEXT
);
```

**`init_db()`** (lines 63-71) — add migration call after `executescript(SCHEMA_SQL)`:
```python
async def init_db(db: aiosqlite.Connection) -> None:
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    await db.executescript(SCHEMA_SQL)
    await migrate_add_streak_columns(db)  # ← ADD THIS
    await db.commit()
    log.info("Database schema initialized")
```

**New `migrate_add_streak_columns()`** (copy PRAGMA check pattern from RESEARCH.md Pattern 7; place before `init_db`):
```python
async def migrate_add_streak_columns(db: aiosqlite.Connection) -> None:
    """Idempotent: add streak columns to user_profiles if not present."""
    cursor = await db.execute("PRAGMA table_info(user_profiles)")
    existing = {row[1] for row in await cursor.fetchall()}
    migrations = [
        ("current_streak", "INTEGER DEFAULT 0"),
        ("longest_streak", "INTEGER DEFAULT 0"),
        ("last_streak_date", "TEXT"),
    ]
    for col_name, col_def in migrations:
        if col_name not in existing:
            await db.execute(
                f"ALTER TABLE user_profiles ADD COLUMN {col_name} {col_def}"
            )
    await db.commit()
    log.info("Streak column migration complete")
```

**New query helpers** (copy style of `get_recent_songs()` lines 159-172 — async, named params, `dict(row)` return):

`get_repeat_song_count()` for PERS-04:
```python
async def get_repeat_song_count(
    db: aiosqlite.Connection, *, guild_id: str, user_id: str, title: str
) -> int:
    """Count plays of the same song by this user in this guild today."""
    cursor = await db.execute(
        """SELECT COUNT(*) as cnt FROM song_history
           WHERE guild_id = ? AND user_id = ? AND title = ?
             AND date(queued_at) = date('now')""",
        (guild_id, user_id, title),
    )
    row = await cursor.fetchone()
    return row["cnt"] if row else 0
```

`update_user_streak()` for PERS-09 (called from `update_user_profile` path or its own call):
```python
async def update_user_streak(
    db: aiosqlite.Connection, *, user_id: str, tz_name: str
) -> tuple[int, int, bool, bool]:
    """
    Update streak for user. Returns (new_streak, longest_streak, is_milestone, milestone_value).
    Calls compute_streak() internally.
    """
```

**`get_recent_songs()`** (lines 159-172) — already exists; `/history` adds `queued_at` and `username` to the SELECT. Either modify the existing function (add fields) or create `get_history_rows()` that also returns `queued_at`:
```python
async def get_history_rows(
    db: aiosqlite.Connection, *, guild_id: str, limit: int = 50
) -> list[dict]:
    cursor = await db.execute(
        """SELECT title, artist, url, duration_seconds, user_id, queued_at
           FROM song_history
           WHERE guild_id = ?
           ORDER BY queued_at DESC, id DESC
           LIMIT ?""",
        (guild_id, limit),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]
```

**`update_user_profile()`** (lines 108-122) — the milestone check for total songs hooks here. After the UPSERT, query the new `total_songs_queued` value and check against `config.MILESTONE_SONG_THRESHOLDS`. Return the new count so the cog can check milestones.

---

### `bot.py` (MODIFY — register new background loops)

**File:** `bot.py` — read in full above (291 lines).

**Background task registration pattern** (copy from lines 180-228 exactly):
```python
@tasks.loop(seconds=300)   # config.STATUS_ROTATION_INTERVAL_SECONDS
async def status_rotation():
    ...

@status_rotation.before_loop
async def before_status_rotation():
    await bot.wait_until_ready()
```
Start guard in `on_ready()` (lines 99-104 pattern):
```python
if not status_rotation.is_running():
    status_rotation.start()
```

**Status rotation task body** (RESEARCH.md Pattern 3):
```python
@tasks.loop(seconds=config.STATUS_ROTATION_INTERVAL_SECONDS)
async def status_rotation():
    status_text = _pick_next_status()  # cycles through pool
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name=status_text,
        )
    )
```
`discord.ActivityType.listening` is the type already used in `create_bot()` line 45-47 — consistent.

**Lyrics service wiring** (add to `on_ready()` after line 84, following Gemini conditional-init pattern lines 78-84):
```python
genius_token = os.getenv("GENIUS_TOKEN")
from services.lyrics import LyricsService
bot.lyrics_service = LyricsService(genius_token)
log.info("Lyrics service initialized")
```

**Startup message** (add as LAST statement in `on_ready()`, after all `load_extension` calls per RESEARCH.md Pitfall 5; currently line 106 is `log.info("Dexter is ready.")`):
```python
# Post startup message (must be last — after all cogs loaded)
from personality.roasts import pick_random, STARTUP_MESSAGES
dexter_channel = _resolve_dexter_channel()
if dexter_channel:
    await dexter_channel.send(pick_random(STARTUP_MESSAGES))
```

**Idle loneliness — extend `idle_check`** (lines 180-215). Add a loneliness post inside the `else:` branch (humans ARE present) when `vc._idle_since_command_seconds >= config.IDLE_LONELINESS_THRESHOLD_SECONDS` and not already posted this window. Mirror the existing `vc._idle_seconds` accumulator pattern.

---

### `config.py` (MODIFY — add Phase 3 constants)

**File:** `config.py` — read in full above (54 lines).

**`DEXTER_CHANNEL_ID` pattern** (copy from line 50 — `ERROR_LOG_CHANNEL_ID` env pattern exactly):
```python
# --- Personality / Ambient Channel ---
DEXTER_CHANNEL_ID = int(os.getenv("DEXTER_CHANNEL_ID", "0")) or None
```

**`STREAK_TIMEZONE`** (env var with sensible default per D-17; planner sets default to `"America/New_York"`):
```python
STREAK_TIMEZONE = os.getenv("STREAK_TIMEZONE", "America/New_York")
```

**New numeric constants** (follow existing numeric constant style — plain assignments with inline comment, lines 12-34):
```python
# --- Phase 3: Roasts & Personality ---
UNPROMPTED_ROAST_CHANCE = 0.30          # 30% on voice join/leave
LATE_NIGHT_ROAST_CHANCE = 0.50          # 50% on 1-5am joins
AMBIENT_ROAST_CEILING_SECONDS = 300     # max 1 ambient roast per 5 min per user
ROAST_COOLDOWN_SECONDS = 300            # same value, alias for clarity
REPEAT_SONG_ROAST_THRESHOLD = 3         # plays same song ≥3× today → always roast
LATE_NIGHT_HOURS = (1, 5)               # tuple[int,int]: hours 1-5 inclusive

# --- Phase 3: Milestones ---
MILESTONE_SONG_THRESHOLDS: list[int] = [100, 250, 500, 1000]
MILESTONE_STREAK_THRESHOLDS: list[int] = [7, 14, 30, 60, 100]

# --- Phase 3: Status & Idle ---
STATUS_ROTATION_INTERVAL_SECONDS = 300  # 5 min
IDLE_LONELINESS_THRESHOLD_SECONDS = 1800  # 30 min silence with humans in voice

# --- Phase 3: Lyrics ---
LYRICS_COOLDOWN_SECONDS = 10
LYRICS_PAGE_SIZE = 1500                 # chars per embed page
HISTORY_PAGE_SIZE = 10                  # songs per history page
HISTORY_FETCH_LIMIT = 50
```

**Placement:** Add a `# --- Phase 3: ...` section block after the existing `# --- Auto-Queue ---` block (line 47) and before `# --- Error Logging ---` (line 49).

---

## Shared Patterns

### Bot-wide `@tasks.loop` pattern
**Source:** `bot.py` lines 180-228
**Apply to:** `status_rotation` (new), idle loneliness extension of `idle_check`
```python
@tasks.loop(seconds=N)
async def task_name():
    ...

@task_name.before_loop
async def before_task_name():
    await bot.wait_until_ready()

# In on_ready():
if not task_name.is_running():
    task_name.start()
```

### Slash command + cooldown pattern
**Source:** `cogs/music.py` lines 533-545
**Apply to:** `/lyrics`, `/history`
```python
@app_commands.command(name="...", description="...")
@app_commands.checks.cooldown(1, N.0)
async def cmd_name(self, interaction: discord.Interaction) -> None:
    ...
    return await interaction.response.send_message(embed=embeds.error("..."), ephemeral=True)
```

### `defer()` for slow commands
**Source:** `cogs/music.py` lines 598-601 (`replay` command)
**Apply to:** `/lyrics` (Genius fetch + AZLyrics scrape can take 2-5s)
```python
await interaction.response.defer()
# ... async work ...
await interaction.followup.send(embed=..., view=...)
```

### Optional env var as int-or-None
**Source:** `config.py` line 50
**Apply to:** `DEXTER_CHANNEL_ID`
```python
SOME_CHANNEL_ID = int(os.getenv("SOME_CHANNEL_ID", "0")) or None
```

### Service init with graceful token-missing degradation
**Source:** `bot.py` lines 78-84
**Apply to:** `LyricsService` init in `on_ready()`
```python
token = os.getenv("TOKEN_NAME")
if token:
    bot.service = MyService(token)
    log.info("Service initialized")
else:
    log.warning("TOKEN_NAME not set — feature disabled")
```

### `pick_random()` for personality messages
**Source:** `personality/responses.py` lines 9-11
**Apply to:** All roast pool selections in `cogs/events.py`, `cogs/music.py`, `bot.py`
```python
from personality.responses import pick_random
from personality import roasts
msg = pick_random(roasts.VOICE_JOIN_ROASTS)
```

### `@commands.Cog.listener()` event handler
**Source:** `cogs/events.py` lines 17-18; `cogs/music.py` lines 604-607
**Apply to:** New `on_voice_state_update` in `EventsCog`
```python
@commands.Cog.listener()
async def on_voice_state_update(self, member, before, after) -> None:
    if member.bot:
        return
```

### Async DB query helper (named kwargs, `dict(row)` return)
**Source:** `database.py` lines 159-172 (`get_recent_songs`)
**Apply to:** `get_repeat_song_count()`, `get_history_rows()`, `update_user_streak()`
```python
async def helper_name(
    db: aiosqlite.Connection, *, kwarg: str
) -> return_type:
    cursor = await db.execute("SELECT ...", (kwarg,))
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]
```

---

## No Analog Found

All files have analogs in the codebase. No greenfield patterns required.

---

## Pure Functions to Unit-Test (RESEARCH.md Validation Architecture)

These must be extractable as standalone functions for `tests/`:

| Function | Proposed Location | Test File |
|----------|-------------------|-----------|
| `compute_streak(current_streak, last_streak_date, tz_name)` | `database.py` or `utils/streak.py` | `tests/test_streak.py` |
| `chunk_lyrics(lyrics, page_size)` | `services/lyrics.py` | `tests/test_lyrics.py` |
| `build_genius_search_query(title, artist)` | `services/lyrics.py` | `tests/test_lyrics.py` |
| `build_azlyrics_url(artist, song)` | `services/lyrics.py` | `tests/test_lyrics.py` |
| `is_late_night(hour)` | `cogs/events.py` or `utils/` | `tests/test_roasts.py` |
| `get_local_date(tz_name)` | `database.py` or `utils/streak.py` | `tests/test_streak.py` |

---

## Metadata

**Analog search scope:** `personality/`, `services/`, `cogs/`, `database.py`, `bot.py`, `config.py`
**Files scanned:** 8 source files read in full
**Pattern extraction date:** 2026-06-11
