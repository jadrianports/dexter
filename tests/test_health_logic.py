"""Tests for logic.health pure functions — health-status decision matrix + REL-01 scar.

Covers TEST-02: determine_health_status status matrix and assemble_degraded_reasons
reason-assembly branches. No asyncio, no mocking, no RNG, no clock — all inputs
are plain bools/lists/strings (D-06 determinism seam).

Named scar test (D-05 scar #3):
  - ``test_degraded_returns_503_when_strict`` asserts each critical reason maps
    to 503 under strict mode and 200 under non-strict (REL-01 degraded path,
    Phase 9 addition).
"""

import json

from logic.health import assemble_degraded_reasons, determine_health_status

# ---------------------------------------------------------------------------
# Critical reason strings (REL-01) — defined once so tests and assertions
# share the same source of truth.
# ---------------------------------------------------------------------------

REASON_POOL_MISSING = "database pool not initialized"
REASON_DB_UNREACHABLE = "database unreachable"
REASON_GATEWAY_NOT_READY = "discord gateway not ready"
REASON_MUSICCOG_NOT_LOADED = "MusicCog not loaded"

ALL_CRITICAL_REASONS = [
    REASON_POOL_MISSING,
    REASON_DB_UNREACHABLE,
    REASON_GATEWAY_NOT_READY,
    REASON_MUSICCOG_NOT_LOADED,
]


# ---------------------------------------------------------------------------
# TestDetermineHealthStatus
# ---------------------------------------------------------------------------


class TestDetermineHealthStatus:
    # --- REL-01 scar #3 (D-05): each critical reason × strict on/off ---

    def test_degraded_returns_503_when_strict(self):
        """Each critical reason produces 503 under strict mode (REL-01 / D-05 scar #3)."""
        for reason in ALL_CRITICAL_REASONS:
            status, body = determine_health_status([reason], strict=True)
            assert status == 503, f"expected 503 for reason {reason!r}, got {status}"
            parsed = json.loads(body)
            assert parsed["status"] == "degraded"
            assert reason in parsed["reasons"]

    def test_degraded_returns_200_when_not_strict(self):
        """Each critical reason returns 200 (not 503) when strict=False (legacy path)."""
        for reason in ALL_CRITICAL_REASONS:
            status, body = determine_health_status([reason], strict=False)
            assert status == 200, f"expected 200 for reason {reason!r} (non-strict), got {status}"
            parsed = json.loads(body)
            assert parsed["status"] == "degraded"
            assert reason in parsed["reasons"]

    # --- Status matrix coverage (D-03) ---

    def test_empty_reasons_returns_200_ok(self):
        status, body = determine_health_status([], strict=True)
        assert status == 200
        assert body == '{"status":"ok"}'

    def test_empty_reasons_strict_false_returns_200_ok(self):
        status, body = determine_health_status([], strict=False)
        assert status == 200
        assert body == '{"status":"ok"}'

    def test_multiple_reasons_strict_returns_503(self):
        reasons = [REASON_DB_UNREACHABLE, REASON_GATEWAY_NOT_READY]
        status, body = determine_health_status(reasons, strict=True)
        assert status == 503
        parsed = json.loads(body)
        assert parsed["status"] == "degraded"
        assert parsed["reasons"] == reasons

    def test_multiple_reasons_not_strict_returns_200_degraded(self):
        reasons = [REASON_DB_UNREACHABLE, REASON_GATEWAY_NOT_READY]
        status, body = determine_health_status(reasons, strict=False)
        assert status == 200
        parsed = json.loads(body)
        assert parsed["status"] == "degraded"
        assert parsed["reasons"] == reasons

    def test_degraded_body_contains_reason_strings(self):
        """Body carries the exact reason strings passed in."""
        reasons = [REASON_MUSICCOG_NOT_LOADED]
        _, body = determine_health_status(reasons, strict=True)
        parsed = json.loads(body)
        assert parsed["reasons"] == [REASON_MUSICCOG_NOT_LOADED]

    def test_ok_body_is_exact_literal(self):
        """Healthy path returns exactly the expected compact JSON literal."""
        _, body = determine_health_status([], strict=True)
        assert body == '{"status":"ok"}'

    def test_returns_tuple_of_two(self):
        result = determine_health_status([], strict=True)
        assert len(result) == 2

    def test_degraded_strict_status_is_int_503(self):
        status, _ = determine_health_status([REASON_DB_UNREACHABLE], strict=True)
        assert isinstance(status, int)
        assert status == 503

    def test_ok_status_is_int_200(self):
        status, _ = determine_health_status([], strict=True)
        assert isinstance(status, int)
        assert status == 200


# ---------------------------------------------------------------------------
# TestAssembleDegradedReasons
# ---------------------------------------------------------------------------


class TestAssembleDegradedReasons:
    def _healthy(self, **overrides) -> dict:
        """Return keyword args representing a fully healthy bot state."""
        base = dict(
            pool_present=True,
            db_ok=True,
            gateway_ready=True,
            ready_done=True,
            musiccog_loaded=True,
        )
        base.update(overrides)
        return base

    # --- Fully healthy → empty list ---

    def test_fully_healthy_returns_empty(self):
        result = assemble_degraded_reasons(**self._healthy())
        assert result == []

    # --- Individual critical reasons (D-05 scar #3 / D-03 branch coverage) ---

    def test_each_critical_reason_assembled(self):
        """Each isolated failure produces the correct reason string."""
        # pool missing
        result = assemble_degraded_reasons(**self._healthy(pool_present=False, db_ok=False))
        assert REASON_POOL_MISSING in result

        # db unreachable (pool present but probe failed)
        result = assemble_degraded_reasons(**self._healthy(db_ok=False))
        assert REASON_DB_UNREACHABLE in result

        # gateway not ready
        result = assemble_degraded_reasons(**self._healthy(gateway_ready=False))
        assert REASON_GATEWAY_NOT_READY in result

        # MusicCog not loaded (after ready)
        result = assemble_degraded_reasons(**self._healthy(musiccog_loaded=False))
        assert REASON_MUSICCOG_NOT_LOADED in result

    def test_pool_missing_emits_pool_reason(self):
        result = assemble_degraded_reasons(**self._healthy(pool_present=False, db_ok=False))
        assert result == [REASON_POOL_MISSING]

    def test_pool_present_db_unreachable_emits_db_reason(self):
        result = assemble_degraded_reasons(**self._healthy(db_ok=False))
        assert result == [REASON_DB_UNREACHABLE]

    def test_pool_missing_does_not_also_emit_db_unreachable(self):
        """Pool-missing and db-unreachable are mutually exclusive (if/elif mirror)."""
        result = assemble_degraded_reasons(**self._healthy(pool_present=False, db_ok=False))
        assert REASON_DB_UNREACHABLE not in result
        assert REASON_POOL_MISSING in result

    def test_gateway_not_ready_emits_gateway_reason(self):
        result = assemble_degraded_reasons(**self._healthy(gateway_ready=False))
        assert result == [REASON_GATEWAY_NOT_READY]

    def test_musiccog_not_loaded_after_ready_emits_musiccog_reason(self):
        result = assemble_degraded_reasons(**self._healthy(musiccog_loaded=False))
        assert result == [REASON_MUSICCOG_NOT_LOADED]

    def test_musiccog_not_loaded_before_ready_suppressed(self):
        """MusicCog reason must NOT fire before _ready_done (Pitfall 3 / REL-01 guard)."""
        result = assemble_degraded_reasons(**self._healthy(ready_done=False, musiccog_loaded=False))
        assert REASON_MUSICCOG_NOT_LOADED not in result
        assert result == []

    def test_multiple_failures_all_appear(self):
        """Independent failures are all reported simultaneously."""
        result = assemble_degraded_reasons(
            pool_present=True,
            db_ok=False,
            gateway_ready=False,
            ready_done=True,
            musiccog_loaded=False,
        )
        assert REASON_DB_UNREACHABLE in result
        assert REASON_GATEWAY_NOT_READY in result
        assert REASON_MUSICCOG_NOT_LOADED in result

    def test_reason_order_preserved(self):
        """Reasons appear in the canonical order: pool/db → gateway → musiccog."""
        result = assemble_degraded_reasons(
            pool_present=True,
            db_ok=False,
            gateway_ready=False,
            ready_done=True,
            musiccog_loaded=False,
        )
        assert result.index(REASON_DB_UNREACHABLE) < result.index(REASON_GATEWAY_NOT_READY)
        assert result.index(REASON_GATEWAY_NOT_READY) < result.index(REASON_MUSICCOG_NOT_LOADED)

    def test_ready_done_false_with_all_else_healthy_returns_empty(self):
        """ready_done=False suppresses the MusicCog check but other gates still run."""
        result = assemble_degraded_reasons(**self._healthy(ready_done=False))
        assert result == []

    def test_pool_missing_and_gateway_both_reported(self):
        """Pool-missing and gateway-not-ready can occur simultaneously."""
        result = assemble_degraded_reasons(**self._healthy(pool_present=False, db_ok=False, gateway_ready=False))
        assert REASON_POOL_MISSING in result
        assert REASON_GATEWAY_NOT_READY in result

    def test_returns_list(self):
        result = assemble_degraded_reasons(**self._healthy())
        assert isinstance(result, list)
