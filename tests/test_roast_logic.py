"""Exhaustive pure-unit tests for logic/roasts.py (TEST-03 / D-03).

No mocks, no clocks, no RNG — all inputs are plain Python primitives.
Rolls (floats), local_hour (int), and cooldown deltas (float) are passed directly.

If a test needs a mock the cut-line in logic/roasts.py is wrong (D-06).
"""

import config
from logic.roasts import RoastScenario, cooldown_elapsed, decide_ambient_roast

# ---------------------------------------------------------------------------
# Fixed inputs (mirrors MOCK_* style from test_youtube.py)
# ---------------------------------------------------------------------------

# Hours derived from config so tests track config, not magic numbers
_LATE_NIGHT_LOW, _LATE_NIGHT_HIGH = config.LATE_NIGHT_HOURS  # (1, 5) inclusive
HOUR_LATE_NIGHT = _LATE_NIGHT_LOW + 1  # 2 — safely inside the window
HOUR_NORMAL = 12  # noon — outside any late-night window

# Rolls that pass the respective gates
CHANCE_PASS = config.UNPROMPTED_ROAST_CHANCE - 0.01  # just under the threshold
CHANCE_FAIL = config.UNPROMPTED_ROAST_CHANCE  # exactly at threshold → NONE

LATE_NIGHT_PASS = config.LATE_NIGHT_ROAST_CHANCE - 0.01  # just under → LATE_NIGHT
LATE_NIGHT_FAIL = config.LATE_NIGHT_ROAST_CHANCE  # exactly at → NONE

# Cooldown deltas
CEILING = config.AMBIENT_ROAST_CEILING_SECONDS  # 300
DELTA_AT_CEILING = float(CEILING)  # exactly at ceiling → elapsed
DELTA_ONE_UNDER = float(CEILING) - 1.0  # one second short → not elapsed
DELTA_WELL_OVER = float(CEILING) + 60.0  # well over → elapsed


# ---------------------------------------------------------------------------
# TestCooldownElapsed
# ---------------------------------------------------------------------------


class TestCooldownElapsed:
    """Full branch + boundary coverage for cooldown_elapsed (D-03)."""

    def test_exactly_at_ceiling_returns_true(self):
        """Exactly-at-ceiling (>=) is allowed — boundary is inclusive."""
        assert cooldown_elapsed(DELTA_AT_CEILING, CEILING) is True

    def test_one_under_ceiling_returns_false(self):
        """One second under ceiling — not enough time has passed."""
        assert cooldown_elapsed(DELTA_ONE_UNDER, CEILING) is False

    def test_well_over_ceiling_returns_true(self):
        """Comfortably past ceiling — always allowed."""
        assert cooldown_elapsed(DELTA_WELL_OVER, CEILING) is True

    def test_zero_seconds_no_prior_roast_returns_true(self):
        """0.0 vs 0 ceiling passes — degenerate case where no ceiling is enforced."""
        assert cooldown_elapsed(0.0, 0.0) is True

    def test_first_roast_large_delta_returns_true(self):
        """Large delta (e.g. user never roasted before, sentinel 0.0 used as last)."""
        assert cooldown_elapsed(999_999.0, CEILING) is True


# ---------------------------------------------------------------------------
# TestDecideAmbientRoast
# ---------------------------------------------------------------------------


class TestDecideAmbientRoast:
    """Full branch + boundary coverage for decide_ambient_roast (D-03 / TEST-03)."""

    # ── chance gate ──────────────────────────────────────────────────────────

    def test_chance_roll_at_threshold_returns_none(self):
        """chance_roll == chance → NONE (the `<` boundary fails, not `<=`)."""
        result = decide_ambient_roast(
            event="join",
            chance_roll=CHANCE_FAIL,
            late_night_roll=LATE_NIGHT_PASS,
            local_hour=HOUR_NORMAL,
            seconds_since_last_roast=DELTA_AT_CEILING,
        )
        assert result == RoastScenario.NONE

    def test_chance_roll_just_under_threshold_proceeds(self):
        """chance_roll just under chance → passes chance gate (leads to JOIN)."""
        result = decide_ambient_roast(
            event="join",
            chance_roll=CHANCE_PASS,
            late_night_roll=LATE_NIGHT_PASS,
            local_hour=HOUR_NORMAL,
            seconds_since_last_roast=DELTA_AT_CEILING,
        )
        assert result == RoastScenario.JOIN

    def test_chance_roll_well_above_threshold_returns_none(self):
        """chance_roll well above chance → NONE."""
        result = decide_ambient_roast(
            event="join",
            chance_roll=0.99,
            late_night_roll=LATE_NIGHT_PASS,
            local_hour=HOUR_NORMAL,
            seconds_since_last_roast=DELTA_AT_CEILING,
        )
        assert result == RoastScenario.NONE

    # ── cooldown gate ─────────────────────────────────────────────────────────

    def test_cooldown_exactly_at_ceiling_proceeds(self):
        """seconds_since == ceiling → cooldown elapsed, proceed (JOIN result)."""
        result = decide_ambient_roast(
            event="join",
            chance_roll=CHANCE_PASS,
            late_night_roll=LATE_NIGHT_PASS,
            local_hour=HOUR_NORMAL,
            seconds_since_last_roast=DELTA_AT_CEILING,
        )
        assert result == RoastScenario.JOIN

    def test_cooldown_one_under_ceiling_returns_none(self):
        """seconds_since one under ceiling → cooldown not elapsed → NONE."""
        result = decide_ambient_roast(
            event="join",
            chance_roll=CHANCE_PASS,
            late_night_roll=LATE_NIGHT_PASS,
            local_hour=HOUR_NORMAL,
            seconds_since_last_roast=DELTA_ONE_UNDER,
        )
        assert result == RoastScenario.NONE

    # ── join + normal hour ────────────────────────────────────────────────────

    def test_join_normal_hour_returns_join(self):
        """Voice join at normal hour → JOIN scenario."""
        result = decide_ambient_roast(
            event="join",
            chance_roll=CHANCE_PASS,
            late_night_roll=LATE_NIGHT_PASS,
            local_hour=HOUR_NORMAL,
            seconds_since_last_roast=DELTA_AT_CEILING,
        )
        assert result == RoastScenario.JOIN

    def test_join_hour_at_late_night_low_boundary(self):
        """Hour == LATE_NIGHT_LOW (1) is inside the late-night window."""
        result = decide_ambient_roast(
            event="join",
            chance_roll=CHANCE_PASS,
            late_night_roll=LATE_NIGHT_PASS,
            local_hour=_LATE_NIGHT_LOW,
            seconds_since_last_roast=DELTA_AT_CEILING,
        )
        assert result == RoastScenario.LATE_NIGHT

    def test_join_hour_at_late_night_high_boundary(self):
        """Hour == LATE_NIGHT_HIGH (5) is inside the late-night window (inclusive)."""
        result = decide_ambient_roast(
            event="join",
            chance_roll=CHANCE_PASS,
            late_night_roll=LATE_NIGHT_PASS,
            local_hour=_LATE_NIGHT_HIGH,
            seconds_since_last_roast=DELTA_AT_CEILING,
        )
        assert result == RoastScenario.LATE_NIGHT

    def test_join_hour_just_before_late_night_low(self):
        """Hour == LATE_NIGHT_LOW - 1 (0, midnight) is outside the window → JOIN."""
        result = decide_ambient_roast(
            event="join",
            chance_roll=CHANCE_PASS,
            late_night_roll=LATE_NIGHT_PASS,
            local_hour=max(0, _LATE_NIGHT_LOW - 1),
            seconds_since_last_roast=DELTA_AT_CEILING,
        )
        assert result == RoastScenario.JOIN

    # ── join + late night + second roll ──────────────────────────────────────

    def test_join_late_night_second_roll_passes_returns_late_night(self):
        """Late-night join + second roll passes → LATE_NIGHT."""
        result = decide_ambient_roast(
            event="join",
            chance_roll=CHANCE_PASS,
            late_night_roll=LATE_NIGHT_PASS,
            local_hour=HOUR_LATE_NIGHT,
            seconds_since_last_roast=DELTA_AT_CEILING,
        )
        assert result == RoastScenario.LATE_NIGHT

    def test_join_late_night_second_roll_fails_returns_none(self):
        """Late-night join + second roll fails (>= late_night_chance) → NONE."""
        result = decide_ambient_roast(
            event="join",
            chance_roll=CHANCE_PASS,
            late_night_roll=LATE_NIGHT_FAIL,
            local_hour=HOUR_LATE_NIGHT,
            seconds_since_last_roast=DELTA_AT_CEILING,
        )
        assert result == RoastScenario.NONE

    def test_join_late_night_second_roll_at_threshold_returns_none(self):
        """late_night_roll exactly at late_night_chance → fails (gate is `<`)."""
        result = decide_ambient_roast(
            event="join",
            chance_roll=CHANCE_PASS,
            late_night_roll=config.LATE_NIGHT_ROAST_CHANCE,
            local_hour=HOUR_LATE_NIGHT,
            seconds_since_last_roast=DELTA_AT_CEILING,
        )
        assert result == RoastScenario.NONE

    # ── leave ─────────────────────────────────────────────────────────────────

    def test_leave_normal_hour_returns_leave(self):
        """Voice leave at normal hour → LEAVE (no late-night branch for leave)."""
        result = decide_ambient_roast(
            event="leave",
            chance_roll=CHANCE_PASS,
            late_night_roll=0.0,
            local_hour=HOUR_NORMAL,
            seconds_since_last_roast=DELTA_AT_CEILING,
        )
        assert result == RoastScenario.LEAVE

    def test_leave_late_night_hour_still_returns_leave(self):
        """Leave during late-night → LEAVE (leave has no late-night second roll)."""
        result = decide_ambient_roast(
            event="leave",
            chance_roll=CHANCE_PASS,
            late_night_roll=0.0,
            local_hour=HOUR_LATE_NIGHT,
            seconds_since_last_roast=DELTA_AT_CEILING,
        )
        assert result == RoastScenario.LEAVE

    def test_leave_chance_gate_fails_returns_none(self):
        """Leave with chance_roll at threshold → NONE (chance gate fires first)."""
        result = decide_ambient_roast(
            event="leave",
            chance_roll=CHANCE_FAIL,
            late_night_roll=0.0,
            local_hour=HOUR_NORMAL,
            seconds_since_last_roast=DELTA_AT_CEILING,
        )
        assert result == RoastScenario.NONE

    def test_leave_cooldown_gate_fails_returns_none(self):
        """Leave with cooldown not elapsed → NONE (cooldown gate fires second)."""
        result = decide_ambient_roast(
            event="leave",
            chance_roll=CHANCE_PASS,
            late_night_roll=0.0,
            local_hour=HOUR_NORMAL,
            seconds_since_last_roast=DELTA_ONE_UNDER,
        )
        assert result == RoastScenario.NONE

    # ── unknown event ─────────────────────────────────────────────────────────

    def test_unknown_event_returns_none(self):
        """Unrecognised event string (e.g. channel-switch) → NONE."""
        result = decide_ambient_roast(
            event="move",
            chance_roll=CHANCE_PASS,
            late_night_roll=LATE_NIGHT_PASS,
            local_hour=HOUR_NORMAL,
            seconds_since_last_roast=DELTA_AT_CEILING,
        )
        assert result == RoastScenario.NONE

    def test_empty_event_string_returns_none(self):
        """Empty event string → NONE."""
        result = decide_ambient_roast(
            event="",
            chance_roll=CHANCE_PASS,
            late_night_roll=LATE_NIGHT_PASS,
            local_hour=HOUR_NORMAL,
            seconds_since_last_roast=DELTA_AT_CEILING,
        )
        assert result == RoastScenario.NONE

    # ── custom threshold overrides ────────────────────────────────────────────

    def test_custom_chance_threshold_respected(self):
        """Passing a custom `chance` override is respected."""
        # chance_roll=0.5, custom chance=0.6 → 0.5 < 0.6 → passes chance gate
        result = decide_ambient_roast(
            event="leave",
            chance_roll=0.5,
            late_night_roll=0.0,
            local_hour=HOUR_NORMAL,
            seconds_since_last_roast=DELTA_AT_CEILING,
            chance=0.6,
        )
        assert result == RoastScenario.LEAVE

    def test_custom_ceiling_seconds_respected(self):
        """Passing a custom `ceiling_seconds` override is respected."""
        # 50s elapsed vs ceiling=100 → not elapsed → NONE
        result = decide_ambient_roast(
            event="join",
            chance_roll=CHANCE_PASS,
            late_night_roll=LATE_NIGHT_PASS,
            local_hour=HOUR_NORMAL,
            seconds_since_last_roast=50.0,
            ceiling_seconds=100.0,
        )
        assert result == RoastScenario.NONE
