---
phase: 15-rag-reach
plan: 02
subsystem: ai
tags: [discord, gemini, rag, memory, cadence-gate, pytest]

# Dependency graph
requires:
  - phase: 11-rag-long-term-memory
    provides: MemoryService.recall() + MEMORY_SIMILARITY_FLOOR/MEMORY_CALLBACK_CHANCE config, ambient recall pattern at four call sites
provides:
  - "/ask and /roast attempt memory recall on every invocation (D-01) instead of a 0.35 dice roll"
  - "Ambient roast surfaces (events.py, music.py) unchanged, still gated at MEMORY_CALLBACK_CHANCE"
  - "First regression test locking the four-site cadence-gate invariant"
affects: [16-proactive-memory-callbacks]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Explicit/opted-in commands always attempt recall; ambient/unprompted surfaces keep a random cadence gate — the split is by user-agency, not by call-site similarity"
    - "Source-inspection tests (inspect.getsource + substring assert) as a non-flaky regression lock for 'this code path must/must not contain X', paired with a behavioral test for the actual runtime effect"

key-files:
  created:
    - tests/test_ambient_recall_cadence.py
  modified:
    - cogs/ai.py

key-decisions:
  - "Removed `import random` from cogs/ai.py entirely rather than leaving an unused import — its only two uses were the deleted gate conditionals (confirmed via grep before removal)"
  - "Updated the stale 'Cadence gate (D-04)' comments above both call sites to cite D-01 and explain MEMORY_SIMILARITY_FLOOR as the real relevance gate, rather than leaving comments that describe removed behavior"

patterns-established:
  - "Four-site enumeration as an explicit checklist (not find-and-replace) when a change touches near-identical code blocks with different intended outcomes — prevents accidental over-removal on the two sites meant to be left untouched"

requirements-completed: [RAG-01, RAG-02]

# Metrics
duration: 12min
completed: 2026-07-03
---

# Phase 15 Plan 02: Remove Explicit-Command Cadence Gate Summary

**`/ask` and `/roast` now attempt memory recall unconditionally (D-01), while ambient roast surfaces keep the 0.35 `MEMORY_CALLBACK_CHANCE` gate byte-for-byte — locked by a new four-site regression test.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-03T01:52Z (approx, first commit at 01:54:51+08:00)
- **Completed:** 2026-07-03T01:58:45+08:00
- **Tasks:** 2 completed
- **Files modified:** 2 (1 modified, 1 created)

## Accomplishments
- `/ask` and `/roast` in `cogs/ai.py` no longer gate memory recall behind `random.random() < config.MEMORY_CALLBACK_CHANCE` — both now attempt recall on every invocation, with `MEMORY_SIMILARITY_FLOOR` (0.70) serving as the real "is this relevant" gate downstream
- Recall scoping preserved exactly: `/ask` recalls the invoker (`str(interaction.user.id)`), `/roast` recalls the target (`str(target.id)`) — RAG-01's "reliable, not a dice roll" grounding without any scoping regression
- Ambient surfaces (`cogs/events.py:_generate_ambient_roast`, `cogs/music.py:_build_roast_line`) left byte-for-byte untouched — verified via `git diff` touching only `cogs/ai.py`
- New `tests/test_ambient_recall_cadence.py` closes a real coverage gap (15-RESEARCH.md Open Question 2 confirmed no prior test locked this invariant at any of the four call sites) with both a non-flaky source-inspection lock and a behavioral recall-scoping lock

## Task Commits

Each task was committed atomically:

1. **Task 1: Remove the recall cadence gate from /ask and /roast in cogs/ai.py** - `72d46b3` (feat)
2. **Task 2: Add tests/test_ambient_recall_cadence.py regression lock** - `772348f` (test)

**Plan metadata:** pending (this commit)

## Files Created/Modified
- `cogs/ai.py` - Removed the `MEMORY_CALLBACK_CHANCE` gate from `/ask` and `/roast`, un-indented the recall bodies, updated stale D-04 comments to cite D-01, removed the now-unused `import random`
- `tests/test_ambient_recall_cadence.py` - New regression suite: 3 source-inspection tests (ambient retains gate, explicit lost gate, no `random` attr on `cogs.ai`) + 2 behavioral tests (`/roast` recalls target-scoped, `/ask` recalls invoker-scoped, both unconditionally)

## Decisions Made
- Removed `import random` entirely (not left as dead import) after confirming via `grep -n "random\."` that its only two uses in `cogs/ai.py` were the deleted gate conditionals
- Rewrote the explanatory comments above both call sites (previously described the now-removed D-04 cadence gate) to cite D-01 and explain that `MEMORY_SIMILARITY_FLOOR` is the real "when relevant" gate — stale comments describing removed behavior are a correctness/readability hazard, not scope creep

## Deviations from Plan

None — plan executed exactly as written. Both call sites edited exactly as enumerated, ambient surfaces confirmed untouched via `git diff --stat`, test file matches the plan's specified coverage (source-inspection + behavioral locks, no `cogs.ai.random` patching).

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- RAG-01 and RAG-02 requirements now code-complete and test-locked; `MEMORY_SIMILARITY_FLOOR` (already-shipped Phase 11 mechanism) is confirmed as the sole relevance gate for explicit commands going forward
- Full verification suite green: `pytest tests/test_ambient_recall_cadence.py -x` (5 passed), `pytest tests/test_prompts.py -k memory_block -x` (3 passed, RAG-02 byte-identical guarantee unchanged), `pytest tests/test_roast_command.py -x` (4 passed), full suite `pytest tests/ -x` (773 passed, 106 skipped — live-DB tests)
- Ready for 15-03 (`/memory` cog view+forget) — no blockers. The ambient-surface cadence gate remains available as the pattern reference for Phase 16 proactive callbacks, which will introduce new unprompted surfaces subject to the same rare-callback design intent

---
*Phase: 15-rag-reach*
*Completed: 2026-07-03*

## Self-Check: PASSED

- FOUND: cogs/ai.py
- FOUND: tests/test_ambient_recall_cadence.py
- FOUND: .planning/phases/15-rag-reach/15-02-SUMMARY.md
- FOUND: commit 72d46b3
- FOUND: commit 772348f
