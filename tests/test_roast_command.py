"""Unit tests for /roast command in cogs/ai.py (SOCIAL-01).

Mock style mirrors tests/test_rate_limiter.py (unit mocks, no live DB or Discord).
All async tests use @pytest.mark.asyncio.

Tests:
- test_roast_template_fallback   — GeminiRateLimitError triggers fallback (never fails)
- test_roast_edge_cases          — self/bot/zero-history each pick the right pool
- test_roast_uses_priority_1     — gemini.chat called with priority=1
- test_roast_no_mass_mention     — followup send uses AllowedMentions.none()
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from services.gemini import GeminiRateLimitError
from personality.roasts import (
    ROAST_COMMAND_LINES,
    ROAST_SELF_LINES,
    ROAST_BOT_LINES,
    ROAST_NO_HISTORY_LINES,
)


# ---------------------------------------------------------------------------
# Helpers to build a minimal fake interaction + bot environment
# ---------------------------------------------------------------------------

def _make_bot(bot_user_id: int = 999) -> MagicMock:
    """Return a minimal fake bot with a pool and a gemini_service."""
    bot = MagicMock()
    bot_user = MagicMock(spec=discord.User)
    bot_user.id = bot_user_id
    bot_user.bot = True
    bot.user = bot_user
    bot.pool = MagicMock()
    # gemini_service is set per-test
    return bot


def _make_interaction(user_id: int = 1, guild_id: int = 100) -> MagicMock:
    """Return a minimal fake discord.Interaction."""
    interaction = MagicMock(spec=discord.Interaction)

    user = MagicMock(spec=discord.Member)
    user.id = user_id
    user.display_name = "Invoker"
    user.bot = False
    interaction.user = user

    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    interaction.guild = guild

    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


def _make_target(
    user_id: int = 2,
    display_name: str = "Target",
    is_bot: bool = False,
) -> MagicMock:
    """Return a minimal fake discord.Member as roast target."""
    target = MagicMock(spec=discord.Member)
    target.id = user_id
    target.display_name = display_name
    target.bot = is_bot
    return target


async def _invoke_roast(bot, interaction, target):
    """Import AICog and call roast() directly, bypassing Discord decorator machinery.

    discord.py's @app_commands.command wraps the method in an app_commands.Command
    object (not directly awaitable). Use .callback to reach the underlying coroutine,
    passing cog as the first 'self' argument explicitly.
    """
    from cogs.ai import AICog
    cog = AICog(bot)
    # .callback is the raw coroutine; pass cog as self
    await cog.roast.callback(cog, interaction, target)


# ---------------------------------------------------------------------------
# test_roast_template_fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_roast_template_fallback():
    """When GeminiService.chat raises GeminiRateLimitError, a fallback line is sent.

    The roast command must NEVER propagate the exception or send nothing.
    """
    bot = _make_bot()
    interaction = _make_interaction(user_id=1)
    target = _make_target(user_id=2, display_name="Victim")

    gemini_service = MagicMock()
    gemini_service.chat = AsyncMock(side_effect=GeminiRateLimitError("rate limited"))
    bot.gemini_service = gemini_service

    with (
        patch("cogs.ai.get_mood", new=AsyncMock(return_value="normal")),
        patch("cogs.ai.get_user_summary", new=AsyncMock(return_value="User 'Victim': 50 songs.")),
        patch("cogs.ai.get_seasonal_context", return_value=""),
        patch("cogs.ai.build_chat_prompt", return_value="system prompt"),
        patch("cogs.ai.increment_daily_stat", new=AsyncMock()),
    ):
        await _invoke_roast(bot, interaction, target)

    # followup.send must have been called exactly once
    interaction.followup.send.assert_called_once()
    sent_text = interaction.followup.send.call_args[0][0]
    # The fallback should be a non-empty string (one of the command lines, name-formatted)
    assert isinstance(sent_text, str) and len(sent_text) > 0
    # Must NOT re-raise the rate-limit error
    # (test passes if we reach here without exception)


# ---------------------------------------------------------------------------
# test_roast_edge_cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_roast_edge_cases():
    """self-target, bot-target, zero-history each hit the correct fallback pool.

    For each branch we force Gemini to raise so the fallback line is the
    only thing sent — makes it easy to assert the pool selection.
    """
    from personality.responses import pick_random

    BOT_USER_ID = 999

    # ---- Case 1: bot target (target IS the bot) ----
    bot = _make_bot(bot_user_id=BOT_USER_ID)
    bot.gemini_service = MagicMock()
    bot.gemini_service.chat = AsyncMock(side_effect=GeminiRateLimitError("rl"))

    interaction = _make_interaction(user_id=1)
    target_bot = _make_target(user_id=BOT_USER_ID, display_name="Dexter", is_bot=True)
    # Make target == bot.user
    target_bot.id = BOT_USER_ID

    with (
        patch("cogs.ai.get_mood", new=AsyncMock(return_value="normal")),
        patch("cogs.ai.get_user_summary", new=AsyncMock(return_value=None)),
        patch("cogs.ai.get_seasonal_context", return_value=""),
        patch("cogs.ai.build_chat_prompt", return_value="system"),
        patch("cogs.ai.increment_daily_stat", new=AsyncMock()),
        patch("cogs.ai.pick_random", side_effect=pick_random) as mock_pick,
    ):
        await _invoke_roast(bot, interaction, target_bot)
        # pick_random was called with ROAST_BOT_LINES for the fallback pool
        pick_call_args = [call.args[0] for call in mock_pick.call_args_list]
        assert ROAST_BOT_LINES in pick_call_args, (
            f"Expected ROAST_BOT_LINES in pick_random calls, got: {pick_call_args}"
        )

    # ---- Case 2: self-target (invoker == target) ----
    bot2 = _make_bot(bot_user_id=BOT_USER_ID)
    bot2.gemini_service = MagicMock()
    bot2.gemini_service.chat = AsyncMock(side_effect=GeminiRateLimitError("rl"))

    interaction2 = _make_interaction(user_id=42)
    target_self = _make_target(user_id=42, display_name="SelfRoaster")

    with (
        patch("cogs.ai.get_mood", new=AsyncMock(return_value="normal")),
        patch("cogs.ai.get_user_summary", new=AsyncMock(return_value=None)),
        patch("cogs.ai.get_seasonal_context", return_value=""),
        patch("cogs.ai.build_chat_prompt", return_value="system"),
        patch("cogs.ai.increment_daily_stat", new=AsyncMock()),
        patch("cogs.ai.pick_random", side_effect=pick_random) as mock_pick2,
    ):
        await _invoke_roast(bot2, interaction2, target_self)
        pick_call_args2 = [call.args[0] for call in mock_pick2.call_args_list]
        assert ROAST_SELF_LINES in pick_call_args2, (
            f"Expected ROAST_SELF_LINES in pick_random calls, got: {pick_call_args2}"
        )

    # ---- Case 3: zero-history target (get_user_summary returns None) ----
    bot3 = _make_bot(bot_user_id=BOT_USER_ID)
    bot3.gemini_service = MagicMock()
    bot3.gemini_service.chat = AsyncMock(side_effect=GeminiRateLimitError("rl"))

    interaction3 = _make_interaction(user_id=1)
    target_nohistory = _make_target(user_id=99, display_name="Ghost")

    with (
        patch("cogs.ai.get_mood", new=AsyncMock(return_value="normal")),
        patch("cogs.ai.get_user_summary", new=AsyncMock(return_value=None)),
        patch("cogs.ai.get_seasonal_context", return_value=""),
        patch("cogs.ai.build_chat_prompt", return_value="system"),
        patch("cogs.ai.increment_daily_stat", new=AsyncMock()),
        patch("cogs.ai.pick_random", side_effect=pick_random) as mock_pick3,
    ):
        await _invoke_roast(bot3, interaction3, target_nohistory)
        pick_call_args3 = [call.args[0] for call in mock_pick3.call_args_list]
        assert ROAST_NO_HISTORY_LINES in pick_call_args3, (
            f"Expected ROAST_NO_HISTORY_LINES in pick_random calls, got: {pick_call_args3}"
        )


# ---------------------------------------------------------------------------
# test_roast_uses_priority_1
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_roast_uses_priority_1():
    """gemini.chat must be called with priority=1 (D-05 / Pitfall 3)."""
    bot = _make_bot()
    interaction = _make_interaction(user_id=1)
    target = _make_target(user_id=2, display_name="Victim")

    gemini_service = MagicMock()
    gemini_service.chat = AsyncMock(return_value="this is a roast line")
    bot.gemini_service = gemini_service

    with (
        patch("cogs.ai.get_mood", new=AsyncMock(return_value="normal")),
        patch("cogs.ai.get_user_summary", new=AsyncMock(return_value="User 'Victim': 10 songs.")),
        patch("cogs.ai.get_seasonal_context", return_value=""),
        patch("cogs.ai.build_chat_prompt", return_value="system prompt"),
        patch("cogs.ai.increment_daily_stat", new=AsyncMock()),
    ):
        await _invoke_roast(bot, interaction, target)

    gemini_service.chat.assert_called_once()
    call_kwargs = gemini_service.chat.call_args[1]
    call_args = gemini_service.chat.call_args[0]
    # priority may be passed as positional or keyword
    priority_value = call_kwargs.get("priority") if "priority" in call_kwargs else call_args[2]
    assert priority_value == 1, (
        f"Expected priority=1 for /roast Gemini call, got priority={priority_value}"
    )


# ---------------------------------------------------------------------------
# test_roast_no_mass_mention
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_roast_no_mass_mention():
    """Public followup send must pass AllowedMentions.none() (T-08-04 mitigation)."""
    bot = _make_bot()
    interaction = _make_interaction(user_id=1)
    target = _make_target(user_id=2, display_name="Victim")

    gemini_service = MagicMock()
    gemini_service.chat = AsyncMock(return_value="your taste is genuinely alarming.")
    bot.gemini_service = gemini_service

    with (
        patch("cogs.ai.get_mood", new=AsyncMock(return_value="normal")),
        patch("cogs.ai.get_user_summary", new=AsyncMock(return_value="User 'Victim': 5 songs.")),
        patch("cogs.ai.get_seasonal_context", return_value=""),
        patch("cogs.ai.build_chat_prompt", return_value="system prompt"),
        patch("cogs.ai.increment_daily_stat", new=AsyncMock()),
    ):
        await _invoke_roast(bot, interaction, target)

    interaction.followup.send.assert_called_once()
    call_kwargs = interaction.followup.send.call_args[1]
    allowed_mentions = call_kwargs.get("allowed_mentions")
    assert allowed_mentions is not None, (
        "followup.send must include allowed_mentions kwarg"
    )
    assert isinstance(allowed_mentions, discord.AllowedMentions), (
        f"allowed_mentions must be discord.AllowedMentions, got {type(allowed_mentions)}"
    )
    # Verify it is AllowedMentions.none() — all flags false
    assert allowed_mentions.everyone is False
    assert allowed_mentions.roles is False
    assert allowed_mentions.users is False
