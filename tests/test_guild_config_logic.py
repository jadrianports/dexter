"""Exhaustive pure-unit tests for logic/guild_config.py (Phase 18 / CONFIG-02).

No mocks, no clocks, no RNG, no DB — every input is a plain Python dict or None.

If a test needs a mock the cut-line in logic/guild_config.py is wrong (D-05).
"""

import inspect

import logic.guild_config as guild_config_module
from logic.guild_config import decide_ambient_channel, is_ambient_channel

# ---------------------------------------------------------------------------
# Purity self-check: the module must not import discord/datetime/random
# ---------------------------------------------------------------------------


def test_module_imports_no_discord_datetime_or_random():
    """The pure seam must never import discord, datetime, or random (D-05)."""
    src = inspect.getsource(guild_config_module)
    assert "import discord" not in src
    assert "import datetime" not in src
    assert "import random" not in src


# ---------------------------------------------------------------------------
# decide_ambient_channel
# ---------------------------------------------------------------------------


class TestDecideAmbientChannel:
    """Full branch coverage for decide_ambient_channel (D-01)."""

    def test_no_row_returns_none(self):
        """No config row at all (guild never configured) -> None (silence)."""
        assert decide_ambient_channel(config_row=None) is None

    def test_unconfigured_row_returns_none_even_with_channel_set(self):
        """configured=False -> None, even if ambient_channel_id happens to be set."""
        result = decide_ambient_channel(config_row={"configured": False, "ambient_channel_id": "123"})
        assert result is None

    def test_configured_but_no_channel_returns_none(self):
        """configured=True but ambient_channel_id is None -> None (fail closed)."""
        result = decide_ambient_channel(config_row={"configured": True, "ambient_channel_id": None})
        assert result is None

    def test_configured_with_channel_returns_int(self):
        """configured=True + ambient_channel_id set -> the channel id as an int."""
        result = decide_ambient_channel(config_row={"configured": True, "ambient_channel_id": "123"})
        assert result == 123
        assert isinstance(result, int)

    def test_missing_configured_key_defaults_to_unconfigured(self):
        """A row with no 'configured' key at all defaults to False -> None."""
        result = decide_ambient_channel(config_row={"ambient_channel_id": "123"})
        assert result is None


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
        )
        assert result is True

    def test_mismatched_channel_returns_false(self):
        """A different channel id -> False."""
        result = is_ambient_channel(
            config_row={"configured": True, "ambient_channel_id": "123"},
            channel_id=999,
        )
        assert result is False

    def test_none_row_returns_false(self):
        """No config row at all -> False (never a match, never a crash)."""
        result = is_ambient_channel(config_row=None, channel_id=123)
        assert result is False

    def test_unconfigured_row_returns_false(self):
        """configured=False -> False, even if channel_id matches ambient_channel_id."""
        result = is_ambient_channel(
            config_row={"configured": False, "ambient_channel_id": "123"},
            channel_id=123,
        )
        assert result is False
