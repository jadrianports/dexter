---
phase: 09-reliability-ops-hardening
verified: 2026-06-26T16:00:00Z
status: human_needed
score: 17/17 must-haves verified
overrides_applied: 0
re_verification: false
human_verification:
  - test: "Boot bot with MusicCog forced to fail (or DB unreachable); run curl -s -o /dev/null -w '%{http_code}' localhost:<port>/health"
    expected: "503 with degraded JSON body; set HEALTH_STRICT_STATUS=false and confirm 200"
    why_human: "Requires live process with HTTP server running and cog-load state; unit tests cover the logic but not the end-to-end HTTP binding"
  - test: "Force _prefetch_next_track or _post_auto_lyrics to raise (e.g. monkeypatch the method to throw); observe dexter.log and ERROR_LOG_CHANNEL_ID in Discord"
    expected: "One log line per occurrence in dexter.log; throttled/deduped embed post in error channel — repeating the same failure does not flood the channel"
    why_human: "Requires a live running bot with Discord error channel configured; dedup timing requires real time.monotonic() clock"
  - test: "Simulate a slow/failing bot.tree.sync (inject delay or error); observe bot startup and /help or any slash command"
    expected: "Bot reaches ready state; warning logged; already-registered slash commands still work; single background retry chain fires"
    why_human: "Requires live Discord gateway; multi-shard READY event timing cannot be replicated in unit tests"
  - test: "Inject a hang (e.g. asyncio.sleep with no timeout) into _initialize_once; observe startup logs and second READY event"
    expected: "asyncio.wait_for watchdog fires after INIT_WATCHDOG_TIMEOUT_SECONDS; pool is cleaned up; _ready_initializing resets; next READY retries"
    why_human: "Requires a live bot process to inject the hang and observe the retry; cannot simulate asyncio task cancellation on _initialize_once in unit tests without the full bot runtime"
  - test: "Run /leaderboard or /stats while the Neon DB is slow (e.g. wake from scale-to-zero); observe response and bot responsiveness"
    expected: "User sees 'database is being slow. try again in a bit.' (leaderboard) or 'stats are taking too long. try again in a bit.' (stats); bot stays responsive"
    why_human: "Requires a live asyncpg pool against Neon with a genuine slow query exceeding command_timeout=30s"
  - test: "Force a transient search()/extract() failure (network blip simulation); then force ExtractorError(expected=True) for a video unavailable URL"
    expected: "Transient failure: bounded quick retry recovers, no update call on first failures; permanent failure: propagates immediately with no retry/update"
    why_human: "Requires a live yt-dlp executor to verify the actual retry timing and update behavior against a real network; unit tests cover the logic but not the full yt-dlp execution chain"
---

# Phase 9: Reliability & Ops Hardening — Verification Report

**Phase Goal:** Dexter can no longer fail silently — `/health` tells the truth, background tasks surface their exceptions, startup sync recovers instead of hanging, and slow queries / transient YouTube failures self-heal.
**Verified:** 2026-06-26T16:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

All must-haves from all four plans are checked against the actual codebase.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | /health returns HTTP 503 with degraded JSON body when HEALTH_STRICT_STATUS is true and reasons present | VERIFIED | `bot.py:225-230` — `status = 503 if getattr(config, "HEALTH_STRICT_STATUS", True) else 200`; test `test_status_503_strict_mode` passes |
| 2 | /health returns HTTP 200 always when HEALTH_STRICT_STATUS is false (legacy escape hatch) | VERIFIED | Same conditional; `test_status_200_legacy_mode` passes |
| 3 | gather_bot_metrics reports "MusicCog not loaded" only after `_ready_done` is set | VERIFIED | `cogs/ops.py:115-117` — guarded by `getattr(bot, "_ready_done", False)`; tests `test_musiccog_missing_post_init` and `test_startup_no_false_degraded` both pass |
| 4 | asyncpg pool command_timeout is driven by config.DB_COMMAND_TIMEOUT_SECONDS, not a hardcoded literal | VERIFIED | `bot.py:326` — `command_timeout=config.DB_COMMAND_TIMEOUT_SECONDS`; all K-04 kwargs (ssl, statement_cache_size, max_inactive_connection_lifetime) byte-identical |
| 5 | A query exceeding the timeout shows a personality message in /leaderboard and /stats instead of hanging | VERIFIED | `cogs/ops.py:166-172` (/leaderboard) and `210-216` (/stats) — `except asyncio.TimeoutError:` before `except Exception:`, static strings, no exc interpolation |
| 6 | A crashing fire-and-forget task (_prefetch_next_track, _post_auto_lyrics, try_auto_queue) logs its exception | VERIFIED | `utils/tasks.py:111` — `log.error("Background task %r raised: %s", task_name, exc, exc_info=exc)` always fires; all three sites wired via `make_task` in `cogs/music.py:622,629,764` |
| 7 | The same crash also posts to Discord error channel, rate-limited per (task_name, exc_type) | VERIFIED | `utils/tasks.py:118-127` — dedup map `_last_task_error_post` keyed `"{task_name}:{ExcType}"` with `-inf` sentinel; `asyncio.ensure_future(_post_task_error(...))` schedules the async post |
| 8 | A cancelled task is silently ignored — no spurious error log or CancelledError | VERIFIED | `utils/tasks.py:103-104` — `if task.cancelled(): return` guard before `task.exception()` (Pitfall 1); `test_cancelled_returns_early` passes |
| 9 | The _play_track fire-and-forget tasks are NOT given error-channel callbacks | VERIFIED | `cogs/music.py:889,1481` — both use bare `asyncio.create_task(self._play_track(...))` as intended by plan Pitfall 4 |
| 10 | A true hang inside _initialize_once converts to TimeoutError so _ready_initializing resets | VERIFIED | `bot.py:277-295` — `asyncio.wait_for(_initialize_once(), timeout=config.INIT_WATCHDOG_TIMEOUT_SECONDS)`; `except asyncio.TimeoutError:` appears BEFORE `except Exception:` (mandatory ordering for 3.11+); pool cleanup + return present; `finally: bot._ready_initializing = False` unchanged |
| 11 | A failed or slow bot.tree.sync logs, bot stays online with existing commands, retries in background | VERIFIED | `bot.py:445-468` — `_background_sync_retry` retries 3 times (60/120/180s backoff); `bot.py:525-553` — sync_commands wraps both guild+global sync in `asyncio.wait_for`; `bot.py:773-785` — first_run wraps both paths |
| 12 | Only one background sync-retry chain runs at a time | VERIFIED | `bot.py:201` — `_sync_retry_active: bool = False`; both branches in `sync_commands` gate on `if not _sync_retry_active:` before spawning |
| 13 | Each @tasks.loop background loop surfaces exceptions via @loop.error that logs and posts throttled embed | VERIFIED | `bot.py:675-678` (idle_check), `710-713` (cache_cleanup), `729-732` (ytdlp_update), `755-758` (status_rotation) — all call `log.error(..., exc_info=error)` then `await _post_loop_error(...)` |
| 14 | A transient search()/extract() failure retries within bounded quick-retry budget and recovers | VERIFIED | `services/youtube.py:256-270` (async_search) and `295-309` (async_extract) — `range(config.YTDLP_MAX_QUICK_RETRIES + 1)` loop with `asyncio.sleep(YTDLP_RETRY_BACKOFF_SECONDS * (attempt+1))` |
| 15 | Exhausted quick retries fall back to throttled yt-dlp self-update + one final attempt | VERIFIED | `services/youtube.py:273-284` (search) and `312-323` (extract) — checks `_UPDATE_THROTTLE_SECONDS` before calling `update_ytdlp`, then one final `run_in_executor` attempt |
| 16 | A permanent failure (ExtractorError.expected=True) bypasses retry and update path entirely | VERIFIED | `services/youtube.py:26-37` — `_is_transient_ytdlp_error` returns `False` for `isinstance(exc, _ExtractorError) and exc.expected`; `263-264` / `302-303` — `if not _is_transient_ytdlp_error(exc): raise` on first attempt |
| 17 | The yt-dlp update step is rate-limited by _UPDATE_THROTTLE_SECONDS | VERIFIED | `services/youtube.py:275` and `314` — both check `now - _last_ytdlp_update >= _UPDATE_THROTTLE_SECONDS` before calling `update_ytdlp`; reuses the existing throttle, no second update path |

**Score:** 17/17 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `config.py` | Phase 9 block with all 7 constants | VERIFIED | Lines 142-149: HEALTH_STRICT_STATUS, DB_COMMAND_TIMEOUT_SECONDS, INIT_WATCHDOG_TIMEOUT_SECONDS, SYNC_TIMEOUT_SECONDS, TASK_ERROR_CHANNEL_COOLDOWN_SECONDS, YTDLP_RETRY_BACKOFF_SECONDS, YTDLP_MAX_QUICK_RETRIES — all present with specified defaults |
| `bot.py` | Configurable /health status code + config-driven pool timeout + watchdog + sync retry + loop error handlers | VERIFIED | HEALTH_STRICT_STATUS in health handler, DB_COMMAND_TIMEOUT_SECONDS in create_pool, asyncio.wait_for on _initialize_once and tree.sync, _sync_retry_active guard, _background_sync_retry, four @loop.error handlers |
| `cogs/ops.py` | MusicCog degraded check + asyncio import + TimeoutError handlers | VERIFIED | `import asyncio` at line 27, MusicCog check at line 115-117 with _ready_done guard, TimeoutError catch before Exception in /leaderboard (line 166) and /stats (line 210) |
| `utils/tasks.py` | make_task fire-and-forget helper with done-callback | VERIFIED | New file, 159 lines, exports `make_task`, `_on_task_done`, `_post_task_error`, `_background_tasks`, `_last_task_error_post` |
| `cogs/music.py` | Three bare create_task sites replaced with make_task | VERIFIED | `from utils.tasks import make_task` at line 47; make_task at lines 622, 629, 764; bare asyncio.create_task at lines 889, 1481 unchanged |
| `services/youtube.py` | _is_transient_ytdlp_error + bounded-retry async_search / async_extract | VERIFIED | `_ExtractorError` import at line 14, `_is_transient_ytdlp_error` at line 26, rewritten async_search at line 245, rewritten async_extract at line 287 |
| `tests/test_tasks.py` | Unit tests for done-callback behavior | VERIFIED | New file, 12 tests across 4 test classes — all pass |
| `tests/test_youtube.py` | Retry/classifier tests (3 new test classes) | VERIFIED | TestIsTransientYtdlpError (3 tests), TestAsyncSearchRetry (5 tests), TestAsyncExtractRetry (5 tests) — all 13 pass |
| `tests/test_config.py` | Phase 9 constant assertions | VERIFIED | TestPhase9Constants class with 9 test methods + 3 flat alias functions; existing K-04 unchanged guard present |
| `tests/test_health_endpoint.py` | MusicCog-missing, startup-no-false-degraded, 503/200 tests | VERIFIED | test_musiccog_missing_post_init, test_startup_no_false_degraded, test_status_503_strict_mode, test_status_200_legacy_mode — all 4 pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `bot.py health()` | `config.HEALTH_STRICT_STATUS` | `getattr(config, 'HEALTH_STRICT_STATUS', True)` | WIRED | `bot.py:227` — exact pattern present |
| `bot.py asyncpg.create_pool` | `config.DB_COMMAND_TIMEOUT_SECONDS` | `command_timeout` kwarg | WIRED | `bot.py:326` — `command_timeout=config.DB_COMMAND_TIMEOUT_SECONDS` |
| `cogs/ops.py gather_bot_metrics` | `bot.cogs['MusicCog']` | guarded cog-presence check after _ready_done | WIRED | `cogs/ops.py:115-117` |
| `cogs/music.py call sites` | `utils.tasks.make_task` | import + call replacing asyncio.create_task | WIRED | `make_task(` appears at 3 call sites (lines 622, 629, 764) |
| `utils.tasks._on_task_done` | `config.TASK_ERROR_CHANNEL_COOLDOWN_SECONDS` | monotonic dedup window per error key | WIRED | `utils/tasks.py:122` — explicit config reference |
| `utils.tasks._post_task_error` | `bot.log_to_discord` | best-effort embed post | WIRED | `utils/tasks.py:156` — `await bot.log_to_discord(embed)` inside try/except |
| `bot.py on_ready` | `config.INIT_WATCHDOG_TIMEOUT_SECONDS` | asyncio.wait_for wrapping _initialize_once | WIRED | `bot.py:277-279` |
| `bot.py sync sites` | `config.SYNC_TIMEOUT_SECONDS` | asyncio.wait_for wrapping bot.tree.sync | WIRED | `bot.py:456,525,541,773,784` |
| `bot.py @loop.error handlers` | `config.TASK_ERROR_CHANNEL_COOLDOWN_SECONDS` | `_post_loop_error` monotonic dedup | WIRED | `bot.py:576` — explicit config reference in `_post_loop_error` |
| `services/youtube.py async_search / async_extract` | `config.YTDLP_MAX_QUICK_RETRIES / config.YTDLP_RETRY_BACKOFF_SECONDS` | bounded retry loop | WIRED | `services/youtube.py:256,265,270,295,304,309` |
| `services/youtube.py retry fallback` | `update_ytdlp + _UPDATE_THROTTLE_SECONDS` | throttled self-update reused from download() | WIRED | `services/youtube.py:275,277,314,316` |
| `services/youtube.py _is_transient_ytdlp_error` | `yt_dlp.utils.ExtractorError.expected` | permanent-vs-transient classification | WIRED | `services/youtube.py:36` — `isinstance(exc, _ExtractorError) and exc.expected` |

### Data-Flow Trace (Level 4)

Not applicable — Phase 9 adds reliability infrastructure (error routing, timeouts, retry loops), not user-visible data rendering. No artifacts render dynamic data from a fetched source.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 7 Phase 9 config constants have correct defaults | `python -c "import config; assert config.HEALTH_STRICT_STATUS is True; assert config.DB_COMMAND_TIMEOUT_SECONDS == 30; assert config.INIT_WATCHDOG_TIMEOUT_SECONDS == 120; assert config.SYNC_TIMEOUT_SECONDS == 30; assert config.TASK_ERROR_CHANNEL_COOLDOWN_SECONDS == 300; assert config.YTDLP_RETRY_BACKOFF_SECONDS == 1.0; assert config.YTDLP_MAX_QUICK_RETRIES == 2"` | exit 0 | PASS |
| make_task imports without circular import | `python -c "from utils.tasks import make_task"` | exit 0 | PASS |
| All modified files parse as valid Python | `python -c "import ast; [ast.parse(open(f).read()) for f in ['bot.py','cogs/ops.py','services/youtube.py','cogs/music.py']]"` | exit 0 | PASS |
| Phase 9 targeted test suite | `python -m pytest tests/test_config.py tests/test_health_endpoint.py tests/test_tasks.py tests/test_youtube.py -q` | 67 passed, 4 warnings | PASS |
| Full non-integration test suite (regression gate) | `python -m pytest tests/ -q -k "not integration"` | 353 passed, 64 skipped, 4 warnings | PASS |

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` probes exist for this phase. Live-bot probes are manually deferred to Phase 10 per all four plan documents.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| REL-01 | 09-01 | /health reports degraded (non-200) when MusicCog failed or core subsystem is down | SATISFIED | bot.py:225-230 (503 on degraded), cogs/ops.py:115-117 (MusicCog check), 4 new health endpoint tests pass |
| REL-02 | 09-02, 09-03 | Fire-and-forget background tasks attach done-callback that logs exceptions; @tasks.loop loops have @loop.error handlers | SATISFIED | utils/tasks.py make_task, 3 call sites in music.py, 4 @loop.error handlers in bot.py, 12 test_tasks.py tests pass |
| REL-03 | 09-03 | Startup sync handles failure/timeout; bot comes online with existing commands; retries in background | SATISFIED | bot.py _background_sync_retry, wait_for on all sync calls, _sync_retry_active guard |
| REL-04 | 09-03 | on_ready re-entry guard cannot get permanently stuck on hang | SATISFIED | bot.py:277-295 asyncio.wait_for watchdog + TimeoutError branch before Exception |
| REL-05 | 09-01 | DB queries enforce timeout; slow /leaderboard or /stats shows personality message | SATISFIED | bot.py:326 command_timeout config-driven, cogs/ops.py TimeoutError handlers with static messages |
| REL-06 | 09-04 | YouTube search/extract self-heal on transient failure with bounded retry | SATISFIED | services/youtube.py bounded retry + _is_transient_ytdlp_error classifier, 13 new test_youtube.py tests pass |

No orphaned requirements found — REQUIREMENTS.md maps REL-01 through REL-06 exclusively to Phase 9, all 6 are covered by the four plans.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | No TBD/FIXME/XXX/TODO markers found in any Phase 9 modified file | — | — |
| None | — | No stub patterns (empty returns, placeholder data, disconnected props) found | — | — |

No debt markers or stub patterns identified in any of the 10 files modified by this phase.

**Code review warnings (from 09-REVIEW.md — non-blocking for Phase 9):**

- **WR-01** (WARNING): `_play_track` dispatched as bare `asyncio.create_task` at `cogs/music.py:889,1481` — no strong reference, no done-callback. The plan explicitly designated this as intentional (Pitfall 4: `_play_track` already handles all its failures internally; a callback would double-log handled track errors). The code reviewer recommends reconsidering this in Phase 10.
- **WR-03** (WARNING): `/health` runs a DB probe with no explicit timeout on `pool.acquire()` — only bounded by `command_timeout=30`. Against a cold Neon DB or exhausted pool, the health check itself can take up to 30s. Not introduced by Phase 9 (the probe existed before); not a correctness issue for Phase 9's truth-telling goal.
- **WR-04** (INFO): Partial-init cleanup (`on_ready` watchdog/exception path) deletes `bot.pool` while already-started background loops may attempt DB access, producing recurring errors until the next successful retry. Edge case in the init-failure path; does not affect the nominal code path.
- **WR-05** (INFO): `test_health_endpoint.py` mutates the shared `MagicMock` class via `type(bot).__contains__`; potential cross-test pollution if suite execution order changes. Tests currently pass.

### Human Verification Required

All six items below are explicitly documented as manual-only in `09-VALIDATION.md` and deferred to Phase 10 in all four plan documents. The code implementations are verified; live-bot confirmation is still pending.

### 1. /health truthful HTTP 503 end-to-end

**Test:** Boot the bot, force MusicCog to fail to load (or bring DB unreachable). Run `curl -s -o /dev/null -w "%{http_code}" localhost:<port>/health`.
**Expected:** Returns 503 with `{"status":"degraded","reasons":["MusicCog not loaded"]}`. Then set `HEALTH_STRICT_STATUS=false` in the environment and confirm 200.
**Why human:** Requires a live aiohttp server bound to a port, the bot's health server task running, and cog-load state from a real Discord connection.

### 2. Crashing fire-and-forget task surfaces in logs and Discord error channel

**Test:** Force `_prefetch_next_track` or `_post_auto_lyrics` to raise (inject a failing mock). Trigger it via `/play`. Observe `dexter.log` and `ERROR_LOG_CHANNEL_ID` in Discord. Repeat the same failure within 5 minutes.
**Expected:** One `log.error` line per occurrence. One embed in the error channel for the first failure. No duplicate embed within the cooldown window (throttled by `TASK_ERROR_CHANNEL_COOLDOWN_SECONDS=300`).
**Why human:** Requires a live bot with `ERROR_LOG_CHANNEL_ID` configured and a running event loop to observe `asyncio.ensure_future` scheduling and Discord channel delivery.

### 3. Startup sync failure: bot comes online, retries in background

**Test:** Inject a delay or exception into `bot.tree.sync`. Start the bot. Attempt any already-registered slash command.
**Expected:** Bot reaches the ready state. Warning logged. The slash command works (using already-registered set). A single background retry chain fires (not multiple concurrent chains if multiple shards fire READY).
**Why human:** Requires a live Discord gateway to inject sync failure; multi-shard READY event race cannot be reliably reproduced without a live connection.

### 4. on_ready watchdog fires on hung _initialize_once

**Test:** Inject `await asyncio.sleep(999)` (no exception) into `_initialize_once`. Observe startup logs and a second READY event.
**Expected:** `asyncio.wait_for` watchdog fires after `INIT_WATCHDOG_TIMEOUT_SECONDS=120s`. Log: "on_ready init hung for 120s; cleaning up pool to retry on next READY event". `_ready_initializing` resets. Next READY event retries successfully.
**Why human:** Requires a live bot process; task cancellation on a truly-hung coroutine cannot be simulated in unit tests without the full asyncio event loop and bot runtime.

### 5. Slow DB query hits timeout and shows personality message

**Test:** Run `/leaderboard` or `/stats` while Neon DB is waking from scale-to-zero (first hit after idle). Observe the user-facing response and bot responsiveness during the timeout.
**Expected:** User sees "database is being slow. try again in a bit." (leaderboard) or "stats are taking too long. try again in a bit." (stats). Bot continues to respond to other commands.
**Why human:** Requires a live asyncpg pool against Neon with a genuine query exceeding `command_timeout=30s`; cannot simulate asyncpg client-side timeout behavior in unit tests.

### 6. YouTube transient retry + permanent bypass

**Test:** Force a transient `search()`/`extract()` failure (network blip simulation). Then use a known video-unavailable URL that produces `ExtractorError(expected=True)`.
**Expected:** Transient: bounded quick retry (up to `YTDLP_MAX_QUICK_RETRIES=2`) recovers; no update call on first retries. Permanent (`ExtractorError.expected=True`): propagates immediately, no retry, no `update_ytdlp` call.
**Why human:** Requires a live yt-dlp executor and a real (or reliably simulated) network failure to validate the timing and retry behavior; the unit tests cover the decision logic but not the full executor path.

### Gaps Summary

No blocking gaps. All 17 must-haves from all four plans are verified in the codebase. Commits `18806e7`, `b7aa948`, `c136a8e` (plan 01), `bfd2ed9`, `f563896`, `1f9e836` (plan 02), `7f857f8`, `53cf00d`, `3e89412` (plan 03), `fef6ed1`, `afa4eec` (plan 04) are all present in git log.

The 6 human verification items are live integration checks explicitly deferred to Phase 10 by all four plan documents and documented in `09-VALIDATION.md`. They are pending but not blockers — the code that enables these behaviors is fully implemented and unit-tested.

---

_Verified: 2026-06-26T16:00:00Z_
_Verifier: Claude (gsd-verifier)_
