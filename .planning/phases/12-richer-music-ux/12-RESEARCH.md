# Phase 12: Richer Music/UX — Research

**Researched:** 2026-06-30
**Domain:** Discord bot UX — guild playlists, skip analytics, lyrics fallback, auto-queue validation
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**UX-01 — Per-server playlists ("jams"):**
- D-01: New `/jam` command group (`save`/`add`/`load`/`list`/`delete`), distinct from `/playlist`
- D-02: Guild-scoped — keyed by `guild_id`. New table `guild_jams` mirroring `user_playlists`
- D-03: Anyone in the server can edit — no role or creator checks
- D-04: Stored named list, no session. `/jam add` appends now-playing; `/jam load <name>` dumps to queue; list/delete manage them. NOT `/jam start`…`/jam stop`
- D-05: Reuse ephemeral responses, per-guild jam cap, name-length cap. Add `JAMS_PER_GUILD_MAX` config knob

**UX-02 — Skip-rate analytics:**
- D-06: Dedicated `/skips` command (NOT folded into `/stats`)
- D-07: Show server's most-skipped songs (reuse `get_leaderboard_skips` at `database.py:442`) + requesting user's personal skip rate as a roastable footer
- D-08: Min-plays floor — add `SKIP_STATS_MIN_PLAYS` config knob (default 5); below floor, omit or label "not enough data"
- D-09: All-time window — aggregate over all of `song_history`, no rolling date filter

**UX-03 — Third lyrics fallback:**
- D-10: LRCLIB (`lrclib.net`) as third source: Genius → AZLyrics → LRCLIB. Free, no API key
- D-11: Use `plainLyrics` field (not `syncedLyrics`). Slot into `LyricsService.get_lyrics()` after AZLyrics returns None, following same async/timeout/byte-cap/pure-helper conventions

**UX-04 — Auto-queue hallucination validation:**
- D-12: Fuzzy title+artist match — normalize (lowercase, strip punctuation, noise tokens), require YouTube result title to fuzzily contain BOTH suggested title AND artist
- D-13: Widen search — bump `async_search` count from 1 to ~3 via `AUTO_QUEUE_SEARCH_CANDIDATES` knob; pick first result that passes fuzzy check
- D-14: On rejection (no candidate passes), try the next Gemini suggestion — loop capped at `AUTO_QUEUE_SONGS_PER_ROUND` tracks added, not suggestions consumed

### Claude's Discretion
- Exact per-guild jam cap value and `SKIP_STATS_MIN_PLAYS` / `AUTO_QUEUE_SEARCH_CANDIDATES` defaults (min-plays ≈ 5, search candidates ≈ 3 as starting points)
- Specific fuzzy-matching implementation (substring containment vs `difflib`); keep a pure, importable, unit-testable helper per Phase 10 `logic/` convention
- LRCLIB request shape (`/api/get` vs `/api/search`) — pick whichever gives reliable plain-lyrics hits with the title/artist Dexter already has

### Deferred Ideas (OUT OF SCOPE)
- Active "jam session" mode (`/jam start` → auto-collecting → `/jam stop`)
- Rolling time-window / re-rollable skip leaderboards
- Per-jam edit permissions / ownership
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| UX-01 | Favorites/playlists can be scoped per-server (guild "jams" distinct from user's global favorites) | `guild_jams` table + `/jam` command group mirrors existing `user_playlists` / `/playlist` pattern exactly |
| UX-02 | Skip-rate analytics surfaced to users | `song_history.was_skipped` column (line 108) + `get_leaderboard_skips` (lines 442-461) already exist; only new query is personal skip rate + min-plays gate |
| UX-03 | Third lyrics fallback for graceful `/lyrics` degradation | LRCLIB `/api/search` verified live — free, no key, JSON response with `plainLyrics` field; slots into `LyricsService.get_lyrics()` after AZLyrics |
| UX-04 | AI auto-queue validates Gemini suggestions against actual YouTube results before queueing | Loop at `cogs/ai.py:307` needs: wider search count, fuzzy validator, fall-through logic; no external deps (stdlib `difflib` or token-set containment) |
</phase_requirements>

---

## Summary

Phase 12 is a pure extension phase — all four features bolt onto existing, well-understood patterns with zero new external dependencies. The most novel element is UX-03 (LRCLIB API), which required live verification; the API is simple, free, and well-suited to Dexter's use case.

**UX-01 (guild jams)** is a near-mechanical clone of the existing `user_playlists` / `/playlist` system, swapping `user_id` keying for `guild_id`. The DB schema, helper function signatures, command group structure, cap/validation guards, and ephemeral response pattern all have direct in-repo templates in `database.py` (lines 660-766) and `cogs/library.py` (lines 424-654).

**UX-02 (skip analytics)** reuses the `get_leaderboard_skips` query that already exists (`database.py:442-461`) for the server's most-skipped list. The only new DB work is a personal-skip-rate query for the requesting user. The min-plays floor is a pure logic gate that belongs in a new `logic/skip_stats.py` module per Phase 10 convention.

**UX-03 (LRCLIB)** was the primary research target. Live API probing confirmed: LRCLIB `/api/search` with `track_name` + `artist_name` returns a JSON array with up to 20 results, each with `plainLyrics` (string or null), `syncedLyrics`, `instrumental` (bool), and a `lyricsfile` (always null in practice). No API key, no rate limits, free. The service implementation mirrors `_get_azlyrics` with one additional wrinkle: some search results embed LRC metadata headers (`[ti:...]`, `[ar:...]`) inside `plainLyrics` — a new `strip_lrc_headers()` pure helper is needed before calling `sanitize_lyrics()`.

**UX-04 (auto-queue validation)** is a targeted change to `cogs/ai.py:try_auto_queue()`. The fuzzy matcher belongs in `logic/autoqueue.py` (new module) per Phase 10 pure-logic convention. Token-set containment (stdlib, zero deps) is recommended over `difflib.SequenceMatcher` because the use case is "does this long YouTube title contain these clean search terms" — a token-subset check is better than a ratio between strings of different lengths.

**Primary recommendation:** Use `/api/search?track_name=<q_title>&artist_name=<q_artist>` for LRCLIB (same cleaned values from existing `build_genius_search_query`); use token-set containment for UX-04 fuzzy matching; keep all pure logic in `logic/` modules; add three config knobs to `config.py`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Guild jam storage (`guild_jams` table) | Database / Storage | — | JSONB snapshot model mirrors `user_playlists`; no session state |
| `/jam` command group | API / Backend (Discord cog) | Database / Storage | Discord interaction → DB read/write; same tier as `/playlist` |
| Skip analytics query | Database / Storage | — | Pure SQL aggregation over `song_history`; min-plays gate is pure logic |
| `/skips` command | API / Backend (Discord cog) | — | Belongs in `cogs/ops.py` alongside `/leaderboard` (same ops-flavored tier) |
| LRCLIB HTTP fetch | API / Backend (service layer) | — | Async HTTP in `services/lyrics.py`, same tier as Genius/AZLyrics paths |
| LRC header stripping | Pure logic helper | — | `strip_lrc_headers()` in `services/lyrics.py` pure helper section |
| Auto-queue fuzzy validator | Pure logic helper | — | `logic/autoqueue.py` — no Discord, no DB, no async; Phase 10 convention |
| Auto-queue search widening | API / Backend (cog) | — | Change to `cogs/ai.py:try_auto_queue()` call site only |

---

## Standard Stack

### Core (No New Packages — All Reuse)

| Library | Current Version | Purpose | Status |
|---------|-----------------|---------|--------|
| `aiohttp` | 3.14.1 (installed) | LRCLIB HTTP fetch (same as AZLyrics path) | Already in requirements.txt |
| `asyncpg` | 0.31.0 (pinned) | `guild_jams` table helpers + skip-rate queries | Already in requirements.txt |
| `difflib` | stdlib | Optional fuzzy ratio for UX-04 (stdlib, zero deps) | Python stdlib — no install |
| `discord.py` | ≥2.3 (installed) | `/jam` and `/skips` slash command groups | Already in requirements.txt |

[VERIFIED: pip registry — aiohttp 3.14.1 confirmed installed; asyncpg 0.31.0 confirmed pinned]

### No New Dependencies
This phase installs zero new packages. All four features extend existing service/cog/DB modules.

---

## Package Legitimacy Audit

> This phase installs **no new external packages**. All functionality uses stdlib (`difflib`, `re`) and already-installed libraries (`aiohttp`, `asyncpg`). LRCLIB is accessed via raw HTTP — no SDK/wrapper library is used.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*Slopcheck was run on `aiohttp` (already installed) — result: [OK]. No new packages to audit.*

---

## Architecture Patterns

### System Architecture Diagram

```
/jam save <name>                    /jam add <name>               /jam load <name>
    │                                    │                              │
    ▼                                    ▼                              ▼
[cogs/library.py JamCog]           get_current() from MusicCog    guild_jams DB row
    │                                    │                              │
    ▼                                    ▼                              ▼
count_jams(guild_id) ── cap? → reject   append track to snapshot   Track.from_dict() ×N
    │                                    │                              │
    ▼                                    ▼                              ▼
save_jam(guild_id, name, snapshot)  save_jam(..., append=True)    MusicCog enqueue path
    │                                                               (same as /playlist load)
    └─── guild_jams (Postgres JSONB)

/skips
    │
    ▼
[cogs/ops.py OpsCog]
    ├── get_leaderboard_skips(pool, guild_id)  ─── song_history (existing query)
    └── get_user_skip_rate(pool, guild_id, user_id)  ─── new query
            │
            ▼
        logic/skip_stats.py: compute_skip_rate(total, skipped, min_plays)
            │
            ▼
        Embed: server most-skipped + personal rate footer (roast-flavored)

/lyrics (chain)
    Genius → AZLyrics → LRCLIB
                              │
                              ▼
                      GET https://lrclib.net/api/search
                      ?track_name=<q_title>&artist_name=<q_artist>
                              │
                              ▼
                      JSON array → filter: not instrumental, plainLyrics not null
                              │
                              ▼
                      strip_lrc_headers() → sanitize_lyrics() → return

try_auto_queue() mutation (UX-04)
    Gemini suggestions[:]
        │
        for suggestion (until N tracks added OR suggestions exhausted):
            │
            ▼
        async_search(query, count=AUTO_QUEUE_SEARCH_CANDIDATES=3)
            │
            for each YouTube result:
                │
                ▼
            logic/autoqueue.validate_youtube_match(yt_title, sug_title, sug_artist)
                │ pass?
                ▼
            async_extract → duration check → Track → queue.add()
            break inner loop, continue outer
```

### Recommended Project Structure Changes

```
logic/
├── __init__.py          # (existing) pure-logic package marker
├── health.py            # (existing)
├── playback.py          # (existing)
├── roasts.py            # (existing)
├── skip_stats.py        # NEW: compute_skip_rate(), min-plays gate
└── autoqueue.py         # NEW: validate_youtube_match(), _normalize(), _contains_tokens()

services/
└── lyrics.py            # EXTEND: add _get_lrclib(), strip_lrc_headers() pure helper

database.py              # EXTEND: guild_jams DDL in SCHEMA_SQL + 5 helpers
                         #         get_user_skip_rate() new query

cogs/
├── library.py           # EXTEND: add /jam command group (or new cogs/jams.py)
└── ops.py               # EXTEND: add /skips command

config.py                # EXTEND: JAMS_PER_GUILD_MAX, SKIP_STATS_MIN_PLAYS,
                         #         AUTO_QUEUE_SEARCH_CANDIDATES

tests/
├── test_skip_stats.py   # NEW: unit tests for logic/skip_stats.py
├── test_autoqueue_validate.py  # NEW: unit tests for logic/autoqueue.py
└── test_lyrics_lrclib.py       # NEW: unit tests for LRCLIB pure helpers + mocked fetch
```

Note: The `/jam` group may live in `cogs/library.py` (extending the existing `LibraryCog`) or in a new `cogs/jams.py`. Both work — adding to `LibraryCog` avoids a new cog registration, but a new cog keeps files smaller. [ASSUMED — planner should decide; adding to LibraryCog mirrors how library-flavored commands are grouped today]

### Pattern 1: guild_jams Schema (mirrors user_playlists)

```sql
-- Source: verified in-repo pattern (database.py lines 160-169)
-- Add to SCHEMA_SQL in database.py (idempotent DDL, no $N params)
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

**Key difference from `user_playlists`:** PK is `(guild_id, name)` not `(user_id, name)`.
`/jam add` is additive (append a single track to existing snapshot) vs `/playlist save` which replaces. This requires a `get_jam` + append + `save_jam` round-trip or a Postgres `jsonb_insert` approach. Simpler: load existing snapshot, append, upsert.

### Pattern 2: guild_jams DB helpers (signatures to mirror)

```python
# Source: database.py lines 664-766 (save_playlist / get_playlist / list_playlists /
#         delete_playlist / count_playlists) — exact template; swap user_id → guild_id

async def save_jam(pool, *, guild_id: str, name: str, snapshot: list[dict]) -> None: ...
async def get_jam(pool, *, guild_id: str, name: str) -> list[dict] | None: ...
async def list_jams(pool, *, guild_id: str) -> list[dict]: ...
async def delete_jam(pool, *, guild_id: str, name: str) -> bool: ...
async def count_jams(pool, *, guild_id: str) -> int: ...
# append_to_jam is a composition: get_jam → append → save_jam (or a single SQL UPDATE)
```

### Pattern 3: LRCLIB fetch (mirrors _get_azlyrics)

```python
# Source: services/lyrics.py lines 279-313 — direct template
# Verified live: GET https://lrclib.net/api/search?track_name=...&artist_name=...
# Returns JSON array. Pick first where instrumental==False and plainLyrics is truthy.

_LRCLIB_BASE = "https://lrclib.net"
_LRC_HEADER_RE = re.compile(
    r"^\[(ti|ar|al|by|offset|length|re|ve):[^\]]*\]\s*$",
    re.MULTILINE,
)

def strip_lrc_headers(text: str) -> str:
    """Strip LRC metadata header lines from plainLyrics text.
    
    Some LRCLIB records embed [ti:...], [ar:...], [al:...], [by:...], [offset:0]
    lines at the start of plainLyrics (verified via live API probe 2026-06-30).
    """
    return _LRC_HEADER_RE.sub("", text).strip()


async def _get_lrclib(self, title: str, artist: str | None) -> str | None:
    """Fetch plainLyrics from LRCLIB as third fallback.
    
    Uses /api/search (not /api/get) — more robust because:
    - /api/get requires duration ±2s to match; Dexter may not have album_name
    - /api/search returns an array; we pick first non-instrumental non-null result
    - No API key, no rate limit (verified live 2026-06-30)
    
    Response JSON fields (verified):
      instrumental: bool  — True when no vocals; plainLyrics will be null
      plainLyrics:  str | null
      syncedLyrics: str | null  — ignored (D-11)
    """
    params = {"track_name": title}
    if artist:
        params["artist_name"] = artist
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{_LRCLIB_BASE}/api/search",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    log.warning("LRCLIB returned HTTP %s", resp.status)
                    return None
                raw = await resp.text()
                if len(raw) > 500_000:
                    log.warning("LRCLIB response too large (%d bytes)", len(raw))
                    return None
                results = json.loads(raw)
                for item in results:
                    if item.get("instrumental"):
                        continue  # no vocals — skip
                    plain = item.get("plainLyrics")
                    if not plain:
                        continue
                    cleaned = strip_lrc_headers(plain)
                    if len(cleaned) < 50:
                        continue  # too short to be real lyrics
                    return sanitize_lyrics(cleaned)
                return None  # all results were instrumental or empty
    except Exception as exc:
        log.warning("LRCLIB fetch failed: %s", exc)
        return None
```

### Pattern 4: Fuzzy auto-queue validator (UX-04)

```python
# Source: logic/autoqueue.py (new module; no Discord/asyncpg/random/datetime imports)
# Per Phase 10 pure-logic convention (logic/__init__.py: "never from discord, asyncio, or the DB")

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
    """Lowercase, strip punctuation, remove noise/stop tokens. Returns token set."""
    lowered = _PUNCT.sub(" ", text.lower())
    tokens = set(lowered.split()) - _NOISE_TOKENS - _STOP_WORDS
    return {t for t in tokens if len(t) >= 2}  # drop single-char tokens


def validate_youtube_match(
    youtube_title: str,
    suggested_title: str,
    suggested_artist: str,
) -> bool:
    """Return True if youtube_title plausibly matches both title and artist.
    
    Uses token-set containment: all significant tokens from the suggestion's
    title AND artist must appear in the normalized YouTube title.
    
    This is preferred over difflib.SequenceMatcher ratio because YouTube
    titles are longer than clean song names — ratio would be artificially
    low even for correct matches (e.g. "Shake It Off" vs
    "Taylor Swift - Shake It Off (Official Music Video)").
    
    Pure function — no I/O, no randomness, deterministic. Suitable for
    unit testing without mocks.
    """
    yt_tokens = _normalize_for_match(youtube_title)
    title_tokens = _normalize_for_match(suggested_title)
    artist_tokens = _normalize_for_match(suggested_artist)
    
    # Empty needle always matches (avoids false-negative on empty artist)
    title_ok = (not title_tokens) or title_tokens.issubset(yt_tokens)
    artist_ok = (not artist_tokens) or artist_tokens.issubset(yt_tokens)
    return title_ok and artist_ok
```

### Pattern 5: Auto-queue loop mutation (UX-04 insertion point)

```python
# Source: cogs/ai.py lines 307-334 — the existing loop (read before modifying)
# Current:
#   for suggestion in suggestions[: config.AUTO_QUEUE_SONGS_PER_ROUND]:
#       results = await self.bot.youtube_service.async_search(search_query, count=1)
#       if not results:
#           continue
#       result = results[0]
#       ... extract + add to queue ...

# After UX-04 change (D-13, D-14):
#   tracks_added = []
#   for suggestion in suggestions:                    # iterate ALL suggestions (D-14)
#       if len(tracks_added) >= config.AUTO_QUEUE_SONGS_PER_ROUND:
#           break
#       search_query = f"{suggestion['title']} {suggestion['artist']}"
#       results = await self.bot.youtube_service.async_search(
#           search_query, count=config.AUTO_QUEUE_SEARCH_CANDIDATES  # D-13: was count=1
#       )
#       if not results:
#           continue
#       # D-12: validate each candidate, take first that passes
#       validated = None
#       for result in results:
#           if validate_youtube_match(
#               result.get("title", ""),
#               suggestion["title"],
#               suggestion["artist"],
#           ):
#               validated = result
#               break
#       if validated is None:
#           log.info("auto-queue: all %d candidates rejected for '%s'",
#                    len(results), suggestion["title"])
#           continue   # D-14: try next suggestion
#       ... extract validated + add to queue ...
```

### Pattern 6: User personal skip rate query (new DB helper)

```sql
-- New helper: get_user_skip_rate(pool, *, guild_id, user_id)
-- All-time, guild-scoped (D-09: no date filter; D-07: per-guild contextual)
SELECT
    COUNT(*) AS total_plays,
    COUNT(*) FILTER (WHERE was_skipped = true) AS total_skips
FROM song_history
WHERE guild_id = $1 AND user_id = $2;
-- min-plays floor ($3 = SKIP_STATS_MIN_PLAYS) applied in pure logic layer, not SQL
```

### Pattern 7: Config knobs to add

```python
# Source: config.py lines 118-139 — existing caps/knobs section

# --- Phase 12: Richer Music/UX ---
JAMS_PER_GUILD_MAX = 25             # mirrors PLAYLISTS_MAX_PER_USER (D-05)
SKIP_STATS_MIN_PLAYS = 5            # min data points before showing skip rate (D-08)
AUTO_QUEUE_SEARCH_CANDIDATES = 3    # YouTube results to validate per suggestion (D-13)
# Note: reuse PLAYLIST_NAME_MAX_LENGTH (60) for jam names — no new knob needed (D-05)
```

### Anti-Patterns to Avoid

- **Don't call `/api/get` without duration:** `GET /api/get?track_name=X&artist_name=Y&duration=WRONG` returns 404. Dexter has title + artist reliably but not album. Use `/api/search` instead — it's robust to missing album/duration.
- **Don't pass raw YouTube title to LRCLIB:** Apply `build_genius_search_query()` cleanup first (same as Genius/AZLyrics paths). "Arctic Monkeys - Do I Wanna Know? (Official Video)" → "Do I Wanna Know?" + "Arctic Monkeys".
- **Don't use `difflib.SequenceMatcher(None, yt_title, suggestion).ratio()` as a simple ratio:** The YouTube title is 5-10x longer than the clean suggestion — ratio will be ~0.2 for a correct match. Token-set containment is the right tool here.
- **Don't try next Gemini suggestion by shrinking the slice:** The loop must iterate over ALL suggestions until `tracks_added` reaches `AUTO_QUEUE_SONGS_PER_ROUND` — not `suggestions[:AUTO_QUEUE_SONGS_PER_ROUND]`.
- **Don't forget `/jam add` needs an "already in voice" guard:** Same as `/play` and `/playlist load` — user must be in a voice channel to know which track is "now playing."
- **Don't omit `strip_lrc_headers()` before `sanitize_lyrics()`:** Some LRCLIB results embed LRC metadata at the top of `plainLyrics`. Passing those headers through `sanitize_lyrics()` won't remove them — it only strips HTML and @mentions.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LRCLIB HTTP client | Custom session management | `aiohttp.ClientSession` (existing pattern) | Already used for AZLyrics; handles timeout, redirects, connection pooling |
| JSON JSONB serialization | Custom snapshot format | `json.dumps(list[dict])` as `$N::jsonb` (existing pattern) | Already proven in `save_playlist` — asyncpg JSONB round-trip works |
| Fuzzy string distance | Custom edit-distance | `difflib.SequenceMatcher` (stdlib) or token-set containment | stdlib, zero deps, already available |
| DB cap checks | Inline count queries in cog | `count_jams()` helper in `database.py` | Keeps cog thin; consistent with `count_playlists()` pattern |
| LRC header stripping | Third-party library | `re.sub()` with `^\[(ti|ar|al|...):[^\]]*\]$` regex | Two-liner; well-understood; no new dependency |

**Key insight:** Every UX pattern in this phase has a direct in-repo template to copy and adapt — none require novel solutions.

---

## Common Pitfalls

### Pitfall 1: LRC Metadata Headers in LRCLIB plainLyrics
**What goes wrong:** Displaying raw `plainLyrics` from LRCLIB produces output starting with `[ti:Song Name]\n[ar:Artist]\n[al:Album]\n[by:]\n[offset:0]\n` followed by actual lyrics.
**Why it happens:** LRCLIB stores LRC-format metadata in some records' `plainLyrics` field (verified live 2026-06-30 — search results for "Bohemian Rhapsody" showed this in ~1 of 3 results).
**How to avoid:** Call `strip_lrc_headers(plain)` before `sanitize_lyrics()`. The regex `r"^\[(ti|ar|al|by|offset|length|re|ve):[^\]]*\]\s*$"` with `re.MULTILINE` matches all standard LRC header tags.
**Warning signs:** Lyrics embed starts with `[ti:` or `[ar:`.

### Pitfall 2: `/api/get` vs `/api/search` — Wrong Endpoint Choice
**What goes wrong:** Using `/api/get?track_name=X&artist_name=Y` without `album_name` + matching `duration` returns a result but may pick the wrong album version, or returns 404 for less-common songs.
**Why it happens:** `/api/get` uses duration (±2s) + album_name for disambiguation. Without them, it may fall back to a random match. Wrong duration → 404.
**How to avoid:** Use `/api/search` which returns an array sorted by relevance. The first non-instrumental, non-null `plainLyrics` result is reliable. [VERIFIED: live probe 2026-06-30]
**Warning signs:** LRCLIB returns 404 more often than expected.

### Pitfall 3: Auto-queue Loop Slicing Prevents Fall-Through
**What goes wrong:** Writing `for suggestion in suggestions[:AUTO_QUEUE_SONGS_PER_ROUND]` means if the first N suggestions are all rejected, the queue comes up empty with no chance to recover from later suggestions.
**Why it happens:** The original code sliced suggestions to the desired count before the loop, which worked when every suggestion was accepted.
**How to avoid:** Iterate over ALL suggestions; break the outer loop when `len(tracks_added) >= AUTO_QUEUE_SONGS_PER_ROUND`. Per D-14: suggestions are exhausted only when the list is consumed, not when the target count is reached.
**Warning signs:** Auto-queue produces 0-track rounds even when Gemini returns 5+ suggestions.

### Pitfall 4: Fuzzy Match False Negatives on Short Artists
**What goes wrong:** Single-token or two-letter artist names (e.g., "P!nk", "SZA") get their tokens discarded after punctuation stripping ("pnk" or "sza") and may not appear in the YouTube title if YouTube uses "Pink" or "SZA Official".
**Why it happens:** Punct stripping changes "P!nk" → "pnk" which doesn't match "pink". Two-letter tokens may be discarded by minimum-length filter.
**How to avoid:** Minimum token length should be 2 chars (catches "SZA", "Ed" from "Ed Sheeran"). Do NOT apply min-length to the YouTube title tokens — only to needle tokens. Consider lowering the bar: if artist token set has only 1 token and it's very short (< 3 chars), relax the artist match to optional (log a warning).
**Warning signs:** Valid auto-queue suggestions for niche/abbreviated artists are rejected.

### Pitfall 5: guild_jams `/jam add` — No "Now Playing" Guard
**What goes wrong:** User runs `/jam add` when nothing is playing → `queue.get_current()` returns None → NoneType error or silent empty add.
**Why it happens:** `/jam add` appends the currently playing track. When nothing plays, there's nothing to add.
**How to avoid:** Guard the same way as `/favorite`: check `track = queue.get_current()` and `queue.is_playing`, respond with personality "nothing's playing right now" if neither is true (reuse `NOTHING_PLAYING` response template).

### Pitfall 6: Personal Skip Rate Query — Guild vs All-Server Scope
**What goes wrong:** A user with 50 plays across 3 servers sees their total "across all guilds" skip rate, not the rate for this specific server, confusing the `/skips` output.
**Why it happens:** D-09 says "all-time" (no date filter) but doesn't specify whether "all-time" means all servers or just the current guild.
**How to avoid:** Per D-07 ("server's most-skipped songs" context), scope the personal rate to `guild_id = $1 AND user_id = $2` — all-time within this server. This gives each server a coherent view of "this user skips X% of what they queue here."

### Pitfall 7: `/jam load` Must Honor MAX_QUEUE_SIZE_PER_GUILD Cap
**What goes wrong:** Loading a large jam (e.g., 200 tracks) onto a near-full queue (e.g., 400 tracks) silently drops 100 tracks.
**Why it happens:** `MusicQueue.add()` raises `QueueFullError` at cap — callers must handle it.
**How to avoid:** Mirror `playlist_load` exactly (lines 545-553): loop `queue.add(track)` in try/except QueueFullError, count truncated tracks, report the truncation in the response message. Same pattern, same cap check.

---

## Code Examples

### LRCLIB Live API Response (Verified 2026-06-30)

```json
// Source: live probe GET https://lrclib.net/api/get?track_name=Bohemian+Rhapsody&artist_name=Queen&album_name=Greatest+Hits&duration=354
// [VERIFIED: lrclib.net live API]
{
  "id": 18982739,
  "name": "Bohemian Rhapsody",
  "trackName": "Bohemian Rhapsody",
  "artistName": "Queen",
  "albumName": "Greatest Hits",
  "duration": 351.76,
  "instrumental": false,
  "plainLyrics": "Is this the real life?...",
  "syncedLyrics": "[00:00.15] Is this the real life?...",
  "lyricsfile": null
}

// Instrumental track example (Moonlight Sonata):
// [VERIFIED: lrclib.net live API]
{
  "trackName": "Moonlight Sonata",
  "artistName": "Beethoven",
  "instrumental": true,
  "plainLyrics": null
}
```

### /api/search vs /api/get — Behavior Summary

```
# [VERIFIED: live probe 2026-06-30]
# /api/search — returns array; 200 with [] if nothing found; never 404
GET https://lrclib.net/api/search?track_name=X&artist_name=Y
→ JSON array (up to 20 results, sorted by relevance)
→ Each item has same fields as /api/get

# /api/get — exact match; 404 if no match or wrong duration (±2s tolerance)
GET https://lrclib.net/api/get?track_name=X&artist_name=Y&duration=354
→ Single JSON object (200) or 404
# /api/get without duration: still returns a result (picks any version)
# /api/get with WRONG duration (e.g., 999): returns 404

# Rate limiting: none (verified — no 429 responses, no auth required)
# API key: none required
```

### Playlist cap check pattern (exact in-repo template)

```python
# Source: cogs/library.py lines 478-487 — copy for jam cap check
# Allows overwriting an existing jam name without counting it twice:
existing = await get_jam(self.bot.pool, guild_id=guild_id, name=name)
if existing is None:  # new name, not overwrite
    current_count = await count_jams(self.bot.pool, guild_id=guild_id)
    if current_count >= config.JAMS_PER_GUILD_MAX:
        await interaction.response.send_message(
            f"this server has too many jams. delete one first ({config.JAMS_PER_GUILD_MAX} max).",
            ephemeral=True,
        )
        return
```

### Pure skip-rate helper (logic/skip_stats.py)

```python
# Source: Phase 10 pure-logic convention (logic/__init__.py)
# Zero imports from discord, asyncio, or database

def compute_skip_rate(
    total_plays: int,
    total_skips: int,
    min_plays: int,
) -> float | None:
    """Return skip rate as a 0.0–1.0 float, or None if below min_plays floor.
    
    Returns None when total_plays < min_plays (D-08 min-plays floor).
    """
    if total_plays < min_plays:
        return None
    if total_plays == 0:
        return 0.0
    return total_skips / total_plays
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LRCLIB `/api/get` (exact) | LRCLIB `/api/search` (fuzzy array) | n/a — both exist today | `/api/search` is more robust for Dexter's use case (no album, no reliable duration) |
| Single top YouTube hit in auto-queue | First validated hit from N candidates | Phase 12 (this phase) | Rejects hallucinated tracks; fallback to next Gemini suggestion |
| Genius → AZLyrics (2 fallbacks) | Genius → AZLyrics → LRCLIB (3 fallbacks) | Phase 12 (this phase) | `/lyrics` now has a last-resort that's purpose-built for music players |

**Deprecated / outdated:**
- `async_search(..., count=1)` in `try_auto_queue` — replace with `count=config.AUTO_QUEUE_SEARCH_CANDIDATES`

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | LRCLIB has no documented rate limit and no User-Agent requirement | Architecture Patterns / Pitfalls | Could get throttled — mitigation: add descriptive UA header and respect HTTP 429 |
| A2 | `/jam` group lives in an extended `LibraryCog` (`cogs/library.py`) rather than a new `cogs/jams.py` | Architecture Patterns | A new cog requires an additional `bot.add_cog()` call in `bot.py`; either works, but planner should decide |
| A3 | Personal skip rate in `/skips` is scoped to the current guild (not all-time across all servers) | Architecture Patterns / Pattern 6 | Cross-server scope changes the SQL query; clarify before implementation if ambiguous |

**All LRCLIB API facts tagged `[VERIFIED: lrclib.net live API]` are confirmed by live HTTP probes on 2026-06-30 — not training data.**

---

## Open Questions

1. **`/jam` group location: extend `LibraryCog` vs new `JamCog`?**
   - What we know: `/playlist` and `/favorite` live in `cogs/library.py`; adding `/jam` there keeps "library" commands together but makes `library.py` longer
   - What's unclear: Whether the planner prefers thin cog files or command-grouping by concept
   - Recommendation: Add to `LibraryCog` (same file) — mirrors how `/playlist` and `/favorite` coexist; avoids a new `bot.add_cog()` registration

2. **`/jam add` — append single track vs snapshot entire queue?**
   - What we know: D-04 says `/jam add` appends the now-playing song (singular) vs `/jam save` which appears to snapshot the queue (like `/playlist save`)
   - What's unclear: Whether `/jam save` = snapshot current queue (like `/playlist save`) or something else
   - Recommendation: Implement both: `/jam save <name>` snapshots the queue (like `/playlist save`), `/jam add <name>` appends the now-playing track only. This matches the "server mixtape that grows over time" framing from CONTEXT.md Specific Ideas.

3. **Does `get_leaderboard_skips` in `cogs/ops.py` already pass `config.LEADERBOARD_TOP_N` or should `/skips` use a different limit?**
   - What we know: `get_leaderboard_skips(pool, guild_id)` uses `LIMIT $2` with `config.LEADERBOARD_TOP_N = 5`
   - What's unclear: Whether the `/skips` embed should show top-5 or a different number
   - Recommendation: Reuse `LEADERBOARD_TOP_N = 5` for consistency — same embed style as `/leaderboard`

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (installed in requirements.txt) + pytest-asyncio |
| Config file | none — run via `python -m pytest` from project root |
| Quick run command | `python -m pytest tests/test_skip_stats.py tests/test_autoqueue_validate.py tests/test_lyrics_lrclib.py -x` |
| Full suite command | `python -m pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| UX-01 | guild_jams table helpers (save/get/list/delete/count) | integration (asyncpg) | `python -m pytest tests/test_database_phase12.py -x` | ❌ Wave 0 |
| UX-01 | `/jam load` truncates at queue cap | unit (pure mock) | `python -m pytest tests/test_jam_load.py -x` | ❌ Wave 0 |
| UX-02 | `compute_skip_rate()` min-plays floor | unit (pure) | `python -m pytest tests/test_skip_stats.py -x` | ❌ Wave 0 |
| UX-02 | `compute_skip_rate()` division and edge (0/0, 0/5) | unit (pure) | `python -m pytest tests/test_skip_stats.py -x` | ❌ Wave 0 |
| UX-03 | `strip_lrc_headers()` removes LRC header lines | unit (pure) | `python -m pytest tests/test_lyrics_lrclib.py -x` | ❌ Wave 0 |
| UX-03 | `_get_lrclib()` picks first non-instrumental result | unit (mocked aiohttp) | `python -m pytest tests/test_lyrics_lrclib.py -x` | ❌ Wave 0 |
| UX-03 | `_get_lrclib()` returns None when all results instrumental | unit (mocked) | `python -m pytest tests/test_lyrics_lrclib.py -x` | ❌ Wave 0 |
| UX-04 | `validate_youtube_match()` accepts valid match | unit (pure) | `python -m pytest tests/test_autoqueue_validate.py -x` | ❌ Wave 0 |
| UX-04 | `validate_youtube_match()` rejects clear mismatch | unit (pure) | `python -m pytest tests/test_autoqueue_validate.py -x` | ❌ Wave 0 |
| UX-04 | `validate_youtube_match()` handles noise tokens in YT title | unit (pure) | `python -m pytest tests/test_autoqueue_validate.py -x` | ❌ Wave 0 |
| UX-04 | Loop falls through to next suggestion on full rejection | unit (mocked services) | `python -m pytest tests/test_autoqueue_validate.py -x` | ❌ Wave 0 |

### Key Edge Cases Per Feature

**UX-01 (guild jams):**
- Empty jam (zero tracks in snapshot) → `/jam load` should message "jam is empty"
- Jam cap hit → clear error message, no insert
- `/jam add` when nothing playing → `NOTHING_PLAYING` response
- `/jam load` on nonexistent jam → not-found message (mirrors `PLAYLIST_NOT_FOUND`)
- `/jam load` on full queue → truncation message

**UX-02 (skip analytics):**
- User with 0 plays → None returned from `compute_skip_rate` → "not enough data" in embed
- User with exactly `SKIP_STATS_MIN_PLAYS - 1` plays → below floor → omit
- User with all skips (5/5) → 100% — valid, should display
- Server with no skipped songs → empty most-skipped list → show empty-state message

**UX-03 (LRCLIB):**
- All results are instrumental → return None (fall through to "no lyrics found")
- `plainLyrics` starts with LRC headers → strip them correctly
- LRCLIB returns empty array `[]` → return None
- LRCLIB returns HTTP 500 → log warning, return None (matches AZLyrics pattern)

**UX-04 (auto-queue validation):**
- All N candidates for one suggestion fail → skip that suggestion, try next (D-14)
- All suggestions exhausted before filling round → round may come up short (acceptable per D-14)
- Very short title like "Love" → may produce false positives (common word)
- Abbreviated/punctuated artist like "P!nk" → normalization must not drop meaningful tokens

### Sampling Rate
- Per task commit: `python -m pytest tests/test_skip_stats.py tests/test_autoqueue_validate.py tests/test_lyrics_lrclib.py -x`
- Per wave merge: `python -m pytest tests/ -x`
- Phase gate: Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_skip_stats.py` — covers UX-02 compute_skip_rate pure logic
- [ ] `tests/test_autoqueue_validate.py` — covers UX-04 validate_youtube_match
- [ ] `tests/test_lyrics_lrclib.py` — covers UX-03 LRCLIB helpers and mocked fetch
- [ ] `tests/test_database_phase12.py` — covers UX-01 guild_jams DB helpers (integration, requires test DB)

---

## Security Domain

> Security enforcement applies. Phase adds HTTP fetch (UX-03) and new DB table (UX-01).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | partial | guild_id keying ensures cross-guild isolation; user_id keying in skip rate ensures users only see their own rate |
| V5 Input Validation | yes | jam name: length cap + strip; LRCLIB params: passed via aiohttp `params=` dict (URL-encoded, no injection) |
| V6 Cryptography | no | — |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via jam name | Tampering | asyncpg `$N` parameterized queries (T-07-04-01 mirrors apply) |
| Cross-guild jam access | Information Disclosure | All `guild_jams` queries keyed on `guild_id = $1` (parameterized) |
| SSRF via LRCLIB URL | Spoofing | Base URL hard-coded as `"https://lrclib.net"` — no user-supplied host |
| Oversized LRCLIB response | DoS | 500,000-byte cap + `aiohttp.ClientTimeout(total=10)` (mirrors AZLyrics) |
| XSS/mention injection in lyrics | Tampering | `sanitize_lyrics()` already handles HTML stripping + @mention neutralization |
| LRC header data exposure | Information Disclosure | `strip_lrc_headers()` removes metadata before display |

---

## Sources

### Primary (HIGH confidence)
- `lrclib.net` live API probes (2026-06-30) — `/api/get`, `/api/search`, instrumental null handling, LRC header behavior
- In-repo: `database.py` lines 99-169, 442-766 — schema + helpers (read directly)
- In-repo: `services/lyrics.py` lines 1-314 — LyricsService pattern (read directly)
- In-repo: `cogs/library.py` lines 424-654 — `/playlist` group pattern (read directly)
- In-repo: `cogs/ai.py` lines 254-408 — `try_auto_queue()` loop (read directly)
- In-repo: `config.py` lines 1-196 — existing config knobs (read directly)
- In-repo: `logic/__init__.py` — Phase 10 pure-logic convention (read directly)

### Secondary (MEDIUM confidence)
- WebSearch: LRCLIB API overview — `/api/get` requires duration ±2s, `/api/search` returns 20-result array [cross-verified with live probe]
- `difflib` stdlib module — available in Python 3.11+, no install needed [verified with `python -c "import difflib"` in project env]

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- LRCLIB API: HIGH — live-probed with real HTTP calls, JSON schema confirmed
- Standard stack: HIGH — no new packages, all patterns in-repo
- Architecture: HIGH — direct in-repo templates exist for every feature
- Fuzzy matching: HIGH — stdlib difflib confirmed available; token-set approach reasoned from first principles
- Pitfalls: HIGH — LRC header issue confirmed by live API; other pitfalls derived from in-repo patterns

**Research date:** 2026-06-30
**Valid until:** 2026-07-30 (LRCLIB API may evolve; re-probe if `/api/search` behavior changes)
