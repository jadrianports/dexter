"""Per-server runtime state: mood lookup and auto-queue tracking."""

from __future__ import annotations

from dataclasses import dataclass, field

import asyncpg

import config
from database import get_daily_command_count


@dataclass
class ServerState:
    """Runtime state for a single guild. Not persisted to database."""

    guild_id: int
    auto_queue_rounds: int = 0
    auto_queue_results: dict = field(default_factory=lambda: {"played": 0, "skipped": 0})

    def reset_auto_queue(self) -> None:
        """Reset auto-queue tracking (called when a human queues a song)."""
        self.auto_queue_rounds = 0
        self.auto_queue_results = {"played": 0, "skipped": 0}


def get_server_state(
    states: dict[int, ServerState], guild_id: int
) -> ServerState:
    """Get or create the ServerState for a guild. Create-on-access pattern."""
    if guild_id not in states:
        states[guild_id] = ServerState(guild_id=guild_id)
    return states[guild_id]


async def get_mood(pool: asyncpg.Pool) -> str:
    """Determine the bot's current mood based on today's command count."""
    count = await get_daily_command_count(pool)
    if count <= config.MOOD_NORMAL_THRESHOLD:
        return "normal"
    if count <= config.MOOD_TIRED_THRESHOLD:
        return "tired"
    if count <= config.MOOD_EXHAUSTED_THRESHOLD:
        return "exhausted"
    return "fumes"
