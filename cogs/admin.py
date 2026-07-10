"""AdminCog — the guild-admin self-service surface (Phase 19, ONBOARD-02/03/04).

Commands:
    /setup channel        — pick dexter's ambient channel via a native typed
                             discord.TextChannel dropdown (ONBOARD-03/D-02),
                             validating send permission at write time and
                             refusing (writing nothing) if it fails (D-06).
                             Branches on the cached `configured` flag to
                             distinguish a first-configure write (turns
                             vision OFF, D-19/D-20) from a silent re-designate
                             (D-03 — resets no toggle).
    /setup roasts on|off   — toggle `ambient_roasts_enabled` for this guild.
    /setup vision on|off   — toggle `vision_roasts_enabled` for this guild.

This is a DIFFERENT audience and DIFFERENT permission model than
`cogs/ops.py` (owner/analytics, gated by `is_owner()`) — D-04 keeps the two
surfaces in separate modules so a future contributor never copies the wrong
gate onto the wrong audience.

Every subcommand:
    - Is gated by an INLINE `interaction.permissions.manage_guild` check via
      the shared `_require_guild_admin` helper, performed FIRST, before any
      data access (mirrors `cogs/ops.py`'s owner-check-first discipline).
      `default_permissions` on the Group is a UI hint ONLY — never the gate
      (ONBOARD-02, T-19-01).
    - Derives `guild_id` exclusively from `interaction.guild.id` — no
      subcommand accepts a `guild`/`guild_id` parameter (T-19-03, structural
      confused-deputy guard).
    - Echoes the FULL resulting config (channel, roasts, vision) ephemerally
      and in persona after any write (D-05).

Security:
    T-19-01 — inline `manage_guild` gate, first statement of every
              subcommand, before any DB read/write. `default_permissions` is
              UI-only.
    T-19-03 — no `guild`/`guild_id` parameter anywhere in this file; every
              write derives the id from the server-provided
              `interaction.guild.id`.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class AdminCog(commands.Cog):
    """The /setup group: channel (ONBOARD-03), roasts + vision toggles (ONBOARD-04)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ---- /setup group ---------------------------------------------------
    # guild_only + default_permissions live on the GROUP ONLY (verified inert
    # on subcommands) — D-09 defense-in-depth pairs with the inline guard
    # below. default_permissions is a UI hint, never the enforcement
    # mechanism (D-08/ONBOARD-02).

    setup_group = app_commands.Group(
        name="setup",
        description="configure dexter for this server",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    # ---- shared helpers ---------------------------------------------------

    async def _require_guild_admin(self, interaction: discord.Interaction) -> bool:
        """Inline manage_guild gate — the first statement of every subcommand.

        D-09: `interaction.guild is None` is a defense-in-depth belt to the
        Group-level `guild_only=True` suspenders. D-08: a non-admin gets an
        in-persona ephemeral refusal — ephemeral so nobody is publicly dunked
        on for trying, and a permission-probing stranger gets no public
        signal.
        """
        if interaction.guild is None:
            return False
        if not interaction.permissions.manage_guild:
            await interaction.response.send_message(
                "nice try. go find someone with manage server.",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return False
        return True

    async def _config_echo(self, interaction: discord.Interaction) -> str:
        """Render the FULL post-write config for this guild (D-05).

        Reads the cached row via `self.bot.guild_config.get(...)` — the
        service's write methods already push-invalidated the cache before
        this is called, so this is always the fresh row, cache-only, no I/O.
        """
        row = self.bot.guild_config.get(interaction.guild.id)
        if row is None:
            return "current setup: nothing on record yet."

        channel_id = row["ambient_channel_id"]
        channel_part = f"<#{channel_id}>" if channel_id else "not set yet"
        roasts_part = "on" if row["ambient_roasts_enabled"] else "off"
        vision_part = "on" if row["vision_roasts_enabled"] else "off"
        return f"current setup — channel: {channel_part} | roasts: {roasts_part} | vision: {vision_part}"

    # ---- /setup channel -----------------------------------------------

    @setup_group.command(name="channel", description="pick dexter's ambient channel")
    @app_commands.describe(channel="the text channel dexter should post in")
    async def setup_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        """/setup channel — native typed-channel dropdown (ONBOARD-03/D-02).

        D-06: validates `send_messages` BEFORE writing and refuses loudly,
        writing nothing, if it fails — the one deliberate loud-failure
        exception in a subsystem that otherwise resolves toward silence.
        Branches first-configure (`configure_guild_first_time` — turns vision
        off, D-19/D-20) vs re-designate (`redesignate_guild_channel` —
        touches only the channel, D-03) on the cached `configured` flag.
        """
        if not await self._require_guild_admin(interaction):
            return

        if not channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(
                f"can't post in {channel.mention} — i don't have send messages there. "
                "fix my permissions or pick a different channel.",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        cached = self.bot.guild_config.get(interaction.guild.id)
        first_configure = cached is None or not cached["configured"]

        if first_configure:
            await self.bot.guild_config.configure_guild_first_time(
                guild_id=str(interaction.guild.id), channel_id=str(channel.id)
            )
            lead = f"alright, {channel.mention} it is. i'll talk there now."
        else:
            old_channel_id = cached["ambient_channel_id"]
            await self.bot.guild_config.redesignate_guild_channel(
                guild_id=str(interaction.guild.id), channel_id=str(channel.id)
            )
            if old_channel_id and int(old_channel_id) != channel.id:
                lead = f"moving from <#{old_channel_id}> to {channel.mention}. fine."
            else:
                lead = f"alright, {channel.mention} it is now."

        echo = await self._config_echo(interaction)
        await interaction.response.send_message(
            f"{lead}\n{echo}",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    # ---- /setup roasts --------------------------------------------------

    @setup_group.command(name="roasts", description="turn ambient roasts on or off")
    @app_commands.describe(setting="on to enable, off to disable")
    @app_commands.choices(
        setting=[
            app_commands.Choice(name="on", value="on"),
            app_commands.Choice(name="off", value="off"),
        ]
    )
    async def setup_roasts(self, interaction: discord.Interaction, setting: app_commands.Choice[str]) -> None:
        """/setup roasts on|off — toggle `ambient_roasts_enabled` (D-18).

        D-07: valid even with no channel designated yet — the toggle is
        independent state; the reply names the gap instead of refusing.
        """
        if not await self._require_guild_admin(interaction):
            return

        enabled = setting.value == "on"
        saved = await self.bot.guild_config.set_ambient_roasts_enabled(
            guild_id=str(interaction.guild.id), enabled=enabled
        )

        if not saved:
            # WR-02: no guild_config row exists yet (e.g. a boot-backfill DB
            # hiccup) — the write was a complete no-op. Never report success.
            await interaction.response.send_message(
                "couldn't save that — try `/setup channel` first.",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        cached = self.bot.guild_config.get(interaction.guild.id)
        gap_note = ""
        if cached is None or not cached["configured"]:
            gap_note = "\nnoted. i still don't have a channel — run `/setup channel` first."

        echo = await self._config_echo(interaction)
        await interaction.response.send_message(
            f"roasts: {'on' if enabled else 'off'}.{gap_note}\n{echo}",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    # ---- /setup vision --------------------------------------------------

    @setup_group.command(name="vision", description="turn vision roasts on or off")
    @app_commands.describe(setting="on to enable, off to disable")
    @app_commands.choices(
        setting=[
            app_commands.Choice(name="on", value="on"),
            app_commands.Choice(name="off", value="off"),
        ]
    )
    async def setup_vision(self, interaction: discord.Interaction, setting: app_commands.Choice[str]) -> None:
        """/setup vision on|off — toggle `vision_roasts_enabled` (D-19).

        Same admin gate, same D-07 no-channel-yet gap note, same D-05 echo
        as `/setup roasts` — vision is strictly on/off, never an intensity
        dial (REQUIREMENTS.md Out of Scope).
        """
        if not await self._require_guild_admin(interaction):
            return

        enabled = setting.value == "on"
        saved = await self.bot.guild_config.set_vision_roasts_enabled(
            guild_id=str(interaction.guild.id), enabled=enabled
        )

        if not saved:
            # WR-02: no guild_config row exists yet (e.g. a boot-backfill DB
            # hiccup) — the write was a complete no-op. Never report success.
            await interaction.response.send_message(
                "couldn't save that — try `/setup channel` first.",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        cached = self.bot.guild_config.get(interaction.guild.id)
        gap_note = ""
        if cached is None or not cached["configured"]:
            gap_note = "\nnoted. i still don't have a channel — run `/setup channel` first."

        echo = await self._config_echo(interaction)
        await interaction.response.send_message(
            f"vision: {'on' if enabled else 'off'}.{gap_note}\n{echo}",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
