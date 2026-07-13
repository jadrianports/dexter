"""Phase 20 Owner Control Plane — database.py tests for the blocklist + silenced helpers.

Covers OWNER-04 (`load_blocklist` / `insert_blocklist` / `delete_blocklist`) and OWNER-02
(`set_silenced`):
  - Static source-inspection checks (no live DB needed) locking the DDL shape, the
    upsert idiom on insert_blocklist, and the UPDATE ... RETURNING shape on set_silenced.
  - Live-DB integration tests proving the blocklist CRUD round-trip, the silenced
    round-trip (including the no-such-guild None contract), and the D-01 durability
    proof: a blocklist row survives a guild_config row delete (the exact operation
    Phase 21's MEM-04 purge will perform).

Set TEST_DATABASE_URL to a pgvector-enabled database before running the live tests.
The default `postgresql://dexter:dexter@localhost:5432/dexter_test` is treated as
"no live DB configured" — the live tests skip automatically.

Autonomous gate (no live DB needed): pytest --collect-only exits 0.
Full integration run: pytest tests/test_database_phase20.py -x (requires a
pgvector-enabled PostgreSQL, e.g. Neon or a local PG 16 + pgvector install).
"""

from __future__ import annotations

import inspect
import os

import pytest

import database

# ---------------------------------------------------------------------------
# Skip guard — mirrors test_database_phase16.py convention
# ---------------------------------------------------------------------------

_LOCAL_DEFAULT = "postgresql://dexter:dexter@localhost:5432/dexter_test"
_TEST_DSN = os.getenv("TEST_DATABASE_URL", _LOCAL_DEFAULT)
_SKIP_LIVE = os.getenv("TEST_DATABASE_URL") is None

_skip_reason = (
    "Live pgvector DB not configured — set TEST_DATABASE_URL to run Phase 20 "
    "integration tests (e.g. a pgvector-enabled Postgres such as Neon)"
)


# ---------------------------------------------------------------------------
# Static source-inspection checks — always run, no live DB needed (20-01 Task 2)
# ---------------------------------------------------------------------------


class TestPhase20BlocklistAndSilencedHelpers:
    """Verify the guild_blocklist DDL + blocklist/silenced helpers exist with locked shapes."""

    def test_helpers_exist(self) -> None:
        assert hasattr(database, "load_blocklist"), "load_blocklist must exist in database.py (OWNER-04)"
        assert hasattr(database, "insert_blocklist"), "insert_blocklist must exist in database.py (OWNER-04)"
        assert hasattr(database, "delete_blocklist"), "delete_blocklist must exist in database.py (OWNER-04)"
        assert hasattr(database, "set_silenced"), "set_silenced must exist in database.py (OWNER-02)"

    def test_schema_sql_contains_guild_blocklist_ddl(self) -> None:
        assert "CREATE TABLE IF NOT EXISTS guild_blocklist" in database.SCHEMA_SQL, (
            "guild_blocklist DDL must live inside the single SCHEMA_SQL string "
            "(asyncpg's param-free multi-statement DDL rule, Pitfall 1) — never "
            "a separate conn.execute()"
        )

    def test_insert_blocklist_is_upsert(self) -> None:
        """A re-block of an already-blocked guild must update the reason, not error/duplicate."""
        src = inspect.getsource(database.insert_blocklist)
        assert "ON CONFLICT (guild_id) DO UPDATE" in src, (
            "insert_blocklist must use INSERT ... ON CONFLICT (guild_id) DO UPDATE "
            "so a re-block updates the reason (mirrors set_proactive_opt_out)"
        )

    def test_set_silenced_targets_silenced_column_with_returning(self) -> None:
        src = inspect.getsource(database.set_silenced)
        assert "silenced = $2" in src, "set_silenced must UPDATE the silenced column via a $2 param"
        assert "RETURNING" in src, (
            "set_silenced must RETURNING the updated row (or None on no-row) — "
            "the 'row existed?' contract the service-tier setter relies on"
        )

    def test_helpers_are_async(self) -> None:
        for name in ("load_blocklist", "insert_blocklist", "delete_blocklist", "set_silenced"):
            assert inspect.iscoroutinefunction(getattr(database, name)), f"{name} must be an async function"


# ---------------------------------------------------------------------------
# Live-DB integration tests (20-01 Task 2)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_blocklist_crud_roundtrip(pool) -> None:
    """Insert, re-insert-with-new-reason (upsert), delete — full blocklist CRUD proof."""
    guild_id = "test-phase20-g1"

    await database.insert_blocklist(pool, guild_id=guild_id, reason="spam")
    rows = await database.load_blocklist(pool)
    matches = [r for r in rows if r["guild_id"] == guild_id]
    assert len(matches) == 1
    assert matches[0]["reason"] == "spam"

    # Re-insert with a new reason — ON CONFLICT must update, not duplicate.
    await database.insert_blocklist(pool, guild_id=guild_id, reason="abuse")
    rows = await database.load_blocklist(pool)
    matches = [r for r in rows if r["guild_id"] == guild_id]
    assert len(matches) == 1, "insert_blocklist must upsert, never duplicate a guild_id row"
    assert matches[0]["reason"] == "abuse"

    await database.delete_blocklist(pool, guild_id=guild_id)
    rows = await database.load_blocklist(pool)
    assert guild_id not in {r["guild_id"] for r in rows}


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_set_silenced_roundtrip(pool) -> None:
    """Seed a guild_config row, silence it, unsilence it; no-such-guild returns None."""
    guild_id = "test-phase20-g2"
    await database.insert_guild_config_if_absent(pool, guild_id=guild_id)

    row = await database.set_silenced(pool, guild_id=guild_id, silenced=True)
    assert row is not None
    assert row["silenced"] is True

    row = await database.set_silenced(pool, guild_id=guild_id, silenced=False)
    assert row is not None
    assert row["silenced"] is False

    # No row exists for this guild_id — the "row existed?" None contract.
    missing_row = await database.set_silenced(pool, guild_id="test-phase20-nonexistent", silenced=True)
    assert missing_row is None


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_blocklist_independent_of_guild_config(pool) -> None:
    """D-01 durability proof: a blocklist row survives a guild_config row delete.

    This simulates exactly the operation Phase 21's MEM-04 purge will perform
    (`DELETE FROM guild_config WHERE guild_id = $1`) — the blacklist must
    remain intact so a kicked abuser cannot launder their block by re-inviting.
    """
    guild_id = "test-phase20-g3"

    await database.insert_guild_config_if_absent(pool, guild_id=guild_id)
    await database.insert_blocklist(pool, guild_id=guild_id, reason="testing durability")

    # Simulate Phase 21's MEM-04 purge of guild_config — must NOT touch guild_blocklist.
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM guild_config WHERE guild_id = $1", guild_id)

    rows = await database.load_blocklist(pool)
    assert guild_id in {r["guild_id"] for r in rows}, (
        "guild_blocklist row must survive a guild_config delete (D-01) — "
        "a kicked abuser's block must not be laundered by a guild_config purge"
    )

    # Clean up.
    await database.delete_blocklist(pool, guild_id=guild_id)
