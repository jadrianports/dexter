"""Tests for seed_restore_test.py — pure seed-row data shape.

These tests do NOT use asyncpg — build_seed_rows() is a pure function
(no DB, no Discord objects, no subprocess) and must stay that way.
"""

import pytest

from scripts.seed_restore_test import build_seed_rows, SEED_USER_ID


class TestSeedData:
    """Validate the shape and content of the seed rows returned by build_seed_rows()."""

    def test_returns_dict_with_expected_keys(self):
        rows = build_seed_rows()
        assert "user_profiles" in rows
        assert "song_history" in rows
        assert "user_artist_counts" in rows

    def test_user_profiles_has_exactly_one_row(self):
        rows = build_seed_rows()
        assert len(rows["user_profiles"]) == 1

    def test_song_history_has_exactly_three_rows(self):
        rows = build_seed_rows()
        assert len(rows["song_history"]) == 3

    def test_user_artist_counts_has_exactly_two_rows(self):
        rows = build_seed_rows()
        assert len(rows["user_artist_counts"]) == 2

    def test_user_profile_user_id_matches_seed_constant(self):
        rows = build_seed_rows()
        profile = rows["user_profiles"][0]
        assert profile["user_id"] == SEED_USER_ID

    def test_user_id_is_string(self):
        rows = build_seed_rows()
        profile = rows["user_profiles"][0]
        assert isinstance(profile["user_id"], str)

    def test_song_history_rows_all_target_seed_user(self):
        rows = build_seed_rows()
        for row in rows["song_history"]:
            assert row["user_id"] == SEED_USER_ID

    def test_song_history_rows_have_title_field(self):
        rows = build_seed_rows()
        for row in rows["song_history"]:
            assert "title" in row
            assert row["title"]  # non-empty

    def test_song_history_rows_have_url_field(self):
        rows = build_seed_rows()
        for row in rows["song_history"]:
            assert "url" in row
            assert row["url"]  # non-empty

    def test_user_artist_counts_all_target_seed_user(self):
        rows = build_seed_rows()
        for row in rows["user_artist_counts"]:
            assert row["user_id"] == SEED_USER_ID

    def test_play_counts_are_positive_integers(self):
        rows = build_seed_rows()
        for row in rows["user_artist_counts"]:
            assert isinstance(row["play_count"], int)
            assert row["play_count"] > 0

    def test_total_songs_queued_is_positive_integer(self):
        rows = build_seed_rows()
        profile = rows["user_profiles"][0]
        assert isinstance(profile["total_songs_queued"], int)
        assert profile["total_songs_queued"] > 0

    def test_user_profile_has_username(self):
        rows = build_seed_rows()
        profile = rows["user_profiles"][0]
        assert "username" in profile
        assert profile["username"]  # non-empty

    def test_user_profile_has_streak_fields(self):
        """Streak columns exist (current_streak, longest_streak, last_streak_date)."""
        rows = build_seed_rows()
        profile = rows["user_profiles"][0]
        assert "current_streak" in profile
        assert "longest_streak" in profile
        assert "last_streak_date" in profile

    def test_seed_user_id_is_obviously_fake_snowflake(self):
        """SEED_USER_ID must be clearly non-production to prevent confusion."""
        assert SEED_USER_ID == "999999999999999999"


class TestTzAwareHour:
    """Smoke test: ZoneInfo TZ-aware hour returns a valid integer (Wave-0 gap)."""

    def test_tz_aware_hour_is_integer(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        hour = datetime.now(tz=ZoneInfo("America/New_York")).hour
        assert isinstance(hour, int)

    def test_tz_aware_hour_in_valid_range(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        hour = datetime.now(tz=ZoneInfo("America/New_York")).hour
        assert 0 <= hour <= 23
