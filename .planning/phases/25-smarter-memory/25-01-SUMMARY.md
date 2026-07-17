---
phase: 25-smarter-memory
plan: 01
subsystem: database
tags: [asyncpg, postgres, pgvector, rag-memory, decay-sweep]

# Dependency graph
requires:
  - phase: 13-semantic-music-memory
    provides: MEMORY_DECAY_DAYS_BY_KIND mapping + resolve_decay_days() kind→decay-days resolver
  - phase: 11-rag-long-term-memory
    provides: user_memories pgvector store, recall()/bump_surfaced()/refresh_memory_expiry()/delete_expired_memories()
provides:
  - database.reinforce_memory_expiry(pool, ids, expires_at) — batched, extend-only expiry UPDATE
  - services/memory.py::recall() step 7b — kind-grouped expiry reinforcement at the single recall chokepoint
  - tests/test_database_phase25.py — source-inspection + live-DB SC-1/SC-3 regression coverage
affects: [25-02-vision-memory, future-memory-phases]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Expiry-only reinforcement sibling helper (GREATEST-guarded, batched via ANY($1)) alongside a hard-overwrite single-id expiry primitive"
    - "Kind read from raw DB rows via a service-local dict + .get(), never threaded onto the pure dataclass"

key-files:
  created:
    - tests/test_database_phase25.py
  modified:
    - database.py
    - services/memory.py
    - tests/test_memory.py

key-decisions:
  - "Reinforcement is expiry-only (D-01) — recall() never mutates salience/hit_count/last_seen_at, keeping SC-3 structurally provable"
  - "New sibling DB helper (reinforce_memory_expiry) rather than folding into bump_surfaced or looping refresh_memory_expiry — per-kind-group values need per-call flexibility a single UPDATE can't express cleanly"
  - "kind threaded as service-local bookkeeping (dict built from raw rows) — MemoryFact and bump_surfaced stay byte-unchanged"

patterns-established:
  - "Pattern: batch expiry-only UPDATE via ANY($1) + GREATEST(expires_at, $2) for extend-only reinforcement — reusable for any future 'use it or lose it' durability mechanic"

requirements-completed: [MEM-06]

# Metrics
duration: 25min
completed: 2026-07-16
---

# Phase 25 Plan 01: MEM-06 Expiry Reinforcement Summary

**A surfaced memory's `expires_at` is pushed out (never shortened) at the single `recall()` chokepoint, grouped by each fact's own kind, without ever touching salience/hit_count/last_seen_at.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 3/3 completed
- **Files modified:** 3 (database.py, services/memory.py, tests/test_memory.py); 1 created (tests/test_database_phase25.py)

## Accomplishments
- `database.reinforce_memory_expiry(pool, ids, expires_at)` — a new, fully parameterized, extend-only (`GREATEST`) batched sibling to `refresh_memory_expiry`, following the `bump_surfaced` `ANY($1)` array-binding idiom.
- `MemoryService.recall()` step 7 extended: step 7a (`bump_surfaced`) stays byte-identical; new step 7b groups the surfaced top-k facts by resolved decay-days (`resolve_decay_days`, kind read via `row.get("kind")` from the raw DB rows) and calls the new helper once per distinct group (at most `MEMORY_INJECT_CAP`=3 groups).
- Regression coverage: a source-inspection test class that runs everywhere (no live DB needed), a mocked grouping/partition unit test, the required Pitfall-2 monkeypatch fix on the one pre-existing test that reaches step 7, and two live-DB tests (SC-1 sweep-ordering, SC-3 non-mutation byte-identical guard) gated on `TEST_DATABASE_URL`.
- Full suite green: 1035 passed, 126 skipped, 0 failed.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add database.reinforce_memory_expiry** - `1e0f8bb` (feat) — includes `tests/test_database_phase25.py` with `TestReinforceMemoryExpiryExists` **and** the two live-DB tests (`test_reinforced_fact_survives_sweep_unreinforced_does_not`, `test_recall_does_not_mutate_salience_or_hit_count`) that the plan assigned to Task 3 (see Deviations).
2. **Task 2: Wire recall() step 7b** - `e0837aa` (feat) — also includes the Pitfall-2 monkeypatch fix that the plan assigned to Task 3 (see Deviations).
3. **Task 3: SC-3 regression guard** - no new commit; its required content (Pitfall-2 fix + live-DB tests) was delivered in Tasks 1/2 above. This task's role was fulfilled by running its verification commands (all passing) and the full-suite gate.

**Plan metadata:** (this commit, docs)

## Files Created/Modified
- `database.py` - `reinforce_memory_expiry` added after `refresh_memory_expiry`, before `count_user_memories`; `bump_surfaced`/`refresh_memory_expiry` untouched
- `services/memory.py` - `recall()` step 7 split into unchanged 7a + new 7b (kind-grouped reinforcement)
- `tests/test_database_phase25.py` - new file: `TestReinforceMemoryExpiryExists` (always-run source-inspection) + two `skipif(_SKIP_LIVE)`-gated live-DB tests
- `tests/test_memory.py` - `TestRecallService` extended with `test_reinforces_expiry_grouped_by_kind`; `test_returns_capped_facts_when_some_clear_floor` monkeypatch block extended to stub `reinforce_memory_expiry`

## Decisions Made
- Followed the plan's/research's recommended shape exactly: new sibling helper (not folded into `bump_surfaced`, not a loop over `refresh_memory_expiry`), `GREATEST` extend-only safety net, kind threaded via a service-local dict never via `MemoryFact`.
- Reworded one phrase in the `reinforce_memory_expiry` docstring (avoided the literal word "interval") so the source-inspection test's `"interval" not in src` assertion checks the SQL body's actual absence of SQL-side date arithmetic rather than tripping on an English description of the anti-pattern in a comment.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Docstring wording collision with the "no `interval`" source-inspection assertion**
- **Found during:** Task 1 verification (`TestReinforceMemoryExpiryExists`)
- **Issue:** The `reinforce_memory_expiry` docstring's own explanatory comment ("never computed in SQL (e.g. `now() + interval`)") contained the literal substring `interval`, which the acceptance-criteria test asserts must NOT appear anywhere in the function's `inspect.getsource()` output — causing a false-positive test failure despite the SQL itself being correctly parameterized.
- **Fix:** Reworded the docstring line to avoid the literal word while preserving the same meaning ("never computed SQL-side, e.g. via a date-arithmetic expression").
- **Files modified:** database.py
- **Verification:** `pytest tests/test_database_phase25.py::TestReinforceMemoryExpiryExists -x -q` passes (5/5).
- **Committed in:** 1e0f8bb (Task 1 commit)

**2. [Rule N/A - Task-ordering, non-functional] Task 3's test content front-loaded into Tasks 1/2 commits**
- **Found during:** Writing `tests/test_database_phase25.py` in Task 1
- **Issue:** The plan structures the work as three atomic commits (Task 1: helper + existence test; Task 2: recall wiring + grouping test; Task 3: Pitfall-2 fix + live-DB SC-1/SC-3 tests). Because `tests/test_database_phase25.py` is a single new file and the live-DB tests share the same skip-guard scaffolding as the existence test, it was more natural to write the complete file once rather than editing it again in a later commit; similarly the Pitfall-2 monkeypatch fix is inseparable from the step-7b wiring change it's reacting to, so it was applied in the same commit as Task 2's `recall()` edit.
- **Impact:** All required content exists and is correctly attributed by task in this SUMMARY's Task Commits table; no acceptance criteria were skipped — every Task 1/2/3 verification command was run and passes. This is a documentation/attribution note, not a functional deviation.
- **Files modified:** tests/test_database_phase25.py (Task 1 commit), tests/test_memory.py (Task 2 commit)
- **Verification:** All three tasks' specified `<verify>` commands pass individually; full suite green.

---

**Total deviations:** 2 (1 auto-fixed bug, 1 task-ordering note)
**Impact on plan:** No scope creep; the docstring fix was a one-line correction required for the plan's own acceptance criterion to pass non-vacuously. The task-ordering note reflects commit-granularity choice, not a change in what was built.

## Issues Encountered
None beyond the docstring wording fix above.

## User Setup Required
None - no external service configuration required. The two live-DB tests (SC-1, SC-3) skip locally (no `TEST_DATABASE_URL` set) and run in CI's `pgvector/pgvector:pg16` service container.

## Next Phase Readiness
- MEM-06 is fully shipped: `bump_surfaced`, `refresh_memory_expiry`, and `models/memory.py` are all byte-unchanged (verified via `git diff`); `recall()`'s new step 7b is additive and idle-safe for every existing kind.
- Plan 25-02 (MEM-07, vision → RAG memory) can proceed independently — it reuses `distill_and_remember` unchanged and composes with this plan's reinforcement (a memorable `vision_roast` fact that keeps getting recalled will have its expiry reinforced by the exact mechanism shipped here).
- Full pytest suite green (1035 passed / 126 skipped / 0 failed) at HEAD `e0837aa`.

---
*Phase: 25-smarter-memory*
*Completed: 2026-07-16*

## Self-Check: PASSED

All created/modified files confirmed present (database.py, services/memory.py, tests/test_database_phase25.py, tests/test_memory.py, this SUMMARY.md). Both task commit hashes (1e0f8bb, e0837aa) confirmed present in git log.
