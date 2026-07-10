"""Help slash command."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

COMMANDS_INFO = [
    ("/play <query or URL>", "Search YouTube or queue a URL directly"),
    ("/skip", "Skip to the next song"),
    ("/pause", "Pause the current song"),
    ("/resume", "Resume playback"),
    ("/stop", "Stop playback, clear queue, and leave voice"),
    ("/queue", "Show the current queue"),
    ("/shuffle", "Shuffle upcoming songs in the queue"),
    ("/loop <off|single|queue>", "Set loop mode"),
    ("/nowplaying", "Show what's currently playing"),
    ("/replay", "Restart the current song from the beginning"),
    ("/ask <question>", "Ask Dexter anything (AI-powered)"),
    ("/imagine <prompt>", "Generate an image"),
    ("/help", "Show this help message"),
]

ADMIN_COMMANDS_INFO = [
    ("/setup channel <channel>", "Pick dexter's ambient channel (admin only)"),
    ("/setup roasts <on|off>", "Toggle ambient roasts for this server (admin only)"),
    ("/setup vision <on|off>", "Toggle vision roasts for this server (admin only)"),
]


class HelpCog(commands.Cog):
    """Provides the /help command."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="help", description="Show all available commands")
    @app_commands.checks.cooldown(1, 5.0)
    async def help_command(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Dexter — Commands",
            description="Here's what I can do.",
            color=0x2C76DD,
        )

        lines = []
        for cmd, desc in COMMANDS_INFO:
            lines.append(f"**`{cmd}`** — {desc}")

        embed.add_field(name="Commands", value="\n".join(lines), inline=False)

        admin_lines = []
        for cmd, desc in ADMIN_COMMANDS_INFO:
            admin_lines.append(f"**`{cmd}`** — {desc}")
        embed.add_field(name="Admin", value="\n".join(admin_lines), inline=False)

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog(bot))
