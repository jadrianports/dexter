"""Phase 21 Plan 02 — database.py tests for purge_guild_data + guild-scoped search.

Covers MEM-04 (`purge_guild_data`) and a live-DB proof of MEM-03/MEM-01's plan
21-01 guild-scoped `search_memories` filter:
  - Static source-inspection checks (no live DB needed) locking the four-table
    DELETE list and the hard invariant that the abuse-mitigation blocklist
    table is structurally unreachable from purge_guild_data (T-21-03).
  - Live-DB integration tests proving: a blocklist row for the purged guild
    survives (OWNER-04 / Phase 20 D-01); the four-table purge is guild-isolated
    (another guild's rows survive) and returns accurate per-table counts; a
    `user_memories` row with `guild_id IS NULL` survives (MEM-03 / D-01
    grandfather rule); and `search_memories(..., guild_id=...)` excludes
    another guild's rows while including NULL rows, against real pgvector
    Postgres.

Set TEST_DATABASE_URL to a pgvector-enabled database before running the live
tests. The default `postgresql://dexter:dexter@localhost:5432/dexter_test` is
treated as "no live DB configured" — the live tests skip automatically.

Autonomous gate (no live DB needed): pytest --collect-only exits 0.
Full integration run: pytest tests/test_database_phase21.py -x (requires a
pgvector-enabled PostgreSQL, e.g. Neon or a local PG 16 + pgvector install).
"""

from __future__ import annotations

import inspect
import os

import pytest

import config
import database

# ---------------------------------------------------------------------------
# Skip guard — mirrors test_database_phase20.py convention
# ---------------------------------------------------------------------------

_LOCAL_DEFAULT = "postgresql://dexter:dexter@localhost:5432/dexter_test"
_TEST_DSN = os.getenv("TEST_DATABASE_URL", _LOCAL_DEFAULT)
_SKIP_LIVE = os.getenv("TEST_DATABASE_URL") is None

_skip_reason = (
    "Live pgvector DB not configured — set TEST_DATABASE_URL to run Phase 21 "
    "integration tests (e.g. a pgvector-enabled Postgres such as Neon)"
)


# ---------------------------------------------------------------------------
# Static source-inspection checks — always run, no live DB needed (21-02 Task 1)
# ---------------------------------------------------------------------------


class TestPurgeGuildDataStructure:
    """Verify purge_guild_data exists with the locked four-table, no-blocklist shape."""

    def test_purge_guild_data_exists(self) -> None:
        assert hasattr(database, "purge_guild_data"), "purge_guild_data must exist in database.py (MEM-04)"

    def test_purge_guild_data_is_async(self) -> None:
        assert inspect.iscoroutinefunction(database.purge_guild_data), "purge_guild_data must be an async function"

    def test_purge_guild_data_never_touches_blocklist(self) -> None:
        """T-21-03: the abuse-mitigation blocklist table must be structurally unreachable."""
        src = inspect.getsource(database.purge_guild_data)
        assert "guild_blocklist" not in src, (
            "purge_guild_data source must NEVER contain 'guild_blocklist' — a blocked "
            "guild's block must outlive this purge (Phase 20 D-01 / OWNER-04)"
        )

    def test_purge_guild_data_deletes_exactly_four_tables(self) -> None:
        src = inspect.getsource(database.purge_guild_data)
        assert src.count("DELETE FROM") == 4, "purge_guild_data must issue exactly 4 DELETE FROM statements"
        for stmt in (
            "DELETE FROM guild_config WHERE guild_id = $1",
            "DELETE FROM guild_queues WHERE guild_id = $1",
            "DELETE FROM guild_jams WHERE guild_id = $1",
            "DELETE FROM user_memories WHERE guild_id = $1",
        ):
            assert stmt in src, f"purge_guild_data must contain the literal statement: {stmt}"

    def test_purge_guild_data_is_transactional(self) -> None:
        src = inspect.getsource(database.purge_guild_data)
        assert "conn.transaction()" in src, "purge_guild_data must run all four DELETEs inside one transaction"

    def test_purge_guild_data_not_dynamic(self) -> None:
        """T-21-03: no information_schema introspection, no table-name loop."""
        src = inspect.getsource(database.purge_guild_data)
        assert "information_schema" not in src, "purge_guild_data must not introspect information_schema"
        assert "for " not in src, "purge_guild_data must not loop over a table-name list"


# ---------------------------------------------------------------------------
# WR-02 (21-REVIEW.md) — lock the single wiring point tying the well-tested
# purge helper to a real guild departure. `database.purge_guild_data` itself
# is thoroughly covered above; nothing previously asserted that
# `bot.py::on_guild_remove` actually calls it. Source-inspection idiom
# mirrors tests/test_ambient_recall_cadence.py::TestGuildScopedOptIns and
# tests/test_autoqueue_wiring.py::TestGuildScopedTasteBlend — the
# established pattern for Discord-glue surfaces too heavy to drive
# behaviorally.
# ---------------------------------------------------------------------------


class TestOnGuildRemoveWiring:
    """A future edit that silently drops, comments out, or reorders past a
    `return` this call would otherwise pass the full test suite with zero
    warning — this is the highest-blast-radius new code path in the phase
    (an unconditional data purge on every guild departure)."""

    def _on_guild_remove_source(self) -> str:
        import bot as bot_module

        return inspect.getsource(bot_module.on_guild_remove)

    def test_on_guild_remove_calls_purge_guild_data(self) -> None:
        src = self._on_guild_remove_source()
        assert "purge_guild_data" in src, (
            "bot.py::on_guild_remove must call database.purge_guild_data (MEM-04) "
            "— a departed guild's data must not resurface on re-invite"
        )

    def test_on_guild_remove_purge_is_wrapped_in_try_except(self) -> None:
        """D-03 / WR-04 discipline: the purge is best-effort and must never crash
        guild removal — a failure logs a warning and is swallowed."""
        src = self._on_guild_remove_source()
        assert "try:" in src and "except Exception" in src, (
            "on_guild_remove's purge call must be wrapped in try/except Exception"
        )
        assert "log.warning" in src, "a failed purge must log a warning, not raise or silently vanish"


# ---------------------------------------------------------------------------
# Live-DB integration tests (21-02 Task 2)
# ---------------------------------------------------------------------------


async def _seed_guild_queue_row(pool, guild_id: str) -> None:
    """Insert a minimal guild_queues row for guild_id (mirrors queue_persistence.py::persist_queue)."""
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO guild_queues (guild_id, payload, updated_at)"
            " VALUES ($1, $2::jsonb, now())"
            " ON CONFLICT (guild_id)"
            " DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()",
            guild_id,
            "[]",
        )


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_purge_survives_blocklist(pool) -> None:
    """OWNER-04 / Phase 20 D-01: a blocklist row for the purged guild must survive.

    This is the highest-value test — the single test most likely to catch a
    future refactor that "helpfully" generalizes the purge to sweep the
    blocklist table too.
    """
    guild_id = "test-phase21-g1"

    await database.insert_blocklist(pool, guild_id=guild_id, reason="testing purge survival")
    await database.purge_guild_data(pool, guild_id=guild_id)

    rows = await database.load_blocklist(pool)
    assert guild_id in {r["guild_id"] for r in rows}, (
        "A guild_blocklist row for the purged guild must survive purge_guild_data "
        "(OWNER-04) — a kicked abuser's block must outlive the purge their own "
        "removal triggers"
    )

    # Clean up.
    await database.delete_blocklist(pool, guild_id=guild_id)


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_purge_four_tables_isolated_and_null_survives(pool) -> None:
    """Four-table purge + isolation: G1 purged, G2 survives, NULL memory survives."""
    g1 = "test-phase21-g2a"
    g2 = "test-phase21-g2b"
    user_id = "test-phase21-user"
    embedding = [0.1] * config.EMBED_DIM

    # Seed guild_config for both guilds.
    await database.insert_guild_config_if_absent(pool, guild_id=g1)
    await database.insert_guild_config_if_absent(pool, guild_id=g2)

    # Seed guild_queues for both guilds.
    await _seed_guild_queue_row(pool, g1)
    await _seed_guild_queue_row(pool, g2)

    # Seed guild_jams for both guilds.
    await database.save_jam(pool, guild_id=g1, name="jam1", snapshot=[{"title": "song"}])
    await database.save_jam(pool, guild_id=g2, name="jam1", snapshot=[{"title": "song"}])

    # Seed user_memories: one row for g1, one for g2, one with guild_id=None.
    from datetime import datetime, timedelta, timezone

    expires_at = datetime.now(timezone.utc) + timedelta(days=90)
    await database.insert_memory(
        pool,
        user_id=user_id,
        guild_id=g1,
        kind="daily_batch",
        fact="G1 fact",
        embedding=embedding,
        salience=0.5,
        expires_at=expires_at,
    )
    await database.insert_memory(
        pool,
        user_id=user_id,
        guild_id=g2,
        kind="daily_batch",
        fact="G2 fact",
        embedding=embedding,
        salience=0.5,
        expires_at=expires_at,
    )
    await database.insert_memory(
        pool,
        user_id=user_id,
        guild_id=None,
        kind="daily_batch",
        fact="NULL guild fact",
        embedding=embedding,
        salience=0.5,
        expires_at=expires_at,
    )

    counts = await database.purge_guild_data(pool, guild_id=g1)

    assert counts == {
        "guild_config": 1,
        "guild_queues": 1,
        "guild_jams": 1,
        "user_memories": 1,
    }, f"Returned counts must reflect actual per-table deletions: {counts}"

    async with pool.acquire() as conn:
        # G1 rows are gone.
        assert await conn.fetchval("SELECT COUNT(*) FROM guild_config WHERE guild_id = $1", g1) == 0
        assert await conn.fetchval("SELECT COUNT(*) FROM guild_queues WHERE guild_id = $1", g1) == 0
        assert await conn.fetchval("SELECT COUNT(*) FROM guild_jams WHERE guild_id = $1", g1) == 0
        assert await conn.fetchval("SELECT COUNT(*) FROM user_memories WHERE guild_id = $1", g1) == 0

        # G2 rows all survive.
        assert await conn.fetchval("SELECT COUNT(*) FROM guild_config WHERE guild_id = $1", g2) == 1
        assert await conn.fetchval("SELECT COUNT(*) FROM guild_queues WHERE guild_id = $1", g2) == 1
        assert await conn.fetchval("SELECT COUNT(*) FROM guild_jams WHERE guild_id = $1", g2) == 1
        assert await conn.fetchval("SELECT COUNT(*) FROM user_memories WHERE guild_id = $1", g2) == 1

        # The NULL-guild memory survives (MEM-03 / D-01 grandfather rule).
        null_count = await conn.fetchval(
            "SELECT COUNT(*) FROM user_memories WHERE user_id = $1 AND guild_id IS NULL",
            user_id,
        )
        assert null_count == 1, "A user_memories row with guild_id IS NULL must survive the purge (D-01)"

    # Clean up remaining rows.
    await database.purge_guild_data(pool, guild_id=g2)
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM user_memories WHERE user_id = $1", user_id)


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_guild_scoped_search_excludes_other_guild_includes_null(pool) -> None:
    """MEM-01/MEM-03 SQL-level proof against real Postgres (plan 21-01's search_memories)."""
    user_id = "test-phase21-search-user"
    g1 = "test-phase21-search-g1"
    g2 = "test-phase21-search-g2"

    from datetime import datetime, timedelta, timezone

    expires_at = datetime.now(timezone.utc) + timedelta(days=90)

    # Distinct-but-close embeddings — this test proves the WHERE clause, not ANN ranking.
    embedding_g1 = [0.10] * config.EMBED_DIM
    embedding_g2 = [0.11] * config.EMBED_DIM
    embedding_null = [0.12] * config.EMBED_DIM
    query_embedding = [0.10] * config.EMBED_DIM

    await database.insert_memory(
        pool,
        user_id=user_id,
        guild_id=g1,
        kind="daily_batch",
        fact="G1 search fact",
        embedding=embedding_g1,
        salience=0.5,
        expires_at=expires_at,
    )
    await database.insert_memory(
        pool,
        user_id=user_id,
        guild_id=g2,
        kind="daily_batch",
        fact="G2 search fact",
        embedding=embedding_g2,
        salience=0.5,
        expires_at=expires_at,
    )
    await database.insert_memory(
        pool,
        user_id=user_id,
        guild_id=None,
        kind="daily_batch",
        fact="NULL search fact",
        embedding=embedding_null,
        salience=0.5,
        expires_at=expires_at,
    )

    # guild_id="G1" scoped search: must return G1 + NULL, must exclude G2.
    scoped_rows = await database.search_memories(
        pool, user_id=user_id, query_embedding=query_embedding, k=10, guild_id=g1
    )
    scoped_facts = {r["fact"] for r in scoped_rows}
    assert scoped_facts == {"G1 search fact", "NULL search fact"}, (
        f"guild_id={g1!r} scoped search must return G1 + NULL rows only, got: {scoped_facts}"
    )

    # No guild_id: all three come back.
    all_rows = await database.search_memories(pool, user_id=user_id, query_embedding=query_embedding, k=10)
    all_facts = {r["fact"] for r in all_rows}
    assert all_facts == {"G1 search fact", "G2 search fact", "NULL search fact"}, (
        f"Unscoped search must return all three rows, got: {all_facts}"
    )

    # Clean up.
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM user_memories WHERE user_id = $1", user_id)
