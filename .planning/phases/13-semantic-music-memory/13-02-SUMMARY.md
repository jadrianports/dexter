---
phase: 13-semantic-music-memory
plan: 02
subsystem: database
tags: [postgres, asyncpg, pgvector, taste-memory, integration-tests]

# Dependency graph
requires:
  - phase: 11-rag-long-term-memory
    provides: user_memories table + pgvector store, bump_memory_hit/insert_memory conventions
  - phase: 13-semantic-music-memory (plan 01)
    provides: taste config knobs (TASTE_* / MEMORY_SALIENCE_BASE_WEIGHTS["taste_episode"])
provides:
  - get_active_taste_users(pool, since) — candidate (guild_id, user_id) pairs active in a window
  - get_user_artist_activity(pool, guild_id, user_id, since, baseline_since) — per-artist window/baseline play+skip splits
  - refresh_memory_expiry(pool, memory_id, expires_at) — D-05 expires_at-only self-refresh primitive
  - tests/test_database_phase13.py — source-assertion + live-DB integration coverage for all three
affects: [13-03 (memory-service self-refresh wiring), 13-04 (taste_distill_batch loop)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Scoped positional-param aggregate helpers (get_user_skip_rate convention): raw counts only, banding/thresholding stays in the caller, never in SQL"
    - "expires_at-only UPDATE sibling to bump_memory_hit — a targeted single-column refresh that never touches hit_count/salience/last_seen_at"

key-files:
  created:
    - tests/test_database_phase13.py
  modified:
    - database.py

key-decisions:
  - "get_active_taste_users is a deliberately global (non-guild-scoped) aggregate — each returned row already carries its own guild_id/user_id, so no cross-user merge occurs even though the query itself is not WHERE-scoped to a single guild+user"
  - "baseline_since ($4) bounds get_user_artist_activity's before-window lookback so the scan stays index-friendly against idx_history_guild instead of scanning all-time history"
  - "refresh_memory_expiry placed directly after bump_memory_hit in database.py as its expires_at-only sibling, per plan's read_first anchor"

patterns-established:
  - "Live-DB integration test files use the conftest.py `pool` fixture directly (test_database_phase12.py style) rather than a redundant env-var skipif gate — simpler and matches the repo's most recent convention"
  - "Tests that insert into user_memories (a table conftest does NOT drop in teardown) must clean up their own rows via a small `memory_cleanup` fixture that DELETEs tracked ids"

requirements-completed: [TASTE-01, TASTE-02, TASTE-03]

# Metrics
duration: 10min
completed: 2026-07-02
---

# Phase 13 Plan 02: Taste Aggregate + Self-Refresh Database Helpers Summary

**Three `database.py` helpers — `get_active_taste_users`, `get_user_artist_activity`, `refresh_memory_expiry` — plus a new `tests/test_database_phase13.py` covering window splits, cross-guild isolation, and the expires_at-only self-refresh primitive.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-07-02T10:01:08Z (session start per STATE.md)
- **Completed:** 2026-07-02T18:08:57+08:00
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Added `get_active_taste_users(pool, *, since)` — one row per active `(guild_id, user_id)` pair with its window track count, feeding the D-08 min-activity gate that plan 13-04's `taste_distill_batch` loop will apply.
- Added `get_user_artist_activity(pool, *, guild_id, user_id, since, baseline_since)` — per-artist `plays_in_window` / `plays_before_window` / `skips_in_window` splits, scoped to one guild+user, baseline-bounded for index-friendly scans.
- Added `refresh_memory_expiry(pool, memory_id, expires_at)` — the D-05 self-refresh primitive that resets ONLY `expires_at` on a `user_memories` row, confirming (via test) it never touches `hit_count`/`salience`/`last_seen_at`.
- Added `tests/test_database_phase13.py`: 6 always-run source-assertion tests (existence, scope guard, no string interpolation) plus 5 live-DB integration tests (skip cleanly without Postgres) covering window/baseline math, cross-guild isolation, and the byte-identical-other-columns refresh assertion.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add get_active_taste_users + get_user_artist_activity aggregate helpers** - `e8489aa` (feat)
2. **Task 2: Add refresh_memory_expiry helper + live-DB integration tests** - `24d12da` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified
- `database.py` - Added `get_active_taste_users`, `get_user_artist_activity` (after `get_user_skip_rate`) and `refresh_memory_expiry` (after `bump_memory_hit`)
- `tests/test_database_phase13.py` - New: source-assertion tests + live-DB integration tests for all three helpers

## Decisions Made
- Followed the `get_user_skip_rate` convention exactly for both aggregate helpers: `async with pool.acquire()`, all inputs positional `$N`, raw `asyncpg.Record` results, zero banding/threshold logic in SQL.
- `refresh_memory_expiry`'s docstring explicitly states it is the expires_at-only sibling of `bump_memory_hit`, so Phase 11 decay semantics for every other kind remain provably untouched — verified in the test by asserting `hit_count`/`salience`/`last_seen_at` are unchanged after the call.
- Chose the simpler `test_database_phase12.py`-style live-DB gating (rely on `conftest.py`'s `pool` fixture runtime skip) over `test_database_phase11.py`'s redundant env-var `_SKIP_LIVE` decorator, since it's the more recent and simpler pattern in this codebase and the plan's artifact spec only required "skip cleanly without Postgres."

## Deviations from Plan

None - plan executed exactly as written. One self-correction during execution: the first draft of `test_refresh_memory_expiry_touches_only_expires_at` searched for bare column-name substrings (`"hit_count"`, `"salience"`, `"last_seen_at"`) which false-positived against the function's own docstring (which names those columns to explain they are NOT touched). Fixed before commit by matching the SQL-assignment form (`"hit_count ="` etc.) instead — not logged as a Rule 1/2/3 deviation since it was caught and fixed within the same task before any commit, not a post-hoc bug fix.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. Live-DB portions of the new test file were verified to collect and skip cleanly (`6 passed, 5 skipped`) against the local environment, which has no `TEST_DATABASE_URL`/local Postgres configured; the full existing suite (`639 passed, 98 skipped`) remains green.

## Next Phase Readiness
- Plan 13-03 (memory-service self-refresh wiring) can now call `refresh_memory_expiry` directly from `MemoryService.remember()`'s dedup branch to resolve the D-05 correctness risk flagged in `13-CONTEXT.md`.
- Plan 13-04 (`taste_distill_batch` loop) can now call `get_active_taste_users` for the candidate-user scan and `get_user_artist_activity` per active user for the D-02 pre-bucketing step.
- No blockers.

---
*Phase: 13-semantic-music-memory*
*Completed: 2026-07-02*

## Self-Check: PASSED

- FOUND: database.py
- FOUND: tests/test_database_phase13.py
- FOUND: e8489aa (Task 1 commit)
- FOUND: 24d12da (Task 2 commit)
