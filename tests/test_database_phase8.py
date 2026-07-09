"""Phase 8 PostgreSQL integration tests — leaderboard aggregates + daily stats.

These tests require a live PostgreSQL database.
Set TEST_DATABASE_URL or ensure postgresql://dexter:dexter@localhost:5432/dexter_test
is reachable before running.

The pool fixture is defined in tests/conftest.py — it calls init_db, yields the
pool, and drops all tables on teardown.

Autonomous gate (no live DB needed): pytest --collect-only exits 0.
Full integration run: pytest tests/test_database_phase8.py -x (requires dexter_test DB).
"""

from __future__ import annotations

import pytest

from database import (
    get_daily_stats_row,
    get_images_today_global,
    get_leaderboard_skips,
    get_leaderboard_songs,
    get_leaderboard_streaks,
    increment_daily_stat,
    log_song,
    log_track_batch,
)

# ---------------------------------------------------------------------------
# TestTotalErrorsColumn — D-23 (OPS-01)
# ---------------------------------------------------------------------------


class TestTotalErrorsColumn:
    """Verify the total_errors column exists and round-trips via increment_daily_stat."""

    @pytest.mark.asyncio
    async def test_total_errors_column_exists(self, pool):
        """total_errors column must be present on bot_daily_stats after init_db."""
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = 'public'"
                "   AND table_name = 'bot_daily_stats'"
                "   AND column_name = 'total_errors'"
            )
        assert len(rows) == 1, "total_errors column missing from bot_daily_stats"

    @pytest.mark.asyncio
    async def test_total_errors_increment(self, pool):
        """increment_daily_stat('total_errors') must upsert without raising;
        calling it twice must yield total_errors == 2 in get_daily_stats_row."""
        await increment_daily_stat(pool, "total_errors")
        await increment_daily_stat(pool, "total_errors")
        stats = await get_daily_stats_row(pool)
        assert stats["total_errors"] == 2, f"Expected total_errors == 2, got {stats['total_errors']}"


# ---------------------------------------------------------------------------
# TestGetDailyStatsRow — D-22/D-25 (OPS-01)
# ---------------------------------------------------------------------------


class TestGetDailyStatsRow:
    """Verify get_daily_stats_row returns the correct shape when no row exists."""

    @pytest.mark.asyncio
    async def test_get_daily_stats_row_empty(self, pool):
        """On a clean DB (no today row), get_daily_stats_row must return a dict
        with all five keys equal to 0."""
        stats = await get_daily_stats_row(pool)
        assert isinstance(stats, dict), "Expected a dict return value"
        expected_keys = {
            "total_commands",
            "total_songs_played",
            "total_ai_queries",
            "total_images_generated",
            "total_errors",
        }
        for key in expected_keys:
            assert key in stats, f"Missing key in get_daily_stats_row result: {key}"
            assert stats[key] == 0, f"Expected {key} == 0 on empty DB, got {stats[key]}"


# ---------------------------------------------------------------------------
# TestLeaderboardSongs — D-10/D-14/D-16/D-18 (SOCIAL-02)
# ---------------------------------------------------------------------------


class TestLeaderboardSongs:
    """Verify get_leaderboard_songs per-guild scoping and tie-break logic."""

    @pytest.mark.asyncio
    async def test_leaderboard_songs_guild_scoped(self, pool):
        """get_leaderboard_songs(pool, 'G1') must count only G1 rows, not G2 (D-10/D-14)."""
        # Insert 3 songs in G1 for user1, 2 songs in G2 for user2
        for i in range(3):
            await log_track_batch(
                pool,
                guild_id="G1",
                user_id="u_scope1",
                username="ScopeUser1",
                title=f"G1 Song {i}",
                artist="Artist A",
                url=f"https://yt.com/g1_{i}",
                duration=200,
            )
        for i in range(2):
            await log_track_batch(
                pool,
                guild_id="G2",
                user_id="u_scope2",
                username="ScopeUser2",
                title=f"G2 Song {i}",
                artist="Artist B",
                url=f"https://yt.com/g2_{i}",
                duration=200,
            )

        g1_rows = await get_leaderboard_songs(pool, "G1")
        user_ids_in_g1 = [r["user_id"] for r in g1_rows]

        assert "u_scope1" in user_ids_in_g1, "u_scope1 should appear in G1 leaderboard"
        assert "u_scope2" not in user_ids_in_g1, "u_scope2 should NOT appear in G1 leaderboard"

        # Verify the count for G1 reflects only G1 history
        g1_user_row = next(r for r in g1_rows if r["user_id"] == "u_scope1")
        assert g1_user_row["songs_queued"] == 3, (
            f"Expected songs_queued=3 for G1 user, got {g1_user_row['songs_queued']}"
        )

    @pytest.mark.asyncio
    async def test_leaderboard_tie_break(self, pool):
        """Two users with equal song count: the one with older first_seen_at ranks first (D-16)."""
        # Insert songs so both users have 2 songs each in guild TG
        # older_user is created first (earlier first_seen_at)
        await log_track_batch(
            pool,
            guild_id="TG",
            user_id="u_older",
            username="OlderUser",
            title="Song A",
            artist="Art",
            url="https://yt.com/ta1",
            duration=200,
        )
        await log_track_batch(
            pool,
            guild_id="TG",
            user_id="u_older",
            username="OlderUser",
            title="Song B",
            artist="Art",
            url="https://yt.com/ta2",
            duration=200,
        )
        # Newer user gets same count
        await log_track_batch(
            pool,
            guild_id="TG",
            user_id="u_newer",
            username="NewerUser",
            title="Song C",
            artist="Art",
            url="https://yt.com/tn1",
            duration=200,
        )
        await log_track_batch(
            pool,
            guild_id="TG",
            user_id="u_newer",
            username="NewerUser",
            title="Song D",
            artist="Art",
            url="https://yt.com/tn2",
            duration=200,
        )

        rows = await get_leaderboard_songs(pool, "TG")
        assert len(rows) >= 2, "Expected at least 2 rows in tie-break test"
        # Both have 2 songs — older first_seen_at should rank first
        # u_older was inserted first so has an earlier first_seen_at
        assert rows[0]["user_id"] == "u_older", (
            f"Expected u_older to rank first (older first_seen_at), got {rows[0]['user_id']}"
        )

    @pytest.mark.asyncio
    async def test_leaderboard_empty_guild(self, pool):
        """A guild with no history must return empty lists for all three helpers."""
        songs = await get_leaderboard_songs(pool, "EMPTY_GUILD_XYZ")
        skips = await get_leaderboard_skips(pool, "EMPTY_GUILD_XYZ")
        streaks = await get_leaderboard_streaks(pool, "EMPTY_GUILD_XYZ")

        assert songs == [], f"Expected empty list for songs, got {songs}"
        assert skips == [], f"Expected empty list for skips, got {skips}"
        assert streaks == [], f"Expected empty list for streaks, got {streaks}"


# ---------------------------------------------------------------------------
# TestLeaderboardSkips — D-12/D-18 (SOCIAL-02)
# ---------------------------------------------------------------------------


class TestLeaderboardSkips:
    """Verify get_leaderboard_skips counts only was_skipped=true rows (D-12/D-18)."""

    @pytest.mark.asyncio
    async def test_leaderboard_skips_filter(self, pool):
        """Only was_skipped=true rows should be counted; zero-skip titles excluded (D-12/D-18)."""
        # Insert 2 skipped plays + 1 non-skipped play for "Skippy Song" in guild SK
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO song_history"
                " (guild_id, user_id, title, url, duration_seconds, was_skipped)"
                " VALUES ($1, $2, $3, $4, $5, $6)",
                "SK",
                "u_sk1",
                "Skippy Song",
                "https://yt.com/sk1",
                200,
                True,
            )
            await conn.execute(
                "INSERT INTO song_history"
                " (guild_id, user_id, title, url, duration_seconds, was_skipped)"
                " VALUES ($1, $2, $3, $4, $5, $6)",
                "SK",
                "u_sk1",
                "Skippy Song",
                "https://yt.com/sk2",
                200,
                True,
            )
            await conn.execute(
                "INSERT INTO song_history"
                " (guild_id, user_id, title, url, duration_seconds, was_skipped)"
                " VALUES ($1, $2, $3, $4, $5, $6)",
                "SK",
                "u_sk1",
                "Skippy Song",
                "https://yt.com/sk3",
                200,
                False,
            )
            # "Never Skipped" song — 2 plays, 0 skips; must be excluded (D-18)
            await conn.execute(
                "INSERT INTO song_history"
                " (guild_id, user_id, title, url, duration_seconds, was_skipped)"
                " VALUES ($1, $2, $3, $4, $5, $6)",
                "SK",
                "u_sk1",
                "Never Skipped",
                "https://yt.com/ns1",
                200,
                False,
            )
            await conn.execute(
                "INSERT INTO song_history"
                " (guild_id, user_id, title, url, duration_seconds, was_skipped)"
                " VALUES ($1, $2, $3, $4, $5, $6)",
                "SK",
                "u_sk1",
                "Never Skipped",
                "https://yt.com/ns2",
                200,
                False,
            )

        rows = await get_leaderboard_skips(pool, "SK")
        titles = [r["title"] for r in rows]

        assert "Skippy Song" in titles, "Skippy Song (2 skips) should appear in skips board"
        assert "Never Skipped" not in titles, "Never Skipped (0 skips) must be excluded from skips board (D-18)"

        # Verify skip_count is correct — only the 2 skipped plays
        skippy_row = next(r for r in rows if r["title"] == "Skippy Song")
        assert skippy_row["skip_count"] == 2, f"Expected skip_count=2 for Skippy Song, got {skippy_row['skip_count']}"


# ---------------------------------------------------------------------------
# TestLeaderboardStreaks — D-15/D-16/D-18 (SOCIAL-02)
# ---------------------------------------------------------------------------


class TestLeaderboardStreaks:
    """Verify get_leaderboard_streaks returns only guild-active users (D-15)."""

    @pytest.mark.asyncio
    async def test_leaderboard_streak_guild_scoped(self, pool):
        """A user active in guild A must appear for guild A and NOT for guild B (D-15)."""
        # Create user profile with a non-zero streak
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO user_profiles"
                " (user_id, username, total_songs_queued, longest_streak)"
                " VALUES ($1, $2, $3, $4)"
                " ON CONFLICT (user_id) DO UPDATE SET"
                "   longest_streak = EXCLUDED.longest_streak",
                "u_streak_a",
                "StreakUserA",
                5,
                7,
            )
            # Insert history in guild A only
            await conn.execute(
                "INSERT INTO song_history"
                " (guild_id, user_id, title, url, duration_seconds)"
                " VALUES ($1, $2, $3, $4, $5)",
                "GA",
                "u_streak_a",
                "Streak Song",
                "https://yt.com/st1",
                200,
            )

        # User appears in guild A
        ga_rows = await get_leaderboard_streaks(pool, "GA")
        ga_user_ids = [r["user_id"] for r in ga_rows]
        assert "u_streak_a" in ga_user_ids, "u_streak_a should appear in guild A streak board"

        # User does NOT appear in guild B (no history there)
        gb_rows = await get_leaderboard_streaks(pool, "GB")
        gb_user_ids = [r["user_id"] for r in gb_rows]
        assert "u_streak_a" not in gb_user_ids, "u_streak_a must NOT appear in guild B streak board (no history in GB)"
