---
phase: 10-critical-path-test-coverage
plan: 02
subsystem: testing
tags: [pure-functions, health-check, unit-tests, tdd, reliability]

# Dependency graph
requires:
  - phase: 10-critical-path-test-coverage
    provides: logic/ package (logic/__init__.py, logic/playback.py) established by 10-01
  - phase: 09-reliability-ops-hardening
    provides: REL-01 degraded-reason strings and /health endpoint behavior being locked
provides:
  - logic/health.py pure functions (determine_health_status, assemble_degraded_reasons)
  - tests/test_health_logic.py — 24 pure-unit tests with REL-01 named scar test
  - D-02 true extraction: bot.py /health and cogs/ops.py wired to pure functions
affects:
  - phase-11-rag
  - any future change to /health status logic or degraded-reason assembly

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure-function extraction with keyword-only primitives (same discipline as logic/playback.py)"
    - "D-02 true extraction: live glue calls pure fn as single source of truth, no duplicated logic"
    - "D-06 determinism seam: async glue computes db_ok/gateway_ready/etc., pure fn receives primitives"

key-files:
  created:
    - logic/health.py
    - tests/test_health_logic.py
  modified:
    - bot.py
    - cogs/ops.py

key-decisions:
  - "D-02 true extraction applied: bot.py /health and cogs/ops.py gather_bot_metrics each call the pure function as the single source of truth — no inline mapping/append logic left in callers"
  - "assemble_degraded_reasons uses keyword-only params matching logic/playback.py style (D-06/D-07)"
  - "pool_present and db_ok computed in async glue, passed as primitives to pure fn — async DB probe stays untested-by-design"

patterns-established:
  - "logic/health.py: all functions keyword-only, no asyncio/discord imports, json stdlib only"
  - "test_health_logic.py: named scar test test_degraded_returns_503_when_strict loops over ALL_CRITICAL_REASONS constant — findable, not buried in parametrize"

requirements-completed: [TEST-02]

# Metrics
duration: 12min
completed: 2026-06-27
---

# Phase 10 Plan 02: Health Logic Extraction Summary

**Pure determine_health_status + assemble_degraded_reasons extracted to logic/health.py with 24 mock-free unit tests locking the REL-01 degraded-503 path**

## Performance

- **Duration:** 12 min
- **Started:** 2026-06-27T00:00:00Z
- **Completed:** 2026-06-27T00:12:00Z
- **Tasks:** 2 (Task 1: extraction + wiring; Task 2: TDD tests)
- **Files modified:** 4 (logic/health.py created, tests/test_health_logic.py created, bot.py modified, cogs/ops.py modified)

## Accomplishments
- Extracted inline /health status decision (bot.py:225-230) and scattered `degraded_reasons.append()` calls (cogs/ops.py:111-124) into two pure, importable functions in `logic/health.py`
- Wired `bot.py` `/health` handler to call `determine_health_status` as the single source of truth (D-02); removed 4 inline lines
- Wired `cogs/ops.py` `gather_bot_metrics` to call `assemble_degraded_reasons` after the async DB probe; removed 4 scattered `.append()` calls; async probe stays glue
- Created `tests/test_health_logic.py` with 24 pure-unit tests covering the full D-03 status matrix and reason-assembly branches; named scar test `test_degraded_returns_503_when_strict` exercises all four REL-01 critical reasons

## Task Commits

Each task was committed atomically:

1. **Task 1: Create logic/health.py + wire bot.py /health and OpsCog** - `77fffa6` (feat)
2. **Task 2: Pure-unit tests for health status matrix + REL-01 degraded scar** - `feb8137` (test)

**Plan metadata:** (follows in final commit)

## Files Created/Modified
- `logic/health.py` — Two pure functions: `assemble_degraded_reasons` (keyword-only bool params → list[str]) and `determine_health_status` (reasons + strict → tuple[int, str]); no asyncio/discord imports
- `tests/test_health_logic.py` — 24 tests: TestDetermineHealthStatus (11) + TestAssembleDegradedReasons (13); named scar test; mock/clock/RNG-free
- `bot.py` — Added `from logic.health import determine_health_status`; replaced inline if/else status mapping with `status, body = determine_health_status(reasons, ...)`
- `cogs/ops.py` — Added `from logic.health import assemble_degraded_reasons`; replaced 4 scattered `.append()` calls with single `assemble_degraded_reasons(...)` call after async DB probe

## Decisions Made
- Maintained keyword-only signature for both functions to match `logic/playback.py` style (D-07)
- Import at module top in `bot.py` (not function-scope) since `logic.health` has no circular import risk; the existing function-scope `from cogs.ops import gather_bot_metrics` stays as-is (circular-import avoidance for that one was the original reason)
- `pool_present` variable introduced in `gather_bot_metrics` glue to capture the result of `pool is not None` before the if/else — passed into pure fn without touching the probe logic

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None. All 96 tests passed on first run after implementation.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `logic/health.py` is ready for Phase 11 to import from as part of the established pure-logic TDD seam
- Full suite (96 tests) green; no regressions
- 10-03 (logic/roasts.py) is the remaining Wave 1 plan and has zero file overlap with this plan

---
*Phase: 10-critical-path-test-coverage*
*Completed: 2026-06-27*
