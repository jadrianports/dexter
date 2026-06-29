---
phase: 11-rag-long-term-memory
plan: "07"
subsystem: memory-hygiene
tags: [rag, decay, sweep, expiry, salience, tdd, asyncpg, background-task, daily-loop]

# Dependency graph
requires:
  - phase: 11-04
    provides: MemoryService.remember() + write-time cap eviction (write-time hygiene partner)
  - phase: 11-05
    provides: memory_distill_batch daily loop pattern (template for memory_sweep)
provides:
  - models/memory.py: decay_predicate — pure expiry selection on salience + age
  - config.py: MEMORY_DECAY_SALIENCE_FLOOR=0.5 (shared threshold for DB + predicate)
  - database.py: delete_expired_memories — parameterized time+salience bounded DELETE
  - services/memory.py: MemoryService.sweep() — calls delete_expired_memories, swallows errors
  - bot.py: memory_sweep daily @tasks.loop (02:30 UTC) + before_loop + error + start guard + cleanup-list
  - tests/test_memory.py: 8 TestDecayPredicate tests + 3 memory_sweep registration tests
  - tests/test_database_phase11.py: 4 static signature checks + 1 live-DB round-trip (skipped without DB)
affects:
  - Phase 11 complete (MEM-07 — both hygiene mechanisms now in place: write-time cap 11-04 + decay sweep 11-07)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TDD commit sequence: RED test commit (c9bbea2) before GREEN implementation (d3d06e6) — skipif import guard allows clean collection at RED"
    - "Import guard pattern: try/except ImportError + pytest.mark.skipif — decay_predicate skips during RED, passes GREEN (mirrors 11-04 dedup_decision pattern)"
    - "decay_predicate: strict > for age boundary (age > decay_days), >= for salience floor (salience >= floor → retain)"
    - "delete_expired_memories: two-param parameterized DELETE (expires_at < $1 AND salience < $2) — T-11-07b bounded-delete mitigaton"
    - "sweep() error handling: all exceptions caught → log.warning + return 0; loop never raises (T-11-07c / REL-02)"
    - "memory_sweep at 02:30 UTC: distinct from cache_cleanup (hourly), ytdlp_update (04:00), memory_distill_batch (03:00) — thundering-herd avoidance"
    - "MEMORY_DECAY_SALIENCE_FLOOR=0.5 in config: single source of truth for DB DELETE and pure decay_predicate default"

key-files:
  created: []
  modified:
    - models/memory.py (added decay_predicate — ~55 lines)
    - config.py (added MEMORY_DECAY_SALIENCE_FLOOR=0.5)
    - database.py (added delete_expired_memories — ~50 lines)
    - services/memory.py (added MemoryService.sweep() — ~50 lines)
    - bot.py (added memory_sweep task + before_loop/error + start guard + cleanup-list — ~38 lines)
    - tests/test_memory.py (added TestDecayPredicate 8 tests + 3 registration checks — ~109 lines)
    - tests/test_database_phase11.py (expanded stub to full live-DB test + 4 static checks — ~70 lines)

key-decisions:
  - "decay_predicate default salience_floor=0.5: pure literal default (no config dep); MEMORY_DECAY_SALIENCE_FLOOR=0.5 in config for DB helper — keeps pure function side-effect-free"
  - "delete_expired_memories includes salience < $2 clause (T-11-07b): mirrors decay_predicate; prevents over-broad deletes of high-salience expired facts"
  - "memory_sweep at 02:30 UTC: distinct from ytdlp_update (04:00) and memory_distill_batch (03:00) to spread daily Neon pool load"
  - "sweep() returns 0 on error (not raises): daily loop must be self-healing — a transient Neon hiccup must never kill the background task (T-11-07c)"

# Metrics
duration: 28min
completed: 2026-06-29
---

# Phase 11 Plan 07: Memory Hygiene — Decay Sweep Summary

**decay_predicate + delete_expired_memories + MemoryService.sweep() + memory_sweep daily loop — the time-based decay backstop that keeps the memory store permanently bounded**

## Performance

- **Duration:** ~28 min
- **Started:** 2026-06-29
- **Completed:** 2026-06-29
- **Tasks:** 3 (Task 1 TDD, Task 2 auto, Task 3 auto)
- **Files modified:** 7

## Accomplishments

- `decay_predicate(fact, now, decay_days, salience_floor=0.5)` (models/memory.py): pure, clock-injectable expiry predicate — returns True when BOTH age > decay_days AND salience < salience_floor; high-salience (milestone=1.0, late_night=0.7, repeat_song=0.5) retained forever; daily_batch=0.2 and auto_queue_ignored=0.4 age out after 90 days
- `MEMORY_DECAY_SALIENCE_FLOOR = 0.5` (config.py): single source of truth for the DB delete salience threshold and the decay_predicate default
- `delete_expired_memories(pool, *, now)` (database.py): `DELETE FROM user_memories WHERE expires_at IS NOT NULL AND expires_at < $1 AND salience < $2`; fully parameterized, returns deleted count; pairs with T-11-07b bounded-delete mitigation
- `MemoryService.sweep()` (services/memory.py): orchestrates delete_expired_memories with `now=datetime.now(UTC)`; logs count; swallows all exceptions and returns 0 (T-11-07c / REL-02 discipline)
- `memory_sweep` (bot.py): daily `@tasks.loop(hour=2, minute=30)` guarded by `getattr(bot, "memory_service", None)`; `before_loop` wait_until_ready; `error` → `_post_loop_error`; started in `_initialize_once` behind `is_running()` guard; added to `_cleanup_partial_init` loop-cancel list (WR-04)
- `TestDecayPredicate` (tests/test_memory.py): 8 tests — old low-salience→selected; old high-salience→retained; recent low-salience→retained; floor boundary (inclusive >=); age boundary (strict >); custom salience_floor; daily_batch and milestone examples; all 93 test_memory tests green
- `test_delete_expired` + 4 static checks (tests/test_database_phase11.py): stub filled in as real live-DB round-trip test (skipped without TEST_DATABASE_URL); 4 static signature checks always run

## Task Commits

1. **Task 1 RED** (test file): `c9bbea2` — `test(11-07): add failing tests for decay_predicate (MEM-07 decay sweep)`
2. **Task 1 GREEN** (implementation): `d3d06e6` — `feat(11-07): decay_predicate — expired low-salience selection (MEM-07 / D-08)`
3. **Task 2** (DB helper + sweep): `40049c9` — `feat(11-07): delete_expired_memories + MemoryService.sweep() — daily decay helper`
4. **Task 3** (daily loop): `af8d9e5` — `feat(11-07): memory_sweep daily @tasks.loop — MEM-07 hygiene backstop`

## Files Created/Modified

- `models/memory.py` — decay_predicate + updated module docstring (~55 lines added)
- `config.py` — MEMORY_DECAY_SALIENCE_FLOOR=0.5 (1 line)
- `database.py` — delete_expired_memories (~50 lines added)
- `services/memory.py` — MemoryService.sweep() (~50 lines added)
- `bot.py` — memory_sweep task + before_loop/error + start guard + cleanup-list (~38 lines added)
- `tests/test_memory.py` — TestDecayPredicate 8 tests + 3 registration checks + module docstring update (~109 lines added)
- `tests/test_database_phase11.py` — test_delete_expired stub filled + 4 static checks (~70 lines added)

## Decisions Made

- **decay_predicate default salience_floor=0.5 as literal**: pure function cannot import config; MEMORY_DECAY_SALIENCE_FLOOR=0.5 in config for DB layer — same value, single conceptual source, no circular dep
- **delete_expired_memories includes salience < $2**: T-11-07b over-broad-delete mitigation requires both clauses; mirrors decay_predicate behavior precisely
- **memory_sweep at 02:30 UTC**: avoids thundering-herd with cache_cleanup (hourly), ytdlp_update (04:00 UTC), memory_distill_batch (03:00 UTC)
- **sweep() returns int (count)**: useful for logging and future instrumentation; 0 on error preserves fire-and-forget safety

## Deviations from Plan

### Auto-added Missing Critical Functionality

**1. [Rule 2 - Auto-add] Added MEMORY_DECAY_SALIENCE_FLOOR to config.py**
- **Found during:** Task 2 implementation of delete_expired_memories
- **Issue:** T-11-07b requires "delete is bounded by expires_at + low-salience clause"; needed a named constant for the DB salience threshold to match decay_predicate's default floor
- **Fix:** Added `MEMORY_DECAY_SALIENCE_FLOOR = 0.5` to config.py; used by `delete_expired_memories` as `$2` parameter; decay_predicate uses the same value (0.5) as its literal default
- **Files modified:** `config.py`
- **Commit:** `40049c9`

## Threat Mitigations Applied (from threat_model)

| Threat ID | Mitigation | Where |
|-----------|-----------|-------|
| T-11-07a | Daily sweep deletes expired low-salience rows; pairs with 11-04 write-time cap (Pitfall 13/14) | `bot.py:memory_sweep`, `services/memory.py:sweep`, `database.py:delete_expired_memories` |
| T-11-07b | decay_predicate retains high-salience/recent facts; DELETE bounded by expires_at < $1 AND salience < $2 (two parameterized conditions) — no string interpolation | `models/memory.py:decay_predicate`, `database.py:delete_expired_memories` |
| T-11-07c | sweep() swallows all exceptions → returns 0; .error → _post_loop_error; before_loop wait_until_ready | `services/memory.py:sweep`, `bot.py:before_memory_sweep/on_memory_sweep_error` |

## Known Stubs

None — all three tasks fully implemented. Phase 11 (RAG Long-Term Memory) is now complete: write-time cap (11-04) + decay sweep (11-07) together bound the store permanently.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes beyond what was planned. The only new Neon surface is the daily DELETE in `delete_expired_memories`, which is bounded by two parameterized clauses and covered by T-11-07b in the plan's threat model.

## Self-Check: PASSED
