---
phase: 17-vision-multimodal-roasting
reviewed: 2026-07-02T22:31:53Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - config.py
  - services/gemini.py
  - logic/vision.py
  - personality/prompts.py
  - personality/roasts.py
  - cogs/events.py
findings:
  critical: 0
  warning: 3
  info: 2
  total: 5
status: issues_found
---

# Phase 17: Code Review Report

**Reviewed:** 2026-07-02T22:31:53Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Reviewed the Phase 17 (Vision/Multimodal Roasting) diff against base `cb68ed4^`: config knobs,
the `_build_safety_settings` retrofit, the image-carrying `chat()` path, the pure
`logic/vision.py` cadence gate, the conduct-clause vision prompt + transport-only fallbacks, and
the `cogs/events.py` glue.

Core design is sound. Verified independently:

- **VIS-02 None-on-block contract holds.** In the installed `google-genai==2.8.0`,
  `GenerateContentResponse.text` calls `_get_text()`, which returns `None` (not raises) when
  `candidates`/`content`/`parts` are empty — the safety-block case. So the `response.text if
  response.text else None` at `services/gemini.py:268` correctly yields `None` on a block without
  throwing, and `_generate_vision_roast`'s silent-skip branch is reachable as designed.
- **Safety retrofit is complete.** Both `generate_content` sites (`chat`, `generate_image`) now
  pass `safety_settings`; `embed_content` needs none. The vision path uses the real-block
  `VISION_SAFETY_THRESHOLD`; text/imagine stay permissive `TEXT_SAFETY_THRESHOLD`.
- **SSRF surface closed.** The trigger is attachments-only; no message-content URL is ever fetched.
  The mime/size gate rejects on metadata before any bytes are read.
- **Bot-loop safety.** `on_message` returns early on `message.author.bot`, so Dexter's own
  `/imagine` attachments cannot self-trigger a vision roast.
- **Cadence rarity locked.** `VISION_ROAST_CHANCE = 0.12` is strictly below both ambient cadences,
  and the gate's `chance_roll >= chance -> False` boundary matches the established convention.

Three warnings and two info items below. No blockers.

## Warnings

### WR-01: Normalized mime discarded — raw `attachment.content_type` sent to Gemini

**File:** `cogs/events.py:665` (call site) → `services/gemini.py:233` (consumer)
**Issue:** `_first_valid_image_attachment` deliberately normalizes the mime for the allowlist test
(`(attachment.content_type or "").split(";")[0].strip().lower()`, RESEARCH Pitfall 3), but that
normalized value is thrown away. `_maybe_fire_vision_roast` then passes the **raw**
`attachment.content_type` into `_generate_vision_roast(... attachment.content_type)`, which forwards
it as `image_mime_type` to `types.Part.from_bytes(mime_type=...)`. If Discord reports a
parameterized or non-canonical type (e.g. `"image/jpeg; charset=binary"` or uppercase
`"IMAGE/PNG"`), the gate still passes (it normalizes first) but Gemini receives the un-normalized
string and can `400`. That surfaces as `GeminiAPIError` → a **visible transport fallback line**,
defeating the exact Pitfall-3 mitigation the gate implemented. The `chat()` docstring even asserts
the arg is the "already-gate-validated content_type (e.g. `image/png`)" — but the code passes the
unvalidated raw value.
**Fix:** Have `_first_valid_image_attachment` return the normalized mime alongside the attachment
(e.g. `return attachment, mime`), and pass that normalized mime through to `_generate_vision_roast`
instead of `attachment.content_type`:
```python
attachment, mime = _first_valid_image_attachment(message) or (None, None)
if attachment is None:
    return
...
line = await self._generate_vision_roast(message.author, image_bytes, mime)
```

### WR-02: `attachment.read()` network fetch is not wrapped — unhandled exception path

**File:** `cogs/events.py:664`
**Issue:** Every other I/O boundary in this method is defended: the opt-out lookup has a
`try/except`, and `message.reply()` catches `discord.HTTPException`. But the single network fetch
`image_bytes = await attachment.read()` is bare. Between the metadata gate and the read there are
`await`s (opt-out DB call, plus the read itself), during which the source message can be deleted or
the CDN can hiccup. `Attachment.read()` can raise `discord.HTTPException` / `discord.NotFound` /
`discord.Forbidden`, which would propagate uncaught out of `_maybe_fire_vision_roast` (awaited
directly in `on_message`). discord.py logs it rather than crashing, but it is an inconsistent,
noisy, unhandled error path for a best-effort cosmetic feature.
**Fix:**
```python
try:
    image_bytes = await attachment.read()
except discord.HTTPException as e:
    log.debug("vision roast: attachment read failed (non-fatal): %s", e)
    return
```

### WR-03: Opt-out DB lookup runs before the free structural gate — ordering contradicts cheapest-first

**File:** `cogs/events.py:626-645`
**Issue:** `_maybe_fire_vision_roast` fetches `database.get_proactive_opt_out` (a network DB
round-trip) as step 1, *before* the zero-I/O structural gate (`_first_valid_image_attachment`) and
the free chance roll. Because `on_message` only checks `message.attachments` truthiness (not image
type), this means **every message carrying any attachment** in the designated channel — videos,
PDFs, zips, non-image files — triggers a DB query that is immediately wasted when the structural
gate rejects. It also inverts the "short-circuit, cheapest-first" ordering that `logic/vision.py`
and this method's own docstring advertise, and it makes a DB outage suppress *all* vision reactions
(the fail-closed `except` returns) even for the common opted-in default. The pure gate needs
`opted_out` as input, but the cheap structural gate does not — run it first.
**Fix:** Reorder so the metadata gate short-circuits before the DB call:
```python
attachment = _first_valid_image_attachment(message)
if attachment is None:
    return
try:
    opted_out = await database.get_proactive_opt_out(self.bot.pool, str(message.author.id))
except Exception as e:
    log.debug("vision roast: opt-out lookup failed (non-fatal): %s", e)
    return
# ... then the pure cadence gate ...
```

## Info

### IN-01: A single image+text post can trigger both a proactive callback and a vision roast

**File:** `cogs/events.py:430-448`
**Issue:** `on_message` runs `_maybe_fire_proactive_callback` and then `_maybe_fire_vision_roast`
as independent gates on the same message. For an image posted *with* text in the designated
channel, both can pass their independent chance rolls (0.10 and 0.12) and each issues its own
`message.reply()`. Combined double-fire is rare (~1.2%) but produces two unprompted bot replies to
one user message, which sits in tension with the "don't spam" convention (CLAUDE.md Critical Rule
9). This appears intentional ("a FOURTH independent cadence"), so flagging for awareness rather
than as a defect — consider a per-message "already reacted unprompted" guard if double-replies feel
spammy in live UAT.
**Fix:** Optional — short-circuit the vision gate when a proactive callback already fired on this
message (e.g. a local `fired` flag), or accept the rare overlap as designed.

### IN-02: `_generate_vision_roast` enforces the ≤500-char cap but the prompt asks for ~120

**File:** `cogs/events.py:590-600`
**Issue:** The vision prompt requests "one short line, under ~120 characters," but the transport
enforcement caps at 500 chars (`result[:497] + "..."`), matching the ambient-roast handler. This is
consistent with existing house style (only the first char is lowercased, one-emoji rule is not
enforced in code either), so it is not a regression — just noting the cap does not match the
prompt's stated intent, so an over-length model response would still post at up to 500 chars.
**Fix:** None required; if a tighter guarantee is wanted, cap to a vision-specific length nearer the
prompt's ~120 rather than reusing the 500 ceiling.

---

_Reviewed: 2026-07-02T22:31:53Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
