---
phase: 20-owner-control-plane-rate-observability
plan: 01
subsystem: database
tags: [postgres, asyncpg, schema, ddl, owner-control-plane]

# Dependency graph
requires:
  - phase: 18-per-guild-config-foundation-ci-gate
    provides: "guild_config table with forward-shipped silenced/is_blocked columns (unread until now)"
  - phase: 19-onboarding-admin-setup
    provides: "D-12 landmine identification (blacklist must survive guild_config purge) — resolved here via D-01"
provides:
  - "guild_blocklist table — the owner kill-switch's persistent, purge-proof blacklist"
  - "database.load_blocklist / insert_blocklist / delete_blocklist CRUD helpers"
  - "database.set_silenced — first reader/writer of guild_config.silenced"
  - "tests/test_database_phase20.py — static-shape + live-DB coverage"
affects: [20-04-guild-config-service, 20-07-owner-guilds-command, 21-memory-scoping-guild-data-lifecycle]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dedicated single-purpose table for a cross-phase-durable flag (guild_blocklist) instead of a column on a table subject to future purge"
    - "Upsert-on-conflict for re-block/re-config idempotency (mirrors set_proactive_opt_out)"
    - "UPDATE ... RETURNING with None-on-no-row as the 'did this write land' contract"

key-files:
  created:
    - tests/test_database_phase20.py
  modified:
    - database.py
    - tests/conftest.py
    - CLAUDE.md

key-decisions:
  - "D-01 (from 20-CONTEXT.md, user-selected): guild_blocklist is its OWN table, not guild_config.is_blocked — Phase 21's MEM-04 purge can DELETE FROM guild_config freely without a blacklist carve-out"
  - "D-03 (from 20-CONTEXT.md): guild_config.is_blocked left in place, unused, documented dead — no DROP COLUMN (additive-only DDL precedent held)"

patterns-established:
  - "guild_blocklist DDL follows the guild_config idiom (guild_id alone as PK, not composite like guild_jams) since it's a single flag per guild"
  - "set_silenced mirrors set_ambient_roasts_enabled/set_vision_roasts_enabled verbatim — UPDATE ... RETURNING _GUILD_CONFIG_RETURNING_COLUMNS"

requirements-completed: [OWNER-04, OWNER-02]

# Metrics
duration: 15min
completed: 2026-07-13
---

# Phase 20 Plan 01: Blocklist Table & Silenced DB Helpers Summary

**Added the purge-proof `guild_blocklist` table plus blocklist CRUD and `set_silenced` helpers in `database.py`, resolving the Phase 19 D-12 landmine by construction.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 2 completed
- **Files modified:** 4 (database.py, tests/conftest.py, CLAUDE.md, tests/test_database_phase20.py created)

## Accomplishments
- `guild_blocklist` table (`guild_id TEXT PRIMARY KEY, reason TEXT, blocked_at TIMESTAMPTZ`) landed in the single `SCHEMA_SQL` string (asyncpg param-free multi-statement DDL rule preserved)
- `load_blocklist` / `insert_blocklist` (upsert) / `delete_blocklist` CRUD helpers, and `set_silenced` (`UPDATE ... RETURNING`) — the first reader/writer of Phase 18's forward-shipped `guild_config.silenced` column
- `tests/test_database_phase20.py`: 5 static-shape tests (no DB) + 3 live-DB tests (blocklist CRUD round-trip, silenced round-trip incl. no-such-guild `None` contract, and the D-01 durability proof that a blocklist row survives a `guild_config` row delete)
- `tests/conftest.py` teardown now drops `guild_blocklist`; `CLAUDE.md` schema narrative updated to mark `guild_config.is_blocked` as dead/superseded (D-03)

## Task Commits

1. **Task 1: guild_blocklist DDL + blocklist/silenced DB helpers + conftest teardown** - `34b5105` (feat)
2. **Task 2: live-DB + static-shape tests for blocklist CRUD and silenced round-trip** - `a094361` (test)

_No separate plan-metadata commit required by this SUMMARY step — see final metadata commit below._

## Files Created/Modified
- `database.py` - `guild_blocklist` DDL appended to `SCHEMA_SQL`; `load_blocklist`/`insert_blocklist`/`delete_blocklist`/`set_silenced` helpers added
- `tests/conftest.py` - `guild_blocklist` added to the teardown `DROP TABLE` list
- `tests/test_database_phase20.py` - new file: static-shape + live-DB test coverage
- `CLAUDE.md` - schema narrative annotated: `guild_blocklist` table added, `guild_config.is_blocked` marked dead (D-03)

## Decisions Made
- Followed 20-CONTEXT.md D-01/D-03 exactly as user-selected: dedicated table, no destructive DDL on the dead column.
- `set_silenced` placed immediately after `set_vision_roasts_enabled` in `database.py`, mirroring its exact shape (verbatim UPDATE/RETURNING idiom) per the plan's read_first pointer.
- Blocklist helpers placed immediately after `set_silenced` (adjacent, same logical block) rather than near the `guild_jams` helpers further down the file — kept the three new blocklist functions and `set_silenced` together as one cohesive Phase 20 addition for easier future review.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The `_GUILD_CONFIG_RETURNING_COLUMNS` constant already included `silenced` (shipped forward in Phase 18), so `set_silenced`'s `RETURNING` clause required no changes to that shared constant.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The DB seam this plan produces (`guild_blocklist` table + 4 helpers) is exactly what 20-04's `GuildConfigService` extension (`_blocked` set, `block_guild`/`unblock_guild`/`is_blocked`/`silence_guild`/`unsilence_guild`) and 20-07's `/guilds` command wrap — both can proceed without further DB-tier work.
- Live-DB tests (`test_blocklist_crud_roundtrip`, `test_set_silenced_roundtrip`, `test_blocklist_independent_of_guild_config`) will exercise against CI's `pgvector/pgvector:pg16` service container; not run against a live DB in this local execution (`TEST_DATABASE_URL` unset here) — they skip cleanly, as designed.
- Full suite green: 941 passed, 121 skipped, 0 failed (confirms the additive DDL didn't regress anything).
- No blockers for 20-02/20-03 (other Wave 1 plans) or the Wave 2 plans that depend on this seam.

---
*Phase: 20-owner-control-plane-rate-observability*
*Completed: 2026-07-13*

## Self-Check: PASSED

All claimed files (database.py, tests/conftest.py, tests/test_database_phase20.py, CLAUDE.md,
this SUMMARY.md) confirmed present on disk; all claimed commits (34b5105, a094361, 07f8929)
confirmed present in `git log --oneline --all`.
