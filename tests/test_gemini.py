"""Tests for GeminiService with mocked API calls."""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import errors

import config
from services.gemini import GeminiAPIError, GeminiRateLimitError, GeminiService


class TestGeminiChat:
    @pytest.mark.asyncio
    async def test_chat_returns_text(self):
        mock_response = MagicMock()
        mock_response.text = "i'm a sarcastic bot"

        with patch("services.gemini.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            service = GeminiService(api_key="fake-key")
            result = await service.chat(
                system_prompt="You are sarcastic.",
                conversation=[],
            )
            assert result == "i'm a sarcastic bot"

    @pytest.mark.asyncio
    async def test_chat_empty_response_returns_none(self):
        mock_response = MagicMock()
        mock_response.text = None

        with patch("services.gemini.genai") as mock_genai:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_genai.Client.return_value = mock_client

            service = GeminiService(api_key="fake-key")
            result = await service.chat(
                system_prompt="test",
                conversation=[],
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_chat_api_error_raises(self):
        with patch("services.gemini.genai") as mock_genai:
            mock_client = MagicMock()
            mock_error = Exception("API Error")
            mock_client.aio.models.generate_content = AsyncMock(side_effect=mock_error)
            mock_genai.Client.return_value = mock_client

            service = GeminiService(api_key="fake-key")
            with pytest.raises(GeminiAPIError):
                await service.chat(
                    system_prompt="test",
                    conversation=[],
                )


# ──────────────────────── Phase 17: safety_settings retrofit ────────────────────────


def _mock_service_and_generate(text="roast line"):
    """Return (service, mock_generate) with genai patched and a captured
    generate_content AsyncMock. `text` is the mocked response.text."""
    mock_response = MagicMock()
    mock_response.text = text
    mock_client = MagicMock()
    mock_generate = AsyncMock(return_value=mock_response)
    mock_client.aio.models.generate_content = mock_generate
    return mock_client, mock_generate


class TestGeminiSafetySettings:
    """VIS-03: every user-influenced generate_content config carries explicit safety_settings."""

    @pytest.mark.asyncio
    async def test_plain_chat_threads_text_threshold(self):
        mock_client, mock_generate = _mock_service_and_generate()
        with patch("services.gemini.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            service = GeminiService(api_key="fake-key")
            await service.chat(system_prompt="test", conversation=[])

            _, kwargs = mock_generate.call_args
            settings = kwargs["config"].safety_settings
            assert settings is not None
            assert len(settings) >= 4
            assert all(s.threshold == config.TEXT_SAFETY_THRESHOLD for s in settings)

    @pytest.mark.asyncio
    async def test_vision_chat_uses_real_block_threshold(self):
        mock_client, mock_generate = _mock_service_and_generate()
        with patch("services.gemini.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            service = GeminiService(api_key="fake-key")
            await service.chat(
                system_prompt="test",
                conversation=[{"role": "user", "content": "react"}],
                image_bytes=b"\x89PNG\r\n",
                image_mime_type="image/png",
            )

            _, kwargs = mock_generate.call_args
            settings = kwargs["config"].safety_settings
            assert settings is not None
            assert all(s.threshold == config.VISION_SAFETY_THRESHOLD for s in settings)

    @pytest.mark.asyncio
    async def test_vision_and_text_thresholds_are_distinct(self):
        # The two call shapes must select two DIFFERENT threshold values.
        assert config.VISION_SAFETY_THRESHOLD != config.TEXT_SAFETY_THRESHOLD

    @pytest.mark.asyncio
    async def test_vision_chat_appends_image_part(self):
        mock_client, mock_generate = _mock_service_and_generate()
        with patch("services.gemini.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            service = GeminiService(api_key="fake-key")
            await service.chat(
                system_prompt="test",
                conversation=[{"role": "user", "content": "react"}],
                image_bytes=b"\x89PNG\r\n",
                image_mime_type="image/png",
            )

            _, kwargs = mock_generate.call_args
            contents = kwargs["contents"]
            # image part appended onto the final user turn (>=2 parts on last Content)
            assert len(contents[-1].parts) >= 2

    @pytest.mark.asyncio
    async def test_generate_image_threads_text_threshold(self):
        mock_response = MagicMock()
        mock_response.candidates = None  # short-circuits extraction -> returns None
        mock_client = MagicMock()
        mock_generate = AsyncMock(return_value=mock_response)
        mock_client.aio.models.generate_content = mock_generate
        with patch("services.gemini.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            service = GeminiService(api_key="fake-key")
            await service.generate_image(prompt="a cat")

            _, kwargs = mock_generate.call_args
            settings = kwargs["config"].safety_settings
            assert settings is not None
            assert all(s.threshold == config.TEXT_SAFETY_THRESHOLD for s in settings)

    @pytest.mark.asyncio
    async def test_vision_chat_blocked_response_returns_none(self):
        # VIS-02 hinge: a safety-blocked/empty response returns None, never raises.
        mock_client, mock_generate = _mock_service_and_generate(text=None)
        with patch("services.gemini.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            service = GeminiService(api_key="fake-key")
            result = await service.chat(
                system_prompt="test",
                conversation=[{"role": "user", "content": "react"}],
                image_bytes=b"\x89PNG\r\n",
                image_mime_type="image/png",
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_chat_429_raises_rate_limit_error(self):
        api_err = errors.APIError(429, {"error": {"message": "rate limited"}}, None)
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(side_effect=api_err)
        with patch("services.gemini.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            service = GeminiService(api_key="fake-key")
            with pytest.raises(GeminiRateLimitError):
                await service.chat(system_prompt="test", conversation=[])

    @pytest.mark.asyncio
    async def test_chat_non_429_api_error_raises_api_error(self):
        api_err = errors.APIError(500, {"error": {"message": "boom"}}, None)
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(side_effect=api_err)
        with patch("services.gemini.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            service = GeminiService(api_key="fake-key")
            with pytest.raises(GeminiAPIError):
                await service.chat(system_prompt="test", conversation=[])


# ──────────────────────── Phase 20-03: RATE-01 guild_id usage counter ────────────────────────


def _mock_image_response(image_bytes: bytes = b"\x89PNG\r\n"):
    """Return a MagicMock response shaped like a successful generate_image call."""
    part = MagicMock()
    part.inline_data.data = image_bytes
    content = MagicMock()
    content.parts = [part]
    candidate = MagicMock()
    candidate.content = content
    response = MagicMock()
    response.candidates = [candidate]
    return response


class TestGeminiGuildUsageCounter:
    """RATE-01 / D-08 / D-09: guild-attributable chat/image calls increment a
    per-guild session counter; guild-less calls and embed() are excluded."""

    @pytest.mark.asyncio
    async def test_chat_with_guild_id_increments_usage(self):
        mock_client, _ = _mock_service_and_generate()
        with patch("services.gemini.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            service = GeminiService(api_key="fake-key")

            assert service.guild_usage("g1") == 0
            await service.chat(system_prompt="test", conversation=[], guild_id="g1")
            assert service.guild_usage("g1") == 1
            await service.chat(system_prompt="test", conversation=[], guild_id="g1")
            assert service.guild_usage("g1") == 2

    @pytest.mark.asyncio
    async def test_chat_without_guild_id_not_counted(self):
        mock_client, _ = _mock_service_and_generate()
        with patch("services.gemini.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            service = GeminiService(api_key="fake-key")

            await service.chat(system_prompt="test", conversation=[], guild_id=None)
            await service.chat(system_prompt="test", conversation=[])  # default None
            assert service.guild_usage(None) == 0
            assert service._guild_usage == {}

    @pytest.mark.asyncio
    async def test_two_guild_ids_track_independently(self):
        mock_client, _ = _mock_service_and_generate()
        with patch("services.gemini.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            service = GeminiService(api_key="fake-key")

            await service.chat(system_prompt="test", conversation=[], guild_id="g1")
            await service.chat(system_prompt="test", conversation=[], guild_id="g2")
            await service.chat(system_prompt="test", conversation=[], guild_id="g1")

            assert service.guild_usage("g1") == 2
            assert service.guild_usage("g2") == 1

    def test_guild_usage_unseen_guild_returns_zero(self):
        with patch("services.gemini.genai"):
            service = GeminiService(api_key="fake-key")
            assert service.guild_usage("never-seen") == 0
            assert service.guild_usage(None) == 0

    @pytest.mark.asyncio
    async def test_generate_image_with_guild_id_increments_usage(self):
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(return_value=_mock_image_response())
        with patch("services.gemini.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            service = GeminiService(api_key="fake-key")

            assert service.guild_usage("g2") == 0
            result = await service.generate_image("a cat", guild_id="g2")
            assert result == b"\x89PNG\r\n"
            assert service.guild_usage("g2") == 1

    @pytest.mark.asyncio
    async def test_generate_image_without_guild_id_not_counted(self):
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(return_value=_mock_image_response())
        with patch("services.gemini.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            service = GeminiService(api_key="fake-key")

            await service.generate_image("a cat")
            assert service._guild_usage == {}

    def test_embed_signature_has_no_guild_id_param(self):
        # D-09: embed() lives on the separate 60 RPM limiter and is never tagged.
        sig = inspect.signature(GeminiService.embed)
        assert "guild_id" not in sig.parameters
