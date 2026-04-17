"""Tests for database schema and query helpers using in-memory SQLite."""

import pytest
import pytest_asyncio
import aiosqlite

from database import init_db, log_song, update_artist_count, update_user_profile, increment_daily_stat


@pytest_asyncio.fixture
async def db():
    """Create an in-memory database with schema for each test."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db(conn)
    yield conn
    await conn.close()


class TestSchema:
    @pytest.mark.asyncio
    async def test_tables_created(self, db):
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]
        assert "bot_daily_stats" in tables
        assert "song_history" in tables
        assert "user_artist_counts" in tables
        assert "user_profiles" in tables

    @pytest.mark.asyncio
    async def test_init_db_idempotent(self, db):
        """Calling init_db twice should not fail."""
        await init_db(db)


class TestLogSong:
    @pytest.mark.asyncio
    async def test_log_song_inserts_row(self, db):
        await log_song(db, guild_id="g1", user_id="u1", title="Test Song",
                       artist="Test Artist", url="https://yt.com/1", duration=200)
        cursor = await db.execute("SELECT * FROM song_history")
        rows = await cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["title"] == "Test Song"
        assert rows[0]["artist"] == "Test Artist"
        assert rows[0]["guild_id"] == "g1"

    @pytest.mark.asyncio
    async def test_log_song_null_artist(self, db):
        await log_song(db, guild_id="g1", user_id="u1", title="No Artist",
                       artist=None, url="https://yt.com/2", duration=100)
        cursor = await db.execute("SELECT artist FROM song_history")
        row = await cursor.fetchone()
        assert row["artist"] is None


class TestUpdateArtistCount:
    @pytest.mark.asyncio
    async def test_first_play_creates_row(self, db):
        await update_artist_count(db, user_id="u1", artist="Radiohead")
        cursor = await db.execute("SELECT * FROM user_artist_counts WHERE user_id='u1'")
        row = await cursor.fetchone()
        assert row["play_count"] == 1

    @pytest.mark.asyncio
    async def test_second_play_increments(self, db):
        await update_artist_count(db, user_id="u1", artist="Radiohead")
        await update_artist_count(db, user_id="u1", artist="Radiohead")
        cursor = await db.execute(
            "SELECT play_count FROM user_artist_counts WHERE user_id='u1' AND artist='Radiohead'"
        )
        row = await cursor.fetchone()
        assert row["play_count"] == 2

    @pytest.mark.asyncio
    async def test_skip_null_artist(self, db):
        await update_artist_count(db, user_id="u1", artist=None)
        cursor = await db.execute("SELECT count(*) as cnt FROM user_artist_counts")
        row = await cursor.fetchone()
        assert row["cnt"] == 0


class TestUpdateUserProfile:
    @pytest.mark.asyncio
    async def test_first_time_creates_profile(self, db):
        await update_user_profile(db, user_id="u1", username="jake")
        cursor = await db.execute("SELECT * FROM user_profiles WHERE user_id='u1'")
        row = await cursor.fetchone()
        assert row["username"] == "jake"
        assert row["total_songs_queued"] == 1

    @pytest.mark.asyncio
    async def test_repeat_increments_songs(self, db):
        await update_user_profile(db, user_id="u1", username="jake")
        await update_user_profile(db, user_id="u1", username="jake")
        cursor = await db.execute("SELECT total_songs_queued FROM user_profiles WHERE user_id='u1'")
        row = await cursor.fetchone()
        assert row["total_songs_queued"] == 2


class TestIncrementDailyStat:
    @pytest.mark.asyncio
    async def test_increment_creates_row(self, db):
        await increment_daily_stat(db, "total_commands")
        cursor = await db.execute("SELECT * FROM bot_daily_stats")
        row = await cursor.fetchone()
        assert row["total_commands"] == 1

    @pytest.mark.asyncio
    async def test_increment_twice(self, db):
        await increment_daily_stat(db, "total_commands")
        await increment_daily_stat(db, "total_commands")
        cursor = await db.execute("SELECT total_commands FROM bot_daily_stats")
        row = await cursor.fetchone()
        assert row["total_commands"] == 2

    @pytest.mark.asyncio
    async def test_increment_songs_played(self, db):
        await increment_daily_stat(db, "total_songs_played")
        cursor = await db.execute("SELECT total_songs_played FROM bot_daily_stats")
        row = await cursor.fetchone()
        assert row["total_songs_played"] == 1
