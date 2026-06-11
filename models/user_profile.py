"""User taste summary generation from database. Read-only queries."""

from __future__ import annotations

import asyncpg


async def get_user_summary(pool: asyncpg.Pool, user_id: str) -> str | None:
    """Generate a natural language summary of a user's music taste.

    Returns None if the user has no history.
    """
    async with pool.acquire() as conn:
        profile = await conn.fetchrow(
            "SELECT username, total_songs_queued FROM user_profiles WHERE user_id = $1",
            user_id,
        )
        if not profile:
            return None

        top_artists = await conn.fetch(
            """SELECT artist, play_count FROM user_artist_counts
               WHERE user_id = $1
               ORDER BY play_count DESC LIMIT 5""",
            user_id,
        )

        top_song = await conn.fetchrow(
            """SELECT title, COUNT(*) as cnt FROM song_history
               WHERE user_id = $1
               GROUP BY title ORDER BY cnt DESC LIMIT 1""",
            user_id,
        )

    username = profile["username"]
    total = profile["total_songs_queued"]
    artist_parts = [f"{row['artist']} ({row['play_count']})" for row in top_artists]

    parts = [f"User '{username}': {total} songs queued."]

    if artist_parts:
        parts.append(f"Top artists: {', '.join(artist_parts)}.")

    if top_song and top_song["cnt"] > 1:
        parts.append(f"Most repeated: {top_song['title']} ({top_song['cnt']} times).")

    return " ".join(parts)
