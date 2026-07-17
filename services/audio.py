"""FFmpeg audio source management and cache cleanup."""

from __future__ import annotations

import asyncio
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


def _build_ffmpeg_opts(seek_seconds: int = 0, ffmpeg_filter: str | None = None) -> dict:
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


class TruncatingSource(discord.AudioSource):
    """Wraps a source and exhausts it early, at a fixed frame count (Phase 27 / D-14).

    To discord.py this looks like an ordinary natural end: read() returns b""
    once frames_read >= max_frames, which triggers the same
    after_callback -> _on_track_end path a real end of stream would. is_opus()
    delegates to the inner source, so the OUTGOING track keeps the Phase 6/7
    opus fast path for its entire body — only the last few seconds a caller
    reads through this wrapper are ever consumed as PCM for a crossfade tail.

    self._suppress_end_silence is set to True ONLY at the exact instant read()
    cuts short for a fade — never at construction, and never on a natural
    early EOF (the inner source itself returning b"" before max_frames is
    reached, e.g. a file shorter than expected). A genuine end of transmission
    still wants discord.py's silence marker; only a fade cut wants it
    suppressed. This is the D-17.3 discipline: utils/discord_patch.py (plan
    27-04) reads this attribute duck-typed via getattr(), so nothing else in
    the codebase ever sets it and the crossfade-off path stays byte-identical.
    """

    def __init__(self, source: discord.AudioSource, max_frames: int) -> None:
        self._inner = source
        self._max_frames = max_frames
        self._frames_read = 0
        self.cut_short = False
        self._suppress_end_silence = False

    def read(self) -> bytes:
        if self._frames_read >= self._max_frames:
            # The cut for a fade — and ONLY this branch sets either flag.
            self.cut_short = True
            self._suppress_end_silence = True
            return b""
        data = self._inner.read()
        if not data:
            # Natural early EOF: a real end of transmission. Neither flag is set.
            return b""
        self._frames_read += 1
        return data

    def is_opus(self) -> bool:
        return self._inner.is_opus()

    def cleanup(self) -> None:
        self._inner.cleanup()

    @property
    def frames_read(self) -> int:
        return self._frames_read

    @property
    def position_seconds(self) -> float:
        """The cut position in seconds — the ONLY safe source for a fade's -ss
        offset (RESEARCH landmine #5: Track.duration_seconds is YouTube
        metadata and disagrees with the real file)."""
        return self._frames_read * 0.02


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

        # 2. Try downloading to cache (bounded by DOWNLOAD_TIMEOUT_SECONDS — PERF-04 / D-10/D-11)
        try:
            path = await asyncio.wait_for(
                self.youtube_service.async_download(track.video_id, track.url),
                timeout=config.DOWNLOAD_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            log.warning(
                "download timeout after %ss video_id=%s, falling back to stream",
                config.DOWNLOAD_TIMEOUT_SECONDS,
                track.video_id,
            )
            path = None
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

    async def cleanup_cache(self, pool, protected_video_ids: set[str]) -> None:
        """Delete least-frequently-played cached files when total cache exceeds max size.

        Eviction order: lowest play_count first (sourced from song_history),
        tie-break by oldest mtime. Files whose video_id is in protected_video_ids
        (currently playing, queued, or prefetched) are NEVER evicted (PERF-05 / D-12/D-13).
        """
        files = list(self.cache_dir.glob("*.opus"))
        if not files:
            return

        total_bytes = sum(f.stat().st_size for f in files)
        max_bytes = self.max_cache_mb * 1024 * 1024

        if total_bytes <= max_bytes:
            return

        # Fetch play counts for all URLs in song_history
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT url, COUNT(*) AS plays FROM song_history GROUP BY url")

        # Build play_count dict keyed by video_id extracted from YouTube URLs
        play_counts: dict[str, int] = {}
        for row in rows:
            url = row["url"]
            if "v=" in url:
                vid = url.split("v=")[-1].split("&")[0]
                play_counts[vid] = row["plays"]

        # Sort: lowest play_count first; tie-break by oldest mtime.
        # Protected files sort to float("inf") so they are never reached.
        def eviction_key(f: Path):
            vid = f.stem
            if vid in protected_video_ids:
                return (float("inf"), 0)
            return (play_counts.get(vid, 0), f.stat().st_mtime)

        files.sort(key=eviction_key)

        for f in files:
            if total_bytes <= max_bytes:
                break
            vid = f.stem
            if vid in protected_video_ids:
                continue
            size = f.stat().st_size
            try:
                f.unlink()
            except OSError as e:
                # One un-deletable file (locked/in-use on Windows, permissions)
                # must not abort the whole pass and leave the cache over the cap.
                log.warning("cache evict failed video_id=%s: %s", vid, e)
                continue
            total_bytes -= size
            log.info(
                "cache evict video_id=%s play_count=%d size=%dKB",
                vid,
                play_counts.get(vid, 0),
                size // 1024,
            )
