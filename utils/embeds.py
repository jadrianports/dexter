"""Discord embed builders for music bot responses."""

from __future__ import annotations

import discord

from models.queue import Track, LoopMode, MusicQueue
from utils.formatters import format_duration, progress_bar

# Brand colors
COLOR_NOW_PLAYING = 0x2C76DD   # blue
COLOR_QUEUED = 0xDF1141        # red
COLOR_SUCCESS = 0x0EAA51       # green
COLOR_ERROR = 0x7D3243         # dark pink
COLOR_QUEUE_LIST = 0x40EC88    # light green


def now_playing(track: Track, queue: MusicQueue, elapsed: int = 0) -> discord.Embed:
    """Build the 'Now Playing' embed for the current track."""
    title_str = track.title
    if track.artist:
        title_str = f"{track.title} — {track.artist}"

    embed = discord.Embed(
        title="Now Playing",
        description=f"[{title_str}]({track.url})",
        color=COLOR_NOW_PLAYING,
    )

    if elapsed > 0:
        duration_str = progress_bar(elapsed, track.duration_seconds)
    else:
        duration_str = format_duration(track.duration_seconds)
    embed.add_field(name="Duration", value=duration_str, inline=False)
    embed.add_field(name="Requested by", value=f"<@{track.requested_by}>", inline=True)
    embed.add_field(name="Loop", value=queue.loop_mode.value.capitalize(), inline=True)

    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)

    return embed


def song_queued(track: Track, position: int) -> discord.Embed:
    """Build the 'Song added to queue' embed."""
    title_str = track.title
    if track.artist:
        title_str = f"{track.title} — {track.artist}"

    embed = discord.Embed(
        title=f"Added to Queue (#{position})",
        description=f"[{title_str}]({track.url})",
        color=COLOR_QUEUED,
    )
    embed.add_field(name="Duration", value=format_duration(track.duration_seconds), inline=True)

    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)

    return embed


def queue_list(queue: MusicQueue, page: int = 0, per_page: int = 10) -> discord.Embed:
    """Build a paginated queue list embed."""
    current = queue.get_current()
    total = len(queue.tracks)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages - 1)

    embed = discord.Embed(
        title=f"Queue ({total} tracks)",
        color=COLOR_QUEUE_LIST,
    )

    if current:
        title_str = current.title
        if current.artist:
            title_str = f"{current.title} — {current.artist}"
        embed.add_field(
            name="Now Playing",
            value=f"[{title_str}]({current.url}) [{format_duration(current.duration_seconds)}]",
            inline=False,
        )

    start = page * per_page
    end = min(start + per_page, total)
    lines = []
    for i in range(start, end):
        track = queue.tracks[i]
        marker = "▶ " if i == queue.current_index else ""
        lines.append(
            f"`{i + 1}.` {marker}**{track.title}** [{format_duration(track.duration_seconds)}]"
        )

    if lines:
        embed.add_field(name="Tracks", value="\n".join(lines), inline=False)

    embed.set_footer(text=f"Page {page + 1}/{total_pages}")
    return embed


def error(message: str) -> discord.Embed:
    """Build an error embed."""
    return discord.Embed(
        title="Error",
        description=message,
        color=COLOR_ERROR,
    )
