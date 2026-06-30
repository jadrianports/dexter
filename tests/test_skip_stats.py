"""Pure unit tests for logic/skip_stats.compute_skip_rate (UX-02 / D-08).

No mocks, no fixtures, no DB — all inputs are plain Python primitives.
Tests the min-plays floor, division-edge cases, and representative ratios.

Coverage:
  - Below floor: returns None (D-08)
  - Exactly floor-1: still None (D-08)
  - At floor: valid (displays)
  - All-skipped at floor: 1.0
  - Representative ratio: 0.3
  - 0/0 with floor=0: 0.0 (no division-by-zero)
"""

from __future__ import annotations

import pytest
from logic.skip_stats import compute_skip_rate


class TestComputeSkipRate:
    """Branch coverage for compute_skip_rate min-plays floor + edge cases."""

    def test_below_floor_returns_none(self):
        """3 plays, floor=5 → None (D-08)."""
        assert compute_skip_rate(3, 3, min_plays=5) is None

    def test_exactly_floor_minus_one_returns_none(self):
        """4 plays, floor=5 → still None (floor is exclusive of 4, D-08)."""
        assert compute_skip_rate(4, 1, min_plays=5) is None

    def test_at_floor_all_skipped_returns_one(self):
        """5/5 plays skipped at floor=5 → 1.0 (valid, displays)."""
        assert compute_skip_rate(5, 5, min_plays=5) == 1.0

    def test_representative_ratio(self):
        """10 plays, 3 skipped, floor=5 → 0.3."""
        assert compute_skip_rate(10, 3, min_plays=5) == pytest.approx(0.3)

    def test_zero_plays_zero_skips_floor_zero_returns_zero(self):
        """0/0 with floor=0: floor satisfied, no division-by-zero, returns 0.0."""
        assert compute_skip_rate(0, 0, min_plays=0) == 0.0

    def test_zero_plays_floor_nonzero_returns_none(self):
        """0 plays, floor=5 → None (below floor)."""
        assert compute_skip_rate(0, 0, min_plays=5) is None

    def test_return_type_is_float_when_above_floor(self):
        """Return type is float (not int) when above the floor."""
        result = compute_skip_rate(10, 5, min_plays=5)
        assert isinstance(result, float)

    def test_never_raises(self):
        """compute_skip_rate must not raise for any valid int inputs."""
        for plays, skips, floor in [
            (0, 0, 0),
            (1, 0, 1),
            (100, 50, 5),
            (5, 5, 5),
        ]:
            compute_skip_rate(plays, skips, min_plays=floor)  # must not raise
