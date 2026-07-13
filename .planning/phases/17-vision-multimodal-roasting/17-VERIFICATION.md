---
phase: 17-vision-multimodal-roasting
verified: 2026-07-03T00:00:00Z
status: human_needed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification:
  # No previous VERIFICATION.md existed — this is initial verification.
human_verification:
  - test: "Vision roast feel/cadence on a real posted image (VIS-01)"
    expected: "Rare, dry, content-not-appearance roasts, reply-anchored with no ping; not every image, not every channel"
    why_human: "Requires a live Discord channel + real image upload + a real Gemini vision round-trip; cadence is chance-gated (0.12) so only observable over a session"
  - test: "A genuinely policy-violating image is silently skipped (VIS-02)"
    expected: "Zero output — no refusal message, no template fallback, no reaction"
    why_human: "Requires a real Gemini safety block on live content; the None-on-block path cannot be exercised without a live API refusal"
  - test: "/ask + /imagine behavior unchanged after the safety_settings retrofit (VIS-03)"
    expected: "No new refusals vs pre-retrofit behavior on existing edgy prompts (TEXT_SAFETY_THRESHOLD stays permissive)"
    why_human: "Requires live Gemini calls to confirm the permissive BLOCK_ONLY_HIGH threshold does not regress existing personality output"
---

# Phase 17: Vision/Multimodal Roasting Verification Report

**Phase Goal:** Dexter reacts to images posted in the designated channel with cadence-gated, safety-guarded vision roasts — the highest-blast-radius new surface in the milestone, built on the cadence/safety discipline proven by Phase 16.
**Verified:** 2026-07-03
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Dexter occasionally reacts to/roasts an image in the designated channel, gated by chance + per-user cooldown + priority-2 — not every image, not every channel (VIS-01) | ✓ VERIFIED | `on_message` dispatch (cogs/events.py:441-447) guards on `message.guild`, `DEXTER_CHANNEL_ID`, `message.attachments`; `_maybe_fire_vision_roast` gates via `should_fire_vision_roast(opted_out, cooldown_elapsed, chance_roll=random.random())`; `chat(..., priority=2)` rides the existing 15 RPM limiter. `VISION_ROAST_CHANCE=0.12` < 0.30 & < 0.35 (config invariant test passes). |
| 2 | Oversized / wrong-mime images rejected before download, never reaching Gemini (VIS-01) | ✓ VERIFIED | `_first_valid_image_attachment` (events.py:30-55) normalizes `content_type`, rejects non-allowlisted mime (gif excluded) or `size > MAX_VISION_IMAGE_BYTES` on metadata alone; `attachment.read()` runs only AFTER the gate + cadence pass (events.py:656). Locked by `test_structural_gate_*` + `test_bytes_read_only_after_gate_passes`. |
| 3 | A safety-blocked image reaction is silently skipped — no visible refusal, never via the generic transport fallback (VIS-02) | ✓ VERIFIED | `chat()` returns `response.text if response.text else None` (gemini.py:268 — None on block, no raise); `_generate_vision_roast` returns None on falsy result (silent skip) and `pick_random(VISION_ROAST_FALLBACKS)` ONLY in `except (GeminiRateLimitError, GeminiAPIError)`. Locked by `test_safety_block_silent_skip`, `test_generate_vision_roast_none_on_safety_block`, `test_generate_vision_roast_fallback_on_transport`. |
| 4 | Explicit safety_settings applied to every user-influenced Gemini call (VIS-03) | ✓ VERIFIED | `_build_safety_settings` threaded into both `generate_content` configs: `chat()` (gemini.py:255, threshold = VISION if image else TEXT) and `generate_image()` (gemini.py:290, TEXT). `embed_content` carries no user text-generation risk. Vision uses real-block `BLOCK_MEDIUM_AND_ABOVE`, text uses permissive `BLOCK_ONLY_HIGH`. |

**Score:** 4/4 truths code-verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `config.py` | 6 Phase 17 vision knobs | ✓ VERIFIED | All 6 present (lines 239-244); rarity/exclusion/distinctness invariants pass |
| `logic/vision.py` | `should_fire_vision_roast` pure gate | ✓ VERIFIED | Keyword-only, cheapest-gate-first (opt-out→cooldown→chance); no random/discord/datetime imports (pure) |
| `services/gemini.py` | `_build_safety_settings` + `_SAFETY_CATEGORIES` + image-carrying `chat()` | ✓ VERIFIED | Helper + 4-category tuple; `Part.from_bytes` appended to final turn; None-on-block / 429→RateLimit / else→APIError contract intact |
| `personality/prompts.py` | `build_vision_prompt` conduct clause | ✓ VERIFIED | `VISION_ROAST_PROMPT` + builder; text contains face/body/appearance/identity conduct clause |
| `personality/roasts.py` | `VISION_ROAST_FALLBACKS` transport-only pool | ✓ VERIFIED | 5 placeholder-free lines; registered in `__all__` |
| `cogs/events.py` | gate + generator + dispatch + cooldowns | ✓ VERIFIED | `_first_valid_image_attachment`, `_generate_vision_roast`, `_maybe_fire_vision_roast`, `_vision_roast_cooldowns`, on_message block all present and wired |
| `tests/test_vision_logic.py` | pure gate truth table + rarity invariant | ✓ VERIFIED | Present; passes |
| `tests/test_gemini.py` | safety threading + threshold diff + None-on-block | ✓ VERIFIED | Present; passes |
| `tests/test_vision_events.py` | behavioral lock (16 tests) | ✓ VERIFIED | 16 tests covering structural gate, silent-skip vs fallback, reply-anchor, opt-out |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `chat()` / `generate_image()` | `_build_safety_settings` | `GenerateContentConfig(safety_settings=...)` | ✓ WIRED | Both sites thread the helper (gemini.py:255, 290) |
| `logic/vision.py` | `config.VISION_ROAST_CHANCE` | keyword-only default arg | ✓ WIRED | `chance: float = config.VISION_ROAST_CHANCE` |
| `on_message` | `_maybe_fire_vision_roast` | DEXTER_CHANNEL_ID + attachments guard | ✓ WIRED | events.py:441-447 |
| `_maybe_fire_vision_roast` | `database.get_proactive_opt_out` | shared Phase 16 opt-out | ✓ WIRED | events.py:628 (fail-closed try/except) |
| `_maybe_fire_vision_roast` | `should_fire_vision_roast` | primitives | ✓ WIRED | events.py:646-652 |
| `_generate_vision_roast` | `chat(image_bytes=..., priority=2)` | str\|None dispatch | ✓ WIRED | events.py:585-591 |
| `_maybe_fire_vision_roast` | `message.reply` | AllowedMentions.none() | ✓ WIRED | events.py:665-669, mention_author=False |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Config invariants (rarity, gif-excluded, distinct thresholds) | `python -c "import config; assert ..."` | exit 0 | ✓ PASS |
| Conduct clause + fallback pool | `python -c "from personality... assert 'face' in p ..."` | exit 0, 5 fallbacks | ✓ PASS |
| Events glue symbols importable | `python -c "import cogs.events; assert all(k in s ...)"` | exit 0 | ✓ PASS |
| Phase 17 test suites | `pytest tests/test_vision_logic.py tests/test_gemini.py tests/test_vision_events.py -q` | 37 passed | ✓ PASS |
| Full suite (no-regression merge gate) | `pytest -q` | 848 passed, 108 skipped, 0 failed | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| VIS-01 | 17-01, 17-02 | Cadence-gated vision reaction + size/mime pre-download guard | ✓ SATISFIED | pure gate + structural gate + on_message dispatch; truths 1-2 |
| VIS-02 | 17-02 | Safety-block silent skip, never generic template fallback | ✓ SATISFIED | dedicated str\|None generator; truth 3 |
| VIS-03 | 17-01 | Explicit safety_settings on all user-influenced Gemini calls | ✓ SATISFIED | `_build_safety_settings` on both generate_content sites; truth 4 |

All three requirement IDs from PLAN frontmatter are present in `.planning/REQUIREMENTS.md` (lines 40-42, mapped to Phase 17 lines 88-90). No orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| cogs/events.py | 658 | Raw `attachment.content_type` (not the normalized mime) forwarded to Gemini as `image_mime_type` | ⚠️ Warning | Code-review WR-01, NOT fixed post-review. For a parameterized/non-canonical content_type (e.g. `image/jpeg; charset=binary`, `IMAGE/PNG`) the gate passes (it normalizes) but Gemini receives the un-normalized string and can 400 → a visible transport-fallback line. Standard Discord uploads report canonical types, so rarely triggers. Does not fail a success criterion; robustness edge case. |
| cogs/events.py | 656 | Bare `await attachment.read()` — no try/except | ℹ️ Info | Code-review WR-02, NOT fixed. A deleted message / CDN hiccup raises `discord.HTTPException` that propagates uncaught (discord.py logs, does not crash). Noisy but non-fatal for a cosmetic feature. |
| cogs/events.py | 626-645 | Opt-out DB lookup runs before the free structural gate | ℹ️ Info | Code-review WR-03, NOT fixed. Any attachment (video/pdf/zip) in the channel triggers a wasted DB query before the metadata reject; inverts advertised cheapest-first ordering. Correctness unaffected. |

No debt markers (TODO/FIXME/XXX/TBD/HACK/PLACEHOLDER) found in any modified file. No blocker anti-patterns.

> Note: WR-01/WR-02/WR-03 belong to the Phase 17 code review (`17-REVIEW.md`, 0 critical, 3 warning, 2 info). The `fix(16): ... WR-01/02/03` commits in git history address the **Phase 16** review, not these. The Phase 17 warnings remain in code but are non-blocking robustness items — none contradicts a success criterion.

### Human Verification Required

The following are live-Discord round-trip checks that cannot be exercised without a running bot + real Gemini calls. Parked per the Phase 11/13/14/15/16 precedent (bot runs on-demand on the user's residential PC, not a 24/7 host). Record in `17-HUMAN-UAT.md` at phase close.

1. **Vision roast feel/cadence on a real posted image (VIS-01)**
   - Test: Post images in the designated channel over a session
   - Expected: Rare, dry, content-not-appearance roasts, reply-anchored with no ping

2. **Policy-violating image silently skipped (VIS-02)**
   - Test: Post an image that trips a real Gemini safety block
   - Expected: Zero output — no refusal, no template, no reaction

3. **/ask + /imagine unregressed after the safety retrofit (VIS-03)**
   - Test: Run existing edgy /ask + /imagine prompts
   - Expected: No new refusals vs pre-retrofit behavior

### Gaps Summary

No gaps. All four success criteria (VIS-01 cadence + pre-download guard, VIS-02 silent-skip, VIS-03 explicit safety_settings) are code-verified with substantive, wired artifacts and 37 passing phase tests inside a fully-green 848-test suite. All three requirement IDs are accounted for in REQUIREMENTS.md. The three code-review warnings are unfixed but non-blocking robustness edge cases, flagged above for awareness. The remaining verification surface is exclusively live-Discord "feel"/round-trip behavior, routed to human verification per project convention.

---

_Verified: 2026-07-03_
_Verifier: Claude (gsd-verifier)_
