"""Tests for AudioService cache logic."""

import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from services.audio import AudioService


@pytest.fixture
def tmp_cache(tmp_path):
    """Create a temporary cache directory."""
    return tmp_path


@pytest.fixture
def audio_service(tmp_cache):
    yt_service = MagicMock()
    service = AudioService(youtube_service=yt_service, cache_dir=tmp_cache)
    return service


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
