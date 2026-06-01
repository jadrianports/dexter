"""Tests for hardening-pass database changes."""

import aiosqlite
import pytest
import pytest_asyncio

from database import init_db, get_recent_songs


@pytest_asyncio.fixture
async def file_db(tmp_path):
    """A real on-disk DB (WAL is a no-op on :memory:)."""
    conn = await aiosqlite.connect(tmp_path / "dexter_test.db")
    conn.row_factory = aiosqlite.Row
    await init_db(conn)
    yield conn
    await conn.close()


class TestWalMode:
    @pytest.mark.asyncio
    async def test_journal_mode_is_wal(self, file_db):
        cursor = await file_db.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        assert row[0].lower() == "wal"


class TestRecentSongsLimitType:
    @pytest.mark.asyncio
    async def test_limit_passed_as_int_not_str(self, file_db, monkeypatch):
        # Capture the params actually bound to the LIMIT query.
        captured = {}
        real_execute = file_db.execute

        async def spy(sql, params=()):
            if "LIMIT" in sql and "song_history" in sql:
                captured["params"] = params
            return await real_execute(sql, params)

        monkeypatch.setattr(file_db, "execute", spy)
        await get_recent_songs(file_db, guild_id="g1", limit=5)
        assert captured["params"] == ("g1", 5)  # int, not "5"
