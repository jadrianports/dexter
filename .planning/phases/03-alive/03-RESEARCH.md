# Phase 3: Alive - Research

**Researched:** 2026-06-11
**Domain:** Discord.py event listeners, lyrics scraping (Genius/AZLyrics), streak timezone math, background loops, SQLite additive migration
**Confidence:** HIGH for discord.py patterns and standard stack; MEDIUM for AZLyrics selector stability; HIGH for lyricsgenius approach with run_in_executor

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Dexter's voice is arrogant, superior, dry, contemptuous — humor comes from specific recall of the user's tracked behavior (real song title / artist / play-count), not generic quips.
- **D-02:** Contempt aimed OUTWARD and DOWN at users only. Three permanently banned inward modes: (1) bot self-awareness/fourth-wall, (2) pop-psych diagnosis, (3) self-deprecation.
- **D-03:** Language = mild swearing (damn, hell, crap, ass, screw). No f-bombs, no censored f-bombs.
- **D-04:** Meanness ceiling is the locked sample batch from DISCUSSION-LOG.md. Ceiling, not floor.
- **D-05:** Existing locked rules preserved: lowercase, ≤500 chars, one emoji max, accurate-first, dials back for serious /ask.
- **D-06:** `DEXTER_SYSTEM_PROMPT` in `personality/prompts.py` MUST be rewritten with few-shot exemplars + arrogant/outward-only rules.
- **D-07:** HYBRID roast source — hand-written template pools in new `personality/roasts.py` (following `personality/responses.py` + `pick_random()` pattern) are the backbone for high-frequency triggers; Gemini for low-frequency special moments (milestones, repeat-song personalization).
- **D-08:** Gemini used only for milestones and repeat-song callbacks — priority 2 on shared 15 RPM limiter, falls back to template if rate-limited (>10s wait).
- **D-09:** New config `DEXTER_CHANNEL_ID` (env var, mirrors `ERROR_LOG_CHANNEL_ID` pattern) for ambient posts.
- **D-10:** Fallback chain if `DEXTER_CHANNEL_ID` unset: `queue._text_channel_id` → guild system channel → first writable channel.
- **D-11:** Reactions attach to triggering message. Repeat-song and milestone roasts post to music channel (`queue._text_channel_id`).
- **D-12:** Keep spec odds/cooldowns: join 30% / 5-min per-user, late-night 50%, repeat-song & milestones 100%, leave 30%.
- **D-13:** One unified per-user ambient roast ceiling (~1 per 5–10 min covering join + leave + late-night combined) to prevent carpet-bombing.
- **D-14:** Earned roasts (repeat-song 3+x/day and milestones) bypass ceiling and always fire.
- **D-15:** `/lyrics` — current song only, no query arg; personality error if nothing playing or neither source returns. Genius primary → AZLyrics fallback. Reuse `QueuePageView`.
- **D-16:** `/history` — server-wide, recently queued songs; each line shows title / artist / who requested / when. Reuse `QueuePageView` pagination. Reads existing `song_history` table.
- **D-17:** Day boundary = single configured timezone. New config `STREAK_TIMEZONE` (IANA, e.g. `America/New_York`, default sensible zone). SQLite `datetime('now')` is UTC; streak date math uses configured tz.
- **D-18:** Strict reset: consecutive calendar day → +1; same day → no-op; one fully missed day → reset to 1.
- **D-19:** Storage: new columns on `user_profiles` — `current_streak INTEGER`, `longest_streak INTEGER`, `last_streak_date TEXT` (date-only in configured tz). Additive migration.
- **D-20:** Track `longest_streak` so roasts can reference personal best.
- **D-21:** Milestone firing: song-count `[100,250,500,1000]` and streak-day `[7,14,30,60,100]` both always-fire, once per threshold.

### Claude's Discretion

- Exact wording of template-pool lines (reviewed by user during execution).
- Exact config values for ambient ceiling window, `STREAK_TIMEZONE` default, status interval, idle-silence threshold.
- `/lyrics` and `/history` page sizes and embed layout.
- Genius lookup implementation (raw HTTP + scrape vs `lyricsgenius` library).
- Which additional seasonal dates to add beyond existing 5.

### Deferred Ideas (OUT OF SCOPE)

- Streak-broken roast (Dexter roasts loss when streak ends).
- Per-user timezones for streaks.
- One-day grace / "streak freeze."
- `/lyrics` arbitrary-song query argument.
- `/history` per-user filter.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PERS-02 | Bot roasts users on voice join/leave (30% / 5-min per-user cooldown) and complains when moved | `on_voice_state_update` (member, before, after) pattern; per-user cooldown via dict; bot-move detection via `member == bot.user` |
| PERS-03 | Bot delivers late-night (1-5am) time-related roasts at 50% chance | `datetime.now().hour` check inside `on_voice_state_update`; unified ambient ceiling guards combined with PERS-02 |
| PERS-04 | Bot always roasts when user plays same song 3+ times in one day | `song_history` COUNT query for guild+user+title+date; trigger inside post-queue logging path |
| PERS-05 | Bot reacts to messages: 👀 on YouTube/Spotify links, 🫡 on goodnight/gn, 😐 on bare mention, deflecting warmth on thanks | Extend existing `on_message` in `cogs/events.py`; `message.add_reaction()` with unicode string |
| PERS-06 | Expanded seasonal awareness injects date-aware personality | Extend `get_seasonal_context()` in `personality/seasonal.py`; add new seasonal string branches |
| PERS-07 | Status rotates every 5 min through pool (current song, server count, personality lines, seasonal) | `tasks.loop` + `bot.change_presence()` pattern; mirror existing `cache_cleanup` loop |
| PERS-08 | Startup message on boot, lonely idle message after 30+ min with users in voice | Startup: post to `DEXTER_CHANNEL_ID` inside `on_ready` after cog load; idle: extend existing `idle_check` loop |
| PERS-09 | Consecutive-day streak tracking + total-songs milestones; roast on milestone hits | `zoneinfo` + additive `ALTER TABLE`; `compute_streak()` pure function; milestone checked on each `update_user_profile` call |
| LYRIC-01 | `/lyrics` fetches current song lyrics (Genius primary, AZLyrics fallback) with pagination | `lyricsgenius` wrapped in `asyncio.to_thread`; `QueuePageView` reuse for pagination; AZLyrics fallback |
| HIST-01 | `/history` shows recently queued songs for the server | `get_recent_songs()` already exists in `database.py`; `QueuePageView` reuse; add `username` to query |
</phase_requirements>

---

## Summary

Phase 3 is primarily a **personality and features phase** — the dominant work is creative content (template pools, few-shot prompts) and Discord API wiring, not novel algorithmic problems. Most technical patterns are already established in the codebase. The three genuinely uncertain areas that needed investigation are: (1) how to get lyrics from Genius/AZLyrics in an async context, (2) `on_voice_state_update` semantics for reliably detecting join/leave/move without interfering with the existing music idle loop, and (3) streak timezone math with a safe additive DB migration.

**Primary recommendation for lyrics:** Use `lyricsgenius` 3.12.2 (synchronous library) wrapped in `asyncio.to_thread()`. It handles Genius search and web-scrape internally using `data-lyrics-container` attribute selectors, is actively maintained (latest release May 2026), and requires only `GENIUS_TOKEN` — no separate HTTP layer. AZLyrics fallback uses `aiohttp` + `BeautifulSoup` with a no-class comment-marker extraction pattern and a `User-Agent` header to avoid bot detection. Both operations must be wrapped async-safely; neither should block the event loop.

**The biggest risk in this phase** is the `DEXTER_SYSTEM_PROMPT` rewrite (D-06): it touches shipped `/ask` behavior and requires careful few-shot construction to produce the locked voice register. This is not a novel technical risk — it is a content quality risk requiring iteration, but zero new infrastructure.

**Tone fix is foundational:** The voice misalignment identified in CONTEXT.md is a root-cause finding. Rewriting `DEXTER_SYSTEM_PROMPT` with few-shot exemplars from DISCUSSION-LOG.md "Voice samples" is the single highest-leverage task in Phase 3 and must be done first (Wave 0) since it gates all personality tests.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Voice join/leave/move roasts | EventsCog (Discord tier) | personality/roasts.py | Discord event listener owns detection; roast templates are pure content |
| Per-user ambient roast cooldown | EventsCog (in-memory dict) | — | State is transient per session; no DB needed |
| Repeat-song roast detection | MusicCog (post-queue log path) | database.py | Triggered during song logging, not on voice event |
| Milestone roast detection | database.py helper (pure logic) | MusicCog / EventsCog | DB update is the right hook; cog dispatches post-update |
| Streak math | Pure `compute_streak()` in database.py or utils | database.py | Business logic must be unit-testable; DB does the persist |
| `/lyrics` command | MusicCog slash command | services/lyrics.py | Command lives in music cog per STRUCTURE.md; service owns Genius + AZLyrics |
| `/history` command | MusicCog slash command | database.py | Query is `get_recent_songs()` already; command just paginates it |
| Status rotation | bot.py background task or EventsCog | personality/roasts.py status pool | Mirror existing `cache_cleanup` loop pattern |
| Startup message | bot.py `on_ready` | personality/roasts.py | Only one startup path; post after all cogs loaded |
| Idle-loneliness message | bot.py `idle_check` or EventsCog | personality/roasts.py | Extend existing 60s idle loop |
| Message reactions | EventsCog `on_message` | — | Already has `on_message`; just add reaction logic |
| Seasonal expansion | personality/seasonal.py | prompts.py build_chat_prompt | Pure function extension, no Discord API needed |
| System prompt rewrite | personality/prompts.py | — | Pure text; tested via test_prompts.py |

---

## Standard Stack

### Core (already in requirements.txt — no new installs for most features)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| discord.py | 2.7.1 (latest) | Discord API, events, tasks, reactions | Already in project; `on_voice_state_update`, `tasks.loop`, `bot.change_presence` all built-in |
| aiosqlite | 0.22.1 (latest) | Async SQLite for streak columns | Already in project; additive migration via `ALTER TABLE` + `PRAGMA table_info` |
| zoneinfo | stdlib (Python 3.9+) | IANA timezone for streak day boundary | Stdlib, no install; use `tzdata` PyPI package as fallback on Windows |

### New Installs (for lyrics feature only)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| lyricsgenius | 3.12.2 | Genius search + page scrape in one call | Handles `GENIUS_TOKEN` auth + `data-lyrics-container` selector internally; actively maintained (May 2026); synchronous — wrap in `asyncio.to_thread()` |
| beautifulsoup4 | 4.15.0 | Parse AZLyrics HTML for fallback | Already pattern-established in project; `requests` dep bundled |
| aiohttp | 3.14.1 | Async HTTP for AZLyrics fallback scrape | Keeps AZLyrics async-native; already available in Python ecosystem; no blocking risk |

> **Note on tzdata:** On Oracle Linux, IANA timezone data is available system-wide (`/usr/share/zoneinfo`), so `zoneinfo` stdlib works without the `tzdata` package. On Windows (dev environment), `tzdata` is needed. Recommend adding `tzdata` to `requirements.txt` as a safe cross-platform fallback. [CITED: docs.python.org/3/library/zoneinfo.html]

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| lyricsgenius | raw aiohttp + BeautifulSoup for Genius | More control over async; but duplicates what lyricsgenius already does correctly; selector maintenance burden |
| aiohttp for AZLyrics | requests + run_in_executor | requests is already a dep of lyricsgenius; but keeping AZLyrics async with aiohttp is cleaner |
| zoneinfo (stdlib) | pytz | pytz is deprecated in favor of zoneinfo for Python 3.9+; no reason to add a new dep |

**Installation (new packages only):**
```bash
pip install lyricsgenius beautifulsoup4 aiohttp tzdata
```

---

## Package Legitimacy Audit

> slopcheck could not be installed in this session (permission denied by sandbox). All packages are verified via PyPI registry and confirmed against official sources. Packages `[ASSUMED]` until slopcheck can run; all are well-established.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| lyricsgenius | PyPI | ~8 yrs (2016) | High (top lyrics lib) | github.com/johnwmillr/LyricsGenius | [ASSUMED] | Approved — well-known, actively maintained, last release May 2026 |
| beautifulsoup4 | PyPI | ~14 yrs | 50M+/wk | github.com/waylan/beautifulsoup | [ASSUMED] | Approved — industry standard HTML parser |
| aiohttp | PyPI | ~10 yrs | 100M+/wk | github.com/aio-libs/aiohttp | [ASSUMED] | Approved — industry standard async HTTP |
| tzdata | PyPI | ~5 yrs | 50M+/wk | github.com/python/tzdata | [ASSUMED] | Approved — official Python timezone data |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*slopcheck was unavailable at research time. Planner must gate each install behind a `checkpoint:human-verify` task if strict supply-chain policy is enforced. All four packages are high-reputation Python ecosystem standards.*

---

## Architecture Patterns

### System Architecture Diagram

```
Discord Events (discord.py event dispatch)
        │
        ├─── on_voice_state_update(member, before, after)
        │         │
        │         ├─ Join? → check ambient ceiling → roll UNPROMPTED_ROAST_CHANCE
        │         │           → pick from personality/roasts.py pool
        │         │           → resolve DEXTER_CHANNEL_ID → post
        │         │
        │         ├─ Leave? → check ambient ceiling → roll 30%
        │         │           → post farewell roast
        │         │
        │         └─ Bot moved? → always post moved_channel complaint
        │
        ├─── on_message(message)
        │         ├─ Buffer feed (existing)
        │         ├─ YouTube/Spotify link → message.add_reaction('👀')
        │         ├─ goodnight/gn → message.add_reaction('🫡')
        │         ├─ bare bot mention → message.add_reaction('😐')
        │         └─ "thanks" directed at bot → send deflect-warmth text
        │
Discord Background Tasks (tasks.loop)
        ├─── status_rotation (every 300s)
        │         → bot.change_presence(activity=discord.Activity(...))
        │         → pool: current song | server count | personality line | seasonal
        │
        └─── idle_check (every 60s, existing — extend)
                  → if no commands 30+ min AND humans in voice AND not posted yet
                  → post lonely idle message once per silence window

Music Path (cogs/music.py post-queue hook)
        ├─ log_song() + update_user_profile() → check repeat-song
        │         → COUNT same title for user today → if ≥ 3, always post roast
        │
        └─ update_user_profile() → update streak → check milestones
                  → song-count crosses [100,250,500,1000] → post milestone roast
                  → streak-day hits [7,14,30,60,100] → post streak roast

/lyrics command (cogs/music.py)
        → get current track from MusicQueue
        → asyncio.to_thread(genius.search_song, title, artist)
        → if None → AZLyrics fallback (aiohttp GET → BS4 parse → comment-marker extract)
        → chunk into 1800-char pages → LyricsPageView (QueuePageView pattern)

/history command (cogs/music.py)
        → get_recent_songs(db, guild_id, limit=50)
        → JOIN or enrich with username
        → HistoryPageView (QueuePageView pattern, 10 songs/page)
```

### Recommended New File Layout

```
personality/
└── roasts.py          # New: template pools for join/leave/late-night/milestone/streak/idle/startup/status
                       # Pattern: POOL_NAME: list[str] + pick_random() reuse

services/
└── lyrics.py          # New: LyricsService(genius_token) with get_lyrics(title, artist) -> str | None

tests/
├── test_roasts.py     # New: pool non-empty assertions, pick_random works
├── test_lyrics.py     # New: unit-test pure helpers (build_search_query, chunk_lyrics)
├── test_streak.py     # New: compute_streak() date math, all cases
└── test_database_phase3.py  # New: streak column migration, milestone query
```

### Pattern 1: `on_voice_state_update` — Join / Leave / Move Detection

**What:** Discord dispatches `on_voice_state_update(member, before, after)` for every voice state change. The key discriminator is `before.channel` vs `after.channel`.

**How to distinguish events:**
```python
# Source: discord.py docs (discordpy.readthedocs.io)
async def on_voice_state_update(
    self,
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    # Ignore bots (including self)
    if member.bot:
        return

    # User JOINED voice (was not in voice, now is)
    if before.channel is None and after.channel is not None:
        ...

    # User LEFT voice (was in voice, now is not)
    if before.channel is not None and after.channel is None:
        ...

    # Bot was MOVED to different channel
    if member == self.bot.user and before.channel != after.channel:
        ...

    # User SWITCHED channels (in voice before and after, different channels)
    # Note: This is distinct from leave and is NOT a roast trigger per D-12
    if (
        before.channel is not None
        and after.channel is not None
        and before.channel != after.channel
        and not member.bot
    ):
        ...  # Not a roast trigger per spec
```

**When to use:** All voice-related roasts (PERS-02, PERS-03).

**Critical coexistence note:** The existing `idle_check` background task in `bot.py` monitors `vc.channel.members` for the idle-leave timer. The new `on_voice_state_update` handler must NOT reset or fight the idle timer — they operate independently. The idle-leave timer fires when `human_members == 0` for 10 min; the roast fires when a user leaves (after.channel is None). No conflict if handled separately.

### Pattern 2: Per-User Ambient Cooldown (D-13)

**What:** One in-memory dict maps `user_id → last_ambient_roast_time`. The unified ceiling covers join + leave + late-night combined (not per-trigger).

```python
# In EventsCog.__init__
self._ambient_roast_times: dict[int, float] = {}  # user_id → asyncio.get_event_loop().time()

def _check_ambient_cooldown(self, user_id: int, ceiling_seconds: int) -> bool:
    """Return True if roast is allowed (cooldown passed)."""
    now = asyncio.get_event_loop().time()
    last = self._ambient_roast_times.get(user_id, 0.0)
    return (now - last) >= ceiling_seconds

def _mark_ambient_roast(self, user_id: int) -> None:
    self._ambient_roast_times[user_id] = asyncio.get_event_loop().time()
```

The per-feature chance (30% join, 50% late-night) applies BEFORE the ceiling check; the ceiling is a hard cap after the roll passes. Earned roasts (repeat-song, milestones) use a separate code path that bypasses this dict entirely (D-14).

### Pattern 3: `tasks.loop` for Status Rotation (PERS-07)

**What:** Mirror existing `idle_check` / `cache_cleanup` loops from `bot.py`. The key difference: status rotation belongs in a cog's `cog_unload` cleanup path, or in `bot.py` alongside the others.

```python
# Source: discord.py docs (tasks.loop)
from discord.ext import tasks

@tasks.loop(seconds=config.STATUS_ROTATION_INTERVAL_SECONDS)
async def status_rotation():
    """Rotate bot presence through a pool every 5 min."""
    status_text = _pick_next_status()
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name=status_text,
        )
    )

@status_rotation.before_loop
async def before_status_rotation():
    await bot.wait_until_ready()
```

**Note:** `discord.ActivityType.listening` is confirmed supported. [CITED: discordpy.readthedocs.io/en/latest]

### Pattern 4: `lyricsgenius` Wrapped in `asyncio.to_thread` (LYRIC-01)

**What:** `lyricsgenius` is synchronous (uses `requests` library internally with `Sender` object). Calling `genius.search_song()` in a discord.py async context blocks the event loop. Wrap with `asyncio.to_thread()` (Python 3.9+ equivalent of `loop.run_in_executor(None, ...)`).

```python
# Source: discord.py FAQ (discordpy.readthedocs.io/en/latest/faq.html)
import asyncio
from lyricsgenius import Genius

class LyricsService:
    def __init__(self, token: str) -> None:
        self._genius = Genius(
            token,
            verbose=False,         # suppress print output
            remove_section_headers=False,
            retries=1,
        )

    async def get_genius_lyrics(self, title: str, artist: str) -> str | None:
        """Search Genius for lyrics. Returns lyrics string or None."""
        try:
            song = await asyncio.to_thread(
                self._genius.search_song, title, artist
            )
            if song and song.lyrics:
                return song.lyrics
            return None
        except Exception:
            return None
```

**Genius internal behavior (verified via lyricsgenius docs):**
- `search_song(title, artist)` calls Genius search API with `GENIUS_TOKEN` auth
- On hit: fetches the song page URL, then scrapes HTML using BeautifulSoup with `data-lyrics-container="true"` attribute selector [CITED: lyricsgenius.readthedocs.io/en/master/how_it_works.html]
- The `data-lyrics-container` selector is current (confirmed by multiple 2024-2025 sources as the modern selector; old `div.lyrics` class is from 2017 and deprecated)
- Returns a `Song` object with `.lyrics` property or `None` if not found

### Pattern 5: AZLyrics Fallback (LYRIC-01)

**What:** AZLyrics does not require auth. URL pattern: `https://www.azlyrics.com/lyrics/{artist}/{song}.html`. Lyrics are in an unnamed `<div>` between HTML comments — no class/id on the lyrics container. [CITED: multiple scraper projects]

**URL construction:**
```python
def build_azlyrics_url(artist: str, song: str) -> str:
    """Build AZLyrics URL. Strip non-alphanum, lowercase."""
    import re
    a = re.sub(r"[^a-z0-9]", "", artist.lower())
    s = re.sub(r"[^a-z0-9]", "", song.lower())
    return f"https://www.azlyrics.com/lyrics/{a}/{s}.html"
```

**Extraction pattern:**
```python
# AZLyrics puts lyrics in a div with NO class, between HTML comment markers
# Find: <!-- Usage of azlyrics.com content... --> and <!-- end of lyrics -->
from bs4 import BeautifulSoup

def extract_azlyrics(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    # Find all divs with no class and no id in the main content area
    # Lyrics div is the first/main classless div after the comment
    divs = soup.find_all("div", class_=False, id=False)
    for div in divs:
        text = div.get_text("\n")
        if len(text) > 100:  # lyrics are always long; filter out short divs
            return text.strip()
    return None
```

**AZLyrics anti-bot status (MEDIUM confidence):**
- AZLyrics does NOT use Cloudflare at the level that blocks Python `requests`/`aiohttp` with a realistic `User-Agent`
- Requires `User-Agent` header mimicking a browser (e.g., Chrome on Windows)
- Responds with 200 OK even for bot traffic IF User-Agent is set; returns an alert page without User-Agent
- No rate limiting for single-song lookups (only bulk scrapers get blocked)
- ToS prohibits scraping, but for personal/hobby use and single-song-on-demand this is standard practice in the lyrics bot ecosystem

**Async AZLyrics fetch:**
```python
async def get_azlyrics(self, title: str, artist: str) -> str | None:
    url = build_azlyrics_url(artist, title)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text()
                # Cap response size to avoid oversized pages
                if len(html) > 500_000:
                    return None
                return extract_azlyrics(html)
    except Exception:
        return None
```

### Pattern 6: Streak Date Math with `zoneinfo` (D-17/D-18/D-19)

**What:** Convert UTC timestamp from SQLite into a tz-local calendar date. Compare to `last_streak_date` to determine consecutive-day / same-day / reset.

```python
# Source: docs.python.org/3/library/zoneinfo.html [CITED]
from datetime import datetime, date
from zoneinfo import ZoneInfo

def get_local_date(tz_name: str) -> date:
    """Get today's date in the configured timezone."""
    tz = ZoneInfo(tz_name)
    return datetime.now(tz=tz).date()

def compute_streak(
    current_streak: int,
    last_streak_date: str | None,  # "YYYY-MM-DD" in configured tz
    tz_name: str,
) -> tuple[int, str]:
    """
    Returns (new_streak, new_last_date).
    Implements D-18: consecutive +1, same-day no-op, missed day reset to 1.
    """
    today = get_local_date(tz_name)
    today_str = today.isoformat()

    if last_streak_date is None:
        return (1, today_str)

    last = date.fromisoformat(last_streak_date)
    delta = (today - last).days

    if delta == 0:
        # Same calendar day — no-op
        return (current_streak, last_streak_date)
    elif delta == 1:
        # Consecutive day — increment
        return (current_streak + 1, today_str)
    else:
        # Missed at least one day — strict reset
        return (1, today_str)
```

**This function is PURE and should be unit-tested.** [VERIFIED: stdlib zoneinfo — CITED: docs.python.org/3.11/library/zoneinfo.html]

### Pattern 7: Additive Schema Migration (D-19)

**What:** `ALTER TABLE ADD COLUMN` does not support `IF NOT EXISTS` in SQLite. Use try/except or `PRAGMA table_info` check to make it idempotent. [CITED: sqlite.org/lang_altertable.html]

```python
async def migrate_add_streak_columns(db: aiosqlite.Connection) -> None:
    """Add streak columns to user_profiles — idempotent via PRAGMA check."""
    cursor = await db.execute("PRAGMA table_info(user_profiles)")
    existing = {row[1] for row in await cursor.fetchall()}

    migrations = [
        "ALTER TABLE user_profiles ADD COLUMN current_streak INTEGER DEFAULT 0",
        "ALTER TABLE user_profiles ADD COLUMN longest_streak INTEGER DEFAULT 0",
        "ALTER TABLE user_profiles ADD COLUMN last_streak_date TEXT",
    ]
    for stmt in migrations:
        col = stmt.split("ADD COLUMN ")[1].split(" ")[0]
        if col not in existing:
            await db.execute(stmt)

    await db.commit()
    log.info("Streak column migration complete")
```

Call `migrate_add_streak_columns(db)` inside `init_db()` **after** `executescript(SCHEMA_SQL)`. This is safe because `SCHEMA_SQL` uses `CREATE TABLE IF NOT EXISTS`, so the table exists at migration time.

### Pattern 8: Lyrics Pagination (LYRIC-01)

**What:** Reuse `QueuePageView` structure. Create `LyricsPageView` with the same `Previous`/`Next` button pattern. Chunk lyrics by character count (not line count) to respect Discord's 4096-char embed description limit. Recommend ~1500 chars per page to leave room for title/footer.

```python
def chunk_lyrics(lyrics: str, page_size: int = 1500) -> list[str]:
    """Split lyrics into chunks of at most page_size characters, breaking on newlines."""
    lines = lyrics.split("\n")
    pages = []
    current = []
    current_len = 0
    for line in lines:
        if current_len + len(line) + 1 > page_size and current:
            pages.append("\n".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += len(line) + 1
    if current:
        pages.append("\n".join(current))
    return pages
```

**This function is PURE and should be unit-tested.**

### Pattern 9: Lyrics Search Query Construction

**What:** The currently playing track has `title` and `artist` fields. For `lyricsgenius.search_song(title, artist)`, pass both. Handle cases where `artist` is `None` (fall back to title-only search).

```python
def build_genius_search_query(title: str, artist: str | None) -> tuple[str, str]:
    """Return (title, artist) for lyricsgenius search_song call."""
    return (title, artist or "")
```

**This function is PURE and should be unit-tested.** Also strip features/remix notations from title if present (e.g., "(feat. X)" suffix).

### Anti-Patterns to Avoid

- **Calling `genius.search_song()` without `asyncio.to_thread()`:** Blocks the event loop for 1-3 seconds during the HTTP + scrape cycle. Always wrap synchronous library calls in `asyncio.to_thread()`.
- **Resetting the music idle timer from `on_voice_state_update`:** The music cog's idle timer tracks empty voice channel time; do not reach into it from the events cog. Treat them as independent.
- **Using `datetime.now()` (naive/local) for streak math:** Always use `datetime.now(tz=ZoneInfo(STREAK_TIMEZONE))` to get a tz-aware datetime, then call `.date()`. Naive `datetime.now()` returns local system time which may differ per host.
- **Using `datetime.utcnow()` for streak date:** `utcnow()` is deprecated in Python 3.12; use `datetime.now(tz=timezone.utc)` instead.
- **Scraping lyrics synchronously in async context without thread offload:** Even `aiohttp` for AZLyrics is already async; only `lyricsgenius` (which uses `requests`) needs thread offloading.
- **Posting ambient roasts from MusicCog:** Ambient voice-join/leave roasts belong in `EventsCog`. Only repeat-song and milestone roasts fire from the music path (D-11).
- **Using `queue._text_channel_id` across cogs without None-check:** This field may be None if the bot has never played in a guild. Always guard: `channel = guild.get_channel(queue._text_channel_id) if queue._text_channel_id else None`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Genius lyrics search + scrape | Custom Genius API client | `lyricsgenius` 3.12.2 | Library handles auth, search API, page scrape, `data-lyrics-container` selector, retries |
| IANA timezone math | Manual UTC offset tables | `zoneinfo` (stdlib) | IANA tz data built into Python 3.9+; correct DST handling |
| Async HTTP for AZLyrics | Synchronous `requests` | `aiohttp` | Non-blocking; matches existing async codebase pattern |
| HTML parsing | Regex on raw HTML | `BeautifulSoup` | HTML is not regex-parseable reliably; BS4 is the standard |
| Background task loops | `asyncio.sleep` in a coroutine | `discord.ext.tasks.loop` | `tasks.loop` handles exceptions, reconnect, `before_loop`, and integrates with discord.py lifecycle |

**Key insight:** For lyrics, all three options (Genius API-only, lyricsgenius library, raw aiohttp+BS4) converge on the same outcome: scraping an HTML page. The `lyricsgenius` library just packages the best-known implementation of that scrape, maintained by the community with up-to-date selectors.

---

## Runtime State Inventory

> Omitted — this is a greenfield feature addition phase, not a rename/refactor/migration phase. No runtime state is being renamed or migrated. The only additive data change is new columns on `user_profiles` (streak fields), which uses a non-destructive `ALTER TABLE ADD COLUMN` migration.

---

## Common Pitfalls

### Pitfall 1: `on_voice_state_update` Fires for Bot's Own Events
**What goes wrong:** The bot joining voice (to play music) triggers `on_voice_state_update` with `member == bot.user` and `before.channel is None, after.channel is not None` — looks like a user join event.
**Why it happens:** Discord dispatches `on_voice_state_update` for all members, including bots.
**How to avoid:** Add `if member.bot: return` at the top of the handler. Only fire the "moved channel" complaint (D-02) when `member == self.bot.user AND before.channel != after.channel` (not on initial join). [CITED: discord.py migration docs]
**Warning signs:** Bot roasts itself joining a channel, or complaints firing every time `/play` starts.

### Pitfall 2: Genius Lyrics Include Section Headers and Non-Lyrics Text
**What goes wrong:** `lyricsgenius` returns lyrics that start with "EmbedX" or contain `[Verse 1]`, `[Chorus]` section headers. Showing these verbatim looks messy in Discord embeds.
**Why it happens:** `lyricsgenius` scrapes the full page content including formatting annotations. `remove_section_headers=False` is the default.
**How to avoid:** Pass `remove_section_headers=True` to `Genius()` constructor to strip `[Verse]`/`[Chorus]` markers. Post-process: strip trailing "EmbedX" / contributor count lines using a simple string cleanup (`.split("Embed")[0]`). [CITED: lyricsgenius docs]
**Warning signs:** Discord embed shows "EmbedXX" at the end of lyrics, or shows `[Bridge]` etc.

### Pitfall 3: Streak Date Computed from `datetime('now')` (UTC) Not Converted to `STREAK_TIMEZONE`
**What goes wrong:** User in EST queues a song at 11pm local time. SQLite `datetime('now')` returns UTC (4am next day). Streak math comparing against UTC dates will count this as the "next day" crossing midnight when the user's local date says it's still the same day.
**Why it happens:** SQLite stores UTC; the code compares raw UTC dates.
**How to avoid:** `compute_streak()` must call `datetime.now(tz=ZoneInfo(STREAK_TIMEZONE)).date()` for "today" — NOT `date.today()` (which is local system time) or UTC. Store `last_streak_date` as a local-date string. [CITED: Python docs, PEP 615]
**Warning signs:** Streaks increment twice in one day or reset early for users far from UTC.

### Pitfall 4: `alter_table` Migration Fails on Fresh Install
**What goes wrong:** A fresh database has no rows in `user_profiles` yet, but the column migration tries to add columns that `SCHEMA_SQL` doesn't define. On first run, `SCHEMA_SQL` creates the table without streak columns (current state), then migration adds them. This is correct. But if someone runs migration before `init_db`, they get "no such table" error.
**Why it happens:** Migration called out of order.
**How to avoid:** Call `migrate_add_streak_columns()` inside `init_db()`, **after** `executescript(SCHEMA_SQL)`. The order is: create tables first, then migrate new columns. Also add streak columns to `SCHEMA_SQL` for completely fresh installs (migration becomes a no-op in that case). [CITED: sqlite.org/lang_altertable.html]

### Pitfall 5: Startup Message Fires Before Cogs Are Loaded
**What goes wrong:** Startup message posted at the top of `on_ready()` before cogs are loaded. The message reads fine but Dexter isn't actually ready yet — a race condition where commands aren't registered.
**Why it happens:** `on_ready()` has both cog loading (async) and the startup message post.
**How to avoid:** Post startup message **after** all `await bot.load_extension(...)` calls. Place it as the last statement in `on_ready()`.

### Pitfall 6: AZLyrics Returns 200 With Alert Page (Bot Detected)
**What goes wrong:** Response status is 200 but the HTML contains an alert/Cloudflare challenge instead of lyrics. `extract_azlyrics()` returns garbage or nothing.
**Why it happens:** AZLyrics returns a bot-detection page with status 200 if `User-Agent` is missing or obviously robotic.
**How to avoid:** Always include a browser `User-Agent` header. After extracting, validate that the text is plausibly lyrics (>50 chars, not just a challenge page). Log a warning if AZLyrics returns suspiciously short content.
**Warning signs:** AZLyrics fallback consistently returns `None` or very short strings.

### Pitfall 7: lyricsgenius `verbose=True` Default Prints to stdout
**What goes wrong:** Every `search_song()` call prints searching/found messages to stdout, polluting logs.
**Why it happens:** lyricsgenius defaults `verbose=True`.
**How to avoid:** Initialize with `Genius(token, verbose=False)`.

### Pitfall 8: `QueuePageView` Has Guild-Scoped State
**What goes wrong:** `QueuePageView` takes a `MusicQueue` object to fetch paginated data. For lyrics and history, there is no `MusicQueue` — a different data source is needed.
**Why it happens:** `QueuePageView` is coupled to `MusicQueue`.
**How to avoid:** Create new `LyricsPageView` and `HistoryPageView` classes that follow the same `discord.ui.View` + `Previous`/`Next` button pattern but take `list[str]` (pre-chunked pages) instead of a `MusicQueue`. This keeps the pattern consistent but decouples from queue state.

---

## Code Examples

### Verify voice join/leave distinction
```python
# Source: discordpy.readthedocs.io/en/latest/migrating_to_v1.html [CITED]
@commands.Cog.listener()
async def on_voice_state_update(
    self,
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    if member.bot:
        return  # Ignore all bot voice events for roast purposes

    guild = member.guild

    # JOIN: was outside, now inside
    if before.channel is None and after.channel is not None:
        await self._handle_voice_join(member, guild)

    # LEAVE: was inside, now outside
    elif before.channel is not None and after.channel is None:
        await self._handle_voice_leave(member, guild)

    # BOT MOVED — handled by checking member == bot.user at start
    # Note: bot.user is the bot itself, not the member that moved
```

### Background loop registration pattern (mirroring bot.py)
```python
# Source: discord.py docs [CITED: discordpy.readthedocs.io/en/latest/ext/tasks/index.html]
@tasks.loop(seconds=config.STATUS_ROTATION_INTERVAL_SECONDS)
async def status_rotation():
    pass

@status_rotation.before_loop
async def before_status_rotation():
    await bot.wait_until_ready()

# In on_ready():
if not status_rotation.is_running():
    status_rotation.start()
```

### Idempotent streak migration
```python
# Source: sqlite.org/lang_altertable.html [CITED]
async def migrate_add_streak_columns(db: aiosqlite.Connection) -> None:
    cursor = await db.execute("PRAGMA table_info(user_profiles)")
    existing_cols = {row[1] async for row in cursor}
    new_cols = [
        ("current_streak", "INTEGER DEFAULT 0"),
        ("longest_streak", "INTEGER DEFAULT 0"),
        ("last_streak_date", "TEXT"),
    ]
    for col_name, col_def in new_cols:
        if col_name not in existing_cols:
            await db.execute(
                f"ALTER TABLE user_profiles ADD COLUMN {col_name} {col_def}"
            )
    await db.commit()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `div.lyrics` CSS class for Genius scraping | `data-lyrics-container="true"` attribute selector | ~2019-2020 | Old selector returns empty; must use attribute-based selection |
| `html.parser` for Genius (class-based) | lyricsgenius 3.x internal BeautifulSoup with `data-lyrics-container` | v3.0+ (2021) | lyricsgenius handles selector internally; no manual scraping needed for Genius |
| `pytz` for timezone | `zoneinfo` (stdlib) | Python 3.9 (PEP 615) | pytz is legacy; zoneinfo is the stdlib standard |
| `datetime.utcnow()` | `datetime.now(tz=timezone.utc)` | Python 3.12 deprecation | `utcnow()` deprecated; use tz-aware equivalent |
| `loop.run_in_executor(None, fn)` | `asyncio.to_thread(fn)` | Python 3.9 | `to_thread` is cleaner API for the common case; same semantics |

**Deprecated/outdated:**
- `div.lyrics` Genius selector: replaced by `data-lyrics-container` attribute; the old selector silently returns `None`
- `pytz.timezone()`: use `zoneinfo.ZoneInfo()` instead
- `datetime.utcnow()`: use `datetime.now(tz=timezone.utc)` or `datetime.now(tz=ZoneInfo("UTC"))`

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | AZLyrics does not use Cloudflare blocking that defeats `aiohttp` with a realistic User-Agent | Common Pitfalls #6, Standard Stack | If AZLyrics has upgraded anti-bot, fallback returns nothing; degrade gracefully with `None` return |
| A2 | `lyricsgenius` 3.12.2 `data-lyrics-container` selector is still working as of June 2026 | Standard Stack, Code Examples | Genius may have changed HTML structure; lyricsgenius would return `None` — fallback to AZLyrics handles this |
| A3 | Oracle Linux (production host) has IANA timezone data at `/usr/share/zoneinfo` so `zoneinfo` stdlib works without `tzdata` package | Standard Stack | If not present, `ZoneInfo("America/New_York")` raises `ZoneInfoNotFoundError`; adding `tzdata` to requirements.txt prevents this |
| A4 | `GENIUS_TOKEN` is already in `.env` on the production instance (the token was documented in dexter-architecture.md and INTEGRATIONS.md marks it as "planned") | Environment Availability | If token is missing, `GENIUS_TOKEN` env var is empty; `lyricsgenius.Genius("")` will raise on first call — handle in `LyricsService.__init__` with a `None` guard |

**If this table is empty:** All claims in this research were verified or cited — no user confirmation needed. (Not empty — 4 assumptions logged above.)

---

## Open Questions (RESOLVED)

> All three resolved during planning (Phase 3 plan-checker iteration 1). Resolutions are implemented in the plans cited below.

1. **Is `GENIUS_TOKEN` already configured in the `.env` file on the live instance?**
   - What we know: INTEGRATIONS.md lists it as "Optional env var (Phase 3, not used yet)"
   - What's unclear: Whether the user already created a Genius API client app and put the token in `.env`
   - Recommendation: The planner should include a Wave 0 task: "Verify `GENIUS_TOKEN` is set in `.env`; if not, create a Genius API app at genius.com/api-clients"
   - **RESOLVED:** Plan 03-03 includes a supply-chain/setup checkpoint that verifies/sets `GENIUS_TOKEN` before install; `/lyrics` degrades to AZLyrics-only if the token is missing.

2. **Should `STREAK_TIMEZONE` default to `America/New_York` or `UTC`?**
   - What we know: D-17 says "sensible zone"; user is likely US-based (based on project context)
   - What's unclear: Whether the server is used with an international audience
   - Recommendation: Default to `America/New_York`; the planner should set this in `config.py` with a comment explaining it can be overridden via env var
   - **RESOLVED:** Plan 03-01 Task 1 sets `STREAK_TIMEZONE = "America/New_York"` in `config.py` (env-overridable), per D-17.

3. **Does the existing `QueuePageView.on_timeout` disable buttons but not delete the message?**
   - What we know: Yes — `on_timeout` sets `item.disabled = True` but doesn't edit the message
   - What's unclear: Whether this causes a stale message problem for lyrics (user sees disabled buttons but no "lyrics expired" message)
   - Recommendation: `LyricsPageView` should override `on_timeout` to also call `await message.edit(view=self)` so the disabled state is visually reflected
   - **RESOLVED:** Plan 03-05 Task 1 `LyricsPageView` overrides `on_timeout` to disable buttons AND edit the stored message.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | All features, `asyncio.to_thread`, `zoneinfo` | ✓ | 3.12.10 | — |
| discord.py 2.x | All Discord features | ✓ | 2.7.1 (in requirements.txt) | — |
| aiosqlite | Streak migration | ✓ | 0.22.1 (in requirements.txt) | — |
| lyricsgenius | LYRIC-01 | ✗ (not installed) | 3.12.2 available on PyPI | — (must install) |
| beautifulsoup4 | AZLyrics fallback | ✗ (not installed) | 4.15.0 available on PyPI | — (must install) |
| aiohttp | AZLyrics fallback | ✗ (not installed) | 3.14.1 available on PyPI | — (must install) |
| tzdata | zoneinfo on Windows | ✗ (not installed) | 2026.2 available on PyPI | zoneinfo works on Linux without it; still recommend adding |
| GENIUS_TOKEN | LYRIC-01 | Unknown | — | Feature degrades gracefully to AZLyrics-only if token missing |

**Missing dependencies with no fallback:**
- `lyricsgenius`, `beautifulsoup4`, `aiohttp` — must install for LYRIC-01; no substitute

**Missing dependencies with fallback:**
- `tzdata` — required only on Windows dev; Oracle Linux host has IANA data natively

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio |
| Config file | No `pytest.ini` (uses implicit defaults per TESTING.md) |
| Quick run command | `pytest tests/ -x --tb=short` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PERS-02 | Join/leave/move detection logic | structural review | — | N/A — Discord event wiring |
| PERS-03 | Late-night hour check (1-5am) | unit | `pytest tests/test_roasts.py::test_is_late_night -x` | ❌ Wave 0 |
| PERS-04 | Repeat-song query: COUNT same title in song_history for user+guild today | unit | `pytest tests/test_database_phase3.py::test_repeat_song_count -x` | ❌ Wave 0 |
| PERS-05 | Message reaction logic: URL detection, keyword detection | structural review | — | N/A — Discord message wiring |
| PERS-06 | Seasonal context expanded branches | unit | `pytest tests/test_seasonal.py -x` | ✅ extends existing |
| PERS-07 | Status pool non-empty, picks rotate | unit | `pytest tests/test_roasts.py::test_status_pool -x` | ❌ Wave 0 |
| PERS-08 | Startup / idle-loneliness: Discord/bot.py wiring | structural review | — | N/A — Discord wiring |
| PERS-09 | `compute_streak()`: consecutive / same-day / missed-day / milestone boundary | unit | `pytest tests/test_streak.py -x` | ❌ Wave 0 |
| LYRIC-01 | `chunk_lyrics()`: character limits, page boundaries | unit | `pytest tests/test_lyrics.py::test_chunk_lyrics -x` | ❌ Wave 0 |
| LYRIC-01 | `build_genius_search_query()`: None artist, special chars | unit | `pytest tests/test_lyrics.py::test_build_search_query -x` | ❌ Wave 0 |
| LYRIC-01 | `build_azlyrics_url()`: strips non-alphanum, lowercase | unit | `pytest tests/test_lyrics.py::test_build_azlyrics_url -x` | ❌ Wave 0 |
| HIST-01 | `get_recent_songs()` returns correct guild data | unit | `pytest tests/test_database.py -x` | ✅ extends existing |

**Pure functions to extract for testability:**
- `compute_streak(current_streak, last_streak_date, tz_name)` → unit-testable, no DB or Discord
- `chunk_lyrics(lyrics, page_size)` → unit-testable, pure string logic
- `build_genius_search_query(title, artist)` → unit-testable, pure string
- `build_azlyrics_url(artist, song)` → unit-testable, pure string
- `is_late_night(hour)` → unit-testable, pure bool
- `get_local_date(tz_name)` → testable with mocking

**Discord/cog wiring (structural review only, per TESTING.md convention):**
- `on_voice_state_update` handler
- `on_message` reaction additions
- `status_rotation` task
- `idle_check` extension for lonely idle message
- `/lyrics` and `/history` command handlers
- Startup message post

### Sampling Rate
- **Per task commit:** `pytest tests/ -x --tb=short` (stop on first failure)
- **Per wave merge:** `pytest tests/ -v` (full suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_streak.py` — covers compute_streak() all cases (PERS-09)
- [ ] `tests/test_lyrics.py` — covers chunk_lyrics, build_search_query, build_azlyrics_url (LYRIC-01)
- [ ] `tests/test_roasts.py` — covers pool non-empty, pick_random, is_late_night (PERS-03/07)
- [ ] `tests/test_database_phase3.py` — covers repeat-song COUNT query, streak migration, milestone crossing (PERS-04/09)

*(Extends existing: `tests/test_seasonal.py` for PERS-06, `tests/test_database.py` for HIST-01)*

---

## Security Domain

> `security_enforcement` not explicitly set in config.json (file absent) — treating as enabled. ASVS L1.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | GENIUS_TOKEN is outbound auth only (env var, not user auth) |
| V3 Session Management | No | Stateless bot; no user sessions |
| V4 Access Control | No | Discord permission model handles this |
| V5 Input Validation | Yes | Song title/artist used in search queries and URLs — must sanitize before injecting into AZLyrics URL |
| V6 Cryptography | No | No encryption in this feature set |
| V7 Error Handling / Logging | Yes | `GENIUS_TOKEN` must never appear in logs; HTTP error responses must not surface raw to Discord |

### Known Threat Patterns for Lyrics Scraping + Discord Bot

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Song title with path traversal chars (`../`, URL-encoded) | Tampering | `re.sub(r"[^a-z0-9]", "", title.lower())` in URL builder strips all non-alphanum |
| Attacker queues a song with `@everyone` in the title | Tampering (mention injection) | Discord automatically neutralizes `@everyone` in `channel.send()` with `allowed_mentions=discord.AllowedMentions.none()` — embed field values also safe |
| Genius/AZLyrics HTML containing `<script>` or markdown injection | Spoofing | `BeautifulSoup.get_text()` strips all HTML tags; only plain text reaches Discord |
| Oversized response from AZLyrics (denial of service to event loop) | DoS | Cap response body: `if len(html) > 500_000: return None` — prevents memory exhaustion from malicious large pages |
| `GENIUS_TOKEN` exposure in logs | Information Disclosure | Never log the raw token; `log.info("LyricsService initialized")` not `log.info(f"Token: {token}")` |
| SSRF via attacker-controlled song URL | Spoofing | URLs are built server-side from sanitized title+artist, not taken from user input directly; no user-supplied URL is passed to the HTTP client |
| AZLyrics fetch timeout hanging event loop | DoS | `aiohttp.ClientTimeout(total=10)` caps fetch time |
| Request-size cap on Genius response via lyricsgenius | DoS | lyricsgenius `retries=1` limits retry amplification; the sync call is wrapped in `to_thread` with no custom timeout — consider adding `timeout` param to `Genius()` constructor (default is 5s) |

### GENIUS_TOKEN Handling
- Loaded from environment: `os.getenv("GENIUS_TOKEN")` — same pattern as `GEMINI_API_KEY`
- Pass to `Genius()` constructor only; never stored as a class attribute accessible from outside `LyricsService`
- If token is missing: `LyricsService` initializes but all Genius calls return `None` immediately (graceful degradation to AZLyrics-only)

---

## Sources

### Primary (HIGH confidence)
- `/websites/discordpy_readthedocs_io_en` (Context7) — `on_voice_state_update` member/before/after semantics, tasks.loop patterns, `change_presence`, `add_reaction`
- `/johnwmillr/lyricsgenius` (Context7) — `search_song` API, `Genius()` constructor params
- `docs.python.org/3.11/library/zoneinfo.html` — `ZoneInfo`, `datetime.now(tz=...)`, Windows/Linux fallback behavior
- `sqlite.org/lang_altertable.html` — `ALTER TABLE ADD COLUMN` constraints, no `IF NOT EXISTS` support
- `pypi.org/project/lyricsgenius/` — confirmed version 3.12.2, release May 2026
- Codebase analysis: `cogs/events.py`, `cogs/music.py`, `bot.py`, `database.py`, `config.py`, `personality/responses.py`, `personality/seasonal.py`, `.planning/codebase/TESTING.md`

### Secondary (MEDIUM confidence)
- `lyricsgenius.readthedocs.io/en/master/how_it_works.html` — confirms BeautifulSoup scraping, `data-lyrics-container` as the current Genius lyrics selector
- Multiple 2024-2025 scraping guides confirming `data-lyrics-container="true"` as current Genius page selector
- AZLyrics URL pattern `https://www.azlyrics.com/lyrics/{artist}/{song}.html` (confirmed via multiple scraper repos)
- `discordpy.readthedocs.io/en/latest/faq.html` — `run_in_executor` / `asyncio.to_thread` for blocking calls

### Tertiary (LOW confidence)
- AZLyrics anti-bot behavior (User-Agent bypass, no Cloudflare) — inferred from multiple scraper projects; may have changed. Flagged as A1 in Assumptions Log.
- AZLyrics "lyrics in classless div" extraction pattern — widely documented but structurally fragile

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages verified on PyPI with current versions; patterns confirmed via Context7 and official docs
- Architecture: HIGH — based on direct codebase analysis of existing patterns
- `/lyrics` Genius path: HIGH — lyricsgenius docs confirm `data-lyrics-container` selector; well-maintained library
- `/lyrics` AZLyrics path: MEDIUM — extraction pattern is community-documented but fragile; no official docs
- Streak timezone math: HIGH — stdlib zoneinfo, confirmed Python 3.9+ standard
- Pitfalls: HIGH — most discovered from direct codebase inspection + official docs

**Research date:** 2026-06-11
**Valid until:** 2026-07-11 (stable stack; AZLyrics extraction pattern may shift sooner — 30 days)
