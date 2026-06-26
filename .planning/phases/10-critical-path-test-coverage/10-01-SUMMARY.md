---
phase: 10-critical-path-test-coverage
plan: "01"
subsystem: testing
tags: [python, pytest, pure-functions, refactoring, playback, tdd]

# Dependency graph
requires:
  - phase: 09-reliability-ops-hardening
    provides: clear_persisted teardown + queue-persistence restore logic that is now extracted
provides:
  - logic/__init__.py: top-level pure-logic package marker
  - logic/playback.py: TrackEndAction enum + five pure deterministic decision functions
  - tests/test_playback_logic.py: 34 pure-unit tests with full branch + boundary + scar coverage
affects:
  - 10-02  (logic/health.py sibling module — shares logic/ package namespace)
  - 10-03  (logic/roasts.py sibling module — same)
  - 10-04  (regression boot gate — runs pytest -q and checks for new errors)
  - 11-*   (Phase 11 imports from logic/ as established pure-logic TDD seam)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure-logic package (logic/) with pure deterministic functions — no discord/asyncio/RNG/clock imports"
    - "Nondeterminism injected as primitives (D-06): voice-client state, clock readings, RNG all computed in cog glue and passed in"
    - "D-02 true extraction: live cog dispatches on returned decision enum, no mirrored logic"
    - "Named scar regression tests (D-05): findable by exact name, not buried in parametrize sweep"

key-files:
  created:
    - logic/__init__.py
    - logic/playback.py
    - tests/test_playback_logic.py
  modified:
    - cogs/music.py
    - cogs/ai.py
    - services/queue_persistence.py

key-decisions:
  - "logic/ top-level package established as the pure-logic seam Phase 11 imports from (D-01)"
  - "Keyword-only primitives chosen for all function signatures (D-07) — keeps each fn small and cohesive"
  - "queue.current_index set before should_start_playback call so has_track=queue.get_current() is not None evaluates correctly"
  - "smart-rejoin: vc_id presence + channel resolution stay in glue; should_smart_rejoin replaces full inner condition"

patterns-established:
  - "Pure decision fn → cog glue dispatches on returned enum/bool — no inline logic duplication"
  - "Test file style mirrors tests/test_queue.py: one Test* class per fn, test_<scenario>_<expected> names, plain assert, no mocks"
  - "Scar tests: explicit named tests for each known live bug, with docstring citing the incident ref"

requirements-completed: [TEST-01]

# Metrics
duration: 30min
completed: 2026-06-27
---

# Phase 10 Plan 01: Playback Logic Extraction Summary

**Pure playback decision logic extracted from MusicCog/AICog/restore_queues into logic/playback.py with TrackEndAction enum and five deterministic functions; locked by 34 pure-unit tests including three named scar regression tests for finished-song replay, silent auto-queue, and restore index clamp**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-06-27T00:00:00Z
- **Completed:** 2026-06-27T00:30:00Z
- **Tasks:** 3 completed
- **Files modified:** 6 (2 created in logic/, 1 test created, 3 cogs/services wired)

## Accomplishments

- Created `logic/` package with pure `playback.py` module: `TrackEndAction` enum + five deterministic functions (`decide_on_track_end`, `should_start_playback`, `clamp_restore_index`, `should_smart_rejoin`, `exceeds_queue_cap`) — zero discord/asyncio/RNG/clock imports
- Wired all three live decision sites to call the pure functions as single source of truth (D-02): `cogs/music.py _on_track_end` dispatches on `TrackEndAction`, `cogs/ai.py try_auto_queue` uses `should_start_playback`, `services/queue_persistence.py restore_queues` uses all three remaining fns
- Created `tests/test_playback_logic.py` with 34 pure-unit tests: full branch + boundary coverage for every function, plus three mandatory named scar regression tests (D-05)

## Task Commits

1. **Task 1: Create logic/ package + pure playback decision functions** - `32dcb16` (feat)
2. **Task 2: Wire live MusicCog/AICog/restore to pure functions** - `1649913` (feat)
3. **Task 3: Exhaustive pure-unit tests for logic/playback.py** - `1d203cc` (test)

## Files Created/Modified

- `logic/__init__.py` - Empty package marker for top-level pure-logic package (D-01)
- `logic/playback.py` - TrackEndAction enum + five pure deterministic decision functions with full docstrings citing scar refs
- `tests/test_playback_logic.py` - 34 pure-unit tests; Test* class per fn; named scar tests for scars #1, #2, #4; no mocks/clocks/RNG
- `cogs/music.py` - Added `decide_on_track_end` import; `_on_track_end` now dispatches on `TrackEndAction` result
- `cogs/ai.py` - Added `should_start_playback` import; `try_auto_queue` gate wired to the pure function
- `services/queue_persistence.py` - Added imports for all three persistence fns; `restore_queues` uses `exceeds_queue_cap`, `clamp_restore_index`, `should_smart_rejoin`

## Decisions Made

- Keyword-only signatures for all pure functions (D-07) — keeps each function small and cohesive, avoids positional arg confusion
- `queue.current_index` set before `should_start_playback` call in `try_auto_queue` so `has_track=queue.get_current() is not None` evaluates against the newly-queued first track (not a stale index)
- `should_smart_rejoin` replaces the full inner condition in `restore_queues` (not just the `any(not m.bot...)` part); `vc_id` presence + channel resolution remain glue per D-07 guidance

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None — all pure functions imported cleanly, existing queue tests (38) and full suite (387 passed, 64 skipped) remained green.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `logic/` package is ready for Plans 10-02 (`logic/health.py`) and 10-03 (`logic/roasts.py`) to add sibling modules — no `__init__.py` changes needed (Python namespace package semantics)
- Full pytest suite green with 387 passed; no regressions from the wiring changes
- Plan 10-04 boot regression gate (`python bot.py` boot check) has no known new ERROR sources to catch

---
*Phase: 10-critical-path-test-coverage*
*Completed: 2026-06-27*
