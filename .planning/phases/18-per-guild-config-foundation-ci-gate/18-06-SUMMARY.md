---
phase: 18-per-guild-config-foundation-ci-gate
plan: 06
subsystem: bot-glue
tags: [discord.py, guild-config, ambient-cadence, refactor, testing]

# Dependency graph
requires:
  - phase: 18-per-guild-config-foundation-ci-gate (18-03/18-04/18-05)
    provides: "logic/guild_config.py::is_ambient_channel, services/guild_config.py::GuildConfigService (sync resolve_ambient_channel + cache-only get), bot.guild_config wired at boot"
provides:
  - "cogs/events.py fully consolidated onto the Phase 18 guild_config seam — zero DEXTER_CHANNEL_ID references remain in cogs/"
  - "all 4 ambient surfaces in events.py (3 voice sites + 2 on_message gates) are structurally silent for an unconfigured guild"
  - "regression test coverage proving the new seam (including a new CONFIG-04 unconfigured-guild silent test)"
affects: [19-per-guild-setup-flow, 20-kill-switch-and-blocklist]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "on_message ambient gates dispatch via is_ambient_channel(config_row=self.bot.guild_config.get(guild_id), channel_id=...) instead of re-deriving config.DEXTER_CHANNEL_ID equality"
    - "voice-event call sites call the now-synchronous self.bot.guild_config.resolve_ambient_channel(guild) with await dropped"

key-files:
  created: []
  modified:
    - cogs/events.py
    - tests/test_proactive_events.py

key-decisions:
  - "Kept the vision-roast gate and the proactive-callback gate as two independent conditionals (not merged) per plan instruction and the Phase 17 comment"
  - "Test fix used the config_row mock approach (bot.guild_config.get returning a dict) rather than patching is_ambient_channel directly, so tests exercise the real predicate/decide_ambient_channel logic, not a stubbed-out always-True/False"
  - "Added one new test (test_unconfigured_guild_skips) beyond the plan's minimum ask, directly proving CONFIG-04 at the on_message layer"

patterns-established:
  - "Fake-bot test fixtures needing guild_config now attach a MagicMock().get(...) returning a plain dict row, matching the Mapping contract logic/guild_config.py expects"

requirements-completed: [CONFIG-02, CONFIG-04]

# Metrics
duration: 20min
completed: 2026-07-10
---

# Phase 18 Plan 06: Consolidate events.py ambient surfaces onto guild_config seam Summary

**Deleted the duplicate `_get_ambient_channel` fallback in `cogs/events.py`, repointed its 3 voice-event call sites at the synchronous `self.bot.guild_config.resolve_ambient_channel`, and replaced both `on_message` bare-equality `config.DEXTER_CHANNEL_ID` gates with the pure `is_ambient_channel` predicate — an unconfigured guild is now structurally silent on all four events.py ambient surfaces, and `DEXTER_CHANNEL_ID` no longer appears anywhere under `cogs/`.**

## Performance

- **Duration:** ~20 min (includes full-suite pytest run, ~7 min)
- **Started:** 2026-07-09T21:46:00Z (approx, following prior plan 18-05 commit)
- **Completed:** 2026-07-09T22:06:00Z
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments
- `cogs/events.py::_get_ambient_channel` deleted (its body already relocated to `GuildConfigService.resolve_announce_channel` in 18-04); 3 voice-event call sites (bot-moved complaint, voice-join roast, voice-leave roast) now call the synchronous `self.bot.guild_config.resolve_ambient_channel(...)` with `await` dropped
- Both `on_message` ambient gates (proactive-callback dispatch, vision-roast dispatch) now route through `is_ambient_channel(config_row=self.bot.guild_config.get(message.guild.id), channel_id=message.channel.id)` instead of the bare `config.DEXTER_CHANNEL_ID` equality check; the vision gate keeps its `message.attachments` condition and remains a separate, unmerged conditional
- `grep -rn DEXTER_CHANNEL_ID cogs/` returns nothing; `cogs/events.py` parses cleanly
- `tests/test_proactive_events.py` updated: `_make_bot()` now attaches a `guild_config` mock whose `.get()` returns a configured row by default; `test_non_designated_channel_skips` / `test_designated_channel_triggers` now drive real `is_ambient_channel` behavior via that mocked row (no longer patching the retired env var); added `test_unconfigured_guild_skips` proving CONFIG-04 directly at the `on_message` layer
- Full sweep of `tests/*.py` confirms zero references to `DEXTER_CHANNEL_ID`, `_get_ambient_channel`, or `_resolve_dexter_channel`
- Full suite: 874 passed, 111 skipped, 0 failed (baseline preserved)

## Task Commits

1. **Task 1: Delete `_get_ambient_channel`; repoint 3 voice sites; rewrite 2 on_message gates** - `3ab3942` (refactor)
2. **Task 2: Update regression tests to patch the new seam; sweep test files** - `fb2e1ba` (test)

**Plan metadata:** (this commit, pending)

## Files Created/Modified
- `cogs/events.py` - deleted duplicate fallback resolver; 3 voice sites + 2 on_message gates routed through the Phase 18 guild_config seam
- `tests/test_proactive_events.py` - patch targets updated to the new seam; new CONFIG-04 unconfigured-guild test added

## Decisions Made
- Chose the config-row-mock approach over patching `is_ambient_channel` directly for the two updated tests (and the new one) — this exercises the real `is_ambient_channel`/`decide_ambient_channel` decision logic rather than trivially stubbing the predicate to always return True/False, satisfying the plan's "must still exercise real behavior" acceptance criterion.
- Left `import config` in `cogs/events.py` untouched — the module still references `config.STREAK_TIMEZONE`, `config.MEMORY_CALLBACK_CHANCE`, `config.MEMORY_SALIENCE_BASE_WEIGHTS`, `config.VISION_MIME_ALLOWLIST`, `config.MAX_VISION_IMAGE_BYTES`, and `config.VISION_ROAST_COOLDOWN_SECONDS` — so removing the import per the plan's conditional instruction was correctly a no-op.

## Deviations from Plan

None - plan executed exactly as written. One additive test (`test_unconfigured_guild_skips`) was added beyond the plan's explicit task list to directly lock CONFIG-04 at the `on_message` gate layer; this is coverage strengthening, not a deviation from any must-have.

## Requirements Note (CONFIG-02 / CONFIG-04)

Per the environment notes, CONFIG-02 and CONFIG-04 are shared across sibling plans in this phase (18-03/18-04/18-05 already lay the pure-logic and service-tier groundwork these requirements describe). This plan is the piece that finishes wiring `cogs/events.py` onto that seam — marking both IDs complete here reflects that the `cogs/events.py` surface (the last events.py-side gap) is now closed; the phase verifier should confirm no other plan's files still need this requirement marked.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `cogs/events.py` fully off the `DEXTER_CHANNEL_ID` env var for all ambient dispatch; an unconfigured guild is silent by construction on voice-join/leave/move roasts, proactive callbacks, and vision roasts.
- No known blockers for the remaining Phase 18 plans (bot.py-side wiring already landed in 18-05; this plan only touched `cogs/events.py` and its test file per its declared scope).

---
*Phase: 18-per-guild-config-foundation-ci-gate*
*Completed: 2026-07-10*

## Self-Check: PASSED
