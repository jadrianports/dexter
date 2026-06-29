"""Phase 11 PostgreSQL integration tests — pgvector + user_memories table.

These tests require a live PostgreSQL instance with the pgvector extension
enabled (run `CREATE EXTENSION IF NOT EXISTS vector;` once per database, or
use a Neon DB where the extension is available).

Set TEST_DATABASE_URL to a pgvector-enabled database before running. The
default `postgresql://dexter:dexter@localhost:5432/dexter_test` is treated
as "no live DB configured" — tests skip automatically.

Autonomous gate (no live DB needed): pytest --collect-only exits 0.
Full integration run: pytest tests/test_database_phase11.py -x (requires
a pgvector-enabled PostgreSQL, e.g. Neon or a local PG 16 + pgvector install).

Phase 11 write helpers (11-04):
  - test_insert_and_search_memories: insert + cosine search round-trip
  - test_bump_hit_and_surface: bump_memory_hit / bump_surfaced verify DB update
  - test_evict_lowest_salience: cap-exceeded → lowest-salience row deleted (T-11-04c)
  - test_delete_expired: stub for 11-07 sweep helper
"""

from __future__ import annotations

import inspect
import os

import pytest

import database


# ---------------------------------------------------------------------------
# Skip guard — mirrors test_database_phase4.py convention
# ---------------------------------------------------------------------------

_LOCAL_DEFAULT = "postgresql://dexter:dexter@localhost:5432/dexter_test"
_TEST_DSN = os.getenv("TEST_DATABASE_URL", _LOCAL_DEFAULT)
_SKIP_LIVE = _TEST_DSN == _LOCAL_DEFAULT

_skip_reason = (
    "Live pgvector DB not configured — set TEST_DATABASE_URL to a "
    "pgvector-enabled Postgres (e.g. Neon) to run Phase 11 integration tests"
)


# ---------------------------------------------------------------------------
# Static write-helper checks — always run, no live DB needed (11-04 Task 2)
# ---------------------------------------------------------------------------


class TestWriteHelpersExist:
    """Verify all Task 2 artifacts exist with the right signatures (T-11-04a,b,c,d)."""

    def test_insert_memory_exists(self) -> None:
        assert hasattr(database, "insert_memory"), "insert_memory must exist in database.py"

    def test_bump_memory_hit_exists(self) -> None:
        assert hasattr(database, "bump_memory_hit"), "bump_memory_hit must exist in database.py"

    def test_count_user_memories_exists(self) -> None:
        assert hasattr(database, "count_user_memories"), "count_user_memories must exist"

    def test_evict_lowest_salience_exists(self) -> None:
        assert hasattr(database, "evict_lowest_salience"), "evict_lowest_salience must exist"

    def test_get_user_memories_for_eviction_exists(self) -> None:
        assert hasattr(database, "get_user_memories_for_eviction"), (
            "get_user_memories_for_eviction must exist (needed by MemoryService.remember)"
        )

    def test_insert_memory_has_returning_id(self) -> None:
        """insert_memory must use RETURNING id so the caller gets the new row id."""
        src = inspect.getsource(database.insert_memory)
        assert "RETURNING id" in src, (
            "insert_memory must include RETURNING id in the INSERT statement"
        )

    def test_evict_lowest_salience_is_user_scoped(self) -> None:
        """evict_lowest_salience must include user_id = $1 guard (T-11-04c)."""
        src = inspect.getsource(database.evict_lowest_salience)
        assert "user_id" in src, (
            "evict_lowest_salience must filter by user_id (T-11-04c cross-user guard)"
        )

    def test_evict_lowest_salience_uses_any_binding(self) -> None:
        """ids must be bound via ANY($N) array binding — never string-interpolated."""
        src = inspect.getsource(database.evict_lowest_salience)
        assert "ANY($" in src, (
            "evict_lowest_salience must use ANY($N) for the ids list (T-11-04b)"
        )

    def test_bump_memory_hit_updates_hit_count(self) -> None:
        """bump_memory_hit SQL must increment hit_count."""
        src = inspect.getsource(database.bump_memory_hit)
        assert "hit_count" in src, "bump_memory_hit must update hit_count"

    def test_bump_memory_hit_updates_last_seen_at(self) -> None:
        """bump_memory_hit SQL must refresh last_seen_at."""
        src = inspect.getsource(database.bump_memory_hit)
        assert "last_seen_at" in src, "bump_memory_hit must update last_seen_at"

    def test_count_user_memories_scoped_to_user(self) -> None:
        """count_user_memories must scope COUNT to user_id."""
        src = inspect.getsource(database.count_user_memories)
        assert "user_id" in src, "count_user_memories must filter by user_id"


# ---------------------------------------------------------------------------
# Phase 11 schema tests (wired in 11-01)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_user_memories_table_exists(pool) -> None:
    """user_memories table must exist after init_db (MEM-01 schema gate).

    Wired by 11-01 (schema DDL); confirmed here as the first live-DB check.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            " AND tablename = 'user_memories'"
        )
    assert rows, "user_memories table not found — init_db may not have run the Phase 11 DDL"


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_vector_extension_active(pool) -> None:
    """pgvector extension must be installed in the public schema.

    The extension-first boot ordering (T-11-01) runs CREATE EXTENSION before
    create_pool so this check confirms the ordering worked on a live DB.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT extname FROM pg_extension WHERE extname = 'vector'"
        )
    assert row is not None, (
        "pgvector extension not active — run `CREATE EXTENSION IF NOT EXISTS vector;`"
        " in the target database or use a Neon DB (pgvector pre-installed)"
    )


# ---------------------------------------------------------------------------
# Phase 11 write helper round-trip tests (11-04 stubs filled in)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_insert_and_search_memories(pool) -> None:
    """Insert a memory with a dummy vector and retrieve it via cosine search.

    Full insert → search_memories round-trip:
    - insert_memory adds a row with a known 768d embedding
    - search_memories with the same embedding returns the row with similarity≈1.0
    - The returned row's fact field matches what was inserted
    """
    from datetime import datetime, timezone, timedelta
    import config

    user_id = "test-phase11-insert-search"
    embedding = [0.1] * config.EMBED_DIM
    expires_at = datetime.now(timezone.utc) + timedelta(days=90)

    memory_id = await database.insert_memory(
        pool,
        user_id=user_id,
        guild_id=None,
        kind="daily_batch",
        fact="user likes lo-fi hip hop",
        embedding=embedding,
        salience=0.3,
        expires_at=expires_at,
    )
    assert isinstance(memory_id, int) and memory_id > 0

    # Search with the same vector — should get similarity ≈ 1.0
    rows = await database.search_memories(
        pool, user_id=user_id, query_embedding=embedding, k=5
    )
    assert len(rows) == 1
    assert rows[0]["fact"] == "user likes lo-fi hip hop"
    assert float(rows[0]["similarity"]) > 0.99


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_bump_hit_and_surface(pool) -> None:
    """Verify hit_count increments and surface_count updates persist correctly.

    - bump_memory_hit increments hit_count + salience nudge
    - bump_surfaced increments surface_count + sets last_surfaced_at
    """
    from datetime import datetime, timezone, timedelta
    import config

    user_id = "test-phase11-bump"
    embedding = [0.2] * config.EMBED_DIM
    expires_at = datetime.now(timezone.utc) + timedelta(days=90)

    memory_id = await database.insert_memory(
        pool,
        user_id=user_id,
        guild_id=None,
        kind="repeat_song",
        fact="queued blinding lights 3 times today",
        embedding=embedding,
        salience=0.5,
        expires_at=expires_at,
    )

    # bump_memory_hit: increments hit_count (started at 1) + salience nudge
    await database.bump_memory_hit(pool, memory_id)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT hit_count, salience FROM user_memories WHERE id = $1",
            memory_id,
        )
    assert row["hit_count"] == 2, "hit_count must be 2 after one bump (initial value is 1)"
    assert float(row["salience"]) > 0.5, "salience must nudge up on bump (D-07)"

    # bump_surfaced: increments surface_count + sets last_surfaced_at
    await database.bump_surfaced(pool, [memory_id])

    async with pool.acquire() as conn:
        row2 = await conn.fetchrow(
            "SELECT surface_count, last_surfaced_at FROM user_memories WHERE id = $1",
            memory_id,
        )
    assert row2["surface_count"] == 1, "surface_count must be 1 after first bump_surfaced"
    assert row2["last_surfaced_at"] is not None, "last_surfaced_at must be set after bump_surfaced"


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_evict_lowest_salience(pool) -> None:
    """Insert → count → evict round-trip: lowest-salience row deleted (T-11-04a/c).

    Verifies:
    1. count_user_memories returns correct count after inserts
    2. evict_lowest_salience deletes only the specified ids (user-scoped)
    3. Cross-user protection (T-11-04c): ids from another user are silently ignored
    """
    from datetime import datetime, timezone, timedelta
    import config

    user_id = "test-phase11-evict-cap"
    other_user = "test-phase11-evict-cap-other"
    embedding = [0.3] * config.EMBED_DIM
    expires_at = datetime.now(timezone.utc) + timedelta(days=90)

    # Insert two rows for user_id
    id_low = await database.insert_memory(
        pool, user_id=user_id, guild_id=None, kind="daily_batch",
        fact="low salience fact", embedding=embedding, salience=0.1, expires_at=expires_at,
    )
    id_high = await database.insert_memory(
        pool, user_id=user_id, guild_id=None, kind="milestone",
        fact="high salience fact", embedding=embedding, salience=0.9, expires_at=expires_at,
    )

    # Insert one row for other_user
    id_other = await database.insert_memory(
        pool, user_id=other_user, guild_id=None, kind="daily_batch",
        fact="other user fact", embedding=embedding, salience=0.1, expires_at=expires_at,
    )

    count_before = await database.count_user_memories(pool, user_id)
    assert count_before == 2, f"Expected 2 memories, got {count_before}"

    # Evict id_low + pass id_other (cross-user id) — only id_low must be deleted
    await database.evict_lowest_salience(pool, user_id=user_id, ids=[id_low, id_other])

    count_after = await database.count_user_memories(pool, user_id)
    count_other = await database.count_user_memories(pool, other_user)

    assert count_after == 1, "Only id_low should be evicted; id_high must survive"
    assert count_other == 1, "id_other must NOT be deleted (T-11-04c cross-user guard)"


@pytest.mark.skip(reason="Stub — wired in 11-07 once delete_expired_memories sweep lands")
@pytest.mark.asyncio
async def test_delete_expired(pool) -> None:
    """Insert a row with past expires_at; confirm sweep removes it."""
    raise NotImplementedError("Stub — implement in 11-07")
