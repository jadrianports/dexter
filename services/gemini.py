"""Gemini API wrapper with rate limiter. Thin layer — no personality logic."""

from __future__ import annotations

import asyncio
import time
from collections import deque

from google import genai
from google.genai import types, errors

import config
from utils.logger import log


# ──────────────────────────── EXCEPTIONS ────────────────────────────


class GeminiRateLimitError(Exception):
    """Raised when the rate limiter rejects a request."""


class GeminiAPIError(Exception):
    """Raised on Gemini API errors (network, server, etc.)."""


class GeminiRefusalError(Exception):
    """Raised when content is filtered or generation is refused."""


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
                raise GeminiRateLimitError(
                    f"Rate limit full, wait would be {wait_time:.0f}s"
                )

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

    async def chat(
        self,
        system_prompt: str,
        conversation: list[dict],
        priority: int = 1,
    ) -> str | None:
        """Send a chat request to Gemini.

        Args:
            system_prompt: The assembled system instruction.
            conversation: List of {"role": "user"|"model", "content": "..."} dicts.
            priority: 1 = user command, 2 = background task.

        Returns:
            Response text, or None if empty.

        Raises:
            GeminiRateLimitError: Rate limit reached.
            GeminiAPIError: API error.
        """
        await self._rate_limiter.acquire(priority)

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

        # Gemini requires at least one user message
        if not contents:
            contents = "."

        try:
            response = await self._client.aio.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
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
        self, prompt: str, priority: int = 1
    ) -> bytes | None:
        """Generate an image using Gemini native image generation.

        Returns:
            Image bytes, or None if refused/empty.

        Raises:
            GeminiRateLimitError: Rate limit reached.
            GeminiAPIError: API error.
        """
        await self._rate_limiter.acquire(priority)

        try:
            response = await self._client.aio.models.generate_content(
                model=config.IMAGEN_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
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
