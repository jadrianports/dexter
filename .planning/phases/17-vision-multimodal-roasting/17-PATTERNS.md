# Phase 17: Vision / Multimodal Roasting - Pattern Map

**Mapped:** 2026-07-03
**Files analyzed:** 8 (new + modified)
**Analogs found:** 8 / 8

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `logic/vision.py` (NEW) | utility (pure decision gate) | event-driven | `logic/proactive.py::should_fire_proactive_callback` | exact |
| `tests/test_vision_logic.py` (NEW) | test | event-driven | `tests/test_proactive_logic.py` | exact |
| `services/gemini.py` (MODIFY) | service | request-response | itself (`chat()` / `generate_image()`) | exact (in-place retrofit) |
| `tests/test_gemini.py` (MODIFY) | test | request-response | itself (existing `TestGeminiChat` mock pattern) | exact |
| `cogs/events.py` (MODIFY) | controller/event-handler | event-driven | itself (`_maybe_fire_proactive_callback` + `_generate_ambient_roast`) | exact |
| `tests/test_vision_events.py` (NEW) | test | event-driven | `tests/test_proactive_events.py` (mock `_make_bot`/`_make_message` helpers) | role-match |
| `personality/prompts.py` (MODIFY, optional) | utility (prompt builder) | transform | `build_discover_commentary_prompt` / `build_jam_suggestion_prompt` | exact |
| `config.py` (MODIFY) | config | — | `PROACTIVE_CALLBACK_CHANCE` / `PROACTIVE_CALLBACK_DAILY_CAP` block | exact |

## Pattern Assignments

### `logic/vision.py` (NEW) — pure gate

**Analog:** `logic/proactive.py::should_fire_proactive_callback` (full file read above)

**Module docstring/imports pattern:**
```python
"""Pure vision-roast firing-decision gate (Phase 17 / VIS-01 / D-04).

All functions in this module are deterministic and side-effect-free: no ``random``,
no ``asyncio``, no ``datetime``, no ``discord``.
"""

from __future__ import annotations

import config
```

**Core gate pattern — copy this shape exactly** (keyword-only, cheapest-gate-first, config defaults):
```python
def should_fire_vision_roast(
    *,
    opted_out: bool,
    cooldown_elapsed: bool,
    chance_roll: float,
    chance: float = config.VISION_ROAST_CHANCE,
) -> bool:
    """Gate 1: opt-out (cheapest, wins — reuses Phase 16 proactive_opt_out, D-03 step 4).
    Gate 2: per-user cooldown must have elapsed (reuse logic.roasts.cooldown_elapsed in glue).
    Gate 3: chance roll must be strictly below chance. All three true -> fire.
    """
    if opted_out:
        return False
    if not cooldown_elapsed:
        return False
    if chance_roll >= chance:
        return False
    return True
```
Note: glue computes `cooldown_elapsed` via the **existing** `logic.roasts.cooldown_elapsed(seconds_since_last, ceiling)` helper (do not reimplement) against a new `self._vision_roast_cooldowns: dict[int, float]` dict mirroring `self._ambient_roast_times` (`cogs/events.py:35`).

**Boundary convention (must match exactly, from `decide_ambient_roast`/`should_fire_proactive_callback`):** `chance_roll >= chance` fails (strictly-less-than passes); exactly-at-cooldown-ceiling passes (`>=` in `cooldown_elapsed`).

---

### `tests/test_vision_logic.py` (NEW) — mock-free boundary tests

**Analog:** `tests/test_proactive_logic.py` (full file structure above)

**Pattern to copy:**
```python
"""Exhaustive pure-unit tests for logic/vision.py (VIS-01 / D-04).

No mocks, no clocks, no RNG — all inputs are plain Python primitives.
"""

import config
from logic.vision import should_fire_vision_roast

CHANCE_PASS = config.VISION_ROAST_CHANCE - 0.01   # just under the threshold
CHANCE_FAIL = config.VISION_ROAST_CHANCE          # exactly at threshold -> False


class TestShouldFireVisionRoast:
    def test_opted_out_returns_false_regardless_of_rolls(self):
        assert should_fire_vision_roast(
            opted_out=True, cooldown_elapsed=True, chance_roll=0.0,
        ) is False

    def test_chance_roll_at_threshold_returns_false(self):
        assert should_fire_vision_roast(
            opted_out=False, cooldown_elapsed=True, chance_roll=CHANCE_FAIL,
        ) is False

    def test_cooldown_not_elapsed_returns_false(self):
        assert should_fire_vision_roast(
            opted_out=False, cooldown_elapsed=False, chance_roll=CHANCE_PASS,
        ) is False

    def test_all_gates_pass_returns_true(self):
        assert should_fire_vision_roast(
            opted_out=False, cooldown_elapsed=True, chance_roll=CHANCE_PASS,
        ) is True
```
Also add a rarity-invariant test mirroring the existing `test_proactive_chance_is_rarer_than_ambient`-style assertion: `assert config.VISION_ROAST_CHANCE < config.UNPROMPTED_ROAST_CHANCE` and `< config.MEMORY_CALLBACK_CHANCE`.

---

### `services/gemini.py` (MODIFY) — safety_settings retrofit + vision call

**Analog:** itself — `chat()` lines 146-207, `generate_image()` lines 209-248, exception pattern lines 189-204/223-238.

**Imports (already present, no new import needed beyond `types`):**
```python
from google import genai
from google.genai import types, errors
```

**Shared safety-settings helper (NEW, module-level, near `_RateLimiter`):**
```python
_SAFETY_CATEGORIES = (
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
)

def _build_safety_settings(threshold: str) -> list[types.SafetySetting]:
    """threshold is one of the HarmBlockThreshold string values, e.g.
    'BLOCK_MEDIUM_AND_ABOVE' (vision, real block) or 'BLOCK_ONLY_HIGH' (/ask, /imagine, permissive)."""
    return [
        types.SafetySetting(category=cat, threshold=threshold)
        for cat in _SAFETY_CATEGORIES
    ]
```

**Thread into existing `GenerateContentConfig` construction — exact call sites to edit:**
- `chat()` line 193-195:
  ```python
  config=types.GenerateContentConfig(
      system_instruction=system_prompt,
      safety_settings=_build_safety_settings(config.TEXT_SAFETY_THRESHOLD),
  ),
  ```
- `generate_image()` line 227-229:
  ```python
  config=types.GenerateContentConfig(
      response_modalities=["IMAGE"],
      safety_settings=_build_safety_settings(config.TEXT_SAFETY_THRESHOLD),
  ),
  ```

**New vision call — extend `chat()` with optional keyword-only image params (recommended over a parallel method per RESEARCH Open Question 2), preserving the exact try/except shape from `chat()` (lines 189-204):**
```python
async def chat(
    self,
    system_prompt: str,
    conversation: list[dict],
    priority: int = 1,
    *,
    image_bytes: bytes | None = None,
    image_mime_type: str | None = None,
) -> str | None:
    ...
    contents = []
    for msg in conversation:
        contents.append(
            types.Content(role=msg["role"], parts=[types.Part.from_text(text=msg["content"])])
        )
    if image_bytes is not None and contents:
        contents[-1].parts.append(
            types.Part.from_bytes(data=image_bytes, mime_type=image_mime_type)
        )
    if not contents:
        contents = "."

    threshold = config.VISION_SAFETY_THRESHOLD if image_bytes is not None else config.TEXT_SAFETY_THRESHOLD
    try:
        response = await self._client.aio.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                safety_settings=_build_safety_settings(threshold),
            ),
        )
    except errors.APIError as e:
        log.error(f"Gemini API error (code={e.code}): {e.message}")
        if e.code == 429:
            raise GeminiRateLimitError("Gemini API rate limit hit") from e
        raise GeminiAPIError(f"Gemini API error: {e.message}") from e
    except Exception as e:
        log.error(f"Gemini unexpected error ({type(e).__name__}): {e}", exc_info=True)
        raise GeminiAPIError(str(e)) from e

    return response.text if response.text else None
```

**CRITICAL contract to preserve (do not change):** `chat()` returns `None` on empty/blocked text — never raises for a safety block. Only `errors.APIError`/other `Exception` raise `GeminiRateLimitError`/`GeminiAPIError`. This is what makes VIS-02's silent-skip-vs-fallback distinguishable one layer up in `cogs/events.py` — **do not add block-reason detection logic inside `chat()` that changes this return/raise contract.**

**Priority-2 rate limiter (unchanged, reused as-is):** `services/gemini.py:34-103` `_RateLimiter.acquire(priority=2)` — no new limiter, no new code needed here; just call `chat(..., priority=2, image_bytes=..., image_mime_type=...)` from the vision glue.

---

### `tests/test_gemini.py` (MODIFY) — safety_settings + mocked vision tests

**Analog:** itself — `TestGeminiChat` mock pattern (full file read above, lines 1-58).

**Pattern to copy for new tests (inspect the `config=` kwarg passed to `generate_content`):**
```python
@pytest.mark.asyncio
async def test_chat_threads_safety_settings(self):
    mock_response = MagicMock()
    mock_response.text = "roast line"
    with patch("services.gemini.genai") as mock_genai:
        mock_client = MagicMock()
        mock_generate = AsyncMock(return_value=mock_response)
        mock_client.aio.models.generate_content = mock_generate
        mock_genai.Client.return_value = mock_client

        service = GeminiService(api_key="fake-key")
        await service.chat(system_prompt="test", conversation=[])

        _, kwargs = mock_generate.call_args
        assert kwargs["config"].safety_settings is not None

@pytest.mark.asyncio
async def test_vision_call_uses_real_block_threshold(self):
    # same mock scaffold; assert kwargs["config"].safety_settings[0].threshold
    # == config.VISION_SAFETY_THRESHOLD when image_bytes is passed, and
    # == config.TEXT_SAFETY_THRESHOLD for a plain chat() call (two distinct values)
    ...

@pytest.mark.asyncio
async def test_chat_safety_blocked_response_returns_none(self):
    mock_response = MagicMock()
    mock_response.text = None
    mock_response.prompt_feedback = MagicMock(block_reason="SAFETY")
    # ... same AsyncMock scaffold as test_chat_empty_response_returns_none
    # assert result is None (already covered contract, add explicit block_reason variant)
```

---

### `cogs/events.py` (MODIFY) — `_maybe_fire_vision_roast` + on_message dispatch

**Analog:** itself — `_maybe_fire_proactive_callback` (lines 406-514) is the structural template; `_generate_ambient_roast` (lines 95-201) is the generator template BUT must **NOT** be reused unmodified (see Shared Patterns below — RESEARCH's Pitfall 1 finding).

**Imports to add:**
```python
from logic.vision import should_fire_vision_roast
from logic.roasts import cooldown_elapsed  # reuse, don't reimplement
```

**Cooldown dict to add in `__init__` (mirrors `self._ambient_roast_times` at line 35):**
```python
self._vision_roast_cooldowns: dict[int, float] = {}
```

**on_message dispatch — add beside the existing proactive-callback dispatch (lines 395-402):**
```python
        # Phase 17 / VIS-01: vision-roast gate — same designated-channel guard,
        # a fourth independent unprompted cadence (do not merge with proactive).
        if (
            message.guild is not None
            and config.DEXTER_CHANNEL_ID
            and message.channel.id == config.DEXTER_CHANNEL_ID
            and message.attachments
        ):
            await self._maybe_fire_vision_roast(message)
```

**`_maybe_fire_vision_roast` — structural template copied from `_maybe_fire_proactive_callback` (opt-out read → structural attachment gate → pure gate → fetch bytes → dedicated generator → reply-anchored send):**
```python
async def _maybe_fire_vision_roast(self, message: discord.Message) -> None:
    user_id = str(message.author.id)
    try:
        opted_out = await database.get_proactive_opt_out(self.bot.pool, user_id)
    except Exception as _opt_out_err:
        log.debug("vision roast: opt-out lookup failed (non-fatal): %s", _opt_out_err)
        return

    attachment = _first_valid_image_attachment(message)  # structural gate, no I/O yet
    if attachment is None:
        return

    seconds_since_last = (
        asyncio.get_event_loop().time()
        - self._vision_roast_cooldowns.get(message.author.id, 0.0)
    )
    if not should_fire_vision_roast(
        opted_out=opted_out,
        cooldown_elapsed=cooldown_elapsed(seconds_since_last, config.VISION_ROAST_COOLDOWN_SECONDS),
        chance_roll=random.random(),
    ):
        return

    image_bytes = await attachment.read()  # only after every gate passes
    line = await self._generate_vision_roast(message.author, image_bytes, attachment.content_type)
    if line is None:
        return  # VIS-02: safety-blocked or empty -> silent skip, no send, no cooldown mark

    try:
        await message.reply(
            line, allowed_mentions=discord.AllowedMentions.none(), mention_author=False,
        )
    except discord.HTTPException:
        return
    self._vision_roast_cooldowns[message.author.id] = asyncio.get_event_loop().time()
```

**Structural attachment gate (module-level helper, mirrors `ALLOWED_VISION_MIME_TYPES` pattern from RESEARCH Code Examples — put near top of `cogs/events.py` or in `logic/vision.py` if kept pure-metadata-only):**
```python
ALLOWED_VISION_MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})  # NOT image/gif

def _first_valid_image_attachment(message: discord.Message) -> discord.Attachment | None:
    for attachment in message.attachments:
        content_type = (attachment.content_type or "").split(";")[0].strip().lower()
        if content_type not in ALLOWED_VISION_MIME_TYPES:
            continue
        if attachment.size > config.MAX_VISION_IMAGE_BYTES:
            continue
        return attachment  # first valid one (D-02)
    return None
```

---

### `personality/prompts.py` (MODIFY, optional) — vision conduct-clause prompt builder

**Analog:** `build_discover_commentary_prompt` (lines 238-249) / `build_jam_suggestion_prompt` (lines 266-283) — small dedicated builder pattern, NOT the full few-shot `build_chat_prompt`.

**Pattern to copy:**
```python
VISION_ROAST_PROMPT = """\
You are Dex reacting to an image someone just posted. Roast the image's content, vibe, or subject \
matter in your usual dry, sarcastic voice. Respond with exactly one short line, under 120 \
characters, lowercase, no preamble.

Hard rule: never comment on a real person's face, body, weight, or perceived identity. If the \
image is primarily a person, keep the roast about the scene or context, not their appearance."""


def build_vision_prompt() -> str:
    """Build the vision-roast system prompt (Phase 17 / VIS-02 D-03 step 2 conduct clause).

    A small dedicated builder rather than the full few-shot DEXTER_SYSTEM_PROMPT
    (via build_chat_prompt) — keeps the inline request small (Gemini's 20MB combined
    inline-data limit, RESEARCH Pitfall 4) and makes the conduct clause unambiguous.
    """
    return VISION_ROAST_PROMPT
```

---

### `config.py` (MODIFY) — new knobs

**Analog:** `PROACTIVE_CALLBACK_CHANCE` / `PROACTIVE_CALLBACK_DAILY_CAP` block (lines 228-232).

**Pattern to copy (place near the Phase 16 proactive block, or in the vision/config section noted in ROADMAP):**
```python
# Vision / multimodal roasting (Phase 17 / VIS-01/02/03)
VISION_ROAST_CHANCE = 0.12                # D-04: strictly < UNPROMPTED_ROAST_CHANCE (0.30) and < MEMORY_CALLBACK_CHANCE (0.35)
VISION_ROAST_COOLDOWN_SECONDS = 600       # per-user cooldown, mirrors ROAST_COOLDOWN_SECONDS scale
MAX_VISION_IMAGE_BYTES = 8 * 1024 * 1024  # 8MB raw — headroom below Gemini's 20MB combined inline-request cap after base64 inflation (RESEARCH Pitfall 4)
VISION_SAFETY_THRESHOLD = "BLOCK_MEDIUM_AND_ABOVE"  # real block (D-01) — vision only
TEXT_SAFETY_THRESHOLD = "BLOCK_ONLY_HIGH"           # permissive-but-explicit (D-01) — /ask + /imagine + non-image chat() calls
```

## Shared Patterns

### Silent-skip vs. template-fallback dispatch (VIS-02) — the one NEW pattern, not a copy of an existing one
**Source:** RESEARCH.md Architecture Patterns, Pattern 3 (Option A, recommended).
**Apply to:** `cogs/events.py::_generate_vision_roast` (NEW dedicated function — do NOT branch `_generate_ambient_roast` and do NOT call it unmodified for vision).
```python
async def _generate_vision_roast(
    self, member: discord.Member, image_bytes: bytes, mime_type: str,
) -> str | None:
    """Returns the roast line, a transport-failure fallback line, or None
    (safety-blocked or genuinely empty response) — caller sends only if not None."""
    gemini_service = getattr(self.bot, "gemini_service", None)
    if gemini_service is None:
        return None  # no service configured — silent skip

    system_prompt = build_vision_prompt()
    fallback_pool = roasts.VISION_ROAST_FALLBACKS  # new personality/roasts.py pool, transport-failure only
    try:
        result = await gemini_service.chat(
            system_prompt,
            [{"role": "user", "content": "react to this image in one line."}],
            priority=2,
            image_bytes=image_bytes,
            image_mime_type=mime_type,
        )
    except GeminiRateLimitError:
        return pick_random(fallback_pool)   # transport failure -> template fallback (D-04)
    except Exception:
        return pick_random(fallback_pool)   # transport failure -> template fallback (D-04)

    if not result:
        return None   # safety-blocked OR genuinely empty -> silent skip (VIS-02), NOT fallback_pool

    result = result.strip()
    if result and result[0].isupper():
        result = result[0].lower() + result[1:]
    return result[:497] + "..." if len(result) > 500 else result
```
**Why this must be a dedicated function, not a flag on `_generate_ambient_roast`:** `_generate_ambient_roast`'s bottom-of-function `return fallback_line` (line 201) is reached both from the two `except` clauses AND from a falsy `result` — it cannot distinguish "safety blocked" from "rate limited." Reusing it unmodified for vision would make a safety-blocked image produce the exact same visible template reply as a rate-limited one, violating VIS-02.

### `AllowedMentions.none()` + reply-anchored send
**Source:** `cogs/events.py` — every unprompted send (lines 224, 268, 314, 359, 502-506).
**Apply to:** the vision roast's `message.reply(...)` call — identical shape to `_maybe_fire_proactive_callback`'s send (lines 501-506): `allowed_mentions=discord.AllowedMentions.none(), mention_author=False`.

### Opt-out reuse (no new column)
**Source:** `database.py:356-372` `get_proactive_opt_out(pool, user_id)`.
**Apply to:** `_maybe_fire_vision_roast` — call identically to `_maybe_fire_proactive_callback` line 426. No new flag/column (D-03 step 4).

### Cooldown helper reuse
**Source:** `logic/roasts.py::cooldown_elapsed(seconds_since_last, ceiling_seconds)` (lines 52-66).
**Apply to:** vision cooldown check in glue — do not reimplement; pass `config.VISION_ROAST_COOLDOWN_SECONDS` as `ceiling_seconds`.

### Community-time / TZ pattern (only if any date-keyed cap is added)
**Source:** `cogs/events.py:436-438` (`ZoneInfo(config.STREAK_TIMEZONE)` day-key pattern used for `_proactive_daily_counts`).
**Apply to:** only needed if planner adds a per-user/day vision cap (CONTEXT.md discretion item) — reuse this exact pattern, never naive `datetime.now()`.

## No Analog Found

None — all 8 files have a strong (exact or role-match) analog in the existing codebase; this phase is explicitly designed to reuse Phase 10/16 seams end-to-end.

## Metadata

**Analog search scope:** `logic/`, `services/gemini.py`, `cogs/events.py`, `personality/prompts.py`, `config.py`, `tests/`
**Files read in full or targeted range:** `logic/proactive.py`, `logic/roasts.py`, `services/gemini.py`, `cogs/events.py` (lines 1-518), `personality/prompts.py` (lines 238-284), `tests/test_proactive_logic.py` (lines 1-60), `tests/test_gemini.py` (lines 1-58), `database.py` (lines 318-372), `config.py` (targeted greps)
**Pattern extraction date:** 2026-07-03
