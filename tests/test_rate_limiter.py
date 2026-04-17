"""Tests for the Gemini rate limiter."""

import asyncio

import pytest

from services.gemini import _RateLimiter, GeminiRateLimitError


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
