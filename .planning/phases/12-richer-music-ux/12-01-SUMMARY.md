---
phase: 12-richer-music-ux
plan: "01"
subsystem: database
tags: [postgres, asyncpg, discord.py, guild-jams, playlists, jsonb]

requires:
  - phase: 12-richer-music-ux
    provides: Phase 12 context, patterns, research, validation strategy

provides:
  - guild_jams Postgres table (PK guild_id+name, JSONB snapshot, idx_jams_guild index) in SCHEMA_SQL
  - save_jam/get_jam/list_jams/delete_jam/count_jams async DB helpers in database.py
  - /jam app_commands.Group in cogs/library.py (save/add/load/list/delete subcommands)
  - JAMS_PER_GUILD_MAX=25 config knob in config.py
  - tests/test_database_phase12.py — asyncpg integration tests (23 tests, cross-guild isolation)
  - tests/test_jam_load.py — pure-unit truncation tests (11 tests)

affects:
  - 12-02 through 12-04 (wave-1 plans that also append to database.py/config.py)
  - any future plan adding guild-scoped collaborative features

tech-stack:
  added: []
  patterns:
    - guild-scoped JSONB snapshot (mirrors user_playlists but keyed on guild_id)
    - collaborative no-ownership-gate command group (D-03)
    - asyncpg $N positional params + JSONB str-normalisation in get helpers

key-files:
  created:
    - tests/test_database_phase12.py
    - tests/test_jam_load.py
  modified:
    - database.py
    - config.py
    - cogs/library.py
    - tests/conftest.py

key-decisions:
  - "guild_jams uses PRIMARY KEY (guild_id, name) — mirrors user_playlists, swap user_id to guild_id (D-01/D-02)"
  - "No ownership gate on /jam subcommands — any guild member can save/add/load/list/delete (D-03)"
  - "Reuse PLAYLIST_NAME_MAX_LENGTH (60) for jam names — no new knob added (D-05)"
  - "/jam add appends now-playing track to existing snapshot; creates new jam if name is fresh (D-04)"
  - "Empty-jam snapshot ([]) in /jam load produces distinct error rather than silent no-op (Pitfall 7)"

patterns-established:
  - "guild-scoped JSONB DB helpers: same five-function template as user_playlists, keyed on guild_id"
  - "jam_load: exact QueueFullError truncation loop from playlist_load — added/truncated counters"

requirements-completed: [UX-01]

duration: 45min
completed: 2026-06-30
---

# Phase 12 Plan 01: Guild Jams Summary

**guild_jams Postgres table + 5 DB helpers + /jam Group (save/add/load/list/delete) giving each Discord server a collaborative shared mixtape keyed on guild_id with no ownership gate**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-06-30T00:00:00Z
- **Completed:** 2026-06-30
- **Tasks:** 3 / 3
- **Files modified:** 6 (database.py, config.py, cogs/library.py, tests/conftest.py, + 2 new test files)

## Accomplishments

- Added `guild_jams` table to `SCHEMA_SQL` (idempotent DDL, PRIMARY KEY (guild_id, name), `idx_jams_guild`, JSONB snapshot) and 5 async helpers: `save_jam`, `get_jam`, `list_jams`, `delete_jam`, `count_jams` — all with `$N` positional params (T-12-01-01) and cross-guild isolation (T-12-01-02)
- Added `/jam` `app_commands.Group` in `cogs/library.py` with save/add/load/list/delete subcommands — all ephemeral, keyed on `guild_id`, no ownership gate (D-03)
- Created 23 asyncpg integration tests including cross-guild isolation assertions and 11 pure-unit truncation tests (all pass)

## Task Commits

1. **Task 1: guild_jams schema + 5 DB helpers + JAMS_PER_GUILD_MAX + integration test** - `b740269` (feat)
2. **Task 2: /jam command group — save, add, list, delete** - `889fa38` (feat)
3. **Task 3: /jam load (queue-cap truncation) + truncation unit test** - `b6846f0` (feat)

## Files Created/Modified

- `database.py` — Added `guild_jams` DDL to `SCHEMA_SQL` + `save_jam`/`get_jam`/`list_jams`/`delete_jam`/`count_jams` helpers (Phase 12 section after playlist helpers)
- `config.py` — Added Phase 12 section: `JAMS_PER_GUILD_MAX=25`, `SKIP_STATS_MIN_PLAYS=5`, `AUTO_QUEUE_SEARCH_CANDIDATES=3`
- `cogs/library.py` — Added `jam = app_commands.Group(name="jam", ...)` with 5 subcommands; updated `from database import` block to include jam helpers
- `tests/conftest.py` — Added `guild_jams` to teardown `DROP TABLE` for clean test isolation
- `tests/test_database_phase12.py` — 23 asyncpg integration tests (schema, CRUD, cross-guild isolation, upsert, delete-returns-false)
- `tests/test_jam_load.py` — 11 pure-unit tests for QueueFullError truncation loop (M tracks vs cap-N queue)

## Decisions Made

- Reused `PLAYLIST_NAME_MAX_LENGTH` (60) for jam names — no new knob (D-05); plan explicitly required this
- Empty-jam snapshot triggers a distinct "that jam is empty." error rather than silent no-op (Pitfall 7)
- `/jam add` creates a new jam (if name doesn't exist) instead of requiring `/jam save` first — convenience for track-by-track curation (D-04)

## Deviations from Plan

None — plan executed exactly as written. All five DB helpers, the config knobs, the `/jam` Group with all 5 subcommands, and both test files were delivered per spec.

## Issues Encountered

None.

## User Setup Required

None — no new external services or environment variables. `guild_jams` table is created idempotently by `init_db()` on next bot boot.

Note: `/jam` commands will not appear in Discord until the bot is restarted and command tree is synced (standard slash command workflow).

## Next Phase Readiness

- `guild_jams` table and 5 helpers are ready for any plan that reads/writes jams
- `SKIP_STATS_MIN_PLAYS` and `AUTO_QUEUE_SEARCH_CANDIDATES` knobs already in config.py for Plans 12-02 and 12-04
- No blockers for subsequent Wave-1 plans (12-02 through 12-04)

---

## Self-Check: PASSED

Files verified:

- `database.py` — FOUND: guild_jams in SCHEMA_SQL, all 5 helpers importable
- `config.py` — FOUND: JAMS_PER_GUILD_MAX == 25
- `cogs/library.py` — FOUND: ast.parse clean, imports OK
- `tests/test_database_phase12.py` — FOUND: 23 tests collected
- `tests/test_jam_load.py` — FOUND: 11 tests pass

Commits verified:

- b740269 — FOUND (Task 1: guild_jams schema + helpers)
- 889fa38 — FOUND (Task 2: /jam group save/add/list/delete)
- b6846f0 — FOUND (Task 3: /jam load + truncation test)

---
*Phase: 12-richer-music-ux*
*Completed: 2026-06-30*
