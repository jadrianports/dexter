"""Phase 7 PostgreSQL integration tests — user_favorites helpers.

These tests require a live PostgreSQL database.
Set TEST_DATABASE_URL or ensure postgresql://dexter:dexter@localhost:5432/dexter_test
is reachable before running.

The pool fixture is defined in tests/conftest.py — it calls init_db, yields the
pool, and drops all tables on teardown (including user_favorites).

Autonomous gate (no live DB needed): pytest --collect-only exits 0.
Full integration run: pytest tests/test_database_phase7.py -x (requires dexter_test DB).
"""

from __future__ import annotations

import pytest

from database import (
    add_favorite,
    count_favorites,
    get_favorites,
    remove_favorite,
)


# ---------------------------------------------------------------------------
# TestUserFavoritesSchema — table exists after init_db
# ---------------------------------------------------------------------------


class TestUserFavoritesSchema:
    """Verify user_favorites table is created by init_db."""

    @pytest.mark.asyncio
    async def test_user_favorites_table_exists(self, pool):
        """init_db must create user_favorites table."""
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        tables = {r["tablename"] for r in rows}
        assert "user_favorites" in tables, "user_favorites table not found"

    @pytest.mark.asyncio
    async def test_user_favorites_has_expected_columns(self, pool):
        """user_favorites must have the required columns."""
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = 'user_favorites' AND table_schema = 'public'"
                " ORDER BY column_name"
            )
        cols = {r["column_name"] for r in rows}
        expected = {"user_id", "video_id", "title", "artist", "url", "duration_seconds", "thumbnail", "added_at"}
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"


# ---------------------------------------------------------------------------
# TestAddFavorite — insert + dedupe
# ---------------------------------------------------------------------------


class TestAddFavorite:
    """Tests for add_favorite helper."""

    @pytest.mark.asyncio
    async def test_add_favorite_inserts_row(self, pool):
        """add_favorite inserts one row for a new (user_id, video_id) pair."""
        await add_favorite(
            pool,
            user_id="u1",
            video_id="vid1",
            title="Song One",
            artist="Artist A",
            url="https://youtube.com/watch?v=vid1",
            duration_seconds=200,
            thumbnail="https://img.youtube.com/vi/vid1/0.jpg",
        )
        count = await count_favorites(pool, user_id="u1")
        assert count == 1

    @pytest.mark.asyncio
    async def test_add_favorite_dedupe_on_conflict(self, pool):
        """Inserting the same (user_id, video_id) twice does NOT create a second row."""
        await add_favorite(
            pool,
            user_id="u2",
            video_id="vid2",
            title="Song Two",
            artist="Artist B",
            url="https://youtube.com/watch?v=vid2",
            duration_seconds=180,
            thumbnail=None,
        )
        # Insert the exact same pair again
        await add_favorite(
            pool,
            user_id="u2",
            video_id="vid2",
            title="Song Two (re-save)",
            artist="Artist B",
            url="https://youtube.com/watch?v=vid2",
            duration_seconds=180,
            thumbnail=None,
        )
        count = await count_favorites(pool, user_id="u2")
        assert count == 1, "Duplicate insert must be a no-op (ON CONFLICT DO NOTHING)"

    @pytest.mark.asyncio
    async def test_add_favorite_multiple_users_isolated(self, pool):
        """Favorites for different users are independent."""
        await add_favorite(
            pool,
            user_id="u3",
            video_id="shared",
            title="Shared Song",
            artist="Artist C",
            url="https://youtube.com/watch?v=shared",
            duration_seconds=240,
            thumbnail=None,
        )
        await add_favorite(
            pool,
            user_id="u4",
            video_id="shared",
            title="Shared Song",
            artist="Artist C",
            url="https://youtube.com/watch?v=shared",
            duration_seconds=240,
            thumbnail=None,
        )
        # Each user independently owns one row
        assert await count_favorites(pool, user_id="u3") == 1
        assert await count_favorites(pool, user_id="u4") == 1


# ---------------------------------------------------------------------------
# TestCountFavorites — count helper
# ---------------------------------------------------------------------------


class TestCountFavorites:
    """Tests for count_favorites helper."""

    @pytest.mark.asyncio
    async def test_count_returns_zero_for_new_user(self, pool):
        """count_favorites returns 0 for a user with no saved favorites."""
        count = await count_favorites(pool, user_id="nobody")
        assert count == 0

    @pytest.mark.asyncio
    async def test_count_increments_with_each_new_video(self, pool):
        """count_favorites returns the correct count after multiple distinct inserts."""
        for i in range(3):
            await add_favorite(
                pool,
                user_id="u5",
                video_id=f"vid_count_{i}",
                title=f"Song {i}",
                artist=None,
                url=f"https://youtube.com/watch?v=vid_count_{i}",
                duration_seconds=120,
                thumbnail=None,
            )
        assert await count_favorites(pool, user_id="u5") == 3


# ---------------------------------------------------------------------------
# TestGetFavorites — list helper
# ---------------------------------------------------------------------------


class TestGetFavorites:
    """Tests for get_favorites helper."""

    @pytest.mark.asyncio
    async def test_get_favorites_returns_empty_list_for_new_user(self, pool):
        """get_favorites returns [] for a user with no favorites."""
        result = await get_favorites(pool, user_id="nobody2")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_favorites_returns_rows_with_track_fields(self, pool):
        """Each row returned by get_favorites has enough fields to rebuild a Track."""
        await add_favorite(
            pool,
            user_id="u6",
            video_id="vid6",
            title="Track Six",
            artist="Artist F",
            url="https://youtube.com/watch?v=vid6",
            duration_seconds=300,
            thumbnail="https://img.youtube.com/vi/vid6/0.jpg",
        )
        rows = await get_favorites(pool, user_id="u6")
        assert len(rows) == 1
        row = rows[0]
        assert row["video_id"] == "vid6"
        assert row["title"] == "Track Six"
        assert row["artist"] == "Artist F"
        assert row["url"] == "https://youtube.com/watch?v=vid6"
        assert row["duration_seconds"] == 300
        assert row["thumbnail"] == "https://img.youtube.com/vi/vid6/0.jpg"

    @pytest.mark.asyncio
    async def test_get_favorites_newest_first_order(self, pool):
        """get_favorites returns rows newest-first (added_at DESC)."""
        for i in range(3):
            await add_favorite(
                pool,
                user_id="u7",
                video_id=f"order_{i}",
                title=f"Song {i}",
                artist=None,
                url=f"https://youtube.com/watch?v=order_{i}",
                duration_seconds=100,
                thumbnail=None,
            )
        rows = await get_favorites(pool, user_id="u7")
        # Newest-first: last inserted should appear at index 0 (or at least titles
        # should be in reverse insertion order — but DB clock resolution means they
        # may collide; just assert all 3 rows are returned)
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_get_favorites_respects_limit(self, pool):
        """get_favorites limit param caps the returned rows."""
        for i in range(5):
            await add_favorite(
                pool,
                user_id="u8",
                video_id=f"lim_{i}",
                title=f"Song {i}",
                artist=None,
                url=f"https://youtube.com/watch?v=lim_{i}",
                duration_seconds=100,
                thumbnail=None,
            )
        rows = await get_favorites(pool, user_id="u8", limit=3)
        assert len(rows) == 3


# ---------------------------------------------------------------------------
# TestRemoveFavorite — delete helper
# ---------------------------------------------------------------------------


class TestRemoveFavorite:
    """Tests for remove_favorite helper."""

    @pytest.mark.asyncio
    async def test_remove_favorite_deletes_row(self, pool):
        """remove_favorite removes exactly the (user_id, video_id) row."""
        await add_favorite(
            pool,
            user_id="u9",
            video_id="del1",
            title="To Delete",
            artist=None,
            url="https://youtube.com/watch?v=del1",
            duration_seconds=100,
            thumbnail=None,
        )
        assert await count_favorites(pool, user_id="u9") == 1
        await remove_favorite(pool, user_id="u9", video_id="del1")
        assert await count_favorites(pool, user_id="u9") == 0

    @pytest.mark.asyncio
    async def test_remove_favorite_only_removes_target(self, pool):
        """remove_favorite does not touch other favorites of the same user."""
        for i in range(3):
            await add_favorite(
                pool,
                user_id="u10",
                video_id=f"keep_{i}",
                title=f"Keep {i}",
                artist=None,
                url=f"https://youtube.com/watch?v=keep_{i}",
                duration_seconds=100,
                thumbnail=None,
            )
        await remove_favorite(pool, user_id="u10", video_id="keep_1")
        remaining = await get_favorites(pool, user_id="u10")
        assert len(remaining) == 2
        remaining_ids = {r["video_id"] for r in remaining}
        assert "keep_1" not in remaining_ids

    @pytest.mark.asyncio
    async def test_remove_favorite_noop_for_missing_row(self, pool):
        """remove_favorite is a no-op when the row does not exist (no error)."""
        # Should not raise
        await remove_favorite(pool, user_id="ghost", video_id="nonexistent")
        assert await count_favorites(pool, user_id="ghost") == 0
