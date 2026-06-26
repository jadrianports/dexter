"""Shared fire-and-forget task helper with exception surfacing (REL-02 / D-03/D-04).

Usage
-----
Replace bare ``asyncio.create_task(some_coro)`` fire-and-forget calls with::

    make_task(some_coro, name="task-name", bot=self.bot)

Done-callback behaviour:
  - Cancelled task  → silent return (normal on shutdown / skip / generation-change)
  - Successful task → silent return
  - Raised task     → log.error to dexter.log (always) + throttled embed post to
                       ERROR_LOG_CHANNEL_ID (rate-limited per (task_name, exc_type))

Security (T-09-03): embeds carry task name + exception type/message only — no guild
IDs, user data, tokens, or DSNs.

Imports: asyncio, functools, time, discord, config, utils.logger only.
No imports from cogs.* or bot — keeps this circular-import-free.
"""

from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, Coroutine

import discord

import config
from utils.logger import log

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

# Strong-reference set prevents GC collecting mid-flight tasks.
# (asyncio docs warn that Task objects may be garbage-collected if nothing else
#  holds a reference, causing the coroutine to be silently abandoned.)
_background_tasks: set[asyncio.Task] = set()

# Dedup map: mirrors _last_ytdlp_update float pattern in services/youtube.py.
# Keys are "{task_name}:{ExcType}" — no user / guild data (T-09-03).
_last_task_error_post: dict[str, float] = {}

# Maximum length for the exception message portion of the embed description.
_MAX_EXC_MSG_CHARS: int = 500


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def make_task(
    coro: Coroutine,
    *,
    name: str | None = None,
    bot: Any = None,
) -> asyncio.Task:
    """Create a fire-and-forget asyncio.Task with exception surfacing.

    The done-callback:
      1. Silently ignores cancellation (shutdown / skip / generation-change).
      2. Logs any exception to dexter.log via log.error (always).
      3. Posts a throttled, sanitized embed to ERROR_LOG_CHANNEL_ID (when bot
         is provided and the (task_name, exc_type) dedup window has expired).

    Args:
        coro: The coroutine to schedule.
        name: Optional task name (surfaced in logs and embeds).
        bot:  The discord.ext.commands.Bot instance.  Pass None to suppress
              channel posting (useful in tests / early-startup contexts).

    Returns:
        The created asyncio.Task.
    """
    task = asyncio.create_task(coro, name=name)
    # Keep a strong reference until the task completes (asyncio GC guard).
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    # Attach the error-surfacing callback with the bot reference baked in.
    task.add_done_callback(functools.partial(_on_task_done, bot=bot))
    return task


# ---------------------------------------------------------------------------
# Done-callback implementation (synchronous — called by the event loop)
# ---------------------------------------------------------------------------


def _on_task_done(task: asyncio.Task, *, bot: Any = None) -> None:
    """Done-callback: log exceptions and optionally post to the Discord error channel.

    Must be synchronous (asyncio done-callbacks are not awaitable).  Async work
    (channel post) is scheduled via asyncio.ensure_future.

    Pitfall 1 guard: task.cancelled() MUST be checked before task.exception() —
    calling exception() on a cancelled task raises asyncio.CancelledError.
    """
    # Cancellation is normal (shutdown, skip, generation-change) — ignore silently.
    if task.cancelled():
        return

    exc = task.exception()
    if exc is None:
        return  # task completed successfully

    task_name = task.get_name() or "unknown"
    log.error("Background task %r raised: %s", task_name, exc, exc_info=exc)

    if bot is None:
        return  # no channel posting requested

    # Rate-limit channel posts per (task_name, exc_type) to avoid flooding (D-04).
    # Logs record every occurrence; the channel only sees the first per window.
    key = f"{task_name}:{type(exc).__name__}"
    now = time.monotonic()
    # Sentinel -inf means "never posted" → now - (-inf) = inf ≥ any cooldown, so first
    # post always goes through regardless of the actual clock value (including t=0 in tests).
    if now - _last_task_error_post.get(key, -float("inf")) < config.TASK_ERROR_CHANNEL_COOLDOWN_SECONDS:
        return  # within cooldown window — log is sufficient
    _last_task_error_post[key] = now

    # done-callbacks are synchronous — the async channel post must be scheduled.
    asyncio.ensure_future(_post_task_error(bot, task_name, exc))


# ---------------------------------------------------------------------------
# Async channel poster (best-effort — must never crash the event loop)
# ---------------------------------------------------------------------------


async def _post_task_error(bot: Any, task_name: str, exc: Exception) -> None:
    """Post a task-failure embed to the Discord error channel (best-effort).

    Security (T-09-03): embed carries task name + exception type/message only.
    No guild IDs, user data, tokens, or DSNs are included.
    """
    if not hasattr(bot, "log_to_discord"):
        return

    # Truncate the exception message to prevent oversized embeds.
    exc_str = str(exc)
    if len(exc_str) > _MAX_EXC_MSG_CHARS:
        exc_str = exc_str[:_MAX_EXC_MSG_CHARS] + "…"  # unicode ellipsis

    embed = discord.Embed(
        title=f"Background Task Error: {task_name}",
        description=f"{type(exc).__name__}: {exc_str}",
        color=0xFF6600,
    )

    try:
        await bot.log_to_discord(embed)
    except Exception:
        pass  # never let the error reporter crash the event loop (T-09-07)
