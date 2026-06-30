"""PostgreSQL database initialization and query helpers (asyncpg)."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone, timedelta
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
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS user_memories (
    id               BIGSERIAL PRIMARY KEY,
    user_id          TEXT NOT NULL,
    guild_id         TEXT,
    kind             TEXT,
    fact             TEXT NOT NULL,
    embedding        vector(768) NOT NULL,
    salience         REAL DEFAULT 0,
    hit_count        INTEGER DEFAULT 1,
    created_at       TIMESTAMPTZ DEFAULT now(),
    last_seen_at     TIMESTAMPTZ DEFAULT now(),
    last_surfaced_at TIMESTAMPTZ,
    surface_count    INTEGER DEFAULT 0,
    expires_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_user_memories_user ON user_memories(user_id, created_at DESC);

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

CREATE TABLE IF NOT EXISTS user_favorites (
    user_id          TEXT NOT NULL,
    video_id         TEXT NOT NULL,
    title            TEXT NOT NULL,
    artist           TEXT,
    url              TEXT NOT NULL,
    duration_seconds INTEGER,
    thumbnail        TEXT,
    added_at         TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, video_id)
);

CREATE INDEX IF NOT EXISTS idx_favorites_user ON user_favorites(user_id, added_at DESC);

CREATE TABLE IF NOT EXISTS user_playlists (
    user_id    TEXT NOT NULL,
    name       TEXT NOT NULL,
    snapshot   JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, name)
);

CREATE INDEX IF NOT EXISTS idx_playlists_user ON user_playlists(user_id, updated_at DESC);

ALTER TABLE bot_daily_stats ADD COLUMN IF NOT EXISTS total_errors INTEGER DEFAULT 0;

CREATE TABLE IF NOT EXISTS resolution_cache (
    query_key   TEXT PRIMARY KEY,
    video_id    TEXT NOT NULL,
    title       TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rescache_expires ON resolution_cache(expires_at);

CREATE TABLE IF NOT EXISTS guild_jams (
    guild_id   TEXT NOT NULL,
    name       TEXT NOT NULL,
    snapshot   JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (guild_id, name)
);

CREATE INDEX IF NOT EXISTS idx_jams_guild ON guild_jams(guild_id, updated_at DESC);
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
        "total_errors",              # Phase 8 addition (D-23)
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


async def get_daily_stats_row(pool: asyncpg.Pool) -> dict:
    """Return today's bot_daily_stats row as a dict (all five fields; 0s if no row).

    Today-only window — keyed by date.today().isoformat() (D-22/D-25).
    Returns bot-wide global stats for the /stats owner dashboard.
    """
    today = date.today().isoformat()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT total_commands, total_songs_played, total_ai_queries,"
            "       total_images_generated, total_errors"
            " FROM bot_daily_stats WHERE date = $1",
            today,
        )
    if row is None:
        return {
            "total_commands": 0,
            "total_songs_played": 0,
            "total_ai_queries": 0,
            "total_images_generated": 0,
            "total_errors": 0,
        }
    return dict(row)


async def get_leaderboard_songs(
    pool: asyncpg.Pool, guild_id: str
) -> list[asyncpg.Record]:
    """Return the top-N users by songs queued within a specific guild (D-10/D-14).

    Per-guild scope: queries song_history WHERE guild_id = $1 (not the global
    user_profiles.total_songs_queued counter). Ties broken by oldest first_seen_at
    (D-16). Excludes users with zero songs (HAVING >= 1, D-18).
    All parameters are $N positional — no string interpolation (T-08-01).
    """
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT sh.user_id, up.username, COUNT(*) AS songs_queued"
            " FROM song_history sh"
            " JOIN user_profiles up USING (user_id)"
            " WHERE sh.guild_id = $1"
            " GROUP BY sh.user_id, up.username, up.first_seen_at"
            " HAVING COUNT(*) >= 1"
            " ORDER BY songs_queued DESC, up.first_seen_at ASC"
            " LIMIT $2",
            guild_id, config.LEADERBOARD_TOP_N,
        )


async def get_leaderboard_skips(
    pool: asyncpg.Pool, guild_id: str
) -> list[asyncpg.Record]:
    """Return the top-N most-skipped song titles within a specific guild (D-12).

    Ranks song titles by skip count (was_skipped = true). Zero-skip titles are
    excluded (HAVING >= 1, D-18). No user attribution — entity is the song title.
    All parameters are $N positional — no string interpolation (T-08-01).
    """
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT title, COUNT(*) AS skip_count"
            " FROM song_history"
            " WHERE guild_id = $1 AND was_skipped = true"
            " GROUP BY title"
            " HAVING COUNT(*) >= 1"
            " ORDER BY skip_count DESC"
            " LIMIT $2",
            guild_id, config.LEADERBOARD_TOP_N,
        )


async def get_leaderboard_streaks(
    pool: asyncpg.Pool, guild_id: str
) -> list[asyncpg.Record]:
    """Return the top-N users by longest streak who are active in this guild (D-15).

    Guild-active filter: subquery selects DISTINCT user_ids from song_history
    WHERE guild_id = $1. Global streak (longest_streak from user_profiles) is
    the ranking metric (D-15). Ties broken by oldest first_seen_at (D-16).
    Users with longest_streak < 1 are excluded (D-18).
    All parameters are $N positional — no string interpolation (T-08-01).
    """
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT up.user_id, up.username, up.longest_streak"
            " FROM user_profiles up"
            " WHERE up.user_id IN ("
            "   SELECT DISTINCT user_id FROM song_history WHERE guild_id = $1"
            " )"
            "   AND up.longest_streak >= 1"
            " ORDER BY up.longest_streak DESC, up.first_seen_at ASC"
            " LIMIT $2",
            guild_id, config.LEADERBOARD_TOP_N,
        )


async def get_images_today_global(pool: asyncpg.Pool) -> int:
    """Return the total number of images generated today (all users, bot-wide).

    Used by /stats to display global image-cap usage (OPS-03/D-24/D-25).
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM image_generation_log"
            " WHERE generated_at::date = CURRENT_DATE"
        )
    return int(row["cnt"]) if row else 0


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


# ---------------------------------------------------------------------------
# Favorites helpers (Phase 7, D-18..D-22, PLAYER-05)
# ---------------------------------------------------------------------------


async def add_favorite(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    video_id: str,
    title: str,
    artist: str | None,
    url: str,
    duration_seconds: int | None,
    thumbnail: str | None,
) -> None:
    """Insert a favorite row for (user_id, video_id).

    Duplicate (same user_id + video_id) is a no-op via ON CONFLICT DO NOTHING
    so it does NOT consume a cap slot.
    All values are bound as $N params — no string interpolation (T-07-03-01).
    """
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO user_favorites"
            " (user_id, video_id, title, artist, url, duration_seconds, thumbnail)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7)"
            " ON CONFLICT (user_id, video_id) DO NOTHING",
            user_id, video_id, title, artist, url, duration_seconds, thumbnail,
        )


async def count_favorites(pool: asyncpg.Pool, *, user_id: str) -> int:
    """Return the number of favorites saved by user_id."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM user_favorites WHERE user_id = $1",
            user_id,
        )
    return int(row["cnt"]) if row else 0


async def get_favorites(
    pool: asyncpg.Pool, *, user_id: str, limit: int = 25
) -> list[dict]:
    """Return the user's saved favorites, newest first.

    Each dict carries enough fields to rebuild a Track:
    video_id, title, artist, url, duration_seconds, thumbnail.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT video_id, title, artist, url, duration_seconds, thumbnail"
            " FROM user_favorites"
            " WHERE user_id = $1"
            " ORDER BY added_at DESC"
            " LIMIT $2",
            user_id, int(limit),
        )
    return [dict(row) for row in rows]


async def remove_favorite(pool: asyncpg.Pool, *, user_id: str, video_id: str) -> None:
    """Delete the (user_id, video_id) row from user_favorites.

    No-op if the row does not exist.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM user_favorites WHERE user_id = $1 AND video_id = $2",
            user_id, video_id,
        )


# ---------------------------------------------------------------------------
# Playlist helpers (Phase 7, D-23..D-28, PLAYER-06)
# ---------------------------------------------------------------------------


async def save_playlist(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    name: str,
    snapshot: list[dict],
) -> None:
    """Upsert a named playlist snapshot for (user_id, name).

    First save inserts; re-saving the same name overwrites the snapshot and
    bumps updated_at (D-27). The snapshot list is serialised via json.dumps
    and stored as JSONB — all values flow through $N params (T-07-04-01).
    """
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO user_playlists (user_id, name, snapshot, created_at, updated_at)"
            " VALUES ($1, $2, $3::jsonb, now(), now())"
            " ON CONFLICT (user_id, name)"
            " DO UPDATE SET snapshot = EXCLUDED.snapshot, updated_at = now()",
            user_id, name, json.dumps(snapshot),
        )


async def get_playlist(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    name: str,
) -> list[dict] | None:
    """Return the snapshot list for (user_id, name), or None if not found.

    asyncpg may return JSONB columns as a dict/list directly or as a JSON
    string depending on the driver version and server type-OID registration.
    We normalise via json.loads when the value is a str (T-07-04-01 / D-23).
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT snapshot FROM user_playlists WHERE user_id = $1 AND name = $2",
            user_id, name,
        )
    if row is None:
        return None
    payload = row["snapshot"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return list(payload)


async def list_playlists(
    pool: asyncpg.Pool,
    *,
    user_id: str,
) -> list[dict]:
    """Return the user's playlists as metadata rows, newest-updated-first (D-24).

    Each dict has: name (str), track_count (int), updated_at (datetime).
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT name,"
            "       jsonb_array_length(snapshot) AS track_count,"
            "       updated_at"
            " FROM user_playlists"
            " WHERE user_id = $1"
            " ORDER BY updated_at DESC",
            user_id,
        )
    return [dict(row) for row in rows]


async def delete_playlist(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    name: str,
) -> bool:
    """Delete (user_id, name) from user_playlists.

    Returns True if a row was deleted, False if no matching row existed (D-28).
    Ownership is implicit — the user_id param ensures users only delete their
    own rows (T-07-04-02).
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM user_playlists WHERE user_id = $1 AND name = $2",
            user_id, name,
        )
    # asyncpg execute() returns a status string like "DELETE 1" or "DELETE 0";
    # parse the trailing affected-row count rather than a fragile suffix match.
    return result.rsplit(" ", 1)[-1] != "0"


async def count_playlists(pool: asyncpg.Pool, *, user_id: str) -> int:
    """Return the number of named playlists saved by user_id (for cap checks, D-28).

    T-07-04-02: keyed on user_id — only counts the requesting user's rows.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM user_playlists WHERE user_id = $1",
            user_id,
        )
    return int(row["cnt"]) if row else 0


# ---------------------------------------------------------------------------
# Phase 12: Guild jams helpers (UX-01, D-01..D-05, T-12-01-01/02)
# ---------------------------------------------------------------------------


async def save_jam(
    pool: asyncpg.Pool,
    *,
    guild_id: str,
    name: str,
    snapshot: list[dict],
) -> None:
    """Upsert a named jam snapshot for (guild_id, name).

    First save inserts; re-saving the same name overwrites the snapshot and
    bumps updated_at (D-05). The snapshot list is serialised via json.dumps
    and stored as JSONB — all values flow through $N params (T-12-01-01).
    """
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO guild_jams (guild_id, name, snapshot, created_at, updated_at)"
            " VALUES ($1, $2, $3::jsonb, now(), now())"
            " ON CONFLICT (guild_id, name)"
            " DO UPDATE SET snapshot = EXCLUDED.snapshot, updated_at = now()",
            guild_id, name, json.dumps(snapshot),
        )


async def get_jam(
    pool: asyncpg.Pool,
    *,
    guild_id: str,
    name: str,
) -> list[dict] | None:
    """Return the snapshot list for (guild_id, name), or None if not found.

    asyncpg may return JSONB columns as a dict/list directly or as a JSON
    string depending on the driver version and server type-OID registration.
    We normalise via json.loads when the value is a str (T-12-01-01 / D-01).

    Cross-guild isolation (T-12-01-02): keyed on guild_id so guild-A jams
    are never visible to guild-B queries.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT snapshot FROM guild_jams WHERE guild_id = $1 AND name = $2",
            guild_id, name,
        )
    if row is None:
        return None
    payload = row["snapshot"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return list(payload)


async def list_jams(
    pool: asyncpg.Pool,
    *,
    guild_id: str,
) -> list[dict]:
    """Return the guild's jams as metadata rows, newest-updated-first (D-02).

    Each dict has: name (str), track_count (int), updated_at (datetime).
    Cross-guild isolation (T-12-01-02): WHERE guild_id = $1.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT name,"
            "       jsonb_array_length(snapshot) AS track_count,"
            "       updated_at"
            " FROM guild_jams"
            " WHERE guild_id = $1"
            " ORDER BY updated_at DESC",
            guild_id,
        )
    return [dict(row) for row in rows]


async def delete_jam(
    pool: asyncpg.Pool,
    *,
    guild_id: str,
    name: str,
) -> bool:
    """Delete (guild_id, name) from guild_jams.

    Returns True if a row was deleted, False if no matching row existed (D-05).
    Cross-guild isolation (T-12-01-02): guild_id in WHERE prevents cross-guild
    deletion. Anyone in the guild may delete (D-03 — no ownership gate).
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM guild_jams WHERE guild_id = $1 AND name = $2",
            guild_id, name,
        )
    # asyncpg execute() returns a status string like "DELETE 1" or "DELETE 0";
    # parse the trailing affected-row count rather than a fragile suffix match.
    return result.rsplit(" ", 1)[-1] != "0"


async def count_jams(pool: asyncpg.Pool, *, guild_id: str) -> int:
    """Return the number of named jams saved for guild_id (for cap checks, D-05).

    Cross-guild isolation (T-12-01-02): WHERE guild_id = $1.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM guild_jams WHERE guild_id = $1",
            guild_id,
        )
    return int(row["cnt"]) if row else 0


# ---------------------------------------------------------------------------
# Phase 11: Memory helpers (MEM-02 / MEM-03 / T-11-03a / T-11-03d)
# ---------------------------------------------------------------------------


async def search_memories(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    query_embedding: list[float],
    k: int,
) -> list[asyncpg.Record]:
    """Cosine ANN search scoped to user_id. Returns up to k rows.

    Uses pgvector ``<=>`` (cosine distance) operator ordered ascending (smallest
    distance = highest similarity). The ``1 - (embedding <=> $2)`` expression
    converts distance to cosine similarity for apply_floor + rerank.

    Security (T-11-03a / V4): ``WHERE user_id = $1`` is the first filter — the
    ANN ORDER BY fires inside that scope only, so cross-user leakage is impossible
    regardless of the embedding neighbourhood.

    Security (T-11-03d): all parameters are $N positional asyncpg bindings;
    ``query_embedding`` is a plain list[float] passed via the pgvector codec
    registered at pool-creation time (register_vector) — no SQL injection path.

    Args:
        pool:            asyncpg connection pool (with pgvector codec registered).
        user_id:         Caller's user_id — scope guard (never cross-user).
        query_embedding: 768d float vector from GeminiService.embed (RETRIEVAL_QUERY).
        k:               Max rows to return (config.MEMORY_TOP_K = 8).

    Returns:
        List of asyncpg.Record rows with columns: id, fact, salience, hit_count,
        created_at, last_seen_at, last_surfaced_at, surface_count, similarity.
    """
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT id, fact, salience, hit_count, created_at, last_seen_at,"
            "       last_surfaced_at, surface_count,"
            "       1 - (embedding <=> $2) AS similarity"
            " FROM user_memories"
            " WHERE user_id = $1"
            " ORDER BY embedding <=> $2"
            " LIMIT $3",
            user_id, query_embedding, k,
        )


async def insert_memory(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    guild_id: str | None,
    kind: str,
    fact: str,
    embedding: list[float],
    salience: float,
    expires_at: datetime,
) -> int:
    """Insert a new user_memories row and return its id.

    Embedding is passed as a plain list[float]; the pgvector codec registered
    via register_vector() in bot.py:_initialize_once handles the Postgres
    vector(768) type encoding (T-11-04b — no SQL injection path for embeddings).

    All parameters are bound via $N positional placeholders — never string-built
    SQL (T-11-04b / ASVS V5). Scoped insert: user_id is always from the
    authenticated session, not from fact text (T-11-04c).

    Args:
        pool:       asyncpg connection pool with pgvector codec registered.
        user_id:    Discord user ID (TEXT) — owner of this memory.
        guild_id:   Guild context for the event; None for cross-guild facts.
        kind:       Event kind (config.MEMORY_SALIENCE_BASE_WEIGHTS key).
        fact:       Already-distilled atomic fact sentence (11-05 produces this).
        embedding:  768d float vector from GeminiService.embed (RETRIEVAL_DOCUMENT).
        salience:   Hybrid salience score from compute_salience() (D-07).
        expires_at: UTC datetime after which the row may be swept (decay horizon).

    Returns:
        The BIGSERIAL id of the newly inserted row.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO user_memories"
            " (user_id, guild_id, kind, fact, embedding, salience, expires_at)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7)"
            " RETURNING id",
            user_id, guild_id, kind, fact, embedding, salience, expires_at,
        )
    return row["id"]


async def bump_memory_hit(pool: asyncpg.Pool, memory_id: int) -> None:
    """Increment hit_count and refresh last_seen_at for a near-duplicate memory.

    Called by MemoryService.remember() when dedup_decision() returns True —
    the incoming fact is nearly identical to an existing row, so we record the
    repeat observation rather than inserting a duplicate.

    A small salience nudge (±0.02, clamped to 1.0) rewards frequently observed
    facts, keeping them above low-frequency facts during eviction ranking (D-07).

    Args:
        pool:      asyncpg connection pool.
        memory_id: The id of the existing user_memories row to bump.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE user_memories"
            " SET hit_count = hit_count + 1,"
            "     last_seen_at = now(),"
            "     salience = LEAST(1.0, salience + 0.02)"
            " WHERE id = $1",
            memory_id,
        )


async def count_user_memories(pool: asyncpg.Pool, user_id: str) -> int:
    """Return the current count of active memory rows for a user.

    Called by MemoryService.remember() immediately after a successful insert to
    check whether the per-user cap (config.MEMORY_MAX_PER_USER) has been exceeded.
    When count > cap, remember() triggers eviction via choose_eviction +
    evict_lowest_salience (D-08 / T-11-04a).

    Args:
        pool:    asyncpg connection pool.
        user_id: Discord user ID (TEXT) — scoped to this user only.

    Returns:
        Number of rows in user_memories for this user_id.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM user_memories WHERE user_id = $1",
            user_id,
        )
    return int(row["cnt"]) if row else 0


async def get_user_memories_for_eviction(
    pool: asyncpg.Pool,
    *,
    user_id: str,
) -> list[asyncpg.Record]:
    """Fetch all memory rows for a user (fields needed for choose_eviction).

    Returns rows with: id, salience, hit_count, created_at, fact, last_seen_at,
    last_surfaced_at, surface_count. The caller (MemoryService.remember) maps
    these to MemoryFact objects and passes them to models.memory.choose_eviction.

    Ordered ascending by eviction priority (lowest-value first) so the caller can
    pass the result directly to choose_eviction without re-sorting.

    Security (T-11-04c): WHERE user_id = $1 ensures eviction candidates never
    include rows belonging to another user.

    Args:
        pool:    asyncpg connection pool.
        user_id: Discord user ID — scope guard, same as insert path.

    Returns:
        All asyncpg.Record rows for this user (may be empty).
    """
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT id, fact, salience, hit_count, created_at,"
            "       last_seen_at, last_surfaced_at, surface_count"
            " FROM user_memories"
            " WHERE user_id = $1"
            " ORDER BY salience ASC, created_at ASC, hit_count ASC",
            user_id,
        )


async def evict_lowest_salience(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    ids: list[int],
) -> None:
    """Delete the given memory ids — scoped to user_id (T-11-04c cross-user guard).

    The DELETE is guarded by BOTH ``id = ANY($2)`` AND ``user_id = $1``, so a
    bug in the eviction id list can NEVER delete rows belonging to another user
    (T-11-04c information-disclosure threat mitigation).

    Called by MemoryService.remember() after choose_eviction() returns the ids
    to remove. No-op when ids is empty ([] from choose_eviction when at/under cap).

    Args:
        pool:    asyncpg connection pool.
        user_id: Discord user ID — ownership scope guard.
        ids:     List of user_memories.id values to delete (from choose_eviction).
                 Passed via ANY($2) array binding — no string interpolation.
    """
    if not ids:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM user_memories WHERE user_id = $1 AND id = ANY($2)",
            user_id, ids,
        )


async def bump_surfaced(pool: asyncpg.Pool, ids: list[int]) -> None:
    """Mark memories as surfaced: set last_surfaced_at = now(), increment surface_count.

    Called by MemoryService.recall() after selecting the top-k facts to inject.
    Updating last_surfaced_at is what drives the novelty_score D-05 anti-repeat
    penalty — without this update, the same memories would surface every call.

    Args:
        pool: asyncpg connection pool.
        ids:  List of user_memories.id values to update. No-op if empty.

    Security (T-11-03d): ids is passed via the ``ANY($1)`` array binding — no
    SQL injection path. asyncpg encodes the Python list as a Postgres array.
    """
    if not ids:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE user_memories"
            " SET last_surfaced_at = now(),"
            "     surface_count = surface_count + 1"
            " WHERE id = ANY($1)",
            ids,
        )


async def delete_expired_memories(pool: asyncpg.Pool, *, now: datetime) -> int:
    """Delete expired low-salience memories. Returns the number of rows deleted.

    Called by MemoryService.sweep() daily to keep the store bounded over time
    (MEM-07 — time-based decay backstop, paired with the 11-04 write-time cap).

    Deletion condition (both must hold — T-11-07b over-broad-delete guard):
      - expires_at IS NOT NULL AND expires_at < now  — past the decay horizon
      - salience < config.MEMORY_DECAY_SALIENCE_FLOOR  — low-value fact only

    High-salience memories (milestone, late_night, repeat_song) survive even
    when past their expiry date, mirroring the decay_predicate logic in
    models/memory.py. The DELETE is bounded by two $N params — no string
    interpolation (T-11-07b parameterization requirement).

    Args:
        pool: asyncpg connection pool.
        now:  Reference clock (UTC); injected by MemoryService.sweep() so that
              test helpers can override without patching datetime.now().

    Returns:
        Number of rows deleted (0 when no expired low-salience rows exist).
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM user_memories"
            " WHERE expires_at IS NOT NULL"
            "   AND expires_at < $1"
            "   AND salience < $2",
            now,
            config.MEMORY_DECAY_SALIENCE_FLOOR,
        )
    # asyncpg returns a string like "DELETE 5"; extract the count
    return int(result.split()[-1])


# ---------------------------------------------------------------------------
# Phase 6: Resolution cache helpers (PERF-03, D-07/D-09, T-06-01)
# ---------------------------------------------------------------------------


def normalize_search_query(q: str) -> str:
    """Strip, lowercase, and collapse internal whitespace of a search query.

    Pure function — no DB access. Used as the resolution-cache key so that
    queries like '  Lo-Fi   Beats  ' and 'lo-fi beats' share the same cache
    entry. All cache writes and reads go through this function before touching
    the DB (T-06-01 / ASVS V5).
    """
    return re.sub(r"\s+", " ", q.strip().lower())


async def get_resolution_cache(pool: asyncpg.Pool, *, query_key: str) -> dict | None:
    """Fetch a cached resolution for a normalized query key.

    Returns dict(video_id, title) if a non-expired row exists, else None.
    The WHERE clause filters on expires_at > now() so stale rows are invisible
    without a background cleanup job (D-07 TTL design).
    All parameters use $N positional binding — no string interpolation (T-06-01).
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT video_id, title FROM resolution_cache"
            " WHERE query_key = $1 AND expires_at > now()",
            query_key,
        )
    return dict(row) if row else None


async def set_resolution_cache(
    pool: asyncpg.Pool,
    *,
    query_key: str,
    video_id: str,
    title: str | None,
    ttl_days: int,
) -> None:
    """Upsert a resolution cache entry, refreshing the TTL on conflict (Pitfall 5).

    The ON CONFLICT clause updates video_id, title, AND expires_at so that a
    frequently-used query never expires while it is actively being resolved.
    TTL is computed in Python and passed as a $N param — never embedded in SQL
    (Pitfall 7 / T-06-01 / ASVS V5).
    """
    expires = datetime.now(timezone.utc) + timedelta(days=ttl_days)
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO resolution_cache (query_key, video_id, title, expires_at)"
            " VALUES ($1, $2, $3, $4)"
            " ON CONFLICT (query_key) DO UPDATE SET"
            "  video_id = EXCLUDED.video_id,"
            "  title = EXCLUDED.title,"
            "  expires_at = EXCLUDED.expires_at",
            query_key, video_id, title, expires,
        )


async def get_user_skip_rate(
    pool: asyncpg.Pool, *, guild_id: str, user_id: str
) -> asyncpg.Record | None:
    """Return an asyncpg Record with total_plays and total_skips for a user in a guild.

    Aggregate is all-time (no date filter, D-09) and scoped to BOTH guild_id ($1)
    and user_id ($2) — preventing cross-guild and cross-user data leakage (Pitfall 6
    / T-12-02-01). fetchrow always returns a row for COUNT(*) even when no matching
    rows exist (both counters = 0), so callers can safely treat None as 0 plays.

    The min-plays floor (D-08) is applied by logic.skip_stats.compute_skip_rate in
    the caller — never here in SQL.
    All values bound as $1/$2 positional params — no string interpolation (T-12-02-03).
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT COUNT(*) AS total_plays,"
            " COUNT(*) FILTER (WHERE was_skipped = true) AS total_skips"
            " FROM song_history"
            " WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )
