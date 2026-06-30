"""Tests for LRCLIB lyrics fallback in services/lyrics.py.

Covers:
- strip_lrc_headers() pure helper (Task 1, TDD RED/GREEN)
- _get_lrclib() mocked HTTP fetch (Task 2)

All tests are fully offline (no live network calls). Network paths are mocked.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# strip_lrc_headers tests (Task 1 — TDD)
# ---------------------------------------------------------------------------


class TestStripLrcHeaders:
    """Pure unit tests for strip_lrc_headers(text) -> str.

    No mocks needed — this is a side-effect-free pure helper.
    """

    def test_removes_standard_header_block(self):
        """All standard LRC metadata header lines are removed; lyrics preserved."""
        from services.lyrics import strip_lrc_headers

        text = (
            "[ti:Bohemian Rhapsody]\n"
            "[ar:Queen]\n"
            "[al:Greatest Hits]\n"
            "[by:]\n"
            "[offset:0]\n"
            "Is this the real life?\n"
            "Is this just fantasy?"
        )
        result = strip_lrc_headers(text)
        assert not result.startswith("[")
        assert "Is this the real life?" in result
        assert "Is this just fantasy?" in result

    def test_passthrough_when_no_headers(self):
        """Text with no LRC headers is returned unchanged (modulo strip)."""
        from services.lyrics import strip_lrc_headers

        text = "Is this the real life?\nIs this just fantasy?"
        result = strip_lrc_headers(text)
        assert result == text

    def test_mid_line_brackets_preserved(self):
        """A bracket expression that is NOT a standalone header line is kept.

        Real lyric lines that happen to contain brackets in the middle of the
        line (not the entire line) must not be stripped.
        """
        from services.lyrics import strip_lrc_headers

        # This is a legitimate lyric line — brackets are mid-line, not the whole line
        text = "It's time [to shine] for real"
        result = strip_lrc_headers(text)
        assert "[to shine]" in result

    def test_whitespace_trimmed(self):
        """Leading and trailing whitespace is removed from the result."""
        from services.lyrics import strip_lrc_headers

        text = "[ti:Title]\n[ar:Artist]\n\n  Some lyrics  \n"
        result = strip_lrc_headers(text)
        assert not result.startswith("[")
        assert not result.startswith(" ")
        assert not result.endswith(" ")

    def test_all_six_standard_tags_stripped(self):
        """ti, ar, al, by, offset, length, re, ve tags are all removed."""
        from services.lyrics import strip_lrc_headers

        text = (
            "[ti:Title]\n"
            "[ar:Artist]\n"
            "[al:Album]\n"
            "[by:contributor]\n"
            "[offset:500]\n"
            "[length:3:45]\n"
            "[re:LRCEditor]\n"
            "[ve:1.0]\n"
            "Some lyric line here"
        )
        result = strip_lrc_headers(text)
        # None of the header lines should remain
        assert "[ti:" not in result
        assert "[ar:" not in result
        assert "[al:" not in result
        assert "[by:" not in result
        assert "[offset:" not in result
        assert "[length:" not in result
        assert "[re:" not in result
        assert "[ve:" not in result
        assert "Some lyric line here" in result

    def test_empty_string_returns_empty(self):
        """Empty input returns empty string."""
        from services.lyrics import strip_lrc_headers

        assert strip_lrc_headers("") == ""

    def test_only_headers_returns_empty(self):
        """Input with only header lines returns empty string after strip."""
        from services.lyrics import strip_lrc_headers

        text = "[ti:Title]\n[ar:Artist]\n[al:Album]\n"
        result = strip_lrc_headers(text)
        assert result == ""


# ---------------------------------------------------------------------------
# _get_lrclib mocked-fetch tests (Task 2)
# ---------------------------------------------------------------------------


class TestGetLrclibMocked:
    """Mocked aiohttp tests for LyricsService._get_lrclib().

    The HTTP layer is patched — no live network calls.
    """

    def _make_response(self, status: int, json_data: list) -> MagicMock:
        """Build a mock aiohttp response context manager returning JSON."""
        mock_resp = MagicMock()
        mock_resp.status = status
        mock_resp.text = AsyncMock(return_value=json.dumps(json_data))
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        return mock_resp

    def _make_session(self, mock_resp: MagicMock) -> MagicMock:
        """Build a mock aiohttp ClientSession context manager."""
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_resp)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        return mock_session

    @pytest.mark.asyncio
    async def test_first_instrumental_second_has_lyrics_returns_second(self):
        """First result is instrumental; second has plainLyrics → returns second's lyrics."""
        from services.lyrics import LyricsService

        data = [
            {"instrumental": True, "plainLyrics": None},
            {
                "instrumental": False,
                "plainLyrics": "Is this the real life?\nIs this just fantasy?\nCaught in a landslide no escape from reality",
            },
        ]
        mock_resp = self._make_response(200, data)
        mock_session = self._make_session(mock_resp)

        service = LyricsService("")
        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await service._get_lrclib("Bohemian Rhapsody", "Queen")

        assert result is not None
        assert "real life" in result

    @pytest.mark.asyncio
    async def test_all_instrumental_returns_none(self):
        """All results are instrumental → returns None."""
        from services.lyrics import LyricsService

        data = [
            {"instrumental": True, "plainLyrics": None},
            {"instrumental": True, "plainLyrics": None},
        ]
        mock_resp = self._make_response(200, data)
        mock_session = self._make_session(mock_resp)

        service = LyricsService("")
        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await service._get_lrclib("Moonlight Sonata", "Beethoven")

        assert result is None

    @pytest.mark.asyncio
    async def test_http_500_returns_none(self):
        """HTTP 500 response → returns None (no exception raised to caller)."""
        from services.lyrics import LyricsService

        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)

        mock_session = self._make_session(mock_resp)

        service = LyricsService("")
        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await service._get_lrclib("Song", "Artist")

        assert result is None

    @pytest.mark.asyncio
    async def test_lrc_headers_stripped_from_plain_lyrics(self):
        """plainLyrics containing LRC metadata headers → headers stripped in returned text."""
        from services.lyrics import LyricsService

        lyrics_with_headers = (
            "[ti:Bohemian Rhapsody]\n"
            "[ar:Queen]\n"
            "[al:Greatest Hits]\n"
            "[by:]\n"
            "[offset:0]\n"
            "Is this the real life?\n"
            "Is this just fantasy?\n"
            "Caught in a landslide no escape from reality"
        )
        data = [
            {
                "instrumental": False,
                "plainLyrics": lyrics_with_headers,
            }
        ]
        mock_resp = self._make_response(200, data)
        mock_session = self._make_session(mock_resp)

        service = LyricsService("")
        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await service._get_lrclib("Bohemian Rhapsody", "Queen")

        assert result is not None
        assert "[ti:" not in result
        assert "[ar:" not in result
        assert "Is this the real life?" in result

    @pytest.mark.asyncio
    async def test_empty_array_returns_none(self):
        """Empty JSON array → returns None."""
        from services.lyrics import LyricsService

        mock_resp = self._make_response(200, [])
        mock_session = self._make_session(mock_resp)

        service = LyricsService("")
        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await service._get_lrclib("Nonexistent Song", "Nonexistent Artist")

        assert result is None

    @pytest.mark.asyncio
    async def test_result_with_empty_plain_lyrics_skipped(self):
        """Results with falsy plainLyrics are skipped; valid later result returned."""
        from services.lyrics import LyricsService

        data = [
            {"instrumental": False, "plainLyrics": ""},
            {"instrumental": False, "plainLyrics": None},
            {
                "instrumental": False,
                "plainLyrics": "Some valid lyric line here\nAnother lyric line\nAnd one more for good measure",
            },
        ]
        mock_resp = self._make_response(200, data)
        mock_session = self._make_session(mock_resp)

        service = LyricsService("")
        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await service._get_lrclib("Song", "Artist")

        assert result is not None
        assert "valid lyric" in result


class TestGetLyricsChainWithLrclib:
    """Tests verifying get_lyrics chains Genius → AZLyrics → LRCLIB."""

    @pytest.mark.asyncio
    async def test_falls_through_to_lrclib_when_both_fail(self):
        """When Genius and AZLyrics both return None, LRCLIB is tried."""
        from services.lyrics import LyricsService

        service = LyricsService("")  # Genius disabled
        service._get_azlyrics = AsyncMock(return_value=None)
        service._get_lrclib = AsyncMock(return_value="LRCLIB lyrics text here")

        result = await service.get_lyrics("Song Title", "Artist Name")

        assert result == "LRCLIB lyrics text here"
        service._get_azlyrics.assert_called_once()
        service._get_lrclib.assert_called_once()

    @pytest.mark.asyncio
    async def test_azlyrics_hit_does_not_call_lrclib(self):
        """When AZLyrics returns lyrics, LRCLIB is not called."""
        from services.lyrics import LyricsService

        service = LyricsService("")  # Genius disabled
        service._get_azlyrics = AsyncMock(return_value="AZLyrics lyrics text")
        service._get_lrclib = AsyncMock(return_value="LRCLIB lyrics text")

        result = await service.get_lyrics("Song Title", "Artist Name")

        assert result == "AZLyrics lyrics text"
        service._get_lrclib.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_three_fail_returns_none(self):
        """When all three sources return None, get_lyrics returns None."""
        from services.lyrics import LyricsService

        service = LyricsService("")  # Genius disabled
        service._get_azlyrics = AsyncMock(return_value=None)
        service._get_lrclib = AsyncMock(return_value=None)

        result = await service.get_lyrics("Nonexistent Song", "No Artist")

        assert result is None
