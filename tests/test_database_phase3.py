"""Tests for Phase 3 database helpers: streak migration, repeat-song count,
update_user_streak, and get_history_rows.

All tests use an in-memory aiosqlite DB — never mutates data/dexter.db.
Pattern: same in-memory + pytest-asyncio fixture as test_database_phase2.py.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import aiosqlite

import config
from database import (
    init_db,
    log_song,
    migrate_add_streak_columns,
    get_repeat_song_count,
    update_user_streak,
    get_history_rows,
    update_user_profile,
)


@pytest_asyncio.fixture
async def db():
    """In-memory SQLite with full schema and migrations applied."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db(conn)
    yield conn
    await conn.close()


# ---------------------------------------------------------------------------
# SCHEMA — streak columns present after init_db
# ---------------------------------------------------------------------------

class TestSchemaStreakColumns:
    @pytest.mark.asyncio
    async def test_current_streak_column_exists(self, db):
        cursor = await db.execute("PRAGMA table_info(user_profiles)")
        cols = {row["name"] for row in await cursor.fetchall()}
        assert "current_streak" in cols

    @pytest.mark.asyncio
    async def test_longest_streak_column_exists(self, db):
        cursor = await db.execute("PRAGMA table_info(user_profiles)")
        cols = {row["name"] for row in await cursor.fetchall()}
        assert "longest_streak" in cols

    @pytest.mark.asyncio
    async def test_last_streak_date_column_exists(self, db):
        cursor = await db.execute("PRAGMA table_info(user_profiles)")
        cols = {row["name"] for row in await cursor.fetchall()}
        assert "last_streak_date" in cols


# ---------------------------------------------------------------------------
# migrate_add_streak_columns — idempotency
# ---------------------------------------------------------------------------

class TestMigrateAddStreakColumns:
    @pytest.mark.asyncio
    async def test_idempotent_does_not_raise_on_second_call(self, db):
        """Running migration twice must not raise (columns already present)."""
        # First call happens inside init_db; second call here must be a no-op
        await migrate_add_streak_columns(db)  # second run — must not raise

    @pytest.mark.asyncio
    async def test_migration_adds_columns_to_existing_table(self):
        """Migration on a table without streak cols adds them correctly."""
        # Create a stripped table (no streak columns) then migrate
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        try:
            # Minimal user_profiles without streak columns
            await conn.executescript("""
                CREATE TABLE user_profiles (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    total_songs_queued INTEGER DEFAULT 0,
                    first_seen_at TEXT DEFAULT (datetime('now')),
                    last_active_at TEXT DEFAULT (datetime('now'))
                );
            """)
            await conn.commit()

            # Columns should not exist yet
            cursor = await conn.execute("PRAGMA table_info(user_profiles)")
            cols_before = {row["name"] for row in await cursor.fetchall()}
            assert "current_streak" not in cols_before

            # Run migration
            await migrate_add_streak_columns(conn)

            # Now they must be present
            cursor = await conn.execute("PRAGMA table_info(user_profiles)")
            cols_after = {row["name"] for row in await cursor.fetchall()}
            assert "current_streak" in cols_after
            assert "longest_streak" in cols_after
            assert "last_streak_date" in cols_after
        finally:
            await conn.close()


# ---------------------------------------------------------------------------
# get_repeat_song_count — PERS-04 seam
# ---------------------------------------------------------------------------

class TestGetRepeatSongCount:
    @pytest.mark.asyncio
    async def test_returns_zero_when_no_songs(self, db):
        count = await get_repeat_song_count(
            db, guild_id="g1", user_id="u1", title="Never Played"
        )
        assert count == 0

    @pytest.mark.asyncio
    async def test_counts_one_play(self, db):
        await log_song(
            db, guild_id="g1", user_id="u1", title="Repeat Song",
            artist="Artist", url="https://yt.com/1", duration=200,
        )
        count = await get_repeat_song_count(
            db, guild_id="g1", user_id="u1", title="Repeat Song"
        )
        assert count == 1

    @pytest.mark.asyncio
    async def test_returns_3_after_three_same_title_inserts(self, db):
        """Core PERS-04 assertion: 3 plays returns >= REPEAT_SONG_ROAST_THRESHOLD."""
        for i in range(3):
            await log_song(
                db, guild_id="g1", user_id="u1", title="Overplayed",
                artist="Artist", url=f"https://yt.com/{i}", duration=200,
            )
        count = await get_repeat_song_count(
            db, guild_id="g1", user_id="u1", title="Overplayed"
        )
        assert count >= config.REPEAT_SONG_ROAST_THRESHOLD
        assert count == 3

    @pytest.mark.asyncio
    async def test_filters_by_user(self, db):
        await log_song(
            db, guild_id="g1", user_id="u1", title="Song",
            artist="A", url="https://yt.com/1", duration=100,
        )
        count = await get_repeat_song_count(
            db, guild_id="g1", user_id="u2", title="Song"
        )
        assert count == 0

    @pytest.mark.asyncio
    async def test_filters_by_guild(self, db):
        await log_song(
            db, guild_id="g1", user_id="u1", title="Song",
            artist="A", url="https://yt.com/1", duration=100,
        )
        count = await get_repeat_song_count(
            db, guild_id="g2", user_id="u1", title="Song"
        )
        assert count == 0

    @pytest.mark.asyncio
    async def test_case_sensitive_title_match(self, db):
        await log_song(
            db, guild_id="g1", user_id="u1", title="Song A",
            artist="A", url="https://yt.com/1", duration=100,
        )
        count = await get_repeat_song_count(
            db, guild_id="g1", user_id="u1", title="song a"
        )
        # SQLite default text comparison is case-sensitive for ASCII
        assert count == 0


# ---------------------------------------------------------------------------
# update_user_streak — PERS-09 seam
# ---------------------------------------------------------------------------

class TestUpdateUserStreak:
    @pytest.mark.asyncio
    async def test_first_call_sets_streak_to_1(self, db):
        """User with no profile: streak starts at 1."""
        await update_user_profile(db, user_id="u1", username="Alice")
        new_streak, new_longest, milestone = await update_user_streak(
            db, user_id="u1", tz_name=config.STREAK_TIMEZONE
        )
        assert new_streak == 1

    @pytest.mark.asyncio
    async def test_first_call_longest_streak_is_1(self, db):
        await update_user_profile(db, user_id="u1", username="Alice")
        new_streak, new_longest, milestone = await update_user_streak(
            db, user_id="u1", tz_name=config.STREAK_TIMEZONE
        )
        assert new_longest == 1

    @pytest.mark.asyncio
    async def test_same_day_call_is_noop(self, db):
        """Calling update_user_streak twice on same day keeps streak at 1."""
        await update_user_profile(db, user_id="u1", username="Alice")
        await update_user_streak(db, user_id="u1", tz_name=config.STREAK_TIMEZONE)
        new_streak, _, _ = await update_user_streak(
            db, user_id="u1", tz_name=config.STREAK_TIMEZONE
        )
        assert new_streak == 1

    @pytest.mark.asyncio
    async def test_persists_current_streak_to_db(self, db):
        """After update_user_streak, SELECT confirms current_streak was written."""
        await update_user_profile(db, user_id="u1", username="Alice")
        await update_user_streak(db, user_id="u1", tz_name=config.STREAK_TIMEZONE)
        cursor = await db.execute(
            "SELECT current_streak FROM user_profiles WHERE user_id='u1'"
        )
        row = await cursor.fetchone()
        assert row["current_streak"] == 1

    @pytest.mark.asyncio
    async def test_persists_last_streak_date_to_db(self, db):
        from database import get_local_date
        await update_user_profile(db, user_id="u1", username="Alice")
        await update_user_streak(db, user_id="u1", tz_name=config.STREAK_TIMEZONE)
        cursor = await db.execute(
            "SELECT last_streak_date FROM user_profiles WHERE user_id='u1'"
        )
        row = await cursor.fetchone()
        today_iso = get_local_date(config.STREAK_TIMEZONE).isoformat()
        assert row["last_streak_date"] == today_iso

    @pytest.mark.asyncio
    async def test_milestone_fires_at_threshold_7(self, db):
        """update_user_streak returns milestone when current_streak crosses to 7."""
        from database import get_local_date
        from datetime import timedelta

        await update_user_profile(db, user_id="u_mile", username="Bob")
        today = get_local_date(config.STREAK_TIMEZONE)

        # Manually set user to streak=6 with last_streak_date = yesterday
        yesterday = (today - timedelta(days=1)).isoformat()
        await db.execute(
            """UPDATE user_profiles
               SET current_streak=6, longest_streak=6, last_streak_date=?
               WHERE user_id='u_mile'""",
            (yesterday,),
        )
        await db.commit()

        new_streak, new_longest, milestone = await update_user_streak(
            db, user_id="u_mile", tz_name=config.STREAK_TIMEZONE
        )
        assert new_streak == 7
        assert milestone == 7

    @pytest.mark.asyncio
    async def test_no_milestone_below_threshold(self, db):
        """streak=2 (non-milestone value) returns None for milestone."""
        from database import get_local_date
        from datetime import timedelta

        await update_user_profile(db, user_id="u_nomile", username="Carol")
        today = get_local_date(config.STREAK_TIMEZONE)
        yesterday = (today - timedelta(days=1)).isoformat()

        await db.execute(
            """UPDATE user_profiles
               SET current_streak=1, longest_streak=1, last_streak_date=?
               WHERE user_id='u_nomile'""",
            (yesterday,),
        )
        await db.commit()

        new_streak, _, milestone = await update_user_streak(
            db, user_id="u_nomile", tz_name=config.STREAK_TIMEZONE
        )
        assert new_streak == 2
        assert milestone is None

    @pytest.mark.asyncio
    async def test_longest_streak_updated_when_new_streak_exceeds(self, db):
        """longest_streak rises when current_streak surpasses it."""
        from database import get_local_date
        from datetime import timedelta

        await update_user_profile(db, user_id="u_long", username="Dave")
        today = get_local_date(config.STREAK_TIMEZONE)
        yesterday = (today - timedelta(days=1)).isoformat()

        await db.execute(
            """UPDATE user_profiles
               SET current_streak=5, longest_streak=5, last_streak_date=?
               WHERE user_id='u_long'""",
            (yesterday,),
        )
        await db.commit()

        _, new_longest, _ = await update_user_streak(
            db, user_id="u_long", tz_name=config.STREAK_TIMEZONE
        )
        assert new_longest == 6


# ---------------------------------------------------------------------------
# get_history_rows — HIST-01 data source
# ---------------------------------------------------------------------------

class TestGetHistoryRows:
    @pytest.mark.asyncio
    async def test_returns_empty_for_new_guild(self, db):
        rows = await get_history_rows(db, guild_id="g_empty")
        assert rows == []

    @pytest.mark.asyncio
    async def test_returns_required_keys(self, db):
        await log_song(
            db, guild_id="g1", user_id="u1", title="Test Song",
            artist="Test Artist", url="https://yt.com/1", duration=300,
        )
        rows = await get_history_rows(db, guild_id="g1")
        assert len(rows) == 1
        row = rows[0]
        for key in ("title", "artist", "user_id", "queued_at"):
            assert key in row, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_returns_newest_first(self, db):
        await log_song(
            db, guild_id="g1", user_id="u1", title="Old",
            artist="A", url="https://yt.com/1", duration=100,
        )
        await log_song(
            db, guild_id="g1", user_id="u1", title="New",
            artist="B", url="https://yt.com/2", duration=100,
        )
        rows = await get_history_rows(db, guild_id="g1")
        assert rows[0]["title"] == "New"
        assert rows[1]["title"] == "Old"

    @pytest.mark.asyncio
    async def test_respects_limit(self, db):
        for i in range(10):
            await log_song(
                db, guild_id="g1", user_id="u1", title=f"Song {i}",
                artist="A", url=f"https://yt.com/{i}", duration=100,
            )
        rows = await get_history_rows(db, guild_id="g1", limit=5)
        assert len(rows) == 5

    @pytest.mark.asyncio
    async def test_filters_by_guild(self, db):
        await log_song(
            db, guild_id="g1", user_id="u1", title="G1 Song",
            artist="A", url="https://yt.com/1", duration=100,
        )
        await log_song(
            db, guild_id="g2", user_id="u1", title="G2 Song",
            artist="A", url="https://yt.com/2", duration=100,
        )
        rows = await get_history_rows(db, guild_id="g1")
        assert len(rows) == 1
        assert rows[0]["title"] == "G1 Song"

    @pytest.mark.asyncio
    async def test_limit_is_respected_as_int(self, db):
        """LIMIT must be bound as an int parameter, not a string (T-03-03)."""
        for i in range(5):
            await log_song(
                db, guild_id="g1", user_id="u1", title=f"Song {i}",
                artist="A", url=f"https://yt.com/{i}", duration=100,
            )
        # limit=3 — verify we get exactly 3 rows back (not all 5)
        rows = await get_history_rows(db, guild_id="g1", limit=3)
        assert len(rows) == 3
