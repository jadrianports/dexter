"""Pure health-status decision logic extracted from bot.py /health handler and
cogs/ops.py gather_bot_metrics (TEST-02).

All functions in this module are deterministic and side-effect-free: no asyncio,
no Discord imports, no database calls, no random, no datetime.now(), no time.monotonic().

Decision functions here are the single source of truth for (D-01/D-02):
  - ``determine_health_status``   — bot.py /health handler (status code + body)
  - ``assemble_degraded_reasons`` — cogs/ops.py gather_bot_metrics degraded_reasons list

Phase 10 scar regressions covered by tests/test_health_logic.py (D-05):
  - scar #3  REL-01 degraded path (each critical reason × HEALTH_STRICT_STATUS on/off)
"""

from __future__ import annotations

import json


def assemble_degraded_reasons(
    *,
    pool_present: bool,
    db_ok: bool,
    gateway_ready: bool,
    ready_done: bool,
    musiccog_loaded: bool,
) -> list[str]:
    """Assemble the list of degraded reasons from bot-state primitives.

    Pure — takes boolean primitives computed by the async glue in
    ``gather_bot_metrics`` and returns the exact reason strings expected by
    the ``/health`` handler.

    Preserves the order and mutual-exclusivity of the live code in
    ``cogs/ops.py``:
    - pool-missing and db-unreachable are mutually exclusive (if/elif mirrors
      the live pool-None / probe-failed branches).
    - Gateway and MusicCog checks are independent of each other.
    - MusicCog check is suppressed until ``ready_done`` is True, preventing
      a false-degraded report during startup (Pitfall 3 / REL-01).

    Args:
        pool_present:    True if ``bot.pool is not None``.
        db_ok:           True if the async DB probe (``SELECT 1``) succeeded.
        gateway_ready:   True if ``bot.is_ready()``.
        ready_done:      True if ``getattr(bot, "_ready_done", False)``.
        musiccog_loaded: True if ``bot.cogs.get("MusicCog") is not None``.

    Returns:
        A list of zero or more human-readable degraded-reason strings.
        An empty list means the bot is healthy.
    """
    reasons: list[str] = []

    # Pool check and DB probe are mutually exclusive: if the pool is absent we
    # cannot run a probe, so we skip to the pool-missing string directly.
    if not pool_present:
        reasons.append("database pool not initialized")
    elif not db_ok:
        reasons.append("database unreachable")

    if not gateway_ready:
        reasons.append("discord gateway not ready")

    # MusicCog check only fires after full init to avoid false-degraded during
    # bot startup — cogs load after pool/services (_ready_done guard; Pitfall 3).
    if ready_done and not musiccog_loaded:
        reasons.append("MusicCog not loaded")

    return reasons


def determine_health_status(reasons: list[str], strict: bool) -> tuple[int, str]:
    """Map degraded reasons + HEALTH_STRICT_STATUS to an HTTP status code and body.

    Single source of truth for the reasons → (status, body) decision previously
    inline in ``bot.py``'s ``/health`` handler (D-02 true extraction).

    Decision matrix (D-03 / D-05 scar #3 — REL-01 degraded path):
    - reasons non-empty + ``strict=True``  → ``(503, degraded-body)``
    - reasons non-empty + ``strict=False`` → ``(200, degraded-body)``
    - reasons empty                        → ``(200, ok-body)``

    D-27: body exposes only ``status`` and generic reason strings —
    no guild/shard/pool internals.

    Args:
        reasons: List of degraded-reason strings (from
                 ``assemble_degraded_reasons`` or a fallback).
        strict:  ``True`` if ``HEALTH_STRICT_STATUS`` is on (the default in
                 ``config.py``). When ``True``, any degraded reason returns 503.
                 When ``False``, returns 200 even when degraded (legacy behavior).

    Returns:
        A ``(status_code, json_body)`` tuple where ``json_body`` is a JSON string.
    """
    if reasons:
        body = json.dumps({"status": "degraded", "reasons": reasons})
        status = 503 if strict else 200
    else:
        body = '{"status":"ok"}'
        status = 200
    return status, body
