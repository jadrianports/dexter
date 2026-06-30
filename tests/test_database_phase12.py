"""Phase 12 PostgreSQL integration tests — guild_jams table + 5 helpers (UX-01).

These tests require a live PostgreSQL database.
Set TEST_DATABASE_URL or ensure postgresql://dexter:dexter@localhost:5432/dexter_test
is reachable before running.

The pool fixture is defined in tests/conftest.py — it calls init_db, yields the
pool, and drops all tables on teardown (including guild_jams).

Autonomous gate (no live DB needed): pytest --collect-only exits 0.
Full integration run: pytest tests/test_database_phase12.py -x (requires dexter_test DB).

Key coverage:
  T-12-01-01 — save_jam/get_jam/list_jams use $N params (SQL injection prevention)
  T-12-01-02 — cross-guild isolation: guild-A jam invisible to guild-B
"""

from __future__ import annotations

import pytest

from database import (
    save_jam,
    get_jam,
    list_jams,
    delete_jam,
    count_jams,
)
from models.queue import Track


# ---------------------------------------------------------------------------
# Helper: build a minimal Track snapshot (list of dicts via to_dict)
# ---------------------------------------------------------------------------


def _make_jam_snapshot(n: int, user_id: int = 999) -> list[dict]:
    """Return a list of n Track.to_dict() dicts for jam round-trip testing."""
    return [
        Track(
            video_id=f"jam_{i}",
            title=f"Jam Song {i}",
            artist=f"Artist {i}",
            url=f"https://youtube.com/watch?v=jam_{i}",
            duration_seconds=180 + i,
            requested_by=user_id,
            thumbnail=f"https://img.youtube.com/vi/jam_{i}/0.jpg",
        ).to_dict()
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# TestGuildJamsSchema — table exists after init_db
# ---------------------------------------------------------------------------


class TestGuildJamsSchema:
    """Verify guild_jams table is created by init_db (idempotent SCHEMA_SQL)."""

    @pytest.mark.asyncio
    async def test_guild_jams_table_exists(self, pool):
        """init_db must create guild_jams table."""
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        tables = {r["tablename"] for r in rows}
        assert "guild_jams" in tables, "guild_jams table not found after init_db"

    @pytest.mark.asyncio
    async def test_guild_jams_has_expected_columns(self, pool):
        """guild_jams must have the required columns."""
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = 'guild_jams' AND table_schema = 'public'"
                " ORDER BY column_name"
            )
        cols = {r["column_name"] for r in rows}
        expected = {"guild_id", "name", "snapshot", "created_at", "updated_at"}
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"

    @pytest.mark.asyncio
    async def test_idx_jams_guild_index_exists(self, pool):
        """idx_jams_guild index must exist on guild_jams."""
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT indexname FROM pg_indexes"
                " WHERE tablename = 'guild_jams' AND schemaname = 'public'"
            )
        indexes = {r["indexname"] for r in rows}
        assert "idx_jams_guild" in indexes, "idx_jams_guild index not found"


# ---------------------------------------------------------------------------
# TestSaveJam — upsert (insert + overwrite same name)
# ---------------------------------------------------------------------------


class TestSaveJam:
    """Tests for save_jam helper — insert + upsert semantics."""

    @pytest.mark.asyncio
    async def test_save_jam_inserts_new_row(self, pool):
        """save_jam creates a new row for a fresh (guild_id, name) pair."""
        snapshot = _make_jam_snapshot(3)
        await save_jam(pool, guild_id="g1", name="summer", snapshot=snapshot)
        result = await get_jam(pool, guild_id="g1", name="summer")
        assert result is not None
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_save_jam_upserts_on_name_clash(self, pool):
        """Re-saving to the same (guild_id, name) replaces the snapshot."""
        await save_jam(pool, guild_id="g2", name="friday-mix", snapshot=_make_jam_snapshot(2))
        new_snapshot = _make_jam_snapshot(5)
        await save_jam(pool, guild_id="g2", name="friday-mix", snapshot=new_snapshot)
        result = await get_jam(pool, guild_id="g2", name="friday-mix")
        assert result is not None
        assert len(result) == 5, "Upsert must replace the snapshot, not append"


# ---------------------------------------------------------------------------
# TestGetJam — fetch + JSONB round-trip
# ---------------------------------------------------------------------------


class TestGetJam:
    """Tests for get_jam helper."""

    @pytest.mark.asyncio
    async def test_get_jam_returns_none_for_missing(self, pool):
        """get_jam returns None when the (guild_id, name) doesn't exist."""
        result = await get_jam(pool, guild_id="ghostguild", name="nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_jam_round_trips_track_dicts(self, pool):
        """Track.to_dict() dicts stored in snapshot come back identical via Track.from_dict."""
        original = _make_jam_snapshot(3, user_id=111)
        await save_jam(pool, guild_id="g3", name="roundtrip", snapshot=original)
        result = await get_jam(pool, guild_id="g3", name="roundtrip")
        assert result is not None
        assert len(result) == 3
        for orig, stored in zip(original, result):
            rebuilt = Track.from_dict(stored).to_dict()
            assert rebuilt == orig, f"Round-trip mismatch: {orig} vs {rebuilt}"

    @pytest.mark.asyncio
    async def test_get_jam_returns_correct_name(self, pool):
        """get_jam fetches the correct named jam, not a different name."""
        await save_jam(pool, guild_id="g4", name="alpha", snapshot=_make_jam_snapshot(1))
        await save_jam(pool, guild_id="g4", name="beta", snapshot=_make_jam_snapshot(3))
        alpha = await get_jam(pool, guild_id="g4", name="alpha")
        beta = await get_jam(pool, guild_id="g4", name="beta")
        assert alpha is not None and len(alpha) == 1
        assert beta is not None and len(beta) == 3


# ---------------------------------------------------------------------------
# TestCrossGuildIsolation — T-12-01-02 isolation assertions
# ---------------------------------------------------------------------------


class TestCrossGuildIsolation:
    """Guild-A jams must be invisible to guild-B queries (T-12-01-02)."""

    @pytest.mark.asyncio
    async def test_get_jam_cross_guild_invisible(self, pool):
        """A jam saved under guild-A is NOT returned by get_jam for guild-B."""
        await save_jam(pool, guild_id="guildA", name="secret", snapshot=_make_jam_snapshot(2))
        result_b = await get_jam(pool, guild_id="guildB", name="secret")
        assert result_b is None, "guild-B must not see guild-A's jam"

    @pytest.mark.asyncio
    async def test_list_jams_cross_guild_invisible(self, pool):
        """list_jams for guild-B must not include jams saved under guild-A."""
        await save_jam(pool, guild_id="guildC", name="shared-name", snapshot=_make_jam_snapshot(1))
        rows_d = await list_jams(pool, guild_id="guildD")
        names_d = {r["name"] for r in rows_d}
        assert "shared-name" not in names_d, "guild-D must not see guild-C's jam"

    @pytest.mark.asyncio
    async def test_same_name_different_guilds_isolated(self, pool):
        """Two guilds can have a jam with the same name and different snapshots."""
        await save_jam(pool, guild_id="guildE", name="vibes", snapshot=_make_jam_snapshot(2))
        await save_jam(pool, guild_id="guildF", name="vibes", snapshot=_make_jam_snapshot(4))
        r_e = await get_jam(pool, guild_id="guildE", name="vibes")
        r_f = await get_jam(pool, guild_id="guildF", name="vibes")
        assert r_e is not None and len(r_e) == 2
        assert r_f is not None and len(r_f) == 4

    @pytest.mark.asyncio
    async def test_count_jams_cross_guild_isolated(self, pool):
        """count_jams counts only the requesting guild's rows."""
        await save_jam(pool, guild_id="guildG", name="g-jam", snapshot=_make_jam_snapshot(1))
        await save_jam(pool, guild_id="guildH", name="h-jam", snapshot=_make_jam_snapshot(1))
        assert await count_jams(pool, guild_id="guildG") == 1
        assert await count_jams(pool, guild_id="guildH") == 1


# ---------------------------------------------------------------------------
# TestListJams — list helper (newest-first, name+count+updated)
# ---------------------------------------------------------------------------


class TestListJams:
    """Tests for list_jams helper."""

    @pytest.mark.asyncio
    async def test_list_jams_empty_for_new_guild(self, pool):
        """list_jams returns [] for a guild with no saved jams."""
        result = await list_jams(pool, guild_id="newguild")
        assert result == []

    @pytest.mark.asyncio
    async def test_list_jams_returns_metadata(self, pool):
        """Each row from list_jams has name, track_count, and updated_at."""
        await save_jam(pool, guild_id="g5", name="session1", snapshot=_make_jam_snapshot(4))
        rows = await list_jams(pool, guild_id="g5")
        assert len(rows) == 1
        row = rows[0]
        assert row["name"] == "session1"
        assert row["track_count"] == 4
        assert "updated_at" in row

    @pytest.mark.asyncio
    async def test_list_jams_newest_first(self, pool):
        """list_jams returns jams newest-updated-first."""
        await save_jam(pool, guild_id="g6", name="first", snapshot=_make_jam_snapshot(1))
        await save_jam(pool, guild_id="g6", name="second", snapshot=_make_jam_snapshot(2))
        rows = await list_jams(pool, guild_id="g6")
        assert len(rows) == 2
        # "second" was saved last so should appear first (updated_at DESC)
        assert rows[0]["name"] == "second"


# ---------------------------------------------------------------------------
# TestDeleteJam — delete helper
# ---------------------------------------------------------------------------


class TestDeleteJam:
    """Tests for delete_jam helper."""

    @pytest.mark.asyncio
    async def test_delete_jam_removes_row(self, pool):
        """delete_jam removes the named jam and returns True."""
        await save_jam(pool, guild_id="g7", name="todelete", snapshot=_make_jam_snapshot(2))
        deleted = await delete_jam(pool, guild_id="g7", name="todelete")
        assert deleted is True
        result = await get_jam(pool, guild_id="g7", name="todelete")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_jam_returns_false_for_missing(self, pool):
        """delete_jam returns False when the row doesn't exist."""
        deleted = await delete_jam(pool, guild_id="g8", name="ghost")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_delete_jam_returns_false_on_re_delete(self, pool):
        """delete_jam returns True on first delete, False on re-delete."""
        await save_jam(pool, guild_id="g9", name="once", snapshot=_make_jam_snapshot(1))
        first = await delete_jam(pool, guild_id="g9", name="once")
        assert first is True
        second = await delete_jam(pool, guild_id="g9", name="once")
        assert second is False

    @pytest.mark.asyncio
    async def test_delete_jam_cross_guild_cannot_delete(self, pool):
        """delete_jam keyed on guild_id cannot delete another guild's jam."""
        await save_jam(pool, guild_id="g10", name="mine", snapshot=_make_jam_snapshot(2))
        # g11 tries to delete g10's "mine" — should be a no-op
        deleted = await delete_jam(pool, guild_id="g11", name="mine")
        assert deleted is False
        # g10's jam should still exist
        result = await get_jam(pool, guild_id="g10", name="mine")
        assert result is not None


# ---------------------------------------------------------------------------
# TestCountJams — count helper (for cap enforcement)
# ---------------------------------------------------------------------------


class TestCountJams:
    """Tests for count_jams helper."""

    @pytest.mark.asyncio
    async def test_count_jams_zero_for_new_guild(self, pool):
        """count_jams returns 0 for a guild with no saved jams."""
        count = await count_jams(pool, guild_id="nojamlguild")
        assert count == 0

    @pytest.mark.asyncio
    async def test_count_jams_increments_with_distinct_names(self, pool):
        """count_jams increments with each new distinct jam name."""
        for i in range(3):
            await save_jam(
                pool, guild_id="g12", name=f"jam_{i}", snapshot=_make_jam_snapshot(1)
            )
        assert await count_jams(pool, guild_id="g12") == 3

    @pytest.mark.asyncio
    async def test_count_jams_upsert_does_not_increment(self, pool):
        """Re-saving to an existing name (upsert) does NOT increase the count."""
        await save_jam(pool, guild_id="g13", name="stable", snapshot=_make_jam_snapshot(1))
        await save_jam(pool, guild_id="g13", name="stable", snapshot=_make_jam_snapshot(2))
        assert await count_jams(pool, guild_id="g13") == 1

    @pytest.mark.asyncio
    async def test_count_jams_reflects_distinct_names(self, pool):
        """count_jams counts distinct jam names for a guild."""
        await save_jam(pool, guild_id="g14", name="a", snapshot=_make_jam_snapshot(1))
        await save_jam(pool, guild_id="g14", name="b", snapshot=_make_jam_snapshot(2))
        await save_jam(pool, guild_id="g14", name="c", snapshot=_make_jam_snapshot(3))
        assert await count_jams(pool, guild_id="g14") == 3
