"""Per-server music queue model."""

from __future__ import annotations

import random
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

    def clear(self) -> None:
        """Reset the queue to empty state."""
        self.tracks.clear()
        self.current_index = 0
        self.is_playing = False
        self.is_paused = False
        self.loop_mode = LoopMode.OFF
        self._now_playing_message_id = None
        self._play_generation = 0

    def upcoming(self) -> list[Track]:
        """Return tracks after the current one."""
        return self.tracks[self.current_index + 1:]

    def __len__(self) -> int:
        return len(self.tracks)
