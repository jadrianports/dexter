"""Tests for user taste summary generation."""

import pytest
import pytest_asyncio
import aiosqlite

from database import init_db, log_song, update_artist_count, update_user_profile
from models.user_profile import get_user_summary


@pytest_asyncio.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db(conn)
    yield conn
    await conn.close()


class TestGetUserSummary:
    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_user(self, db):
        result = await get_user_summary(db, user_id="unknown")
        assert result is None

    @pytest.mark.asyncio
    async def test_includes_total_songs(self, db):
        await update_user_profile(db, user_id="u1", username="jake")
        await update_user_profile(db, user_id="u1", username="jake")
        result = await get_user_summary(db, user_id="u1")
        assert result is not None
        assert "2" in result

    @pytest.mark.asyncio
    async def test_includes_top_artists(self, db):
        await update_user_profile(db, user_id="u1", username="jake")
        await update_artist_count(db, user_id="u1", artist="The Weeknd")
        await update_artist_count(db, user_id="u1", artist="The Weeknd")
        await update_artist_count(db, user_id="u1", artist="Drake")
        result = await get_user_summary(db, user_id="u1")
        assert "The Weeknd" in result

    @pytest.mark.asyncio
    async def test_includes_username(self, db):
        await update_user_profile(db, user_id="u1", username="jake")
        result = await get_user_summary(db, user_id="u1")
        assert "jake" in result

    @pytest.mark.asyncio
    async def test_includes_most_played_song(self, db):
        await update_user_profile(db, user_id="u1", username="jake")
        for _ in range(3):
            await log_song(db, guild_id="g1", user_id="u1", title="Blinding Lights",
                           artist="The Weeknd", url="https://yt.com/1", duration=200)
        await log_song(db, guild_id="g1", user_id="u1", title="Other Song",
                       artist="Other", url="https://yt.com/2", duration=200)
        result = await get_user_summary(db, user_id="u1")
        assert "Blinding Lights" in result
