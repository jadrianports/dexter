"""Exhaustive pure-unit tests for logic/vision.py (VIS-01 / D-04).

No mocks, no clocks, no RNG — all inputs are plain Python primitives.
Rolls (floats), the opt-out flag, and the pre-computed cooldown_elapsed bool
are passed directly, mirroring tests/test_proactive_logic.py's discipline.

If a test needs a mock the cut-line in logic/vision.py is wrong.
"""

import config
from logic.vision import should_fire_vision_roast

# ---------------------------------------------------------------------------
# Fixed inputs (mirrors config-derived boundary style from test_proactive_logic.py)
# ---------------------------------------------------------------------------

# Rolls that pass/fail the chance gate — derived from config, not magic numbers
CHANCE_PASS = config.VISION_ROAST_CHANCE - 0.01   # just under the threshold
CHANCE_FAIL = config.VISION_ROAST_CHANCE          # exactly at threshold -> False


# ---------------------------------------------------------------------------
# TestShouldFireVisionRoast
# ---------------------------------------------------------------------------


class TestShouldFireVisionRoast:
    """Full branch + boundary coverage for should_fire_vision_roast (D-04)."""

    # ── opt-out gate (cheapest, wins) ─────────────────────────────────────

    def test_opted_out_returns_false_regardless_of_rolls(self):
        """opted_out=True short-circuits before any other gate — always False."""
        result = should_fire_vision_roast(
            opted_out=True,
            cooldown_elapsed=True,
            chance_roll=0.0,
        )
        assert result is False

    def test_gate_order_opt_out_checked_before_cooldown_and_chance(self):
        """opt-out beats an otherwise-fully-passing cooldown/roll combo."""
        result = should_fire_vision_roast(
            opted_out=True,
            cooldown_elapsed=True,
            chance_roll=CHANCE_PASS,
        )
        assert result is False

    # ── cooldown gate ─────────────────────────────────────────────────────

    def test_cooldown_not_elapsed_returns_false(self):
        """cooldown_elapsed=False -> False even with a passing chance roll."""
        result = should_fire_vision_roast(
            opted_out=False,
            cooldown_elapsed=False,
            chance_roll=CHANCE_PASS,
        )
        assert result is False

    # ── chance gate ───────────────────────────────────────────────────────

    def test_chance_roll_at_threshold_returns_false(self):
        """chance_roll == chance -> False (the `<` boundary fails, not `<=`)."""
        result = should_fire_vision_roast(
            opted_out=False,
            cooldown_elapsed=True,
            chance_roll=CHANCE_FAIL,
        )
        assert result is False

    def test_chance_roll_well_above_threshold_returns_false(self):
        """chance_roll well above chance -> False."""
        result = should_fire_vision_roast(
            opted_out=False,
            cooldown_elapsed=True,
            chance_roll=0.99,
        )
        assert result is False

    # ── all gates pass ────────────────────────────────────────────────────

    def test_all_gates_pass_returns_true(self):
        """Not opted out, cooldown elapsed, chance roll passes -> True."""
        result = should_fire_vision_roast(
            opted_out=False,
            cooldown_elapsed=True,
            chance_roll=CHANCE_PASS,
        )
        assert result is True

    # ── custom threshold override ─────────────────────────────────────────

    def test_custom_chance_threshold_respected(self):
        """Passing a custom `chance` override is respected, not hard-coded to config."""
        # chance_roll=0.5, custom chance=0.6 -> 0.5 < 0.6 -> passes chance gate
        result = should_fire_vision_roast(
            opted_out=False,
            cooldown_elapsed=True,
            chance_roll=0.5,
            chance=0.6,
        )
        assert result is True

    def test_custom_chance_threshold_still_fails_above_it(self):
        """Custom `chance` override still fails when the roll meets/exceeds it."""
        result = should_fire_vision_roast(
            opted_out=False,
            cooldown_elapsed=True,
            chance_roll=0.6,
            chance=0.6,
        )
        assert result is False


# ---------------------------------------------------------------------------
# Config rarity invariant (T-17-RARITY)
# ---------------------------------------------------------------------------


def test_vision_chance_is_rarer_than_ambient():
    """VISION_ROAST_CHANCE must stay strictly below both ambient cadences.

    This is the anti-creepy discipline's test-enforced invariant (D-04):
    if a future edit ever raises the vision chance to/above the ambient
    UNPROMPTED_ROAST_CHANCE (0.30) or MEMORY_CALLBACK_CHANCE (0.35) rates,
    this test fails immediately.
    """
    assert config.VISION_ROAST_CHANCE < config.UNPROMPTED_ROAST_CHANCE
    assert config.VISION_ROAST_CHANCE < config.MEMORY_CALLBACK_CHANCE
