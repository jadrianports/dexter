"""Tests for duration formatting and progress bar rendering."""

from utils.formatters import format_duration, progress_bar


class TestFormatDuration:
    def test_seconds_only(self):
        assert format_duration(45) == "0:45"

    def test_minutes_and_seconds(self):
        assert format_duration(200) == "3:20"

    def test_hours(self):
        assert format_duration(3661) == "1:01:01"

    def test_zero(self):
        assert format_duration(0) == "0:00"

    def test_exact_minute(self):
        assert format_duration(60) == "1:00"

    def test_single_digit_seconds_padded(self):
        assert format_duration(65) == "1:05"


class TestProgressBar:
    def test_half_progress(self):
        bar = progress_bar(100, 200, length=10)
        assert bar == "▓▓▓▓▓░░░░░ 1:40 / 3:20"

    def test_zero_progress(self):
        bar = progress_bar(0, 200, length=10)
        assert bar == "░░░░░░░░░░ 0:00 / 3:20"

    def test_full_progress(self):
        bar = progress_bar(200, 200, length=10)
        assert bar == "▓▓▓▓▓▓▓▓▓▓ 3:20 / 3:20"

    def test_over_total_clamps(self):
        bar = progress_bar(300, 200, length=10)
        assert bar == "▓▓▓▓▓▓▓▓▓▓ 3:20 / 3:20"
