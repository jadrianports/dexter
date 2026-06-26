---
phase: "09"
plan: "04"
subsystem: reliability-ops
tags: [yt-dlp, retry, self-heal, bounded-retry, classifier, REL-06]
dependency_graph:
  requires:
    - config.YTDLP_MAX_QUICK_RETRIES
    - config.YTDLP_RETRY_BACKOFF_SECONDS
    - services.youtube.update_ytdlp
    - services.youtube._UPDATE_THROTTLE_SECONDS
  provides:
    - services.youtube._is_transient_ytdlp_error
    - services.youtube.YouTubeService.async_search (bounded-retry + throttled self-heal)
    - services.youtube.YouTubeService.async_extract (bounded-retry + throttled self-heal)
  affects:
    - services/youtube.py
    - tests/test_youtube.py
tech_stack:
  added: []
  patterns:
    - bounded-retry loop with exponential backoff (mirrors download() self-heal)
    - _is_transient_ytdlp_error permanent-vs-transient classifier (ExtractorError.expected heuristic)
    - throttled yt-dlp self-update reuse (same _UPDATE_THROTTLE_SECONDS / update_ytdlp path)
    - TDD RED/GREEN cycle (test(09-04) commit before feat(09-04))
key_files:
  created: []
  modified:
    - services/youtube.py (_is_transient_ytdlp_error + rewritten async_search/async_extract)
    - tests/test_youtube.py (TestIsTransientYtdlpError + TestAsyncSearchRetry + TestAsyncExtractRetry)
decisions:
  - "_is_transient_ytdlp_error returns False only for ExtractorError.expected=True — conservative fallback treats all other errors as transient so no valid retry is ever skipped (A1/A2 [ASSUMED])"
  - "bounded-retry loop structure reuses existing update_ytdlp() + _UPDATE_THROTTLE_SECONDS — no second update path added"
  - "asyncio.sleep(YTDLP_RETRY_BACKOFF_SECONDS * (attempt+1)) provides linear backoff: 1s, 2s for the default YTDLP_MAX_QUICK_RETRIES=2"
  - "async_extract uses functools.partial(self.extract, url) to match async_search structure for symmetry and testability"
metrics:
  duration_seconds: 546
  completed_date: "2026-06-26"
  tasks_completed: 1
  tasks_total: 1
  files_changed: 2
---

# Phase 9 Plan 04: YouTube Search/Extract Self-Heal Summary

Bounded-retry + throttled yt-dlp self-update for `async_search` and `async_extract`, closing the self-heal gap between `download()` (already resilient since Phase 3) and the search/extract paths (which previously propagated the first failure immediately).

## What Was Built

### Task 1 — _is_transient_ytdlp_error classifier + bounded-retry async_search / async_extract (REL-06)

**`services/youtube.py`:**

Added `from yt_dlp.utils import ExtractorError as _ExtractorError` import.

Added module-level pure function `_is_transient_ytdlp_error(exc: Exception) -> bool`:
- Returns `False` for `ExtractorError` where `exc.expected=True` (video unavailable, age-restricted — permanent condition, must not retry)
- Returns `True` for all other exceptions (network blips, unexpected extractor failures — transient candidates)
- Conservative: any non-`expected` error is treated as transient, so no retry budget is ever skipped on a recoverable error (Assumption A1/A2 [ASSUMED])

Rewrote `async_search` as a bounded-retry loop:
- `range(config.YTDLP_MAX_QUICK_RETRIES + 1)` iterations (0, 1, 2 with defaults)
- Each iteration runs `loop.run_in_executor(None, functools.partial(self.search, query, count))`
- On exception: if not transient → re-raise immediately; if `attempt < YTDLP_MAX_QUICK_RETRIES` → log warning + `await asyncio.sleep(YTDLP_RETRY_BACKOFF_SECONDS * (attempt + 1))`
- On final quick-retry failure (attempt == YTDLP_MAX_QUICK_RETRIES): checks `_UPDATE_THROTTLE_SECONDS` and — only if outside window — calls `await loop.run_in_executor(None, update_ytdlp)`, then one final `run_in_executor` attempt; re-raises if that fails too
- `update_ytdlp()` already sets `_last_ytdlp_update = time.monotonic()` internally; no second throttle path needed

Rewrote `async_extract` with identical loop structure, substituting `functools.partial(self.extract, url)` for `functools.partial(self.search, query, count)`.

**`tests/test_youtube.py`:**

Added `AsyncMock` to imports.

Added three new test classes (TDD RED/GREEN cycle):

`TestIsTransientYtdlpError` (3 tests):
- `ExtractorError(expected=True)` → `False` (permanent)
- `ExtractorError(expected=False)` → `True` (transient)
- `Exception(...)` → `True` (transient)

`TestAsyncSearchRetry` (5 tests):
- `test_success_on_first_attempt` — no retry, no sleep, no update
- `test_transient_failure_retries_and_recovers` — fails once, succeeds on retry (1 sleep, 0 updates)
- `test_permanent_extractor_error_propagates_immediately` — called once, no sleep, no update
- `test_exhausted_retries_calls_update_once` — update called exactly once; total search calls == `YTDLP_MAX_QUICK_RETRIES + 2`
- `test_exhausted_retries_skips_update_when_throttled` — update not called when within throttle window

`TestAsyncExtractRetry` (5 tests): identical coverage to `TestAsyncSearchRetry` for the extract path.

## Verification

- `python -m pytest tests/test_youtube.py -q` — 30 passed
- `python -m pytest tests/ -q -k "not integration"` — 353 passed, 64 skipped (exit 0)
- RED commit `fef6ed1` confirmed 7 failures before implementation
- GREEN commit `afa4eec` confirmed all tests pass after implementation

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — no stubs or placeholder data introduced.

## Threat Flags

T-09-05 and T-09-11 mitigated as specified:
- Failure messages in `log.warning` / `log.error` include only the exception string (yt-dlp error text, which contains public YouTube URLs — no tokens, DSNs, or user data)
- `_is_transient_ytdlp_error` skips retry for `expected=True`; update fallback is rate-limited by `_UPDATE_THROTTLE_SECONDS` (≤ once/hour) regardless

No new threat surface beyond what the plan's threat model covers.

## TDD Gate Compliance

- `test(09-04)` RED commit: `fef6ed1` — 7 failures confirmed
- `feat(09-04)` GREEN commit: `afa4eec` — all 30 tests pass
- No REFACTOR commit needed (implementation is clean as-written)

## Self-Check: PASSED

Files verified:
- `services/youtube.py` — `_is_transient_ytdlp_error` present, `async_search` rewritten with retry loop, `async_extract` rewritten with identical loop structure
- `tests/test_youtube.py` — `AsyncMock` import present; `TestIsTransientYtdlpError`, `TestAsyncSearchRetry`, `TestAsyncExtractRetry` present and passing

Commits verified:
- `fef6ed1` test(09-04): add failing tests for _is_transient_ytdlp_error + async_search/extract retry (REL-06)
- `afa4eec` feat(09-04): bounded-retry + throttled self-heal for async_search / async_extract (REL-06)
