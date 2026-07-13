"""Gemini API wrapper with rate limiter. Thin layer — no personality logic."""

from __future__ import annotations

import asyncio
import time
from collections import deque

from google import genai
from google.genai import errors, types

import config
from utils.logger import log

# ──────────────────────────── EXCEPTIONS ────────────────────────────


class GeminiRateLimitError(Exception):
    """Raised when the rate limiter rejects a request."""


class GeminiAPIError(Exception):
    """Raised on Gemini API errors (network, server, etc.)."""


class GeminiRefusalError(Exception):
    """Raised when content is filtered or generation is refused."""


# ──────────────────────────── SAFETY SETTINGS ────────────────────────────

# The four adjustable, non-deprecated safety categories the installed google-genai
# SDK exposes for gemini-2.5-flash text/vision (RESEARCH Assumption A2 — verified
# against list(types.HarmCategory) at implementation time; the additional
# HARM_CATEGORY_IMAGE_*/CIVIC_INTEGRITY/JAILBREAK entries are model-specific or
# deprecated specials, not standard adjustable SafetySettings for this model).
# Gemini 2.5-series defaults these to OFF when unspecified, so every user-influenced
# generate_content call MUST set them explicitly (D-01 / VIS-03).
_SAFETY_CATEGORIES = (
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
)


def _build_safety_settings(threshold: str) -> list[types.SafetySetting]:
    """Build an explicit SafetySetting list applying ``threshold`` to every
    adjustable HarmCategory.

    ``threshold`` is a HarmBlockThreshold string value, e.g.
    ``"BLOCK_MEDIUM_AND_ABOVE"`` (config.VISION_SAFETY_THRESHOLD — vision real block)
    or ``"BLOCK_ONLY_HIGH"`` (config.TEXT_SAFETY_THRESHOLD — /ask + /imagine +
    non-image chat(), permissive-but-explicit so edgy personality output is not
    newly blocked).
    """
    return [types.SafetySetting(category=cat, threshold=threshold) for cat in _SAFETY_CATEGORIES]


# ──────────────────────────── RATE LIMITER ────────────────────────────


class _RateLimiter:
    """Hybrid sliding-window rate limiter with priority support.

    Priority 1 (user commands): wait for a slot if at limit.
    Priority 2 (background/auto-queue): reject if wait > 10s.
    """

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: float = 60.0,
    ) -> None:
        self._max_requests = max_requests or config.GEMINI_RPM_LIMIT
        self._window = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    def _clean(self) -> None:
        """Remove timestamps outside the sliding window."""
        now = time.monotonic()
        while self._timestamps and (now - self._timestamps[0]) >= self._window:
            self._timestamps.popleft()

    def rpm_usage(self) -> int:
        """Return the number of requests in the current sliding window.

        Calls _clean() to prune stale timestamps before counting. Synchronous —
        no asyncio.Lock acquire (Pitfall 4). The benign read race (off-by-1 if
        acquire() fires concurrently) is acceptable for a dashboard display (D-24).
        """
        self._clean()
        return len(self._timestamps)

    def rpm_headroom(self) -> int:
        """Return remaining request slots in the current sliding window.

        Floored at 0 so callers never see a negative value.
        """
        return max(0, self._max_requests - self.rpm_usage())

    async def acquire(self, priority: int = 1) -> None:
        """Acquire a rate limit slot.

        Raises GeminiRateLimitError if priority 2 and wait > 10s.
        """
        async with self._lock:
            self._clean()

            if len(self._timestamps) < self._max_requests:
                self._timestamps.append(time.monotonic())
                return

            # At limit — calculate wait time
            oldest = self._timestamps[0]
            wait_time = self._window - (time.monotonic() - oldest)

            if priority >= 2 and wait_time > 10:
                raise GeminiRateLimitError(f"Rate limit full, wait would be {wait_time:.0f}s")

        # Wait outside the lock so other requests can proceed
        if wait_time > 0:
            log.info(f"Rate limiter: waiting {wait_time:.1f}s (priority {priority})")
            await asyncio.sleep(wait_time)

        async with self._lock:
            self._clean()
            self._timestamps.append(time.monotonic())


# ──────────────────────────── SERVICE ────────────────────────────


class GeminiService:
    """Thin wrapper around the google-genai SDK."""

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or ""
        # Auto-retry transient server overloads (503/500/502/504) with exponential
        # backoff so a momentary "model overloaded" spike self-heals instead of
        # failing the request. 429 is deliberately EXCLUDED — rate limits are owned
        # by our _RateLimiter + priority tiers (a priority-2 429 must fall back, not
        # silently retry and contend with user /ask requests).
        self._client = genai.Client(
            api_key=key,
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(
                    attempts=3,
                    initial_delay=1.0,
                    max_delay=8.0,
                    exp_base=2.0,
                    http_status_codes=[500, 502, 503, 504],
                ),
            ),
        )
        self._rate_limiter = _RateLimiter()
        # Separate embedding quota — ~60 RPM endpoint vs 15 RPM for chat/image.
        # MUST NOT share _rate_limiter: embedding calls never consume the chat budget
        # (MEM-02 / Critical Rule 1 / A2 / T-11-03b).
        self._embed_limiter = _RateLimiter(max_requests=config.EMBED_RPM_LIMIT)
        # Per-guild session usage counter (RATE-01 / D-08). In-memory, since-boot,
        # reset on restart — a triage view for a LIVE session, not durable history.
        # Deliberately NOT a second limiter/quota (D-09, Critical Rule 1) — purely
        # additive observability for /guilds list.
        self._guild_usage: dict[str, int] = {}

    @property
    def rpm_usage(self) -> int:
        """Current requests in the sliding window (for /stats Gemini quota panel, D-24)."""
        return self._rate_limiter.rpm_usage()

    @property
    def rpm_headroom(self) -> int:
        """Remaining request slots in the sliding window (D-24)."""
        return self._rate_limiter.rpm_headroom()

    def guild_usage(self, guild_id: str | None) -> int:
        """Return this session's guild-attributable chat/image call count.

        Returns 0 for an unknown or None guild_id. Read-only observability
        (RATE-01) — never a gate, never a quota (D-09).
        """
        return self._guild_usage.get(str(guild_id), 0) if guild_id is not None else 0

    async def chat(
        self,
        system_prompt: str,
        conversation: list[dict],
        priority: int = 1,
        *,
        image_bytes: bytes | None = None,
        image_mime_type: str | None = None,
        guild_id: str | None = None,
    ) -> str | None:
        """Send a chat request to Gemini.

        Args:
            system_prompt: The assembled system instruction.
            conversation: List of {"role": "user"|"model", "content": "..."} dicts.
            priority: 1 = user command, 2 = background task.
            image_bytes: Optional raw image bytes to compose onto the final user
                turn (vision path, Phase 17 / VIS-01). When provided, the call uses
                the real-block VISION_SAFETY_THRESHOLD instead of the permissive
                TEXT_SAFETY_THRESHOLD.
            image_mime_type: The attachment's already-gate-validated content_type
                (e.g. "image/png"); not re-derived from bytes.
            guild_id: Per-session usage tagging ONLY (RATE-01) — never a gate.
                Pass the originating guild's id for a guild-attributable call;
                pass None (default) for guild-less background calls (daily_batch
                distill, DM /ask) so they are not counted (D-09).

        Returns:
            Response text, or None if empty/blocked. NEVER raises for a safety
            block — this None-on-empty contract is the VIS-02 silent-skip hinge
            the Wave-2 glue depends on.

        Raises:
            GeminiRateLimitError: Rate limit reached.
            GeminiAPIError: API error (transport/network/server).
        """
        await self._rate_limiter.acquire(priority)

        if guild_id is not None:
            self._guild_usage[str(guild_id)] = self._guild_usage.get(str(guild_id), 0) + 1

        # Log the full context being sent
        log.info(f"── Gemini chat request (priority={priority}) ──")
        log.info(f"System prompt ({len(system_prompt)} chars):\n{system_prompt}")
        log.info(f"Conversation ({len(conversation)} messages):")
        for i, msg in enumerate(conversation):
            log.info(f"  [{i}] {msg['role']}: {msg['content'][:200]}")

        # Build contents list for Gemini
        contents = []
        for msg in conversation:
            contents.append(
                types.Content(
                    role=msg["role"],
                    parts=[types.Part.from_text(text=msg["content"])],
                )
            )

        # Phase 17 / VIS-01: compose the image onto the final user turn (before the
        # empty-contents fallback, since an image call always supplies a user turn).
        if image_bytes is not None and contents:
            contents[-1].parts.append(types.Part.from_bytes(data=image_bytes, mime_type=image_mime_type))

        # Gemini requires at least one user message
        if not contents:
            contents = "."

        # Vision path uses the real-block threshold; every text path stays
        # permissive-but-explicit so existing edgy /ask + ambient output is not
        # newly blocked (D-01 / VIS-03).
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

        log.info(f"Gemini chat response: {len(response.text or '')} chars")
        return response.text if response.text else None

    async def generate_image(
        self,
        prompt: str,
        priority: int = 1,
        *,
        guild_id: str | None = None,
    ) -> bytes | None:
        """Generate an image using Gemini native image generation.

        Args:
            prompt: The image generation prompt.
            priority: 1 = user command, 2 = background task.
            guild_id: Per-session usage tagging ONLY (RATE-01) — never a gate.
                Pass None (default) for a guild-less call so it is not counted
                (D-09).

        Returns:
            Image bytes, or None if refused/empty.

        Raises:
            GeminiRateLimitError: Rate limit reached.
            GeminiAPIError: API error.
        """
        await self._rate_limiter.acquire(priority)

        if guild_id is not None:
            self._guild_usage[str(guild_id)] = self._guild_usage.get(str(guild_id), 0) + 1

        try:
            response = await self._client.aio.models.generate_content(
                model=config.IMAGEN_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    safety_settings=_build_safety_settings(config.TEXT_SAFETY_THRESHOLD),
                ),
            )
        except errors.APIError as e:
            log.error(f"Image gen API error (code={e.code}): {e.message}")
            if e.code == 429:
                raise GeminiRateLimitError("Gemini API rate limit hit") from e
            raise GeminiAPIError(f"Image gen API error: {e.message}") from e
        except Exception as e:
            log.error(f"Image gen unexpected error ({type(e).__name__}): {e}", exc_info=True)
            raise GeminiAPIError(str(e)) from e

        # Extract image bytes from response parts
        if not response.candidates or not response.candidates[0].content.parts:
            return None

        for part in response.candidates[0].content.parts:
            if part.inline_data:
                return part.inline_data.data

        return None

    async def embed(
        self,
        texts: list[str],
        *,
        task_type: str,
        priority: int = 2,
    ) -> list[list[float]]:
        """Embed a batch of texts via gemini-embedding-001 @ 768d.

        Uses the SEPARATE ``_embed_limiter`` (~60 RPM) — never the shared 15 RPM
        chat budget. This satisfies MEM-02 / T-11-03b: embedding calls must not
        starve /ask and /imagine (Critical Rule 1 / A2).

        Args:
            texts:     List of strings to embed in a single API call.
            task_type: Gemini task-type hint — ``"RETRIEVAL_DOCUMENT"`` for writes,
                       ``"RETRIEVAL_QUERY"`` for recall queries (affects embedding space).
            priority:  1 = user critical path (recall); 2 = background write (default).
                       Priority 2 raises GeminiRateLimitError if wait > 10s.

        Returns:
            List of 768-dimensional float vectors, one per input text.

        Raises:
            GeminiRateLimitError: _embed_limiter slot unavailable (priority-2 timeout).
            GeminiAPIError:       API error (network, server overload, 4xx/5xx).
        """
        await self._embed_limiter.acquire(priority)

        log.info(f"── Gemini embed request (priority={priority}, task_type={task_type}, texts={len(texts)}) ──")

        try:
            resp = await self._client.aio.models.embed_content(
                model=config.EMBEDDING_MODEL,
                contents=texts,
                config=types.EmbedContentConfig(
                    output_dimensionality=config.EMBED_DIM,
                    task_type=task_type,
                ),
            )
        except errors.APIError as e:
            log.error(f"Embed API error (code={e.code}): {e.message}")
            if e.code == 429:
                raise GeminiRateLimitError("Gemini embed rate limit hit") from e
            raise GeminiAPIError(f"Embed API error: {e.message}") from e
        except Exception as e:
            log.error(f"Embed unexpected error ({type(e).__name__}): {e}", exc_info=True)
            raise GeminiAPIError(str(e)) from e

        log.info(f"Gemini embed response: {len(resp.embeddings)} vectors @ {config.EMBED_DIM}d")
        return [e.values for e in resp.embeddings]
