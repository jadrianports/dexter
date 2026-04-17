"""Tests for server state and mood system."""

import pytest
import pytest_asyncio
import aiosqlite

from database import init_db, increment_daily_stat
from models.server_state import ServerState, get_mood, get_server_state


class TestServerState:
    def test_initial_state(self):
        state = ServerState(guild_id=1)
        assert state.auto_queue_rounds == 0
        assert state.auto_queue_results == {"played": 0, "skipped": 0}

    def test_reset_auto_queue(self):
        state = ServerState(guild_id=1)
        state.auto_queue_rounds = 3
        state.auto_queue_results = {"played": 2, "skipped": 1}
        state.reset_auto_queue()
        assert state.auto_queue_rounds == 0
        assert state.auto_queue_results == {"played": 0, "skipped": 0}


class TestGetServerState:
    def test_creates_on_first_access(self):
        states: dict[int, ServerState] = {}
        state = get_server_state(states, guild_id=1)
        assert isinstance(state, ServerState)
        assert state.guild_id == 1

    def test_returns_existing(self):
        states: dict[int, ServerState] = {}
        first = get_server_state(states, guild_id=1)
        first.auto_queue_rounds = 2
        second = get_server_state(states, guild_id=1)
        assert second.auto_queue_rounds == 2


class TestGetMood:
    @pytest_asyncio.fixture
    async def db(self):
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        await init_db(conn)
        yield conn
        await conn.close()

    @pytest.mark.asyncio
    async def test_normal_mood(self, db):
        for _ in range(5):
            await increment_daily_stat(db, "total_commands")
        mood = await get_mood(db)
        assert mood == "normal"

    @pytest.mark.asyncio
    async def test_tired_mood(self, db):
        for _ in range(20):
            await increment_daily_stat(db, "total_commands")
        mood = await get_mood(db)
        assert mood == "tired"

    @pytest.mark.asyncio
    async def test_exhausted_mood(self, db):
        for _ in range(40):
            await increment_daily_stat(db, "total_commands")
        mood = await get_mood(db)
        assert mood == "exhausted"

    @pytest.mark.asyncio
    async def test_fumes_mood(self, db):
        for _ in range(55):
            await increment_daily_stat(db, "total_commands")
        mood = await get_mood(db)
        assert mood == "fumes"

    @pytest.mark.asyncio
    async def test_no_stats_returns_normal(self, db):
        mood = await get_mood(db)
        assert mood == "normal"
