---
phase: 17-vision-multimodal-roasting
plan: 02
subsystem: events
tags: [vision, multimodal, gemini, unprompted-roast, safety, events-glue]

# Dependency graph
requires:
  - phase: 17-vision-multimodal-roasting
    provides: "17-01 — logic/vision.py gate, six vision config knobs, image-carrying chat() (None-on-block hinge)"
  - phase: 16-proactive-memory-callbacks
    provides: "proactive_opt_out column + get_proactive_opt_out (reused as the shared vision opt-out — no new flag)"
  - phase: 10-critical-path-test-coverage
    provides: "logic/ pure-decision seam convention (glue dispatches on the pure gate)"
provides:
  - "personality/prompts.py::build_vision_prompt — D-03 conduct-clause vision system prompt (VIS-02)"
  - "personality/roasts.py::VISION_ROAST_FALLBACKS — transport-failure-only fallback pool (D-04)"
  - "cogs/events.py::_first_valid_image_attachment — before-download mime/size structural gate (VIS-01/D-02)"
  - "cogs/events.py::EventsCog._generate_vision_roast — str|None dispatch: None on safety-block/empty, fallback only on transport (VIS-02)"
  - "cogs/events.py::EventsCog._maybe_fire_vision_roast — opt-out + pure cadence gate + reply-anchored send"
  - "cogs/events.py on_message — fourth independent unprompted cadence under DEXTER_CHANNEL_ID + attachments guard"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dedicated str|None generator keeps safety-block (silent skip) distinct from transport-failure (template fallback) — NOT a reuse of _generate_ambient_roast's always-str contract (RESEARCH Pitfall 1)"
    - "Before-download structural gate: reject on attachment metadata (mime/size) alone, zero bytes fetched — content_type normalized via .split(';')[0].strip().lower() (Pitfall 3)"
    - "Vision roast is a fourth independent on_message cadence, reusing the shared Phase 16 opt-out and the reply-anchored AllowedMentions.none() send"

key-files:
  created:
    - tests/test_vision_events.py
  modified:
    - personality/prompts.py
    - personality/roasts.py
    - cogs/events.py

key-decisions:
  - "Dedicated _generate_vision_roast (str|None) rather than reusing _generate_ambient_roast — the ambient generator collapses a safety block and a transport failure into one visible template, which would violate VIS-02 (a safety-blocked image must leave zero visible trace)"
  - "No gemini_service present -> silent skip (None), NOT a transport fallback — absence of AI is not a transport failure and must not emit a visible template"
  - "Vision cadence is a fourth, separate on_message block (not merged with the proactive gate) so the two rarities stay independent and each keys on its own guard (proactive: always; vision: only when message.attachments)"

patterns-established:
  - "Structural gate is a module-level pure function (_first_valid_image_attachment) — unit-testable without a cog instance, mirrors the logic/ seam discipline at the I/O boundary"
  - "Transport-only fallback pools carry NO placeholders, so the generator picks one without .format()"

requirements-completed: [VIS-01, VIS-02]

# Metrics
duration: 6min
completed: 2026-07-02
---

# Phase 17 Plan 02: Vision Events Glue Summary

**The vision-roast trigger surface wired end-to-end: a D-03 conduct-clause prompt, a before-download mime/size gate, and a dedicated str|None generator that silently skips a safety block but template-falls-back only on a transport failure — dispatched from on_message as a fourth independent unprompted cadence reusing the Phase 16 opt-out.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-07-02T22:17:29Z
- **Completed:** 2026-07-02T22:22:59Z
- **Tasks:** 3
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments
- `personality/prompts.py::build_vision_prompt` — a small dedicated builder (mirrors `build_discover_commentary_prompt`, not the full few-shot DEXTER block, keeping the inline request small under Gemini's 20MB combined inline-data cap) carrying the D-03 step 2 conduct clause verbatim in intent: roast the image's content/vibe, NEVER a real person's face/body/weight/identity (VIS-02)
- `personality/roasts.py::VISION_ROAST_FALLBACKS` — five dry, lowercase, placeholder-free lines that fire ONLY on a transport failure, registered in `__all__`
- `cogs/events.py::_first_valid_image_attachment` — before-download structural gate: normalize `content_type` (None -> reject, `; charset=` -> strip), reject non-allowlisted mime (image/gif excluded) or `size > MAX_VISION_IMAGE_BYTES`, return the first passing attachment with zero bytes fetched (VIS-01/D-02, mitigates T-17-01/T-17-02)
- `cogs/events.py::_generate_vision_roast` — dedicated `str | None`: `None` on a safety-blocked/empty response (silent skip) or a missing gemini_service; `pick_random(VISION_ROAST_FALLBACKS)` only in the `except (GeminiRateLimitError, GeminiAPIError)` clause (VIS-02/D-04, mitigates T-17-06)
- `cogs/events.py::_maybe_fire_vision_roast` — shared Phase 16 opt-out (fail closed) -> structural gate -> pure `should_fire_vision_roast` cadence (opt-out/cooldown/chance) -> single `attachment.read()` only after the gate passes -> reply-anchored `AllowedMentions.none()` + `mention_author=False`, cooldown marked only on a successful send
- `on_message` fourth independent cadence under `DEXTER_CHANNEL_ID` + `message.attachments`
- `tests/test_vision_events.py` — 17 behavioral tests locking the structural gate (size/mime/None/charset/first-valid), the VIS-02 silent-skip-vs-transport-fallback distinction (both through the dispatch and directly on the generator), reply-anchor + cooldown mark, bytes-read-only-after-gate, and the shared opt-out

## Task Commits

Each task was committed atomically:

1. **Task 1: conduct-clause vision prompt + transport-only fallback pool** — `fdb8891`
2. **Task 2: events glue — structural gate, str|None generator, on_message dispatch** — `5c8c359`
3. **Task 3: behavioral lock for the VIS-01/VIS-02 dispatch contract** — `8474d7f`

## Files Created/Modified
- `tests/test_vision_events.py` (created) — 17 behavioral tests for the vision dispatch contract
- `personality/prompts.py` (modified) — `VISION_ROAST_PROMPT` + `build_vision_prompt()`
- `personality/roasts.py` (modified) — `VISION_ROAST_FALLBACKS` + `__all__` entry
- `cogs/events.py` (modified) — imports, `_vision_roast_cooldowns`, `_first_valid_image_attachment`, `_generate_vision_roast`, `_maybe_fire_vision_roast`, on_message dispatch block

## Decisions Made
- A dedicated `_generate_vision_roast` (not a reuse of `_generate_ambient_roast`) is the safety-critical hinge: the ambient generator always returns a string, which would surface a safety-blocked image as the same visible template as a rate-limited one — a VIS-02 violation. The dedicated generator returns `None` for the block/empty path and a fallback only for the transport-exception path, and `test_vision_events.py` locks the two apart directly.
- Missing `gemini_service` is treated as a silent skip (`None`), not a transport fallback — the absence of AI is not a transport failure and must not emit a visible line.
- The vision cadence is a separate on_message block from the proactive gate so the two rarities stay independent; it additionally guards on `message.attachments` so text-only messages never enter the vision path.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. Phase installs zero new packages (T-17-SC).

## Threat Model Coverage
All `mitigate` dispositions in the plan's STRIDE register are implemented and test-locked:
- **T-17-01** (oversized/wrong-mime DoS) — `_first_valid_image_attachment` before-download reject, locked by the structural-gate tests
- **T-17-02** (SSRF) — attachments-only trigger; bytes come solely from `attachment.read()` (Discord CDN), the on_message guard keys on `message.attachments`
- **T-17-04** (roasting a real person's appearance) — `build_vision_prompt` conduct clause, prompt-text assertion in Task 1
- **T-17-05** (prompt injection via image text) — defense in depth: app-level conduct clause (this plan) + model-level real-block safety_settings (17-01)
- **T-17-06** (safety-block leaking as a visible reply) — dedicated `_generate_vision_roast` None-on-block, locked by the vis02-regression + safety-block-silent-skip tests

## Next Phase Readiness
- Phase 17 (Vision/Multimodal Roasting) is code-complete across both waves. Full suite green: **848 passed, 108 skipped, 0 failed** (+17 vision-events tests over the 17-01 baseline; the fourth cadence did not regress ambient/proactive/`/ask`).
- Parked for phase close (per Phase 11/13/14/15/16 precedent): the live "feel"/cadence of a roast on a real posted image, a genuine Gemini vision round-trip, a real safety-block producing zero visible trace, and `/ask` + `/imagine` being unregressed to a human ear — all live-Discord manual checks, to be recorded in `17-HUMAN-UAT.md` at phase close (see 17-VALIDATION.md §Manual-Only).

---
*Phase: 17-vision-multimodal-roasting*
*Completed: 2026-07-02*

## Self-Check: PASSED

- Created/modified files verified on disk: `personality/prompts.py`, `personality/roasts.py`, `cogs/events.py`, `tests/test_vision_events.py`, `17-02-SUMMARY.md`
- Task commits verified in git log: `fdb8891`, `5c8c359`, `8474d7f`
