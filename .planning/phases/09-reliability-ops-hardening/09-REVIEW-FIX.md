---
phase: 09-reliability-ops-hardening
fixed_at: 2026-06-26T18:15:50Z
review_path: .planning/phases/09-reliability-ops-hardening/09-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 9: Code Review Fix Report

**Fixed at:** 2026-06-26T18:15:50Z
**Source review:** .planning/phases/09-reliability-ops-hardening/09-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (Warning tier; Info findings IN-01..IN-04 out of scope)
- Fixed: 5
- Skipped: 0

All fixes applied in an isolated git worktree, each committed atomically.
Full test suite re-run after the bot.py change: 353 passed, 64 skipped.

## Fixed Issues

### WR-01: `_play_track` dispatched via bare `asyncio.create_task` — no exception surfacing, GC-abandonment risk

**Files modified:** `cogs/music.py`
**Commit:** 6651665
**Applied fix:** Routed both skip-dispatch sites (`_do_skip` line ~889 and the `/skip`
slash command line ~1481) through `make_task(..., name="play-after-skip", bot=self.bot)`.

Resolved the reviewer-vs-plan tension explicitly: Plan 09-02 Pitfall 4 left these
bare on the premise that `_play_track` "handles its own failures internally". On
inspection that is only partially true — the `get_source` path is caught and
chains to the next track, but the `voice_client.play()` block (lines 614-617)
runs `source.cleanup()` and **re-raises**. That re-raised exception escapes
`_play_track`, so under a bare `create_task` it is silently swallowed (no log, no
error-channel embed) and the task has no strong reference (GC-abandonment risk).
Because `make_task` is the only error surfacing on that path (no inner
error-channel post exists to duplicate), routing through it does **not**
double-handle — it adds the missing surfacing and a strong reference. Fix applied
rather than skipped. Verified: `test_now_playing_refresh`, `test_queue`,
`test_autoqueue_playback` all green.

### WR-02: `/skip` slash command leaves a stale now-playing embed

**Files modified:** `cogs/music.py`
**Commit:** 9f1bd00
**Applied fix:** After scheduling background playback in the `if next_track:` branch
of the `/skip` slash command, added `await self._refresh_now_playing(interaction.guild, queue)`
to mirror the button path (`_do_skip`) and natural-advance path (`_on_track_end`).
The persistent player embed + controls now re-render onto the new track instead of
freezing on the previous song. Verified: `test_now_playing_refresh` green.

### WR-03: `/health` runs a blocking DB probe with an unbounded `acquire()` on every request

**Files modified:** `cogs/ops.py`, `config.py`
**Commit:** d12676b
**Applied fix:** Added `config.HEALTH_DB_PROBE_TIMEOUT = 3.0` and wrapped the **entire**
probe (`pool.acquire()` + `SELECT 1`) in `asyncio.wait_for(_db_probe(), timeout=...)`
inside `gather_bot_metrics`. A cold/scaling Neon instance or exhausted pool now
degrades fast (`db_ok=False`, "database unreachable") instead of blocking the health
request up to `command_timeout` or indefinitely on `acquire()`. A timeout raises
`asyncio.TimeoutError`, already caught by the existing `except Exception`. Verified:
all 7 `test_health_endpoint` tests + `test_config` green.

### WR-04: Partial-init cleanup deletes `bot.pool` while leaving started loops/cogs bound to the dead pool

**Files modified:** `bot.py`
**Commit:** 3a1155f
**Status note:** fixed — **requires human verification** (init-lifecycle code not
covered by unit tests; verified for syntax + no regression only).
**Applied fix:** Chose the reviewer's option (b) — the localized cleanup-path fix —
over option (a) (reordering loop/health-server startup), because the health server
is documented to start early so Koyeb's first-deploy health check passes; reordering
it conflicts with that intent. Extracted a `_cleanup_partial_init()` helper called
from both the `TimeoutError` and generic-`Exception` branches of `on_ready`. It now:
(1) cancels the pool-bound background loops (`idle_check`, `cache_cleanup`,
`ytdlp_update`, `status_rotation`) so they stop firing against the about-to-be-closed
pool; (2) drops `bot.queue_persistence` (recreated by `_initialize_once` on retry);
(3) closes + deletes `bot.pool` last. The health server is intentionally left running
(it reads `bot.pool` live and degrades gracefully when absent). The retry's
`if not <loop>.is_running(): <loop>.start()` guards re-arm everything atomically.
Full suite re-run after this change: 353 passed, 64 skipped.

### WR-05: `test_health_endpoint.py` mutates the shared `MagicMock` class (global cross-test pollution)

**Files modified:** `tests/test_health_endpoint.py`
**Commit:** 67a249b
**Applied fix:** Replaced the `MagicMock`-based `_make_fake_bot` with a plain
`types.SimpleNamespace` stub, removing the `type(bot).__contains__ = MagicMock(...)`
line that monkeypatched `__contains__` process-wide for every MagicMock in the
session. With the namespace stub, `hasattr(bot, "_start_monotonic")` is genuinely
False, so `gather_bot_metrics` keeps `uptime_seconds` at its `0.0` default; added
`assert metrics["uptime_seconds"] == 0.0` in `test_health_ok` to lock that intent.
Confirmed the prior "coroutine never awaited" cross-test RuntimeWarning disappeared
after the change. Verified: all 7 `test_health_endpoint` tests green.

---

_Fixed: 2026-06-26T18:15:50Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
