"""Tests for yt-dlp self-heal: update helper + download retry-after-update."""

from unittest.mock import MagicMock, patch

import services.youtube as yt
from services.youtube import YouTubeService, update_ytdlp


class TestUpdateYtdlp:
    def test_returns_true_on_success(self):
        with patch("services.youtube.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0)
            assert update_ytdlp() is True
            run.assert_called_once()

    def test_returns_false_on_failure(self):
        with patch("services.youtube.subprocess.run", side_effect=Exception("pip boom")):
            assert update_ytdlp() is False

    def test_update_sets_throttle(self):
        yt._last_ytdlp_update = 0.0
        with patch("services.youtube.subprocess.run", return_value=MagicMock(returncode=0)):
            update_ytdlp()
        assert yt._last_ytdlp_update > 0.0


class TestDownloadRetryAfterUpdate:
    def setup_method(self):
        # Reset the on-failure throttle before each test.
        yt._last_ytdlp_update = 0.0

    def test_updates_and_retries_on_failure(self, tmp_path, monkeypatch):
        monkeypatch.setattr(yt.config, "AUDIO_CACHE_DIR", tmp_path)
        service = YouTubeService()
        cached = tmp_path / "vid123.opus"

        calls = {"n": 0}

        class FakeYDL:
            def __init__(self, opts): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def download(self, urls):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise Exception("first attempt fails")
                cached.write_bytes(b"opus")  # second attempt "succeeds"

        with patch("services.youtube.YoutubeDL", FakeYDL), \
             patch("services.youtube.update_ytdlp", return_value=True) as upd:
            result = service.download("vid123", "https://youtube.com/watch?v=vid123")

        assert calls["n"] == 2          # retried once
        upd.assert_called_once()        # attempted an update
        assert result == cached

    def test_no_update_when_throttled(self, tmp_path, monkeypatch):
        import time
        monkeypatch.setattr(yt.config, "AUDIO_CACHE_DIR", tmp_path)
        yt._last_ytdlp_update = time.monotonic()  # just updated → throttled
        service = YouTubeService()

        class AlwaysFails:
            def __init__(self, opts): pass
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def download(self, urls): raise Exception("nope")

        with patch("services.youtube.YoutubeDL", AlwaysFails), \
             patch("services.youtube.update_ytdlp", return_value=True) as upd:
            result = service.download("vidX", "https://youtube.com/watch?v=vidX")

        assert result is None
        upd.assert_not_called()         # throttle prevented the update
