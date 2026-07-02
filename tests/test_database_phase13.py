"""Phase 13 PostgreSQL integration tests — taste aggregate helpers + expires_at refresh.

Covers the three database.py helpers added for Semantic Music Memory
(TASTE-01/TASTE-02/TASTE-03):
  - get_active_taste_users   — candidate (guild_id, user_id) pairs active in a window
  - get_user_artist_activity — per-artist in-window vs before-window play/skip counts
  - refresh_memory_expiry    — D-05 self-refresh primitive (expires_at ONLY)

The pool fixture is defined in tests/conftest.py — it calls init_db, yields the
pool, and drops song_history/etc. on teardown. It does NOT drop user_memories
(Phase 11 rows persist across the test DB's lifetime), so tests that insert
into user_memories clean up their own rows via the `memory_cleanup` fixture
below.

Autonomous gate (no live DB needed): pytest --collect-only exits 0.
Full integration run: pytest tests/test_database_phase13.py -q (requires a
live dexter_test DB reachable per tests/conftest.py's pool fixture; skips
cleanly — not an error — when Postgres is unavailable).
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

import config
import database


# ---------------------------------------------------------------------------
# Static source-assertion checks — always run, no live DB needed
# ---------------------------------------------------------------------------


class TestTasteHelpersExist:
    """Verify all Task 1/2 artifacts exist with the right scoping (T-13-02/T-13-04/T-13-05)."""

    def test_get_active_taste_users_exists(self) -> None:
        assert hasattr(database, "get_active_taste_users"), (
            "get_active_taste_users must exist in database.py"
        )

    def test_get_user_artist_activity_exists(self) -> None:
        assert hasattr(database, "get_user_artist_activity"), (
            "get_user_artist_activity must exist in database.py"
        )

    def test_refresh_memory_expiry_exists(self) -> None:
        assert hasattr(database, "refresh_memory_expiry"), (
            "refresh_memory_expiry must exist in database.py"
        )

    def test_get_user_artist_activity_is_scoped(self) -> None:
        """get_user_artist_activity must scope by guild_id=$1 AND user_id=$2 (T-13-02)."""
        src = inspect.getsource(database.get_user_artist_activity)
        assert "WHERE guild_id = $1 AND user_id = $2" in src, (
            "get_user_artist_activity must include WHERE guild_id = $1 AND user_id = $2"
        )

    def test_refresh_memory_expiry_touches_only_expires_at(self) -> None:
        """refresh_memory_expiry must SET expires_at = $2 and touch nothing else (T-13-04)."""
        src = inspect.getsource(database.refresh_memory_expiry)
        assert "SET expires_at = $2" in src, (
            "refresh_memory_expiry must SET expires_at = $2"
        )
        # Check the SQL-assignment form (`column =`), not mere docstring mentions of
        # the column names (the docstring explicitly names them as NOT touched).
        for forbidden in ("hit_count =", "salience =", "last_seen_at ="):
            assert forbidden not in src, (
                f"refresh_memory_expiry must not touch {forbidden!r} —"
                " that is bump_memory_hit's job"
            )

    def test_no_string_interpolation(self) -> None:
        """None of the three new helpers may use f-strings or %-interpolated SQL (T-13-05)."""
        for fn in (
            database.get_active_taste_users,
            database.get_user_artist_activity,
            database.refresh_memory_expiry,
        ):
            src = inspect.getsource(fn)
            assert 'f"' not in src and "f'" not in src, (
                f"{fn.__name__} must not use f-string SQL (T-13-05)"
            )
            assert "%s" not in src, f"{fn.__name__} must not use %-interpolated SQL (T-13-05)"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def memory_cleanup(pool):
    """Track user_memories ids inserted during a test and delete them at teardown.

    conftest's pool fixture does NOT drop user_memories in teardown — this
    module inserts real rows via insert_memory for the refresh_memory_expiry
    round-trip, so it must clean up after itself (per plan 13-02 note).
    """
    ids: list[int] = []
    yield ids
    if ids:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM user_memories WHERE id = ANY($1)", ids)


async def _insert_history_row(
    pool,
    *,
    guild_id: str,
    user_id: str,
    artist: str | None,
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
            guild_id, user_id, "Test Song", artist,
            f"https://youtube.com/watch?v=test{url_suffix}", 200, queued_at, was_skipped,
        )


# ---------------------------------------------------------------------------
# get_active_taste_users
# ---------------------------------------------------------------------------


class TestGetActiveTasteUsers:
    """Tests for get_active_taste_users — candidate (guild_id, user_id) pairs."""

    @pytest.mark.asyncio
    async def test_includes_recent_active_user(self, pool) -> None:
        """A user with a play inside the window appears with the correct track count."""
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=3)
        await _insert_history_row(
            pool, guild_id="gtaste1", user_id="u-recent", artist="Radiohead",
            queued_at=now - timedelta(hours=1), url_suffix="recent1",
        )

        rows = await database.get_active_taste_users(pool, since=since)
        found = {(r["guild_id"], r["user_id"]): r["tracks_in_window"] for r in rows}

        assert ("gtaste1", "u-recent") in found
        assert found[("gtaste1", "u-recent")] == 1

    @pytest.mark.asyncio
    async def test_excludes_user_whose_plays_predate_since(self, pool) -> None:
        """A user whose only plays are before `since` must not appear in the result."""
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=3)
        await _insert_history_row(
            pool, guild_id="gtaste2", user_id="u-stale", artist="Old Band",
            queued_at=now - timedelta(days=10), url_suffix="stale1",
        )

        rows = await database.get_active_taste_users(pool, since=since)
        found_pairs = {(r["guild_id"], r["user_id"]) for r in rows}

        assert ("gtaste2", "u-stale") not in found_pairs


# ---------------------------------------------------------------------------
# get_user_artist_activity
# ---------------------------------------------------------------------------


class TestGetUserArtistActivity:
    """Tests for get_user_artist_activity — window/baseline splits + isolation."""

    @pytest.mark.asyncio
    async def test_window_and_baseline_splits(self, pool) -> None:
        """plays_in_window / plays_before_window / skips_in_window split correctly."""
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=7)
        baseline_since = now - timedelta(days=60)
        guild_id, user_id, artist = "gartist1", "u-artist", "The Killers"

        # 3 plays in-window (queued_at > since), one of them skipped
        for i in range(3):
            await _insert_history_row(
                pool, guild_id=guild_id, user_id=user_id, artist=artist,
                queued_at=now - timedelta(days=1, hours=i),
                was_skipped=(i == 0), url_suffix=f"win{i}",
            )
        # 2 plays before-window but within baseline (since >= queued_at > baseline_since)
        for i in range(2):
            await _insert_history_row(
                pool, guild_id=guild_id, user_id=user_id, artist=artist,
                queued_at=now - timedelta(days=20, hours=i), url_suffix=f"base{i}",
            )
        # 1 play beyond baseline_since — must be excluded entirely from all counts
        await _insert_history_row(
            pool, guild_id=guild_id, user_id=user_id, artist=artist,
            queued_at=now - timedelta(days=100), url_suffix="ancient",
        )

        rows = await database.get_user_artist_activity(
            pool, guild_id=guild_id, user_id=user_id,
            since=since, baseline_since=baseline_since,
        )

        assert len(rows) == 1, "Only one artist was seeded; exactly one row expected"
        row = rows[0]
        assert row["artist"] == artist
        assert row["plays_in_window"] == 3
        assert row["plays_before_window"] == 2
        assert row["skips_in_window"] == 1

    @pytest.mark.asyncio
    async def test_cross_guild_isolation(self, pool) -> None:
        """A guild-A artist row must not appear when querying guild-B (T-13-02)."""
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=7)
        baseline_since = now - timedelta(days=60)

        await _insert_history_row(
            pool, guild_id="gartist-A", user_id="u-shared", artist="Mac DeMarco",
            queued_at=now - timedelta(hours=1), url_suffix="crossA",
        )

        rows_b = await database.get_user_artist_activity(
            pool, guild_id="gartist-B", user_id="u-shared",
            since=since, baseline_since=baseline_since,
        )

        assert rows_b == [], "guild-B query must not see guild-A's artist activity"


# ---------------------------------------------------------------------------
# refresh_memory_expiry
# ---------------------------------------------------------------------------


class TestRefreshMemoryExpiry:
    """Tests for refresh_memory_expiry — D-05 expires_at-only self-refresh."""

    @pytest.mark.asyncio
    async def test_refresh_advances_expiry_without_touching_other_columns(
        self, pool, memory_cleanup
    ) -> None:
        """expires_at advances; hit_count/salience/last_seen_at stay byte-identical."""
        embedding = [0.5] * config.EMBED_DIM
        original_expires = datetime.now(timezone.utc) + timedelta(days=5)

        memory_id = await database.insert_memory(
            pool,
            user_id="test-phase13-refresh",
            guild_id=None,
            kind="taste_episode",
            fact="user keeps coming back to mac demarco",
            embedding=embedding,
            salience=0.4,
            expires_at=original_expires,
        )
        memory_cleanup.append(memory_id)

        async with pool.acquire() as conn:
            before = await conn.fetchrow(
                "SELECT hit_count, salience, last_seen_at, expires_at"
                " FROM user_memories WHERE id = $1",
                memory_id,
            )

        new_expires = datetime.now(timezone.utc) + timedelta(days=30)
        await database.refresh_memory_expiry(pool, memory_id, new_expires)

        async with pool.acquire() as conn:
            after = await conn.fetchrow(
                "SELECT hit_count, salience, last_seen_at, expires_at"
                " FROM user_memories WHERE id = $1",
                memory_id,
            )

        assert after["expires_at"] > before["expires_at"], "expires_at must advance"
        assert after["hit_count"] == before["hit_count"], "hit_count must be untouched"
        assert float(after["salience"]) == float(before["salience"]), (
            "salience must be untouched"
        )
        assert after["last_seen_at"] == before["last_seen_at"], (
            "last_seen_at must be untouched"
        )
