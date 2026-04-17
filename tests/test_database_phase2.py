"""Tests for Phase 2 database query helpers."""

import pytest
import pytest_asyncio
import aiosqlite

from database import (
    init_db,
    log_song,
    mark_song_skipped,
    get_recent_songs,
    get_images_today,
    get_daily_command_count,
    log_image,
    increment_daily_stat,
)


@pytest_asyncio.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db(conn)
    yield conn
    await conn.close()


class TestMarkSongSkipped:
    @pytest.mark.asyncio
    async def test_marks_most_recent_entry(self, db):
        await log_song(db, guild_id="g1", user_id="u1", title="Song A",
                       artist="Artist", url="https://yt.com/a", duration=200)
        await log_song(db, guild_id="g1", user_id="u1", title="Song B",
                       artist="Artist", url="https://yt.com/b", duration=200)
        await mark_song_skipped(db, guild_id="g1", url="https://yt.com/b")
        cursor = await db.execute(
            "SELECT was_skipped FROM song_history WHERE url='https://yt.com/b' "
            "ORDER BY queued_at DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        assert row["was_skipped"] == 1

    @pytest.mark.asyncio
    async def test_does_not_affect_other_songs(self, db):
        await log_song(db, guild_id="g1", user_id="u1", title="Song A",
                       artist="Artist", url="https://yt.com/a", duration=200)
        await log_song(db, guild_id="g1", user_id="u1", title="Song B",
                       artist="Artist", url="https://yt.com/b", duration=200)
        await mark_song_skipped(db, guild_id="g1", url="https://yt.com/b")
        cursor = await db.execute(
            "SELECT was_skipped FROM song_history WHERE url='https://yt.com/a'"
        )
        row = await cursor.fetchone()
        assert row["was_skipped"] == 0


class TestGetRecentSongs:
    @pytest.mark.asyncio
    async def test_returns_songs_newest_first(self, db):
        await log_song(db, guild_id="g1", user_id="u1", title="Old",
                       artist="A", url="https://yt.com/1", duration=100)
        await log_song(db, guild_id="g1", user_id="u1", title="New",
                       artist="B", url="https://yt.com/2", duration=100)
        songs = await get_recent_songs(db, guild_id="g1", limit=10)
        assert len(songs) == 2
        assert songs[0]["title"] == "New"

    @pytest.mark.asyncio
    async def test_respects_limit(self, db):
        for i in range(5):
            await log_song(db, guild_id="g1", user_id="u1", title=f"Song {i}",
                           artist="A", url=f"https://yt.com/{i}", duration=100)
        songs = await get_recent_songs(db, guild_id="g1", limit=3)
        assert len(songs) == 3

    @pytest.mark.asyncio
    async def test_filters_by_guild(self, db):
        await log_song(db, guild_id="g1", user_id="u1", title="G1 Song",
                       artist="A", url="https://yt.com/1", duration=100)
        await log_song(db, guild_id="g2", user_id="u1", title="G2 Song",
                       artist="A", url="https://yt.com/2", duration=100)
        songs = await get_recent_songs(db, guild_id="g1", limit=10)
        assert len(songs) == 1
        assert songs[0]["title"] == "G1 Song"

    @pytest.mark.asyncio
    async def test_empty_guild_returns_empty(self, db):
        songs = await get_recent_songs(db, guild_id="g1", limit=10)
        assert songs == []


class TestGetImagesToday:
    @pytest.mark.asyncio
    async def test_counts_todays_images(self, db):
        await log_image(db, guild_id="g1", user_id="u1", prompt="cats")
        await log_image(db, guild_id="g1", user_id="u1", prompt="dogs")
        count = await get_images_today(db, user_id="u1")
        assert count == 2

    @pytest.mark.asyncio
    async def test_zero_when_no_images(self, db):
        count = await get_images_today(db, user_id="u1")
        assert count == 0

    @pytest.mark.asyncio
    async def test_filters_by_user(self, db):
        await log_image(db, guild_id="g1", user_id="u1", prompt="cats")
        await log_image(db, guild_id="g1", user_id="u2", prompt="dogs")
        count = await get_images_today(db, user_id="u1")
        assert count == 1


class TestGetDailyCommandCount:
    @pytest.mark.asyncio
    async def test_returns_count(self, db):
        await increment_daily_stat(db, "total_commands")
        await increment_daily_stat(db, "total_commands")
        count = await get_daily_command_count(db)
        assert count == 2

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_stats(self, db):
        count = await get_daily_command_count(db)
        assert count == 0
