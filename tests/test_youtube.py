"""Tests for YouTubeService with mocked yt-dlp responses."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.queue import Track
from services.youtube import YouTubeService


@pytest.fixture
def yt_service():
    return YouTubeService()


MOCK_SEARCH_RESULT = {
    "entries": [
        {
            "id": "abc123",
            "title": "Test Song - Test Artist",
            "url": "https://www.youtube.com/watch?v=abc123",
            "duration": 200,
            "thumbnails": [{"url": "https://i.ytimg.com/vi/abc123/default.jpg"}],
        },
        {
            "id": "def456",
            "title": "Another Song",
            "url": "https://www.youtube.com/watch?v=def456",
            "duration": 180,
            "thumbnails": [{"url": "https://i.ytimg.com/vi/def456/default.jpg"}],
        },
    ]
}

MOCK_EXTRACT_RESULT = {
    "id": "abc123",
    "title": "Test Song",
    "uploader": "Test Artist",
    "artist": "Test Artist",
    "webpage_url": "https://www.youtube.com/watch?v=abc123",
    "duration": 200,
    "thumbnails": [{"url": "https://i.ytimg.com/vi/abc123/hqdefault.jpg"}],
    "is_live": False,
}

MOCK_LIVESTREAM_RESULT = {
    "id": "live123",
    "title": "24/7 Lofi",
    "uploader": "Lofi Girl",
    "webpage_url": "https://www.youtube.com/watch?v=live123",
    "duration": None,
    "is_live": True,
    "thumbnails": [],
}

MOCK_PLAYLIST_RESULT = {
    "entries": [
        {
            "id": f"vid{i}",
            "title": f"Song {i}",
            "url": f"https://youtube.com/watch?v=vid{i}",
            "duration": 180,
            "thumbnails": [],
        }
        for i in range(60)
    ]
}


class TestSearch:
    def test_search_returns_results(self, yt_service):
        with patch.object(yt_service, "_extract", return_value=MOCK_SEARCH_RESULT):
            results = yt_service.search("test query")
        assert len(results) == 2
        assert results[0]["video_id"] == "abc123"
        assert results[0]["title"] == "Test Song - Test Artist"
        assert results[0]["duration"] == 200

    def test_search_respects_count(self, yt_service):
        with patch.object(yt_service, "_extract", return_value=MOCK_SEARCH_RESULT):
            results = yt_service.search("test", count=1)
        assert len(results) == 1


class TestExtract:
    def test_extract_returns_track_data(self, yt_service):
        with patch.object(yt_service, "_extract", return_value=MOCK_EXTRACT_RESULT):
            data = yt_service.extract("https://youtube.com/watch?v=abc123")
        assert data["video_id"] == "abc123"
        assert data["title"] == "Test Song"
        assert data["artist"] == "Test Artist"
        assert data["duration"] == 200

    def test_extract_livestream_raises(self, yt_service):
        with patch.object(yt_service, "_extract", return_value=MOCK_LIVESTREAM_RESULT):
            with pytest.raises(ValueError, match="[Ll]ivestream"):
                yt_service.extract("https://youtube.com/watch?v=live123")

    def test_extract_too_long_raises(self, yt_service):
        long_video = {**MOCK_EXTRACT_RESULT, "duration": 1200}
        with patch.object(yt_service, "_extract", return_value=long_video):
            with pytest.raises(ValueError, match="[Dd]uration|[Ll]ong"):
                yt_service.extract("https://youtube.com/watch?v=abc123")

    def test_extract_falls_back_to_uploader(self, yt_service):
        no_artist = {**MOCK_EXTRACT_RESULT, "artist": None}
        with patch.object(yt_service, "_extract", return_value=no_artist):
            data = yt_service.extract("https://youtube.com/watch?v=abc123")
        assert data["artist"] == "Test Artist"  # falls back to uploader


class TestPlaylist:
    def test_playlist_truncates_to_max(self, yt_service):
        with patch.object(yt_service, "_extract", return_value=MOCK_PLAYLIST_RESULT):
            results = yt_service.extract_playlist("https://youtube.com/playlist?list=PL123")
        assert len(results) == 50  # MAX_PLAYLIST_IMPORT from config


class TestIsUrl:
    def test_youtube_url(self, yt_service):
        assert yt_service.is_url("https://www.youtube.com/watch?v=abc123") is True

    def test_youtu_be_url(self, yt_service):
        assert yt_service.is_url("https://youtu.be/abc123") is True

    def test_search_query(self, yt_service):
        assert yt_service.is_url("blinding lights the weeknd") is False

    def test_http_generic(self, yt_service):
        assert yt_service.is_url("http://example.com") is True


class TestDownloadOpts:
    """Tests for DOWNLOAD_OPTS postprocessor list shape and ordering (PERF-07)."""

    def test_has_sponsorblock_and_modifychapters(self):
        from services.youtube import DOWNLOAD_OPTS

        keys = [pp["key"] for pp in DOWNLOAD_OPTS["postprocessors"]]
        assert "SponsorBlock" in keys
        assert "ModifyChapters" in keys
        assert "FFmpegExtractAudio" in keys

    def test_sponsorblock_when(self):
        from services.youtube import DOWNLOAD_OPTS

        sb = next(pp for pp in DOWNLOAD_OPTS["postprocessors"] if pp["key"] == "SponsorBlock")
        assert sb["when"] == "after_filter"

    def test_pp_order(self):
        from services.youtube import DOWNLOAD_OPTS

        keys = [pp["key"] for pp in DOWNLOAD_OPTS["postprocessors"]]
        assert keys.index("FFmpegExtractAudio") < keys.index("ModifyChapters")

    def test_categories_wired(self):
        import config
        from services.youtube import DOWNLOAD_OPTS

        sb = next(pp for pp in DOWNLOAD_OPTS["postprocessors"] if pp["key"] == "SponsorBlock")
        assert sb["categories"] == config.SPONSORBLOCK_CATEGORIES


class TestCodecLogging:
    """Tests for codec-path logging via postprocessor_hooks in download() (PERF-02/D-03)."""

    def _make_ydl_mock(self, hook_payload: dict, opus_file_to_create=None):
        """Build a YoutubeDL context-manager mock that fires the hook on .download().

        ``opus_file_to_create`` — if provided, the mock creates this file during .download()
        to simulate yt-dlp writing the cache file (so the post-download existence check passes).
        """
        mock_ydl = MagicMock()
        captured_opts = {}

        def fake_init(opts):
            captured_opts.update(opts)
            return mock_ydl

        def fake_download(urls):
            # Simulate yt-dlp writing the output file before firing hooks
            if opus_file_to_create is not None:
                opus_file_to_create.touch()
            for hook_fn in captured_opts.get("postprocessor_hooks", []):
                hook_fn(hook_payload)

        mock_ydl.__enter__ = lambda s: s
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.download = fake_download
        return fake_init, captured_opts

    def test_copy_logged(self, tmp_path, caplog):
        """opus source → codec_path=copy is logged."""
        import logging
        from unittest.mock import patch

        import services.youtube as yt_mod

        video_id = "test_copy_vid"
        opus_file = tmp_path / f"{video_id}.opus"
        hook_payload = {
            "postprocessor": "FFmpegExtractAudio",
            "status": "finished",
            "info_dict": {"acodec": "opus"},
        }
        # File must NOT exist before download; the mock creates it inside fake_download
        fake_init, _ = self._make_ydl_mock(hook_payload, opus_file_to_create=opus_file)

        with (
            patch.object(yt_mod, "YoutubeDL", side_effect=fake_init),
            patch.object(yt_mod.config, "AUDIO_CACHE_DIR", tmp_path),
            caplog.at_level(logging.INFO, logger="dexter"),
        ):
            yt = yt_mod.YouTubeService()
            result = yt.download(video_id, "https://www.youtube.com/watch?v=test_copy_vid")

        assert result is not None
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "codec_path=copy" in log_text

    def test_transcode_logged(self, tmp_path, caplog):
        """non-opus source (aac) → codec_path=transcode is logged."""
        import logging
        from unittest.mock import patch

        import services.youtube as yt_mod

        video_id = "test_transcode_vid"
        opus_file = tmp_path / f"{video_id}.opus"
        hook_payload = {
            "postprocessor": "FFmpegExtractAudio",
            "status": "finished",
            "info_dict": {"acodec": "aac"},
        }
        fake_init, _ = self._make_ydl_mock(hook_payload, opus_file_to_create=opus_file)

        with (
            patch.object(yt_mod, "YoutubeDL", side_effect=fake_init),
            patch.object(yt_mod.config, "AUDIO_CACHE_DIR", tmp_path),
            caplog.at_level(logging.INFO, logger="dexter"),
        ):
            yt = yt_mod.YouTubeService()
            result = yt.download(video_id, "https://www.youtube.com/watch?v=test_transcode_vid")

        assert result is not None
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "codec_path=transcode" in log_text


# ---------------------------------------------------------------------------
# REL-06: bounded-retry + throttled self-heal for async_search / async_extract
# ---------------------------------------------------------------------------


class TestIsTransientYtdlpError:
    """Unit tests for the _is_transient_ytdlp_error permanent-vs-transient classifier."""

    def test_extractor_error_expected_true_is_permanent(self):
        """ExtractorError.expected=True → content unavailable (permanent) — do not retry."""
        from yt_dlp.utils import ExtractorError

        from services.youtube import _is_transient_ytdlp_error

        exc = ExtractorError("Video unavailable", expected=True)
        assert _is_transient_ytdlp_error(exc) is False

    def test_extractor_error_expected_false_is_transient(self):
        """ExtractorError.expected=False → unexpected extractor failure — treat as transient."""
        from yt_dlp.utils import ExtractorError

        from services.youtube import _is_transient_ytdlp_error

        exc = ExtractorError("Unexpected extractor failure", expected=False)
        assert _is_transient_ytdlp_error(exc) is True

    def test_generic_exception_is_transient(self):
        """Any non-ExtractorError (network timeout, connection reset) → transient."""
        from services.youtube import _is_transient_ytdlp_error

        exc = Exception("connection reset by peer")
        assert _is_transient_ytdlp_error(exc) is True


class TestAsyncSearchRetry:
    """Tests for bounded quick-retry + throttled self-heal in async_search (REL-06 / D-08)."""

    def setup_method(self):
        # Reset the on-failure throttle before each test (mirrors test_ytdlp_selfheal.py pattern)
        import services.youtube as yt_mod

        yt_mod._last_ytdlp_update = 0.0

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self, yt_service):
        """Happy path: succeeds immediately — no retry, no sleep, no update."""
        with (
            patch.object(yt_service, "search", return_value=[{"video_id": "abc"}]) as mock_s,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch("services.youtube.update_ytdlp") as mock_update,
        ):
            result = await yt_service.async_search("happy path")

        assert result == [{"video_id": "abc"}]
        mock_s.assert_called_once()
        mock_sleep.assert_not_called()
        mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_transient_failure_retries_and_recovers(self, yt_service):
        """Transient fail on attempt 1, success on attempt 2 — one backoff sleep, no update."""
        call_count = {"n": 0}

        def flaky_search(q, c=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise Exception("transient network blip")
            return [{"video_id": "rec"}]

        with (
            patch.object(yt_service, "search", side_effect=flaky_search),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch("services.youtube.update_ytdlp") as mock_update,
        ):
            result = await yt_service.async_search("query")

        assert result == [{"video_id": "rec"}]
        assert call_count["n"] == 2
        assert mock_sleep.call_count == 1
        mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_permanent_extractor_error_propagates_immediately(self, yt_service):
        """ExtractorError(expected=True) — search called once, no sleep, no update, re-raised."""
        from yt_dlp.utils import ExtractorError

        exc = ExtractorError("Video unavailable", expected=True)
        with (
            patch.object(yt_service, "search", side_effect=exc) as mock_s,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch("services.youtube.update_ytdlp") as mock_update,
        ):
            with pytest.raises(ExtractorError):
                await yt_service.async_search("blocked query")

        mock_s.assert_called_once()
        mock_sleep.assert_not_called()
        mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_exhausted_retries_calls_update_once(self, yt_service):
        """All quick retries exhausted + outside throttle → update called exactly once."""
        import config as cfg
        import services.youtube as yt_mod

        yt_mod._last_ytdlp_update = 0.0  # outside throttle window

        with (
            patch.object(yt_service, "search", side_effect=Exception("persistent")) as mock_s,
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch("services.youtube.update_ytdlp", return_value=True) as mock_update,
        ):
            with pytest.raises(Exception, match="persistent"):
                await yt_service.async_search("query")

        mock_update.assert_called_once()
        # quick-retry loop: YTDLP_MAX_QUICK_RETRIES+1 attempts + 1 final after update
        assert mock_s.call_count == cfg.YTDLP_MAX_QUICK_RETRIES + 2

    @pytest.mark.asyncio
    async def test_exhausted_retries_skips_update_when_throttled(self, yt_service):
        """All quick retries exhausted but within throttle window → update is skipped."""
        import time

        import services.youtube as yt_mod

        yt_mod._last_ytdlp_update = time.monotonic()  # just updated — throttled

        with (
            patch.object(yt_service, "search", side_effect=Exception("throttled")),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch("services.youtube.update_ytdlp") as mock_update,
        ):
            with pytest.raises(Exception):
                await yt_service.async_search("query")

        mock_update.assert_not_called()


class TestAsyncExtractRetry:
    """Tests for bounded quick-retry + throttled self-heal in async_extract (REL-06 / D-08)."""

    def setup_method(self):
        import services.youtube as yt_mod

        yt_mod._last_ytdlp_update = 0.0

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self, yt_service):
        """Happy path: succeeds immediately — no retry, no sleep, no update."""
        with (
            patch.object(yt_service, "extract", return_value={"video_id": "abc"}) as mock_e,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch("services.youtube.update_ytdlp") as mock_update,
        ):
            result = await yt_service.async_extract("https://youtube.com/watch?v=abc")

        assert result == {"video_id": "abc"}
        mock_e.assert_called_once()
        mock_sleep.assert_not_called()
        mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_transient_failure_retries_and_recovers(self, yt_service):
        """Transient fail on attempt 1, success on attempt 2 — one backoff sleep, no update."""
        call_count = {"n": 0}

        def flaky_extract(url):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise Exception("transient blip")
            return {"video_id": "abc"}

        with (
            patch.object(yt_service, "extract", side_effect=flaky_extract),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch("services.youtube.update_ytdlp") as mock_update,
        ):
            result = await yt_service.async_extract("https://youtube.com/watch?v=abc")

        assert result == {"video_id": "abc"}
        assert call_count["n"] == 2
        assert mock_sleep.call_count == 1
        mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_permanent_extractor_error_propagates_immediately(self, yt_service):
        """ExtractorError(expected=True) — extract called once, no sleep, no update, re-raised."""
        from yt_dlp.utils import ExtractorError

        exc = ExtractorError("Video unavailable", expected=True)
        with (
            patch.object(yt_service, "extract", side_effect=exc) as mock_e,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch("services.youtube.update_ytdlp") as mock_update,
        ):
            with pytest.raises(ExtractorError):
                await yt_service.async_extract("https://youtube.com/watch?v=blocked")

        mock_e.assert_called_once()
        mock_sleep.assert_not_called()
        mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_exhausted_retries_calls_update_once(self, yt_service):
        """All quick retries exhausted + outside throttle → update called exactly once."""
        import config as cfg
        import services.youtube as yt_mod

        yt_mod._last_ytdlp_update = 0.0

        with (
            patch.object(yt_service, "extract", side_effect=Exception("blip")) as mock_e,
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch("services.youtube.update_ytdlp", return_value=True) as mock_update,
        ):
            with pytest.raises(Exception, match="blip"):
                await yt_service.async_extract("https://youtube.com/watch?v=x")

        mock_update.assert_called_once()
        assert mock_e.call_count == cfg.YTDLP_MAX_QUICK_RETRIES + 2

    @pytest.mark.asyncio
    async def test_exhausted_retries_skips_update_when_throttled(self, yt_service):
        """All quick retries exhausted but within throttle window → update is skipped."""
        import time

        import services.youtube as yt_mod

        yt_mod._last_ytdlp_update = time.monotonic()  # just updated — throttled

        with (
            patch.object(yt_service, "extract", side_effect=Exception("throttled")),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch("services.youtube.update_ytdlp") as mock_update,
        ):
            with pytest.raises(Exception):
                await yt_service.async_extract("https://youtube.com/watch?v=x")

        mock_update.assert_not_called()
