"""Rolling in-memory message buffer per channel. Not persisted to disk."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

import config


class MessageBuffer:
    """Stores the last N messages per channel for AI context."""

    def __init__(self, max_length: int = 10) -> None:
        self._max_length = max_length
        self._buffers: dict[int, deque[dict]] = {}
        self._last_seen: dict[int, datetime] = {}
        self._ttl = timedelta(hours=config.MESSAGE_BUFFER_TTL_HOURS)

    def _evict_stale(self) -> None:
        """Remove channels that have not been seen within the TTL window."""
        cutoff = datetime.now() - self._ttl
        stale = [ch for ch, ts in self._last_seen.items() if ts < cutoff]
        for ch in stale:
            self._buffers.pop(ch, None)
            self._last_seen.pop(ch, None)

    def add(self, channel_id: int, role: str, author: str, content: str) -> None:
        """Add a message to the channel's buffer.

        Evicts idle channels (not seen within MESSAGE_BUFFER_TTL_HOURS) before
        adding, bounding memory growth across many guilds (SCALE-01).
        """
        self._evict_stale()
        self._last_seen[channel_id] = datetime.now()
        if channel_id not in self._buffers:
            self._buffers[channel_id] = deque(maxlen=self._max_length)
        self._buffers[channel_id].append(
            {
                "role": role,
                "author": author,
                "content": content,
                "timestamp": datetime.now(),
            }
        )

    def get_history(self, channel_id: int) -> list[dict]:
        """Return all buffered messages for a channel in chronological order."""
        if channel_id not in self._buffers:
            return []
        return list(self._buffers[channel_id])

    def get_gemini_history(self, channel_id: int) -> list[dict]:
        """Return history formatted for Gemini API contents.

        User messages include the author name prefix so Gemini knows who said what.
        Model messages are returned as-is (Dexter's own responses).
        """
        history = self.get_history(channel_id)
        result = []
        for msg in history:
            if msg["role"] == "user":
                result.append({"role": "user", "content": f"{msg['author']}: {msg['content']}"})
            else:
                result.append({"role": "model", "content": msg["content"]})
        return result

    def clear(self, channel_id: int) -> None:
        """Clear the buffer for a specific channel."""
        self._buffers.pop(channel_id, None)
