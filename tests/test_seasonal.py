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
        with patch("personality.seasonal.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 15)
            result = get_seasonal_context()
            assert result == ""
