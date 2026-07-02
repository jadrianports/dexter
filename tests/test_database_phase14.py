"""Phase 14 PostgreSQL integration tests — Smarter Music Brain aggregate helpers.

Covers the three database.py helpers added in plan 14-01 (BRAIN-01/BRAIN-02):
  - get_recently_skipped     — guild-scoped negative-hint source, NO per-user attribution
  - get_user_top_artist      — guild+invoker-scoped /discover anchor (OQ2 Option B)
  - get_artist_cooccurrence  — guild-wide same-day co-occurrence, NO per-user attribution

The pool fixture is defined in tests/conftest.py — it calls init_db, yields the
pool, and drops song_history/etc. on teardown.

Autonomous gate (no live DB needed): pytest --collect-only exits 0.
Full integration run: pytest tests/test_database_phase14.py -q (requires a
live dexter_test DB reachable per tests/conftest.py's pool fixture; skips
cleanly — not an error — when Postgres is unavailable).
"""

from __future__ import annotations

import inspect
import re
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

import database


# ---------------------------------------------------------------------------
# Static source-assertion checks — always run, no live DB needed
# ---------------------------------------------------------------------------


class TestPhase14HelpersExist:
    """Verify all Task 2 artifacts exist with the right scoping (T-14-01/T-14-02)."""

    def test_get_recently_skipped_exists(self) -> None:
        assert hasattr(database, "get_recently_skipped"), (
            "get_recently_skipped must exist in database.py"
        )

    def test_get_user_top_artist_exists(self) -> None:
        assert hasattr(database, "get_user_top_artist"), (
            "get_user_top_artist must exist in database.py"
        )

    def test_get_artist_cooccurrence_exists(self) -> None:
        assert hasattr(database, "get_artist_cooccurrence"), (
            "get_artist_cooccurrence must exist in database.py"
        )

    def test_get_recently_skipped_is_scoped(self) -> None:
        """get_recently_skipped must scope guild_id=$1 + was_skipped + queued_at bound (D-01)."""
        src = inspect.getsource(database.get_recently_skipped)
        assert "WHERE guild_id = $1 AND was_skipped = true AND queued_at > $2" in src, (
            "get_recently_skipped must include"
            " WHERE guild_id = $1 AND was_skipped = true AND queued_at > $2"
        )

    def test_get_user_top_artist_is_scoped(self) -> None:
        """get_user_top_artist must scope by guild_id=$1 AND user_id=$2 (Option B, OQ2)."""
        src = inspect.getsource(database.get_user_top_artist)
        assert "WHERE guild_id = $1 AND user_id = $2" in src, (
            "get_user_top_artist must include WHERE guild_id = $1 AND user_id = $2"
        )

    def test_get_artist_cooccurrence_shape(self) -> None:
        """get_artist_cooccurrence must use date_trunc('day' bucketing, exclude the anchor,
        and bind $1..$4 — and its SQL query literal must not select/reference a
        user_id column (T-14-02). Only the SQL string literals are checked here
        (not the docstring, which legitimately discusses the no-attribution
        guarantee in prose)."""
        src = inspect.getsource(database.get_artist_cooccurrence)
        assert "date_trunc('day'" in src
        assert "sh.artist <> $2" in src
        assert "$1" in src and "$2" in src and "$3" in src and "$4" in src

        # Strip the triple-quoted docstring first (it legitimately discusses
        # "user_id" in prose), then check only the remaining code — the SQL
        # string literals passed to conn.fetch — for a literal user_id mention.
        code_without_docstring = re.sub(r'""".*?"""', "", src, flags=re.DOTALL)
        assert "user_id" not in code_without_docstring, (
            "get_artist_cooccurrence's SQL must not select/reference user_id — "
            "guild-wide artist aggregate only, no per-user attribution"
        )

    def test_no_string_interpolation(self) -> None:
        """None of the three new helpers may use f-strings or %-interpolated SQL (T-14-01)."""
        for fn in (
            database.get_recently_skipped,
            database.get_user_top_artist,
            database.get_artist_cooccurrence,
        ):
            src = inspect.getsource(fn)
            assert 'f"' not in src and "f'" not in src, (
                f"{fn.__name__} must not use f-string SQL (T-14-01)"
            )
            assert "%s" not in src, f"{fn.__name__} must not use %-interpolated SQL (T-14-01)"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _insert_history_row(
    pool,
    *,
    guild_id: str,
    user_id: str,
    artist: str | None,
    title: str = "Test Song",
    queued_at: datetime,
    was_skipped: bool = False,
    url_suffix: str = "",
) -> None:
    """Insert a song_history row with an explicit queued_at for window-boundary testing."""
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO song_history"
            " (guild_id, user_id, title, artist, url, duration_seconds, queued_at, was_skipped)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
            guild_id, user_id, title, artist,
            f"https://youtube.com/watch?v=test{url_suffix}", 200, queued_at, was_skipped,
        )


# ---------------------------------------------------------------------------
# get_recently_skipped
# ---------------------------------------------------------------------------


class TestGetRecentlySkipped:
    """Tests for get_recently_skipped — guild-scoped, no per-user attribution (T-14-02)."""

    @pytest.mark.asyncio
    async def test_returns_skipped_rows_with_no_user_id(self, pool) -> None:
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=7)
        await _insert_history_row(
            pool, guild_id="g14-skip1", user_id="u-a", artist="Radiohead",
            title="Karma Police", queued_at=now - timedelta(hours=1),
            was_skipped=True, url_suffix="skip1",
        )

        rows = await database.get_recently_skipped(
            pool, guild_id="g14-skip1", since=since, limit=15
        )

        assert len(rows) == 1
        assert rows[0]["title"] == "Karma Police"
        assert rows[0]["artist"] == "Radiohead"
        assert "user_id" not in rows[0].keys()

    @pytest.mark.asyncio
    async def test_excludes_non_skipped_and_stale_rows(self, pool) -> None:
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=7)
        # not skipped
        await _insert_history_row(
            pool, guild_id="g14-skip2", user_id="u-a", artist="Not Skipped Artist",
            queued_at=now - timedelta(hours=1), was_skipped=False, url_suffix="notskip",
        )
        # skipped but stale (predates `since`)
        await _insert_history_row(
            pool, guild_id="g14-skip2", user_id="u-a", artist="Stale Skip Artist",
            queued_at=now - timedelta(days=30), was_skipped=True, url_suffix="staleskip",
        )

        rows = await database.get_recently_skipped(
            pool, guild_id="g14-skip2", since=since, limit=15
        )

        assert rows == []

    @pytest.mark.asyncio
    async def test_cross_user_collective_signal_not_attributed(self, pool) -> None:
        """Two different users' skips in the same guild both surface, with no user_id leak."""
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=7)
        await _insert_history_row(
            pool, guild_id="g14-skip3", user_id="u-a", artist="Artist A",
            title="Song A", queued_at=now - timedelta(hours=2),
            was_skipped=True, url_suffix="crossA",
        )
        await _insert_history_row(
            pool, guild_id="g14-skip3", user_id="u-b", artist="Artist B",
            title="Song B", queued_at=now - timedelta(hours=1),
            was_skipped=True, url_suffix="crossB",
        )

        rows = await database.get_recently_skipped(
            pool, guild_id="g14-skip3", since=since, limit=15
        )

        titles = {r["title"] for r in rows}
        assert titles == {"Song A", "Song B"}
        for r in rows:
            assert "user_id" not in r.keys()


# ---------------------------------------------------------------------------
# get_user_top_artist
# ---------------------------------------------------------------------------


class TestGetUserTopArtist:
    """Tests for get_user_top_artist — guild+invoker-scoped anchor (Option B, OQ2)."""

    @pytest.mark.asyncio
    async def test_ranks_by_play_count_within_guild_and_user(self, pool) -> None:
        guild_id, user_id = "g14-top1", "u-top1"
        now = datetime.now(timezone.utc)
        for i in range(3):
            await _insert_history_row(
                pool, guild_id=guild_id, user_id=user_id, artist="Heavy Rotation",
                queued_at=now - timedelta(hours=i), url_suffix=f"heavy{i}",
            )
        await _insert_history_row(
            pool, guild_id=guild_id, user_id=user_id, artist="One Timer",
            queued_at=now - timedelta(hours=5), url_suffix="onetime",
        )

        rows = await database.get_user_top_artist(
            pool, guild_id=guild_id, user_id=user_id, limit=5
        )

        assert rows[0]["artist"] == "Heavy Rotation"
        assert rows[0]["play_count"] == 3

    @pytest.mark.asyncio
    async def test_excludes_other_users_and_other_guilds(self, pool) -> None:
        now = datetime.now(timezone.utc)
        await _insert_history_row(
            pool, guild_id="g14-top2", user_id="u-other", artist="Not Mine",
            queued_at=now - timedelta(hours=1), url_suffix="notmine",
        )

        rows = await database.get_user_top_artist(
            pool, guild_id="g14-top2", user_id="u-top2", limit=5
        )

        assert rows == []


# ---------------------------------------------------------------------------
# get_artist_cooccurrence
# ---------------------------------------------------------------------------


class TestGetArtistCooccurrence:
    """Tests for get_artist_cooccurrence — guild-wide same-day co-occurrence (T-14-02)."""

    @pytest.mark.asyncio
    async def test_returns_same_day_co_occurring_artists_no_user_id(self, pool) -> None:
        guild_id = "g14-co1"
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=90)

        # anchor artist played by user-a
        await _insert_history_row(
            pool, guild_id=guild_id, user_id="u-a", artist="Anchor Artist",
            queued_at=now - timedelta(hours=3), url_suffix="anchor1",
        )
        # co-occurring artist played same day by a DIFFERENT user
        await _insert_history_row(
            pool, guild_id=guild_id, user_id="u-b", artist="Co-Occurring Artist",
            queued_at=now - timedelta(hours=1), url_suffix="co1",
        )
        # different day — must not appear
        await _insert_history_row(
            pool, guild_id=guild_id, user_id="u-a", artist="Different Day Artist",
            queued_at=now - timedelta(days=5), url_suffix="diffday",
        )

        rows = await database.get_artist_cooccurrence(
            pool, guild_id=guild_id, anchor_artist="Anchor Artist", since=since, limit=10
        )

        artists = {r["artist"] for r in rows}
        assert "Co-Occurring Artist" in artists
        assert "Anchor Artist" not in artists, "anchor artist must exclude itself"
        assert "Different Day Artist" not in artists
        for r in rows:
            assert "user_id" not in r.keys()

    @pytest.mark.asyncio
    async def test_scoped_to_guild(self, pool) -> None:
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=90)

        await _insert_history_row(
            pool, guild_id="g14-co2-A", user_id="u-a", artist="Anchor",
            queued_at=now - timedelta(hours=2), url_suffix="ganchorA",
        )
        await _insert_history_row(
            pool, guild_id="g14-co2-A", user_id="u-b", artist="Adjacent",
            queued_at=now - timedelta(hours=1), url_suffix="gadjA",
        )

        rows_other_guild = await database.get_artist_cooccurrence(
            pool, guild_id="g14-co2-B", anchor_artist="Anchor", since=since, limit=10
        )

        assert rows_other_guild == []
