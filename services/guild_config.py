"""Per-guild configuration cache (Phase 18 / CONFIG-03/05, D-04).

``GuildConfigService`` is the single cache-owning I/O tier for per-guild config:
it loads every ``guild_config`` row once at boot (D-06), serves them from an
in-memory cache with zero per-event Neon round-trips (CONFIG-03), fails closed
on a load error (D-07), and idempotently seeds the home guild (CONFIG-05 /
D-08/D-09).

Constructed unconditionally in ``bot.py`` (no external-key guard, unlike the
Gemini-gated services) and attached as ``bot.guild_config``, mirroring the
``services/memory.py`` / ``services/metrics.py`` wiring pattern.

Both named resolvers (D-02, ``resolve_ambient_channel`` / ``resolve_announce_channel``)
are added in the next task of this plan.
"""

from __future__ import annotations

import logging

import asyncpg
import discord

import database

log = logging.getLogger(__name__)


class GuildConfigService:
    """Cache-owning per-guild config service (D-04).

    Attributes:
        pool: The asyncpg connection pool (same pool every other service uses).
        _bot: Back-reference to the bot, needed only by
            ``resolve_announce_channel``'s music-channel fallback step
            (``self._bot.cogs.get("MusicCog")``), added in the next task.
        _cache: ``{str(guild_id): asyncpg.Record}`` — the in-memory config
            cache. Populated once via ``load_all()`` and push-invalidated
            one entry at a time via ``_refresh_cache_entry`` (the seam Phase
            19's ``/setup`` and Phase 20's kill-switch both call into).
    """

    def __init__(self, pool: asyncpg.Pool, bot) -> None:
        self.pool = pool
        self._bot = bot
        self._cache: dict[str, asyncpg.Record] = {}

    # -------------------------------------------------------------------------
    # Cache load + accessor (CONFIG-03 / D-06/D-07)
    # -------------------------------------------------------------------------

    async def load_all(self) -> None:
        """Load every guild_config row into the cache in ONE round-trip (D-06).

        Fails closed (D-07): on ANY exception from the underlying fetch, the
        cache is left as an empty dict and the exception is NOT re-raised —
        boot must continue with every guild reading as unconfigured (ambient
        silent, core commands unaffected). The error is logged locally and,
        best-effort, surfaced to the Discord error-log channel.
        """
        try:
            rows = await database.load_all_guild_configs(self.pool)
        except Exception as exc:
            self._cache = {}
            log.error("guild_config: load_all failed, cache left empty (fail-closed): %s", exc)
            if hasattr(self._bot, "log_to_discord"):
                embed = discord.Embed(
                    title="GuildConfigService load_all failed",
                    description=f"Error: {exc}\nEvery guild will read as unconfigured until a restart succeeds.",
                    color=0xFF0000,
                )
                await self._bot.log_to_discord(embed)
            return

        self._cache = {str(row["guild_id"]): row for row in rows}

    def get(self, guild_id) -> asyncpg.Record | None:
        """Cache-only accessor — no I/O, ever. Returns None on a cache miss."""
        return self._cache.get(str(guild_id))

    def _refresh_cache_entry(self, record: asyncpg.Record) -> None:
        """Push-invalidate a single cache entry (the seam CONFIG-03 names).

        Only ``seed_home_guild`` calls this in Phase 18; Phase 19's `/setup`
        and Phase 20's kill-switch call it after their own writes.
        """
        self._cache[str(record["guild_id"])] = record

    # -------------------------------------------------------------------------
    # Home-guild seed (CONFIG-05 / D-08/D-09)
    # -------------------------------------------------------------------------

    async def seed_home_guild(self, *, guild_id, ambient_channel_id) -> None:
        """Idempotently seed the home guild's row and refresh its cache entry.

        Delegates to ``database.seed_guild_config_if_absent`` (an
        ``ON CONFLICT (guild_id) DO NOTHING`` insert, D-09 — never overwrites
        a later `/setup` write). Refreshes ONLY the seeded guild's cache
        entry via ``_refresh_cache_entry``.
        """
        row = await database.seed_guild_config_if_absent(
            self.pool,
            guild_id=guild_id,
            ambient_channel_id=ambient_channel_id,
        )
        if row is not None:
            self._refresh_cache_entry(row)
