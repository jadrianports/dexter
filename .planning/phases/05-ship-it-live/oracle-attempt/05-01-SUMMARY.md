---
phase: 05-ship-it-live
plan: 01
subsystem: reliability
tags: [postgresql, asyncio, discord.py, zoneinfo, queue-persistence, reconnect]

# Dependency graph
requires:
  - phase: 04-scale
    provides: "queue_persistence service with clear_persisted(), PostgreSQL guild_queues table, smart-rejoin restore logic"
provides:
  - "clear_persisted() called on idle-leave path (bot.py) — ghost-queue-on-restart bug closed"
  - "clear_persisted() called on reconnect-failure path (cogs/music.py) — dead session no longer persists"
  - "is_connected() guard in smart-rejoin (services/queue_persistence.py) — race-defensive post-connect check"
  - "Diagnostic INFO logs on reconnect path, DEBUG logs in _play_track for /gsd:debug trail"
  - "TZ-explicit late-night hour via ZoneInfo(config.STREAK_TIMEZONE) in cogs/events.py"
  - "Wave-0 TZ smoke test in tests/test_streak.py"
affects: [05-02, 05-03, deploy-runbook]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "clear_persisted() call template: queue._play_generation += 1 → queue.clear() → hasattr guard → await clear_persisted()"
    - "is_connected() post-connect paranoia guard before _play_track in async voice code"
    - "DEBUG for hot per-play logs, INFO for low-frequency reconnect path — log-level discipline"
    - "ZoneInfo(config.STREAK_TIMEZONE) for all community-time hour calculations"

key-files:
  created:
    - "tests/test_streak.py (test_tz_aware_hour_is_integer function added)"
  modified:
    - "bot.py — idle-leave clear_persisted() gap closed at ~396"
    - "cogs/music.py — reconnect-failure clear_persisted() gap closed at ~1206; _play_track DEBUG logs added"
    - "services/queue_persistence.py — smart-rejoin is_connected() guard + INFO log"
    - "cogs/events.py — naive datetime.now().hour replaced with ZoneInfo-aware read"

key-decisions:
  - "Mirror the /stop template exactly at both gap sites (generation increment → clear → hasattr guard → clear_persisted) — no divergence from established pattern"
  - "Use bot (not self.bot) in bot.py idle-leave — module-level task, not a cog method"
  - "DEBUG level for _play_track logs (hot per-play path); INFO for reconnect loop (low-frequency) — per D-03 log-level rule"
  - "bot.py:467 yt-dlp loop tzinfo left unchanged (deferred per D-06 Claude's discretion — low-stakes)"

patterns-established:
  - "clear_persisted template: always use queue._play_generation += 1 before clear() and hasattr() guard before await"
  - "Post-connect vc.is_connected() paranoia guard required before any _play_track call from outside a cog"

requirements-completed: [DEPLOY-04, DEPLOY-06]

# Metrics
duration: 25min
completed: 2026-06-12
---

# Phase 5 Plan 01: Pre-Deploy Bug Fixes Summary

**Ghost-queue-on-restart bug closed (clear_persisted at idle-leave + reconnect-failure), smart-rejoin race-hardened with is_connected() guard, late-night roast hour TZ-corrected via ZoneInfo(config.STREAK_TIMEZONE)**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-06-12T00:00:00Z
- **Completed:** 2026-06-12
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- DEPLOY-06 / IN-02 closed: `clear_persisted()` now fires on both the idle-leave path (bot.py) and the reconnect-failure path (cogs/music.py), exactly mirroring the authoritative `/stop` template — a cleared queue can no longer resurrect on next boot
- DEPLOY-04 / WR-03 hardened: smart-rejoin in `services/queue_persistence.py` now captures `vc = await connect()` and guards with `vc.is_connected()` before calling `_play_track`; reconnect loop logs at INFO level and `_play_track` logs at DEBUG level for a live `/gsd:debug` trail
- D-06 fixed: `cogs/events.py` late-night hour computed via `ZoneInfo(config.STREAK_TIMEZONE)` instead of naive `datetime.now().hour` (host-local); Wave-0 TZ smoke test `test_tz_aware_hour_is_integer` added and passing

## Task Commits

1. **Task 1: Close the clear_persisted() gaps (DEPLOY-06 / IN-02)** - `571821d` (fix)
2. **Task 2: Reconnect-race defensive guard + diagnostic instrumentation (DEPLOY-04)** - `5afa18c` (fix)
3. **Task 3: Timezone-correct late-night hour + Wave-0 TZ smoke test (D-06)** - `e1a1d3a` (fix)

## Files Created/Modified

- `bot.py` — idle-leave path: `queue._play_generation += 1` before `vc.stop()`, then `await bot.queue_persistence.clear_persisted(guild.id)` after `queue.clear()`
- `cogs/music.py` — reconnect-failure path: same generation increment + `clear_persisted` added; reconnect loop gets two INFO log calls; `_play_track` gets three DEBUG log calls (gen transition, stop, play)
- `services/queue_persistence.py` — smart-rejoin: captures `vc = await connect()`, logs connected state at INFO, guards with `if not vc.is_connected(): return` before `_play_track`
- `cogs/events.py` — replaces `import datetime as _dt; local_hour = _dt.datetime.now().hour` with `from zoneinfo import ZoneInfo as _ZoneInfo; local_hour = _dt.datetime.now(tz=_ZoneInfo(config.STREAK_TIMEZONE)).hour`
- `tests/test_streak.py` — adds `test_tz_aware_hour_is_integer()` as module-level function

## Decisions Made

- Mirror the `/stop` template exactly at both gap sites — no creative variation, just copy the established pattern with the correct `bot` vs `self.bot` distinction
- `bot.py:467` (yt-dlp loop tzinfo) left unchanged per D-06 Claude's discretion — deferred as low-stakes
- DEBUG (not INFO) for `_play_track` logs — per-track path fires on every song, INFO would flood production logs; reconnect path is low-frequency so INFO is appropriate

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Full pure-unit suite (`python -m pytest tests/ -q --ignore=tests/test_database_phase4.py`) hits import errors for `google.genai` and `yt_dlp` — these packages are not installed in the Windows dev environment (they live on the Oracle Cloud VM). This is pre-existing, not introduced by these changes. The directly-relevant test files (`test_queue.py` 26 tests, `test_streak.py` 12 tests) all pass.

## User Setup Required

None - no external service configuration required. All changes are pure code fixes verified by py_compile and unit tests.

## Next Phase Readiness

- All three pre-deploy code blockers resolved: ghost-queue resurrection (DEPLOY-06), reconnect race hardening (DEPLOY-04), TZ personality correctness (D-06)
- Ready for Plan 05-02 (deploy infrastructure setup / Oracle A1 + Docker + Postgres standup)
- Live behavioral confirmation of these fixes (runbook checks B2/DEPLOY-06, DEPLOY-04, DEPLOY-02 C2) requires the Oracle A1 VM to be running — deferred to Plan 05-03 runbook

## Self-Check: PASSED

- `bot.py`: contains `clear_persisted` in idle-leave block, `queue._play_generation += 1` before `vc.stop()` — FOUND
- `cogs/music.py`: `grep -c "clear_persisted"` returns 2 (existing /stop site + new reconnect-failure site) — FOUND
- `services/queue_persistence.py`: `is_connected()` guard in smart-rejoin try block, `vc = await connect()` captured — FOUND
- `cogs/events.py`: `ZoneInfo` present, naive `datetime.now().hour` absent — FOUND
- `tests/test_streak.py`: `test_tz_aware_hour_is_integer` function present, passes — FOUND
- Commits 571821d, 5afa18c, e1a1d3a: all verified in `git log` — FOUND

---
*Phase: 05-ship-it-live*
*Completed: 2026-06-12*
