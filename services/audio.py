"""FFmpeg audio source management and cache cleanup."""

from __future__ import annotations

import os
from pathlib import Path

import discord

import config
from models.queue import Track
from utils.logger import log

# FFmpeg reconnect flags shared across stream and seeked/filtered paths
_RECONNECT_FLAGS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"

# FFmpeg options for stream fallback (non-opus sources)
FFMPEG_STREAM_OPTS = {
    "before_options": _RECONNECT_FLAGS,
    "options": "-vn",
}


def _build_ffmpeg_opts(
    seek_seconds: int = 0, ffmpeg_filter: str | None = None
) -> dict:
    """Build FFmpeg before_options/options for a seeked or filtered source.

    - Always includes reconnect flags in before_options.
    - Prepends -ss {seek_seconds} only when seek_seconds > 0.
    - Appends -af "{ffmpeg_filter}" to options only when a filter is set.
    - With neither seek nor filter the result is equivalent to FFMPEG_STREAM_OPTS
      (reconnect flags + -vn), so callers can safely pass the result through
      without special-casing the passthrough default.

    Pure function — fully unit-testable (no FFmpeg invocation).
    """
    before = _RECONNECT_FLAGS
    if seek_seconds > 0:
        before = f"-ss {seek_seconds} {before}"

    options = "-vn"
    if ffmpeg_filter:
        options = f'-vn -af "{ffmpeg_filter}"'

    return {"before_options": before, "options": options}


class AudioService:
    """Manages FFmpeg audio sources and the download cache."""

    def __init__(
        self,
        youtube_service,
        cache_dir: Path | None = None,
        max_cache_mb: int | None = None,
    ) -> None:
        self.youtube_service = youtube_service
        self.cache_dir = cache_dir or config.AUDIO_CACHE_DIR
        self.max_cache_mb = max_cache_mb or config.AUDIO_CACHE_MAX_MB
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def cache_path(self, video_id: str) -> Path:
        """Return the cache file path for a video ID."""
        return self.cache_dir / f"{video_id}.opus"

    def is_cached(self, video_id: str) -> bool:
        """Check if a video's audio is in the cache."""
        return self.cache_path(video_id).exists()

    async def get_source(
        self,
        track: Track,
        *,
        seek_seconds: int = 0,
        ffmpeg_filter: str | None = None,
    ) -> discord.AudioSource:
        """Get a playable audio source for a track.

        When seek_seconds == 0 and ffmpeg_filter is None the existing
        opus-passthrough behaviour is preserved exactly (D-12): cached tracks
        use FFmpegOpusAudio with no extra options, downloaded tracks likewise.
        A transcode path is taken ONLY when a seek or filter is requested.

        Args:
            track: the track to play.
            seek_seconds: start playback from this offset (0 = beginning).
            ffmpeg_filter: FFmpeg -af chain string from config.FFMPEG_FILTERS, or
                None for no filter.
        """
        cached = self.cache_path(track.video_id)
        use_opts = seek_seconds > 0 or ffmpeg_filter is not None

        # 1. Cache hit
        if cached.exists():
            log.info(f"Cache hit for {track.video_id}")
            if not use_opts:
                # Opus passthrough — D-12 default path, unchanged
                return discord.FFmpegOpusAudio(str(cached))
            opts = _build_ffmpeg_opts(seek_seconds, ffmpeg_filter)
            return discord.FFmpegOpusAudio(str(cached), **opts)

        # 2. Try downloading to cache
        path = await self.youtube_service.async_download(track.video_id, track.url)
        if path and path.exists():
            if not use_opts:
                return discord.FFmpegOpusAudio(str(path))
            opts = _build_ffmpeg_opts(seek_seconds, ffmpeg_filter)
            return discord.FFmpegOpusAudio(str(path), **opts)

        # 3. Stream fallback — re-extract for fresh URL
        log.warning(f"Download failed for {track.video_id}, falling back to stream")
        try:
            data = await self.youtube_service.async_extract(track.url)
            stream_url = data.get("url") or track.url
            if not use_opts:
                return discord.FFmpegPCMAudio(stream_url, **FFMPEG_STREAM_OPTS)
            opts = _build_ffmpeg_opts(seek_seconds, ffmpeg_filter)
            return discord.FFmpegPCMAudio(stream_url, **opts)
        except Exception as e:
            log.error(f"Stream fallback also failed for {track.video_id}: {e}")
            raise RuntimeError(f"Track unavailable: {track.title}") from e

    def cleanup_cache(self) -> None:
        """Delete oldest cached files if total cache exceeds max size."""
        files = list(self.cache_dir.glob("*.opus"))
        if not files:
            return

        total_bytes = sum(f.stat().st_size for f in files)
        max_bytes = self.max_cache_mb * 1024 * 1024

        if total_bytes <= max_bytes:
            return

        # Sort by last access time (oldest first)
        files.sort(key=lambda f: f.stat().st_atime)

        for f in files:
            if total_bytes <= max_bytes:
                break
            size = f.stat().st_size
            f.unlink()
            total_bytes -= size
            log.info(f"Cache cleanup: deleted {f.name} ({size // 1024}KB)")
