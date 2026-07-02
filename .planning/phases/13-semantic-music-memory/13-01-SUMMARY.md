---
phase: 13-semantic-music-memory
plan: 01
subsystem: config
tags: [pure-logic, tdd, config, accuracy-firewall]

# Dependency graph
requires:
  - phase: 11-rag-long-term-memory
    provides: MEMORY_SALIENCE_BASE_WEIGHTS dict, MEMORY_DECAY_SALIENCE_FLOOR, MemoryService.distill_and_remember() kind-agnostic plumbing
provides:
  - config.TASTE_* tuning knobs (decay days, distill hour, lookback/baseline windows, min-activity threshold, classification thresholds)
  - config.MEMORY_SALIENCE_BASE_WEIGHTS["taste_episode"] = 0.4 (below the sweep floor, D-04)
  - config.MEMORY_DECAY_DAYS_BY_KIND per-kind decay-horizon override map
  - logic/taste.py: has_min_activity, TastePattern enum, classify_artist, summarize_taste, resolve_decay_days — pure, mock-free decision seam
  - tests/test_taste_logic.py: 24 mock-free unit tests including the digit-free accuracy-firewall assertion
affects: [13-02-database-taste-helpers, 13-03-memory-service-self-refresh, 13-04-taste-distill-batch-task]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "logic/taste.py follows the established logic/*.py pure-seam convention (logic/skip_stats.py, logic/autoqueue.py, logic/playback.py): no Discord/asyncio/asyncpg/random imports, no datetime.now(), all nondeterministic values passed in as primitives by the caller."
    - "Accuracy-firewall pre-bucketing: raw integer counts are classified into a TastePattern enum, then mapped to FIXED template phrases (no f-string count interpolation) — numbers are structurally excluded from the output, not merely filtered downstream."

key-files:
  created: [logic/taste.py, tests/test_taste_logic.py]
  modified: [config.py]

key-decisions:
  - "taste_episode salience weight set to 0.4, strictly below MEMORY_DECAY_SALIENCE_FLOOR (0.5) per D-04, so taste rows are genuinely sweep-eligible and fads age out per the D-05 self-refresh design intent."
  - "MEMORY_DECAY_DAYS_BY_KIND introduced as a new mapping (not a modification to MEMORY_DECAY_DAYS) so Phase 11 kinds fall back unchanged via .get(kind, MEMORY_DECAY_DAYS) — verified by an explicit assertion in Task 1's verify step."
  - "classify_artist precedence is OBSESSION > NEW_ARRIVAL > STEADY > DROPPED_OFF > NONE, matching the plan's literal check order; skips_in_window is accepted in the signature for future-proofing but not consulted by current precedence rules."
  - "Digit-free firewall test fixture uses only digit-free artist names — artist name sanitization is explicitly out of scope for this firewall (it guards against leaking raw listening COUNTS, not user-controlled strings that may legitimately contain digits, e.g. real artist names like 'Blink-182')."

patterns-established:
  - "Pure taste-classification seam (logic/taste.py) ready for plan 13-04's bot.py::taste_distill_batch to call directly with DB-sourced primitives."
  - "resolve_decay_days(kind, default_days=, kind_overrides=) gives plan 13-03's memory-service self-refresh a single call site for per-kind decay horizons without touching services/memory.py's core dedup/remember logic."

requirements-completed: [TASTE-01, TASTE-02]

# Metrics
duration: 12min
completed: 2026-07-02
---

# Phase 13 Plan 01: Taste Config + Pure Logic Seam Summary

**New `TASTE_*` config knobs + a below-floor `taste_episode` salience weight + a pure `logic/taste.py` module (has_min_activity/classify_artist/summarize_taste/resolve_decay_days) locked by 24 mock-free unit tests proving the number-free accuracy firewall.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-02T09:52:00Z
- **Completed:** 2026-07-02T09:57:40Z
- **Tasks:** 2 (Task 2 is TDD: RED + GREEN commits)
- **Files modified:** 3 (config.py, logic/taste.py, tests/test_taste_logic.py)

## Accomplishments
- Added the full `# --- Phase 13: Semantic Music Memory ---` config block: `TASTE_DECAY_DAYS`, `TASTE_DISTILL_BATCH_HOUR`, `TASTE_LOOKBACK_DAYS`, `TASTE_BASELINE_DAYS`, `TASTE_MIN_ACTIVITY_TRACKS`, and the five classification-threshold constants, plus `MEMORY_DECAY_DAYS_BY_KIND`.
- Extended the existing `MEMORY_SALIENCE_BASE_WEIGHTS` dict (did not create a parallel dict) with `"taste_episode": 0.4`, strictly below the 0.5 sweep floor per D-04.
- Built `logic/taste.py` as a pure, mock-free decision seam: the D-08 min-activity gate, the D-01 five-way `TastePattern` classification precedence, the D-02 number-free phrase emission, and the D-03 per-kind decay resolver.
- Locked all of the above with `tests/test_taste_logic.py` (24 tests, 0 skips), including an explicit digit-free firewall assertion over a fixture spanning all four notable patterns.
- Followed strict TDD gate sequence for Task 2: RED commit (test fails — module doesn't exist) → GREEN commit (test passes).
- Confirmed full existing test suite remains green (633 passed, 93 skipped — pre-existing live-DB integration tests unaffected) — no Phase 11 regression from the config additions.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Phase 13 taste config knobs, salience weight, and decay-by-kind mapping** - `0d4117f` (feat)
2. **Task 2: Create logic/taste.py pure banding + gate + decay-resolver (RED)** - `9b27db8` (test)
3. **Task 2: Create logic/taste.py pure banding + gate + decay-resolver (GREEN)** - `c447c8d` (feat)

**Plan metadata:** _pending — added by the final metadata commit step_

_Note: Task 2 is a TDD task with two commits (test → feat); no refactor commit was needed._

## Files Created/Modified
- `config.py` - New Phase 13 taste knobs, `taste_episode` salience weight (below sweep floor), `MEMORY_DECAY_DAYS_BY_KIND` mapping
- `logic/taste.py` - Pure `has_min_activity`, `TastePattern` enum, `classify_artist`, `summarize_taste`, `resolve_decay_days`
- `tests/test_taste_logic.py` - 24 mock-free unit tests: min-activity floor, classification branch coverage, phrase emission, digit-free firewall, decay resolution

## Decisions Made
- `TASTE_OBSESSION_MIN_PLAYS`/`TASTE_NEW_ARRIVAL_MIN_PLAYS`/`TASTE_STEADY_MIN_BASELINE`/`TASTE_BAND_HEAVY_PLAYS`/`TASTE_BAND_FEW_PLAYS` were all added in Task 1 as directional-prior constants per the plan's explicit list, even though only the first three are consumed by `logic/taste.py` in this plan — `TASTE_BAND_HEAVY_PLAYS`/`TASTE_BAND_FEW_PLAYS` are reserved for the raw-count-to-band step inside `bot.py::taste_distill_batch` (plan 13-04), which builds the `raw_text` handed to `distill_and_remember`.
- `classify_artist` accepts `skips_in_window` per the plan's literal signature but does not consult it in the current precedence rules — kept for signature stability / future-proofing (e.g. skip-adjusted confidence) rather than dropped, matching the plan's explicit instruction to include it in the signature.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed a test-fixture bug in the digit-free firewall test**
- **Found during:** Task 2 GREEN phase (first test run against the real implementation)
- **Issue:** The RED-phase fixture included an artist name `"artist99"` to pad the fixture — running the firewall test against the working implementation immediately revealed the digit leaked from the artist *name*, not from a raw count. The firewall's actual guarantee (D-02) is that `summarize_taste` never interpolates a raw count into a phrase; it does not — and was never meant to — sanitize digits out of user-controlled artist strings (e.g. real artist names like "Blink-182" or "Sum 41" legitimately contain digits).
- **Fix:** Removed the digit-containing artist from the fixture and added an inline comment documenting the scope boundary, so the test isolates exactly the property under test (count-leakage, not artist-name sanitization).
- **Files modified:** tests/test_taste_logic.py
- **Verification:** `python -m pytest tests/test_taste_logic.py -q` — 24 passed.
- **Committed in:** `c447c8d` (Task 2 GREEN commit, documented inline in the commit message)

---

**Total deviations:** 1 auto-fixed (1 bug in test fixture, not implementation)
**Impact on plan:** Zero scope creep — the fix corrected a test authored in this same plan before it was ever asserted against real code; the implementation required no changes.

## Issues Encountered
None beyond the fixture bug documented above.

## User Setup Required
None - no external service configuration required. Zero new package installs (pure config + pure-Python logic per the threat model's T-13-SC "accept" disposition).

## Next Phase Readiness
- `logic/taste.py`'s four public functions are ready for plan 13-02 (`database.py` aggregate helpers) to feed raw counts into, and for plan 13-04 (`bot.py::taste_distill_batch`) to call directly for classification + phrase generation.
- `resolve_decay_days` + `MEMORY_DECAY_DAYS_BY_KIND` are ready for plan 13-03's memory-service self-refresh work — but the open D-05 correctness risk flagged in `13-PATTERNS.md` (dedup's `bump_memory_hit` does not refresh `expires_at`, so a still-true steady favorite could age out under `TASTE_DECAY_DAYS` even while remaining true) is **not addressed by this plan** and remains an explicit open decision for plan 13-03's planner/executor to resolve (options (a)/(b)/(c) in `13-PATTERNS.md`).
- No blockers for 13-02.

---
*Phase: 13-semantic-music-memory*
*Completed: 2026-07-02*
