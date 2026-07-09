"""Event listeners — message buffer feeding, voice roasts, message reactions."""

from __future__ import annotations

import asyncio
import random

import discord
from discord.ext import commands

import config
import database
from logic.guild_config import is_ambient_channel
from logic.proactive import should_fire_proactive_callback
from logic.roasts import RoastScenario, cooldown_elapsed, decide_ambient_roast
from logic.vision import should_fire_vision_roast
from models.user_profile import get_user_summary
from personality import roasts
from personality.prompts import build_chat_prompt, build_vision_prompt
from personality.roasts import pick_random
from services.gemini import GeminiAPIError, GeminiRateLimitError
from utils.logger import log

# ---------------------------------------------------------------------------
# Ambient roasts reuse the locked few-shot DEXTER voice (DEXTER_SYSTEM_PROMPT via
# build_chat_prompt) per D-06 — examples beat descriptions. See _generate_ambient_roast.


def _normalize_image_mime(attachment: discord.Attachment) -> str:
    """Normalize an attachment's content_type for the allowlist AND the Gemini call.

    Phase 17 / RESEARCH Pitfall 3 — canonicalize with
    ``(attachment.content_type or "").split(";")[0].strip().lower()`` so a None
    content_type collapses to ``""`` (-> allowlist reject) and a parameterized or
    upper-cased type (e.g. ``"image/jpeg; charset=binary"``, ``"IMAGE/PNG"``) is
    reduced to its canonical form. Single source of truth so the structural gate
    and the value forwarded to ``types.Part.from_bytes(mime_type=...)`` can never
    drift (WR-01).
    """
    return (attachment.content_type or "").split(";")[0].strip().lower()


def _first_valid_image_attachment(
    message: discord.Message,
) -> discord.Attachment | None:
    """Return the first attachment passing the vision structural gate, or None.

    Phase 17 / VIS-01 / D-02 — a BEFORE-download metadata gate (T-17-01/T-17-02):
    reject on metadata alone, ZERO bytes fetched for a rejected attachment. The
    trigger is attachments-only (never a message-content URL — SSRF, T-17-02);
    bytes come solely from attachment.read() (Discord CDN).

    Each attachment's content_type is normalized via ``_normalize_image_mime``
    (handles a None content_type -> reject and a "; charset=" suffix, RESEARCH
    Pitfall 3). An attachment is rejected if its normalized type is not in
    ``config.VISION_MIME_ALLOWLIST`` (image/gif deliberately excluded) or if its
    size exceeds ``config.MAX_VISION_IMAGE_BYTES``. The FIRST passing attachment
    is returned (roast the first valid image, D-02).
    """
    for attachment in message.attachments:
        mime = _normalize_image_mime(attachment)
        if mime not in config.VISION_MIME_ALLOWLIST:
            continue
        if attachment.size > config.MAX_VISION_IMAGE_BYTES:
            continue
        return attachment
    return None


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
        # Phase 17 / VIS-01: per-user vision-roast cooldown (monotonic loop time
        # of last fire). int-keyed, mirrors _ambient_roast_times above — a fourth
        # independent unprompted cadence, separate from the ambient/proactive gates.
        self._vision_roast_cooldowns: dict[int, float] = {}

    # ──────────────────────────── COOLDOWN HELPERS ────────────────────────────

    def _mark_ambient_roast(self, user_id: int) -> None:
        """Record that a roast just fired for this user."""
        self._ambient_roast_times[user_id] = asyncio.get_event_loop().time()

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
                                scenario,  # formatted scenario is the recall anchor
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
            channel = self.bot.guild_config.resolve_ambient_channel(member.guild)
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
            seconds_since_last_roast = asyncio.get_event_loop().time() - self._ambient_roast_times.get(member.id, 0.0)
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
                channel = self.bot.guild_config.resolve_ambient_channel(guild)
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
            seconds_since_last_roast = asyncio.get_event_loop().time() - self._ambient_roast_times.get(member.id, 0.0)
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
                channel = self.bot.guild_config.resolve_ambient_channel(guild)
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
        # Phase 18 / CONFIG-02/04: routed through is_ambient_channel over the
        # guild's cached config row instead of the bare-equality env-var check —
        # an unconfigured guild is structurally silent here.
        if message.guild is not None and is_ambient_channel(
            config_row=self.bot.guild_config.get(message.guild.id),
            channel_id=message.channel.id,
        ):
            await self._maybe_fire_proactive_callback(message)

        # Phase 17 / VIS-01: vision-roast gate — a FOURTH independent cadence
        # (do NOT merge with the proactive gate). Designated channel only, and
        # only when the message actually carries attachments (the structural
        # mime/size gate runs inside _maybe_fire_vision_roast).
        if (
            message.guild is not None
            and is_ambient_channel(
                config_row=self.bot.guild_config.get(message.guild.id),
                channel_id=message.channel.id,
            )
            and message.attachments
        ):
            await self._maybe_fire_vision_roast(message)

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
        # WR-02: fail closed on a DB hiccup, matching the recall path's
        # degrade-to-default discipline two steps below. Unlike recall(),
        # there's no meaningful "default" opt-out value to substitute here, so
        # an error just skips this message's callback silently rather than
        # raising an unhandled listener exception into on_message.
        try:
            opted_out = await database.get_proactive_opt_out(self.bot.pool, user_id)
        except Exception as _opt_out_err:
            log.debug(
                "proactive callback: opt-out lookup failed (non-fatal): %s",
                _opt_out_err,
            )
            return

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

        # WR-01: reserve the slot immediately once the gate passes, before any
        # further awaits. A concurrent on_message for the same user then reads
        # the incremented count and is capped by should_fire_proactive_callback
        # above -- this closes the TOCTOU window across the recall/generate/reply
        # awaits below (two interleaved messages could otherwise both observe
        # daily_count == 0 and both fire). Rolled back to the exact
        # pre-reservation state (present-or-absent) on every path below that
        # does not end in an actual fire.
        _had_entry = user_id in self._proactive_daily_counts
        _prior_value = self._proactive_daily_counts.get(user_id)
        self._proactive_daily_counts[user_id] = (today, daily_count + 1)

        def _release_reserved_slot() -> None:
            if _had_entry:
                self._proactive_daily_counts[user_id] = _prior_value
            else:
                self._proactive_daily_counts.pop(user_id, None)

        memory_service = getattr(self.bot, "memory_service", None)
        if memory_service is None:
            _release_reserved_slot()
            return

        # WR-03: anchor recall on the actual triggering message text so it can
        # clear MEMORY_SIMILARITY_FLOOR against concrete stored facts — the prior
        # static "a proactive callback moment" anchor was content-free and would
        # almost never match, silently neutering the feature. Empty/whitespace
        # content falls back to a taste/behavior-flavored phrase (still not a
        # live-SQL number — accuracy firewall unaffected).
        anchor = message.content.strip() or "this user's music taste and history"
        try:
            memories = await memory_service.recall(user_id, str(message.guild.id), anchor)
        except Exception as _mem_err:
            log.debug("proactive callback: memory.recall failed (non-fatal): %s", _mem_err)
            memories = []

        if not memories:
            # D-02 step 4 / Pitfall 8: no memory beats a wrong memory. Silent
            # skip — no send, no counter increment.
            _release_reserved_slot()
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
            _release_reserved_slot()
            return

        # Counter was already reserved (incremented) up front above (WR-01) —
        # the successful send simply confirms the reservation; nothing further
        # to write here.

    # ──────────────────────────── VISION ROAST ────────────────────────────

    async def _generate_vision_roast(self, member: discord.Member, image_bytes: bytes, mime_type: str) -> str | None:
        """Generate a vision-roast line: str on success/transport-fallback, None on skip.

        Phase 17 / VIS-02 / D-04 — a DEDICATED generator (NOT a reuse of
        _generate_ambient_roast, whose always-returns-str contract collapses a
        safety block and a transport failure into the same visible template,
        RESEARCH Pitfall 1). The three outcomes are kept distinct:

          * safety-blocked OR genuinely-empty response -> None (silent skip,
            VIS-02 — MUST NOT emit a fallback line; chat() returns None-on-block
            without raising, the 17-01 hinge).
          * transport failure (GeminiRateLimitError / GeminiAPIError) ->
            pick_random(VISION_ROAST_FALLBACKS) (D-04 template fallback).
          * success -> the stripped, lowercase-first, ≤500-char line.
        """
        gemini_service = getattr(self.bot, "gemini_service", None)
        if gemini_service is None:
            # No AI available -> silent skip (not a transport failure).
            return None

        try:
            result = await gemini_service.chat(
                build_vision_prompt(),
                [{"role": "user", "content": "react to this image in one line."}],
                priority=2,
                image_bytes=image_bytes,
                image_mime_type=mime_type,
            )
        except (GeminiRateLimitError, GeminiAPIError) as e:
            # Transport failure only (rate-limit / API-down) -> template fallback.
            log.debug(f"Vision roast: Gemini transport failure for {member.display_name}: {e}")
            return pick_random(roasts.VISION_ROAST_FALLBACKS)

        if not result:
            # Safety-blocked or empty -> silent skip (VIS-02). Never a fallback here.
            return None

        # Enforce voice rules: strip, lowercase the first char, cap to <=500 chars.
        result = result.strip()
        if not result:
            return None
        if len(result) > 500:
            result = result[:497] + "..."
        if result[0].isupper():
            result = result[0].lower() + result[1:]
        return result

    async def _maybe_fire_vision_roast(self, message: discord.Message) -> None:
        """Evaluate and, rarely, fire a vision roast on a posted image (VIS-01/VIS-02).

        Firing order (short-circuit, cheapest-first; structure copied from
        _maybe_fire_proactive_callback):
          1. Structural gate (_first_valid_image_attachment) — free, zero-I/O:
             reject on metadata alone, ZERO bytes fetched for a rejected/absent
             image (D-02 / VIS-01). Runs FIRST so a non-image attachment (video,
             PDF, zip) never triggers a wasted DB round-trip (WR-03).
          2. Shared Phase 16 opt-out (database.get_proactive_opt_out — no new flag,
             D-03 step 4); fail closed on a DB hiccup. Only reached once a valid
             image is present, since the pure gate needs opted_out as input.
          3. Pure cadence gate (should_fire_vision_roast): opt-out -> cooldown ->
             chance, no I/O and no cooldown mark when it fails.
          4. Read bytes (the single network fetch), generate str|None, and — only
             on a non-None line — reply-anchored with AllowedMentions.none(),
             marking the cooldown ONLY on a successful send.
        """
        # 1. Structural mime/size gate — free, before any I/O (D-02 / VIS-01).
        # Short-circuit here so a non-image attachment never hits the DB (WR-03).
        attachment = _first_valid_image_attachment(message)
        if attachment is None:
            return

        # 2. Shared opt-out (fail closed on error, matching the proactive path).
        try:
            opted_out = await database.get_proactive_opt_out(self.bot.pool, str(message.author.id))
        except Exception as _opt_out_err:
            log.debug("vision roast: opt-out lookup failed (non-fatal): %s", _opt_out_err)
            return

        # 3. Pure cadence gate — opt-out / cooldown / chance. No I/O, no mark on fail.
        seconds_since_last = asyncio.get_event_loop().time() - self._vision_roast_cooldowns.get(message.author.id, 0.0)
        if not should_fire_vision_roast(
            opted_out=opted_out,
            cooldown_elapsed=cooldown_elapsed(seconds_since_last, config.VISION_ROAST_COOLDOWN_SECONDS),
            chance_roll=random.random(),
        ):
            return

        # 4. Only now fetch the bytes (single network read) and generate. Forward
        # the NORMALIZED mime (not raw attachment.content_type) so Gemini's
        # Part.from_bytes(mime_type=...) receives the same canonical value the gate
        # validated — a parameterized/upper-cased type would otherwise 400 and
        # surface a visible transport fallback, defeating Pitfall 3 (WR-01).
        # The source message can be deleted or the CDN can hiccup between the gate
        # and the read, so guard the one bare I/O boundary — fail closed to a
        # silent skip (WR-02 / VIS-02: never a visible error for a cosmetic feature).
        try:
            image_bytes = await attachment.read()
        except discord.HTTPException as read_err:
            log.debug("vision roast: attachment read failed (non-fatal): %s", read_err)
            return
        line = await self._generate_vision_roast(message.author, image_bytes, _normalize_image_mime(attachment))
        if line is None:
            # VIS-02 silent skip (safety-blocked/empty) — no send, no cooldown mark.
            return

        try:
            await message.reply(
                line,
                allowed_mentions=discord.AllowedMentions.none(),
                mention_author=False,
            )
        except discord.HTTPException:
            # Send failed — do not mark the cooldown (allow a future retry).
            return

        # Successful send — mark the per-user cooldown.
        self._vision_roast_cooldowns[message.author.id] = asyncio.get_event_loop().time()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventsCog(bot))
