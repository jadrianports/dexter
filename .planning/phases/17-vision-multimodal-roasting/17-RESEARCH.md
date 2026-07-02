# Phase 17: Vision / Multimodal Roasting - Research

**Researched:** 2026-07-03
**Domain:** Gemini vision (multimodal) input via `google-genai`, Gemini `safety_settings`, Discord attachment metadata, cadence-gated unprompted Discord bot surfaces
**Confidence:** HIGH (Gemini SDK/safety mechanics — verified via Context7 + official docs; Discord attachment metadata — verified via official docs/source); MEDIUM (exact numeric knob values, mime-allowlist trimming — planner discretion per CONTEXT.md)

## Summary

Phase 17 adds one new unprompted surface (`_maybe_fire_vision_roast` in `cogs/events.py`) plus a
`safety_settings` retrofit across three existing `generate_content` call sites in
`services/gemini.py` (`chat()` used by `/ask` + ambient/proactive roasts, `generate_image()` used
by `/imagine`, and a new vision-capable call). Zero new dependencies: `google-genai` 2.8.0 and
`discord.py` 2.7.1 (both already installed, confirmed via `pip show`/`import`) fully cover
`types.Part.from_bytes`, `types.SafetySetting`, `types.GenerateContentConfig(safety_settings=...)`,
and `Attachment.content_type`/`Attachment.size` metadata reads.

The single most important architectural finding: **the existing `chat()` return contract already
maps cleanly onto VIS-02's silent-skip requirement, but `_generate_ambient_roast`'s *wrapper*
contract does not.** `GeminiService.chat()` never raises on a safety block or an empty response —
it returns `None` in both cases (confirmed by `GenerateContentResponse.text`/`_get_text()` source:
returns `None` when there are no candidates/parts, no exception). Only genuine transport failures
(429 rate limit, network/server error, priority-2 limiter timeout) raise
`GeminiRateLimitError`/`GeminiAPIError`. This means the *service* layer already distinguishes
"safety-blocked-or-empty" (silent `None`) from "transport failure" (exception) with zero new code.
The bug is one layer up: `_generate_ambient_roast` (`cogs/events.py:95-201`) currently treats
**both** of those cases identically — a falsy `chat()` result **and** a caught exception both fall
through to `return fallback_line` (the template pool). Reusing it unmodified for vision, as D-04's
prose suggests ("extending it with an image Part"), would silently violate VIS-02: a safety-blocked
image would get a visible template reply exactly like a rate-limited one. The fix is a return-shape
change (`str | None` instead of always-`str`) gated behind a new keyword-only flag, or a small
dedicated sibling function — see Architecture Patterns and Common Pitfalls below for both options
and the recommended one.

Gemini's default safety posture for 2.5/3-series models is **officially confirmed OFF** (not
merely assumed) via `ai.google.dev/gemini-api/docs/safety-settings`: *"If the threshold is not
set, the default block threshold is Off for Gemini 2.5 and 3 models."* This upgrades the
CONTEXT.md/CLAUDE.md claim from assumption to CITED fact and validates D-01's premise that `/ask`
and `/imagine` are today running with no safety filtering at all.

A concrete, non-obvious finding that affects D-03's mime allowlist: **Gemini's image-understanding
endpoint does not accept `image/gif`** (official docs list PNG/JPEG/WEBP/HEIC/HEIF only; multiple
independent sources confirm a GIF upload 400s). CONTEXT.md D-03 explicitly says "planner may trim"
the allowlist — this research recommends trimming `image/gif` out entirely, since every GIF
attachment would otherwise burn a real priority-2 Gemini call that is guaranteed to fail with a
`GeminiAPIError`, which then (correctly, but wastefully) fires the transport-failure template on
every single animated-image post.

**Primary recommendation:** Thread a shared `_build_safety_settings(threshold)` helper into all
three `generate_content` config sites; give the vision call a real-block threshold and `/ask`/
`/imagine` a permissive one; add an optional image-carrying path to `GeminiService.chat()` (append
a `types.Part.from_bytes` to the contents); write a **new** cog-glue generator (or a
`safety_sensitive=True` branch of `_generate_ambient_roast`) whose return type is `str | None` so a
safety-block/empty-response maps to "send nothing" while a caught `GeminiRateLimitError`/
`GeminiAPIError` maps to "send the fallback template"; trim `image/gif` from the mime allowlist;
detect blocks via `response.prompt_feedback.block_reason` / `candidates[0].finish_reason ==
types.FinishReason.SAFETY` for logging only — the actual dispatch decision does not need to
distinguish "why empty," only "exception vs. no-exception."

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Safety-settings scope (VIS-03) — D-01 (Claude recommendation, adopted on user's behalf):**
Retrofit ALL THREE user-influenced surfaces — the vision call AND `/ask` + `/imagine`. Gemini 2.5
defaults safety OFF, so `/ask`/`/imagine` are unguarded today. Do it once, in a shared helper
(`services/gemini.py`), threaded into every `generate_content` config. Threshold differs by
surface: **vision** uses a real BLOCK threshold (a block yields a silent skip, D-03/VIS-02);
**`/ask` + `/imagine`** get explicit-but-permissive thresholds (block only the most severe
categories) so Dex's existing edgy/roasty behavior is not regressed. Exact `HarmBlockThreshold`
per category is planner discretion.

**Trigger surface (VIS-01) — D-02 (Claude recommendation, adopted on user's behalf):** Image
ATTACHMENTS only; on a multi-image message, roast the FIRST valid image. Evaluate in `on_message`
(designated channel, non-bot author — guards already present at `cogs/events.py:377-402`) over
`message.attachments`, selecting attachments whose `content_type` starts with `image/` and is in
the allowlist. Discord exposes `attachment.content_type`/`attachment.size` without downloading —
the guard is a pure metadata check; only a passing attachment is fetched (via `attachment.read()`)
into `types.Part.from_bytes`. Pasted image URLs/embeds are excluded (SSRF + no pre-download size).

**App-level hard-rule layer (VIS-02) — D-03 (Claude recommendation, adopted on user's behalf):**
The hard rule = structural gate + a personality conduct clause, and it honors the shared Phase 16
opt-out.
1. **Structural gate** (pre-Gemini, hard reject → silent skip): `content_type` must be in a mime
   allowlist (`image/png`, `image/jpeg`, `image/webp`, `image/gif` — planner may trim); `size` ≤
   `MAX_VISION_IMAGE_BYTES`. Fails → never call Gemini.
2. **Conduct clause** (in the vision system prompt): roast the image's content/vibe/subject
   matter; never comment on a real person's face, body, weight, or perceived identity; if the
   image is primarily a person, keep it about the scene, not their appearance.
3. **Model-level `safety_settings`** (D-01) catch genuinely harmful/policy content; any block →
   silent skip: return nothing, do not `.reply`, do NOT route through the generic
   rate-limit/API-down template.
4. **Shared opt-out:** a user who ran `/memory callbacks off` (Phase 16 `proactive_opt_out`) is
   also spared vision roasts. No new opt-out flag/column/subcommand for v1.3.

**Reaction shape & cadence (VIS-01) — D-04 (Claude recommendation, adopted on user's behalf):** A
Gemini-framed TEXT reply, reusing the Phase 16 reply-anchored path, gated by its own chance +
per-user cooldown.
- Text reply, not emoji — post as a reply to the triggering message with `AllowedMentions.none()`,
  lowercase/length enforced, Gemini-first with a guaranteed template fallback on rate-limit/API
  error — the `_generate_ambient_roast`-style pipeline, extended to pass an image `Part`.
  **Exception:** a safety block is NOT a fallback case — it is a silent skip. Fallback templates
  cover transport failures only.
- Own cadence knobs: a new `VISION_ROAST_CHANCE` (rarer; planner picks ≈0.10-0.15, tunable) + a
  per-user `VISION_ROAST_COOLDOWN_SECONDS`, mirroring `self._roast_cooldowns`
  (`cogs/events.py:34`). Independent of the ambient/proactive gates — a fourth distinct surface.
- **Priority-2** on the shared 15 RPM `_RateLimiter` — background/unprompted, must yield to user
  commands and fall back (not block) on a priority-2 timeout.
- Pure-logic gate: `logic/vision.py::should_fire_vision_roast(*, chance_roll, chance,
  cooldown_elapsed, opted_out, ...) -> bool`, keyword-only, `random`/`datetime`/`discord`-free,
  mirroring `logic/proactive.py::should_fire_proactive_callback`. Glue computes rolls/cooldowns/
  opt-out and dispatches on the result; size/mime/attachment I/O stays in glue.

### Claude's Discretion

- Exact numeric knobs — `MAX_VISION_IMAGE_BYTES`, `VISION_ROAST_CHANCE`,
  `VISION_ROAST_COOLDOWN_SECONDS`, mime allowlist contents, per-category `HarmBlockThreshold`
  values for each of the three surfaces. Chance strictly below the ambient 0.30/0.35 cadences.
- `safety_settings` helper shape — module-level constant list vs. a builder taking a per-surface
  threshold; either is fine so long as all three `generate_content` configs thread it and vision
  gets the real-block threshold.
- How a safety block is detected — `response.prompt_feedback.block_reason`,
  `candidate.finish_reason == SAFETY`, and/or an empty-parts response; planner picks the robust
  check. All map to "return None → glue silently skips."
- Cog placement of the trigger glue — fold into `EventsCog.on_message` vs. a dedicated
  `_maybe_fire_vision_roast` method; lean toward a dedicated method.
- Vision system prompt — reuse `build_chat_prompt` with an added image part, or a small dedicated
  vision prompt builder in `personality/prompts.py`; either, as long as the conduct clause is
  present.
- Daily-cap-vs-cooldown — planner may add a per-user/day cap too (belt-and-suspenders) if cheap.

### Deferred Ideas (OUT OF SCOPE)

- Vision reactions feeding RAG memory → v2 (MEM-R2) — needs its own safety-gate design before an
  image-derived fact touches the memory store. The vision roast is fire-and-forget: no
  `remember()` write.
- Pasted image URLs/embeds as a trigger — D-02 scopes to attachments only (SSRF + no
  pre-download size).
- A dedicated vision opt-out distinct from the Phase 16 proactive opt-out — D-03 reuses the shared
  unprompted-surface control.
- Emoji reaction on images (alongside/instead of the text roast) — D-04 chose text.
- Batch/multi-image roasting — D-02 roasts the first valid image only.
- Any polling loop or DM delivery — permanently out (Phase 16 anti-creepy discipline).
- New dependency, new table, new limiter, new memory `kind`, or a manual-avatar code path.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VIS-01 | Cadence-gated (chance + per-user cooldown + priority-2) image reaction/roast, with a `MAX_VISION_IMAGE_BYTES` size guard and mime-type check **before download** | `Part.from_bytes` usage confirmed (Code Examples); Discord `Attachment.content_type`/`.size` confirmed readable without `.read()` (Code Examples, Sources); priority-2 `_RateLimiter.acquire()` mechanics already documented in `services/gemini.py` (no change needed, only a new call site); `logic/vision.py` gate design mirrors `logic/proactive.py` exactly (Architecture Patterns) |
| VIS-02 | Two-layer safety (explicit `safety_settings` + app-level hard rule); a safety block silently skips, never routed through the generic rate-limit/API-down template | Detection recipe (block_reason / finish_reason==SAFETY) confirmed via official docs + Context7 (Code Examples); the critical `chat()` vs. `_generate_ambient_roast` contract mismatch identified and a concrete fix proposed (Architecture Patterns, Common Pitfalls); GIF-format rejection finding (Common Pitfalls) closes a silent-failure gap in the structural gate |
| VIS-03 | `safety_settings` applied consistently to every Gemini call that can receive user-influenced content | Shared `_build_safety_settings(threshold)` helper design (Code Examples); confirmed HarmCategory/HarmBlockThreshold enum values (Standard Stack); confirmed Gemini 2.5 default is OFF (Summary, Sources) — validates the premise that `/ask`/`/imagine` need the retrofit |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Language/stack lock:** Python 3.11+, `discord.py` ≥2.3 (`AutoShardedBot`), Google Gemini via
  `google-genai` (free tier, `gemini-2.5-flash`) — vision must use the same model, no new client.
- **Critical Rule 1:** All AI features share the 15 RPM Gemini limit — the vision call MUST use
  the existing `_rate_limiter` at priority 2, never a new limiter and never the separate 60 RPM
  embed limiter (Critical Rule 11 reaffirms embeddings stay isolated — vision is a chat-budget
  consumer, not an embedding one).
- **Critical Rule 12 / accuracy firewall:** memory is roast ammo, not a number source — irrelevant
  to vision directly, but the phase must not introduce any live-SQL-number-in-vision-prompt
  pattern; N/A here since vision is memory-free by design (D-02/deferred MEM-R2).
- **One emoji max per message; lowercase everything** — the vision roast text output must be
  post-processed identically to `_generate_ambient_roast`'s existing enforcement (strip, lowercase
  first char, ≤500 chars per `MAX_AI_RESPONSE_LENGTH`/similar cap).
- **`logic/` pure-seam convention:** nondeterminism (chance rolls, cooldowns, opt-out) computed in
  glue and passed as primitives into a keyword-only, `random`/`datetime`/`discord`-free function in
  `logic/`, locked by mock-free tests (Phase 10 convention, reaffirmed Phase 16).
- **`asyncio.TimeoutError` caught before generic `except Exception`** — REL-04 gotcha; relevant if
  the vision glue adds any new `asyncio.wait_for`-wrapped call (unlikely needed here since
  `_RateLimiter.acquire` already handles its own timeout logic internally).
- **`AllowedMentions.none()` + reply-anchored** on every unprompted send — the vision roast reply
  must follow this exactly (D-04 explicit).
- **No new pip dependency** (Out of Scope table, `.planning/REQUIREMENTS.md`) — confirmed
  achievable; `google-genai` 2.8.0 and `discord.py` 2.7.1 (both already installed) cover 100% of
  this phase's needs.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Image attachment detection + before-download mime/size guard | API/Backend (Discord event glue, `cogs/events.py`) | — | Pure metadata read on `discord.Attachment`; no I/O, no external call — belongs in the same tier as the existing `on_message` guards |
| Cadence gate (chance + cooldown + opt-out) | API/Backend (`logic/vision.py` pure module) | — | Deterministic decision logic, same tier as `logic/proactive.py`/`logic/roasts.py`; explicitly `discord`/`random`/`datetime`-free so it is unit-testable without any Discord or network context |
| Attachment byte fetch (`attachment.read()`) | API/Backend (Discord event glue) | — | Only occurs after the structural gate passes; Discord's CDN is the source, not user-controlled arbitrary URL (SSRF closed by D-02's attachments-only scope) |
| Vision `generate_content` call (image + text prompt) | API/Backend (`services/gemini.py`, external Gemini API) | — | Same tier as existing `chat()`/`generate_image()` — a thin wrapper around the Google Gen AI SDK, no business logic |
| `safety_settings` configuration | API/Backend (`services/gemini.py` shared helper) | — | Cross-cutting hardening applied at the one place all three `generate_content` calls originate |
| Safety-block / transport-failure dispatch (silent-skip vs. template-fallback) | API/Backend (cog glue, new/extended generator function) | — | Business-logic decision about *what to do* with the service-layer result; belongs beside `_generate_ambient_roast`, not inside `services/gemini.py` (which stays a thin, personality-free wrapper per its own module docstring) |
| Reply delivery (`message.reply(..., allowed_mentions=...)`) | API/Backend (Discord.py client, `cogs/events.py`) | — | Standard Discord bot response path, same tier as every other unprompted send in this codebase |
| Personality/conduct clause (roast the image, not the person) | API/Backend (`personality/prompts.py` or an added vision prompt builder) | — | Prompt text is backend-authored content sent to the LLM, not client-rendered — same tier as `DEXTER_SYSTEM_PROMPT` |

*(No Browser/Client, Frontend-SSR, CDN/Static, or Database/Storage tier work exists in this
phase — Dexter has no client-side surface, and D-02/deferred-MEM-R2 explicitly keep vision
memory-free, so no new Database/Storage tier touch either.)*

## Standard Stack

### Core

| Library | Version (installed) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `google-genai` | 2.8.0 `[VERIFIED: pip show / python import]` | Gemini API client — `types.Part.from_bytes`, `types.SafetySetting`, `types.GenerateContentConfig` | Already the project's sole Gemini SDK (Phase 2/11); no alternative considered — CLAUDE.md tech-stack lock |
| `discord.py` | 2.7.1 `[VERIFIED: python import]`, requirements.txt pins `>=2.3.0` | `discord.Attachment.content_type`/`.size`/`.read()`, `discord.AllowedMentions` | Already the project's sole Discord framework; attachment metadata API unchanged since well before 2.3 |

**No new packages required for this phase.** Both libraries above are already installed and
pinned; this is a code-only phase.

**Version verification:**
```bash
pip show google-genai discord.py   # confirms 2.8.0 / (import) 2.7.1 present in the venv
python -c "import discord; print(discord.__version__)"       # 2.7.1
python -c "import google.genai; ..."                          # 2.8.0
```

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `types.Part.from_bytes` (inline base64 image data) | `types.Part.from_uri` (GCS URI) | Not applicable — Discord attachments are not in GCS; inline bytes is the only path for user-uploaded content, and it is the documented pattern for local/in-memory image data (Context7-confirmed) |
| App-level structural mime/size gate + model `safety_settings` | Pillow/`imghdr`-style deep image validation (magic-byte sniffing) | Rejected — no new dependency allowed (Out of Scope table); Gemini's own decode is the backstop for content-type spoofing (see Common Pitfalls) |

## Package Legitimacy Audit

**Not applicable — this phase installs zero new external packages.** Both dependencies used
(`google-genai`, `discord.py`) are pre-existing, already-pinned project dependencies (see Standard
Stack above). No `pip install`/`slopcheck`/registry-verification steps are required. If the
planner discovers a need for any new package during planning, that would itself be a violation of
the "No new pip dependency" project constraint (CLAUDE.md / REQUIREMENTS.md Out of Scope) and
should be escalated, not silently added.

## Architecture Patterns

### System Architecture Diagram

```
Discord message posted in DEXTER_CHANNEL_ID
        │
        ▼
EventsCog.on_message()                              (existing, cogs/events.py:377-402)
   │  ├─ message buffer feed (unchanged)
   │  ├─ reaction/deflection handling (unchanged)
   │  ├─ _maybe_fire_proactive_callback (existing, unchanged)
   │  └─ _maybe_fire_vision_roast(message)  ◄────────── NEW dispatch, same designated-channel guard
        │
        ▼
_maybe_fire_vision_roast (NEW, mirrors _maybe_fire_proactive_callback structure)
   │
   ├─ 1. opt-out check ─────────► database.get_proactive_opt_out(pool, user_id)   (REUSED, no new column)
   │        │ opted_out=True → return (no further work)
   │        ▼
   ├─ 2. structural gate (pure metadata, no I/O):
   │        for attachment in message.attachments:
   │            content_type startswith "image/" AND in mime allowlist
   │            AND size <= MAX_VISION_IMAGE_BYTES
   │        → first passing attachment, else return (no images qualify)
   │        ▼
   ├─ 3. pure cadence gate ─────► logic.vision.should_fire_vision_roast(
   │                                  opted_out=..., chance_roll=random.random(),
   │                                  cooldown_elapsed=..., ...) -> bool   (NEW, mirrors logic/proactive.py)
   │        │ False → return (no roast this time)
   │        ▼
   ├─ 4. fetch bytes ───────────► image_bytes = await attachment.read()   (only after every gate passes)
   │        ▼
   ├─ 5. build vision prompt ───► conduct-clause system prompt (D-03 step 2) +
   │                              types.Part.from_bytes(data=image_bytes, mime_type=attachment.content_type)
   │        ▼
   ├─ 6. call Gemini (priority=2, real-block safety_settings) ──► services/gemini.py
   │        │
   │        ├─ SUCCESS + non-empty text  → the roast line
   │        ├─ SUCCESS + empty/blocked text (None) → SILENT SKIP (no send, no counter bump)  [VIS-02]
   │        └─ GeminiRateLimitError / GeminiAPIError (transport) → fallback template line     [D-04]
   │        ▼
   └─ 7. message.reply(line, allowed_mentions=discord.AllowedMentions.none(), mention_author=False)
            (only reached if step 6 produced a line — the SILENT SKIP branch returns before this)
```

### Recommended Project Structure

```
logic/
└── vision.py                  # NEW — should_fire_vision_roast pure gate (mirrors logic/proactive.py)
cogs/
└── events.py                  # EXTENDED — _maybe_fire_vision_roast + on_message dispatch line
services/
└── gemini.py                  # EXTENDED — _build_safety_settings helper, image-carrying chat() path
                                #            (or a small new vision-specific method), safety_settings
                                #            threaded into chat()/generate_image() configs
personality/
└── prompts.py                 # EXTENDED (optional) — vision conduct-clause prompt builder
config.py                      # EXTENDED — MAX_VISION_IMAGE_BYTES, VISION_ROAST_CHANCE,
                                #            VISION_ROAST_COOLDOWN_SECONDS, mime allowlist,
                                #            per-surface HarmBlockThreshold constants
tests/
├── test_vision_logic.py       # NEW — mock-free should_fire_vision_roast boundary/rarity tests
├── test_gemini.py             # EXTENDED — safety_settings threading + block detection (mocked)
└── test_vision_events.py      # NEW — behavioral glue tests (mirrors test_proactive_events.py)
```

### Pattern 1: Shared `safety_settings` helper threaded into every user-influenced call

**What:** A single function in `services/gemini.py` that builds a `list[types.SafetySetting]` for
a given threshold, used identically by `chat()`, `generate_image()`, and the vision call.
**When to use:** Any `generate_content`/`generate_images` call whose prompt or input can be
influenced by a Discord user (this is exactly what VIS-03 means by "consistently").
**Example:**
```python
# Source: Context7 /googleapis/python-genai (SafetySetting/GenerateContentConfig usage,
# verified against README.md + docs/_sources/index.rst.txt)
from google.genai import types

_VISION_SAFETY_CATEGORIES = (
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
)  # confirmed adjustable set per ai.google.dev/gemini-api/docs/safety-settings; child-safety
   # protections are separately always-on and NOT configurable via safety_settings.

def _build_safety_settings(threshold: str) -> list[types.SafetySetting]:
    """Build an explicit SafetySetting list at a uniform threshold across all adjustable
    categories. threshold is one of the HarmBlockThreshold string values:
    'BLOCK_LOW_AND_ABOVE' | 'BLOCK_MEDIUM_AND_ABOVE' | 'BLOCK_ONLY_HIGH' | 'BLOCK_NONE' | 'OFF'.
    """
    return [
        types.SafetySetting(category=cat, threshold=threshold)
        for cat in _VISION_SAFETY_CATEGORIES
    ]
```
Threaded at each call site:
```python
config=types.GenerateContentConfig(
    system_instruction=system_prompt,
    safety_settings=_build_safety_settings(config.VISION_SAFETY_THRESHOLD),   # real block, e.g. BLOCK_MEDIUM_AND_ABOVE
)
# vs. /ask and /imagine:
config=types.GenerateContentConfig(
    system_instruction=system_prompt,
    safety_settings=_build_safety_settings(config.TEXT_SAFETY_THRESHOLD),     # permissive, e.g. BLOCK_ONLY_HIGH
)
```

### Pattern 2: Image input via `Part.from_bytes` composed with a text prompt

**What:** Passing image bytes + a text instruction in one `generate_content` call.
**When to use:** The vision roast call.
**Example:**
```python
# Source: Context7 /googleapis/python-genai
# (docs/index.html "Generate Content ... for Image from Local File"; types.py source)
from google.genai import types

contents = [
    conduct_clause_prompt_text,   # plain str, or types.Part.from_text(text=...)
    types.Part.from_bytes(data=image_bytes, mime_type=attachment_mime_type),
]
response = await client.aio.models.generate_content(
    model=config.GEMINI_MODEL,      # gemini-2.5-flash — same model as chat()/no new model
    contents=contents,
    config=types.GenerateContentConfig(
        system_instruction=vision_system_prompt,
        safety_settings=_build_safety_settings(config.VISION_SAFETY_THRESHOLD),
    ),
)
```
Note `mime_type` here is the attachment's own `content_type` (already validated against the
allowlist in the structural gate) — do not re-derive it from file bytes; Gemini decodes and
validates the actual bytes server-side (see Don't Hand-Roll).

### Pattern 3: Silent-skip vs. template-fallback dispatch (the VIS-02 contract)

**What:** A generator whose return type is `str | None`, not always-`str`.
**When to use:** Any unprompted surface with a hard "no visible refusal" requirement (currently
only vision; ambient/proactive roasts do NOT have this requirement and should stay unchanged).
**Example (Option A — dedicated function, no change to `_generate_ambient_roast`):**
```python
async def _generate_vision_roast(
    self, message: discord.Message, image_bytes: bytes, mime_type: str,
    fallback_pool: list[str],
) -> str | None:
    """Returns the roast line, a transport-failure fallback line, or None
    (safety-blocked or genuinely empty response) — caller sends only if not None."""
    gemini_service = getattr(self.bot, "gemini_service", None)
    if gemini_service is None:
        return None   # no service configured — silent skip, not a fallback (no user-facing gap either way)

    system_prompt = build_vision_prompt()   # conduct clause (D-03 step 2)
    try:
        result = await gemini_service.vision_chat(   # or chat(..., image_bytes=..., image_mime_type=...)
            system_prompt, image_bytes, mime_type, priority=2,
        )
    except GeminiRateLimitError:
        return pick_random(fallback_pool)     # transport failure -> template fallback (D-04)
    except GeminiAPIError:
        return pick_random(fallback_pool)     # transport failure -> template fallback (D-04)

    if not result:
        return None    # safety-blocked OR genuinely empty -> silent skip (VIS-02), NOT the fallback pool

    result = result.strip()
    if result and result[0].isupper():
        result = result[0].lower() + result[1:]
    return result[:497] + "..." if len(result) > 500 else result
```
**Example (Option B — extend `_generate_ambient_roast` with a flag):** add a keyword-only
`safety_sensitive: bool = False` param; when `True`, the final `return fallback_line` at the
bottom of the function becomes `return None` instead, while the two `except` clauses still return
`fallback_line`. This keeps one source of truth for the lowercase/length enforcement, at the cost
of a slightly more branchy shared function. **Either is acceptable; Option A is recommended** for
clarity given how safety-critical the distinction is — a shared function with a boolean silently
controlling "does an exception path differ from a success-but-empty path" is an easy place for a
future edit to reintroduce the bug this phase is designed to prevent.

### Pattern 4: Pure cadence gate mirrors `logic/proactive.py` exactly

**What:** `logic/vision.py::should_fire_vision_roast`.
**Example:**
```python
# Source: mirrors logic/proactive.py::should_fire_proactive_callback (Phase 16 pattern)
from __future__ import annotations
import config

def should_fire_vision_roast(
    *,
    opted_out: bool,
    chance_roll: float,
    cooldown_elapsed: bool,
    chance: float = config.VISION_ROAST_CHANCE,
) -> bool:
    """Gate 1: opt-out (cheapest, wins). Gate 2: per-user cooldown must have elapsed.
    Gate 3: chance roll must be strictly below chance. All three true -> fire."""
    if opted_out:
        return False
    if not cooldown_elapsed:
        return False
    if chance_roll >= chance:
        return False
    return True
```
Glue computes `cooldown_elapsed` via the existing `logic.roasts.cooldown_elapsed(seconds_since_last,
ceiling)` helper (reused, not reinvented) against a new `self._vision_roast_cooldowns: dict[int,
float]` dict mirroring `self._roast_cooldowns`.

### Anti-Patterns to Avoid

- **Reusing `_generate_ambient_roast` unmodified for vision:** its always-returns-a-string contract
  cannot distinguish "safety blocked" from "rate limited," which is exactly the distinction VIS-02
  requires. See Pattern 3.
- **Sniffing image bytes with a hand-rolled magic-number check:** no new dependency is allowed, and
  Gemini's own decode is a sufficient backstop for content-type spoofing (see Don't Hand-Roll).
  Don't add PIL-free magic-byte parsing code either — it's unnecessary complexity for a problem the
  API already handles safely (a garbage upload either 400s — `GeminiAPIError` → template fallback —
  or decodes fine, in which case the "spoofed" content_type didn't matter).
- **Including `image/gif` in the mime allowlist:** Gemini's image-understanding endpoint does not
  accept GIF (PNG/JPEG/WEBP/HEIC/HEIF only per official docs) — every GIF post would burn a
  guaranteed-to-fail priority-2 call. Trim it (D-03 explicitly allows this).
- **Distinguishing safety-block reasons in the *dispatch* logic:** the glue only needs to know
  "did an exception fire, yes/no" — it does not need to parse `block_reason`/`finish_reason` to
  decide silent-skip-vs-fallback (both non-exception outcomes are silent-skip). Reserve the
  granular block-reason inspection for `log.debug` observability only, not for control flow.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Detecting a Gemini safety block | A custom heuristic scanning response text for refusal phrases | `response.prompt_feedback.block_reason` (prompt-level) / `response.candidates[0].finish_reason == types.FinishReason.SAFETY` (response-level) — or simply "did `chat()`/the vision call raise, yes/no" for the dispatch decision itself | The SDK already surfaces this structurally; text-sniffing for refusal phrases is exactly the kind of brittle heuristic that breaks on wording changes and is unnecessary here |
| Image content validation beyond mime/size | Magic-byte/`imghdr`-style sniffing, a mini image-decoding library | The existing structural gate (content_type allowlist + size cap) as the app-level layer, plus Gemini's own server-side decode as the backstop (a spoofed-but-undecodable file 400s → `GeminiAPIError` → template fallback path, already a defined outcome) | No new dependency allowed; a genuinely malformed image either decodes (fine — Gemini is the authority on "is this really an image") or fails the API call (already handled) |
| Priority-tiered rate limiting for the vision call | A second rate limiter or a bespoke queue for background vision calls | The existing `_RateLimiter` at `priority=2` (`services/gemini.py:34-103`) — already implements the exact "wait if room, reject-with-exception if a priority-2 wait would exceed 10s" semantics this phase needs | Zero new code; this is precisely what the existing limiter's priority tiers were built for (Phase 9/11 precedent) |

**Key insight:** Every "hard part" of this phase (safety detection, rate limiting, cadence gating)
already has a working, tested analog in the codebase (`chat()`'s exception contract, `_RateLimiter`,
`logic/proactive.py`). The actual net-new code is small: one image-Part-carrying call site, one
shared safety_settings helper, one pure gate module, and one return-contract fix.

## Common Pitfalls

### Pitfall 1: Reusing `_generate_ambient_roast`'s contract silently breaks VIS-02

**What goes wrong:** A safety-blocked image produces the exact same visible template-fallback
reply as a rate-limited one, because both non-success paths in the existing function converge on
`return fallback_line`.
**Why it happens:** `_generate_ambient_roast` was designed for a surface (ambient/proactive roasts)
that has no silent-skip requirement — "no output beats a wrong output" wasn't a design constraint
there, so a template fallback was always an acceptable substitute for "Gemini didn't give me
anything."
**How to avoid:** Use a dedicated generator (or an explicit `safety_sensitive` branch) whose
success-but-empty path returns `None`, distinct from its exception-caught path, which still returns
the fallback template. See Architecture Patterns, Pattern 3.
**Warning signs:** A test that asserts "safety-blocked image → no message sent" fails because the
glue sent a fallback template instead.

### Pitfall 2: `image/gif` allowlisted but unsupported by Gemini

**What goes wrong:** Every animated-GIF post burns a real Gemini API call that 400s
(`GeminiAPIError`), then fires the transport-failure template — technically VIS-02-compliant
(it's a real transport failure, not a safety block) but wasteful and a confusing UX (a "couldn't
process that" line on every single GIF, forever).
**Why it happens:** GIF is a commonly-assumed "image format," and CONTEXT.md's suggested allowlist
literally lists it (while noting "planner may trim").
**How to avoid:** Trim `image/gif` from `MIME` allowlist at plan time. Gemini's documented supported
input image types are PNG, JPEG, WEBP, HEIC, HEIF — not GIF.
**Warning signs:** Repeated `GeminiAPIError` log lines correlating with `.gif` attachments in
production.

### Pitfall 3: `content_type` may carry parameters, not just a bare MIME type

**What goes wrong:** An allowlist equality check (`attachment.content_type in ALLOWED`) can fail
for a value like `"image/jpeg; charset=utf-8"` even though the file is a perfectly valid JPEG,
because Discord's stored `content_type` mirrors the raw uploaded `Content-Type` header, which can
in principle carry parameters.
**Why it happens:** `Content-Type` is an HTTP header value, not a normalized enum, on the wire.
**How to avoid:** Normalize before comparing: `(attachment.content_type or "").split(";")[0].strip().lower()`.
Also guard the `None` case explicitly — `content_type` is `Optional[str]` and Discord does not
guarantee it is populated for every attachment (treat `None` as reject, per D-02).
**Warning signs:** A locally-tested "clean JPEG" attachment intermittently fails the gate depending
on how the client that uploaded it set the header.

### Pitfall 4: Inline base64 request-size limit vs. Discord's attachment size limit

**What goes wrong:** `MAX_VISION_IMAGE_BYTES` is set close to Discord's own attachment ceiling
(8-25MB depending on server boost tier) without accounting for the Gemini inline-data combined
request limit of 20MB (text + system instruction + base64-inflated image bytes, per official docs)
— base64 encoding inflates raw bytes by roughly 33%, so a 15MB raw image becomes ~20MB encoded,
potentially exceeding the ceiling together with prompt text.
**Why it happens:** The two limits (Discord's upload cap and Gemini's inline-request cap) are
independent and easy to conflate.
**How to avoid:** Set `MAX_VISION_IMAGE_BYTES` with real headroom below 20MB raw-bytes-equivalent —
a value in the 5-10MB range comfortably avoids the combined-request ceiling even after base64
inflation and leaves room for the system prompt text.
**Warning signs:** Large-but-under-Discord-limit images intermittently fail with an API error that
mentions request/payload size.

### Pitfall 5: Vision roast cadence contending with `/ask`/proactive on the shared 15 RPM budget

**What goes wrong:** Adding a fourth priority-2 consumer to the same 15 RPM window increases the
odds that `/ask` (priority 1) has to wait for a slot during high-traffic bursts, even though
priority ordering technically protects it (priority 1 always waits for a slot rather than being
rejected — it just may queue longer if priority-2 traffic saturates the window immediately before
a user command).
**Why it happens:** More background consumers on a shared, small (15 RPM) budget compounds queuing
delay, even without breaking the priority contract.
**How to avoid:** Keep `VISION_ROAST_CHANCE` low (< 0.15 recommended, well below ambient 0.30/0.35)
and combine chance + per-user cooldown so the realistic firing rate stays far below what would
meaningfully contend with the existing ambient (0.30/0.35) + proactive (0.10) background consumers
already sharing this budget.
**Warning signs:** `/stats`' Gemini quota panel (`rpm_usage`/`rpm_headroom`, Phase 6 D-24) showing
sustained near-ceiling usage correlating with vision-roast activity.

## Code Examples

### Detection recipe for a safety-blocked or empty vision response

```python
# Source: Context7 /googleapis/python-genai (GenerateContentResponse._get_text source;
# GenerateContentResponsePromptFeedback docs) + ai.google.dev/gemini-api/docs/safety-settings
# ("Prompt blocked: promptFeedback.blockReason is set. Response blocked: Candidate.finishReason
# equals SAFETY.")

# response.text already returns None (no exception) in EITHER of these cases:
#   (a) response.prompt_feedback.block_reason is set (prompt itself blocked pre-generation)
#   (b) response.candidates[0].finish_reason == types.FinishReason.SAFETY (response blocked)
#   (c) candidates exist but content.parts is empty/non-text for any other reason
#
# For the DISPATCH decision (silent-skip vs. template-fallback), you do not need to
# distinguish (a)/(b)/(c) from each other -- all three collapse to "result is falsy, no
# exception was raised" -> silent skip. Reserve the finer-grained check for logging only:

if not result:
    if response.prompt_feedback and response.prompt_feedback.block_reason:
        log.debug("vision roast: prompt blocked (%s)", response.prompt_feedback.block_reason)
    elif response.candidates and response.candidates[0].finish_reason == types.FinishReason.SAFETY:
        log.debug("vision roast: response blocked (SAFETY)")
    else:
        log.debug("vision roast: empty response, no block signal")
    return None  # silent skip either way
```

### Discord attachment before-download guard

```python
# Source: discordpy.readthedocs.io API reference (Attachment.content_type: Optional[str],
# Attachment.size: int) — both populated from message payload metadata, no network read()
# required. Verified via WebSearch cross-referencing discord.py source (message.py) +
# discordpy.readthedocs.io/en/latest/api.html.

ALLOWED_VISION_MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})  # NOT image/gif — see Pitfall 2

def _first_valid_image_attachment(message: discord.Message) -> discord.Attachment | None:
    for attachment in message.attachments:
        content_type = (attachment.content_type or "").split(";")[0].strip().lower()
        if content_type not in ALLOWED_VISION_MIME_TYPES:
            continue
        if attachment.size > config.MAX_VISION_IMAGE_BYTES:
            continue
        return attachment  # first valid one (D-02) -- no bytes fetched yet
    return None

# Only after this returns non-None:
image_bytes = await attachment.read()   # the one and only network fetch
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `/ask`/`/imagine` run with implicit (unset) `safety_settings` | Gemini 2.5/3 default `safety_settings` to **OFF** when unset — confirmed current, not a recent change, but worth stating precisely: this is not "safe by default," it's "unfiltered by default" | Current for Gemini 2.5/3-series (official docs, checked 2026-07-03) | Confirms D-01's premise: `/ask`/`/imagine` today have zero model-level content filtering; the retrofit is a pure hardening add, not a behavior clamp, as long as thresholds stay permissive |
| Text-only Gemini calls in this codebase (`chat`, `embed`) | First multimodal (image+text) call in the codebase (`vision_chat`/extended `chat`) | New in Phase 17 | New call shape (`types.Part.from_bytes` composed with text) — verified current syntax via Context7, not from training-data memory |

**Deprecated/outdated:** None identified — `google-genai` 2.8.0 is the current unified SDK (the
prior `google-generativeai` package is the one that's deprecated/frozen, and this project already
uses the current `google-genai` package, confirmed by `requirements.txt`/`import google.genai`).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Exact numeric values for `MAX_VISION_IMAGE_BYTES`, `VISION_ROAST_CHANCE`, `VISION_ROAST_COOLDOWN_SECONDS` are planner/Claude discretion (per CONTEXT.md) — this research suggests directional bands (5-10MB, ≤0.15, cooldown mirroring `ROAST_COOLDOWN_SECONDS`-scale) but does not lock exact figures | Standard Stack / Pitfall 4 | Low — CONTEXT.md explicitly delegates these to the planner; a wrong initial value is a one-line config tune, not a design flaw |
| A2 | The `HARM_CATEGORY_CIVIC_INTEGRITY` category (present in some Vertex AI docs) is NOT part of the adjustable set for the Gemini Developer API — this research found only 4 adjustable categories (HARASSMENT, HATE_SPEECH, SEXUALLY_EXPLICIT, DANGEROUS_CONTENT) documented for `ai.google.dev` | Code Examples / Pattern 1 | Low-Medium — if the SDK's `HarmCategory` enum does expose a 5th adjustable value at implementation time, the shared helper should iterate `list(types.HarmCategory)` filtered to non-deprecated/non-unspecified values rather than a hardcoded tuple; recommend the planner verify with `python -c "from google.genai import types; print(list(types.HarmCategory))"` at implementation time before locking the tuple |
| A3 | The recommended "Option A: dedicated `_generate_vision_roast` function" vs. "Option B: flag-branch on `_generate_ambient_roast`" choice is left to the planner; this research recommends Option A but both satisfy VIS-02 if implemented correctly | Architecture Patterns, Pattern 3 | Low — both are functionally equivalent if the return-contract fix is applied; Option B risks a future edit re-coupling the two paths, Option A risks minor code duplication (prompt-building/post-processing) |

**A2 requires user/planner confirmation before being treated as locked** — everything else in
this research is either directly confirmed via Context7/official docs or explicitly delegated to
planner discretion by CONTEXT.md.

## Open Questions

1. **Does the vision system prompt reuse `build_chat_prompt` (with an appended image Part) or a
   dedicated builder?**
   - What we know: CONTEXT.md leaves this as Claude's/planner's discretion; either satisfies the
     conduct-clause requirement (D-03 step 2).
   - What's unclear: `build_chat_prompt` currently assembles a large few-shot text-only system
     prompt (`DEXTER_SYSTEM_PROMPT`) tuned for text conversation — whether the existing few-shot
     examples remain useful/relevant framing for "you are looking at an image" is untested.
   - Recommendation: a small dedicated vision prompt builder (in `personality/prompts.py`,
     following the `build_discover_commentary_prompt`/`build_jam_suggestion_prompt` pattern
     already in that file) that includes the conduct clause plus a short voice reminder, rather
     than reusing the full `DEXTER_SYSTEM_PROMPT` few-shot block verbatim — keeps prompt size down
     (relevant given the 20MB inline combined-size ceiling, Pitfall 4) and lets the conduct clause
     be unambiguous rather than buried in an unrelated few-shot block.

2. **Does `GeminiService` need a new dedicated method (`vision_chat`) or should `chat()` itself
   grow optional image parameters?**
   - What we know: both approaches are technically viable; `chat()` already accepts `priority` and
     builds a `GenerateContentConfig` — adding optional `image_bytes`/`image_mime_type`/
     `safety_settings` keyword params keeps one call site.
   - What's unclear: whether the existing `chat()` unit tests in `tests/test_gemini.py` assume a
     fixed signature that a new optional-kwarg addition might need to account for (should still be
     additive/backward-compatible since all new params are optional keyword-only).
   - Recommendation: extend `chat()` with optional keyword-only params rather than adding a
     parallel method — this keeps the `safety_settings` retrofit and the image-carrying path in
     one place, consistent with the "shared helper, one call site" spirit of D-01. If the planner
     finds this makes `chat()` too overloaded, a thin `vision_chat()` wrapper that calls `chat()`
     internally (not a fully separate implementation) is an acceptable alternative.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `google-genai` (Python package) | Vision call, safety_settings retrofit | ✓ | 2.8.0 `[VERIFIED]` | — |
| `discord.py` (Python package) | Attachment metadata, reply delivery | ✓ | 2.7.1 `[VERIFIED]` (requirements.txt pins `>=2.3.0`) | — |
| `GEMINI_API_KEY` (env var) | All Gemini calls including vision | Assumed present (existing `/ask`/`/imagine` already depend on it in production) | — | Bot already degrades gracefully when unset (`getattr(self.bot, "gemini_service", None)` guard pattern reused) |
| `config.DEXTER_CHANNEL_ID` (env var) | Designated-channel gate for the vision trigger | Assumed present (existing ambient/proactive surfaces already depend on it) | — | If unset, `on_message`'s existing gate (`config.DEXTER_CHANNEL_ID and message.channel.id == ...`) already no-ops — vision inherits this, no new fallback needed |

**Missing dependencies with no fallback:** None — both Python packages are already installed and
pinned; no new external dependency is introduced by this phase.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 `[VERIFIED: pip show pytest]` |
| Config file | none detected at repo root (no `pytest.ini`/`pyproject.toml` `[tool.pytest]` section) — tests run via `pytest tests/` with `tests/conftest.py` fixtures and `pytest.mark.asyncio` markers (existing convention, e.g. `tests/test_gemini.py`, `tests/test_proactive_events.py`) |
| Quick run command | `pytest tests/test_vision_logic.py tests/test_gemini.py tests/test_vision_events.py -x` |
| Full suite command | `pytest tests/` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VIS-01 | `should_fire_vision_roast` chance/cooldown/opt-out boundary truth table (mock-free) | unit | `pytest tests/test_vision_logic.py -x` | ❌ Wave 0 |
| VIS-01 | `VISION_ROAST_CHANCE` strictly below ambient (0.30) and callback (0.35) cadences — rarity invariant, mirroring `test_proactive_chance_is_rarer_than_ambient` | unit | `pytest tests/test_vision_logic.py::test_vision_chance_is_rarer_than_ambient -x` | ❌ Wave 0 |
| VIS-01 | Before-download mime/size structural gate rejects oversized/wrong-mime attachments without ever calling `attachment.read()` or Gemini | unit (mocked `discord.Attachment`, no live Discord) | `pytest tests/test_vision_events.py -k structural_gate -x` | ❌ Wave 0 |
| VIS-01 | Priority-2 call threads through `_RateLimiter.acquire(priority=2)` — reuse existing `tests/test_rate_limiter.py` coverage; only a new call-site assertion needed (mock `GeminiService._rate_limiter.acquire`) | unit (mocked) | `pytest tests/test_gemini.py -k vision_priority -x` | ❌ Wave 0 (new test in an existing file) |
| VIS-02 | Safety-blocked vision response (mocked `finish_reason=SAFETY` / `prompt_feedback.block_reason` set) → generator returns `None` → glue sends nothing, no counter/cooldown mutation | unit (mocked Gemini client, mirrors `tests/test_gemini.py` `patch("services.gemini.genai")` pattern) | `pytest tests/test_gemini.py -k safety_block -x` | ❌ Wave 0 |
| VIS-02 | Transport failure (`GeminiRateLimitError`/`GeminiAPIError`) on the vision call → generator returns the fallback template, DOES send a reply | unit (mocked) | `pytest tests/test_vision_events.py -k transport_fallback -x` | ❌ Wave 0 |
| VIS-02 | The generic rate-limit/API-down template pool used elsewhere is never reached by the safety-block path specifically (regression guard distinguishing the two non-fire outcomes) | unit (mocked, asserts `message.reply` NOT called on safety-block, IS called on transport-error with a template string) | `pytest tests/test_vision_events.py -k vis02_regression -x` | ❌ Wave 0 |
| VIS-03 | All three `generate_content` configs (`chat()`, `generate_image()`, vision call) carry non-`None` `safety_settings` in their `GenerateContentConfig` | unit (mocked, inspect the `config=` kwarg passed to `generate_content`) | `pytest tests/test_gemini.py -k safety_settings_threaded -x` | ❌ Wave 0 |
| VIS-03 | Vision surface uses the real-block threshold constant; `/ask`+`/imagine` use the permissive threshold constant (two distinct values, asserted by identity/equality, not just "non-None") | unit (mocked) | `pytest tests/test_gemini.py -k safety_settings_threshold_differs -x` | ❌ Wave 0 |
| VIS-03 | `/ask` and `/imagine` existing behavior is unregressed after the retrofit (permissive threshold does not newly block anything that passed before) | regression | existing `tests/test_gemini.py`, `tests/test_roast_command.py`-adjacent suites must stay green | ✅ (existing tests, re-run as regression gate) |

### Sampling Rate

- **Per task commit:** `pytest tests/test_vision_logic.py tests/test_gemini.py tests/test_vision_events.py -x`
- **Per wave merge:** `pytest tests/`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_vision_logic.py` — covers VIS-01 (pure gate boundary/rarity truth table)
- [ ] `tests/test_gemini.py` additions — covers VIS-02 (safety-block detection), VIS-03
      (safety_settings threading + threshold differentiation across all three call sites)
- [ ] `tests/test_vision_events.py` — covers VIS-01 (structural gate), VIS-02 (silent-skip vs.
      template-fallback dispatch), mirrors `tests/test_proactive_events.py`'s `_make_bot`/
      `_make_message` mock helpers (extend with a `_make_attachment(content_type, size)` helper)
- [ ] No shared fixtures beyond `tests/conftest.py` (existing) are anticipated as required

### Manual-Only (Human-Verify, Live-Discord)

Following the Phase 11/13/14/15/16 precedent — these cannot be code-verified and belong in a
`17-HUMAN-UAT.md` parked doc at phase close:
- The actual "feel" of the roast cadence in a live server (rarity, tone, whether it reads as
  "judging" vs. "a treat" per CONTEXT.md's Feel Target).
- A real image round-trip end-to-end (posting an actual photo/screenshot in the designated channel
  and observing a genuine Gemini vision response, as opposed to a mocked one).
- Confirming a genuinely safety-triggering image (if one is ever deliberately tested) produces
  zero visible trace in a live channel.
- Confirming `/ask`/`/imagine` personality is unregressed to a human ear, not just to existing
  automated assertions, after the safety_settings retrofit.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V5 Input Validation | Yes | Before-download mime-type allowlist + size cap on `discord.Attachment` metadata (structural gate); reject on any parse ambiguity (`content_type is None` → reject, D-02) |
| V12 File Handling | Yes | Attachment bytes are fetched only from Discord's own CDN (`attachment.read()`), never from an arbitrary user-supplied URL (D-02 explicitly excludes URL/embed triggers to close this SSRF path) |
| V4 Access Control | Partial | Opt-out check (`database.get_proactive_opt_out`) is a user-self-scoped preference, not an authorization boundary in the security sense — no privilege distinction needed here (any non-bot user in the designated channel can trigger the surface, same as every other ambient behavior in this codebase) |
| V2/V3 Auth/Session | No | No new auth surface — this phase adds no new command, no new session concept, purely a passive event listener |
| V6 Cryptography | No | No new cryptographic material handled |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| SSRF via user-controlled URL fetch | Information Disclosure / Elevation of Privilege | Attachments-only trigger (D-02) — Discord's own CDN serves the bytes, never an arbitrary user-supplied URL; explicitly rejected as out of scope |
| Resource exhaustion via oversized/repeated uploads | Denial of Service | `MAX_VISION_IMAGE_BYTES` pre-download size guard (checked against metadata, zero bytes fetched for a rejected attachment) + chance/cooldown cadence gate bounding call frequency + the shared 15 RPM limiter's priority-2 timeout-and-reject behavior |
| Content-type spoofing (metadata says image/png, bytes are something else) | Tampering | App-level gate trusts metadata for the *cheap* pre-download reject; Gemini's own server-side decode is the authoritative backstop post-fetch — a mismatched/malformed file either decodes fine (metadata was "wrong" but harmless) or 400s (`GeminiAPIError` → handled transport-failure path). No custom magic-byte sniffing needed (Don't Hand-Roll) |
| Prompt injection via image content (e.g., an image containing adversarial text instructing the model to ignore its conduct clause) | Tampering / Elevation of Privilege | The app-level conduct clause (D-03 step 2) plus model-level `safety_settings` are the two independent layers; this is inherent to any vision-input LLM feature and is exactly why VIS-02 mandates defense-in-depth (structural + model) rather than relying on either alone |
| PII/appearance-based harm from roasting a real person's photo | Tampering (of intended behavior)/reputational harm | Personality conduct clause explicitly instructs the model to roast content/vibe, never a real person's face/body/weight/identity (D-03 step 2) — this is a prompt-level control, not a technical filter, and is the phase's primary non-technical risk mitigation |

## Sources

### Primary (HIGH confidence)

- Context7 `/googleapis/python-genai` — `types.Part.from_bytes` signature and usage examples
  (image+text `generate_content` composition), `types.SafetySetting`/`GenerateContentConfig
  (safety_settings=...)` usage, `HarmBlockThreshold`/`HarmCategory`/`BlockedReason`/`FinishReason`
  enum descriptions, `GenerateContentResponse.text`/`_get_text()` exact source (confirms `None`
  return, no exception, on empty/blocked candidates).
- `ai.google.dev/gemini-api/docs/safety-settings` (fetched 2026-07-03) — full `HarmCategory`
  adjustable list (4 categories), full `HarmBlockThreshold` enum, explicit confirmation that
  Gemini 2.5/3 default block threshold is **Off** when unset, and the blocked-response detection
  recipe (`promptFeedback.blockReason` / `Candidate.finishReason == SAFETY`).
- `ai.google.dev/gemini-api/docs/image-understanding` (fetched 2026-07-03) — supported image
  input MIME types (PNG, JPEG, WEBP, HEIC, HEIF — **not** GIF), 20MB combined inline-request size
  limit, 3,600-images-per-request file-count limit.
- `pip show google-genai` / `python -c "import discord; print(discord.__version__)"` (run in this
  session against the project's actual venv) — confirms `google-genai` 2.8.0 and `discord.py`
  2.7.1 installed, matching `requirements.txt`'s `discord.py>=2.3.0` pin.

### Secondary (MEDIUM confidence)

- WebSearch (cross-referencing discordpy.readthedocs.io API reference + `discord.py` GitHub
  source `message.py`) — confirms `Attachment.content_type` and `Attachment.size` are simple
  metadata attributes populated from the Discord API payload, readable without calling `.read()`.
- WebSearch (GIF-support cross-check, 2 independent results including a `google-gemini/gemini-cli`
  GitHub issue reporting a 400 on `image/gif` uploads) — corroborates the official-docs finding
  that GIF is unsupported.

### Tertiary (LOW confidence)

- None — all findings above were verifiable against Context7 or official Google/Discord
  documentation; no claim in this research rests solely on unverified training-data memory.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — both libraries already installed and version-confirmed in this session;
  zero new dependencies.
- Architecture: HIGH for the safety-detection/dispatch-contract finding (directly sourced from SDK
  source code + official docs); MEDIUM for the exact cog-glue shape (Option A vs. B, prompt-builder
  choice) since those are explicitly left to planner discretion by CONTEXT.md.
- Pitfalls: HIGH for the GIF-unsupported and content_type-normalization findings (official-docs
  and source-level confirmation); MEDIUM for the exact numeric size/rate-limit headroom
  recommendations (directional, not empirically measured against this project's actual traffic).

**Research date:** 2026-07-03
**Valid until:** 2026-08-02 (30 days — stable SDK surface; re-verify `HarmCategory`/
`HarmBlockThreshold` enum completeness and GIF-support status if `google-genai` is upgraded past
2.8.0 before this phase is planned/executed)
