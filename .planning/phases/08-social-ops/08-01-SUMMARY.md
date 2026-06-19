---
phase: 08-social-ops
plan: 01
subsystem: database
tags: [postgres, asyncpg, leaderboard, sql, rate-limiter, gemini, config]

# Dependency graph
requires:
  - phase: 07-player-ux-filters
    provides: asyncpg pool pattern, conftest.py pool fixture, log_track_batch helper
  - phase: 04-scale
    provides: PostgreSQL schema, increment_daily_stat, bot_daily_stats table
provides:
  - total_errors column on bot_daily_stats (idempotent ALTER TABLE)
  - increment_daily_stat allowlist extended with "total_errors"
  - get_leaderboard_songs — per-guild song count aggregate
  - get_leaderboard_skips — per-guild most-skipped song titles
  - get_leaderboard_streaks — guild-active users by global longest_streak
  - get_daily_stats_row — today-only bot-wide stats dict (all 5 fields)
  - get_images_today_global — bot-wide daily image count
  - _RateLimiter.rpm_usage() and .rpm_headroom() synchronous getters
  - GeminiService.rpm_usage and .rpm_headroom properties
  - ROAST_COOLDOWN_SECONDS = 30 (slash command per-invoker cooldown)
  - LEADERBOARD_TOP_N = 5 constant
  - Wave-0 test scaffolding: test_database_phase8.py (8 tests) + test_rate_limiter.py extensions
affects: [08-02-PLAN, 08-03-PLAN, cogs/ops.py, cogs/ai.py]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ALTER TABLE ... ADD COLUMN IF NOT EXISTS inside SCHEMA_SQL for idempotent column additions"
    - "Synchronous getters on asyncio-based classes to avoid lock contention in dashboard reads"
    - "Per-guild leaderboard aggregates via COUNT(*) FROM song_history WHERE guild_id = $1 (not global counters)"

key-files:
  created:
    - tests/test_database_phase8.py
  modified:
    - database.py
    - services/gemini.py
    - config.py
    - tests/test_rate_limiter.py

key-decisions:
  - "total_errors column added via ALTER TABLE ... ADD COLUMN IF NOT EXISTS in SCHEMA_SQL (idempotent, consistent with project pattern)"
  - "ROAST_COOLDOWN_SECONDS updated from 300 to 30 — ambient ceiling preserved in separate AMBIENT_ROAST_CEILING_SECONDS constant; slash command cooldown is distinct from ambient roast ceiling"
  - "rpm_usage() / rpm_headroom() are synchronous (not async) — benign read race acceptable for dashboard; avoids Lock contention (Pitfall 4)"
  - "Leaderboard SQL uses COUNT(*) FROM song_history per guild, never user_profiles.total_songs_queued (Pitfall 1: global vs per-guild)"
  - "GROUP BY includes up.first_seen_at in get_leaderboard_songs to enable ORDER BY tie-break without ambiguity"

patterns-established:
  - "Per-guild leaderboard: always query song_history WHERE guild_id = $1, not global profile counters"
  - "SCHEMA_SQL idempotent column addition: ALTER TABLE ... ADD COLUMN IF NOT EXISTS appended after CREATE TABLE block"
  - "RPM getter pattern: synchronous read of deque len() after _clean(), no lock acquisition"

requirements-completed: [SOCIAL-02, OPS-01, OPS-03]

# Metrics
duration: 6min
completed: 2026-06-19
---

# Phase 08 Plan 01: Social & Ops Foundation Summary

**Per-guild leaderboard SQL helpers, total_errors column with allowlist extension, synchronous Gemini RPM getters, and Wave-0 test scaffolding — all contracts that Phase 8's /roast, /leaderboard, and /stats plans wire against**

## Performance

- **Duration:** 6 min
- **Started:** 2026-06-19T07:20:36Z
- **Completed:** 2026-06-19T07:26:21Z
- **Tasks:** 3
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments

- `database.py` extended with 5 new query helpers (leaderboard aggregates, daily stats, global image count) and idempotent `total_errors` column addition — all using `$N` parameterized SQL (T-08-01 mitigated)
- `services/gemini.py` extended with synchronous `rpm_usage()` / `rpm_headroom()` methods on `_RateLimiter` and matching properties on `GeminiService` for the `/stats` Gemini quota panel (D-24)
- Wave-0 test scaffolding complete: 8 integration tests in `tests/test_database_phase8.py` + 2 RPM getter unit tests in `tests/test_rate_limiter.py` — all 14 tests collect cleanly, rate limiter tests pass

## Task Commits

1. **Task 1: Wave-0 test scaffolding** - `74dd7de` (test)
2. **Task 2: database.py total_errors + leaderboard helpers** - `c5bb69a` (feat)
3. **Task 3: RPM getters + config constants** - `940eb77` (feat)

## Files Created/Modified

- `tests/test_database_phase8.py` — 8 integration tests for Phase 8 database helpers (collects clean; runs live with Postgres)
- `database.py` — `total_errors` column, allowlist entry, 5 new query helpers
- `services/gemini.py` — synchronous `rpm_usage()`, `rpm_headroom()` on `_RateLimiter`; `rpm_usage`, `rpm_headroom` properties on `GeminiService`
- `config.py` — `ROAST_COOLDOWN_SECONDS` updated to 30, `LEADERBOARD_TOP_N = 5` added
- `tests/test_rate_limiter.py` — extended with `test_rpm_usage_getter` and `test_rpm_headroom_getter`

## Decisions Made

- `ROAST_COOLDOWN_SECONDS` updated from 300 → 30: the existing value was an alias for `AMBIENT_ROAST_CEILING_SECONDS` (which is preserved at 300). The slash command per-invoker cooldown (D-04) is 30s — a semantically different concept that the same constant name now correctly represents.
- `GROUP BY` in `get_leaderboard_songs` includes `up.first_seen_at` (in addition to `user_id` and `username`) to support the `ORDER BY songs_queued DESC, up.first_seen_at ASC` tie-break clause without a Postgres "column must appear in GROUP BY" error.
- Leaderboard helpers return `list[asyncpg.Record]` (not `list[dict]`) — callers can use both `row["key"]` and `dict(row)` access patterns, consistent with other fetch helpers.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] GROUP BY clause extended to include first_seen_at for tie-break**
- **Found during:** Task 2 (database.py leaderboard helpers)
- **Issue:** `get_leaderboard_songs` orders by `up.first_seen_at ASC` for tie-break (D-16), but `first_seen_at` was not in the `GROUP BY` clause, which would cause a Postgres `ERROR: column "up.first_seen_at" must appear in the GROUP BY clause` at query runtime
- **Fix:** Added `up.first_seen_at` to the `GROUP BY` clause: `GROUP BY sh.user_id, up.username, up.first_seen_at`
- **Files modified:** `database.py`
- **Verification:** Python import check + `--collect-only` passes cleanly
- **Committed in:** `c5bb69a` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug prevention)
**Impact on plan:** Fix prevents a runtime SQL error on first `/leaderboard` invocation. No scope creep.

## Issues Encountered

- Task 1 test scaffolding import-fails during `--collect-only` until Task 2 helpers are present (ImportError on `get_leaderboard_songs`). Resolved per plan's note: "Task 2 may be done first in the same wave — coordinate via commit order." Task 1 was committed first (RED), Task 2 immediately after (GREEN), making collection clean.

## Known Stubs

None — all helpers return real query results with no placeholder data.

## Threat Flags

None — no new network endpoints, auth paths, or file access patterns introduced. SQL injection surface (T-08-01) mitigated by `$N` parameterized queries throughout.

## Next Phase Readiness

- All symbols required by Plan 02 (`/roast`) and Plan 03 (`/leaderboard`, `/stats`) are defined and import-clean
- Live DB integration tests in `test_database_phase8.py` are the automated gate for Phase 8 — will run at phase gate (no local Postgres; deferred per plan's acceptance criteria)
- Rate limiter tests pass locally (no Postgres needed): 6/6 green

## Self-Check: PASSED

- `tests/test_database_phase8.py` exists and defines 8 test functions ✓
- `tests/test_rate_limiter.py` contains `test_rpm_usage_getter` and `test_rpm_headroom_getter` ✓
- All 14 tests collect cleanly: `python -m pytest tests/test_database_phase8.py tests/test_rate_limiter.py --collect-only -q` ✓
- `database.py` SCHEMA_SQL contains `total_errors INTEGER DEFAULT 0` ✓
- `increment_daily_stat` `allowed_fields` includes `"total_errors"` ✓
- `database.py` defines all 5 new helpers ✓
- No f-string interpolation of guild_id in leaderboard helpers ✓
- `services/gemini.py` defines `rpm_usage` and `rpm_headroom` (sync, no lock) ✓
- `config.py` defines `ROAST_COOLDOWN_SECONDS = 30` and `LEADERBOARD_TOP_N = 5` ✓
- Commit hashes verified: 74dd7de, c5bb69a, 940eb77 ✓

---
*Phase: 08-social-ops*
*Completed: 2026-06-19*
