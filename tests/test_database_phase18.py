"""Phase 18 Per-Guild Config Foundation — database.py tests for guild_config.

Covers CONFIG-01 (schema shape) and CONFIG-05 (idempotent home-guild seed):
  - Static source-inspection / SCHEMA_SQL checks (no live DB needed) locking
    the DDL shape and the ON CONFLICT DO NOTHING (never DO UPDATE) seed idiom.
  - Live-DB integration tests proving init_db() actually creates the table
    with the expected column types/defaults, and that seeding the same
    guild_id twice with a different ambient_channel_id never overwrites the
    first value (the D-09 idempotence guarantee).

Set TEST_DATABASE_URL to a pgvector-enabled database before running the live
tests. The default `postgresql://dexter:dexter@localhost:5432/dexter_test` is
treated as "no live DB configured" — the live tests skip automatically.

Autonomous gate (no live DB needed): pytest --collect-only exits 0.
Full integration run: pytest tests/test_database_phase18.py -x (requires a
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
    "Live pgvector DB not configured — set TEST_DATABASE_URL to run Phase 18 "
    "integration tests (e.g. a pgvector-enabled Postgres such as Neon)"
)

_GUILD_CONFIG_COLUMNS = [
    "guild_id",
    "ambient_channel_id",
    "configured",
    "silenced",
    "is_blocked",
    "joined_at",
    "updated_at",
]


# ---------------------------------------------------------------------------
# Static structural checks — always run, no live DB needed (18-02 Task 2a)
# ---------------------------------------------------------------------------


class TestGuildConfigSchemaShape:
    """Verify the guild_config DDL shape without touching a database."""

    def test_guild_config_table_present(self) -> None:
        assert "CREATE TABLE IF NOT EXISTS guild_config" in database.SCHEMA_SQL

    def test_guild_config_all_columns_present(self) -> None:
        for column in _GUILD_CONFIG_COLUMNS:
            assert column in database.SCHEMA_SQL, f"guild_config is missing column {column!r}"

    def test_guild_config_no_phase19_columns(self) -> None:
        """D-12: Phase 18 ships exactly CONFIG-01's columns, nothing speculative."""
        assert "ambient_roasts_enabled" not in database.SCHEMA_SQL
        assert "vision_roasts_enabled" not in database.SCHEMA_SQL

    def test_boot_helpers_exist(self) -> None:
        assert hasattr(database, "load_all_guild_configs")
        assert hasattr(database, "seed_guild_config_if_absent")

    def test_seed_uses_do_nothing_never_do_update(self) -> None:
        """D-09 guard: the seed must use ON CONFLICT DO NOTHING, never DO UPDATE.

        A future edit that "helpfully" upserts the env value on every boot
        would make a later /setup silently self-revert — exactly the bug
        D-09 exists to prevent.
        """
        src = inspect.getsource(database.seed_guild_config_if_absent)
        assert "ON CONFLICT (guild_id) DO NOTHING" in src
        assert "DO UPDATE" not in src

    def test_load_all_guild_configs_is_param_free(self) -> None:
        """D-06: one round-trip, no params — a bare SELECT * FROM guild_config."""
        src = inspect.getsource(database.load_all_guild_configs)
        assert "FROM guild_config" in src
        # No $N positional params anywhere in the query body.
        assert "$1" not in src


# ---------------------------------------------------------------------------
# Live-DB integration tests (18-02 Task 2b/2c)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_guild_config_columns_and_defaults(pool) -> None:
    """init_db() must create guild_config with the 7 expected columns/types.

    Introspects information_schema.columns rather than trusting SCHEMA_SQL's
    string contents — proves the DDL actually applies cleanly against a real
    Postgres instance (CONFIG-01).
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT column_name, data_type, column_default"
            " FROM information_schema.columns"
            " WHERE table_name = 'guild_config'"
        )
    by_name = {row["column_name"]: row for row in rows}

    assert set(by_name) == set(_GUILD_CONFIG_COLUMNS), (
        f"guild_config columns mismatch: got {sorted(by_name)}, expected {sorted(_GUILD_CONFIG_COLUMNS)}"
    )

    assert by_name["guild_id"]["data_type"] == "text"
    assert by_name["ambient_channel_id"]["data_type"] == "text"
    assert by_name["configured"]["data_type"] == "boolean"
    assert by_name["silenced"]["data_type"] == "boolean"
    assert by_name["is_blocked"]["data_type"] == "boolean"
    assert by_name["joined_at"]["data_type"] == "timestamp with time zone"
    assert by_name["updated_at"]["data_type"] == "timestamp with time zone"

    # Defaults: configured/silenced/is_blocked all default to false.
    for col in ("configured", "silenced", "is_blocked"):
        default = by_name[col]["column_default"] or ""
        assert "false" in default.lower(), f"{col} default must be false, got {default!r}"


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_seed_guild_config_if_absent_is_idempotent(pool) -> None:
    """A second seed with a DIFFERENT ambient_channel_id must NOT change the row.

    Proves the D-09 ON CONFLICT DO NOTHING guarantee end-to-end: once a
    guild_config row exists, the bootstrap env value never overwrites it.
    """
    guild_id = "test-phase18-guild"

    first = await database.seed_guild_config_if_absent(pool, guild_id=guild_id, ambient_channel_id="111111111111111111")
    assert first is not None
    assert first["guild_id"] == guild_id
    assert first["ambient_channel_id"] == "111111111111111111"
    assert first["configured"] is True

    second = await database.seed_guild_config_if_absent(
        pool, guild_id=guild_id, ambient_channel_id="222222222222222222"
    )
    assert second is not None
    assert second["guild_id"] == guild_id
    assert second["ambient_channel_id"] == "111111111111111111", (
        "seed_guild_config_if_absent must never overwrite an existing row's "
        "ambient_channel_id (D-09 — ON CONFLICT DO NOTHING)"
    )
    assert second["configured"] is True


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_load_all_guild_configs_returns_seeded_rows(pool) -> None:
    """load_all_guild_configs must surface every row in one call, no filter."""
    await database.seed_guild_config_if_absent(pool, guild_id="test-phase18-load-a", ambient_channel_id="1")
    await database.seed_guild_config_if_absent(pool, guild_id="test-phase18-load-b", ambient_channel_id="2")

    rows = await database.load_all_guild_configs(pool)
    by_id = {row["guild_id"]: row for row in rows}

    assert "test-phase18-load-a" in by_id
    assert "test-phase18-load-b" in by_id
    assert by_id["test-phase18-load-a"]["ambient_channel_id"] == "1"
    assert by_id["test-phase18-load-b"]["ambient_channel_id"] == "2"
