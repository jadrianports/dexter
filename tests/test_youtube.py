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
