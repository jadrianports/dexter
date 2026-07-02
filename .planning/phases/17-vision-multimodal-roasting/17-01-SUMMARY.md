---
phase: 17-vision-multimodal-roasting
plan: 01
subsystem: ai
tags: [gemini, safety-settings, vision, multimodal, pure-logic, tdd]

# Dependency graph
requires:
  - phase: 16-proactive-memory-callbacks
    provides: proactive_opt_out column + get_proactive_opt_out (reused as the vision opt-out gate)
  - phase: 10-critical-path-test-coverage
    provides: logic/ pure-decision seam convention (mock-free keyword-only gates)
provides:
  - "logic/vision.py::should_fire_vision_roast pure cadence gate (VIS-01/D-04)"
  - "services/gemini.py::_build_safety_settings + _SAFETY_CATEGORIES (VIS-03/D-01)"
  - "explicit safety_settings on all three user-influenced generate_content configs (chat/generate_image/vision)"
  - "image-carrying chat() (image_bytes/image_mime_type kwargs) preserving the None-on-block contract (VIS-02 hinge)"
  - "six Phase 17 config knobs (chance/cooldown/byte cap/mime allowlist/two safety thresholds)"
affects: [17-02-vision-events-glue]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shared _build_safety_settings helper threaded into every generate_content config"
    - "Per-surface safety thresholds: vision real-block vs text permissive-but-explicit"
    - "Optional image_bytes/image_mime_type kwargs compose an image onto the final user turn without changing the return/raise contract"

key-files:
  created:
    - logic/vision.py
    - tests/test_vision_logic.py
  modified:
    - config.py
    - services/gemini.py
    - tests/test_gemini.py

key-decisions:
  - "_SAFETY_CATEGORIES locked to the four canonical adjustable HarmCategory strings; the SDK's additional IMAGE_*/CIVIC_INTEGRITY/JAILBREAK entries are model-specific/deprecated specials, not standard adjustable SafetySettings for gemini-2.5-flash (RESEARCH A2)"
  - "chat() selects VISION_SAFETY_THRESHOLD when image_bytes is not None, else TEXT_SAFETY_THRESHOLD — a single call path, no parallel vision method (RESEARCH Open Question 2)"
  - "chat() preserves None-on-empty/blocked, raise-only-on-transport; no block-reason branching added that changes the contract (VIS-02 hinge lives one layer up in 17-02)"

patterns-established:
  - "Pure vision gate mirrors logic/proactive.py: keyword-only, cheapest-gate-first (opt-out -> cooldown -> chance), config-defaulted, discord/random/datetime-free"
  - "Rarity invariant test-locks VISION_ROAST_CHANCE strictly below both ambient cadences"

requirements-completed: [VIS-01, VIS-03]

# Metrics
duration: 12min
completed: 2026-07-02
---

# Phase 17 Plan 01: Vision Foundations & Safety Retrofit Summary

**Explicit Gemini safety_settings retrofit across all three user-influenced generate_content sites, an image-carrying chat() that preserves the None-on-block contract, and the pure logic/vision.py cadence gate plus six Phase 17 config knobs.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-07-02T22:01:00Z
- **Completed:** 2026-07-02T22:13:16Z
- **Tasks:** 2
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments
- `logic/vision.py::should_fire_vision_roast` — mock-free, keyword-only, cheapest-gate-first pure gate (opt-out → cooldown → chance), reusing `logic.roasts.cooldown_elapsed` in glue (VIS-01/D-04)
- Six Phase 17 config knobs added after the Phase 16 proactive block: `VISION_ROAST_CHANCE=0.12`, `VISION_ROAST_COOLDOWN_SECONDS=600`, `MAX_VISION_IMAGE_BYTES=8MB`, `VISION_MIME_ALLOWLIST` (gif excluded), `VISION_SAFETY_THRESHOLD=BLOCK_MEDIUM_AND_ABOVE`, `TEXT_SAFETY_THRESHOLD=BLOCK_ONLY_HIGH`
- Shared `_build_safety_settings` + `_SAFETY_CATEGORIES` threaded into both `chat()` and `generate_image()` configs; vision uses the real-block threshold, text stays permissive-but-explicit (VIS-03/D-01)
- `chat()` extended with optional `image_bytes`/`image_mime_type` kwargs that append a `Part.from_bytes` onto the final user turn while preserving the `None`-on-empty/blocked, raise-only-on-transport contract (VIS-02 hinge for 17-02)

## Task Commits

Each task was committed atomically (TDD red → green):

1. **Task 1: config knobs + pure logic/vision.py gate** — `cb68ed4` (test) → `f7501a7` (feat)
2. **Task 2: safety_settings helper + retrofit + image-carrying chat()** — `6fa54cc` (test) → `1452b25` (feat)

_No REFACTOR commits needed — implementations landed clean against the tests._

## Files Created/Modified
- `logic/vision.py` (created) — pure `should_fire_vision_roast` cadence gate
- `tests/test_vision_logic.py` (created) — mock-free boundary truth table + rarity invariant (9 tests)
- `config.py` (modified) — six Phase 17 vision knobs after the Phase 16 block
- `services/gemini.py` (modified) — `_SAFETY_CATEGORIES` tuple, `_build_safety_settings` helper, safety_settings threaded into both configs, image-carrying `chat()`
- `tests/test_gemini.py` (modified) — 8 new tests: threshold differentiation, image-part append, None-on-block, 429→GeminiRateLimitError, non-429→GeminiAPIError

## Decisions Made
- Locked `_SAFETY_CATEGORIES` to the four canonical adjustable categories (HARASSMENT, HATE_SPEECH, SEXUALLY_EXPLICIT, DANGEROUS_CONTENT). Verified `list(types.HarmCategory)` at implementation time (RESEARCH A2): the SDK also exposes `HARM_CATEGORY_IMAGE_*`, `CIVIC_INTEGRITY`, and `JAILBREAK`, but these are model-specific/deprecated specials, not standard adjustable `SafetySetting`s for gemini-2.5-flash — including them risks 400s.
- Single-call-path vision (optional kwargs on `chat()`), not a parallel method — matches RESEARCH Open Question 2 recommendation and keeps the None-on-block contract in one place.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. Phase installs zero new packages (`google-genai` + `discord.py` already pinned).

## Next Phase Readiness
- Everything the Wave-2 glue (17-02) consumes is landed: the pure gate, all six config symbols, the image-carrying `chat()` with the preserved None-on-block hinge, and the safety retrofit.
- Full suite green: 831 passed, 108 skipped, 0 failed — the permissive TEXT threshold did not newly block any existing `/ask`/ambient behavior (wave merge gate satisfied).

---
*Phase: 17-vision-multimodal-roasting*
*Completed: 2026-07-02*

## Self-Check: PASSED

- Created files verified on disk: `logic/vision.py`, `tests/test_vision_logic.py`, `17-01-SUMMARY.md`
- Task commits verified in git log: `cb68ed4`, `f7501a7`, `6fa54cc`, `1452b25`
