"""Phase 6 performance / caching test scaffold (Wave 0).

Tests:
  - TestNormalizeQuery: pure normalization function (PERF-03)
  - TestPerfMetrics: rolling-aggregate class (PERF-06)
  - TestResolutionCache: live-DB integration for get/set helpers (PERF-03)
  - test_url_bypasses_cache: YouTubeService.is_url() classification (D-09)
  - test_prefetch_task_spawned, test_prefetch_skips_cached, test_prefetch_stale_gen: xfail (Plan 04)
  - test_timing_logged: xfail (Plan 04)

Live-DB tests (TestResolutionCache) require the pool fixture from conftest.py
and an accessible TEST_DATABASE_URL. They are skipped automatically when
Postgres is unavailable — matching the skip-on-connect-error pattern used by
test_database_phase4.py.
"""

from __future__ import annotations

import pytest

from database import normalize_search_query, get_resolution_cache, set_resolution_cache
from services.metrics import PerfMetrics
from services.youtube import YouTubeService


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
# Prefetch placeholders (Plan 04 will implement & remove xfail)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="implemented in Plan 04-04", strict=False)
def test_prefetch_task_spawned():
    """A prefetch task is created immediately after voice_client.play() starts.

    Satisfies PERF-01. Plan 04 wires _prefetch_next_track in _play_track;
    this test verifies asyncio.create_task was called with the right arguments.
    """
    raise NotImplementedError("Plan 04 prefetch wiring not yet implemented")


@pytest.mark.xfail(reason="implemented in Plan 04-04", strict=False)
def test_prefetch_skips_cached():
    """Prefetch exits early without downloading if the track is already cached.

    Satisfies PERF-01. Plan 04 adds the AudioService.is_cached() guard inside
    _prefetch_next_track; this test verifies no download is attempted.
    """
    raise NotImplementedError("Plan 04 prefetch wiring not yet implemented")


@pytest.mark.xfail(reason="implemented in Plan 04-04", strict=False)
def test_prefetch_stale_gen():
    """Prefetch discards its result when _play_generation advanced during download.

    Satisfies PERF-01. Plan 04 adds the generation guard in _prefetch_next_track;
    this test verifies the prefetched file is not used after a user skip.
    """
    raise NotImplementedError("Plan 04 prefetch wiring not yet implemented")


# ---------------------------------------------------------------------------
# Timing placeholder (Plan 04 will implement & remove xfail)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="implemented in Plan 04-04", strict=False)
def test_timing_logged():
    """Pipeline timing is logged and recorded in PerfMetrics after each /play.

    Satisfies PERF-06. Plan 04 wires time.monotonic() deltas into record_download,
    record_search, and record_ttfa; this test verifies structured log output and
    PerfMetrics.summary() reflects the recorded values.
    """
    raise NotImplementedError("Plan 04 timing wiring not yet implemented")
