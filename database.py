"""SQLite database initialization and query helpers."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import aiosqlite

import config
from utils.logger import log

# ---------------------------------------------------------------------------
# Pure streak helper functions (no DB, no Discord — unit-testable seam)
# ---------------------------------------------------------------------------


def get_local_date(tz_name: str) -> date:
    """Return today's date in the given IANA timezone.

    Uses datetime.now(tz=ZoneInfo(tz_name)).date() — NOT date.today() or
    datetime.utcnow() — so DST and UTC offset are handled correctly (D-17,
    Pitfall 3).
    """
    return datetime.now(tz=ZoneInfo(tz_name)).date()


def compute_streak(
    current_streak: int,
    last_streak_date: str | None,
    tz_name: str,
) -> tuple[int, str]:
    """Return (new_streak, new_last_date) based on D-18 strict-reset rules.

    Rules:
    - last_streak_date is None  → first activity; return (1, today_iso)
    - delta == 0 (same day)     → no-op; return (current_streak, last_streak_date)
    - delta == 1 (consecutive)  → increment; return (current_streak + 1, today_iso)
    - delta >= 2 (missed day)   → strict reset; return (1, today_iso)

    Both today and last_streak_date are in the configured timezone (tz_name),
    ensuring a consistent calendar-day boundary for all users (D-17).
    """
    today = get_local_date(tz_name)
    today_str = today.isoformat()

    if last_streak_date is None:
        return (1, today_str)

    last = date.fromisoformat(last_streak_date)
    delta = (today - last).days

    if delta == 0:
        return (current_streak, last_streak_date)
    elif delta == 1:
        return (current_streak + 1, today_str)
    else:
        return (1, today_str)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    total_songs_queued INTEGER DEFAULT 0,
    first_seen_at TEXT DEFAULT (datetime('now')),
    last_active_at TEXT DEFAULT (datetime('now')),
    current_streak INTEGER DEFAULT 0,
    longest_streak INTEGER DEFAULT 0,
    last_streak_date TEXT
);

CREATE TABLE IF NOT EXISTS song_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    artist TEXT,
    url TEXT NOT NULL,
    duration_seconds INTEGER,
    queued_at TEXT DEFAULT (datetime('now')),
    was_skipped BOOLEAN DEFAULT 0,
    was_auto_queued BOOLEAN DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_history_guild ON song_history(guild_id, queued_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_user ON song_history(user_id, queued_at DESC);

CREATE TABLE IF NOT EXISTS user_artist_counts (
    user_id TEXT NOT NULL,
    artist TEXT NOT NULL,
    play_count INTEGER DEFAULT 1,
    PRIMARY KEY (user_id, artist)
);

CREATE TABLE IF NOT EXISTS image_generation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    prompt TEXT NOT NULL,
    generated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_imagine_user_date ON image_generation_log(user_id, generated_at);

CREATE TABLE IF NOT EXISTS bot_daily_stats (
    date TEXT PRIMARY KEY,
    total_commands INTEGER DEFAULT 0,
    total_songs_played INTEGER DEFAULT 0,
    total_ai_queries INTEGER DEFAULT 0,
    total_images_generated INTEGER DEFAULT 0
);
"""


async def migrate_add_streak_columns(db: aiosqlite.Connection) -> None:
    """Idempotent additive migration: add streak columns to user_profiles if absent.

    Safe to call on an already-migrated DB (D-19). Column names are hard-coded
    literals — never derived from input — so no injection surface (T-03-04).
    Must be called AFTER executescript(SCHEMA_SQL) so the table exists first.
    """
    cursor = await db.execute("PRAGMA table_info(user_profiles)")
    existing = {row[1] for row in await cursor.fetchall()}
    migrations = [
        ("current_streak", "INTEGER DEFAULT 0"),
        ("longest_streak", "INTEGER DEFAULT 0"),
        ("last_streak_date", "TEXT"),
    ]
    for col_name, col_def in migrations:
        if col_name not in existing:
            await db.execute(
                f"ALTER TABLE user_profiles ADD COLUMN {col_name} {col_def}"
            )
    await db.commit()
    log.debug("Streak column migration complete")


async def init_db(db: aiosqlite.Connection) -> None:
    """Create all tables if they don't exist."""
    # WAL improves read/write concurrency; busy_timeout makes brief lock
    # contention block-and-retry instead of raising. (WAL is a no-op on :memory:.)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    await db.executescript(SCHEMA_SQL)
    await migrate_add_streak_columns(db)  # additive streak migration (D-19, Pitfall 4)
    await db.commit()
    log.info("Database schema initialized")


async def log_song(
    db: aiosqlite.Connection,
    *,
    guild_id: str,
    user_id: str,
    title: str,
    artist: str | None,
    url: str,
    duration: int,
) -> None:
    """Insert a song into the history."""
    await db.execute(
        """INSERT INTO song_history (guild_id, user_id, title, artist, url, duration_seconds)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (guild_id, user_id, title, artist, url, duration),
    )
    await db.commit()


async def update_artist_count(
    db: aiosqlite.Connection, *, user_id: str, artist: str | None
) -> None:
    """Increment the play count for an artist. Skips if artist is None."""
    if artist is None:
        return
    await db.execute(
        """INSERT INTO user_artist_counts (user_id, artist, play_count)
           VALUES (?, ?, 1)
           ON CONFLICT(user_id, artist) DO UPDATE SET play_count = play_count + 1""",
        (user_id, artist),
    )
    await db.commit()


async def update_user_profile(
    db: aiosqlite.Connection, *, user_id: str, username: str
) -> None:
    """Create or update a user profile, incrementing their song count."""
    await db.execute(
        """INSERT INTO user_profiles (user_id, username, total_songs_queued)
           VALUES (?, ?, 1)
           ON CONFLICT(user_id) DO UPDATE SET
               username = excluded.username,
               total_songs_queued = total_songs_queued + 1,
               last_active_at = datetime('now')""",
        (user_id, username),
    )
    await db.commit()


async def increment_daily_stat(db: aiosqlite.Connection, field: str) -> None:
    """Increment a field in today's daily stats row."""
    today = date.today().isoformat()
    allowed_fields = {
        "total_commands",
        "total_songs_played",
        "total_ai_queries",
        "total_images_generated",
    }
    if field not in allowed_fields:
        raise ValueError(f"Invalid stat field: {field}")

    await db.execute(
        f"""INSERT INTO bot_daily_stats (date, {field})
            VALUES (?, 1)
            ON CONFLICT(date) DO UPDATE SET {field} = {field} + 1""",
        (today,),
    )
    await db.commit()


async def mark_song_skipped(db: aiosqlite.Connection, *, guild_id: str, url: str) -> None:
    """Mark the most recent song_history entry matching guild_id + url as skipped."""
    await db.execute(
        """UPDATE song_history SET was_skipped = 1
           WHERE id = (
               SELECT id FROM song_history
               WHERE guild_id = ? AND url = ?
               ORDER BY queued_at DESC, id DESC LIMIT 1
           )""",
        (guild_id, url),
    )
    await db.commit()


async def get_recent_songs(
    db: aiosqlite.Connection, *, guild_id: str, limit: int = 10
) -> list[dict]:
    """Return the last N songs for a guild, newest first."""
    cursor = await db.execute(
        """SELECT title, artist, url, duration_seconds, user_id
           FROM song_history
           WHERE guild_id = ?
           ORDER BY queued_at DESC, id DESC
           LIMIT ?""",
        (guild_id, limit),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def log_image(
    db: aiosqlite.Connection,
    *,
    guild_id: str,
    user_id: str,
    prompt: str,
) -> None:
    """Insert an image generation log entry."""
    await db.execute(
        """INSERT INTO image_generation_log (guild_id, user_id, prompt)
           VALUES (?, ?, ?)""",
        (guild_id, user_id, prompt),
    )
    await db.commit()


async def get_images_today(db: aiosqlite.Connection, *, user_id: str) -> int:
    """Count how many images a user has generated today."""
    cursor = await db.execute(
        """SELECT COUNT(*) as cnt FROM image_generation_log
           WHERE user_id = ? AND date(generated_at) = date('now')""",
        (user_id,),
    )
    row = await cursor.fetchone()
    return row["cnt"] if row else 0


async def get_daily_command_count(db: aiosqlite.Connection) -> int:
    """Return today's total command count for the mood system."""
    today = date.today().isoformat()
    cursor = await db.execute(
        "SELECT total_commands FROM bot_daily_stats WHERE date = ?",
        (today,),
    )
    row = await cursor.fetchone()
    return row["total_commands"] if row else 0


async def get_repeat_song_count(
    db: aiosqlite.Connection, *, guild_id: str, user_id: str, title: str
) -> int:
    """Count plays of the same song by this user in this guild today (PERS-04).

    All parameters are bound via parameterized placeholders — no string
    interpolation — preventing SQL injection (T-03-03).
    """
    cursor = await db.execute(
        """SELECT COUNT(*) as cnt FROM song_history
           WHERE guild_id = ? AND user_id = ? AND title = ?
             AND date(queued_at) = date('now')""",
        (guild_id, user_id, title),
    )
    row = await cursor.fetchone()
    return row["cnt"] if row else 0


async def update_user_streak(
    db: aiosqlite.Connection, *, user_id: str, tz_name: str
) -> tuple[int, int, int | None]:
    """Update streak for user; return (new_streak, new_longest, milestone_or_None).

    Reads current_streak / last_streak_date from user_profiles, runs compute_streak(),
    persists the result, and checks config.MILESTONE_STREAK_THRESHOLDS for an exact
    crossing (D-21: fires once per threshold on exact equality, no extra bookkeeping).

    Returns:
        (new_streak, new_longest_streak, milestone_value)
        milestone_value is the threshold int if new_streak exactly equals one of
        MILESTONE_STREAK_THRESHOLDS AND it increased this call; else None.
    """
    cursor = await db.execute(
        "SELECT current_streak, longest_streak, last_streak_date FROM user_profiles WHERE user_id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        # User not found — no-op to avoid phantom writes
        return (0, 0, None)

    old_streak: int = row["current_streak"] or 0
    old_longest: int = row["longest_streak"] or 0
    last_date: str | None = row["last_streak_date"]

    new_streak, new_date = compute_streak(old_streak, last_date, tz_name)
    new_longest = max(old_longest, new_streak)

    await db.execute(
        """UPDATE user_profiles
           SET current_streak = ?, longest_streak = ?, last_streak_date = ?
           WHERE user_id = ?""",
        (new_streak, new_longest, new_date, user_id),
    )
    await db.commit()

    # Milestone: fires when new_streak exactly equals a threshold AND increased
    milestone: int | None = None
    if new_streak > old_streak and new_streak in config.MILESTONE_STREAK_THRESHOLDS:
        milestone = new_streak

    return (new_streak, new_longest, milestone)


async def get_history_rows(
    db: aiosqlite.Connection, *, guild_id: str, limit: int = 50
) -> list[dict]:
    """Return the last N songs for a guild, newest first, with queued_at (HIST-01).

    LIMIT is bound as an int parameter — not string-interpolated (T-03-03).
    """
    cursor = await db.execute(
        """SELECT title, artist, url, duration_seconds, user_id, queued_at
           FROM song_history
           WHERE guild_id = ?
           ORDER BY queued_at DESC, id DESC
           LIMIT ?""",
        (guild_id, int(limit)),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]
