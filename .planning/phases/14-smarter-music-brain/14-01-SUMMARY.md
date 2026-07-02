---
phase: 14-smarter-music-brain
plan: 01
subsystem: database
tags: [postgres, asyncpg, pgvector, sql-aggregates, taste-graph]

# Dependency graph
requires:
  - phase: 13-semantic-music-memory
    provides: user_memories table, MemoryService.recall/remember, kind column on user_memories
provides:
  - "database.get_recently_skipped — guild-scoped negative-hint source for auto-queue (D-01)"
  - "database.get_user_top_artist — guild+invoker-scoped /discover anchor (D-04, OQ2 Option B)"
  - "database.get_artist_cooccurrence — guild-wide same-day co-occurrence for /discover (D-04)"
  - "database.search_memories kind param — optional exact-match filter, byte-identical when omitted (OQ1)"
  - "services.memory.MemoryService.recall kind param — forwards to search_memories"
  - "6 config.py tuning knobs for auto-queue/discover/jam-suggest (Phase 14)"
affects: [14-02-plan, 14-03-plan, 14-04-plan, 14-05-plan]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "D-08 scoping template: bound $N positional params, WHERE guild_id [AND user_id], queued_at > $N index-friendly bounds"
    - "Guild-wide no-attribution aggregate: SELECT never exposes user_id when the entity is a title/artist collective signal"
    - "Optional-signal-byte-identical-when-omitted: kind: str | None = None, clause omitted entirely (never `IS NULL`) when not provided"

key-files:
  created:
    - tests/test_database_phase14.py
  modified:
    - config.py
    - database.py
    - services/memory.py
    - tests/test_config.py
    - tests/test_memory.py

key-decisions:
  - "OQ2 anchor discrepancy resolved as Option B: get_user_top_artist derives the /discover anchor from guild-scoped song_history (guild_id + user_id), NOT from the lifetime cross-server user_artist_counts table (which has no guild_id column) — avoids surfacing a cross-guild-flavored 'top artist' the invoker never played on this server"
  - "OQ1 resolved: search_memories/recall's kind param defaults to None and omits the SQL clause entirely when unset (never 'kind IS NULL'), guaranteeing byte-identical behavior for every pre-Phase-14 call site"
  - "get_artist_cooccurrence co-occurrence definition = same-guild-calendar-day bucket join (date_trunc('day', queued_at)) over song_history, a guild-wide aggregate with no per-user attribution"

patterns-established:
  - "Pattern: new database.py aggregate helpers mirror get_user_skip_rate/get_user_artist_activity's D-08 template exactly — no try/except inside helpers, callers wrap DB calls"
  - "Pattern: static source-assertion tests (inspect.getsource) verify bound-$N params + no f-string/.format() SQL + no user_id leak, independent of live-DB availability"

requirements-completed: [BRAIN-01, BRAIN-02]

# Metrics
duration: 25min
completed: 2026-07-02
---

# Phase 14 Plan 1: Smarter Music Brain — SQL + Config Substrate Summary

**Three new guild/invoker-scoped `database.py` aggregate helpers (recently-skipped, top-artist anchor, artist co-occurrence), an optional `kind` filter threaded through `search_memories`/`recall` via TDD, and six Phase 14 config knobs — the data layer wave-2 cog plans will consume.**

## Performance

- **Duration:** 25 min
- **Tasks:** 3 completed
- **Files modified:** 5 (config.py, database.py, services/memory.py, tests/test_config.py, tests/test_memory.py) + 1 created (tests/test_database_phase14.py)

## Accomplishments
- Added `get_recently_skipped`, `get_user_top_artist`, `get_artist_cooccurrence` to `database.py`, each following the D-08 bound-`$N`-params / no-f-string / no-cross-user-leak template, with the Option B anchor decision documented in-docstring
- Threaded an optional `kind: str | None = None` filter through `database.search_memories` and `services/memory.py::MemoryService.recall` via a full RED→GREEN TDD cycle, proving byte-identical behavior when `kind` is omitted
- Landed all six Phase 14 tuning knobs in `config.py` with inline `D-NN` rationale comments

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the six Phase 14 config knobs** - `41b84a7` (feat)
2. **Task 2: Add the three guild/invoker-scoped aggregate helpers to database.py** - `4996f59` (feat)
3. **Task 3: Thread optional kind filter through search_memories and recall (OQ1)** - `c13e64c` (test, RED) + `267a231` (feat, GREEN)

## Files Created/Modified
- `config.py` - Added `# --- Phase 14: Smarter Music Brain ---` block with 6 tuning knobs
- `database.py` - Added `get_recently_skipped`, `get_user_top_artist`, `get_artist_cooccurrence`; added `kind` param to `search_memories`
- `services/memory.py` - Added `kind` param to `MemoryService.recall`, forwarded to `database.search_memories`
- `tests/test_config.py` - `TestPhase14Constants` + flat-alias test for all six knobs
- `tests/test_database_phase14.py` - Static source-assertion class (scoping, no-f-string, no-user_id-leak) + live-DB cross-user isolation regressions for the three new helpers
- `tests/test_memory.py` - `TestSearchMemoriesKindFilter` (fake-pool SQL/param capture) + `TestRecallKindParam` (fake `search_memories` capturing forwarded `kind`); widened two pre-existing `fake_search` stubs to accept `kind=None`

## Decisions Made
- **OQ2 / anchor discrepancy (D-04):** Chose Option B — `get_user_top_artist` derives from guild-scoped `song_history` (matching `get_user_artist_activity`'s discipline), not from the guild-less `user_artist_counts` table, to avoid a cross-guild-flavored "top artist" surprise on `/discover`.
- **OQ1 / kind-scoped recall:** `kind` defaults to `None` and the SQL clause is omitted entirely (not `kind IS NULL`) when unset, verified via a dedicated fake-pool test that captures the emitted SQL string and param tuple.
- **Co-occurrence definition (D-04):** Same-guild-calendar-day bucket join via a `WITH anchor_days AS (...)` CTE over `song_history`, entirely in SQL, guild-wide (no per-user attribution) — mirrors `get_leaderboard_skips`'s no-attribution discipline.

## Deviations from Plan

None - plan executed exactly as written. Task 3 followed the plan's TDD instruction precisely (RED commit `c13e64c`, GREEN commit `267a231`).

## Issues Encountered

The `get_artist_cooccurrence` static-source test initially over-matched: checking `"user_id" not in inspect.getsource(fn)` also caught the docstring's prose discussion of the no-attribution guarantee (which necessarily mentions "user_id" to explain the invariant). Fixed in the same task/commit by stripping the triple-quoted docstring before the substring check, so only the actual SQL/code is inspected — not a plan deviation, just a self-correction during test authoring before the commit landed.

## Verification

```
python -m pytest tests/test_config.py tests/test_database_phase14.py tests/test_memory.py -q
# 130 passed, 7 skipped (live-DB cases skip cleanly — no Postgres available in this sandbox)

python -m pytest tests/ -q
# 669 passed, 105 skipped
```

## TDD Gate Compliance

Task 3 (`tdd="true"`) gate sequence verified in git log:
- RED: `c13e64c test(14-01): add failing tests for kind filter (OQ1 RED)` — 3 of the 5 new assertions failed pre-implementation (TypeError: unexpected keyword argument 'kind'), confirming the tests exercised not-yet-existing behavior.
- GREEN: `267a231 feat(14-01): thread optional kind filter through search_memories and recall (OQ1 GREEN)` — all tests pass after implementation.
- No REFACTOR commit needed (implementation matched the PATTERNS.md-specified shape on the first pass).

## User Setup Required

None - no external service configuration required. Zero new dependencies, zero new tables, zero new limiters.

## Next Phase Readiness

- The 3 new `database.py` helpers, the `kind`-filtered `recall()`, and the 6 config knobs are ready for wave-2 plans (14-02 through 14-05) to consume without inventing any new SQL or scoping.
- Live-DB regression tests for the new helpers exist in `tests/test_database_phase14.py` but are skipped in this sandbox (no reachable Postgres) — they will run against a live `dexter_test` DB in CI/local-dev per the existing `tests/conftest.py` `pool` fixture convention.
- No blockers for 14-02 (pure logic + prompt builders).

---
*Phase: 14-smarter-music-brain*
*Completed: 2026-07-02*

## Self-Check: PASSED

All created/modified files confirmed present on disk; all 4 task commit hashes
(`41b84a7`, `4996f59`, `c13e64c`, `267a231`) confirmed present in git log.
