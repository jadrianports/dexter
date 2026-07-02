# Stack Research — v1.3 "Taste Brain"

**Domain:** Additions to an existing, shipped Discord bot (Dexter) for vision/multimodal roasting + semantic music memory
**Researched:** 2026-07-02
**Confidence:** HIGH (Context7-verified against the installed SDK version)

> **Scope:** This is a *stack-addition* research for milestone v1.3. The existing stack (Python
> 3.11, discord.py, asyncpg→Neon, google-genai, pgvector, the shared 15 RPM `_RateLimiter`, the
> separate 60 RPM embed limiter) is fixed and NOT re-evaluated here — it was already validated in
> v1.2's STACK.md research. This document covers only the four NEW v1.3 features: vision/multimodal
> roasting, semantic music memory / taste-graph, proactive memory callbacks, and `/memory`.

## Summary

**No new dependencies are required for any of the four v1.3 features.** `requirements.txt` already
has everything needed:

- Vision/multimodal roasting → `google-genai` (installed: **2.8.0**, unpinned in `requirements.txt`)
  already supports image input via `types.Part.from_bytes(...)` and safety configuration via
  `types.GenerateContentConfig(safety_settings=[types.SafetySetting(...)])`. Verified against the
  live installed version, not just docs.
- Discord attachment bytes → `discord.py` `Attachment.read()` / `.content_type` / `.size` /
  `.width` / `.height` are already in the dependency tree and sufficient; no image-processing
  library (Pillow, etc.) is needed.
- Music brain / taste-graph → `asyncpg` + `pgvector` (both already shipped in v1.2 for RAG memory)
  plus plain SQL aggregation over `song_history` / `user_artist_counts` covers taste-graph
  discovery and semantic retrieval. No graph library (networkx), no vector DB (Chroma/FAISS/Pinecone)
  needed — pgvector on Neon already does cosine similarity at this scale.
- Proactive callbacks / `/memory` command → pure orchestration over the existing `MemoryService`
  (v1.2) + `asyncio` background task pattern already used for status rotation / idle checks. No
  scheduling library (APScheduler etc.) needed.

The one thing that **is** new is a *config decision*, not a dependency: Gemini 2.5 models default
`safety_settings` to **OFF** when unspecified (verified via official docs, see below). Today's
`chat()`/`generate_image()` calls in `services/gemini.py` never pass `safety_settings`, which was a
reasonable default for text-only trusted-input paths but becomes a real content-safety gap the
moment untrusted user-uploaded images are fed into the model for vision roasting (VIS-01/02). This
is a required code change (explicit `safety_settings` on the new vision call), not a new package.

## Stack Additions

**None required.** Table intentionally empty — every capability needed for v1.3 is already covered
by the installed stack (`google-genai==2.8.0`, `discord.py`, `asyncpg`, `pgvector`). Anything that
looks like it might need a new library is addressed by an existing dependency below.

| Capability | Needs new library? | Covered by | Why existing stack suffices |
|---|---|---|---|
| Send image bytes to Gemini for vision | No | `google-genai` 2.8.0 (installed) | `types.Part.from_bytes(data=..., mime_type=...)` — native SDK feature, present since early 0.x/1.x releases, confirmed live at 2.8.0 |
| Read Discord image attachment bytes | No | `discord.py` (installed, `>=2.3.0`) | `discord.Attachment.read()` is a coroutine returning `bytes`; `.content_type`, `.size`, `.width`, `.height` give you mime/size/dimension validation with zero extra parsing |
| Content-safety guardrails on image input | No | `google-genai` `types.SafetySetting` / `HarmCategory` / `HarmBlockThreshold` | Native `GenerateContentConfig(safety_settings=[...])` — same mechanism already usable for `chat()`, just not currently invoked anywhere in `services/gemini.py` |
| Taste-graph discovery (artist/genre affinities) | No | `asyncpg` + existing `user_artist_counts` / `song_history` tables | Plain `GROUP BY artist ORDER BY play_count DESC` / co-occurrence SQL is sufficient at single-community scale; no graph theory needed for "top artists" / "artists that cluster with X" |
| Semantic music memory (taste embeddings) | No | `pgvector` (installed, v1.2) + `gemini-embedding-001` (already wired in `GeminiService.embed()`) | Same `user_memories(vector(768))` pattern from v1.2 RAG — add a new memory `kind` (e.g. `"taste"`), reuse `remember()`/`recall()` wholesale |
| Proactive background callback surface | No | `asyncio` background task pattern (`bot.py` — status rotation, idle check, `make_task` from Phase 9) | Same `tasks.loop`-or-manual-`asyncio.sleep` polling pattern already used 4x in the codebase; a new loop calling `recall()` + a cadence gate is orchestration, not new infra |
| `/memory` inspect/forget command | No | `discord.py` `app_commands` (existing pattern) + `MemoryService` (v1.2) | Straight CRUD-style command on the existing `user_memories` table; no new surface |

## Vision Input — Call Shape

Verified against Context7 `/googleapis/python-genai` docs and the installed `google-genai==2.8.0`.
This slots directly into `services/gemini.py` alongside `chat()`/`generate_image()`/`embed()`,
reusing `self._rate_limiter` (the shared 15 RPM budget — **not** a new limiter; a multimodal
image+text request counts as a single request against RPM/RPD, confirmed via Gemini API rate-limits
docs and multiple secondary sources).

```python
# services/gemini.py — new method, same shape as existing chat()/generate_image()

async def analyze_image(
    self,
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
    priority: int = 2,   # background/ambient trigger, not a slash command — mirrors auto-queue's priority=2
) -> str | None:
    """Send an image + text prompt to Gemini for vision-based roasting.

    Raises:
        GeminiRateLimitError, GeminiAPIError, GeminiRefusalError
    """
    await self._rate_limiter.acquire(priority)

    try:
        response = await self._client.aio.models.generate_content(
            model=config.GEMINI_MODEL,  # gemini-2.5-flash — same chat model, no new model ID
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                types.Part.from_text(text=prompt),
            ],
            config=types.GenerateContentConfig(
                system_instruction=prompt,  # or reuse existing personality system prompt
                safety_settings=VISION_SAFETY_SETTINGS,  # see Safety Settings section — REQUIRED, not optional
            ),
        )
    except errors.APIError as e:
        log.error(f"Vision API error (code={e.code}): {e.message}")
        if e.code == 429:
            raise GeminiRateLimitError("Gemini API rate limit hit") from e
        raise GeminiAPIError(f"Gemini API error: {e.message}") from e
    except Exception as e:
        log.error(f"Vision unexpected error ({type(e).__name__}): {e}", exc_info=True)
        raise GeminiAPIError(str(e)) from e

    # Refusal / block detection — see Safety Settings section for the full check
    if response.prompt_feedback and response.prompt_feedback.block_reason:
        raise GeminiRefusalError(f"Prompt blocked: {response.prompt_feedback.block_reason}")
    if not response.candidates:
        raise GeminiRefusalError("No candidates returned (likely blocked)")
    if response.candidates[0].finish_reason == "SAFETY":
        raise GeminiRefusalError("Response blocked by safety filter")

    return response.text if response.text else None
```

**Discord attachment → bytes** (in the cog, e.g. `cogs/events.py` `on_message`):

```python
for attachment in message.attachments:
    if not (attachment.content_type or "").startswith("image/"):
        continue  # skip non-images (discord.py sets content_type from the upload)
    if attachment.size > MAX_VISION_IMAGE_BYTES:  # new config knob, see below — guard before download
        continue
    image_bytes = await attachment.read()
    reply = await gemini_service.analyze_image(
        image_bytes, attachment.content_type, roast_prompt, priority=2,
    )
```

### Supported inputs / limits (verified via `ai.google.dev/gemini-api/docs/image-understanding`)

- **Supported MIME types:** `image/png`, `image/jpeg`, `image/webp`, `image/heic`, `image/heif`.
  Reject anything else before calling the API (Discord attachments can be arbitrary file types).
- **Token cost:** 258 tokens if both dimensions ≤ 384px; larger images are tiled into 768×768 tiles
  at 258 tokens/tile. Irrelevant to the 15 RPM budget (RPM is request-count-based) but relevant if
  `MAX_AI_RESPONSE_LENGTH`-style token budgeting is ever added — not needed for v1.3.
  **LOW confidence on exact tiling formula for very large images** — WebFetch summary only, not
  independently re-verified against a second source; not load-bearing for v1.3 scope.
- **Inline (`Part.from_bytes`) size limit:** total request size (text + system instruction + inline
  image bytes) capped at **20MB**. Discord attachments can be up to 25MB (or more on boosted
  servers) — **must validate `attachment.size` before download/send**, not just mime type. Suggest
  a `MAX_VISION_IMAGE_BYTES` config knob (e.g. 8–10MB, well under the 20MB ceiling to leave room for
  prompt text) and a personality-flavored rejection message for oversized images, mirroring the
  existing `MAX_SONG_DURATION_SECONDS` reject pattern.
- **Free tier confirms multimodal input is included** — no separate "vision" tier/paywall. Gemini
  2.5 Flash free tier: 15 RPM / 1M TPM / 1,500 RPD (matches `config.GEMINI_RPM_LIMIT = 15` already
  in place — no rate-limiter change needed). MEDIUM confidence on the exact RPD/TPM figures
  (WebSearch-aggregated from third-party trackers, not the official AI Studio dashboard, which is
  account-gated and can't be checked from here) — the RPM figure (15) is HIGH confidence since it
  matches the value already hardcoded in `config.py`, which the user presumably set from their own
  AI Studio dashboard.

## Safety Settings

**Verified via Context7 `/googleapis/python-genai` + `ai.google.dev/gemini-api/docs/safety-settings`.**

### Critical finding: the default changed under you

> "The default block threshold is **Off** for Gemini 2.5 and 3 models" when `safety_settings` is
> unspecified.

`services/gemini.py`'s existing `chat()` and `generate_image()` calls never pass `safety_settings`
— today that's low-risk because the model only ever sees trusted inputs (system prompt + Discord
text messages the bot already moderates via its own personality layer). **Vision roasting changes
the trust boundary**: the model will now see arbitrary user-uploaded images with safety filtering
effectively OFF unless you explicitly configure it. This is exactly what VIS-01/02 (content-safety
guardrails) needs to close.

### Configurable HarmCategory values (Gemini Developer API)

| Category | Blocks |
|---|---|
| `HARM_CATEGORY_HARASSMENT` | Negative/harmful comments targeting identity or protected attributes |
| `HARM_CATEGORY_HATE_SPEECH` | Rude, disrespectful, or profane content |
| `HARM_CATEGORY_SEXUALLY_EXPLICIT` | References to sexual acts or lewd content |
| `HARM_CATEGORY_DANGEROUS` | Content that promotes/facilitates/encourages harmful acts |

(Note: CSAM/child-safety filtering is always-on and non-configurable regardless of `safety_settings`
— not something you need to wire up.)

### HarmBlockThreshold values

`OFF` · `BLOCK_NONE` · `BLOCK_ONLY_HIGH` · `BLOCK_MEDIUM_AND_ABOVE` · `BLOCK_LOW_AND_ABOVE` ·
`HARM_BLOCK_THRESHOLD_UNSPECIFIED` (falls back to the model default, i.e. `OFF` for 2.5/3 models —
so `UNSPECIFIED` is functionally the same trap as omitting `safety_settings` entirely).

### Recommended config for `analyze_image()`

```python
VISION_SAFETY_SETTINGS = [
    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_MEDIUM_AND_ABOVE"),
    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_MEDIUM_AND_ABOVE"),
    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_MEDIUM_AND_ABOVE"),
    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS", threshold="BLOCK_MEDIUM_AND_ABOVE"),
]
```

`BLOCK_MEDIUM_AND_ABOVE` matches Gemini's pre-2.5-era default and is a reasonable single-community
starting point — strict enough to close the "default is now OFF" gap, loose enough that a sarcastic
roast bot doesn't choke on mildly edgy meme images. Tune down to `BLOCK_ONLY_HIGH` per-category if
false-positive refusals turn out to be annoying in practice; that's a config-value change, not an
architecture change.

### Refusal detection (both prompt-level and response-level blocks exist)

```python
# 1. Prompt-level block (the image/prompt itself was rejected before generation)
if response.prompt_feedback and response.prompt_feedback.block_reason:
    ...  # personality-flavored refusal message, mirrors /imagine's existing refusal handling

# 2. Response-level block (generation started but was blocked, or no candidates returned)
if not response.candidates:
    ...
elif response.candidates[0].finish_reason == "SAFETY":
    ...  # inspect response.candidates[0].safety_ratings for which category tripped, if logging detail is wanted
```

This mirrors the refusal-handling shape `generate_image()` already partially has (checking for
empty `candidates`/`parts`) — extend it with the explicit `block_reason` / `finish_reason == "SAFETY"`
checks, which the current image-gen path does not check today (it only handles the empty-response
case, not an explicit safety block). Recommend raising the existing `GeminiRefusalError` in both
cases so callers get one exception type to handle, same as `/imagine`'s refusal path.

## Music Brain / Taste-Graph — No New Library

Confirmed via review of `config.py` + `services/gemini.py` (v1.2 RAG shipped) that everything needed
already exists:

- **Storage:** `pgvector` (`vector(768)`) on the existing `user_memories` table, same as v1.2. Add a
  new `kind` value (e.g. `"taste"` or reuse the memory-kind pattern) rather than a new table —
  matches the "zero new infrastructure" precedent set in Phase 11.
- **Embeddings:** `GeminiService.embed()` already exists, already rate-limited on the separate 60
  RPM `_embed_limiter` — reuse directly for taste-episode embedding, no new quota concern.
- **Taste-graph discovery (artist/genre affinity):** this is aggregation SQL over `user_artist_counts`
  / `song_history`, not a graph-database problem at single-community scale (dozens of users, low
  thousands of songs). `SELECT artist, COUNT(*) ... GROUP BY ... ORDER BY ...` plus simple
  co-occurrence queries (songs queued in the same session/day) covers "discovery surfaced via a
  command." A real graph library (`networkx`) would be over-engineering for this data volume and
  adds a dependency with no corresponding infra reuse story.
- **Generative jams / "continue this jam":** this is a `chat()`-shaped Gemini call (same pattern as
  the existing AI auto-queue prompt in `cogs/ai.py` / `services/gemini.py`), fed a taste-graph
  summary + recent session history as context. No new SDK surface — it's the same
  `generate_content` call shape already used for auto-queue recommendations.
- **`was_skipped`-aware learning:** already a column on `song_history` (used today for `/skips`
  analytics in v1.2). Auto-queue can weight/filter recommendations by skip rate via SQL, no ML
  library needed for a heuristic (not statistical-model) taste weighting at this scale.

## What NOT to Add

| Avoid | Why | Use Instead |
|---|---|---|
| `Pillow` / `opencv-python` | Discord already supplies `.content_type`, `.size`, `.width`, `.height` on `Attachment` — no server-side image decoding/resizing needed for basic mime/size/dimension validation. Gemini handles internal resizing/tiling itself. | `discord.Attachment` properties |
| `networkx` (or any graph DB) | Single-community bot, low thousands of songs — "taste graph" is served by `GROUP BY`/aggregation SQL, not graph traversal algorithms | `asyncpg` SQL over `user_artist_counts` / `song_history` |
| A dedicated vector DB (Chroma, FAISS, Pinecone, Weaviate, Qdrant) | `pgvector` on the existing Neon Postgres already does cosine similarity search and was explicitly chosen over exactly this class of tool in Phase 11 ("zero new infrastructure") — the same reasoning applies to taste embeddings, which are just another `kind` of memory in the same table | `pgvector` (already installed) |
| `APScheduler` / `celery` / any task-queue library | Proactive callbacks are "check a cadence gate on an existing polling loop," identical in shape to the status-rotation / idle-check loops already running in `bot.py` | `asyncio` loop pattern (Phase 3/9 precedent) |
| A second/separate Gemini rate limiter for vision | A multimodal image+text request counts as ONE request toward RPM/RPD — vision roasting is just another consumer of the existing shared 15 RPM `_rate_limiter`, same as `chat()`/`generate_image()` | `self._rate_limiter.acquire(priority)` (existing) |
| `google-generativeai` (deprecated SDK) | Explicitly forbidden by CLAUDE.md/PROJECT.md constraints; also unmaintained — Google's migration guide points to `google-genai` | `google-genai` (already installed, already used everywhere) |
| Bumping `google-genai` to pin a specific version in `requirements.txt` | Not required for functionality — `Part.from_bytes`, `SafetySetting`, `HarmCategory` are all present and stable at the currently-installed 2.8.0; unpinned dependency already tracks latest | No action — optionally pin `google-genai>=2.8.0` for reproducibility, but that's a hygiene choice, not a feature requirement |

## Version Compatibility

| Package | Installed | Compatible With | Notes |
|---|---|---|---|
| `google-genai` | 2.8.0 | `discord.py>=2.3.0`, Python 3.11+ | `Part.from_bytes`/`SafetySetting`/`HarmCategory` verified present via Context7 docs generated from this same repo; no version bump needed for v1.3 |
| `discord.py` | `>=2.3.0` (per `requirements.txt`) | — | `Attachment.read()`, `.content_type`, `.size`, `.width`, `.height` are stable APIs, present well before 2.3.0 |
| `pgvector` | `>=0.3.6,<0.5` (per `requirements.txt`) | Neon Postgres (v1.2 already validated) | No change needed; new memory `kind` reuses existing table/index |

## Open Questions / Flags for Roadmap

- **`safety_settings` on existing `chat()`/`generate_image()` calls**: this research surfaced that
  Gemini 2.5 models default to safety filtering **OFF**. That's arguably a latent gap on the
  *existing* `/ask` and `/imagine` paths too (both process free-text user input), not just the new
  vision path. Recommend flagging this as a small hardening task alongside the vision work rather
  than silently leaving `/ask`/`/imagine` unfiltered while only vision gets guardrails — but this is
  a judgment call for the roadmap/requirements phase, not a stack decision.
- **Image size cap (`MAX_VISION_IMAGE_BYTES`) and cooldown value** are new `config.py` knobs (no
  new library), needed for VIS-01/02 — exact numeric values are a requirements/roadmap decision
  (mirrors the `MAX_IMAGES_PER_USER_PER_DAY` / `IMAGINE_COOLDOWN_SECONDS` precedent), not something
  this stack research resolves.
- **Tiling token-cost formula for very large images** is LOW confidence (single WebFetch summary,
  not cross-verified) — not load-bearing since RPM (not TPM) is the binding constraint at this
  bot's scale, but flag if a future phase ever needs precise token budgeting.
- **Exact free-tier RPD/TPM numbers** for `gemini-2.5-flash` are MEDIUM confidence (third-party
  trackers, not the account-gated AI Studio dashboard) — the RPM=15 figure is HIGH confidence
  because it's already the value hardcoded in `config.GEMINI_RPM_LIMIT`, presumably set from the
  user's own dashboard.

## Sources

- Context7 `/googleapis/python-genai` — `Part.from_bytes` signature, multimodal `generate_content`
  examples, `SafetySetting`/`HarmCategory` usage (HIGH confidence, matches installed SDK version)
- [ai.google.dev/gemini-api/docs/image-understanding](https://ai.google.dev/gemini-api/docs/image-understanding?lang=python) — supported MIME types, token/tiling cost, 20MB inline-data limit, 3,600 images/request cap (MEDIUM — WebFetch summary of official docs)
- [ai.google.dev/gemini-api/docs/safety-settings](https://ai.google.dev/gemini-api/docs/safety-settings) — HarmCategory list, HarmBlockThreshold values, default-OFF-for-2.5/3 finding (MEDIUM — WebFetch summary of official docs; category list cross-checked against Context7 SDK docs = HIGH for the category/threshold names themselves)
- [ai.google.dev/gemini-api/docs/rate-limits](https://ai.google.dev/gemini-api/docs/rate-limits) — confirms tiered rate limits exist per Google AI Studio dashboard; did not surface exact free-tier numbers directly (LOW for exact figures from this source alone)
- WebSearch aggregation (multiple third-party trackers: tokenmix.ai, aifreeapi.com, laozhang.ai) — free tier RPM/TPM/RPD figures, multimodal-counts-as-one-request confirmation (MEDIUM — multiple independent sources agree, none is the primary source)
- Context7 `/rapptz/discord.py` — `Attachment` API surface confirmed present (HIGH)
- Local inspection: `pip show google-genai` → 2.8.0 installed (HIGH — ground truth from the actual environment)
- `C:\Users\James\desktop\projects\dexter\services\gemini.py`, `config.py`, `requirements.txt`, `.planning/PROJECT.md` — existing patterns to match (HIGH — primary source)

---
*Stack research for: Dexter v1.3 "Taste Brain" (vision roasting + music brain)*
*Researched: 2026-07-02*
