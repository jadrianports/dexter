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

Stubs to be wired in 11-03 / 11-04:
  - test_insert_and_search_memories: insert a row with a dummy vector(768),
    confirm cosine-similarity search returns it above the floor
  - test_bump_hit_and_surface: insert a memory, bump hit_count + surface_count,
    verify DB reflects the update
  - test_evict_lowest_salience: insert rows above MEMORY_MAX_PER_USER, confirm
    the lowest-salience row is evicted
  - test_delete_expired: insert a row with expires_at in the past, run
    delete_expired_memories, confirm it is gone
"""

from __future__ import annotations

import os

import pytest


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
# Phase 11 schema tests (wire helpers from database.py in 11-03)
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
# Placeholder stubs — to be filled in by plans 11-03 / 11-04
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Stub — wired in 11-03 once insert_memory / search_memories land")
@pytest.mark.asyncio
async def test_insert_and_search_memories(pool) -> None:
    """Insert a memory with a dummy vector and retrieve it via cosine search."""
    raise NotImplementedError("Stub — implement in 11-03")


@pytest.mark.skip(reason="Stub — wired in 11-04 once bump_memory_hit / bump_surfaced land")
@pytest.mark.asyncio
async def test_bump_hit_and_surface(pool) -> None:
    """Verify hit_count and surface_count increments persist correctly."""
    raise NotImplementedError("Stub — implement in 11-04")


@pytest.mark.skip(reason="Stub — wired in 11-04 once evict_lowest_salience lands")
@pytest.mark.asyncio
async def test_evict_lowest_salience(pool) -> None:
    """Insert rows exceeding MEMORY_MAX_PER_USER; confirm LFS eviction fires."""
    raise NotImplementedError("Stub — implement in 11-04")


@pytest.mark.skip(reason="Stub — wired in 11-04 once delete_expired_memories lands")
@pytest.mark.asyncio
async def test_delete_expired(pool) -> None:
    """Insert a row with past expires_at; confirm sweep removes it."""
    raise NotImplementedError("Stub — implement in 11-04")
