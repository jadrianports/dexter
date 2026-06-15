# Phase 5: Ship It Live (Koyeb + Neon Re-target) — Pattern Map

**Mapped:** 2026-06-15
**Files analyzed:** 8 (net-new code targets from RESEARCH integration map)
**Analogs found:** 8 / 8 (all files have at least a role-match analog; 2 are exact matches)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `config.py` (new `sanitize_database_url` + new constants) | config / pure-logic | transform (string sanitize) | `database.py:19-59` (`get_local_date`, `compute_streak`) | role-match (pure testable function in non-config file; closest structural match) |
| `bot.py` — `create_pool` call site (~line 223) | async-runtime / wiring | request-response (DB init) | `bot.py:223-228` (the call itself — replace in place) | exact |
| `bot.py` — `_run_health_server()` new background task | async-runtime / service | request-response (HTTP) | `bot.py:377-477` (`idle_check`, `cache_cleanup`, `ytdlp_update` task loop pattern) | role-match (task-launch pattern; aiohttp server itself is net-new) |
| `tests/test_config.py` (new file) | test | transform (unit) | `tests/test_streak.py` | exact |
| `utils/logger.py` — stdout handler confirm/fix | utility / config | batch (logging) | `utils/logger.py:40-43` (existing `StreamHandler`) | exact |
| `requirements.txt` — pin yt-dlp + explicit aiohttp | config / infra | — | `requirements.txt:1-13` (existing pinned lines) | exact |
| `Dockerfile` — comment cleanup lines 1-4 | infra | — | `Dockerfile:1-4` (existing header comments) | exact |
| `scripts/` — archive Oracle scripts | infra / ops | — | `scripts/` directory (the files themselves) | exact (retire/move, no code analog needed) |

---

## Pattern Assignments

### `config.py` — new `sanitize_database_url()` + new constants (K-04/K-05/K-07)

**Role:** config + pure-logic
**Analog:** `database.py:19-59` (pure functions `get_local_date` / `compute_streak`)

**Pattern: how pure testable functions are structured in this codebase** (`database.py:14-59`):
```python
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
    ...
    Pure function — fully unit-testable (D-17).
    """
```

Key conventions to copy:
- Section header comment (`# --- Phase 5: Neon pool tuning (K-04) ---`) matches the existing block pattern in `config.py:88-100`
- Pure helper functions get a docstring that includes "Pure function — fully unit-testable" and the decision reference (e.g. "K-05")
- No imports at module level for standard-library-only helpers (`import re` can go inside the function body, matching how `database.py` keeps its imports minimal at top)

**Pattern: constant block format** (`config.py:88-100`):
```python
# --- Phase 4: Database (Postgres) ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dexter:dexter@localhost:5432/dexter")
DB_POOL_MIN = 2
DB_POOL_MAX = 10

# --- Phase 4: Queue persistence ---
MAX_QUEUE_SIZE_PER_GUILD = 500
```

**New constants to add** (after line 100 in `config.py`, following the same block convention):
```python
# --- Phase 5: Neon pool tuning (K-04) ---
DB_POOL_MAX = 5                          # was 10; trimmed for Neon free single-worker (K-04)
DB_MAX_INACTIVE_CONN_LIFETIME = 240      # recycle before Neon 5-min scale-to-zero (K-04)
DB_STATEMENT_CACHE_SIZE = 0             # disable prepared stmts for PgBouncer tx-mode (K-04)
AUDIO_CACHE_MAX_MB = 512                # was 2048; Koyeb 2GB ephemeral disk (K-07)
```

Note: `DB_POOL_MAX` and `AUDIO_CACHE_MAX_MB` are updates to existing constants, not new lines; edit in place at `config.py:22` and `config.py:91`.

**`sanitize_database_url` function** — place after the constants block at bottom of `config.py`:
```python
def sanitize_database_url(dsn: str) -> str:
    """Strip asyncpg-incompatible query params from a Neon connection string.

    Neon's console DSN includes ?sslmode=require&channel_binding=require.
    asyncpg does not recognize channel_binding and may treat it as a Postgres
    GUC, causing an error. sslmode is handled via explicit ssl= kwarg in
    create_pool. Strips the entire query string; safe for non-Neon DSNs
    (no-op if no ? present).

    Pure function — fully unit-testable (K-05).
    """
    import re
    return re.sub(r'\?.*$', '', dsn)
```

---

### `bot.py` — `create_pool` call site modification (K-04/K-05)

**Role:** async-runtime wiring
**Analog:** `bot.py:223-228` — the current call, replaced in place

**Current pattern** (`bot.py:223-228`):
```python
    bot.pool = await asyncpg.create_pool(
        dsn=config.DATABASE_URL,
        min_size=config.DB_POOL_MIN,
        max_size=config.DB_POOL_MAX,
        command_timeout=30,
    )
```

**Replace with** (same indentation, same location inside `_initialize_once()`, same surrounding comment block preserved):
```python
    bot.pool = await asyncpg.create_pool(
        dsn=config.sanitize_database_url(config.DATABASE_URL),
        min_size=config.DB_POOL_MIN,
        max_size=config.DB_POOL_MAX,          # now 5 via K-04 constant update
        command_timeout=30,
        ssl='require',                         # K-05: explicit ssl, not via DSN string
        max_inactive_connection_lifetime=config.DB_MAX_INACTIVE_CONN_LIFETIME,  # K-04: 240s
        statement_cache_size=config.DB_STATEMENT_CACHE_SIZE,                     # K-04: 0
    )
```

Use config constants for the new params (consistent with `min_size=config.DB_POOL_MIN` pattern already in place). The surrounding `# SECURITY (T-04-05)` comment block at `bot.py:221-222` stays unchanged.

---

### `bot.py` — `_run_health_server()` new background task (K-02 amendment)

**Role:** async-runtime / HTTP service
**Analog:** `bot.py:377-477` — existing `tasks.loop` background tasks + `before_loop` guards

**Pattern: how background tasks are started** (`bot.py:274-282`):
```python
    # Start background tasks
    if not idle_check.is_running():
        idle_check.start()
    if not cache_cleanup.is_running():
        cache_cleanup.start()
    if not ytdlp_update.is_running():
        ytdlp_update.start()
    if not status_rotation.is_running():
        status_rotation.start()
```

**Pattern: `before_loop` guard** (`bot.py:453-455`):
```python
@idle_check.before_loop
async def before_idle_check():
    await bot.wait_until_ready()
```

**Pattern: plain `asyncio.create_task` for non-loop background work** — the health server is a long-running coroutine (not a periodic `tasks.loop`), so use `asyncio.ensure_future` or `asyncio.create_task`, NOT `@tasks.loop`.

The health server function itself is net-new (aiohttp, no codebase analog for the implementation). Use `aiohttp.web` which is already an explicit dep in `requirements.txt:13`. Start pattern to use inside `_initialize_once()`, after the existing background task starts (after line 282), so it follows the established ordering:

```python
    # K-02: Minimal HTTP health endpoint for Koyeb WEB service
    # Must start before bot.run() and run in the same event loop.
    asyncio.ensure_future(_run_health_server())
    log.info("Health server task scheduled")
```

The `_run_health_server` coroutine is defined at module level (like `idle_check`, `cache_cleanup`, etc.), before `on_ready`. Import style matches `bot.py:1-11`:

```python
from aiohttp import web as _aio_web   # add to imports block at top of bot.py
```

The `_` prefix on the alias (`_aio_web`) signals it is an internal/implementation import — consistent with how `bot.py` uses `_pick_random` (local alias pattern) and `_post_startup_messages` (underscore-prefixed private helpers).

---

### `tests/test_config.py` — new unit test file (Wave 0)

**Role:** test
**Analog:** `tests/test_streak.py` (closest exact match — pure-function unit tests, no DB, same conventions)

**Imports pattern** (`tests/test_streak.py:1-13`):
```python
"""Tests for pure streak math: compute_streak and get_local_date.

These tests do NOT use aiosqlite — compute_streak and get_local_date are
pure functions (no DB, no Discord objects) and must stay that way.
"""

from datetime import timedelta

import pytest

from database import compute_streak, get_local_date


TZ = "America/New_York"
```

**Class-based test grouping pattern** (`tests/test_streak.py:17-96`):
```python
class TestGetLocalDate:
    def test_returns_date_object(self):
        ...

    def test_matches_datetime_now_tz(self):
        ...


class TestComputeStreakFirstActivity:
    def test_none_last_date_starts_at_1(self):
        ...
```

**Copy this structure for `tests/test_config.py`:**
```python
"""Tests for config.py pure helpers: sanitize_database_url.

These tests do NOT touch the DB, Discord, or any network — sanitize_database_url
is a pure string function and must stay that way. (K-05)
"""

import pytest

from config import sanitize_database_url


class TestSanitizeDatabaseUrl:
    def test_strips_query_string_with_neon_params(self):
        raw = "postgresql://user:pass@host-pooler.neon.tech/db?sslmode=require&channel_binding=require"
        result = sanitize_database_url(raw)
        assert result == "postgresql://user:pass@host-pooler.neon.tech/db"

    def test_noop_when_no_query_string(self):
        raw = "postgresql://user:pass@host/db"
        result = sanitize_database_url(raw)
        assert result == raw

    def test_strips_reversed_param_order(self):
        raw = "postgresql://user:pass@host/db?channel_binding=require&sslmode=require"
        result = sanitize_database_url(raw)
        assert result == "postgresql://user:pass@host/db"
```

Note: no `@pytest.mark.asyncio` needed (function is synchronous). No fixtures. No conftest imports. Matches the "pure function, no external deps" style of `test_streak.py`.

---

### `utils/logger.py` — stdout handler confirm/fix (K-16)

**Role:** utility / config
**Analog:** `utils/logger.py:40-43` (existing `StreamHandler` — the file to confirm, not replace)

**Current state** (`utils/logger.py:40-43`):
```python
    # Console handler — always on during development
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
```

`logging.StreamHandler()` with no argument defaults to `sys.stderr`. Koyeb captures both stdout and stderr in its log viewer, so this is already adequate (K-16: no functional change required). Optional improvement: change to `logging.StreamHandler(sys.stdout)` to follow Docker log convention — requires adding `import sys` at top of `utils/logger.py` (not currently imported).

**Decision:** Change to `sys.stdout` for clarity and Docker convention alignment. Minimal risk.

**Updated line** (replace `utils/logger.py:41`):
```python
    console_handler = logging.StreamHandler(sys.stdout)
```

**Add `import sys`** at `utils/logger.py:5` (after `from __future__ import annotations`, before `import logging`).

---

### `requirements.txt` — pin yt-dlp + explicit aiohttp (K-15)

**Role:** config / infra
**Analog:** `requirements.txt:1-13` (existing file — `asyncpg==0.31.0` at line 3 is the pinned-version model)

**Current state** (`requirements.txt:1-13`):
```
discord.py>=2.3.0
yt-dlp
asyncpg==0.31.0
python-dotenv
PyNaCl
davey
google-genai
pytest
pytest-asyncio
tzdata
lyricsgenius
beautifulsoup4
aiohttp
```

**Changes:**
- Line 2: `yt-dlp` → `yt-dlp>=2025.6.9` (pin a recent stable floor; daily self-heal in bot handles future updates)
- Line 13: `aiohttp` → `aiohttp>=3.9.0` (already present as transitive dep; explicit version floor guards against discord.py ever dropping it — per Research open question #1)

Pinning model: `asyncpg==0.31.0` (exact pin for critical DB driver); `yt-dlp>=2025.6.9` (floor pin, self-heal updates beyond it). Use floor pin (`>=`) not exact pin (`==`) for yt-dlp since the bot self-updates it at runtime.

---

### `Dockerfile` — comment cleanup lines 1-4 (K-11/K-12)

**Role:** infra
**Analog:** `Dockerfile:1-4` — the lines being replaced

**Current state** (`Dockerfile:1-8`):
```dockerfile
# Source: hub.docker.com/r/arm64v8/python; Oracle A1 ARM (arm64) target
# Builds the Dexter Discord bot image with ffmpeg (audio) + curl.
# Secrets are injected at runtime via docker-compose env_file (.env) — never bake
# token/password/key literals into image layers (T-04-05).
FROM python:3.11-slim-bookworm

# Install system deps: ffmpeg (opus audio processing), curl (available in-container if needed)
# arm64-native packages in Debian Bookworm — no cross-compile needed on Oracle A1 ARM.
```

**Replace lines 1-4 and 7-8 with** (rest of Dockerfile from line 5 onward is unchanged):
```dockerfile
# Dexter Discord bot image — multi-arch (amd64 on Koyeb/CI, arm64 on dev machines).
# Koyeb builds this Dockerfile directly from git (K-11); docker-compose.yml is local-dev only (K-12).
# Secrets are injected at runtime via env vars — never bake token/key literals into image layers (T-04-05).
FROM python:3.11-slim-bookworm

# Install system deps: ffmpeg (opus audio processing), curl (available in-container if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
```

The `FROM python:3.11-slim-bookworm` base image is already multi-arch and works on Koyeb amd64 without change. Drop `arm64v8/` source reference and Oracle/arm64 notes.

---

### `scripts/` — Oracle script retirement (K-08/K-09/K-11)

**Role:** ops / infra
**No code analog needed** — this is a file-move operation.

**Disposition table** (from RESEARCH.md):

| File | Action | Replacement |
|------|--------|-------------|
| `scripts/backup.sh` | Move to `scripts/archive/` | Neon-managed PITR |
| `scripts/keepalive.sh` | Move to `scripts/archive/` | UptimeRobot external ping |
| `scripts/deploy.sh` | Move to `scripts/archive/` | Koyeb git-auto-build |
| `scripts/lifecycle-policy.json` | Move to `scripts/archive/` | No OCI bucket |
| `scripts/seed_restore_test.py` | Keep at `scripts/` (optional) | Useful for PITR UAT roast-fuel |

**Implementation:** `git mv scripts/backup.sh scripts/archive/backup.sh` (etc.) — keeps git history intact, removes from active working tree. Create `scripts/archive/` directory first.

---

## Shared Patterns

### Pure-function docstring convention
**Source:** `database.py:19-59`
**Apply to:** `config.sanitize_database_url`
- One-line summary, blank line, then multi-sentence explanation of what/why
- Final line: `Pure function — fully unit-testable (decision-ref).`
- Decision reference in parentheses (e.g. `K-05`)

### Config constant block header comment
**Source:** `config.py:56`, `config.py:88`
**Apply to:** new Phase 5 constants block in `config.py`
```python
# --- Phase 5: Neon pool tuning (K-04) ---
```
Pattern: `# --- Phase N: short-description (decision-ref) ---`

### Background task guard pattern
**Source:** `bot.py:274-282`
**Apply to:** health server task launch in `_initialize_once()`
```python
    if not idle_check.is_running():
        idle_check.start()
```
The health server uses `asyncio.ensure_future(...)` instead of `.start()` (it is a one-shot coroutine, not a `tasks.loop`), but follows the same "start after all cog loads, before queue restore" ordering established at `bot.py:274-290`.

### `before_loop` guard
**Source:** `bot.py:453-455`
**Apply to:** NOT needed for `_run_health_server` (it starts immediately, not waiting for `wait_until_ready`, because the health endpoint must be up before Discord connects so Koyeb's health check can pass)

### Unit test class grouping
**Source:** `tests/test_streak.py:17-96`
**Apply to:** `tests/test_config.py`
- One class per logical function under test
- Method names: `test_<condition>_<expected_outcome>`
- No `async` on sync-function tests
- No fixtures for pure-function tests

---

## No Analog Found

None. All 8 files have usable analogs. The aiohttp health server *implementation* is net-new (no existing aiohttp web server in the codebase), but the *task-launch pattern* has a clear analog in `bot.py:274-282`.

---

## Metadata

**Analog search scope:** `bot.py`, `config.py`, `database.py`, `utils/logger.py`, `requirements.txt`, `Dockerfile`, `tests/test_streak.py`, `tests/test_database_phase4.py`
**Files read:** 10
**Pattern extraction date:** 2026-06-15
