"""Phase 4 PostgreSQL integration tests.

These tests require a live PostgreSQL database.
Set TEST_DATABASE_URL or ensure postgresql://dexter:dexter@localhost:5432/dexter_test
is reachable before running.

The pool fixture is defined in tests/conftest.py — it calls init_db, yields the
pool, and drops all 7 tables on teardown.

Autonomous gate (no live DB needed): pytest --collect-only exits 0.
Full integration run: pytest tests/test_database_phase4.py -x (requires dexter_test DB).
"""

from __future__ import annotations

import pytest

import config
from database import (
    get_history_rows,
    get_images_today,
    get_repeat_song_count,
    init_db,
    log_image,
    log_song,
    log_track_batch,
    update_user_profile,
    update_user_streak,
)

# ---------------------------------------------------------------------------
# TestPostgresSchema — schema creation (SCALE-02)
# ---------------------------------------------------------------------------


class TestPostgresSchema:
    """Verify that init_db creates all 7 Postgres tables with correct columns."""

    @pytest.mark.asyncio
    async def test_all_tables_created(self, pool):
        """init_db must create all 7 tables in the public schema."""
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
        tables = {r["tablename"] for r in rows}
        expected = {
            "song_history",
            "user_profiles",
            "user_artist_counts",
            "image_generation_log",
            "bot_daily_stats",
            "guild_queues",
        }
        assert expected.issubset(tables), f"Missing tables: {expected - tables}"

    @pytest.mark.asyncio
    async def test_song_history_table_exists(self, pool):
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = {r["tablename"] for r in rows}
        assert "song_history" in tables

    @pytest.mark.asyncio
    async def test_guild_queues_table_exists(self, pool):
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = {r["tablename"] for r in rows}
        assert "guild_queues" in tables

    @pytest.mark.asyncio
    async def test_user_profiles_has_streak_columns(self, pool):
        """user_profiles must have current_streak, longest_streak, last_streak_date
        directly in the CREATE TABLE (no migration needed — D-16)."""
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = 'public' AND table_name = 'user_profiles'"
            )
        cols = {r["column_name"] for r in rows}
        assert "current_streak" in cols, "current_streak column missing from user_profiles"
        assert "longest_streak" in cols, "longest_streak column missing from user_profiles"
        assert "last_streak_date" in cols, "last_streak_date column missing from user_profiles"

    @pytest.mark.asyncio
    async def test_user_profiles_timestamps_are_timestamptz(self, pool):
        """first_seen_at and last_active_at must use TIMESTAMPTZ (not TEXT)."""
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns"
                " WHERE table_schema = 'public' AND table_name = 'user_profiles'"
                "   AND column_name IN ('first_seen_at', 'last_active_at')"
            )
        types = {r["column_name"]: r["data_type"] for r in rows}
        for col in ("first_seen_at", "last_active_at"):
            assert col in types, f"{col} column not found in user_profiles"
            assert "timestamp" in types[col], f"{col} should be TIMESTAMPTZ, got {types[col]!r}"

    @pytest.mark.asyncio
    async def test_song_history_was_skipped_is_boolean(self, pool):
        """was_skipped must be a native boolean column (not integer)."""
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns"
                " WHERE table_schema = 'public' AND table_name = 'song_history'"
                "   AND column_name IN ('was_skipped', 'was_auto_queued')"
            )
        types = {r["column_name"]: r["data_type"] for r in rows}
        for col in ("was_skipped", "was_auto_queued"):
            assert col in types, f"{col} column not found in song_history"
            assert types[col] == "boolean", f"{col} should be boolean, got {types[col]!r}"

    @pytest.mark.asyncio
    async def test_init_db_idempotent(self, pool):
        """Calling init_db a second time on the same pool must not raise
        (CREATE TABLE IF NOT EXISTS is idempotent)."""
        await init_db(pool)  # second call — must be a no-op


# ---------------------------------------------------------------------------
# TestBatchTransaction — log_track_batch atomicity (D-06 / SCALE-01)
# ---------------------------------------------------------------------------


class TestBatchTransaction:
    """Verify log_track_batch writes all 3 rows atomically."""

    @pytest.mark.asyncio
    async def test_first_call_inserts_all_three_rows(self, pool):
        """log_track_batch must insert song_history, user_artist_counts,
        and user_profiles rows in one call."""
        await log_track_batch(
            pool,
            guild_id="g1",
            user_id="u1",
            username="Alice",
            title="Test Song",
            artist="Test Artist",
            url="https://yt.com/1",
            duration=200,
        )

        async with pool.acquire() as conn:
            sh_count = await conn.fetchval("SELECT COUNT(*) FROM song_history WHERE guild_id = $1", "g1")
            ac_count = await conn.fetchval(
                "SELECT play_count FROM user_artist_counts WHERE user_id = $1 AND artist = $2",
                "u1",
                "Test Artist",
            )
            up_count = await conn.fetchval(
                "SELECT total_songs_queued FROM user_profiles WHERE user_id = $1",
                "u1",
            )

        assert sh_count == 1, f"Expected 1 song_history row, got {sh_count}"
        assert ac_count == 1, f"Expected play_count=1, got {ac_count}"
        assert up_count == 1, f"Expected total_songs_queued=1, got {up_count}"

    @pytest.mark.asyncio
    async def test_second_call_upserts_correctly(self, pool):
        """Second call with the same user+artist must increment play_count to 2
        and total_songs_queued to 2 (upsert path)."""
        for i in range(2):
            await log_track_batch(
                pool,
                guild_id="g1",
                user_id="u2",
                username="Bob",
                title=f"Song {i}",
                artist="Same Artist",
                url=f"https://yt.com/{i}",
                duration=180,
            )

        async with pool.acquire() as conn:
            play_count = await conn.fetchval(
                "SELECT play_count FROM user_artist_counts WHERE user_id = $1 AND artist = $2",
                "u2",
                "Same Artist",
            )
            total_queued = await conn.fetchval(
                "SELECT total_songs_queued FROM user_profiles WHERE user_id = $1",
                "u2",
            )

        assert play_count == 2, f"Expected play_count=2, got {play_count}"
        assert total_queued == 2, f"Expected total_songs_queued=2, got {total_queued}"

    @pytest.mark.asyncio
    async def test_null_artist_skips_artist_count(self, pool):
        """log_track_batch with artist=None must NOT insert into user_artist_counts."""
        await log_track_batch(
            pool,
            guild_id="g1",
            user_id="u3",
            username="Carol",
            title="No Artist Song",
            artist=None,
            url="https://yt.com/noartist",
            duration=150,
        )

        async with pool.acquire() as conn:
            ac_count = await conn.fetchval(
                "SELECT COUNT(*) FROM user_artist_counts WHERE user_id = $1",
                "u3",
            )
            sh_count = await conn.fetchval("SELECT COUNT(*) FROM song_history WHERE user_id = $1", "u3")
            up_count = await conn.fetchval(
                "SELECT total_songs_queued FROM user_profiles WHERE user_id = $1",
                "u3",
            )

        assert ac_count == 0, "user_artist_counts should be empty for null artist"
        assert sh_count == 1, "song_history should have 1 row"
        assert up_count == 1, "user_profiles total_songs_queued should be 1"


# ---------------------------------------------------------------------------
# TestHelpers — smoke tests for individual helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    """Smoke tests: individual helper functions execute without error and
    return expected types/values."""

    @pytest.mark.asyncio
    async def test_log_song_inserts_row(self, pool):
        await log_song(
            pool,
            guild_id="gsmoke",
            user_id="usmoke",
            title="Smoke Song",
            artist="Smoke Artist",
            url="https://yt.com/smoke",
            duration=240,
        )
        async with pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM song_history WHERE guild_id = $1", "gsmoke")
        assert count == 1

    @pytest.mark.asyncio
    async def test_update_user_profile_creates_profile(self, pool):
        await update_user_profile(pool, user_id="uprofile", username="Dave")
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT total_songs_queued FROM user_profiles WHERE user_id = $1",
                "uprofile",
            )
        assert row is not None
        assert row["total_songs_queued"] == 1

    @pytest.mark.asyncio
    async def test_update_user_streak_first_call(self, pool):
        await update_user_profile(pool, user_id="ustreak", username="Eve")
        new_streak, new_longest, milestone = await update_user_streak(
            pool, user_id="ustreak", tz_name=config.STREAK_TIMEZONE
        )
        assert new_streak == 1
        assert new_longest >= 1

    @pytest.mark.asyncio
    async def test_get_history_rows_returns_list(self, pool):
        rows = await get_history_rows(pool, guild_id="ghist_empty")
        assert isinstance(rows, list)
        assert rows == []

    @pytest.mark.asyncio
    async def test_get_repeat_song_count_after_two_logs(self, pool):
        """get_repeat_song_count returns 2 after logging the same song twice today."""
        for i in range(2):
            await log_song(
                pool,
                guild_id="grep_guild",
                user_id="grep_user",
                title="Repeated Song",
                artist="Artist",
                url=f"https://yt.com/rep{i}",
                duration=200,
            )
        count = await get_repeat_song_count(pool, guild_id="grep_guild", user_id="grep_user", title="Repeated Song")
        assert count == 2, f"Expected 2, got {count}"

    @pytest.mark.asyncio
    async def test_get_images_today_returns_int(self, pool):
        count = await get_images_today(pool, user_id="uimg_none")
        assert isinstance(count, int)
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_images_today_counts_correctly(self, pool):
        await log_image(pool, guild_id="gimg", user_id="uimg1", prompt="a cat")
        await log_image(pool, guild_id="gimg", user_id="uimg1", prompt="a dog")
        count = await get_images_today(pool, user_id="uimg1")
        assert count == 2

    @pytest.mark.asyncio
    async def test_get_history_rows_returns_required_keys(self, pool):
        await log_song(
            pool,
            guild_id="ghist_keys",
            user_id="uhist",
            title="History Song",
            artist="H Artist",
            url="https://yt.com/hist",
            duration=300,
        )
        rows = await get_history_rows(pool, guild_id="ghist_keys")
        assert len(rows) == 1
        row = rows[0]
        for key in ("title", "artist", "user_id", "queued_at"):
            assert key in row, f"Missing key: {key}"
