"""Tests for services/lyrics.py — pure helpers + LyricsService init.

All tests are fully offline (no network). Network paths are mocked/patched.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Pure helper tests — these will fail until services/lyrics.py is created
# ---------------------------------------------------------------------------


class TestBuildGeniusSearchQuery:
    """Tests for build_genius_search_query(title, artist)."""

    def test_basic_title_and_artist(self):
        from services.lyrics import build_genius_search_query

        title, artist = build_genius_search_query("God's Plan", "Drake")
        assert title == "God's Plan"
        assert artist == "Drake"

    def test_none_artist_returns_empty_string(self):
        from services.lyrics import build_genius_search_query

        title, artist = build_genius_search_query("Blinding Lights", None)
        assert title == "Blinding Lights"
        assert artist == ""

    def test_empty_artist_returns_empty_string(self):
        from services.lyrics import build_genius_search_query

        title, artist = build_genius_search_query("Bohemian Rhapsody", "")
        assert title == "Bohemian Rhapsody"
        assert artist == ""

    def test_feat_suffix_stripped_from_title(self):
        from services.lyrics import build_genius_search_query

        title, _ = build_genius_search_query("Song (feat. Somebody)", "Artist")
        assert "(feat." not in title.lower()

    def test_remix_suffix_stripped_from_title(self):
        from services.lyrics import build_genius_search_query

        title, _ = build_genius_search_query("Track (Remix)", "Artist")
        assert "(remix)" not in title.lower()

    def test_returns_tuple(self):
        from services.lyrics import build_genius_search_query

        result = build_genius_search_query("Song", "Artist")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_youtube_artist_title_split_with_junk_channel(self):
        """The real bug: 'Billy Joel - Vienna (Audio) (Official Audio)' / channel name."""
        from services.lyrics import build_genius_search_query

        title, artist = build_genius_search_query("Billy Joel - Vienna (Audio) (Official Audio)", "Trackateering Music")
        assert title == "Vienna"
        assert artist == "Billy Joel"

    def test_strips_official_music_video_and_vevo_channel(self):
        from services.lyrics import build_genius_search_query

        title, artist = build_genius_search_query(
            "Rick Astley - Never Gonna Give You Up (Official Music Video)", "RickAstleyVEVO"
        )
        assert title == "Never Gonna Give You Up"
        assert artist == "Rick Astley"

    def test_topic_channel_artist_ignored(self):
        from services.lyrics import build_genius_search_query

        title, artist = build_genius_search_query("Adele - Hello", "Adele - Topic")
        assert title == "Hello"
        assert artist == "Adele"

    def test_noise_tag_stripped_but_real_parenthetical_kept(self):
        from services.lyrics import build_genius_search_query

        t1, _ = build_genius_search_query("Hello (Official Video)", "Adele")
        assert t1 == "Hello"
        t2, _ = build_genius_search_query("Wake Me Up (When September Ends)", "Green Day")
        assert "(When September Ends)" in t2

    def test_reliable_artist_kept_when_title_has_artist_prefix(self):
        from services.lyrics import build_genius_search_query

        title, artist = build_genius_search_query("Drake - God's Plan (Official Audio)", "Drake")
        assert title == "God's Plan"
        assert artist == "Drake"

    def test_random_reuploader_channel_ignored_for_split_title(self):
        """The deeper bug: a random re-uploader name must NOT be used as the artist
        when the title already carries 'Artist - Title' (e.g. Rodrigo Lima / LatinHype)."""
        from services.lyrics import build_genius_search_query

        title, artist = build_genius_search_query("Arctic Monkeys - Suck It And See", "Rodrigo Lima")
        assert title == "Suck It And See"
        assert artist == "Arctic Monkeys"

        title2, artist2 = build_genius_search_query("Joji - Glimpse Of Us", "LatinHype")
        assert title2 == "Glimpse Of Us"
        assert artist2 == "Joji"

    def test_artist_matches_helper(self):
        from services.lyrics import _artist_matches

        assert _artist_matches("Arctic Monkeys", "Arctic Monkeys")
        assert _artist_matches("Joji", "Joji (Ft. Diplo)")
        assert not _artist_matches("Arctic Monkeys", "Rodrigo Lima")
        assert _artist_matches("", "anything")  # nothing to validate -> allow


class TestBuildAZLyricsUrl:
    """Tests for build_azlyrics_url(artist, song)."""

    def test_basic_url_construction(self):
        from services.lyrics import build_azlyrics_url

        url = build_azlyrics_url("Drake", "God's Plan")
        assert url == "https://www.azlyrics.com/lyrics/drake/godsplan.html"

    def test_artist_lowercased(self):
        from services.lyrics import build_azlyrics_url

        url = build_azlyrics_url("THE WEEKND", "Blinding Lights")
        assert "theweeknd" in url

    def test_non_alphanum_stripped_from_artist(self):
        from services.lyrics import build_azlyrics_url

        url = build_azlyrics_url("Drake!", "Track")
        # The exclamation mark must be removed from the artist segment
        assert "drake!" not in url
        assert "drake" in url

    def test_non_alphanum_stripped_from_song(self):
        from services.lyrics import build_azlyrics_url

        url = build_azlyrics_url("Drake", "God's Plan")
        # Apostrophe and space must be stripped
        assert "god's" not in url
        assert "godsplan" in url

    def test_path_traversal_stripped(self):
        """../  characters must not survive the URL builder (T-03-06)."""
        from services.lyrics import build_azlyrics_url

        url = build_azlyrics_url("a/../b", "x")
        assert ".." not in url
        # Only the fixed host path should have slashes
        assert url.startswith("https://www.azlyrics.com/lyrics/")

    def test_at_sign_stripped(self):
        """@ must be stripped — kills potential SSRF header injection."""
        from services.lyrics import build_azlyrics_url

        url = build_azlyrics_url("@evil", "track")
        assert "@" not in url.replace("https://", "")

    def test_host_is_hardcoded_azlyrics(self):
        from services.lyrics import build_azlyrics_url

        url = build_azlyrics_url("anyartist", "anysong")
        assert url.startswith("https://www.azlyrics.com/lyrics/")
        assert url.endswith(".html")


class TestChunkLyrics:
    """Tests for chunk_lyrics(lyrics, page_size)."""

    def test_short_lyrics_single_chunk(self):
        from services.lyrics import chunk_lyrics

        lyrics = "line one\nline two\nline three"
        chunks = chunk_lyrics(lyrics, page_size=1500)
        assert len(chunks) == 1
        assert chunks[0] == lyrics

    def test_long_lyrics_split_into_multiple_chunks(self):
        from services.lyrics import chunk_lyrics

        # Build lyrics larger than 100 chars
        lines = ["a" * 40] * 10  # 400 chars total
        lyrics = "\n".join(lines)
        chunks = chunk_lyrics(lyrics, page_size=100)
        assert len(chunks) > 1

    def test_no_chunk_exceeds_page_size(self):
        from services.lyrics import chunk_lyrics

        lines = ["word " * 10] * 50  # ~50 lines of 50 chars each
        lyrics = "\n".join(lines)
        page_size = 200
        chunks = chunk_lyrics(lyrics, page_size=page_size)
        for chunk in chunks:
            assert len(chunk) <= page_size + 50  # allow line-boundary overage

    def test_rejoining_preserves_all_lines(self):
        from services.lyrics import chunk_lyrics

        lines = [f"line {i}" for i in range(30)]
        lyrics = "\n".join(lines)
        chunks = chunk_lyrics(lyrics, page_size=100)
        rejoined = "\n".join(chunks)
        for line in lines:
            assert line in rejoined

    def test_empty_lyrics_returns_empty_list_or_single_empty(self):
        from services.lyrics import chunk_lyrics

        chunks = chunk_lyrics("", page_size=1500)
        # Either empty list or list with one empty string is acceptable
        assert isinstance(chunks, list)

    def test_custom_page_size_respected(self):
        from services.lyrics import chunk_lyrics

        long_line = "x" * 300
        lyrics = f"{long_line}\n{long_line}\n{long_line}"
        chunks = chunk_lyrics(lyrics, page_size=500)
        assert len(chunks) >= 2


class TestSanitizeLyrics:
    """Tests for sanitize_lyrics(text)."""

    def test_html_tags_stripped(self):
        from services.lyrics import sanitize_lyrics

        text = "<b>Hello</b> <script>alert(1)</script> world"
        result = sanitize_lyrics(text)
        assert "<b>" not in result
        assert "<script>" not in result
        assert "Hello" in result
        assert "world" in result

    def test_everyone_mention_neutralized(self):
        """@everyone must not be a bare pinging string (T-03-07)."""
        from services.lyrics import sanitize_lyrics

        result = sanitize_lyrics("@everyone hello")
        # The @ must be broken — either stripped or zero-width space inserted
        assert "@everyone" not in result

    def test_here_mention_neutralized(self):
        """@here must not be a bare pinging string (T-03-07)."""
        from services.lyrics import sanitize_lyrics

        result = sanitize_lyrics("@here what's up")
        assert "@here" not in result

    def test_plain_text_preserved(self):
        from services.lyrics import sanitize_lyrics

        text = "just a normal lyric line\nwith no special markup"
        result = sanitize_lyrics(text)
        assert "normal lyric line" in result

    def test_mention_broken_preserves_surrounding_text(self):
        from services.lyrics import sanitize_lyrics

        result = sanitize_lyrics("hey @everyone how are you")
        assert "how are you" in result


class TestExtractAzlyrics:
    """Tests for extract_azlyrics(html) with inline HTML fixtures."""

    # Minimal AZLyrics-shaped HTML: lyrics in a classless div of reasonable length
    AZLYRICS_FIXTURE = """<!DOCTYPE html>
<html>
<head><title>Song - Artist Lyrics | AZLyrics.com</title></head>
<body>
<div class="col-xs-12 col-lg-8 text-center">
  <div class="lyricsh"><h2>Song Lyrics</h2></div>
  <!-- Usage of azlyrics.com content by any third-party lyrics provider is prohibited -->
  <div>
Oh baby when the night falls
And the stars come out
I will hold you tight
And never let you go
This is a lyric line that makes the div text long enough to be detected
as actual lyrics content by the extraction function.
  </div>
  <!-- end of lyrics -->
</div>
</body>
</html>"""

    # Alert/bot-detection page (short or suspicious content)
    ALERT_FIXTURE = """<!DOCTYPE html>
<html>
<head><title>AZLyrics</title></head>
<body>
<div>Please verify you are human.</div>
</body>
</html>"""

    def test_extracts_lyrics_from_valid_page(self):
        from services.lyrics import extract_azlyrics

        result = extract_azlyrics(self.AZLYRICS_FIXTURE)
        assert result is not None
        # Should contain some of the lyric text
        assert len(result) > 50

    def test_returns_none_for_short_alert_page(self):
        from services.lyrics import extract_azlyrics

        result = extract_azlyrics(self.ALERT_FIXTURE)
        # Alert page div is too short to be lyrics
        assert result is None

    def test_returns_none_for_empty_html(self):
        from services.lyrics import extract_azlyrics

        result = extract_azlyrics("<html><body></body></html>")
        assert result is None

    def test_result_is_string_when_found(self):
        from services.lyrics import extract_azlyrics

        result = extract_azlyrics(self.AZLYRICS_FIXTURE)
        if result is not None:
            assert isinstance(result, str)


class TestLyricsServiceInit:
    """Tests for LyricsService.__init__ graceful degradation."""

    def test_empty_token_initializes_without_raising(self):
        """LyricsService('') must not raise (Assumption A4, graceful degradation)."""
        from services.lyrics import LyricsService

        service = LyricsService("")
        assert service is not None

    def test_none_token_initializes_without_raising(self):
        from services.lyrics import LyricsService

        service = LyricsService(None)
        assert service is not None

    def test_empty_token_sets_genius_to_none(self):
        """When no token, _genius must be None so _get_genius fast-returns None."""
        from services.lyrics import LyricsService

        service = LyricsService("")
        assert service._genius is None

    def test_valid_token_creates_genius_instance(self):
        """With a token, _genius should be a Genius instance (not None)."""
        from lyricsgenius import Genius

        from services.lyrics import LyricsService

        # We do NOT want to make real network calls, so patch the Genius constructor
        with patch("services.lyrics.Genius") as mock_genius_cls:
            mock_genius_cls.return_value = MagicMock()
            LyricsService("fake-token-value")
            # Genius() was called once with the token
            mock_genius_cls.assert_called_once()
            call_args = mock_genius_cls.call_args
            assert call_args[0][0] == "fake-token-value"

    def test_valid_token_constructs_against_real_genius(self):
        """Regression: constructing with a token must NOT raise against the REAL
        lyricsgenius API (do not mock Genius here). The mocked test above hid a
        lyricsgenius 3.x signature change — the `verbose` kwarg was removed —
        which raised TypeError at init and aborted on_ready before cogs loaded."""
        from services.lyrics import LyricsService

        service = LyricsService("dummy-token-never-used-for-network")
        assert service._genius is not None

    @pytest.mark.asyncio
    async def test_get_genius_returns_none_when_no_token(self):
        """_get_genius must fast-return None when _genius is None."""
        from services.lyrics import LyricsService

        service = LyricsService("")
        result = await service._get_genius("Some Song", "Some Artist")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_lyrics_returns_none_when_both_fail(self):
        """get_lyrics returns None when Genius returns None and AZLyrics returns None."""
        from services.lyrics import LyricsService

        service = LyricsService("")  # Genius disabled
        # Patch _get_azlyrics to also return None
        service._get_azlyrics = AsyncMock(return_value=None)
        result = await service.get_lyrics("NonExistentSong", "NoArtist")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_lyrics_falls_back_to_azlyrics(self):
        """When Genius returns None, get_lyrics tries AZLyrics."""
        from services.lyrics import LyricsService

        service = LyricsService("")  # Genius disabled -> _get_genius returns None
        service._get_azlyrics = AsyncMock(return_value="AZLyrics lyrics text")
        result = await service.get_lyrics("Song", "Artist")
        assert result == "AZLyrics lyrics text"
        service._get_azlyrics.assert_called_once()

    @pytest.mark.asyncio
    async def test_genius_result_returned_without_azlyrics_call(self):
        """When Genius succeeds, AZLyrics is not called."""
        from services.lyrics import LyricsService

        service = LyricsService("")
        service._get_genius = AsyncMock(return_value="Genius lyrics text")
        service._get_azlyrics = AsyncMock(return_value="AZLyrics would not be called")
        result = await service.get_lyrics("Song", "Artist")
        assert result == "Genius lyrics text"
        service._get_azlyrics.assert_not_called()
