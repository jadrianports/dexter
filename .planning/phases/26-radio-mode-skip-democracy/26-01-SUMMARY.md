---
phase: 26-radio-mode-skip-democracy
plan: 01
subsystem: music
tags: [radio, dj-01, pure-logic, tdd, gemini-prompt, music-queue]

# Dependency graph
requires:
  - phase: 14-smarter-music-brain
    provides: "build_recommendation_prompt's recently_skipped/positive_taste optional-kwarg pattern (Pattern 1), AUTO_QUEUE_SONGS_PER_ROUND"
  - phase: 16-proactive-memory-callbacks
    provides: "logic/proactive.py as the exact pure-gate module template (docstring, keyword-only, cheapest-gate-first)"
provides:
  - "logic/radio.py — pure, mock-free, keyword-only refill-gate seam (should_refill_radio, is_already_played, has_room_for_refill)"
  - "MusicQueue.radio_armed / radio_seed / radio_played in-memory state + arm_radio()/disarm_radio()/set_loop_mode() methods"
  - "clear() now disarms radio for free at all four existing teardown sites"
  - "build_recommendation_prompt(seed=, already_played=) optional kwargs, byte-identical when unset"
  - "RADIO_LOOKAHEAD_DEPTH / RADIO_ALREADY_PLAYED_HINT_CAP config knobs"
affects: [26-03-radio-glue, 26-05-radio-command, 27-crossfade-playback]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure decision seam (logic/radio.py) cloned from logic/proactive.py's template: no discord/asyncio/random/datetime, keyword-only params, cheapest-gate-first ordering, config defaults as kwargs"
    - "Playback-state-not-preference discipline: radio state resets via clear() (like loop_mode), unlike auto_lyrics which deliberately survives clear()"
    - "One-choke-point mutual exclusion: set_loop_mode() is the single path both /loop and the loop button must route through to enforce D-11"

key-files:
  created:
    - logic/radio.py
    - tests/test_radio_logic.py
  modified:
    - config.py
    - models/queue.py
    - personality/prompts.py
    - tests/test_prompts.py
    - tests/test_hosting_drift_guard.py

key-decisions:
  - "A3: radio armed-state lives on MusicQueue, clear() disarms it — covers all four existing teardown sites for free, zero bot.py changes needed this plan"
  - "radio_played is dict[str, str] (video_id -> display string), one field serving both the D-03 hard-filter membership check and the prompt hint"
  - "No played-set cap: the armed-radio session lifetime IS the bound (D-08); only the prompt HINT is capped (RADIO_ALREADY_PLAYED_HINT_CAP=25), never the hard filter"
  - "should_refill_radio includes a free humans_present gate (already computed by _on_track_end for decide_on_track_end) to avoid burning the shared 15 RPM budget refilling an empty room (T-26-02)"

requirements-completed: [DJ-01]

# Metrics
duration: 45min
completed: 2026-07-16
---

# Phase 26 Plan 01: Radio Decision + State Core Summary

**Pure `logic/radio.py` refill-gate seam, in-memory `MusicQueue` radio armed-state with a D-11 loop-mutual-exclusion choke point, and two optional `build_recommendation_prompt` kwargs — all mock-free tested, zero Discord glue yet.**

## Performance

- **Duration:** ~45 min (including reconciliation of a prior executor's uncommitted partial work and a mid-flight test-suite regression fix)
- **Tasks:** 3 completed
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments

- `logic/radio.py`: three pure, keyword-only functions (`should_refill_radio`, `is_already_played`, `has_room_for_refill`) locking every DJ-01 branch (SC-2 disarm lock, D-10 lookahead trigger, T-26-02 empty-room budget guard, D-03 hard post-filter, queue-cap guard) — 48 mock-free tests, zero Discord/asyncio/random/datetime imports
- `MusicQueue` gains `radio_armed`/`radio_seed`/`radio_played` in-memory state plus `arm_radio()`, `disarm_radio()`, `set_loop_mode()` — `clear()` now disarms radio for free, covering all four existing teardown sites (`/stop`, the stop button, `idle_check`, reconnect-failure) with zero `bot.py` changes
- `build_recommendation_prompt` gains `seed=` (D-02 anchor) and `already_played=` (D-03 prompt hint) optional kwargs, byte-identical to today's output when both are unset or falsy-empty
- Reconciled and verified a prior executor's uncommitted partial work (`logic/radio.py`, the `config.py` Phase 26 block) against the plan spec before building on top of it — both were correct and required no rewrite, only the missing test file

## Task Commits

Each task was committed atomically:

1. **Task 1: Pure radio refill-gate seam + config knobs** - `e05d5e3` (feat)
2. **Task 2: Radio armed-state + session played-set on MusicQueue** - `43017a6` (feat)
3. **Task 3: D-02 seed anchor + D-03 already-played hint on build_recommendation_prompt** - `503e497` (feat)

**Deviation fix (Rule 3):** `83bd787` (fix — Phase 24 hosting drift-guard allowlist re-derivation, see Deviations below)

_Note: Task 1's `logic/radio.py` and `config.py` content pre-existed uncommitted from a prior executor that died mid-task; this session verified it against the plan spec (correct, unchanged) before adding the test file and committing._

## Files Created/Modified

- `logic/radio.py` - Pure DJ-01 refill-gate seam: `should_refill_radio` (armed/humans/lookahead gates), `is_already_played` (D-03 hard filter), `has_room_for_refill` (queue-cap guard)
- `tests/test_radio_logic.py` - Mock-free tests: `TestShouldRefillRadio`, `TestIsAlreadyPlayed`, `TestHasRoomForRefill` (Task 1), `TestRadioDisarm`, `TestRadioLoopExclusion` (Task 2) — 48 tests total
- `config.py` - `RADIO_LOOKAHEAD_DEPTH = 2` (D-10), `RADIO_ALREADY_PLAYED_HINT_CAP = 25` (D-03), appended after the Phase 22 invite block
- `models/queue.py` - `radio_armed`/`radio_seed`/`radio_played` fields, `arm_radio()`/`disarm_radio()`/`set_loop_mode()` methods, `clear()` now calls `disarm_radio()`
- `personality/prompts.py` - `build_recommendation_prompt(seed=None, already_played=None)` — two new keyword-only kwargs, seed anchor concatenated last
- `tests/test_prompts.py` - `TestBuildRecommendationPromptPhase26Kwargs`: byte-identical regression lock + content assertions
- `tests/test_hosting_drift_guard.py` - `RENDER_ALLOWLIST` entries re-derived for `personality/prompts.py` and `tests/test_prompts.py` after Task 3's docstring edits shifted line numbers and added new legitimate "renders" occurrences

## Decisions Made

- Followed the plan's `<planner_decisions>` (A2/A3/D-08) exactly — radio armed-state lives on `MusicQueue` and is reset by `clear()`, not treated as a server preference like `auto_lyrics`
- `has_room_for_refill`'s "exactly-at-cap" boundary tested as `True` (inclusive `<=`), matching the plan's own return-expression spec (`queue_size + batch_size <= cap`) rather than a looser natural-language reading in the task's boundary-test prose — the concrete formula and the already-implemented, verified code took precedence
- Test method names in `tests/test_radio_logic.py` deliberately embed their `-k` selector substring literally (e.g. `test_should_refill_...`, `test_played_set_...`) since pytest's `-k` does plain substring matching with no underscore/casing normalization between `ShouldRefillRadio` and `should_refill`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Re-derived Phase 24 hosting drift-guard allowlist after Task 3's docstring edit**
- **Found during:** Task 3 (full-suite verification)
- **Issue:** `build_recommendation_prompt`'s new `seed`/`already_played` docstring text used the word "renders" (matching the existing `recently_skipped`/`positive_taste` docstring convention), and shifted the line numbers of pre-existing "renders" occurrences in `personality/prompts.py`. Both tripped `tests/test_hosting_drift_guard.py::test_render_hits_are_all_allowlisted` (Phase 24's hardcoded `RENDER_ALLOWLIST` of `(file, line)` pairs), a test entirely outside this plan's `files_modified` list.
- **Fix:** Re-derived the affected `RENDER_ALLOWLIST` entries via `git grep -niE '\brender[a-z]*\b'` on the two touched files, per the guard's own stated derivation method — no wording changed anywhere, only the allowlist's line numbers/additions.
- **Files modified:** `tests/test_hosting_drift_guard.py`
- **Verification:** `pytest tests/test_hosting_drift_guard.py -x` green; full suite subsequently green (1082 passed / 129 skipped / 0 failed)
- **Committed in:** `83bd787`

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary to keep the full suite green; no scope creep — the fix touched only the allowlist data, not the guard's logic or wording of the docstrings it was reacting to.

## Issues Encountered

A prior executor died mid-Task-1 due to an API connection error, leaving `logic/radio.py` and a `config.py` Phase 26 block uncommitted on the working tree with zero commits. This session read both files first, verified them line-by-line against the plan's `<action>`/`<acceptance_criteria>` spec (module docstring, three keyword-only functions, config knob comments and values), found both correct and non-duplicated, then proceeded to build the missing test file and commit — per the resume-context instructions, no blind re-application or rewrite was needed.

## Next Phase Readiness

- `logic/radio.py`, `MusicQueue` radio state, and the two prompt kwargs are all in place and locked by tests — plans 26-03/26-05 (radio Discord glue + `/radio` command) can wire directly against this seam with no further pure-logic work needed
- `26-02`/`26-04` (skip democracy, DJ-02) are independent of this plan and unblocked
- No blockers; full suite green at HEAD

---
*Phase: 26-radio-mode-skip-democracy*
*Completed: 2026-07-16*

## Self-Check: PASSED

- FOUND: logic/radio.py
- FOUND: tests/test_radio_logic.py
- FOUND: .planning/phases/26-radio-mode-skip-democracy/26-01-SUMMARY.md
- FOUND: e05d5e3 (Task 1 commit)
- FOUND: 43017a6 (Task 2 commit)
- FOUND: 503e497 (Task 3 commit)
- FOUND: 83bd787 (deviation fix commit)
- FOUND: c0309c1 (this summary's own commit)
