"""Tests for AudioService cache logic and FFmpeg options builder."""

import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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


class TestCacheCleanup:
    def test_cleanup_removes_oldest(self, audio_service, tmp_cache):
        # Create files that exceed the max size (using small sizes to avoid disk issues)
        # 5 files x 500KB each = 2.5MB total, limit set to 1MB
        for i in range(5):
            f = tmp_cache / f"vid{i}.opus"
            f.write_bytes(b"x" * (500 * 1024))  # 500KB each = 2.5MB total

        # Access the newest ones to update access time
        for i in [3, 4]:
            os.utime(tmp_cache / f"vid{i}.opus", None)

        audio_service.max_cache_mb = 1  # 1MB limit
        audio_service.cleanup_cache()

        remaining = list(tmp_cache.glob("*.opus"))
        total_size = sum(f.stat().st_size for f in remaining)
        assert total_size <= 1 * 1024 * 1024

    def test_cleanup_noop_under_limit(self, audio_service, tmp_cache):
        (tmp_cache / "small.opus").write_bytes(b"x" * 1024)
        audio_service.max_cache_mb = 2048
        audio_service.cleanup_cache()
        assert (tmp_cache / "small.opus").exists()
