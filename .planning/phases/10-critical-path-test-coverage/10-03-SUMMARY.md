---
phase: 10-critical-path-test-coverage
plan: 03
subsystem: testing
tags: [pure-functions, ambient-roast, unit-tests, tdd, events]

# Dependency graph
requires:
  - phase: 10-critical-path-test-coverage
    provides: logic/ package (logic/__init__.py) established by 10-01
  - phase: 03-alive
    provides: EventsCog ambient-roast trigger nest and late-night gating being locked
provides:
  - logic/roasts.py pure functions (decide_ambient_roast, cooldown_elapsed, RoastScenario)
  - tests/test_roast_logic.py — 25 pure-unit tests, full branch + boundary coverage
  - D-02 true extraction: cogs/events.py on_voice_state_update + _check_ambient_cooldown wired to pure functions
affects:
  - phase-11-rag
  - any future change to ambient-roast gating, cooldown, or late-night eligibility
  - 10-04 TEST-04 regression gate

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure-function extraction with keyword-only primitives (same discipline as logic/playback.py)"
    - "D-02 true extraction: live glue calls pure fn as single source of truth, no duplicated gating logic"
    - "D-06 determinism seam: glue computes RNG rolls + ZoneInfo local_hour + cooldown delta, pure fn receives primitives"

key-files:
  created:
    - logic/roasts.py
    - tests/test_roast_logic.py
  modified:
    - cogs/events.py

key-decisions:
  - "D-02 true extraction applied: on_voice_state_update dispatches on RoastScenario from decide_ambient_roast; _check_ambient_cooldown returns cooldown_elapsed(now-last, ceiling) — no duplicated gating logic left in callers"
  - "decide_ambient_roast/cooldown_elapsed use injected primitives (two rolls, local_hour, cooldown delta) — random/asyncio/datetime stay in glue (D-06)"
  - "logic/roasts.py composes personality.roasts.is_late_night rather than re-implementing the hour bound check"

patterns-established:
  - "logic/roasts.py: pure — no random/asyncio/datetime/discord imports; rolls + clock deltas injected"
  - "test_roast_logic.py: late-night cases pick hours from config.LATE_NIGHT_HOURS, not magic numbers — tests track config"

requirements-completed: [TEST-03]

# Metrics
duration: ~25min (two dispatch attempts; first two stalled on API stream errors, work completed + closed out by orchestrator)
completed: 2026-06-27
---

# Phase 10 Plan 03: Roast Logic Extraction Summary

**Pure decide_ambient_roast + cooldown_elapsed extracted to logic/roasts.py with 25 mock-free unit tests locking the chance/cooldown/late-night gating boundaries (TEST-03)**

## Performance

- **Duration:** ~25 min (two executor dispatches stalled mid-stream on API errors; the actual code/tests landed and the orchestrator completed the mechanical close-out — commit of the test file, SUMMARY, tracking)
- **Completed:** 2026-06-27
- **Tasks:** 2 (Task 1: extraction + wiring; Task 2: TDD tests)
- **Files modified:** 3 (logic/roasts.py created, tests/test_roast_logic.py created, cogs/events.py modified)

## Accomplishments
- Extracted the nested ambient-roast trigger logic in `on_voice_state_update` (chance roll → per-user cooldown → late-night eligibility → second late-night roll → join/leave scenario) into a deterministic `decide_ambient_roast(...)` returning a `RoastScenario` enum
- Extracted the `_check_ambient_cooldown` clock comparison into pure `cooldown_elapsed(seconds_since_last, ceiling_seconds)` (mirrors the live `>=` so exactly-at-ceiling is allowed)
- Wired `cogs/events.py` (D-02 true extraction): glue computes the two `random.random()` rolls, the ZoneInfo `local_hour`, and the cooldown delta, then dispatches on the returned `RoastScenario`; Gemini generation, channel resolution, `channel.send`, `_mark_ambient_roast`, the bot-move early-return, and the `member.bot` guard all stay untested-by-design glue
- Created `tests/test_roast_logic.py` with 25 pure-unit tests covering every chance/cooldown/late-night/event branch and boundary (chance-roll == threshold, cooldown delta == ceiling, late-night low/high hour boundaries, both late-night second-roll outcomes, JOIN/LATE_NIGHT/LEAVE + NONE counterparts, custom-threshold overrides); no mocks, no clocks, no RNG

## Task Commits

Each task was committed atomically:

1. **Task 1: Create logic/roasts.py + wire EventsCog (D-02)** - `a928471` (feat)
2. **Task 2: Pure-unit tests for the ambient-roast gating decision** - `d7f9eff` (test)

**Plan metadata:** (follows in final commit)

## Files Created/Modified
- `logic/roasts.py` — `RoastScenario` enum (NONE/JOIN/LATE_NIGHT/LEAVE) + `cooldown_elapsed` + `decide_ambient_roast`; keyword-only primitives, composes `personality.roasts.is_late_night`; no random/asyncio/datetime/discord imports
- `tests/test_roast_logic.py` — 25 tests: `TestCooldownElapsed` (5) + `TestDecideAmbientRoast` (20); mock/clock/RNG-free; late-night hours sourced from `config.LATE_NIGHT_HOURS`
- `cogs/events.py` — `on_voice_state_update` and `_check_ambient_cooldown` now call the pure functions as the single source of truth

## Decisions Made
- Pure functions take the RNG rolls and clock delta as injected parameters (D-06 determinism seam) so the gating boundaries are exhaustively testable without patching `random` or the event loop clock
- Composed the existing `personality.roasts.is_late_night(hour)` rather than re-implementing the late-night hour bound, keeping a single definition of the late-night window

## Deviations from Plan

None on the code itself — plan executed as written. Process note: the executor subagent stalled twice on transient API stream errors (first attempt before any write; second after Task 1 was committed and the test file written + passing but before the close-out commit). The orchestrator verified all plan acceptance criteria against the live tree (imports, wiring greps, purity greps, boundary assertions, full suite green) and completed the remaining mechanical steps — committing the passing test file, writing this SUMMARY, and updating tracking. No code was authored by the orchestrator.

## Issues Encountered

Two transient `API Error: Response stalled mid-stream` failures terminated the executor subagent before it emitted a completion signal. Resolved via the workflow's completion-signal fallback: spot-check filesystem + git state, verify acceptance criteria, finish close-out. All 25 new tests and the full suite (436 passed, 64 skipped) are green.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `logic/roasts.py` joins `logic/playback.py` and `logic/health.py` in the established pure-logic TDD seam
- Full suite (436 passed, 64 skipped) green — no regressions; Wave 1 (10-01/10-02/10-03) complete
- 10-04 (TEST-04 regression gate) can now run as Wave 2

---
*Phase: 10-critical-path-test-coverage*
*Completed: 2026-06-27*
