"""Discord embed builders for music bot responses."""

from __future__ import annotations

import discord

from models.queue import MusicQueue, Track
from personality.responses import (
    LEADERBOARD_EMPTY,
    LEADERBOARD_SKIPS_COMMENTARY,
    LEADERBOARD_SONGS_COMMENTARY,
    LEADERBOARD_STREAK_COMMENTARY,
    SKIPS_NOT_ENOUGH_DATA,
    SKIPS_RATE_ROASTS,
    pick_random,
)
from utils.formatters import format_duration, progress_bar

# Brand colors
COLOR_NOW_PLAYING = 0x2C76DD  # blue
COLOR_QUEUED = 0xDF1141  # red
COLOR_SUCCESS = 0x0EAA51  # green
COLOR_ERROR = 0x7D3243  # dark pink
COLOR_QUEUE_LIST = 0x40EC88  # light green
COLOR_LEADERBOARD = 0xFFD700  # gold — competitive/social
COLOR_STATS = 0x7289DA  # discord blurple — ops/system


def now_playing(track: Track, queue: MusicQueue, elapsed: int | None = None) -> discord.Embed:
    """Build the 'Now Playing' embed for the current track.

    Phase 7: elapsed is now derived from queue.elapsed_seconds() when not
    provided explicitly, so the embed always reflects live position.
    The 'elapsed' parameter is kept for backward compat but ignored in favour
    of the queue's own tracker.
    """
    title_str = track.title
    if track.artist:
        title_str = f"{track.title} — {track.artist}"

    embed = discord.Embed(
        title="Now Playing",
        description=f"[{title_str}]({track.url})",
        color=COLOR_NOW_PLAYING,
    )

    # Phase 7: always query the queue's clock-injectable elapsed tracker (D-13)
    live_elapsed = queue.elapsed_seconds()
    if live_elapsed > 0:
        duration_str = progress_bar(live_elapsed, track.duration_seconds)
    else:
        duration_str = format_duration(track.duration_seconds)
    embed.add_field(name="Duration", value=duration_str, inline=False)
    embed.add_field(name="Requested by", value=f"<@{track.requested_by}>", inline=True)
    embed.add_field(name="Loop", value=queue.loop_mode.value.capitalize(), inline=True)

    # Phase 7: show active filter when one is set (D-13)
    if queue.active_filter != "off":
        embed.add_field(name="🎛 Filter", value=queue.active_filter, inline=True)

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
        lines.append(f"`{i + 1}.` {marker}**{track.title}** [{format_duration(track.duration_seconds)}]")

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


def leaderboard_embed(
    songs_rows: list,
    skips_rows: list,
    streaks_rows: list,
) -> discord.Embed:
    """Build the per-guild leaderboard embed (D-11: one embed, three sections).

    Each section shows top-5 rows (D-13) plus a dry commentary line. If a
    section has no rows, a personality empty-state line is shown (D-17).
    Section order: most songs queued · longest streak · most-skipped songs (D-11).
    Discord limits: 25 fields max / 1024 chars per field / 6000 chars total.
    This embed uses exactly 3 fields — well under all limits.
    """
    embed = discord.Embed(title="leaderboard", color=COLOR_LEADERBOARD)

    # Section 1: Most songs queued
    if songs_rows:
        lines = [f"{i + 1}. {r['username']} — {r['songs_queued']} songs" for i, r in enumerate(songs_rows)]
        commentary = pick_random(LEADERBOARD_SONGS_COMMENTARY)
        embed.add_field(
            name="most songs queued",
            value="\n".join(lines) + f"\n\n{commentary}",
            inline=False,
        )
    else:
        embed.add_field(
            name="most songs queued",
            value=pick_random(LEADERBOARD_EMPTY),
            inline=False,
        )

    # Section 2: Longest streak (guild-active users by global streak, D-15)
    if streaks_rows:
        lines = [f"{i + 1}. {r['username']} — {r['longest_streak']} days" for i, r in enumerate(streaks_rows)]
        commentary = pick_random(LEADERBOARD_STREAK_COMMENTARY)
        embed.add_field(
            name="longest streak",
            value="\n".join(lines) + f"\n\n{commentary}",
            inline=False,
        )
    else:
        embed.add_field(
            name="longest streak",
            value="no streaks to speak of.",
            inline=False,
        )

    # Section 3: Most-skipped songs (titles, per-guild, D-12)
    if skips_rows:
        lines = [f"{i + 1}. {r['title']} — {r['skip_count']} skips" for i, r in enumerate(skips_rows)]
        commentary = pick_random(LEADERBOARD_SKIPS_COMMENTARY)
        embed.add_field(
            name="most-skipped songs",
            value="\n".join(lines) + f"\n\n{commentary}",
            inline=False,
        )
    else:
        embed.add_field(
            name="most-skipped songs",
            value="nobody's skipped enough to make the board. yet.",
            inline=False,
        )

    return embed


def skips_embed(
    skips_rows: list,
    skip_rate: float | None,
) -> discord.Embed:
    """Build the /skips embed: server most-skipped songs + personal roast footer (UX-02).

    Lead section: per-guild most-skipped song titles from get_leaderboard_skips
    (song — N skips). If no rows, a personality empty-state line.
    Footer: personal skip rate roast when skip_rate is not None (floor-gated, D-08);
    a 'not enough data' line otherwise.

    skip_rate is a float in [0.0, 1.0] or None. Values are rendered as a rounded
    integer percentage (e.g. 0.3 → "30%"). One emoji max, Dexter's voice.
    """
    embed = discord.Embed(title="skips", color=COLOR_LEADERBOARD)

    # Server most-skipped songs
    if skips_rows:
        lines = [f"{i + 1}. {r['title']} — {r['skip_count']} skips" for i, r in enumerate(skips_rows)]
        commentary = pick_random(LEADERBOARD_SKIPS_COMMENTARY)
        embed.add_field(
            name="most-skipped songs",
            value="\n".join(lines) + f"\n\n{commentary}",
            inline=False,
        )
    else:
        embed.add_field(
            name="most-skipped songs",
            value="nobody's skipped anything yet. suspicious.",
            inline=False,
        )

    # Personal skip rate footer (D-08: gated by min-plays floor in the caller)
    if skip_rate is None:
        footer_text = pick_random(SKIPS_NOT_ENOUGH_DATA)
    else:
        pct = round(skip_rate * 100)
        template = pick_random(SKIPS_RATE_ROASTS)
        footer_text = template.format(pct=pct)

    embed.set_footer(text=footer_text)

    return embed


def stats_embed(
    daily: dict,
    rpm_usage: int,
    rpm_max: int,
    images_today_global: int,
    metrics: dict,
    perf_metrics: dict | None = None,
) -> discord.Embed:
    """Build the owner-only /stats embed (OPS-01/OPS-03, D-22/D-24/D-25).

    Shows today-only window (D-22) for activity stats, Gemini RPM headroom
    (D-24), image-cap usage, and bot-state. Rich metrics live here ONLY —
    never on the public /health endpoint (D-27).
    Total fields: 14 (well under Discord's 25-field limit).
    """
    embed = discord.Embed(title="dexter system status", color=COLOR_STATS)

    # Today's activity (D-22)
    embed.add_field(name="commands today", value=str(daily.get("total_commands", 0)), inline=True)
    embed.add_field(name="songs played", value=str(daily.get("total_songs_played", 0)), inline=True)
    embed.add_field(name="ai queries", value=str(daily.get("total_ai_queries", 0)), inline=True)
    embed.add_field(name="images generated", value=str(daily.get("total_images_generated", 0)), inline=True)
    embed.add_field(name="errors logged", value=str(daily.get("total_errors", 0)), inline=True)

    # Gemini quota panel (D-24)
    embed.add_field(
        name="gemini rpm",
        value=f"{rpm_usage}/{rpm_max}",
        inline=True,
    )
    embed.add_field(
        name="images today (all users)",
        value=f"{images_today_global} total",
        inline=True,
    )

    # Bot state
    uptime_min = int(metrics.get("uptime_seconds", 0) // 60)
    embed.add_field(name="uptime", value=f"{uptime_min}m", inline=True)
    embed.add_field(name="guilds", value=str(metrics.get("guild_count", 0)), inline=True)
    embed.add_field(name="voice connections", value=str(metrics.get("voice_count", 0)), inline=True)
    embed.add_field(name="shards", value=str(metrics.get("shard_count", 1)), inline=True)

    # DB + gateway health
    db_status = "ok" if metrics.get("db_ok") else "unreachable"
    gw_status = "ready" if metrics.get("gateway_ready") else "not ready"
    embed.add_field(name="database", value=db_status, inline=True)
    embed.add_field(name="gateway", value=gw_status, inline=True)

    # Phase-6 pipeline instrumentation (PERF-06 / D-18)
    # Rendered only when perf_metrics is provided (guard ensures backward-compat).
    # No Oracle/CPU label — baselines against actual run environment (D-19).
    if perf_metrics:
        embed.add_field(
            name="cache hit rate",
            value=f"{perf_metrics['cache_hit_rate']:.0f}%",
            inline=True,
        )
        embed.add_field(
            name="avg time-to-first-audio",
            value=f"{perf_metrics['avg_ttfa_s']:.1f}s",
            inline=True,
        )
        embed.add_field(
            name="avg download",
            value=f"{perf_metrics['avg_download_s']:.1f}s",
            inline=True,
        )

    # Host dashboard link — no in-process psutil (D-30)
    embed.set_footer(text="host metrics: neon console")

    return embed
