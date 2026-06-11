"""Tests for the MusicQueue model."""

import pytest
import config
from models.queue import Track, LoopMode, MusicQueue, QueueFullError


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


def test_auto_lyrics_defaults_off_and_survives_clear():
    q = MusicQueue(123)
    # default OFF, no thread yet
    assert q.auto_lyrics is False
    assert q.lyrics_thread_id is None
    # it's a per-server preference, NOT playback state -> clear() must not reset it
    q.auto_lyrics = True
    q.lyrics_thread_id = 999
    q.clear()
    assert q.auto_lyrics is True
    assert q.lyrics_thread_id == 999


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


class TestQueueCap:
    def test_add_raises_when_full(self):
        q = MusicQueue(guild_id=1)
        for i in range(config.MAX_QUEUE_SIZE_PER_GUILD):
            q.add(make_track(video_id=str(i)))
        with pytest.raises(QueueFullError):
            q.add(make_track(video_id="overflow"))

    def test_add_returns_index_when_not_full(self):
        """add() still returns the inserted index (len-1) — preserve existing contract."""
        q = MusicQueue(guild_id=1)
        idx = q.add(make_track(video_id="a"))
        assert idx == 0
        idx2 = q.add(make_track(video_id="b"))
        assert idx2 == 1

    def test_add_at_exact_cap_raises(self):
        """Adding exactly one more than capacity raises QueueFullError."""
        q = MusicQueue(guild_id=1)
        for i in range(config.MAX_QUEUE_SIZE_PER_GUILD):
            q.add(make_track(video_id=str(i)))
        assert len(q.tracks) == config.MAX_QUEUE_SIZE_PER_GUILD
        with pytest.raises(QueueFullError):
            q.add(make_track(video_id="one_too_many"))


class TestTrackSerialization:
    def test_to_dict_round_trip(self):
        """Track.from_dict(t.to_dict()) == t — lossless round-trip."""
        t = make_track()
        assert Track.from_dict(t.to_dict()) == t

    def test_round_trip_with_all_fields(self):
        """Round-trip with a fully-populated track (all optional fields set)."""
        t = make_track(
            video_id="xyz",
            title="Full Track",
            artist="Some Artist",
            url="https://youtube.com/watch?v=xyz",
            duration_seconds=300,
            requested_by=99999,
            was_auto_queued=True,
            thumbnail="https://img.youtube.com/vi/xyz/0.jpg",
        )
        assert Track.from_dict(t.to_dict()) == t

    def test_from_dict_tolerates_missing_artist(self):
        """from_dict uses .get() for artist — missing key yields None."""
        d = {
            "video_id": "v1",
            "title": "No Artist",
            "url": "https://youtube.com/watch?v=v1",
            "duration_seconds": 120,
            "requested_by": 42,
        }
        t = Track.from_dict(d)
        assert t.artist is None

    def test_from_dict_tolerates_missing_thumbnail(self):
        """from_dict uses .get() for thumbnail — missing key yields None."""
        d = {
            "video_id": "v2",
            "title": "No Thumb",
            "url": "https://youtube.com/watch?v=v2",
            "duration_seconds": 180,
            "requested_by": 42,
        }
        t = Track.from_dict(d)
        assert t.thumbnail is None

    def test_from_dict_tolerates_missing_was_auto_queued(self):
        """from_dict defaults was_auto_queued to False when key is absent."""
        d = {
            "video_id": "v3",
            "title": "No AutoQ",
            "url": "https://youtube.com/watch?v=v3",
            "duration_seconds": 200,
            "requested_by": 42,
        }
        t = Track.from_dict(d)
        assert t.was_auto_queued is False
