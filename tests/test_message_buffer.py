"""Tests for the rolling message buffer."""

from datetime import datetime, timedelta

import config
from models.message_buffer import MessageBuffer


class TestMessageBufferAdd:
    def test_add_stores_message(self):
        buf = MessageBuffer()
        buf.add(channel_id=100, role="user", author="jake", content="hello")
        history = buf.get_history(100)
        assert len(history) == 1
        assert history[0]["role"] == "user"

    def test_add_respects_maxlen(self):
        buf = MessageBuffer(max_length=3)
        for i in range(5):
            buf.add(channel_id=100, role="user", author="jake", content=f"msg {i}")
        history = buf.get_history(100)
        assert len(history) == 3
        assert history[0]["content"] == "msg 2"
        assert history[2]["content"] == "msg 4"

    def test_separate_channels(self):
        buf = MessageBuffer()
        buf.add(channel_id=100, role="user", author="jake", content="ch100")
        buf.add(channel_id=200, role="user", author="mike", content="ch200")
        assert len(buf.get_history(100)) == 1
        assert len(buf.get_history(200)) == 1


class TestMessageBufferGetHistory:
    def test_empty_channel_returns_empty(self):
        buf = MessageBuffer()
        assert buf.get_history(999) == []

    def test_returns_chronological_order(self):
        buf = MessageBuffer()
        buf.add(channel_id=100, role="user", author="jake", content="first")
        buf.add(channel_id=100, role="model", author="dexter", content="second")
        history = buf.get_history(100)
        assert history[0]["content"] == "first"
        assert history[1]["content"] == "second"

    def test_format_for_gemini(self):
        buf = MessageBuffer()
        buf.add(channel_id=100, role="user", author="jake", content="hello")
        buf.add(channel_id=100, role="model", author="dexter", content="hi")
        history = buf.get_gemini_history(100)
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "jake: hello"
        assert history[1]["role"] == "model"
        assert history[1]["content"] == "hi"


class TestMessageBufferClear:
    def test_clear_removes_channel(self):
        buf = MessageBuffer()
        buf.add(channel_id=100, role="user", author="jake", content="hello")
        buf.clear(100)
        assert buf.get_history(100) == []

    def test_clear_doesnt_affect_other_channels(self):
        buf = MessageBuffer()
        buf.add(channel_id=100, role="user", author="jake", content="hello")
        buf.add(channel_id=200, role="user", author="mike", content="hi")
        buf.clear(100)
        assert len(buf.get_history(200)) == 1


class TestTTLEviction:
    def test_stale_channel_evicted(self):
        """Channel whose _last_seen is older than TTL is removed on next add()."""
        buf = MessageBuffer(max_length=10)
        buf.add(channel_id=100, role="user", author="jake", content="old")
        # Manually backdate last_seen past TTL
        buf._last_seen[100] = datetime.now() - timedelta(hours=config.MESSAGE_BUFFER_TTL_HOURS + 1)
        # Add to a different channel — triggers eviction
        buf.add(channel_id=200, role="user", author="mike", content="new")
        assert buf.get_history(100) == []
        assert len(buf.get_history(200)) == 1

    def test_fresh_channel_survives_eviction(self):
        """A channel added in the same add() call is NOT evicted — its history has 1 entry."""
        buf = MessageBuffer(max_length=10)
        buf.add(channel_id=100, role="user", author="jake", content="old")
        buf._last_seen[100] = datetime.now() - timedelta(hours=config.MESSAGE_BUFFER_TTL_HOURS + 1)
        buf.add(channel_id=200, role="user", author="mike", content="new")
        # Channel 200 is fresh — should survive
        assert len(buf.get_history(200)) == 1

    def test_recent_channel_not_evicted(self):
        """A channel within TTL window is NOT evicted."""
        buf = MessageBuffer(max_length=10)
        buf.add(channel_id=100, role="user", author="jake", content="recent")
        # last_seen[100] is just now — well within TTL
        buf.add(channel_id=200, role="user", author="mike", content="trigger")
        assert len(buf.get_history(100)) == 1

    def test_eviction_removes_from_last_seen(self):
        """_last_seen dict is also cleaned up on eviction (no stale metadata)."""
        buf = MessageBuffer(max_length=10)
        buf.add(channel_id=100, role="user", author="jake", content="old")
        buf._last_seen[100] = datetime.now() - timedelta(hours=config.MESSAGE_BUFFER_TTL_HOURS + 1)
        buf.add(channel_id=200, role="user", author="mike", content="trigger")
        assert 100 not in buf._last_seen
