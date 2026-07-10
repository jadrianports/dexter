"""Behavioral glue tests for the Phase 16 proactive-callback surface (PROACT-01/02).

Locks `EventsCog._maybe_fire_proactive_callback` — the D-02 firing order
(opt-out -> pure gate -> recall-floor silent-skip -> reply-anchored fire with
mention suppression, counter increments only on an actual fire) — plus the
`on_message` designated-channel gate and the accuracy firewall (no live-SQL
numeric-stat helper referenced by the glue).

Mock style mirrors tests/test_ambient_recall_cadence.py (`_make_bot` helper,
AsyncMock recall, spec=discord.* mocks; no live Discord or DB connection).
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

import cogs.events
from cogs.events import EventsCog

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bot() -> MagicMock:
    """Return a minimal fake bot with a pool and a memory_service.recall AsyncMock.

    Phase 18 / CONFIG-02: also carries a `guild_config` seam whose `.get(...)`
    returns a configured row with `ambient_channel_id="500"` by default — the
    new seam `on_message` gates dispatch through (replacing the old bare
    env-var equality check).

    Phase 19 / D-22: the row also carries both toggle keys, both True by
    default, so ROAST and VISION surfaces resolve identically unless a test
    overrides one explicitly.
    """
    bot = MagicMock()
    bot.pool = MagicMock()
    bot.memory_service = MagicMock()
    bot.memory_service.recall = AsyncMock(return_value=[])
    bot.guild_config = MagicMock()
    bot.guild_config.get = MagicMock(
        return_value={
            "configured": True,
            "ambient_channel_id": "500",
            "ambient_roasts_enabled": True,
            "vision_roasts_enabled": True,
        }
    )
    return bot


def _make_message(user_id: int = 1, guild_id: int = 100, channel_id: int = 500) -> MagicMock:
    """Return a minimal fake discord.Message with a spec'd Member author."""
    message = MagicMock(spec=discord.Message)

    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    message.guild = guild

    channel = MagicMock()
    channel.id = channel_id
    message.channel = channel

    author = MagicMock(spec=discord.Member)
    author.id = user_id
    author.display_name = "Tester"
    author.bot = False
    message.author = author

    message.content = "hey dexter"
    message.reply = AsyncMock()
    return message


# ---------------------------------------------------------------------------
# (A) recall-floor silent-skip (D-02 step 4 / Pitfall 8)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_floor_silent_skip():
    """Gate passes but recall() returns [] -> no send, no counter increment."""
    bot = _make_bot()
    bot.memory_service.recall = AsyncMock(return_value=[])
    message = _make_message()
    cog = EventsCog(bot)

    with (
        patch("cogs.events.database.get_proactive_opt_out", new=AsyncMock(return_value=False)),
        patch("cogs.events.random.random", return_value=0.0),
    ):
        await cog._maybe_fire_proactive_callback(message)

    message.reply.assert_not_awaited()
    assert str(message.author.id) not in cog._proactive_daily_counts


# ---------------------------------------------------------------------------
# (B) reply-anchor + mention suppression on an actual fire
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reply_anchor():
    """A real fire replies to the message with AllowedMentions.none(), never channel.send."""
    bot = _make_bot()
    bot.memory_service.recall = AsyncMock(return_value=["a recalled fact"])
    message = _make_message()
    cog = EventsCog(bot)

    with (
        patch("cogs.events.database.get_proactive_opt_out", new=AsyncMock(return_value=False)),
        patch("cogs.events.random.random", return_value=0.0),
        patch.object(cog, "_generate_ambient_roast", new=AsyncMock(return_value="dex remembers stuff")),
    ):
        await cog._maybe_fire_proactive_callback(message)

    message.reply.assert_awaited_once()
    call_args, call_kwargs = message.reply.call_args
    assert call_args[0] == "dex remembers stuff"

    allowed_mentions = call_kwargs.get("allowed_mentions")
    assert allowed_mentions is not None, "message.reply must include allowed_mentions kwarg"
    assert isinstance(allowed_mentions, discord.AllowedMentions)
    assert allowed_mentions.everyone is False
    assert allowed_mentions.roles is False
    assert allowed_mentions.users is False
    assert call_kwargs.get("mention_author") is False

    message.channel.send.assert_not_called()


# ---------------------------------------------------------------------------
# (C) daily counter increments only on an actual fire
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_daily_counter_increments_only_on_fire():
    bot = _make_bot()
    bot.memory_service.recall = AsyncMock(return_value=["a recalled fact"])
    message = _make_message(user_id=11)
    cog = EventsCog(bot)

    with (
        patch("cogs.events.database.get_proactive_opt_out", new=AsyncMock(return_value=False)),
        patch("cogs.events.random.random", return_value=0.0),
        patch.object(cog, "_generate_ambient_roast", new=AsyncMock(return_value="line")),
    ):
        await cog._maybe_fire_proactive_callback(message)

    assert cog._proactive_daily_counts[str(message.author.id)][1] == 1

    # A gate-skip (opt-out True) for a different user leaves the counter absent.
    message2 = _make_message(user_id=22)
    with patch("cogs.events.database.get_proactive_opt_out", new=AsyncMock(return_value=True)):
        await cog._maybe_fire_proactive_callback(message2)

    assert str(message2.author.id) not in cog._proactive_daily_counts


# ---------------------------------------------------------------------------
# (D) opt-out short-circuits before any recall/send
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_opted_out_short_circuits():
    bot = _make_bot()
    message = _make_message()
    cog = EventsCog(bot)

    with patch("cogs.events.database.get_proactive_opt_out", new=AsyncMock(return_value=True)):
        await cog._maybe_fire_proactive_callback(message)

    bot.memory_service.recall.assert_not_awaited()
    message.reply.assert_not_awaited()


# ---------------------------------------------------------------------------
# (E) on_message channel gate — non-designated channel never reaches the glue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_designated_channel_skips():
    """A channel id that does not match the guild's configured ambient channel
    (via bot.guild_config.get -> is_ambient_channel) never reaches the glue."""
    bot = _make_bot()
    bot.message_buffer = MagicMock()
    bot.message_buffer.add = MagicMock()
    message = _make_message(channel_id=999)
    cog = EventsCog(bot)

    with (
        patch.object(cog, "_maybe_fire_proactive_callback", new=AsyncMock()) as mock_fire,
        patch.object(cog, "_handle_message_reactions", new=AsyncMock()),
    ):
        await cog.on_message(message)

    mock_fire.assert_not_awaited()


@pytest.mark.asyncio
async def test_designated_channel_triggers():
    """The mirror positive case: a channel id matching the guild's configured
    ambient channel (bot.guild_config.get -> is_ambient_channel) DOES call the glue."""
    bot = _make_bot()
    bot.message_buffer = MagicMock()
    bot.message_buffer.add = MagicMock()
    message = _make_message(channel_id=500)
    cog = EventsCog(bot)

    with (
        patch.object(cog, "_maybe_fire_proactive_callback", new=AsyncMock()) as mock_fire,
        patch.object(cog, "_handle_message_reactions", new=AsyncMock()),
    ):
        await cog.on_message(message)

    mock_fire.assert_awaited_once_with(message)


@pytest.mark.asyncio
async def test_unconfigured_guild_skips():
    """CONFIG-04: an unconfigured guild (guild_config.get -> None) is silent,
    even when the channel id would otherwise have matched the old env var."""
    bot = _make_bot()
    bot.guild_config.get = MagicMock(return_value=None)
    bot.message_buffer = MagicMock()
    bot.message_buffer.add = MagicMock()
    message = _make_message(channel_id=500)
    cog = EventsCog(bot)

    with (
        patch.object(cog, "_maybe_fire_proactive_callback", new=AsyncMock()) as mock_fire,
        patch.object(cog, "_handle_message_reactions", new=AsyncMock()),
    ):
        await cog.on_message(message)

    mock_fire.assert_not_awaited()


# ---------------------------------------------------------------------------
# (E2) Phase 19 / D-21/D-22: reaction gate + independent surface-keyed split
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reactions_fire_in_ambient_channel_with_roasts_enabled():
    """D-21: _handle_message_reactions IS awaited in the ambient channel with
    ambient_roasts_enabled True (closes the CONFIG-04 reaction hole)."""
    bot = _make_bot()
    bot.message_buffer = MagicMock()
    bot.message_buffer.add = MagicMock()
    message = _make_message(channel_id=500)
    cog = EventsCog(bot)

    with (
        patch.object(cog, "_handle_message_reactions", new=AsyncMock()) as mock_react,
        patch.object(cog, "_maybe_fire_proactive_callback", new=AsyncMock()),
        patch.object(cog, "_maybe_fire_vision_roast", new=AsyncMock()),
    ):
        await cog.on_message(message)

    mock_react.assert_awaited_once_with(message)


@pytest.mark.asyncio
async def test_reactions_suppressed_when_unconfigured():
    """D-21: an unconfigured guild (guild_config.get -> None) never triggers reactions."""
    bot = _make_bot()
    bot.guild_config.get = MagicMock(return_value=None)
    bot.message_buffer = MagicMock()
    bot.message_buffer.add = MagicMock()
    message = _make_message(channel_id=500)
    cog = EventsCog(bot)

    with (
        patch.object(cog, "_handle_message_reactions", new=AsyncMock()) as mock_react,
        patch.object(cog, "_maybe_fire_proactive_callback", new=AsyncMock()),
        patch.object(cog, "_maybe_fire_vision_roast", new=AsyncMock()),
    ):
        await cog.on_message(message)

    mock_react.assert_not_awaited()


@pytest.mark.asyncio
async def test_reactions_suppressed_when_channel_mismatched():
    """D-21: a non-ambient channel id never triggers reactions."""
    bot = _make_bot()
    message = _make_message(channel_id=999)
    cog = EventsCog(bot)

    with (
        patch.object(cog, "_handle_message_reactions", new=AsyncMock()) as mock_react,
        patch.object(cog, "_maybe_fire_proactive_callback", new=AsyncMock()),
        patch.object(cog, "_maybe_fire_vision_roast", new=AsyncMock()),
    ):
        await cog.on_message(message)

    mock_react.assert_not_awaited()


@pytest.mark.asyncio
async def test_reactions_suppressed_when_ambient_roasts_disabled():
    """D-22: ambient_roasts_enabled=False silences reactions (and the proactive
    dispatch) even in the correctly-configured ambient channel."""
    bot = _make_bot()
    bot.guild_config.get = MagicMock(
        return_value={
            "configured": True,
            "ambient_channel_id": "500",
            "ambient_roasts_enabled": False,
            "vision_roasts_enabled": True,
        }
    )
    message = _make_message(channel_id=500)
    cog = EventsCog(bot)

    with (
        patch.object(cog, "_handle_message_reactions", new=AsyncMock()) as mock_react,
        patch.object(cog, "_maybe_fire_proactive_callback", new=AsyncMock()) as mock_fire,
        patch.object(cog, "_maybe_fire_vision_roast", new=AsyncMock()),
    ):
        await cog.on_message(message)

    mock_react.assert_not_awaited()
    mock_fire.assert_not_awaited()


@pytest.mark.asyncio
async def test_vision_disabled_does_not_affect_roast_surface():
    """D-22: vision_roasts_enabled=False + an attachment silences ONLY the
    vision dispatch — the proactive/reaction (ROAST) path is unaffected."""
    bot = _make_bot()
    bot.guild_config.get = MagicMock(
        return_value={
            "configured": True,
            "ambient_channel_id": "500",
            "ambient_roasts_enabled": True,
            "vision_roasts_enabled": False,
        }
    )
    message = _make_message(channel_id=500)
    message.attachments = [MagicMock()]  # an attachment IS present
    cog = EventsCog(bot)

    with (
        patch.object(cog, "_handle_message_reactions", new=AsyncMock()) as mock_react,
        patch.object(cog, "_maybe_fire_proactive_callback", new=AsyncMock()) as mock_fire,
        patch.object(cog, "_maybe_fire_vision_roast", new=AsyncMock()) as mock_vision,
    ):
        await cog.on_message(message)

    mock_react.assert_awaited_once_with(message)
    mock_fire.assert_awaited_once_with(message)
    mock_vision.assert_not_awaited()


# ---------------------------------------------------------------------------
# (F) accuracy firewall — no live-SQL numeric-stat helper in the glue
# ---------------------------------------------------------------------------


def test_accuracy_firewall():
    """_maybe_fire_proactive_callback never references a live-SQL numeric-stat helper.

    Hard numbers must only ever come from the already-firewalled
    _generate_ambient_roast/build_chat_prompt path (CLAUDE.md Critical Rule 12).
    """
    src = inspect.getsource(EventsCog._maybe_fire_proactive_callback)
    assert "get_user_summary" not in src
    assert "get_user_top_artist" not in src
