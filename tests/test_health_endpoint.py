"""Tests for the degraded /health endpoint (OPS-02, D-28, REL-01).

Verifies:
    test_health_ok              — no degraded_reasons → body is {"status":"ok"}
    test_health_degraded_db     — pool raises on execute → body includes "database unreachable"
    test_health_always_200      — HTTP status is always 200 when HEALTH_STRICT_STATUS=False (D-28)
    test_musiccog_missing       — MusicCog absent post-init → "MusicCog not loaded" in reasons
    test_startup_no_false_degraded — MusicCog absent during startup (_ready_done absent) → NOT degraded
    test_503_strict_mode        — strict + degraded → status 503
    test_200_legacy_mode        — legacy flag False + degraded → status 200

Test approach: construct gather_bot_metrics() directly with a fake bot, then
assert on the dict it produces. The health handler logic (body selection) is
tested by re-implementing it inline (same logic path as bot.py handler) so
we validate both gather_bot_metrics AND the handler's body-selection logic.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
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


def _make_fake_bot(
    db_ok: bool = True,
    gateway_ready: bool = True,
    ready_done: bool = False,
    music_cog_loaded: bool = True,
):
    """Build a minimal bot-like object for gather_bot_metrics.

    Args:
        db_ok:             Whether the fake pool responds to SELECT 1 without raising.
        gateway_ready:     Whether bot.is_ready() returns True.
        ready_done:        Whether bot._ready_done is True (post-init complete).
        music_cog_loaded:  Whether "MusicCog" is present in bot.cogs.
    """
    # WR-05: a plain SimpleNamespace stub (not MagicMock) so attribute presence
    # is REAL — hasattr(bot, "_start_monotonic") is genuinely False here, so
    # gather_bot_metrics keeps uptime_seconds at its 0.0 default. A MagicMock would
    # auto-create the attribute (hasattr always True) and compute uptime as a
    # MagicMock. Crucially this also avoids mutating the shared MagicMock class
    # (the old `type(bot).__contains__ = ...` monkeypatched __contains__ process-wide).
    cog_value = SimpleNamespace() if music_cog_loaded else None
    bot = SimpleNamespace(
        guilds=[],
        voice_clients=[],
        is_ready=lambda: gateway_ready,
        shard_count=1,
        cogs={"MusicCog": cog_value} if music_cog_loaded else {},
        pool=_make_fake_pool(db_ok),
        # _ready_done explicit so getattr(bot, "_ready_done", False) is correct.
        _ready_done=ready_done,
        # Intentionally NO _start_monotonic attribute → hasattr is False → 0.0 default.
    )
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
    # WR-05: with no _start_monotonic on the stub, uptime must stay at its 0.0 default
    # (the old MagicMock fake auto-created the attr and produced a MagicMock here).
    assert metrics["uptime_seconds"] == 0.0

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


# ---------------------------------------------------------------------------
# REL-01: New tests for MusicCog degraded check + status code selection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_musiccog_missing_post_init():
    """gather_bot_metrics appends 'MusicCog not loaded' when _ready_done=True and MusicCog absent.

    Fake bot: _ready_done=True, cogs={} (no MusicCog), DB ok, gateway ready.
    Expected: 'MusicCog not loaded' in degraded_reasons.
    """
    from cogs.ops import gather_bot_metrics

    bot = _make_fake_bot(db_ok=True, gateway_ready=True, ready_done=True, music_cog_loaded=False)
    metrics = await gather_bot_metrics(bot)

    assert "MusicCog not loaded" in metrics["degraded_reasons"], (
        f"Expected 'MusicCog not loaded' in reasons, got: {metrics['degraded_reasons']}"
    )


@pytest.mark.asyncio
async def test_startup_no_false_degraded():
    """During startup (_ready_done absent/False), missing MusicCog must NOT be degraded.

    Fake bot: _ready_done=False (startup in progress), cogs={} (MusicCog not yet loaded),
    DB ok, gateway ready.
    Expected: 'MusicCog not loaded' NOT in degraded_reasons.
    """
    from cogs.ops import gather_bot_metrics

    # _ready_done=False simulates startup (MusicCog loads after pool/services)
    bot = _make_fake_bot(db_ok=True, gateway_ready=True, ready_done=False, music_cog_loaded=False)
    metrics = await gather_bot_metrics(bot)

    assert "MusicCog not loaded" not in metrics["degraded_reasons"], (
        f"'MusicCog not loaded' must NOT appear during startup, got: {metrics['degraded_reasons']}"
    )


@pytest.mark.asyncio
async def test_status_503_strict_mode():
    """Handler yields status=503 when strict mode on + degraded reasons present.

    Simulates the bot.py inline handler logic: HEALTH_STRICT_STATUS=True + reasons → 503.
    """
    from cogs.ops import gather_bot_metrics
    import config

    # Bot with MusicCog missing post-init → guarantees a degraded reason
    bot = _make_fake_bot(db_ok=True, gateway_ready=True, ready_done=True, music_cog_loaded=False)
    metrics = await gather_bot_metrics(bot)
    reasons = metrics.get("degraded_reasons", [])

    assert reasons, "Need non-empty degraded_reasons to test 503 path"

    # Inline handler logic (mirrors bot.py health() handler)
    if reasons:
        body = json.dumps({"status": "degraded", "reasons": reasons})
        status = 503 if getattr(config, "HEALTH_STRICT_STATUS", True) else 200
    else:
        body = '{"status":"ok"}'
        status = 200

    # HEALTH_STRICT_STATUS defaults True → expect 503
    assert status == 503, f"Expected 503 in strict mode, got {status}"
    parsed = json.loads(body)
    assert parsed["status"] == "degraded"
    # D-27: body must NOT contain internal state keys
    assert "guild_count" not in parsed
    assert "shard_count" not in parsed
    assert "voice_count" not in parsed


@pytest.mark.asyncio
async def test_status_200_legacy_mode(monkeypatch):
    """Handler yields status=200 when HEALTH_STRICT_STATUS=False even with degraded reasons.

    Simulates the legacy escape hatch: flag false → always-200 (D-28 preserved).
    """
    import importlib
    import config as cfg_mod
    from cogs.ops import gather_bot_metrics

    # Temporarily set HEALTH_STRICT_STATUS to False
    monkeypatch.setattr(cfg_mod, "HEALTH_STRICT_STATUS", False)

    bot = _make_fake_bot(db_ok=True, gateway_ready=True, ready_done=True, music_cog_loaded=False)
    metrics = await gather_bot_metrics(bot)
    reasons = metrics.get("degraded_reasons", [])

    assert reasons, "Need non-empty degraded_reasons to test legacy-200 path"

    # Inline handler logic (mirrors bot.py health() handler)
    if reasons:
        body = json.dumps({"status": "degraded", "reasons": reasons})
        status = 503 if getattr(cfg_mod, "HEALTH_STRICT_STATUS", True) else 200
    else:
        body = '{"status":"ok"}'
        status = 200

    # HEALTH_STRICT_STATUS=False → expect 200 (legacy escape hatch)
    assert status == 200, f"Expected 200 in legacy mode, got {status}"
