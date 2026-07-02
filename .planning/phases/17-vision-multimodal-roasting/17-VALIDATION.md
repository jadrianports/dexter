---
phase: 17
slug: vision-multimodal-roasting
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-03
---

# Phase 17 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | none at repo root — tests run via `pytest tests/` with `tests/conftest.py` fixtures + `pytest.mark.asyncio` markers (existing convention) |
| **Quick run command** | `pytest tests/test_vision_logic.py tests/test_gemini.py tests/test_vision_events.py -q` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | ~30-60 seconds (full suite) |

---

## Sampling Rate

- **After every task commit:** Run the plan-scoped quick test (e.g. `pytest tests/test_vision_logic.py -q`)
- **After every plan wave:** Run `pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

*One row per planned task (2 plans / 2 waves / 5 tasks). Derived from RESEARCH.md §Validation Architecture.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 17-01-01 | 01 | 1 | VIS-01 | — | `logic/vision.py::should_fire_vision_roast` chance/cooldown/opt-out truth table + rarity invariant (mock-free pure gate) | unit | `pytest tests/test_vision_logic.py -q` | ❌ W0 | ⬜ pending |
| 17-01-02 | 01 | 1 | VIS-03 | T-17-06 | Explicit safety_settings threaded into all 3 generate_content configs (vision=real-block, /ask+/imagine=permissive); `chat()` None-on-block / raise-on-transport contract preserved | unit (mocked genai) | `pytest tests/test_gemini.py -q` | ❌ W0 | ⬜ pending |
| 17-02-01 | 02 | 2 | VIS-02 | T-17-04 | `build_vision_prompt` carries the conduct clause (roast content, not appearance); `VISION_ROAST_FALLBACKS` is transport-failure-only | unit (import assert) | `python -c` prompt/fallback assertion | ❌ W0 | ⬜ pending |
| 17-02-02 | 02 | 2 | VIS-01/02 | T-17-01/02/06 | Before-download mime/size gate; dedicated str\|None generator (safety→None silent skip, transport→fallback); reply-anchored, opt-out-respecting send | smoke + regression | `python -c` symbol smoke + `pytest tests/test_gemini.py tests/test_vision_logic.py tests/test_proactive_events.py -q` | ❌ W0 | ⬜ pending |
| 17-02-03 | 02 | 2 | VIS-01/02 | T-17-01/06 | Behavioral lock: structural gate reject (size+mime+content_type norm), safety-block silent skip, transport template fallback, reply-anchor + AllowedMentions.none(), opt-out | unit (mocked Gemini) | `pytest tests/test_vision_events.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky. Every task has an `<automated>` verify; no 3 consecutive tasks lack one.*

---

## Wave 0 Requirements

- [ ] `tests/test_vision_logic.py` — mock-free truth table + rarity invariant for `should_fire_vision_roast` (VIS-01) — created in task 17-01-01
- [ ] `tests/test_gemini.py` additions — safety_settings threaded into all 3 generate_content configs + threshold differentiation + None-on-block contract (VIS-03) — created in task 17-01-02
- [ ] `tests/test_vision_events.py` — mocked-Gemini: mime/size reject, safety-block silent skip, transport fallback, reply-anchor, opt-out (VIS-01/02); mirrors `tests/test_proactive_events.py` helpers extended with `_make_attachment(content_type, size)` — created in task 17-02-03

*Test files are materialized inside their producing tasks (TDD-style for the pure gate + gemini, behavioral-lock task for the glue) — there is no separate pre-wave scaffold step; `wave_0_complete` flips true once execution creates them.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Actual vision roast feel/cadence on a real posted image | VIS-01 | Requires a live Discord channel + real image upload + Gemini vision round-trip; cadence is chance-gated | Post images in the designated channel over a session; confirm rare, dry, content-not-appearance roasts, reply-anchored with no ping |
| A genuinely policy-violating image is silently skipped (no trace) | VIS-02 | Requires a real Gemini safety block on live content | Post an image that trips Gemini safety; confirm zero output — no refusal, no template, no reaction |
| /ask + /imagine behavior unchanged after safety retrofit | VIS-03 | Requires live Gemini calls to confirm permissive thresholds don't regress edgy output | Run existing /ask + /imagine prompts; confirm no new refusals vs pre-retrofit behavior |

*Live-Discord checks parked in 17-HUMAN-UAT.md per the Phase 11/13/14/15/16 precedent.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (planner, 2026-07-03) — 2 plans / 2 waves / 5 tasks; every task carries an automated verify.
