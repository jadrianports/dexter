"""AI slash commands and auto-queue logic."""

from __future__ import annotations

import json
import random
import re
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

import config
from database import get_recent_songs, get_recently_skipped, increment_daily_stat
from logic.autoqueue import is_recently_skipped_artist, validate_youtube_match
from logic.playback import should_start_playback
from logic.taste import select_positive_taste_context
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
from personality.roasts import (
    ROAST_COMMAND_LINES,
    ROAST_SELF_LINES,
    ROAST_BOT_LINES,
    ROAST_NO_HISTORY_LINES,
)
from personality.seasonal import get_seasonal_context
from services.gemini import GeminiRateLimitError, GeminiAPIError
from services.lyrics import build_genius_search_query
from utils.logger import log
from utils.tasks import make_task

# Phase 14 / D-03: fixed recall anchor for the positive-taste blend. Any stable
# anchor works since recall() is already scoped to user_id + kind="taste_episode"
# (RESEARCH.md OQ#3) — this just needs to consistently retrieve taste-flavored facts.
_AUTO_QUEUE_TASTE_ANCHOR = "music taste and listening preferences"


def parse_suggestions(response: str) -> list[dict] | None:
    """Parse Gemini's recommendation response into a list of {title, artist} dicts.

    Tolerant of: code fences, leading/trailing prose, and an object that wraps
    the array (e.g. {"songs": [...]}). Returns None if nothing usable is found.
    """
    if not response or not response.strip():
        return None

    text = response.strip()
    # Strip a leading ``` or ```json fence and a trailing ``` fence.
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()

    candidates: list[str] = [text]
    # Fallback: pull JSON arrays/objects out of surrounding prose. Non-greedy +
    # findall so a stray bracketed token before the real array (models often
    # echo context first) doesn't swallow the actual payload.
    candidates.extend(re.findall(r"\[.*?\]|\{.*?\}", text, re.DOTALL))

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue

        # Accept a bare list, or the first list found inside a dict wrapper.
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), None)
        if not isinstance(data, list):
            continue

        valid = [
            item for item in data
            if isinstance(item, dict) and item.get("title") and item.get("artist")
        ]
        if valid:
            return valid

    log.warning(f"Auto-queue JSON parse failed: {response[:200]}")
    return None


class AICog(commands.Cog):
    """Handles /ask and AI-powered auto-queue."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def gemini(self):
        return self.bot.gemini_service

    @property
    def pool(self):
        return self.bot.pool

    # ──────────────────────────── /ask ────────────────────────────

    @app_commands.command(name="ask", description="Ask Dexter anything")
    @app_commands.describe(question="Your question")
    @app_commands.checks.cooldown(1, config.ASK_COOLDOWN_SECONDS)
    async def ask(self, interaction: discord.Interaction, question: str) -> None:
        await interaction.response.defer()

        try:
            # Gather context
            mood = await get_mood(self.bot.pool)
            user_summary = await get_user_summary(self.bot.pool, str(interaction.user.id))
            seasonal = get_seasonal_context()
            conversation = self.bot.message_buffer.get_gemini_history(interaction.channel.id)

            # Add the current question to conversation
            conversation.append({
                "role": "user",
                "content": f"{interaction.user.display_name}: {question}",
            })

            # Phase 11 / MEM-06: occasional recall to surface a stat×episode callback.
            # Cadence gate (D-04) keeps callbacks rare and avoids extra embed calls
            # on every /ask. recall() degrades to [] on any error (Pitfall 8).
            memories: list[str] = []
            if random.random() < config.MEMORY_CALLBACK_CHANCE:
                _memory_svc = getattr(self.bot, "memory_service", None)
                if _memory_svc is not None:
                    try:
                        memories = await _memory_svc.recall(
                            str(interaction.user.id),
                            str(interaction.guild_id),
                            question,   # /ask question text is the recall anchor
                        )
                    except Exception as _mem_err:
                        log.debug("memory.recall failed (non-fatal): %s", _mem_err)

            # Build prompt and call Gemini
            system_prompt = build_chat_prompt(mood, user_summary, seasonal, memories=memories or None)
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
            await increment_daily_stat(self.bot.pool, "total_commands")
            await increment_daily_stat(self.bot.pool, "total_ai_queries")

        except GeminiRateLimitError:
            await interaction.followup.send(pick_random(RATE_LIMIT_MESSAGES))
        except GeminiAPIError as e:
            log.error(f"/ask Gemini error: {e}")
            await interaction.followup.send(pick_random(ERROR_MESSAGES))
            await self._log_error("Gemini API Error", str(e))

    # ──────────────────────────── /roast ────────────────────────────

    @app_commands.command(name="roast", description="Roast a user based on their music history")
    @app_commands.describe(target="The user to roast")
    @app_commands.checks.cooldown(1, config.ROAST_COOLDOWN_SECONDS, key=lambda i: i.user.id)
    async def roast(self, interaction: discord.Interaction, target: discord.Member) -> None:
        await interaction.response.defer()  # public response (D-01)

        # 1. Resolve edge cases first (D-02), before mood/Gemini setup
        user_summary: str | None = None
        if target == self.bot.user or target.bot:
            scenario = "someone tried to roast the bot itself"
            fallback_pool = ROAST_BOT_LINES
        elif target.id == interaction.user.id:
            scenario = "someone tried to roast themselves"
            fallback_pool = ROAST_SELF_LINES
        else:
            user_summary = await get_user_summary(self.bot.pool, str(target.id))
            if user_summary is None:
                scenario = f"{target.display_name} has no music history in this bot"
                fallback_pool = ROAST_NO_HISTORY_LINES
            else:
                scenario = f"roast {target.display_name}: {user_summary}"
                fallback_pool = ROAST_COMMAND_LINES

        # 2. Build fallback line before any async calls that may fail
        fallback_line = pick_random(fallback_pool)
        if "{name}" in fallback_line:
            fallback_line = fallback_line.format(name=target.display_name)

        # 3. Mood + seasonal context injection (D-08) — same as /ask
        mood = await get_mood(self.bot.pool)
        seasonal = get_seasonal_context()

        # Phase 11 / MEM-06: occasional recall for stat×episode callback (D-04).
        # Recall the TARGET (the person being roasted) — their stored episodes
        # are the ammo. Degrades to [] on any error; numbers stay in user_summary.
        roast_memories: list[str] = []
        if random.random() < config.MEMORY_CALLBACK_CHANCE:
            _memory_svc = getattr(self.bot, "memory_service", None)
            if _memory_svc is not None:
                try:
                    roast_memories = await _memory_svc.recall(
                        str(target.id),
                        str(interaction.guild_id),
                        scenario,   # roast scenario string is the recall anchor
                    )
                except Exception as _mem_err:
                    log.debug("memory.recall failed (non-fatal): %s", _mem_err)

        system_prompt = build_chat_prompt(mood, user_summary, seasonal, memories=roast_memories or None)

        # 4. Gemini call at priority=1 (D-05) + guaranteed template fallback
        try:
            conversation = [
                {
                    "role": "user",
                    "content": (
                        f"{scenario}. respond with exactly one roast line in your voice — "
                        "under 200 characters, lowercase, no preamble. harsher than usual."
                    ),
                }
            ]
            result = await self.gemini.chat(system_prompt, conversation, priority=1)
            if result:
                # Personality-voice enforcement (from events.py _generate_ambient_roast)
                result = result.strip()
                if len(result) > 500:
                    result = result[:497] + "..."
                if result and result[0].isupper():
                    result = result[0].lower() + result[1:]
                await interaction.followup.send(
                    result, allowed_mentions=discord.AllowedMentions.none()
                )
            else:
                await interaction.followup.send(
                    fallback_line, allowed_mentions=discord.AllowedMentions.none()
                )
        except (GeminiRateLimitError, GeminiAPIError):
            # Guaranteed template fallback (D-05) — roast never fails
            await interaction.followup.send(
                fallback_line, allowed_mentions=discord.AllowedMentions.none()
            )

        # 5. Update daily stats
        await increment_daily_stat(self.bot.pool, "total_commands")
        await increment_daily_stat(self.bot.pool, "total_ai_queries")

    # ──────────────────────────── AUTO-QUEUE ────────────────────────────

    async def try_auto_queue(self, guild: discord.Guild) -> None:
        """Attempt to auto-queue songs. Called by music cog when queue empties."""
        server_state = get_server_state(self.bot.server_states, guild.id)
        log.info("auto-queue: invoked for guild %d (round %d/%d)",
                 guild.id, server_state.auto_queue_rounds, config.AUTO_QUEUE_MAX_ROUNDS)

        if server_state.auto_queue_rounds >= config.AUTO_QUEUE_MAX_ROUNDS:
            log.info("auto-queue: bail — round cap %d reached; resets on next /play (guild %d)",
                     config.AUTO_QUEUE_MAX_ROUNDS, guild.id)
            channel = self._get_text_channel(guild)
            if channel:
                await channel.send(pick_random(AUTO_QUEUE_CAP_REACHED))
            return

        try:
            recent = await get_recent_songs(self.bot.pool, guild_id=str(guild.id), limit=10)
            if not recent:
                log.info("auto-queue: bail — no recent song history for guild %d", guild.id)
                return

            # Clean messy YouTube titles/uploaders before the recommender sees them,
            # so Gemini reads the real artist/title (e.g. "Joji - Glimpse Of Us" /
            # "LatinHype" -> "Glimpse Of Us" / "Joji") instead of a re-uploader name.
            cleaned = []
            for song in recent:
                c_title, c_artist = build_genius_search_query(
                    song.get("title", ""), song.get("artist")
                )
                cleaned.append({
                    "title": c_title or song.get("title", ""),
                    "artist": c_artist or song.get("artist"),
                })

            # Phase 14 / D-01: guild-scoped "recently skipped" negative hint.
            # Degrades to [] on any failure — never blocks the recommendation call.
            skipped_artists: list[str] = []
            recently_skipped: list[dict] = []
            try:
                since = datetime.now(timezone.utc) - timedelta(
                    days=config.AUTO_QUEUE_SKIP_LOOKBACK_DAYS
                )
                skip_rows = await get_recently_skipped(
                    self.bot.pool,
                    guild_id=str(guild.id),
                    since=since,
                    limit=config.AUTO_QUEUE_SKIP_HINT_CAP,
                )
                recently_skipped = [
                    {"title": r["title"], "artist": r["artist"]} for r in skip_rows
                ]
                skipped_artists = [r["artist"] for r in skip_rows if r["artist"]]
            except Exception as e:
                log.debug("auto-queue: get_recently_skipped failed, degrading to [] (%s)", e)

            # Phase 14 / D-03: unattributed collective "the room tends to like"
            # positive hint, blended from in-voice non-bot members' taste_episode
            # memory. This enumeration is REUSED below for the auto_queue_ignored
            # write (D-03 — do not compute a second, different member set).
            vc = guild.voice_client
            voice_members = (
                [m for m in vc.channel.members if not m.bot]
                if vc and vc.channel else []
            )
            positive_taste: list[str] = []
            _memory_svc = getattr(self.bot, "memory_service", None)
            if _memory_svc is not None and voice_members:
                member_facts: list[list[str]] = []
                for _member in voice_members:
                    try:
                        facts = await _memory_svc.recall(
                            str(_member.id),
                            str(guild.id),
                            _AUTO_QUEUE_TASTE_ANCHOR,
                            kind="taste_episode",
                        )
                    except Exception as e:
                        log.debug(
                            "auto-queue: recall failed for member %s, degrading to [] (%s)",
                            _member.id, e,
                        )
                        facts = []
                    member_facts.append(facts)
                positive_taste = select_positive_taste_context(
                    member_facts, cap=config.AUTO_QUEUE_POSITIVE_TASTE_CAP
                )

            prompt = build_recommendation_prompt(
                cleaned,
                recently_skipped=recently_skipped or None,
                positive_taste=positive_taste or None,
            )
            response = await self.gemini.chat(prompt, [], priority=2)

            if not response:
                log.info("auto-queue: bail — Gemini returned nothing "
                         "(priority-2 rejected when limiter wait >10s, e.g. near 15 RPM) (guild %d)", guild.id)
                return

            suggestions = parse_suggestions(response)
            if not suggestions:
                log.warning("Auto-queue: failed to parse suggestions")
                return

            music_cog = self.bot.cogs.get("MusicCog")
            if not music_cog:
                return

            queue = music_cog.get_queue(guild.id)
            tracks_added = []

            # D-14: iterate ALL suggestions, break when round is full.
            # Do NOT slice suggestions — slicing prevented fall-through when an
            # early suggestion had no passing candidate (Pitfall 3 / 12-RESEARCH.md).
            for suggestion in suggestions:
                if len(tracks_added) >= config.AUTO_QUEUE_SONGS_PER_ROUND:
                    break

                search_query = f"{suggestion['title']} {suggestion['artist']}"
                # D-13: widen search to AUTO_QUEUE_SEARCH_CANDIDATES (was count=1)
                # so we have multiple YouTube results to validate against.
                results = await self.bot.youtube_service.async_search(
                    search_query, count=config.AUTO_QUEUE_SEARCH_CANDIDATES
                )
                if not results:
                    continue

                # D-12: validate each candidate; take the first that passes.
                validated = None
                for result in results:
                    if validate_youtube_match(
                        result.get("title", ""),
                        suggestion["title"],
                        suggestion["artist"],
                    ):
                        validated = result
                        break

                if validated is None:
                    # D-14: no candidate matched — fall through to next suggestion.
                    log.info(
                        "auto-queue: all %d candidate(s) rejected for '%s' — trying next suggestion",
                        len(results), suggestion["title"],
                    )
                    continue

                # D-02: independent second gate, after validate_youtube_match (the
                # hallucination guard, unchanged) — belt-and-suspenders reject of a
                # candidate whose artist matches a recently-skipped artist.
                if is_recently_skipped_artist(suggestion["artist"], skipped_artists):
                    log.info(
                        "auto-queue: dropping '%s' by '%s' — recently-skipped artist",
                        suggestion["title"], suggestion["artist"],
                    )
                    continue

                result = validated
                try:
                    data = await self.bot.youtube_service.async_extract(result["url"])
                except Exception as extract_error:
                    log.warning(f"Auto-queue: skipping unextractable suggestion '{search_query}': {extract_error}")
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
                log.info("auto-queue: bail — %d Gemini suggestion(s) yielded no playable track "
                         "(no YouTube result or all >%ds) (guild %d)",
                         len(suggestions), config.MAX_SONG_DURATION_SECONDS, guild.id)
                return

            # Start playback if no audio is actually flowing. Gate on the live voice
            # client state (voice_client.is_playing() / is_paused()), NOT queue.is_playing:
            # on the natural-exhaustion path _on_track_end leaves is_playing=True and
            # defers to auto-queue ("auto-queue will handle it"), so the old
            # `not queue.is_playing` guard never fired and the freshly-queued tracks sat
            # silent. The voice client is the only ground truth for "audio is flowing"
            # (scar #2 / CLAUDE.md Phase 6-8 gotcha; now locked by should_start_playback).
            voice_client = guild.voice_client
            if should_start_playback(
                connected=voice_client is not None,
                voice_is_playing=voice_client.is_playing() if voice_client else False,
                voice_is_paused=voice_client.is_paused() if voice_client else False,
                has_track=len(queue.tracks) > 0,
            ):
                # Only move the queue pointer onto the first newly-appended track on
                # the branch that actually starts playback. Mutating it unconditionally
                # (when audio is already flowing) desyncs the pointer from the live
                # player and makes _on_track_end skip tracks (WR-01).
                queue.current_index = len(queue.tracks) - len(tracks_added)
                await music_cog._play_track(guild, queue.get_current())

            channel = self._get_text_channel(guild)
            if channel:
                msg = pick_random(AUTO_QUEUE_ANNOUNCE)
                prev = server_state.auto_queue_results
                ignored_signal = prev["skipped"] > 0 and prev["played"] + prev["skipped"] > 0
                if ignored_signal:
                    msg = pick_random(AUTO_QUEUE_IGNORED) + "\n\n" + msg
                await channel.send(msg)

                # D-09 path 1: fire-and-forget memory write for auto_queue_ignored signal.
                # auto-queue is guild-scoped so we write the signal for every non-bot
                # member currently in the voice channel (collective taste signal).
                # create_task keeps the handler non-blocking (T-11-05e / 3s rule).
                if ignored_signal:
                    _memory_svc = getattr(self.bot, "memory_service", None)
                    if _memory_svc is not None:
                        # D-03: reuse the exact voice_members enumeration computed
                        # earlier for the positive-taste recall fan-out — do not
                        # recompute a second, potentially different member set.
                        scenario = (
                            "dexter auto-queued songs were all skipped — "
                            "the recommendations were not to the server's taste"
                        )
                        for _member in voice_members:
                            # Route through make_task so the event loop retains a
                            # strong reference (bare create_task can be GC'd mid-flight,
                            # silently dropping the memory write) and any exception is
                            # surfaced rather than swallowed (WR-04).
                            make_task(
                                _memory_svc.distill_and_remember(
                                    user_id=str(_member.id),
                                    guild_id=str(guild.id),
                                    raw_text=scenario,
                                    kind="auto_queue_ignored",
                                    base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS[
                                        "auto_queue_ignored"
                                    ],
                                ),
                                name="auto-queue-memory",
                                bot=self.bot,
                            )

            log.info("auto-queue: queued %d track(s) for guild %d (round %d)",
                     len(tracks_added), guild.id, server_state.auto_queue_rounds + 1)
            server_state.auto_queue_rounds += 1
            server_state.auto_queue_results = {"played": 0, "skipped": 0}

        except GeminiRateLimitError:
            log.info("Auto-queue: rate limited, skipping")
        except GeminiAPIError as e:
            log.error(f"Auto-queue Gemini error: {e}")
        except Exception as e:
            log.error(f"Auto-queue unexpected error: {e}", exc_info=True)

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
