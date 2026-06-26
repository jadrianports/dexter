---
phase: 09-reliability-ops-hardening
reviewed: 2026-06-26T15:45:25Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - bot.py
  - cogs/music.py
  - cogs/ops.py
  - config.py
  - services/youtube.py
  - tests/test_config.py
  - tests/test_health_endpoint.py
  - tests/test_tasks.py
  - tests/test_youtube.py
  - utils/tasks.py
findings:
  critical: 0
  warning: 5
  info: 4
  total: 9
status: issues_found
---

# Phase 9: Code Review Report

**Reviewed:** 2026-06-26T15:45:25Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Phase 9 (Reliability & Ops Hardening) wires up a degraded `/health` endpoint
(503-on-degraded), a config-driven init watchdog + sync timeout, a throttled
background-task error reporter (`utils/tasks.make_task`), and bounded yt-dlp
quick-retry/self-heal in `services/youtube.py`. The new code is generally well
structured and well tested — the retry classifier, the dedup throttle, and the
health body-selection logic all have targeted unit tests.

No security vulnerabilities or correctness BLOCKERs were found. The defects are
concentrated in two themes: (1) the new `make_task` exception-surfacing pattern
was **not applied at two of the most failure-prone fire-and-forget sites**
(`_play_track` background dispatch), leaving silent-failure / GC-abandonment
paths exactly where Phase 9 set out to close them; and (2) the health DB probe
plus partial-init cleanup introduce robustness gaps under a slow/cold Neon DB.
There are also test-quality issues in `test_health_endpoint.py` (global
MagicMock class mutation) and several stale comments / minor input-validation
gaps.

## Narrative Findings (AI reviewer)

## Warnings

### WR-01: `_play_track` dispatched via bare `asyncio.create_task` — no exception surfacing, GC-abandonment risk

**File:** `cogs/music.py:889`, `cogs/music.py:1481`
**Issue:** Phase 9 (REL-02) introduced `utils.tasks.make_task` precisely to keep
a strong reference to fire-and-forget tasks and surface their exceptions to logs
+ the error channel. Two of the highest-risk dispatch sites were not migrated:

```python
# _do_skip (line 889) and /skip slash (line 1481)
asyncio.create_task(self._play_track(guild, next_track))
```

These tasks keep no strong reference and attach no done-callback. If
`_play_track` raises (e.g. `get_source`/ffmpeg spawn failure on a path the inner
try doesn't cover, or a `voice_client` race), the exception is silently
swallowed — no `log.error`, no error-channel embed. Worse, per the asyncio docs
(cited verbatim in `utils/tasks.py`), a task with no live reference may be
garbage-collected mid-await, silently stopping playback after a skip. Auto-queue
(`make_task(ai_cog.try_auto_queue...)`) and prefetch already use `make_task`, so
this is an inconsistent, partial rollout that leaves the skip path unguarded.
**Fix:**
```python
from utils.tasks import make_task
make_task(self._play_track(guild, next_track), name="play-after-skip", bot=self.bot)
```
Apply at both line 889 and line 1481.

### WR-02: `/skip` slash command leaves a stale now-playing embed (button-skip path refreshes, slash path does not)

**File:** `cogs/music.py:1476-1485`
**Issue:** The button skip path (`_do_skip`, lines 875-896) calls
`await self._refresh_now_playing(guild, queue)` so the persistent player embed +
controls re-render onto the new track. The `/skip` slash command does not — it
plays the next track in the background and only posts a transient
`"Skipped to **title**"` text message. The persistent now-playing message stays
frozen on the *previous* song's title/thumbnail/progress, diverging from both
the button path and the natural-advance path (`_on_track_end` →
`_refresh_now_playing`). This is an observable inconsistency, not just style.
**Fix:** After scheduling playback in the `if next_track:` branch, call
`await self._refresh_now_playing(interaction.guild, queue)` to match `_do_skip`.

### WR-03: `/health` runs a blocking DB probe with an unbounded `acquire()` on every request

**File:** `bot.py:212-236`, `cogs/ops.py:96-104`
**Issue:** The health handler calls `gather_bot_metrics(bot)` on every hit, which
does `async with pool.acquire() as conn: await conn.execute("SELECT 1")`.
`pool.acquire()` has no timeout, and the only bound on the query is the pool's
`command_timeout=30`. Against a cold/scaling Neon instance (the documented
deploy target, which scales to zero) or an exhausted pool (`DB_POOL_MAX=5`,
shared with `/play`, `/leaderboard`, `/stats`), a single `/health` request can
block up to ~30s — or indefinitely if `acquire()` waits on an exhausted pool.
External health checkers (Koyeb/UptimeRobot) will time out and may flap the
service; concurrent probes can pile up and consume the remaining pool slots.
**Fix:** Bound the probe explicitly so health degrades fast rather than hanging:
```python
async with pool.acquire() as conn:
    await asyncio.wait_for(conn.execute("SELECT 1"), timeout=config.HEALTH_DB_PROBE_TIMEOUT)
```
Wrap the whole probe (acquire included) in `asyncio.wait_for` with a small
(2-3s) timeout and treat a timeout as `db_ok=False` / "database unreachable".

### WR-04: Partial-init cleanup deletes `bot.pool` while leaving started loops/cogs bound to the dead pool

**File:** `bot.py:282-308`, `bot.py:379-388`
**Issue:** `_initialize_once` starts the background loops (`idle_check`,
`cache_cleanup`, `status_rotation`, `ytdlp_update`) and the health server *before*
`restore_queues` and before `_start_monotonic`. If init then hangs (watchdog
`TimeoutError`) or raises during/after those starts, the cleanup path does
`await _pool.close()` then `del bot.pool` and returns to retry on the next READY.
But the already-running `idle_check` keeps firing every 60s and, on an idle
guild, calls `bot.queue_persistence.clear_persisted(...)` against the now-closed
pool held by the *old* `QueuePersistenceService` (only re-created on the next
successful retry). That raises inside the loop (caught by `@idle_check.error`,
posting a recurring error) until a retry succeeds. Live cogs accessing
`self.bot.pool` during the window hit `AttributeError`.
**Fix:** Start the background loops and health server only after the
fail-prone steps (DB ready, `restore_queues`) succeed, or have the cleanup path
also stop the loops (`idle_check.cancel()`, etc.) and drop
`bot.queue_persistence` so the retry re-wires everything atomically.

### WR-05: `test_health_endpoint.py` mutates the shared `MagicMock` class (global cross-test pollution)

**File:** `tests/test_health_endpoint.py:78-83`
**Issue:** `_make_fake_bot` does `type(bot).__contains__ = MagicMock(return_value=False)`.
`type(MagicMock())` is the shared `unittest.mock.MagicMock` class, so this
monkeypatches `__contains__` process-wide for every MagicMock in the test
session — a classic source of order-dependent, flaky failures in unrelated
tests. Additionally, the surrounding code's stated intent
("`hasattr(bot, '_start_monotonic') == False`") does not hold: a MagicMock
auto-creates attributes, so `hasattr` is always True and `del bot._start_monotonic`
is a no-op; `gather_bot_metrics` then computes `uptime_seconds` as a MagicMock
(not `0.0`). The current assertions pass only because nothing checks uptime.
**Fix:** Use `MagicMock(spec=...)` or a small plain stub object/`SimpleNamespace`
for the fake bot so attribute presence is real and no class-level state is
mutated; assert `metrics["uptime_seconds"] == 0.0` to lock the intended default.

## Info

### IN-01: `_pick_next_status` rotation is uneven because the pool length varies tick-to-tick

**File:** `bot.py:142-190`
**Issue:** `_status_index` increments monotonically while the pool is rebuilt each
tick with a *variable* length — slot 0 (current song) is appended only when
something is playing, slot 3 (seasonal) only when applicable. Indexing
`pool[_status_index % len(pool)]` against a changing length maps the same index
to different content as `len(pool)` shifts, so the same status can show twice in
a row or a slot can be skipped entirely. Cosmetic (presence text), but the
"round-robin" intent isn't actually achieved.
**Fix:** Track rotation against a fixed slot set (compute the candidate for a
stable slot index, falling back when empty) rather than modulo over a
variable-length list.

### IN-02: Stale / contradictory comments around hosting and cache size

**File:** `bot.py:243-249`, `config.py:22`
**Issue:** The health-server comment block references Render, Railway, and Koyeb
interchangeably (`$PORT`, "Render injects $PORT", "keeps a Render free web
service from sleeping") while the rest of the codebase/CLAUDE.md targets
Koyeb+Neon then a residential PC. `config.py:22` says
`AUDIO_CACHE_MAX_MB = 512  # Koyeb 2GB ephemeral disk (K-07)` — the comment cites
2GB but the value is 512. These mislead future maintainers about the deploy
target and disk budget.
**Fix:** Normalize the comments to the current host story and correct the cache
comment to reflect the 512MB cap.

### IN-03: `int(guild_id)` in `/sync` and `first_run` can raise on non-numeric input after defer

**File:** `bot.py:522`, `bot.py:770`
**Issue:** `discord.Object(id=int(guild_id))` will raise `ValueError` for a
non-numeric `guild_id`. In `/sync` this happens after `interaction.response.defer`,
surfacing as an unhandled invoke error routed to the global handler rather than a
clean "invalid guild id" message. In `first_run` it aborts the sync-and-exit run.
**Fix:** Validate/parse defensively, e.g.
`if not guild_id.isdigit(): return await interaction.followup.send("guild id must be numeric.")`.

### IN-04: `HEALTH_STRICT_STATUS` is disabled only by the exact string `"false"`

**File:** `config.py:143`
**Issue:** `os.getenv("HEALTH_STRICT_STATUS", "true").lower() != "false"` means
common falsey values (`0`, `no`, `off`, `disabled`) silently leave strict mode
on, which is surprising for an operator toggling the legacy 200 escape hatch.
**Fix:** Parse a small truthy set, e.g.
`os.getenv("HEALTH_STRICT_STATUS", "true").strip().lower() not in {"false","0","no","off"}`.

---

_Reviewed: 2026-06-26T15:45:25Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
