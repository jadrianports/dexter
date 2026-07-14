"""Invite slash command (Phase 22 / INVITE-02 / D-05, D-06).

The URL comes from the single pure builder in `logic/invite.py` and is never
constructed here (D-03) — this cog only calls that builder and hands its
output to a link-style button.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from logic.invite import build_invite_url


class InviteCog(commands.Cog):
    """Provides the /invite command."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # Mirrors /help's cooldown — /invite is also a public reply, and without
    # rate-limiting it's a channel-flood/spam vector: compute cost was never
    # the concern, flood control is (WR-03, 22-REVIEW.md).
    #
    # Deliberately no DM-restriction decorator here — DM support is a
    # requirement (D-06). It needs zero new plumbing: this command already
    # flows through bot.py::DexterCommandTree.interaction_check, which
    # computes has_guild, and logic/guild_config.py::decide_interaction_allowed
    # models has_guild=False as a first-class allowed case.
    @app_commands.command(name="invite", description="Get Dexter's invite link")
    @app_commands.checks.cooldown(1, config.INVITE_COOLDOWN_SECONDS)
    async def invite_command(self, interaction: discord.Interaction) -> None:
        # The running bot's real application_id is the authoritative source
        # (it self-heals a fork that forgot to set DISCORD_CLIENT_ID); the
        # committed constant is only the fallback for when there's no
        # running client (e.g. the CI drift-guard) (WR-01, 22-REVIEW.md).
        client_id = self.bot.application_id or config.DISCORD_CLIENT_ID
        if not client_id:
            # Both sources are falsy -- refuse to build a malformed
            # client_id=None URL (WR-02, 22-REVIEW.md). Ephemeral: this is
            # an owner-configuration problem, not something the invoker did.
            await interaction.response.send_message(
                "can't build an invite right now — my client id isn't configured. tell the owner.",
                ephemeral=True,
            )
            return

        url = build_invite_url(
            client_id=client_id,
            permissions_value=config.INVITE_PERMISSIONS_VALUE,
            scopes=config.INVITE_SCOPES,
        )

        embed = discord.Embed(
            description="here. go unleash me on your own server. i'm sure it'll be fine.",
            color=0x2C76DD,
        )

        view = discord.ui.View()
        view.add_item(discord.ui.Button(style=discord.ButtonStyle.link, url=url, label="Add to Discord"))

        # Public reply, not a private one (D-05: spreading the bot is the
        # point), and no defer() (the builder is synchronous and instant).
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InviteCog(bot))
