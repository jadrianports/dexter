# Phase 12: Richer Music/UX — Pattern Map

**Mapped:** 2026-06-30
**Files analyzed:** 10 new/modified files
**Analogs found:** 10 / 10

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `database.py` (guild_jams DDL + 5 helpers) | model | CRUD | `database.py` lines 160–169 (user_playlists DDL) + lines 660–766 (save/get/list/delete/count_playlist) | exact |
| `database.py` (get_user_skip_rate) | model | CRUD | `database.py` lines 442–461 (`get_leaderboard_skips`) | exact |
| `cogs/library.py` (/jam group) | controller | request-response | `cogs/library.py` lines 424–654 (/playlist group) | exact |
| `cogs/ops.py` (/skips command) | controller | request-response | `cogs/ops.py` lines 147–191 (/leaderboard command) | exact |
| `services/lyrics.py` (_get_lrclib + strip_lrc_headers) | service | request-response | `services/lyrics.py` lines 279–313 (`_get_azlyrics`) | exact |
| `logic/skip_stats.py` | utility | transform | `logic/playback.py` lines 1–22 (pure logic module) | role-match |
| `logic/autoqueue.py` | utility | transform | `logic/playback.py` lines 1–22 (pure logic module) | role-match |
| `cogs/ai.py` (try_auto_queue loop mutation) | controller | request-response | `cogs/ai.py` lines 307–334 (existing loop) | exact (modify in place) |
| `config.py` (3 new knobs) | config | — | `config.py` lines 118–139 (existing caps section) | exact |
| `tests/test_skip_stats.py`, `test_autoqueue_validate.py`, `test_lyrics_lrclib.py`, `test_database_phase12.py` | test | — | `tests/test_playback_logic.py` (Phase 10 pure-unit pattern) | role-match |

---

## Pattern Assignments

### `database.py` — guild_jams DDL (add to SCHEMA_SQL)

**Analog:** `database.py` lines 160–169 (`user_playlists` DDL) and lines 140–144 (`guild_queues` pattern)

**Schema pattern** (lines 160–169):
```python
# user_playlists template — swap user_id → guild_id, change PK accordingly
CREATE TABLE IF NOT EXISTS user_playlists (
    user_id    TEXT NOT NULL,
    name       TEXT NOT NULL,
    snapshot   JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, name)
);
CREATE INDEX IF NOT EXISTS idx_playlists_user ON user_playlists(user_id, updated_at DESC);

# guild_jams target DDL (idempotent, no $N params — plain DDL in SCHEMA_SQL):
CREATE TABLE IF NOT EXISTS guild_jams (
    guild_id   TEXT NOT NULL,
    name       TEXT NOT NULL,
    snapshot   JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (guild_id, name)
);
CREATE INDEX IF NOT EXISTS idx_jams_guild ON guild_jams(guild_id, updated_at DESC);
```

---

### `database.py` — save/get/list/delete/count_jam helpers

**Analog:** `database.py` lines 664–766 (`save_playlist`/`get_playlist`/`list_playlists`/`delete_playlist`/`count_playlists`)

**save pattern** (lines 677–684):
```python
async with pool.acquire() as conn:
    await conn.execute(
        "INSERT INTO user_playlists (user_id, name, snapshot, created_at, updated_at)"
        " VALUES ($1, $2, $3::jsonb, now(), now())"
        " ON CONFLICT (user_id, name)"
        " DO UPDATE SET snapshot = EXCLUDED.snapshot, updated_at = now()",
        user_id, name, json.dumps(snapshot),
    )
# guild_jams: replace user_id → guild_id, table → guild_jams, conflict target → (guild_id, name)
```

**get pattern** (lines 699–709) — JSONB normalisation:
```python
payload = row["snapshot"]
if isinstance(payload, str):
    payload = json.loads(payload)
return list(payload)
# Same normalisation required for get_jam — asyncpg may return JSONB as str or list
```

**delete pattern** (lines 747–753) — parse asyncpg status string:
```python
result = await conn.execute(
    "DELETE FROM user_playlists WHERE user_id = $1 AND name = $2",
    user_id, name,
)
return result.rsplit(" ", 1)[-1] != "0"
# guild_jams: WHERE guild_id = $1 AND name = $2
```

**count pattern** (lines 756–766):
```python
row = await conn.fetchrow(
    "SELECT COUNT(*) AS cnt FROM user_playlists WHERE user_id = $1",
    user_id,
)
return int(row["cnt"]) if row else 0
# guild_jams: WHERE guild_id = $1
```

---

### `database.py` — get_user_skip_rate (new helper)

**Analog:** `database.py` lines 442–461 (`get_leaderboard_skips`) — same table, same guild-scoped pattern

**Query pattern** (lines 451–461):
```python
async with pool.acquire() as conn:
    return await conn.fetch(
        "SELECT title, COUNT(*) AS skip_count"
        " FROM song_history"
        " WHERE guild_id = $1 AND was_skipped = true"
        " GROUP BY title"
        " HAVING COUNT(*) >= 1"
        " ORDER BY skip_count DESC"
        " LIMIT $2",
        guild_id, config.LEADERBOARD_TOP_N,
    )

# get_user_skip_rate target query (all-time, guild-scoped, D-07/D-09):
async def get_user_skip_rate(
    pool: asyncpg.Pool, *, guild_id: str, user_id: str
) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT COUNT(*) AS total_plays,"
            " COUNT(*) FILTER (WHERE was_skipped = true) AS total_skips"
            " FROM song_history"
            " WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )
# min-plays floor applied in logic/skip_stats.py, NOT here
```

---

### `cogs/library.py` — /jam command group

**Analog:** `cogs/library.py` lines 424–654 (`/playlist` group)

**Group declaration pattern** (lines 426–429):
```python
playlist = app_commands.Group(
    name="playlist",
    description="Save and load named playlists",
)
# jam group: name="jam", description="Manage this server's shared mixtapes"
```

**Name validation + cap check pattern** (lines 448–487):
```python
name = name.strip()
if not name:
    await interaction.response.send_message("playlist name can't be empty.", ephemeral=True)
    return
if len(name) > config.PLAYLIST_NAME_MAX_LENGTH:
    await interaction.response.send_message(
        f"that name is too long. keep it under {config.PLAYLIST_NAME_MAX_LENGTH} chars.",
        ephemeral=True,
    )
    return
# cap check — allow overwrite without counting twice:
existing = await get_playlist(self.bot.pool, user_id=user_id, name=name)
if existing is None:
    current_count = await count_playlists(self.bot.pool, user_id=user_id)
    if current_count >= config.PLAYLISTS_MAX_PER_USER:
        await interaction.response.send_message(pick_random(PLAYLIST_CAP_HIT), ephemeral=True)
        return
# jam: swap get_jam/count_jams, use guild_id, config.JAMS_PER_GUILD_MAX
```

**Queue snapshot pattern** (lines 489–498):
```python
snapshot = [t.to_dict() for t in queue.tracks]
await save_playlist(self.bot.pool, user_id=user_id, name=name, snapshot=snapshot)
await interaction.response.send_message(
    f"{pick_random(PLAYLIST_SAVED)} ({len(snapshot)} tracks, \"{name}\")",
    ephemeral=True,
)
```

**Load + QueueFullError pattern** (lines 540–553):
```python
await interaction.response.defer(ephemeral=True)
queue = music_cog.get_queue(guild.id)
was_idle = not queue.is_playing
added = 0
truncated = 0
for track_dict in rows:
    track = Track.from_dict({**track_dict, "requested_by": interaction.user.id})
    try:
        queue.add(track)
        added += 1
    except QueueFullError:
        truncated += 1
# /jam load must use this same try/except pattern (Pitfall 7)
```

**Now-playing guard for /jam add** — mirror the `/favorite` nothing-playing check:
- Check `track = queue.get_current()` — if None, respond ephemeral "nothing's playing right now."
- `/jam add` appends `track.to_dict()` to existing snapshot: `get_jam` → append → `save_jam`

---

### `cogs/ops.py` — /skips command

**Analog:** `cogs/ops.py` lines 147–191 (`/leaderboard` command)

**Defer + DB call + embed pattern** (lines 165–190):
```python
await interaction.response.defer()
guild_id = str(guild.id)
try:
    songs_rows = await get_leaderboard_songs(self.pool, guild_id=guild_id)
    skips_rows = await get_leaderboard_skips(self.pool, guild_id=guild_id)
    streaks_rows = await get_leaderboard_streaks(self.pool, guild_id=guild_id)
except asyncio.TimeoutError:
    log.warning("/leaderboard DB timeout")
    await interaction.followup.send("database is being slow. try again in a bit.", ephemeral=True)
    return
except Exception as exc:
    log.error("/leaderboard DB error: %s", exc)
    await interaction.followup.send("couldn't load the leaderboard right now.", ephemeral=True)
    return
embed = embeds.leaderboard_embed(songs_rows, skips_rows, streaks_rows)
await interaction.followup.send(embed=embed)

# /skips pattern: same defer + two DB calls (get_leaderboard_skips + get_user_skip_rate)
# + logic/skip_stats.compute_skip_rate() for the personal footer
# + ephemeral=False (public embed like /leaderboard)
# + roast-flavored footer from Dexter personality ("you skip X% of what you queue. bold of you to keep going.")
```

---

### `services/lyrics.py` — _get_lrclib + strip_lrc_headers

**Analog:** `services/lyrics.py` lines 279–313 (`_get_azlyrics`)

**aiohttp fetch pattern** (lines 291–313):
```python
async with aiohttp.ClientSession() as session:
    async with session.get(
        url,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=10),
    ) as resp:
        if resp.status != 200:
            log.warning("AZLyrics returned HTTP %s for %s", resp.status, url)
            return None
        html = await resp.text()
        if len(html) > 500_000:
            log.warning("AZLyrics response too large (%d bytes)", len(html))
            return None
        # ... extract + return sanitize_lyrics(text)
except Exception as exc:
    log.warning("AZLyrics fetch failed: %s", exc)
    return None

# _get_lrclib: same skeleton; diff = JSON parse + iterate array + strip_lrc_headers()
# URL: f"https://lrclib.net/api/search" with params={"track_name": title, "artist_name": artist}
# No User-Agent header needed (no bot detection; LRCLIB is API-first)
# Filter: skip item if item.get("instrumental") or not item.get("plainLyrics")
# Call chain: strip_lrc_headers(plain) → sanitize_lyrics(cleaned) → return if len >= 50
```

**strip_lrc_headers pure helper** (new, no analog — add just above `_get_lrclib`):
```python
_LRC_HEADER_RE = re.compile(
    r"^\[(ti|ar|al|by|offset|length|re|ve):[^\]]*\]\s*$",
    re.MULTILINE,
)

def strip_lrc_headers(text: str) -> str:
    return _LRC_HEADER_RE.sub("", text).strip()
```

**Fallback chain insertion point** — find `get_lyrics()` where AZLyrics fallback returns None and add:
```python
# After AZLyrics returns None:
lyrics = await self._get_lrclib(title, artist)
if lyrics:
    return lyrics
```

---

### `logic/skip_stats.py` (new pure module)

**Analog:** `logic/playback.py` lines 1–22 (module docstring + no-discord constraint)

**Module header pattern** (lines 1–21 of logic/playback.py):
```python
"""Pure <domain> decision logic extracted from <cog> (TEST-01).

All functions in this module are deterministic and side-effect-free: no Discord imports,
no asyncio, no database calls, no random, no datetime.now(), no time.monotonic().
"""
from __future__ import annotations
# NO: import discord, import asyncio, import asyncpg
```

**Function signature:**
```python
def compute_skip_rate(
    total_plays: int,
    total_skips: int,
    min_plays: int,
) -> float | None:
    """Return 0.0–1.0 skip rate, or None if below min_plays floor (D-08)."""
    if total_plays < min_plays:
        return None
    if total_plays == 0:
        return 0.0
    return total_skips / total_plays
```

---

### `logic/autoqueue.py` (new pure module)

**Analog:** `logic/playback.py` lines 1–22 (same pure-module convention)

**Module constraints** — same header: no discord, asyncio, asyncpg imports. Only `re` from stdlib.

**Core signatures:**
```python
import re

_PUNCT = re.compile(r"[^\w\s]")
_NOISE_TOKENS = frozenset({
    "official", "audio", "video", "music", "lyrics", "lyric",
    "hd", "hq", "4k", "8k", "remastered", "remaster", "explicit",
    "clean", "live", "performance", "feat", "featuring", "ft",
    "visualizer", "mv",
})
_STOP_WORDS = frozenset({"the", "a", "an", "in", "of", "and", "or"})

def _normalize_for_match(text: str) -> set[str]:
    """Return significant token set (lowercase, no punct, no noise/stop words, len>=2)."""
    ...

def validate_youtube_match(
    youtube_title: str,
    suggested_title: str,
    suggested_artist: str,
) -> bool:
    """Token-set containment: all title+artist tokens must appear in yt_tokens."""
    ...
```

---

### `cogs/ai.py` — try_auto_queue loop mutation (UX-04)

**Analog:** `cogs/ai.py` lines 307–334 (existing loop — modify in place)

**Current pattern** (lines 307–334) — to be replaced:
```python
for suggestion in suggestions[: config.AUTO_QUEUE_SONGS_PER_ROUND]:
    search_query = f"{suggestion['title']} {suggestion['artist']}"
    results = await self.bot.youtube_service.async_search(search_query, count=1)
    if not results:
        continue
    result = results[0]
    # ... extract + add to queue
```

**New pattern** (D-13 + D-14):
```python
from logic.autoqueue import validate_youtube_match  # add to imports

# In try_auto_queue, replace the loop:
tracks_added = []
for suggestion in suggestions:                              # D-14: iterate ALL
    if len(tracks_added) >= config.AUTO_QUEUE_SONGS_PER_ROUND:
        break
    search_query = f"{suggestion['title']} {suggestion['artist']}"
    results = await self.bot.youtube_service.async_search(
        search_query, count=config.AUTO_QUEUE_SEARCH_CANDIDATES  # D-13: was count=1
    )
    if not results:
        continue
    validated = None
    for result in results:
        if validate_youtube_match(
            result.get("title", ""),
            suggestion["title"],
            suggestion["artist"],
        ):
            validated = result
            break
    if validated is None:
        log.info("auto-queue: all %d candidates rejected for '%s'",
                 len(results), suggestion["title"])
        continue                                            # D-14: try next suggestion
    # ... existing extract + Track + queue.add() using validated
```

---

### `config.py` — three new knobs

**Analog:** `config.py` lines 118–142 (caps section — `FAVORITES_MAX_PER_USER`, `PLAYLISTS_MAX_PER_USER`, `LEADERBOARD_TOP_N`)

**Insertion point** — after the Phase 8 section (`LEADERBOARD_TOP_N = 5`), before Phase 9:
```python
# --- Phase 12: Richer Music/UX ---
JAMS_PER_GUILD_MAX = 25             # per-guild jam cap (mirrors PLAYLISTS_MAX_PER_USER, D-05)
SKIP_STATS_MIN_PLAYS = 5            # min data points before showing skip rate (D-08)
AUTO_QUEUE_SEARCH_CANDIDATES = 3    # YouTube candidates per auto-queue suggestion (D-13)
# Note: reuse PLAYLIST_NAME_MAX_LENGTH (60) for jam names — no new knob needed (D-05)
```

---

## Shared Patterns

### Ephemeral Responses (all /jam subcommands)
**Source:** `cogs/library.py` lines 443–498
**Apply to:** all `/jam` subcommands — all guard messages `ephemeral=True`; only `/jam list` may be ephemeral by default (mirrors `/playlist list`)

### asyncpg $N Parameterization (no string interpolation)
**Source:** `database.py` lines 451–461, 677–684
**Apply to:** all `guild_jams` helpers, `get_user_skip_rate`
Constraint: all SQL values passed as `$1`, `$2`, etc. — never f-strings in SQL.

### JSONB String Normalisation
**Source:** `database.py` lines 706–709
**Apply to:** `get_jam` — asyncpg may return JSONB as `str` or `list`; always normalise with `if isinstance(payload, str): payload = json.loads(payload)`.

### MusicCog Access from Other Cogs
**Source:** `cogs/library.py` lines 462–469
**Apply to:** `/jam save`, `/jam add`, `/jam load`
```python
music_cog = self.bot.get_cog("MusicCog")
if music_cog is None:
    await interaction.response.send_message("music isn't loaded right now.", ephemeral=True)
    return
queue = music_cog.get_queue(guild.id)
```

### Delete Result Parsing (asyncpg status string)
**Source:** `database.py` lines 747–753
**Apply to:** `delete_jam`
```python
return result.rsplit(" ", 1)[-1] != "0"
```

### LyricsService fallback chain
**Source:** `services/lyrics.py` `get_lyrics()` method (find the `_get_azlyrics` call)
**Apply to:** `_get_lrclib` insertion — add after the AZLyrics branch returns None

---

## No Analog Found

All files have direct in-repo analogs. No novel patterns required.

---

## Metadata

**Analog search scope:** `database.py`, `cogs/library.py`, `cogs/ops.py`, `cogs/ai.py`, `services/lyrics.py`, `logic/`, `config.py`
**Files scanned:** 9 source files
**Pattern extraction date:** 2026-06-30
