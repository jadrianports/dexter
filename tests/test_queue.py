"""Tests for the MusicQueue model."""

import pytest
from models.queue import Track, LoopMode, MusicQueue


def make_track(video_id: str = "abc123", title: str = "Test Song", **kwargs) -> Track:
    """Helper to create a Track with defaults."""
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


class TestMusicQueueAdd:
    def test_add_track(self):
        q = MusicQueue(guild_id=1)
        track = make_track()
        q.add(track)
        assert len(q.tracks) == 1
        assert q.tracks[0] is track

    def test_add_multiple(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track(video_id="a"))
        q.add(make_track(video_id="b"))
        assert len(q.tracks) == 2


class TestMusicQueueSkip:
    def test_skip_advances_index(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track(video_id="a"))
        q.add(make_track(video_id="b"))
        q.current_index = 0
        result = q.skip()
        assert q.current_index == 1
        assert result is not None

    def test_skip_at_end_returns_none_loop_off(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track())
        q.current_index = 0
        result = q.skip()
        assert result is None

    def test_skip_at_end_wraps_loop_queue(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track(video_id="a"))
        q.add(make_track(video_id="b"))
        q.current_index = 1
        q.loop_mode = LoopMode.QUEUE
        result = q.skip()
        assert q.current_index == 0
        assert result is not None

    def test_skip_ignores_single_loop(self):
        """Skip always advances, even in SINGLE loop mode."""
        q = MusicQueue(guild_id=1)
        q.add(make_track(video_id="a"))
        q.add(make_track(video_id="b"))
        q.current_index = 0
        q.loop_mode = LoopMode.SINGLE
        result = q.skip()
        assert q.current_index == 1


class TestMusicQueueAdvance:
    def test_advance_repeats_on_single_loop(self):
        """Natural end (advance) repeats the track on SINGLE loop."""
        q = MusicQueue(guild_id=1)
        q.add(make_track(video_id="a"))
        q.add(make_track(video_id="b"))
        q.current_index = 0
        q.loop_mode = LoopMode.SINGLE
        result = q.advance()
        assert q.current_index == 0
        assert result is not None

    def test_advance_moves_on_loop_off(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track(video_id="a"))
        q.add(make_track(video_id="b"))
        q.current_index = 0
        result = q.advance()
        assert q.current_index == 1

    def test_advance_wraps_on_loop_queue(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track(video_id="a"))
        q.add(make_track(video_id="b"))
        q.current_index = 1
        q.loop_mode = LoopMode.QUEUE
        result = q.advance()
        assert q.current_index == 0


class TestMusicQueuePrevious:
    def test_previous_decrements(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track(video_id="a"))
        q.add(make_track(video_id="b"))
        q.current_index = 1
        result = q.previous()
        assert q.current_index == 0
        assert result is not None

    def test_previous_at_start_returns_none(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track())
        q.current_index = 0
        result = q.previous()
        assert result is None
        assert q.current_index == 0


class TestMusicQueueShuffle:
    def test_shuffle_only_upcoming(self):
        q = MusicQueue(guild_id=1)
        for i in range(10):
            q.add(make_track(video_id=str(i), title=f"Song {i}"))
        q.current_index = 3

        before_current = [t.video_id for t in q.tracks[: q.current_index + 1]]
        q.shuffle()
        after_current = [t.video_id for t in q.tracks[: q.current_index + 1]]

        # Tracks at and before current_index should be unchanged
        assert before_current == after_current

    def test_shuffle_empty_upcoming_noop(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track())
        q.current_index = 0
        q.shuffle()  # should not raise
        assert len(q.tracks) == 1


class TestMusicQueueClear:
    def test_clear_resets_everything(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track())
        q.current_index = 0
        q.is_playing = True
        q.loop_mode = LoopMode.QUEUE
        q.clear()
        assert q.tracks == []
        assert q.current_index == 0
        assert q.is_playing is False
        assert q.is_paused is False
        assert q.loop_mode == LoopMode.OFF


class TestMusicQueueGetCurrent:
    def test_get_current_returns_track(self):
        q = MusicQueue(guild_id=1)
        t = make_track()
        q.add(t)
        q.current_index = 0
        assert q.get_current() is t

    def test_get_current_empty_returns_none(self):
        q = MusicQueue(guild_id=1)
        assert q.get_current() is None

    def test_get_current_index_out_of_range(self):
        q = MusicQueue(guild_id=1)
        q.add(make_track())
        q.current_index = 5
        assert q.get_current() is None
