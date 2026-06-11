"""Tests for server state."""

from models.server_state import ServerState, get_server_state


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
