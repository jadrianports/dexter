"""Per-server music queue model."""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum

import config


class QueueFullError(Exception):
    """Raised when MusicQueue.add() exceeds MAX_QUEUE_SIZE_PER_GUILD."""


class LoopMode(Enum):
    OFF = "off"
    SINGLE = "single"
    QUEUE = "queue"


@dataclass
class Track:
    """A single queued track. Stores the permanent YouTube URL, not a stream URL."""

    video_id: str
    title: str
    artist: str | None
    url: str
    duration_seconds: int
    requested_by: int
    was_auto_queued: bool = False
    thumbnail: str | None = None

    def to_dict(self) -> dict:
        """Serialize this Track to a JSON-safe dict (for Postgres jsonb persistence)."""
        return {
            "video_id": self.video_id,
            "title": self.title,
            "artist": self.artist,
            "url": self.url,
            "duration_seconds": self.duration_seconds,
            "requested_by": self.requested_by,
            "was_auto_queued": self.was_auto_queued,
            "thumbnail": self.thumbnail,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Track":
        """Reconstruct a Track from a dict (e.g. deserialized from Postgres jsonb)."""
        return cls(
            video_id=d["video_id"],
            title=d["title"],
            artist=d.get("artist"),
            url=d["url"],
            duration_seconds=d["duration_seconds"],
            requested_by=d["requested_by"],
            was_auto_queued=d.get("was_auto_queued", False),
            thumbnail=d.get("thumbnail"),
        )


class MusicQueue:
    """Per-server music queue. All index math and loop logic lives here."""

    def __init__(self, guild_id: int) -> None:
        self.guild_id = guild_id
        self.tracks: list[Track] = []
        self.current_index: int = 0
        self.loop_mode: LoopMode = LoopMode.OFF
        self.is_playing: bool = False
        self.is_paused: bool = False
        self._now_playing_message_id: int | None = None
        self._play_generation: int = 0  # incremented each time a new track starts
        self._text_channel_id: int | None = None  # channel where commands are used
        # Auto-lyrics: per-guild, in-memory. Deliberately NOT reset by clear() —
        # it's a server preference, not playback state. Resets only on restart.
        self.auto_lyrics: bool = False
        self.lyrics_thread_id: int | None = None  # reused "🎵 lyrics" thread id
        # Elapsed-tracking state (Phase 7). These ARE playback state → reset by clear().
        self.playback_started_at: float | None = None
        self.paused_at: float | None = None
        # Active audio filter preset (Phase 7). "off" = no filter.
        self.active_filter: str = "off"
        # Phase 6: prefetch state — cleared on queue clear (PERF-01, D-04)
        self._prefetch_video_id: str | None = None   # video_id currently being prefetched
        self._prefetch_task: asyncio.Task | None = None  # in-flight prefetch task

    def add(self, track: Track) -> int:
        """Add a track to the end of the queue. Returns its index.

        Raises QueueFullError if the queue has reached MAX_QUEUE_SIZE_PER_GUILD.
        """
        if len(self.tracks) >= config.MAX_QUEUE_SIZE_PER_GUILD:
            raise QueueFullError(
                f"Queue is at capacity ({config.MAX_QUEUE_SIZE_PER_GUILD} tracks)."
            )
        self.tracks.append(track)
        return len(self.tracks) - 1

    def get_current(self) -> Track | None:
        """Return the current track, or None if queue is empty/index out of range."""
        if 0 <= self.current_index < len(self.tracks):
            return self.tracks[self.current_index]
        return None

    def skip(self) -> Track | None:
        """Advance to next track (manual skip — ignores SINGLE loop).

        Returns the next Track, or None if queue is exhausted.
        """
        return self._advance(respect_single_loop=False)

    def advance(self) -> Track | None:
        """Advance to next track (natural song end — respects SINGLE loop).

        Returns the next Track, or None if queue is exhausted.
        """
        return self._advance(respect_single_loop=True)

    def _advance(self, respect_single_loop: bool) -> Track | None:
        if not self.tracks:
            return None

        if respect_single_loop and self.loop_mode == LoopMode.SINGLE:
            return self.get_current()

        next_index = self.current_index + 1

        if next_index >= len(self.tracks):
            if self.loop_mode == LoopMode.QUEUE:
                next_index = 0
            else:
                return None

        self.current_index = next_index
        return self.get_current()

    def previous(self) -> Track | None:
        """Go to previous track. Returns None if already at start."""
        if self.current_index <= 0:
            return None
        self.current_index -= 1
        return self.get_current()

    def shuffle(self) -> None:
        """Shuffle tracks after current_index. Current and past tracks untouched."""
        start = self.current_index + 1
        if start >= len(self.tracks):
            return
        upcoming = self.tracks[start:]
        random.shuffle(upcoming)
        self.tracks[start:] = upcoming

    # ------------------------------------------------------------------
    # Phase 7: Elapsed tracking (clock-injectable for tests)
    # ------------------------------------------------------------------

    def mark_started(self, offset_seconds: int = 0, now: float | None = None) -> None:
        """Record that playback just started (or restarted with a seek offset).

        offset_seconds — the position we're starting from (e.g. a seek target).
        now — injectable monotonic timestamp; defaults to time.monotonic().
        """
        t = now if now is not None else time.monotonic()
        self.playback_started_at = t - offset_seconds
        self.paused_at = None

    def mark_paused(self, now: float | None = None) -> None:
        """Freeze the elapsed counter at the current position."""
        self.paused_at = now if now is not None else time.monotonic()

    def mark_resumed(self, now: float | None = None) -> None:
        """Advance the virtual start-stamp so the pause gap is excluded."""
        if self.playback_started_at is not None and self.paused_at is not None:
            t = now if now is not None else time.monotonic()
            self.playback_started_at += t - self.paused_at
            self.paused_at = None

    def elapsed_seconds(self, now: float | None = None) -> int:
        """Return how many seconds of the current track have been played.

        Returns 0 if playback has not started yet.  Result is clamped to
        [0, track.duration_seconds] when a current track is available.

        Pure function when `now` is supplied — fully clock-injectable for tests.
        """
        if self.playback_started_at is None:
            return 0
        ref = self.paused_at if self.paused_at is not None else (
            now if now is not None else time.monotonic()
        )
        elapsed = int(ref - self.playback_started_at)
        elapsed = max(0, elapsed)
        track = self.get_current()
        if track is not None:
            elapsed = min(elapsed, track.duration_seconds)
        return elapsed

    # ------------------------------------------------------------------
    # Phase 7: Jump navigation
    # ------------------------------------------------------------------

    def jump_to(self, index: int) -> Track | None:
        """Set current_index to *index* and return that track.

        Returns None (and leaves current_index unchanged) if the index is
        out of bounds.  Reuses the no-pop current_index model.
        """
        if 0 <= index < len(self.tracks):
            self.current_index = index
            return self.get_current()
        return None

    def clear(self) -> None:
        """Reset the queue to empty state."""
        self.tracks.clear()
        self.current_index = 0
        self.is_playing = False
        self.is_paused = False
        self.loop_mode = LoopMode.OFF
        self._now_playing_message_id = None
        # Keep the play-generation counter monotonic — resetting to 0 here would
        # let a stale prefetch/after-callback from before this clear() collide
        # with the next track's generation and fire on it (the exact double-play
        # race the counter exists to prevent — CLAUDE.md). Teardown sites
        # pre-increment, so clear() must only ever advance, never rewind.
        self._play_generation += 1
        # Phase 7 playback state (NOT server preferences like auto_lyrics)
        self.active_filter = "off"
        self.playback_started_at = None
        self.paused_at = None
        # Phase 6: prefetch state reset
        self._prefetch_video_id = None
        self._prefetch_task = None

    def upcoming(self) -> list[Track]:
        """Return tracks after the current one."""
        return self.tracks[self.current_index + 1:]

    def __len__(self) -> int:
        return len(self.tracks)
