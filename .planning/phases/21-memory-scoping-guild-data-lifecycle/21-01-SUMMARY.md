---
phase: 21-memory-scoping-guild-data-lifecycle
plan: 01
subsystem: database
tags: [pgvector, asyncpg, rag-memory, guild-scoping, tdd]

# Dependency graph
requires:
  - phase: 20-owner-control-plane-rate-observability
    provides: guild_blocklist as its own table (D-01), so this phase's future purge work
      never needs a "except if blocked" carve-out
provides:
  - "database.search_memories() optional guild_id keyword filter, dynamic $N numbering"
  - "MemoryService.recall() keyword-only guild_scoped opt-in (default False = global)"
  - "MEM-05 structural regression lock on remember()'s k=1 dedup search call shape"
affects: [21-02, 21-03, 21-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Append-time dynamic $N SQL placeholder numbering (params.append then f\"${len(params)}\") replaces hardcoded literals when a second optional clause is added to an existing query builder"
    - "Keyword-only opt-in boolean (guild_scoped) forwards a kwarg via a conditionally-built dict + ** splat, so unopted callers see byte-identical kwarg sets to pre-change behavior"

key-files:
  created: []
  modified:
    - database.py
    - services/memory.py
    - tests/test_memory.py

key-decisions:
  - "kind is appended to params/clauses BEFORE guild_id so the pre-existing kind-only SQL shape keeps binding at literal $3 (no shift for existing callers/tests)"
  - "guild_id is forwarded to search_memories via a conditionally-populated kwargs dict (dict + ** splat) rather than an unconditional guild_id=X-if-Y-else-None kwarg, because the latter breaks every hand-written fake_search test double on the recall path that doesn't declare a guild_id parameter"
  - "remember()'s k=1 dedup search is explicitly left untouched — D-02 / MEM-05 constraint carried over from the Phase 13 CR-01 scar"

requirements-completed: [MEM-02, MEM-03, MEM-05]

# Metrics
duration: 20min
completed: 2026-07-14
---

# Phase 21 Plan 01: Memory Read-Path Guild Scoping Substrate Summary

**`database.search_memories()` gains a dynamic-numbered optional `guild_id` filter (D-01 grandfather OR-group) and `MemoryService.recall()` gains a keyword-only `guild_scoped` opt-in defaulting to global recall — zero call sites changed yet.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 3 completed
- **Files modified:** 2 (database.py, services/memory.py) + 1 test file (tests/test_memory.py)

## Accomplishments
- `database.search_memories` now supports 4 kind × guild_id combinations with correct dynamic `$N` binding; the no-clause and kind-only shapes are provably byte-identical to pre-Phase-21 (locked by the pre-existing `TestSearchMemoriesKindFilter`, unmodified).
- `MemoryService.recall()` gained `guild_scoped: bool = False` (keyword-only); the default path forwards NO `guild_id` kwarg to `database.search_memories` at all — MEM-02's "byte-identical for non-opting callers" guarantee is now enforced at the call boundary, not just in prose.
- `remember()`'s k=1 dedup search (the Phase 13 CR-01 scarred path) is structurally proven unreachable by the new parameter via a strict-signature test double that has no `guild_id`/`kind`/`**kwargs` escape hatch.

## Task Commits

Each task was committed atomically:

1. **Task 1: search_memories gains the optional guild clause with dynamic $N numbering (MEM-03 / D-01)** - `fd144fc` (feat)
2. **Task 2: MemoryService.recall gains the keyword-only guild_scoped opt-in (MEM-02 / D-02)** - `c318beb` (feat)
3. **Task 3: MEM-05 regression lock — remember()'s dedup search call shape is byte-identical** - `aea2a1e` (test)

**Plan metadata:** (this commit) — docs: complete plan

## Files Created/Modified
- `database.py` - `search_memories` gains keyword-only `guild_id: str | None = None`; hardcoded `$3` kind clause replaced by append-time dynamic `$N` numbering (`kind` appended before `guild_id`); guild clause emits `AND (guild_id = $N OR guild_id IS NULL)` only when set.
- `services/memory.py` - `recall()` gains `guild_scoped: bool = False` keyword-only param; `guild_id` forwarded to `search_memories` via a conditionally-populated kwargs dict, only when `guild_scoped` is truthy; stale "reserved for future per-guild memory scoping" docstring rewritten; `remember()` body untouched.
- `tests/test_memory.py` - Added `TestSearchMemoriesGuildFilter` (4 tests, all kind × guild combos), `TestRecallGuildScoped` (4 tests: default-omits, opt-in-forwards, kind+guild-scoped-both-forward, signature is KEYWORD_ONLY/default-False), `TestRememberDedupCallShapeUnchanged` (4 tests: strict-signature call-shape lock, source-level `guild_scoped`/`guild_id=` absence guard, D-05 taste_episode-refreshes / daily_batch-does-not-refresh regression). All pre-existing test classes (`TestSearchMemoriesKindFilter`, `TestRecallKindParam`, `TestRememberService`, and the entirety of `tests/test_memory_taste.py`) verified unmodified (`git diff --stat` empty for the latter).

## Decisions Made
- `kind` is appended to `params`/`clauses` before `guild_id` in `search_memories` so the pre-existing kind-only SQL shape (and its literal-`$3`-asserting test) stays byte-identical — order in the function body is load-bearing, not incidental.
- `recall()` forwards `guild_id` via a small conditionally-built kwargs dict splatted into the `search_memories` call, rather than the RESEARCH/PATTERNS sample's `guild_id=guild_id if guild_scoped else None` (which was flagged in the plan itself as WRONG — it unconditionally passes the keyword and breaks all four pre-existing hand-written `fake_search` test doubles on the recall path that don't declare a `guild_id` parameter).
- `remember()`'s k=1 dedup `search_memories` call is explicitly untouched — this plan is read-path only (D-02); Task 3 formalizes that constraint as a structural test rather than just a code-review note.

## Deviations from Plan

None - plan executed exactly as written. The plan's own `<action>` block for Task 2 explicitly flagged and pre-empted the one hazard (the unconditional-`guild_id`-kwarg anti-pattern from RESEARCH/PATTERNS samples), so no in-flight deviation was needed — the correct implementation was followed from the start.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The exact kwarg names `guild_id=` (on `search_memories`) and `guild_scoped=` (on `recall`) are now the artifacts plan 21-03 (call-site wiring: `/roast`, ambient roast, proactive callback, `_build_roast_line`, auto-queue taste-blend) depends on and must not rename.
- `/ask` (the one call site that must stay global per MEM-02) requires zero code change — its existing `recall()` call already produces the byte-identical default behavior this plan locked in.
- Verification commands green: `pytest tests/test_memory.py tests/test_memory_taste.py -x` (121 passed), the phase quick command `pytest tests/test_memory.py tests/test_ambient_recall_cadence.py tests/test_autoqueue_wiring.py tests/test_memory_taste.py -x` (141 passed), `ruff check database.py services/memory.py tests/test_memory.py` (clean).
- No blockers for plan 21-02 (the `purge_guild_data` write-path work) or 21-03 (call-site wiring).

---
*Phase: 21-memory-scoping-guild-data-lifecycle*
*Completed: 2026-07-14*

## Self-Check: PASSED

- FOUND: database.py
- FOUND: services/memory.py
- FOUND: tests/test_memory.py
- FOUND: .planning/phases/21-memory-scoping-guild-data-lifecycle/21-01-SUMMARY.md
- FOUND commit: fd144fc (Task 1)
- FOUND commit: c318beb (Task 2)
- FOUND commit: aea2a1e (Task 3)
