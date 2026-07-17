---
phase: 27-crossfade-playback-spike-gated
plan: 01
subsystem: music
tags: [pure-logic-seam, tdd, crossfade, enum-verdict, config-knobs]

# Dependency graph
requires:
  - phase: 26-radio-mode-skip-democracy
    provides: "logic/radio.py and logic/skip_vote.py's keyword-only, cheapest-gate-first, enum-verdict seam convention this plan copies verbatim"
provides:
  - "logic/crossfade.py: FadeVerdict enum + decide_crossfade() + cut_frame() — the D-14 pure eligibility seam every later Phase 27 plan dispatches on"
  - "config.py: CROSSFADE_SECONDS=4 and CROSSFADE_MIN_TRACK_SECONDS=20 global knobs (D-12b/D-10b)"
  - "tests/test_crossfade_logic.py: 24 mock-free tests locking Behavior Map rows 1-8"
affects: [27-02, 27-03, "any future Phase 27 plan wiring services/audio.py or cogs/music.py to this seam"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure decision seam (logic/*.py): keyword-only signature, config defaults bound in the signature, cheapest-gate-first ladder, one numbered comment per rung naming its decision ID, enum verdict never a bare bool"

key-files:
  created:
    - logic/crossfade.py
    - tests/test_crossfade_logic.py
  modified:
    - config.py

key-decisions:
  - "Followed RESEARCH §3's validated signature and Narrow-go exclusions table row order verbatim for the 7-rung ladder (NO_TOGGLE -> NO_NEXT_TRACK -> LOOP_SINGLE -> FILTER_ACTIVE -> NOT_CACHED -> SEEKED -> TOO_SHORT -> FADE)"
  - "cut_frame floors at 0 (T-27-01) so a YouTube-metadata/real-file duration mismatch can never produce a negative -ss seek offset"

patterns-established:
  - "logic/crossfade.py mirrors logic/radio.py's four-part module docstring (purity contract / what caller passes in / what caller must still do / lock file) and logic/skip_vote.py's arithmetic-helper docstring convention (glue must never re-derive cut_frame's arithmetic itself)"

requirements-completed: [DJ-03]

# Metrics
duration: 25min
completed: 2026-07-17
---

# Phase 27 Plan 01: Crossfade Eligibility Seam Summary

**Pure `logic/crossfade.py` seam (FadeVerdict enum + decide_crossfade + cut_frame) locked by 24 mock-free tests covering all 8 Behavior Map rows, plus two global config.py knobs.**

## Performance

- **Duration:** ~25 min
- **Tasks:** 3 completed
- **Files modified:** 3 (1 created config edit, 1 new module, 1 new test file)

## Accomplishments
- `logic/crossfade.py` exports `FadeVerdict` (8 members), `decide_crossfade()` (keyword-only, 7-rung cheapest-gate-first ladder), and `cut_frame()` (frame-index arithmetic floored at 0)
- Two global `config.py` knobs (`CROSSFADE_SECONDS=4`, `CROSSFADE_MIN_TRACK_SECONDS=20`) with decision-ID comments (D-12b/D-10b), no per-guild surface added
- 24 mock-free tests in `tests/test_crossfade_logic.py` lock every ladder rung, the D-11b loop-QUEUE-still-fades positive case, the `<=` duration-floor boundary, full precedence ordering, and `cut_frame`'s metadata-mismatch floor
- Full suite: 1199 passed, 0 failed (>= 1175 baseline required by plan)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the two global crossfade knobs to config.py** - `d4afd7c` (feat)
2. **Task 2: Create logic/crossfade.py — FadeVerdict + decide_crossfade + cut_frame** - `13aa5fb` (feat)
3. **Task 3: tests/test_crossfade_logic.py — mock-free lock for all 8 ladder behaviors** - `1854b8c` (test, also carries the Rule 1 config.py wording fix)

## Files Created/Modified
- `logic/crossfade.py` - The D-14 pure eligibility seam: `FadeVerdict` enum, `decide_crossfade()`, `cut_frame()`
- `config.py` - `CROSSFADE_SECONDS` and `CROSSFADE_MIN_TRACK_SECONDS` global knobs
- `tests/test_crossfade_logic.py` - 24 mock-free tests, one class per Behavior Map row

## Decisions Made
- Ladder rung order and `FadeVerdict` value strings copied verbatim from `27-RESEARCH.md` §3's validated signature and the "Narrow-go exclusions" table row order — no deviation from the researched shape.
- `decide_crossfade`'s duration-floor rung checks `outgoing_duration < min_track_seconds OR incoming_duration < min_track_seconds OR outgoing_duration <= fade_seconds * 2` per the plan's `<behavior>` spec, all three conditions collapsing to a single `TOO_SHORT` verdict.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Reworded a config.py comment that false-positived the hosting drift guard**
- **Found during:** Task 3 (running the full suite verification)
- **Issue:** Task 1's `CROSSFADE_SECONDS` comment used the phrase "spike render" — `tests/test_hosting_drift_guard.py`'s `RENDER_PATTERN` (a Phase 24 guard against re-introducing Render.com hosting references) matches `\brender[a-z]*\b` case-insensitively and flagged it as an un-allowlisted Render reference, even though the comment has nothing to do with the Render hosting platform.
- **Fix:** Reworded "the D-08 spike render demonstrated" to "the D-08 spike output demonstrated" — same meaning, no `render` token.
- **Files modified:** `config.py`
- **Verification:** `pytest tests/test_hosting_drift_guard.py -q` — 7 passed. Full suite re-run: 1199 passed, 0 failed.
- **Committed in:** `1854b8c` (part of Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Cosmetic wording fix only; no behavior or test-coverage change. No scope creep.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The pure eligibility seam (`FadeVerdict`, `decide_crossfade`, `cut_frame`) is ready for the next Phase 27 plan to wire into `services/audio.py` (`TruncatingSource`/`CrossfadeSource`) and `cogs/music.py`'s `_play_track`/`_on_track_end` integration points per RESEARCH §5.
- No blockers. Full suite green, ruff clean on all three modified/created files.

---
*Phase: 27-crossfade-playback-spike-gated*
*Completed: 2026-07-17*

## Self-Check: PASSED

All created files and commit hashes verified present:
- FOUND: logic/crossfade.py
- FOUND: tests/test_crossfade_logic.py
- FOUND: .planning/phases/27-crossfade-playback-spike-gated/27-01-SUMMARY.md
- FOUND: d4afd7c, 13aa5fb, 1854b8c
