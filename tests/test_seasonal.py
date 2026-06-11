"""Tests for seasonal personality context."""

from datetime import datetime
from unittest.mock import patch

from personality.seasonal import get_seasonal_context


class TestSeasonalContext:
    def test_december_returns_christmas_context(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 12, 15)
            result = get_seasonal_context()
            assert "december" in result.lower() or "christmas" in result.lower()

    def test_october_returns_halloween_context(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 10, 20)
            result = get_seasonal_context()
            assert "october" in result.lower() or "halloween" in result.lower()

    def test_valentines_day(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 14)
            result = get_seasonal_context()
            assert "valentine" in result.lower()

    def test_new_years_day(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 1, 1)
            result = get_seasonal_context()
            assert "new year" in result.lower() or "resolution" in result.lower()

    def test_april_fools(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 1)
            result = get_seasonal_context()
            assert "april" in result.lower() or "chaotic" in result.lower()

    def test_normal_day_returns_empty(self):
        # September 15 is not covered by any seasonal branch
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 9, 15)
            result = get_seasonal_context()
            assert result == ""

    # ── New seasonal branches ──

    def test_thanksgiving_week_late_november(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 11, 26)  # Nov 26
            result = get_seasonal_context()
            assert result != ""
            assert "thanksgiving" in result.lower() or "november" in result.lower() or "holiday" in result.lower() or "relative" in result.lower() or "pandora" in result.lower()

    def test_thanksgiving_week_boundary_day_22(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 11, 22)  # first day of range
            result = get_seasonal_context()
            assert result != ""

    def test_st_patricks_day(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 17)
            result = get_seasonal_context()
            assert result != ""
            assert (
                "patrick" in result.lower()
                or "irish" in result.lower()
                or "st." in result.lower()
            )

    def test_fourth_of_july(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 4)
            result = get_seasonal_context()
            assert result != ""
            assert (
                "july" in result.lower()
                or "fourth" in result.lower()
                or "barbecue" in result.lower()
                or "independence" in result.lower()
            )

    def test_summer_june(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 20)
            result = get_seasonal_context()
            assert result != ""
            assert "summer" in result.lower() or "outside" in result.lower()

    def test_summer_august(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 8, 10)
            result = get_seasonal_context()
            assert result != ""
            assert "summer" in result.lower() or "outside" in result.lower()

    def test_non_seasonal_september_returns_empty(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 9, 15)
            result = get_seasonal_context()
            assert result == ""

    def test_non_seasonal_early_november_returns_empty(self):
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 11, 10)
            result = get_seasonal_context()
            assert result == ""
