---
phase: 04-scale
plan: 04
subsystem: database
tags: [asyncpg, postgres, queue-persistence, queue-cap, aiosqlite-migration]

# Dependency graph
requires:
  - phase: 04-03
    provides: "bot.pool (asyncpg pool) and bot.queue_persistence (QueuePersistenceService) wired in on_ready"
  - phase: 04-02
    provides: "log_track_batch, asyncpg helpers with $N params"
  - phase: 04-01
    provides: "QueueFullError raised by MusicQueue.add() at cap; Track.to_dict/from_dict"
provides:
  - "All three DB-consuming cogs migrated from aiosqlite self.bot.db to asyncpg self.bot.pool"
  - "/play writes batched through log_track_batch in one transaction (D-06/SCALE-01)"
  - "QueueFullError caught at all 3 queue.add() sites with personality rejection (D-04/SCALE-01)"
  - "persist-on-mutation hooks at 8 mutation sites with live voice-channel-id capture (D-19/D-20/SCALE-04)"
  - "clear_persisted called after queue.clear() in /stop so cleared queues are not restored"
  - "Global Gemini 15 RPM limiter confirmed intact in cogs/ai.py (D-03 confirm-only)"
affects: [04-05, runtime bot operation, all cog commands]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "pool property on each cog returns self.bot.pool (single pool, no per-cog wiring)"
    - "_persist_queue helper: captures vc_id live from guild.voice_client.channel (D-20); guarded with hasattr; failures swallowed by service (T-04-09)"
    - "QueueFullError caught at every queue.add() site with lowercase personality rejection + return/break"
    - "clear_persisted guarded with hasattr(self.bot, 'queue_persistence') like persist hooks"

key-files:
  created: []
  modified:
    - cogs/music.py
    - cogs/ai.py
    - cogs/imagine.py

key-decisions:
  - "3 queue.add() catch sites total (not 2): _queue_from_selection + playlist loop + direct URL in /play — all three needed"
  - "playlist loop uses break on QueueFullError (not return) plus a cap notice in the summary message"
  - "reconnect race region (on_voice_state_update loop) left untouched per D-22 — no persist hook injected there"
  - "_log_track now imports log_track_batch, increment_daily_stat, mark_song_skipped at module top level (not inline)"
  - "bot.py idle_check's queue.clear() call not given clear_persisted — it uses queue.clear() but doesn't import queue_persistence; leaving it is consistent with D-22 scope boundary and bot.py file ownership"

patterns-established:
  - "Cog DB access: self.bot.pool property, never self.bot.db"
  - "Per-/play writes: always route through log_track_batch (not individual helpers)"
  - "Queue mutations: always follow with await self._persist_queue(guild, queue)"
  - "Queue clears (intentional): always follow with await self.bot.queue_persistence.clear_persisted(guild.id)"

requirements-completed: [SCALE-01, SCALE-04]

# Metrics
duration: 20min
completed: 2026-06-12
---

# Phase 04 Plan 04: Cog DB Migration Summary

**asyncpg pool wired into all three cogs: /play writes batched in one transaction, QueueFullError caught at all add sites, persist-on-mutation hooks at 8 mutation sites with live voice-channel-id capture**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-06-12T20:40:00Z
- **Completed:** 2026-06-12T21:00:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- All `self.bot.db` (aiosqlite) references removed from cogs/music.py, cogs/ai.py, cogs/imagine.py — every DB call now uses `self.bot.pool` (asyncpg)
- `_log_track` in cogs/music.py replaced three sequential awaits (`log_song` + `update_artist_count` + `update_user_profile`) with a single `log_track_batch` call — one atomic transaction per /play (D-06/SCALE-01)
- `QueueFullError` caught at all 3 `queue.add()` sites with personality rejection message; playlist loop uses `break` + cap notice (D-04/SCALE-01)
- `_persist_queue` helper wired at 8 mutation sites; `clear_persisted` called after `/stop` queue.clear(); voice-channel id captured live at persist time (D-19/D-20/SCALE-04)
- Global Gemini 15 RPM limiter in cogs/ai.py confirmed intact — no per-guild logic introduced (D-03)

## Task Commits

Each task was committed atomically:

1. **Task 1: Migrate cog DB access to asyncpg pool + batched /play logging** - `50e0428` (feat)
2. **Task 2: Queue-cap rejection + persist-on-mutation hooks** - `b4d3974` (feat)

**Plan metadata:** (see below — created with this SUMMARY)

## Files Created/Modified

- `cogs/music.py` — pool property; _log_track batched via log_track_batch; _get_top_artist/milestone fetch converted to asyncpg pool.acquire + $N; QueueFullError at 3 add sites; _persist_queue helper + 8 call sites; clear_persisted in /stop
- `cogs/ai.py` — pool property replacing db; self.bot.pool throughout get_mood/get_user_summary/get_recent_songs/increment_daily_stat; global Gemini limiter unchanged
- `cogs/imagine.py` — pool property replacing db; self.bot.pool throughout get_images_today/log_image/increment_daily_stat

## Decisions Made

- Three `queue.add()` call sites exist (not two): `_queue_from_selection` (dropdown), playlist loop, direct URL in `/play`. All three wrapped with `try/except QueueFullError`.
- Playlist loop uses `break` on `QueueFullError` (not `return`) since there is post-loop work (playback start + summary message). A `cap_reached` flag drives the cap notice appended to the summary message.
- Reconnect race region (`on_voice_state_update`, ~line 1188) left untouched per D-22 — the `queue.clear()` inside the reconnect failure path does not receive `clear_persisted`.
- Module-level imports: `log_track_batch`, `increment_daily_stat`, `mark_song_skipped`, `QueueFullError` moved to top-level imports in cogs/music.py instead of inline `from database import ...` inside `_log_track`.

## Deviations from Plan

None — plan executed exactly as written. The only notable discovery was that there are 3 `queue.add()` call sites, not 2 as loosely described in the plan action text (the plan's acceptance criteria correctly said "both the single-add and playlist-loop add" plus `_queue_from_selection` is a third path). All three are wrapped.

## Issues Encountered

None. All three cogs compiled cleanly, existing tests passed (58/58), and all verification grep assertions were satisfied.

## Verification Results

Static verification (no live Postgres or Discord on dev machine):

- `python -m py_compile cogs/music.py cogs/ai.py cogs/imagine.py` — all pass
- `python -c "import ast; ..."` syntax check — all three cogs valid
- `grep -c "self.bot.db"` — 0 in all three cogs
- `grep -c "self.db"` — 0 in all three cogs  
- Verified: `log_track_batch` present in cogs/music.py; `pool.acquire()` count = 2 (top-artist + milestone fetch)
- Verified: `QueueFullError` caught at 3 add sites; `_persist_queue` at 8 call sites; `clear_persisted` at 1 site; `voice_client.channel.id` present
- `pytest tests/test_rate_limiter.py tests/test_queue.py tests/test_message_buffer.py tests/test_ai_helpers.py tests/test_autoqueue_parse.py -x -q` — **58 passed**

Deferred (requires live runtime):
- Boot with persisted guild queue → queue restored + smart rejoin (UAT gate D-21)
- Over-cap `/play` with full queue → personality rejection message visible in Discord
- `/stop` → persisted row deleted (verify via `SELECT * FROM guild_queues`)

## User Setup Required

None — no new external service configuration required. This plan wires the existing asyncpg pool (configured in 04-03) into the cogs.

## Next Phase Readiness

- All three DB-consuming cogs are now fully on asyncpg; aiosqlite is no longer used anywhere in the cog layer
- Wave 3 (cog consumer integration) is complete; bot is ready for 04-05 (Docker + hosting infra)
- Runtime verification of persistence restore and cap rejection is deferred to first live boot on Oracle Cloud

---
*Phase: 04-scale*
*Completed: 2026-06-12*
