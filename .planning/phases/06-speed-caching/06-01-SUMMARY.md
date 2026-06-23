---
phase: "06-speed-caching"
plan: "01"
subsystem: "data-layer + metrics + tests"
tags: [phase6, perf, resolution-cache, metrics, postgres, tdd-scaffold]
dependency_graph:
  requires: []
  provides:
    - "config.PREFETCH_TIMEOUT_SECONDS, RES_CACHE_TTL_DAYS, SPONSORBLOCK_CATEGORIES, PERF_ROLLING_WINDOW"
    - "database.resolution_cache table + normalize_search_query / get_resolution_cache / set_resolution_cache"
    - "services/metrics.py PerfMetrics class"
    - "models/queue.py _prefetch_video_id / _prefetch_task fields"
    - "tests/test_phase6_perf.py Wave-0 test scaffold (all 14 pure + 4 skip + 4 xfail)"
  affects:
    - "database.py SCHEMA_SQL (new table)"
    - "tests/conftest.py (resolution_cache teardown, pool skip-on-no-DB fix)"
tech_stack:
  added:
    - "services/metrics.py (new module) — collections.deque rolling aggregate"
  patterns:
    - "asyncpg ON CONFLICT (query_key) DO UPDATE SET ... expires_at = EXCLUDED.expires_at (TTL refresh, Pitfall 5)"
    - "pytest.skip in pool fixture on asyncpg.create_pool failure (vs error)"
    - "pytest.mark.xfail strict=False for Plan-04 prefetch placeholders"
key_files:
  created:
    - services/metrics.py
    - tests/test_phase6_perf.py
  modified:
    - config.py
    - database.py
    - models/queue.py
    - tests/conftest.py
decisions:
  - "SCHEMA_SQL DDL-only (no $N params) — asyncpg multi-statement path requires it (CLAUDE.md Pitfall 1 / Pitfall 7)"
  - "set_resolution_cache ON CONFLICT updates expires_at to refresh TTL on re-write (Pitfall 5)"
  - "conftest pool fixture now pytest.skip on connection error instead of raising (Rule 1 bug fix — matches documented behaviour)"
  - "PerfMetrics in services/metrics.py (standalone module) rather than inlined in audio.py for clean import graph"
metrics:
  duration: "~15 min"
  completed_date: "2026-06-24"
  tasks_completed: 2
  files_created: 2
  files_modified: 4
---

# Phase 06 Plan 01: Phase 6 Foundation — Data Layer, Metrics, Test Scaffold Summary

**One-liner:** Postgres resolution_cache table + asyncpg helpers, PerfMetrics deque-backed rolling aggregate in services/metrics.py, queue prefetch state fields, and Wave-0 xfail test scaffold so downstream plans (02–04) have stable contracts to build on.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Config constants, resolution_cache schema + helpers, PerfMetrics, queue fields | f6d305f | config.py, database.py, services/metrics.py, models/queue.py |
| 2 | Wave-0 test scaffold + conftest teardown | fcda0fb | tests/test_phase6_perf.py, tests/conftest.py |

## What Was Built

### Task 1 — Contracts and data layer

**config.py** — Phase 6 constant block added after the Phase 5 block:
- `PREFETCH_TIMEOUT_SECONDS = 45` (D-10)
- `RES_CACHE_TTL_DAYS = 14` (D-07)
- `SPONSORBLOCK_CATEGORIES = frozenset({6 D-14 categories})` (D-14)
- `PERF_ROLLING_WINDOW = 50` (D-18)

**database.py** — three additions:
1. `resolution_cache` table appended to `SCHEMA_SQL` (DDL-only, no `$N` params, Pitfall 7). Columns: `query_key TEXT PK`, `video_id TEXT NOT NULL`, `title TEXT`, `created_at TIMESTAMPTZ DEFAULT now()`, `expires_at TIMESTAMPTZ NOT NULL`. Plus `idx_rescache_expires` index on `expires_at`.
2. `normalize_search_query(q)` — pure function; `re.sub(r"\s+", " ", q.strip().lower())`. Used as cache key (T-06-01 / ASVS V5).
3. `get_resolution_cache(pool, *, query_key)` — `fetchrow` with `WHERE expires_at > now()` TTL filter; returns `dict | None`.
4. `set_resolution_cache(pool, *, query_key, video_id, title, ttl_days)` — `INSERT ... ON CONFLICT (query_key) DO UPDATE SET video_id=..., title=..., expires_at=...`; TTL computed in Python and passed as `$N` param. Updates `expires_at` on conflict so frequently-used queries never expire (Pitfall 5).

**services/metrics.py** — new module with `PerfMetrics` class:
- Four `collections.deque(maxlen=window)` fields: `cache_hits`, `download_times`, `search_times`, `ttfa_times`.
- `record_cache_result(hit)`, `record_download(elapsed)`, `record_search(elapsed)`, `record_ttfa(elapsed)`.
- `summary()` returns `{cache_hit_rate, avg_download_s, avg_ttfa_s, avg_search_s, samples}` with guarded division (0.0 on empty).

**models/queue.py** — two prefetch fields added to `__init__` and reset in `clear()`:
- `self._prefetch_video_id: str | None = None`
- `self._prefetch_task: asyncio.Task | None = None`
- `asyncio` import added at module top.

### Task 2 — Wave-0 test scaffold

**tests/test_phase6_perf.py** — 22 test functions across 3 classes + 6 standalone functions:
- `TestNormalizeQuery` (6 pure tests) — strips, lowercases, collapses whitespace
- `TestPerfMetrics` (7 pure tests) — hit rate, empty safety, maxlen eviction, averages
- `TestResolutionCache` (4 live-DB tests, skip when no Postgres) — hit, expired TTL miss, TTL refresh upsert, missing key returns None
- `test_url_bypasses_cache` — `YouTubeService.is_url()` classification (D-09 guard)
- `test_prefetch_task_spawned`, `test_prefetch_skips_cached`, `test_prefetch_stale_gen`, `test_timing_logged` — `@pytest.mark.xfail(strict=False)` placeholders; Plan 04 removes xfail when wiring lands

**tests/conftest.py** — two changes:
1. `resolution_cache` added to DROP TABLE teardown list.
2. `pool` fixture now calls `pytest.skip()` on `asyncpg.create_pool` failure instead of raising — fixes the "skipped (connection error)" claim in the module docstring that was previously wrong (Rule 1 bug fix).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] conftest pool fixture errored instead of skipping on no-DB**
- **Found during:** Task 2 verification run
- **Issue:** conftest.py docstring claimed "skipped (connection error) when no Postgres is available" but the fixture raised `ConnectionRefusedError`, causing test ERROR rather than SKIP
- **Fix:** Added `try/except` around `asyncpg.create_pool(dsn)` with `pytest.skip(...)` on failure
- **Files modified:** `tests/conftest.py`
- **Commit:** fcda0fb

## Verification Results

```
python -c "import config, database; from services.metrics import PerfMetrics; from models.queue import MusicQueue"
# imports cleanly

python -m pytest tests/test_phase6_perf.py -x -q
# 14 passed, 4 skipped, 4 xfailed, 1 warning

grep -v '^#' database.py | grep -c resolution_cache
# 6 (> 3 required)
```

## Threat Surface Scan

No new network endpoints or auth paths introduced. The `resolution_cache` table write path was already covered in the plan's threat model (T-06-01 / T-06-02). All DB writes use `$N` positional params. No additional threat flags.

## Known Stubs

None — this plan defines contracts, not UI or command stubs. The `test_prefetch_*` and `test_timing_logged` are intentional `xfail` placeholders with `strict=False` (Plan 04 removes them).

## Self-Check: PASSED

| Item | Status |
|------|--------|
| services/metrics.py | FOUND |
| tests/test_phase6_perf.py | FOUND |
| 06-01-SUMMARY.md | FOUND |
| Commit f6d305f | FOUND |
| Commit fcda0fb | FOUND |
