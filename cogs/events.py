"""Event listeners — message buffer feeding, future Phase 3 events."""

from __future__ import annotations

import discord
from discord.ext import commands

from utils.logger import log


class EventsCog(commands.Cog):
    """Listens for Discord events to feed the message buffer."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Add non-bot messages to the channel's message buffer."""
        if message.author.bot:
            return
        if not hasattr(self.bot, "message_buffer"):
            return
        self.bot.message_buffer.add(
            channel_id=message.channel.id,
            role="user",
            author=message.author.display_name,
            content=message.content,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventsCog(bot))
