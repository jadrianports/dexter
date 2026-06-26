"""OpsCog — /leaderboard (SOCIAL-02) and /stats (OPS-01/OPS-03) commands.

Decisions implemented:
    D-11  One embed, three sections for /leaderboard
    D-13  Top-5 per section + dry commentary
    D-17  Per-section empty-state personality line
    D-19  /leaderboard output is public
    D-20  /leaderboard lives in cogs/ops.py
    D-21  /stats owner-only via inline is_owner (no decorator)
    D-22  Today-only window for /stats
    D-24  Gemini RPM headroom + image-cap usage in /stats
    D-25  /stats is bot-wide / global
    D-26  /stats lives in cogs/ops.py
    D-27  Rich metrics only in /stats; never on public /health
    D-31  gather_bot_metrics is the shared source of truth for /stats + /health
    D-33  Non-owner /stats: ephemeral refusal before any data is gathered

Security:
    T-08-09  Owner gate — inline await bot.is_owner() before any data access
    T-08-10  Guild-scoped leaderboard — str(interaction.guild_id) passed as $N param
    T-08-08  No internal state in public /health (D-27) — gather_bot_metrics is
             only called from /stats (ephemeral) and the health handler (generic reasons only)
"""

from __future__ import annotations

import asyncio
import time

import discord
from discord import app_commands
from discord.ext import commands

import config
from database import (
    get_leaderboard_songs,
    get_leaderboard_skips,
    get_leaderboard_streaks,
    get_daily_stats_row,
    get_images_today_global,
)
from utils import embeds
from utils.logger import log


# ---------------------------------------------------------------------------
# Shared bot-state metrics helper (D-31)
# Feeds both /stats embed and /health degraded check.
# Lives here so /health can import it at request time (function-scope import
# in bot.py health handler) without a circular import at module load.
# ---------------------------------------------------------------------------


async def gather_bot_metrics(bot) -> dict:
    """Collect current bot-state metrics for /stats embed and /health degraded check.

    Returns a dict with:
        guild_count:       int   — number of guilds the bot is in
        voice_count:       int   — active voice connections
        queue_count:       int   — guilds whose MusicCog queue has tracks
        uptime_seconds:    float — monotonic seconds since _start_monotonic (0 if unset)
        db_ok:             bool  — True if DB pool is reachable
        gateway_ready:     bool  — True if bot.is_ready()
        shard_count:       int   — bot.shard_count or 1
        degraded_reasons:  list[str] — empty list = healthy

    Safe to call before all cogs are loaded — each access is guarded.
    """
    metrics: dict = {
        "guild_count": len(bot.guilds),
        "voice_count": len(bot.voice_clients),
        "queue_count": 0,
        "uptime_seconds": 0.0,
        "db_ok": False,
        "gateway_ready": bot.is_ready(),
        "shard_count": bot.shard_count or 1,
        "degraded_reasons": [],
    }

    # Queue count — how many guilds have non-empty queues (T-08-08: no cross-guild leak)
    music_cog = bot.cogs.get("MusicCog")
    if music_cog is not None:
        for guild in bot.guilds:
            try:
                queue = music_cog.get_queue(guild.id)
                if queue.tracks:
                    metrics["queue_count"] += 1
            except Exception:
                pass  # one guild failure must not abort the rest

    # Uptime (requires bot._start_monotonic set in _initialize_once)
    if hasattr(bot, "_start_monotonic"):
        metrics["uptime_seconds"] = time.monotonic() - bot._start_monotonic

    # DB probe — determines db_ok + appends to degraded_reasons on failure
    pool = getattr(bot, "pool", None)
    if pool is not None:
        # WR-03: bound the whole probe (acquire + SELECT 1) so a cold/scaling Neon
        # instance or an exhausted pool degrades fast (db_ok=False) instead of
        # blocking the health request up to command_timeout — or indefinitely on
        # acquire(). A timeout raises asyncio.TimeoutError, caught below as degraded.
        async def _db_probe() -> None:
            async with pool.acquire() as conn:
                await conn.execute("SELECT 1")

        try:
            await asyncio.wait_for(_db_probe(), timeout=config.HEALTH_DB_PROBE_TIMEOUT)
            metrics["db_ok"] = True
        except Exception:
            metrics["db_ok"] = False
            metrics["degraded_reasons"].append("database unreachable")
    else:
        metrics["degraded_reasons"].append("database pool not initialized")

    # Gateway check
    if not metrics["gateway_ready"]:
        metrics["degraded_reasons"].append("discord gateway not ready")

    # MusicCog load check (REL-01 / D-02)
    # Guard: only report missing as degraded after full init (_ready_done).
    # During startup, MusicCog is absent by design — cogs load after pool/services.
    if getattr(bot, "_ready_done", False):
        if bot.cogs.get("MusicCog") is None:
            metrics["degraded_reasons"].append("MusicCog not loaded")

    return metrics


# ---------------------------------------------------------------------------
# OpsCog
# ---------------------------------------------------------------------------


class OpsCog(commands.Cog):
    """Ops surface: /leaderboard (public) and /stats (owner-only, ephemeral)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def pool(self):
        return self.bot.pool

    # ---- /leaderboard -------------------------------------------------------

    @app_commands.command(
        name="leaderboard",
        description="Show the server leaderboard — top songs, streaks, and skips",
    )
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        """/leaderboard — public per-guild 3-section ranking (D-19/D-20).

        Calls the three Plan-01 aggregate helpers with the guild_id as a
        parameterized $N argument (T-08-10 — no string interpolation).
        The embed builder handles per-section empty-state (D-17).
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "this only works in a server.", ephemeral=True
            )
            return

        # Defer publicly — leaderboard is public (D-19), DB call may exceed 3s
        await interaction.response.defer()

        guild_id = str(guild.id)  # T-08-10: str cast, passed as $N param

        try:
            songs_rows = await get_leaderboard_songs(self.pool, guild_id=guild_id)
            skips_rows = await get_leaderboard_skips(self.pool, guild_id=guild_id)
            streaks_rows = await get_leaderboard_streaks(self.pool, guild_id=guild_id)
        except asyncio.TimeoutError:
            # REL-05 / T-09-02: static message — never interpolate exc, SQL, or DSN
            log.warning("/leaderboard DB timeout")
            await interaction.followup.send(
                "database is being slow. try again in a bit.", ephemeral=True
            )
            return
        except Exception as exc:
            log.error("/leaderboard DB error: %s", exc)
            await interaction.followup.send(
                "couldn't load the leaderboard right now. try again in a bit.",
                ephemeral=True,
            )
            return

        embed = embeds.leaderboard_embed(songs_rows, skips_rows, streaks_rows)
        await interaction.followup.send(embed=embed)

    # ---- /stats -------------------------------------------------------------

    @app_commands.command(
        name="stats",
        description="(Owner only) Show today's bot stats and system status",
    )
    async def stats(self, interaction: discord.Interaction) -> None:
        """/stats — owner-only ephemeral bot-wide status embed (D-21/D-25/D-26).

        Owner check is FIRST — inline await bot.is_owner() before any data is
        gathered (T-08-09). Non-owner gets an ephemeral refusal (D-33).
        Defer is ephemeral so followup content never leaks publicly (D-27/Pitfall 7).
        """
        # Owner gate FIRST — before any async data access (T-08-09, D-21)
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("not authorized.", ephemeral=True)
            return

        # Ephemeral defer — owner output must NOT leak to channel (D-27/D-33/Pitfall 7)
        await interaction.response.defer(ephemeral=True)

        try:
            daily = await get_daily_stats_row(self.pool)
            images = await get_images_today_global(self.pool)
            rpm = self.bot.gemini_service.rpm_usage if hasattr(self.bot, "gemini_service") else 0
            metrics = await gather_bot_metrics(self.bot)
        except asyncio.TimeoutError:
            # REL-05 / T-09-02: static message — never interpolate exc, SQL, or DSN
            log.warning("/stats DB timeout")
            await interaction.followup.send(
                "stats are taking too long. try again in a bit.", ephemeral=True
            )
            return
        except Exception as exc:
            log.error("/stats data gather error: %s", exc)
            await interaction.followup.send(
                "couldn't load stats right now.", ephemeral=True
            )
            return

        # Phase 6: surface rolling perf metrics in /stats (PERF-06 / D-18).
        # getattr guard: bot booted without perf_metrics (e.g. tests) never crashes.
        perf_summary = (
            self.bot.perf_metrics.summary()
            if getattr(self.bot, "perf_metrics", None) is not None
            else None
        )
        embed = embeds.stats_embed(daily, rpm, config.GEMINI_RPM_LIMIT, images, metrics, perf_metrics=perf_summary)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OpsCog(bot))
