"""Unit tests for cogs/memory.py — /memory view (RAG-03) + /memory forget (RAG-04).

Mock style mirrors tests/test_roast_command.py (unit mocks, no live DB or
Discord connection) and tests/test_discover.py's direct button-callback
invocation convention (discord.ui.button decorates the function in place,
so `ViewClass.button_method(view, interaction, button)` is directly
callable — unlike app_commands.command, which needs `.callback`).

Tests:
- test_memory_view_shows_verbatim_facts   — raw fact text appears unedited
- test_memory_view_empty_state            — in-character empty-state line, no view
- test_memory_view_is_ephemeral           — response always ephemeral=True
- test_memory_view_uses_max_per_user_cap  — Pitfall 2 regression guard
- test_forget_empty_state_skips_confirm   — Pitfall 5: no confirm view, no delete
- test_forget_confirm_deletes             — Confirm press hard-deletes via the DB helper
- test_forget_cancel_leaves_memories      — Cancel press never deletes
- test_memory_subcommands_have_no_target_param — V4 structural self-scoping guard
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import discord
import pytest

import config
from cogs.memory import ForgetConfirmView, MemoryCog


# ---------------------------------------------------------------------------
# Helpers to build a minimal fake interaction + bot environment
# ---------------------------------------------------------------------------


def _make_bot() -> MagicMock:
    """Return a minimal fake bot with a pool (MemoryCog has no gemini dep)."""
    bot = MagicMock()
    bot.pool = MagicMock()
    return bot


def _make_message_mock() -> MagicMock:
    """A fake discord.Message whose .edit() is awaitable."""
    message = MagicMock(spec=discord.Message)
    message.edit = AsyncMock()
    return message


def _make_interaction(user_id: int = 1) -> MagicMock:
    """Return a minimal fake discord.Interaction."""
    interaction = MagicMock(spec=discord.Interaction)

    user = MagicMock(spec=discord.Member)
    user.id = user_id
    user.display_name = "Invoker"
    user.bot = False
    interaction.user = user

    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    interaction.original_response = AsyncMock(return_value=_make_message_mock())
    return interaction


# ---------------------------------------------------------------------------
# /memory view
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_view_shows_verbatim_facts():
    """The raw stored fact text appears unedited in the sent embed (D-02)."""
    bot = _make_bot()
    interaction = _make_interaction()
    cog = MemoryCog(bot)

    fake_rows = [{"fact": "user listens to synthwave at 2am and denies it"}]
    with patch("database.list_user_memories", new=AsyncMock(return_value=fake_rows)):
        await cog.memory_view.callback(cog, interaction)

    interaction.response.send_message.assert_awaited_once()
    kwargs = interaction.response.send_message.call_args.kwargs
    assert kwargs["ephemeral"] is True
    embed = kwargs["embed"]
    assert "user listens to synthwave at 2am and denies it" in embed.description


@pytest.mark.asyncio
async def test_memory_view_empty_state():
    """No stored memories -> in-character empty line, no view constructed."""
    bot = _make_bot()
    interaction = _make_interaction()
    cog = MemoryCog(bot)

    with patch("database.list_user_memories", new=AsyncMock(return_value=[])):
        await cog.memory_view.callback(cog, interaction)

    interaction.response.send_message.assert_awaited_once_with(
        "i don't remember anything about you yet.", ephemeral=True
    )


@pytest.mark.asyncio
async def test_memory_view_is_ephemeral():
    """Every /memory view send is ephemeral, regardless of how many facts exist."""
    bot = _make_bot()
    interaction = _make_interaction()
    cog = MemoryCog(bot)

    fake_rows = [{"fact": "fact one"}, {"fact": "fact two"}]
    with patch("database.list_user_memories", new=AsyncMock(return_value=fake_rows)):
        await cog.memory_view.callback(cog, interaction)

    kwargs = interaction.response.send_message.call_args.kwargs
    assert kwargs["ephemeral"] is True


@pytest.mark.asyncio
async def test_memory_view_uses_max_per_user_cap():
    """Pitfall 2 regression: must pass MEMORY_MAX_PER_USER, never the smaller
    prompt-injection cap — the view must never truncate below what forget erases."""
    bot = _make_bot()
    interaction = _make_interaction()
    cog = MemoryCog(bot)

    list_mock = AsyncMock(return_value=[{"fact": "x"}])
    with patch("database.list_user_memories", new=list_mock):
        await cog.memory_view.callback(cog, interaction)

    list_mock.assert_awaited_once()
    assert list_mock.await_args.kwargs["limit"] == config.MEMORY_MAX_PER_USER


# ---------------------------------------------------------------------------
# /memory forget
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forget_empty_state_skips_confirm():
    """Pitfall 5: an empty store skips the confirm view entirely — no delete call."""
    bot = _make_bot()
    interaction = _make_interaction()
    cog = MemoryCog(bot)

    delete_mock = AsyncMock()
    with patch("database.count_user_memories", new=AsyncMock(return_value=0)), \
            patch("database.delete_all_user_memories", new=delete_mock):
        await cog.memory_forget.callback(cog, interaction)

    interaction.response.send_message.assert_awaited_once_with(
        "already got nothing on you.", ephemeral=True
    )
    delete_mock.assert_not_awaited()
    kwargs = interaction.response.send_message.call_args.kwargs
    assert "view" not in kwargs


@pytest.mark.asyncio
async def test_forget_confirm_deletes():
    """Confirm press hard-deletes via delete_all_user_memories(pool, user_id)."""
    bot = _make_bot()
    interaction = _make_interaction()
    cog = MemoryCog(bot)

    delete_mock = AsyncMock(return_value=3)
    with patch("database.count_user_memories", new=AsyncMock(return_value=3)), \
            patch("database.delete_all_user_memories", new=delete_mock):
        await cog.memory_forget.callback(cog, interaction)

        kwargs = interaction.response.send_message.call_args.kwargs
        view = kwargs["view"]
        assert isinstance(view, ForgetConfirmView)

        confirm_interaction = _make_interaction()
        await ForgetConfirmView.confirm_button(view, confirm_interaction, Mock())

    delete_mock.assert_awaited_once_with(bot.pool, str(interaction.user.id))
    confirm_interaction.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_forget_cancel_leaves_memories():
    """Cancel press never touches delete_all_user_memories."""
    bot = _make_bot()
    interaction = _make_interaction()
    cog = MemoryCog(bot)

    delete_mock = AsyncMock()
    with patch("database.count_user_memories", new=AsyncMock(return_value=3)), \
            patch("database.delete_all_user_memories", new=delete_mock):
        await cog.memory_forget.callback(cog, interaction)

        kwargs = interaction.response.send_message.call_args.kwargs
        view = kwargs["view"]

        cancel_interaction = _make_interaction()
        await ForgetConfirmView.cancel_button(view, cancel_interaction, Mock())

    delete_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# V4 structural self-scoping guard
# ---------------------------------------------------------------------------


def test_memory_subcommands_have_no_target_param():
    """Neither subcommand accepts a target/user parameter — self-scoped only."""
    view_params = list(inspect.signature(MemoryCog.memory_view.callback).parameters)
    forget_params = list(inspect.signature(MemoryCog.memory_forget.callback).parameters)
    assert view_params == ["self", "interaction"]
    assert forget_params == ["self", "interaction"]
