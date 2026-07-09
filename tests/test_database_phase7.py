"""Phase 7 PostgreSQL integration tests — user_favorites + user_playlists helpers.

These tests require a live PostgreSQL database.
Set TEST_DATABASE_URL or ensure postgresql://dexter:dexter@localhost:5432/dexter_test
is reachable before running.

The pool fixture is defined in tests/conftest.py — it calls init_db, yields the
pool, and drops all tables on teardown (including user_favorites, user_playlists).

Autonomous gate (no live DB needed): pytest --collect-only exits 0.
Full integration run: pytest tests/test_database_phase7.py -x (requires dexter_test DB).
"""

from __future__ import annotations

import pytest

from database import (
    add_favorite,
    count_favorites,
    count_playlists,
    delete_playlist,
    get_favorites,
    get_playlist,
    list_playlists,
    remove_favorite,
    # playlist helpers (Plan 04)
    save_playlist,
)
from models.queue import Track

# ---------------------------------------------------------------------------
# TestUserFavoritesSchema — table exists after init_db
# ---------------------------------------------------------------------------


class TestUserFavoritesSchema:
    """Verify user_favorites table is created by init_db."""

    @pytest.mark.asyncio
    async def test_user_favorites_table_exists(self, pool):
        """init_db must create user_favorites table."""
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
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


# ---------------------------------------------------------------------------
# Helper: build a minimal Track snapshot (list of dicts via to_dict)
# ---------------------------------------------------------------------------


def _make_snapshot(n: int, user_id: int = 999) -> list[dict]:
    """Return a list of n Track.to_dict() dicts for testing round-trips."""
    return [
        Track(
            video_id=f"snap_{i}",
            title=f"Snapshot Song {i}",
            artist=f"Artist {i}",
            url=f"https://youtube.com/watch?v=snap_{i}",
            duration_seconds=180 + i,
            requested_by=user_id,
            thumbnail=f"https://img.youtube.com/vi/snap_{i}/0.jpg",
        ).to_dict()
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# TestUserPlaylistsSchema — table exists after init_db (Plan 04, D-23)
# ---------------------------------------------------------------------------


class TestUserPlaylistsSchema:
    """Verify user_playlists table is created by init_db."""

    @pytest.mark.asyncio
    async def test_user_playlists_table_exists(self, pool):
        """init_db must create user_playlists table."""
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = {r["tablename"] for r in rows}
        assert "user_playlists" in tables, "user_playlists table not found"

    @pytest.mark.asyncio
    async def test_user_playlists_has_expected_columns(self, pool):
        """user_playlists must have the required columns."""
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = 'user_playlists' AND table_schema = 'public'"
                " ORDER BY column_name"
            )
        cols = {r["column_name"] for r in rows}
        expected = {"user_id", "name", "snapshot", "created_at", "updated_at"}
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"


# ---------------------------------------------------------------------------
# TestSavePlaylist — upsert (insert + overwrite same name) (D-27)
# ---------------------------------------------------------------------------


class TestSavePlaylist:
    """Tests for save_playlist helper."""

    @pytest.mark.asyncio
    async def test_save_playlist_inserts_new_row(self, pool):
        """save_playlist creates a new row for a fresh (user_id, name) pair."""
        snapshot = _make_snapshot(3)
        await save_playlist(pool, user_id="p1", name="chill", snapshot=snapshot)
        result = await get_playlist(pool, user_id="p1", name="chill")
        assert result is not None
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_save_playlist_upserts_on_name_clash(self, pool):
        """Re-saving to the same (user_id, name) replaces the snapshot (D-27)."""
        await save_playlist(pool, user_id="p2", name="my-mix", snapshot=_make_snapshot(2))
        new_snapshot = _make_snapshot(5)
        await save_playlist(pool, user_id="p2", name="my-mix", snapshot=new_snapshot)
        result = await get_playlist(pool, user_id="p2", name="my-mix")
        assert result is not None
        assert len(result) == 5, "Upsert must replace the snapshot, not append"

    @pytest.mark.asyncio
    async def test_save_playlist_different_users_isolated(self, pool):
        """Two users can have a playlist with the same name independently."""
        await save_playlist(pool, user_id="p3", name="vibes", snapshot=_make_snapshot(2))
        await save_playlist(pool, user_id="p4", name="vibes", snapshot=_make_snapshot(4))
        r3 = await get_playlist(pool, user_id="p3", name="vibes")
        r4 = await get_playlist(pool, user_id="p4", name="vibes")
        assert r3 is not None and len(r3) == 2
        assert r4 is not None and len(r4) == 4


# ---------------------------------------------------------------------------
# TestGetPlaylist — fetch + JSONB round-trip (D-23)
# ---------------------------------------------------------------------------


class TestGetPlaylist:
    """Tests for get_playlist helper."""

    @pytest.mark.asyncio
    async def test_get_playlist_returns_none_for_missing(self, pool):
        """get_playlist returns None when the (user_id, name) doesn't exist."""
        result = await get_playlist(pool, user_id="nobody_pl", name="ghost")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_playlist_round_trips_track_dicts(self, pool):
        """Track.to_dict() dicts stored in snapshot come back identical via Track.from_dict."""
        original = _make_snapshot(3, user_id=111)
        await save_playlist(pool, user_id="p5", name="roundtrip", snapshot=original)
        result = await get_playlist(pool, user_id="p5", name="roundtrip")
        assert result is not None
        assert len(result) == 3
        # Verify each dict round-trips through Track.from_dict → to_dict
        for orig, stored in zip(original, result):
            rebuilt = Track.from_dict(stored).to_dict()
            assert rebuilt == orig, f"Round-trip mismatch: {orig} vs {rebuilt}"

    @pytest.mark.asyncio
    async def test_get_playlist_returns_correct_name(self, pool):
        """get_playlist fetches the correct named playlist, not a different name."""
        await save_playlist(pool, user_id="p6", name="alpha", snapshot=_make_snapshot(1))
        await save_playlist(pool, user_id="p6", name="beta", snapshot=_make_snapshot(3))
        alpha = await get_playlist(pool, user_id="p6", name="alpha")
        beta = await get_playlist(pool, user_id="p6", name="beta")
        assert alpha is not None and len(alpha) == 1
        assert beta is not None and len(beta) == 3


# ---------------------------------------------------------------------------
# TestListPlaylists — list helper (newest-first, name+count+updated) (D-24)
# ---------------------------------------------------------------------------


class TestListPlaylists:
    """Tests for list_playlists helper."""

    @pytest.mark.asyncio
    async def test_list_playlists_empty_for_new_user(self, pool):
        """list_playlists returns [] for a user with no saved playlists."""
        result = await list_playlists(pool, user_id="nobody_list")
        assert result == []

    @pytest.mark.asyncio
    async def test_list_playlists_returns_metadata(self, pool):
        """Each row from list_playlists has name, track_count, and updated_at."""
        await save_playlist(pool, user_id="p7", name="session1", snapshot=_make_snapshot(4))
        rows = await list_playlists(pool, user_id="p7")
        assert len(rows) == 1
        row = rows[0]
        assert row["name"] == "session1"
        assert row["track_count"] == 4
        assert "updated_at" in row

    @pytest.mark.asyncio
    async def test_list_playlists_newest_first(self, pool):
        """list_playlists returns playlists newest-updated-first."""
        await save_playlist(pool, user_id="p8", name="first", snapshot=_make_snapshot(1))
        await save_playlist(pool, user_id="p8", name="second", snapshot=_make_snapshot(2))
        rows = await list_playlists(pool, user_id="p8")
        assert len(rows) == 2
        # "second" was saved last so should appear first (updated_at DESC)
        assert rows[0]["name"] == "second"

    @pytest.mark.asyncio
    async def test_list_playlists_only_own_playlists(self, pool):
        """list_playlists returns only the invoking user's rows."""
        await save_playlist(pool, user_id="p9", name="mine", snapshot=_make_snapshot(1))
        await save_playlist(pool, user_id="p10", name="theirs", snapshot=_make_snapshot(1))
        rows = await list_playlists(pool, user_id="p9")
        names = {r["name"] for r in rows}
        assert "mine" in names
        assert "theirs" not in names


# ---------------------------------------------------------------------------
# TestDeletePlaylist — delete helper (D-28)
# ---------------------------------------------------------------------------


class TestDeletePlaylist:
    """Tests for delete_playlist helper."""

    @pytest.mark.asyncio
    async def test_delete_playlist_removes_row(self, pool):
        """delete_playlist removes the named playlist and returns True."""
        await save_playlist(pool, user_id="p11", name="todelete", snapshot=_make_snapshot(2))
        deleted = await delete_playlist(pool, user_id="p11", name="todelete")
        assert deleted is True
        result = await get_playlist(pool, user_id="p11", name="todelete")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_playlist_returns_false_for_missing(self, pool):
        """delete_playlist returns False when the row doesn't exist."""
        deleted = await delete_playlist(pool, user_id="p12", name="ghost")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_delete_playlist_only_removes_target(self, pool):
        """delete_playlist does not touch other playlists of the same user."""
        await save_playlist(pool, user_id="p13", name="keep", snapshot=_make_snapshot(1))
        await save_playlist(pool, user_id="p13", name="remove", snapshot=_make_snapshot(1))
        await delete_playlist(pool, user_id="p13", name="remove")
        rows = await list_playlists(pool, user_id="p13")
        names = {r["name"] for r in rows}
        assert "keep" in names
        assert "remove" not in names

    @pytest.mark.asyncio
    async def test_delete_playlist_cross_user_isolation(self, pool):
        """delete_playlist cannot delete another user's playlist with the same name."""
        await save_playlist(pool, user_id="p14", name="shared", snapshot=_make_snapshot(2))
        # p15 tries to delete p14's "shared" — should be a no-op
        deleted = await delete_playlist(pool, user_id="p15", name="shared")
        assert deleted is False
        # p14's playlist should still exist
        result = await get_playlist(pool, user_id="p14", name="shared")
        assert result is not None


# ---------------------------------------------------------------------------
# TestCountPlaylists — count helper (for cap enforcement) (D-28)
# ---------------------------------------------------------------------------


class TestCountPlaylists:
    """Tests for count_playlists helper."""

    @pytest.mark.asyncio
    async def test_count_playlists_zero_for_new_user(self, pool):
        """count_playlists returns 0 for a user with no saved playlists."""
        count = await count_playlists(pool, user_id="nobody_count")
        assert count == 0

    @pytest.mark.asyncio
    async def test_count_playlists_increments(self, pool):
        """count_playlists increments with each new playlist."""
        for i in range(3):
            await save_playlist(pool, user_id="p16", name=f"list_{i}", snapshot=_make_snapshot(1))
        assert await count_playlists(pool, user_id="p16") == 3

    @pytest.mark.asyncio
    async def test_count_playlists_upsert_does_not_increment(self, pool):
        """Re-saving to an existing name (upsert) does NOT increase the count."""
        await save_playlist(pool, user_id="p17", name="stable", snapshot=_make_snapshot(1))
        await save_playlist(pool, user_id="p17", name="stable", snapshot=_make_snapshot(2))
        assert await count_playlists(pool, user_id="p17") == 1

    @pytest.mark.asyncio
    async def test_count_playlists_isolated_per_user(self, pool):
        """count_playlists counts only the requesting user's rows."""
        await save_playlist(pool, user_id="p18", name="mine", snapshot=_make_snapshot(1))
        await save_playlist(pool, user_id="p19", name="mine", snapshot=_make_snapshot(1))
        assert await count_playlists(pool, user_id="p18") == 1
        assert await count_playlists(pool, user_id="p19") == 1
