---
phase: "09"
plan: "02"
subsystem: reliability-ops
tags: [fire-and-forget, done-callback, exception-surfacing, discord-error-channel, dedup, tdd]
dependency_graph:
  requires:
    - config.TASK_ERROR_CHANNEL_COOLDOWN_SECONDS (09-01)
  provides:
    - utils.tasks.make_task
    - utils.tasks._on_task_done
    - utils.tasks._post_task_error
    - utils.tasks._background_tasks
    - utils.tasks._last_task_error_post
  affects:
    - cogs/music.py (auto-lyrics, prefetch, auto-queue tasks now surface exceptions)
tech_stack:
  added: []
  patterns:
    - "-inf sentinel in dedup dict: first post always goes through regardless of clock value in tests"
    - "functools.partial(_on_task_done, bot=bot) to bake bot reference into done-callback"
    - "asyncio.ensure_future to schedule async channel post from synchronous done-callback"
    - "Strong-reference set to prevent GC of in-flight tasks (asyncio docs pattern)"
    - "Truncate exc message to 500 chars before embed post (T-09-03)"
key_files:
  created:
    - utils/tasks.py
    - tests/test_tasks.py
  modified:
    - cogs/music.py (import + 3 call-site replacements)
decisions:
  - "Use -float(inf) as default sentinel in _last_task_error_post.get() so the first post always goes through even when time.monotonic() is 0.0 in tests (clock-independent correctness)"
  - "_play_track create_task calls (lines 889/1481) left as bare asyncio.create_task per Pitfall 4 — they already handle failures internally; a done-callback would double-log handled track errors"
  - "utils/tasks.py imports only asyncio/functools/time/discord/config/log — no cogs.* or bot imports, ensuring circular-import-free importability from music.py"
metrics:
  duration_seconds: 620
  completed_date: "2026-06-26"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 3
---

# Phase 9 Plan 02: Fire-and-Forget Task Visibility Summary

`utils/tasks.py` `make_task` helper with done-callback that logs every exception to dexter.log and posts a throttled, sanitized embed to the Discord error channel; three bare `asyncio.create_task` sites in `cogs/music.py` replaced with `make_task`.

## What Was Built

### Task 1 — TDD: utils/tasks.py + tests/test_tasks.py (REL-02)

**`utils/tasks.py` (new file, 158 lines):**

- `_background_tasks: set[asyncio.Task]` — strong-reference set prevents GC of in-flight tasks (asyncio docs warning).
- `_last_task_error_post: dict[str, float]` — dedup map keyed on `"{task_name}:{ExcType}"`, using `-float("inf")` as the absence sentinel so the first post always goes through regardless of `time.monotonic()` value.
- `make_task(coro, *, name=None, bot=None) -> asyncio.Task` — public helper: `asyncio.create_task(coro, name=name)`, adds to `_background_tasks`, attaches `_background_tasks.discard` and `functools.partial(_on_task_done, bot=bot)` as done-callbacks, returns task.
- `_on_task_done(task, *, bot=None)` — synchronous done-callback: Pitfall 1 guard (`task.cancelled()` before `task.exception()`), `log.error` with `exc_info` on any exception, dedup check, `asyncio.ensure_future(_post_task_error(...))` to schedule the async channel post.
- `_post_task_error(bot, task_name, exc)` — async channel poster: guards `hasattr(bot, "log_to_discord")`, builds embed with `title=f"Background Task Error: {task_name}"` and `description=f"{type(exc).__name__}: {exc_str[:500]}"`, `await bot.log_to_discord(embed)` inside `try/except Exception: pass`.

Security (T-09-03): embed carries task name + exception type/message only — no guild IDs, user data, tokens, or DSNs.

**`tests/test_tasks.py` (new file, 12 tests):**

TDD RED/GREEN cycle:
- `TestCancelledTask::test_cancelled_returns_early` — verifies Pitfall 1 guard: `exception()` side_effect raises `CancelledError`; if the guard is absent the test raises.
- `TestExceptionTask::test_exception_logged_with_exc_info` — asserts `log.error` called with `exc_info=exc`.
- `TestExceptionTask::test_success_task_not_logged` — success path is silent.
- `TestExceptionTask::test_bot_none_no_channel_post` — `asyncio.ensure_future` not called when bot is None.
- `TestDedupThrottle::test_dedup_throttles_second_post` — same key within window → only one `ensure_future` call.
- `TestDedupThrottle::test_dedup_allows_post_after_window` — after cooldown, second call is allowed.
- `TestDedupThrottle::test_dedup_different_keys_both_post` — distinct keys both post.
- `TestPostTaskError::test_description_truncated` — 1000-char message truncated to ≤600-char description.
- `TestPostTaskError::test_description_contains_type_and_message` — type name and message text present.
- `TestPostTaskError::test_no_guild_user_data_in_embed` — embed has no extra fields (T-09-03).
- `TestPostTaskError::test_bot_without_log_to_discord_returns_early` — silent on missing attribute.
- `TestPostTaskError::test_log_to_discord_exception_is_swallowed` — reporter exception silenced (T-09-07).

### Task 2 — Wire make_task into cogs/music.py

Added `from utils.tasks import make_task` to the import block (line 47).

Replaced exactly three bare fire-and-forget sites:
- Line 622: `make_task(self._post_auto_lyrics(guild, track), name="auto-lyrics", bot=self.bot)`
- Line 629: `make_task(self._prefetch_next_track(guild, next_tracks[0], current_gen), name="prefetch", bot=self.bot)`
- Line 764: `make_task(ai_cog.try_auto_queue(guild), name="auto-queue", bot=self.bot)`

Lines 889 and 1481 (`asyncio.create_task(self._play_track(...))`) remain as bare `asyncio.create_task` per Pitfall 4 — `_play_track` handles all its failures internally; a done-callback would double-log handled track errors and flood the error channel.

## Verification

- `python -c "from utils.tasks import make_task"` — exits 0 (no circular import)
- `python -m pytest tests/test_tasks.py -v` — 12 passed
- `python -c "import ast; ast.parse(open('cogs/music.py', encoding='utf-8').read())"` — exits 0
- `python -m pytest tests/test_tasks.py tests/test_config.py tests/test_health_endpoint.py tests/test_queue.py tests/test_autoqueue_playback.py tests/test_now_playing_refresh.py -q` — 83 passed

## Deviations from Plan

**1. [Rule 1 - Bug] Fixed dedup sentinel: 0.0 → -float("inf")**
- **Found during:** GREEN phase — all 3 dedup tests failed after initial implementation
- **Issue:** `_last_task_error_post.get(key, 0.0)` returns `0.0` for absent keys. With `time.monotonic()` patched to `0.0` in tests, `0.0 - 0.0 = 0 < 300` triggered the cooldown on the FIRST call, suppressing the first post.
- **Fix:** Changed default to `-float("inf")` so `now - (-inf) = inf ≥ any cooldown` → first post always goes through. Production behavior is identical since real `time.monotonic()` values (seconds since boot, typically millions) are always >> 300.
- **Files modified:** `utils/tasks.py` (one line change in `_on_task_done`)
- **Commit:** f563896

## Known Stubs

None — no stubs or placeholder data introduced.

## Threat Flags

No new threat surface beyond what the plan's threat model covers. All three threat mitigations implemented:
- T-09-03: embed carries task name + `type(exc).__name__` + truncated message only (no guild IDs, user data, tokens).
- T-09-06: dedup per `(task_name, exc_type)` key within `TASK_ERROR_CHANNEL_COOLDOWN_SECONDS` (5 min).
- T-09-07: `_post_task_error` wraps `log_to_discord` in `try/except Exception: pass`.

## Self-Check: PASSED

Files verified:
- `utils/tasks.py` — FOUND (158 lines, exports make_task, _on_task_done, _post_task_error, _background_tasks, _last_task_error_post)
- `tests/test_tasks.py` — FOUND (12 tests, 283 lines)
- `cogs/music.py` — make_task import at line 47 FOUND; 3 call sites FOUND; _play_track bare create_task at lines 889/1481 FOUND (unchanged)

Commits verified:
- `bfd2ed9` test(09-02): add failing tests for make_task done-callback
- `f563896` feat(09-02): implement make_task fire-and-forget helper (REL-02)
- `1f9e836` feat(09-02): wire make_task into three bare create_task sites (REL-02)
