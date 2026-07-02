---
phase: 13-semantic-music-memory
plan: 03
subsystem: memory
tags: [rag, memory-decay, taste-memory, asyncpg]

# Dependency graph
requires:
  - phase: 13-semantic-music-memory (plan 01)
    provides: logic/taste.py::resolve_decay_days, config.MEMORY_DECAY_DAYS_BY_KIND, config.TASTE_DECAY_DAYS
  - phase: 13-semantic-music-memory (plan 02)
    provides: database.py::refresh_memory_expiry (expires_at-only self-refresh primitive)
provides:
  - services/memory.py::remember() kind-aware insert horizon (D-03) via resolve_decay_days
  - services/memory.py::remember() dedup-path self-refresh for short-decay kinds (D-05 fix)
  - tests/test_memory_taste.py regression lock (resolver, map-membership guard, dedup wiring)
affects: [13-04-taste-distill-batch-task]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Kind-gated touch path inside remember() (13-PATTERNS.md option (b)): the dedup branch only calls refresh_memory_expiry when kind is a key in config.MEMORY_DECAY_DAYS_BY_KIND — a shared-path change was explicitly rejected to keep Phase 11 kinds provably untouched."

key-files:
  created: [tests/test_memory_taste.py]
  modified: [services/memory.py]

key-decisions:
  - "Both new branches gate strictly on `kind in config.MEMORY_DECAY_DAYS_BY_KIND` (currently only taste_episode) rather than a separate allowlist, so the resolver map from plan 13-01 is the single source of truth for which kinds get the shorter horizon AND the self-refresh."
  - "bump_memory_hit itself was left completely unchanged — the self-refresh is a second, separate database call (refresh_memory_expiry) made from remember() after bump_memory_hit returns, not a modification to the hit-bump UPDATE statement."
  - "Test coverage went beyond the plan's minimum bar (resolver + map-membership) to also include the integration-style dedup-wiring tests, since test_memory.py already establishes a faithful monkeypatch-the-database-module seam for remember() with no heavy mocking required."

patterns-established:
  - "Kind-aware decay horizon + gated self-refresh is now the reference implementation for any future memory kind that needs a non-default decay tier (Phase 14+ can add new keys to MEMORY_DECAY_DAYS_BY_KIND with zero changes to remember() itself)."

requirements-completed: [TASTE-02]

# Metrics
duration: 12min
completed: 2026-07-02
---

# Phase 13 Plan 03: Memory Service Self-Refresh (D-05 Fix) Summary

**`services/memory.py::remember()` made kind-aware: taste_episode inserts at a 30-day horizon and self-refreshes `expires_at` on every dedup hit, while all five Phase 11 kinds keep the exact 90-day insert horizon and never refresh — closing the D-05 correctness risk flagged in 13-PATTERNS.md.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-02T18:20:00+08:00 (approx, per session continuity)
- **Completed:** 2026-07-02T18:32:00+08:00
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Fixed the D-05 correctness risk: `bump_memory_hit` refreshes `hit_count`/`last_seen_at`/`salience` but never `expires_at`, so a still-true "steady favorite" taste episode that keeps re-distilling to a near-duplicate would silently age out under the new shorter 30-day horizon even while remaining true. `remember()`'s dedup branch now calls `database.refresh_memory_expiry` for taste_episode after bumping.
- Made the insert path kind-aware via `resolve_decay_days(kind, default_days=config.MEMORY_DECAY_DAYS, kind_overrides=config.MEMORY_DECAY_DAYS_BY_KIND)` — taste_episode inserts at `TASTE_DECAY_DAYS` (30), every other kind keeps `MEMORY_DECAY_DAYS` (90), byte-identical to Phase 11.
- Both new code paths are gated strictly on `kind in config.MEMORY_DECAY_DAYS_BY_KIND` — Phase 11 kinds (milestone, late_night, repeat_song, auto_queue_ignored, daily_batch) are absent from that map and hit neither branch.
- `bump_memory_hit` in database.py left completely unchanged (verified — no diff to that function).
- Added `tests/test_memory_taste.py` (10 tests): resolver assertions over the real config, a map-membership guard proving no Phase 11 kind can trigger self-refresh, and integration-style dedup-wiring tests (mirroring `test_memory.py::TestRememberService`'s monkeypatch-the-database-module seam) proving taste_episode dedup calls `refresh_memory_expiry` while milestone dedup does not, plus an insert-horizon assertion.
- Full existing suite remains green: 649 passed, 98 skipped — zero regressions.

## Task Commits

Each task was committed atomically:

1. **Task 1: Make remember() insert horizon and dedup path kind-aware (D-03 + D-05)** - `e35fca0` (feat)
2. **Task 2: Lock the fix with a regression test (taste self-refreshes; Phase 11 unchanged)** - `5e228c1` (test)

**Plan metadata:** _pending — added by the final metadata commit step_

## Files Created/Modified
- `services/memory.py` - Imported `resolve_decay_days` from `logic.taste`; insert path (step 4) now resolves the kind-aware horizon; dedup path (step 3) now self-refreshes `expires_at` for kinds in `MEMORY_DECAY_DAYS_BY_KIND` after `bump_memory_hit`, with an extended debug log noting the refresh.
- `tests/test_memory_taste.py` - New: `TestResolveDecayDaysOverRealConfig` (5 tests), `TestDecayDaysByKindMapGuard` (2 tests), `TestRememberDedupRefreshWiring` (3 tests, integration-style with monkeypatched `database` module functions).

## Decisions Made
- Gate both branches on `kind in config.MEMORY_DECAY_DAYS_BY_KIND` rather than a hardcoded `kind == "taste_episode"` check, so the map from plan 13-01 remains the single source of truth for which kinds get non-default treatment (future kinds slot in with zero `remember()` changes).
- Kept the self-refresh as a fully separate database call after `bump_memory_hit` rather than folding `expires_at` into the existing hit-bump UPDATE — this is exactly what `refresh_memory_expiry` (plan 13-02) was purpose-built for, and it keeps `bump_memory_hit`'s contract (and Phase 11 semantics for every non-taste kind) byte-for-byte unchanged.
- Extended test coverage beyond the plan's stated minimum (resolver + map-membership) with three integration-style dedup-wiring tests, since `tests/test_memory.py`'s `TestRememberService` already established a faithful, lightweight monkeypatch seam for exercising `remember()` without a real DB or heavy mocking — the plan explicitly invited this if the seam existed ("add an integration-style test... If no such faithful seam exists... keep the coverage at the resolver + map-membership assertions").

## Deviations from Plan

None - plan executed exactly as written. The faithful monkeypatch seam described as optional in the plan's Task 2 action did exist in `tests/test_memory.py`, so the fuller integration-style coverage was added as the plan anticipated for that case.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. Zero new package installs.

## Next Phase Readiness
- Plan 13-04 (`bot.py::taste_distill_batch`) can now call `MemoryService.distill_and_remember(..., kind="taste_episode", ...)` (or `remember` directly) with full confidence that taste episodes decay on their own 30-day tier and self-refresh correctly on re-distillation — the D-05 risk flagged at the end of plan 13-01 is fully closed.
- No blockers.

---
*Phase: 13-semantic-music-memory*
*Completed: 2026-07-02*

## Self-Check: PASSED

- FOUND: services/memory.py
- FOUND: tests/test_memory_taste.py
- FOUND: .planning/phases/13-semantic-music-memory/13-03-SUMMARY.md
- FOUND: e35fca0 (Task 1 commit)
- FOUND: 5e228c1 (Task 2 commit)
