# Phase 4: Scale - Pattern Map

**Mapped:** 2026-06-12
**Files analyzed:** 12 (7 modified, 5 created)
**Analogs found:** 12 / 12 (all have close analogs; infra/scripts are greenfield with doc-only reference)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `database.py` | db-layer | CRUD (batch) | `database.py` itself (full rewrite) | self |
| `models/queue.py` | model | transform | `models/queue.py` itself + RESEARCH.md Track example | self + spec |
| `bot.py` | orchestrator | event-driven | `bot.py` itself (targeted changes) | self |
| `config.py` | config | — | `config.py` itself (additive) | self |
| `cogs/music.py` | cog | request-response | `cogs/music.py` itself (mutation hook injection) | self |
| `models/message_buffer.py` | model | transform | `models/message_buffer.py` itself (additive) | self |
| `services/gemini.py` | service | request-response | `services/gemini.py` itself (confirm only) | self |
| `services/queue_persistence.py` (NEW) | service | CRUD | `services/gemini.py` — service wired in `bot.py` `on_ready`, accessed via `self.bot.<svc>` | role-match |
| `docker-compose.yml` (NEW) | infra | — | no existing file — greenfield | none |
| `Dockerfile` (NEW) | infra | — | no existing file — greenfield | none |
| `scripts/keepalive.sh` (NEW) | infra/script | — | no existing scripts/ dir — greenfield | none |
| `scripts/backup.sh` (NEW) | infra/script | — | no existing scripts/ dir — greenfield | none |
| `tests/test_database_phase4.py` (NEW) | test | CRUD | `tests/test_database_phase3.py` | exact |
| `tests/conftest.py` (NEW) | test fixture | — | `tests/test_database.py` fixture block (lines 11-17) | role-match |

---

## Pattern Assignments

### `database.py` (db-layer, full rewrite — aiosqlite → asyncpg)

**Analog:** `database.py` itself. The full file is the before-state; every pattern shown is what to REPLACE.

**Current import pattern** (lines 1-11) — REMOVE `aiosqlite`, ADD `asyncpg`:
```python
# BEFORE (remove):
import aiosqlite
# AFTER:
import asyncpg
import json   # for guild_queues jsonb payload
```

**Current `init_db` signature and PRAGMA block** (lines 143-152) — REPLACE entirely:
```python
# BEFORE:
async def init_db(db: aiosqlite.Connection) -> None:
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    await db.executescript(SCHEMA_SQL)
    await migrate_add_streak_columns(db)
    await db.commit()
    log.info("Database schema initialized")

# AFTER — pool param, no PRAGMAs, no executescript, no migrate:
async def init_db(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)   # multi-stmt DDL: asyncpg accepts it when no $N params present
    log.info("Database schema initialized")
```

**Current per-call commit pattern** (lines 155-171) — REPLACE with pool.acquire():
```python
# BEFORE (every helper):
async def log_song(db: aiosqlite.Connection, *, guild_id: str, ...) -> None:
    await db.execute("INSERT INTO song_history ... VALUES (?, ?, ?, ?, ?, ?)",
                     (guild_id, user_id, title, artist, url, duration))
    await db.commit()

# AFTER — pool, $N placeholders, no explicit commit (asyncpg auto-commits outside transaction):
async def log_song(pool: asyncpg.Pool, *, guild_id: str, ...) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO song_history (guild_id, user_id, title, artist, url, duration_seconds)"
            " VALUES ($1, $2, $3, $4, $5, $6)",
            guild_id, user_id, title, artist, url, duration,
        )
```

**Current ON CONFLICT upsert** (lines 180-186) — ports VERBATIM, only `?` → `$N`:
```python
# BEFORE:
await db.execute(
    "INSERT INTO user_artist_counts (user_id, artist, play_count) VALUES (?, ?, 1)"
    " ON CONFLICT(user_id, artist) DO UPDATE SET play_count = play_count + 1",
    (user_id, artist),
)
# AFTER:
await conn.execute(
    "INSERT INTO user_artist_counts (user_id, artist, play_count) VALUES ($1, $2, 1)"
    " ON CONFLICT (user_id, artist) DO UPDATE SET play_count = user_artist_counts.play_count + 1",
    user_id, artist,
)
```

**New batched transaction helper** (new function, replaces 3 separate calls per /play):
```python
# Pattern: async with conn.transaction() — asyncpg auto-rollbacks on exception
async def log_track_batch(pool: asyncpg.Pool, *, guild_id: str, user_id: str,
                          username: str, title: str, artist: str | None,
                          url: str, duration: int) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO song_history (guild_id, user_id, title, artist, url, duration_seconds)"
                " VALUES ($1, $2, $3, $4, $5, $6)",
                guild_id, user_id, title, artist, url, duration,
            )
            if artist is not None:
                await conn.execute(
                    "INSERT INTO user_artist_counts (user_id, artist, play_count) VALUES ($1, $2, 1)"
                    " ON CONFLICT (user_id, artist)"
                    " DO UPDATE SET play_count = user_artist_counts.play_count + 1",
                    user_id, artist,
                )
            await conn.execute(
                "INSERT INTO user_profiles (user_id, username, total_songs_queued) VALUES ($1, $2, 1)"
                " ON CONFLICT (user_id) DO UPDATE SET"
                "   username = EXCLUDED.username,"
                "   total_songs_queued = user_profiles.total_songs_queued + 1,"
                "   last_active_at = now()",
                user_id, username,
            )
```

**SCHEMA_SQL conversion rules** (replace the block at lines 65-117):
- `INTEGER PRIMARY KEY AUTOINCREMENT` → `BIGSERIAL PRIMARY KEY`
- `TEXT DEFAULT (datetime('now'))` → `TIMESTAMPTZ DEFAULT now()`
- `BOOLEAN DEFAULT 0` → `BOOLEAN DEFAULT false`
- Add `guild_queues` table (new for SCALE-04)
- Delete `migrate_add_streak_columns` entirely — streak cols go into the fresh CREATE TABLE
- `date(col) = date('now')` → `col::date = CURRENT_DATE` (in `get_repeat_song_count`, `get_images_today`)

**Functions to carry over UNCHANGED** (lines 18-58): `get_local_date`, `compute_streak` — pure Python, no SQL, fully DB-agnostic.

**Row access pattern** — `asyncpg.Record` is already dict-like (`row["field"]`), same as `aiosqlite.Row`. No change to fetch/access patterns at callers.

---

### `models/queue.py` (model, transform — additive)

**Analog:** `models/queue.py` itself. Two additions: `Track.to_dict`/`from_dict` and `MusicQueue.add()` cap enforcement.

**Existing `Track` dataclass** (lines 16-27) — copy as-is, then ADD methods:
```python
@dataclass
class Track:
    video_id: str
    title: str
    artist: str | None
    url: str
    duration_seconds: int
    requested_by: int
    was_auto_queued: bool = False
    thumbnail: str | None = None

    # ADD these two methods:
    def to_dict(self) -> dict:
        return {
            "video_id": self.video_id,
            "title": self.title,
            "artist": self.artist,
            "url": self.url,
            "duration_seconds": self.duration_seconds,
            "requested_by": self.requested_by,
            "was_auto_queued": self.was_auto_queued,
            "thumbnail": self.thumbnail,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Track":
        return cls(
            video_id=d["video_id"],
            title=d["title"],
            artist=d.get("artist"),
            url=d["url"],
            duration_seconds=d["duration_seconds"],
            requested_by=d["requested_by"],
            was_auto_queued=d.get("was_auto_queued", False),
            thumbnail=d.get("thumbnail"),
        )
```

**Existing `MusicQueue.add()`** (lines 48-51) — ADD cap check before append:
```python
# BEFORE:
def add(self, track: Track) -> int:
    self.tracks.append(track)
    return len(self.tracks) - 1

# AFTER — raise so cog layer catches it with personality message:
class QueueFullError(Exception):
    """Raised when MusicQueue.add() exceeds MAX_QUEUE_SIZE_PER_GUILD."""

def add(self, track: Track) -> int:
    if len(self.tracks) >= config.MAX_QUEUE_SIZE_PER_GUILD:
        raise QueueFullError(
            f"Queue is at capacity ({config.MAX_QUEUE_SIZE_PER_GUILD} tracks)."
        )
    self.tracks.append(track)
    return len(self.tracks) - 1
```

**`_text_channel_id` location** (line 42) — confirmed on `MusicQueue`; voice_channel_id is NOT stored here per D-20 (captured from `guild.voice_client.channel.id` at save time in the persistence service).

---

### `bot.py` (orchestrator — targeted changes only)

**Analog:** `bot.py` itself. Three change sites: base class swap, pool creation in `on_ready`, and queue-restore call after cog loading.

**`create_bot()` — base class swap** (lines 35-51):
```python
# BEFORE:
bot = commands.Bot(command_prefix="!", intents=intents, ...)
# AFTER — one word change:
bot = commands.AutoShardedBot(command_prefix="!", intents=intents, ...)
```

**`on_ready` DB setup block** (lines 162-169) — REPLACE aiosqlite with asyncpg pool:
```python
# BEFORE:
bot.db = await aiosqlite.connect(config.BASE_DIR / "data" / "dexter.db")
bot.db.row_factory = aiosqlite.Row
await init_db(bot.db)

# AFTER:
import asyncpg
bot.pool = await asyncpg.create_pool(
    dsn=config.DATABASE_URL,
    min_size=config.DB_POOL_MIN,
    max_size=config.DB_POOL_MAX,
    command_timeout=30,
)
await init_db(bot.pool)
```

**`on_ready` guard pattern** (lines 209-216 show existing task guard) — apply same `hasattr` guard for the whole init block:
```python
# Pattern: existing guard for background tasks — generalize to full on_ready init:
if not idle_check.is_running():
    idle_check.start()
# New guard for one-time init (prevents double-fire on AutoShardedBot reconnect):
if hasattr(bot, "_ready_once"):
    return
bot._ready_once = True
# ... rest of on_ready init ...
```

**Queue restore — inject AFTER `load_extension` calls, BEFORE startup message** (lines 201-235):
```python
# Inject after all load_extension calls, before startup message:
from services.queue_persistence import restore_queues
await restore_queues(bot)
```

**`on_close` — ADD pool teardown** (lines 238-241):
```python
@bot.event
async def on_close():
    if hasattr(bot, "pool"):
        await bot.pool.close()
    # remove: if hasattr(bot, "db"): await bot.db.close()
```

---

### `config.py` (config — additive only)

**Analog:** `config.py` itself. Existing pattern for new constants (lines 83-86):
```python
# Existing env-var pattern to replicate exactly:
ERROR_LOG_CHANNEL_ID = int(os.getenv("ERROR_LOG_CHANNEL_ID") or "0") or None
OWNER_ID = int(os.getenv("OWNER_ID") or "0")

# New Phase 4 constants follow the same pattern:
# --- Database (Postgres) ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dexter:dexter@localhost:5432/dexter")
DB_POOL_MIN = 2
DB_POOL_MAX = 10

# --- Queue persistence ---
MAX_QUEUE_SIZE_PER_GUILD = 500

# --- Message buffer ---
MESSAGE_BUFFER_TTL_HOURS = 24

# --- Keep-alive / down-detection ---
HEALTHCHECK_URL = os.getenv("HEALTHCHECK_URL", "")
```

**Convention:** module-level constants, `os.getenv()` for secrets/env-specific values, literal defaults for tuning values. `load_dotenv()` already called at top of file (line 11) — no change needed.

---

### `cogs/music.py` (cog — mutation hook injection + cap handling)

**Analog:** `cogs/music.py` itself. Pattern: every queue mutation today calls `queue.<method>()` directly; inject `await self.bot.queue_persistence.persist(guild, queue)` immediately after each mutation call.

**Convention for finding mutation sites** — grep the cog for these call patterns:
```
queue.add(        → after: await self.bot.queue_persistence.persist(guild, queue)
queue.skip()      → after persist
queue.advance()   → after persist
queue.shuffle()   → after persist
queue.clear()     → after persist
queue.loop_mode = → after persist
```

**Cap enforcement — catch `QueueFullError` at the cog layer** (where `/play` calls `queue.add()`):
```python
from models.queue import QueueFullError

try:
    queue.add(track)
except QueueFullError:
    await interaction.followup.send(
        f"queue's full at {config.MAX_QUEUE_SIZE_PER_GUILD} tracks. impressive dedication, wrong bot.",
        ephemeral=True,
    )
    return
```

**Voice-channel-id capture** (at persist call sites, not stored on queue model per D-20):
```python
vc_id = guild.voice_client.channel.id if guild.voice_client else None
await self.bot.queue_persistence.persist(guild, queue, vc_id)
```

**Line ~609 reconnect race — DO NOT TOUCH.** Parked per D-22.

---

### `models/message_buffer.py` (model — additive TTL eviction)

**Analog:** `models/message_buffer.py` itself. Current `__init__` (lines 11-14) and `add()` (lines 16-27) are the change sites.

**Current `__init__`** (lines 11-14) — ADD TTL tracking dict and `timedelta`:
```python
# BEFORE:
from collections import deque
from datetime import datetime

class MessageBuffer:
    def __init__(self, max_length: int = 10) -> None:
        self._max_length = max_length
        self._buffers: dict[int, deque[dict]] = {}

# AFTER — add _last_seen and _ttl:
from collections import deque
from datetime import datetime, timedelta
import config

class MessageBuffer:
    def __init__(self, max_length: int = 10) -> None:
        self._max_length = max_length
        self._buffers: dict[int, deque[dict]] = {}
        self._last_seen: dict[int, datetime] = {}
        self._ttl = timedelta(hours=config.MESSAGE_BUFFER_TTL_HOURS)
```

**Current `add()`** (lines 16-27) — prepend eviction call and update `_last_seen`:
```python
# BEFORE:
def add(self, channel_id: int, role: str, author: str, content: str) -> None:
    if channel_id not in self._buffers:
        self._buffers[channel_id] = deque(maxlen=self._max_length)
    self._buffers[channel_id].append({...})

# AFTER:
def _evict_stale(self) -> None:
    cutoff = datetime.now() - self._ttl
    stale = [ch for ch, ts in self._last_seen.items() if ts < cutoff]
    for ch in stale:
        self._buffers.pop(ch, None)
        self._last_seen.pop(ch, None)

def add(self, channel_id: int, role: str, author: str, content: str) -> None:
    self._evict_stale()
    self._last_seen[channel_id] = datetime.now()
    if channel_id not in self._buffers:
        self._buffers[channel_id] = deque(maxlen=self._max_length)
    self._buffers[channel_id].append({...})
```

---

### `services/gemini.py` (service — confirm only, no change)

**Analog:** `services/gemini.py` itself.

**Rate limiter location** (grep result — lines 46, 113, 135, 190): the `_RateLimiter` class is instantiated at line 113 as `self._rate_limiter = _RateLimiter()` inside `GeminiService.__init__`. The `_RateLimiter` uses `config.GEMINI_RPM_LIMIT` (15) as its `max_requests`.

**Confirmed:** limiter is instance-level on the single `GeminiService` object wired in `bot.on_ready` as `bot.gemini_service`. Since only one `GeminiService` instance exists for the whole bot, it is already effectively global. No change needed per D-03.

---

### `services/queue_persistence.py` (NEW service)

**Analog:** `services/gemini.py` — the pattern of a service class wired in `bot.py` `on_ready` and accessed via `self.bot.<svc>` in cogs.

**Wiring pattern from `bot.py` `on_ready`** (lines 181-198 show the gemini/lyrics service wiring style):
```python
# Pattern to replicate in on_ready (after pool creation, before cog loading):
from services.queue_persistence import QueuePersistenceService
bot.queue_persistence = QueuePersistenceService(bot.pool)
```

**Service class structure** (copy this shape from gemini.py's `__init__` + public method style):
```python
"""Queue persistence service — UPSERT on mutation, restore on boot."""
from __future__ import annotations
import json
import asyncpg
from utils.logger import log

class QueuePersistenceService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def persist(self, guild, queue, voice_channel_id: int | None) -> None:
        """UPSERT full queue state. Called on every mutation (D-19)."""
        payload = {
            "tracks": [t.to_dict() for t in queue.tracks],
            "current_index": queue.current_index,
            "loop_mode": queue.loop_mode.value,
            "text_channel_id": queue._text_channel_id,
            "voice_channel_id": voice_channel_id,
        }
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO guild_queues (guild_id, payload, updated_at)"
                    " VALUES ($1, $2::jsonb, now())"
                    " ON CONFLICT (guild_id)"
                    " DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()",
                    str(guild.id), json.dumps(payload),
                )
        except Exception as exc:
            log.warning("persist_queue failed for guild %s: %s", guild.id, exc)

    async def restore_queues(self, bot) -> None:
        """Restore all guild queues from Postgres on boot (D-21)."""
        ...
```

**Error handling convention** — wrap in `try/except Exception`, log via `from utils.logger import log` with `log.warning(...)`. Never let persistence failures crash playback. Matches `bot.py` lines 225-235 startup message pattern.

---

### `docker-compose.yml` and `Dockerfile` (NEW — greenfield)

**Analog:** No existing Docker files in the repo. Use RESEARCH.md Pattern 8 (lines 426-468) and Pattern 12 (Dockerfile, lines 735-751) verbatim as the template — these are the canonical patterns for this project.

**Key conventions to carry from the Python codebase:**
- `.env` is already the secrets file (used by `config.py` via `python-dotenv`); Docker Compose reads it via `env_file: .env` — no separate prod secrets file
- `config.py` already uses `BASE_DIR / "data" / "cache"` and `BASE_DIR / "logs"` as path constants — volume mount paths must match these: `/app/data/cache` and `/app/logs`
- `CMD ["python", "bot.py"]` matches the existing `main()` entry point in `bot.py` (line 466-476)

---

### `scripts/keepalive.sh` and `scripts/backup.sh` (NEW — greenfield)

**Analog:** No `scripts/` directory exists. Use RESEARCH.md Pattern 9 (keepalive, lines 474-488) and Pattern 10 (backup, lines 491-509) as templates. Both are standalone shell scripts with no Python codebase dependencies.

**Convention:** Scripts live in `scripts/`, are executable (`chmod +x`), source environment variables from the shell environment (not from `.env` directly — cron environment is separate from Docker). `HEALTHCHECK_URL` and Postgres credentials must be set in the crontab environment or via a sourced env file.

---

## Shared Patterns

### Pool acquisition (applies to all `database.py` helpers and `services/queue_persistence.py`)
**Source:** RESEARCH.md Pattern 2; replaces every `db: aiosqlite.Connection` param
```python
async with pool.acquire() as conn:
    await conn.execute("...", $1_value, $2_value)
    # asyncpg auto-commits single statements; no explicit commit needed
    # For multi-statement atomicity: async with conn.transaction():
```

### Service wiring in `on_ready`
**Source:** `bot.py` lines 172-198 — services constructed, assigned to `bot.<name>`, then cogs loaded
```python
# Pattern: construct service with dependencies, assign to bot, then load cogs
bot.youtube_service = YouTubeService()
bot.audio_service = AudioService(youtube_service=bot.youtube_service)
# Phase 4 addition follows same pattern:
bot.queue_persistence = QueuePersistenceService(bot.pool)
# ... then: await bot.load_extension("cogs.music") etc.
```

### Error logging pattern (applies to all new async code)
**Source:** `bot.py` lines 225-235 and `cogs/` throughout
```python
try:
    ...
except Exception as exc:
    log.warning("description of what failed: %s", exc)
    # For severe errors, also post to Discord error channel:
    # if hasattr(bot, "log_to_discord"): await bot.log_to_discord(embed)
```

### `log` import (applies to all new files)
**Source:** every existing Python file in the project
```python
from utils.logger import log
```

### `config` import (applies to all new files that use constants)
**Source:** every existing Python file
```python
import config
# Access as: config.MAX_QUEUE_SIZE_PER_GUILD, config.MESSAGE_BUFFER_TTL_HOURS, etc.
```

---

## Test Patterns

### `tests/test_database_phase4.py` (NEW integration tests)

**Analog:** `tests/test_database_phase3.py` — exact structure to replicate.

**Existing fixture pattern** (`test_database_phase3.py` lines 26-33) — REPLACE with asyncpg pool:
```python
# BEFORE (aiosqlite in-memory):
@pytest_asyncio.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db(conn)
    yield conn
    await conn.close()

# AFTER (asyncpg pool — requires real Postgres running):
@pytest_asyncio.fixture
async def pool():
    p = await asyncpg.create_pool("postgresql://dexter:dexter@localhost:5432/dexter_test")
    await init_db(p)
    yield p
    async with p.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS guild_queues, song_history, "
                           "user_artist_counts, image_generation_log, bot_daily_stats, "
                           "user_profiles CASCADE")
    await p.close()
```

**Test class structure** (replicate from `test_database_phase3.py` lines 40-50):
```python
class TestPostgresSchema:
    @pytest.mark.asyncio
    async def test_tables_created(self, pool):
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
            )
        tables = {r["tablename"] for r in rows}
        assert "song_history" in tables
        assert "guild_queues" in tables
```

### `tests/test_queue.py` additions (new test classes in existing file)

**Analog:** `tests/test_queue.py` existing classes (lines 35-60) — same `make_track()` helper, same synchronous pytest (no `@pytest.mark.asyncio` needed — `Track` methods and `MusicQueue.add()` are sync).

```python
# Pattern: pure sync tests, no fixture needed, uses existing make_track() helper
class TestTrackSerialization:
    def test_to_dict_round_trip(self):
        t = make_track()
        assert Track.from_dict(t.to_dict()) == t

class TestQueueCap:
    def test_add_raises_when_full(self):
        q = MusicQueue(guild_id=1)
        for i in range(config.MAX_QUEUE_SIZE_PER_GUILD):
            q.add(make_track(video_id=str(i)))
        with pytest.raises(QueueFullError):
            q.add(make_track(video_id="overflow"))
```

### `tests/test_message_buffer.py` additions (new test class in existing file)

**Analog:** `tests/test_message_buffer.py` existing `TestMessageBufferAdd` class (lines 6-22) — pure sync, no fixture.

```python
# Pattern: sync, no asyncio mark, time-manipulation with freezegun or manual datetime injection
class TestTTLEviction:
    def test_stale_channel_evicted(self):
        buf = MessageBuffer(max_length=10)
        buf.add(channel_id=100, role="user", author="jake", content="old")
        # Manually set last_seen to past TTL
        buf._last_seen[100] = datetime.now() - timedelta(hours=config.MESSAGE_BUFFER_TTL_HOURS + 1)
        buf.add(channel_id=200, role="user", author="mike", content="new")  # triggers evict
        assert buf.get_history(100) == []
        assert len(buf.get_history(200)) == 1
```

---

## No Analog Found

None. All files have either a direct self-analog (modifications) or a close role-match analog in the codebase or RESEARCH.md. Infra files (`docker-compose.yml`, `Dockerfile`, shell scripts) are greenfield but their complete templates are in RESEARCH.md patterns 8-10.

---

## Metadata

**Analog search scope:** `database.py`, `models/`, `bot.py`, `config.py`, `cogs/music.py` (mutation sites), `services/gemini.py` (limiter), `tests/` (all 22 files), project root for Docker/scripts
**Files read:** 12 source files + 2 test files
**Pattern extraction date:** 2026-06-12
