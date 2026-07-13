"""Image generation slash command."""

from __future__ import annotations

import io
import random

import discord
from discord import app_commands
from discord.ext import commands

import config
from database import get_images_today, increment_daily_stat, log_image
from personality.responses import (
    ERROR_MESSAGES,
    IMAGE_CAP_MESSAGES,
    IMAGE_REFUSAL_MESSAGES,
    RATE_LIMIT_MESSAGES,
    pick_random,
)
from services.gemini import GeminiAPIError, GeminiRateLimitError
from utils.logger import log

IMAGE_CAPTIONS: list[str] = [
    "here. i made this. you're welcome.",
    "one ai-generated masterpiece, as requested.",
    "i can't believe i'm doing art for you.",
    "behold. or don't. i don't care.",
    "this is what my processing power is being used for.",
]


class ImagineCog(commands.Cog):
    """Handles the /imagine command."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def gemini(self):
        return self.bot.gemini_service

    @property
    def pool(self):
        return self.bot.pool

    @app_commands.command(name="imagine", description="Generate an image")
    @app_commands.describe(prompt="What to generate")
    @app_commands.checks.cooldown(1, config.IMAGINE_COOLDOWN_SECONDS)
    async def imagine(self, interaction: discord.Interaction, prompt: str) -> None:
        # Check daily cap
        images_today = await get_images_today(self.bot.pool, user_id=str(interaction.user.id))
        if images_today >= config.MAX_IMAGES_PER_USER_PER_DAY:
            return await interaction.response.send_message(pick_random(IMAGE_CAP_MESSAGES), ephemeral=True)

        await interaction.response.defer()

        try:
            image_bytes = await self.gemini.generate_image(
                prompt,
                priority=1,
                guild_id=str(interaction.guild_id) if interaction.guild_id else None,
            )

            if image_bytes is None:
                await interaction.followup.send(pick_random(IMAGE_REFUSAL_MESSAGES))
                return

            file = discord.File(
                io.BytesIO(image_bytes),
                filename="dexter_imagine.jpg",
            )
            caption = random.choice(IMAGE_CAPTIONS)
            await interaction.followup.send(content=caption, file=file)

            await log_image(
                self.bot.pool,
                guild_id=str(interaction.guild.id),
                user_id=str(interaction.user.id),
                prompt=prompt,
            )
            await increment_daily_stat(self.bot.pool, "total_images_generated")
            await increment_daily_stat(self.bot.pool, "total_commands")

        except GeminiRateLimitError:
            await interaction.followup.send(pick_random(RATE_LIMIT_MESSAGES))
        except GeminiAPIError as e:
            log.error(f"/imagine Gemini error: {e}")
            await interaction.followup.send(pick_random(ERROR_MESSAGES))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ImagineCog(bot))
