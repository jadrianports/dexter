"""User taste summary generation from database. Read-only queries."""

from __future__ import annotations

import aiosqlite


async def get_user_summary(db: aiosqlite.Connection, user_id: str) -> str | None:
    """Generate a natural language summary of a user's music taste.

    Returns None if the user has no history.
    """
    cursor = await db.execute(
        "SELECT username, total_songs_queued FROM user_profiles WHERE user_id = ?",
        (user_id,),
    )
    profile = await cursor.fetchone()
    if not profile:
        return None

    username = profile["username"]
    total = profile["total_songs_queued"]

    cursor = await db.execute(
        """SELECT artist, play_count FROM user_artist_counts
           WHERE user_id = ?
           ORDER BY play_count DESC LIMIT 5""",
        (user_id,),
    )
    top_artists = await cursor.fetchall()
    artist_parts = [f"{row['artist']} ({row['play_count']})" for row in top_artists]

    cursor = await db.execute(
        """SELECT title, COUNT(*) as cnt FROM song_history
           WHERE user_id = ?
           GROUP BY title ORDER BY cnt DESC LIMIT 1""",
        (user_id,),
    )
    top_song = await cursor.fetchone()

    parts = [f"User '{username}': {total} songs queued."]

    if artist_parts:
        parts.append(f"Top artists: {', '.join(artist_parts)}.")

    if top_song and top_song["cnt"] > 1:
        parts.append(f"Most repeated: {top_song['title']} ({top_song['cnt']} times).")

    return " ".join(parts)
