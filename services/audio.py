"""FFmpeg audio source management and cache cleanup."""

from __future__ import annotations

import os
from pathlib import Path

import discord

import config
from models.queue import Track
from utils.logger import log

# FFmpeg options for stream fallback (non-opus sources)
FFMPEG_STREAM_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


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

    async def get_source(self, track: Track) -> discord.AudioSource:
        """Get a playable audio source for a track."""
        cached = self.cache_path(track.video_id)

        # 1. Cache hit — opus passthrough
        if cached.exists():
            log.info(f"Cache hit for {track.video_id}")
            return discord.FFmpegOpusAudio(str(cached))

        # 2. Try downloading to cache
        path = await self.youtube_service.async_download(track.video_id, track.url)
        if path and path.exists():
            return discord.FFmpegOpusAudio(str(path))

        # 3. Stream fallback — re-extract for fresh URL
        log.warning(f"Download failed for {track.video_id}, falling back to stream")
        try:
            data = await self.youtube_service.async_extract(track.url)
            stream_url = data.get("url") or track.url
            return discord.FFmpegPCMAudio(stream_url, **FFMPEG_STREAM_OPTS)
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
