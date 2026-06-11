---
phase: 04-scale
verified: 2026-06-12T00:00:00Z
status: human_needed
score: 4/4 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Full Docker Compose clean-boot on Oracle A1 ARM"
    expected: "docker compose up brings up Postgres (healthcheck-gated), then bot connects to it, init_db creates all 7 tables, and bot logs 'Dexter is ready.' and posts its startup message"
    why_human: "Requires live Oracle VM with Docker, arm64 Postgres image pull, and a valid DISCORD_TOKEN — not runnable on Windows dev machine without Postgres"
  - test: "Queue persistence round-trip across restart"
    expected: "Queue a song, stop the bot, start it again — bot restores the in-memory queue (and smart-rejoins voice if a human is still present)"
    why_human: "Requires a live Discord connection plus Postgres — asyncpg integration tests written but not run (no Postgres on dev machine)"
  - test: "Over-cap /play rejection"
    expected: "After 500 tracks are in the queue, a further /play returns 'queue's full at 500 tracks. impressive dedication, wrong bot.' and the queue is not modified"
    why_human: "Requires live Discord bot invocation"
  - test: "PostgreSQL integration test suite (18 tests)"
    expected: "pytest tests/test_database_phase4.py -x exits 0 against a live dexter_test Postgres"
    why_human: "Requires CREATE DATABASE dexter_test; no Postgres available on this dev machine"
  - test: "keepalive.sh cron on Oracle host"
    expected: "HEALTHCHECK_URL is set in crontab env; script curls hc-ping.com; Healthchecks.io dashboard shows pings arriving every 5 min"
    why_human: "Requires live Oracle VM + Healthchecks.io account + crontab setup"
  - test: "backup.sh on Oracle host"
    expected: "oci-cli configured; script produces a dexter_YYYYMMDD_HHMMSS.dump object in the dexter-backups bucket"
    why_human: "Requires live Oracle VM + oci-cli config + Object Storage bucket"
---

# Phase 4: Scale Verification Report

**Phase Goal:** Dexter runs reliably across many servers on chosen 24/7 hosting with durable persistence
**Verified:** 2026-06-12
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Bot handles concurrent multi-server use without DB write contention, unbounded queues, or buffer-eviction issues | VERIFIED | `QueueFullError` enforced in `MusicQueue.add()` at `len >= MAX_QUEUE_SIZE_PER_GUILD (500)`; `log_track_batch` wraps 3 writes in one `async with conn.transaction()`; `MessageBuffer._evict_stale()` evicts channels older than `MESSAGE_BUFFER_TTL_HOURS=24` on every `add()` call |
| 2 | Persistence runs on PostgreSQL with no SQLite-specific `datetime('now')` dependence | VERIFIED | `database.py` has zero `aiosqlite`, `AUTOINCREMENT`, `PRAGMA`, `datetime('now')` references; all timestamps are `TIMESTAMPTZ DEFAULT now()`; `requirements.txt` has `asyncpg==0.31.0` with no `aiosqlite` |
| 3 | Bot runs as an `AutoShardedBot` and restores music queues across restarts | VERIFIED (static) | `class DexterBot(commands.AutoShardedBot)` in `bot.py`; `_ready_done` guard prevents reconnect double-fire; `restore_queues(bot)` called after `load_extension`, before `_post_startup_messages`; `QueuePersistenceService.restore_queues` caps restored list at `MAX_QUEUE_SIZE_PER_GUILD` and clamps `current_index` (CR-03 fixes applied) — live behavior requires Postgres |
| 4 | A hosting/deployment decision is resolved and the bot runs 24/7 on the chosen provider | VERIFIED (static) | Oracle Cloud Always Free A1 ARM decided; `Dockerfile` (python:3.11-slim-bookworm, ffmpeg, runs `bot.py`), `docker-compose.yml` (2 services, arm64, `service_healthy` gated, 3 named volumes), `scripts/keepalive.sh` (Oracle idle-nudge + Healthchecks.io dead-man), `scripts/backup.sh` (pg_dump to OCI Object Storage) all present with no hardcoded secrets |

**Score:** 4/4 truths verified (static/structural checks; runtime/Postgres checks deferred to human verification)

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `models/queue.py` | `QueueFullError`, `MusicQueue.add()` cap, `Track.to_dict/from_dict` | VERIFIED | All three present; `add()` raises at `len(tracks) >= 500`; round-trip methods complete |
| `models/message_buffer.py` | `_evict_stale()` TTL eviction, `_last_seen` tracking | VERIFIED | `_evict_stale()` defined and called first in `add()`; `_last_seen` dict updated on every add |
| `config.py` | Phase 4 constants: `DATABASE_URL`, `DB_POOL_MIN/MAX`, `MAX_QUEUE_SIZE_PER_GUILD`, `MESSAGE_BUFFER_TTL_HOURS`, `HEALTHCHECK_URL` | VERIFIED | All 6 constants present; `DATABASE_URL` and `HEALTHCHECK_URL` via `os.getenv` |
| `database.py` | asyncpg full rewrite, Postgres DDL, 7 tables incl. `guild_queues`, `log_track_batch` transaction | VERIFIED | No SQLite-isms remain; `guild_queues` present; `log_track_batch` wraps 3 inserts in `async with conn.transaction()` |
| `tests/test_database_phase4.py` | `TestPostgresSchema`, `TestBatchTransaction`, `TestHelpers` (18 tests) | VERIFIED (collection) | All 18 tests collected; require live Postgres to execute |
| `tests/conftest.py` | asyncpg pool fixture with `dexter_test` DSN, teardown drops all 7 tables | VERIFIED | `asyncpg.create_pool`, `init_db`, yield, `DROP TABLE … CASCADE`, `p.close()` all present |
| `requirements.txt` | `asyncpg==0.31.0`; no `aiosqlite` | VERIFIED | Line 3: `asyncpg==0.31.0`; `aiosqlite` absent from file |
| `bot.py` | `DexterBot(AutoShardedBot)` subclass, asyncpg pool, `_ready_done` guard, `restore_queues` call, pool teardown via `close()` override | VERIFIED | `DexterBot.close()` overrides the method and calls `await pool.close()` (CR-01 fix); `_ready_done` set only after successful init (WR-01 fix); ordering: load_extension → restore_queues → _post_startup_messages confirmed |
| `services/queue_persistence.py` | `QueuePersistenceService`, `persist()` UPSERT, `clear_persisted()`, `restore_queues()` + module-level wrapper | VERIFIED | All four present; smart-rejoin checks for non-bot humans; CR-03 fixes applied (cap truncation + `current_index` clamping) |
| `cogs/music.py` | Pool migration, `log_track_batch`, `QueueFullError` handling, persist-on-mutation hooks (>=6 sites), `clear_persisted` after `queue.clear()` | VERIFIED | `self.bot.db` absent; `log_track_batch` called in `_log_track`; `QueueFullError` caught at both add sites; `_persist_queue` called 9 times; `clear_persisted` called in `/stop`; `voice_client.channel.id` live-captured (not stored on model); WR-06 fix: `system_channel` gated on `permissions_for(guild.me).send_messages` |
| `cogs/ai.py` | Pool migration; global Gemini limiter unchanged | VERIFIED | `self.bot.pool` in all DB calls; no `self.bot.db`; global `self.bot.gemini_service` unchanged |
| `cogs/imagine.py` | Pool migration | VERIFIED | `self.bot.pool` in all DB calls; no `self.bot.db` |
| `Dockerfile` | python:3.11-slim-bookworm, ffmpeg, pip install, CMD bot.py, no secret literals | VERIFIED | All present; no ENV with secret literal |
| `docker-compose.yml` | 2 services (postgres, bot), arm64, 3 named volumes, `service_healthy` gated, POSTGRES_PASSWORD interpolated | VERIFIED | All present; `${POSTGRES_PASSWORD}` interpolated; `/app/data/cache` and `/app/logs` volume mounts match `config.py` path constants |
| `scripts/keepalive.sh` | Bash script, curls `$HEALTHCHECK_URL`, `|| true` non-fatal, no hardcoded secrets | VERIFIED | Present; `curl -fsS … "${HEALTHCHECK_URL}" … || true`; no secret literals |
| `scripts/backup.sh` | `pg_dump --format=custom dexter \| oci os object put --bucket-name dexter-backups`, no hardcoded password | VERIFIED | Both commands present; password docs use `~/.pgpass`; no literal credential |
| `.env.example` | All vars documented with placeholders, `CHANGE_ME` values, no real secrets | VERIFIED | 7 vars documented; `DATABASE_URL`, `POSTGRES_PASSWORD`, `HEALTHCHECK_URL`, `DISCORD_TOKEN`, `GEMINI_API_KEY`, `GENIUS_TOKEN`, `OWNER_ID` present with placeholder values |
| `.dockerignore` | Excludes `.env`, `data/`, `logs/`, `.git/`, `__pycache__`, `.planning/` | VERIFIED | All exclusions present |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `models/queue.py MusicQueue.add()` | `config.MAX_QUEUE_SIZE_PER_GUILD` | `len(self.tracks) >= config.MAX_QUEUE_SIZE_PER_GUILD` | VERIFIED | Line 86: exact pattern present |
| `models/message_buffer.py add()` | `config.MESSAGE_BUFFER_TTL_HOURS` | `timedelta(hours=config.MESSAGE_BUFFER_TTL_HOURS)` | VERIFIED | `__init__` line 18: `self._ttl = timedelta(hours=config.MESSAGE_BUFFER_TTL_HOURS)` |
| `bot.py on_ready` → `_initialize_once()` | asyncpg pool | `asyncpg.create_pool(dsn=config.DATABASE_URL, …)` | VERIFIED | Line 222 in `_initialize_once` |
| `bot.py` | `services.queue_persistence.restore_queues` | `await restore_queues(bot)` after `load_extension`, before `_post_startup_messages` | VERIFIED | Lines 288-289 in `_initialize_once`; `_post_startup_messages` called in `on_ready` after `_initialize_once` returns |
| `services/queue_persistence.py persist()` | `guild_queues` table | `INSERT … ON CONFLICT (guild_id) DO UPDATE` | VERIFIED | Lines 57-63 |
| `cogs/music.py _log_track()` | `database.log_track_batch` | `await log_track_batch(self.bot.pool, …)` | VERIFIED | Lines 662-670 |
| `cogs/music.py mutation sites` | `self.bot.queue_persistence.persist` | `await self._persist_queue(guild, queue)` (9 sites) | VERIFIED | 9 `_persist_queue` calls confirmed by grep |
| `cogs/music.py /play handler` | `QueueFullError` | `try: queue.add(track) except QueueFullError` | VERIFIED | Both single-add (line 545) and playlist-loop (line 821) sites |
| `docker-compose.yml bot service` | `postgres` service | `depends_on: condition: service_healthy` | VERIFIED | Lines 41-43 |
| `DexterBot.close()` | `bot.pool.close()` | `await pool.close()` in overridden `close()` method | VERIFIED | Lines 43-50 (CR-01 fix applied) |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `cogs/music.py HistoryPageView` | `self.rows` (list[dict] from `get_history_rows`) | `database.get_history_rows(pool, guild_id=…)` fetches from `song_history` via asyncpg | Yes — real Postgres query returning `TIMESTAMPTZ` `queued_at` values; `strftime` format guard applied (CR-02 fix) | FLOWING (static) |
| `services/queue_persistence.py restore_queues` | `queue.tracks` | `pool.fetch("SELECT guild_id, payload FROM guild_queues")` | Yes — real Postgres query; `Track.from_dict` reconstructs; capped at `MAX_QUEUE_SIZE_PER_GUILD` | FLOWING (static) |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All Phase 4 config constants importable with correct values | `python -c "import config; assert config.MAX_QUEUE_SIZE_PER_GUILD == 500; …"` | Exit 0 | PASS |
| No SQLite-isms in database.py | `python -c "src=open('database.py').read(); assert 'aiosqlite' not in src; …"` | Exit 0 | PASS |
| No aiosqlite in any cog | `grep -c "self.bot.db" cogs/music.py cogs/ai.py cogs/imagine.py` | 0 matches | PASS |
| bot.py structural checks (AutoShardedBot, asyncpg, guard, restore) | `python -c "src=open('bot.py').read(); assert 'AutoShardedBot' in src; …"` | Exit 0 | PASS |
| queue_persistence.py importable with all required symbols | `python -c "import services.queue_persistence as qp; assert hasattr(qp, 'QueuePersistenceService'); …"` | Exit 0 | PASS |
| 130 pure unit tests (queue, buffer, audio, formatters, streaks, roasts, seasonal, server_state, prompts, responses) | `pytest tests/test_queue.py tests/test_message_buffer.py … -q` | 130 passed | PASS |
| 18 Postgres integration tests collectible (no live DB needed) | `pytest tests/test_database_phase4.py --collect-only -q` | 18 collected, exit 0 | PASS |
| All modified source files parse without syntax errors | `python -c "import ast; [ast.parse(open(f).read()) for f in [9 files]]"` | Exit 0 | PASS |

---

### Probe Execution

No `scripts/*/tests/probe-*.sh` files present. Phase 4 probes are expressed as pytest tests and in-verification spot-checks — all passed where runnable (see Behavioral Spot-Checks above). Full integration probes (Postgres, Docker, Discord) are deferred to human verification.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SCALE-01 | 04-01, 04-02, 04-04 | Bot hardened for concurrent multi-server use (DB write contention, queue caps, buffer eviction) | SATISFIED | `QueueFullError` in `models/queue.py`; `log_track_batch` transaction in `database.py`; `_evict_stale` in `MessageBuffer`; all wired in cog consumers |
| SCALE-02 | 04-02, 04-03, 04-04 | Persistence migrates SQLite → PostgreSQL (no `datetime('now')` dependence) | SATISFIED | `database.py` fully asyncpg with Postgres DDL; all cogs use `self.bot.pool`; zero SQLite-isms remain in any file |
| SCALE-03 | 04-03 | Bot runs as `AutoShardedBot` for scale across many guilds | SATISFIED (static) | `class DexterBot(commands.AutoShardedBot)` instantiated in `create_bot()`; `_ready_done` guard prevents reconnect double-fire (WR-01 fix applied) |
| SCALE-04 | 04-01, 04-02, 04-03, 04-04 | Music queues persist across restarts | SATISFIED (static) | `guild_queues` table in schema; `QueuePersistenceService.persist()` UPSERT at 9 mutation sites; `restore_queues()` called on boot after cogs load; CR-03 hardening applied; full round-trip requires live Postgres |
| SCALE-05 | 04-05 | Hosting/deployment decision made; bot runs 24/7 on chosen provider | SATISFIED (structural) | Oracle Cloud Always Free A1 ARM chosen; complete Docker Compose stack (arm64, healthcheck-gated, named volumes); keepalive + backup scripts; no secrets committed |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `bot.py` | 399 | `queue.clear()` in idle-leave does NOT call `clear_persisted()` | Info (IN-02 from review) | Idle-cleared queues will be restored on next boot; behavioral inconsistency, not a crash. Documented deferred in 04-REVIEW.md |
| `cogs/music.py` | 1206 | `queue.clear()` in reconnect-failure path does NOT call `clear_persisted()` | Info (same as IN-02) | Same as above |
| `database.py` | 9 | `import json  # noqa: F401` — json not used in this module | Info (IN-01 from review) | Unused import; no functional impact |
| `models/queue.py` | 6 | `from dataclasses import dataclass, field` — `field` never used | Info (IN-01 from review) | Unused import; no functional impact |
| `services/queue_persistence.py` | 147-148 | `await vc_channel.connect()` then immediately `await music_cog._play_track(...)` without confirming `is_connected()` | Warning (WR-03 partial — smart-rejoin voice race from original CR-03) | `_play_track` has its own guard (`if not voice_client or not voice_client.is_connected(): return`) so the no-op worst case is a silently non-started playback; queue is restored in memory. The parked reconnect race (D-22) is documented out of scope |

No `TBD`, `FIXME`, or `XXX` debt markers found in any Phase 4 file.

---

### Human Verification Required

#### 1. Full Docker Compose Clean Boot (Oracle A1 ARM)

**Test:** On the Oracle VM: `docker compose down -v && docker compose up -d && docker compose logs -f bot`
**Expected:** Postgres passes healthcheck; bot container starts; asyncpg pool created; `init_db` runs; `Dexter is ready.` logged; startup message posted to Discord guild
**Why human:** Requires live Oracle VM with Docker, arm64 image pull, valid `.env` with `DISCORD_TOKEN` and `POSTGRES_PASSWORD`

#### 2. Queue Persistence Round-Trip

**Test:** `/play` a song in a guild so it appears in `guild_queues`; restart the bot; verify queue is restored in memory (check `/queue`); if a human is in voice, verify smart-rejoin fires
**Expected:** Queue survives restart; smart-rejoin connects and starts playback only when humans are present
**Why human:** Requires live Discord bot + Postgres; behavior involves discord.py gateway reconnect flow

#### 3. Over-Cap /play Rejection

**Test:** With 500 tracks already queued (or by temporarily setting `MAX_QUEUE_SIZE_PER_GUILD=1`), run `/play <song>`
**Expected:** Bot responds: "queue's full at 500 tracks. impressive dedication, wrong bot." and the queue length does not increase
**Why human:** Requires live Discord bot

#### 4. PostgreSQL Integration Test Suite

**Test:** `CREATE DATABASE dexter_test; pytest tests/test_database_phase4.py -x`
**Expected:** All 18 tests pass: schema creation, batch transaction atomicity, upsert paths, helper smoke tests
**Why human:** Requires running Postgres with `dexter_test` database; not available on this Windows dev machine

#### 5. Keepalive Cron Verification

**Test:** Add crontab entry on Oracle host: `HEALTHCHECK_URL=https://hc-ping.com/<uuid> */5 * * * * /opt/dexter/scripts/keepalive.sh`; check Healthchecks.io dashboard after 10 min
**Expected:** Pings arrive every ~5 min; Oracle VM stays above 20% network threshold
**Why human:** Requires Oracle VM + Healthchecks.io account

#### 6. Backup Cron Verification

**Test:** `bash scripts/backup.sh` on Oracle host with oci-cli configured and `~/.pgpass` set
**Expected:** `dexter_YYYYMMDD_HHMMSS.dump` object appears in the `dexter-backups` OCI bucket; exit 0
**Why human:** Requires Oracle VM + oci-cli config + Object Storage bucket

---

### Gaps Summary

No gaps. All static-verifiable must-haves pass. The 3 Critical and 2 Warning items from 04-REVIEW.md were applied and confirmed:

- **CR-01** (pool never closed): Fixed via `DexterBot.close()` override
- **CR-02** (/history datetime crash): Fixed via `hasattr(queued_at, "strftime")` guard in `HistoryPageView._build_embed`
- **CR-03** (restore bypasses cap, index race): Fixed in `QueuePersistenceService.restore_queues` — list truncated to `MAX_QUEUE_SIZE_PER_GUILD`, `current_index` clamped to `[0, len-1]`
- **WR-01** (boot deadlock on init failure): Fixed — `_ready_done` set only after `_initialize_once()` succeeds; `_ready_initializing` blocks concurrent re-entry
- **WR-06** (system_channel perm check): Fixed — `_get_text_channel` gates `system_channel` on `permissions_for(guild.me).send_messages`

Known follow-ups (deferred per 04-REVIEW.md, not blockers):
- WR-02: Timezone mismatch between `date.today()` in daily-stat writes vs `CURRENT_DATE` in SQL — documented deferred
- WR-03: Restore does not re-persist corrected state after truncation — documented deferred  
- WR-04: `_play_track` recursion on unavailable runs — documented deferred
- WR-05: `change_presence` on single-shard deploy is harmless; multi-shard presence accuracy is a future concern
- WR-07: `backup.sh` pipe masks pg_dump failure — documented deferred
- IN-01, IN-02, IN-03, IN-04: minor cleanups, no functional impact

---

_Verified: 2026-06-12_
_Verifier: Claude (gsd-verifier)_
