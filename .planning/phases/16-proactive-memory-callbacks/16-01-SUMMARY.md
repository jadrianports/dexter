---
phase: 16-proactive-memory-callbacks
plan: 01
subsystem: logic
tags: [pure-logic, decision-gate, config, pytest, tdd]

# Dependency graph
requires:
  - phase: 10-critical-path-test-coverage
    provides: "logic/roasts.py::decide_ambient_roast pure-gate template + logic/ seam convention"
  - phase: 15-rag-reach
    provides: "MEMORY_CALLBACK_CHANCE (0.35) config knob this plan's chance must undercut"
provides:
  - "logic/proactive.py::should_fire_proactive_callback — pure, deterministic firing-decision gate (opt-out -> chance -> daily-cap)"
  - "config.PROACTIVE_CALLBACK_CHANCE (0.10) and config.PROACTIVE_CALLBACK_DAILY_CAP (1) knobs"
  - "tests/test_proactive_logic.py — mock-free boundary coverage + rarity invariant lock"
affects: [16-02, 16-03, 16-04, proactive-memory-callbacks-cog-glue]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Phase 10 pure-logic seam applied to a third cadence: nondeterminism (random roll, daily counter, opt-out flag) computed in glue, passed as primitives to a keyword-only, side-effect-free gate function"

key-files:
  created:
    - logic/proactive.py
    - tests/test_proactive_logic.py
  modified:
    - config.py

key-decisions:
  - "PROACTIVE_CALLBACK_CHANCE set to 0.10 (within the D-02 0.08-0.12 discretion band), strictly below UNPROMPTED_ROAST_CHANCE (0.30) and MEMORY_CALLBACK_CHANCE (0.35); enforced by a dedicated test (T-16-RARITY)"
  - "PROACTIVE_CALLBACK_DAILY_CAP set to 1 (per-user, per-calendar-day); no additional per-user cooldown knob added, per plan instruction"
  - "Gate implements only D-02 steps 1-3 (opt-out, chance, daily-cap); step 4 (recall-floor silent-skip) is explicitly excluded — it requires async I/O and is documented as living in cog glue (plan 16-03)"

patterns-established:
  - "logic/proactive.py mirrors logic/roasts.py exactly: module docstring disclaiming random/datetime/asyncio/discord imports, keyword-only signature, cheapest-gate-first short-circuit ordering, config-defaulted thresholds overridable by keyword"

requirements-completed: [PROACT-01]

# Metrics
duration: 3min
completed: 2026-07-02
---

# Phase 16 Plan 1: Proactive Callback Firing-Decision Gate Summary

**Pure `should_fire_proactive_callback` gate in `logic/proactive.py` (opt-out -> chance -> daily-cap, D-02 ordering) plus two new `config.py` knobs (`PROACTIVE_CALLBACK_CHANCE=0.10`, `PROACTIVE_CALLBACK_DAILY_CAP=1`), locked by 16 mock-free tests including a rarity invariant.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-07-02T19:56:14Z
- **Completed:** 2026-07-02T19:59:00Z
- **Tasks:** 2 completed
- **Files modified:** 3 (1 new logic module, 1 new test file, 1 modified config)

## Accomplishments
- Established the deterministic firing-decision seam for Phase 16's rarest ambient cadence — the pure `logic/proactive.py::should_fire_proactive_callback` gate, mirroring the exact structure/conventions of `logic/roasts.py::decide_ambient_roast` (Phase 10 D-01/D-02/D-03 seam pattern)
- Added the two `config.py` knobs the gate defaults from, with the anti-creepy rarity constraint (`PROACTIVE_CALLBACK_CHANCE` strictly below both existing ambient cadences) documented inline and test-enforced
- Locked the gate math and the config-rarity invariant with 16 mock-free pytest tests (`tests/test_proactive_logic.py`) covering every branch, boundary, and custom-override case from the plan's behavior table

## Task Commits

Each task was committed atomically:

1. **Task 1: Config knobs + pure should_fire_proactive_callback gate** - `f1a7eb1` (feat)
2. **Task 2: Mock-free boundary tests + config rarity invariant** - `8b30d44` (test)

**Plan metadata:** (this commit, docs)

## Files Created/Modified
- `logic/proactive.py` - New pure module: `should_fire_proactive_callback(*, opted_out, chance_roll, daily_count, chance=config.PROACTIVE_CALLBACK_CHANCE, daily_cap=config.PROACTIVE_CALLBACK_DAILY_CAP) -> bool`; short-circuit gate order opt-out -> chance (`>=` fails) -> daily-cap (`>=` fails); no `random`/`datetime`/`asyncio`/`discord` imports
- `config.py` - New `# --- Phase 16: Proactive Memory Callbacks ---` section (after Phase 14 block, before `sanitize_database_url`) adding `PROACTIVE_CALLBACK_CHANCE = 0.10` and `PROACTIVE_CALLBACK_DAILY_CAP = 1`
- `tests/test_proactive_logic.py` - New mock-free test file: `TestShouldFireProactiveCallback` class (opt-out short-circuit, chance boundary, daily-cap boundary, custom-override honoring, gate-ordering checks) plus standalone `test_proactive_chance_is_rarer_than_ambient` (T-16-RARITY invariant, matched by `-k rarer_than_ambient`)

## Decisions Made
- Chosen `PROACTIVE_CALLBACK_CHANCE = 0.10` (mid-band of the D-02 0.08-0.12 discretion range) — comfortably below both 0.30 and 0.35 ambient rates
- Chosen `PROACTIVE_CALLBACK_DAILY_CAP = 1` per D-02's suggested starting value; no belt-and-suspenders per-user cooldown knob added (plan explicitly scoped this out — the daily cap alone is the additive bound D-02 specifies)
- Confirmed via `inspect.signature` that the gate's keyword-only parameter list/defaults match the plan's exact specification before committing

## Deviations from Plan

None - plan executed exactly as written. Both tasks matched their `<action>`/`<behavior>`/`<verify>` specs on the first pass; no auto-fixes needed.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `logic/proactive.py::should_fire_proactive_callback` and both `config.PROACTIVE_CALLBACK_*` knobs are ready for plan 16-02 (opt-out storage: `proactive_opt_out` column + `database.py` getter/setter) and plan 16-03 (the `EventsCog.on_message` glue that computes `chance_roll`/`daily_count`/`opted_out` and dispatches on this gate, plus the D-02 step 4 recall-floor check that intentionally lives outside this pure module).
- Full test suite verified green post-change: 797 passed, 106 skipped, 0 failed (additive-only, no regressions).
- No blockers for 16-02.

---
*Phase: 16-proactive-memory-callbacks*
*Completed: 2026-07-02*

## Self-Check: PASSED

- FOUND: logic/proactive.py
- FOUND: tests/test_proactive_logic.py
- FOUND: .planning/phases/16-proactive-memory-callbacks/16-01-SUMMARY.md
- FOUND: f1a7eb1 (Task 1 commit)
- FOUND: 8b30d44 (Task 2 commit)
- FOUND: 048d571 (SUMMARY commit)
