---
phase: 04-scale
plan: "01"
subsystem: models/config
tags: [queue-cap, serialization, ttl-eviction, config, tdd, scale]
dependency_graph:
  requires: []
  provides: [QueueFullError, Track.to_dict, Track.from_dict, MessageBuffer._evict_stale, Phase4Config]
  affects: [models/queue.py, models/message_buffer.py, config.py]
tech_stack:
  added: []
  patterns: [module-level exception class, dataclass serialization, TTL eviction pattern]
key_files:
  created:
    - tests/test_queue.py (TestQueueCap + TestTrackSerialization classes added)
    - tests/test_message_buffer.py (TestTTLEviction class added)
  modified:
    - config.py (Phase 4 constants block appended)
    - models/queue.py (QueueFullError, Track.to_dict/from_dict, cap guard in add())
    - models/message_buffer.py (_evict_stale, _last_seen, _ttl, modified add())
decisions:
  - "MAX_QUEUE_SIZE_PER_GUILD=500 (mid-range of D-04 allowed 500-1000)"
  - "MESSAGE_BUFFER_TTL_HOURS=24 per D-05"
  - "DB_POOL_MIN=2, DB_POOL_MAX=10 per D-01 asyncpg sizing"
  - "DATABASE_URL default points at local compose Postgres (postgresql://dexter:dexter@localhost:5432/dexter)"
  - "HEALTHCHECK_URL defaults empty string so absence is safe"
  - "cap guard placed in model (not cog) so playlist loop is covered at the source (Pitfall 3)"
metrics:
  duration: "4m"
  completed: "2026-06-12"
  tasks_completed: 3
  files_modified: 5
---

# Phase 4 Plan 01: Pure-logic Spine (Queue Cap, Serialization, Buffer TTL, Config) Summary

Pure-logic seams for Phase 4: queue cap via `QueueFullError` + `MusicQueue.add()` enforcement, lossless `Track.to_dict`/`from_dict` jsonb serialization, `MessageBuffer._evict_stale()` TTL eviction for idle channels, and six new Phase 4 `config.py` constants — all covered by three new TDD-green test classes with zero regressions.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add Phase 4 config constants | 2d6c57b | config.py |
| 2 | Queue cap + Track serialization (TDD) | ca65134, db21180 | models/queue.py, tests/test_queue.py |
| 3 | MessageBuffer TTL eviction (TDD) | 4776a1e, 0cd04f0 | models/message_buffer.py, tests/test_message_buffer.py |

## What Was Built

### Task 1: Phase 4 Config Constants (`config.py`)

Six new constants appended as a Phase 4 block:
- `DATABASE_URL = os.getenv(...)` — asyncpg DSN, defaults to local compose Postgres
- `DB_POOL_MIN = 2` / `DB_POOL_MAX = 10` — asyncpg pool bounds
- `MAX_QUEUE_SIZE_PER_GUILD = 500` — per-guild queue cap (SCALE-01)
- `MESSAGE_BUFFER_TTL_HOURS = 24` — idle-channel eviction window (SCALE-01)
- `HEALTHCHECK_URL = os.getenv(...)` — dead-man ping URL (D-13), empty default is safe

Secrets (`DATABASE_URL`, `HEALTHCHECK_URL`) read via `os.getenv` exclusively — never literal strings in source (T-04-01 information disclosure mitigation).

### Task 2: `QueueFullError` + `Track` Serialization (`models/queue.py`)

**`QueueFullError(Exception)`** defined at module level with docstring.

**`MusicQueue.add()` cap guard:** raises `QueueFullError(f"Queue is at capacity ({config.MAX_QUEUE_SIZE_PER_GUILD} tracks).")` before appending when `len(self.tracks) >= config.MAX_QUEUE_SIZE_PER_GUILD`. Placed in the model (not the cog) so the playlist-import loop is protected at the source (PATTERNS.md Pitfall 3).

**`Track.to_dict()`** returns a plain dict of all 8 fields (`video_id`, `title`, `artist`, `url`, `duration_seconds`, `requested_by`, `was_auto_queued`, `thumbnail`) — JSON-safe for Postgres jsonb storage.

**`Track.from_dict(cls, d)`** (classmethod) reconstructs a `Track` using `d[key]` for required fields and `d.get(key, default)` for `artist` (None), `was_auto_queued` (False), `thumbnail` (None).

### Task 3: `MessageBuffer._evict_stale()` (`models/message_buffer.py`)

**`__init__`** gains `_last_seen: dict[int, datetime] = {}` and `_ttl = timedelta(hours=config.MESSAGE_BUFFER_TTL_HOURS)`.

**`_evict_stale()`** computes `cutoff = datetime.now() - self._ttl` and removes every channel from both `_buffers` and `_last_seen` whose timestamp is older than the cutoff. Bounds unbounded buffer growth across many idle guilds (SCALE-01, T-04-02 DoS mitigation).

**`add()`** calls `_evict_stale()` first, then records `_last_seen[channel_id] = datetime.now()`, then proceeds with the existing append logic unchanged.

## Test Coverage

| Class | File | Tests | Result |
|-------|------|-------|--------|
| TestQueueCap | tests/test_queue.py | 3 | PASS |
| TestTrackSerialization | tests/test_queue.py | 5 | PASS |
| TestTTLEviction | tests/test_message_buffer.py | 4 | PASS |

Full file regressions:
- `pytest tests/test_queue.py -x` → 26 passed (was 17; +9 new)
- `pytest tests/test_message_buffer.py -x` → 12 passed (was 8; +4 new)
- `pytest tests/test_queue.py tests/test_message_buffer.py -x` → 38 passed total

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| Task 2 RED | ca65134 | PASS (ImportError on missing QueueFullError) |
| Task 2 GREEN | db21180 | PASS (8/8 new tests pass) |
| Task 3 RED | 4776a1e | PASS (AttributeError on missing _last_seen) |
| Task 3 GREEN | 0cd04f0 | PASS (4/4 new tests pass) |

## Deviations from Plan

None — plan executed exactly as written.

## Threat Mitigations Applied

| Threat ID | Mitigation Applied |
|-----------|-------------------|
| T-04-01 | `DATABASE_URL` and `HEALTHCHECK_URL` read via `os.getenv` only — no secret literals in source |
| T-04-02 | `QueueFullError` cap (500 tracks/guild) + `_evict_stale()` TTL (24h) bound memory growth |
| T-04-03 | Buffer content stored verbatim (never eval'd or interpolated into SQL); accepted per plan |

## Known Stubs

None — all logic is fully wired within scope of this plan. Downstream wiring (cog QueueFullError catch, persistence service usage) is intentionally deferred to plans 04-03 and 04-04 per the wave design.

## Self-Check: PASSED

Files exist:
- `config.py` — FOUND (MAX_QUEUE_SIZE_PER_GUILD, MESSAGE_BUFFER_TTL_HOURS, DATABASE_URL, DB_POOL_MIN, DB_POOL_MAX, HEALTHCHECK_URL)
- `models/queue.py` — FOUND (QueueFullError, to_dict, from_dict, cap guard)
- `models/message_buffer.py` — FOUND (_evict_stale, _last_seen, _ttl)
- `tests/test_queue.py` — FOUND (TestQueueCap, TestTrackSerialization)
- `tests/test_message_buffer.py` — FOUND (TestTTLEviction)

Commits verified:
- 2d6c57b — chore(04-01): add Phase 4 config constants
- ca65134 — test(04-01): add failing tests for queue cap and Track serialization
- db21180 — feat(04-01): QueueFullError cap + Track to_dict/from_dict serialization
- 4776a1e — test(04-01): add failing tests for MessageBuffer TTL idle-channel eviction
- 0cd04f0 — feat(04-01): MessageBuffer TTL idle-channel eviction (_evict_stale)
