---
phase: 03-alive
plan: "02"
subsystem: database
tags: [python, sqlite, aiosqlite, streak, tdd, zoneinfo, migration]

# Dependency graph
requires:
  - phase: 03-alive
    plan: "01"
    provides: "MILESTONE_STREAK_THRESHOLDS, MILESTONE_SONG_THRESHOLDS, REPEAT_SONG_ROAST_THRESHOLD, STREAK_TIMEZONE in config.py"
provides:
  - "compute_streak(current_streak, last_streak_date, tz_name) pure function — D-18 strict reset via ZoneInfo timezone (D-17)"
  - "get_local_date(tz_name) pure function — timezone-correct date using ZoneInfo"
  - "user_profiles streak columns: current_streak, longest_streak, last_streak_date via additive idempotent migration (D-19)"
  - "migrate_add_streak_columns(db) — PRAGMA-guarded idempotent ALTER TABLE; called in init_db after executescript"
  - "get_repeat_song_count(db, guild_id, user_id, title) — PERS-04 same-song-today COUNT"
  - "update_user_streak(db, user_id, tz_name) -> (new_streak, longest, milestone_or_None) — PERS-09 persistence + D-21 milestone detection"
  - "get_history_rows(db, guild_id, limit) — HIST-01 data source for /history (plan 03-05)"
  - "36 tests green: 11 in test_streak.py + 25 in test_database_phase3.py"
affects:
  - "03-05 (MusicCog /history + repeat-song roast — consumes get_history_rows, get_repeat_song_count)"
  - "03-04 (EventsCog streak hooks — consumes update_user_streak)"
  - "03-06 (bot.py streak-update path)"

# Tech-stack
tech_stack:
  added:
    - "zoneinfo.ZoneInfo — DST-correct timezone date math (D-17)"
    - "tzdata — Windows ZoneInfo data package (added to requirements.txt)"
  patterns:
    - "TDD RED → GREEN cycle: failing import error first, then all green"
    - "PRAGMA table_info idempotency guard for additive ALTER TABLE migration"
    - "Parameterized SQL only — no string interpolation on user-influenced inputs (T-03-03)"

# Key files
key_files:
  modified:
    - path: "database.py"
      changes: "Added get_local_date, compute_streak (pure), migrate_add_streak_columns, get_repeat_song_count, update_user_streak, get_history_rows; added streak cols to SCHEMA_SQL; updated init_db to call migration"
    - path: "requirements.txt"
      changes: "Added tzdata for Windows ZoneInfo support"
  created:
    - path: "tests/test_streak.py"
      purpose: "11 pure-unit tests for compute_streak (4 branches) + get_local_date"
    - path: "tests/test_database_phase3.py"
      purpose: "25 async in-memory DB tests: schema columns, migration idempotency, repeat-song count, streak updates + milestones, history rows"

# Key decisions
decisions:
  - "compute_streak placed in database.py (not a separate utils/ file) — single module owns all streak logic per PATTERNS.md"
  - "migrate_add_streak_columns placed BEFORE init_db in source and called AFTER executescript() — avoids table-not-yet-exists failure (Pitfall 4)"
  - "update_user_streak returns (new_streak, longest, milestone_or_None) — milestone is the threshold int on exact crossing (D-21), else None; no separate 'already_fired' column needed"
  - "LIMIT bound as int(limit) in get_history_rows — explicit cast matches OBS-05 convention from Phase 2.5 hardening"

# Metrics
metrics:
  duration_minutes: 25
  completed_date: "2026-06-11"
  tasks_completed: 2
  files_modified: 2
  files_created: 2
  tests_added: 36
---

# Phase 3 Plan 02: Streak DB Migration + Pure Streak Math + Helpers Summary

**One-liner:** Additive streak migration + timezone-correct compute_streak + get_repeat_song_count/update_user_streak/get_history_rows DB seams — all TDD RED→GREEN.

## What Was Built

### Task 1: Pure streak math (RED → GREEN)

Added two pure functions to `database.py` — no DB, no Discord, fully unit-testable:

- `get_local_date(tz_name: str) -> date` — returns `datetime.now(tz=ZoneInfo(tz_name)).date()`, ensuring DST-correct timezone boundary (D-17, Pitfall 3). NOT `date.today()` or `datetime.utcnow()`.
- `compute_streak(current_streak, last_streak_date, tz_name) -> tuple[int, str]` — implements D-18 strict reset:
  - `last_streak_date is None` → first activity: `(1, today_iso)`
  - `delta == 0` (same day) → no-op: `(current_streak, last_streak_date)`
  - `delta == 1` (consecutive) → increment: `(current_streak + 1, today_iso)`
  - `delta >= 2` (missed day) → reset: `(1, today_iso)`

`tests/test_streak.py` covers all 4 branches with dynamically-computed reference dates (timezone-correct, not date-of-run-dependent): 11 tests, all green.

### Task 2: DB migration + query helpers (RED → GREEN)

All additions to `database.py`:

**SCHEMA_SQL** — `user_profiles` now includes streak columns for fresh installs:
```sql
current_streak INTEGER DEFAULT 0,
longest_streak INTEGER DEFAULT 0,
last_streak_date TEXT
```

**`migrate_add_streak_columns(db)`** — PRAGMA-guarded idempotent migration. Checks `PRAGMA table_info(user_profiles)` before each ALTER TABLE so re-running on an already-migrated DB is a no-op. Called in `init_db` after `executescript(SCHEMA_SQL)` (not before — Pitfall 4 ordering enforced).

**`get_repeat_song_count(db, *, guild_id, user_id, title) -> int`** — PERS-04 seam. Parameterized COUNT query for same-song-today plays. Returns 3 after 3 inserts of the same title (threshold check).

**`update_user_streak(db, *, user_id, tz_name) -> tuple[int, int, int | None]`** — PERS-09 persistence. Reads current streak/last_date, calls `compute_streak`, persists updated values, returns `(new_streak, new_longest, milestone)`. `milestone` is the threshold int on exact crossing against `config.MILESTONE_STREAK_THRESHOLDS`, else `None` (D-21 always-fire-once-per-threshold via exact equality, no extra bookkeeping).

**`get_history_rows(db, *, guild_id, limit=50) -> list[dict]`** — HIST-01 data source for plan 03-05. Returns `title, artist, url, duration_seconds, user_id, queued_at` ordered newest-first. LIMIT bound as `int(limit)` (T-03-03).

`tests/test_database_phase3.py` covers: schema columns present, migration idempotency, get_repeat_song_count (zero/one/three/guild-filter/user-filter/case-sensitive), update_user_streak (first-call, same-day no-op, db persistence, milestone fires at 7, no milestone at non-threshold, longest_streak updates), get_history_rows (empty, required keys, ordering, limit, guild filter). 25 tests, all green.

## Test Results

```
tests/test_streak.py          11 passed
tests/test_database_phase3.py 25 passed
Combined target               36 passed

Full suite: 207 passed, 1 pre-existing failure (test_ytdlp_selfheal.py::TestDownloadRetryAfterUpdate::test_updates_and_retries_on_failure — unrelated to this plan; confirmed failing before 03-02 work began)
```

## Must-Haves Status

| Truth | Status |
|-------|--------|
| compute_streak() implements consecutive+1 / same-day no-op / missed-day reset using configured timezone | Met — all 4 branches tested in test_streak.py; ZoneInfo(tz_name) via get_local_date confirmed |
| user_profiles gains current_streak, longest_streak, last_streak_date via idempotent additive migration | Met — SCHEMA_SQL + migrate_add_streak_columns + idempotency test passes |
| get_repeat_song_count() returns same-song-today plays for a user in a guild | Met — returns 3 after 3 inserts; parameterized SQL (T-03-03) |
| update_user_streak() persists streak and reports milestone crossings | Met — persists to DB; returns milestone=7 on exact crossing; None otherwise |

## Commits

| Hash | Message |
|------|---------|
| b2051cf | feat(03-02): add pure streak math — compute_streak + get_local_date (Task 1) |
| 3f52500 | test(03-02): add failing tests for DB migration + streak/repeat-song helpers (Task 2 RED) |
| 93998c1 | feat(03-02): add streak migration + DB helpers — SCHEMA_SQL, migrate, repeat-song, streak, history (Task 2) |

## Deviations from Plan

None — plan executed exactly as written. The pure functions (`compute_streak`, `get_local_date`) were already present in the working tree when execution started (leftover from plan 03-01 setup); they were staged and committed as Task 1 GREEN at the start of this plan execution. The RED test file (`tests/test_streak.py`) was similarly untracked and committed as part of Task 1.

## Threat Surface Scan

No new network endpoints, auth paths, or file access patterns introduced. All SQL is parameterized (T-03-03 addressed). Column names in migrate_add_streak_columns are hard-coded literals (T-03-04 addressed). No new external inputs beyond what already flows into the existing DB helpers.

## Self-Check: PASSED

- `database.py` — modified, contains `compute_streak`, `migrate_add_streak_columns`, `get_repeat_song_count`, `update_user_streak`, `get_history_rows`
- `tests/test_streak.py` — created, 11 tests green
- `tests/test_database_phase3.py` — created, 25 tests green
- Commits b2051cf, 3f52500, 93998c1 verified in git log
