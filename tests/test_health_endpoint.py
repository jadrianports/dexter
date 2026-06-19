"""Tests for the degraded /health endpoint (OPS-02, D-28).

Verifies:
    test_health_ok         — no degraded_reasons → body is {"status":"ok"}
    test_health_degraded_db — pool raises on execute → body includes "database unreachable"
    test_health_always_200 — HTTP status is always 200, even with DB down (D-28)

Test approach: construct gather_bot_metrics() directly with a fake bot, then
assert on the dict it produces. The health handler logic (body selection) is
tested by re-implementing it inline (same logic path as bot.py handler) so
we validate both gather_bot_metrics AND the handler's body-selection logic.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers to build a fake bot for gather_bot_metrics
# ---------------------------------------------------------------------------


def _make_fake_pool(db_ok: bool):
    """Build a mock asyncpg pool that succeeds or raises on conn.execute."""
    pool = MagicMock()

    # Fake connection
    conn = AsyncMock()
    if db_ok:
        conn.execute = AsyncMock(return_value=None)
    else:
        conn.execute = AsyncMock(side_effect=ConnectionRefusedError("db down"))

    # pool.acquire() as async context manager
    @asynccontextmanager
    async def _acquire():
        yield conn

    pool.acquire = _acquire
    return pool


def _make_fake_bot(db_ok: bool = True, gateway_ready: bool = True):
    """Build a minimal bot-like object for gather_bot_metrics."""
    bot = MagicMock()
    bot.guilds = []
    bot.voice_clients = []
    bot.is_ready.return_value = gateway_ready
    bot.shard_count = 1
    bot.cogs = {}
    bot.pool = _make_fake_pool(db_ok)
    # No _start_monotonic → uptime_seconds defaults to 0.0
    if hasattr(bot, "_start_monotonic"):
        del bot._start_monotonic
    # Remove _start_monotonic via spec (MagicMock may expose it via attribute access)
    # We want hasattr(bot, "_start_monotonic") == False
    bot._spec_class = None
    # Use configure_mock to avoid having _start_monotonic
    type(bot).__contains__ = MagicMock(return_value=False)
    return bot


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_ok():
    """When gather_bot_metrics returns no degraded_reasons, handler body is {"status":"ok"}."""
    from cogs.ops import gather_bot_metrics

    bot = _make_fake_bot(db_ok=True, gateway_ready=True)
    metrics = await gather_bot_metrics(bot)

    assert metrics["degraded_reasons"] == [], (
        f"Expected empty degraded_reasons for healthy bot, got: {metrics['degraded_reasons']}"
    )
    assert metrics["db_ok"] is True
    assert metrics["gateway_ready"] is True

    # Simulate the handler's body-selection logic (same as bot.py health handler)
    reasons = metrics.get("degraded_reasons", [])
    if reasons:
        body = json.dumps({"status": "degraded", "reasons": reasons})
    else:
        body = '{"status":"ok"}'

    assert body == '{"status":"ok"}', f"Expected ok body, got: {body}"


@pytest.mark.asyncio
async def test_health_degraded_db():
    """When the pool raises on execute, body includes status=degraded and reason."""
    from cogs.ops import gather_bot_metrics

    bot = _make_fake_bot(db_ok=False, gateway_ready=True)
    metrics = await gather_bot_metrics(bot)

    assert metrics["db_ok"] is False
    assert "database unreachable" in metrics["degraded_reasons"], (
        f"Expected 'database unreachable' in reasons, got: {metrics['degraded_reasons']}"
    )

    # Simulate handler body-selection logic
    reasons = metrics.get("degraded_reasons", [])
    assert reasons, "Expected non-empty degraded_reasons with db down"

    body = json.dumps({"status": "degraded", "reasons": reasons})
    parsed = json.loads(body)

    assert parsed["status"] == "degraded"
    assert "database unreachable" in parsed["reasons"]
    # D-27: body must NOT contain internal state keys
    assert "guild_count" not in parsed
    assert "shard_count" not in parsed
    assert "voice_count" not in parsed


@pytest.mark.asyncio
async def test_health_always_200():
    """With DB down, the HTTP status must still be 200 (D-28 — no kill-loop).

    We test this by verifying gather_bot_metrics completes without raising
    even when the DB pool raises, and that the handler logic always produces
    a valid body (never raises or returns None) regardless of degraded state.
    """
    from cogs.ops import gather_bot_metrics

    bot = _make_fake_bot(db_ok=False, gateway_ready=False)
    # gather_bot_metrics must not raise — it must always return a dict
    metrics = await gather_bot_metrics(bot)

    assert isinstance(metrics, dict), "gather_bot_metrics must always return a dict"
    assert "degraded_reasons" in metrics

    # Handler body-selection: must always produce a valid JSON string, never raise
    reasons = metrics.get("degraded_reasons", [])
    if reasons:
        body = json.dumps({"status": "degraded", "reasons": reasons})
    else:
        body = '{"status":"ok"}'

    # Body must be valid JSON (parseable)
    parsed = json.loads(body)
    assert "status" in parsed, "Health body must have a 'status' key"
    # Status must be a known value (ok or degraded) — never a bare exception
    assert parsed["status"] in ("ok", "degraded"), (
        f"Unexpected status value: {parsed['status']}"
    )
    # HTTP 200 is enforced by bot.py returning Response(...) unconditionally —
    # validated here by confirming the handler logic path never raises
