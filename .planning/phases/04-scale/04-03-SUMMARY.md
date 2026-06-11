---
phase: 04-scale
plan: "03"
subsystem: bot-runtime
tags: [autoshardedbot, asyncpg, queue-persistence, pool-lifecycle, smart-rejoin]
dependency_graph:
  requires: [04-01, 04-02]
  provides: [bot.pool, bot.queue_persistence, restore_queues, AutoShardedBot]
  affects: [bot.py, services/queue_persistence.py]
tech_stack:
  added: [asyncpg pool lifecycle, QueuePersistenceService, AutoShardedBot]
  patterns: [_ready_once guard, UPSERT persist, smart-rejoin restore, service-wired-in-on_ready]
key_files:
  created: [services/queue_persistence.py]
  modified: [bot.py]
decisions:
  - "_ready_once guard placed immediately after login log line so ALL subsequent on_ready init (pool, cogs, services) is skipped on reconnect"
  - "restore_queues module-level wrapper chosen so bot.py imports a single name without needing service instance reference"
  - "asyncpg payload normalisation handles both str and dict returns from asyncpg jsonb column"
metrics:
  duration: ~15 minutes
  completed: "2026-06-12"
  tasks_completed: 2
  tasks_total: 2
---

# Phase 04 Plan 03: Production Runtime Wiring Summary

AutoShardedBot, asyncpg connection pool, `_ready_once` reconnect guard, and `QueuePersistenceService` wired into the production runtime with smart-rejoin boot restore.

## What Was Built

### Task 1 — `services/queue_persistence.py` (new file)

`QueuePersistenceService` with three public methods:

- `persist(guild, queue, voice_channel_id)` — builds a typed jsonb payload from current `MusicQueue` state and UPSERTs it to `guild_queues` via parameterised SQL. Failures are caught and logged; never propagated to playback (D-20).
- `clear_persisted(guild_id)` — DELETEs the `guild_queues` row so a cleared queue is not restored on next boot.
- `restore_queues(bot)` — fetches all `guild_queues` rows, reconstructs in-memory `MusicQueue` state (tracks, current_index, loop_mode, text/voice channel ids), and performs a smart rejoin: connects to voice and calls `_play_track` only when the previously-active channel has at least one non-bot human present (D-21). Silently skips guilds the bot has left. Returns early if `MusicCog` is not yet loaded (Pitfall 4 guard).

A module-level `restore_queues(bot)` wrapper delegates to the service instance so `bot.py` can import a single name.

### Task 2 — `bot.py` (modified)

- `create_bot()` changed to `commands.AutoShardedBot(...)` and return annotation updated (SCALE-03, D-02).
- `import aiosqlite` removed; `import asyncpg` added at module level.
- `on_ready`: `_ready_once` guard added immediately after the login log line — if `bot._ready_once` already exists, the handler returns immediately. This prevents pool double-creation, duplicate `load_extension` calls, and double startup messages on AutoShardedBot reconnect events (Pitfall 2, T-04-07).
- `on_ready`: aiosqlite DB block (`connect` + `row_factory` + `init_db`) replaced with `asyncpg.create_pool(dsn=config.DATABASE_URL, min_size=config.DB_POOL_MIN, max_size=config.DB_POOL_MAX, command_timeout=30)` followed by `init_db(bot.pool)`.
- `on_ready`: `bot.queue_persistence = QueuePersistenceService(bot.pool)` wired after pool creation, before cog loading.
- `on_ready`: `await restore_queues(bot)` called after all `load_extension` calls and background-task starts, before the startup-message block (Pitfall 4 ordering, Anti-Pattern ordering).
- `on_close`: `bot.db.close()` replaced with `bot.pool.close()`.

## Decisions Made

1. `_ready_once` guard placement: immediately after the login log line (before any service/DB/cog init) so a reconnect READY returns before touching pool or cogs.
2. Module-level `restore_queues` wrapper: simplifies `bot.py` import to `from services.queue_persistence import restore_queues` without exposing the service class.
3. asyncpg jsonb normalisation: `if isinstance(payload, str): payload = json.loads(payload)` handles both dict (asyncpg native jsonb decode) and str (raw text column fallback) so the restore is resilient across asyncpg version behaviour differences.
4. `first_run` left unchanged: it defines its own minimal `on_ready` that closes immediately after sync — no pool needed; `AutoShardedBot` inherits `start()` without issue.

## Deviations from Plan

None — plan executed exactly as written.

## Security Notes

- T-04-05: DSN comes from `config.DATABASE_URL` (env, git-ignored); `bot.py` never logs the pool object or DSN string.
- T-04-06: `guild_queues` jsonb payload is `json.dumps` of a typed dict written by the bot itself; `Track.from_dict` reads only known keys with `.get` defaults; no `eval`/exec on payload.
- T-04-07: `_ready_once` guard prevents double pool creation and double `load_extension` on reconnect (DoS mitigation).
- T-04-08: Smart rejoin fires only when a non-bot human is present in the previously-active channel; failure is caught and logged.

## Known Stubs

None — `services/queue_persistence.py` is fully functional. The persist-on-mutation call sites (cogs/music.py hooks) land in plan 04-04.

## Self-Check

### Files Created/Modified
- [x] `services/queue_persistence.py` exists
- [x] `bot.py` modified (AutoShardedBot, asyncpg pool, _ready_once, restore_queues, pool teardown)

### Commits Exist
- [x] `9d8c155` — feat(04-03): add QueuePersistenceService
- [x] `1508e01` — feat(04-03): AutoShardedBot, asyncpg pool lifecycle, _ready_once guard

### Runtime Verification
DEFERRED — no local Postgres or Discord token available on this Windows dev machine. Runtime/pool verification requires `docker compose up` with the live environment (deferred to plan 04-05 infra). Static verification confirmed:
- Both files parse with `ast.parse()` — syntax OK
- Import check: `import services.queue_persistence` succeeds and exposes all expected names
- Structural assertions: all `grep` / `assert` acceptance criteria pass
- Ordering: `restore_queues` call is after `await bot.load_extension(...)` calls and before `STARTUP_MESSAGES` block (verified by line-number inspection)

## Self-Check Result: PASSED (static verification only — runtime deferred as documented)
