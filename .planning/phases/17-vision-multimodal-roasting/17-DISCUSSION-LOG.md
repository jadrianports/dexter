# Phase 17: Vision / Multimodal Roasting - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-03
**Phase:** 17-vision-multimodal-roasting
**Areas discussed:** Safety-settings scope (VIS-03), Trigger surface, App-level hard-rule layer (VIS-02), Reaction shape & voice

> **Session note:** User selected all four gray areas, then went AFK (60s) before the batched
> decision question. Per the Phase 14/15/16 precedent, all decisions below are Claude's
> conservative, requirement-anchored recommendations adopted on the user's behalf — flagged
> revisable in CONTEXT.md.

---

## Safety-settings scope (VIS-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Retrofit all three | Explicit safety_settings on vision + /ask + /imagine; vision real-block, /ask+/imagine permissive-but-explicit | ✓ (D-01) |
| Vision-only | Scope strictly to the new vision call | |
| Vision + /imagine | Guard both image surfaces, leave /ask | |

**User's choice:** Retrofit all three (adopted on user's behalf).
**Notes:** VIS-03 frames "consistent application" as the goal; Gemini 2.5 defaults safety OFF, so /ask + /imagine are unguarded today. Thresholds differ by surface — vision blocks for real (silent skip), text/image-gen stay permissive so the edgy personality does not regress.

---

## Trigger surface

| Option | Description | Selected |
|--------|-------------|----------|
| Attachments only, first valid image | image/* attachments; multi-image → roast first valid; mime/size checked pre-download via attachment metadata | ✓ (D-02) |
| Attachments + image URLs/embeds | Also roast pasted image links | |
| Attachments only, batch-aware | Roast the whole image set | |

**User's choice:** Attachments only, first valid image (adopted on user's behalf).
**Notes:** Discord exposes content_type + size without downloading (satisfies VIS-01's before-download guard). Pasted URLs excluded — SSRF surface + no pre-download size.

---

## App-level hard-rule layer (VIS-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Structural gate + conduct clause | mime/size gate + prompt conduct clause (roast content not real people's appearance); honors shared Phase 16 opt-out | ✓ (D-03) |
| Structural gate only | mime/size + safety_settings, no conduct clause | |
| Add a dedicated vision opt-out | Same as recommended but a separate vision opt-out flag | |

**User's choice:** Structural gate + conduct clause (adopted on user's behalf).
**Notes:** The app-level layer is code we own beside model safety_settings. Conduct clause prevents an image roast becoming a personal-appearance attack. Reuses the Phase 16 proactive_opt_out as the shared "unprompted-surface" silence — no new flag.

---

## Reaction shape & voice

| Option | Description | Selected |
|--------|-------------|----------|
| Text reply + own chance/cooldown | Reply-anchored Gemini roast, AllowedMentions.none(), new VISION_ROAST_CHANCE + per-user cooldown, priority-2 | ✓ (D-04) |
| Emoji reaction + text reply | Add an emoji react alongside | |
| Emoji reaction only | No Gemini text | |

**User's choice:** Text reply + own chance/cooldown (adopted on user's behalf).
**Notes:** VIS-01 says "roasts" → a dry text line is the deliverable. A safety block is a silent skip, NOT a template fallback. Cadence stays independent of ambient/proactive gates (fourth distinct surface). Pure logic/vision.py gate mirrors logic/proactive.py.

---

## Claude's Discretion

- Exact numeric knobs: MAX_VISION_IMAGE_BYTES, VISION_ROAST_CHANCE, VISION_ROAST_COOLDOWN_SECONDS, mime allowlist contents, per-category HarmBlockThreshold per surface.
- safety_settings helper shape (constant vs. per-surface builder).
- Safety-block detection mechanism (prompt_feedback.block_reason / finish_reason / empty parts).
- Cog placement of the trigger glue (dedicated _maybe_fire_vision_roast preferred).
- Vision system prompt (reuse build_chat_prompt + image part vs. dedicated builder).
- Optional per-user/day cap on top of the cooldown (belt-and-suspenders).

## Deferred Ideas

- Vision reactions feeding RAG memory → v2 (MEM-R2).
- Pasted image URLs / embeds as a trigger.
- A dedicated vision opt-out distinct from the Phase 16 proactive opt-out.
- Emoji reaction on images (alongside/instead of text).
- Batch/multi-image roasting.
