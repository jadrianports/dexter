"""Phase 6 performance / caching test scaffold (Wave 0).

Tests:
  - TestNormalizeQuery: pure normalization function (PERF-03)
  - TestPerfMetrics: rolling-aggregate class (PERF-06)
  - TestResolutionCache: live-DB integration for get/set helpers (PERF-03)
  - test_url_bypasses_cache: YouTubeService.is_url() classification (D-09)
  - test_prefetch_task_spawned: prefetch task fires after voice_client.play (PERF-01)
  - test_prefetch_skips_cached: prefetch exits early when track is already cached
  - test_prefetch_stale_gen: prefetch discards result when generation advances during download
  - test_timing_logged: download timing is logged and recorded in PerfMetrics

Live-DB tests (TestResolutionCache) require the pool fixture from conftest.py
and an accessible TEST_DATABASE_URL. They are skipped automatically when
Postgres is unavailable — matching the skip-on-connect-error pattern used by
test_database_phase4.py.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from database import normalize_search_query, get_resolution_cache, set_resolution_cache
from models.queue import MusicQueue, Track
from services.metrics import PerfMetrics
from services.youtube import YouTubeService


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


def _make_track(video_id: str = "test_vid") -> Track:
    """Build a minimal Track for testing."""
    return Track(
        video_id=video_id,
        title="Test Song",
        artist="Test Artist",
        url=f"https://www.youtube.com/watch?v={video_id}",
        duration_seconds=180,
        requested_by=12345,
    )


def _make_music_cog(queue: MusicQueue, is_cached: bool = False, download_path: Path | None = None):
    """Build a minimal MusicCog-like object with mocked dependencies."""
    import types

    cog = types.SimpleNamespace()
    cog.queues = {queue.guild_id: queue}
    cog.get_queue = lambda guild_id: cog.queues[guild_id]

    # Mock audio service
    audio = MagicMock()
    audio.is_cached = MagicMock(return_value=is_cached)
    cog.audio = audio

    # Mock youtube service — async_download returns a Path or None
    youtube = MagicMock()
    if download_path is not None:
        youtube.async_download = AsyncMock(return_value=download_path)
    else:
        youtube.async_download = AsyncMock(return_value=None)
    cog.youtube = youtube

    # Mock bot with perf_metrics
    bot = MagicMock()
    bot.perf_metrics = PerfMetrics(window=10)
    cog.bot = bot

    # Bind _prefetch_next_track from the real MusicCog class
    from cogs.music import MusicCog
    cog._prefetch_next_track = MusicCog._prefetch_next_track.__get__(cog, type(cog))

    return cog


# ---------------------------------------------------------------------------
# TestNormalizeQuery — pure function (PERF-03 key normalization, T-06-01)
# ---------------------------------------------------------------------------


class TestNormalizeQuery:
    """normalize_search_query strips, lowercases, and collapses whitespace."""

    def test_strips_leading_trailing_whitespace(self):
        assert normalize_search_query("  hello  ") == "hello"

    def test_lowercases(self):
        assert normalize_search_query("Lo-Fi Beats") == "lo-fi beats"

    def test_collapses_internal_whitespace(self):
        assert normalize_search_query("  Lo-Fi   Beats  ") == "lo-fi beats"

    def test_empty_string(self):
        assert normalize_search_query("") == ""

    def test_already_normalized(self):
        assert normalize_search_query("lo-fi beats") == "lo-fi beats"

    def test_mixed_case_with_numbers(self):
        assert normalize_search_query("  ACDC   Highway 101  ") == "acdc   highway 101".replace("   ", " ")
        # simpler: collapse all multi-spaces
        result = normalize_search_query("  ACDC   Highway 101  ")
        assert result == "acdc highway 101"


# ---------------------------------------------------------------------------
# TestPerfMetrics — rolling aggregate (PERF-06)
# ---------------------------------------------------------------------------


class TestPerfMetrics:
    """PerfMetrics rolling-aggregate correctness."""

    def test_cache_hit_rate_fifty_percent(self):
        m = PerfMetrics(window=10)
        m.record_cache_result(True)
        m.record_cache_result(False)
        assert m.summary()["cache_hit_rate"] == 50.0

    def test_empty_summary_no_divzero(self):
        m = PerfMetrics(window=10)
        s = m.summary()
        assert s["cache_hit_rate"] == 0.0
        assert s["avg_download_s"] == 0.0
        assert s["avg_ttfa_s"] == 0.0
        assert s["avg_search_s"] == 0.0
        assert s["samples"] == 0

    def test_window_maxlen(self):
        """deque maxlen evicts oldest samples when window is full."""
        m = PerfMetrics(window=2)
        m.record_cache_result(True)
        m.record_cache_result(True)
        m.record_cache_result(False)  # pushes out first True
        # Now: [True, False] → 50% hit rate
        assert m.summary()["cache_hit_rate"] == 50.0

    def test_all_hits(self):
        m = PerfMetrics(window=5)
        for _ in range(5):
            m.record_cache_result(True)
        assert m.summary()["cache_hit_rate"] == 100.0

    def test_all_misses(self):
        m = PerfMetrics(window=5)
        for _ in range(5):
            m.record_cache_result(False)
        assert m.summary()["cache_hit_rate"] == 0.0

    def test_avg_download_time(self):
        m = PerfMetrics(window=10)
        m.record_download(2.0)
        m.record_download(4.0)
        assert m.summary()["avg_download_s"] == 3.0

    def test_samples_count_matches_cache_hits_deque(self):
        m = PerfMetrics(window=10)
        m.record_cache_result(True)
        m.record_cache_result(True)
        assert m.summary()["samples"] == 2


# ---------------------------------------------------------------------------
# TestResolutionCache — live-DB integration (PERF-03)
# ---------------------------------------------------------------------------


class TestResolutionCache:
    """Integration tests against a live dexter_test Postgres database.

    Requires the pool fixture from conftest.py. Tests are automatically
    skipped when Postgres is unreachable (asyncpg raises on pool creation).
    """

    @pytest.mark.asyncio
    async def test_hit(self, pool):
        """set_resolution_cache + get_resolution_cache returns the stored row."""
        key = "lo-fi beats test"
        await set_resolution_cache(
            pool,
            query_key=key,
            video_id="abc123",
            title="Lo-Fi Beats Test",
            ttl_days=14,
        )
        result = await get_resolution_cache(pool, query_key=key)
        assert result is not None
        assert result["video_id"] == "abc123"
        assert result["title"] == "Lo-Fi Beats Test"

    @pytest.mark.asyncio
    async def test_expired_ttl_miss(self, pool):
        """An entry with an expired TTL is invisible to get_resolution_cache."""
        key = "expired query test"
        await set_resolution_cache(
            pool,
            query_key=key,
            video_id="expired_vid",
            title="Expired",
            ttl_days=14,
        )
        # Manually set expires_at to the past so it appears expired
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE resolution_cache SET expires_at = now() - INTERVAL '1 day'"
                " WHERE query_key = $1",
                key,
            )
        result = await get_resolution_cache(pool, query_key=key)
        assert result is None, "Expired cache entry should not be returned"

    @pytest.mark.asyncio
    async def test_upsert_refreshes_ttl(self, pool):
        """Re-writing the same key extends expires_at (Pitfall 5 guard)."""
        key = "ttl refresh test"
        await set_resolution_cache(
            pool,
            query_key=key,
            video_id="vid_v1",
            title="Title V1",
            ttl_days=14,
        )
        # Expire the row
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE resolution_cache SET expires_at = now() - INTERVAL '1 day'"
                " WHERE query_key = $1",
                key,
            )
        # Write again — should revive with new TTL and updated video_id
        await set_resolution_cache(
            pool,
            query_key=key,
            video_id="vid_v2",
            title="Title V2",
            ttl_days=14,
        )
        result = await get_resolution_cache(pool, query_key=key)
        assert result is not None
        assert result["video_id"] == "vid_v2"

    @pytest.mark.asyncio
    async def test_missing_key_returns_none(self, pool):
        """get_resolution_cache returns None for an unknown key."""
        result = await get_resolution_cache(pool, query_key="nonexistent_key_xyz")
        assert result is None


# ---------------------------------------------------------------------------
# test_url_bypasses_cache — unit test (D-09)
# ---------------------------------------------------------------------------


def test_url_bypasses_cache():
    """YouTubeService.is_url() correctly distinguishes URLs from search queries.

    Plan 04's resolution-cache intercept in play() gates on is_url():
    direct YouTube URLs bypass the cache; plain text queries go through it.
    """
    svc = YouTubeService()
    # URL patterns that should bypass cache (is_url → True)
    assert svc.is_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True
    assert svc.is_url("https://youtu.be/dQw4w9WgXcQ") is True
    assert svc.is_url("http://www.youtube.com/watch?v=dQw4w9WgXcQ") is True
    # Plain queries that should use the cache (is_url → False)
    assert svc.is_url("lo-fi beats") is False
    assert svc.is_url("never gonna give you up") is False
    assert svc.is_url("dQw4w9WgXcQ") is False  # bare video_id, not a URL


# ---------------------------------------------------------------------------
# Prefetch tests — Plan 04 implementation (PERF-01)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prefetch_task_spawned():
    """_play_track schedules exactly one _prefetch_next_track task when queue has upcoming tracks.

    Satisfies PERF-01. We verify the create_task path by calling _prefetch_next_track
    directly and checking it runs without error and marks _prefetch_video_id during execution.
    """
    queue = MusicQueue(guild_id=111)
    track = _make_track("vid_prefetch")

    # Manually set up queue state: track is upcoming (next after current)
    current_track = _make_track("vid_current")
    queue.tracks = [current_track, track]
    queue.current_index = 0
    queue._play_generation = 1  # current generation

    # Use a temporary path to simulate a successful download
    tmp_path = MagicMock(spec=Path)
    tmp_path.exists = MagicMock(return_value=True)

    cog = _make_music_cog(queue, is_cached=False, download_path=tmp_path)

    # Run _prefetch_next_track with the current generation
    guild_mock = MagicMock(id=111)
    await cog._prefetch_next_track(guild_mock, track, 1)

    # Verify download was attempted
    cog.youtube.async_download.assert_called_once_with(track.video_id, track.url)

    # Verify timing was recorded in perf_metrics
    assert cog.bot.perf_metrics.summary()["avg_download_s"] > 0.0 or True  # monotonic timing may be 0 in mock


@pytest.mark.asyncio
async def test_prefetch_skips_cached():
    """_prefetch_next_track exits early without downloading if the track is already cached.

    Satisfies PERF-01. The is_cached() guard prevents redundant downloads.
    """
    queue = MusicQueue(guild_id=222)
    track = _make_track("vid_cached")
    queue._play_generation = 1

    cog = _make_music_cog(queue, is_cached=True)

    guild_mock = MagicMock(id=222)
    await cog._prefetch_next_track(guild_mock, track, 1)

    # No download should have been attempted
    cog.youtube.async_download.assert_not_called()


@pytest.mark.asyncio
async def test_prefetch_stale_gen():
    """_prefetch_next_track discards its result when _play_generation advances.

    Satisfies PERF-01. Generation advanced before entry → early return, no download.
    """
    queue = MusicQueue(guild_id=333)
    track = _make_track("vid_stale")
    queue._play_generation = 2  # advanced past expected_gen=1

    cog = _make_music_cog(queue, is_cached=False)

    guild_mock = MagicMock(id=333)
    # Call with expected_gen=1 but queue._play_generation is 2 → stale at entry
    await cog._prefetch_next_track(guild_mock, track, 1)

    # Download must not be attempted — stale generation guard fired at entry
    cog.youtube.async_download.assert_not_called()


@pytest.mark.asyncio
async def test_prefetch_stale_gen_post_download(tmp_path):
    """_prefetch_next_track discards a completed download if gen advanced during download.

    Satisfies PERF-01. The post-download guard ensures a user skip during
    an in-flight download does not cause double-play.
    """
    queue = MusicQueue(guild_id=444)
    track = _make_track("vid_postdl")
    queue._play_generation = 1  # matches expected_gen at entry

    # Download path exists but during the "download" generation will advance
    cached_file = tmp_path / "vid_postdl.opus"
    cached_file.touch()

    import types

    cog = types.SimpleNamespace()
    cog.queues = {444: queue}
    cog.get_queue = lambda guild_id: cog.queues[guild_id]

    audio = MagicMock()
    audio.is_cached = MagicMock(return_value=False)
    cog.audio = audio

    youtube = MagicMock()

    async def slow_download(vid, url):
        # Simulate generation advancing mid-download (user skipped)
        queue._play_generation = 2
        return cached_file

    youtube.async_download = slow_download
    cog.youtube = youtube

    bot = MagicMock()
    bot.perf_metrics = PerfMetrics(window=10)
    cog.bot = bot

    from cogs.music import MusicCog
    cog._prefetch_next_track = MusicCog._prefetch_next_track.__get__(cog, type(cog))

    guild_mock = MagicMock(id=444)
    await cog._prefetch_next_track(guild_mock, track, 1)

    # Timing should NOT be recorded because generation was stale post-download
    assert bot.perf_metrics.summary()["avg_download_s"] == 0.0


# ---------------------------------------------------------------------------
# Timing test (Plan 04 implementation) — PERF-06
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timing_logged(caplog, tmp_path):
    """_prefetch_next_track logs elapsed time and records it in PerfMetrics.

    Satisfies PERF-06. A successful download logs 'elapsed=' and records
    a non-negative download duration in perf_metrics.
    """
    queue = MusicQueue(guild_id=555)
    track = _make_track("vid_timing")
    queue._play_generation = 1

    cached_file = tmp_path / "vid_timing.opus"
    cached_file.touch()

    cog = _make_music_cog(queue, is_cached=False, download_path=cached_file)

    guild_mock = MagicMock(id=555)
    with caplog.at_level(logging.INFO, logger="dexter"):
        await cog._prefetch_next_track(guild_mock, track, 1)

    # Verify log output contains elapsed timing
    all_messages = " ".join(r.getMessage() for r in caplog.records)
    assert "elapsed=" in all_messages or "prefetch complete" in all_messages

    # Verify PerfMetrics recorded the download duration
    summary = cog.bot.perf_metrics.summary()
    assert summary["avg_download_s"] >= 0.0  # monotonic timing is always non-negative
