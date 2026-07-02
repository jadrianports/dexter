"""Event listeners — message buffer feeding, voice roasts, message reactions."""

from __future__ import annotations

import asyncio
import random

import discord
from discord.ext import commands

import config
import database
from logic.proactive import should_fire_proactive_callback
from logic.roasts import RoastScenario, decide_ambient_roast
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
        # Phase 16 / PROACT-01: per-user daily fire counter for the proactive
        # callback surface. str-keyed (matches recall()/database's str(user.id)
        # convention, distinct from the int-keyed _ambient_roast_times above).
        # In-memory only — a restart resetting this is harmless (rarer-is-fine,
        # no durability requirement, D-02).
        self._proactive_daily_counts: dict[str, tuple[str, int]] = {}

    # ──────────────────────────── COOLDOWN HELPERS ────────────────────────────

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
        *,
        pre_recalled_memories: list[str] | None = None,
    ) -> str:
        """Generate an ambient roast line, Gemini-first with template fallback.

        Priority-2 Gemini (personalized to the member's tracked taste) is attempted
        first. Falls back to pick_random(fallback_pool) on GeminiRateLimitError or
        any other exception. Never raises. Never uses priority 1.

        Args:
            pre_recalled_memories: Phase 16 / Pitfall 1 bypass. When not None, the
                internal MEMORY_CALLBACK_CHANCE-gated recall roll and the internal
                memory_service.recall() call are both skipped entirely — the
                supplied list is used as-is as the recall result. Default None
                preserves byte-identical behavior for the two voice-event call
                sites (on_voice_state_update join/leave), which still run the
                internal chance-gated recall unchanged.
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

            # Phase 11 / MEM-06: occasional recall for stat×episode callback (D-04).
            # The substituted scenario string doubles as the recall anchor. Cadence
            # gate keeps recalls rare; degrade to [] on any error (non-fatal).
            #
            # Phase 16 / Pitfall 1: when the proactive surface (plan 16-03) already
            # did its own floor-checked recall, it passes the result in via
            # pre_recalled_memories and this whole gated block is skipped — calling
            # this method unmodified from that surface would otherwise triple-gate
            # (proactive chance gate -> this 0.35 roll -> the floor check again).
            # Default None keeps the two voice-event call sites byte-identical.
            if pre_recalled_memories is not None:
                amb_memories: list[str] = pre_recalled_memories
            else:
                amb_memories = []
                if random.random() < config.MEMORY_CALLBACK_CHANCE:
                    _memory_svc = getattr(self.bot, "memory_service", None)
                    if _memory_svc is not None:
                        try:
                            amb_memories = await _memory_svc.recall(
                                str(member.id),
                                str(member.guild.id),
                                scenario,   # formatted scenario is the recall anchor
                            )
                        except Exception as _mem_err:
                            log.debug("memory.recall failed (non-fatal): %s", _mem_err)

            # Use the locked few-shot DEXTER voice (D-06: examples >> descriptions).
            # mood="normal" is a pure MOOD_CONTEXTS lookup (no DB call); seasonal omitted.
            system_prompt = build_chat_prompt("normal", user_context, "", memories=amb_memories or None)
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

        # Use the member's local guild time via Python's datetime (TZ-explicit via STREAK_TIMEZONE)
        import datetime as _dt
        from zoneinfo import ZoneInfo as _ZoneInfo
        local_hour = _dt.datetime.now(tz=_ZoneInfo(config.STREAK_TIMEZONE)).hour

        # JOIN: before.channel is None, after.channel is not None
        if before.channel is None and after.channel is not None:
            chance_roll = random.random()
            late_night_roll = random.random()
            seconds_since_last_roast = (
                asyncio.get_event_loop().time()
                - self._ambient_roast_times.get(member.id, 0.0)
            )
            scenario_result = decide_ambient_roast(
                event="join",
                chance_roll=chance_roll,
                late_night_roll=late_night_roll,
                local_hour=local_hour,
                seconds_since_last_roast=seconds_since_last_roast,
            )
            if scenario_result != RoastScenario.NONE:
                if scenario_result == RoastScenario.LATE_NIGHT:
                    scenario = "it's late night (1-5am) and {name} just joined voice"
                    fallback_pool = roasts.LATE_NIGHT_ROASTS
                    mem_kind = "late_night"
                else:  # JOIN
                    scenario = "{name} just joined the voice channel"
                    fallback_pool = roasts.VOICE_JOIN_ROASTS
                    mem_kind = "daily_batch"  # WR-01: a daytime join is not a late_night event
                line = await self._generate_ambient_roast(member, scenario, fallback_pool)
                channel = await self._get_ambient_channel(guild)
                if channel:
                    await channel.send(
                        line,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                self._mark_ambient_roast(member.id)
                # D-09 path 1: fire-and-forget memory write for this notable voice event.
                # Uses create_task so the event handler is never blocked (T-11-05e / 3s rule).
                # Guarded by getattr so the bot degrades gracefully when GEMINI_API_KEY unset.
                memory_service = getattr(self.bot, "memory_service", None)
                if memory_service is not None:
                    # Format {name} placeholder before passing as raw_text so the
                    # distiller sees the real display name, not the template literal.
                    raw_text = scenario.format(name=member.display_name) if "{name}" in scenario else scenario
                    asyncio.create_task(
                        memory_service.distill_and_remember(
                            user_id=str(member.id),
                            guild_id=str(guild.id),
                            raw_text=raw_text,
                            kind=mem_kind,
                            base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS[mem_kind],
                        )
                    )
            return

        # LEAVE: before.channel is not None, after.channel is None
        if before.channel is not None and after.channel is None:
            chance_roll = random.random()
            seconds_since_last_roast = (
                asyncio.get_event_loop().time()
                - self._ambient_roast_times.get(member.id, 0.0)
            )
            scenario_result = decide_ambient_roast(
                event="leave",
                chance_roll=chance_roll,
                late_night_roll=0.0,
                local_hour=local_hour,
                seconds_since_last_roast=seconds_since_last_roast,
            )
            if scenario_result != RoastScenario.NONE:
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
                author_id=str(message.author.id),  # CR-02: real snowflake for distill-batch keying
                content=message.content,
            )

        # Handle reactions / deflecting responses
        await self._handle_message_reactions(message)

        # Phase 16 / PROACT-01: proactive callback gate — designated channel only,
        # never a DM (Pitfall 2). message.author.bot already returned above.
        if (
            message.guild is not None
            and config.DEXTER_CHANNEL_ID
            and message.channel.id == config.DEXTER_CHANNEL_ID
        ):
            await self._maybe_fire_proactive_callback(message)

    # ──────────────────────────── PROACTIVE CALLBACK ────────────────────────────

    async def _maybe_fire_proactive_callback(self, message: discord.Message) -> None:
        """Evaluate and, rarely, fire a proactive memory callback (PROACT-01/02).

        D-02 firing order, short-circuit cheapest-first:
          1. Opt-out check (database.get_proactive_opt_out).
          2. Pure gate (should_fire_proactive_callback): chance roll + daily cap.
          3. Recall floor: only fire if memory_service.recall() actually returns
             a memory clearing MEMORY_SIMILARITY_FLOOR (Pitfall 8 — no memory
             beats a wrong memory; silent skip on empty).
          4. Generate via the reused _generate_ambient_roast pipeline
             (pre_recalled_memories bypass — Pitfall 1) and reply, mentions
             suppressed. The daily counter increments ONLY on an actual fire.
        """
        user_id = str(message.author.id)
        opted_out = await database.get_proactive_opt_out(self.bot.pool, user_id)

        # Community-time day key (STREAK_TIMEZONE convention — never naive
        # datetime.now(), see on_voice_state_update above).
        import datetime as _dt
        from zoneinfo import ZoneInfo as _ZoneInfo
        today = _dt.datetime.now(tz=_ZoneInfo(config.STREAK_TIMEZONE)).date().isoformat()

        last_date, count = self._proactive_daily_counts.get(user_id, (today, 0))
        daily_count = count if last_date == today else 0

        if not should_fire_proactive_callback(
            opted_out=opted_out,
            chance_roll=random.random(),
            daily_count=daily_count,
        ):
            return

        memory_service = getattr(self.bot, "memory_service", None)
        if memory_service is None:
            return

        try:
            memories = await memory_service.recall(
                user_id, str(message.guild.id), "a proactive callback moment"
            )
        except Exception as _mem_err:
            log.debug("proactive callback: memory.recall failed (non-fatal): %s", _mem_err)
            memories = []

        if not memories:
            # D-02 step 4 / Pitfall 8: no memory beats a wrong memory. Silent
            # skip — no send, no counter increment.
            return

        line = await self._generate_ambient_roast(
            message.author,
            "{name} is here and dexter has a thought",
            roasts.PROACTIVE_CALLBACK_FALLBACKS,
            pre_recalled_memories=memories,
        )

        try:
            await message.reply(
                line,
                allowed_mentions=discord.AllowedMentions.none(),
                mention_author=False,
            )
        except discord.HTTPException:
            return

        # Counter increments only after a successful send (D-02: fire-only).
        self._proactive_daily_counts[user_id] = (today, daily_count + 1)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventsCog(bot))
