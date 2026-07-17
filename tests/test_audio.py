"""Tests for AudioService cache logic and FFmpeg options builder."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.audio import AudioService, CrossfadeSource, TruncatingSource, _build_ffmpeg_opts


@pytest.fixture
def tmp_cache(tmp_path):
    """Create a temporary cache directory."""
    return tmp_path


@pytest.fixture
def audio_service(tmp_cache):
    yt_service = MagicMock()
    service = AudioService(youtube_service=yt_service, cache_dir=tmp_cache)
    return service


class TestBuildFfmpegOpts:
    """Pure unit tests for the _build_ffmpeg_opts helper — no FFmpeg invocation."""

    def test_no_seek_no_filter_passthrough(self):
        """Default case: before_options has no -ss, options is -vn (passthrough)."""
        opts = _build_ffmpeg_opts(0, None)
        assert "-ss" not in opts["before_options"]
        assert opts["options"] == "-vn"

    def test_seek_only(self):
        """With seek but no filter: before_options contains -ss, options still -vn."""
        opts = _build_ffmpeg_opts(45, None)
        assert "-ss 45" in opts["before_options"]
        assert opts["options"] == "-vn"

    def test_filter_only(self):
        """With filter but no seek: options contains -af chain and -vn."""
        opts = _build_ffmpeg_opts(0, "bass=g=8")
        assert "-ss" not in opts["before_options"]
        assert '-af "bass=g=8"' in opts["options"]
        assert "-vn" in opts["options"]

    def test_seek_and_filter(self):
        """Both seek and filter: -ss in before_options and -af in options."""
        opts = _build_ffmpeg_opts(45, "bass=g=8")
        assert "-ss 45" in opts["before_options"]
        assert '-af "bass=g=8"' in opts["options"]
        assert "-vn" in opts["options"]

    def test_reconnect_flags_preserved(self):
        """Reconnect flags are included in before_options regardless of seek."""
        opts_no_seek = _build_ffmpeg_opts(0, None)
        opts_seek = _build_ffmpeg_opts(10, None)
        assert "-reconnect" in opts_no_seek["before_options"]
        assert "-reconnect" in opts_seek["before_options"]


class TestCacheLookup:
    def test_cache_path(self, audio_service, tmp_cache):
        path = audio_service.cache_path("abc123")
        assert path == tmp_cache / "abc123.opus"

    def test_is_cached_true(self, audio_service, tmp_cache):
        (tmp_cache / "abc123.opus").write_bytes(b"fake audio")
        assert audio_service.is_cached("abc123") is True

    def test_is_cached_false(self, audio_service):
        assert audio_service.is_cached("nonexistent") is False


def _make_pool_mock(url_to_plays: dict[str, int]) -> MagicMock:
    """Build a mock pool whose acquire() works as an async context manager.

    url_to_plays: mapping of YouTube URL → play count.
    """
    rows = [{"url": url, "plays": plays} for url, plays in url_to_plays.items()]

    # conn_mock: the object returned inside `async with pool.acquire() as conn:`
    conn_mock = MagicMock()
    conn_mock.fetch = AsyncMock(return_value=rows)

    # The async context manager returned by pool.acquire()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn_mock)
    cm.__aexit__ = AsyncMock(return_value=False)

    pool_mock = MagicMock()
    pool_mock.acquire = MagicMock(return_value=cm)
    return pool_mock


class TestLFUEviction:
    """Tests for the LFU cleanup_cache implementation (PERF-05 / D-12/D-13)."""

    @pytest.mark.asyncio
    async def test_evicts_lowest_play_count(self, audio_service, tmp_cache):
        """cleanup_cache removes the file with the lowest play_count first."""
        # Create 3 files totalling 1.5MB; cap is 1MB — need to evict at least 512KB
        file_low = tmp_cache / "vidLOW.opus"
        file_mid = tmp_cache / "vidMID.opus"
        file_high = tmp_cache / "vidHIGH.opus"
        file_low.write_bytes(b"x" * (512 * 1024))  # 512KB, play_count=1
        file_mid.write_bytes(b"x" * (512 * 1024))  # 512KB, play_count=3
        file_high.write_bytes(b"x" * (512 * 1024))  # 512KB, play_count=5

        pool = _make_pool_mock(
            {
                "https://youtube.com/watch?v=vidLOW": 1,
                "https://youtube.com/watch?v=vidMID": 3,
                "https://youtube.com/watch?v=vidHIGH": 5,
            }
        )

        audio_service.max_cache_mb = 1  # 1MB cap
        await audio_service.cleanup_cache(pool, protected_video_ids=set())

        remaining = list(tmp_cache.glob("*.opus"))
        total_size = sum(f.stat().st_size for f in remaining)
        assert total_size <= 1 * 1024 * 1024
        # The lowest-play-count file should have been evicted first
        assert not file_low.exists(), "vidLOW (play_count=1) should have been evicted first"

    @pytest.mark.asyncio
    async def test_protected_not_evicted(self, audio_service, tmp_cache):
        """A video_id in protected_video_ids is never unlinked, even if it has the lowest play count."""
        file_low = tmp_cache / "vidPROTECTED.opus"
        file_other = tmp_cache / "vidOTHER.opus"
        file_low.write_bytes(b"x" * (512 * 1024))  # 512KB, play_count=0 (not even in history)
        file_other.write_bytes(b"x" * (700 * 1024))  # 700KB, play_count=5

        pool = _make_pool_mock(
            {
                "https://youtube.com/watch?v=vidOTHER": 5,
            }
        )

        audio_service.max_cache_mb = 1  # 1MB cap; total is 1.2MB → need to evict
        await audio_service.cleanup_cache(pool, protected_video_ids={"vidPROTECTED"})

        # Protected file must survive
        assert file_low.exists(), "Protected file must NOT be evicted"
        # The other file should have been evicted to get under cap
        assert not file_other.exists(), "vidOTHER (unprotected) should have been evicted"

    @pytest.mark.asyncio
    async def test_tiebreak_oldest(self, audio_service, tmp_cache):
        """When two files share equal play_count, the one with the older mtime is evicted first."""
        file_old = tmp_cache / "vidOLD.opus"
        file_new = tmp_cache / "vidNEW.opus"
        file_old.write_bytes(b"x" * (512 * 1024))
        file_new.write_bytes(b"x" * (512 * 1024))

        # Set mtime: old file earlier than new file
        os.utime(file_old, (1000000, 1000000))  # epoch + ~11.5 days
        os.utime(file_new, (9999999, 9999999))  # much newer

        pool = _make_pool_mock(
            {
                # Both files have the same play_count via matching URLs
                "https://youtube.com/watch?v=vidOLD": 2,
                "https://youtube.com/watch?v=vidNEW": 2,
            }
        )

        audio_service.max_cache_mb = 0  # force at-least-one eviction (total 1MB > 0)
        await audio_service.cleanup_cache(pool, protected_video_ids=set())

        # Only vidOLD should be gone (oldest mtime wins tie-break)
        assert not file_old.exists(), "vidOLD (oldest mtime, same play_count) should be evicted first"

    @pytest.mark.asyncio
    async def test_under_cap_no_eviction(self, audio_service, tmp_cache):
        """When total size is under cap, no files are deleted and pool is not queried."""
        small = tmp_cache / "vidSMALL.opus"
        small.write_bytes(b"x" * 1024)  # 1KB

        pool = _make_pool_mock({})  # No rows needed

        audio_service.max_cache_mb = 2048  # Large cap
        await audio_service.cleanup_cache(pool, protected_video_ids=set())

        assert small.exists(), "File under cap must not be deleted"
        # pool.acquire should not have been called (early return)
        pool.acquire.assert_not_called()


class TestDownloadTimeout:
    """Tests for asyncio.wait_for timeout in get_source tier-2 (PERF-04 / D-10/D-11)."""

    @pytest.mark.asyncio
    async def test_timeout_falls_back_to_stream(self, audio_service, tmp_cache):
        """When async_download times out, get_source falls back to stream tier."""
        import discord

        from models.queue import Track

        # Build a track with no cached file
        track = Track(
            video_id="timeout_vid",
            title="Slow Song",
            url="https://youtube.com/watch?v=timeout_vid",
            duration_seconds=120,
            requested_by=12345,
            thumbnail=None,
            artist=None,
        )

        # Ensure cache file does NOT exist (forces tier-2 attempt)
        cached = tmp_cache / "timeout_vid.opus"
        assert not cached.exists()

        # Mock async_extract to return a stream URL (tier-3 path)
        stream_url = "https://example.com/stream.mp3"
        audio_service.youtube_service.async_extract = AsyncMock(return_value={"url": stream_url})

        # Patch asyncio.wait_for in services.audio namespace to raise TimeoutError
        with patch("services.audio.asyncio.wait_for", side_effect=asyncio.TimeoutError):
            with patch("services.audio.discord.FFmpegPCMAudio") as mock_ffmpeg:
                mock_ffmpeg.return_value = MagicMock()
                await audio_service.get_source(track, seek_seconds=0, ffmpeg_filter=None)

        # The stream tier was reached: FFmpegPCMAudio was instantiated with the stream URL
        mock_ffmpeg.assert_called_once()
        call_args = mock_ffmpeg.call_args
        assert call_args[0][0] == stream_url, f"Expected stream URL {stream_url!r}, got {call_args[0][0]!r}"

    @pytest.mark.asyncio
    async def test_timeout_warning_logged(self, audio_service, tmp_cache, caplog):
        """A warning is logged when the download timeout fires."""
        import logging

        from models.queue import Track

        track = Track(
            video_id="timeout_vid2",
            title="Another Slow Song",
            url="https://youtube.com/watch?v=timeout_vid2",
            duration_seconds=200,
            requested_by=12345,
            thumbnail=None,
            artist=None,
        )

        audio_service.youtube_service.async_extract = AsyncMock(return_value={"url": "https://example.com/stream2.mp3"})

        with patch("services.audio.asyncio.wait_for", side_effect=asyncio.TimeoutError):
            with patch("services.audio.discord.FFmpegPCMAudio"):
                with caplog.at_level(logging.WARNING, logger="dexter"):
                    await audio_service.get_source(track, seek_seconds=0, ffmpeg_filter=None)

        # At least one warning mentioning the timeout should have been emitted
        warning_msgs = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("timeout" in m.lower() or "falling back" in m.lower() for m in warning_msgs), (
            f"Expected a timeout warning, got: {warning_msgs}"
        )


class _FakeAudioSource:
    """Minimal discord.AudioSource-shaped stub for TruncatingSource/CrossfadeSource tests.

    Not a discord.AudioSource subclass — TruncatingSource/CrossfadeSource only
    call read()/is_opus()/cleanup() on their children, so duck typing is
    sufficient and keeps these tests free of any FFmpeg subprocess.
    """

    def __init__(self, frames=None, opus: bool = False, raise_on_cleanup: bool = False):
        self._frames = list(frames) if frames is not None else []
        self._opus = opus
        self._raise_on_cleanup = raise_on_cleanup
        self.cleanup_calls = 0

    def read(self) -> bytes:
        if self._frames:
            return self._frames.pop(0)
        return b""

    def is_opus(self) -> bool:
        return self._opus

    def cleanup(self) -> None:
        self.cleanup_calls += 1
        if self._raise_on_cleanup:
            raise RuntimeError("boom: tail cleanup failed")


def test_truncating_source():
    """VALIDATION row 12 (exact node id, MANDATED name — do not rename):
    exhausts at max_frames, delegates is_opus() to the inner source, cleans
    the inner source exactly once, position_seconds tracks frames_read, and
    cut_short distinguishes a fade cut from a natural early EOF.
    """
    frame = b"x" * 3840

    # Exhausts at max_frames: 10 frames available, max_frames=5 -> exactly 5
    # non-empty reads, then b"" forever.
    inner = _FakeAudioSource([frame] * 10)
    ts = TruncatingSource(inner, max_frames=5)
    reads = [ts.read() for _ in range(7)]
    assert reads[:5] == [frame] * 5
    assert reads[5] == b""
    assert reads[6] == b""
    assert ts.frames_read == 5
    assert ts.cut_short is True

    # is_opus() delegates to the inner source — assert both True and False.
    assert TruncatingSource(_FakeAudioSource(opus=True), 5).is_opus() is True
    assert TruncatingSource(_FakeAudioSource(opus=False), 5).is_opus() is False

    # cleanup() calls the inner's cleanup() exactly once.
    inner2 = _FakeAudioSource()
    ts2 = TruncatingSource(inner2, max_frames=5)
    ts2.cleanup()
    assert inner2.cleanup_calls == 1

    # position_seconds == frames_read * 0.02
    inner3 = _FakeAudioSource([frame] * 10)
    ts3 = TruncatingSource(inner3, max_frames=10)
    for _ in range(3):
        ts3.read()
    assert ts3.position_seconds == pytest.approx(0.06)

    # cut_short is False after a natural inner EOF (inner exhausts before max_frames).
    inner4 = _FakeAudioSource([frame] * 3)
    ts4 = TruncatingSource(inner4, max_frames=10)
    for _ in range(3):
        ts4.read()
    assert ts4.read() == b""
    assert ts4.cut_short is False


def test_suppress_flag_only_on_fade_cut():
    """VALIDATION row 16 (exact node id, MANDATED name — do not rename). This
    is the non-negotiable D-17.3 guard rail: _suppress_end_silence is False
    at construction, False after a natural inner EOF, and True ONLY at the
    instant the truncator itself cuts short for a fade.
    """
    frame = b"x" * 3840

    # False at construction.
    inner = _FakeAudioSource([frame] * 10)
    ts = TruncatingSource(inner, max_frames=5)
    assert ts._suppress_end_silence is False

    # False after a natural inner EOF — a real end of transmission wants the
    # silence marker, so the flag must stay unset.
    inner_natural = _FakeAudioSource([frame] * 3)
    ts_natural = TruncatingSource(inner_natural, max_frames=10)
    for _ in range(3):
        ts_natural.read()
    assert ts_natural._suppress_end_silence is False
    assert ts_natural.read() == b""
    assert ts_natural._suppress_end_silence is False

    # True only after a fade cut (frames_read reaching max_frames).
    inner_fade = _FakeAudioSource([frame] * 10)
    ts_fade = TruncatingSource(inner_fade, max_frames=5)
    for _ in range(5):
        assert ts_fade._suppress_end_silence is False
        ts_fade.read()
    # All 5 real frames consumed; the flag is still unset until the cut itself.
    assert ts_fade._suppress_end_silence is False
    assert ts_fade.read() == b""  # the 6th read is the fade cut
    assert ts_fade._suppress_end_silence is True


class TestCrossfadeSourceMixing:
    """Additional CrossfadeSource coverage beyond the two VALIDATION-mandated tests."""

    def test_is_opus_false(self):
        cs = CrossfadeSource(tail=_FakeAudioSource(), head=_FakeAudioSource(), fade_frames=4)
        assert cs.is_opus() is False

    def test_mixes_for_exactly_fade_frames_then_head_alone(self):
        """With fade_frames=N, frames 0..N-1 differ from the head-alone bytes;
        frame N onward equals the head's bytes exactly."""
        head_frames = [bytes([i]) * 3840 for i in range(1, 7)]
        tail_frames = [bytes([200 + i]) * 3840 for i in range(4)]
        tail = _FakeAudioSource(list(tail_frames))
        head = _FakeAudioSource(list(head_frames))
        cs = CrossfadeSource(tail=tail, head=head, fade_frames=4)

        mixed = [cs.read() for _ in range(4)]
        for i, out in enumerate(mixed):
            assert out != head_frames[i], f"frame {i} should differ from head-alone bytes"

        # Frame 4 onward: head alone, byte-identical to the head's own output.
        assert cs.read() == head_frames[4]
        assert cs.read() == head_frames[5]

    def test_tail_dropped_the_instant_fade_window_ends(self):
        tail = _FakeAudioSource([b"x" * 3840] * 2)
        head = _FakeAudioSource([b"y" * 3840] * 10)
        cs = CrossfadeSource(tail=tail, head=head, fade_frames=2)
        assert tail.cleanup_calls == 0
        cs.read()
        assert tail.cleanup_calls == 0
        cs.read()
        # The fade window just ended on this read — the tail must already be dropped.
        assert tail.cleanup_calls == 1
        cs.read()
        # Never cleaned a second time just because the track keeps playing.
        assert tail.cleanup_calls == 1

    def test_equal_power_no_headroom_gain(self):
        """Verifies the equal-power mix formula directly, with no extra gain applied
        beyond audioop.mul/add (RESEARCH: 0.0019% clipping measured with none)."""
        import audioop
        import math

        sample = (10000).to_bytes(2, "little", signed=True) * 1920  # 3840 bytes
        tail = _FakeAudioSource([sample, sample])
        head = _FakeAudioSource([sample, sample])
        cs = CrossfadeSource(tail=tail, head=head, fade_frames=2)

        cs.read()  # frame 0: progress=0 -> g_out=1, g_in=0
        out = cs.read()  # frame 1: progress=0.5 -> g_out=g_in=cos/sin(pi/4)
        g = math.sin(0.5 * math.pi / 2)
        expected = audioop.add(audioop.mul(sample, 2, g), audioop.mul(sample, 2, g), 2)
        assert out == expected


def test_crossfade_source_cleans_both():
    """VALIDATION row 13 (exact test name, MANDATED — do not rename) / Critical
    Rule 3: a tail whose cleanup() raises still results in the head's
    cleanup() being called. The head must be cleaned in a finally, never
    skipped just because the tail raised.
    """
    frame = b"x" * 3840
    tail = _FakeAudioSource([frame] * 2, raise_on_cleanup=True)
    head = _FakeAudioSource([frame] * 10)
    cs = CrossfadeSource(tail=tail, head=head, fade_frames=4)

    with pytest.raises(RuntimeError):
        cs.cleanup()

    assert tail.cleanup_calls == 1
    assert head.cleanup_calls == 1

    # cleanup() is idempotent — a second call (e.g. from _play_track's failure
    # path, or discord.py's player calling it again) must not re-invoke
    # either child's cleanup or raise again.
    cs.cleanup()
    assert tail.cleanup_calls == 1
    assert head.cleanup_calls == 1


def test_crossfade_tolerates_empty_tail():
    """VALIDATION row 14 (exact test name, MANDATED — do not rename): a tail
    returning b"" on its very first read (a short file, or an -ss seek
    landing past EOF) degrades to a plain fade-in and never raises.
    """
    frame = b"x" * 3840
    tail = _FakeAudioSource([])  # empty from the very first read
    head = _FakeAudioSource([frame] * 10)
    cs = CrossfadeSource(tail=tail, head=head, fade_frames=4)

    # Must not raise, and must still produce non-empty output for every fade frame.
    outputs = [cs.read() for _ in range(4)]
    for out in outputs:
        assert out != b""

    # The (empty) tail is still cleaned up once the fade window ends.
    assert tail.cleanup_calls == 1

    # After the fade window: head alone, no crash.
    remaining = head.read()
    assert cs.read() == remaining
