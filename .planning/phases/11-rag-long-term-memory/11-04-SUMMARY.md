---
phase: 11-rag-long-term-memory
plan: "04"
subsystem: memory-write
tags: [rag, embeddings, pgvector, dedup, eviction, salience, tdd, asyncpg, write-path]

# Dependency graph
requires:
  - phase: 11-03
    provides: MemoryService.recall() + GeminiService.embed() + search_memories + bump_surfaced + MemoryFact dataclass
  - phase: 11-02
    provides: MEMORY_DEDUP_THRESHOLD=0.92 (spike-validated), MEMORY_MAX_PER_USER=150, MEMORY_DECAY_DAYS=90
provides:
  - models/memory.py: dedup_decision + compute_salience + choose_eviction pure functions
  - config.py: MEMORY_SALIENCE_BASE_WEIGHTS ordinal event-kind ladder
  - database.py: insert_memory / bump_memory_hit / count_user_memories / get_user_memories_for_eviction / evict_lowest_salience
  - services/memory.py: MemoryService.remember() complete write pipeline
  - tests/test_memory.py: 27 new tests (22 write-logic + 5 remember service)
  - tests/test_database_phase11.py: 11 static checks + 4 live-DB round-trip tests (skipped without live DB)
affects:
  - 11-05 (distillation + triggers that call remember())
  - 11-07 (sweep / expiry — uses evict_lowest_salience pattern)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TDD commit sequence: RED test commit (63cab81) before GREEN implementation (9d6fb03) — write-logic tests skip during RED via importlib guard, pass after GREEN"
    - "Import guard pattern for pure-logic functions: try/except ImportError + pytest.mark.skipif — allows test file to collect cleanly at all commit boundaries"
    - "choose_eviction sort key: (salience ASC, created_at ASC, hit_count ASC) — low-salience-old-cold ages out first (D-08)"
    - "dedup_decision uses >= threshold (inclusive boundary): at exactly 0.92 treats as near-dup; consistent with apply_floor >= convention"
    - "compute_salience: additive (base + bump), clamped to [0.0, 1.0]; ordinal sane not finely-tuned (RESEARCH Q3/A5)"
    - "remember() outer try/except swallows all exceptions — fire-and-forget from cogs via asyncio.create_task must never raise (T-11-04d)"
    - "evict_lowest_salience WHERE user_id=$1 AND id=ANY($2) double-scope: cross-user ids in eviction list are silently ignored (T-11-04c)"
    - "get_user_memories_for_eviction: ORDER BY salience ASC, created_at ASC, hit_count ASC in DB — matches choose_eviction ranking"

key-files:
  created:
    - tests/test_database_phase11.py (expanded from stub to full test file — 11 static + 4 live-DB + 1 future stub)
  modified:
    - models/memory.py (added dedup_decision, compute_salience, choose_eviction + updated module docstring)
    - config.py (added MEMORY_SALIENCE_BASE_WEIGHTS dict)
    - database.py (added insert_memory, bump_memory_hit, count_user_memories, get_user_memories_for_eviction, evict_lowest_salience)
    - services/memory.py (added remember() + timedelta import + dedup_decision/choose_eviction imports)
    - tests/test_memory.py (added TestDedupDecision, TestComputeSalience, TestChooseEviction, TestRememberService — 27 tests)

key-decisions:
  - "dedup_decision uses >= (inclusive boundary at threshold=0.92): consistent with apply_floor's >= convention; near-dup at exact threshold treated as bump not insert"
  - "MEMORY_SALIENCE_BASE_WEIGHTS: milestone=1.0, late_night=0.7, repeat_song=0.5, auto_queue_ignored=0.4, daily_batch=0.2 — ordinal only, not finely tuned (RESEARCH Q3/A5)"
  - "bump_memory_hit adds salience nudge of +0.02 clamped to 1.0: frequently-observed facts rank above cold facts during eviction (D-07)"
  - "get_user_memories_for_eviction added as Rule 2 auto-add: Task 3 remember() needs to fetch all user memories for eviction but no fetch helper was listed in Task 2 artifacts — added alongside evict_lowest_salience as logically required"
  - "MemoryFact used for choose_eviction with similarity=0.0: avoids a second data type; similarity is unused by eviction ranking; consistent with the existing MemoryFact-as-pure-logic-input pattern"

# Metrics
duration: 14min
completed: 2026-06-29
---

# Phase 11 Plan 04: Write Path — Dedup, Salience, Cap Eviction Summary

**remember() that never inserts a near-duplicate, keeps each user bounded at MEMORY_MAX_PER_USER via salience-ranked eviction, and degrades silently on embed rate-limit**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-06-29T09:32:38Z
- **Completed:** 2026-06-29T09:47:11Z
- **Tasks:** 3 (Task 1 TDD, Task 2 auto, Task 3 auto)
- **Files modified:** 5 (models/memory.py modified, config.py modified, database.py modified, services/memory.py modified, tests/test_memory.py modified, tests/test_database_phase11.py expanded)

## Accomplishments

- `models/memory.py`: Added `dedup_decision`, `compute_salience`, `choose_eviction` — pure, deterministic, no I/O; all follow the clock-injectable seam convention from 11-03
- `config.py`: Added `MEMORY_SALIENCE_BASE_WEIGHTS` — ordinally-monotone dict (`milestone=1.0 > late_night=0.7 > repeat_song=0.5 > auto_queue_ignored=0.4 >= daily_batch=0.2`); annotated as ordinal-sane not finely-tuned (RESEARCH Q3/A5)
- `database.py`: Added `insert_memory` (RETURNING id), `bump_memory_hit` (hit_count+1, last_seen_at, salience nudge), `count_user_memories`, `get_user_memories_for_eviction`, `evict_lowest_salience` (double-scoped WHERE user_id=$1 AND id=ANY($2))
- `services/memory.py`: `MemoryService.remember()` — full write pipeline: embed at priority=2, dedup check, bump or insert, count, evict if over cap; outer try/except swallows all errors (fire-and-forget safe)
- `tests/test_memory.py`: 27 new tests across TestDedupDecision (6), TestComputeSalience (8), TestChooseEviction (8), TestRememberService (5); all 58 total tests green
- `tests/test_database_phase11.py`: Expanded from 4 stubs to 11 static signature checks + 4 live-DB round-trip tests (skipped without TEST_DATABASE_URL) + 1 future stub for sweep (11-07)

## Task Commits

Each task was committed atomically:

1. **Task 1 RED** (test file): `63cab81` — `test(11-04): add failing tests for dedup_decision + compute_salience + choose_eviction + remember`
2. **Task 1 GREEN** (implementation): `9d6fb03` — `feat(11-04): pure write-logic seam — dedup_decision + compute_salience + choose_eviction`
3. **Task 2** (DB helpers): `f877199` — `feat(11-04): DB write helpers — insert_memory / bump_memory_hit / count / evict`
4. **Task 3** (remember pipeline): `9bc21fe` — `feat(11-04): MemoryService.remember() — embed, dedup, insert, cap eviction`

## Files Created/Modified

- `models/memory.py` — added ~90 lines (dedup_decision, compute_salience, choose_eviction + updated docstring)
- `config.py` — added 9 lines (MEMORY_SALIENCE_BASE_WEIGHTS dict with inline comments)
- `database.py` — added ~165 lines (5 new async helpers, all $N parameterized, user-scoped)
- `services/memory.py` — added ~125 lines (remember() method + import updates)
- `tests/test_memory.py` — 27 new tests (~205 lines added); 58 total, all green
- `tests/test_database_phase11.py` — rewritten from 4 stubs to full file (~175 lines); 11+4 tests

## Decisions Made

- **dedup_decision uses >= threshold**: inclusive boundary consistent with apply_floor's `>=` convention; near-dup at exactly 0.92 treated as bump (safer than treating as insert)
- **MEMORY_SALIENCE_BASE_WEIGHTS ordinal values**: milestone=1.0, late_night=0.7, repeat_song=0.5, auto_queue_ignored=0.4, daily_batch=0.2; annotated as ordinal-sane not finely-tuned per RESEARCH Q3/A5 guidance
- **bump_memory_hit salience nudge**: `LEAST(1.0, salience + 0.02)` — small uplift rewards high-frequency observations, improves eviction ranking for cold vs hot facts (D-07)
- **get_user_memories_for_eviction added**: required by Task 3 remember() but absent from Task 2 plan artifacts — added as Rule 2 (missing critical functionality for the eviction to work)
- **MemoryFact for choose_eviction input**: similarity=0.0 for eviction candidates avoids a second data type; eviction ranking only uses salience/created_at/hit_count (similarity unused)

## Deviations from Plan

### Auto-added Missing Critical Functionality

**1. [Rule 2 - Auto-add] Added get_user_memories_for_eviction to database.py**
- **Found during:** Task 3 implementation of MemoryService.remember()
- **Issue:** Task 3 action specifies "fetch the user's facts" for eviction but no DB fetch helper was listed in Task 2's artifact list — only insert/bump/count/evict_lowest_salience were listed
- **Fix:** Added `get_user_memories_for_eviction(pool, *, user_id)` returning all memory rows (id, fact, salience, hit_count, created_at, last_seen_at, last_surfaced_at, surface_count) ordered by eviction priority (salience ASC, created_at ASC)
- **Files modified:** `database.py`
- **Commit:** `f877199`

## Threat Mitigations Applied (from threat_model)

| Threat ID | Mitigation | Where |
|-----------|-----------|-------|
| T-11-04a | count_user_memories after every insert; choose_eviction + evict_lowest_salience fires when count > MEMORY_MAX_PER_USER (Pitfall 13/14) | `services/memory.py:remember` |
| T-11-04b | $N parameterized asyncpg — embedding passed as list[float] via pgvector codec; no SQL built from strings | `database.py` all helpers |
| T-11-04c | evict_lowest_salience: DELETE WHERE user_id=$1 AND id=ANY($2) — cross-user ids silently ignored | `database.py:evict_lowest_salience` |
| T-11-04d | embed at priority=2; GeminiRateLimitError caught → log debug → return; outer try/except swallows all exceptions | `services/memory.py:remember` |

## Known Stubs

None — all three tasks fully implemented. `MemoryService.sweep()` and `delete_expired_memories` are planned for 11-07 (not stubs affecting this plan's goal).

## Threat Flags

None — no new network endpoints, auth paths, or schema changes. All write paths go through $N-parameterized asyncpg helpers. The only new surface (Neon write on remember()) was already covered by the plan's threat model.

## Self-Check: PASSED
