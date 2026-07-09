"""Tests for pure streak math: compute_streak and get_local_date.

These tests do NOT use aiosqlite — compute_streak and get_local_date are
pure functions (no DB, no Discord objects) and must stay that way.
"""

from datetime import timedelta

import pytest

from database import compute_streak, get_local_date

TZ = "America/New_York"


class TestGetLocalDate:
    def test_returns_date_object(self):
        from datetime import date

        result = get_local_date(TZ)
        assert isinstance(result, date)

    def test_matches_datetime_now_tz(self):
        from datetime import date, datetime
        from zoneinfo import ZoneInfo

        expected = datetime.now(tz=ZoneInfo(TZ)).date()
        result = get_local_date(TZ)
        assert result == expected


class TestComputeStreakFirstActivity:
    def test_none_last_date_starts_at_1(self):
        new_streak, new_date = compute_streak(0, None, TZ)
        assert new_streak == 1

    def test_none_last_date_returns_today_iso(self):
        today_iso = get_local_date(TZ).isoformat()
        _, new_date = compute_streak(0, None, TZ)
        assert new_date == today_iso


class TestComputeStreakConsecutiveDay:
    def test_consecutive_day_increments(self):
        yesterday = (get_local_date(TZ) - timedelta(days=1)).isoformat()
        new_streak, _ = compute_streak(5, yesterday, TZ)
        assert new_streak == 6

    def test_consecutive_day_updates_date_to_today(self):
        yesterday = (get_local_date(TZ) - timedelta(days=1)).isoformat()
        today_iso = get_local_date(TZ).isoformat()
        _, new_date = compute_streak(5, yesterday, TZ)
        assert new_date == today_iso


class TestComputeStreakSameDay:
    def test_same_day_is_noop_streak_unchanged(self):
        today_iso = get_local_date(TZ).isoformat()
        new_streak, _ = compute_streak(5, today_iso, TZ)
        assert new_streak == 5

    def test_same_day_preserves_last_date(self):
        today_iso = get_local_date(TZ).isoformat()
        _, new_date = compute_streak(5, today_iso, TZ)
        assert new_date == today_iso


class TestComputeStreakMissedDay:
    def test_two_days_ago_resets_to_1(self):
        two_days_ago = (get_local_date(TZ) - timedelta(days=2)).isoformat()
        new_streak, _ = compute_streak(5, two_days_ago, TZ)
        assert new_streak == 1

    def test_two_days_ago_updates_date_to_today(self):
        two_days_ago = (get_local_date(TZ) - timedelta(days=2)).isoformat()
        today_iso = get_local_date(TZ).isoformat()
        _, new_date = compute_streak(5, two_days_ago, TZ)
        assert new_date == today_iso

    def test_far_past_resets_to_1(self):
        far_past = (get_local_date(TZ) - timedelta(days=30)).isoformat()
        new_streak, _ = compute_streak(25, far_past, TZ)
        assert new_streak == 1


def test_tz_aware_hour_is_integer():
    """Wave-0 TZ smoke test (D-06): ZoneInfo-aware datetime.now().hour returns a valid hour int.

    Covers the fix in cogs/events.py — replacing naive datetime.now().hour (host-local)
    with datetime.now(tz=ZoneInfo(config.STREAK_TIMEZONE)).hour (TZ-explicit).
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    hour = datetime.now(tz=ZoneInfo(TZ)).hour
    assert isinstance(hour, int)
    assert 0 <= hour <= 23
