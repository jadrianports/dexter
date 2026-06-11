"""PostgreSQL database initialization and query helpers (asyncpg)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import asyncpg
import json  # noqa: F401 — used by callers for guild_queues jsonb payload

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
# Schema (Postgres DDL — no SQLite-isms)
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id             TEXT PRIMARY KEY,
    username            TEXT NOT NULL,
    total_songs_queued  INTEGER DEFAULT 0,
    first_seen_at       TIMESTAMPTZ DEFAULT now(),
    last_active_at      TIMESTAMPTZ DEFAULT now(),
    current_streak      INTEGER DEFAULT 0,
    longest_streak      INTEGER DEFAULT 0,
    last_streak_date    TEXT
);

CREATE TABLE IF NOT EXISTS song_history (
    id               BIGSERIAL PRIMARY KEY,
    guild_id         TEXT NOT NULL,
    user_id          TEXT NOT NULL,
    title            TEXT NOT NULL,
    artist           TEXT,
    url              TEXT NOT NULL,
    duration_seconds INTEGER,
    queued_at        TIMESTAMPTZ DEFAULT now(),
    was_skipped      BOOLEAN DEFAULT false,
    was_auto_queued  BOOLEAN DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_history_guild ON song_history(guild_id, queued_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_user  ON song_history(user_id,  queued_at DESC);

CREATE TABLE IF NOT EXISTS user_artist_counts (
    user_id    TEXT NOT NULL,
    artist     TEXT NOT NULL,
    play_count INTEGER DEFAULT 1,
    PRIMARY KEY (user_id, artist)
);

CREATE TABLE IF NOT EXISTS image_generation_log (
    id           BIGSERIAL PRIMARY KEY,
    guild_id     TEXT NOT NULL,
    user_id      TEXT NOT NULL,
    prompt       TEXT NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_imagine_user_date ON image_generation_log(user_id, generated_at);

CREATE TABLE IF NOT EXISTS bot_daily_stats (
    date                   TEXT PRIMARY KEY,
    total_commands         INTEGER DEFAULT 0,
    total_songs_played     INTEGER DEFAULT 0,
    total_ai_queries       INTEGER DEFAULT 0,
    total_images_generated INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS guild_queues (
    guild_id   TEXT PRIMARY KEY,
    payload    JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);
"""


async def init_db(pool: asyncpg.Pool) -> None:
    """Create all tables if they don't exist (Postgres DDL via asyncpg)."""
    # SCHEMA_SQL contains only DDL with no $N params — asyncpg accepts
    # multi-statement strings when there are no positional parameters (Pitfall 1).
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
    log.info("Database schema initialized")


# ---------------------------------------------------------------------------
# Batched per-/play transaction (D-06 / SCALE-01)
# ---------------------------------------------------------------------------


async def log_track_batch(
    pool: asyncpg.Pool,
    *,
    guild_id: str,
    user_id: str,
    username: str,
    title: str,
    artist: str | None,
    url: str,
    duration: int,
) -> None:
    """Write song_history + user_artist_counts + user_profiles in ONE transaction.

    All three per-/play inserts are atomic (D-06 / SCALE-01).
    asyncpg auto-rollbacks the transaction on any exception.
    All guild_id/user_id/title/url values flow through $N params — no string
    interpolation anywhere (T-04-04 / V5).
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO song_history"
                " (guild_id, user_id, title, artist, url, duration_seconds)"
                " VALUES ($1, $2, $3, $4, $5, $6)",
                guild_id, user_id, title, artist, url, duration,
            )
            if artist is not None:
                await conn.execute(
                    "INSERT INTO user_artist_counts (user_id, artist, play_count)"
                    " VALUES ($1, $2, 1)"
                    " ON CONFLICT (user_id, artist)"
                    " DO UPDATE SET play_count = user_artist_counts.play_count + 1",
                    user_id, artist,
                )
            await conn.execute(
                "INSERT INTO user_profiles (user_id, username, total_songs_queued)"
                " VALUES ($1, $2, 1)"
                " ON CONFLICT (user_id) DO UPDATE SET"
                "   username = EXCLUDED.username,"
                "   total_songs_queued = user_profiles.total_songs_queued + 1,"
                "   last_active_at = now()",
                user_id, username,
            )


# ---------------------------------------------------------------------------
# Individual helpers (kept for backward-compat callers that haven't migrated
# to log_track_batch yet — all converted to asyncpg pool style)
# ---------------------------------------------------------------------------


async def log_song(
    pool: asyncpg.Pool,
    *,
    guild_id: str,
    user_id: str,
    title: str,
    artist: str | None,
    url: str,
    duration: int,
) -> None:
    """Insert a song into the history."""
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO song_history"
            " (guild_id, user_id, title, artist, url, duration_seconds)"
            " VALUES ($1, $2, $3, $4, $5, $6)",
            guild_id, user_id, title, artist, url, duration,
        )


async def update_artist_count(
    pool: asyncpg.Pool, *, user_id: str, artist: str | None
) -> None:
    """Increment the play count for an artist. Skips if artist is None."""
    if artist is None:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO user_artist_counts (user_id, artist, play_count)"
            " VALUES ($1, $2, 1)"
            " ON CONFLICT (user_id, artist)"
            " DO UPDATE SET play_count = user_artist_counts.play_count + 1",
            user_id, artist,
        )


async def update_user_profile(
    pool: asyncpg.Pool, *, user_id: str, username: str
) -> None:
    """Create or update a user profile, incrementing their song count."""
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO user_profiles (user_id, username, total_songs_queued)"
            " VALUES ($1, $2, 1)"
            " ON CONFLICT (user_id) DO UPDATE SET"
            "   username = EXCLUDED.username,"
            "   total_songs_queued = user_profiles.total_songs_queued + 1,"
            "   last_active_at = now()",
            user_id, username,
        )


async def increment_daily_stat(pool: asyncpg.Pool, field: str) -> None:
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

    # field is validated against the allowlist above — safe to interpolate
    async with pool.acquire() as conn:
        await conn.execute(
            f"INSERT INTO bot_daily_stats (date, {field})"
            f" VALUES ($1, 1)"
            f" ON CONFLICT (date) DO UPDATE SET {field} = bot_daily_stats.{field} + 1",
            today,
        )


async def mark_song_skipped(pool: asyncpg.Pool, *, guild_id: str, url: str) -> None:
    """Mark the most recent song_history entry matching guild_id + url as skipped."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE song_history SET was_skipped = true"
            " WHERE id = ("
            "   SELECT id FROM song_history"
            "   WHERE guild_id = $1 AND url = $2"
            "   ORDER BY queued_at DESC, id DESC LIMIT 1"
            ")",
            guild_id, url,
        )


async def get_recent_songs(
    pool: asyncpg.Pool, *, guild_id: str, limit: int = 10
) -> list[dict]:
    """Return the last N songs for a guild, newest first."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT title, artist, url, duration_seconds, user_id"
            " FROM song_history"
            " WHERE guild_id = $1"
            " ORDER BY queued_at DESC, id DESC"
            " LIMIT $2",
            guild_id, limit,
        )
    return [dict(row) for row in rows]


async def log_image(
    pool: asyncpg.Pool,
    *,
    guild_id: str,
    user_id: str,
    prompt: str,
) -> None:
    """Insert an image generation log entry."""
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO image_generation_log (guild_id, user_id, prompt)"
            " VALUES ($1, $2, $3)",
            guild_id, user_id, prompt,
        )


async def get_images_today(pool: asyncpg.Pool, *, user_id: str) -> int:
    """Count how many images a user has generated today."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM image_generation_log"
            " WHERE user_id = $1 AND generated_at::date = CURRENT_DATE",
            user_id,
        )
    return row["cnt"] if row else 0


async def get_daily_command_count(pool: asyncpg.Pool) -> int:
    """Return today's total command count for the mood system."""
    today = date.today().isoformat()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT total_commands FROM bot_daily_stats WHERE date = $1",
            today,
        )
    return row["total_commands"] if row else 0


async def get_repeat_song_count(
    pool: asyncpg.Pool, *, guild_id: str, user_id: str, title: str
) -> int:
    """Count plays of the same song by this user in this guild today (PERS-04).

    All parameters are bound via $N positional placeholders — no string
    interpolation — preventing SQL injection (T-04-04 / V5).
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM song_history"
            " WHERE guild_id = $1 AND user_id = $2 AND title = $3"
            "   AND queued_at::date = CURRENT_DATE",
            guild_id, user_id, title,
        )
    return row["cnt"] if row else 0


async def update_user_streak(
    pool: asyncpg.Pool, *, user_id: str, tz_name: str
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
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT current_streak, longest_streak, last_streak_date"
            " FROM user_profiles WHERE user_id = $1",
            user_id,
        )
        if row is None:
            # User not found — no-op to avoid phantom writes
            return (0, 0, None)

        old_streak: int = row["current_streak"] or 0
        old_longest: int = row["longest_streak"] or 0
        last_date: str | None = row["last_streak_date"]

        new_streak, new_date = compute_streak(old_streak, last_date, tz_name)
        new_longest = max(old_longest, new_streak)

        await conn.execute(
            "UPDATE user_profiles"
            " SET current_streak = $1, longest_streak = $2, last_streak_date = $3"
            " WHERE user_id = $4",
            new_streak, new_longest, new_date, user_id,
        )

    # Milestone: fires when new_streak exactly equals a threshold AND increased
    milestone: int | None = None
    if new_streak > old_streak and new_streak in config.MILESTONE_STREAK_THRESHOLDS:
        milestone = new_streak

    return (new_streak, new_longest, milestone)


async def get_history_rows(
    pool: asyncpg.Pool, *, guild_id: str, limit: int = 50
) -> list[dict]:
    """Return the last N songs for a guild, newest first, with queued_at (HIST-01).

    LIMIT is bound as an int parameter — not string-interpolated (T-04-04 / V5).
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT title, artist, url, duration_seconds, user_id, queued_at"
            " FROM song_history"
            " WHERE guild_id = $1"
            " ORDER BY queued_at DESC, id DESC"
            " LIMIT $2",
            guild_id, int(limit),
        )
    return [dict(row) for row in rows]
