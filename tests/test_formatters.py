"""Tests for duration formatting and progress bar rendering."""

from utils.formatters import format_duration, parse_time, progress_bar


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


class TestParseTime:
    def test_raw_seconds_int(self):
        assert parse_time("90") == 90

    def test_mm_ss(self):
        assert parse_time("1:30") == 90

    def test_h_mm_ss(self):
        assert parse_time("1:01:30") == 3690

    def test_zero_minutes(self):
        assert parse_time("0:45") == 45

    def test_strips_whitespace(self):
        assert parse_time("  2:00 ") == 120

    def test_empty_string_is_none(self):
        assert parse_time("") is None

    def test_non_numeric_is_none(self):
        assert parse_time("abc") is None

    def test_seconds_out_of_range_is_none(self):
        """Seconds field > 59 is invalid."""
        assert parse_time("1:99") is None

    def test_negative_raw_seconds_is_none(self):
        assert parse_time("-5") is None

    def test_round_trip_with_format_duration(self):
        """parse_time(format_duration(x)) == x for typical values."""
        assert parse_time(format_duration(90)) == 90
        assert parse_time(format_duration(3690)) == 3690
        assert parse_time(format_duration(45)) == 45


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
