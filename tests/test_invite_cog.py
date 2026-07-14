"""Unit tests for cogs/invite.py — the /invite slash command (Phase 22 / INVITE-02).

Mock style mirrors tests/test_memory_command.py (mocked interaction, no live
Discord connection).

Tests:
- test_invite_command_sends_the_canonical_url    — button URL == build_invite_url()'s output
- test_invite_command_is_public_not_ephemeral    — reply is public (D-05)
- test_invite_command_is_dm_allowed              — guild_only is False (D-06)
- test_invite_command_has_cooldown               — mirrors /help's cooldown (WR-03)
- test_invite_command_falls_back_to_config_client_id — application_id=None -> config.DISCORD_CLIENT_ID (WR-01)
- test_invite_command_guards_against_unresolved_client_id — both falsy -> ephemeral error, no malformed URL (WR-02)
- test_cog_does_not_construct_a_url_itself       — no literal oauth2 URL / oauth_url( in the cog (D-03)
- test_invite_cog_registered_at_both_bot_load_sites — Phase 8 scar: bot.py dual cog-registration
- test_invite_listed_in_help_commands            — /invite discoverable via /help (D-06)
"""

from __future__ import annotations

import inspect
import pathlib
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.invite as invite_module
import config
from cogs.invite import InviteCog
from logic.invite import build_invite_url

# ---------------------------------------------------------------------------
# Helpers to build a minimal fake interaction + bot environment
# ---------------------------------------------------------------------------


def _make_bot(application_id: int = 999888777) -> MagicMock:
    """Return a minimal fake bot (InviteCog has no DB/gemini dep)."""
    bot = MagicMock()
    bot.application_id = application_id
    return bot


def _make_interaction(user_id: int = 1) -> MagicMock:
    """Return a minimal fake discord.Interaction."""
    interaction = MagicMock(spec=discord.Interaction)

    user = MagicMock(spec=discord.Member)
    user.id = user_id
    user.display_name = "Invoker"
    user.bot = False
    interaction.user = user

    interaction.response = AsyncMock()
    return interaction


# ---------------------------------------------------------------------------
# /invite command behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invite_command_sends_the_canonical_url():
    """The sent view carries exactly one link-style button whose url matches
    build_invite_url()'s output byte-for-byte (T-22-02)."""
    bot = _make_bot()
    interaction = _make_interaction()
    cog = InviteCog(bot)

    await InviteCog.invite_command.callback(cog, interaction)

    interaction.response.send_message.assert_awaited_once()
    kwargs = interaction.response.send_message.call_args.kwargs
    view = kwargs["view"]
    assert len(view.children) == 1
    button = view.children[0]
    assert isinstance(button, discord.ui.Button)
    assert button.style == discord.ButtonStyle.link
    assert button.label == "Add to Discord"
    # WR-01: bot.application_id is now the authoritative source, checked
    # before config.DISCORD_CLIENT_ID -- so the expected URL is built from
    # the fake bot's application_id (999888777), not the config constant.
    expected_url = build_invite_url(
        client_id=bot.application_id,
        permissions_value=config.INVITE_PERMISSIONS_VALUE,
    )
    assert button.url == expected_url


@pytest.mark.asyncio
async def test_invite_command_is_public_not_ephemeral():
    """D-05: the reply is public — no ephemeral=True kwarg at all."""
    bot = _make_bot()
    interaction = _make_interaction()
    cog = InviteCog(bot)

    await InviteCog.invite_command.callback(cog, interaction)

    kwargs = interaction.response.send_message.call_args.kwargs
    assert "ephemeral" not in kwargs


def test_invite_command_is_dm_allowed():
    """D-06: guild_only defaults to False on discord.py 2.7.1 — this asserts
    nobody later slaps @app_commands.guild_only() on the command."""
    assert InviteCog.invite_command.guild_only is False


def test_invite_command_has_cooldown():
    """WR-03: /invite mirrors /help's cooldown -- a public reply with no
    cooldown is a channel-flood vector, so a single
    app_commands.checks.cooldown check must be registered."""
    assert len(InviteCog.invite_command.checks) == 1


@pytest.mark.asyncio
async def test_invite_command_falls_back_to_config_client_id(monkeypatch):
    """WR-01: bot.application_id is primary; when it's falsy (e.g. the bot
    isn't fully identified yet), the committed config.DISCORD_CLIENT_ID
    constant is used instead."""
    bot = _make_bot(application_id=None)
    interaction = _make_interaction()
    cog = InviteCog(bot)

    await InviteCog.invite_command.callback(cog, interaction)

    kwargs = interaction.response.send_message.call_args.kwargs
    button = kwargs["view"].children[0]
    expected_url = build_invite_url(
        client_id=config.DISCORD_CLIENT_ID,
        permissions_value=config.INVITE_PERMISSIONS_VALUE,
    )
    assert button.url == expected_url


@pytest.mark.asyncio
async def test_invite_command_guards_against_unresolved_client_id(monkeypatch):
    """WR-02: if both bot.application_id and config.DISCORD_CLIENT_ID are
    falsy, the command must not emit a malformed client_id=None URL -- it
    replies with an ephemeral error instead."""
    monkeypatch.setattr(config, "DISCORD_CLIENT_ID", 0)
    bot = _make_bot(application_id=None)
    interaction = _make_interaction()
    cog = InviteCog(bot)

    await InviteCog.invite_command.callback(cog, interaction)

    interaction.response.send_message.assert_awaited_once()
    kwargs = interaction.response.send_message.call_args.kwargs
    assert kwargs.get("ephemeral") is True
    assert "view" not in kwargs
    assert "embed" not in kwargs


def test_cog_does_not_construct_a_url_itself():
    """D-03: the cog calls the builder, period — no hand-built OAuth2 URL."""
    src = inspect.getsource(invite_module)
    assert "discord.com/oauth2" not in src
    assert "oauth_url(" not in src


# ---------------------------------------------------------------------------
# Wiring-regression tests (source-inspection, no live bot)
# ---------------------------------------------------------------------------


def test_invite_cog_registered_at_both_bot_load_sites():
    """Phase 8 scar: bot.py has TWO cog-registration sites (the
    _initialize_once list-form loop and the --first-run sequential
    fallback). If they drift, --first-run syncs a different command set than
    the running bot exposes — Phase 8 UAT surfaced /leaderboard, /stats, and
    the library commands missing this exact way. cogs.invite must appear in
    both."""
    src = pathlib.Path("bot.py").read_text(encoding="utf-8")
    assert src.count("cogs.invite") >= 2
    assert '"cogs.invite"' in src
    assert 'await bot.load_extension("cogs.invite")' in src


def test_invite_listed_in_help_commands():
    """D-06: /invite is discoverable from /help, as a Utility command (not
    an admin one)."""
    from cogs.help import ADMIN_COMMANDS_INFO, COMMANDS_INFO

    assert any(cmd.startswith("/invite") for cmd, _ in COMMANDS_INFO)
    assert not any(cmd.startswith("/invite") for cmd, _ in ADMIN_COMMANDS_INFO)
