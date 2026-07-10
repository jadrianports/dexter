"""Phase 19 Onboarding & Admin Setup — database.py tests for the two new
guild_config toggle columns and the RETURNING-based write helpers.

Covers ONBOARD-01 (D-14 insert-if-absent signal) and ONBOARD-04 (per-guild
ambient/vision toggles):
  - Static source-inspection / SCHEMA_SQL checks (no live DB needed) locking
    the new DDL shape and the five new helper signatures.
  - Live-DB integration tests proving:
      * insert_guild_config_if_absent returns a Record on a genuine insert
        and None on a conflict (the D-14 core contract).
      * a row seeded before this ALTER (the Phase 18 home-guild shape) reads
        both new toggles as True — the D-20 home-guild-regression lock.
      * configure_guild_first_time flips configured True + vision False while
        leaving ambient_roasts_enabled True, and a subsequent
        redesignate_guild_channel changes only ambient_channel_id.
      * set_ambient_roasts_enabled / set_vision_roasts_enabled round-trip.

Set TEST_DATABASE_URL to a pgvector-enabled database before running the live
tests. The default `postgresql://dexter:dexter@localhost:5432/dexter_test` is
treated as "no live DB configured" — the live tests skip automatically.

Autonomous gate (no live DB needed): pytest --collect-only exits 0.
Full integration run: pytest tests/test_database_phase19.py -x (requires a
pgvector-enabled PostgreSQL, e.g. Neon or a local PG 16 + pgvector install).
"""

from __future__ import annotations

import inspect
import os

import pytest

import database

# ---------------------------------------------------------------------------
# Skip guard — mirrors test_database_phase18.py convention
# ---------------------------------------------------------------------------

_LOCAL_DEFAULT = "postgresql://dexter:dexter@localhost:5432/dexter_test"
_TEST_DSN = os.getenv("TEST_DATABASE_URL", _LOCAL_DEFAULT)
_SKIP_LIVE = os.getenv("TEST_DATABASE_URL") is None

_skip_reason = (
    "Live pgvector DB not configured — set TEST_DATABASE_URL to run Phase 19 "
    "integration tests (e.g. a pgvector-enabled Postgres such as Neon)"
)

_NEW_TOGGLE_COLUMNS = ["ambient_roasts_enabled", "vision_roasts_enabled"]

_NEW_HELPERS = [
    "insert_guild_config_if_absent",
    "configure_guild_first_time",
    "redesignate_guild_channel",
    "set_ambient_roasts_enabled",
    "set_vision_roasts_enabled",
]


# ---------------------------------------------------------------------------
# Static structural checks — always run, no live DB needed
# ---------------------------------------------------------------------------


class TestGuildConfigTogglesSchemaShape:
    """Verify the Phase 19 DDL shape without touching a database."""

    def test_toggle_columns_present_in_schema(self) -> None:
        """Inverse of Phase 18's test_guild_config_no_phase19_columns guard —
        that test intentionally locks Phase 18's scope (columns ABSENT); this
        phase's own file asserts them PRESENT now that they've landed."""
        assert "ambient_roasts_enabled" in database.SCHEMA_SQL
        assert "vision_roasts_enabled" in database.SCHEMA_SQL

    def test_toggle_columns_use_add_column_if_not_exists_default_true(self) -> None:
        assert "ADD COLUMN IF NOT EXISTS ambient_roasts_enabled BOOLEAN NOT NULL DEFAULT true" in database.SCHEMA_SQL
        assert "ADD COLUMN IF NOT EXISTS vision_roasts_enabled BOOLEAN NOT NULL DEFAULT true" in database.SCHEMA_SQL

    def test_new_helpers_exist(self) -> None:
        for name in _NEW_HELPERS:
            assert hasattr(database, name), f"database.py is missing helper {name!r}"

    def test_insert_guild_config_if_absent_uses_do_nothing_returning(self) -> None:
        src = inspect.getsource(database.insert_guild_config_if_absent)
        assert "ON CONFLICT (guild_id) DO NOTHING" in src
        assert "RETURNING" in src

    def test_configure_guild_first_time_upserts_and_turns_vision_off(self) -> None:
        src = inspect.getsource(database.configure_guild_first_time)
        assert "ON CONFLICT (guild_id) DO UPDATE" in src
        assert "configured = true" in src
        assert "vision_roasts_enabled = false" in src
        assert "ambient_roasts_enabled" not in src

    def test_redesignate_guild_channel_touches_only_the_channel(self) -> None:
        src = inspect.getsource(database.redesignate_guild_channel)
        assert "ambient_channel_id" in src
        assert "configured" not in src
        assert "vision_roasts_enabled" not in src
        assert "ambient_roasts_enabled" not in src

    def test_load_all_guild_configs_carries_both_toggles(self) -> None:
        src = inspect.getsource(database.load_all_guild_configs)
        for column in _NEW_TOGGLE_COLUMNS:
            assert column in src

    def test_seed_guild_config_if_absent_carries_both_toggles(self) -> None:
        src = inspect.getsource(database.seed_guild_config_if_absent)
        for column in _NEW_TOGGLE_COLUMNS:
            assert column in src
        # D-09 idempotency lock unchanged by this ALTER.
        assert "ON CONFLICT (guild_id) DO NOTHING" in src
        assert "DO UPDATE" not in src

    def test_no_string_interpolation_in_new_write_helpers(self) -> None:
        """T-19-03: guild_id/channel_id/enabled must arrive as $N params only."""
        for name in _NEW_HELPERS:
            src = inspect.getsource(getattr(database, name))
            assert 'f"' not in src, f"{name} uses an f-string against SQL"
            assert "f'" not in src, f"{name} uses an f-string against SQL"
            assert "%" not in src, f"{name} uses %-formatting against SQL"


# ---------------------------------------------------------------------------
# Live-DB integration tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_insert_guild_config_if_absent_first_call_inserts(pool) -> None:
    """D-14 core contract: first call returns a Record with the true column defaults."""
    guild_id = "test-phase19-insert-a"

    row = await database.insert_guild_config_if_absent(pool, guild_id=guild_id)

    assert row is not None
    assert row["guild_id"] == guild_id
    assert row["configured"] is False
    assert row["ambient_roasts_enabled"] is True
    assert row["vision_roasts_enabled"] is True


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_insert_guild_config_if_absent_second_call_returns_none(pool) -> None:
    """D-14 core contract: a second insert for the same guild_id is a no-op signal."""
    guild_id = "test-phase19-insert-b"

    first = await database.insert_guild_config_if_absent(pool, guild_id=guild_id)
    assert first is not None

    second = await database.insert_guild_config_if_absent(pool, guild_id=guild_id)
    assert second is None


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_pre_existing_row_reads_both_toggles_true(pool) -> None:
    """D-20 home-guild-regression lock: a row seeded via the Phase 18 path
    (predating this ALTER's toggle intent) reads both toggles as True."""
    guild_id = "test-phase19-preexisting"

    seeded = await database.seed_guild_config_if_absent(
        pool, guild_id=guild_id, ambient_channel_id="123456789012345678"
    )
    assert seeded is not None
    assert seeded["ambient_roasts_enabled"] is True
    assert seeded["vision_roasts_enabled"] is True

    loaded = await database.load_all_guild_configs(pool)
    by_id = {row["guild_id"]: row for row in loaded}
    assert by_id[guild_id]["ambient_roasts_enabled"] is True
    assert by_id[guild_id]["vision_roasts_enabled"] is True


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_configure_guild_first_time_sets_configured_and_turns_vision_off(pool) -> None:
    guild_id = "test-phase19-first-configure"

    row = await database.configure_guild_first_time(pool, guild_id=guild_id, channel_id="222222222222222222")

    assert row is not None
    assert row["configured"] is True
    assert row["ambient_channel_id"] == "222222222222222222"
    assert row["vision_roasts_enabled"] is False
    assert row["ambient_roasts_enabled"] is True


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_redesignate_guild_channel_changes_only_channel(pool) -> None:
    guild_id = "test-phase19-redesignate"

    await database.configure_guild_first_time(pool, guild_id=guild_id, channel_id="333333333333333333")
    await database.set_ambient_roasts_enabled(pool, guild_id=guild_id, enabled=False)

    redesignated = await database.redesignate_guild_channel(pool, guild_id=guild_id, channel_id="444444444444444444")

    assert redesignated is not None
    assert redesignated["ambient_channel_id"] == "444444444444444444"
    assert redesignated["configured"] is True
    # Toggles untouched by the re-designate — the toggle the admin already
    # changed (ambient off) stays off; vision (turned off by first-configure)
    # also stays off.
    assert redesignated["ambient_roasts_enabled"] is False
    assert redesignated["vision_roasts_enabled"] is False


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_set_ambient_roasts_enabled_round_trips(pool) -> None:
    guild_id = "test-phase19-toggle-ambient"
    await database.insert_guild_config_if_absent(pool, guild_id=guild_id)

    off = await database.set_ambient_roasts_enabled(pool, guild_id=guild_id, enabled=False)
    assert off is not None
    assert off["ambient_roasts_enabled"] is False

    on = await database.set_ambient_roasts_enabled(pool, guild_id=guild_id, enabled=True)
    assert on is not None
    assert on["ambient_roasts_enabled"] is True


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_set_vision_roasts_enabled_round_trips(pool) -> None:
    guild_id = "test-phase19-toggle-vision"
    await database.insert_guild_config_if_absent(pool, guild_id=guild_id)

    off = await database.set_vision_roasts_enabled(pool, guild_id=guild_id, enabled=False)
    assert off is not None
    assert off["vision_roasts_enabled"] is False

    on = await database.set_vision_roasts_enabled(pool, guild_id=guild_id, enabled=True)
    assert on is not None
    assert on["vision_roasts_enabled"] is True
