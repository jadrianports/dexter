---
phase: 14-smarter-music-brain
plan: 05
subsystem: music-brain
tags: [discord-ui-view, gemini, jam, confirm-first, validation-gate]

# Dependency graph
requires:
  - phase: 14-01
    provides: config.JAM_SUGGEST_CANDIDATE_COUNT knob
  - phase: 14-02
    provides: personality.prompts.build_jam_suggestion_prompt (D-06, parse_suggestions-compatible)
  - phase: 14-04
    provides: one-shot confirm-view pattern precedent (DiscoverQueueView — finite timeout, not setup_hook-registered)
provides:
  - "cogs/library.py::jam_suggest — /jam suggest <name> subcommand (BRAIN-03): seeds Gemini from the named jam's existing tracks, validates every suggestion against real YouTube results before ever offering it"
  - "cogs/library.py::JamSuggestConfirmView — one-shot propose-and-confirm discord.ui.View (D-07): shared jam snapshot mutated ONLY inside the Confirm callback"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Second application of the one-shot discord.ui.View confirm pattern (finite timeout, not setup_hook-registered) established by 14-04's DiscoverQueueView — same shape, different mutation target (jam snapshot append vs queue.add)"
    - "Cog-to-cog function reuse: cogs/library.py imports parse_suggestions directly from cogs/ai.py (one-way, no cycle) rather than duplicating the JSON-parsing logic"

key-files:
  created:
    - tests/test_jam_suggest.py
  modified:
    - cogs/library.py

key-decisions:
  - "Validated candidates collected in jam_suggest are lightweight (title/artist/url only, from async_search results) — full Track construction (duration_seconds, requested_by, thumbnail) happens inside the Confirm callback via async_extract, mirroring try_auto_queue's search-then-extract split rather than extracting all N candidates before the user has even seen them"
  - "Confirm callback defensively reloads the jam via get_jam before appending, guarding against a concurrent edit landing between the propose step and the confirm press"
  - "No new personality/responses.py pool added for the non-existent-jam / none-survive messages — followed the existing plain-ephemeral-string convention already used by jam_load/jam_delete rather than introducing a third response-pool pattern for this subcommand"
  - "Queueing the additions immediately was left as a note pointing to /jam load rather than a second button — D-07 explicitly leaves this optional, and a single Confirm/Cancel pair keeps the interaction to one unambiguous action"

patterns-established:
  - "/jam suggest is the second and final Phase 14 surface to use the one-shot confirm-view pattern (after /discover) — both now share the same finite-timeout, not-setup_hook-registered, message-ref-for-on_timeout shape"

requirements-completed: [BRAIN-03]

# Metrics
duration: 15min
completed: 2026-07-03
---

# Phase 14 Plan 5: /jam suggest Command Summary

**`/jam suggest <name>` seeds Gemini with a shared jam's existing tracks, validates every candidate against real YouTube search results before ever offering it, and writes to the shared snapshot only after explicit user confirmation.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 2 completed
- **Files modified:** 1 (cogs/library.py) + 1 created (tests/test_jam_suggest.py)

## Accomplishments
- Added `jam_suggest` to `LibraryCog` as a sibling of the existing `save`/`add`/`load`/`list`/`delete` subcommands: loads the named jam's EXISTING tracks via `get_jam` (a non-existent jam returns an in-character message, never a crash — D-06), seeds `build_jam_suggestion_prompt`, and parses the reply with `parse_suggestions` (reused directly from `cogs/ai.py`, one-way import, no cycle)
- EVERY parsed suggestion is re-validated against real `youtube_service.async_search` results via `validate_youtube_match` (reused verbatim — no second tokenizer, no difflib) before it can ever reach the user; a suggestion with no passing candidate is silently dropped (BRAIN-03 hard requirement)
- If nothing survives validation, Dex says so in character and the jam snapshot is left completely untouched — no `save_jam` call is reachable from `jam_suggest` itself under any path
- Added `JamSuggestConfirmView`, a one-shot `discord.ui.View` (finite timeout, never registered in `setup_hook`) with Confirm/Cancel buttons — the second application of the pattern 14-04's `DiscoverQueueView` established. On Confirm: defensively reloads the jam snapshot, extracts full track data for each validated candidate (duration cap enforced), appends to the existing snapshot (append semantics identical to `/jam add`), and writes via `save_jam`. On Cancel or timeout: buttons disabled, nothing written.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the /jam suggest subcommand core (seed -> generate -> validate)** - `97c00d3` (feat)
2. **Task 2: Add the propose-and-confirm view + snapshot append (D-07)** - `6eabb7a` (feat)

## Files Created/Modified
- `cogs/library.py` - Added `jam_suggest` subcommand method (guard sequence copied from `jam_add`, existing-jam load, prompt build, per-suggestion validation loop); added `JamSuggestConfirmView` class with `confirm_button`/`cancel_button`/`on_timeout`; added imports for `parse_suggestions` (from `cogs.ai`), `validate_youtube_match` (from `logic.autoqueue`), `build_jam_suggestion_prompt` (from `personality.prompts`)
- `tests/test_jam_suggest.py` - Source-assertion test suite (28 tests) mirroring the `tests/test_discover.py` `inspect.getsource` convention: seed/generate/validate source-grounding, both early-return guards (non-existent jam, none-survive) verified to return before any `save_jam(` call, validation-loop shape, one-shot view contract (finite timeout, not setup_hook-registered), Confirm/Cancel callback source assertions, and view-attached-only-on-survivors-path ordering

## Decisions Made
- Collected validated candidates as lightweight `{title, artist, url}` dicts during the search/validate step (Task 1), deferring the full `async_extract` (duration, thumbnail, video_id) to the Confirm callback (Task 2) — avoids extracting N candidates' full metadata before the user has even seen or confirmed them, and mirrors `try_auto_queue`'s own search-then-extract split.
- The Confirm callback reloads the jam via `get_jam` before appending (rather than reusing the `existing` snapshot captured at propose-time) — a defensive guard against a concurrent edit landing between the two steps.
- Followed the existing plain-ephemeral-string convention (used by `jam_load`/`jam_delete`) for the non-existent-jam and none-survive messages, rather than introducing a new `personality/responses.py` pool — kept the footprint minimal since these are guard messages, not the primary Gemini-flavored surface.
- The "optionally also queue them now" note from 14-PATTERNS.md was implemented as a one-line pointer to `/jam load` in the confirm success message rather than a second button — D-07 states this is optional, and a single Confirm/Cancel pair keeps the interaction unambiguous.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Reworded JamSuggestConfirmView's docstring to avoid tripping its own "not timeout=None" source assertion**
- **Found during:** Task 2 (writing the `test_view_uses_finite_timeout_not_none` test)
- **Issue:** The class docstring's prose, contrasting this one-shot view with `NowPlayingView`'s persistent controller, contained the literal substring `timeout=None` — tripping the `"timeout=None" not in src` assertion that is supposed to check the view's actual `__init__` signature, not its documentation. This is the identical self-correction 14-04's SUMMARY documented for `DiscoverQueueView`'s own docstring.
- **Fix:** Reworded the docstring to say "persistent always-on controller (which never expires)" instead of naming the literal `timeout=None` keyword argument — same meaning, no banned substring.
- **Files modified:** cogs/library.py
- **Verification:** `tests/test_jam_suggest.py::TestJamSuggestConfirmViewIsOneShot::test_view_uses_finite_timeout_not_none` passes.
- **Committed in:** `6eabb7a` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 self-correction, caught during test authoring before commit)
**Impact on plan:** Cosmetic docstring wording only — no functional change, no scope creep.

## Issues Encountered

None beyond the documented docstring self-correction above.

## User Setup Required

None - no external service configuration required. Zero new dependencies, zero new tables, zero new limiters.

## Verification

```
python -m pytest tests/test_jam_suggest.py tests/test_autoqueue_validate.py -q
# 55 passed

python -m pytest tests/ -q
# 754 passed, 105 skipped
```

## Next Phase Readiness

- BRAIN-03 is fully implemented and test-covered; `/jam suggest` is ready for the parked live-Discord UAT pass alongside `/discover` (14-04) and the rest of Phase 14's manual verification items.
- Phase 14 (Smarter Music Brain) is now feature-complete across all 5 plans (14-01 through 14-05) — all 3 requirements (BRAIN-01, BRAIN-02, BRAIN-03) implemented and test-covered.
- No blockers.

---
*Phase: 14-smarter-music-brain*
*Completed: 2026-07-03*

## Self-Check: PASSED

All created/modified files confirmed present on disk (`cogs/library.py`,
`tests/test_jam_suggest.py`); both task commit hashes (`97c00d3`, `6eabb7a`)
confirmed present in git log.
