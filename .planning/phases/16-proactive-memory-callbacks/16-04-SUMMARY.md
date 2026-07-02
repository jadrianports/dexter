---
phase: 16-proactive-memory-callbacks
plan: 04
subsystem: discord-commands
tags: [discord.py, app_commands, opt-out, proactive-callbacks]

# Dependency graph
requires:
  - phase: 16-proactive-memory-callbacks (plan 02)
    provides: database.set_proactive_opt_out(pool, *, user_id, opted_out) upsert setter + proactive_opt_out column
provides:
  - "/memory callbacks on|off subcommand — self-scoped, ephemeral, Choice-constrained opt-out toggle"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Third self-scoped subcommand under an existing app_commands.Group, following the exact V4 self-scoping + ephemeral + in-character-copy convention of memory_view/memory_forget"
    - "Structural source-inspection test proving a command touches zero rows of an adjacent, more-destructive data store (mirrors T-15-12 pattern from 16-02)"

key-files:
  created: []
  modified: [cogs/memory.py, tests/test_memory_command.py]

key-decisions:
  - "No deviations from plan prose — the action/behavior/verify sections were unambiguous and directly implementable as written."

patterns-established:
  - "Opt-out/pause controls for a data-adjacent surface get a structural source-inspection guard (no reference to the destructive-helper name or the table it touches) proving they are provably distinct from the corresponding hard-delete command."

requirements-completed: [PROACT-02]

# Metrics
duration: 4min
completed: 2026-07-03
---

# Phase 16 Plan 04: /memory callbacks Opt-Out Command Summary

**Self-scoped, ephemeral `/memory callbacks on|off` subcommand under the existing `/memory` group that flips only `user_profiles.proactive_opt_out` via `database.set_proactive_opt_out`, provably touching zero memory rows.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-07-03T04:26Z (approx, first read after 16-03 commit)
- **Completed:** 2026-07-03T04:30Z
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments
- `MemoryCog.memory_callbacks` added as a third subcommand under the `/memory` `app_commands.Group`, with `app_commands.Choice`-constrained `on`/`off` input (no free-text parsing surface)
- Callback signature locked to exactly `["self", "interaction", "setting"]` — no `target`/`user` param (V4 self-scoping, matching `memory_view`/`memory_forget`)
- Body calls `database.set_proactive_opt_out(self.bot.pool, user_id=str(interaction.user.id), opted_out=...)` and replies ephemerally with the D-03 in-character lines
- `MemoryCog` module docstring and Security block extended with T-16-02/T-16-03/T-16-08 notes documenting the self-scoping, Choice-constraint, and zero-memory-row guarantees
- `tests/test_memory_command.py` extended with 4 new tests (off/on round-trip, ephemeral assertion, signature guard, source-inspection distinctness-from-forget) plus the existing `test_memory_subcommands_have_no_target_param` extended to cover the new subcommand

## Task Commits

Each task was committed atomically:

1. **Task 1: /memory callbacks on|off subcommand** - `a1a303c` (feat)
2. **Task 2: Callbacks subcommand tests + extended self-scoping guard** - `3f3cc9f` (test)

**Plan metadata:** (this commit, following SUMMARY write)

## Files Created/Modified
- `cogs/memory.py` - Added `memory_callbacks` subcommand (Task 1's `action` verbatim: `Choice`-constrained setting, self-scoped body, D-03 in-character ephemeral replies); extended module docstring + `MemoryCog` class docstring with the T-16-02/T-16-03/T-16-08 security notes
- `tests/test_memory_command.py` - Added `_make_choice` helper + `test_memory_callbacks_off_then_on`, `test_memory_callbacks_response_ephemeral`, `test_memory_callbacks_is_self_scoped`, `test_memory_callbacks_touches_no_memories`; extended `test_memory_subcommands_have_no_target_param` to assert the `memory_callbacks` signature too

## Decisions Made
None beyond what the plan specified — the `<action>`, `<behavior>`, and `<verify>` sections fully determined the implementation (exact subcommand decorator shape, exact signature, exact copy strings, exact source-inspection assertions), leaving no ambiguity to resolve.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- PROACT-02 is now fully implemented end-to-end: storage (16-02), events-glue opt-out read (16-03), and this user-facing toggle (16-04).
- Phase 16 (proactive-memory-callbacks) is code-complete across all 4 plans. Full test suite green (814 passed, 108 skipped).
- Two live-Discord feel/UX checks remain parked behind the host per 16-VALIDATION.md §Manual-Only (unrelated to this plan's code correctness).
- No blockers for phase close / `/gsd-verify-phase 16`.

---
*Phase: 16-proactive-memory-callbacks*
*Completed: 2026-07-03*

## Self-Check: PASSED

- FOUND: cogs/memory.py
- FOUND: tests/test_memory_command.py
- FOUND: .planning/phases/16-proactive-memory-callbacks/16-04-SUMMARY.md
- FOUND: a1a303c (feat commit)
- FOUND: 3f3cc9f (test commit)
- FOUND: 92da531 (docs: summary commit)
