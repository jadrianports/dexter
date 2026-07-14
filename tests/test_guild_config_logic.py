"""Exhaustive pure-unit tests for logic/guild_config.py (Phase 18 / CONFIG-02;
surface-keyed extension Phase 19 / ONBOARD-04 / D-22).

No mocks, no clocks, no RNG, no DB — every input is a plain Python dict or None.

If a test needs a mock the cut-line in logic/guild_config.py is wrong (D-05).
"""

import inspect

import logic.guild_config as guild_config_module
from logic.guild_config import (
    AmbientSurface,
    decide_ambient_channel,
    decide_interaction_allowed,
    is_ambient_channel,
)

# ---------------------------------------------------------------------------
# Purity self-check: the module must not import discord/datetime/random
# ---------------------------------------------------------------------------


def test_module_imports_no_discord_datetime_or_random():
    """The pure seam must never import discord, datetime, or random (D-05)."""
    src = inspect.getsource(guild_config_module)
    assert "import discord" not in src
    assert "import datetime" not in src
    assert "import random" not in src


def test_ambient_surface_has_exactly_three_members():
    """AmbientSurface has ROAST, VISION, PRESENCE — no more, no fewer."""
    assert {m.name for m in AmbientSurface} == {"ROAST", "VISION", "PRESENCE"}


def test_decide_ambient_channel_requires_surface_kwarg():
    """surface is required keyword-only with no default — omitting it raises TypeError."""
    try:
        decide_ambient_channel(config_row=None)
        raised = False
    except TypeError:
        raised = True
    assert raised


def test_is_ambient_channel_requires_surface_kwarg():
    """surface is required keyword-only with no default — omitting it raises TypeError."""
    try:
        is_ambient_channel(config_row=None, channel_id=123)
        raised = False
    except TypeError:
        raised = True
    assert raised


# ---------------------------------------------------------------------------
# decide_ambient_channel
# ---------------------------------------------------------------------------


class TestDecideAmbientChannel:
    """Full branch coverage for decide_ambient_channel (D-01/D-22)."""

    def test_no_row_returns_none(self):
        """No config row at all (guild never configured) -> None (silence)."""
        assert decide_ambient_channel(config_row=None, surface=AmbientSurface.ROAST) is None

    def test_unconfigured_row_returns_none_even_with_channel_set(self):
        """configured=False -> None, even if ambient_channel_id happens to be set."""
        result = decide_ambient_channel(
            config_row={"configured": False, "ambient_channel_id": "123"},
            surface=AmbientSurface.ROAST,
        )
        assert result is None

    def test_configured_but_no_channel_returns_none(self):
        """configured=True but ambient_channel_id is None -> None (fail closed)."""
        result = decide_ambient_channel(
            config_row={"configured": True, "ambient_channel_id": None},
            surface=AmbientSurface.ROAST,
        )
        assert result is None

    def test_configured_with_channel_returns_int(self):
        """configured=True + ambient_channel_id set -> the channel id as an int."""
        result = decide_ambient_channel(
            config_row={"configured": True, "ambient_channel_id": "123"},
            surface=AmbientSurface.ROAST,
        )
        assert result == 123
        assert isinstance(result, int)

    def test_missing_configured_key_defaults_to_unconfigured(self):
        """A row with no 'configured' key at all defaults to False -> None."""
        result = decide_ambient_channel(
            config_row={"ambient_channel_id": "123"},
            surface=AmbientSurface.ROAST,
        )
        assert result is None

    def test_malformed_channel_id_empty_string_returns_none(self):
        """WR-01: a malformed (empty-string) ambient_channel_id fails closed to None."""
        result = decide_ambient_channel(
            config_row={"configured": True, "ambient_channel_id": ""},
            surface=AmbientSurface.ROAST,
        )
        assert result is None

    def test_malformed_channel_id_non_numeric_string_returns_none(self):
        """WR-01: a non-numeric ambient_channel_id fails closed to None, never raises."""
        result = decide_ambient_channel(
            config_row={"configured": True, "ambient_channel_id": "abc"},
            surface=AmbientSurface.ROAST,
        )
        assert result is None

    # -- surface / toggle coverage (D-22) -----------------------------------

    def test_missing_toggle_keys_default_to_true_for_both_surfaces(self):
        """A row with neither toggle key set (fail-open, matches column DEFAULT true)."""
        row = {"configured": True, "ambient_channel_id": "123"}
        assert decide_ambient_channel(config_row=row, surface=AmbientSurface.ROAST) == 123
        assert decide_ambient_channel(config_row=row, surface=AmbientSurface.VISION) == 123
        assert decide_ambient_channel(config_row=row, surface=AmbientSurface.PRESENCE) == 123

    def test_ambient_roasts_enabled_false_silences_roast(self):
        """ambient_roasts_enabled=False -> None for ROAST."""
        row = {
            "configured": True,
            "ambient_channel_id": "123",
            "ambient_roasts_enabled": False,
            "vision_roasts_enabled": True,
        }
        assert decide_ambient_channel(config_row=row, surface=AmbientSurface.ROAST) is None

    def test_ambient_roasts_enabled_false_silences_presence(self):
        """ambient_roasts_enabled=False -> None for PRESENCE (shares the ROAST column, D-18)."""
        row = {
            "configured": True,
            "ambient_channel_id": "123",
            "ambient_roasts_enabled": False,
            "vision_roasts_enabled": True,
        }
        assert decide_ambient_channel(config_row=row, surface=AmbientSurface.PRESENCE) is None

    def test_ambient_roasts_enabled_false_does_not_silence_vision(self):
        """ambient_roasts_enabled=False does NOT affect VISION — independent toggles."""
        row = {
            "configured": True,
            "ambient_channel_id": "123",
            "ambient_roasts_enabled": False,
            "vision_roasts_enabled": True,
        }
        assert decide_ambient_channel(config_row=row, surface=AmbientSurface.VISION) == 123

    def test_vision_roasts_enabled_false_silences_vision(self):
        """vision_roasts_enabled=False -> None for VISION."""
        row = {
            "configured": True,
            "ambient_channel_id": "123",
            "ambient_roasts_enabled": True,
            "vision_roasts_enabled": False,
        }
        assert decide_ambient_channel(config_row=row, surface=AmbientSurface.VISION) is None

    def test_vision_roasts_enabled_false_does_not_silence_roast_or_presence(self):
        """vision_roasts_enabled=False does NOT affect ROAST/PRESENCE — independent toggles."""
        row = {
            "configured": True,
            "ambient_channel_id": "123",
            "ambient_roasts_enabled": True,
            "vision_roasts_enabled": False,
        }
        assert decide_ambient_channel(config_row=row, surface=AmbientSurface.ROAST) == 123
        assert decide_ambient_channel(config_row=row, surface=AmbientSurface.PRESENCE) == 123

    # -- silenced coverage (D-14) --------------------------------------------

    def test_silenced_true_silences_roast(self):
        """silenced=True -> None for ROAST, even on a configured+toggled-on row."""
        row = {
            "configured": True,
            "ambient_channel_id": "500",
            "ambient_roasts_enabled": True,
            "silenced": True,
        }
        assert decide_ambient_channel(config_row=row, surface=AmbientSurface.ROAST) is None

    def test_silenced_true_silences_vision(self):
        """silenced=True -> None for VISION, even on a configured+toggled-on row."""
        row = {
            "configured": True,
            "ambient_channel_id": "500",
            "vision_roasts_enabled": True,
            "silenced": True,
        }
        assert decide_ambient_channel(config_row=row, surface=AmbientSurface.VISION) is None

    def test_silenced_true_silences_presence(self):
        """silenced=True -> None for PRESENCE, even on a configured+toggled-on row."""
        row = {
            "configured": True,
            "ambient_channel_id": "500",
            "ambient_roasts_enabled": True,
            "silenced": True,
        }
        assert decide_ambient_channel(config_row=row, surface=AmbientSurface.PRESENCE) is None

    def test_silenced_key_omitted_still_resolves_channel(self):
        """A row omitting 'silenced' entirely still resolves its channel (default-False,
        backward-compat with every pre-Phase-20 row/mock)."""
        row = {
            "configured": True,
            "ambient_channel_id": "500",
            "ambient_roasts_enabled": True,
        }
        assert decide_ambient_channel(config_row=row, surface=AmbientSurface.ROAST) == 500

    def test_silenced_explicitly_false_still_resolves_channel(self):
        """silenced=False (explicit) still resolves the channel."""
        row = {
            "configured": True,
            "ambient_channel_id": "500",
            "ambient_roasts_enabled": True,
            "silenced": False,
        }
        assert decide_ambient_channel(config_row=row, surface=AmbientSurface.ROAST) == 500


# ---------------------------------------------------------------------------
# is_ambient_channel
# ---------------------------------------------------------------------------


class TestIsAmbientChannel:
    """Full branch coverage for is_ambient_channel (CONFIG-02 predicate)."""

    def test_matching_channel_returns_true(self):
        """The configured channel id matches channel_id -> True."""
        result = is_ambient_channel(
            config_row={"configured": True, "ambient_channel_id": "123"},
            channel_id=123,
            surface=AmbientSurface.ROAST,
        )
        assert result is True

    def test_mismatched_channel_returns_false(self):
        """A different channel id -> False."""
        result = is_ambient_channel(
            config_row={"configured": True, "ambient_channel_id": "123"},
            channel_id=999,
            surface=AmbientSurface.ROAST,
        )
        assert result is False

    def test_none_row_returns_false(self):
        """No config row at all -> False (never a match, never a crash)."""
        result = is_ambient_channel(config_row=None, channel_id=123, surface=AmbientSurface.ROAST)
        assert result is False

    def test_unconfigured_row_returns_false(self):
        """configured=False -> False, even if channel_id matches ambient_channel_id."""
        result = is_ambient_channel(
            config_row={"configured": False, "ambient_channel_id": "123"},
            channel_id=123,
            surface=AmbientSurface.ROAST,
        )
        assert result is False

    def test_malformed_channel_id_returns_false(self):
        """WR-01: a malformed ambient_channel_id fails closed to False, never raises."""
        result = is_ambient_channel(
            config_row={"configured": True, "ambient_channel_id": "not-a-number"},
            channel_id=123,
            surface=AmbientSurface.ROAST,
        )
        assert result is False

    def test_vision_toggle_off_returns_false_for_vision_surface(self):
        """vision_roasts_enabled=False -> False for VISION even on a matching channel."""
        result = is_ambient_channel(
            config_row={
                "configured": True,
                "ambient_channel_id": "123",
                "vision_roasts_enabled": False,
            },
            channel_id=123,
            surface=AmbientSurface.VISION,
        )
        assert result is False

    def test_vision_toggle_off_does_not_affect_roast_surface(self):
        """vision_roasts_enabled=False does not silence the ROAST surface on the same channel."""
        result = is_ambient_channel(
            config_row={
                "configured": True,
                "ambient_channel_id": "123",
                "vision_roasts_enabled": False,
            },
            channel_id=123,
            surface=AmbientSurface.ROAST,
        )
        assert result is True

    def test_silenced_row_returns_false_dispatch_through(self):
        """A silenced row -> False (is_ambient_channel dispatches on decide_ambient_channel,
        inheriting the D-14 silenced branch for free — never re-derives it)."""
        result = is_ambient_channel(
            config_row={
                "configured": True,
                "ambient_channel_id": "500",
                "ambient_roasts_enabled": True,
                "silenced": True,
            },
            channel_id=500,
            surface=AmbientSurface.ROAST,
        )
        assert result is False


# ---------------------------------------------------------------------------
# decide_interaction_allowed
# ---------------------------------------------------------------------------


class TestDecideInteractionAllowed:
    """Full branch coverage for decide_interaction_allowed (D-13 / OWNER-05)."""

    def test_owner_always_allowed_even_blocked_and_silenced(self):
        """is_owner=True -> True regardless of blocked/silenced (T-20-06: owner never
        locked out, even by self-silencing/blocking the home guild)."""
        assert decide_interaction_allowed(is_owner=True, has_guild=True, blocked=True, silenced=True) is True

    def test_dm_guildless_always_allowed(self):
        """has_guild=False (DM/guild-less) -> True, even for a non-owner and even with
        blocked/silenced set (D-13 DM exemption)."""
        assert decide_interaction_allowed(is_owner=False, has_guild=False, blocked=True, silenced=True) is True

    def test_blocked_refuses(self):
        """Non-owner, has guild, blocked=True, silenced=False -> False."""
        assert decide_interaction_allowed(is_owner=False, has_guild=True, blocked=True, silenced=False) is False

    def test_silenced_refuses(self):
        """Non-owner, has guild, blocked=False, silenced=True -> False."""
        assert decide_interaction_allowed(is_owner=False, has_guild=True, blocked=False, silenced=True) is False

    def test_neither_flag_allows(self):
        """Non-owner, has guild, blocked=False, silenced=False -> True (the all-clear case)."""
        assert decide_interaction_allowed(is_owner=False, has_guild=True, blocked=False, silenced=False) is True

    def test_requires_all_kwargs_keyword_only(self):
        """All four args are required keyword-only with no default -- a positional call or an
        omitted arg raises TypeError."""
        try:
            decide_interaction_allowed(True, True, True, True)  # positional -> TypeError
            raised = False
        except TypeError:
            raised = True
        assert raised

        try:
            decide_interaction_allowed(is_owner=True, has_guild=True, blocked=True)  # missing silenced
            raised = False
        except TypeError:
            raised = True
        assert raised

    def test_source_still_imports_no_discord_datetime_or_random(self):
        """Adding decide_interaction_allowed must not introduce discord/datetime/random imports
        (extends the purity self-check at module scope)."""
        src = inspect.getsource(guild_config_module)
        assert "import discord" not in src
        assert "import datetime" not in src
        assert "import random" not in src
