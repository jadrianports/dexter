---
phase: 12-richer-music-ux
plan: "02"
subsystem: ops-ux
tags: [skip-stats, leaderboard, pure-logic, tdd, ux]
dependency_graph:
  requires: []
  provides: [UX-02]
  affects: [cogs/ops.py, database.py, utils/embeds.py, logic/skip_stats.py]
tech_stack:
  added: []
  patterns:
    - pure-logic seam (logic/ package, TEST-01) — compute_skip_rate extracted, no discord/asyncio imports
    - TDD RED/GREEN cycle — test-first commit before implementation
    - $N positional params — get_user_skip_rate uses guild_id=$1 AND user_id=$2 (T-12-02-01/03)
    - defer + try/except pattern — /skips mirrors /leaderboard (asyncio.TimeoutError before Exception)
key_files:
  created:
    - logic/skip_stats.py
    - tests/test_skip_stats.py
  modified:
    - config.py         # SKIP_STATS_MIN_PLAYS = 5 (already present in Phase 12 section)
    - database.py       # get_user_skip_rate appended
    - utils/embeds.py   # skips_embed added; SKIPS_RATE_ROASTS/SKIPS_NOT_ENOUGH_DATA imported
    - cogs/ops.py       # /skips command added between /leaderboard and /stats
    - personality/responses.py  # SKIPS_RATE_ROASTS and SKIPS_NOT_ENOUGH_DATA pools
decisions:
  - "SKIP_STATS_MIN_PLAYS=5 was already present in config.py Phase 12 section from 12-01 patterns — no change needed"
  - "Roast footer templates added to personality/responses.py (SKIPS_RATE_ROASTS) following existing leaderboard commentary pattern"
  - "compute_skip_rate handles the 0/0 edge (floor=0 satisfied → 0.0) preventing division-by-zero"
  - "get_user_skip_rate returns a Record with total_plays/total_skips even when no rows exist (COUNT(*) always returns a row)"
metrics:
  duration_seconds: 80
  completed_date: "2026-06-30"
  tasks_completed: 2
  files_modified: 6
---

# Phase 12 Plan 02: /skips Command Summary

**One-liner:** Dedicated `/skips` command surfacing Dexter's tracked skip data — server most-skipped list + roast-flavored personal skip rate footer, gated by a min-plays floor.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (TDD RED) | Failing tests for compute_skip_rate | 2566238 | tests/test_skip_stats.py |
| 1 (TDD GREEN) | compute_skip_rate pure logic | 92bbbc8 | logic/skip_stats.py |
| 2 | DB helper + embed + /skips command | 293bd69 | database.py, utils/embeds.py, cogs/ops.py, personality/responses.py |

## What Was Built

**`logic/skip_stats.py`** — Pure function `compute_skip_rate(total_plays, total_skips, min_plays) -> float | None`. Returns None below the min-plays floor (D-08), 0.0 for 0/0 edge, and a 0.0–1.0 rate otherwise. No discord/asyncio/asyncpg imports.

**`database.get_user_skip_rate`** — `fetchrow` aggregate over `song_history` keyed on both `guild_id=$1 AND user_id=$2` (T-12-02-01). All-time, no date filter (D-09). Min-plays floor not applied in SQL — delegated to pure logic.

**`utils.embeds.skips_embed`** — Two-section embed: server most-skipped songs list (reusing `get_leaderboard_skips` format) and a `set_footer` personal roast. Footer is either a "not enough data" line (None skip_rate) or a roast template formatted with integer percentage, e.g. "you skip 30% of what you queue. bold of you to keep going." (D-07).

**`cogs/ops.py /skips`** — Public command (`defer()` not ephemeral). Calls `get_leaderboard_skips` for the server list and `get_user_skip_rate` for the personal row. Applies `compute_skip_rate` with `config.SKIP_STATS_MIN_PLAYS`. Mirrors `/leaderboard`'s `asyncio.TimeoutError → Exception` error handling. `/stats` command unchanged (D-06: skip analytics in own surface).

**`personality/responses.py`** — Added `SKIPS_RATE_ROASTS` (4 format-string templates, `{pct}` substitution) and `SKIPS_NOT_ENOUGH_DATA` (3 lines).

**`tests/test_skip_stats.py`** — 8 pure unit tests: below-floor → None, floor-1 → None, at-floor all-skipped → 1.0, representative ratio → 0.3, 0/0 with floor=0 → 0.0, never-raises.

## Verification

```
python -m pytest tests/test_skip_stats.py -x          → 8 passed
python -m pytest tests/ -x (unit tests only)           → 538 passed, 0 failures
python -c "import cogs.ops, utils.embeds, database,
           logic.skip_stats, config"                   → exits 0
python -c "import logic.skip_stats as s;
           assert s.compute_skip_rate(3,3,5) is None
           and s.compute_skip_rate(5,5,5)==1.0
           and s.compute_skip_rate(0,0,0)==0.0"        → exits 0
python -c "import config; assert config.SKIP_STATS_MIN_PLAYS == 5"   → exits 0
AST parse (cogs/ops.py, utils/embeds.py)               → clean
```

Manual (live guild): deferred — bot runs on residential PC on demand. Expected behavior: `/skips` renders server most-skipped + personal footer; user under SKIP_STATS_MIN_PLAYS sees "not enough data yet" path.

## Deviations from Plan

None — plan executed exactly as written.

`config.SKIP_STATS_MIN_PLAYS` was already present in the Phase 12 section of `config.py` (added by Plan 12-01 scaffolding). No change was needed; the acceptance criteria check `assert config.SKIP_STATS_MIN_PLAYS == 5` still passes.

## TDD Gate Compliance

- RED gate: `test(12-02)` commit `2566238` — 8 failing tests for `compute_skip_rate` (import error = correct RED).
- GREEN gate: `feat(12-02)` commit `92bbbc8` — implementation; all 8 tests pass.
- No REFACTOR step needed — implementation was clean on first pass.

## Threat Surface Scan

No new network endpoints or auth paths. `/skips` reads from `song_history` (aggregate only) via parameterized SQL. All mitigations from the plan's threat register (T-12-02-01 through T-12-02-05) are implemented:
- T-12-02-01: `guild_id=$1 AND user_id=$2` in `get_user_skip_rate`
- T-12-02-02: `get_leaderboard_skips` already guild-scoped
- T-12-02-03: No f-string SQL anywhere
- T-12-02-04: `SKIP_STATS_MIN_PLAYS=5` floor applied
- T-12-02-05: `asyncio.TimeoutError` caught, degrades gracefully

## Self-Check: PASSED

- `logic/skip_stats.py` exists: FOUND
- `tests/test_skip_stats.py` exists: FOUND
- `get_user_skip_rate` in `database.py`: FOUND
- `def skips_embed` in `utils/embeds.py`: FOUND
- `name="skips"` in `cogs/ops.py`: FOUND
- Commits 2566238, 92bbbc8, 293bd69: FOUND
