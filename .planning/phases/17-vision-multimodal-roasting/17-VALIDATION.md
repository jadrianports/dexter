---
phase: 17
slug: vision-multimodal-roasting
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-03
---

# Phase 17 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pytest.ini` / `pyproject.toml` (existing) |
| **Quick run command** | `pytest tests/test_vision_logic.py -q` |
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

*Populated by the planner / execution — one row per task. Derived from RESEARCH.md §Validation Architecture:*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 17-01-01 | 01 | 1 | VIS-03 | T-17-01 | Explicit safety_settings thread into every generate_content config (vision=real-block, /ask+/imagine=permissive-but-explicit) | unit | `pytest tests/test_gemini_safety.py -q` | ❌ W0 | ⬜ pending |
| 17-02-01 | 02 | 1 | VIS-01 | — | logic/vision.py::should_fire_vision_roast chance/cooldown/opt-out truth table (mock-free pure gate) | unit | `pytest tests/test_vision_logic.py -q` | ❌ W0 | ⬜ pending |
| 17-03-01 | 03 | 2 | VIS-01/02 | T-17-02 | Before-download mime/size reject; safety-block→None→silent skip; transport-failure→template fallback | unit (mocked Gemini) | `pytest tests/test_vision_glue.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky · Task IDs indicative — planner is authoritative.*

---

## Wave 0 Requirements

- [ ] `tests/test_vision_logic.py` — mock-free truth table for `should_fire_vision_roast` (VIS-01)
- [ ] `tests/test_gemini_safety.py` — assert safety_settings threaded into all 3 generate_content configs (VIS-03)
- [ ] `tests/test_vision_glue.py` — mocked-Gemini: mime/size reject, safety-block silent skip, transport fallback (VIS-01/02)

*Existing pytest infrastructure covers framework; new test files stub the phase requirements.*

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

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
