# Phase 14: Smarter Music Brain - Research

**Researched:** 2026-07-02
**Domain:** SQL aggregation + Gemini-in-the-loop prompt engineering over an existing Postgres/pgvector Discord music bot (no new infra)
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

> Session note: the user stepped away before selecting discussion topics. D-01 through D-08 below
> were decided by Claude on the user's behalf using best judgment, grounded in the locked
> BRAIN-01/02/03 requirement text, Success Criterion 4 (multi-user-safety), and the Phase 11/13
> accuracy-firewall precedent. They are conservative, tunable defaults — revise before planning if
> any feel wrong. All numeric values remain Claude's-discretion / spike territory.

### Locked Decisions

**Negative-hint shape for auto-queue (BRAIN-01)**
- **D-01:** The negative signal is a guild-scoped, aggregate "recently skipped" block injected into
  the recommendation prompt — a number-free list of recently-skipped titles + artists sourced from
  `song_history WHERE was_skipped = true AND guild_id = $1` over a recent window (directional ~7
  days / ~15 rows). The prompt gains an "avoid these — the server keeps skipping them" section
  alongside the existing recent-plays block. Guild-collective, not per-listener. *(Rejected:
  per-active-listener skip lists — leak risk + complexity for a shared queue.)*
- **D-02:** Keep the negative hint primarily a soft prompt instruction (preserves Gemini-in-the-loop),
  but add a lightweight hard post-filter: after search, reject a candidate whose normalized artist
  token-set matches a recently-skipped artist. The existing post-search `validate_youtube_match`
  (hallucination guard) stays unchanged and runs independently.

**Positive taste signal in auto-queue (BRAIN-01)**
- **D-03:** Auto-queue recalls the `taste_episode` memory of each non-bot member currently in the
  voice channel — reusing the exact in-voice member set already computed for the
  `auto_queue_ignored` write (`cogs/ai.py` ~line 404) — and blends them as a collective "the room
  tends to like…" positive context in the prompt. Multi-user-safe because it is scoped to
  consenting-present members' shared session, never surfacing one member's data into an unrelated
  context. Total injected taste facts are capped (directional ~3-4). If no member has a taste
  episode above the recall floor, the block is omitted and behavior is byte-identical to today.
  *(See Open Question 1 — recall() currently returns mixed kinds.)*

**Discovery command (BRAIN-02)**
- **D-04:** A new `/discover` slash command that is invoker-anchored, server-adjacency-grounded: it
  reads the invoker's top artist(s) from `user_artist_counts`, then computes server-wide
  co-occurrence adjacency from `song_history` (artists that co-occur with the anchor within the same
  guild's listening) to surface 1-3 adjacent artists/genres. The recommendation itself is 100%
  SQL-derived (zero hallucination); Gemini only supplies Dex's voice/commentary wrapping the SQL
  result, never the picks. *(Rejected: Gemini-generated recommendations — would violate the
  zero-hallucination requirement.)*
- **D-05:** `/discover` is actionable but confirm-first — it presents the adjacent artist(s) with
  Dex commentary and offers to queue one (button/follow-up), rather than silently auto-queuing. Cog
  placement (`cogs/music.py` since it can queue, vs `cogs/ops.py`) is planner discretion; lean
  `music.py`. New empty/low-history state returns an in-character "not enough listening yet"
  message rather than erroring.

**Jam assist surface (BRAIN-03)**
- **D-06:** A new `/jam suggest <name>` subcommand (sibling of the existing
  `save`/`add`/`load`/`list`/`delete` in `cogs/library.py`) — not a flag overloading `/jam add`. It
  seeds Gemini with the named jam's existing tracks as taste context, requests N additions, and
  validates every suggestion through `logic/autoqueue.py::validate_youtube_match` against real
  YouTube search results before it is ever offered (BRAIN-03 hard requirement).
- **D-07:** `/jam suggest` is propose-and-confirm: Dex shows the validated candidate additions and
  the user confirms before anything is written. On confirm, validated tracks are appended to the
  jam snapshot (consistent with `/jam add` semantics), with an option to also queue them now. It
  never silently mutates a shared server artifact. Suggestions that fail validation are dropped and,
  if none survive, Dex says so in character rather than committing garbage.

**Multi-user-safety (Criterion 4 — cross-cutting)**
- **D-08:** Every new aggregate query is guild-scoped or invoker-anchored-with-aggregate-adjacency,
  following the exact param-binding + scoping discipline of Phase 13's `get_user_artist_activity` /
  `get_user_skip_rate` (bound `$N` positional params, never string interpolation; `WHERE guild_id`
  and/or `WHERE user_id` scoping; index-friendly `queued_at >` bounds against
  `idx_history_guild`/`idx_history_user`). No query returns one user's individual listening rows
  into another user's result. This is a verification target, not just a convention.

### Claude's Discretion

- All numeric values are directional priors, tuned during planning/spike + live observation: skip-window
  lookback (~7 days / ~15 rows), injected-taste-fact cap (~3-4), number of `/discover` adjacents
  (1-3), number of `/jam suggest` candidates, and the co-occurrence "same session/window" definition.
- Exact SQL shape of the new `get_recently_skipped` (guild, window) helper and the co-occurrence
  adjacency helper over `song_history` / `user_artist_counts`, plus the prompt-template edits to
  `build_recommendation_prompt` and the new jam/discovery prompt builders, are planning detail.
- Cog placement of `/discover` (`music.py` vs `ops.py`) — planner's call.

### Deferred Ideas (OUT OF SCOPE)

- Per-active-listener (non-aggregate) auto-queue personalization — rejected for Phase 14 in favor
  of the guild-collective blend (D-01/D-03) to preserve multi-user-safety. Revisit only if
  collective auto-queue feels too bland after live observation.
- Embeddings-based track/artist similarity for discovery — out of scope; `/discover` uses SQL
  co-occurrence only (zero new infra, zero hallucination). A learned recommender is a
  future-milestone idea, not v1.3.
- `/roast @user` / `/ask` / `/memory` memory grounding → Phase 15 (explicitly next phase).
- Proactive unprompted taste callbacks → Phase 16.
- Any new memory `kind` or write path (Phase 14 is read-only against the taste substrate).
- A trained/learned recommender, embeddings-based track similarity, or any new dep/table/limiter.
- Embedding any SQL-known number into memory (permanent anti-feature — accuracy firewall).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BRAIN-01 | Auto-queue is taste-aware — incorporates recent taste and `was_skipped` history as negative hints so it stops re-queueing skipped tracks (Gemini-in-the-loop + SQL, not ML) | Pattern 1 (optional-signal prompt extension), Pattern 2 (OQ1 kind-filtered recall resolution), Code Examples `get_recently_skipped`/`is_recently_skipped_artist`/`select_positive_taste_context`, Pitfall 1/3/4 |
| BRAIN-02 | A discovery command surfaces artist/genre adjacency from listening history via grounded co-occurrence SQL over `song_history`/`user_artist_counts` (multi-user-safe aggregate; zero hallucination, zero cost) | Pattern 3 (OQ2 co-occurrence definition resolution), Code Examples `get_artist_cooccurrence`, Pitfall 2 (flagged `user_artist_counts` guild-scope discrepancy), Pitfall 5 |
| BRAIN-03 | Generative jam assist — Dexter suggests jam additions using taste context + Gemini, with hallucination validation reusing `logic/autoqueue.py` token-set containment | Pattern 4 (verbatim `validate_youtube_match` reuse), Don't Hand-Roll table, System Architecture Diagram §BRAIN-03, Validation Architecture test map |
</phase_requirements>

## Summary

Phase 14 wires three existing surfaces (auto-queue, a new `/discover` command, a new `/jam suggest`
subcommand) to read taste signal and change a decision. Nothing here requires new infrastructure —
every piece is either (a) a new guild/user-scoped aggregate SQL helper in `database.py`, following
the exact param-binding/scoping template already proven by `get_user_skip_rate` /
`get_user_artist_activity` / `get_leaderboard_skips`, or (b) a prompt-template extension in
`personality/prompts.py` that stays byte-identical when the new optional signal is empty (mirroring
`build_chat_prompt`'s `memory_context` pattern), or (c) reuse of `logic/autoqueue.py::validate_youtube_match`
verbatim for hallucination gating.

Both flagged correctness questions have concrete, evidence-backed answers (see Code Examples):
**OQ1** (kind-scoped recall) resolves cleanly to an optional `kind` parameter threaded through
`database.search_memories()` → `MemoryService.recall()`, defaulting to `None` so all 15+ existing
call sites stay byte-identical — no `MemoryFact` dataclass change needed because filtering happens
in SQL against an already-bounded per-user row set (≤150 rows, the `MEMORY_MAX_PER_USER` cap), not
via post-fetch Python filtering. **OQ2** (co-occurrence definition) resolves to a same-guild-day
bucket join over `song_history`, bounded by a recency window for index-friendliness against
`idx_history_guild(guild_id, queued_at DESC)` — a guild-wide aggregate with no per-user attribution,
mirroring `get_leaderboard_skips`'s "no user attribution — entity is the artist" discipline. One
genuine discrepancy surfaces during this research and is flagged for the planner: CONTEXT.md's D-04
names `user_artist_counts` as the invoker-anchor source, but that table has **no `guild_id` column**
(it's a user-global lifetime count) — the planner must explicitly choose global-anchor (reuse
`user_artist_counts` as written) vs. guild-scoped-anchor (derive top artist from
`song_history WHERE guild_id AND user_id`, matching the guild-flavored feel `/discover` is going for).

**Primary recommendation:** Add three new `database.py` helpers (`get_recently_skipped`,
`get_user_top_artists` or a guild-scoped equivalent, `get_artist_cooccurrence`) following the D-08
scoping template; add an optional `kind` filter to `search_memories`/`recall`; extend
`build_recommendation_prompt` with two optional signal blocks; add two new pure `logic/` functions
for the skip-hint hard-filter and taste-fact blend/cap; reuse `validate_youtube_match` verbatim for
`/jam suggest`. Zero new tables, deps, limiters, or schema changes.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Negative skip-hint aggregation (BRAIN-01) | Database / Storage | API/Backend (`cogs/ai.py`) | New guild-scoped SQL read; assembled into prompt text at the cog/service boundary |
| Positive taste-hint recall (BRAIN-01) | API/Backend (`services/memory.py`) | Database / Storage | ANN recall is a service-layer operation over Postgres/pgvector; ranking/capping stays in `logic/` |
| Recommendation prompt assembly (BRAIN-01) | API/Backend (`personality/prompts.py`) | — | Pure string templating, no I/O |
| Hard post-filter reject (BRAIN-01, D-02) | API/Backend (`logic/autoqueue.py`) | — | Pure token-set logic, mirrors existing `validate_youtube_match` |
| Artist co-occurrence adjacency (BRAIN-02) | Database / Storage | API/Backend (`cogs/music.py` or `cogs/ops.py`) | 100% SQL-derived per D-04 (zero hallucination); cog only wraps result in Dex's voice via Gemini |
| `/discover` confirm-and-queue interaction | API/Backend (Discord cog) | — | Discord button/view state, no persistence beyond the queue |
| Jam-suggestion generation (BRAIN-03) | API/Backend (`personality/prompts.py` + Gemini) | Database / Storage (existing tracks as context) | Gemini proposes, SQL/validation gates — same split as auto-queue |
| Jam-suggestion validation (BRAIN-03) | API/Backend (`logic/autoqueue.py`, reused) | — | Pure, already exists — zero new logic |
| Jam snapshot mutation (BRAIN-03, on confirm) | Database / Storage (`guild_jams` JSONB) | API/Backend (`cogs/library.py`) | Existing `save_jam`/`get_jam` helpers, unchanged |

## Standard Stack

No new dependencies. Every capability in this phase is built from the already-shipped stack.

### Core (existing, reused)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `asyncpg` | 0.31.0 (shipped) | New guild/user-scoped aggregate queries | Already the project's sole DB driver; Phase 13 established the exact scoping template this phase mirrors |
| `google-genai` | 2.8.0 (shipped) | Recommendation/discovery-commentary/jam-suggestion prompts | Already the project's sole LLM client; `priority=2` background-safe chat calls already proven in `try_auto_queue` |
| `pgvector` (Postgres extension, shipped) | — | `taste_episode` recall for the positive-hint blend (BRAIN-01) | Already enabled in Phase 11; Phase 14 adds a `kind` filter to an existing query, no extension change |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SQL co-occurrence (day-bucket join) | Embedding-based artist similarity | Explicitly out of scope (REQUIREMENTS.md Out of Scope, CONTEXT.md deferred); would add a new infra dependency and hallucination surface for a single-community bot where SQL co-occurrence is already sufficient (research FEATURES.md/STACK.md convergence) |
| Gemini-in-the-loop + SQL | Trained ML recommender | Explicitly out of scope; over-engineering per REQUIREMENTS.md Out of Scope table and all four v1.3 research agents |
| Optional `kind` param on existing `search_memories`/`recall` | New `recall_taste()` method | Rejected — duplicates the entire 7-step pipeline for one WHERE clause; violates the "MemoryService is the only place that wires this together" docstring contract already established in Phase 11 |

**Installation:** None required — zero new packages for this phase.

## Package Legitimacy Audit

**Not applicable.** This phase installs zero new external packages (confirmed above — all
capabilities build on `asyncpg`, `google-genai`, and Postgres/`pgvector`, all already present in
`requirements.txt` and verified in prior phases). No `pip install` step, no slopcheck run needed.

## Architecture Patterns

### System Architecture Diagram

```
BRAIN-01 (taste-aware auto-queue)
──────────────────────────────────
queue empties (cogs/music.py)
    │
    ▼
cogs/ai.py::try_auto_queue(guild)
    │
    ├─► database.get_recent_songs(guild_id)              ─┐  (existing, unchanged)
    ├─► database.get_recently_skipped(guild_id, window)   ─┼─► negative hint (titles+artists, no counts)
    ├─► [in-voice non-bot members] ──► memory_service.recall(user_id, guild_id, anchor, kind="taste_episode")
    │        (per member, reuses D-03's existing member-enumeration site at ~line 404)   ─┘  positive hint (facts, capped ~3-4)
    │
    ▼
personality/prompts.py::build_recommendation_prompt(recent, recently_skipped, positive_taste)
    │
    ▼
gemini.chat(prompt, priority=2) ──► parse_suggestions() ──► per-suggestion loop:
    │                                                            │
    │                                              ┌─────────────┴─────────────┐
    │                                     logic/autoqueue.py:                  │
    │                                     is_recently_skipped_artist()   validate_youtube_match()
    │                                     (D-02 hard post-filter, NEW)   (existing, unchanged)
    │                                              │                            │
    │                                              ▼ reject if match            ▼ reject if no match
    └───────────────────────────────────────► queue.add(track) ◄────────────────┘


BRAIN-02 (/discover)
──────────────────────────────────
/discover slash command (cogs/music.py, D-05 placement)
    │
    ▼
database.get_user_top_artist(user_id[, guild_id])   ── invoker-anchored (D-04; scope choice flagged — see Open Questions)
    │
    ▼
database.get_artist_cooccurrence(guild_id, anchor_artist, since, limit)   ── 100% SQL, guild-wide aggregate
    │
    ▼
[empty result?] ──yes──► in-character "not enough listening yet" message (D-05)
    │no
    ▼
gemini.chat(discover_commentary_prompt(anchor, adjacent_artists))  ── Dex's VOICE ONLY, never the picks (D-04 firewall)
    │
    ▼
embed/message: "you're into X; the server also spins Y" + confirm-to-queue button (D-05, propose-and-confirm)
    │
    ▼ (on confirm)
youtube_service.async_search + async_extract ──► queue.add(track)


BRAIN-03 (/jam suggest <name>)
──────────────────────────────────
/jam suggest <name> (cogs/library.py, sibling of jam_save/jam_add/jam_load/jam_list/jam_delete, D-06)
    │
    ▼
database.get_jam(guild_id, name) ──► existing snapshot (title/artist pairs) as taste context
    │
    ▼
personality/prompts.py::build_jam_suggestion_prompt(existing_tracks, count)   (NEW, mirrors MUSIC_RECOMMENDATION_PROMPT shape)
    │
    ▼
gemini.chat(prompt, priority=2) ──► parse_suggestions()  (reused verbatim — same {title, artist} JSON shape)
    │
    ▼ per suggestion:
youtube_service.async_search ──► logic/autoqueue.py::validate_youtube_match()  (reused verbatim, D-06 hard requirement)
    │
    ▼ [none survive?] ──► in-character "nothing landed" message (D-07)
    ▼ [survivors]
Discord confirm view: show validated candidates ──► user confirms (D-07, propose-and-confirm)
    │
    ▼ (on confirm)
database.save_jam(guild_id, name, snapshot + validated tracks)   ── existing helper, unchanged
    + optional: queue.add() the confirmed tracks now (D-07 "option to also queue")
```

### Recommended Project Structure

No new top-level modules. Extensions to existing files only:

```
database.py            # + get_recently_skipped, get_user_top_artist(s), get_artist_cooccurrence
services/memory.py      # + optional kind param threaded through recall()
logic/autoqueue.py       # + is_recently_skipped_artist (D-02 hard filter) — sibling of validate_youtube_match
logic/taste.py           # + select_positive_taste_context (blend/cap, D-03) — sibling of summarize_taste
personality/prompts.py   # + build_recommendation_prompt(recently_skipped=, positive_taste=) extended
                         # + build_discover_commentary_prompt (NEW)
                         # + build_jam_suggestion_prompt (NEW)
cogs/ai.py               # try_auto_queue extended: fetch negative + positive hints, hard-filter loop
cogs/music.py            # + /discover command (D-05 lean placement)
cogs/library.py          # + /jam suggest subcommand (D-06)
config.py                # + AUTO_QUEUE_SKIP_LOOKBACK_DAYS, AUTO_QUEUE_SKIP_HINT_CAP,
                         #   AUTO_QUEUE_POSITIVE_TASTE_CAP, DISCOVER_ADJACENT_COUNT,
                         #   DISCOVER_COOCCURRENCE_WINDOW_DAYS, JAM_SUGGEST_CANDIDATE_COUNT
                         #   (all directional/Claude's-discretion per CONTEXT.md)
```

### Pattern 1: Optional-signal prompt extension (byte-identical when empty)

**What:** Extend a prompt builder with new optional parameters that produce an empty string
(no injected block) when the signal is absent, so every existing call site and every existing
test stays byte-identical.
**When to use:** Any new BRAIN-01 prompt injection (negative skip hint, positive taste hint).
**Example:**
```python
# Source: mirrors personality/prompts.py::build_chat_prompt's memory_context pattern (Phase 11)
def build_recommendation_prompt(
    recent_songs: list[dict],
    *,
    recently_skipped: list[dict] | None = None,
    positive_taste: list[str] | None = None,
) -> str:
    lines = [f"- {s['title']} by {s.get('artist') or 'Unknown'}" for s in recent_songs]

    skip_block = ""
    if recently_skipped:
        skip_lines = "\n".join(
            f"- {s['title']} by {s.get('artist') or 'Unknown'}" for s in recently_skipped
        )
        skip_block = (
            "\n\nAVOID these — the server keeps skipping them:\n" + skip_lines
        )

    taste_block = ""
    if positive_taste:
        taste_lines = "\n".join(f"- {t}" for t in positive_taste)
        taste_block = (
            "\n\nTHE ROOM TENDS TO LIKE:\n" + taste_lines
        )

    return MUSIC_RECOMMENDATION_PROMPT.format(
        recent_songs="\n".join(lines),
    ) + skip_block + taste_block
```
Note: when both new kwargs are omitted/empty, output is byte-identical to the current
`MUSIC_RECOMMENDATION_PROMPT.format(recent_songs=...)` call — no existing test in
`tests/test_autoqueue_parse.py`-adjacent prompt tests should need updating.

### Pattern 2: Optional `kind` filter threaded through recall (OQ1 resolution)

**What:** Add `kind: str | None = None` to `database.search_memories()` and
`MemoryService.recall()`, appending `AND kind = $N` to the SQL only when provided.
**When to use:** BRAIN-01's positive-taste blend (`kind="taste_episode"`); every other existing
call site (`/ask`, `/roast`, ambient roast) omits the param and is unaffected.
**Example:**
```python
# Source: extends database.py:899-939 (search_memories) — see full rationale in Open Questions §OQ1
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
`MemoryService.recall(..., kind: str | None = None)` threads the same optional param through to
`database.search_memories(..., kind=kind)`. No `MemoryFact` dataclass change is needed — the
`kind` column is already selected in the row (`database.py` line 934, used today by
`remember()`'s dedup branch to read `nearest_kind`) but is dropped at the `MemoryFact` mapping
step in `recall()` (models/memory.py `MemoryFact` has no `kind` field) — that is fine, because
filtering happens in the SQL WHERE clause before the Python mapping, not after.

### Pattern 3: Guild-wide day-bucket co-occurrence (OQ2 resolution)

**What:** Artists that appear in `song_history` on the same calendar day, in the same guild, as
the anchor artist — a simple, index-friendly, non-hallucinated adjacency signal.
**When to use:** `/discover`'s BRAIN-02 SQL-only recommendation core.
**Example:** see Code Examples § `get_artist_cooccurrence`.

### Pattern 4: Reuse `validate_youtube_match` verbatim for a second surface

**What:** `logic/autoqueue.py::validate_youtube_match` is already pure and Discord/DB-free — call
it identically from the new `/jam suggest` validation loop, no wrapper, no reimplementation.
**When to use:** BRAIN-03's hard requirement ("every suggestion passes ... before being offered").
**Example:**
```python
# Source: logic/autoqueue.py (existing, unchanged) — cogs/library.py:jam_suggest calls this
# in the exact same shape as cogs/ai.py:try_auto_queue's per-suggestion loop (lines 326-333)
for result in search_results:
    if validate_youtube_match(result.get("title", ""), suggestion["title"], suggestion["artist"]):
        validated_candidates.append(result)
        break
```

### Anti-Patterns to Avoid

- **Reimplementing token normalization for the D-02 skip-artist filter:** reuse
  `logic/autoqueue.py`'s existing `_normalize_for_match` (module-private but same-module reuse is
  fine) inside a new `is_recently_skipped_artist()` function — do NOT write a second
  tokenizer/normalizer, and do NOT swap to `difflib` (explicit anti-pattern per CLAUDE.md D-12).
- **Per-active-listener (N-way) `recall()` fan-out with no cap:** D-03 already caps total
  injected taste facts (~3-4) — do not call `recall()` once per in-voice member and inject all
  results unbounded; blend-and-cap in `logic/taste.py` before it reaches the prompt (protects both
  prompt length and the shared 60 RPM embed limiter, per Pitfall 7's "cap how heavily any single
  signal source can dominate a round" discipline).
- **Post-fetch Python filtering by kind instead of a SQL WHERE clause:** would require
  over-fetching (`k` larger than needed) and adding a `kind` field to the frozen `MemoryFact`
  dataclass for no benefit — SQL-side filtering is strictly cheaper and simpler (see Pattern 2).
- **Auto-queue filter-bubble convergence (research Pitfall 7):** a purely skip-avoidance-driven
  auto-queue drifts toward bland, "safest" picks over weeks in a shared-server context. D-01/D-02
  already scope the negative signal to guild-collective (not per-listener), which is the safety
  requirement — but the planner should also consider (not mandated by CONTEXT.md, worth flagging)
  whether some exploration budget survives the hard post-filter so BRAIN-01 doesn't silently
  narrow the genre pool over time. Not a blocking requirement for Phase 14, but a live-observation
  watch-item.
- **Embedding-based similarity, a genre taxonomy, or a second memory kind for co-occurrence:**
  all explicitly out of scope (REQUIREMENTS.md, CONTEXT.md deferred list) — do not reach for these
  even if `/discover`'s adjacency feels thin at first; tune the SQL window/thresholds instead.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| YouTube-result hallucination validation | A second token-matching function for `/jam suggest` | `logic/autoqueue.py::validate_youtube_match` (verbatim) | Already correct, already tested (`tests/test_autoqueue_validate.py`); BRAIN-03 explicitly mandates reusing this exact function |
| Skip-artist token normalization | A second normalizer for the D-02 hard filter | `logic/autoqueue.py::_normalize_for_match` (same-module reuse) | Avoids two divergent definitions of "matching artist" in the same file |
| JSON suggestion parsing for `/jam suggest` | A new parser for `{title, artist}` arrays | `cogs/ai.py::parse_suggestions` (reuse — move to a shared module if cog-to-cog import is awkward) | Already tolerant of fences/prose-wrapping/dict-wrapping; BRAIN-03's Gemini output should use the identical `{title, artist}` JSON contract so this parser works unchanged |
| Recommendation ranking / graph clustering for `/discover` | An in-Python adjacency graph or clustering pass | Plain SQL `GROUP BY artist ORDER BY COUNT(*) DESC` | Research (STACK.md/FEATURES.md) converged: no graph library needed at single-community scale; SQL aggregation is both correct and avoids Pitfall 10 (blocking the event loop with synchronous clustering work) |
| Skip-rate floor logic | A new min-plays gate | `logic/skip_stats.py::compute_skip_rate`'s floor pattern (mirror, don't call directly — different table shape) | Same discipline already proven: below-floor data returns `None`/empty rather than a misleadingly confident 100%-of-1 result |

**Key insight:** Every "don't hand-roll" item in this phase is "don't hand-roll a second copy of
something Phase 10-13 already built correctly." The phase's actual net-new surface is small: three
SQL helpers, two prompt-template extensions, two small pure `logic/` functions, and two new Discord
entry points (`/discover`, `/jam suggest`) that call existing plumbing.

## Common Pitfalls

### Pitfall 1: `recall()` kind filter silently breaks existing call sites if the default is wrong

**What goes wrong:** If `kind` defaults to `""` or is required (no default), every existing call
site (`cogs/events.py`, `cogs/ai.py`'s `/ask`/`/roast`) breaks or silently starts filtering to an
empty/wrong kind, degrading Phase 11/15 recall to always-empty.
**Why it happens:** Adding a filter parameter to a widely-called function is an easy place to get
the default wrong.
**How to avoid:** `kind: str | None = None` with the SQL clause omitted entirely (not
`kind IS NULL`) when `None` — verified by a regression test asserting `search_memories(..., kind=None)`
produces the exact same SQL shape/row set as calling without the parameter at all.
**Warning signs:** Any drop in recall hit-rate for non-taste kinds after this phase ships.

### Pitfall 2: `user_artist_counts` has no `guild_id` — anchor-artist scope mismatch (OQ2 discrepancy)

**What goes wrong:** CONTEXT.md D-04 says "reads the invoker's top artist(s) from
`user_artist_counts`" but that table (`database.py` schema, confirmed) is `PRIMARY KEY (user_id,
artist)` with **no guild_id column** — it's a lifetime, cross-server count. If the planner reads
this literally, `/discover` on Server A could anchor on an artist the invoker only ever played on
Server B, then present it as "you're into X" wrapped in Server A's co-occurrence data — a subtle
identity mismatch (not a security/multi-user-leak issue, since it's still the invoker's own data,
but a UX/correctness surprise).
**Why it happens:** `user_artist_counts` predates guild-scoping (it was added Phase 1/2, before
multi-server hardening); `song_history` (Phase 4+) is the guild-scoped table.
**How to avoid:** Planner must explicitly choose: (a) use `user_artist_counts` as CONTEXT.md
literally states (simpler, one query, but cross-guild-flavored anchor), or (b) derive the
guild-scoped top artist via a new query `SELECT artist, COUNT(*) FROM song_history WHERE guild_id=$1
AND user_id=$2 GROUP BY artist ORDER BY COUNT(*) DESC LIMIT $3` (matches `get_user_artist_activity`'s
existing guild+user scoping template, feels more "in this server" personal). This research
recommends (b) for consistency with the guild-scoped feel D-04 describes ("server-adjacency-grounded"),
but either is defensible — CONTEXT.md's discretion section allows SQL-shape decisions at planning
time.
**Warning signs:** A user who only ever played an artist on a different server sees that artist
surfaced as their "top artist" on a server where they've never played it.

### Pitfall 3: Auto-queue filter bubble (research Pitfall 7, restated for this phase)

**What goes wrong:** A purely skip-avoidance-driven auto-queue converges toward generic,
inoffensive picks over weeks on a shared server — see full analysis in
`.planning/research/PITFALLS.md` Pitfall 7.
**Why it happens:** `was_skipped` is a strong negative signal with no equally strong positive
counterpart; naive optimization drifts toward "least skippable," not "most loved."
**How to avoid:** D-03's positive `taste_episode` blend is the intended counterbalance (a real
positive signal, not just skip-avoidance) — verify during planning/spike that the positive block
has genuine pull on suggestions, not just the negative block. Consider (not mandated) whether some
picks per round bypass the skip-hint filter entirely for exploration.
**Warning signs:** `/skips` analytics (Phase 12, already shipped) showing a narrowing artist/genre
set over successive auto-queue rounds.

### Pitfall 4: Cross-user leakage on new `recall()`/aggregate call sites

**What goes wrong:** A new SQL helper or `recall()` call site accidentally omits a `user_id`/`guild_id`
WHERE clause, or the D-03 per-member `recall()` loop accidentally surfaces one member's fact into
a context another member sees attributed to them.
**Why it happens:** New call sites are the highest-risk moment for this class of bug (research
PITFALLS.md Pitfall 4, explicitly flagged as inherited by this phase).
**How to avoid:** Every new `database.py` helper must follow the D-08 template exactly (bound `$N`
params, `WHERE guild_id`/`WHERE user_id` scoping, never merging cross-user rows into one result —
mirror `get_leaderboard_skips`'s "no user attribution" discipline for guild-wide aggregates). The
D-03 per-member blend must present facts as an unattributed collective block ("the room tends to
like...") — never "member X likes Y" — so even though the underlying `recall()` call is per-member,
the injected prompt text never identifies which member contributed which fact.
**Warning signs:** A roast/suggestion that names a specific *other* user's taste in a shared-queue
context.

### Pitfall 5: Blocking the event loop with in-Python co-occurrence computation

**What goes wrong:** Computing artist adjacency by fetching all guild `song_history` rows into
Python and clustering/grouping there (instead of `GROUP BY` in SQL) blocks the event loop on a
CPU-bound synchronous pass, stalling every guild's playback handling (research Pitfall 10).
**Why it happens:** Easy to reach for "fetch rows, process in Python" instead of pushing the
aggregation into the query.
**How to avoid:** `get_artist_cooccurrence` (Code Examples below) does the `GROUP BY`/`COUNT`/`ORDER
BY`/`LIMIT` entirely in SQL — the Python side only receives an already-ranked, already-capped list
of rows. Do not fetch raw rows and rank in Python.
**Warning signs:** A `/discover` invocation that takes noticeably longer as `song_history` grows.

## Code Examples

### `get_recently_skipped` (D-01 negative hint source)

```python
# Source: mirrors database.py:get_recent_songs (350-363) and get_leaderboard_skips (453-472) shape
async def get_recently_skipped(
    pool: asyncpg.Pool, *, guild_id: str, since: datetime, limit: int
) -> list[asyncpg.Record]:
    """Return recently-skipped (title, artist) pairs for a guild, newest first.

    Guild-scoped ($1), index-friendly (queued_at > $2 against idx_history_guild),
    bound $N params (D-08). No per-user attribution — collective signal (D-01).
    """
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

### `get_artist_cooccurrence` (OQ2 resolution — BRAIN-02 core)

```python
# Source: NEW helper, follows the D-08 scoping template (get_user_artist_activity precedent)
async def get_artist_cooccurrence(
    pool: asyncpg.Pool, *, guild_id: str, anchor_artist: str, since: datetime, limit: int
) -> list[asyncpg.Record]:
    """Return artists that co-occurred with anchor_artist on the same day in this guild.

    "Co-occur" = played (by anyone) in this guild on a calendar day when anchor_artist
    was also played in this guild — a simple, non-hallucinated adjacency signal
    (research FEATURES.md: "co-occurrence = artists appearing in the same session/day").

    Guild-wide aggregate (D-04): no per-user attribution in the result, mirroring
    get_leaderboard_skips's "entity is the artist, not the user" discipline — satisfies
    Criterion 4 even though the underlying rows span multiple users' plays.

    Both the CTE and the main query filter guild_id=$1 AND queued_at > $3, matching
    idx_history_guild(guild_id, queued_at DESC) for an index-friendly range scan. The
    date_trunc('day', ...) equality join itself is not indexed, but is bounded by the
    guild+window filter first — acceptable at this project's single-community scale
    (CLAUDE.md / research STACK.md).
    """
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

### `is_recently_skipped_artist` (D-02 hard post-filter — new `logic/autoqueue.py` function)

```python
# Source: NEW pure function, sibling of validate_youtube_match in logic/autoqueue.py.
# Reuses the module's existing _normalize_for_match — do not duplicate the tokenizer.
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

### `select_positive_taste_context` (D-03 blend/cap — new `logic/taste.py` function)

```python
# Source: NEW pure function, sibling of summarize_taste in logic/taste.py.
def select_positive_taste_context(
    member_facts: list[list[str]], *, cap: int
) -> list[str]:
    """Flatten per-member recalled taste_episode facts into one capped, deduped list.

    member_facts: one list[str] per in-voice member (already recall()-filtered to
    kind="taste_episode" upstream). Interleaves round-robin across members by index
    position (not member-by-member concatenation) so no single member's facts dominate
    the cap purely by list position — mirrors D-03's "collective, not per-listener"
    framing.

    Deliberately presents an UNATTRIBUTED collective list — the caller must not
    re-associate a returned fact with which member it came from (Pitfall 4).
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

## State of the Art

Not applicable — this phase extends existing, currently-shipped internal patterns (Phase 10-13
`logic/` seam, Phase 11 recall/remember pipeline, Phase 12 skip-stats aggregate template). No
external library/API version drift is relevant.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | A same-guild-day bucket join is an adequate "co-occurrence" definition for a small single-community bot (not same-session/rolling-window) | Pattern 3 / Code Examples | If the guild has very high daily song volume, day-bucket adjacency could feel too loose (everything co-occurs with everything within a busy day) — would need tightening to a tighter time window (e.g. ±30-60 min) instead of full-day, a spike/tuning decision not a design-invalidating one |
| A2 | `user_artist_counts` (no guild_id) vs. a new guild-scoped `song_history` top-artist query — this research recommends the guild-scoped option but CONTEXT.md D-04 literally names `user_artist_counts` | Pitfall 2 | Low risk either way — both are invoker-anchored and safe; only affects UX correctness (cross-guild-flavored vs. server-authentic anchor), not multi-user-safety (Criterion 4) |
| A3 | A ~7-day recency window (mirroring `TASTE_LOOKBACK_DAYS`) is a reasonable default for `get_recently_skipped`'s window, and a longer window (~90 days, mirroring `TASTE_BASELINE_DAYS`) for `get_artist_cooccurrence`'s bound | Code Examples | Purely a tuning value — CONTEXT.md already marks all numeric windows as Claude's-discretion/spike territory; no correctness risk, only feel-tuning |
| A4 | Round-robin (not simple concatenation) is the right blend order for D-03's multi-member taste facts, to avoid one member's `recall()` call dominating the cap by list position | Code Examples | Low risk — either order satisfies Criterion 4 (neither leaks attribution); round-robin is a fairness nicety, not a requirement CONTEXT.md mandates |

**All claims above were derived from direct code reading (database.py, services/memory.py,
models/memory.py, logic/autoqueue.py, logic/taste.py, personality/prompts.py, cogs/ai.py,
cogs/library.py) — this is a code-only phase with no external library/API claims requiring
Context7 or WebSearch verification.**

## Open Questions

1. **OQ1 — RESOLVED.** Add optional `kind: str | None = None` to `database.search_memories()` and
   `MemoryService.recall()`; append `AND kind = $N` only when provided. No `MemoryFact` change
   needed. Byte-identical for every existing call site when omitted. See Pattern 2 / Code Examples.

2. **OQ2 — RESOLVED (with one flagged discrepancy).** Co-occurrence = same-guild-calendar-day
   adjacency, bounded by a recency window, computed entirely in SQL (`get_artist_cooccurrence`,
   Code Examples). Guild-wide aggregate, no per-user attribution — satisfies Criterion 4.
   **Flagged discrepancy (Pitfall 2):** CONTEXT.md D-04 names `user_artist_counts` as the anchor
   source, but that table has no `guild_id` column (lifetime cross-server counts). Planner must
   explicitly decide: use it as-is (simpler, cross-guild-flavored anchor) or derive a guild-scoped
   top artist from `song_history` instead (more "in this server" authentic, one more query). This
   research recommends the guild-scoped option for consistency with D-04's "server-adjacency-grounded"
   framing, but both are safe and either is a reasonable planning-time call.

3. **Prompt anchor for D-03's per-member `recall()` call.** `recall(user_id, guild_id, query_text,
   kind="taste_episode")` needs a `query_text` to embed as the ANN query. Unlike `/ask` (the user's
   actual question) or `/roast` (a roast-context string), auto-queue has no natural "question" —
   a generic anchor phrase (e.g. `"their music taste"` or the current session's recent artist
   names) is needed. This is a small prompt-design detail left to planning; any reasonable fixed
   or session-derived anchor string works since the ANN search is already scoped to `user_id` +
   `kind="taste_episode"`, so the anchor mainly affects *which* taste facts rank highest when a
   user has more than `MEMORY_TOP_K` taste facts (uncommon at `MEMORY_MAX_PER_USER` early growth).

4. **Cog placement for `/discover`.** D-05 leans `cogs/music.py` (it can queue) over `cogs/ops.py`.
   This research concurs — `cogs/music.py` already owns `_get_text_channel`-style helpers and the
   `Track`/queue-add flow `/discover`'s confirm-to-queue action needs, whereas `cogs/ops.py`'s
   existing commands (`/leaderboard`, `/skips`, `/stats`) are all read-only. Confirms D-05's lean
   as the right default; not a blocking question.

## Environment Availability

Skipped — this phase has no new external dependencies. Postgres (Neon), `pgvector`, and the
Gemini API are already-provisioned infrastructure verified operational by Phases 4/5/11/13; this
phase only adds new SQL queries and prompt calls against those existing connections.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing, no new config) |
| Config file | none detected (`tests/conftest.py` exists; no `pytest.ini`/`pyproject.toml` `[tool.pytest]` section) — Wave 0 gap only if the planner wants one; not currently required (existing suite runs fine without it) |
| Quick run command | `python -m pytest tests/test_taste_logic.py tests/test_autoqueue_validate.py tests/test_memory.py -q` (scope to touched modules) |
| Full suite command | `python -m pytest tests/ -q` (650 pass / 0 fail baseline per Phase 13 close) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BRAIN-01 | `is_recently_skipped_artist` rejects a candidate whose artist matches a recently-skipped artist (D-02) | unit | `pytest tests/test_autoqueue_validate.py -k skipped -x` | ❌ Wave 0 — new test file/cases needed alongside existing `validate_youtube_match` tests |
| BRAIN-01 | `select_positive_taste_context` caps at config value, dedups, round-robins across members (D-03) | unit | `pytest tests/test_taste_logic.py -k positive_taste -x` | ❌ Wave 0 |
| BRAIN-01 | `build_recommendation_prompt` is byte-identical when `recently_skipped`/`positive_taste` are omitted (Pattern 1) | unit | `pytest tests/test_prompts.py -k recommendation -x` | ❌ Wave 0 — no `tests/test_prompts.py` currently exists; check for an existing prompt-test file before creating a new one |
| BRAIN-01 | `search_memories(..., kind=None)` produces identical SQL/rows to the pre-Phase-14 call shape (OQ1 regression) | integration (live-DB) | `pytest tests/test_memory.py -k kind_filter -x` | ❌ Wave 0 — extends existing `tests/test_memory.py`; needs live Postgres per existing Phase 11 integration-test convention |
| BRAIN-02 | `get_artist_cooccurrence` never returns a row attributable to a single other user (Criterion 4 regression, mirrors Pitfall 4 test) | integration (live-DB) | `pytest tests/test_database_taste.py -k cooccurrence -x` | ❌ Wave 0 — new integration test file, mirrors `tests/test_memory_taste.py` convention for Phase 13's live-DB aggregate tests |
| BRAIN-02 | Cold-start (no `user_artist_counts`/`song_history` rows) returns empty, cog shows in-character message, never errors (D-05) | unit + manual | `pytest tests/test_taste_logic.py -k cold_start -x` | ❌ Wave 0 |
| BRAIN-03 | `validate_youtube_match` gates every `/jam suggest` candidate (reused, already locked) | unit | `pytest tests/test_autoqueue_validate.py -x` | ✅ existing — no new test needed, just confirm the jam-suggest call site uses it identically |
| BRAIN-03 | `parse_suggestions` parses jam-suggestion Gemini output using the same `{title, artist}` contract | unit | `pytest tests/test_autoqueue_parse.py -x` | ✅ existing — reused, add a jam-flavored fixture case if the prompt differs meaningfully in framing |
| BRAIN-03 | No suggestions survive validation → in-character "nothing landed" message, jam snapshot untouched (D-07) | unit | `pytest tests/test_library_jam_suggest.py -k none_survive -x` | ❌ Wave 0 — new test file mirroring the `jam_save`/`jam_add` cog-test convention (check for an existing `tests/test_library.py` first) |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_taste_logic.py tests/test_autoqueue_validate.py tests/test_memory.py -q` (fast, touched-module scope)
- **Per wave merge:** `python -m pytest tests/ -q` (full suite green)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_autoqueue_validate.py` — add `is_recently_skipped_artist` coverage (BRAIN-01/D-02)
- [ ] `tests/test_taste_logic.py` — add `select_positive_taste_context` coverage (BRAIN-01/D-03)
- [ ] Confirm whether a prompt-builder test file already exists before creating `tests/test_prompts.py` — grep for `build_recommendation_prompt`/`build_chat_prompt` test coverage first; extend in place if found
- [ ] `tests/test_memory.py` — add a `kind` regression case confirming `recall()`/`search_memories(kind=None)` byte-identical behavior (OQ1)
- [ ] New live-DB integration test(s) for `get_recently_skipped` / `get_artist_cooccurrence` / guild-scoped-or-not top-artist helper, mirroring `tests/test_memory_taste.py`'s Phase 13 convention for DB-backed aggregate tests
- [ ] `tests/test_library.py` (or equivalent) — `/jam suggest` cog-level coverage for the propose-and-confirm flow and the "nothing landed" branch (D-07)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Discord OAuth handles identity; unchanged by this phase |
| V3 Session Management | No | No new session concept introduced |
| V4 Access Control | Yes | Guild-scoped/invoker-anchored SQL (D-08 template) — no query returns another user's individual rows; Discord slash-command guild context is the access-control boundary (unchanged pattern from Phase 12) |
| V5 Input Validation | Yes | Jam `name` param reuses existing `PLAYLIST_NAME_MAX_LENGTH`/empty-check validation (cogs/library.py, unchanged pattern); Gemini-returned `{title, artist}` suggestions are never trusted directly — always re-validated against real YouTube search results via `validate_youtube_match` before use (existing pattern, reused) |
| V6 Cryptography | No | No new secrets/crypto surface |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via string-interpolated guild/user/artist values | Tampering | All new queries use bound `$N` positional asyncpg params exclusively (T-08-01/D-08 discipline) — never f-string/`.format()` SQL |
| Cross-user data leakage via a new aggregate query missing a scope filter | Information Disclosure | Every new `database.py` helper mirrors `get_leaderboard_skips`/`get_user_skip_rate`'s guild_id/user_id WHERE-clause template; `/discover`/BRAIN-01 blends stay unattributed collective text, never "user X likes Y" (Pitfall 4) |
| Gemini-hallucinated track/artist offered as real | Spoofing (content) | `validate_youtube_match` token-set containment gate on every suggestion before it is ever offered or queued (existing, reused verbatim per BRAIN-03's hard requirement) |
| Prompt injection via song titles/artist names from `song_history` (user-influenced YouTube metadata) fed into a Gemini prompt | Tampering | Existing risk surface, unchanged by this phase — `build_genius_search_query` already cleans titles before recommendation prompts (cogs/ai.py:280); no new trust boundary is crossed since this phase reuses the same recent-songs cleaning step for the new negative-hint block |

## Sources

### Primary (HIGH confidence — direct codebase reads this session)
- `database.py` — `search_memories` (899-939), `get_recent_songs` (350-363), `get_leaderboard_skips`
  (453-472), `get_user_skip_rate` (1255-1276), `get_active_taste_users`/`get_user_artist_activity`
  (1284-1360), `user_memories`/`song_history`/`user_artist_counts`/`guild_jams` schema (SCHEMA_SQL)
- `services/memory.py` — full `recall`/`remember`/`distill`/`distill_and_remember`/`sweep` read
- `models/memory.py` — `MemoryFact` dataclass fields (no `kind` field, confirmed)
- `logic/autoqueue.py` — `validate_youtube_match`, `_normalize_for_match` (full read)
- `logic/taste.py` — `classify_artist`, `summarize_taste`, `resolve_decay_days` (full read, Phase 13)
- `logic/skip_stats.py` — `compute_skip_rate` floor pattern (full read)
- `cogs/ai.py` — `try_auto_queue` (255-448), `parse_suggestions` (43-83)
- `cogs/library.py` — `/jam` group (692-967): `jam_save`, `jam_add`, `jam_load`
- `personality/prompts.py` — `build_chat_prompt`, `build_recommendation_prompt`,
  `MUSIC_RECOMMENDATION_PROMPT` (full read)
- `models/queue.py` — `Track.to_dict`/`from_dict` (jam snapshot serialization shape)
- `config.py` — `MEMORY_*`/`TASTE_*`/`AUTO_QUEUE_*` knob block (lines 53-208)
- `bot.py` — `_initialize_once` service-wiring pattern (356-450), cog-load list (1121-1128)
- `.planning/phases/14-smarter-music-brain/14-CONTEXT.md` — full read (D-01..D-08, OQ1/OQ2)
- `.planning/phases/13-semantic-music-memory/13-CONTEXT.md` — full read (substrate precedent)
- `.planning/REQUIREMENTS.md`, `.planning/STATE.md` — full read

### Secondary (MEDIUM confidence — v1.3 research docs, already-committed prior research)
- `.planning/research/ARCHITECTURE.md` §(a)-(d) — `TasteService`/`logic/taste.py` design guidance,
  the `recall()` guild-scoping gotcha (lines 156-164)
- `.planning/research/FEATURES.md` — co-occurrence definition precedent ("same session/day,
  weighted by frequency"), anti-feature table (collaborative filtering / audio embeddings / genre
  taxonomy rejected)
- `.planning/research/PITFALLS.md` — Pitfall 4 (cross-user leak), Pitfall 5 (stale taste), Pitfall 7
  (auto-queue filter bubble), Pitfall 10 (event-loop blocking)
- `.planning/research/STACK.md` — "no new library" confirmation for taste-graph SQL aggregation

### Tertiary (LOW confidence)
- None — this phase required no WebSearch/Context7 lookups; it is entirely internal-codebase
  research over an already-researched (v1.3 SUMMARY/FEATURES/ARCHITECTURE/PITFALLS,
  `research done` per project memory) milestone.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies, every pattern verified by direct code reads
- Architecture: HIGH — mirrors four already-shipped precedents (get_user_skip_rate,
  get_user_artist_activity, get_leaderboard_skips, build_chat_prompt's optional-block pattern)
- Pitfalls: HIGH for cross-user-leak/event-loop/kind-filter risks (verified against real schema
  and code); MEDIUM for the filter-bubble pitfall (inherited research finding, not newly verified
  against live auto-queue behavior — no live-Discord UAT available this session, consistent with
  the milestone's ongoing parked-UAT status)

**Research date:** 2026-07-02
**Valid until:** 30 days (stable internal codebase, no external API/library version drift risk)
