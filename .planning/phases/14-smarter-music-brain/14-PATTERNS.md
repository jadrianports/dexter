# Phase 14: Smarter Music Brain - Pattern Map

**Mapped:** 2026-07-02
**Files analyzed:** 8 (5 modified, 2 new commands added to existing cogs, plus config)
**Analogs found:** 8 / 8

RESEARCH.md already contains HIGH-confidence, directly-verified code excerpts for every new
helper (Code Examples section). This document cross-references those excerpts against the real
analog files (confirmed by direct reads this session) and adds import/error-handling/testing
context RESEARCH.md didn't fully spell out.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `database.py` (+ `get_recently_skipped`, `get_user_top_artist`/guild-scoped variant, `get_artist_cooccurrence`) | service/model (SQL helper) | CRUD (read aggregate) | `database.py::get_user_skip_rate` (1255-1276), `get_user_artist_activity` (1312-1349) | exact |
| `database.py` (`search_memories` + `kind` param) | service/model (SQL helper) | CRUD (read, ANN) | `database.py::search_memories` (899-939, existing) | exact — same function, additive param |
| `services/memory.py` (`recall` + `kind` param) | service | request-response | `services/memory.py::recall` (61-110+, existing) | exact — same function, additive param |
| `logic/autoqueue.py` (+ `is_recently_skipped_artist`) | utility (pure logic) | transform | `logic/autoqueue.py::validate_youtube_match` (64-89) | exact |
| `logic/taste.py` (+ `select_positive_taste_context`) | utility (pure logic) | transform | `logic/taste.py::summarize_taste` (105-148) | exact |
| `personality/prompts.py` (`build_recommendation_prompt` extended + 2 new builders) | utility (prompt template) | transform | `personality/prompts.py::build_chat_prompt` memory_context block (150-180) + existing `build_recommendation_prompt` (183-189) | exact |
| `cogs/ai.py` (`try_auto_queue` extended) | controller (Discord cog) | event-driven | `cogs/ai.py::try_auto_queue` (255-448, existing — being edited in place) | exact |
| `cogs/music.py` (+ `/discover` command) | controller (Discord cog, slash command) | request-response | `cogs/library.py::jam_save`/`jam_add` (702-830) for the guard/response/logging shape; `cogs/music.py`'s own `Track`/queue-add flow for the confirm-to-queue action | role-match |
| `cogs/library.py` (+ `/jam suggest` subcommand) | controller (Discord cog, slash command) | request-response | `cogs/library.py::jam_add` (774-830+) | exact |
| `config.py` (+ 6 new knobs) | config | — | `config.py` Phase 13 `TASTE_*` block (193-202) | exact |

## Pattern Assignments

### `database.py` — `get_recently_skipped`, `get_artist_cooccurrence`, top-artist helper (service, CRUD)

**Analog:** `get_user_skip_rate` (lines 1255-1276) and `get_user_artist_activity` (lines 1312-1349)

**Imports** (file header, lines 1-13 — already present, no new imports needed):
```python
from __future__ import annotations
import re
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import asyncpg
import json  # noqa: F401
import config
from utils.logger import log
```

**D-08 scoping + param-binding template** (verbatim structure to copy, from `get_user_skip_rate`):
```python
async def get_user_skip_rate(
    pool: asyncpg.Pool, *, guild_id: str, user_id: str
) -> asyncpg.Record | None:
    """... Aggregate is all-time (no date filter, D-09) and scoped to BOTH guild_id ($1)
    and user_id ($2) — preventing cross-guild and cross-user data leakage ...
    The min-plays floor is applied by the caller in logic/ — never here in SQL.
    All values bound as $1/$2 positional params — no string interpolation.
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT COUNT(*) AS total_plays,"
            " COUNT(*) FILTER (WHERE was_skipped = true) AS total_skips"
            " FROM song_history"
            " WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )
```

**Concrete new-helper code to copy verbatim** (RESEARCH.md Code Examples, verified HIGH-confidence
against real schema — use these signatures, docstrings, and param-binding as-is):

`get_recently_skipped` (D-01 negative hint source — guild-scoped, no per-user attribution):
```python
async def get_recently_skipped(
    pool: asyncpg.Pool, *, guild_id: str, since: datetime, limit: int
) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT title, artist"
            " FROM song_history"
            " WHERE guild_id = $1 AND was_skipped = true AND queued_at > $2"
            " ORDER BY queued_at DESC"
            " LIMIT $3",
            guild_id, since, limit,
        )
```

`get_artist_cooccurrence` (BRAIN-02 core — 100% SQL, guild-wide aggregate, entity is the artist
not the user, mirrors `get_leaderboard_skips`'s no-attribution discipline):
```python
async def get_artist_cooccurrence(
    pool: asyncpg.Pool, *, guild_id: str, anchor_artist: str, since: datetime, limit: int
) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch(
            "WITH anchor_days AS ("
            "  SELECT DISTINCT date_trunc('day', queued_at) AS play_day"
            "  FROM song_history"
            "  WHERE guild_id = $1 AND artist = $2 AND queued_at > $3"
            ")"
            " SELECT sh.artist, COUNT(*) AS co_occurrence"
            " FROM song_history sh"
            " JOIN anchor_days ad ON date_trunc('day', sh.queued_at) = ad.play_day"
            " WHERE sh.guild_id = $1 AND sh.artist IS NOT NULL"
            "   AND sh.artist <> $2 AND sh.queued_at > $3"
            " GROUP BY sh.artist"
            " ORDER BY co_occurrence DESC"
            " LIMIT $4",
            guild_id, anchor_artist, since, limit,
        )
```

**Top-artist anchor helper — planner decision required (Pitfall 2 / OQ2):** CONTEXT.md D-04 names
`user_artist_counts` (no `guild_id` column, cross-server lifetime counts) as the source. RESEARCH.md
recommends deriving a guild-scoped equivalent instead, following the exact `get_user_artist_activity`
template:
```python
# Option B (research-recommended): guild-scoped, matches D-08 template exactly
async def get_user_top_artist(
    pool: asyncpg.Pool, *, guild_id: str, user_id: str, limit: int
) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT artist, COUNT(*) AS play_count"
            " FROM song_history"
            " WHERE guild_id = $1 AND user_id = $2 AND artist IS NOT NULL"
            " GROUP BY artist"
            " ORDER BY play_count DESC"
            " LIMIT $3",
            guild_id, user_id, limit,
        )
```
Planner must pick Option A (`user_artist_counts` as literally named in D-04, no guild filter,
simpler) or Option B (above, guild-scoped, more "in this server" — research's recommendation).
Either is Criterion-4-safe (invoker's own data either way); this is a UX-correctness call, not a
security one.

**Error handling:** none of these helpers wrap exceptions internally — callers (`cogs/ai.py`,
new `/discover`/`/jam suggest` commands) already wrap DB calls in `try/except Exception` blocks
(see `try_auto_queue`'s outer `try` at line 269 and `except Exception as e: log.error(..., exc_info=True)`
at line 446) — mirror that, don't add new try/except inside `database.py` helpers.

---

### `database.py` — `search_memories` kind filter (service, CRUD, OQ1)

**Analog:** existing `search_memories` (lines 899-939, unread this session but fully quoted and
verified by RESEARCH.md's direct-code-read Pattern 2 — trust as HIGH confidence).

**Pattern to copy** (additive optional param, SQL clause omitted entirely when `None`, not
`kind IS NULL`):
```python
async def search_memories(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    query_embedding: list[float],
    k: int,
    kind: str | None = None,          # NEW — optional, defaults to unfiltered (byte-identical)
) -> list[asyncpg.Record]:
    kind_clause = " AND kind = $3" if kind is not None else ""
    params = [user_id, query_embedding] + ([kind] if kind is not None else [])
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT id, fact, kind, salience, hit_count, created_at, last_seen_at,"
            "       last_surfaced_at, surface_count,"
            "       1 - (embedding <=> $2) AS similarity"
            " FROM user_memories"
            f" WHERE user_id = $1{kind_clause}"
            " ORDER BY embedding <=> $2"
            " LIMIT $" + str(len(params) + 1),
            *params, k,
        )
```

---

### `services/memory.py` — `MemoryService.recall` kind filter (service, request-response)

**Analog:** the existing `recall()` method itself (lines 61-136), being edited in place — confirmed
by direct read this session.

**Imports** (already present, no changes needed — lines 15-39):
```python
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import asyncpg
import config
import database
import json
import re as _re
from logic.taste import resolve_decay_days
from models.memory import (
    MemoryFact, apply_floor, rerank, dedup_decision,
    choose_eviction, compute_salience, is_sensitive, contains_number,
)
from personality.prompts import DISTILL_PROMPT
from services.gemini import GeminiService, GeminiAPIError, GeminiRateLimitError
from utils.logger import log
```

**Core pattern** (add `kind: str | None = None` param, thread through to `database.search_memories`,
keep the exact same degrade-to-`[]` error handling that already exists):
```python
async def recall(
    self,
    user_id: str,
    guild_id: str,
    query_text: str,
    kind: str | None = None,   # NEW — e.g. "taste_episode" for D-03's positive-taste blend
) -> list[str]:
    try:
        vectors = await self._gemini.embed(
            [query_text], task_type="RETRIEVAL_QUERY", priority=1,
        )
        query_vec: list[float] = vectors[0]
    except (GeminiRateLimitError, GeminiAPIError) as e:
        log.debug(f"memory.recall: embed failed, returning [] ({type(e).__name__}: {e})")
        return []
    except Exception as e:
        log.debug(f"memory.recall: unexpected embed error, returning [] ({e})")
        return []
    # ... unchanged: database.search_memories(..., kind=kind) call, apply_floor, rerank, cap, bump
```

**Error handling pattern:** "no memory beats a wrong memory" (Pitfall 8) — every failure mode
degrades to `[]`, never raises up to the caller. Preserve this exactly; `kind` must not introduce
a new raise path.

---

### `logic/autoqueue.py` — `is_recently_skipped_artist` (utility, transform, D-02)

**Analog:** `validate_youtube_match` (lines 64-89) and `_normalize_for_match` (lines 38-56) in the
same file.

**Imports** (file header, lines 1-12 — no new imports needed, pure stdlib `re` already imported):
```python
from __future__ import annotations
import re
```

**Core pattern to copy verbatim** (RESEARCH.md Code Examples — reuses `_normalize_for_match`,
does NOT duplicate the tokenizer, does NOT use `difflib` — D-12 anti-pattern):
```python
def is_recently_skipped_artist(candidate_artist: str, skipped_artists: list[str]) -> bool:
    """Return True if candidate_artist's normalized tokens match any recently-skipped artist.

    Belt-and-suspenders hard filter (D-02) alongside the soft prompt instruction —
    runs independently of validate_youtube_match (hallucination guard stays unchanged).
    Empty candidate_artist or empty skipped_artists -> False (vacuous, never blocks).
    """
    candidate_tokens = _normalize_for_match(candidate_artist)
    if not candidate_tokens:
        return False
    for skipped in skipped_artists:
        skipped_tokens = _normalize_for_match(skipped)
        if skipped_tokens and skipped_tokens.issubset(candidate_tokens):
            return True
    return False
```

**Docstring/module-header convention to preserve** (module top, lines 1-8 — "pure, deterministic,
side-effect-free, no Discord/asyncio/DB/random/datetime.now()" contract):
```python
"""Pure auto-queue suggestion-validation logic extracted from AICog (UX-04).

All functions in this module are deterministic and side-effect-free: no Discord imports,
no asyncio, no database calls, no random, no datetime.now(), no time.monotonic().
"""
```

---

### `logic/taste.py` — `select_positive_taste_context` (utility, transform, D-03)

**Analog:** `summarize_taste` (lines 105-148) in the same file.

**Imports** (file header, lines 1-19 — no new imports needed):
```python
from __future__ import annotations
import enum
```

**Core pattern to copy verbatim** (RESEARCH.md Code Examples — round-robin interleave, dedup,
cap, UNATTRIBUTED collective output per Pitfall 4):
```python
def select_positive_taste_context(
    member_facts: list[list[str]], *, cap: int
) -> list[str]:
    """Flatten per-member recalled taste_episode facts into one capped, deduped list.

    Interleaves round-robin across members by index position so no single member's
    facts dominate the cap purely by list position (D-03 "collective, not per-listener").
    Deliberately UNATTRIBUTED — caller must not re-associate a fact with its member.
    """
    seen: set[str] = set()
    result: list[str] = []
    max_len = max((len(f) for f in member_facts), default=0)
    for i in range(max_len):
        for facts in member_facts:
            if i < len(facts) and facts[i] not in seen:
                seen.add(facts[i])
                result.append(facts[i])
                if len(result) >= cap:
                    return result
    return result
```

**Same-module doc-comment convention to preserve** (module header, lines 1-15 — accuracy-firewall
note applies): note that `select_positive_taste_context` returns raw fact *strings* (already
number-free by construction of `taste_episode` distillation, per Phase 13's firewall) — do not
add any numeric interpolation here.

---

### `personality/prompts.py` — extended `build_recommendation_prompt` + 2 new builders (utility, transform)

**Analog:** `build_chat_prompt`'s `memory_context` optional-block pattern (lines 150-180, confirmed
by direct read) and the existing `build_recommendation_prompt` (lines 183-189, confirmed — currently
takes only `recent_songs`).

**Imports:** `personality/prompts.py` builders are pure string templating — `import config` is done
locally inside `build_chat_prompt` (line 153, `import config` inside the function body, not at module
top) — mirror this local-import convention if a new builder needs a config knob.

**Optional-block pattern to copy verbatim** (byte-identical when empty — this is the exact structure
`build_chat_prompt` already uses for `memory_context`, lines 163-172):
```python
if memories:
    memory_context = (
        "THINGS YOU REMEMBER ABOUT THIS USER (episodes/opinions, not stats):\n"
        + "\n".join(f"- {m}" for m in memories)
        + "\nUse at most one of these, and only if it genuinely lands."
          " Do NOT invent details beyond these lines."
          " All numbers/counts come from USER CONTEXT above — never from these memories.\n\n"
    )
else:
    memory_context = ""
```

**Current `build_recommendation_prompt` being extended** (lines 183-189, exact current shape —
new kwargs must default to producing byte-identical output when omitted, per RESEARCH.md Pattern 1):
```python
def build_recommendation_prompt(recent_songs: list[dict]) -> str:
    """Build the auto-queue recommendation prompt from recent song history."""
    lines = []
    for song in recent_songs:
        artist = song.get("artist") or "Unknown"
        lines.append(f"- {song['title']} by {artist}")
    return MUSIC_RECOMMENDATION_PROMPT.format(recent_songs="\n".join(lines))
```

**Extended version to write** (RESEARCH.md Pattern 1, verified against the real current shape above
— note real code uses a per-song loop with `.get("artist") or "Unknown"`, keep that exact idiom
rather than the dict-comprehension shorthand in RESEARCH.md's illustrative snippet):
```python
def build_recommendation_prompt(
    recent_songs: list[dict],
    *,
    recently_skipped: list[dict] | None = None,
    positive_taste: list[str] | None = None,
) -> str:
    lines = []
    for song in recent_songs:
        artist = song.get("artist") or "Unknown"
        lines.append(f"- {song['title']} by {artist}")

    skip_block = ""
    if recently_skipped:
        skip_lines = "\n".join(
            f"- {s['title']} by {s.get('artist') or 'Unknown'}" for s in recently_skipped
        )
        skip_block = "\n\nAVOID these — the server keeps skipping them:\n" + skip_lines

    taste_block = ""
    if positive_taste:
        taste_lines = "\n".join(f"- {t}" for t in positive_taste)
        taste_block = "\n\nTHE ROOM TENDS TO LIKE:\n" + taste_lines

    return MUSIC_RECOMMENDATION_PROMPT.format(
        recent_songs="\n".join(lines),
    ) + skip_block + taste_block
```

**New `build_discover_commentary_prompt` / `build_jam_suggestion_prompt`:** no existing analog for
these two (net-new builders) — model them on `MUSIC_RECOMMENDATION_PROMPT`'s template-string shape
(a module-level `str` constant with `{placeholder}` slots, `.format()`-called from the builder
function) rather than inventing a new templating convention. `build_jam_suggestion_prompt` must
produce output that `cogs/ai.py::parse_suggestions` can parse unchanged (same `{title, artist}` JSON
array contract) — do not alter the JSON-shape instruction wording in ways that would require a new
parser.

---

### `cogs/ai.py` — `try_auto_queue` extended (controller, event-driven)

**Analog:** the function itself (lines 255-448), edited in place — confirmed by direct read.

**Imports** (lines 1-40, already present — add `database.get_recently_skipped`,
`database.get_artist_cooccurrence`/top-artist helper if directly called here, and
`logic.autoqueue.is_recently_skipped_artist`, `logic.taste.select_positive_taste_context`):
```python
from __future__ import annotations
import json, random, re
import discord
from discord import app_commands
from discord.ext import commands
import config
from database import get_recent_songs, increment_daily_stat
from logic.autoqueue import validate_youtube_match          # + is_recently_skipped_artist (NEW)
from logic.playback import should_start_playback
from models.queue import Track
from models.server_state import get_server_state, get_mood
from models.user_profile import get_user_summary
from personality.prompts import build_chat_prompt, build_recommendation_prompt
# ... personality.responses / roasts / seasonal, services.gemini errors, services.lyrics,
# utils.logger, utils.tasks.make_task — all unchanged
```

**In-voice member set reuse (D-03) — exact site to reuse**, lines 402-413 (already computes
non-bot voice members for the `auto_queue_ignored` write; D-03 says reuse this same enumeration
for the positive-taste `recall()` fan-out, not a second computation):
```python
vc = guild.voice_client
voice_members = (
    [m for m in vc.channel.members if not m.bot]
    if vc and vc.channel else []
)
```

**Negative-hint + positive-hint wiring point** — insert right before `prompt = build_recommendation_prompt(cleaned)`
at line 288, following the exact `try/except` shape already wrapping the whole function body (outer
`try` at line 269, `except GeminiRateLimitError` / `except GeminiAPIError as e` / `except Exception as e:
log.error(..., exc_info=True)` at lines 442-447 — new DB calls for skip-hint/taste-hint go inside this
same try block, degrading to empty lists on failure rather than raising, matching `recall()`'s own
degrade-to-`[]` contract).

**D-02 hard post-filter insertion point** — inside the per-suggestion validation loop (lines 311-341),
alongside the existing `validate_youtube_match` check at line 327 — add `is_recently_skipped_artist`
as an independent second gate on the same `validated` candidate, per D-02 ("runs independently of
validate_youtube_match").

**should_start_playback gotcha (scar #2, lines 372-391) — do NOT touch this logic** while wiring
hints; it must remain gated on `voice_client.is_playing()`/`is_paused()`, never `queue.is_playing`.

---

### `cogs/library.py` — `/jam suggest <name>` subcommand (controller, request-response, D-06/D-07)

**Analog:** `jam_add` (lines 774-830+, confirmed by direct read) — nothing-playing / empty-name /
too-long-name / cap-check guard sequence, ephemeral responses throughout.

**Imports:** `cogs/library.py` already imports `get_jam`, `count_jams`, `save_jam` from `database`
and `pick_random`, `NOTHING_PLAYING` from `personality.responses` — new imports needed: the Gemini
prompt builder (`build_jam_suggestion_prompt`), `services.youtube_service.async_search`,
`logic.autoqueue.validate_youtube_match`, `cogs.ai.parse_suggestions` (reuse — cog-to-cog import;
research flags moving to a shared module if this import is awkward).

**Guard sequence to copy verbatim shape** (from `jam_add`, lines 786-822 — guild-only check, name
strip/empty/length checks, `music_cog` presence check, ephemeral responses throughout):
```python
guild = interaction.guild
if guild is None:
    await interaction.response.send_message("this only works in a server.", ephemeral=True)
    return

name = name.strip()
if not name:
    await interaction.response.send_message("jam name can't be empty.", ephemeral=True)
    return

if len(name) > config.PLAYLIST_NAME_MAX_LENGTH:
    await interaction.response.send_message(
        f"that name is too long. keep it under {config.PLAYLIST_NAME_MAX_LENGTH} chars.",
        ephemeral=True,
    )
    return
```

**Existing-jam load pattern** (from `jam_add`, line 827): `existing = await get_jam(self.bot.pool,
guild_id=guild_id, name=name)` — `/jam suggest` needs `existing is not None` (error/"nothing to
suggest from" in-character message if the jam doesn't exist yet — unlike `jam_add`'s create-on-miss
semantics) since D-06 seeds Gemini with the jam's *existing* tracks as taste context.

**Propose-and-confirm (D-07) — no existing analog in `cogs/library.py`**; nearest UX precedent is
`cogs/music.py`'s `NowPlayingView` persistent-button pattern (`timeout=None` + stable `custom_id`s
registered in `setup_hook`, per CLAUDE.md Phase 7 gotcha) — but a one-shot confirm view (not
persistent across restarts) is more appropriate here; use `discord.ui.View(timeout=...)` with a
Confirm/Cancel button pair, NOT `timeout=None`/`setup_hook` registration (this view only needs to
survive one interaction round-trip, unlike the always-on now-playing controls).

**On confirm — mutation call, unchanged existing helper:**
```python
snapshot = [t.to_dict() for t in queue.tracks]  # existing tracks + validated additions
await save_jam(self.bot.pool, guild_id=guild_id, name=name, snapshot=snapshot)
```

**Validation loop — reuse verbatim from `cogs/ai.py::try_auto_queue` lines 326-341:**
```python
validated = None
for result in results:
    if validate_youtube_match(result.get("title", ""), suggestion["title"], suggestion["artist"]):
        validated = result
        break
if validated is None:
    continue  # D-07: drop, don't error; if none survive, in-character "nothing landed" message
```

---

### `cogs/music.py` — `/discover` command (controller, request-response, D-04/D-05)

**Analog:** `cogs/library.py::jam_save`/`jam_add` for the guard/response/ephemeral shape (guild-only
check, empty-state in-character message); `cogs/music.py`'s own existing `Track` construction +
`queue.add()` flow (see `try_auto_queue`'s Track-building block, lines 353-363, for the exact
`Track(...)` field shape to mirror when the confirm-to-queue button fires) for the "queue it now"
action.

**Cold-start / empty-history guard (D-05):** mirror the "not enough listening yet" in-character
message pattern the same way `jam_add`'s `NOTHING_PLAYING` guard works (lines 817-822) — a
`pick_random(...)` call against a new personality-response list, not a raw string, keeping with
`personality/responses.py`'s existing convention (`pick_random(RATE_LIMIT_MESSAGES)`, etc., already
imported in `cogs/ai.py` lines 21-29).

**Gemini call — commentary only, never picks (D-04 firewall):** reuse the exact `self.gemini.chat(prompt,
[], priority=2)` shape from `try_auto_queue` line 289, but the prompt (`build_discover_commentary_prompt`)
must instruct Gemini to *only* produce wrapping commentary text around SQL-supplied artist names —
never asked to invent a recommendation. No `parse_suggestions`/JSON-array contract needed here since
the picks are already 100% SQL-derived (D-04) — Gemini's reply is used as plain text, not parsed JSON.

**Confirm-to-queue button → track resolution:** on confirm, call `youtube_service.async_search` +
`async_extract` exactly as `try_auto_queue` does (lines 318-345), including the duration cap check
(`data["duration"] > config.MAX_SONG_DURATION_SECONDS`, line 350) before `queue.add(track)`.

---

### `config.py` — new Phase 14 knobs (config)

**Analog:** the Phase 13 `TASTE_*` block (lines 193-202, confirmed by grep).

**Pattern to copy** (flat module-level constants, inline comment citing the deciding-D-number,
grouped under a `# Phase 14` header comment mirroring the existing `# Phase 11/13` block style):
```python
# Phase 14: Smarter Music Brain (BRAIN-01/02/03) — all directional/Claude's-discretion (CONTEXT.md)
AUTO_QUEUE_SKIP_LOOKBACK_DAYS = 7        # D-01: recently-skipped window
AUTO_QUEUE_SKIP_HINT_CAP = 15            # D-01: max rows in the negative-hint block
AUTO_QUEUE_POSITIVE_TASTE_CAP = 4        # D-03: max injected taste_episode facts
DISCOVER_ADJACENT_COUNT = 3              # D-04: max /discover adjacent artists surfaced
DISCOVER_COOCCURRENCE_WINDOW_DAYS = 90   # D-04: get_artist_cooccurrence recency bound
JAM_SUGGEST_CANDIDATE_COUNT = 3          # D-06: /jam suggest candidate additions requested
```

---

## Shared Patterns

### D-08 scoping + param-binding discipline (cross-cutting — the verification target)
**Source:** `database.py::get_user_skip_rate` (1255-1276), `get_user_artist_activity` (1312-1349)
**Apply to:** every new `database.py` helper in this phase (`get_recently_skipped`,
`get_artist_cooccurrence`, top-artist helper, `search_memories` kind param)
- Bound `$N` positional params exclusively — never f-string/`.format()` SQL.
- `WHERE guild_id = $1 [AND user_id = $2]` — never merge cross-user rows into one result row.
- `queued_at > $N` bounds for index-friendliness against `idx_history_guild(guild_id, queued_at DESC)`
  / `idx_history_user(user_id, queued_at DESC)`.
- Thresholding/capping (e.g. `AUTO_QUEUE_SKIP_HINT_CAP`) is applied by the SQL `LIMIT` clause or the
  calling `logic/` module — never a Python-side floor buried in the cog.

### Pure `logic/` seam convention (cross-cutting)
**Source:** `logic/autoqueue.py` module docstring (lines 1-8), `logic/taste.py` module docstring (lines 1-15)
**Apply to:** `is_recently_skipped_artist` (logic/autoqueue.py), `select_positive_taste_context` (logic/taste.py)
- No Discord imports, no asyncio, no database calls, no random, no `datetime.now()`/`time.monotonic()`.
- Any nondeterministic value is fetched by the calling cog/task glue and passed in as a primitive.
- Every new pure function gets a docstring stating this contract explicitly (copy the module-header
  wording verbatim into the function's own docstring if it's a notable addition).

### Optional-signal, byte-identical-when-empty prompt extension (cross-cutting)
**Source:** `personality/prompts.py::build_chat_prompt`'s `memory_context` block (lines 163-172)
**Apply to:** `build_recommendation_prompt`'s new `recently_skipped`/`positive_taste` kwargs, and any
new prompt builder that accepts an optional signal
- `if signal: block = "...".join(...) else: block = ""` — never omit the `else` branch.
- New kwargs are keyword-only (`*,`) with `None`/falsy defaults so every existing call site is
  unaffected.
- A regression test should assert the omitted-kwarg call produces identical output to the pre-change
  function signature.

### Accuracy firewall — Gemini supplies voice, SQL supplies facts (cross-cutting, Critical Rule 12)
**Source:** `logic/taste.py::summarize_taste` docstring (lines 105-121, "FIREWALL" note) and CLAUDE.md
Critical Rule 12
**Apply to:** `/discover`'s commentary prompt (D-04 — Gemini never picks, only wraps SQL results in
voice), and any hard numbers surfaced anywhere in this phase (never embed a count into a memory or a
Gemini-generated string — numbers come from live SQL / already-rendered SQL result text only).

### Reuse-verbatim, don't-reimplement discipline (cross-cutting, D-12 anti-pattern precedent)
**Source:** `logic/autoqueue.py::validate_youtube_match`/`_normalize_for_match`
**Apply to:** `/jam suggest`'s validation loop (call `validate_youtube_match` unchanged, exact same
shape as `try_auto_queue` lines 326-333); `is_recently_skipped_artist` (reuse `_normalize_for_match`,
same-module private-function reuse is fine, do not duplicate the tokenizer or swap to `difflib`);
`parse_suggestions` (reuse from `cogs/ai.py` for `/jam suggest`'s Gemini JSON parsing — same
`{title, artist}` contract, do not write a second parser).

## No Analog Found

None — every new file/function in this phase has at least a role-match analog in the existing
codebase (see table above). The two genuinely novel Discord surfaces (`/discover` confirm-to-queue
button, `/jam suggest` propose-and-confirm view) have partial analogs (`NowPlayingView`'s button
pattern for the *mechanics*, `jam_add`'s guard/ephemeral shape for the *cog conventions*) rather
than an exact precedent, since Phase 14 is the first phase to add a one-shot (non-persistent)
confirm/cancel button flow.

## Metadata

**Analog search scope:** `database.py`, `services/memory.py`, `logic/autoqueue.py`, `logic/taste.py`,
`logic/skip_stats.py`, `personality/prompts.py`, `cogs/ai.py`, `cogs/library.py`, `cogs/music.py`
(structure only), `config.py`
**Files scanned:** 9 direct reads this session + RESEARCH.md's prior direct-code-read excerpts
(database.py 899-939/350-472, models/memory.py, cogs/ai.py 1-90/255-448, cogs/library.py 692-967,
personality/prompts.py full, bot.py 356-450/1121-1128, config.py 53-208)
**Pattern extraction date:** 2026-07-02
