---
phase: "09"
plan: "03"
subsystem: reliability-ops
tags: [asyncio, wait_for, startup, background-tasks, loop-error, discord-error-channel, dedup]
dependency_graph:
  requires:
    - config.INIT_WATCHDOG_TIMEOUT_SECONDS (09-01)
    - config.SYNC_TIMEOUT_SECONDS (09-01)
    - config.TASK_ERROR_CHANNEL_COOLDOWN_SECONDS (09-01)
  provides:
    - bot.on_ready asyncio.wait_for watchdog on _initialize_once
    - bot._sync_retry_active single-flight sync-retry guard
    - bot._background_sync_retry async retry helper (3 retries, 60/120/180s backoff)
    - bot._last_loop_error_post module-level dedup map
    - bot._post_loop_error throttled embed poster for loop crashes
    - bot.on_idle_check_error @loop.error handler
    - bot.on_cache_cleanup_error @loop.error handler
    - bot.on_ytdlp_update_error @loop.error handler
    - bot.on_status_rotation_error @loop.error handler
  affects:
    - bot.py on_ready startup path
    - bot.py sync_commands owner command
    - bot.py first_run CLI sync path
    - bot.py four @tasks.loop background loops
tech_stack:
  added: []
  patterns:
    - "asyncio.wait_for wrapping _initialize_once converts hangs to TimeoutError so finally resets _ready_initializing (REL-04 / D-06)"
    - "asyncio.TimeoutError caught before generic Exception in on_ready (Python 3.11+ subclass ordering)"
    - "_sync_retry_active module-level bool guard mirrors _health_server_task pattern (Pitfall 5: multiple shards each fire READY)"
    - "_background_sync_retry best-effort retry modeled on _post_startup_messages pattern"
    - "@loop.error handlers log with exc_info + call throttled _post_loop_error helper"
    - "dedup per (loop_name, exc_type) key with time.monotonic() window — mirrors youtube.py _UPDATE_THROTTLE_SECONDS pattern"
key_files:
  created: []
  modified:
    - bot.py (watchdog wrap, sync timeout + retry, four @loop.error handlers)
decisions:
  - "asyncio.TimeoutError caught BEFORE generic except Exception — it IS a subclass of Exception in Python 3.11+, so order is mandatory"
  - "first_run sync failure logs and proceeds to bot.close() without spawning background retry — one-shot CLI op, no running event loop to retry into"
  - "_sync_retry_active guard placed at top of sync_commands function so single global declaration covers both if/else branches"
  - "_post_loop_error dedup uses 0.0 sentinel (mirrors youtube.py pattern) — correct in production where time.monotonic() >> TASK_ERROR_CHANNEL_COOLDOWN_SECONDS"
  - "import time added at module scope (was only imported locally inside _initialize_once as 'import time as _time')"

requirements-completed: [REL-03, REL-04, REL-02]

# Metrics
duration: 13min
completed: "2026-06-26"
---

# Phase 9 Plan 03: Startup Hardening & Loop Error Visibility Summary

`asyncio.wait_for` watchdog on `_initialize_once` (REL-04), timeout-wrapped `bot.tree.sync` with single-flight background retry (REL-03), and four `@loop.error` handlers with throttled Discord-channel reporting (REL-02 loop path) — all in bot.py.

## Performance

- **Duration:** ~13 min
- **Started:** 2026-06-26T23:00:50+08:00
- **Completed:** 2026-06-26T23:13:02+08:00
- **Tasks:** 3
- **Files modified:** 1 (bot.py)

## Accomplishments

- A true hang inside `_initialize_once` (e.g. stuck cold-Postgres connect) now converts to `asyncio.TimeoutError`, runs the `finally` block, resets `_ready_initializing`, and allows the next READY event to retry — closing the permanent-wedge hole (REL-04 / D-06)
- A failed or slow `bot.tree.sync` on startup now logs a warning, the bot comes online with already-registered commands, and a single background retry chain attempts sync up to 3 times (60/120/180s backoff) without blocking usability (REL-03 / D-05)
- All four `@tasks.loop` background loops (`idle_check`, `cache_cleanup`, `ytdlp_update`, `status_rotation`) now surface crashes via `@loop.error` handlers that log with `exc_info` and post a throttled, sanitized embed to the Discord error channel — no loop fails silently (REL-02 loop path)

## Task Commits

Each task was committed atomically:

1. **Task 1: Watchdog-wrap _initialize_once** - `7f857f8` (feat)
2. **Task 2: Timeout-wrap bot.tree.sync with single-flight background retry** - `53cf00d` (feat)
3. **Task 3: @loop.error handlers for the four background loops** - `3e89412` (feat)

## Files Created/Modified

- `bot.py` — Three targeted edits:
  - Task 1: `on_ready` try/except block — bare `await _initialize_once()` → `asyncio.wait_for(...)` with `except asyncio.TimeoutError:` branch before `except Exception:`
  - Task 2: Added `_sync_retry_active` guard, `_background_sync_retry` async helper, wrapped `sync_commands` and `first_run` sync calls in `asyncio.wait_for`
  - Task 3: Added `import time`, `_last_loop_error_post` dict, `_post_loop_error` helper, and four `@loop.error` handlers

## Decisions Made

- `asyncio.TimeoutError` is caught BEFORE the generic `except Exception:` — mandatory in Python 3.11+ because `asyncio.TimeoutError` is a subclass of `Exception`; wrong order would shadow it with the generic handler
- `first_run` sync failure logs and proceeds to `bot.close()` without spawning `_background_sync_retry` — `first_run` is a one-shot CLI op; once `bot.close()` runs the event loop is done and there is no running loop to retry into
- `global _sync_retry_active` declared at the top of `sync_commands` (not inside each if/else branch) — Python requires the global declaration once per function scope; placing it at the top of the function covers both branches cleanly
- `_post_loop_error` dedup uses `0.0` as the absence sentinel — correct in production (real `time.monotonic()` values are always >> 300s since boot); differs from the `-float("inf")` fix in 09-02 which was needed for the test-time `time.monotonic() == 0.0` scenario; Phase 10 will add tests and can align the sentinel then

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — no stubs or placeholder data introduced.

## Threat Flags

No new threat surface beyond what the plan's threat model covers:
- T-09-04: `_post_loop_error` embed carries `loop_name + type(error).__name__ + str(error)[:500]` only — no guild IDs, user data, tokens, or DSNs. Verified by code inspection.
- T-09-08: `asyncio.wait_for(INIT_WATCHDOG_TIMEOUT_SECONDS)` implemented and verified.
- T-09-09: `asyncio.wait_for(SYNC_TIMEOUT_SECONDS)` on all sync call sites implemented and verified.
- T-09-10: `_sync_retry_active` single-flight guard implemented and verified.

## Self-Check: PASSED

Files verified:
- `bot.py` — `asyncio.wait_for(_initialize_once(), ...)` FOUND; `except asyncio.TimeoutError:` before `except Exception:` in `on_ready` FOUND; `_sync_retry_active` FOUND; `_background_sync_retry` FOUND; all four `@loop.error` handlers FOUND; `_post_loop_error` FOUND; `import time` at module scope FOUND

Commits verified:
- `7f857f8` feat(09-03): watchdog-wrap _initialize_once so on_ready never wedges (REL-04)
- `53cf00d` feat(09-03): timeout-wrap bot.tree.sync with single-flight background retry (REL-03)
- `3e89412` feat(09-03): add @loop.error handlers for four background loops (REL-02 loop path)

Test suite: 340 passed, 64 skipped (no regressions from any of the three tasks).
