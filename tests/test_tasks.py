"""Tests for utils/tasks.py make_task done-callback helper (REL-02 / D-03/D-04).

Covers the five behavioral requirements from 09-02-PLAN:

    test_cancelled_returns_early          — task.cancelled() True → no exception() call, no log
    test_exception_logged_with_exc_info   — raising task → log.error called with exc_info
    test_bot_none_no_channel_post         — bot=None → no asyncio.ensure_future scheduled
    test_dedup_throttles_second_post      — same error key within cooldown → only first post
    test_dedup_allows_post_after_window   — same error key after cooldown → second post allowed
    test_post_error_description_truncated — embed desc truncated; contains type name + message
    test_post_error_no_guild_user_data    — embed has only task name + exc info, no extra fields
    test_post_error_no_log_to_discord     — bot without log_to_discord → returns without error

Test approach: drive _on_task_done and _post_task_error directly with Mock task objects.
No real event loop required for cancelled/log/dedup paths; asyncio paths use pytest-asyncio.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task(
    *,
    cancelled: bool = False,
    exc: Exception | None = None,
    name: str = "test-task",
) -> MagicMock:
    """Build a fake asyncio.Task for testing _on_task_done.

    If `cancelled=True`, calling exception() on the task raises asyncio.CancelledError
    (mirroring real asyncio behaviour — Pitfall 1 guard required).
    """
    task = MagicMock(spec=asyncio.Task)
    task.cancelled.return_value = cancelled
    task.get_name.return_value = name
    if cancelled:
        task.exception.side_effect = asyncio.CancelledError("exception() must not be called on a cancelled task")
    else:
        task.exception.return_value = exc
    return task


# ---------------------------------------------------------------------------
# Import target (will fail at collection time until utils/tasks.py is created)
# ---------------------------------------------------------------------------

from utils.tasks import _last_task_error_post, _on_task_done, _post_task_error  # noqa: E402

# ---------------------------------------------------------------------------
# _on_task_done — cancelled path
# ---------------------------------------------------------------------------


class TestCancelledTask:
    def test_cancelled_returns_early(self):
        """A cancelled task must return before calling exception() or log.error.

        If _on_task_done calls task.exception() without checking task.cancelled()
        first, it will raise asyncio.CancelledError (Pitfall 1) and the test fails.
        """
        task = _make_task(cancelled=True)

        with patch("utils.tasks.log") as mock_log:
            _on_task_done(task, bot=None)

        # Critical: exception() must NOT be called on a cancelled task
        task.exception.assert_not_called()
        # No error should be logged
        mock_log.error.assert_not_called()


# ---------------------------------------------------------------------------
# _on_task_done — exception path
# ---------------------------------------------------------------------------


class TestExceptionTask:
    def test_exception_logged_with_exc_info(self):
        """A raising task must call log.error with exc_info set to the exception."""
        exc = ValueError("something broke")
        task = _make_task(exc=exc, name="prefetch")

        with (
            patch("utils.tasks.log") as mock_log,
            patch("utils.tasks._post_task_error", return_value=None),
            patch("asyncio.ensure_future"),
        ):
            _on_task_done(task, bot=None)

        mock_log.error.assert_called_once()
        call_args = mock_log.error.call_args
        # exc_info must be passed as a keyword argument and match the exception
        assert call_args.kwargs.get("exc_info") is exc, f"Expected exc_info={exc!r}, got {call_args.kwargs}"

    def test_success_task_not_logged(self):
        """A task that completed successfully (exception() returns None) must not log."""
        task = _make_task(exc=None)

        with patch("utils.tasks.log") as mock_log:
            _on_task_done(task, bot=None)

        mock_log.error.assert_not_called()

    def test_bot_none_no_channel_post(self):
        """When bot is None, no channel post must be scheduled (no ensure_future call)."""
        exc = RuntimeError("crash")
        task = _make_task(exc=exc)

        with patch("utils.tasks.log"), patch("asyncio.ensure_future") as mock_ensure:
            _on_task_done(task, bot=None)

        mock_ensure.assert_not_called()


# ---------------------------------------------------------------------------
# _on_task_done — dedup throttle
# ---------------------------------------------------------------------------


class TestDedupThrottle:
    def _run_on_task_done(self, task, bot, monotonic_value: float):
        """Helper: run _on_task_done with a mocked monotonic time and patched helpers."""
        with (
            patch("utils.tasks.log"),
            patch("utils.tasks._post_task_error", return_value=None),
            patch("asyncio.ensure_future") as mock_ensure,
            patch("time.monotonic", return_value=monotonic_value),
        ):
            _on_task_done(task, bot=bot)
        return mock_ensure

    def test_dedup_throttles_second_post(self):
        """Two same-key errors within TASK_ERROR_CHANNEL_COOLDOWN_SECONDS → only one post."""
        import utils.tasks as tasks_mod

        exc = ValueError("boom")
        task = _make_task(exc=exc, name="auto-lyrics")
        bot = MagicMock()

        # Clear dedup state to ensure a clean slate
        tasks_mod._last_task_error_post.clear()

        # First call at t=0 → should schedule a post
        mock1 = self._run_on_task_done(task, bot, monotonic_value=0.0)
        assert mock1.call_count == 1, "First error should schedule a channel post"

        # Second call at t=1 (within 300s window) → should be throttled
        mock2 = self._run_on_task_done(task, bot, monotonic_value=1.0)
        assert mock2.call_count == 0, "Second error within cooldown should be throttled"

    def test_dedup_allows_post_after_window(self):
        """Same error key after TASK_ERROR_CHANNEL_COOLDOWN_SECONDS → second post allowed."""
        import config
        import utils.tasks as tasks_mod

        exc = TypeError("type error")
        task = _make_task(exc=exc, name="auto-queue")
        bot = MagicMock()

        tasks_mod._last_task_error_post.clear()

        cooldown = config.TASK_ERROR_CHANNEL_COOLDOWN_SECONDS

        # First call
        mock1 = self._run_on_task_done(task, bot, monotonic_value=0.0)
        assert mock1.call_count == 1, "First error should schedule a post"

        # Second call after the cooldown window expires
        mock2 = self._run_on_task_done(task, bot, monotonic_value=float(cooldown + 1))
        assert mock2.call_count == 1, "Error after cooldown window should schedule a new post"

    def test_dedup_different_keys_both_post(self):
        """Two different (task_name, exc_type) keys → both schedule a post."""
        import utils.tasks as tasks_mod

        bot = MagicMock()
        tasks_mod._last_task_error_post.clear()

        task_a = _make_task(exc=ValueError("boom"), name="auto-lyrics")
        task_b = _make_task(exc=RuntimeError("crash"), name="prefetch")

        mock_a = self._run_on_task_done(task_a, bot, monotonic_value=0.0)
        mock_b = self._run_on_task_done(task_b, bot, monotonic_value=0.0)

        assert mock_a.call_count == 1, "First unique key should post"
        assert mock_b.call_count == 1, "Different key should also post"


# ---------------------------------------------------------------------------
# _post_task_error — embed content and truncation
# ---------------------------------------------------------------------------


class TestPostTaskError:
    @pytest.mark.asyncio
    async def test_description_truncated(self):
        """Description is truncated when the exception message is very long (>500 chars)."""
        captured: list = []

        async def fake_log_to_discord(embed):
            captured.append(embed)

        bot = MagicMock()
        bot.log_to_discord = fake_log_to_discord

        long_msg = "x" * 1000
        exc = RuntimeError(long_msg)
        await _post_task_error(bot, "prefetch", exc)

        assert captured, "_post_task_error must call bot.log_to_discord"
        desc = captured[0].description
        # description must start with the exception type name
        assert desc.startswith("RuntimeError"), f"Expected type prefix, got: {desc[:50]}"
        # description must be bounded (500 char message cap + type name + ": " + ellipsis)
        assert len(desc) <= 600, f"Description too long: {len(desc)} chars"

    @pytest.mark.asyncio
    async def test_description_contains_type_and_message(self):
        """Embed description contains exception type name and message text."""
        captured: list = []

        async def fake_log_to_discord(embed):
            captured.append(embed)

        bot = MagicMock()
        bot.log_to_discord = fake_log_to_discord

        exc = ValueError("specific error text")
        await _post_task_error(bot, "auto-queue", exc)

        assert captured
        embed = captured[0]
        assert "ValueError" in embed.description, "Type name must be in description"
        assert "specific error text" in embed.description, "Error message must be in description"
        # Title must reference the task name
        assert "auto-queue" in embed.title, "Task name must be in embed title"

    @pytest.mark.asyncio
    async def test_no_guild_user_data_in_embed(self):
        """Embed carries only task name and exception info — no guild IDs or user data (T-09-03)."""
        captured: list = []

        async def fake_log_to_discord(embed):
            captured.append(embed)

        bot = MagicMock()
        bot.log_to_discord = fake_log_to_discord

        exc = ConnectionError("network blip")
        await _post_task_error(bot, "prefetch", exc)

        assert captured
        embed = captured[0]
        # Verify no extra fields are added (guild IDs, user IDs, etc.)
        assert len(embed.fields) == 0, f"Embed must have no extra fields, got: {embed.fields}"

    @pytest.mark.asyncio
    async def test_bot_without_log_to_discord_returns_early(self):
        """Bot without log_to_discord attribute must return silently (no AttributeError)."""
        bot = MagicMock(spec=[])  # empty spec — no attributes

        # Must not raise
        await _post_task_error(bot, "task-name", ValueError("boom"))

    @pytest.mark.asyncio
    async def test_log_to_discord_exception_is_swallowed(self):
        """Exception from bot.log_to_discord must not propagate (T-09-07)."""
        bot = MagicMock()
        bot.log_to_discord = AsyncMock(side_effect=RuntimeError("discord down"))

        # Must not raise — the reporter can never crash the event loop
        await _post_task_error(bot, "auto-lyrics", ValueError("some error"))
