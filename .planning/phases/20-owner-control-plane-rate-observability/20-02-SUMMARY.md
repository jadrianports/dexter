---
phase: 20-owner-control-plane-rate-observability
plan: 02
subsystem: auth
tags: [pure-logic, guild-config, owner-control-plane, tdd]

# Dependency graph
requires:
  - phase: 18-per-guild-config-foundation-ci-gate
    provides: "logic/guild_config.py pure decision seam (decide_ambient_channel, is_ambient_channel, AmbientSurface)"
  - phase: 20-owner-control-plane-rate-observability (plan 01)
    provides: "guild_blocklist table + silenced/blocked DB helpers"
provides:
  - "silenced early-return branch in decide_ambient_channel (D-14) -- every ambient surface routed through it (and is_ambient_channel, which dispatches on it) becomes silence-aware for free"
  - "decide_interaction_allowed(*, is_owner, has_guild, blocked, silenced) -> bool -- the pure OWNER-05/D-13 slash-command choke-point predicate"
  - "13 new mock-free tests locking both additions (branch coverage + keyword-only enforcement)"
affects: [20-05-ambient-toctou-recheck, 20-06-command-tree-interaction-check]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Structural safety over remembered safety: silence/block enforcement lives in exactly one pure function per choke point, glue dispatches on the return value (Phase 10 D-02)"
    - "Fail-open key defaults on missing dict keys (config_row.get(key, False/True)) to keep pre-existing rows/mocks byte-identical when a new column/branch is added"

key-files:
  created: []
  modified:
    - logic/guild_config.py
    - tests/test_guild_config_logic.py

key-decisions:
  - "silenced defaults to False via config_row.get('silenced', False) so every existing test/mock that omits the key stays byte-identical (matches the column's DEFAULT false)"
  - "decide_interaction_allowed checks is_owner first, then has_guild, then blocked-or-silenced -- exact D-13 order, keyword-only with no defaults so a missing arg raises TypeError instead of silently defaulting to a lockout or a bypass"
  - "boot-race fail-open (bot.guild_config absent) deliberately NOT modeled in this pure predicate -- documented as a glue concern for 20-06"

patterns-established:
  - "Silenced-branch insertion point: directly after the 'configured' check, before the toggle-column check, mirroring the existing early-return shape"

requirements-completed: [OWNER-05, OWNER-06, OWNER-02]

# Metrics
duration: 12min
completed: 2026-07-13
---

# Phase 20 Plan 02: Silenced Branch + decide_interaction_allowed Predicate Summary

**Added a `silenced` early-return to the pure `decide_ambient_channel` resolver and a new `decide_interaction_allowed` predicate to `logic/guild_config.py`, both keyword-only and discord/datetime/random-free, locked by 13 new mock-free tests.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-13T14:19:42Z
- **Completed:** 2026-07-13T14:31:38Z
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments
- `decide_ambient_channel` now silences a configured, toggled-on guild when `config_row.get("silenced", False)` is true (D-14) -- `is_ambient_channel`, which dispatches on it, inherits this for free with zero code change
- New `decide_interaction_allowed(*, is_owner, has_guild, blocked, silenced) -> bool` gives the OWNER-05 slash-command choke point (D-13) a pure, mock-free-testable predicate: owner always allowed, DM/guild-less always allowed, refuses on blocked-or-silenced otherwise
- Full branch coverage added to `tests/test_guild_config_logic.py`: silenced-true for all three `AmbientSurface` members, silenced-omitted/false backward-compat, `is_ambient_channel` dispatch-through proof, and all six `decide_interaction_allowed` behavior rows plus a required-keyword-only `TypeError` case
- `logic/guild_config.py` remains import-pure (no `discord`/`datetime`/`random`) -- reasserted by both the pre-existing purity self-check and a new one scoped to `decide_interaction_allowed`

## Task Commits

Each task was committed atomically:

1. **Task 1: silenced branch in decide_ambient_channel + decide_interaction_allowed predicate** - `0064910` (feat)
2. **Task 2: mock-free tests for the silenced branch + decide_interaction_allowed** - `2e2447d` (test)

**Plan metadata:** (this commit, docs: complete plan)

## Files Created/Modified
- `logic/guild_config.py` - new `silenced` early-return branch in `decide_ambient_channel` (D-14) + new `decide_interaction_allowed` pure predicate (D-13)
- `tests/test_guild_config_logic.py` - 13 new tests: silenced branch coverage (5), `is_ambient_channel` dispatch-through (1), `decide_interaction_allowed` full coverage (7)

## Decisions Made
- Followed the plan's exact insertion point and branch order (silenced check directly after the `configured` check, before the toggle-column check) -- no deviation
- Followed the plan's exact `decide_interaction_allowed` body order (owner -> DM -> blocked-or-silenced -> allow) -- no deviation

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `logic/guild_config.py` now exposes both pieces of pure logic that 20-05 (ambient TOCTOU re-check) and 20-06 (`DexterCommandTree.interaction_check`) will dispatch on -- neither downstream plan needs to re-derive the silenced/blocked branch logic
- Full suite green: 954 passed, 121 skipped, 0 failed (`pytest tests/ -q`)
- No blockers for 20-03/20-04/20-05/20-06

---
*Phase: 20-owner-control-plane-rate-observability*
*Completed: 2026-07-13*

## Self-Check: PASSED

- FOUND: logic/guild_config.py
- FOUND: tests/test_guild_config_logic.py
- FOUND: .planning/phases/20-owner-control-plane-rate-observability/20-02-SUMMARY.md
- FOUND: 0064910 (feat commit)
- FOUND: 2e2447d (test commit)
- FOUND: 58049db (docs: summary commit)
