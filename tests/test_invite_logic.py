"""Exhaustive pure-unit tests for the invite-plumbing bitfield/URL surface
(Phase 22 / INVITE-01 / D-01, D-02, D-09) and logic/invite.py::build_invite_url
(INVITE-02 / D-03, D-07).

No mocks, no clocks, no RNG — all inputs are plain Python primitives, mirroring
tests/test_vision_logic.py's discipline. The ten-permission bitfield is derived
from named discord.Permissions() keyword flags before it is ever compared to the
literal 309240908864 — the magic number is never trusted on its own.

If a test needs a mock the cut-line in config.py / logic/invite.py is wrong.
"""

import discord

import config
from logic.invite import build_invite_url

# ---------------------------------------------------------------------------
# Task 1: config.py constants (D-01/D-02/D-04/D-09)
# ---------------------------------------------------------------------------


def test_bitfield_matches_ten_permission_derivation():
    """The locked bitfield is derivable from ten named Permissions() keywords.

    This is the self-documenting derivation (D-09): the magic number
    309240908864 is never asserted as a bare literal without first proving
    where it comes from.
    """
    derived = discord.Permissions(
        view_channel=True,
        send_messages=True,
        embed_links=True,
        attach_files=True,
        add_reactions=True,
        read_message_history=True,
        connect=True,
        speak=True,
        create_public_threads=True,
        send_messages_in_threads=True,
    )
    assert derived.value == 309240908864
    assert derived.value == config.INVITE_PERMISSIONS_VALUE


def test_bitfield_excludes_dangerous_permissions():
    """D-02 / T-22-01 negative-assertion lock.

    The invite bitfield must never grant administrator, manage_guild,
    manage_roles, manage_channels, ban_members, or kick_members. A future
    phase silently adding any of these fails CI instead of shipping unnoticed.
    """
    perms = discord.Permissions(config.INVITE_PERMISSIONS_VALUE)
    assert perms.administrator is False
    assert perms.manage_guild is False
    assert perms.manage_roles is False
    assert perms.manage_channels is False
    assert perms.ban_members is False
    assert perms.kick_members is False


def test_bitfield_grants_every_required_permission():
    """T-22-01b: the inverse lock — no silent capability loss.

    A well-meaning "tighten the bitfield" edit that drops attach_files,
    add_reactions, connect, or the /autolyrics thread permissions also
    fails CI, not just an escalation.
    """
    perms = discord.Permissions(config.INVITE_PERMISSIONS_VALUE)
    assert perms.view_channel is True
    assert perms.send_messages is True
    assert perms.embed_links is True
    assert perms.attach_files is True
    assert perms.add_reactions is True
    assert perms.read_message_history is True
    assert perms.connect is True
    assert perms.speak is True
    assert perms.create_public_threads is True
    assert perms.send_messages_in_threads is True


def test_client_id_is_a_positive_int():
    """Proves config.DISCORD_CLIENT_ID resolves in a zero-secret CI env (D-04)."""
    assert isinstance(config.DISCORD_CLIENT_ID, int)
    assert config.DISCORD_CLIENT_ID > 0


def test_scopes_constant_is_the_expected_tuple():
    assert config.INVITE_SCOPES == ("bot", "applications.commands")


# ---------------------------------------------------------------------------
# Task 2: logic/invite.py::build_invite_url (D-03/D-07)
# ---------------------------------------------------------------------------


def test_url_contains_expected_scopes():
    url = build_invite_url(
        client_id=config.DISCORD_CLIENT_ID,
        permissions_value=config.INVITE_PERMISSIONS_VALUE,
    )
    assert "scope=bot+applications.commands" in url


def test_url_contains_locked_permissions_value():
    url = build_invite_url(
        client_id=config.DISCORD_CLIENT_ID,
        permissions_value=config.INVITE_PERMISSIONS_VALUE,
    )
    assert "permissions=309240908864" in url
    assert f"client_id={config.DISCORD_CLIENT_ID}" in url


def test_url_is_the_literal_oauth2_endpoint():
    """No shortener, no vanity redirect (D-07)."""
    url = build_invite_url(
        client_id=config.DISCORD_CLIENT_ID,
        permissions_value=config.INVITE_PERMISSIONS_VALUE,
    )
    assert url.startswith("https://discord.com/oauth2/authorize?")


def test_scopes_are_overridable_but_default_to_the_config_tuple():
    """Passing an explicit scopes= changes the emitted scope= param."""
    url = build_invite_url(
        client_id=config.DISCORD_CLIENT_ID,
        permissions_value=config.INVITE_PERMISSIONS_VALUE,
        scopes=("bot",),
    )
    assert "scope=bot" in url
    assert "applications.commands" not in url


def test_builder_is_deterministic():
    """Pure function: identical args -> identical output, no clock/RNG/network."""
    kwargs = {
        "client_id": config.DISCORD_CLIENT_ID,
        "permissions_value": config.INVITE_PERMISSIONS_VALUE,
    }
    assert build_invite_url(**kwargs) == build_invite_url(**kwargs)
