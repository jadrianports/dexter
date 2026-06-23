---
phase: "06-speed-caching"
plan: "03"
subsystem: "audio-service + tests"
tags: [phase6, perf, lfu-eviction, download-timeout, asyncio, tdd]
dependency_graph:
  requires: ["06-01"]
  provides:
    - "services/audio.py get_source: asyncio.wait_for around tier-2 download with TimeoutError → stream fallback"
    - "services/audio.py cleanup_cache: async LFU with pool + protected_video_ids guard"
    - "tests/test_audio.py TestLFUEviction + TestDownloadTimeout (6 new tests)"
  affects:
    - "Plan 04: cleanup_cache call site in cogs/ must pass pool + protected_video_ids set"
tech_stack:
  added: []
  patterns:
    - "asyncio.wait_for(coro, timeout=DOWNLOAD_TIMEOUT_SECONDS) → except asyncio.TimeoutError: path=None"
    - "async def cleanup_cache(self, pool, protected_video_ids: set[str]) LFU via song_history play counts"
    - "eviction_key(f): (float('inf'), 0) for protected; (play_count, mtime) for evictable"
    - "MagicMock cm with __aenter__/__aexit__ AsyncMock for async context manager testing"
key_files:
  created: []
  modified:
    - services/audio.py
    - tests/test_audio.py
decisions:
  - "asyncio.wait_for wraps async_download at tier-2; TimeoutError sets path=None → falls through to existing stream tier with no structural change"
  - "cleanup_cache early returns before pool.acquire() when total <= cap — pool never called on under-cap check"
  - "_make_pool_mock uses MagicMock (not AsyncMock) for pool.acquire() so it returns a sync context manager object (not a coroutine)"
metrics:
  duration: "~20 min"
  completed_date: "2026-06-24"
  tasks_completed: 2
  files_created: 0
  files_modified: 2
---

# Phase 06 Plan 03: Download Timeout + LFU Cache Eviction Summary

**One-liner:** `asyncio.wait_for(DOWNLOAD_TIMEOUT_SECONDS)` bounds tier-2 download in `get_source` with stream fallback on timeout; `cleanup_cache` rewritten as async LFU keyed on `song_history` play counts with `protected_video_ids` guard.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | asyncio.wait_for timeout in get_source + async LFU cleanup_cache rewrite | 98fe742 | services/audio.py |
| 2 | TestLFUEviction + TestDownloadTimeout in tests/test_audio.py | 17b9005 | tests/test_audio.py |

## What Was Built

### Task 1 — services/audio.py

**Download timeout (PERF-04 / D-10/D-11):**

`get_source` tier-2 download now wrapped in `asyncio.wait_for(..., timeout=config.DOWNLOAD_TIMEOUT_SECONDS)`. On `asyncio.TimeoutError`, a warning is logged and `path` is set to `None`, falling through to the existing tier-3 stream path (FFmpegPCMAudio with fresh stream URL from `async_extract`). The orphan `run_in_executor` thread drains harmlessly (Pitfall 3 / D-10 discretion). The opus-passthrough early path (`if not use_opts: return discord.FFmpegOpusAudio(str(cached))`) is unchanged (D-12). `import asyncio` added at module top.

**Async LFU cleanup_cache (PERF-05 / D-12/D-13):**

`cleanup_cache` rewritten as `async def cleanup_cache(self, pool, protected_video_ids: set[str]) -> None`. New behavior:

1. Early returns preserved: empty glob → return; total <= max → return (pool never acquired on under-cap).
2. `async with pool.acquire() as conn:` fetches `SELECT url, COUNT(*) AS plays FROM song_history GROUP BY url`.
3. Builds `play_counts: dict[str, int]` by extracting video_id from `v=` YouTube URLs.
4. `eviction_key(f)`: returns `(float("inf"), 0)` for protected files; `(play_counts.get(vid, 0), f.stat().st_mtime)` for evictable files.
5. Iterates sorted files: skips if in `protected_video_ids`, unlinks otherwise, logs `cache evict video_id= play_count= size=`.

### Task 2 — tests/test_audio.py

**TestCacheCleanup renamed to TestLFUEviction** with all-new async tests using a `_make_pool_mock` helper (MagicMock with `__aenter__`/`__aexit__` AsyncMock returning mock rows):

- `test_evicts_lowest_play_count`: 3 × 512KB files totalling 1.5MB over 1MB cap; pool returns play counts 1/3/5; asserts lowest-count (play_count=1) file is removed.
- `test_protected_not_evicted`: protected video_id has play_count=0 (not in history); survives even though it would otherwise be evicted first; unprotected file with play_count=5 is removed to bring total under cap.
- `test_tiebreak_oldest`: two files with equal play_count=2; different mtimes via `os.utime`; asserts older-mtime file is evicted first.
- `test_under_cap_no_eviction`: total 1KB under 2048MB cap; asserts file survives and `pool.acquire` is never called.

**TestDownloadTimeout** (2 tests):

- `test_timeout_falls_back_to_stream`: patches `services.audio.asyncio.wait_for` with `side_effect=asyncio.TimeoutError`; `async_extract` returns a stream URL; asserts `FFmpegPCMAudio` is called with that stream URL (stream tier reached).
- `test_timeout_warning_logged`: same patch; asserts at least one WARNING log message contains "timeout" or "falling back".

**Total: 14 tests in test_audio.py — all pass offline.**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Track constructor uses `duration_seconds` + `requested_by`, not `duration`**
- **Found during:** Task 2 — first test run failure (`TypeError: Track.__init__() got an unexpected keyword argument 'duration'`)
- **Issue:** Plan's test pseudocode used `duration=120, thumbnail=None, artist=None` but the `Track` dataclass requires `duration_seconds`, `requested_by` (required field), plus `artist`.
- **Fix:** Updated Track instantiation in both TestDownloadTimeout tests to use `duration_seconds=120, requested_by=12345`.
- **Files modified:** `tests/test_audio.py`
- **Commit:** 17b9005 (included in Task 2 commit)

**2. [Rule 1 - Bug] MagicMock pool: AsyncMock pool.acquire() returns coroutine, not async context manager**
- **Found during:** Task 2 — second test run failure (`TypeError: 'coroutine' object does not support the asynchronous context manager protocol`)
- **Issue:** `_make_pool_mock` initially used `AsyncMock` for the pool, which made `pool.acquire()` return a coroutine rather than an async context manager object.
- **Fix:** Rewrote `_make_pool_mock` to use `MagicMock(return_value=cm)` for `pool.acquire`, where `cm` is a `MagicMock` with `__aenter__ = AsyncMock(return_value=conn_mock)` and `__aexit__ = AsyncMock(return_value=False)`.
- **Files modified:** `tests/test_audio.py`
- **Commit:** 17b9005

**3. [Rule 1 - Bug] `MagicMock(spec=discord.FFmpegPCMAudio)` fails when discord.FFmpegPCMAudio is already patched**
- **Found during:** Task 2 — third test run failure (`InvalidSpecError: Cannot spec a Mock object`)
- **Issue:** Inside `patch("services.audio.discord.FFmpegPCMAudio")`, assigning `mock_ffmpeg.return_value = MagicMock(spec=discord.FFmpegPCMAudio)` tried to spec against the already-mocked class.
- **Fix:** Changed to `MagicMock()` without spec.
- **Files modified:** `tests/test_audio.py`
- **Commit:** 17b9005

## Verification Results

```
grep -v '^#' services/audio.py | grep -c 'asyncio.wait_for'
# 1

python -c "import inspect, asyncio, services.audio as a; assert inspect.iscoroutinefunction(a.AudioService.cleanup_cache); sig=str(inspect.signature(a.AudioService.cleanup_cache)); assert 'protected_video_ids' in sig; print('OK')"
# OK

python -m pytest tests/test_audio.py -x -q
# 14 passed, 1 warning in 0.12s
```

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced. `cleanup_cache` reads `song_history` via `SELECT url, COUNT(*) AS plays FROM song_history GROUP BY url` — read-only, no user-supplied params, no interpolation (T-06-06 mitigated as designed). No additional threat flags.

## Known Stubs

None — both implementations are complete. Plan 04 will wire `cleanup_cache` call sites (hourly task in bot.py/cogs) by building `protected_video_ids` from queue + `_prefetch_video_id` and passing the pool, as noted in the plan's `<artifacts_produced>` note.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| services/audio.py contains `asyncio.wait_for` | FOUND (grep returns 1) |
| services/audio.py `cleanup_cache` is async with `protected_video_ids` param | FOUND (inspect check OK) |
| tests/test_audio.py defines `class TestLFUEviction` | FOUND |
| tests/test_audio.py defines `class TestDownloadTimeout` | FOUND |
| Commit 98fe742 | FOUND |
| Commit 17b9005 | FOUND |
| 06-03-SUMMARY.md | FOUND |
