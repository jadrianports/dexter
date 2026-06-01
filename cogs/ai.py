"""AI slash commands and auto-queue logic."""

from __future__ import annotations

import json
import random
import re

import discord
from discord import app_commands
from discord.ext import commands

import config
from database import get_recent_songs, increment_daily_stat
from models.queue import Track
from models.server_state import get_server_state, get_mood
from models.user_profile import get_user_summary
from personality.prompts import build_chat_prompt, build_recommendation_prompt
from personality.responses import (
    pick_random,
    RATE_LIMIT_MESSAGES,
    ERROR_MESSAGES,
    AI_EMPTY_RESPONSE,
    AUTO_QUEUE_ANNOUNCE,
    AUTO_QUEUE_CAP_REACHED,
    AUTO_QUEUE_IGNORED,
)
from personality.seasonal import get_seasonal_context
from services.gemini import GeminiRateLimitError, GeminiAPIError
from utils.logger import log


class AICog(commands.Cog):
    """Handles /ask and AI-powered auto-queue."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def gemini(self):
        return self.bot.gemini_service

    @property
    def db(self):
        return self.bot.db

    # ──────────────────────────── /ask ────────────────────────────

    @app_commands.command(name="ask", description="Ask Dexter anything")
    @app_commands.describe(question="Your question")
    @app_commands.checks.cooldown(1, config.ASK_COOLDOWN_SECONDS)
    async def ask(self, interaction: discord.Interaction, question: str) -> None:
        await interaction.response.defer()

        try:
            # Gather context
            mood = await get_mood(self.db)
            user_summary = await get_user_summary(self.db, str(interaction.user.id))
            seasonal = get_seasonal_context()
            conversation = self.bot.message_buffer.get_gemini_history(interaction.channel.id)

            # Add the current question to conversation
            conversation.append({
                "role": "user",
                "content": f"{interaction.user.display_name}: {question}",
            })

            # Build prompt and call Gemini
            system_prompt = build_chat_prompt(mood, user_summary, seasonal)
            response = await self.gemini.chat(system_prompt, conversation, priority=1)

            if not response:
                response = pick_random(AI_EMPTY_RESPONSE)

            await interaction.followup.send(response)

            # Add bot response to buffer
            self.bot.message_buffer.add(
                channel_id=interaction.channel.id,
                role="model",
                author="Dexter",
                content=response,
            )

            # Update stats
            await increment_daily_stat(self.db, "total_commands")
            await increment_daily_stat(self.db, "total_ai_queries")

        except GeminiRateLimitError:
            await interaction.followup.send(pick_random(RATE_LIMIT_MESSAGES))
        except GeminiAPIError as e:
            log.error(f"/ask Gemini error: {e}")
            await interaction.followup.send(pick_random(ERROR_MESSAGES))
            await self._log_error("Gemini API Error", str(e))

    # ──────────────────────────── AUTO-QUEUE ────────────────────────────

    async def try_auto_queue(self, guild: discord.Guild) -> None:
        """Attempt to auto-queue songs. Called by music cog when queue empties."""
        server_state = get_server_state(self.bot.server_states, guild.id)

        if server_state.auto_queue_rounds >= config.AUTO_QUEUE_MAX_ROUNDS:
            channel = self._get_text_channel(guild)
            if channel:
                await channel.send(pick_random(AUTO_QUEUE_CAP_REACHED))
            return

        try:
            recent = await get_recent_songs(self.db, guild_id=str(guild.id), limit=10)
            if not recent:
                return

            prompt = build_recommendation_prompt(recent)
            response = await self.gemini.chat(prompt, [], priority=2)

            if not response:
                return

            suggestions = self._parse_suggestions(response)
            if not suggestions:
                log.warning("Auto-queue: failed to parse suggestions")
                return

            music_cog = self.bot.cogs.get("MusicCog")
            if not music_cog:
                return

            queue = music_cog.get_queue(guild.id)
            tracks_added = []

            for suggestion in suggestions[: config.AUTO_QUEUE_SONGS_PER_ROUND]:
                search_query = f"{suggestion['title']} {suggestion['artist']}"
                results = await self.bot.youtube_service.async_search(search_query, count=1)
                if not results:
                    continue

                result = results[0]
                try:
                    data = await self.bot.youtube_service.async_extract(result["url"])
                except Exception as extract_error:
                    log.info(f"Auto-queue: skipping unextractable suggestion '{search_query}': {extract_error}")
                    continue

                if data["duration"] > config.MAX_SONG_DURATION_SECONDS:
                    continue

                track = Track(
                    video_id=data["video_id"],
                    title=data["title"],
                    artist=data.get("artist"),
                    url=data["url"],
                    duration_seconds=data["duration"],
                    requested_by=self.bot.user.id,
                    was_auto_queued=True,
                    thumbnail=data.get("thumbnail"),
                )
                queue.add(track)
                tracks_added.append(track)

            if not tracks_added:
                return

            voice_client = guild.voice_client
            if voice_client and not queue.is_playing:
                queue.current_index = len(queue.tracks) - len(tracks_added)
                await music_cog._play_track(guild, queue.get_current())

            channel = self._get_text_channel(guild)
            if channel:
                msg = pick_random(AUTO_QUEUE_ANNOUNCE)
                prev = server_state.auto_queue_results
                if prev["skipped"] > 0 and prev["played"] + prev["skipped"] > 0:
                    msg = pick_random(AUTO_QUEUE_IGNORED) + "\n\n" + msg
                await channel.send(msg)

            server_state.auto_queue_rounds += 1
            server_state.auto_queue_results = {"played": 0, "skipped": 0}

        except GeminiRateLimitError:
            log.info("Auto-queue: rate limited, skipping")
        except GeminiAPIError as e:
            log.error(f"Auto-queue Gemini error: {e}")
        except Exception as e:
            log.error(f"Auto-queue unexpected error: {e}", exc_info=True)

    def _parse_suggestions(self, response: str) -> list[dict] | None:
        """Parse Gemini's JSON response into song suggestions."""
        cleaned = response.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            data = json.loads(cleaned)
            if isinstance(data, list) and all(
                isinstance(item, dict) and "title" in item and "artist" in item
                for item in data
            ):
                return data
        except (json.JSONDecodeError, TypeError):
            log.warning(f"Auto-queue JSON parse failed: {response[:200]}")
        return None

    def _get_text_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """Get the text channel for posting (reuses music cog's channel tracking)."""
        music_cog = self.bot.cogs.get("MusicCog")
        if music_cog:
            return music_cog._get_text_channel(guild)
        return None

    async def _log_error(self, title: str, details: str) -> None:
        """Log an error to the Discord error channel if configured."""
        if hasattr(self.bot, "log_to_discord"):
            embed = discord.Embed(title=title, description=details, color=0xFF0000)
            await self.bot.log_to_discord(embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AICog(bot))
