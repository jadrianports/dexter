"""Shared pytest fixtures for Phase 4 integration tests.

These fixtures require a running PostgreSQL instance.
The test database DSN is read from TEST_DATABASE_URL (default:
postgresql://dexter:dexter@localhost:5432/dexter_test).

To create the test database:
    psql -U postgres -c "CREATE DATABASE dexter_test;"
    psql -U postgres -c "CREATE USER dexter WITH PASSWORD 'dexter';"
    psql -U postgres -c "GRANT ALL ON DATABASE dexter_test TO dexter;"

These tests are skipped (connection error) when no Postgres is available.
The autonomous gate is --collect-only (no live DB needed for test discovery).
"""

from __future__ import annotations

import os

import asyncpg
import pytest_asyncio

from database import init_db


@pytest_asyncio.fixture
async def pool():
    """asyncpg pool pointed at the dexter_test database.

    Creates all schema tables via init_db, yields the pool, then drops all
    tables in teardown so each test run starts clean.

    Skips the test (not errors) when Postgres is unavailable — matching the
    documented "skipped (connection error)" behaviour in the module docstring.
    """
    import pytest  # local import keeps the global namespace clean

    dsn = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://dexter:dexter@localhost:5432/dexter_test",
    )
    try:
        p = await asyncpg.create_pool(dsn)
    except Exception as exc:
        pytest.skip(f"Postgres unavailable ({exc}); skipping live-DB test")
        return  # unreachable — skip raises; satisfies type checkers

    await init_db(p)
    yield p
    async with p.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS guild_queues, song_history,"
            " user_artist_counts, image_generation_log,"
            " bot_daily_stats, user_profiles,"
            " user_favorites, user_playlists, user_playlist_tracks,"
            " resolution_cache CASCADE"
        )
    await p.close()
