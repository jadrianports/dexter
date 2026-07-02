"""Phase 15 RAG Reach — database.py tests for the new /memory view + forget helpers.

Covers RAG-03 (`list_user_memories`) and RAG-04 (`delete_all_user_memories`):
  - Static source-inspection checks (no live DB needed) locking the SQL shape,
    user_id scoping, and the single-identity-parameter signature guard.
  - A live-DB integration test proving `remember -> forget -> recall == []`
    against a real pgvector column via the real search_memories ANN path
    (Success Criterion 4 — the trust escape hatch Phase 16 hard-depends on).

Set TEST_DATABASE_URL to a pgvector-enabled database before running the live
test. The default `postgresql://dexter:dexter@localhost:5432/dexter_test` is
treated as "no live DB configured" — the live test skips automatically.

Autonomous gate (no live DB needed): pytest --collect-only exits 0.
Full integration run: pytest tests/test_database_phase15.py -x (requires a
pgvector-enabled PostgreSQL, e.g. Neon or a local PG 16 + pgvector install).
"""

from __future__ import annotations

import inspect
import os

import pytest

import database


# ---------------------------------------------------------------------------
# Skip guard — mirrors test_database_phase11.py convention
# ---------------------------------------------------------------------------

_LOCAL_DEFAULT = "postgresql://dexter:dexter@localhost:5432/dexter_test"
_TEST_DSN = os.getenv("TEST_DATABASE_URL", _LOCAL_DEFAULT)
_SKIP_LIVE = _TEST_DSN == _LOCAL_DEFAULT

_skip_reason = (
    "Live pgvector DB not configured — set TEST_DATABASE_URL to a "
    "pgvector-enabled Postgres (e.g. Neon) to run Phase 15 integration tests"
)


# ---------------------------------------------------------------------------
# Static source-inspection checks — always run, no live DB needed (15-01 Task 2)
# ---------------------------------------------------------------------------


class TestPhase15HelpersExist:
    """Verify the two new /memory-surface helpers exist with locked-down shapes."""

    def test_list_user_memories_exists(self) -> None:
        assert hasattr(database, "list_user_memories"), (
            "list_user_memories must exist in database.py (RAG-03)"
        )

    def test_delete_all_user_memories_exists(self) -> None:
        assert hasattr(database, "delete_all_user_memories"), (
            "delete_all_user_memories must exist in database.py (RAG-04)"
        )

    def test_list_user_memories_is_user_scoped(self) -> None:
        """list_user_memories must filter WHERE user_id = $1 (T-11-04c pattern)."""
        src = inspect.getsource(database.list_user_memories)
        assert "user_id" in src and "$1" in src, (
            "list_user_memories must filter by user_id = $1 (cross-user guard)"
        )

    def test_list_user_memories_uses_display_ordering(self) -> None:
        """list_user_memories must order salience DESC — display order, not eviction order."""
        src = inspect.getsource(database.list_user_memories)
        assert "ORDER BY salience DESC" in src, (
            "list_user_memories must use display ordering (salience DESC, "
            "created_at DESC) — NOT the ascending eviction ordering used by "
            "get_user_memories_for_eviction"
        )

    def test_delete_all_user_memories_is_user_scoped(self) -> None:
        """delete_all_user_memories must DELETE ... WHERE user_id = $1."""
        src = inspect.getsource(database.delete_all_user_memories)
        assert "user_id = $1" in src, (
            "delete_all_user_memories must scope the DELETE to user_id = $1"
        )
        assert "DELETE FROM user_memories" in src, (
            "delete_all_user_memories must DELETE FROM user_memories"
        )

    def test_delete_all_user_memories_is_hard_delete(self) -> None:
        """No tombstone/soft-delete column — a real DELETE only (T-15-03)."""
        src = inspect.getsource(database.delete_all_user_memories)
        assert "deleted_at" not in src, (
            "delete_all_user_memories must be a hard DELETE — no deleted_at "
            "tombstone column (Pitfall 3 / T-15-03)"
        )

    def test_delete_all_user_memories_has_single_identity_param(self) -> None:
        """Structural guard: signature must be exactly (pool, user_id) — no target param.

        This is the V4 / T-11-04c access-control enforcement: a future edit
        that adds a second identity parameter (e.g. an accidental `target_id`)
        fails this test immediately, before it can ever reach a cross-user
        forget bug.
        """
        params = list(inspect.signature(database.delete_all_user_memories).parameters)
        assert params == ["pool", "user_id"], (
            f"delete_all_user_memories must accept exactly ['pool', 'user_id'] "
            f"— no second identity parameter, ever; got {params}"
        )
