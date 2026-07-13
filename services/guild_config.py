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
from logic.guild_config import AmbientSurface, decide_ambient_channel

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
        self._blocked: set[str] = set()
        """The in-memory blocked-guild-id set (D-01/D-02/D-03), boot-loaded from
        the dedicated ``guild_blocklist`` table by ``load_all()``. Read by
        ``is_blocked`` as an O(1) set test -- never a Neon round-trip. Mutated
        write-then-invalidate by ``block_guild``/``unblock_guild``."""
        self.home_guild_id: str | None = None
        """The home guild's id (D-24), set only by ``seed_home_guild`` — even on
        an ``ON CONFLICT DO NOTHING`` no-op, since the seed still resolved the
        guild. Stays ``None`` only when ``seed_home_guild`` is never called
        (``DEXTER_CHANNEL_ID`` unset/unresolvable — the fresh-clone case)."""

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
        else:
            self._cache = {str(row["guild_id"]): row for row in rows}

        # Blocklist load is INDEPENDENT of the config-cache load above (D-02/D-03,
        # Phase 20 T-20-12): its own try/except so a blocklist-load failure never
        # blanks the config cache, and vice-versa. An empty `_blocked` on failure
        # means "nothing blocked" -- the safer fail-OPEN default for this one read
        # only (the config cache keeps its own fail-CLOSED rule, D-07).
        try:
            blocklist_rows = await database.load_blocklist(self.pool)
        except Exception as exc:
            self._blocked = set()
            log.error("guild_config: blocklist load failed, _blocked left empty (fail-open): %s", exc)
        else:
            self._blocked = {str(row["guild_id"]) for row in blocklist_rows}

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
    # Blocklist (D-01/D-02/D-03) -- own table, own set, write-then-invalidate.
    # -------------------------------------------------------------------------

    async def block_guild(self, *, guild_id: str, reason: str | None) -> None:
        """Block a guild (`/guilds block`, OWNER-04): write DB THEN mutate the set (D-02).

        Delegates to ``database.insert_blocklist`` (upsert). Does NOT touch
        ``_cache``/``_refresh_cache_entry`` -- the blocklist is its own table
        with its own in-memory set, independent of the config cache (D-03).
        """
        await database.insert_blocklist(self.pool, guild_id=str(guild_id), reason=reason)
        self._blocked.add(str(guild_id))

    async def unblock_guild(self, *, guild_id: str) -> None:
        """Unblock a guild (`/guilds unblock`, OWNER-04): delete THEN discard (D-02)."""
        await database.delete_blocklist(self.pool, guild_id=str(guild_id))
        self._blocked.discard(str(guild_id))

    def is_blocked(self, guild_id) -> bool:
        """O(1) set membership test -- no await, no pool access (CONFIG-03 / D-02)."""
        return str(guild_id) in self._blocked

    # -------------------------------------------------------------------------
    # Silence (D-14) -- writes guild_config.silenced, reads via the config cache.
    # -------------------------------------------------------------------------

    async def silence_guild(self, *, guild_id: str) -> bool:
        """Silence a guild (`/guilds silence`, OWNER-02). Mirrors
        ``set_ambient_roasts_enabled`` verbatim: write then push-invalidate.

        Returns:
            True if a guild_config row existed and was updated, False if no
            row exists for guild_id (WR-02-style contract) -- the caller must
            not report success on a no-op.
        """
        row = await database.set_silenced(self.pool, guild_id=guild_id, silenced=True)
        if row is None:
            return False
        self._refresh_cache_entry(row)
        return True

    async def unsilence_guild(self, *, guild_id: str) -> bool:
        """Unsilence a guild (`/guilds unsilence`, OWNER-02). Same contract as
        ``silence_guild``.
        """
        row = await database.set_silenced(self.pool, guild_id=guild_id, silenced=False)
        if row is None:
            return False
        self._refresh_cache_entry(row)
        return True

    def is_silenced(self, guild_id) -> bool:
        """Cache-only read (D-14) -- never a pool query. False on a cache miss."""
        row = self.get(guild_id)
        return bool(row and row.get("silenced", False))

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
        # D-24: set even on ON CONFLICT DO NOTHING — the seed still resolved
        # the guild, so this is the home guild whether or not a new row
        # was actually inserted.
        self.home_guild_id = str(guild_id)

    # -------------------------------------------------------------------------
    # Resolvers (D-01/D-02/D-03/D-22)
    # -------------------------------------------------------------------------

    def resolve_ambient_channel(self, guild: discord.Guild, *, surface: AmbientSurface) -> discord.TextChannel | None:
        """STRICT, cache-only ambient-channel resolver (D-01), surface-keyed (D-22). SYNCHRONOUS.

        Dispatches on ``logic.guild_config.decide_ambient_channel`` — does not
        re-derive the ``configured``/toggle branch here (Phase 10 D-02
        convention). Returns ``None`` (silent) for an unconfigured or
        toggled-off guild with NO discord lookup attempted at all.

        For a configured, toggled-on guild, returns the resolved
        ``discord.TextChannel`` only when the channel still exists and Dexter
        can still send there. Otherwise returns ``None`` and logs a WARNING
        (D-03) — the cache row is NEVER mutated or cleared here; a transient
        permission blip or a temporarily-missing channel must not permanently
        un-configure a guild.

        Args:
            guild:   The discord.Guild to resolve for.
            surface: Which ambient behavior category is asking. Required
                keyword-only, no default — see
                ``logic.guild_config.AmbientSurface``.
        """
        row = self.get(guild.id)
        channel_id = decide_ambient_channel(config_row=row, surface=surface)
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

        perms = ch.permissions_for(guild.me)
        if not (perms.send_messages and perms.view_channel):
            # WR-03: also require view_channel — a view_channel-denied,
            # send_messages-allowed overwrite still fails an actual
            # channel.send() with Forbidden in practice.
            log.warning(
                "guild_config: lost send_messages/view_channel in configured channel %s (guild %s)",
                channel_id,
                guild.id,
            )
            return None

        return ch

    # -------------------------------------------------------------------------
    # Write + push-invalidate methods (Phase 19 / ONBOARD-01/04) — the single
    # owner of "write then invalidate cache". `/setup` (19-04) calls these;
    # it never writes via `database` directly nor re-derives the cache push.
    # -------------------------------------------------------------------------

    async def configure_guild_first_time(self, *, guild_id: str, channel_id: str) -> None:
        """First `/setup channel` write — designates the channel, flips
        ``configured`` true, and turns vision off (D-19/D-20). Delegates to
        ``database.configure_guild_first_time`` then push-invalidates the
        cache with the returned Record.
        """
        row = await database.configure_guild_first_time(self.pool, guild_id=guild_id, channel_id=channel_id)
        if row is not None:
            self._refresh_cache_entry(row)

    async def redesignate_guild_channel(self, *, guild_id: str, channel_id: str) -> None:
        """Re-designate an already-set-up guild's ambient channel (D-03/D-20) —
        touches ONLY ``ambient_channel_id``, never ``configured`` or either
        toggle. Delegates to ``database.redesignate_guild_channel`` then
        push-invalidates the cache with the returned Record.
        """
        row = await database.redesignate_guild_channel(self.pool, guild_id=guild_id, channel_id=channel_id)
        if row is not None:
            self._refresh_cache_entry(row)

    async def set_ambient_roasts_enabled(self, *, guild_id: str, enabled: bool) -> bool:
        """Toggle ambient roasts for a guild (`/setup roasts on|off`).
        Delegates to ``database.set_ambient_roasts_enabled`` then
        push-invalidates the cache with the returned Record.

        Returns:
            True if a guild_config row existed and was updated, False if no
            row exists for guild_id (WR-02) — the plain ``UPDATE`` is then a
            complete no-op and the caller must not report success.
        """
        row = await database.set_ambient_roasts_enabled(self.pool, guild_id=guild_id, enabled=enabled)
        if row is None:
            return False
        self._refresh_cache_entry(row)
        return True

    async def set_vision_roasts_enabled(self, *, guild_id: str, enabled: bool) -> bool:
        """Toggle vision roasts for a guild (`/setup vision on|off`).
        Delegates to ``database.set_vision_roasts_enabled`` then
        push-invalidates the cache with the returned Record.

        Returns:
            True if a guild_config row existed and was updated, False if no
            row exists for guild_id (WR-02) — the plain ``UPDATE`` is then a
            complete no-op and the caller must not report success.
        """
        row = await database.set_vision_roasts_enabled(self.pool, guild_id=guild_id, enabled=enabled)
        if row is None:
            return False
        self._refresh_cache_entry(row)
        return True

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
