"""Exhaustive pure-unit tests for logic/guild_config.py (Phase 18 / CONFIG-02;
surface-keyed extension Phase 19 / ONBOARD-04 / D-22).

No mocks, no clocks, no RNG, no DB — every input is a plain Python dict or None.

If a test needs a mock the cut-line in logic/guild_config.py is wrong (D-05).
"""

import inspect

import logic.guild_config as guild_config_module
from logic.guild_config import AmbientSurface, decide_ambient_channel, is_ambient_channel

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
