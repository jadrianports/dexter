"""Tests for the Gemini rate limiter."""

import asyncio

import pytest

from services.gemini import GeminiRateLimitError, _RateLimiter


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_allows_under_limit(self):
        limiter = _RateLimiter(max_requests=5, window_seconds=60)
        await limiter.acquire(priority=1)

    @pytest.mark.asyncio
    async def test_tracks_request_count(self):
        limiter = _RateLimiter(max_requests=3, window_seconds=60)
        await limiter.acquire(priority=1)
        await limiter.acquire(priority=1)
        assert len(limiter._timestamps) == 2

    @pytest.mark.asyncio
    async def test_low_priority_rejected_when_full(self):
        limiter = _RateLimiter(max_requests=2, window_seconds=60)
        await limiter.acquire(priority=1)
        await limiter.acquire(priority=1)
        with pytest.raises(GeminiRateLimitError):
            await limiter.acquire(priority=2)

    @pytest.mark.asyncio
    async def test_cleans_old_timestamps(self):
        limiter = _RateLimiter(max_requests=2, window_seconds=0.1)
        await limiter.acquire(priority=1)
        await limiter.acquire(priority=1)
        await asyncio.sleep(0.15)
        await limiter.acquire(priority=1)
        assert len(limiter._timestamps) == 1

    @pytest.mark.asyncio
    async def test_rpm_usage_getter(self):
        """After N acquire(priority=1) calls, rpm_usage() must return N (D-24/OPS-03)."""
        limiter = _RateLimiter(max_requests=5, window_seconds=60)
        await limiter.acquire(priority=1)
        await limiter.acquire(priority=1)
        await limiter.acquire(priority=1)
        assert limiter.rpm_usage() == 3, f"Expected rpm_usage() == 3 after 3 acquires, got {limiter.rpm_usage()}"

    @pytest.mark.asyncio
    async def test_rpm_headroom_getter(self):
        """rpm_headroom() must equal max_requests - rpm_usage(), floored at 0 (D-24/OPS-03)."""
        max_req = 5
        limiter = _RateLimiter(max_requests=max_req, window_seconds=60)
        await limiter.acquire(priority=1)
        await limiter.acquire(priority=1)
        usage = limiter.rpm_usage()
        headroom = limiter.rpm_headroom()
        assert headroom == max_req - usage, f"Expected rpm_headroom() == {max_req - usage}, got {headroom}"
