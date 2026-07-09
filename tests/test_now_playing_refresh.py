"""Regression tests for now-playing controller refresh on track change (Phase 7 UAT issue).

Bug: after a new song starts (skip), the now-playing embed + buttons stayed frozen
on the previous song. Root cause: the refresh logic lived only inside
`_on_track_end` and was never called from the skip path, and it rebuilt the view
with hardcoded default labels instead of deriving them from queue state.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from cogs.music import MusicCog, NowPlayingView
from models.queue import LoopMode, MusicQueue, Track


def make_track(video_id: str = "abc123", title: str = "Test Song", **kwargs) -> Track:
    defaults = {
        "video_id": video_id,
        "title": title,
        "artist": "Test Artist",
        "url": f"https://youtube.com/watch?v={video_id}",
        "duration_seconds": 200,
        "requested_by": 12345,
        "was_auto_queued": False,
    }
    defaults.update(kwargs)
    return Track(**defaults)


class TestApplyState:
    def test_labels_default_when_off_and_playing(self):
        view = NowPlayingView(bot=Mock())
        q = MusicQueue(1)  # loop OFF, not paused
        view.apply_state(q)
        labels = {c.custom_id: c.label for c in view.children if hasattr(c, "label")}
        assert labels["dex:np:playpause"] == "⏸ Pause"
        assert labels["dex:np:loop"] == "🔁 Loop: Off"

    def test_labels_reflect_paused_and_loop_queue(self):
        view = NowPlayingView(bot=Mock())
        q = MusicQueue(1)
        q.is_paused = True
        q.loop_mode = LoopMode.QUEUE
        view.apply_state(q)
        labels = {c.custom_id: c.label for c in view.children if hasattr(c, "label")}
        assert labels["dex:np:playpause"] == "▶ Resume"
        assert labels["dex:np:loop"] == "🔁 Loop: Queue"

    def test_labels_reflect_loop_single(self):
        view = NowPlayingView(bot=Mock())
        q = MusicQueue(1)
        q.loop_mode = LoopMode.SINGLE
        view.apply_state(q)
        labels = {c.custom_id: c.label for c in view.children if hasattr(c, "label")}
        assert labels["dex:np:loop"] == "🔂 Loop: Single"


class TestRefreshNowPlaying:
    @pytest.mark.asyncio
    async def test_reposts_at_bottom_deleting_previous_message(self):
        """On track change the old now-playing message is deleted and a fresh one
        is sent at the bottom (so the live player + controls follow the chat)."""
        cog = MusicCog.__new__(MusicCog)
        cog.bot = Mock()
        q = MusicQueue(1)
        q.add(make_track(video_id="a", title="Song A"))
        q.add(make_track(video_id="b", title="Song B"))
        q.advance()  # current = B
        q._now_playing_message_id = 555

        old_msg = Mock()
        old_msg.delete = AsyncMock()
        channel = Mock()
        channel.fetch_message = AsyncMock(return_value=old_msg)
        new_msg = Mock(id=888)
        channel.send = AsyncMock(return_value=new_msg)
        cog._get_text_channel = Mock(return_value=channel)

        await cog._refresh_now_playing(Mock(), q)

        # Old message fetched and deleted
        channel.fetch_message.assert_awaited_once_with(555)
        old_msg.delete.assert_awaited_once()
        # Fresh message sent at the bottom, with a state-synced view
        channel.send.assert_awaited_once()
        kwargs = channel.send.await_args.kwargs
        assert isinstance(kwargs["view"], NowPlayingView)
        assert q._now_playing_message_id == 888

    @pytest.mark.asyncio
    async def test_posts_new_message_when_tracked_message_gone(self):
        import discord

        cog = MusicCog.__new__(MusicCog)
        cog.bot = Mock()
        q = MusicQueue(1)
        q.add(make_track(video_id="a", title="Song A"))
        q._now_playing_message_id = 999

        channel = Mock()
        channel.fetch_message = AsyncMock(side_effect=discord.NotFound(Mock(status=404), "gone"))
        new_msg = Mock(id=777)
        channel.send = AsyncMock(return_value=new_msg)
        cog._get_text_channel = Mock(return_value=channel)

        await cog._refresh_now_playing(Mock(), q)

        channel.send.assert_awaited_once()
        assert q._now_playing_message_id == 777


class TestSkipRefreshes:
    @pytest.mark.asyncio
    async def test_do_skip_refreshes_now_playing(self):
        """The reported bug: skipping must refresh the now-playing controller."""
        cog = MusicCog.__new__(MusicCog)
        cog.bot = Mock()
        cog._persist_queue = AsyncMock()
        cog._play_track = AsyncMock()
        cog._refresh_now_playing = AsyncMock()

        q = MusicQueue(1)
        q.add(make_track(video_id="a"))
        q.add(make_track(video_id="b"))
        q.is_playing = True

        guild = Mock()
        guild.id = 1
        vc = Mock()

        await cog._do_skip(guild, q, vc)

        cog._refresh_now_playing.assert_awaited_once()
