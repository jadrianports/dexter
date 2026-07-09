#!/usr/bin/env python3
"""D-15: Seed known rows → backup → restore into throwaway DB → verify → teardown.

Non-destructive restore proof:
  1. Connect to the live 'dexter' DB via asyncpg and INSERT known seed rows.
  2. Run scripts/backup.sh to produce a fresh dump and upload it to OCI.
  3. Download the newest dexter_* dump from OCI Object Storage.
  4. Validate dump file is above a minimum size (guards the pipe-masks-failure pitfall).
  5. Create the throwaway DB 'dexter_restore_test' inside the Postgres container
     (via docker compose exec) — never touches the live 'dexter' DB.
  6. Restore via 'docker compose exec -T postgres pg_restore' (Option B, version-matched
     — avoids the host pg_restore version-mismatch landmine, Pitfall 4).
  7. Connect to 'dexter_restore_test', assert row counts equal the seeded counts.
  8. Drop the throwaway DB.
  9. Delete the seed rows from the LIVE 'dexter' DB so the proof leaves no trace
     (runs in a finally — the live DB is cleaned even if an earlier step fails).

This script is run ONCE manually by the user on Oracle (runbook check D1).
It is NOT a cron job and is NOT executed on the dev machine.

Security (T-05-05): restore/createdb/dropdb target ONLY 'dexter_restore_test'.
  The live 'dexter' DB is read (for seeding) but never passed to pg_restore,
  createdb, or dropdb. The dropdb call is guarded to the THROWAWAY_DB constant.
  The seed rows written to the live DB are removed in step 9 (_cleanup_seed),
  so the proof is fully non-destructive AND leaves no residue (CR-02).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
from urllib.parse import urlsplit, urlunsplit

import asyncpg

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

THROWAWAY_DB = "dexter_restore_test"  # target for all restore/createdb/dropdb ops
SEED_USER_ID = "999999999999999999"  # obviously-fake Discord snowflake

MIN_DUMP_SIZE_BYTES = 1024  # guard: a valid pg_dump custom-format file is > 1 KB
BUCKET = "dexter-backups"


# ---------------------------------------------------------------------------
# Pure seed-row builder (no IO — importable and unit-testable)
# ---------------------------------------------------------------------------


def build_seed_rows() -> dict:
    """Return the seed row dicts for user_profiles, song_history, user_artist_counts.

    This function performs NO IO and has no side effects. The test suite imports
    it directly to validate the data shape without a DB connection.

    Column names match database.py SCHEMA_SQL exactly (no invented columns).
    Streak columns (current_streak, longest_streak, last_streak_date) are
    included per the actual user_profiles schema in database.py.
    """
    user_profiles = [
        {
            "user_id": SEED_USER_ID,
            "username": "seed_user",
            "total_songs_queued": 3,
            "current_streak": 2,
            "longest_streak": 5,
            "last_streak_date": "2026-01-01",
        },
    ]

    song_history = [
        {
            "guild_id": "111111111111111111",
            "user_id": SEED_USER_ID,
            "title": "Seed Song Alpha",
            "artist": "Artist A",
            "url": "https://www.youtube.com/watch?v=seed_alpha",
            "duration_seconds": 180,
        },
        {
            "guild_id": "111111111111111111",
            "user_id": SEED_USER_ID,
            "title": "Seed Song Beta",
            "artist": "Artist B",
            "url": "https://www.youtube.com/watch?v=seed_beta",
            "duration_seconds": 240,
        },
        {
            "guild_id": "111111111111111111",
            "user_id": SEED_USER_ID,
            "title": "Seed Song Gamma",
            "artist": "Artist A",
            "url": "https://www.youtube.com/watch?v=seed_gamma",
            "duration_seconds": 210,
        },
    ]

    user_artist_counts = [
        {
            "user_id": SEED_USER_ID,
            "artist": "Artist A",
            "play_count": 2,
        },
        {
            "user_id": SEED_USER_ID,
            "artist": "Artist B",
            "play_count": 1,
        },
    ]

    return {
        "user_profiles": user_profiles,
        "song_history": song_history,
        "user_artist_counts": user_artist_counts,
    }


# ---------------------------------------------------------------------------
# DB helpers (async, connect to a named DB)
# ---------------------------------------------------------------------------


async def _get_pool(db_name: str) -> asyncpg.Pool:
    """Create an asyncpg connection pool for the given database name.

    Reads the DATABASE_URL from the environment and substitutes the DB name.
    Falls back to the standard dexter DSN pattern with the given db_name.
    """
    base_url = os.getenv(
        "DATABASE_URL",
        "postgresql://dexter:dexter@localhost:5432/dexter",
    )
    # Swap ONLY the path (db name) component, preserving query params like
    # ?sslmode=require — a naive rpartition("/") mangles those, so the throwaway
    # pool would connect with different TLS/settings than the live pool (WR-06).
    parts = urlsplit(base_url)
    dsn = urlunsplit(parts._replace(path=f"/{db_name}"))
    return await asyncpg.create_pool(dsn)


async def _seed(pool: asyncpg.Pool, rows: dict) -> None:
    """Insert seed rows into the live 'dexter' DB."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            # user_profiles
            for p in rows["user_profiles"]:
                await conn.execute(
                    "INSERT INTO user_profiles"
                    " (user_id, username, total_songs_queued,"
                    "  current_streak, longest_streak, last_streak_date)"
                    " VALUES ($1, $2, $3, $4, $5, $6)"
                    " ON CONFLICT (user_id) DO UPDATE SET"
                    "   username = EXCLUDED.username,"
                    "   total_songs_queued = EXCLUDED.total_songs_queued,"
                    "   current_streak = EXCLUDED.current_streak,"
                    "   longest_streak = EXCLUDED.longest_streak,"
                    "   last_streak_date = EXCLUDED.last_streak_date",
                    p["user_id"],
                    p["username"],
                    p["total_songs_queued"],
                    p["current_streak"],
                    p["longest_streak"],
                    p["last_streak_date"],
                )
            # song_history
            for s in rows["song_history"]:
                await conn.execute(
                    "INSERT INTO song_history"
                    " (guild_id, user_id, title, artist, url, duration_seconds)"
                    " VALUES ($1, $2, $3, $4, $5, $6)",
                    s["guild_id"],
                    s["user_id"],
                    s["title"],
                    s["artist"],
                    s["url"],
                    s["duration_seconds"],
                )
            # user_artist_counts
            for a in rows["user_artist_counts"]:
                await conn.execute(
                    "INSERT INTO user_artist_counts (user_id, artist, play_count)"
                    " VALUES ($1, $2, $3)"
                    " ON CONFLICT (user_id, artist)"
                    " DO UPDATE SET play_count = EXCLUDED.play_count",
                    a["user_id"],
                    a["artist"],
                    a["play_count"],
                )
    print(
        f"[seed_restore_test] Seeded {len(rows['user_profiles'])} user_profiles, "
        f"{len(rows['song_history'])} song_history, "
        f"{len(rows['user_artist_counts'])} user_artist_counts rows into live DB."
    )


async def _cleanup_seed() -> None:
    """Delete every seeded row from the LIVE 'dexter' DB (CR-02).

    Rows are identified solely by SEED_USER_ID — a fake snowflake no real user can
    own — so this can never touch genuine production data. Called from main()'s
    finally block so the live DB is cleaned even if the backup/restore cycle raises.
    Without this, the fake rows permanently corrupt /history, milestone counts, and
    top-artist roast logic for real users.
    """
    pool = await _get_pool("dexter")
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM song_history WHERE user_id = $1", SEED_USER_ID)
                await conn.execute("DELETE FROM user_artist_counts WHERE user_id = $1", SEED_USER_ID)
                await conn.execute("DELETE FROM user_profiles WHERE user_id = $1", SEED_USER_ID)
    finally:
        await pool.close()
    print(f"[seed_restore_test] Removed seed rows for user {SEED_USER_ID} from live DB.")


async def _verify(pool: asyncpg.Pool, expected: dict) -> None:
    """Assert row counts in dexter_restore_test match the seeded counts."""
    async with pool.acquire() as conn:
        up_count = await conn.fetchval(
            "SELECT COUNT(*) FROM user_profiles WHERE user_id = $1",
            SEED_USER_ID,
        )
        sh_count = await conn.fetchval(
            "SELECT COUNT(*) FROM song_history WHERE user_id = $1",
            SEED_USER_ID,
        )
        uac_count = await conn.fetchval(
            "SELECT COUNT(*) FROM user_artist_counts WHERE user_id = $1",
            SEED_USER_ID,
        )

    expected_up = len(expected["user_profiles"])
    expected_sh = len(expected["song_history"])
    expected_uac = len(expected["user_artist_counts"])

    print("[seed_restore_test] Restore verification:")
    print(f"  user_profiles  (seed user): expected={expected_up}, got={up_count}")
    print(f"  song_history   (seed user): expected={expected_sh}, got={sh_count}")
    print(f"  user_artist_counts (seed user): expected={expected_uac}, got={uac_count}")

    assert up_count == expected_up, f"user_profiles mismatch: expected {expected_up}, got {up_count}"
    assert sh_count == expected_sh, f"song_history mismatch: expected {expected_sh}, got {sh_count}"
    assert uac_count == expected_uac, f"user_artist_counts mismatch: expected {expected_uac}, got {uac_count}"
    print("[seed_restore_test] All row counts match. Restore verified OK.")


# ---------------------------------------------------------------------------
# OCI helpers
# ---------------------------------------------------------------------------


def _get_oci_namespace() -> str:
    """Retrieve the OCI Object Storage namespace."""
    result = subprocess.run(
        ["oci", "os", "ns", "get", "--query", "data", "--raw-output"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _download_latest_dump(namespace: str, dest_path: str) -> None:
    """List objects in the bucket and download the newest dexter_* dump."""
    # List objects sorted by name (timestamps embedded in name give chronological order)
    result = subprocess.run(
        [
            "oci",
            "os",
            "object",
            "list",
            "--namespace-name",
            namespace,
            "--bucket-name",
            BUCKET,
            "--prefix",
            "dexter_",
            "--query",
            "data[*].name",
            "--output",
            "json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    names = json.loads(result.stdout)
    if not names:
        raise RuntimeError(f"No objects with prefix 'dexter_' found in bucket '{BUCKET}'. Has backup.sh been run yet?")
    # Names are ISO-timestamped — lexicographic sort gives chronological order
    latest = sorted(names)[-1]
    print(f"[seed_restore_test] Downloading latest dump: {latest}")

    subprocess.run(
        [
            "oci",
            "os",
            "object",
            "get",
            "--namespace-name",
            namespace,
            "--bucket-name",
            BUCKET,
            "--name",
            latest,
            "--file",
            dest_path,
        ],
        check=True,
    )
    size = os.path.getsize(dest_path)
    print(f"[seed_restore_test] Downloaded {size} bytes to {dest_path}")
    if size < MIN_DUMP_SIZE_BYTES:
        raise RuntimeError(
            f"Dump file is suspiciously small ({size} bytes < {MIN_DUMP_SIZE_BYTES}). "
            "Possible pg_dump pipe failure — check backup.sh logs."
        )


# ---------------------------------------------------------------------------
# Docker compose helpers (all pg_restore/createdb/dropdb target THROWAWAY_DB)
# ---------------------------------------------------------------------------


def _docker_exec(*args: str) -> None:
    """Run 'docker compose exec postgres <args>' and raise on failure."""
    cmd = ["docker", "compose", "exec", "postgres"] + list(args)
    subprocess.run(cmd, check=True)


def _docker_exec_stdin(stdin_bytes: bytes, *args: str) -> None:
    """Run 'docker compose exec -T postgres <args>' with stdin piped from bytes."""
    cmd = ["docker", "compose", "exec", "-T", "postgres"] + list(args)
    subprocess.run(cmd, input=stdin_bytes, check=True)


def _createdb_throwaway() -> None:
    """Create dexter_restore_test inside the Postgres container (template0)."""
    _docker_exec("createdb", "-U", "dexter", "-T", "template0", THROWAWAY_DB)
    print(f"[seed_restore_test] Created throwaway DB: {THROWAWAY_DB}")


def _restore_into_throwaway(dump_path: str) -> None:
    """Restore the dump into dexter_restore_test via docker compose exec (version-matched).

    Uses Option B (docker exec pg_restore) to avoid the host pg_restore version-mismatch
    pitfall (Pitfall 4 in RESEARCH.md).
    """
    with open(dump_path, "rb") as f:
        dump_bytes = f.read()
    _docker_exec_stdin(
        dump_bytes,
        "pg_restore",
        "-U",
        "dexter",
        "-d",
        THROWAWAY_DB,  # always the throwaway — never the live DB
        "--no-owner",
        "--no-acl",
    )
    print(f"[seed_restore_test] pg_restore into {THROWAWAY_DB} complete.")


def _dropdb_throwaway() -> None:
    """Drop dexter_restore_test — guarded to only target the throwaway name."""
    # Security guard (T-05-05): hardcoded THROWAWAY_DB constant — can never
    # accidentally drop the live 'dexter' DB.
    _docker_exec("dropdb", "-U", "dexter", THROWAWAY_DB)
    print(f"[seed_restore_test] Dropped throwaway DB: {THROWAWAY_DB}")


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


async def main() -> None:
    """End-to-end D-15 seed → backup → restore-verify → live-DB teardown."""
    rows = build_seed_rows()
    print("[seed_restore_test] Starting D-15 non-destructive restore proof.")

    # 1. Connect to live DB and seed known rows
    print("[seed_restore_test] Step 1: Seeding known rows into live 'dexter' DB...")
    live_pool = await _get_pool("dexter")
    try:
        await _seed(live_pool, rows)
    finally:
        await live_pool.close()

    # Everything after seeding runs inside a try whose finally ALWAYS removes the
    # seed rows from the live DB — even if backup/download/restore raises (CR-02).
    try:
        # 2. Run backup.sh to produce a fresh dump and upload to OCI
        print("[seed_restore_test] Step 2: Running backup.sh...")
        subprocess.run(["bash", "scripts/backup.sh"], check=True)

        # 3. Download the newest dump from OCI
        print("[seed_restore_test] Step 3: Downloading latest dump from OCI...")
        namespace = _get_oci_namespace()
        with tempfile.NamedTemporaryFile(suffix=".dump", delete=False, prefix="dexter_restore_") as tmp:
            dump_path = tmp.name

        try:
            _download_latest_dump(namespace, dump_path)

            # 4. Create the throwaway DB
            print("[seed_restore_test] Step 4: Creating throwaway DB...")
            _createdb_throwaway()

            try:
                # 5. Restore into throwaway DB
                print("[seed_restore_test] Step 5: Restoring dump into throwaway DB...")
                _restore_into_throwaway(dump_path)

                # 6. Verify row counts in the throwaway DB
                print("[seed_restore_test] Step 6: Verifying row counts in throwaway DB...")
                restore_pool = await _get_pool(THROWAWAY_DB)
                try:
                    await _verify(restore_pool, rows)
                finally:
                    await restore_pool.close()

            finally:
                # 7. Always drop the throwaway DB
                print("[seed_restore_test] Step 7: Dropping throwaway DB...")
                _dropdb_throwaway()

        finally:
            # Clean up temp dump file
            if os.path.exists(dump_path):
                os.unlink(dump_path)
                print(f"[seed_restore_test] Cleaned up temp dump file: {dump_path}")

    finally:
        # 8/9. ALWAYS remove the seed rows from the LIVE DB (CR-02) — runs whether
        # the restore proof passed or raised, so the live DB never keeps fake rows.
        print("[seed_restore_test] Step 9: Removing seed rows from live 'dexter' DB...")
        await _cleanup_seed()

    print("[seed_restore_test] D-15 restore proof PASSED.")


if __name__ == "__main__":
    asyncio.run(main())
