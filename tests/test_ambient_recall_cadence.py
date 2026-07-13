"""Regression lock for the D-01 cadence-gate invariant (Phase 15 / RAG-01, RAG-02).

Locks all four MEMORY_CALLBACK_CHANCE call sites:
- cogs/ai.py /ask                        -> gate REMOVED (recall on every invocation)
- cogs/ai.py /roast                      -> gate REMOVED (recall on every invocation,
                                             target-scoped)
- cogs/events.py _generate_ambient_roast -> gate RETAINED (unchanged, byte-identical)
- cogs/music.py _build_roast_line        -> gate RETAINED (unchanged, byte-identical)

There was previously NO test locking this invariant at any of the four call sites
(15-RESEARCH.md Open Question 2) — this file is new coverage, not an adjustment of
an existing test.

Mock style mirrors tests/test_roast_command.py (unit mocks, no live DB or Discord).
`import random` no longer exists in cogs/ai.py after the D-01 edit — do NOT patch
`cogs.ai.random`; there is no gate left to defeat, so the behavioral assertion here
is simply "recall fires, scoped correctly."
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

import cogs.ai
import cogs.events
import cogs.music

# ---------------------------------------------------------------------------
# (A) Source-inspection lock — the primary, non-flaky guarantee
# ---------------------------------------------------------------------------


def test_ambient_surfaces_retain_gate():
    """cogs/events.py and cogs/music.py ambient roast surfaces KEEP the 0.35 gate."""
    events_src = inspect.getsource(cogs.events.EventsCog._generate_ambient_roast)
    music_src = inspect.getsource(cogs.music.MusicCog._build_roast_line)
    assert "MEMORY_CALLBACK_CHANCE" in events_src, "cogs/events.py._generate_ambient_roast must retain the cadence gate"
    assert "MEMORY_CALLBACK_CHANCE" in music_src, "cogs/music.py._build_roast_line must retain the cadence gate"


def test_explicit_surfaces_lost_gate():
    """cogs/ai.py /ask and /roast callbacks no longer reference the cadence gate."""
    ask_src = inspect.getsource(cogs.ai.AICog.ask.callback)
    roast_src = inspect.getsource(cogs.ai.AICog.roast.callback)
    assert "MEMORY_CALLBACK_CHANCE" not in ask_src, (
        "/ask must attempt recall unconditionally (D-01) — gate must be gone"
    )
    assert "MEMORY_CALLBACK_CHANCE" not in roast_src, (
        "/roast must attempt recall unconditionally (D-01) — gate must be gone"
    )


def test_cogs_ai_has_no_random_import():
    """`import random` was removed from cogs/ai.py — its only uses were the two gates."""
    assert not hasattr(cogs.ai, "random"), "cogs.ai.random should not exist after the D-01 gate removal"


# ---------------------------------------------------------------------------
# Helpers — mirrors tests/test_roast_command.py conventions
# ---------------------------------------------------------------------------


def _make_bot(bot_user_id: int = 999) -> MagicMock:
    """Return a minimal fake bot with a pool, gemini_service slot, and memory_service."""
    bot = MagicMock()
    bot_user = MagicMock(spec=discord.User)
    bot_user.id = bot_user_id
    bot_user.bot = True
    bot.user = bot_user
    bot.pool = MagicMock()
    bot.memory_service = MagicMock()
    bot.memory_service.recall = AsyncMock(return_value=[])
    return bot


def _make_interaction(user_id: int = 1, guild_id: int = 100, channel_id: int = 500) -> MagicMock:
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
    interaction.guild_id = guild_id

    channel = MagicMock()
    channel.id = channel_id
    interaction.channel = channel

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


# ---------------------------------------------------------------------------
# (B) Behavioral lock — explicit surfaces always recall, correctly scoped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_roast_always_recalls_target_scoped():
    """/roast calls recall() exactly once, first arg == str(target.id) (RAG-01).

    Target != invoker — a regression that swapped scoping to the invoker would
    fail this assertion.
    """
    bot = _make_bot()
    interaction = _make_interaction(user_id=1)
    target = _make_target(user_id=2, display_name="Victim")

    gemini_service = MagicMock()
    gemini_service.chat = AsyncMock(return_value="your taste is genuinely alarming.")
    bot.gemini_service = gemini_service

    with (
        patch("cogs.ai.get_mood", new=AsyncMock(return_value="normal")),
        patch("cogs.ai.get_user_summary", new=AsyncMock(return_value="User 'Victim': 10 songs.")),
        patch("cogs.ai.get_seasonal_context", return_value=""),
        patch("cogs.ai.build_chat_prompt", return_value="system prompt"),
        patch("cogs.ai.increment_daily_stat", new=AsyncMock()),
    ):
        from cogs.ai import AICog

        cog = AICog(bot)
        await cog.roast.callback(cog, interaction, target)

    bot.memory_service.recall.assert_awaited_once()
    call_args = bot.memory_service.recall.call_args[0]
    assert call_args[0] == str(target.id), f"Expected recall scoped to target id {target.id}, got {call_args[0]}"
    assert call_args[0] != str(interaction.user.id), "recall must never be scoped to the invoker for /roast (RAG-01)"
    # Phase 21 / MEM-01: /roast is an explicit opt-in into guild-scoped recall.
    assert bot.memory_service.recall.call_args.kwargs.get("guild_scoped") is True, (
        "/roast recall must pass guild_scoped=True (MEM-01)"
    )


@pytest.mark.asyncio
async def test_ask_always_recalls_invoker_scoped():
    """/ask calls recall() exactly once, first arg == str(interaction.user.id) (RAG-02)."""
    bot = _make_bot()
    interaction = _make_interaction(user_id=42)

    bot.message_buffer = MagicMock()
    bot.message_buffer.get_gemini_history = MagicMock(return_value=[])
    bot.message_buffer.add = MagicMock()

    gemini_service = MagicMock()
    gemini_service.chat = AsyncMock(return_value="an answer, reluctantly.")
    bot.gemini_service = gemini_service

    with (
        patch("cogs.ai.get_mood", new=AsyncMock(return_value="normal")),
        patch("cogs.ai.get_user_summary", new=AsyncMock(return_value="User summary")),
        patch("cogs.ai.get_seasonal_context", return_value=""),
        patch("cogs.ai.build_chat_prompt", return_value="system prompt"),
        patch("cogs.ai.increment_daily_stat", new=AsyncMock()),
    ):
        from cogs.ai import AICog

        cog = AICog(bot)
        await cog.ask.callback(cog, interaction, "what is the meaning of life")

    bot.memory_service.recall.assert_awaited_once()
    call_args = bot.memory_service.recall.call_args[0]
    assert call_args[0] == str(interaction.user.id), (
        f"Expected recall scoped to invoker id {interaction.user.id}, got {call_args[0]}"
    )


@pytest.mark.asyncio
async def test_ask_recall_is_never_guild_scoped():
    """/ask recall() must NEVER carry a guild_scoped kwarg (MEM-02).

    /ask is a user explicitly and synchronously pulling their OWN memory — no
    cross-user exposure is possible, so recall stays global. This is the test
    that fails if someone "consistency-fixes" /ask to match /roast's opt-in.
    """
    bot = _make_bot()
    interaction = _make_interaction(user_id=42)

    bot.message_buffer = MagicMock()
    bot.message_buffer.get_gemini_history = MagicMock(return_value=[])
    bot.message_buffer.add = MagicMock()

    gemini_service = MagicMock()
    gemini_service.chat = AsyncMock(return_value="an answer, reluctantly.")
    bot.gemini_service = gemini_service

    with (
        patch("cogs.ai.get_mood", new=AsyncMock(return_value="normal")),
        patch("cogs.ai.get_user_summary", new=AsyncMock(return_value="User summary")),
        patch("cogs.ai.get_seasonal_context", return_value=""),
        patch("cogs.ai.build_chat_prompt", return_value="system prompt"),
        patch("cogs.ai.increment_daily_stat", new=AsyncMock()),
    ):
        from cogs.ai import AICog

        cog = AICog(bot)
        await cog.ask.callback(cog, interaction, "what is the meaning of life")

    bot.memory_service.recall.assert_awaited_once()
    call_kwargs = bot.memory_service.recall.call_args.kwargs
    assert call_kwargs.get("guild_scoped") is not True
    assert "guild_scoped" not in call_kwargs, "MEM-02: /ask recall must carry NO guild_scoped kwarg at all"


# ---------------------------------------------------------------------------
# (C) Phase 16 / Pitfall 1 regression lock — pre_recalled_memories bypass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pre_recalled_bypasses_internal_recall():
    """pre_recalled_memories provided -> internal recall() never awaited.

    The default None path (unchanged) still runs the internal
    MEMORY_CALLBACK_CHANCE-gated recall — proving the two voice-event call
    sites remain byte-identical while only the proactive caller (plan 16-03)
    bypasses the internal gate.
    """
    bot = _make_bot()
    bot.gemini_service = MagicMock()
    bot.gemini_service.chat = AsyncMock(return_value="a generated line")

    member = _make_target(user_id=5, display_name="Bypasser")
    member.guild = MagicMock(spec=discord.Guild)
    member.guild.id = 100

    with (
        patch("cogs.events.get_user_summary", new=AsyncMock(return_value="taste summary")),
        patch("cogs.events.build_chat_prompt", return_value="system prompt"),
    ):
        cog = cogs.events.EventsCog(bot)
        result = await cog._generate_ambient_roast(
            member,
            "scenario text",
            ["fallback line"],
            pre_recalled_memories=["fact"],
        )

    bot.memory_service.recall.assert_not_awaited()
    assert result == "a generated line"

    # Default None path (the two voice-event call sites) still runs the
    # internal chance-gated recall, unchanged.
    bot.memory_service.recall.reset_mock()
    with (
        patch("cogs.events.get_user_summary", new=AsyncMock(return_value="taste summary")),
        patch("cogs.events.build_chat_prompt", return_value="system prompt"),
        patch("cogs.events.random.random", return_value=0.0),  # force MEMORY_CALLBACK_CHANCE gate to pass
    ):
        await cog._generate_ambient_roast(member, "scenario text", ["fallback line"])

    bot.memory_service.recall.assert_awaited_once()


@pytest.mark.asyncio
async def test_ambient_roast_recall_is_guild_scoped():
    """Ambient voice-join roast (default pre_recalled_memories=None path) recalls
    with guild_scoped=True (MEM-01) — this surface is an unprompted broadcast to a
    channel, the exact case guild-scoping exists to close.
    """
    bot = _make_bot()
    bot.gemini_service = MagicMock()
    bot.gemini_service.chat = AsyncMock(return_value="a generated line")

    member = _make_target(user_id=5, display_name="Scoped")
    member.guild = MagicMock(spec=discord.Guild)
    member.guild.id = 100

    with (
        patch("cogs.events.get_user_summary", new=AsyncMock(return_value="taste summary")),
        patch("cogs.events.build_chat_prompt", return_value="system prompt"),
        patch("cogs.events.random.random", return_value=0.0),  # force MEMORY_CALLBACK_CHANCE gate to pass
    ):
        cog = cogs.events.EventsCog(bot)
        await cog._generate_ambient_roast(member, "scenario text", ["fallback line"])

    bot.memory_service.recall.assert_awaited_once()
    assert bot.memory_service.recall.call_args.kwargs.get("guild_scoped") is True


# ---------------------------------------------------------------------------
# (D) Phase 21 / MEM-01 — per-call-site guild-scoping opt-in lock
# ---------------------------------------------------------------------------


class TestGuildScopedOptIns:
    """Source-level assertions for surfaces too Discord-heavy to drive
    behaviorally (proactive callback, music-command callback) — per TESTING.md,
    Discord glue is structural-review; source assertions are the established
    idiom in this file and in tests/test_autoqueue_wiring.py.
    """

    def test_proactive_callback_recall_is_guild_scoped(self):
        src = inspect.getsource(cogs.events.EventsCog._maybe_fire_proactive_callback)
        assert "guild_scoped=True" in src

    def test_music_callback_recall_is_guild_scoped(self):
        src = inspect.getsource(cogs.music.MusicCog._build_roast_line)
        assert "guild_scoped=" in src
        assert "guild_id reserved" not in src

    def test_ask_callback_never_mentions_guild_scoped(self):
        """A second, cheap MEM-02 net that runs even if the behavioral test's
        mock stack drifts."""
        src = inspect.getsource(cogs.ai.AICog.ask.callback)
        assert "guild_scoped" not in src
