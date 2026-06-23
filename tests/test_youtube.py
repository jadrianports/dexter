"""Tests for YouTubeService with mocked yt-dlp responses."""

import pytest
from unittest.mock import patch, MagicMock

from services.youtube import YouTubeService
from models.queue import Track


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
        {"id": f"vid{i}", "title": f"Song {i}", "url": f"https://youtube.com/watch?v=vid{i}",
         "duration": 180, "thumbnails": []}
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

    def _make_ydl_mock(self, hook_payload: dict):
        """Build a YoutubeDL context-manager mock that fires the hook on .download()."""
        mock_ydl = MagicMock()
        captured_opts = {}

        def fake_init(opts):
            captured_opts.update(opts)
            return mock_ydl

        def fake_download(urls):
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
        hook_payload = {
            "postprocessor": "FFmpegExtractAudio",
            "status": "finished",
            "info_dict": {"acodec": "opus"},
        }
        fake_init, _ = self._make_ydl_mock(hook_payload)

        # Point cache dir to tmp_path so the existence check passes
        opus_file = tmp_path / f"{video_id}.opus"
        opus_file.touch()

        with patch.object(yt_mod, "YoutubeDL", side_effect=fake_init), \
             patch.object(yt_mod.config, "AUDIO_CACHE_DIR", tmp_path), \
             caplog.at_level(logging.INFO, logger="dexter"):
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
        hook_payload = {
            "postprocessor": "FFmpegExtractAudio",
            "status": "finished",
            "info_dict": {"acodec": "aac"},
        }
        fake_init, _ = self._make_ydl_mock(hook_payload)

        opus_file = tmp_path / f"{video_id}.opus"
        opus_file.touch()

        with patch.object(yt_mod, "YoutubeDL", side_effect=fake_init), \
             patch.object(yt_mod.config, "AUDIO_CACHE_DIR", tmp_path), \
             caplog.at_level(logging.INFO, logger="dexter"):
            yt = yt_mod.YouTubeService()
            result = yt.download(video_id, "https://www.youtube.com/watch?v=test_transcode_vid")

        assert result is not None
        log_text = " ".join(r.getMessage() for r in caplog.records)
        assert "codec_path=transcode" in log_text
