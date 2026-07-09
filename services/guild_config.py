"""Per-guild configuration cache + resolvers (Phase 18 / CONFIG-02/03/05, D-04).

``GuildConfigService`` is the single cache-owning I/O tier for per-guild config:
it loads every ``guild_config`` row once at boot (D-06), serves them from an
in-memory cache with zero per-event Neon round-trips (CONFIG-03), fails closed
on a load error (D-07), and idempotently seeds the home guild (CONFIG-05 /
D-08/D-09).

It also owns BOTH named resolvers (D-02):

- ``resolve_ambient_channel`` — the STRICT, synchronous, cache-only resolver
  (D-01) every unprompted/ambient surface must use. Returns ``None`` (silent +
  a ``log.warning``, row left intact — D-03) on any uncertainty.
- ``resolve_announce_channel`` — the preserved 4-step best-effort fallback
  chain (env designation -> last-active music channel -> system channel ->
  first writable text channel), relocated verbatim from the old
  ``bot.py::_resolve_dexter_channel`` / ``cogs/events.py::_get_ambient_channel``
  duplicates. It has ZERO callers this phase — Phase 19's join-welcome flow is
  the intended first caller.

Constructed unconditionally in ``bot.py`` (no external-key guard, unlike the
Gemini-gated services) and attached as ``bot.guild_config``, mirroring the
``services/memory.py`` / ``services/metrics.py`` wiring pattern.
"""

from __future__ import annotations

import logging

import asyncpg
import discord

import config
import database
from logic.guild_config import decide_ambient_channel

log = logging.getLogger(__name__)


class GuildConfigService:
    """Cache-owning per-guild config service (D-04).

    Attributes:
        pool: The asyncpg connection pool (same pool every other service uses).
        _bot: Back-reference to the bot, needed only by
            ``resolve_announce_channel``'s music-channel fallback step
            (``self._bot.cogs.get("MusicCog")``).
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

    # -------------------------------------------------------------------------
    # Resolvers (D-01/D-02/D-03)
    # -------------------------------------------------------------------------

    def resolve_ambient_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """STRICT, cache-only ambient-channel resolver (D-01). SYNCHRONOUS.

        Dispatches on ``logic.guild_config.decide_ambient_channel`` — does not
        re-derive the ``configured`` branch (Phase 10 D-02 convention). Returns
        ``None`` (silent) for an unconfigured guild with NO discord lookup
        attempted at all.

        For a configured guild, returns the resolved ``discord.TextChannel``
        only when the channel still exists and Dexter can still send there.
        Otherwise returns ``None`` and logs a WARNING (D-03) — the cache row
        is NEVER mutated or cleared here; a transient permission blip or a
        temporarily-missing channel must not permanently un-configure a guild.
        """
        row = self.get(guild.id)
        channel_id = decide_ambient_channel(config_row=row)
        if channel_id is None:
            return None

        ch = guild.get_channel(channel_id)
        if ch is None or not isinstance(ch, discord.TextChannel):
            log.warning(
                "guild_config: configured ambient channel %s in guild %s no longer resolves",
                channel_id,
                guild.id,
            )
            return None

        if not ch.permissions_for(guild.me).send_messages:
            log.warning(
                "guild_config: lost send_messages in configured channel %s (guild %s)",
                channel_id,
                guild.id,
            )
            return None

        return ch

    def resolve_announce_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """Best-effort 4-step fallback chain (D-02). Preserved, NOT used by any
        ambient surface — this is the seam Phase 19's join-welcome flow (and
        owner-facing notices) will call into.

        Order:
          1. config.DEXTER_CHANNEL_ID (explicit env designation)
          2. Last active music channel (MusicCog queue._text_channel_id)
          3. guild.system_channel (if the bot can send there)
          4. First writable text channel

        Relocated verbatim from the old bot.py::_resolve_dexter_channel /
        cogs/events.py::_get_ambient_channel duplicates, adapted only to reach
        the music cog via self._bot instead of a module-level `bot` global.
        """
        # Step 1: explicit designation
        if config.DEXTER_CHANNEL_ID:
            ch = guild.get_channel(config.DEXTER_CHANNEL_ID)
            if ch and isinstance(ch, discord.TextChannel):
                return ch

        # Step 2: last active music channel
        music_cog = self._bot.cogs.get("MusicCog")
        if music_cog is not None:
            queue = music_cog.get_queue(guild.id)
            channel_id = getattr(queue, "_text_channel_id", None)
            if channel_id is not None:
                ch = guild.get_channel(channel_id)
                if ch and isinstance(ch, discord.TextChannel):
                    return ch

        # Step 3: system channel
        if guild.system_channel is not None:
            perms = guild.system_channel.permissions_for(guild.me)
            if perms.send_messages:
                return guild.system_channel

        # Step 4: first writable text channel
        for ch in guild.text_channels:
            perms = ch.permissions_for(guild.me)
            if perms.send_messages:
                return ch

        return None
