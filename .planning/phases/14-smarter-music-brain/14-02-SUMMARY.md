---
phase: 14-smarter-music-brain
plan: 02
subsystem: music-brain
tags: [gemini, prompt-engineering, pure-logic, auto-queue, taste]

# Dependency graph
requires:
  - phase: 14-01
    provides: get_recently_skipped, get_artist_cooccurrence, get_user_top_artist SQL helpers + kind-filtered recall + Phase 14 config knobs
provides:
  - logic/autoqueue.py::is_recently_skipped_artist — D-02 hard post-filter, reuses _normalize_for_match
  - logic/taste.py::select_positive_taste_context — D-03 round-robin blend/cap, unattributed collective output
  - personality/prompts.py::build_recommendation_prompt extended with recently_skipped=/positive_taste= kwargs (byte-identical when omitted)
  - personality/prompts.py::build_discover_commentary_prompt (+ DISCOVER_COMMENTARY_PROMPT) — D-04 firewall
  - personality/prompts.py::build_jam_suggestion_prompt (+ JAM_SUGGESTION_PROMPT) — D-06, parse_suggestions-compatible
affects: [14-03-auto-queue-wiring, 14-04-discover-command, 14-05-jam-suggest-command]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure logic/ seam (Phase 10-13 convention) extended with two new sibling functions, no Discord/DB/asyncio/random/datetime.now()"
    - "Optional-signal, byte-identical-when-empty prompt extension (Phase 11 build_chat_prompt memory_context pattern) reused for build_recommendation_prompt's two new kwargs"

key-files:
  created: []
  modified:
    - logic/autoqueue.py
    - logic/taste.py
    - personality/prompts.py
    - tests/test_autoqueue_validate.py
    - tests/test_taste_logic.py
    - tests/test_prompts.py

key-decisions:
  - "Fixed a cap=0 off-by-one in select_positive_taste_context vs the RESEARCH.md reference snippet: check len(result) >= cap BEFORE appending (not after), so cap=0 returns [] instead of one item"

patterns-established:
  - "Prompt builders for new Gemini surfaces (discover commentary, jam suggestion) follow the existing module-level TEMPLATE constant + .format()-calling function idiom, not a new templating convention"

requirements-completed: [BRAIN-01, BRAIN-02, BRAIN-03]

# Metrics
duration: 18min
completed: 2026-07-02
---

# Phase 14 Plan 2: Pure-Logic Seams + Prompt Builders Summary

**Two new mock-free `logic/` functions (D-02 skip-artist hard filter, D-03 taste blend/cap) plus three `personality/prompts.py` extensions (recommendation prompt kwargs, discover commentary, jam suggestion) — all byte-identical to today when their new optional signal is empty.**

## Performance

- **Duration:** 18 min
- **Tasks:** 3 completed
- **Files modified:** 6 (3 source, 3 test)

## Accomplishments
- `logic/autoqueue.py::is_recently_skipped_artist` — pure hard post-filter reusing `_normalize_for_match` verbatim (no second tokenizer, no difflib per D-12)
- `logic/taste.py::select_positive_taste_context` — round-robin interleave, dedup, cap, UNATTRIBUTED collective output (Pitfall 4 safe)
- `personality/prompts.py::build_recommendation_prompt` extended with `recently_skipped=`/`positive_taste=` keyword-only kwargs, byte-identical when both omitted
- `personality/prompts.py::build_discover_commentary_prompt` (+ `DISCOVER_COMMENTARY_PROMPT`) — Gemini wraps SQL-supplied artist names only, instructed never to invent picks (D-04 firewall)
- `personality/prompts.py::build_jam_suggestion_prompt` (+ `JAM_SUGGESTION_PROMPT`) — identical `{title, artist}` JSON contract `cogs/ai.py::parse_suggestions` already parses, verified via round-trip test

## Task Commits

Each task was committed atomically:

1. **Task 1: Add is_recently_skipped_artist to logic/autoqueue.py (D-02)** - `8c0ac6c` (test)
2. **Task 2: Add select_positive_taste_context to logic/taste.py (D-03)** - `d764629` (test)
3. **Task 3: Extend build_recommendation_prompt + add discover/jam prompt builders** - `63a2ea4` (feat)

_Note: Tasks marked tdd="true" in the plan; committed as single test+impl commits per task rather than separate RED/GREEN commits since the plan's own commit-type table treats each task as one atomic unit._

## Files Created/Modified
- `logic/autoqueue.py` - added `is_recently_skipped_artist` pure function (sibling of `validate_youtube_match`)
- `logic/taste.py` - added `select_positive_taste_context` pure function (sibling of `summarize_taste`)
- `personality/prompts.py` - extended `build_recommendation_prompt`; added `build_discover_commentary_prompt`/`DISCOVER_COMMENTARY_PROMPT`; added `build_jam_suggestion_prompt`/`JAM_SUGGESTION_PROMPT`
- `tests/test_autoqueue_validate.py` - added `TestIsRecentlySkippedArtist` (5 cases)
- `tests/test_taste_logic.py` - added `TestSelectPositiveTasteContext` (6 cases, named with `positive_taste` substring for `-k` discoverability)
- `tests/test_prompts.py` - added `TestBuildRecommendationPromptPhase14Kwargs`, `TestBuildDiscoverCommentaryPrompt`, `TestBuildJamSuggestionPrompt`

## Decisions Made
- Fixed a cap=0 off-by-one bug in `select_positive_taste_context` relative to the RESEARCH.md/PATTERNS.md reference snippet (Rule 1 — auto-fix bug): the reference code checked `len(result) >= cap` *after* appending, so `cap=0` would still return one item instead of `[]`. Restructured to check the cap *before* appending each candidate, preserving identical round-robin/dedup/output order for all `cap > 0` cases (verified against the `["a","c","b"]` cap=3 fixture).
- `tests/test_prompts.py` already existed (confirmed by grep before creating) — extended in place per the Wave 0 gap note in RESEARCH.md rather than creating a duplicate file.
- Test method names in `TestSelectPositiveTasteContext` were prefixed with `test_positive_taste_` (not just `test_`) so the plan's literal `-k positive_taste` verification command matches — pytest `-k` is case-sensitive and the class name alone (`TestSelectPositiveTasteContext`) does not contain the lowercase-with-underscore substring `positive_taste`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed cap=0 off-by-one in select_positive_taste_context**
- **Found during:** Task 2 (writing the `cap=0 -> []` test case)
- **Issue:** The RESEARCH.md/PATTERNS.md reference implementation checks `if len(result) >= cap: return result` *after* appending a candidate to `result`, so calling with `cap=0` would still append and return one item instead of the required empty list.
- **Fix:** Moved the cap check to the top of the inner loop body, before the append, so `cap=0` returns `[]` immediately while preserving identical output for all `cap > 0` inputs (verified against the round-robin order fixture).
- **Files modified:** logic/taste.py
- **Verification:** `tests/test_taste_logic.py::TestSelectPositiveTasteContext::test_positive_taste_cap_zero_returns_empty_list` and `test_positive_taste_round_robin_interleave_order` both pass.
- **Committed in:** d764629 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 bug fix)
**Impact on plan:** Necessary for correctness against the plan's own stated behavior spec ("cap=0 → []"). No scope creep — same function signature, same non-zero-cap behavior.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `is_recently_skipped_artist`, `select_positive_taste_context`, and all three prompt-builder changes are ready for plans 14-03 (auto-queue wiring), 14-04 (`/discover`), and 14-05 (`/jam suggest`) to consume as pure glue-free building blocks.
- Full test suite green (691 passed, 105 skipped) — no regression in any existing prompt/logic/auto-queue test.
- No blockers.

---
*Phase: 14-smarter-music-brain*
*Completed: 2026-07-02*

## Self-Check: PASSED

All created/modified files verified present on disk; all 4 commits (8c0ac6c, d764629, 63a2ea4, 9e63bf4) verified present in git log.
