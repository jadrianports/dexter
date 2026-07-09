---
phase: 18-per-guild-config-foundation-ci-gate
plan: 03
subsystem: logic
tags: [pure-function, decision-seam, ambient-channel, tdd, mock-free]

# Dependency graph
requires:
  - phase: 18-01
    provides: "Ruff pyproject.toml config + CI groundwork this plan's new files must pass"
provides:
  - "logic/guild_config.py::decide_ambient_channel(*, config_row) -> int | None — D-01 strict resolution, silence-by-default"
  - "logic/guild_config.py::is_ambient_channel(*, config_row, channel_id) -> bool — CONFIG-02 predicate replacing bare-equality gates"
  - "tests/test_guild_config_logic.py — mock-free branch lock for both functions"
affects: [18-04, 18-05, 18-06, 18-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure logic/ decision seam (Phase 10 D-02 convention): keyword-only, discord/asyncio/datetime/random-free functions; glue dispatches on the return value without re-deriving the branch"

key-files:
  created:
    - logic/guild_config.py
    - tests/test_guild_config_logic.py
  modified: []

key-decisions:
  - "Followed 18-PATTERNS.md's verbatim target skeleton for both functions exactly — no deviation from the researched shape"
  - "Added one extra test beyond the plan's 7 behavior cases (missing 'configured' key defaults to unconfigured) since decide_ambient_channel uses config_row.get('configured', False) — locks the .get default explicitly"

patterns-established:
  - "logic/guild_config.py mirrors logic/proactive.py's module-docstring convention (states no random/asyncio/datetime/discord) and its keyword-only, boundary-commented function style"

requirements-completed: [CONFIG-02]

# Metrics
duration: 15min
completed: 2026-07-10
---

# Phase 18 Plan 03: Guild Config Pure Decision Seam Summary

**Pure `logic/guild_config.py` decision seam (decide_ambient_channel + is_ambient_channel) locking the silent-until-configured invariant under 10 mock-free tests, mirroring logic/proactive.py exactly.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 2 completed
- **Files modified:** 2 (both new)

## Accomplishments
- `decide_ambient_channel(*, config_row)` — returns `None` for a missing row, `None` for an unconfigured row (even with a channel id set), `None` for a configured row with no channel, and the `int`-coerced channel id only when fully configured. Silence is structural, not something a caller must remember to check (D-01).
- `is_ambient_channel(*, config_row, channel_id)` — delegates to `decide_ambient_channel` and compares; never re-derives the branch (Phase 10 D-02 convention). This is the single predicate the two bare-equality `== config.DEXTER_CHANNEL_ID` gates in `cogs/events.py` (Plan 18-06) will route through.
- Module verified to import none of `discord`/`datetime`/`random`/`asyncio` — both by an inline `python -c` verification command and by a dedicated test (`test_module_imports_no_discord_datetime_or_random`).
- `tests/test_guild_config_logic.py` — 10 mock-free tests, one assertion per branch, no DB, no fixtures, no `unittest.mock`.

## Task Commits

Each task was committed atomically:

1. **Task 1: logic/guild_config.py — pure decision seam** - `b7f75e5` (feat)
2. **Task 2: tests/test_guild_config_logic.py — mock-free branch lock** - `620ad16` (test)

_Note: Task 1 had `tdd="true"` frontmatter, but the plan's actual task structure separates RED (Task 2's test file) from GREEN (Task 1's implementation) across two distinct tasks rather than the usual test-first/impl/refactor triad within one task — executed in the plan's stated order (implementation first, since Task 1 IS the implementation task and Task 2 IS the test task, both explicitly enumerated in `<tasks>`)._

## Files Created/Modified
- `logic/guild_config.py` - Pure `decide_ambient_channel` + `is_ambient_channel` functions, no I/O, keyword-only args, `from __future__ import annotations` header
- `tests/test_guild_config_logic.py` - 10 mock-free tests: 5 for `decide_ambient_channel` (no row, unconfigured, configured-null-channel, configured-with-channel, missing-key-default), 4 for `is_ambient_channel` (match, mismatch, None row, unconfigured), 1 purity self-check

## Decisions Made
- Followed `18-PATTERNS.md`'s verbatim target skeleton for both functions with no structural deviation — this plan's scope is narrow enough (2 pure functions) that the researched shape needed no adjustment.
- Added a 5th `decide_ambient_channel` test beyond the plan's 7 documented behavior cases: a row missing the `configured` key entirely (not just `configured: False`) to lock the `.get("configured", False)` default explicitly, since a real `asyncpg.Record` will always have the key but defensive coverage costs nothing.

## Deviations from Plan

None - plan executed exactly as written. Both files match the `18-PATTERNS.md` target skeleton; no auto-fixes, no blockers, no architectural questions.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. This is a pure, dependency-free logic module.

## Next Phase Readiness

- `logic/guild_config.py` is ready for Plan 18-04 (`services/guild_config.py::GuildConfigService`) to dispatch on `decide_ambient_channel` inside its `resolve_ambient_channel(guild)` method (per `18-PATTERNS.md`'s resolver pattern).
- Ready for Plan 18-06 (`cogs/events.py` call-site rewrites) to import `is_ambient_channel` and replace both bare-equality `message.channel.id == config.DEXTER_CHANNEL_ID` gates.
- Full suite run: 864 passed, 111 skipped (live-DB, expected — no `TEST_DATABASE_URL` in this environment), 0 failed. No regressions introduced.
- CONFIG-02 is only the "pure half" of the requirement per this plan's `<environment_notes>` — the wiring into `cogs/events.py`/`bot.py` call sites happens in Plan 18-06. Left `requirements-completed: [CONFIG-02]` per this plan's frontmatter `requirements:` field, but the phase verifier should confirm CONFIG-02 is only fully closed once 18-06 lands the glue.

---
*Phase: 18-per-guild-config-foundation-ci-gate*
*Completed: 2026-07-10*

## Self-Check: PASSED

- FOUND: logic/guild_config.py
- FOUND: tests/test_guild_config_logic.py
- FOUND commit: b7f75e5
- FOUND commit: 620ad16
