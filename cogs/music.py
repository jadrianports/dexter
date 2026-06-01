"""Music slash commands and playback engine."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

import config
from models.queue import Track, LoopMode, MusicQueue
from utils import embeds
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
            await self.cog._queue_from_selection(interaction, selected)
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

    def __init__(self, results: list[dict], cog: "MusicCog", timeout: float = 180.0) -> None:
        super().__init__(timeout=timeout)
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
    def db(self):
        return self.bot.db

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

    async def _play_track(self, guild: discord.Guild, track: Track, _skipped: list | None = None) -> None:
        """Start playing a track through the voice client.

        Silently skips unavailable tracks, posting one summary message.
        """
        voice_client = guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return

        queue = self.get_queue(guild.id)
        queue.is_playing = True
        queue.is_paused = False

        if _skipped is None:
            _skipped = []

        try:
            source = await self.audio.get_source(track)
        except Exception as e:
            log.warning(f"Skipping unavailable: '{track.title}'")
            _skipped.append(track.title)
            next_track = queue.skip()
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
                voice_client.stop()

            if not voice_client.is_connected():
                source.cleanup()
                queue.is_playing = False
                return

            voice_client.play(source, after=after_callback)
            log.info(f"Playing '{track.title}' in guild {guild.id}")
        except Exception:
            source.cleanup()
            raise

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
        if next_track:
            await self._play_track(guild, next_track)
            # Edit existing now-playing message, or send new one if edit fails
            channel = self._get_text_channel(guild)
            if channel:
                embed = embeds.now_playing(next_track, queue)
                if queue._now_playing_message_id:
                    try:
                        msg = await channel.fetch_message(queue._now_playing_message_id)
                        await msg.edit(embed=embed)
                        return
                    except (discord.NotFound, discord.HTTPException) as edit_error:
                        log.debug(f"Now-playing edit failed, sending a new message: {edit_error}")
                msg = await channel.send(embed=embed)
                queue._now_playing_message_id = msg.id
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

    def _get_text_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """Get the text channel to post messages in (uses the channel where commands were last used)."""
        queue = self.get_queue(guild.id)
        if queue._text_channel_id:
            channel = guild.get_channel(queue._text_channel_id)
            if channel:
                return channel
        # Fallback
        if guild.system_channel:
            return guild.system_channel
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                return channel
        return None

    async def _queue_from_selection(self, interaction: discord.Interaction, selected: dict) -> None:
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
        position = queue.add(track) + 1

        await self._log_track(interaction, track)

        voice_client = await self._ensure_voice(interaction)
        if not voice_client:
            return

        if not queue.is_playing:
            queue.current_index = len(queue.tracks) - 1
            await self._play_track(interaction.guild, track)
            embed = embeds.now_playing(track, queue)
            msg = await interaction.followup.send(embed=embed, wait=True)
            queue._now_playing_message_id = msg.id
        else:
            embed = embeds.song_queued(track, position)
            await interaction.followup.send(embed=embed)

    async def _log_track(self, interaction: discord.Interaction, track: Track) -> None:
        """Log a queued track to all database tables."""
        from database import log_song, update_artist_count, update_user_profile, increment_daily_stat

        await log_song(
            self.db,
            guild_id=str(interaction.guild.id),
            user_id=str(interaction.user.id),
            title=track.title,
            artist=track.artist,
            url=track.url,
            duration=track.duration_seconds,
        )
        await update_artist_count(self.db, user_id=str(interaction.user.id), artist=track.artist)
        await update_user_profile(self.db, user_id=str(interaction.user.id), username=interaction.user.display_name)
        await increment_daily_stat(self.db, "total_songs_played")
        await increment_daily_stat(self.db, "total_commands")

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
                                queue.add(track)
                                count += 1
                                if first_track is None:
                                    first_track = track
                            except (KeyError, TypeError, AttributeError) as entry_error:
                                log.warning(f"Skipping malformed playlist entry: {entry_error}")
                                continue

                        msg = f"Queued {count} tracks from playlist."
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
            position = queue.add(track) + 1

            await self._log_track(interaction, track)

            voice_client = await self._ensure_voice(interaction)
            if not voice_client:
                return

            if not queue.is_playing:
                queue.current_index = len(queue.tracks) - 1
                await self._play_track(interaction.guild, track)
                embed = embeds.now_playing(track, queue)
                msg = await interaction.followup.send(embed=embed, wait=True)
                queue._now_playing_message_id = msg.id
            else:
                embed = embeds.song_queued(track, position)
                await interaction.followup.send(embed=embed)
        else:
            # Text search — show select menu
            results = await self.youtube.async_search(query)
            if not results:
                return await interaction.followup.send(embed=embeds.error("No results found."))

            view = SongSelectView(results, self)
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
            from database import mark_song_skipped
            from models.server_state import get_server_state
            await mark_song_skipped(self.db, guild_id=str(interaction.guild.id), url=current.url)
            if hasattr(self.bot, "server_states"):
                state = get_server_state(self.bot.server_states, interaction.guild.id)
                state.auto_queue_results["skipped"] += 1

        next_track = queue.skip()
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
        await interaction.response.send_message("Resumed.")

    @app_commands.command(name="stop", description="Stop playback, clear queue, leave voice")
    async def stop(self, interaction: discord.Interaction) -> None:
        voice_client = interaction.guild.voice_client
        queue = self.get_queue(interaction.guild.id)

        queue._play_generation += 1  # invalidate any pending after-callbacks
        queue.clear()

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
                    await asyncio.sleep(1)
                    vc = await before.channel.connect()
                    track = queue.get_current()
                    if track:
                        await self._play_track(member.guild, track)
                        log.info(f"Reconnected and restarted track in guild {member.guild.id}")
                    return
                except Exception as e:
                    log.error(f"Reconnect attempt {attempt + 1} failed: {e}")

            queue.clear()
            channel = self._get_text_channel(member.guild)
            if channel:
                await channel.send(embed=embeds.error("Lost voice connection. Queue cleared."))
            return

        # Check if bot is now alone in voice
        if voice_client.channel and len(voice_client.channel.members) == 1:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
