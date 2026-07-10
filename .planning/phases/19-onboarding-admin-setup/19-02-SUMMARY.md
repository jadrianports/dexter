---
phase: 19-onboarding-admin-setup
plan: 02
subsystem: bot-behavior
tags: [discord-py, enum, ambient-surfaces, guild-config, structural-safety]

# Dependency graph
requires:
  - phase: 19-onboarding-admin-setup
    provides: "plan 01 — ambient_roasts_enabled/vision_roasts_enabled columns + configure_guild_first_time/redesignate_guild_channel/set_ambient_roasts_enabled/set_vision_roasts_enabled/insert_guild_config_if_absent database.py helpers"
provides:
  - "AmbientSurface enum (ROAST, VISION, PRESENCE) — required keyword-only on decide_ambient_channel/is_ambient_channel/resolve_ambient_channel, no default"
  - "surface-keyed decide_ambient_channel/is_ambient_channel (logic/guild_config.py) gating ROAST+PRESENCE on ambient_roasts_enabled and VISION on vision_roasts_enabled"
  - "should_welcome_guild(inserted_row) — D-14 insert-vs-conflict welcome signal, never derivable from a cache miss"
  - "surface-keyed GuildConfigService.resolve_ambient_channel; GuildConfigService.home_guild_id (D-24)"
  - "GuildConfigService.configure_guild_first_time / redesignate_guild_channel / set_ambient_roasts_enabled / set_vision_roasts_enabled — write-then-push-invalidate methods for /setup (19-04)"
  - "cogs/events.py on_message: reaction gate (D-21, closes CONFIG-04 hole) + independent roast_channel_ok/vision_channel_ok surface split (D-22); all three voice-roast resolves declare surface=ROAST"
affects: [19-03, 19-04, 20-owner-control-plane-rate-observability]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Required keyword-only enum threading (no default) as a structural anti-forgetting device — a call site cannot resolve/gate an ambient surface without declaring which one it is"
    - "Two independently-computed gate booleans (roast_channel_ok / vision_channel_ok) replacing a single shared boolean once two toggle columns can disagree"

key-files:
  created:
    - tests/test_guild_lifecycle_logic.py
  modified:
    - logic/guild_config.py
    - services/guild_config.py
    - cogs/events.py
    - tests/test_guild_config_logic.py
    - tests/test_guild_config_service.py
    - tests/test_proactive_events.py

key-decisions:
  - "AmbientSurface is a plain enum.Enum (ROAST/VISION/PRESENCE) with no default anywhere it's threaded — a TypeError on a missing surface= is the intended failure mode for a future call site that forgets to declare itself (D-22)"
  - "Missing toggle key defaults to True (fail-open) inside decide_ambient_channel, matching the guild_config column DEFAULT true — a pre-Phase-19 cached row (no toggle keys yet) behaves identically to today until the next load_all()"
  - "home_guild_id is set unconditionally at the end of seed_home_guild, even on ON CONFLICT DO NOTHING — the seed still resolved which guild is home, independent of whether a new row was actually inserted (D-24)"
  - "resolve_ambient_channel/GuildConfigService write methods do not re-derive the toggle/configured branch — they dispatch on decide_ambient_channel's return value and push the DB helper's own RETURNING row into the cache (Phase 10 D-02 convention, extended)"
  - "on_message's single in_ambient_channel boolean (Phase 18 WR-02) is retired in favor of two independent booleans now that ambient_roasts_enabled and vision_roasts_enabled can disagree per guild"

patterns-established:
  - "Required-keyword enum threading with no default (AmbientSurface) as the structural pattern for any future ambient-surface predicate/resolver"

requirements-completed: [ONBOARD-01, ONBOARD-04]

# Metrics
duration: 20min
completed: 2026-07-10
---

# Phase 19 Plan 02: Surface-Keyed Ambient Gating + Reaction Hole Closure Summary

**`AmbientSurface` enum threaded as a required keyword-only argument through `decide_ambient_channel`/`is_ambient_channel`/`resolve_ambient_channel` so `ambient_roasts_enabled` and `vision_roasts_enabled` can independently silence ROAST/PRESENCE vs VISION, plus a closed CONFIG-04 reaction-gating hole in `on_message`.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-10T11:42:59Z
- **Tasks:** 3
- **Files modified:** 6 (1 new: tests/test_guild_lifecycle_logic.py)

## Accomplishments
- Added `AmbientSurface(enum.Enum)` (`ROAST`, `VISION`, `PRESENCE`) to `logic/guild_config.py`; `decide_ambient_channel`/`is_ambient_channel` now require `surface=` with no default (`TypeError` if omitted), gating `ambient_roasts_enabled` for ROAST/PRESENCE and `vision_roasts_enabled` for VISION, with a missing toggle key defaulting to `True` (fail-open, matches the column `DEFAULT true`). Added `should_welcome_guild(inserted_row)` — a deliberately trivial wrapper naming the D-14 rule (welcome iff the INSERT actually inserted, never a cache-miss derivation).
- Extended `services/guild_config.py`: `resolve_ambient_channel` now requires `surface=` and dispatches on `decide_ambient_channel(config_row=row, surface=surface)` without re-deriving the toggle branch; added `home_guild_id` (set unconditionally in `seed_home_guild`, even on `ON CONFLICT DO NOTHING`); added four write-then-push-invalidate methods (`configure_guild_first_time`, `redesignate_guild_channel`, `set_ambient_roasts_enabled`, `set_vision_roasts_enabled`) that each call the matching 19-01 `database.py` helper and refresh the cache with its returned Record — the single seam `/setup` (19-04) will call.
- Closed the CONFIG-04 reaction hole in `cogs/events.py::on_message` (D-21): `_handle_message_reactions` now fires only inside `if roast_channel_ok:`, not unconditionally. Retired the shared `in_ambient_channel` boolean (Phase 18 WR-02) in favor of two independently-computed surface-keyed booleans, `roast_channel_ok` and `vision_channel_ok` (D-22), since the two toggle columns can now disagree. All three voice-roast `resolve_ambient_channel` call sites (bot-moved, voice-join, voice-leave) declare `surface=AmbientSurface.ROAST`.

## Task Commits

Each task was committed atomically:

1. **Task 1: AmbientSurface + surface-keyed pure functions + should_welcome_guild (mock-free)** - `ea42407` (feat)
2. **Task 2: Surface passthrough + home_guild_id + toggle/channel write methods on GuildConfigService** - `8d134da` (feat)
3. **Task 3: Reaction gate + per-surface split in on_message; voice resolves take surface=ROAST** - `6f645be` (feat)

## Files Created/Modified
- `logic/guild_config.py` - `AmbientSurface` enum; surface-keyed `decide_ambient_channel`/`is_ambient_channel` (required kwarg, no default); new `should_welcome_guild`
- `services/guild_config.py` - surface-keyed `resolve_ambient_channel`; `home_guild_id` attribute; four write+push-invalidate methods
- `cogs/events.py` - `AmbientSurface` import; reaction gate under `roast_channel_ok`; `roast_channel_ok`/`vision_channel_ok` split replacing `in_ambient_channel`; `surface=AmbientSurface.ROAST` on all three voice-roast resolves
- `tests/test_guild_config_logic.py` - `surface=` on every existing call + new toggle-off/toggle-independence coverage + required-kwarg TypeError tests
- `tests/test_guild_lifecycle_logic.py` - new file: mock-free `should_welcome_guild` coverage including the D-14 fail-closed scar
- `tests/test_guild_config_service.py` - `surface=AmbientSurface.ROAST` on every `resolve_ambient_channel` call; new VISION-surface case, toggle-isolation case, `home_guild_id` before/after test
- `tests/test_proactive_events.py` - `_make_bot`'s mocked row carries both toggle keys; new reaction-gate firing/suppression tests and a ROAST/VISION independent-toggle test

## Decisions Made
- `AmbientSurface` has no default anywhere it's threaded — the intended failure mode for a future call site that forgets `surface=` is a loud `TypeError`, not a silent fallback to the wrong gate (D-22).
- A missing toggle key on a cached row defaults to `True` (fail-open) inside `decide_ambient_channel`, so a guild whose cache was populated before this plan's toggle columns existed keeps behaving exactly as before until the next `load_all()` refreshes it with the real column values.
- `home_guild_id` is set unconditionally at the end of `seed_home_guild`, even when the underlying insert is a no-op (`ON CONFLICT DO NOTHING` returns `None`) — the seed call still identifies which guild is home regardless of whether a new row was written (D-24).
- The service's write methods (`configure_guild_first_time` etc.) delegate entirely to the matching `database.py` helper and push its returned `Record` into the cache — they never re-derive the toggle/configured decision, keeping the Phase 10 D-02 "glue dispatches, logic decides" convention intact for the new write paths too.

## Deviations from Plan

None — plan executed exactly as written. Test file additions (toggle-off coverage, `home_guild_id` test, reaction-gate tests) match the plan's `<action>` instructions precisely; no unplanned production-code changes were needed.

## Issues Encountered
- One self-inflicted ruff-format wrap: `services/guild_config.py`'s `resolve_ambient_channel` signature initially exceeded a comfortable line length after adding `*, surface: AmbientSurface`; `ruff format` auto-wrapped it and the file was re-verified clean. No behavior change.
- One structural-check near-miss: an in-code comment in `cogs/events.py::on_message` referenced the retired identifier `in_ambient_channel` by name (documentation only, not a variable reference), which would have failed the plan's own `'in_ambient_channel' not in s` structural grep. Reworded the comment to describe the retired shape without using the literal identifier — no functional change.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Plan 03 (bot.py `on_guild_join`/`on_guild_remove`/boot-backfill glue, and the deferred `bot.py`/`cogs/music.py` `resolve_ambient_channel` call sites that now require `surface=`) can proceed directly: `should_welcome_guild`, the surface-keyed resolver, and `home_guild_id` are all in place and test-locked.
- Plan 04 (`cogs/admin.py` `/setup` command surface) can call `GuildConfigService.configure_guild_first_time`/`redesignate_guild_channel`/`set_ambient_roasts_enabled`/`set_vision_roasts_enabled` directly — each already owns "write then invalidate cache".
- Deferred-by-design and unchanged this plan (per the plan's own scope boundary): `bot.py`'s two `resolve_ambient_channel(guild)` call sites (startup message, idle-loneliness) and `cogs/music.py::_post_music_roast`'s pre-Phase-18 fallback still lack `surface=` — calling them today would raise `TypeError`. This is intentional; boot is incomplete between waves 2 and 3, and 19-03 is the plan that fixes these call sites. No test currently exercises these code paths (untested-by-design glue, confirmed via `tests/test_roasts.py` only testing message pools, not the call sites themselves), so the full suite stays green despite the now-broken signatures.
- Full suite green: 936 passed, 118 skipped, 0 failed (`pytest -q`). `ruff check .` and `ruff format --check .` both clean repo-wide.

---
*Phase: 19-onboarding-admin-setup*
*Completed: 2026-07-10*

## Self-Check: PASSED

All created/modified files found on disk (logic/guild_config.py, services/guild_config.py, cogs/events.py, tests/test_guild_config_logic.py, tests/test_guild_lifecycle_logic.py, tests/test_guild_config_service.py, tests/test_proactive_events.py); all three task commit hashes (ea42407, 8d134da, 6f645be) found in git history.
