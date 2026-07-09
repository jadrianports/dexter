"""yt-dlp wrapper for YouTube search, metadata extraction, and download."""

from __future__ import annotations

import asyncio
import functools
import re
import subprocess
import sys
import time
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import ExtractorError as _ExtractorError

import config
from utils.logger import log

_URL_PATTERN = re.compile(r"^https?://")

# On-failure self-update throttle: attempt at most once per hour.
_last_ytdlp_update: float = 0.0
_UPDATE_THROTTLE_SECONDS: float = 3600.0


def _is_transient_ytdlp_error(exc: Exception) -> bool:
    """Return True if the error is plausibly transient and worth retrying.

    ExtractorError.expected=True signals content unavailable / age-restricted —
    a permanent condition that must NOT be retried (A1/A2: [ASSUMED] — no formal
    yt-dlp API docs, but the conservative fallback is sound: any non-expected
    error is treated as transient so we never skip a retry we should make).
    All other errors (network blips, unexpected extractor failures) are transient
    candidates.
    """
    if isinstance(exc, _ExtractorError) and exc.expected:
        return False
    return True


def update_ytdlp() -> bool:
    """Update yt-dlp via pip. Returns True on success. Safe to call from a thread."""
    global _last_ytdlp_update
    _last_ytdlp_update = time.monotonic()  # throttle on-failure retries after any update
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-U", "yt-dlp"],
            check=True,
            capture_output=True,
            timeout=120,
        )
        log.info("yt-dlp updated successfully")
        return True
    except Exception as e:
        log.error(f"yt-dlp update failed: {e}")
        return False


SEARCH_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "noplaylist": True,
}

PLAYLIST_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": True,
    "skip_download": True,
}

EXTRACT_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "skip_download": True,
}

DOWNLOAD_OPTS = {
    "format": "bestaudio/best",
    "postprocessors": [
        {
            "key": "SponsorBlock",
            "categories": config.SPONSORBLOCK_CATEGORIES,
            "when": "after_filter",  # REQUIRED: populates chapters before ModifyChapters runs (Pitfall 1)
        },
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "opus",
            "preferredquality": config.AUDIO_QUALITY,  # unchanged; no effect on copy path (D-01)
        },
        {
            "key": "ModifyChapters",
            "remove_sponsor_segments": config.SPONSORBLOCK_CATEGORIES,
            "remove_chapters_patterns": [],
            "remove_ranges": [],
            "force_keyframes": False,
        },
    ],
    "outtmpl": str(config.AUDIO_CACHE_DIR / "%(id)s.%(ext)s"),
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
}


class YouTubeService:
    """Wraps yt-dlp for search, extract, and download operations."""

    def is_url(self, query: str) -> bool:
        """Check if the query is a URL rather than a search term."""
        return bool(_URL_PATTERN.match(query.strip()))

    def _extract(self, query: str, opts: dict | None = None) -> dict:
        """Synchronous yt-dlp extract_info call."""
        with YoutubeDL(opts or EXTRACT_OPTS) as ydl:
            return ydl.extract_info(query, download=False)

    def search(self, query: str, count: int | None = None) -> list[dict]:
        """Search YouTube and return lightweight result dicts."""
        if count is None:
            count = config.SEARCH_RESULTS_COUNT

        opts = {**SEARCH_OPTS, "default_search": f"ytsearch{count}"}
        data = self._extract(query, opts)

        entries = list(data.get("entries") or [])
        results = []
        for entry in entries[:count]:
            thumbnails = entry.get("thumbnails") or []
            thumbnail = thumbnails[0]["url"] if thumbnails else None
            video_id = entry.get("id", "")
            results.append(
                {
                    "video_id": video_id,
                    "title": entry.get("title", "Unknown"),
                    "url": entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}",
                    "duration": entry.get("duration"),
                    "thumbnail": thumbnail,
                }
            )
        return results

    def extract(self, url: str) -> dict:
        """Full metadata extraction for a single video."""
        data = self._extract(url)

        duration = data.get("duration")
        if duration is None or data.get("is_live"):
            raise ValueError("Livestream URLs are not supported")
        if duration > config.MAX_SONG_DURATION_SECONDS:
            raise ValueError(f"Duration {duration}s exceeds max of {config.MAX_SONG_DURATION_SECONDS}s")

        artist = data.get("artist") or data.get("uploader") or None
        thumbnails = data.get("thumbnails") or []
        thumbnail = thumbnails[-1]["url"] if thumbnails else None

        return {
            "video_id": data["id"],
            "title": data.get("title", "Unknown"),
            "artist": artist,
            "url": data.get("webpage_url", url),
            "duration": duration,
            "thumbnail": thumbnail,
        }

    def extract_playlist(self, url: str) -> list[dict]:
        """Extract entries from a playlist URL. Truncates to MAX_PLAYLIST_IMPORT."""
        opts = {**PLAYLIST_OPTS, "noplaylist": False}
        data = self._extract(url, opts)
        entries = list(data.get("entries") or [])

        results = []
        for entry in entries[: config.MAX_PLAYLIST_IMPORT]:
            thumbnails = entry.get("thumbnails") or []
            thumbnail = thumbnails[0]["url"] if thumbnails else None
            video_id = entry.get("id", "")
            results.append(
                {
                    "video_id": video_id,
                    "title": entry.get("title", "Unknown"),
                    "url": entry.get("webpage_url")
                    or entry.get("url")
                    or f"https://www.youtube.com/watch?v={video_id}",
                    "duration": entry.get("duration"),
                    "thumbnail": thumbnail,
                }
            )
        return results

    def download(self, video_id: str, url: str) -> Path | None:
        """Download audio to cache. Returns file path or None on failure."""
        cached = config.AUDIO_CACHE_DIR / f"{video_id}.opus"
        if cached.exists():
            return cached

        # Codec-path detection closure (D-03): tracks whether FFmpegExtractAudio
        # performed a stream-copy (opus source) or a transcode (non-opus source).
        _codec_path = {"value": "unknown"}

        def _pp_hook(d: dict) -> None:
            if d.get("postprocessor") == "FFmpegExtractAudio" and d.get("status") == "finished":
                acodec = (d.get("info_dict") or {}).get("acodec", "unknown")
                _codec_path["value"] = "copy" if acodec == "opus" else "transcode"

        opts = {**DOWNLOAD_OPTS, "postprocessor_hooks": [_pp_hook]}
        try:
            t0 = time.monotonic()
            with YoutubeDL(opts) as ydl:
                ydl.download([url])
            elapsed = time.monotonic() - t0
            if cached.exists():
                log.info(
                    "download complete video_id=%s codec_path=%s elapsed=%.2fs",
                    video_id,
                    _codec_path["value"],
                    elapsed,
                )
                return cached
            return None
        except Exception as e:
            log.error(f"Download failed for {video_id}: {e}")
            # Self-heal: yt-dlp breaks often. Update (throttled) and retry once.
            global _last_ytdlp_update
            now = time.monotonic()
            if now - _last_ytdlp_update < _UPDATE_THROTTLE_SECONDS:
                return None
            _last_ytdlp_update = now
            log.warning(f"Attempting yt-dlp self-update after download failure for {video_id}")
            if not update_ytdlp():
                return None
            try:
                t0 = time.monotonic()
                with YoutubeDL(opts) as ydl:
                    ydl.download([url])
                elapsed = time.monotonic() - t0
                if cached.exists():
                    log.info(
                        "download complete video_id=%s codec_path=%s elapsed=%.2fs",
                        video_id,
                        _codec_path["value"],
                        elapsed,
                    )
                    return cached
            except Exception as retry_error:
                log.error(f"Retry after update failed for {video_id}: {retry_error}")
            return None

    async def async_search(self, query: str, count: int | None = None) -> list[dict]:
        """Run search with bounded quick-retry + throttled self-heal (REL-06 / D-08).

        Retry budget: YTDLP_MAX_QUICK_RETRIES quick attempts with exponential backoff.
        If all quick retries are exhausted, fall back to a throttled yt-dlp self-update
        (at most once per _UPDATE_THROTTLE_SECONDS) and one final attempt, matching the
        self-heal path already in download(). A permanent ExtractorError (expected=True)
        bypasses both the retry loop and the update path entirely.
        """
        loop = asyncio.get_running_loop()
        last_exc: Exception | None = None
        for attempt in range(config.YTDLP_MAX_QUICK_RETRIES + 1):
            try:
                return await loop.run_in_executor(None, functools.partial(self.search, query, count))
            except Exception as exc:
                last_exc = exc
                if not _is_transient_ytdlp_error(exc):
                    raise  # permanent failure (video unavailable etc.) — don't retry
                if attempt < config.YTDLP_MAX_QUICK_RETRIES:
                    log.warning(
                        "search attempt %d/%d failed (transient): %s",
                        attempt + 1,
                        config.YTDLP_MAX_QUICK_RETRIES + 1,
                        exc,
                    )
                    await asyncio.sleep(config.YTDLP_RETRY_BACKOFF_SECONDS * (attempt + 1))
                else:
                    # All quick retries exhausted — throttled update + one final attempt
                    global _last_ytdlp_update
                    now = time.monotonic()
                    if now - _last_ytdlp_update >= _UPDATE_THROTTLE_SECONDS:
                        log.warning("search exhausted quick retries; attempting yt-dlp update")
                        await loop.run_in_executor(None, update_ytdlp)
                    try:
                        return await loop.run_in_executor(None, functools.partial(self.search, query, count))
                    except Exception as final_exc:
                        log.error("search failed after update: %s", final_exc)
                        raise
        raise last_exc  # unreachable; satisfies type checker

    async def async_extract(self, url: str) -> dict:
        """Run extract with bounded quick-retry + throttled self-heal (REL-06 / D-08).

        Identical structure to async_search — see that method's docstring for the
        retry/update contract. Substitutes self.extract for self.search (no count arg).
        """
        loop = asyncio.get_running_loop()
        last_exc: Exception | None = None
        for attempt in range(config.YTDLP_MAX_QUICK_RETRIES + 1):
            try:
                return await loop.run_in_executor(None, functools.partial(self.extract, url))
            except Exception as exc:
                last_exc = exc
                if not _is_transient_ytdlp_error(exc):
                    raise  # permanent failure — don't retry
                if attempt < config.YTDLP_MAX_QUICK_RETRIES:
                    log.warning(
                        "extract attempt %d/%d failed (transient): %s",
                        attempt + 1,
                        config.YTDLP_MAX_QUICK_RETRIES + 1,
                        exc,
                    )
                    await asyncio.sleep(config.YTDLP_RETRY_BACKOFF_SECONDS * (attempt + 1))
                else:
                    # All quick retries exhausted — throttled update + one final attempt
                    global _last_ytdlp_update
                    now = time.monotonic()
                    if now - _last_ytdlp_update >= _UPDATE_THROTTLE_SECONDS:
                        log.warning("extract exhausted quick retries; attempting yt-dlp update")
                        await loop.run_in_executor(None, update_ytdlp)
                    try:
                        return await loop.run_in_executor(None, functools.partial(self.extract, url))
                    except Exception as final_exc:
                        log.error("extract failed after update: %s", final_exc)
                        raise
        raise last_exc  # unreachable; satisfies type checker

    async def async_download(self, video_id: str, url: str) -> Path | None:
        """Run download in a thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.download, video_id, url)

    async def async_extract_playlist(self, url: str) -> list[dict]:
        """Run playlist extraction in a thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.extract_playlist, url)
