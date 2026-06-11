---
phase: 4
slug: scale
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-12
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Per-task map is populated after planning (see RESEARCH.md `## Validation Architecture`).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio |
| **Config file** | none (implicit defaults) |
| **Quick run command** | `pytest tests/ -x --tb=short` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~30s unit; integration adds Postgres spin-up |

> **Postgres dependency (new this phase):** integration tests require a live Postgres
> (the Docker Compose Postgres, or a local instance at `postgresql://localhost:5432/dexter_test`).
> A `@pytest_asyncio.fixture` creates an `asyncpg.Pool`, runs `init_db(pool)`, yields, drops tables —
> mirroring the existing `aiosqlite.connect(":memory:")` pattern. **Wave 0 must stand Postgres up before integration tests can run.**

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_queue.py tests/test_message_buffer.py -x` (fast, pure-logic units — no Postgres)
- **After every plan wave:** Run `pytest tests/ -v` (full suite; integration tests require Postgres up)
- **Before `/gsd-verify-work`:** Full suite green **+** `docker compose up` clean-volume smoke test
- **Max feedback latency:** < 30s for the per-commit unit sample

---

## Per-Task Verification Map

> Populated after PLAN.md files exist (per-task IDs come from the plans).
> Project convention: PURE LOGIC (queue-cap enforcement, buffer TTL eviction, `Track`
> (de)serialization round-trip, `compute_streak`/`get_local_date`) → unit-tested under `tests/`;
> Postgres helpers → integration tests behind an asyncpg fixture; `AutoShardedBot` swap,
> voice smart-rejoin, Docker/infra, Oracle keep-alive/backup → structural review + clean boot (manual-only).

| Req ID | Behavior | Test Type | Automated Command | Approach |
|--------|----------|-----------|-------------------|----------|
| SCALE-01 (queue cap) | `MusicQueue.add()` rejects over `MAX_QUEUE_SIZE_PER_GUILD` | Unit | `pytest tests/test_queue.py::TestQueueCap -x` | Pure logic — TDD candidate |
| SCALE-01 (buffer TTL) | `MessageBuffer._evict_stale()` removes channels beyond TTL | Unit | `pytest tests/test_message_buffer.py::TestTTLEviction -x` | Pure logic — TDD candidate |
| SCALE-01 (batch tx) | `log_track_batch()` inserts all 3 rows atomically (rollback on failure) | Integration | `pytest tests/test_database_phase4.py::TestBatchTransaction -x` | Requires real Postgres |
| SCALE-02 (schema) | Postgres `SCHEMA_SQL` creates all tables with correct column types | Integration | `pytest tests/test_database_phase4.py::TestPostgresSchema -x` | Requires Postgres; asyncpg fixture |
| SCALE-02 (helpers) | All `database.py` helpers run; date logic uses `col::date = CURRENT_DATE` | Integration | `pytest tests/test_database_phase4.py -x` | Requires Postgres |
| SCALE-02 (streak) | `get_local_date` + `compute_streak` unchanged; existing unit tests still pass | Unit | `pytest tests/test_database.py -x` | Confirms D-17 — tests carry over |
| SCALE-03 (AutoShardedBot) | `create_bot()` returns an `AutoShardedBot` instance | Structural + boot | `python -c "from bot import ...; assert isinstance(bot, AutoShardedBot)"` | No Discord connection needed |
| SCALE-04 (serialize) | `Track.to_dict()`/`from_dict()` round-trip is lossless | Unit | `pytest tests/test_queue.py::TestTrackSerialization -x` | Pure logic — TDD candidate |
| SCALE-04 (persist) | Every mutation site in `cogs/music.py` calls the persist hook | Structural review | grep for persist call at each mutation | Cannot automate without Discord mock |
| SCALE-04 (rejoin) | Smart rejoin: restore+resume if humans, silent restore if empty | Boot + structural | `docker compose up` clean volume; verify restore | Requires Discord voice state |
| SCALE-05 (Docker) | `docker compose up` starts both services; bot connects to Postgres | Boot / smoke | `docker compose up -d && docker compose ps` | Infra — boot test only |
| SCALE-05 (keep-alive) | keep-alive script pings Healthchecks.io successfully | Structural + manual | run script; assert exit 0 | Requires Healthchecks.io account |
| SCALE-05 (backup) | backup script produces a valid `pg_dump` to Object Storage | Structural + manual | run script; `oci os object list` | Requires OCI CLI + bucket |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky — per-task IDs assigned after planning.*

---

## Wave 0 Requirements

- [ ] `tests/test_database_phase4.py` — SCALE-02 Postgres schema, `log_track_batch`, persist/restore round-trip; asyncpg fixture pointed at real Postgres
- [ ] `tests/test_queue.py::TestTrackSerialization` — `Track.to_dict()`/`from_dict()` round-trip
- [ ] `tests/test_queue.py::TestQueueCap` — `MusicQueue.add()` rejects over `MAX_QUEUE_SIZE_PER_GUILD`
- [ ] `tests/test_message_buffer.py::TestTTLEviction` — `_evict_stale()` removes stale channels
- [ ] `tests/conftest.py` — asyncpg pool fixture for Postgres integration tests

*Existing `test_database.py` / `test_database_phase2.py` test aiosqlite helpers and will be replaced or archived; the unit-pure `compute_streak` / `get_local_date` tests stay and remain green.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| AutoShardedBot runs 1 shard, all cogs load | SCALE-03 | Needs real Discord gateway connect | Boot bot against test guild; confirm `READY` + 1 shard + slash commands synced |
| Voice smart-rejoin on restart | SCALE-04 | Requires a voice channel with/without humans | Queue songs, kill bot, restart: rejoins+resumes if humans present, silent restore if empty |
| Docker Compose full-stack boot on clean volume | SCALE-05 | Infra — fresh-host simulation | `docker compose down -v && docker compose up`; bot connects to fresh Postgres, schema created |
| Oracle keep-alive + dead-man ping | SCALE-05 | Requires Oracle VM + Healthchecks.io | Cron beat nudges idle thresholds AND pings check-in URL; stop bot → alert fires |
| pg_dump → Oracle Object Storage backup/restore | SCALE-05 | Requires OCI account + bucket | Run backup script; confirm object in bucket; restore into a scratch DB |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (asyncpg fixture + new test files)
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s (unit sample)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
