"""Exhaustive pure-unit tests for logic/proactive.py (PROACT-01 / D-02).

No mocks, no clocks, no RNG — all inputs are plain Python primitives.
Rolls (floats) and daily counts (ints) are passed directly.

If a test needs a mock the cut-line in logic/proactive.py is wrong (mirrors
tests/test_roast_logic.py's D-06 discipline).
"""

import config
from logic.proactive import should_fire_proactive_callback

# ---------------------------------------------------------------------------
# Fixed inputs (mirrors config-derived boundary style from test_roast_logic.py)
# ---------------------------------------------------------------------------

# Rolls that pass/fail the chance gate — derived from config, not magic numbers
CHANCE_PASS = config.PROACTIVE_CALLBACK_CHANCE - 0.01  # just under the threshold
CHANCE_FAIL = config.PROACTIVE_CALLBACK_CHANCE  # exactly at threshold -> False

# Daily-cap boundary values — derived from config
DAILY_CAP = config.PROACTIVE_CALLBACK_DAILY_CAP
COUNT_AT_CAP = DAILY_CAP  # exactly at cap -> False
COUNT_ONE_UNDER_CAP = DAILY_CAP - 1  # one under cap -> True


# ---------------------------------------------------------------------------
# TestShouldFireProactiveCallback
# ---------------------------------------------------------------------------


class TestShouldFireProactiveCallback:
    """Full branch + boundary coverage for should_fire_proactive_callback (D-02)."""

    # ── opt-out gate ──────────────────────────────────────────────────────

    def test_opted_out_returns_false_regardless_of_rolls(self):
        """opted_out=True short-circuits before any other gate — always False."""
        result = should_fire_proactive_callback(
            opted_out=True,
            chance_roll=0.0,
            daily_count=0,
        )
        assert result is False

    def test_opted_out_returns_false_even_with_passing_rolls(self):
        """opted_out=True beats an otherwise-fully-passing roll/count combo."""
        result = should_fire_proactive_callback(
            opted_out=True,
            chance_roll=CHANCE_PASS,
            daily_count=COUNT_ONE_UNDER_CAP,
        )
        assert result is False

    # ── chance gate ───────────────────────────────────────────────────────

    def test_chance_roll_at_threshold_returns_false(self):
        """chance_roll == chance -> False (the `<` boundary fails, not `<=`)."""
        result = should_fire_proactive_callback(
            opted_out=False,
            chance_roll=CHANCE_FAIL,
            daily_count=0,
        )
        assert result is False

    def test_chance_roll_just_under_threshold_returns_true(self):
        """chance_roll just under chance, daily_count=0, daily_cap=1 -> True."""
        result = should_fire_proactive_callback(
            opted_out=False,
            chance_roll=CHANCE_PASS,
            daily_count=0,
        )
        assert result is True

    def test_chance_roll_well_above_threshold_returns_false(self):
        """chance_roll well above chance -> False."""
        result = should_fire_proactive_callback(
            opted_out=False,
            chance_roll=0.99,
            daily_count=0,
        )
        assert result is False

    # ── daily-cap gate ────────────────────────────────────────────────────

    def test_daily_count_at_cap_returns_false(self):
        """daily_count == daily_cap (at ceiling) -> False (inclusive ceiling fails)."""
        result = should_fire_proactive_callback(
            opted_out=False,
            chance_roll=CHANCE_PASS,
            daily_count=COUNT_AT_CAP,
        )
        assert result is False

    def test_daily_count_one_under_cap_returns_true(self):
        """daily_count == daily_cap - 1 -> True (still room under the ceiling)."""
        result = should_fire_proactive_callback(
            opted_out=False,
            chance_roll=CHANCE_PASS,
            daily_count=COUNT_ONE_UNDER_CAP,
        )
        assert result is True

    def test_daily_count_well_over_cap_returns_false(self):
        """daily_count comfortably above daily_cap -> False."""
        result = should_fire_proactive_callback(
            opted_out=False,
            chance_roll=CHANCE_PASS,
            daily_count=DAILY_CAP + 5,
        )
        assert result is False

    # ── custom threshold overrides ───────────────────────────────────────

    def test_custom_chance_threshold_respected(self):
        """Passing a custom `chance` override is respected, not hard-coded to config."""
        # chance_roll=0.5, custom chance=0.6 -> 0.5 < 0.6 -> passes chance gate
        result = should_fire_proactive_callback(
            opted_out=False,
            chance_roll=0.5,
            daily_count=0,
            chance=0.6,
        )
        assert result is True

    def test_custom_chance_threshold_still_fails_above_it(self):
        """Custom `chance` override still fails when the roll exceeds it."""
        result = should_fire_proactive_callback(
            opted_out=False,
            chance_roll=0.65,
            daily_count=0,
            chance=0.6,
        )
        assert result is False

    def test_custom_daily_cap_respected(self):
        """Passing a custom `daily_cap` override is respected, not hard-coded to config."""
        # daily_count=2, custom daily_cap=3 -> 2 < 3 -> passes cap gate
        result = should_fire_proactive_callback(
            opted_out=False,
            chance_roll=CHANCE_PASS,
            daily_count=2,
            daily_cap=3,
        )
        assert result is True

    def test_custom_daily_cap_still_fails_at_it(self):
        """Custom `daily_cap` override still fails exactly at the ceiling."""
        result = should_fire_proactive_callback(
            opted_out=False,
            chance_roll=CHANCE_PASS,
            daily_count=3,
            daily_cap=3,
        )
        assert result is False

    # ── gate ordering ─────────────────────────────────────────────────────

    def test_gate_order_opt_out_checked_before_chance(self):
        """opt-out is checked before the chance roll (cheapest-first ordering)."""
        # A passing chance roll would otherwise proceed; opt-out must still win.
        result = should_fire_proactive_callback(
            opted_out=True,
            chance_roll=CHANCE_PASS,
            daily_count=0,
        )
        assert result is False

    def test_gate_order_chance_checked_before_daily_cap(self):
        """chance gate fires before the daily-cap gate is even relevant."""
        # daily_count under cap would pass that gate, but the chance roll fails first.
        result = should_fire_proactive_callback(
            opted_out=False,
            chance_roll=CHANCE_FAIL,
            daily_count=0,
        )
        assert result is False

    # ── all gates pass ───────────────────────────────────────────────────

    def test_all_gates_pass_returns_true(self):
        """Not opted out, chance roll passes, daily count under cap -> True."""
        result = should_fire_proactive_callback(
            opted_out=False,
            chance_roll=CHANCE_PASS,
            daily_count=COUNT_ONE_UNDER_CAP,
        )
        assert result is True


# ---------------------------------------------------------------------------
# Config rarity invariant (T-16-RARITY)
# ---------------------------------------------------------------------------


def test_proactive_chance_is_rarer_than_ambient():
    """PROACTIVE_CALLBACK_CHANCE must stay strictly below both ambient cadences.

    This is the anti-creepy discipline's test-enforced invariant (T-16-RARITY):
    if a future edit ever raises the proactive chance to/above the ambient
    UNPROMPTED_ROAST_CHANCE (0.30) or MEMORY_CALLBACK_CHANCE (0.35) rates, this
    test fails immediately.
    """
    assert config.PROACTIVE_CALLBACK_CHANCE < config.UNPROMPTED_ROAST_CHANCE
    assert config.PROACTIVE_CALLBACK_CHANCE < config.MEMORY_CALLBACK_CHANCE
