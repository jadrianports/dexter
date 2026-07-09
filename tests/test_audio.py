"""Tests for AudioService cache logic and FFmpeg options builder."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.audio import AudioService, _build_ffmpeg_opts


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
