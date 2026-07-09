"""Phase 16 Proactive Memory Callbacks — database.py tests for the opt-out store.

Covers PROACT-02 (`get_proactive_opt_out` / `set_proactive_opt_out`):
  - Static source-inspection checks (no live DB needed) locking the SQL shape,
    single-identity-parameter signatures, and the structural independence
    from the `user_memories` (RAG) store.
  - Live-DB integration tests proving the round-trip (including the
    zero-prior-history Pitfall 3 case) and the two-way independence from
    `/memory forget` (`delete_all_user_memories`).

Set TEST_DATABASE_URL to a pgvector-enabled database before running the live
tests. The default `postgresql://dexter:dexter@localhost:5432/dexter_test` is
treated as "no live DB configured" — the live tests skip automatically.

Autonomous gate (no live DB needed): pytest --collect-only exits 0.
Full integration run: pytest tests/test_database_phase16.py -x (requires a
pgvector-enabled PostgreSQL, e.g. Neon or a local PG 16 + pgvector install).
"""

from __future__ import annotations

import inspect
import os

import pytest

import database

# ---------------------------------------------------------------------------
# Skip guard — mirrors test_database_phase15.py convention
# ---------------------------------------------------------------------------

_LOCAL_DEFAULT = "postgresql://dexter:dexter@localhost:5432/dexter_test"
_TEST_DSN = os.getenv("TEST_DATABASE_URL", _LOCAL_DEFAULT)
_SKIP_LIVE = _TEST_DSN == _LOCAL_DEFAULT

_skip_reason = (
    "Live pgvector DB not configured — set TEST_DATABASE_URL to a "
    "pgvector-enabled Postgres (e.g. Neon) to run Phase 16 integration tests"
)


# ---------------------------------------------------------------------------
# Static source-inspection checks — always run, no live DB needed (16-02 Task 2)
# ---------------------------------------------------------------------------


class TestPhase16OptOutHelpers:
    """Verify the two new proactive-callback opt-out helpers exist with locked shapes."""

    def test_opt_out_helpers_exist(self) -> None:
        assert hasattr(database, "set_proactive_opt_out"), "set_proactive_opt_out must exist in database.py (PROACT-02)"
        assert hasattr(database, "get_proactive_opt_out"), "get_proactive_opt_out must exist in database.py (PROACT-02)"

    def test_set_proactive_opt_out_single_identity_param(self) -> None:
        """Structural guard: signature must be exactly (pool, user_id, opted_out).

        A future edit that adds a second identity parameter (e.g. an
        accidental `target_id`) fails this test immediately, before it can
        ever reach a cross-user opt-out bug (V4 / T-16-01).
        """
        params = list(inspect.signature(database.set_proactive_opt_out).parameters)
        assert params == ["pool", "user_id", "opted_out"], (
            f"set_proactive_opt_out must accept exactly "
            f"['pool', 'user_id', 'opted_out'] — no second identity "
            f"parameter, ever; got {params}"
        )

    def test_get_proactive_opt_out_single_identity_param(self) -> None:
        """Structural guard: signature must be exactly (pool, user_id)."""
        params = list(inspect.signature(database.get_proactive_opt_out).parameters)
        assert params == ["pool", "user_id"], (
            f"get_proactive_opt_out must accept exactly ['pool', 'user_id'] "
            f"— no second identity parameter, ever; got {params}"
        )

    def test_opt_out_scope(self) -> None:
        """Both helpers must touch only user_profiles, never user_memories.

        The structural proof of independence from `/memory forget`
        (T-16-01 boundary: opt-out store vs. memory store).
        """
        set_src = inspect.getsource(database.set_proactive_opt_out)
        get_src = inspect.getsource(database.get_proactive_opt_out)
        assert "user_memories" not in set_src, "set_proactive_opt_out must never reference user_memories"
        assert "user_memories" not in get_src, "get_proactive_opt_out must never reference user_memories"
        assert "user_profiles" in set_src, "set_proactive_opt_out must reference user_profiles"
        assert "user_profiles" in get_src, "get_proactive_opt_out must reference user_profiles"

    def test_set_proactive_opt_out_is_upsert(self) -> None:
        """Pitfall 3 / T-16-06 guard: must be an upsert, never a bare UPDATE."""
        src = inspect.getsource(database.set_proactive_opt_out)
        assert "ON CONFLICT (user_id) DO UPDATE" in src, (
            "set_proactive_opt_out must use INSERT ... ON CONFLICT (user_id) "
            "DO UPDATE — a bare UPDATE silently no-ops for a user with no "
            "prior user_profiles row (Pitfall 3)"
        )


# ---------------------------------------------------------------------------
# Live-DB integration tests (16-02 Task 2)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_opt_out_roundtrip(pool) -> None:
    """Round-trip proof, including the zero-prior-history Pitfall 3 case.

    A fresh user id with NO prior user_profiles row must still persist the
    opt-out flag via the upsert (not silently no-op).
    """
    user_id = "test-phase16-roundtrip"

    # No prior row at all — default is opted-in (False).
    assert await database.get_proactive_opt_out(pool, user_id) is False

    # Opt out for a user with zero prior song_history / profile row.
    await database.set_proactive_opt_out(pool, user_id=user_id, opted_out=True)
    assert await database.get_proactive_opt_out(pool, user_id) is True

    # Opt back in.
    await database.set_proactive_opt_out(pool, user_id=user_id, opted_out=False)
    assert await database.get_proactive_opt_out(pool, user_id) is False


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_zero_memories_touched(pool) -> None:
    """Two-way independence proof between the opt-out flag and `/memory forget`.

    1. Opting out/in never deletes or alters any user_memories row.
    2. delete_all_user_memories (the /memory forget hard-delete) never
       flips the opt-out flag.
    """
    from datetime import datetime, timedelta, timezone

    import config

    user_id = "test-phase16-independence"
    embedding = [0.4] * config.EMBED_DIM
    expires_at = datetime.now(timezone.utc) + timedelta(days=90)

    await database.insert_memory(
        pool,
        user_id=user_id,
        guild_id=None,
        kind="daily_batch",
        fact="user opted out of proactive callbacks once, on principle",
        embedding=embedding,
        salience=0.3,
        expires_at=expires_at,
    )

    # Opt-out flips the flag but must not touch the memory row.
    await database.set_proactive_opt_out(pool, user_id=user_id, opted_out=True)
    still_there = await database.search_memories(pool, user_id=user_id, query_embedding=embedding, k=5)
    assert len(still_there) == 1, "set_proactive_opt_out(opted_out=True) must not delete memory rows"

    await database.set_proactive_opt_out(pool, user_id=user_id, opted_out=False)
    still_there_2 = await database.search_memories(pool, user_id=user_id, query_embedding=embedding, k=5)
    assert len(still_there_2) == 1, "set_proactive_opt_out(opted_out=False) must not delete memory rows"

    # Now set opted_out=True and confirm /memory forget doesn't flip it back.
    await database.set_proactive_opt_out(pool, user_id=user_id, opted_out=True)
    assert await database.get_proactive_opt_out(pool, user_id) is True

    deleted = await database.delete_all_user_memories(pool, user_id)
    assert deleted == 1

    assert await database.get_proactive_opt_out(pool, user_id) is True, (
        "delete_all_user_memories (/memory forget) must never flip proactive_opt_out — the two controls are independent"
    )
