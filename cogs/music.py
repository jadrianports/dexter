"""Music slash commands and playback engine."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

import config
from database import (
    get_history_rows,
    get_repeat_song_count,
    update_user_streak,
    log_track_batch,
    increment_daily_stat,
    mark_song_skipped,
    normalize_search_query,
    get_resolution_cache,
    set_resolution_cache,
)
from models.queue import Track, LoopMode, MusicQueue, QueueFullError
from models.user_profile import get_user_summary
from personality.prompts import build_chat_prompt
from personality.roasts import (
    pick_random,
    NO_LYRICS_FOUND,
    REPEAT_SONG_ROAST_TEMPLATES,
    MILESTONE_SONG_TEMPLATES,
    MILESTONE_STREAK_TEMPLATES,
)
from personality.responses import (
    pick_random as pick_random_r,
    FILTER_APPLIED,
    FILTER_CLEARED,
    NOT_IN_VOICE,
    NOTHING_PLAYING,
)
from services.gemini import GeminiRateLimitError
from services.lyrics import chunk_lyrics
from utils import embeds
from utils.formatters import parse_time, format_duration
from utils.logger import log

if TYPE_CHECKING:
    from services.youtube import YouTubeService
    from services.audio import AudioService


class SongSelect(discord.ui.Select):
    """Dropdown menu for selecting a song from search results."""

    def __init__(self, results: list[dict], cog: "MusicCog") -> None:
        self.results = results
        self.cog = cog
        options = []
        for i, r in enumerate(results):
            duration = r.get("duration")
            desc = f"Duration: {duration // 60}:{duration % 60:02d}" if duration else "Unknown duration"
            options.append(
                discord.SelectOption(
                    label=r["title"][:100],
                    description=desc[:100],
                    value=str(i),
                )
            )
        super().__init__(placeholder="Pick a song...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        try:
            index = int(self.values[0])
            selected = self.results[index]
            # Phase 6: pass orig_query from the view so _queue_from_selection
            # can write the resolution cache after extraction (PERF-03).
            orig_query = getattr(self.view, "orig_query", None)
            await self.cog._queue_from_selection(interaction, selected, orig_query=orig_query)
        except Exception as e:
            log.error(f"Song select callback error: {e}", exc_info=True)
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embeds.error(f"Something went wrong: {e}"))
                else:
                    await interaction.response.send_message(embed=embeds.error(f"Something went wrong: {e}"))
            except discord.DiscordException as notify_error:
                log.error(f"Failed to deliver select-callback error notice: {notify_error}")
        finally:
            self.view.stop()


class SongSelectView(discord.ui.View):
    """View containing the song select dropdown."""

    def __init__(
        self,
        results: list[dict],
        cog: "MusicCog",
        timeout: float = 180.0,
        orig_query: str | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        # Phase 6: carry the original search query so _queue_from_selection can
        # write the resolution cache after the user picks (PERF-03).
        self.orig_query: str | None = orig_query
        self.add_item(SongSelect(results, cog))

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True


class QueuePageView(discord.ui.View):
    """Paginated queue view with Previous/Next buttons."""

    def __init__(self, queue: MusicQueue, timeout: float = 120.0) -> None:
        super().__init__(timeout=timeout)
        self.queue = queue
        self.page = 0

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.page = max(0, self.page - 1)
        embed = embeds.queue_list(self.queue, page=self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        total_pages = max(1, (len(self.queue.tracks) + 9) // 10)
        self.page = min(total_pages - 1, self.page + 1)
        embed = embeds.queue_list(self.queue, page=self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True


class LyricsPageView(discord.ui.View):
    """Paginated lyrics view with Previous/Next buttons.

    Takes pre-chunked pages (list[str]) rather than a MusicQueue — avoids
    the QueuePageView coupling issue (RESEARCH.md Pitfall 8). Stores a
    reference to the interaction message so on_timeout can visually disable
    buttons (RESEARCH.md Open Question 3).

    All sends/edits use allowed_mentions=discord.AllowedMentions.none() as
    defense-in-depth against mention injection from scraped lyrics (T-03-14).
    """

    def __init__(self, pages: list[str], title: str, timeout: float = 600.0) -> None:
        super().__init__(timeout=timeout)
        self.pages = pages
        self.title = title
        self.page = 0
        self.message: discord.Message | None = None  # set after send

    def _build_embed(self) -> discord.Embed:
        total = len(self.pages)
        embed = discord.Embed(
            title=f"Lyrics — {self.title}",
            description=self.pages[self.page],
            color=0x5865F2,  # discord blurple for lyrics
        )
        embed.set_footer(text=f"Page {self.page + 1}/{total}")
        return embed

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.page = max(0, self.page - 1)
        await interaction.response.edit_message(
            embed=self._build_embed(),
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.page = min(len(self.pages) - 1, self.page + 1)
        await interaction.response.edit_message(
            embed=self._build_embed(),
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class HistoryPageView(discord.ui.View):
    """Paginated history view with Previous/Next buttons.

    Takes a list of song-history dicts and a guild reference for username
    resolution (D-16: show title / artist / who-requested / when). All
    sends/edits use allowed_mentions=discord.AllowedMentions.none() (T-03-14).
    """

    def __init__(
        self,
        rows: list[dict],
        guild: discord.Guild,
        timeout: float = 120.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.rows = rows
        self.guild = guild
        self.page = 0
        self.per_page = config.HISTORY_PAGE_SIZE
        self.message: discord.Message | None = None  # set after send

    def _build_embed(self) -> discord.Embed:
        total_pages = max(1, (len(self.rows) + self.per_page - 1) // self.per_page)
        start = self.page * self.per_page
        end = min(start + self.per_page, len(self.rows))
        page_rows = self.rows[start:end]

        lines: list[str] = []
        for row in page_rows:
            title = row.get("title") or "Unknown"
            artist = row.get("artist") or "Unknown Artist"
            user_id = row.get("user_id") or "?"
            queued_at = row.get("queued_at")

            # Resolve user_id to display name (fall back to the raw id)
            member = self.guild.get_member(int(user_id)) if user_id.isdigit() else None
            who = member.display_name if member else f"<@{user_id}>"

            # Compact date: show only the date portion. queued_at is a TIMESTAMPTZ
            # (datetime) from asyncpg now — format it; tolerate legacy str / None.
            if hasattr(queued_at, "strftime"):
                when = queued_at.strftime("%Y-%m-%d")
            elif queued_at:
                when = str(queued_at)[:10]
            else:
                when = "?"

            lines.append(f"**{title}** — {artist}\n  ↳ {who} · {when}")

        embed = discord.Embed(
            title=f"Server History ({len(self.rows)} songs)",
            description="\n\n".join(lines) if lines else "No entries on this page.",
            color=0x40EC88,
        )
        embed.set_footer(text=f"Page {self.page + 1}/{total_pages}")
        return embed

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.page = max(0, self.page - 1)
        await interaction.response.edit_message(
            embed=self._build_embed(),
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        total_pages = max(1, (len(self.rows) + self.per_page - 1) // self.per_page)
        self.page = min(total_pages - 1, self.page + 1)
        await interaction.response.edit_message(
            embed=self._build_embed(),
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class NowPlayingView(discord.ui.View):
    """Persistent 5-button controller on the now-playing embed (D-01..D-06, PLAYER-01).

    timeout=None  — buttons never expire so they survive a bot restart.
    custom_ids are stable across restarts so Discord routes presses to
    the registered instance (added via bot.add_view in setup_hook).

    All callbacks:
      1. Resolve guild + queue + voice_client from the interaction.
      2. Guard the presser is in the bot's voice channel (D-02).
      3. Call the matching _do_* helper from MusicCog.
      4. Re-render the now-playing embed in-place via edit_message (D-04, silent).
    """

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    def apply_state(self, queue: "MusicQueue") -> "NowPlayingView":
        """Sync button labels to current queue state (pause/resume, loop mode).

        A freshly-constructed view carries default labels; call this before
        rendering so the controls reflect reality after a track change
        (otherwise loop/pause state snaps back to defaults on the new song).
        """
        mode_labels = {
            LoopMode.OFF: "🔁 Loop: Off",
            LoopMode.SINGLE: "🔂 Loop: Single",
            LoopMode.QUEUE: "🔁 Loop: Queue",
        }
        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                continue
            if child.custom_id == "dex:np:playpause":
                child.label = "▶ Resume" if queue.is_paused else "⏸ Pause"
            elif child.custom_id == "dex:np:loop":
                child.label = mode_labels.get(queue.loop_mode, "🔁 Loop: Off")
        return self

    def _resolve_cog_queue_vc(
        self, interaction: discord.Interaction
    ) -> tuple["MusicCog | None", "MusicQueue | None", discord.VoiceClient | None]:
        cog: MusicCog | None = self.bot.cogs.get("MusicCog")  # type: ignore[assignment]
        if cog is None:
            return None, None, None
        guild = interaction.guild
        if guild is None:
            return cog, None, None
        queue = cog.get_queue(guild.id)
        vc = guild.voice_client
        return cog, queue, vc

    async def _guard_in_voice(self, interaction: discord.Interaction, vc: discord.VoiceClient | None) -> bool:
        """Return True if the presser is in the bot's voice channel; send ephemeral refusal otherwise."""
        if vc is None or not vc.is_connected():
            await interaction.response.send_message(
                embed=embeds.error(pick_random_r(NOTHING_PLAYING)), ephemeral=True
            )
            return False
        member = interaction.user
        if not hasattr(member, "voice") or member.voice is None or member.voice.channel != vc.channel:
            await interaction.response.send_message(
                embed=embeds.error(pick_random_r(NOT_IN_VOICE)), ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        label="⏸ Pause", style=discord.ButtonStyle.secondary, custom_id="dex:np:playpause"
    )
    async def playpause_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        cog, queue, vc = self._resolve_cog_queue_vc(interaction)
        if cog is None or queue is None:
            await interaction.response.send_message(
                embed=embeds.error("bot isn't ready yet."), ephemeral=True
            )
            return
        if not await self._guard_in_voice(interaction, vc):
            return
        track = queue.get_current()
        if not track or not queue.is_playing and not queue.is_paused:
            await interaction.response.send_message(
                embed=embeds.error(pick_random_r(NOTHING_PLAYING)), ephemeral=True
            )
            return
        result = cog._do_pause_toggle(queue, vc)
        # Update button label to reflect new state
        if result == "paused":
            button.label = "▶ Resume"
        else:
            button.label = "⏸ Pause"
        await interaction.response.edit_message(
            embed=embeds.now_playing(track, queue), view=self
        )

    @discord.ui.button(
        label="⏭ Skip", style=discord.ButtonStyle.secondary, custom_id="dex:np:skip"
    )
    async def skip_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        cog, queue, vc = self._resolve_cog_queue_vc(interaction)
        if cog is None or queue is None:
            await interaction.response.send_message(
                embed=embeds.error("bot isn't ready yet."), ephemeral=True
            )
            return
        if not await self._guard_in_voice(interaction, vc):
            return
        if not queue.is_playing and not queue.is_paused:
            await interaction.response.send_message(
                embed=embeds.error(pick_random_r(NOTHING_PLAYING)), ephemeral=True
            )
            return
        # Ack first — skip starts a background task
        await interaction.response.defer()
        next_track = await cog._do_skip(interaction.guild, queue, vc)
        if next_track:
            await interaction.followup.send(f"skipped. now playing **{next_track.title}**.", ephemeral=True)
        else:
            await interaction.followup.send("end of queue.", ephemeral=True)

    @discord.ui.button(
        label="🔁 Loop: Off", style=discord.ButtonStyle.secondary, custom_id="dex:np:loop"
    )
    async def loop_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        cog, queue, vc = self._resolve_cog_queue_vc(interaction)
        if cog is None or queue is None:
            await interaction.response.send_message(
                embed=embeds.error("bot isn't ready yet."), ephemeral=True
            )
            return
        if not await self._guard_in_voice(interaction, vc):
            return
        track = queue.get_current()
        new_mode = cog._do_loop_cycle(queue)
        # Reflect new loop mode on the button label
        mode_labels = {
            LoopMode.OFF: "🔁 Loop: Off",
            LoopMode.SINGLE: "🔂 Loop: Single",
            LoopMode.QUEUE: "🔁 Loop: Queue",
        }
        button.label = mode_labels[new_mode]
        embed = embeds.now_playing(track, queue) if track else embeds.error("nothing playing.")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(
        label="🔀 Shuffle", style=discord.ButtonStyle.secondary, custom_id="dex:np:shuffle"
    )
    async def shuffle_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        cog, queue, vc = self._resolve_cog_queue_vc(interaction)
        if cog is None or queue is None:
            await interaction.response.send_message(
                embed=embeds.error("bot isn't ready yet."), ephemeral=True
            )
            return
        if not await self._guard_in_voice(interaction, vc):
            return
        track = queue.get_current()
        count = cog._do_shuffle(queue)
        embed = embeds.now_playing(track, queue) if track else embeds.error("nothing playing.")
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(
        label="⏹ Stop", style=discord.ButtonStyle.danger, custom_id="dex:np:stop"
    )
    async def stop_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        cog, queue, vc = self._resolve_cog_queue_vc(interaction)
        if cog is None or queue is None:
            await interaction.response.send_message(
                embed=embeds.error("bot isn't ready yet."), ephemeral=True
            )
            return
        if not await self._guard_in_voice(interaction, vc):
            return
        # Ack first before the async stop + disconnect
        await interaction.response.defer()
        await cog._do_stop(interaction.guild, queue, vc)
        await interaction.followup.send("stopped and cleared the queue.", ephemeral=True)


class MusicCog(commands.Cog):
    """All music slash commands and the playback engine."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.queues: dict[int, MusicQueue] = {}

    @property
    def youtube(self) -> "YouTubeService":
        return self.bot.youtube_service

    @property
    def audio(self) -> "AudioService":
        return self.bot.audio_service

    @property
    def pool(self):
        return self.bot.pool

    def get_queue(self, guild_id: int) -> MusicQueue:
        """Get or create the MusicQueue for a guild."""
        if guild_id not in self.queues:
            self.queues[guild_id] = MusicQueue(guild_id)
        return self.queues[guild_id]

    async def _ensure_voice(self, interaction: discord.Interaction) -> discord.VoiceClient | None:
        """Ensure bot is in the user's voice channel. Returns VoiceClient or None."""
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send(embed=embeds.error("You're not in a voice channel."))
            return None

        user_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            voice_client = await user_channel.connect()
        return voice_client

    async def _play_track(
        self,
        guild: discord.Guild,
        track: Track,
        _skipped: list | None = None,
        offset_seconds: int = 0,
    ) -> None:
        """Start playing a track through the voice client.

        Silently skips unavailable tracks, posting one summary message.

        offset_seconds — seek to this position before starting (0 = beginning).
        """
        voice_client = guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return

        queue = self.get_queue(guild.id)
        queue.is_playing = True
        queue.is_paused = False

        if _skipped is None:
            _skipped = []

        # Resolve the active audio filter chain (Phase 7, D-10, D-12)
        ffmpeg_filter: str | None = None
        if queue.active_filter != "off":
            ffmpeg_filter = config.FFMPEG_FILTERS.get(queue.active_filter)

        # Time-to-first-audio starts now: from source acquisition (cache/copy or
        # cold download + ffmpeg spawn) through to voice_client.play() (PERF-06).
        _ttfa_t0 = time.monotonic()
        try:
            source = await self.audio.get_source(
                track,
                seek_seconds=offset_seconds,
                ffmpeg_filter=ffmpeg_filter,
            )
        except Exception as e:
            log.warning(f"Skipping unavailable: '{track.title}'")
            _skipped.append(track.title)
            next_track = queue.skip()
            await self._persist_queue(guild, queue)
            if next_track:
                await self._play_track(guild, next_track, _skipped)
            else:
                queue.is_playing = False
                # Post summary if we skipped tracks but found nothing playable
                if _skipped:
                    channel = self._get_text_channel(guild)
                    if channel:
                        await channel.send(f"Skipped {len(_skipped)} unavailable tracks. Nothing left to play.")
            return

        # Post summary if we skipped tracks before finding this one
        if _skipped:
            channel = self._get_text_channel(guild)
            if channel:
                await channel.send(f"Skipped {len(_skipped)} unavailable tracks.")

        # Increment generation — any old after-callbacks will see a stale generation and bail
        log.debug("gen=%d → %d in guild %d", queue._play_generation, queue._play_generation + 1, guild.id)
        queue._play_generation += 1
        current_gen = queue._play_generation

        def after_callback(error):
            if error:
                log.error(f"Playback error in guild {guild.id}: {error}")
            # Only advance if this callback belongs to the current generation
            if queue._play_generation == current_gen:
                asyncio.run_coroutine_threadsafe(
                    self._on_track_end(guild), self.bot.loop
                )

        # get_source() already spawned an ffmpeg subprocess. If we don't hand it
        # to voice_client.play(), we must cleanup() it or it orphans.
        try:
            # Stop current playback (old after_callback will fire but see stale generation)
            if voice_client.is_playing() or voice_client.is_paused():
                log.debug("stopping current playback gen=%d in guild %d", queue._play_generation, guild.id)
                voice_client.stop()

            if not voice_client.is_connected():
                source.cleanup()
                queue.is_playing = False
                return

            # Phase 7: record when this track started and from what offset (elapsed tracking)
            queue.mark_started(offset_seconds)

            voice_client.play(source, after=after_callback)
            if hasattr(self.bot, "perf_metrics"):
                self.bot.perf_metrics.record_ttfa(time.monotonic() - _ttfa_t0)
            log.debug("play() called gen=%d connected=%s guild=%d", current_gen, voice_client.is_connected(), guild.id)
            log.info(f"Playing '{track.title}' in guild {guild.id}")
        except Exception:
            source.cleanup()
            queue.is_playing = False
            raise

        # Auto-lyrics (off the playback path): post this song's lyrics to the
        # lyrics thread if enabled. Never awaited — must not delay playback.
        if queue.auto_lyrics:
            asyncio.create_task(self._post_auto_lyrics(guild, track))

        # Prefetch the next track so the inter-song gap is zero (PERF-01 / D-04).
        # Fire-and-forget — must not block or delay current playback.
        # Use the in-scope current_gen captured above; never re-read the generation.
        next_tracks = queue.upcoming()
        if next_tracks:
            asyncio.create_task(self._prefetch_next_track(guild, next_tracks[0], current_gen))

    async def _prefetch_next_track(
        self,
        guild: discord.Guild,
        track: Track,
        expected_gen: int,
    ) -> None:
        """Background prefetch of the next queued track during current playback (PERF-01 / D-04/D-06).

        Generation-guarded at entry AND after the download so a user skip discards
        a stale result — mirrors the existing after_callback generation guard
        (CLAUDE.md gotcha). Swallows all exceptions like _post_auto_lyrics so it
        never affects the playback path.
        """
        try:
            queue = self.get_queue(guild.id)

            # Entry guard: if generation has advanced the user already skipped
            if queue._play_generation != expected_gen:
                log.debug(
                    "prefetch skipped (stale gen): gen=%d expected=%d video_id=%s",
                    queue._play_generation, expected_gen, track.video_id,
                )
                return

            # Early exit if already cached — nothing to download
            if self.audio.is_cached(track.video_id):
                log.debug("prefetch skip — already cached: video_id=%s", track.video_id)
                return

            # Mark this video_id as in-use so LFU eviction skips it (D-13)
            queue._prefetch_video_id = track.video_id
            t0 = time.monotonic()
            try:
                path = await asyncio.wait_for(
                    self.youtube.async_download(track.video_id, track.url),
                    timeout=config.PREFETCH_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                log.info(
                    "prefetch timeout after %.0fs video_id=%s",
                    config.PREFETCH_TIMEOUT_SECONDS, track.video_id,
                )
                return

            elapsed = time.monotonic() - t0

            # Post-download generation guard: discard result if user skipped
            if queue._play_generation != expected_gen:
                log.debug(
                    "prefetch discarded (stale post-download): gen=%d expected=%d video_id=%s",
                    queue._play_generation, expected_gen, track.video_id,
                )
                return

            ok = path is not None and path.exists()
            log.info(
                "prefetch complete video_id=%s elapsed=%.2fs ok=%s",
                track.video_id, elapsed, ok,
            )
            if hasattr(self.bot, "perf_metrics"):
                self.bot.perf_metrics.record_download(elapsed)

        except Exception as exc:  # noqa: BLE001
            log.debug("prefetch error video_id=%s: %s", track.video_id, exc)
        finally:
            # Only clear if this task is still the owner of the slot
            queue = self.get_queue(guild.id)
            if queue._prefetch_video_id == track.video_id:
                queue._prefetch_video_id = None

    async def _refresh_now_playing(self, guild: discord.Guild, queue: MusicQueue) -> None:
        """Re-post the now-playing message at the BOTTOM of the channel on song change.

        Single source of truth for now-playing refresh on track change (natural
        advance + skip). To keep the live player and its controls at the bottom of
        the chat, this deletes the previous now-playing message and sends a fresh
        one as the most recent message — rather than editing the old one in place
        up in scroll history. There is always exactly one live player.

        In-song state changes (pause/resume/loop/shuffle button toggles) edit in
        place via NowPlayingView and intentionally do NOT move the message.
        """
        track = queue.get_current()
        channel = self._get_text_channel(guild)
        if channel is None or track is None:
            return
        embed = embeds.now_playing(track, queue)
        view = NowPlayingView(self.bot).apply_state(queue)
        # Delete the previous now-playing message so there's exactly one live
        # player, and it always lands at the bottom of the channel.
        if queue._now_playing_message_id:
            try:
                old = await channel.fetch_message(queue._now_playing_message_id)
                await old.delete()
            except (discord.NotFound, discord.HTTPException) as del_error:
                log.debug(f"Old now-playing delete skipped (already gone?): {del_error}")
            finally:
                queue._now_playing_message_id = None
        msg = await channel.send(embed=embed, view=view)
        queue._now_playing_message_id = msg.id

    async def _on_track_end(self, guild: discord.Guild) -> None:
        """Called when a track finishes naturally. Handles advance/loop/auto-queue logic."""
        queue = self.get_queue(guild.id)

        # Don't advance if we were manually stopped
        if not queue.is_playing:
            return

        # Track auto-queued song that played fully (not skipped)
        current = queue.get_current()
        if current and current.was_auto_queued and hasattr(self.bot, "server_states"):
            from models.server_state import get_server_state
            state = get_server_state(self.bot.server_states, guild.id)
            state.auto_queue_results["played"] += 1

        next_track = queue.advance()
        await self._persist_queue(guild, queue)
        if next_track:
            await self._play_track(guild, next_track)
            await self._refresh_now_playing(guild, queue)
        else:
            # Queue exhausted — try auto-queue before stopping
            voice_client = guild.voice_client
            if voice_client and voice_client.channel:
                human_members = [m for m in voice_client.channel.members if not m.bot]
                if human_members:
                    ai_cog = self.bot.cogs.get("AICog")
                    if ai_cog:
                        asyncio.create_task(ai_cog.try_auto_queue(guild))
                        return  # Don't set is_playing = False; auto-queue will handle it

            queue.is_playing = False

    async def _post_auto_lyrics(self, guild: discord.Guild, track: Track) -> None:
        """Post the current track's lyrics to the per-guild '🎵 lyrics' thread.

        Background task off the playback path. Resolves (or lazily creates) the
        thread, fetches lyrics via the shared service, posts a paginated view.
        Any failure is logged and swallowed so playback is never affected.
        """
        try:
            queue = self.get_queue(guild.id)
            none = discord.AllowedMentions.none()

            # Resolve the lyrics thread; recreate if it was deleted.
            thread: discord.Thread | None = None
            if queue.lyrics_thread_id is not None:
                thread = guild.get_thread(queue.lyrics_thread_id)
                if thread is None:
                    try:
                        fetched = await guild.fetch_channel(queue.lyrics_thread_id)
                        thread = fetched if isinstance(fetched, discord.Thread) else None
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        thread = None
            if thread is None:
                parent = self._get_text_channel(guild)
                if parent is None:
                    return  # no music channel known yet -> nowhere to post
                thread = await parent.create_thread(
                    name="🎵 lyrics",
                    type=discord.ChannelType.public_thread,
                )
                queue.lyrics_thread_id = thread.id

            lyrics_service = getattr(self.bot, "lyrics_service", None)
            if lyrics_service is None:
                return
            lyrics_text = await lyrics_service.get_lyrics(track.title, track.artist)

            if not lyrics_text:
                await thread.send(
                    f"no lyrics for **{track.title}** — instrumental, or genius is slacking.",
                    allowed_mentions=none,
                )
                return

            pages = chunk_lyrics(lyrics_text, config.LYRICS_PAGE_SIZE)
            if not pages:
                await thread.send(
                    f"no lyrics for **{track.title}** — instrumental, or genius is slacking.",
                    allowed_mentions=none,
                )
                return

            view = LyricsPageView(pages, title=track.title)
            msg = await thread.send(
                embed=view._build_embed(),
                view=view,
                allowed_mentions=none,
            )
            view.message = msg
        except Exception as exc:
            log.warning(f"Auto-lyrics post failed in guild {guild.id}: {exc}")

    def _get_text_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """Get the text channel to post messages in (uses the channel where commands were last used)."""
        queue = self.get_queue(guild.id)
        if queue._text_channel_id:
            channel = guild.get_channel(queue._text_channel_id)
            if channel:
                return channel
        # Fallback — only use system_channel if we can actually post there (WR-06)
        if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
            return guild.system_channel
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                return channel
        return None

    async def _persist_queue(self, guild: discord.Guild, queue: MusicQueue) -> None:
        """Persist queue state after every mutation (D-19/SCALE-04).

        Captures voice-channel id live from guild.voice_client.channel (D-20) —
        NOT stored on the model. Guarded with hasattr so a missing service never
        crashes a command. Persistence failures are swallowed by the service (T-04-09).
        """
        if not hasattr(self.bot, "queue_persistence"):
            return
        # D-20: capture live, not from model — voice channel may change per session
        vc_id = guild.voice_client.channel.id if guild.voice_client else None
        await self.bot.queue_persistence.persist(guild, queue, vc_id)

    # ──────────────────────────── SHARED CONTROL HELPERS ────────────────────────────
    # These are called by both slash commands AND NowPlayingView button callbacks
    # so that logic lives in one place (Task 1 — plan 07-02).

    async def _do_skip(self, guild: discord.Guild, queue: MusicQueue, voice_client: discord.VoiceClient) -> Track | None:
        """Skip to the next track. Returns the new track, or None if queue exhausted."""
        # Track skipped auto-queued songs for "ignored" memory
        current = queue.get_current()
        if current and current.was_auto_queued:
            from models.server_state import get_server_state
            await mark_song_skipped(self.pool, guild_id=str(guild.id), url=current.url)
            if hasattr(self.bot, "server_states"):
                state = get_server_state(self.bot.server_states, guild.id)
                state.auto_queue_results["skipped"] += 1

        next_track = queue.skip()
        await self._persist_queue(guild, queue)
        if next_track:
            asyncio.create_task(self._play_track(guild, next_track))
            # Refresh the now-playing controller so it reflects the new track
            # (otherwise the embed + buttons stay frozen on the skipped song).
            await self._refresh_now_playing(guild, queue)
        else:
            queue.is_playing = False
            voice_client.stop()
        return next_track

    def _do_pause_toggle(self, queue: MusicQueue, voice_client: discord.VoiceClient) -> str:
        """Toggle pause/resume. Returns 'paused' or 'resumed'."""
        if voice_client.is_paused():
            voice_client.resume()
            queue.is_playing = True
            queue.is_paused = False
            queue.mark_resumed()
            return "resumed"
        else:
            voice_client.pause()
            queue.is_playing = False
            queue.is_paused = True
            queue.mark_paused()
            return "paused"

    def _do_loop_cycle(self, queue: MusicQueue) -> LoopMode:
        """Cycle loop mode: off → single → queue → off. Returns new mode."""
        cycle = {
            LoopMode.OFF: LoopMode.SINGLE,
            LoopMode.SINGLE: LoopMode.QUEUE,
            LoopMode.QUEUE: LoopMode.OFF,
        }
        queue.loop_mode = cycle[queue.loop_mode]
        return queue.loop_mode

    def _do_shuffle(self, queue: MusicQueue) -> int:
        """Shuffle upcoming tracks. Returns number of tracks shuffled."""
        upcoming = queue.upcoming()
        queue.shuffle()
        return len(upcoming)

    async def _do_stop(self, guild: discord.Guild, queue: MusicQueue, voice_client: discord.VoiceClient) -> None:
        """Stop playback, clear queue, leave voice. Mirrors the /stop command."""
        queue._play_generation += 1  # invalidate any pending after-callbacks
        queue.clear()
        if hasattr(self.bot, "queue_persistence"):
            await self.bot.queue_persistence.clear_persisted(guild.id)
        if voice_client:
            voice_client.stop()
            await voice_client.disconnect()

    async def _queue_from_selection(
        self,
        interaction: discord.Interaction,
        selected: dict,
        orig_query: str | None = None,
    ) -> None:
        """Queue a song after the user picks from the select menu."""
        await interaction.response.defer()
        log.info(f"Selection: {selected.get('title')} | URL: {selected.get('url')}")

        try:
            data = await self.youtube.async_extract(selected["url"])
            log.info(f"Extracted: {data.get('title')} | {data.get('video_id')}")
        except ValueError as e:
            await interaction.followup.send(embed=embeds.error(str(e)))
            return
        except Exception as e:
            log.error(f"Extract failed: {e}", exc_info=True)
            await interaction.followup.send(embed=embeds.error(f"Failed to extract: {e}"))
            return

        # Phase 6: write the resolution cache so a repeat of this query skips YouTube
        # re-search entirely (PERF-03 / D-07). Guarded by orig_query presence so URL
        # direct-play (which never passes orig_query) never writes the cache (D-09).
        if orig_query is not None and hasattr(self.bot, "pool"):
            try:
                cache_key = normalize_search_query(orig_query)
                await set_resolution_cache(
                    self.bot.pool,
                    query_key=cache_key,
                    video_id=data["video_id"],
                    title=data["title"],
                    ttl_days=config.RES_CACHE_TTL_DAYS,
                )
                log.debug(
                    "resolution_cache write key=%r video_id=%s",
                    cache_key, data["video_id"],
                )
            except Exception as cache_err:
                log.debug("resolution_cache write failed (non-fatal): %s", cache_err)

        track = Track(
            video_id=data["video_id"],
            title=data["title"],
            artist=data["artist"],
            url=data["url"],
            duration_seconds=data["duration"],
            requested_by=interaction.user.id,
            thumbnail=data.get("thumbnail"),
        )

        queue = self.get_queue(interaction.guild.id)
        try:
            position = queue.add(track) + 1
        except QueueFullError:
            await interaction.followup.send(
                f"queue's full at {config.MAX_QUEUE_SIZE_PER_GUILD} tracks. impressive dedication, wrong bot.",
                ephemeral=True,
            )
            return
        await self._persist_queue(interaction.guild, queue)

        await self._log_track(interaction, track)

        voice_client = await self._ensure_voice(interaction)
        if not voice_client:
            return

        if not queue.is_playing:
            queue.current_index = len(queue.tracks) - 1
            await self._play_track(interaction.guild, track)
            embed = embeds.now_playing(track, queue)
            view = NowPlayingView(self.bot)
            msg = await interaction.followup.send(embed=embed, view=view, wait=True)
            queue._now_playing_message_id = msg.id
        else:
            embed = embeds.song_queued(track, position)
            await interaction.followup.send(embed=embed)

    async def _get_top_artist(self, user_id: str) -> str | None:
        """Return the user's top artist from user_artist_counts, or None."""
        try:
            async with self.bot.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT artist FROM user_artist_counts"
                    " WHERE user_id = $1"
                    " ORDER BY play_count DESC LIMIT 1",
                    user_id,
                )
            return row["artist"] if row else None
        except Exception as exc:
            log.debug("Top-artist lookup failed for %s: %s", user_id, exc)
            return None

    async def _post_music_roast(
        self, guild: discord.Guild, line: str
    ) -> None:
        """Post a roast line to the music channel with allowed_mentions=none (D-11, T-03-14)."""
        channel = self._get_text_channel(guild)
        if channel is None:
            return
        try:
            await channel.send(line, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as exc:
            log.debug("Music roast post failed: %s", exc)

    async def _build_roast_line(
        self,
        user_id: str,
        scenario_content: str,
        fallback_pool: list[str],
        fallback_kwargs: dict,
    ) -> str:
        """Attempt a priority-2 Gemini roast; fall back to template on any failure.

        Mirrors EventsCog._generate_ambient_roast but scoped to music-path earned
        roasts (D-08, D-14). Uses the locked few-shot DEXTER voice (D-06) via
        build_chat_prompt. priority=2 only — never contends with /ask (D-08).
        """
        # Prepare template fallback first (guaranteed path, PERS-04/PERS-09)
        fallback_line = pick_random(fallback_pool)
        if fallback_kwargs:
            try:
                fallback_line = fallback_line.format(**fallback_kwargs)
            except KeyError:
                pass  # template without matching placeholder — use as-is

        gemini_service = getattr(self.bot, "gemini_service", None)
        if gemini_service is None:
            return fallback_line

        try:
            pool = getattr(self.bot, "pool", None)
            user_summary: str | None = None
            if pool is not None:
                try:
                    user_summary = await get_user_summary(pool, user_id)
                except Exception as db_err:
                    log.debug("Music roast: taste lookup failed for %s: %s", user_id, db_err)

            user_context = user_summary or "No data on this user yet."
            system_prompt = build_chat_prompt("normal", user_context, "")
            conversation = [
                {
                    "role": "user",
                    "content": (
                        f"{scenario_content}. respond with exactly one short roast line "
                        "in your voice — under 120 characters, lowercase, no preamble."
                    ),
                }
            ]

            result = await gemini_service.chat(system_prompt, conversation, priority=2)

            if result:
                result = result.strip()
                if len(result) > 500:
                    result = result[:497] + "..."
                if result and result[0].isupper():
                    result = result[0].lower() + result[1:]
                return result

        except GeminiRateLimitError:
            log.debug("Music roast: Gemini rate limited, using template")
        except Exception as exc:
            log.debug("Music roast: Gemini failed: %s", exc)

        return fallback_line

    async def _log_track(self, interaction: discord.Interaction, track: Track) -> None:
        """Log a queued track to all database tables, then fire earned roasts."""
        # D-06 / SCALE-01: all 3 per-/play writes in ONE transaction via log_track_batch
        await log_track_batch(
            self.bot.pool,
            guild_id=str(interaction.guild.id),
            user_id=str(interaction.user.id),
            username=interaction.user.display_name,
            title=track.title,
            artist=track.artist,
            url=track.url,
            duration=track.duration_seconds,
        )

        await increment_daily_stat(self.bot.pool, "total_songs_played")
        await increment_daily_stat(self.bot.pool, "total_commands")

        # Fetch new total_songs_queued for milestone check (asyncpg $N params — T-04-04)
        try:
            async with self.bot.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT total_songs_queued FROM user_profiles WHERE user_id = $1",
                    str(interaction.user.id),
                )
            new_total: int = row["total_songs_queued"] if row else 0
        except Exception as exc:
            log.debug("Could not fetch total_songs_queued: %s", exc)
            new_total = 0

        # ── PERS-04: Repeat-song roast (D-08, D-14 always fires at threshold) ──
        try:
            count = await get_repeat_song_count(
                self.bot.pool,
                guild_id=str(interaction.guild.id),
                user_id=str(interaction.user.id),
                title=track.title,
            )
            if count >= config.REPEAT_SONG_ROAST_THRESHOLD:
                top_artist = await self._get_top_artist(str(interaction.user.id))
                scenario = (
                    f"{interaction.user.display_name} has queued '{track.title}' "
                    f"{count} times today"
                    + (f", their top artist is {top_artist}" if top_artist else "")
                )
                line = await self._build_roast_line(
                    user_id=str(interaction.user.id),
                    scenario_content=scenario,
                    fallback_pool=REPEAT_SONG_ROAST_TEMPLATES,
                    fallback_kwargs={
                        "name": interaction.user.display_name,
                        "title": track.title,
                        "count": count,
                    },
                )
                await self._post_music_roast(interaction.guild, line)
        except Exception as exc:
            log.debug("Repeat-song roast failed (non-blocking): %s", exc)

        # ── PERS-09: Song-count milestone roast ──
        try:
            if new_total in config.MILESTONE_SONG_THRESHOLDS:
                top_artist = await self._get_top_artist(str(interaction.user.id))
                scenario = (
                    f"{interaction.user.display_name} just queued their {new_total}th song"
                    + (f", their top artist is {top_artist}" if top_artist else "")
                )
                line = await self._build_roast_line(
                    user_id=str(interaction.user.id),
                    scenario_content=scenario,
                    fallback_pool=MILESTONE_SONG_TEMPLATES,
                    fallback_kwargs={"count": new_total},
                )
                await self._post_music_roast(interaction.guild, line)
        except Exception as exc:
            log.debug("Song-count milestone roast failed (non-blocking): %s", exc)

        # ── PERS-09: Streak update + streak-day milestone roast ──
        try:
            new_streak, longest, streak_milestone = await update_user_streak(
                self.bot.pool,
                user_id=str(interaction.user.id),
                tz_name=config.STREAK_TIMEZONE,
            )
            if streak_milestone is not None:
                top_artist = await self._get_top_artist(str(interaction.user.id))
                scenario = (
                    f"{interaction.user.display_name} just hit a {streak_milestone}-day streak"
                    + (f", their top artist is {top_artist}" if top_artist else "")
                    + (f", their record is {longest} days" if longest else "")
                )
                line = await self._build_roast_line(
                    user_id=str(interaction.user.id),
                    scenario_content=scenario,
                    fallback_pool=MILESTONE_STREAK_TEMPLATES,
                    fallback_kwargs={
                        "days": new_streak,
                        "record": longest,
                    },
                )
                await self._post_music_roast(interaction.guild, line)
        except Exception as exc:
            log.debug("Streak/milestone roast failed (non-blocking): %s", exc)

    # ──────────────────────────── SLASH COMMANDS ────────────────────────────

    @app_commands.command(name="play", description="Search YouTube or queue a URL")
    @app_commands.describe(query="Song name or YouTube URL")
    @app_commands.checks.cooldown(1, config.PLAY_COOLDOWN_SECONDS)
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        if not interaction.user.voice or not interaction.user.voice.channel:
            return await interaction.response.send_message(
                embed=embeds.error("You're not in a voice channel."), ephemeral=True
            )

        await interaction.response.defer()

        # Remember which channel commands are used in
        queue = self.get_queue(interaction.guild.id)
        queue._text_channel_id = interaction.channel.id

        # Reset auto-queue rounds when a human queues a song
        if hasattr(self.bot, "server_states"):
            from models.server_state import get_server_state
            state = get_server_state(self.bot.server_states, interaction.guild.id)
            state.reset_auto_queue()

        if self.youtube.is_url(query):
            # Check for playlist
            if "list=" in query:
                try:
                    log.info(f"Extracting playlist: {query}")
                    playlist_results = await self.youtube.async_extract_playlist(query)
                    log.info(f"Playlist returned {len(playlist_results)} entries")
                    if playlist_results:
                        queue = self.get_queue(interaction.guild.id)
                        voice_client = await self._ensure_voice(interaction)
                        if not voice_client:
                            return

                        count = 0
                        skipped = 0
                        cap_reached = False
                        first_track = None
                        for item in playlist_results:
                            try:
                                duration = item.get("duration") or 0
                                # Skip tracks that exceed duration limit
                                if duration > config.MAX_SONG_DURATION_SECONDS:
                                    skipped += 1
                                    continue

                                track = Track(
                                    video_id=item["video_id"],
                                    title=item["title"],
                                    artist=None,
                                    url=item["url"],
                                    duration_seconds=duration,
                                    requested_by=interaction.user.id,
                                    thumbnail=item.get("thumbnail"),
                                )
                                try:
                                    queue.add(track)
                                except QueueFullError:
                                    cap_reached = True
                                    break
                                count += 1
                                if first_track is None:
                                    first_track = track
                            except (KeyError, TypeError, AttributeError) as entry_error:
                                log.warning(f"Skipping malformed playlist entry: {entry_error}")
                                continue

                        if count > 0:
                            await self._persist_queue(interaction.guild, queue)

                        msg = f"Queued {count} tracks from playlist."
                        if cap_reached:
                            msg += f" (stopped at queue cap of {config.MAX_QUEUE_SIZE_PER_GUILD})"
                        if skipped > 0:
                            msg += f" ({skipped} skipped — too long)"
                        if len(playlist_results) >= config.MAX_PLAYLIST_IMPORT:
                            msg += f" (capped at {config.MAX_PLAYLIST_IMPORT})"

                        if not queue.is_playing and first_track:
                            queue.current_index = len(queue.tracks) - count
                            await self._play_track(interaction.guild, queue.get_current())

                        await interaction.followup.send(msg)
                        return
                    else:
                        await interaction.followup.send(
                            embed=embeds.error("That playlist came back empty — nothing to queue.")
                        )
                        return
                except Exception as e:
                    log.error(f"Playlist extraction failed: {e}", exc_info=True)
                    await interaction.followup.send(
                        embed=embeds.error("Couldn't load that playlist. Try a direct video URL.")
                    )
                    return

            # Direct URL — single video
            try:
                data = await self.youtube.async_extract(query)
            except ValueError as e:
                return await interaction.followup.send(embed=embeds.error(str(e)))

            track = Track(
                video_id=data["video_id"],
                title=data["title"],
                artist=data["artist"],
                url=data["url"],
                duration_seconds=data["duration"],
                requested_by=interaction.user.id,
                thumbnail=data.get("thumbnail"),
            )

            queue = self.get_queue(interaction.guild.id)
            try:
                position = queue.add(track) + 1
            except QueueFullError:
                await interaction.followup.send(
                    f"queue's full at {config.MAX_QUEUE_SIZE_PER_GUILD} tracks. impressive dedication, wrong bot.",
                    ephemeral=True,
                )
                return
            await self._persist_queue(interaction.guild, queue)

            await self._log_track(interaction, track)

            voice_client = await self._ensure_voice(interaction)
            if not voice_client:
                return

            if not queue.is_playing:
                queue.current_index = len(queue.tracks) - 1
                await self._play_track(interaction.guild, track)
                embed = embeds.now_playing(track, queue)
                view = NowPlayingView(self.bot)
                msg = await interaction.followup.send(embed=embed, view=view, wait=True)
                queue._now_playing_message_id = msg.id
            else:
                embed = embeds.song_queued(track, position)
                await interaction.followup.send(embed=embed)
        else:
            # Text search — check resolution cache first (PERF-03 / D-07 / D-09).
            # Direct-URL /play never reaches this branch (is_url guard above).
            cache_key = normalize_search_query(query)
            cached_res = None
            if hasattr(self.bot, "pool"):
                cached_res = await get_resolution_cache(self.bot.pool, query_key=cache_key)

            if cached_res is not None:
                # Cache hit: route cached video_id through the same single-video
                # queue path as the URL branch so duration cap, livestream
                # rejection, and song_history logging are all applied.
                # NOTE: record the hit only after the extract succeeds (below) —
                # a stale entry that forces a fresh search is effectively a miss,
                # and recording True here would double-count it against the False
                # on the fall-through path, corrupting the /stats hit-rate.
                watch_url = f"https://www.youtube.com/watch?v={cached_res['video_id']}"
                log.info(
                    "resolution_cache hit key=%r video_id=%s",
                    cache_key, cached_res["video_id"],
                )
                try:
                    data = await self.youtube.async_extract(watch_url)
                except ValueError as e:
                    # Stale/removed/blocked — fall through to a fresh search
                    log.info(
                        "resolution_cache stale video_id=%s (%s), falling through to search",
                        cached_res["video_id"], e,
                    )
                    cached_res = None
                except Exception as e:
                    log.warning("resolution_cache extract failed (%s), falling through to search", e)
                    cached_res = None

                if cached_res is not None:
                    # Usable hit confirmed — count it once here.
                    if hasattr(self.bot, "perf_metrics"):
                        self.bot.perf_metrics.record_cache_result(True)
                    # Refresh TTL on hit (Pitfall 5 guard)
                    if hasattr(self.bot, "pool"):
                        try:
                            await set_resolution_cache(
                                self.bot.pool,
                                query_key=cache_key,
                                video_id=data["video_id"],
                                title=data["title"],
                                ttl_days=config.RES_CACHE_TTL_DAYS,
                            )
                        except Exception as ttl_err:
                            log.debug("resolution_cache TTL refresh failed (non-fatal): %s", ttl_err)

                    track = Track(
                        video_id=data["video_id"],
                        title=data["title"],
                        artist=data["artist"],
                        url=data["url"],
                        duration_seconds=data["duration"],
                        requested_by=interaction.user.id,
                        thumbnail=data.get("thumbnail"),
                    )

                    queue = self.get_queue(interaction.guild.id)
                    try:
                        position = queue.add(track) + 1
                    except QueueFullError:
                        await interaction.followup.send(
                            f"queue's full at {config.MAX_QUEUE_SIZE_PER_GUILD} tracks. impressive dedication, wrong bot.",
                            ephemeral=True,
                        )
                        return
                    await self._persist_queue(interaction.guild, queue)

                    await self._log_track(interaction, track)

                    voice_client = await self._ensure_voice(interaction)
                    if not voice_client:
                        return

                    if not queue.is_playing:
                        queue.current_index = len(queue.tracks) - 1
                        await self._play_track(interaction.guild, track)
                        embed = embeds.now_playing(track, queue)
                        view = NowPlayingView(self.bot)
                        msg = await interaction.followup.send(embed=embed, view=view, wait=True)
                        queue._now_playing_message_id = msg.id
                    else:
                        embed = embeds.song_queued(track, position)
                        await interaction.followup.send(embed=embed)
                    return

            # Cache miss (or stale) — run the YouTube search
            if hasattr(self.bot, "perf_metrics"):
                self.bot.perf_metrics.record_cache_result(False)
            t0 = time.monotonic()
            results = await self.youtube.async_search(query)
            if hasattr(self.bot, "perf_metrics"):
                self.bot.perf_metrics.record_search(time.monotonic() - t0)
            if not results:
                return await interaction.followup.send(embed=embeds.error("No results found."))

            # Pass orig_query so _queue_from_selection can write the cache after pick
            view = SongSelectView(results, self, orig_query=query)
            await interaction.followup.send("Pick a song:", view=view)

    @app_commands.command(name="skip", description="Skip to the next song")
    @app_commands.checks.cooldown(1, config.SKIP_COOLDOWN_SECONDS)
    async def skip(self, interaction: discord.Interaction) -> None:
        queue = self.get_queue(interaction.guild.id)
        voice_client = interaction.guild.voice_client

        if not voice_client or not queue.is_playing:
            return await interaction.response.send_message(
                embed=embeds.error("Nothing is playing."), ephemeral=True
            )

        # Track skipped auto-queued songs for "ignored" memory
        current = queue.get_current()
        if current and current.was_auto_queued:
            from models.server_state import get_server_state
            await mark_song_skipped(self.bot.pool, guild_id=str(interaction.guild.id), url=current.url)
            if hasattr(self.bot, "server_states"):
                state = get_server_state(self.bot.server_states, interaction.guild.id)
                state.auto_queue_results["skipped"] += 1

        next_track = queue.skip()
        await self._persist_queue(interaction.guild, queue)
        if next_track:
            await interaction.response.send_message(f"Skipped to **{next_track.title}**")
            # Play in background — don't block the response
            asyncio.create_task(self._play_track(interaction.guild, next_track))
        else:
            queue.is_playing = False
            voice_client.stop()
            await interaction.response.send_message("End of queue.")

    @app_commands.command(name="pause", description="Pause the current song")
    async def pause(self, interaction: discord.Interaction) -> None:
        voice_client = interaction.guild.voice_client
        queue = self.get_queue(interaction.guild.id)

        if not voice_client or not voice_client.is_playing():
            return await interaction.response.send_message(
                embed=embeds.error("Nothing is playing."), ephemeral=True
            )

        voice_client.pause()
        queue.is_playing = False
        queue.is_paused = True
        queue.mark_paused()
        await interaction.response.send_message("Paused.")

    @app_commands.command(name="resume", description="Resume playback")
    async def resume(self, interaction: discord.Interaction) -> None:
        voice_client = interaction.guild.voice_client
        queue = self.get_queue(interaction.guild.id)

        if not voice_client or not voice_client.is_paused():
            return await interaction.response.send_message(
                embed=embeds.error("Nothing is paused."), ephemeral=True
            )

        voice_client.resume()
        queue.is_playing = True
        queue.is_paused = False
        queue.mark_resumed()
        await interaction.response.send_message("Resumed.")

    @app_commands.command(name="stop", description="Stop playback, clear queue, leave voice")
    async def stop(self, interaction: discord.Interaction) -> None:
        voice_client = interaction.guild.voice_client
        queue = self.get_queue(interaction.guild.id)

        queue._play_generation += 1  # invalidate any pending after-callbacks
        queue.clear()
        if hasattr(self.bot, "queue_persistence"):
            await self.bot.queue_persistence.clear_persisted(interaction.guild.id)

        if voice_client:
            voice_client.stop()
            await voice_client.disconnect()
        await interaction.response.send_message("Stopped and cleared the queue.")

    @app_commands.command(name="queue", description="Show the current queue")
    @app_commands.checks.cooldown(1, 2.0)
    async def queue_cmd(self, interaction: discord.Interaction) -> None:
        queue = self.get_queue(interaction.guild.id)

        if not queue.tracks:
            return await interaction.response.send_message(
                embed=embeds.error("The queue is empty."), ephemeral=True
            )

        view = QueuePageView(queue)
        embed = embeds.queue_list(queue, page=0)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="shuffle", description="Shuffle upcoming songs")
    @app_commands.checks.cooldown(1, 2.0)
    async def shuffle(self, interaction: discord.Interaction) -> None:
        queue = self.get_queue(interaction.guild.id)

        if len(queue.upcoming()) == 0:
            return await interaction.response.send_message(
                embed=embeds.error("Nothing to shuffle."), ephemeral=True
            )

        queue.shuffle()
        await self._persist_queue(interaction.guild, queue)
        await interaction.response.send_message(f"Shuffled {len(queue.upcoming())} upcoming tracks.")

    @app_commands.command(name="loop", description="Set loop mode")
    @app_commands.describe(mode="Loop mode")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Single", value="single"),
        app_commands.Choice(name="Queue", value="queue"),
    ])
    async def loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        queue = self.get_queue(interaction.guild.id)
        queue.loop_mode = LoopMode(mode.value)
        await self._persist_queue(interaction.guild, queue)
        await interaction.response.send_message(f"Loop mode: **{mode.name}**")

    @app_commands.command(name="nowplaying", description="Show what's currently playing")
    @app_commands.checks.cooldown(1, 2.0)
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        queue = self.get_queue(interaction.guild.id)
        track = queue.get_current()

        if not track or not queue.is_playing:
            return await interaction.response.send_message(
                embed=embeds.error("Nothing is playing."), ephemeral=True
            )

        embed = embeds.now_playing(track, queue)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="replay", description="Restart the current song")
    @app_commands.checks.cooldown(1, 2.0)
    async def replay(self, interaction: discord.Interaction) -> None:
        queue = self.get_queue(interaction.guild.id)
        track = queue.get_current()
        voice_client = interaction.guild.voice_client

        if not track or not voice_client:
            return await interaction.response.send_message(
                embed=embeds.error("Nothing is playing."), ephemeral=True
            )

        await interaction.response.defer()
        await self._play_track(interaction.guild, track)
        embed = embeds.now_playing(track, queue)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="autolyrics", description="Auto-post each song's lyrics to a lyrics thread")
    @app_commands.choices(mode=[
        app_commands.Choice(name="on", value="on"),
        app_commands.Choice(name="off", value="off"),
    ])
    async def autolyrics(
        self, interaction: discord.Interaction, mode: app_commands.Choice[str]
    ) -> None:
        """Toggle auto-lyrics for this server (in-memory; resets on restart)."""
        queue = self.get_queue(interaction.guild.id)
        none = discord.AllowedMentions.none()
        if mode.value == "on":
            queue.auto_lyrics = True
            await interaction.response.send_message(
                "fine. i'll narrate your questionable taste in a thread. enjoy.",
                allowed_mentions=none,
            )
        else:
            queue.auto_lyrics = False
            await interaction.response.send_message(
                "auto-lyrics off. blessed silence.",
                allowed_mentions=none,
            )

    @app_commands.command(name="lyrics", description="Show lyrics for the current song")
    @app_commands.checks.cooldown(1, float(config.LYRICS_COOLDOWN_SECONDS))
    async def lyrics(self, interaction: discord.Interaction) -> None:
        """Fetch and paginate lyrics for the current song (LYRIC-01, D-15).

        Defers before the network call (Genius fetch can take 2-5s).
        Falls back to NO_LYRICS_FOUND personality error when nothing is
        playing or neither Genius nor AZLyrics returns lyrics (D-15).
        self.bot.lyrics_service is wired by plan 03-06 on_ready — guarded
        with hasattr so a cold-start without the service degrades cleanly.
        All sends use allowed_mentions=none (T-03-14 / defense-in-depth).
        """
        queue = self.get_queue(interaction.guild.id)
        track = queue.get_current()

        if not track or not queue.is_playing:
            return await interaction.response.send_message(
                embed=embeds.error("nothing is playing. queue something first."),
                ephemeral=True,
            )

        await interaction.response.defer()

        # Guard: lyrics_service wired by 03-06; degrade if absent
        lyrics_service = getattr(self.bot, "lyrics_service", None)
        if lyrics_service is None:
            await interaction.followup.send(
                pick_random(NO_LYRICS_FOUND),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        lyrics_text = await lyrics_service.get_lyrics(track.title, track.artist)

        if not lyrics_text:
            await interaction.followup.send(
                pick_random(NO_LYRICS_FOUND),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        pages = chunk_lyrics(lyrics_text, config.LYRICS_PAGE_SIZE)
        if not pages:
            await interaction.followup.send(
                pick_random(NO_LYRICS_FOUND),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        view = LyricsPageView(pages, title=track.title)
        msg = await interaction.followup.send(
            embed=view._build_embed(),
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
            wait=True,
        )
        view.message = msg

    @app_commands.command(name="history", description="Show recently queued songs")
    @app_commands.checks.cooldown(1, 5.0)
    async def history(self, interaction: discord.Interaction) -> None:
        """Show server-wide recent song history with pagination (HIST-01, D-16).

        Fetches up to config.HISTORY_FETCH_LIMIT rows from song_history,
        paginated at config.HISTORY_PAGE_SIZE per page. Each row shows:
        title / artist / who requested (username or fallback) / when (date).
        All sends use allowed_mentions=none (T-03-14).
        """
        rows = await get_history_rows(
            self.bot.pool,
            guild_id=str(interaction.guild.id),
            limit=int(config.HISTORY_FETCH_LIMIT),
        )

        if not rows:
            return await interaction.response.send_message(
                embed=embeds.error("no history yet. queue something."),
                ephemeral=True,
            )

        view = HistoryPageView(rows, guild=interaction.guild)
        msg = await interaction.response.send_message(
            embed=view._build_embed(),
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        # Fetch the sent message to store on the view for on_timeout
        try:
            view.message = await interaction.original_response()
        except discord.HTTPException:
            pass

    # ──────────────────────────── PHASE 7: NAVIGATION + FILTER COMMANDS ────────────────────────────

    @app_commands.command(name="seek", description="Jump to a position in the current song")
    @app_commands.describe(position="Time to jump to — e.g. 1:30 or 90 (seconds)")
    @app_commands.checks.cooldown(1, config.SEEK_COOLDOWN_SECONDS)
    async def seek(self, interaction: discord.Interaction, position: str) -> None:
        """Seek to a position within the current track (D-14, D-15, PLAYER-02).

        Accepts mm:ss, h:mm:ss, or raw seconds.  Past-end seeks advance to the
        next track (D-15).  Enforces SEEK_COOLDOWN_SECONDS.
        """
        queue = self.get_queue(interaction.guild.id)
        track = queue.get_current()
        voice_client = interaction.guild.voice_client

        if not track or not queue.is_playing:
            return await interaction.response.send_message(
                embed=embeds.error(pick_random_r(NOTHING_PLAYING)), ephemeral=True
            )

        secs = parse_time(position)
        if secs is None:
            return await interaction.response.send_message(
                embed=embeds.error(
                    "i don't know what that time is. try something like `1:30` or `90`."
                ),
                ephemeral=True,
            )

        await interaction.response.defer()

        if secs >= track.duration_seconds:
            # Past end — skip to next track (D-15)
            next_track = await self._do_skip(interaction.guild, queue, voice_client)
            if next_track:
                await interaction.followup.send(
                    f"seek past the end — skipping to **{next_track.title}**."
                )
            else:
                await interaction.followup.send("seek past the end — nothing left to play.")
            return

        # Re-play from the new offset (filter chain preserved via active_filter)
        await self._play_track(interaction.guild, track, offset_seconds=secs)
        embed = embeds.now_playing(track, queue)
        view = NowPlayingView(self.bot)
        await interaction.followup.send(
            f"jumped to **{format_duration(secs)}**.", embed=embed, view=view
        )

    @app_commands.command(name="previous", description="Go back to the previous song")
    @app_commands.checks.cooldown(1, config.SEEK_COOLDOWN_SECONDS)
    async def previous(self, interaction: discord.Interaction) -> None:
        """Restart the prior queue entry on the no-pop index model (D-17, PLAYER-03)."""
        queue = self.get_queue(interaction.guild.id)
        voice_client = interaction.guild.voice_client

        if not voice_client or not queue.is_playing and not queue.is_paused:
            return await interaction.response.send_message(
                embed=embeds.error(pick_random_r(NOTHING_PLAYING)), ephemeral=True
            )

        prev_track = queue.previous()
        if prev_track is None:
            return await interaction.response.send_message(
                embed=embeds.error("nothing before this. you're at the beginning."), ephemeral=True
            )

        await interaction.response.defer()
        await self._play_track(interaction.guild, prev_track)
        await self._persist_queue(interaction.guild, queue)
        embed = embeds.now_playing(prev_track, queue)
        view = NowPlayingView(self.bot)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="jump", description="Jump to a specific song in the queue")
    @app_commands.describe(position="Queue position to jump to (1-based)")
    @app_commands.checks.cooldown(1, config.SEEK_COOLDOWN_SECONDS)
    async def jump(self, interaction: discord.Interaction, position: int) -> None:
        """Jump to the nth queue slot (1-based in UI) on the no-pop index model (D-17, PLAYER-04)."""
        queue = self.get_queue(interaction.guild.id)

        if not queue.tracks:
            return await interaction.response.send_message(
                embed=embeds.error(pick_random_r(NOTHING_PLAYING)), ephemeral=True
            )

        # Convert 1-based UI position to 0-based index
        index = position - 1
        target = queue.jump_to(index)
        if target is None:
            return await interaction.response.send_message(
                embed=embeds.error(
                    f"position {position} is out of range. queue has {len(queue.tracks)} tracks."
                ),
                ephemeral=True,
            )

        await interaction.response.defer()
        await self._play_track(interaction.guild, target)
        await self._persist_queue(interaction.guild, queue)
        embed = embeds.now_playing(target, queue)
        view = NowPlayingView(self.bot)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="filter", description="Apply an audio filter to the current stream")
    @app_commands.describe(preset="Audio filter to apply")
    @app_commands.choices(preset=[
        app_commands.Choice(name="Bass Boost", value="bassboost"),
        app_commands.Choice(name="Nightcore", value="nightcore"),
        app_commands.Choice(name="Slowed + Reverb", value="slowed+reverb"),
        app_commands.Choice(name="8D", value="8d"),
        app_commands.Choice(name="Off", value="off"),
    ])
    @app_commands.checks.cooldown(1, config.FILTER_COOLDOWN_SECONDS)
    async def filter_cmd(
        self, interaction: discord.Interaction, preset: app_commands.Choice[str]
    ) -> None:
        """Apply a sticky whole-guild audio filter, resuming from current position (D-07..D-13, PLAYER-07/08).

        Preset is resolved from config.FFMPEG_FILTERS — no raw user text reaches FFmpeg (T-07-02-02).
        off restores opus passthrough (D-12). Sticky across tracks until /filter off (D-10).
        """
        queue = self.get_queue(interaction.guild.id)
        voice_client = interaction.guild.voice_client

        if not voice_client or not voice_client.is_connected():
            return await interaction.response.send_message(
                embed=embeds.error(pick_random_r(NOTHING_PLAYING)), ephemeral=True
            )

        if not interaction.user.voice or interaction.user.voice.channel != voice_client.channel:
            return await interaction.response.send_message(
                embed=embeds.error(pick_random_r(NOT_IN_VOICE)), ephemeral=True
            )

        current = queue.get_current()
        queue.active_filter = preset.value

        await interaction.response.defer()

        if current and (queue.is_playing or queue.is_paused):
            # Re-play from current elapsed position with the new (or cleared) filter (D-09)
            pos = queue.elapsed_seconds()
            await self._play_track(interaction.guild, current, offset_seconds=pos)
            await self._persist_queue(interaction.guild, queue)

        if preset.value == "off":
            msg = pick_random_r(FILTER_CLEARED)
        else:
            # Format the filter name into the response if the template uses {filter}
            template = pick_random_r(FILTER_APPLIED)
            try:
                msg = template.format(filter=preset.name)
            except (KeyError, IndexError):
                msg = template

        embed = embeds.now_playing(current, queue) if current else None
        view = NowPlayingView(self.bot) if current else None
        if embed:
            await interaction.followup.send(msg, embed=embed, view=view)
        else:
            await interaction.followup.send(msg)

    # ──────────────────────────── VOICE EVENTS ────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        """Handle bot disconnect recovery and empty channel detection."""
        if not member.guild.voice_client:
            return

        voice_client = member.guild.voice_client
        queue = self.get_queue(member.guild.id)

        # Bot was disconnected
        if member.id == self.bot.user.id and after.channel is None and before.channel is not None:
            log.warning(f"Bot disconnected from voice in guild {member.guild.id}")
            queue.is_playing = False
            queue.is_paused = False

            for attempt in range(3):
                try:
                    log.info("reconnect attempt %d/3 in guild %d", attempt + 1, member.guild.id)
                    await asyncio.sleep(1)
                    vc = await before.channel.connect()
                    log.info("reconnect: vc.is_connected()=%s gen=%d guild=%d", vc.is_connected(), queue._play_generation, member.guild.id)
                    track = queue.get_current()
                    if track:
                        await self._play_track(member.guild, track)
                        log.info(f"Reconnected and restarted track in guild {member.guild.id}")
                    return
                except Exception as e:
                    log.error(f"Reconnect attempt {attempt + 1} failed: {e}")

            queue._play_generation += 1  # invalidate stale after-callbacks (mirrors /stop template)
            queue.clear()
            if hasattr(self.bot, "queue_persistence"):
                await self.bot.queue_persistence.clear_persisted(member.guild.id)
            channel = self._get_text_channel(member.guild)
            if channel:
                await channel.send(embed=embeds.error("Lost voice connection. Queue cleared."))
            return

        # Check if bot is now alone in voice
        if voice_client.channel and len(voice_client.channel.members) == 1:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
