"""OpsCog — /leaderboard (SOCIAL-02), /stats (OPS-01/OPS-03), and /guilds
(OWNER-01…06 / RATE-01, Phase 20) commands.

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
    D-04  /guilds is a single app_commands.Group (list/silence/unsilence/leave/block/unblock)
    D-05  /guilds lives in cogs/ops.py (the owner is_owner()-gated surface, distinct
          from cogs/admin.py's manage_guild-gated /setup)
    D-06  default_permissions on the group is a UI hint ONLY; the real gate is the
          inline await self.bot.is_owner(interaction.user) as each subcommand's FIRST statement
    D-07  /guilds leave|block|silence|unsilence|unblock execute immediately with an
          in-persona ephemeral echo — no danger-confirm (both leave and block are reversible)
    D-10  /guilds list: one row per guild, sorted by session AI usage descending
          (the budget hog is line one), paginated (no silent truncation), ephemeral
    D-11  /guilds block = the OWNER-03 force-leave teardown THEN a guild_blocklist insert;
          /guilds leave is the teardown standalone (no blacklist)

Security:
    T-08-09  Owner gate — inline await bot.is_owner() before any data access
    T-08-10  Guild-scoped leaderboard — str(interaction.guild_id) passed as $N param
    T-08-08  No internal state in public /health (D-27) — gather_bot_metrics is
             only called from /stats (ephemeral) and the health handler (generic reasons only)
    T-20-01  Elevation of privilege — every /guilds subcommand opens with the inline
             is_owner() check; default_permissions never the gate
    T-20-05  Tampering (malformed input) — _parse_guild_id wraps int() in try/except,
             never raises into the interaction
    T-20-07  Injection — /guilds list rows render guild names as plain text, ids
             backtick-wrapped (mirrors bot.py::_build_guild_notice_embed); echoes use
             AllowedMentions.none()
    T-20-16  Tampering (ghost state on re-invite) — /guilds leave|block resolve the
             target via bot.get_guild(int(guild_id)), never interaction.guild (Pitfall 3),
             and run the exact /stop teardown template before leaving/blocking
"""

from __future__ import annotations

import asyncio
import time

import discord
from discord import app_commands
from discord.ext import commands

import config
from database import (
    get_daily_stats_row,
    get_images_today_global,
    get_leaderboard_skips,
    get_leaderboard_songs,
    get_leaderboard_streaks,
    get_user_skip_rate,
)
from logic.health import assemble_degraded_reasons
from logic.skip_stats import compute_skip_rate
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

    # DB probe — determines db_ok (async glue stays here; reason assembly is pure)
    pool = getattr(bot, "pool", None)
    pool_present = pool is not None
    if pool_present:
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
    else:
        metrics["db_ok"] = False

    # Assemble degraded_reasons via pure function (D-02 single source of truth).
    # The async DB probe + bot.is_ready() / _ready_done checks remain glue above;
    # the reason-string mapping belongs entirely to logic.health.assemble_degraded_reasons.
    metrics["degraded_reasons"] = assemble_degraded_reasons(
        pool_present=pool_present,
        db_ok=metrics["db_ok"],
        gateway_ready=metrics["gateway_ready"],
        ready_done=getattr(bot, "_ready_done", False),
        musiccog_loaded=bot.cogs.get("MusicCog") is not None,
    )

    return metrics


# ---------------------------------------------------------------------------
# /guilds list pagination (D-10) — char-budget chunking, clone of
# cogs/memory.py::_chunk_facts_into_pages / MemoryPageView.
# ---------------------------------------------------------------------------


def _chunk_guild_rows_into_pages(rows: list[str], char_budget: int) -> list[str]:
    """Group pre-formatted guild-row strings into page strings bounded by char_budget.

    Mirrors cogs/memory.py::_chunk_facts_into_pages — rows arrive already
    fully rendered (unlike facts, no "- " prefix is added here since each row
    already carries its own separators), never truncated (D-10 / Phase 19 D-15).
    """
    if not rows:
        return [""]
    pages: list[str] = []
    current: list[str] = []
    current_len = 0
    for row in rows:
        # +1 for the newline separator that will be added between rows
        if current and current_len + len(row) + 1 > char_budget:
            pages.append("\n".join(current))
            current, current_len = [], 0
        current.append(row)
        current_len += len(row) + 1
    if current:
        pages.append("\n".join(current))
    return pages


class GuildListPageView(discord.ui.View):
    """Paginated /guilds list view with Previous/Next buttons.

    Clone of cogs/memory.py::MemoryPageView (D-10) — pre-chunked pages
    (list[str]), message reference stored so on_timeout can visually disable
    buttons. All edits use allowed_mentions=discord.AllowedMentions.none() as
    defense-in-depth against mention injection from guild names (T-20-07).
    """

    def __init__(self, pages: list[str], title: str, timeout: float = 600.0) -> None:
        super().__init__(timeout=timeout)
        self.pages = pages
        self.title = title
        self.page = 0
        self.message: discord.Message | None = None  # set after send

    def _build_embed(self) -> discord.Embed:
        total = len(self.pages)
        embed = discord.Embed(
            title=self.title,
            description=self.pages[self.page],
            color=0x3498DB,  # blue — distinct from memory's purple / lyrics' blurple
        )
        embed.set_footer(text=f"Page {self.page + 1}/{total}")
        return embed

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = max(0, self.page - 1)
        await interaction.response.edit_message(
            embed=self._build_embed(),
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = min(len(self.pages) - 1, self.page + 1)
        await interaction.response.edit_message(
            embed=self._build_embed(),
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


# ---------------------------------------------------------------------------
# OpsCog
# ---------------------------------------------------------------------------


class OpsCog(commands.Cog):
    """Ops surface: /leaderboard (public), /stats (owner-only, ephemeral), and
    /guilds (owner-only kill-switch group, Phase 20)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def pool(self):
        return self.bot.pool

    def _parse_guild_id(self, s: str) -> int | None:
        """Parse an owner-supplied guild_id string, never raising (V5 / T-20-05).

        A malformed or non-numeric value returns None rather than propagating
        a ValueError into the interaction handler.
        """
        try:
            return int(s.strip())
        except (TypeError, ValueError, AttributeError):
            return None

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
            await interaction.response.send_message("this only works in a server.", ephemeral=True)
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
            await interaction.followup.send("database is being slow. try again in a bit.", ephemeral=True)
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

    # ---- /skips -------------------------------------------------------------

    @app_commands.command(
        name="skips",
        description="Show this server's most-skipped songs and your personal skip rate",
    )
    async def skips(self, interaction: discord.Interaction) -> None:
        """/skips — public embed: server most-skipped songs + personal skip-rate footer (UX-02).

        Surfaces the skip data Dexter already tracks (D-06: own embed, NOT folded into
        /stats). Personal rate is all-time, guild-scoped, and floor-gated so a 1/1
        never shows as 100% (D-07/D-08/D-09). Defers publicly — embed is not private.
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("this only works in a server.", ephemeral=True)
            return

        # Defer publicly — skips embed is public like /leaderboard (D-07)
        await interaction.response.defer()

        guild_id = str(guild.id)  # T-12-02-02: str cast, passed as $N param
        user_id = str(interaction.user.id)

        try:
            skips_rows = await get_leaderboard_skips(self.pool, guild_id=guild_id)
            rate_row = await get_user_skip_rate(self.pool, guild_id=guild_id, user_id=user_id)
        except asyncio.TimeoutError:
            # REL-05 / T-09-02: static message — never interpolate exc, SQL, or DSN
            log.warning("/skips DB timeout")
            await interaction.followup.send("database is being slow. try again in a bit.", ephemeral=True)
            return
        except Exception as exc:
            log.error("/skips DB error: %s", exc)
            await interaction.followup.send(
                "couldn't load skip stats right now. try again in a bit.",
                ephemeral=True,
            )
            return

        # Apply min-plays floor via pure logic (D-08 / T-12-02-04).
        # Treat a missing row (None) the same as 0 plays — no data means below floor.
        total_plays = int(rate_row["total_plays"]) if rate_row else 0
        total_skips = int(rate_row["total_skips"]) if rate_row else 0
        rate = compute_skip_rate(total_plays, total_skips, config.SKIP_STATS_MIN_PLAYS)

        embed = embeds.skips_embed(skips_rows, rate)
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
            await interaction.followup.send("stats are taking too long. try again in a bit.", ephemeral=True)
            return
        except Exception as exc:
            log.error("/stats data gather error: %s", exc)
            await interaction.followup.send("couldn't load stats right now.", ephemeral=True)
            return

        # Phase 6: surface rolling perf metrics in /stats (PERF-06 / D-18).
        # getattr guard: bot booted without perf_metrics (e.g. tests) never crashes.
        perf_summary = self.bot.perf_metrics.summary() if getattr(self.bot, "perf_metrics", None) is not None else None
        embed = embeds.stats_embed(daily, rpm, config.GEMINI_RPM_LIMIT, images, metrics, perf_metrics=perf_summary)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ---- /guilds group (Phase 20, OWNER-01…06 / RATE-01) ---------------------

    guilds = app_commands.Group(
        name="guilds",
        description="owner-only: list, silence, or remove guilds",
        default_permissions=discord.Permissions(administrator=True),  # UI hint ONLY (D-06)
    )

    @guilds.command(
        name="list",
        description="(Owner only) List every guild Dexter is in, sorted by session AI usage",
    )
    async def guilds_list(self, interaction: discord.Interaction) -> None:
        """/guilds list — the fleet view (OWNER-01/RATE-01/D-10).

        Owner gate is FIRST (OWNER-06). One row per guild, sorted by this
        session's Gemini usage descending so the budget hog is line one.
        Guild names render as plain text, ids backtick-wrapped (T-20-07,
        mirrors bot.py::_build_guild_notice_embed). Paginated — never
        silently truncated (D-10 / Phase 19 D-15).
        """
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("not authorized.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        gemini_service = getattr(self.bot, "gemini_service", None)

        def _usage(g: discord.Guild) -> int:
            return gemini_service.guild_usage(g.id) if gemini_service is not None else 0

        guild_config = self.bot.guild_config
        ordered = sorted(self.bot.guilds, key=_usage, reverse=True)

        rows: list[str] = []
        for g in ordered:
            config_row = guild_config.get(g.id)
            flags = ["configured"] if config_row and config_row.get("configured", False) else ["unconfigured"]
            if guild_config.is_silenced(g.id):
                flags.append("silenced")
            if guild_config.is_blocked(g.id):
                flags.append("blocked")
            rows.append(
                f"{g.name} (`{g.id}`) — {g.member_count} members — {_usage(g)} calls this session — {', '.join(flags)}"
            )

        if not rows:
            await interaction.followup.send("i'm not in any guilds right now.", ephemeral=True)
            return

        pages = _chunk_guild_rows_into_pages(rows, config.GUILDS_LIST_PAGE_SIZE)
        view = GuildListPageView(pages, title="guild fleet (sorted by session ai usage)")
        await interaction.followup.send(
            embed=view._build_embed(),
            view=view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OpsCog(bot))
