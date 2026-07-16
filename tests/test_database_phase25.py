"""Phase 25 PostgreSQL integration tests — MEM-06 expiry reinforcement.

These tests require a live PostgreSQL instance with the pgvector extension
enabled (same requirement as tests/test_database_phase11.py). Set
TEST_DATABASE_URL to a pgvector-enabled database before running. The default
`postgresql://dexter:dexter@localhost:5432/dexter_test` is treated as "no
live DB configured" — live-DB tests skip automatically.

Autonomous gate (no live DB needed): TestReinforceMemoryExpiryExists runs
everywhere via source-inspection (mirrors tests/test_database_phase11.py's
TestWriteHelpersExist pattern).

Phase 25 write helper (25-01):
  - TestReinforceMemoryExpiryExists: signature/source-inspection, no live DB
  - test_reinforced_fact_survives_sweep_unreinforced_does_not: SC-1 live round-trip
  - test_recall_does_not_mutate_salience_or_hit_count: SC-3 byte-identical guard
"""

from __future__ import annotations

import inspect
import os
from datetime import datetime, timedelta, timezone

import pytest

import database

# ---------------------------------------------------------------------------
# Skip guard — mirrors tests/test_database_phase11.py convention
# ---------------------------------------------------------------------------

_LOCAL_DEFAULT = "postgresql://dexter:dexter@localhost:5432/dexter_test"
_TEST_DSN = os.getenv("TEST_DATABASE_URL", _LOCAL_DEFAULT)
_SKIP_LIVE = os.getenv("TEST_DATABASE_URL") is None

_skip_reason = (
    "Live pgvector DB not configured — set TEST_DATABASE_URL to run Phase 25 "
    "integration tests (e.g. a pgvector-enabled Postgres such as Neon)"
)


# ---------------------------------------------------------------------------
# Static write-helper checks — always run, no live DB needed (25-01 Task 1)
# ---------------------------------------------------------------------------


class TestReinforceMemoryExpiryExists:
    """Verify reinforce_memory_expiry exists, is parameterized, and is extend-only."""

    def test_reinforce_memory_expiry_exists(self) -> None:
        assert hasattr(database, "reinforce_memory_expiry"), (
            "reinforce_memory_expiry must exist in database.py"
        )

    def test_reinforce_memory_expiry_signature(self) -> None:
        sig = inspect.signature(database.reinforce_memory_expiry)
        params = list(sig.parameters)
        assert params == ["pool", "ids", "expires_at"], (
            f"reinforce_memory_expiry must have signature (pool, ids, expires_at), got {params}"
        )

    def test_reinforce_memory_expiry_uses_any_binding(self) -> None:
        src = inspect.getsource(database.reinforce_memory_expiry)
        assert "ANY($1)" in src, "reinforce_memory_expiry must bind ids via ANY($1) array binding"

    def test_reinforce_memory_expiry_uses_greatest(self) -> None:
        src = inspect.getsource(database.reinforce_memory_expiry)
        assert "GREATEST(expires_at, $2)" in src, (
            "reinforce_memory_expiry must use GREATEST(expires_at, $2) — extend-only, never shorten"
        )

    def test_reinforce_memory_expiry_never_computes_datetime_in_sql(self) -> None:
        src = inspect.getsource(database.reinforce_memory_expiry)
        assert "interval" not in src, (
            "reinforce_memory_expiry must never compute expires_at in SQL (e.g. now() + interval) — "
            "the caller computes the datetime in Python and passes it as $2"
        )


# ---------------------------------------------------------------------------
# Live-DB round-trip tests (25-01 Task 3)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_reinforced_fact_survives_sweep_unreinforced_does_not(pool) -> None:
    """SC-1: a reinforced sweep-eligible fact survives the daily sweep while an
    equally-old, unreinforced sweep-eligible fact does not.

    Uses a sweep-eligible kind (salience < MEMORY_DECAY_SALIENCE_FLOOR = 0.5) —
    NEVER milestone (Pitfall 1: a milestone-kind test would pass vacuously,
    since high-salience rows are never swept regardless of expires_at).
    """
    import config

    user_id = "test-phase25-sc1-sweep"
    embedding = [0.5] * config.EMBED_DIM
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=1)  # already expired

    # Two equal-age, sweep-eligible (daily_batch, salience 0.2) facts, both
    # already past their expiry horizon.
    id_reinforced = await database.insert_memory(
        pool,
        user_id=user_id,
        guild_id=None,
        kind="daily_batch",
        fact="the reinforced fact — kept getting surfaced",
        embedding=embedding,
        salience=0.2,
        expires_at=past,
    )
    id_unreinforced = await database.insert_memory(
        pool,
        user_id=user_id,
        guild_id=None,
        kind="daily_batch",
        fact="the unreinforced fact — never surfaced again",
        embedding=embedding,
        salience=0.2,
        expires_at=past,
    )

    # Simulate recall() step 7b surfacing exactly one of the two facts:
    # push its expires_at out into the future.
    await database.reinforce_memory_expiry(pool, [id_reinforced], now + timedelta(days=30))

    # Run the daily sweep referenced at `now`.
    await database.delete_expired_memories(pool, now=now)

    async with pool.acquire() as conn:
        row_reinforced = await conn.fetchrow(
            "SELECT id FROM user_memories WHERE id = $1", id_reinforced
        )
        row_unreinforced = await conn.fetchrow(
            "SELECT id FROM user_memories WHERE id = $1", id_unreinforced
        )

    assert row_reinforced is not None, (
        "The reinforced fact must survive the sweep (its expires_at was pushed out)"
    )
    assert row_unreinforced is None, (
        "The unreinforced, equally-old fact must be swept (its expires_at stayed in the past)"
    )


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_recall_does_not_mutate_salience_or_hit_count(pool) -> None:
    """SC-3: surfacing a fact (bump_surfaced + reinforce_memory_expiry, the two
    recall() step-7 calls) never mutates salience, hit_count, or last_seen_at —
    only expires_at/last_surfaced_at/surface_count may change.

    Uses a high-salience kind (milestone, salience >= 0.5) so the byte-identical
    guarantee is exercised on a fact type every other subsystem keys on.
    """
    import config

    user_id = "test-phase25-sc3-no-mutate"
    embedding = [0.6] * config.EMBED_DIM
    expires_at = datetime.now(timezone.utc) + timedelta(days=90)

    memory_id = await database.insert_memory(
        pool,
        user_id=user_id,
        guild_id=None,
        kind="milestone",
        fact="hit 500 songs queued",
        embedding=embedding,
        salience=1.0,
        expires_at=expires_at,
    )

    async with pool.acquire() as conn:
        before = await conn.fetchrow(
            "SELECT salience, hit_count, last_seen_at FROM user_memories WHERE id = $1",
            memory_id,
        )

    # The two recall() step-7 calls, in order (7a then 7b).
    await database.bump_surfaced(pool, [memory_id])
    await database.reinforce_memory_expiry(
        pool, [memory_id], datetime.now(timezone.utc) + timedelta(days=90)
    )

    async with pool.acquire() as conn:
        after = await conn.fetchrow(
            "SELECT salience, hit_count, last_seen_at, expires_at, last_surfaced_at, surface_count"
            " FROM user_memories WHERE id = $1",
            memory_id,
        )

    assert float(after["salience"]) == float(before["salience"]), (
        "salience must be byte-identical after surfacing (D-01 expiry-only restraint)"
    )
    assert after["hit_count"] == before["hit_count"], (
        "hit_count must be byte-identical after surfacing — recall() never bumps it"
    )
    assert after["last_seen_at"] == before["last_seen_at"], (
        "last_seen_at must be byte-identical after surfacing — recall() never touches it"
    )
    # Fields that ARE expected to change on surface:
    assert after["last_surfaced_at"] is not None, "last_surfaced_at must be set by bump_surfaced"
    assert after["surface_count"] == 1, "surface_count must increment by bump_surfaced"
