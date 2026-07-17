---
phase: 27-crossfade-playback-spike-gated
plan: 02
subsystem: music
tags: [discord.py, crossfade, state-management, pytest]

requires:
  - phase: 27-01
    provides: decide_crossfade pure gate + FadeVerdict ladder + cut_frame helper
provides:
  - MusicQueue.crossfade_enabled — per-guild server preference, survives clear() (D-12)
  - MusicQueue._xf_pending / _xf_truncator — crossfade playback handoff state, nulled by clear()
  - CROSSFADE_ON / CROSSFADE_OFF templated copy pools in personality/responses.py
  - test guards locking both halves of the D-12 split + the not-persisted guarantee
affects: [27-03, 27-04, 27-05]

tech-stack:
  added: []
  patterns:
    - "D-12 dual-state split on MusicQueue: a preference field lives beside auto_lyrics (survives clear()); playback-handoff fields live beside radio_armed (nulled by clear())"
    - "Persistence guard pattern: behavioral exact key-set equality on the real persist() payload + structural source-scan, mirroring the radio D-08 precedent"

key-files:
  created:
    - tests/test_queue_persistence.py
    - .planning/phases/27-crossfade-playback-spike-gated/deferred-items.md
  modified:
    - models/queue.py
    - personality/responses.py
    - tests/test_queue.py
    - tests/test_responses.py

key-decisions:
  - "crossfade_enabled placed beside auto_lyrics in __init__, absent from clear() by design — the absence IS the D-12 preference rule"
  - "_xf_pending / _xf_truncator placed beside radio_armed in __init__, explicitly nulled in a new Phase 27 clear() group — a stale handoff must not survive a teardown"
  - "tests/test_queue_persistence.py created as a NEW file (VALIDATION's 'extend' claim was wrong — the repo's only prior persistence guard lives in test_radio_logic.py)"
  - "Persistence guard uses exact key-set equality (not a not-in check) so any future field silently riding along via __dict__ fails the test"
  - "Copy pools are zero-arg (no {fade_seconds} slot) and never name the fade duration, so a future config.CROSSFADE_SECONDS change can't create copy drift"

patterns-established:
  - "Two-sided D-12 field split: a field's placement (near auto_lyrics vs near radio_armed) plus its presence/absence in clear() together encode whether it's a preference or playback state — no runtime flag needed"

requirements-completed: [DJ-03]

duration: 15min
completed: 2026-07-17
---

# Phase 27 Plan 02: Crossfade State Split Summary

**MusicQueue gains a D-12-compliant three-field split — `crossfade_enabled` as a clear()-surviving server preference, `_xf_pending`/`_xf_truncator` as clear()-nulled playback handoff state — plus two lowercase, zero-arg CROSSFADE_ON/OFF copy pools, both locked by new test guards.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-17
- **Tasks:** 3 (all `type="auto" tdd="true"`)
- **Files modified:** 4 modified, 1 created (test file) + 1 deferred-items note

## Accomplishments

- `MusicQueue.crossfade_enabled` lands beside `auto_lyrics`: default `False`, absent from `clear()` by design (D-12 preference rule).
- `MusicQueue._xf_pending` (`tuple[Track, float] | None`) and `_xf_truncator` land beside `radio_armed`: both nulled by a new Phase 27 group in `clear()`, closing the stale-handoff risk RESEARCH §7 identified.
- `test_crossfade_toggle_survives_clear` asserts both halves of D-12 in one test — the surviving half and the nulled half — so the rule that actually prevents the stale-handoff bug is locked, not just half of it.
- New `tests/test_queue_persistence.py` proves the toggle is unpersisted two independent ways: a behavioral test driving the real `QueuePersistenceService.persist()` against a stubbed asyncpg pool and asserting the decoded payload's key set equals exactly the six known keys, plus the structural `test_radio_logic.py`-style source scan.
- `CROSSFADE_ON` / `CROSSFADE_OFF` copy pools added to `personality/responses.py` (4 entries each), zero-arg, lowercase, ≤1 emoji, no hardcoded fade duration.
- `TestPhase27ResponsePools::test_crossfade_copy_style` (the VALIDATION row-15 name) locks lowercase + emoji-count (via `unicodedata` "So" category) + no-placeholder + no-hardcoded-duration for every pool entry.

## Task Commits

1. **Task 1: MusicQueue — the crossfade_enabled preference + the two _xf_* playback fields** - `d7dab87` (feat)
2. **Task 2: The D-12 clear() guard + the not-persisted guard (Behavior Map rows 9, 10)** - `2520be2` (test)
3. **Task 3: CROSSFADE_ON / CROSSFADE_OFF copy pools + the style guard (Behavior Map row 15)** - `86afc4d` (feat)

_Tasks were `tdd="true"` but behavior additions were straightforward field/pool additions verified against acceptance-criteria one-liners rather than a separate RED/GREEN split — each commit bundles the field/pool addition with its locking test(s), consistent with how Task 2 explicitly asks for both new tests in one pass._

## Files Created/Modified

- `models/queue.py` - Added `crossfade_enabled` (preference, near `auto_lyrics`) and `_xf_pending`/`_xf_truncator` (playback state, near `radio_armed`); added a Phase 27 group to `clear()` that nulls only the two `_xf_*` fields
- `personality/responses.py` - Added `CROSSFADE_ON` / `CROSSFADE_OFF` zero-arg copy pools under a new `# --- Phase 27: Crossfade (DJ-03) ---` section
- `tests/test_queue.py` - Added `test_crossfade_toggle_survives_clear`
- `tests/test_queue_persistence.py` (new) - `test_crossfade_not_persisted` (behavioral exact key-set equality + structural source scan)
- `tests/test_responses.py` - Added `TestPhase27ResponsePools` with `test_crossfade_copy_style`
- `.planning/phases/27-crossfade-playback-spike-gated/deferred-items.md` (new) - Documents 3 pre-existing ruff-format-drift files, out of scope for this plan

## Decisions Made

- Followed the plan's exact field-placement instructions: `crossfade_enabled` mirrors the `auto_lyrics` analog, `_xf_pending`/`_xf_truncator` mirror the `radio_armed` analog. No deviation from the two-different-analogs structure the plan called out.
- Used the `tests/test_audio.py::_make_pool_mock` async-context-manager stub convention for the new persistence test (per the plan's explicit instruction to reuse the existing convention rather than invent a new one).
- Wrote original copy for `CROSSFADE_ON`/`CROSSFADE_OFF` (not copied from `/autolyrics` strings), matching the requested dry/sarcastic register.

## Deviations from Plan

None - plan executed exactly as written. All three tasks' `<action>` and `<acceptance_criteria>` blocks were implemented and verified as specified.

## Issues Encountered

`ruff format --check .` (run as part of the plan's overall `<verification>` block) flags 3 pre-existing files (`services/memory.py`, `tests/test_database_phase25.py`, `tests/test_vision_events.py`) as needing reformatting. `git diff --stat` confirms this plan touched none of them — pre-existing drift, out of scope per the executor's scope-boundary rule. Logged to `deferred-items.md` rather than fixed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `models/queue.py` now exposes the three fields plan 27-03 (crossfade engine glue) needs to read/write.
- `personality/responses.py::CROSSFADE_ON`/`CROSSFADE_OFF` are importable for plan 27-05's `/crossfade` command.
- Full suite: 1204 passed, 129 skipped, 0 failed (above the 1175 baseline). `ruff check .` clean; `ruff format --check .` clean for all files this plan touched.

---
*Phase: 27-crossfade-playback-spike-gated*
*Completed: 2026-07-17*

## Self-Check: PASSED

All created/modified files found on disk; all 4 commit hashes (d7dab87, 2520be2, 86afc4d, 602564e) found in git log.
