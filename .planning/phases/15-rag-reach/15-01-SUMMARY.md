---
phase: 15-rag-reach
plan: 01
subsystem: database
tags: [postgres, asyncpg, pgvector, rag, memory]

# Dependency graph
requires:
  - phase: 11-rag-long-term-memory
    provides: user_memories table (pgvector), search_memories, insert_memory, evict_lowest_salience patterns
provides:
  - "database.list_user_memories(pool, *, user_id, limit) — display-ordered SELECT for the /memory view"
  - "database.delete_all_user_memories(pool, user_id) — single-param nuke-all DELETE for /memory forget"
  - "tests/test_database_phase15.py — static signature/scoping lock + live-DB remember->forget->recall==[] proof"
affects: [15-03 (/memory cog consumes both helpers), 16-proactive-memory-callbacks (hard-depends on forget being a verified real deletion)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Nuke-all DELETE helpers take exactly one identity parameter (pool, user_id) — no second id param, ever, so a future edit cannot introduce a cross-user forget without failing a static inspect.signature test"
    - "Display-ordering (salience DESC, created_at DESC) is a distinct query shape from eviction-ordering (salience ASC) — same table, opposite sort intent, must not be conflated"

key-files:
  created: [tests/test_database_phase15.py]
  modified: [database.py]

key-decisions:
  - "list_user_memories's limit param is documented (not enforced in code) to require config.MEMORY_MAX_PER_USER at the 15-03 call site — the helper itself has no opinion on which config constant is passed, so the guard is a docstring contract for the caller, not a code check"

patterns-established:
  - "Structural signature-lock test: assert inspect.signature(fn).parameters == [...] to make an entire class of future security regression (accidental extra parameter) fail loudly at test time"

requirements-completed: [RAG-03, RAG-04]

# Metrics
duration: 5min
completed: 2026-07-03
---

# Phase 15 Plan 1: DB Substrate for /memory View + Forget Summary

**Added `list_user_memories` (display-ordered, user-scoped SELECT) and `delete_all_user_memories` (single-param hard-delete) to `database.py`, locked by static signature/scoping tests plus a live-DB `remember -> forget -> recall == []` proof through the real pgvector ANN search path.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-03T01:42:33+08:00
- **Completed:** 2026-07-03T01:44:57+08:00
- **Tasks:** 3 completed
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- `database.list_user_memories` — plain, non-ANN SELECT of a user's full memory store, ordered best/most-recent first, for the upcoming `/memory` view (RAG-03).
- `database.delete_all_user_memories` — a real hard `DELETE FROM user_memories WHERE user_id = $1`, structurally incapable of targeting another user because its signature has exactly one identity parameter (RAG-04).
- A live-DB integration test (`test_remember_forget_recall_empty`) that inserts a memory, confirms it via `search_memories`, deletes it, and re-confirms `search_memories` returns `[]` — the actual trust-escape-hatch proof Phase 16 depends on, not just a row-count check.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add list_user_memories + delete_all_user_memories to database.py** - `d88192b` (feat)
2. **Task 2: Static source-inspection tests in tests/test_database_phase15.py** - `b1c43ca` (test)
3. **Task 3: Live-DB remember -> forget -> recall == [] proof (Success Criterion 4)** - `fece449` (test)

**Plan metadata:** (this commit, following SUMMARY creation)

## Files Created/Modified
- `database.py` - Added `list_user_memories` and `delete_all_user_memories` near the existing Phase 11 memory-helper block (after `evict_lowest_salience`, before `bump_surfaced`).
- `tests/test_database_phase15.py` - New file: `TestPhase15HelpersExist` static class (7 tests, no live DB needed) + `test_remember_forget_recall_empty` live-DB integration test (skips cleanly without `TEST_DATABASE_URL`).

## Decisions Made
- Followed 15-PATTERNS.md's research-provided code verbatim for both helpers (exact SQL text, exact docstrings) rather than reinterpreting — this phase's plan explicitly called out the patterns doc as the source of truth.
- Placed both new helpers between `evict_lowest_salience` and `bump_surfaced` (matching the plan's stated location) rather than at end-of-file, keeping all Phase 11/15 memory helpers physically grouped.

## Deviations from Plan

None - plan executed exactly as written. All three tasks matched their `<action>` blocks precisely; no Rule 1-4 triggers encountered.

## Issues Encountered

None. The live-DB test (`test_remember_forget_recall_empty`) skips in this environment because `TEST_DATABASE_URL` is not configured (matching the existing `test_database_phase11.py` pattern, which also skips here) — this is expected and documented in the plan's Task 3 `<done>` note: "Phase gate: MUST be run at least once against a real pgvector Postgres before phase close — it is RAG-04's verification." That run is deferred to phase close / whenever a live pgvector DB is available for this environment, consistent with how Phase 11's live-DB tests are handled.

## User Setup Required

None - no external service configuration required. (The live-DB test run against a real pgvector Postgres remains an open phase-close item, tracked above — not a per-plan blocker.)

## Next Phase Readiness
- `database.list_user_memories` and `database.delete_all_user_memories` are ready for 15-03's `/memory` cog to consume directly (view + forget commands).
- Full regression suite green: `pytest tests/ -x -q` → 768 passed, 106 skipped, 0 failed.
- Static tests structurally lock the single-identity-parameter contract, so 15-03 (or any future phase) cannot accidentally widen `delete_all_user_memories` into a cross-user forget without breaking a test immediately.
- Outstanding: the live-DB Success Criterion 4 test must be run at least once against a real pgvector Postgres (e.g. Neon) before Phase 15 formally closes — flagged for phase-close verification, not blocking 15-02/15-03 execution.

---
*Phase: 15-rag-reach*
*Completed: 2026-07-03*

## Self-Check: PASSED

- FOUND: database.py
- FOUND: tests/test_database_phase15.py
- FOUND: .planning/phases/15-rag-reach/15-01-SUMMARY.md
- FOUND commit: d88192b
- FOUND commit: b1c43ca
- FOUND commit: fece449
- FOUND commit: 7270354
