"""Event listeners — message buffer feeding, voice roasts, message reactions."""

from __future__ import annotations

import asyncio
import random

import discord
from discord.ext import commands

import config
from models.user_profile import get_user_summary
from personality import roasts
from personality.prompts import build_chat_prompt
from personality.roasts import pick_random
from personality.seasonal import get_seasonal_context
from services.gemini import GeminiRateLimitError
from utils.logger import log


# ---------------------------------------------------------------------------
# Ambient roasts reuse the locked few-shot DEXTER voice (DEXTER_SYSTEM_PROMPT via
# build_chat_prompt) per D-06 — examples beat descriptions. See _generate_ambient_roast.


class EventsCog(commands.Cog):
    """Listens for Discord events: message buffer feeding, voice roasts, reactions."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Per-user ambient roast cooldown dict (join + leave + late-night combined)
        self._ambient_roast_times: dict[int, float] = {}
        self._idle_loneliness_posted: bool = False

    # ──────────────────────────── COOLDOWN HELPERS ────────────────────────────

    def _check_ambient_cooldown(self, user_id: int, ceiling_seconds: int) -> bool:
        """Return True if roast is allowed (ceiling_seconds has elapsed since last roast)."""
        now = asyncio.get_event_loop().time()
        last = self._ambient_roast_times.get(user_id, 0.0)
        return (now - last) >= ceiling_seconds

    def _mark_ambient_roast(self, user_id: int) -> None:
        """Record that a roast just fired for this user."""
        self._ambient_roast_times[user_id] = asyncio.get_event_loop().time()

    # ──────────────────────────── CHANNEL RESOLVER ────────────────────────────

    async def _get_ambient_channel(
        self, guild: discord.Guild
    ) -> discord.TextChannel | None:
        """Resolve the channel for ambient posts via the D-09/D-10 fallback chain.

        Order:
        1. config.DEXTER_CHANNEL_ID (explicit designation)
        2. Last active music channel (queue._text_channel_id)
        3. guild.system_channel
        4. First writable text channel
        """
        # Step 1: explicit designation
        if config.DEXTER_CHANNEL_ID:
            ch = guild.get_channel(config.DEXTER_CHANNEL_ID)
            if ch and isinstance(ch, discord.TextChannel):
                return ch

        # Step 2: last active music channel
        music_cog = self.bot.cogs.get("MusicCog")
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

    # ──────────────────────────── MAXIMIZE-AI GENERATOR ────────────────────────────

    async def _generate_ambient_roast(
        self,
        member: discord.Member,
        scenario: str,
        fallback_pool: list[str],
    ) -> str:
        """Generate an ambient roast line, Gemini-first with template fallback.

        Priority-2 Gemini (personalized to the member's tracked taste) is attempted
        first. Falls back to pick_random(fallback_pool) on GeminiRateLimitError or
        any other exception. Never raises. Never uses priority 1.
        """
        fallback_line = pick_random(fallback_pool)
        # Apply {name} placeholder if present (tolerate lines without it)
        if "{name}" in fallback_line:
            fallback_line = fallback_line.format(name=member.display_name)

        gemini_service = getattr(self.bot, "gemini_service", None)
        if gemini_service is None:
            return fallback_line

        try:
            # Reuse the Phase-2 taste-summary path (same helper /ask uses)
            pool = getattr(self.bot, "pool", None)
            user_summary: str | None = None
            if pool is not None:
                try:
                    user_summary = await get_user_summary(pool, str(member.id))
                except Exception as db_err:
                    log.debug(f"Ambient roast: taste lookup failed for {member.id}: {db_err}")

            user_context = user_summary or f"No data on {member.display_name} yet."

            # Fill in {name} in scenario if present
            if "{name}" in scenario:
                scenario = scenario.format(name=member.display_name)

            # Use the locked few-shot DEXTER voice (D-06: examples >> descriptions).
            # mood="normal" is a pure MOOD_CONTEXTS lookup (no DB call); seasonal omitted.
            system_prompt = build_chat_prompt("normal", user_context, "")
            conversation = [
                {
                    "role": "user",
                    "content": (
                        f"{scenario}. respond with exactly one short roast line in your "
                        "voice — under 120 characters, lowercase, no preamble."
                    ),
                }
            ]

            # Priority 2 only — never contend with user /ask (priority 1)
            result = await gemini_service.chat(system_prompt, conversation, priority=2)

            if result:
                # Enforce voice rules: lowercase, strip to <=500 chars
                result = result.strip()
                if len(result) > 500:
                    result = result[:497] + "..."
                # Gemini sometimes capitalizes — enforce lowercase
                # (only lowercase the first character to avoid emoji/proper noun issues)
                if result and result[0].isupper():
                    result = result[0].lower() + result[1:]
                return result

        except GeminiRateLimitError:
            log.debug(f"Ambient roast: Gemini rate limited for {member.display_name}, using template")
        except Exception as e:
            log.debug(f"Ambient roast: Gemini failed for {member.display_name}: {e}")

        return fallback_line

    # ──────────────────────────── VOICE STATE ────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Handle voice join/leave/move events for ambient personality."""
        # Bot-move complaint FIRST (before any bot guard) — D-12 always fires
        if (
            member == self.bot.user
            and before.channel is not None
            and after.channel is not None
            and before.channel != after.channel
        ):
            channel = await self._get_ambient_channel(member.guild)
            if channel:
                await channel.send(
                    pick_random(roasts.BOT_MOVED_COMPLAINTS),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            return

        # Ignore all other bot voice events (Pitfall 1 — don't self-roast)
        if member.bot:
            return

        guild = member.guild
        hour = discord.utils.utcnow().hour  # Use UTC; late-night check uses local hour below

        # Use the member's local guild time via Python's datetime
        import datetime as _dt
        local_hour = _dt.datetime.now().hour  # local server time for late-night check

        # JOIN: before.channel is None, after.channel is not None
        if before.channel is None and after.channel is not None:
            if random.random() < config.UNPROMPTED_ROAST_CHANCE:
                if self._check_ambient_cooldown(
                    member.id, config.AMBIENT_ROAST_CEILING_SECONDS
                ):
                    if roasts.is_late_night(local_hour):
                        # Late-night chance is a second roll
                        if random.random() < config.LATE_NIGHT_ROAST_CHANCE:
                            scenario = "it's late night (1-5am) and {name} just joined voice"
                            fallback_pool = roasts.LATE_NIGHT_ROASTS
                        else:
                            return  # Late-night roll failed — no roast this time
                    else:
                        scenario = "{name} just joined the voice channel"
                        fallback_pool = roasts.VOICE_JOIN_ROASTS

                    line = await self._generate_ambient_roast(member, scenario, fallback_pool)
                    channel = await self._get_ambient_channel(guild)
                    if channel:
                        await channel.send(
                            line,
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                    self._mark_ambient_roast(member.id)
            return

        # LEAVE: before.channel is not None, after.channel is None
        if before.channel is not None and after.channel is None:
            if random.random() < config.UNPROMPTED_ROAST_CHANCE:
                if self._check_ambient_cooldown(
                    member.id, config.AMBIENT_ROAST_CEILING_SECONDS
                ):
                    line = await self._generate_ambient_roast(
                        member,
                        "{name} just left the voice channel",
                        roasts.VOICE_LEAVE_ROASTS,
                    )
                    channel = await self._get_ambient_channel(guild)
                    if channel:
                        await channel.send(
                            line,
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                    self._mark_ambient_roast(member.id)
            return

        # Channel switch (both non-None, different) — NOT a roast trigger per D-12

    # ──────────────────────────── MESSAGE REACTIONS ────────────────────────────

    async def _handle_message_reactions(self, message: discord.Message) -> None:
        """Add reactions and deflecting-warmth responses based on message content."""
        content = message.content
        content_lower = content.lower().strip()

        # YouTube or Spotify URL → eyes reaction
        if any(
            domain in content
            for domain in (
                "youtube.com",
                "youtu.be",
                "spotify.com",
                "open.spotify",
            )
        ):
            try:
                await message.add_reaction("\N{EYES}")
            except discord.HTTPException:
                pass

        # "goodnight" or "gn" at start or as standalone — salute reaction
        # Word-boundary check: "gn" must not be part of a larger word
        import re
        if re.search(r"(?:^|\s)(?:goodnight|gn)(?:\s|$|[!.,?])", content_lower):
            try:
                await message.add_reaction("\N{SALUTING FACE}")
            except discord.HTTPException:
                pass

        # Bot mentioned with thanks → deflecting-warmth response
        bot_mentioned = self.bot.user in message.mentions
        thanks_keywords = ("thanks", "thank you", "ty", "thx", "thank u")
        if bot_mentioned and any(kw in content_lower for kw in thanks_keywords):
            try:
                await message.channel.send(
                    "...you're welcome. don't get used to it.",
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                pass
            return  # Skip the bare-mention reaction if thanks already handled

        # Bot mentioned but no other substance → neutral-face reaction
        if bot_mentioned:
            # "Bare mention" = the message is essentially just the mention tag
            # Strip all mention tags and whitespace; if nothing meaningful remains, react
            stripped = re.sub(r"<@!?\d+>", "", content).strip()
            if not stripped or stripped in ("?", ".", "...", "!"):
                try:
                    await message.add_reaction("\N{NEUTRAL FACE}")
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Add non-bot messages to the channel's message buffer, then handle reactions."""
        if message.author.bot:
            return

        # Feed message buffer (existing behavior — must not break)
        if hasattr(self.bot, "message_buffer"):
            self.bot.message_buffer.add(
                channel_id=message.channel.id,
                role="user",
                author=message.author.display_name,
                content=message.content,
            )

        # Handle reactions / deflecting responses
        await self._handle_message_reactions(message)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventsCog(bot))
