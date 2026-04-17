"""Tests for GeminiService with mocked API calls."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.gemini import GeminiService, GeminiAPIError, GeminiRateLimitError


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
