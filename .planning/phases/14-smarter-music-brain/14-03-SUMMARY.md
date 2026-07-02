---
phase: 14-smarter-music-brain
plan: 03
subsystem: music-brain
tags: [discord, auto-queue, gemini, taste-graph, rag-memory]

# Dependency graph
requires:
  - phase: 14-01
    provides: database.get_recently_skipped, kind-filtered search_memories/recall, Phase 14 config knobs
  - phase: 14-02
    provides: logic.autoqueue.is_recently_skipped_artist, logic.taste.select_positive_taste_context, build_recommendation_prompt recently_skipped=/positive_taste= kwargs
provides:
  - "cogs/ai.py::try_auto_queue wired with D-01 negative hint (recently-skipped titles/artists), D-03 positive hint (unattributed room-taste blend), and D-02 hard post-filter (independent second gate after validate_youtube_match)"
  - "tests/test_autoqueue_wiring.py — source-assertion regression suite locking the wiring shape and scar #2"
affects: [14-04-discover-command, 14-05-jam-suggest-command]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Degrade-to-empty DB/recall fetches inside the outer try/except of try_auto_queue — new hint sources never raise past the existing except GeminiRateLimitError/GeminiAPIError/Exception chain"
    - "Single voice-member enumeration computed once, reused at two call sites (positive-taste recall fan-out + auto_queue_ignored write) instead of recomputed"
    - "Independent second gate pattern: is_recently_skipped_artist runs strictly after validate_youtube_match passes, as a separate belt-and-suspenders check, never merged into the hallucination-guard function itself"

key-files:
  created:
    - tests/test_autoqueue_wiring.py
  modified:
    - cogs/ai.py

key-decisions:
  - "Recall anchor for the positive-taste blend is a fixed module-level string (_AUTO_QUEUE_TASTE_ANCHOR = \"music taste and listening preferences\") per RESEARCH.md OQ#3 — any stable anchor works since recall() is already scoped to user_id + kind=\"taste_episode\""
  - "Both Task 1 (D-01/D-03 wiring) and Task 2 (D-02 hard filter) were split into separate commits despite touching the same two files, by temporarily removing the Task 2 hunk before the first commit and re-applying it for the second — preserves the plan's one-task-one-commit contract even though both tasks share cogs/ai.py::try_auto_queue"

patterns-established:
  - "Wiring regression tests via inspect.getsource(...) rather than live Discord/Gemini/DB integration — matches the Phase 10-13 pure-logic-seam testing convention, extended here to controller-layer wiring assertions"

requirements-completed: [BRAIN-01]

# Metrics
duration: ~20min
completed: 2026-07-02
---

# Phase 14 Plan 3: Auto-Queue Taste-Aware Wiring Summary

**`try_auto_queue` now injects a guild-scoped "recently skipped" negative block and an unattributed "the room tends to like" positive block into the Gemini recommendation prompt, plus an independent hard filter that rejects recently-skipped artists even if they pass the hallucination guard — all byte-identical to today when both taste signals are empty.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 2 completed
- **Files modified:** 2 (1 source, 1 test)

## Accomplishments
- D-01: `try_auto_queue` fetches guild-scoped recently-skipped `(title, artist)` rows via `get_recently_skipped` (bounded by `AUTO_QUEUE_SKIP_LOOKBACK_DAYS`/`AUTO_QUEUE_SKIP_HINT_CAP`) and passes them as `recently_skipped=` to `build_recommendation_prompt`, degrading to `[]` on any failure
- D-03: for every non-bot in-voice member (the exact enumeration already used for the `auto_queue_ignored` write — computed once, reused, not recomputed), `memory_service.recall(..., kind="taste_episode")` results are blended via `select_positive_taste_context(cap=AUTO_QUEUE_POSITIVE_TASTE_CAP)` into an unattributed `positive_taste=` block
- D-02: inside the per-suggestion validation loop, after a candidate passes `validate_youtube_match` (unchanged), an independent second gate — `is_recently_skipped_artist(suggestion["artist"], skipped_artists)` — drops candidates whose artist matches a recently-skipped artist
- Both new prompt kwargs are keyword-only and omitted (`None`) when empty, so the prompt stays byte-identical to pre-Phase-14 output in the no-signal case (already covered by 14-02's `test_prompts.py` byte-identical assertions)
- Scar #2 (`should_start_playback` gated on `voice_client.is_playing()`/`is_paused()`, never `queue.is_playing`) is untouched — verified by a dedicated regression test
- New `tests/test_autoqueue_wiring.py` — 14 source-assertion + direct-behavioral tests locking the wiring shape, the single-reused-member-enumeration invariant, the D-02 gate ordering, and the scar #2 guard

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire the negative + positive taste hints into try_auto_queue (D-01/D-03)** - `7716675` (feat)
2. **Task 2: Add the D-02 hard post-filter to the per-suggestion validation loop** - `91228bb` (feat)

## Files Created/Modified
- `cogs/ai.py` - imports `get_recently_skipped`, `is_recently_skipped_artist`, `select_positive_taste_context`, `datetime`/`timedelta`/`timezone`; adds module-level `_AUTO_QUEUE_TASTE_ANCHOR`; extends `try_auto_queue` with the D-01 negative-hint fetch, the D-03 positive-hint recall/blend (reusing the single voice-member enumeration), the extended `build_recommendation_prompt` call, and the D-02 hard filter in the per-suggestion loop
- `tests/test_autoqueue_wiring.py` - new source-assertion regression module: `TestNegativeAndPositiveHintWiring` (7 tests), `TestHardPostFilterWiring` (4 tests), `TestScarTwoUntouched` (2 tests)

## Decisions Made
- Chose a fixed module-level anchor string for the positive-taste recall query text (`"music taste and listening preferences"`) — RESEARCH.md OQ#3 left this to implementer discretion since `recall()`'s ANN scoping is by `user_id` + `kind`, not by anchor-text specificity.
- Split the plan's two tasks into two commits despite both touching `cogs/ai.py`/`tests/test_autoqueue_wiring.py`, by staging Task 1's hunk first (temporarily holding back the Task 2 D-02 filter block and its test class), committing, then re-applying and committing Task 2 — preserves per-task atomic commit history as required by the executor's task_commit_protocol.

## Deviations from Plan

None - plan executed exactly as written. Both tasks matched the PATTERNS.md-specified insertion points and code shapes exactly (negative/positive hint wiring point immediately before the `build_recommendation_prompt` call; D-02 filter immediately after the `validated is None` fall-through branch).

## Issues Encountered

None. The single wrinkle was purely mechanical: writing both tasks' code in one pass (since they're adjacent edits to the same function) then re-splitting them into two commits by temporarily reverting the Task 2 hunk before the first commit — not a plan deviation, just a commit-sequencing detail to preserve the one-task-one-commit contract.

## Verification

```
python -m pytest tests/test_autoqueue_wiring.py -q
# 10 passed (Task 1 checkpoint)

python -m pytest tests/test_autoqueue_wiring.py tests/test_autoqueue_validate.py -q
# 41 passed (Task 2 checkpoint)

python -m pytest tests/ -q
# 705 passed, 105 skipped (full suite, no regression)
```

## User Setup Required

None - no external service configuration required. Zero new dependencies, zero new tables, zero new limiters — consumes only the Phase 14-01/14-02 substrate.

## Next Phase Readiness

- `try_auto_queue` is now taste-aware end to end (BRAIN-01 delivered); auto-queue suggestions degrade gracefully when `memory_service` is unavailable or recall/DB calls fail (never blocks the Gemini call or the fall-through loop).
- Plans 14-04 (`/discover`) and 14-05 (`/jam suggest`) can proceed independently — they consume the same 14-01/14-02 substrate but do not depend on this plan's `cogs/ai.py` changes.
- Manual live-Discord UAT (confirm a repeatedly-skipped artist stops reappearing in auto-queue rounds) remains deferred/parked per the plan's own verification note — consistent with the project's existing parked-live-UAT posture (Phases 03-06/09/11).
- No blockers.

---
*Phase: 14-smarter-music-brain*
*Completed: 2026-07-02*

## Self-Check: PASSED

All created/modified files confirmed present on disk (`cogs/ai.py`, `tests/test_autoqueue_wiring.py`);
both task commit hashes (`7716675`, `91228bb`) confirmed present in git log.
