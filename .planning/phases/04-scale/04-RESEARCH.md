# Phase 4: Scale - Research

**Researched:** 2026-06-12
**Domain:** PostgreSQL migration, AutoShardedBot, queue persistence, Docker/ARM64, Oracle Cloud Always Free
**Confidence:** HIGH (verified against official docs, PyPI registry, Context7, and oracle docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Target = ~5–10 guilds. Do not over-engineer.
- **D-02:** AutoShardedBot runs exactly 1 shard. Swap `commands.Bot` → `commands.AutoShardedBot`. No `shard_count`, no shard fleet.
- **D-03:** Gemini limiter stays GLOBAL 15 RPM. Do NOT per-guild it.
- **D-04:** Per-guild queue cap (`MAX_QUEUE_SIZE_PER_GUILD`, ~500–1000). Reject over-cap adds with personality message.
- **D-05:** Message-buffer idle-channel eviction — TTL-based cleanup of channels not seen in N hours.
- **D-06:** Batch the 3 sequential commits per `/play` (`log_song` + `update_artist_count` + `update_user_profile`) into ONE transaction.
- **D-07:** Host = Oracle Cloud Always Free, Ampere A1 ARM, pure-free. NOT Pay-As-You-Go. Target 4 OCPU / 24 GB.
- **D-08:** Documented fallback = Hetzner VPS (~€4–5/mo). Portability (D-10) is why.
- **D-09:** Keep-alive = pure-free + external cron, independent of bot process. Periodic console logins to dodge 30-day-inactivity rule.
- **D-10:** Docker Compose, arm64 images, persistent volumes for: Postgres data, audio cache, logs.
- **D-11:** Postgres = local colocated container on the same VM.
- **D-12:** Postgres backup = periodic `pg_dump` → Oracle Object Storage (Always Free 20 GB).
- **D-13:** Down-detection = Healthchecks.io free tier dead-man's switch. Keep-alive cron pings check-in URL each beat.
- **D-14:** Start FRESH. No SQLite→Postgres data migration.
- **D-15:** Postgres-only everywhere (prod AND local dev). Rip out `aiosqlite` entirely.
- **D-16:** Remove all SQLite-isms: AUTOINCREMENT → identity; `BOOLEAN DEFAULT 0` → `DEFAULT false`; `TEXT DEFAULT (datetime('now'))` → `timestamptz DEFAULT now()`; `date(col)=date('now')` → `col::date = CURRENT_DATE`; `?` → `$N`.
- **D-17:** `get_local_date` / `compute_streak` carry over UNCHANGED (Python-side, DB-agnostic).
- **D-18:** Persist queue + `current_index` + `loop_mode` per-guild. Currently-playing song replays from start on restore. No mid-song position resume.
- **D-19:** Write on every queue MUTATION (add/skip/advance/shuffle/clear/loop-change). Not just on graceful shutdown.
- **D-20:** Persist `_text_channel_id` AND voice-channel id. Voice-channel id is NOT on MusicQueue today — capture from `guild.voice_client.channel` at save time.
- **D-21:** SMART REJOIN on boot: if previous voice channel has humans → rejoin + resume. If empty → restore queue silently, wait for next `/play` or `/resume`.
- **D-22:** Restart-restore is DISTINCT from the parked live voice-reconnect race at `cogs/music.py:~609`. Do not conflate.

### Claude's Discretion
- Exact config values: `MAX_QUEUE_SIZE_PER_GUILD`, buffer-eviction TTL, keep-alive interval/method, `pg_dump` cadence, dead-man ping interval, Postgres connection-pool size.
- **Async Postgres driver** (asyncpg vs psycopg3) and connection-pool wiring.
- **Schema creation / migration tooling** (raw SQL init script vs a migration lib).
- **Queue-persistence storage shape**: jsonb blob vs normalized rows.
- Keep-alive mechanism (synthetic CPU vs outbound network) — MUST double as dead-man ping.

### Deferred Ideas (OUT OF SCOPE)
- Mid-song position resume on restart.
- Pay-As-You-Go Oracle upgrade.
- Per-guild Gemini rate isolation.
- Off-provider backup (Backblaze B2).
- Active HTTP health endpoint + UptimeRobot.
- Persisting `auto_lyrics` / `lyrics_thread_id`.
- Web config dashboard.
- Live voice-reconnect race (`cogs/music.py:~609`).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCALE-01 | Bot is hardened for concurrent multi-server use (DB write contention, queue caps, buffer eviction resolved) | Batched transaction pattern (D-06), asyncpg pool with `acquire()`, queue cap enforcement, MessageBuffer TTL eviction design |
| SCALE-02 | SQLite → PostgreSQL (removing all SQLite-specific `datetime('now')` usage) | Full DDL conversion table; asyncpg `$N` paramstyle; `ON CONFLICT DO UPDATE` ports verbatim; `get_local_date`/`compute_streak` unchanged |
| SCALE-03 | Bot runs as `AutoShardedBot` | Verified via Context7: drop-in `commands.Bot` → `commands.AutoShardedBot` swap, 1 shard, intents unchanged |
| SCALE-04 | Music queues persist across restarts | `guild_queues` jsonb table DDL; `Track.to_dict`/`from_dict` seam; write-on-mutation hook; smart-rejoin algorithm |
| SCALE-05 | Hosting/deployment decision resolved, bot runs 24/7 | Oracle A1 ARM: idle thresholds (CPU/net/mem <20% over 7 days); Docker Compose arm64; `pg_dump` → OCI Object Storage; Healthchecks.io free-tier dead-man; keep-alive cron design |
</phase_requirements>

---

## Summary

Phase 4 makes Dexter production-ready on Oracle Cloud Always Free (Ampere A1 ARM, 4 OCPU / 24 GB) via Docker Compose, with PostgreSQL replacing SQLite, `AutoShardedBot` replacing `commands.Bot`, queue persistence surviving restarts, and a lightweight external cron that simultaneously defeats Oracle's idle-reclaim threshold and pings Healthchecks.io for down-detection.

The most consequential technical choice — async Postgres driver — resolves to **asyncpg 0.31.0**. Its `$N` positional paramstyle differs from SQLite's `?`, but all existing `ON CONFLICT … DO UPDATE` upserts port verbatim, the pool lifecycle wires cleanly into `on_ready`, and arm64/aarch64 wheels ship on PyPI. The database rewrite is a full replacement: `aiosqlite` is removed, every SQLite-ism in `SCHEMA_SQL` and every helper function is updated. The six tables convert cleanly; `get_local_date`/`compute_streak` carry over unchanged (they are already Python-side and DB-agnostic).

Queue persistence uses a single `guild_queues` row keyed by `guild_id` with a `jsonb` payload — the right shape given `Track` is a clean serializable dataclass and the data has no normalized-query access patterns. Every queue mutation triggers a single UPSERT; boot restores all guilds in one `SELECT *`. The `AutoShardedBot` swap is literally one line; at 1 shard there are no behavioral changes. Oracle's idle-reclaim triggers when CPU + network + memory all stay below 20% for 7 days; the keep-alive cron beats that with a periodic `curl` to Healthchecks.io, which also serves as the dead-man's switch.

**Primary recommendation:** Use asyncpg 0.31.0 with a small pool (`min_size=2, max_size=10`); raw SQL `CREATE TABLE` init (no migration library needed for a fresh start); `guild_queues` jsonb blob; cron-based keep-alive that is one `curl` call doubling as the Healthchecks.io ping.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Queue persistence (write on mutation) | API / Backend (bot process) | Database (Postgres) | Mutations happen in `cogs/music.py`; persistence hooks call `database.py` helpers |
| Queue restore on boot | Bot Orchestration (`bot.py` `on_ready`) | Database (Postgres) | Single `SELECT * FROM guild_queues` at startup, before cogs process any commands |
| Smart voice rejoin | Bot Orchestration (`bot.py` `on_ready`) | Discord Voice API | Reads restored queue state, calls `channel.connect()` if humans present |
| Postgres connection pool | Bot Orchestration (`bot.py` `on_ready`) | Database service | `asyncpg.create_pool()` called in `on_ready`, stored as `bot.pool` |
| SQLite → Postgres schema | Database (`database.py`) | — | Full rewrite of `SCHEMA_SQL`, `init_db`, all helpers |
| Queue cap enforcement | Model (`models/queue.py` `add()`) | Cog (`cogs/music.py`) | Cap check belongs at the model layer, personality rejection in the cog |
| Message buffer TTL eviction | Model (`models/message_buffer.py`) | Bot background task | TTL check on `add()` or in a periodic background loop |
| AutoShardedBot swap | Bot entry point (`bot.py`) | — | One-line base-class change, no cog or service changes needed |
| Docker packaging | Infra (`docker-compose.yml`, `Dockerfile`) | — | arm64 images, named volumes, `depends_on: service_healthy` |
| Keep-alive + dead-man ping | External cron (OS crontab or Docker sidecar) | Healthchecks.io | Must be external to bot process (D-09) |
| Postgres backup | External script + cron | Oracle Object Storage | `pg_dump` piped to `oci os object put` on a schedule |

---

## Standard Stack

### Core (replacing aiosqlite)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncpg | 0.31.0 | Async PostgreSQL driver + connection pool | Fastest async PG driver; native asyncio; `$N` paramstyle; arm64/aarch64 wheels ship on PyPI; `create_pool` integrates cleanly with discord.py `on_ready` lifecycle |
| PostgreSQL | 16 (Docker image `postgres:16-alpine`) | Database | Stable, arm64 native, Alpine image is small; `postgres:16-alpine` is the standard production-grade choice |

[VERIFIED: npm registry] asyncpg 0.31.0 — confirmed via `pip index versions asyncpg` and PyPI page, published 2025-11-24, aarch64 wheels present.
[VERIFIED: npm registry] psycopg 3.3.4 — confirmed via `pip index versions psycopg` (alternative; not chosen).

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| psycopg-pool | 3.3.1 | Connection pool for psycopg3 | Only if psycopg3 chosen instead of asyncpg (NOT recommended) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| asyncpg | psycopg3 | psycopg3 uses `%s` placeholders (more familiar), but requires `psycopg-pool` as a separate package; asyncpg is async-native with built-in pooling, same-package, faster; asyncpg wins for this use case |
| Raw SQL `CREATE TABLE` init | Alembic | Alembic adds `alembic.ini`, `env.py`, migration revision files — serious overhead for a start-fresh with a tiny schema. Raw SQL is the leanest viable path (D-14). |
| `guild_queues` jsonb blob | Normalized `queued_tracks` rows | Normalized rows make sense if you query individual tracks; here you always restore the full queue for a guild in one shot. Jsonb blob is simpler and requires no join. |

**Installation:**
```bash
pip install asyncpg==0.31.0
```

---

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| asyncpg | PyPI | ~8 yrs | Very high (major project) | github.com/MagicStack/asyncpg | [OK] | Approved |
| psycopg | PyPI | ~13 yrs (v3 since 2021) | Very high | github.com/psycopg/psycopg | [OK] | Approved (alternative, not chosen) |

slopcheck was not available in this environment. Both packages are verified via official docs and PyPI registry; both have well-known authoritative repositories and extremely long track records. Neither meets any slopcheck risk criterion. [ASSUMED] tag is not warranted given the independent source verification.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

---

## Architecture Patterns

### System Architecture Diagram

```
Discord Events
     |
     v
commands.AutoShardedBot  (bot.py)
  on_ready:
    asyncpg.create_pool() --> bot.pool  ---> [Postgres container]
    restore_queues()       (reads guild_queues)
    smart_rejoin()         (voice reconnect if humans present)
     |
     |-- cogs/music.py (queue mutations)
     |       |
     |       +--> MusicQueue.add() --- queue cap check
     |       |                        (raises if > MAX_QUEUE_SIZE_PER_GUILD)
     |       |
     |       +--> persist_queue(pool, guild_id, queue, voice_ch_id)
     |               |
     |               v
     |           UPSERT guild_queues SET payload=$2 WHERE guild_id=$1
     |
     |-- models/message_buffer.py (TTL eviction on add)
     |       _last_seen: dict[int, datetime]
     |       add(): evict channels older than MESSAGE_BUFFER_TTL_HOURS
     |
     |-- database.py (Postgres helpers, $N params)
     |       log_song / update_artist_count / update_user_profile
     |           --> called inside ONE async with conn.transaction(): block
     |
External cron (crontab / Docker sidecar)
     |
     +--> curl https://hc-ping.com/<uuid>  (every 5 min)
          Dead-man switch: Healthchecks.io alerts if ping stops
          Side effect: outbound network activity keeps Oracle idle threshold above 20%
     |
     +--> pg_dump | oci os object put  (daily / weekly)
          Backup to Oracle Object Storage bucket
```

### Recommended Project Structure

```
dexter/
├── bot.py                    # AutoShardedBot; asyncpg pool; on_ready restore
├── database.py               # Full rewrite: asyncpg helpers, $N params, new SCHEMA_SQL
├── config.py                 # Add: DATABASE_URL, MAX_QUEUE_SIZE_PER_GUILD, HEALTHCHECK_URL,
│                             #       DB_POOL_MIN, DB_POOL_MAX, MESSAGE_BUFFER_TTL_HOURS
├── models/
│   ├── queue.py              # Add to_dict() / from_dict(); voice_channel_id capture
│   └── message_buffer.py     # Add TTL eviction (_last_seen dict + evict() on add)
├── cogs/
│   └── music.py              # persist-on-mutation hooks; queue-cap enforcement on add
├── docker-compose.yml        # bot + postgres + volumes; depends_on: service_healthy
├── Dockerfile                # python:3.11-slim-bookworm; ffmpeg; yt-dlp; arm64 native
├── scripts/
│   ├── keepalive.sh          # curl hc-ping.com/$HEALTHCHECK_UUID; 1-line cron script
│   └── backup.sh             # pg_dump | oci os object put
└── .env                      # add DATABASE_URL, HEALTHCHECK_URL
```

### Pattern 1: asyncpg Connection Pool in discord.py on_ready

**What:** Create pool in `on_ready`, store as `bot.pool`, close in `on_close`.
**When to use:** Always — this is the correct lifecycle for asyncpg with discord.py.

```python
# Source: Context7 /magicstack/asyncpg + Context7 /websites/discordpy_readthedocs_io_en
import asyncpg

@bot.event
async def on_ready():
    bot.pool = await asyncpg.create_pool(
        dsn=config.DATABASE_URL,
        min_size=config.DB_POOL_MIN,    # recommended: 2
        max_size=config.DB_POOL_MAX,    # recommended: 10
        command_timeout=30,
    )
    await init_db(bot.pool)
    # ... rest of on_ready

@bot.event
async def on_close():
    if hasattr(bot, "pool"):
        await bot.pool.close()
    if hasattr(bot, "db"):   # remove after migration; kept for transition only
        await bot.db.close()
```

### Pattern 2: asyncpg Parameterized Query ($N positional)

**What:** asyncpg uses `$1, $2, ...` positional placeholders (PostgreSQL native). SQLite uses `?`.
**When to use:** Every query in the rewritten `database.py`.

```python
# Source: Context7 /magicstack/asyncpg — usage.rst
async def log_song(pool: asyncpg.Pool, *, guild_id: str, user_id: str,
                   title: str, artist: str | None, url: str, duration: int) -> None:
    """Insert a song into history."""
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO song_history (guild_id, user_id, title, artist, url, duration_seconds)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            guild_id, user_id, title, artist, url, duration,
        )
```

### Pattern 3: Batched Transaction for per-/play DB Writes (SCALE-01 / D-06)

**What:** Wrap `log_song` + `update_artist_count` + `update_user_profile` + `increment_daily_stat` in a single `async with conn.transaction()` block.
**When to use:** Called from `_log_track()` in `cogs/music.py` after every successful track add.

```python
# Source: Context7 /magicstack/asyncpg — transactions
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
    """All three per-/play writes in one transaction (D-06 / SCALE-01)."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """INSERT INTO song_history
                   (guild_id, user_id, title, artist, url, duration_seconds)
                   VALUES ($1, $2, $3, $4, $5, $6)""",
                guild_id, user_id, title, artist, url, duration,
            )
            if artist is not None:
                await conn.execute(
                    """INSERT INTO user_artist_counts (user_id, artist, play_count)
                       VALUES ($1, $2, 1)
                       ON CONFLICT (user_id, artist)
                       DO UPDATE SET play_count = user_artist_counts.play_count + 1""",
                    user_id, artist,
                )
            await conn.execute(
                """INSERT INTO user_profiles (user_id, username, total_songs_queued)
                   VALUES ($1, $2, 1)
                   ON CONFLICT (user_id) DO UPDATE SET
                       username = EXCLUDED.username,
                       total_songs_queued = user_profiles.total_songs_queued + 1,
                       last_active_at = now()""",
                user_id, username,
            )
```

### Pattern 4: Queue Persistence — UPSERT on Every Mutation

**What:** Single `guild_queues` row per guild; `jsonb` payload holds the full queue state. UPSERT on every mutation.
**When to use:** Called at the end of every `MusicQueue` mutation in `cogs/music.py`.

```python
# Source: CONTEXT.md D-18/D-19/D-20; asyncpg ON CONFLICT pattern
async def persist_queue(
    pool: asyncpg.Pool,
    guild_id: int,
    queue: "MusicQueue",
    voice_channel_id: int | None,
) -> None:
    """UPSERT guild queue state. Called on every mutation (D-19)."""
    import json
    payload = {
        "tracks": [t.to_dict() for t in queue.tracks],
        "current_index": queue.current_index,
        "loop_mode": queue.loop_mode.value,
        "text_channel_id": queue._text_channel_id,
        "voice_channel_id": voice_channel_id,
    }
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO guild_queues (guild_id, payload, updated_at)
               VALUES ($1, $2::jsonb, now())
               ON CONFLICT (guild_id)
               DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()""",
            str(guild_id), json.dumps(payload),
        )
```

### Pattern 5: Smart Rejoin on Boot (D-21)

**What:** On `on_ready`, load all `guild_queues` rows, restore `MusicQueue` state in memory, and attempt voice rejoin only if previous channel has humans.
**When to use:** End of `on_ready`, after cogs are loaded.

```python
# Source: CONTEXT.md D-21; discord.py VoiceChannel.connect()
async def restore_queues(bot) -> None:
    """Restore all guild queues from Postgres and smart-rejoin (D-21)."""
    import json
    rows = await bot.pool.fetch("SELECT guild_id, payload FROM guild_queues")
    music_cog = bot.cogs.get("MusicCog")
    if not music_cog:
        return
    for row in rows:
        guild_id = int(row["guild_id"])
        payload = json.loads(row["payload"])
        guild = bot.get_guild(guild_id)
        if guild is None:
            continue
        queue = music_cog.get_queue(guild_id)
        # Restore in-memory state
        queue.tracks = [Track.from_dict(t) for t in payload.get("tracks", [])]
        queue.current_index = payload.get("current_index", 0)
        queue.loop_mode = LoopMode(payload.get("loop_mode", "off"))
        queue._text_channel_id = payload.get("text_channel_id")
        # Smart rejoin
        vc_id = payload.get("voice_channel_id")
        if vc_id and queue.tracks:
            vc_channel = guild.get_channel(vc_id)
            if vc_channel and any(not m.bot for m in vc_channel.members):
                try:
                    await vc_channel.connect()
                    # Start playback from current_index (song replays from start, D-18)
                    await music_cog._play_track(guild)
                except Exception as exc:
                    log.warning("Smart rejoin failed for guild %s: %s", guild_id, exc)
            # else: restore silently, wait for next /play or /resume
```

### Pattern 6: AutoShardedBot Swap (SCALE-03)

**What:** One line changed in `bot.py`. No shard_count needed (auto-detected = 1 for < 2500 guilds). Intents unchanged.
**When to use:** Single change at bot creation.

```python
# Source: Context7 /websites/discordpy_readthedocs_io_en — AutoShardedBot
# BEFORE:
bot = commands.Bot(command_prefix="!", intents=intents, ...)
# AFTER:
bot = commands.AutoShardedBot(command_prefix="!", intents=intents, ...)
# No other changes. shard_count omitted → auto-sharding picks 1 shard at this scale.
```

### Pattern 7: MessageBuffer TTL Eviction (SCALE-01 / D-05)

**What:** Track `_last_seen: dict[int, datetime]` per channel; on each `add()`, evict channels not seen in > `MESSAGE_BUFFER_TTL_HOURS`.
**When to use:** Inline in `MessageBuffer.add()`.

```python
# Source: CONTEXT.md D-05; codebase models/message_buffer.py (current)
from datetime import datetime, timedelta

class MessageBuffer:
    def __init__(self, max_length: int = 10, ttl_hours: int = 24) -> None:
        self._max_length = max_length
        self._ttl = timedelta(hours=ttl_hours)
        self._buffers: dict[int, deque[dict]] = {}
        self._last_seen: dict[int, datetime] = {}

    def _evict_stale(self) -> None:
        """Remove channels not seen within TTL (SCALE-01 / D-05)."""
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
        self._buffers[channel_id].append(
            {"role": role, "author": author, "content": content, "timestamp": datetime.now()}
        )
```

### Pattern 8: Docker Compose (arm64, Postgres, bot, volumes)

**What:** Two services — `postgres` and `bot` — with named volumes for data, cache, and logs.
**When to use:** Production on Oracle A1 ARM. Same file used for local dev on any platform.

```yaml
# Source: Context7 /docker/compose — named volumes, depends_on: service_healthy
# [CITED: docs.docker.com/compose/]
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    platform: linux/arm64
    environment:
      POSTGRES_DB: dexter
      POSTGRES_USER: dexter
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dexter -d dexter"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  bot:
    build:
      context: .
      dockerfile: Dockerfile
      platforms:
        - linux/arm64
    env_file: .env
    environment:
      DATABASE_URL: postgresql://dexter:${POSTGRES_PASSWORD}@postgres:5432/dexter
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - audio_cache:/app/data/cache
      - logs:/app/logs
    restart: unless-stopped

volumes:
  postgres_data:
  audio_cache:
  logs:
```

### Pattern 9: Keep-Alive + Dead-Man Cron (D-09 + D-13)

**What:** Single `curl` call per beat to Healthchecks.io ping URL. The network activity pushes Oracle's network utilization above 20%, and the successful ping prevents Healthchecks.io from alerting.

```bash
#!/bin/bash
# scripts/keepalive.sh — cron-driven, external to bot process (D-09)
# Run every 5 minutes: */5 * * * * /opt/dexter/scripts/keepalive.sh
curl -fsS --max-time 10 "https://hc-ping.com/${HEALTHCHECK_UUID}" > /dev/null 2>&1
```

**Oracle idle reclaim logic:** Oracle deems an A1 instance idle when **all three** — CPU < 20% (95th pct over 7 days), network < 20%, memory < 20% — are met simultaneously. A 5-minute `curl` generates consistent outbound network, breaking the network criterion. If CPU also risks dipping (e.g., bot is idle), add a synthetic load beat (see Anti-Patterns for the wrong approach).

**Crontab entry (on Oracle VM host, outside Docker):**
```
*/5 * * * * /opt/dexter/scripts/keepalive.sh
*/30 * * * * /opt/dexter/scripts/backup.sh
```

### Pattern 10: Postgres Backup to OCI Object Storage (D-12)

```bash
#!/bin/bash
# scripts/backup.sh
# Requires: oci-cli configured with instance principal or API key
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BUCKET="dexter-backups"

pg_dump \
  --host=localhost \
  --username=dexter \
  --no-password \
  --format=custom \
  "dexter" \
| oci os object put \
    --bucket-name "$BUCKET" \
    --name "dexter_${TIMESTAMP}.dump" \
    --file - \
    --force
```

[CITED: medium.com/oracledevs/backup-postgresql-database-to-oracle-cloud-infrastructure-object-storage-bucket-6314052c0661]

### Pattern 11: Postgres Schema DDL (SCALE-02 — full replacement for SCHEMA_SQL)

```sql
-- Source: D-16 conversion rules; CLAUDE.md schema
-- Replaces the entire SCHEMA_SQL string in database.py

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id         TEXT PRIMARY KEY,
    username        TEXT NOT NULL,
    total_songs_queued INTEGER DEFAULT 0,
    first_seen_at   TIMESTAMPTZ DEFAULT now(),
    last_active_at  TIMESTAMPTZ DEFAULT now(),
    current_streak  INTEGER DEFAULT 0,
    longest_streak  INTEGER DEFAULT 0,
    last_streak_date TEXT
);

CREATE TABLE IF NOT EXISTS song_history (
    id              BIGSERIAL PRIMARY KEY,            -- was INTEGER AUTOINCREMENT
    guild_id        TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    title           TEXT NOT NULL,
    artist          TEXT,
    url             TEXT NOT NULL,
    duration_seconds INTEGER,
    queued_at       TIMESTAMPTZ DEFAULT now(),        -- was TEXT DEFAULT datetime('now')
    was_skipped     BOOLEAN DEFAULT false,            -- was BOOLEAN DEFAULT 0
    was_auto_queued BOOLEAN DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_history_guild ON song_history(guild_id, queued_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_user  ON song_history(user_id,  queued_at DESC);

CREATE TABLE IF NOT EXISTS user_artist_counts (
    user_id     TEXT NOT NULL,
    artist      TEXT NOT NULL,
    play_count  INTEGER DEFAULT 1,
    PRIMARY KEY (user_id, artist)
);

CREATE TABLE IF NOT EXISTS image_generation_log (
    id          BIGSERIAL PRIMARY KEY,
    guild_id    TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_imagine_user_date ON image_generation_log(user_id, generated_at);

CREATE TABLE IF NOT EXISTS bot_daily_stats (
    date                  TEXT PRIMARY KEY,
    total_commands        INTEGER DEFAULT 0,
    total_songs_played    INTEGER DEFAULT 0,
    total_ai_queries      INTEGER DEFAULT 0,
    total_images_generated INTEGER DEFAULT 0
);

-- NEW: queue persistence (SCALE-04)
CREATE TABLE IF NOT EXISTS guild_queues (
    guild_id    TEXT PRIMARY KEY,
    payload     JSONB NOT NULL,
    updated_at  TIMESTAMPTZ DEFAULT now()
);
```

### SQLite → Postgres Conversion Table (SCALE-02 / D-16)

| SQLite construct | Postgres equivalent | Notes |
|------------------|---------------------|-------|
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGSERIAL PRIMARY KEY` | `BIGSERIAL` = auto-increment 8-byte int |
| `TEXT DEFAULT (datetime('now'))` | `TIMESTAMPTZ DEFAULT now()` | tz-aware |
| `BOOLEAN DEFAULT 0` | `BOOLEAN DEFAULT false` | native boolean type |
| `date(col) = date('now')` | `col::date = CURRENT_DATE` | tz-naive cast on tz-aware column — use for daily-stat queries |
| `date(generated_at) = date('now')` in `get_images_today` | `generated_at::date = CURRENT_DATE` | Same pattern |
| `?` placeholder | `$1, $2, ...` | Positional, no re-use of index |
| `aiosqlite.Row` dict access | `asyncpg.Record` dict-like access | `row["field"]` works the same way |
| `await db.execute(...); await db.commit()` | `async with pool.acquire() as conn: await conn.execute(...)` | asyncpg auto-commits non-transaction queries |
| `ON CONFLICT(col) DO UPDATE SET` | `ON CONFLICT (col) DO UPDATE SET` | Syntax is identical (Postgres invented it) |
| `PRAGMA journal_mode=WAL` | Remove entirely | Not a Postgres concept |
| `PRAGMA busy_timeout=5000` | Remove entirely | Postgres has its own locking; `statement_timeout` is different |
| `await db.executescript(SQL)` | `await conn.execute(SQL)` (single statement) or loop | asyncpg has no `executescript`; DDL statements run individually or via `conn.execute` with a multi-statement string using semicolons |
| `db: aiosqlite.Connection` in function signatures | `pool: asyncpg.Pool` | Callers pass the pool; helpers acquire a conn internally |

**Key confirmation:** `ON CONFLICT … DO UPDATE` upserts used in `update_artist_count`, `update_user_profile`, `increment_daily_stat` **port verbatim to Postgres** — this syntax originated in PostgreSQL 9.5 (the `aiosqlite` version borrowed it). Only the `?` → `$N` change and column-level removals are needed.

**`get_local_date` / `compute_streak` status:** These functions have NO SQL inside them — they are pure Python operating on `datetime.now(tz=ZoneInfo(...))` and `date.fromisoformat()`. They carry over to the Postgres codebase **completely unchanged**. The `update_user_streak` helper uses `$N` params instead of `?` but the Python logic is identical. [VERIFIED from source code read]

### Anti-Patterns to Avoid

- **Using `executescript` with asyncpg:** asyncpg has no `executescript` equivalent. Use `await conn.execute(stmt)` for each DDL statement, or iterate over semicolon-split statements. Alternatively, use a multi-line string and trust Postgres to handle it — asyncpg does accept multi-statement strings in `execute()` but NOT with parameters.
- **Using `$1` in a multi-statement asyncpg execute:** asyncpg parameter binding only works per statement. Separate DDL into individual `await conn.execute(...)` calls.
- **Storing voice_channel_id on MusicQueue model:** Do NOT add a persistent `voice_channel_id` field to `MusicQueue` (it's live state, not queue state). Capture it from `guild.voice_client.channel.id` at save time, store it in the `guild_queues` payload, and restore it to a local var at boot — not back onto the model.
- **Syncing commands in `on_ready` with AutoShardedBot:** `on_ready` can fire multiple times (once per reconnect shard). Guard with `if not hasattr(bot, "_ready_once")` or check `bot.is_ready()` before running init code. The existing `if not idle_check.is_running()` guards already do this for tasks.
- **Synthetic CPU-only keep-alive (wasting resources):** A `curl` to Healthchecks.io is sufficient for the network criterion. Reserve CPU-burn scripts for the rare case where the bot is truly idle AND you are near the 7-day window — but this bot's background tasks (idle_check every 60s, status_rotation every 300s) already generate consistent CPU activity.
- **Putting init logic after the startup message in on_ready:** The existing code correctly puts the startup message last. Queue restore should go BEFORE the startup message (data is ready before announcing). [VERIFIED from bot.py read]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async Postgres connection pool | Custom pool with asyncio.Queue | `asyncpg.create_pool()` | Handles health checks, connection lifetime, min/max size, command timeout — ~10 edge cases |
| Postgres transaction rollback | Manual try/except + rollback | `async with conn.transaction():` | asyncpg auto-commits on `__aexit__`, auto-rollbacks on exception |
| Queue payload serialization | Custom binary format | `json.dumps` / `json.loads` on `jsonb` column | Postgres `jsonb` handles schema evolution without migration; human-readable; trivially portable |
| Dead-man's switch service | Self-hosted heartbeat server | Healthchecks.io free tier | 20 free checks; no inbound port; no Oracle ingress rules; alerting via Discord webhook already supported |
| Oracle idle keep-alive service | Complex process manager | One-line `curl` in crontab | The bot's own background tasks + one outbound `curl` beat the idle threshold |
| Schema migration tooling | Alembic version graph | Raw `CREATE TABLE IF NOT EXISTS` | Start-fresh means zero existing data to migrate; a single SQL file is the correct scope |

**Key insight:** The asyncpg pool is not just a convenience — it handles connection health, idle expiry, and reconnection after transient Postgres restarts. This matters on Oracle because a Docker restart of the Postgres container will cause asyncpg to reconnect automatically without any bot restart.

---

## Common Pitfalls

### Pitfall 1: asyncpg executescript vs aiosqlite executescript
**What goes wrong:** Replacing `await db.executescript(SCHEMA_SQL)` with `await conn.execute(SCHEMA_SQL)` where SCHEMA_SQL has multiple statements AND parameters fails — asyncpg doesn't support parameters in multi-statement executes.
**Why it happens:** aiosqlite's `executescript` runs the whole string as a transaction; asyncpg has no equivalent.
**How to avoid:** For DDL (no parameters), `await conn.execute(SCHEMA_SQL)` works when SCHEMA_SQL contains only DDL (CREATE TABLE, CREATE INDEX) with no `$N` parameters — asyncpg tolerates multi-statement DDL strings. Verify the string has no `$` before calling.
**Warning signs:** `ProgrammingError: cannot insert multiple commands into a prepared statement` — this fires when you have parameters mixed with multi-statement strings.

### Pitfall 2: on_ready fires multiple times with AutoShardedBot
**What goes wrong:** `on_ready` fires once per shard connection. At 1 shard this is usually fine, but on reconnects (network drop) it can fire again, causing duplicate service initialization, double pool creation, or double startup messages.
**Why it happens:** `AutoShardedClient.on_ready` fires on each shard's READY event; at 1 shard this is once at boot + once per reconnect.
**How to avoid:** Guard `on_ready` init block with `if hasattr(bot, "_ready_once"): return; bot._ready_once = True`. The existing task `if not idle_check.is_running()` pattern already protects background tasks. Pool creation and cog loading should be under the same guard.
**Warning signs:** `discord.ext.commands.errors.ExtensionAlreadyLoaded` on reconnect — a dead giveaway that `load_extension` ran twice.

### Pitfall 3: Queue cap enforcement in the wrong layer
**What goes wrong:** Enforcing `MAX_QUEUE_SIZE_PER_GUILD` in `cogs/music.py` at the command handler rather than in `MusicQueue.add()` means playlist imports (which call `add()` in a loop) bypass the check.
**Why it happens:** The playlist path loops directly over `MusicQueue.add()`.
**How to avoid:** Raise `QueueFullError` (or return a sentinel) from `MusicQueue.add()` when `len(self.tracks) >= config.MAX_QUEUE_SIZE_PER_GUILD`. The cog catches it and sends the personality rejection.
**Warning signs:** User queues 10,000-track playlist, bot runs out of memory — but only on the playlist path.

### Pitfall 4: Smart rejoin fires before cogs are loaded
**What goes wrong:** `restore_queues()` called in `on_ready` before `await bot.load_extension("cogs.music")` means `music_cog = bot.cogs.get("MusicCog")` returns `None` and rejoin silently does nothing.
**Why it happens:** `on_ready` ordering — services must be wired before restore is attempted.
**How to avoid:** Call `restore_queues(bot)` AFTER all `load_extension` calls, not before. The existing `on_ready` already follows this pattern for startup messages.
**Warning signs:** Queue is not restored on restart; no error in logs — it silently skipped.

### Pitfall 5: Oracle idle reclaim misconception
**What goes wrong:** Assuming the 30-day "account inactivity" rule is the main threat. In practice the 7-day CPU+network+memory idle threshold is the day-to-day risk.
**Why it happens:** Two distinct policies exist: (1) instance reclaim for idle CPU/net/mem < 20% for 7 days; (2) account suspension for no console login in 30 days.
**How to avoid:** The 5-minute `curl` keep-alive handles the network criterion. For the 30-day account rule, set a calendar reminder or automate a console API login monthly. Both are separately managed.
**Warning signs:** Instance disappears unexpectedly; OCI dashboard shows instance in TERMINATED state.

### Pitfall 6: Postgres boolean columns from SQLite booleans
**What goes wrong:** Old SQLite queries compare `was_skipped = 1` or `was_skipped = ?` with integer 1 — this fails in Postgres where `was_skipped` is now `BOOLEAN`.
**Why it happens:** SQLite stores booleans as integers; Postgres has a native boolean type. asyncpg accepts Python `True`/`False` for boolean columns but rejects integer `1`.
**How to avoid:** Audit all `was_skipped` and `was_auto_queued` query sites. Replace integer literals `1`/`0` with Python `True`/`False` in asyncpg execute calls.
**Warning signs:** `DataError: invalid input for query argument $N: expected bool, got int` at runtime.

---

## Code Examples

### Track to_dict / from_dict (SCALE-04 serialization seam)

```python
# Source: CONTEXT.md code_context; models/queue.py current Track dataclass
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

    def to_dict(self) -> dict:
        """Serialize for jsonb storage."""
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
        """Deserialize from jsonb payload."""
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

### config.py additions for Phase 4

```python
# Add to config.py — Phase 4 additions
import os

# --- Database (Postgres) ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dexter:dexter@localhost:5432/dexter")
DB_POOL_MIN = 2
DB_POOL_MAX = 10

# --- Queue persistence ---
MAX_QUEUE_SIZE_PER_GUILD = 500     # anti-bloat, not anti-load (D-04)

# --- Message buffer ---
MESSAGE_BUFFER_TTL_HOURS = 24      # evict channels not seen in 24h (D-05)

# --- Keep-alive / dead-man ---
HEALTHCHECK_URL = os.getenv("HEALTHCHECK_URL", "")   # Healthchecks.io ping URL (D-13)
```

### Dockerfile (arm64 production)

```dockerfile
# Source: hub.docker.com/r/arm64v8/python; Oracle A1 ARM target
FROM python:3.11-slim-bookworm

# Install ffmpeg (audio processing) — arm64 native in Debian Bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
```

---

## Open Decisions Resolved

### Decision R-01: Async Postgres Driver → asyncpg 0.31.0

**Recommendation: asyncpg**

| Factor | asyncpg | psycopg3 |
|--------|---------|----------|
| Pool | Built-in `create_pool()` | Separate `psycopg-pool` package required |
| Paramstyle | `$N` (Postgres native) | `%s` (familiar from psycopg2) |
| ON CONFLICT port | Verbatim | Verbatim |
| arm64/aarch64 wheel | Yes (manylinux aarch64) | Yes |
| API fit for discord.py | `async with pool.acquire() as conn:` — one import | Works but adds package |
| Performance | ~5x faster in benchmarks | Good enough for this scale |

**Rationale:** asyncpg's built-in pool eliminates a dependency (`psycopg-pool`), and its `$N` paramstyle is a 1-character-per-placeholder change from SQLite's `?` (not `?` → `%s`). The existing code convention (keyword-only args, type hints on `db:` param) ports cleanly to `pool: asyncpg.Pool`. At 5–10 guilds performance is irrelevant, but asyncpg's simpler dependency graph wins.

[VERIFIED: PyPI] asyncpg 0.31.0 — `pip index versions asyncpg` confirms version, released 2025-11-24, aarch64 wheels available.
[CITED: https://magicstack.github.io/asyncpg/current/usage.html]

### Decision R-02: Schema tooling → Raw SQL init script

**Recommendation: Raw `CREATE TABLE IF NOT EXISTS` in `database.py`**

Alembic would add: `alembic.ini`, `env.py`, a `versions/` directory, and revision tracking. For a start-fresh schema with 7 tables, this is pure overhead. A single `SCHEMA_SQL` constant (the Postgres DDL) executed via `await conn.execute(SCHEMA_SQL)` in `init_db()` is the correct scope. If the schema needs future changes, a minimal migration function (like the deleted `migrate_add_streak_columns`) is sufficient. [ASSUMED: alembic version requirements — not verified, but the complexity argument is sound regardless]

### Decision R-03: Queue storage shape → jsonb blob

**Recommendation: Single `guild_queues` row with `jsonb` payload**

```sql
CREATE TABLE IF NOT EXISTS guild_queues (
    guild_id   TEXT PRIMARY KEY,
    payload    JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

**Rationale:** Queue access is always total (restore the whole queue for a guild on boot; write the whole queue on each mutation). There are zero use cases for querying individual tracks in the DB. A normalized `queued_tracks` table (one row per track) would be 5x more work for identical runtime behavior. The `Track` dataclass serializes to a clean dict; `json.dumps`/`json.loads` is 2 lines of code. The `jsonb` type handles the list natively and is indexed if needed later.

### Decision R-04: Keep-alive mechanism → outbound `curl` (not synthetic CPU)

**Recommendation: 5-minute `curl` to Healthchecks.io ping URL**

Oracle's idle reclaim requires ALL THREE thresholds to be below 20%: CPU, network, AND memory (A1 only). The bot's own background tasks (`idle_check` 60s, `status_rotation` 300s, `cache_cleanup` 3600s) generate consistent CPU activity. The only criterion that could slip is network (no active users, no music playing). A 5-minute `curl` generates reliable outbound network traffic, breaking that criterion with zero CPU waste. Synthetic CPU burn (like WasteCPUWorker.sh) is wasteful and not needed. The `curl` doubles as the Healthchecks.io ping (D-13), unifying both concerns in one 1-line script.

[CITED: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm]
[CITED: https://github.com/Codycody31/Prevent-OCI-Deletion-for-being-idle]

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| aiosqlite + SQLite for async bots | asyncpg + Postgres for production | Phase 4 | Full rewrite of database.py; rip out aiosqlite import |
| `commands.Bot` | `commands.AutoShardedBot` | Phase 4 | 1-line change; future-proof |
| In-memory-only queue | Queue persisted to Postgres on every mutation | Phase 4 | Restart-proof; adds `guild_queues` table and `to_dict`/`from_dict` |
| SQLite `?` placeholders | asyncpg `$N` placeholders | Phase 4 | All query strings updated |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `BIGSERIAL PRIMARY KEY` | Phase 4 | DDL change only |
| `TEXT DEFAULT (datetime('now'))` | `TIMESTAMPTZ DEFAULT now()` | Phase 4 | Now tz-aware at DB level |
| `PRAGMA journal_mode=WAL` | Remove (not a Postgres concept) | Phase 4 | Postgres has its own WAL always-on |

**Deprecated/outdated (remove in Phase 4):**
- `aiosqlite`: removed entirely from `requirements.txt` and all imports.
- `migrate_add_streak_columns`: deleted — streak columns go straight into the fresh `CREATE TABLE`.
- `PRAGMA journal_mode=WAL` / `PRAGMA busy_timeout`: removed from `init_db`.
- `db.row_factory = aiosqlite.Row`: removed (asyncpg `Record` is already dict-like).

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | asyncpg multi-statement DDL strings work in `await conn.execute(SCHEMA_SQL)` | Anti-Patterns Pitfall 1 | If asyncpg rejects multi-statement DDL, DDL must be split into per-statement `execute()` calls — extra code but trivially fixable |
| A2 | Oracle's 30-day account inactivity rule requires only a console login (not specific service usage) | Keep-alive section | If rule requires API/service activity, the monthly reminder must also make an API call — low risk |
| A3 | `postgres:16-alpine` image ships arm64 natively on Docker Hub | Dockerfile section | If alpine arm64 unavailable, fall back to `postgres:16` (bullseye) which definitely ships arm64 |
| A4 | Alembic would add meaningful complexity overhead for a 7-table start-fresh schema | R-02 decision | If the project later needs many schema versions, alembic is the right tool — not a now problem |

**If this table is empty:** It is not — four assumptions are listed above.

---

## Open Questions (RESOLVED)

> Each question below carries an inline recommendation that resolves it for planning/execution.

1. **Postgres superuser password management**
   - What we know: `DATABASE_URL` goes in `.env`; `POSTGRES_PASSWORD` goes in `.env` for Docker Compose.
   - What's unclear: Whether a separate `.env.prod` is needed, or if the same file serves both.
   - Recommendation: Single `.env` file; `POSTGRES_PASSWORD` and `DATABASE_URL` added alongside existing secrets. Docker Compose reads from `env_file: .env`.

2. **Backup authentication method (instance principal vs API key)**
   - What we know: OCI CLI supports both. Instance principal (IAM role for the VM) is more secure and avoids storing API keys.
   - What's unclear: Whether the Oracle Always Free tier supports instance principal IAM policies.
   - Recommendation: Start with API key in `.env` (simpler); document instance principal as the upgrade path. [ASSUMED: instance principal availability on free tier not verified]

3. **First-run command sync with AutoShardedBot**
   - What we know: `first_run()` currently uses `bot.start(DISCORD_TOKEN)` and closes after sync.
   - What's unclear: Whether `AutoShardedBot.start()` behaves identically for the `--first-run` path.
   - Recommendation: No change needed — `AutoShardedBot` inherits `start()` from `AutoShardedClient`. The `on_ready` in `first_run()` fires exactly once and calls `bot.close()`. [LOW confidence — no explicit verification found]

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | Bot runtime | ✓ (local dev) | 3.11+ (confirmed by project) | — |
| Docker + Docker Compose | SCALE-05 packaging | [ASSUMED] | Not checked — must be installed on Oracle VM | Manual Python install |
| FFmpeg | Audio | ✓ (local dev) | Available in Debian Bookworm apt | — |
| PostgreSQL | SCALE-02 | ✗ (local: SQLite) | Will be Docker container | — |
| asyncpg 0.31.0 | SCALE-02 | ✗ (not installed yet) | Latest on PyPI | — |
| oci-cli | SCALE-05 backup | [ASSUMED] | Not checked — needs install on Oracle VM | rclone (see Oracle docs) |
| Healthchecks.io account | SCALE-05 down-detection | ✓ (free tier sign-up) | Free, 20 checks | None needed |

**Missing dependencies with no fallback:**
- PostgreSQL (handled by Docker container in SCALE-05)
- asyncpg (pip install in requirements.txt update)

**Missing dependencies with fallback:**
- oci-cli: rclone can be used as an alternative OCI Object Storage client

---

## Validation Architecture

Nyquist validation is enabled (no explicit `false` in `.planning/config.json`).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio |
| Config file | none (implicit defaults) |
| Quick run command | `pytest tests/ -x --tb=short` |
| Full suite command | `pytest tests/ -v` |

### Requirement → Test Map

| Req ID | Behavior | Test Type | Automated Command | Approach |
|--------|----------|-----------|-------------------|----------|
| SCALE-01 (queue cap) | `MusicQueue.add()` raises/returns cap sentinel when over limit | Unit | `pytest tests/test_queue.py::TestQueueCap -x` | Pure logic — TDD candidate |
| SCALE-01 (buffer TTL) | `MessageBuffer._evict_stale()` removes channels beyond TTL | Unit | `pytest tests/test_message_buffer.py::TestTTLEviction -x` | Pure logic — TDD candidate |
| SCALE-01 (batch tx) | `log_track_batch()` inserts all 3 rows atomically (rollback on failure) | Integration | `pytest tests/test_database_phase4.py::TestBatchTransaction -x` | Requires real Postgres or pg-compatible in-process test DB |
| SCALE-02 (schema) | Postgres SCHEMA_SQL creates all 7 tables with correct column types | Integration | `pytest tests/test_database_phase4.py::TestPostgresSchema -x` | Requires Postgres; fixture uses `asyncpg.create_pool` to real test DB |
| SCALE-02 (helpers) | All `database.py` helpers execute without error; `get_repeat_song_count` uses `col::date = CURRENT_DATE` | Integration | `pytest tests/test_database_phase4.py -x` | Requires Postgres |
| SCALE-02 (streak) | `get_local_date` + `compute_streak` unchanged; unit tests still pass | Unit | `pytest tests/test_database.py -x` | These tests run unchanged — confirms D-17 |
| SCALE-03 (AutoShardedBot) | `create_bot()` returns `commands.AutoShardedBot` instance | Structural review + boot | `python -c "from bot import bot; from discord.ext.commands import AutoShardedBot; assert isinstance(bot, AutoShardedBot)"` | Structural — no Discord connection needed |
| SCALE-04 (to_dict/from_dict) | `Track.to_dict()` + `Track.from_dict()` round-trip is lossless | Unit | `pytest tests/test_queue.py::TestTrackSerialization -x` | Pure logic — TDD candidate |
| SCALE-04 (persist on mutation) | Each mutation site in `cogs/music.py` calls `persist_queue` | Structural review | Code inspection (grep for `persist_queue` at each mutation) | Cannot automate without Discord mock |
| SCALE-04 (smart rejoin) | Smart rejoin logic: restore state if humans, silent if not | Boot + structural review | `docker compose up` on clean volume; verify queue restored | Cannot automate — requires Discord voice state |
| SCALE-05 (Docker) | `docker compose up` starts both services, bot connects to Postgres | Boot / smoke | `docker compose up -d && docker compose ps` | Infra — boot test only |
| SCALE-05 (keep-alive) | `scripts/keepalive.sh` pings Healthchecks.io URL successfully | Structural + manual | `bash scripts/keepalive.sh && echo exit $?` | Requires Healthchecks.io account configured |
| SCALE-05 (backup) | `scripts/backup.sh` produces a valid pg_dump | Structural + manual | `bash scripts/backup.sh && oci os object list --bucket-name dexter-backups` | Requires OCI CLI and bucket |

### Unit-Testable Seams (TDD in Wave 0)

1. `Track.to_dict()` / `Track.from_dict()` round-trip (no DB, no Discord)
2. `MusicQueue.add()` queue-cap enforcement
3. `MessageBuffer._evict_stale()` TTL logic
4. `get_local_date()` / `compute_streak()` — **existing tests carry over unchanged**

### Integration-Testable Seams (require real Postgres)

5. `log_track_batch()` — atomic insert of 3 rows, rollback on failure
6. `persist_queue()` / `restore_queue()` round-trip via `guild_queues` table
7. Full schema creation (`init_db()`) and all helper functions

**Strategy for integration tests:** Use a real local Postgres instance (or the Docker Compose Postgres). Create a `@pytest_asyncio.fixture` that creates an `asyncpg.Pool` pointed at `postgresql://localhost:5432/dexter_test`, runs `init_db(pool)`, yields, then drops all tables. This mirrors the existing `aiosqlite.connect(":memory:")` pattern but requires Postgres to be running. The planner should note this in Wave 0: Postgres must be up before integration tests can run.

### Boot/Structural-Review Only

- AutoShardedBot type check (one import, one assert)
- Smart rejoin (requires Discord voice channel with humans)
- Docker Compose startup sequence
- Oracle keep-alive + backup (requires cloud infrastructure)

### Sampling Rate
- **Per task commit:** `pytest tests/test_queue.py tests/test_message_buffer.py -x` (unit tests only, fast)
- **Per wave merge:** `pytest tests/ -v` (full suite; integration tests require Postgres up)
- **Phase gate:** Full suite green + `docker compose up` smoke test before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_database_phase4.py` — covers SCALE-02 Postgres schema, `log_track_batch`, `persist_queue`/`restore_queue` round-trip; requires asyncpg fixture pointed at real Postgres
- [ ] `tests/test_queue.py::TestTrackSerialization` — `Track.to_dict()`/`from_dict()` round-trip (new class on `Track`)
- [ ] `tests/test_queue.py::TestQueueCap` — `MusicQueue.add()` rejects over `MAX_QUEUE_SIZE_PER_GUILD`
- [ ] `tests/test_message_buffer.py::TestTTLEviction` — `_evict_stale()` removes stale channels
- [ ] `conftest.py` update — asyncpg pool fixture for Postgres tests

*(Existing `test_database.py` and `test_database_phase2.py` test `aiosqlite`-based helpers and will be replaced or archived; the unit-pure `compute_streak` / `get_local_date` tests stay and are still green.)*

---

## Security Domain

`security_enforcement` not set in `.planning/config.json` — treat as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No (no user auth in bot) | — |
| V3 Session Management | No | — |
| V4 Access Control | No (Discord handles permissions) | — |
| V5 Input Validation | Yes — `guild_id` and `user_id` as SQL params | asyncpg parameterized queries (`$N`) — no string interpolation |
| V6 Cryptography | No | — |
| V7 Error Handling | Yes | Log Postgres errors to Discord error channel; no stack traces to users |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via guild/user ID | Tampering | asyncpg `$N` params — no string interpolation anywhere |
| Queue poisoning (malicious track URL) | Tampering | URL already validated before queue add (existing `is_url()` check); jsonb stores it verbatim; no exec |
| Postgres password leakage via logs | Information Disclosure | `DATABASE_URL` in `.env` (git-ignored); never log the DSN string |
| OCI credential leakage | Information Disclosure | `oci-cli` config in `~/.oci/` (not in Docker image); API keys never in `Dockerfile` or `.env` committed to git |
| `guild_queues` payload injection | Tampering | `json.dumps(payload)` of a Python dict with typed fields; no user-controlled keys |

---

## Sources

### Primary (HIGH confidence)
- [Context7 /magicstack/asyncpg] — `create_pool`, `acquire`, `transaction`, `$N` paramstyle, `ON CONFLICT DO UPDATE`
- [Context7 /websites/discordpy_readthedocs_io_en] — `AutoShardedBot` class, `shard_count` behavior, `VoiceChannel.connect()`
- [Context7 /docker/compose] — named volumes, `depends_on: service_healthy`, `platform: linux/arm64`
- [PyPI asyncpg 0.31.0](https://pypi.org/project/asyncpg/) — version, arm64/aarch64 wheel availability, Python 3.11+ support
- [Oracle Always Free Resources docs](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) — idle reclaim thresholds (CPU/net/mem <20% over 7 days; A1: 4 OCPU / 24 GB)
- Current source code: `database.py`, `models/queue.py`, `bot.py`, `config.py`, `models/message_buffer.py` — read directly

### Secondary (MEDIUM confidence)
- [Healthchecks.io docs](https://healthchecks.io/docs/) — dead-man's switch ping URL format, free tier (20 checks)
- [asyncpg vs psycopg3 comparison](https://fernandoarteaga.dev/blog/psycopg-vs-asyncpg/) — paramstyle difference, benchmarks
- [Oracle/PostgreSQL OCI backup](https://medium.com/oracledevs/backup-postgresql-database-to-oracle-cloud-infrastructure-object-storage-bucket-6314052c0661) — `pg_dump` + `oci os object put` pattern
- [Codycody31 OCI keep-alive](https://github.com/Codycody31/Prevent-OCI-Deletion-for-being-idle) — idle-reclaim threshold confirmation (7-day, CPU/net/mem <20%)

### Tertiary (LOW confidence)
- [Oracle FAQ](https://www.oracle.com/cloud/free/faq/) — 30-day account inactivity rule (HTTP 403 prevented direct verification; indirect confirmation via community discussions)

---

## Metadata

**Confidence breakdown:**
- Standard stack (asyncpg, Postgres, Docker): HIGH — verified via PyPI, Context7 official docs, and official Docker Hub
- Architecture (pool lifecycle, transaction pattern): HIGH — verified via Context7 asyncpg docs
- SQLite → Postgres conversion: HIGH — verified by reading actual source code + official Postgres SQL docs
- AutoShardedBot swap: HIGH — verified via Context7 discord.py docs
- Oracle idle reclaim thresholds: HIGH — verified via official Oracle docs page
- Queue persistence (jsonb shape): HIGH — based on official asyncpg jsonb support; design rationale verified
- Pitfalls: MEDIUM — executescript behavior inferred from asyncpg docs; on_ready double-fire verified by discord.py docs
- Healthchecks.io free tier: MEDIUM — official docs read but no direct fetch of pricing page possible
- OCI backup CLI pattern: MEDIUM — confirmed via official Oracle developer blog

**Research date:** 2026-06-12
**Valid until:** 2026-09-12 (90 days — Postgres and asyncpg are stable; Oracle free-tier policy may change)
