"""LibraryCog — personal favorites + named playlists + guild jams (Phase 7/12).

Commands:
    /favorite  — save the currently-playing song to the invoking user's favorites
    /favorites — show a pick-list select menu; choose to queue or remove a saved song
    /playlist save <name>   — freeze the current queue as a named snapshot
    /playlist load <name>   — append a saved snapshot to the current queue
    /playlist list          — show the user's saved playlists
    /playlist delete <name> — delete a saved playlist
    /jam save <name>        — freeze the current queue as a server-shared jam
    /jam add <name>         — append the now-playing track to a named jam
    /jam load <name>        — append a saved jam to the current queue
    /jam list               — show this server's saved jams
    /jam delete <name>      — delete a saved jam

Favorites are per-user and global (cross-server, D-18), capped at FAVORITES_MAX_PER_USER
(25, D-21), current-song-only (D-19). All responses are ephemeral (D-29, D-30).

Playlists are per-user frozen JSONB snapshots (D-23), capped at PLAYLISTS_MAX_PER_USER
(25, D-28), append-on-load (D-26), upsert-on-name-clash (D-27).

Jams are per-guild shared frozen JSONB snapshots (UX-01, D-01..D-05), capped at
JAMS_PER_GUILD_MAX (25), keyed on guild_id (no ownership gate, D-03).

Security:
    T-07-03-01 — all DB calls use $N-parameterised asyncpg helpers; no string interpolation.
    T-07-03-02 — every read/write is keyed on str(interaction.user.id); users only touch
                 their own rows.
    T-07-03-03 — FAVORITES_MAX_PER_USER cap enforced before insert; dedupe via PK avoids
                 count inflation.
    T-07-04-01 — playlist snapshot serialised via json.dumps; name stored as bound param.
    T-07-04-02 — every playlist op keyed on str(interaction.user.id); no cross-user reads.
    T-07-04-03 — PLAYLISTS_MAX_PER_USER + PLAYLIST_NAME_MAX_LENGTH enforced on save.
    T-12-01-01 — all guild_jams helpers bind values as $N positional params; no f-string SQL.
    T-12-01-02 — every jam read/write keyed on guild_id; cross-guild isolation enforced in DB.
    T-12-01-03 — jam name empty/length enforced before any write (reuse playlist guard, D-05).
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from cogs.ai import parse_suggestions
from database import (
    add_favorite,
    count_favorites,
    get_favorites,
    remove_favorite,
    save_playlist,
    get_playlist,
    list_playlists,
    delete_playlist,
    count_playlists,
    save_jam,
    get_jam,
    list_jams,
    delete_jam,
    count_jams,
)
from logic.autoqueue import validate_youtube_match
from models.queue import Track, QueueFullError
from personality.prompts import build_jam_suggestion_prompt
from personality.responses import (
    pick_random,
    FAVORITE_SAVED,
    FAVORITE_DUPLICATE,
    FAVORITE_CAP_HIT,
    FAVORITES_EMPTY,
    NOTHING_PLAYING,
    PLAYLIST_SAVED,
    PLAYLIST_LOADED,
    PLAYLIST_NOT_FOUND,
    PLAYLIST_CAP_HIT,
)
from utils.logger import log
from utils import embeds


# ---------------------------------------------------------------------------
# FavoritesView — ephemeral select menu for /favorites
#
# UX flow:
#   1. User sees a Select (up to 25 favorites) + "Queue" button + "Remove" button.
#   2. User picks from the Select → title is shown in "Queue" / "Remove" labels.
#   3. "Queue" button → queues the selected track via MusicCog.
#   4. "Remove" button → deletes the selected entry from user_favorites.
#
# All responses are ephemeral (D-29, D-30). The view is ephemeral so no
# stable custom_ids needed (timeout=180s).
# ---------------------------------------------------------------------------


class FavoritesSelect(discord.ui.Select):
    """Dropdown listing the user's saved favorites (up to 25 options, D-20)."""

    def __init__(self, rows: list[dict], user_id: int) -> None:
        self._rows = rows
        self._user_id = user_id

        options = []
        for row in rows:
            title = row["title"][:100]
            artist = row.get("artist") or "Unknown Artist"
            desc = artist[:100]
            options.append(
                discord.SelectOption(
                    label=title,
                    description=desc,
                    value=row["video_id"],
                )
            )

        super().__init__(
            placeholder="Pick a favorite...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Store the selected video_id on the parent view and acknowledge."""
        # Ownership guard (T-07-03-02)
        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                "that's not your favorites list.", ephemeral=True
            )
            return

        selected_video_id = self.values[0]
        row = next((r for r in self._rows if r["video_id"] == selected_video_id), None)
        if row is None:
            await interaction.response.send_message(
                "couldn't find that track. try /favorites again.", ephemeral=True
            )
            return

        # Store selection on the parent view so Queue/Remove buttons can act on it
        view: FavoritesView = self.view  # type: ignore[assignment]
        view.selected_video_id = selected_video_id
        view.selected_row = row

        # Acknowledge the selection in-place
        title = row["title"]
        await interaction.response.edit_message(
            content=f"selected: **{title}** — press Queue to play or Remove to delete.",
        )


class QueueButton(discord.ui.Button):
    """Button to queue the currently selected favorite."""

    def __init__(self, cog: "LibraryCog", user_id: int) -> None:
        super().__init__(
            label="Queue",
            style=discord.ButtonStyle.primary,
            emoji="▶",
        )
        self._cog = cog
        self._user_id = user_id

    async def callback(self, interaction: discord.Interaction) -> None:
        """Queue the selected favorite via MusicCog."""
        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                "that's not your favorites list.", ephemeral=True
            )
            return

        view: FavoritesView = self.view  # type: ignore[assignment]
        if view.selected_row is None:
            await interaction.response.send_message(
                "pick a track from the menu first.", ephemeral=True
            )
            return

        await self._cog._queue_favorite(interaction, view.selected_row)
        self.view.stop()


class RemoveButton(discord.ui.Button):
    """Button to remove the currently selected favorite."""

    def __init__(self, cog: "LibraryCog", user_id: int) -> None:
        super().__init__(
            label="Remove",
            style=discord.ButtonStyle.danger,
            emoji="🗑",
        )
        self._cog = cog
        self._user_id = user_id

    async def callback(self, interaction: discord.Interaction) -> None:
        """Delete the selected favorite from the database."""
        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                "that's not your favorites list.", ephemeral=True
            )
            return

        view: FavoritesView = self.view  # type: ignore[assignment]
        if view.selected_video_id is None:
            await interaction.response.send_message(
                "pick a track from the menu first, then hit remove.", ephemeral=True
            )
            return

        video_id = view.selected_video_id
        title = view.selected_row["title"] if view.selected_row else video_id

        await remove_favorite(
            self._cog.bot.pool,
            user_id=str(self._user_id),
            video_id=video_id,
        )
        log.info("User %s removed favorite video_id=%s", self._user_id, video_id)

        await interaction.response.edit_message(
            content=f"removed **{title}** from your favorites.",
            view=None,
        )
        self.view.stop()


class FavoritesView(discord.ui.View):
    """Ephemeral view with a favorites select + Queue + Remove buttons (D-20).

    timeout=180s — ephemeral views don't survive restarts, so no need for
    stable custom_ids or timeout=None here.
    """

    def __init__(self, rows: list[dict], cog: "LibraryCog", user_id: int) -> None:
        super().__init__(timeout=180.0)
        self.selected_video_id: str | None = None
        self.selected_row: dict | None = None

        self.add_item(FavoritesSelect(rows, user_id))
        self.add_item(QueueButton(cog, user_id))
        self.add_item(RemoveButton(cog, user_id))

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# LibraryCog
# ---------------------------------------------------------------------------


class LibraryCog(commands.Cog):
    """Personal favorites commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ---- internal helpers ------------------------------------------------

    async def _queue_favorite(
        self, interaction: discord.Interaction, row: dict
    ) -> None:
        """Queue a favorite track via MusicCog's existing add+play path.

        Mirrors what _queue_from_selection does after the user picks from the
        search menu, but skips the YouTube extraction (we already have all
        Track fields in the favorite row).
        """
        music_cog = self.bot.get_cog("MusicCog")  # type: ignore[attr-defined]
        if music_cog is None:
            await interaction.response.send_message(
                "music isn't loaded right now. can't queue that.", ephemeral=True
            )
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "this only works in a server.", ephemeral=True
            )
            return

        # Rebuild a Track from the stored favorite row
        track = Track(
            video_id=row["video_id"],
            title=row["title"],
            artist=row.get("artist"),
            url=row["url"],
            duration_seconds=row.get("duration_seconds") or 0,
            requested_by=interaction.user.id,
            thumbnail=row.get("thumbnail"),
        )

        queue = music_cog.get_queue(guild.id)  # type: ignore[attr-defined]

        # Ensure bot is in voice (same guard as _ensure_voice in MusicCog)
        if not interaction.user.voice or not interaction.user.voice.channel:  # type: ignore[union-attr]
            await interaction.response.send_message(
                "you're not in a voice channel.", ephemeral=True
            )
            return

        # Defer the response to allow async operations (if not already done)
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        user_channel = interaction.user.voice.channel  # type: ignore[union-attr]
        voice_client = guild.voice_client
        if voice_client is None:
            try:
                voice_client = await user_channel.connect()
            except Exception as exc:
                # Guard the connect (permissions / already-connecting race / region
                # failure) so the deferred-ephemeral interaction gets a real error
                # rather than a permanent "thinking…" (WR-03).
                log.warning("favorites: connect failed: %s", exc)
                await interaction.followup.send(
                    "couldn't join your voice channel. try again.", ephemeral=True
                )
                return

        # Add to queue (cap enforced in MusicQueue.add)
        try:
            position = queue.add(track) + 1
        except QueueFullError:
            await interaction.followup.send(
                f"queue is full at {config.MAX_QUEUE_SIZE_PER_GUILD}. impressive hoarding.",
                ephemeral=True,
            )
            return

        # Persist queue state
        if hasattr(self.bot, "queue_persistence"):
            try:
                await self.bot.queue_persistence.persist(
                    guild, queue, user_channel.id
                )
            except Exception as exc:
                log.debug("favorites: queue persist failed: %s", exc)

        if not queue.is_playing:
            queue.current_index = len(queue.tracks) - 1
            queue._text_channel_id = interaction.channel.id
            await music_cog._play_track(guild, track)  # type: ignore[attr-defined]
            # Post the public now-playing player via the music cog's shared helper so
            # every entry point uses one player-management path — an ephemeral followup
            # would only be visible to the loader and could not be re-bound after a
            # restart, and the music cog's player manager cannot fetch/delete an
            # ephemeral message id on the next song change (WR-02).
            await music_cog._refresh_now_playing(guild, queue)  # type: ignore[attr-defined]
            await interaction.followup.send(
                f"playing **{track.title}** now.", ephemeral=True
            )
        else:
            embed = embeds.song_queued(track, position)
            await interaction.followup.send(embed=embed, ephemeral=True)

    # ---- slash commands --------------------------------------------------

    @app_commands.command(name="favorite", description="Save the current song to your favorites")
    @app_commands.checks.cooldown(1, config.FAVORITE_COOLDOWN_SECONDS)
    async def favorite(self, interaction: discord.Interaction) -> None:
        """/favorite — save the current song to the invoking user's personal favorites.

        Ephemeral responses only (D-29, D-30). Cap at FAVORITES_MAX_PER_USER = 25 (D-21).
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "this only works in a server.", ephemeral=True
            )
            return

        music_cog = self.bot.get_cog("MusicCog")  # type: ignore[attr-defined]
        if music_cog is None:
            await interaction.response.send_message(
                pick_random(NOTHING_PLAYING), ephemeral=True
            )
            return

        queue = music_cog.get_queue(guild.id)  # type: ignore[attr-defined]
        track = queue.get_current()

        if track is None or not queue.is_playing:
            await interaction.response.send_message(
                pick_random(NOTHING_PLAYING), ephemeral=True
            )
            return

        user_id = str(interaction.user.id)

        # Cap check (D-21, T-07-03-03) — checked BEFORE insert attempt
        current_count = await count_favorites(self.bot.pool, user_id=user_id)
        if current_count >= config.FAVORITES_MAX_PER_USER:
            await interaction.response.send_message(
                pick_random(FAVORITE_CAP_HIT), ephemeral=True
            )
            return

        # Dedupe: ON CONFLICT DO NOTHING means add_favorite is a no-op for duplicates.
        # We detect a duplicate by comparing count before and after.
        count_before = current_count  # already fetched above
        await add_favorite(
            self.bot.pool,
            user_id=user_id,
            video_id=track.video_id,
            title=track.title,
            artist=track.artist,
            url=track.url,
            duration_seconds=track.duration_seconds,
            thumbnail=track.thumbnail,
        )
        count_after = await count_favorites(self.bot.pool, user_id=user_id)

        if count_after == count_before:
            # No row was inserted → duplicate (D-19)
            await interaction.response.send_message(
                pick_random(FAVORITE_DUPLICATE), ephemeral=True
            )
        else:
            log.info("User %s favorited: %s (%s)", user_id, track.title, track.video_id)
            await interaction.response.send_message(
                pick_random(FAVORITE_SAVED), ephemeral=True
            )

    @app_commands.command(name="favorites", description="View and queue your saved favorites")
    async def favorites(self, interaction: discord.Interaction) -> None:
        """/favorites — show an ephemeral pick-list of the user's saved favorites (D-20).

        Select a song to set it as active, then press Queue to play it or Remove to delete it.
        """
        user_id = str(interaction.user.id)
        rows = await get_favorites(self.bot.pool, user_id=user_id)

        if not rows:
            await interaction.response.send_message(
                pick_random(FAVORITES_EMPTY), ephemeral=True
            )
            return

        view = FavoritesView(rows, self, interaction.user.id)
        await interaction.response.send_message(
            "your favorites — pick one, then press Queue or Remove:",
            view=view,
            ephemeral=True,
        )

    @favorite.error
    async def favorite_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"cooldown. try again in {error.retry_after:.1f}s.", ephemeral=True
            )

    # ---- /playlist group -------------------------------------------------

    playlist = app_commands.Group(
        name="playlist",
        description="Save and load named playlists",
    )

    @playlist.command(name="save", description="Save the current queue as a named playlist")
    @app_commands.describe(name="Name for the playlist (max 60 chars)")
    async def playlist_save(
        self, interaction: discord.Interaction, name: str
    ) -> None:
        """/playlist save <name> — snapshot the current queue to a named playlist.

        Guards: empty queue, over-long name, playlist cap (unless overwriting).
        Upserts on name clash (D-27). Ephemeral response (D-29, D-30).
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "this only works in a server.", ephemeral=True
            )
            return

        name = name.strip()
        if not name:
            await interaction.response.send_message(
                "playlist name can't be empty.", ephemeral=True
            )
            return

        if len(name) > config.PLAYLIST_NAME_MAX_LENGTH:
            await interaction.response.send_message(
                f"that name is too long. keep it under {config.PLAYLIST_NAME_MAX_LENGTH} chars.",
                ephemeral=True,
            )
            return

        music_cog = self.bot.get_cog("MusicCog")  # type: ignore[attr-defined]
        if music_cog is None:
            await interaction.response.send_message(
                "music isn't loaded right now.", ephemeral=True
            )
            return

        queue = music_cog.get_queue(guild.id)  # type: ignore[attr-defined]
        if not queue.tracks:
            await interaction.response.send_message(
                "the queue is empty. add some songs first.", ephemeral=True
            )
            return

        user_id = str(interaction.user.id)

        # Cap check — allow overwriting an existing playlist without counting it twice
        # (T-07-04-03, D-28). Only block when creating a genuinely new name.
        existing = await get_playlist(self.bot.pool, user_id=user_id, name=name)
        if existing is None:
            current_count = await count_playlists(self.bot.pool, user_id=user_id)
            if current_count >= config.PLAYLISTS_MAX_PER_USER:
                await interaction.response.send_message(
                    pick_random(PLAYLIST_CAP_HIT), ephemeral=True
                )
                return

        snapshot = [t.to_dict() for t in queue.tracks]
        await save_playlist(self.bot.pool, user_id=user_id, name=name, snapshot=snapshot)

        log.info(
            "User %s saved playlist '%s' with %d tracks", user_id, name, len(snapshot)
        )
        await interaction.response.send_message(
            f"{pick_random(PLAYLIST_SAVED)} ({len(snapshot)} tracks, \"{name}\")",
            ephemeral=True,
        )

    @playlist.command(name="load", description="Append a saved playlist to the current queue")
    @app_commands.describe(name="Name of the playlist to load")
    async def playlist_load(
        self, interaction: discord.Interaction, name: str
    ) -> None:
        """/playlist load <name> — rebuild tracks from snapshot and APPEND to queue (D-26).

        Truncates to MAX_QUEUE_SIZE_PER_GUILD with a message if the queue would overflow.
        Starts playback if the queue was idle. Ephemeral summary (D-29, D-30).
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "this only works in a server.", ephemeral=True
            )
            return

        user_id = str(interaction.user.id)
        name = name.strip()

        rows = await get_playlist(self.bot.pool, user_id=user_id, name=name)
        if rows is None:
            await interaction.response.send_message(
                pick_random(PLAYLIST_NOT_FOUND), ephemeral=True
            )
            return

        music_cog = self.bot.get_cog("MusicCog")  # type: ignore[attr-defined]
        if music_cog is None:
            await interaction.response.send_message(
                "music isn't loaded right now.", ephemeral=True
            )
            return

        if not interaction.user.voice or not interaction.user.voice.channel:  # type: ignore[union-attr]
            await interaction.response.send_message(
                "you're not in a voice channel.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        queue = music_cog.get_queue(guild.id)  # type: ignore[attr-defined]
        was_idle = not queue.is_playing

        added = 0
        truncated = 0
        for track_dict in rows:
            track = Track.from_dict({**track_dict, "requested_by": interaction.user.id})
            try:
                queue.add(track)
                added += 1
            except QueueFullError:
                truncated += 1

        # Persist queue state
        if hasattr(self.bot, "queue_persistence"):
            try:
                await self.bot.queue_persistence.persist(
                    guild,
                    queue,
                    interaction.user.voice.channel.id,  # type: ignore[union-attr]
                )
            except Exception as exc:
                log.debug("playlist load: queue persist failed: %s", exc)

        # Kick off playback if we were idle
        if was_idle and queue.tracks:
            user_channel = interaction.user.voice.channel  # type: ignore[union-attr]
            voice_client = guild.voice_client
            if voice_client is None:
                try:
                    voice_client = await user_channel.connect()
                except Exception as exc:
                    # Stop here on connect failure instead of falling through to
                    # _play_track with no voice client connected (WR-03).
                    log.warning("playlist load: connect failed: %s", exc)
                    await interaction.followup.send(
                        "couldn't join your voice channel. try again.", ephemeral=True
                    )
                    return

            queue.current_index = len(queue.tracks) - added  # first newly added track
            queue._text_channel_id = interaction.channel.id
            first_track = queue.get_current()
            if first_track is not None:
                await music_cog._play_track(guild, first_track)  # type: ignore[attr-defined]
                # Shared now-playing helper posts the public player (WR-02); the
                # ephemeral text below is the loader's private confirmation.
                await music_cog._refresh_now_playing(guild, queue)  # type: ignore[attr-defined]
                await interaction.followup.send(
                    f"{pick_random(PLAYLIST_LOADED)} now playing \"{name}\" — {added} track(s).",
                    ephemeral=True,
                )
                return

        summary = f"{pick_random(PLAYLIST_LOADED)} added {added} track(s) from \"{name}\"."
        if truncated:
            summary += (
                f" {truncated} track(s) were skipped — queue is at the"
                f" {config.MAX_QUEUE_SIZE_PER_GUILD}-song cap."
            )
        await interaction.followup.send(summary, ephemeral=True)

    @playlist.command(name="list", description="Show your saved playlists")
    async def playlist_list(self, interaction: discord.Interaction) -> None:
        """/playlist list — ephemeral embed of the user's saved playlists (D-24)."""
        user_id = str(interaction.user.id)
        rows = await list_playlists(self.bot.pool, user_id=user_id)

        if not rows:
            await interaction.response.send_message(
                "you don't have any saved playlists. use /playlist save while something's queued.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="your playlists",
            color=discord.Color.blurple(),
        )
        for row in rows:
            updated = row["updated_at"]
            # updated_at may be a datetime or an aware datetime from asyncpg
            ts = (
                discord.utils.format_dt(updated, style="R")
                if hasattr(updated, "tzinfo")
                else str(updated)
            )
            embed.add_field(
                name=row["name"],
                value=f"{row['track_count']} track(s) — updated {ts}",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @playlist.command(name="delete", description="Delete a saved playlist")
    @app_commands.describe(name="Name of the playlist to delete")
    async def playlist_delete(
        self, interaction: discord.Interaction, name: str
    ) -> None:
        """/playlist delete <name> — remove a named playlist (D-28).

        Ephemeral confirmation or not-found message (D-29, D-30).
        """
        user_id = str(interaction.user.id)
        name = name.strip()

        deleted = await delete_playlist(self.bot.pool, user_id=user_id, name=name)
        if not deleted:
            await interaction.response.send_message(
                pick_random(PLAYLIST_NOT_FOUND), ephemeral=True
            )
            return

        log.info("User %s deleted playlist '%s'", user_id, name)
        await interaction.response.send_message(
            f"deleted playlist \"{name}\".", ephemeral=True
        )

    # ---- /jam group (Phase 12, UX-01) ------------------------------------
    # Guild-scoped shared mixtapes — anyone in the server can save/add/load/list/delete.
    # Mental model: /playlist = yours (user-global), /jam = the server's (guild-scoped, D-01).
    # All subcommands respond ephemeral=True (T-12-01-03).

    jam = app_commands.Group(
        name="jam",
        description="Manage this server's shared mixtapes",
    )

    @jam.command(name="save", description="Save the current queue as a server jam")
    @app_commands.describe(name="Name for the jam (max 60 chars)")
    async def jam_save(
        self, interaction: discord.Interaction, name: str
    ) -> None:
        """/jam save <name> — snapshot the current queue to a guild-shared jam.

        Guards: guild-only, empty queue, over-long name, jam cap (unless overwriting).
        Upserts on name clash. Ephemeral response (T-12-01-03, D-03, D-05).
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "this only works in a server.", ephemeral=True
            )
            return

        name = name.strip()
        if not name:
            await interaction.response.send_message(
                "jam name can't be empty.", ephemeral=True
            )
            return

        if len(name) > config.PLAYLIST_NAME_MAX_LENGTH:
            await interaction.response.send_message(
                f"that name is too long. keep it under {config.PLAYLIST_NAME_MAX_LENGTH} chars.",
                ephemeral=True,
            )
            return

        music_cog = self.bot.get_cog("MusicCog")  # type: ignore[attr-defined]
        if music_cog is None:
            await interaction.response.send_message(
                "music isn't loaded right now.", ephemeral=True
            )
            return

        queue = music_cog.get_queue(guild.id)  # type: ignore[attr-defined]
        if not queue.tracks:
            await interaction.response.send_message(
                "the queue is empty. add some songs first.", ephemeral=True
            )
            return

        guild_id = str(guild.id)

        # Cap check — allow overwriting an existing jam without counting it twice (D-05).
        # Only block when creating a genuinely new name.
        existing = await get_jam(self.bot.pool, guild_id=guild_id, name=name)
        if existing is None:
            current_count = await count_jams(self.bot.pool, guild_id=guild_id)
            if current_count >= config.JAMS_PER_GUILD_MAX:
                await interaction.response.send_message(
                    f"this server has hit the {config.JAMS_PER_GUILD_MAX}-jam cap."
                    " delete one before saving a new jam.",
                    ephemeral=True,
                )
                return

        snapshot = [t.to_dict() for t in queue.tracks]
        await save_jam(self.bot.pool, guild_id=guild_id, name=name, snapshot=snapshot)

        log.info(
            "Guild %s: jam '%s' saved with %d tracks by user %s",
            guild_id, name, len(snapshot), interaction.user.id,
        )
        await interaction.response.send_message(
            f"saved jam \"{name}\" ({len(snapshot)} tracks).",
            ephemeral=True,
        )

    @jam.command(name="add", description="Add the now-playing track to a jam")
    @app_commands.describe(name="Name of the jam to append to")
    async def jam_add(
        self, interaction: discord.Interaction, name: str
    ) -> None:
        """/jam add <name> — append the now-playing track to a named jam (D-04).

        If no track is currently playing, responds with a nothing-playing message.
        If the named jam doesn't exist yet, creates it with just the one track.
        Applies the jam cap check only when creating a new jam name.
        Ephemeral response (T-12-01-03, D-03).
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "this only works in a server.", ephemeral=True
            )
            return

        name = name.strip()
        if not name:
            await interaction.response.send_message(
                "jam name can't be empty.", ephemeral=True
            )
            return

        if len(name) > config.PLAYLIST_NAME_MAX_LENGTH:
            await interaction.response.send_message(
                f"that name is too long. keep it under {config.PLAYLIST_NAME_MAX_LENGTH} chars.",
                ephemeral=True,
            )
            return

        music_cog = self.bot.get_cog("MusicCog")  # type: ignore[attr-defined]
        if music_cog is None:
            await interaction.response.send_message(
                "music isn't loaded right now.", ephemeral=True
            )
            return

        queue = music_cog.get_queue(guild.id)  # type: ignore[attr-defined]

        # Nothing-playing guard — do NOT crash on None track (T-12-01-03, Pitfall 5)
        track = queue.get_current()
        if track is None:
            await interaction.response.send_message(
                pick_random(NOTHING_PLAYING), ephemeral=True
            )
            return

        guild_id = str(guild.id)

        # Load existing snapshot (None = new jam)
        existing = await get_jam(self.bot.pool, guild_id=guild_id, name=name)

        # Cap check — only applies when creating a new jam name
        if existing is None:
            current_count = await count_jams(self.bot.pool, guild_id=guild_id)
            if current_count >= config.JAMS_PER_GUILD_MAX:
                await interaction.response.send_message(
                    f"this server has hit the {config.JAMS_PER_GUILD_MAX}-jam cap."
                    " delete one before creating a new jam.",
                    ephemeral=True,
                )
                return

        snapshot = existing if existing is not None else []
        snapshot = list(snapshot)  # defensive copy
        snapshot.append(track.to_dict())

        await save_jam(self.bot.pool, guild_id=guild_id, name=name, snapshot=snapshot)

        log.info(
            "Guild %s: track '%s' added to jam '%s' by user %s (now %d tracks)",
            guild_id, track.title, name, interaction.user.id, len(snapshot),
        )
        await interaction.response.send_message(
            f"added \"{track.title}\" to jam \"{name}\" ({len(snapshot)} track(s) total).",
            ephemeral=True,
        )

    @jam.command(name="load", description="Append a server jam to the current queue")
    @app_commands.describe(name="Name of the jam to load")
    async def jam_load(
        self, interaction: discord.Interaction, name: str
    ) -> None:
        """/jam load <name> — rebuild tracks from a guild jam and APPEND to queue (D-04).

        Mirrors playlist_load exactly but reads from get_jam(guild_id=...) instead of
        get_playlist(user_id=...). Truncates at MAX_QUEUE_SIZE_PER_GUILD with a report
        (T-12-01-05 / Pitfall 7). Handles empty-jam snapshot as a distinct error case.
        Starts playback if the queue was idle. Ephemeral summary (T-12-01-03).
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "this only works in a server.", ephemeral=True
            )
            return

        guild_id = str(guild.id)
        name = name.strip()

        rows = await get_jam(self.bot.pool, guild_id=guild_id, name=name)
        if rows is None:
            await interaction.response.send_message(
                f"i can't find a jam called \"{name}\". check /jam list.",
                ephemeral=True,
            )
            return

        # Empty-jam snapshot — distinct error rather than silent no-op (Pitfall 7)
        if len(rows) == 0:
            await interaction.response.send_message(
                f"that jam is empty.", ephemeral=True
            )
            return

        music_cog = self.bot.get_cog("MusicCog")  # type: ignore[attr-defined]
        if music_cog is None:
            await interaction.response.send_message(
                "music isn't loaded right now.", ephemeral=True
            )
            return

        if not interaction.user.voice or not interaction.user.voice.channel:  # type: ignore[union-attr]
            await interaction.response.send_message(
                "you're not in a voice channel.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        queue = music_cog.get_queue(guild.id)  # type: ignore[attr-defined]
        was_idle = not queue.is_playing

        added = 0
        truncated = 0
        for track_dict in rows:
            track = Track.from_dict({**track_dict, "requested_by": interaction.user.id})
            try:
                queue.add(track)
                added += 1
            except QueueFullError:
                truncated += 1

        # Persist queue state
        if hasattr(self.bot, "queue_persistence"):
            try:
                await self.bot.queue_persistence.persist(
                    guild,
                    queue,
                    interaction.user.voice.channel.id,  # type: ignore[union-attr]
                )
            except Exception as exc:
                log.debug("jam load: queue persist failed: %s", exc)

        # Kick off playback if we were idle
        if was_idle and queue.tracks:
            user_channel = interaction.user.voice.channel  # type: ignore[union-attr]
            voice_client = guild.voice_client
            if voice_client is None:
                try:
                    voice_client = await user_channel.connect()
                except Exception as exc:
                    # Stop here on connect failure instead of falling through to
                    # _play_track with no voice client connected (WR-03).
                    log.warning("jam load: connect failed: %s", exc)
                    await interaction.followup.send(
                        "couldn't join your voice channel. try again.", ephemeral=True
                    )
                    return

            queue.current_index = len(queue.tracks) - added  # first newly added track
            queue._text_channel_id = interaction.channel.id
            first_track = queue.get_current()
            if first_track is not None:
                await music_cog._play_track(guild, first_track)  # type: ignore[attr-defined]
                # Shared now-playing helper posts the public player (WR-02); the
                # ephemeral text below is the loader's private confirmation.
                await music_cog._refresh_now_playing(guild, queue)  # type: ignore[attr-defined]
                await interaction.followup.send(
                    f"loaded jam \"{name}\": now playing — {added} track(s).",
                    ephemeral=True,
                )
                return

        summary = f"loaded jam \"{name}\": added {added} track(s)."
        if truncated:
            summary += (
                f" {truncated} track(s) were skipped — queue is at the"
                f" {config.MAX_QUEUE_SIZE_PER_GUILD}-song cap."
            )
        await interaction.followup.send(summary, ephemeral=True)

    @jam.command(name="list", description="Show this server's saved jams")
    async def jam_list(self, interaction: discord.Interaction) -> None:
        """/jam list — ephemeral embed of the guild's saved jams (UX-01, D-02)."""
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "this only works in a server.", ephemeral=True
            )
            return

        guild_id = str(guild.id)
        rows = await list_jams(self.bot.pool, guild_id=guild_id)

        if not rows:
            await interaction.response.send_message(
                "this server has no jams yet. use /jam save while something's queued.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="server jams",
            color=discord.Color.blurple(),
        )
        for row in rows:
            updated = row["updated_at"]
            ts = (
                discord.utils.format_dt(updated, style="R")
                if hasattr(updated, "tzinfo")
                else str(updated)
            )
            embed.add_field(
                name=row["name"],
                value=f"{row['track_count']} track(s) — updated {ts}",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @jam.command(name="delete", description="Delete a server jam")
    @app_commands.describe(name="Name of the jam to delete")
    async def jam_delete(
        self, interaction: discord.Interaction, name: str
    ) -> None:
        """/jam delete <name> — remove a named guild jam (D-03, D-05).

        Any guild member can delete (no ownership gate — collaborative model).
        Ephemeral confirmation or not-found message (T-12-01-03).
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "this only works in a server.", ephemeral=True
            )
            return

        guild_id = str(guild.id)
        name = name.strip()

        deleted = await delete_jam(self.bot.pool, guild_id=guild_id, name=name)
        if not deleted:
            await interaction.response.send_message(
                f"i can't find a jam called \"{name}\". check /jam list.",
                ephemeral=True,
            )
            return

        log.info("Guild %s: jam '%s' deleted by user %s", guild_id, name, interaction.user.id)
        await interaction.response.send_message(
            f"deleted jam \"{name}\".", ephemeral=True
        )

    @jam.command(
        name="suggest",
        description="Get validation-gated AI suggestions for a jam",
    )
    @app_commands.describe(name="Name of the jam to riff on")
    async def jam_suggest(
        self, interaction: discord.Interaction, name: str
    ) -> None:
        """/jam suggest <name> — seed Gemini with the named jam's EXISTING tracks and
        request additions (D-06). EVERY suggestion is validated against real YouTube
        search results via validate_youtube_match (reused verbatim from the auto-queue
        hallucination guard — NOT reimplemented, NOT difflib) before it is ever offered
        (BRAIN-03 hard requirement). Propose-and-confirm (D-07): the validated
        candidates are shown and the shared jam snapshot is written ONLY inside the
        confirm view's Confirm callback — never here, never before the user presses it.
        A non-existent jam name returns an in-character message and never crashes,
        since D-06 seeds from tracks that must already exist.
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "this only works in a server.", ephemeral=True
            )
            return

        name = name.strip()
        if not name:
            await interaction.response.send_message(
                "jam name can't be empty.", ephemeral=True
            )
            return

        if len(name) > config.PLAYLIST_NAME_MAX_LENGTH:
            await interaction.response.send_message(
                f"that name is too long. keep it under {config.PLAYLIST_NAME_MAX_LENGTH} chars.",
                ephemeral=True,
            )
            return

        music_cog = self.bot.get_cog("MusicCog")  # type: ignore[attr-defined]
        if music_cog is None:
            await interaction.response.send_message(
                "music isn't loaded right now.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        guild_id = str(guild.id)

        # D-06: seed from the jam's EXISTING tracks. Unlike jam_add's create-on-miss
        # semantics, a jam that doesn't exist yet has nothing to riff on — in-character
        # message, never a crash.
        existing = await get_jam(self.bot.pool, guild_id=guild_id, name=name)
        if existing is None:
            await interaction.followup.send(
                f"i don't have a jam called \"{name}\" to riff on. check /jam list.",
                ephemeral=True,
            )
            return

        gemini_service = getattr(self.bot, "gemini_service", None)
        if gemini_service is None:
            await interaction.followup.send(
                "the brain's offline right now. try again later.", ephemeral=True
            )
            return

        prompt = build_jam_suggestion_prompt(existing, count=config.JAM_SUGGEST_CANDIDATE_COUNT)
        try:
            response = await gemini_service.chat(prompt, [], priority=2)
        except Exception as exc:
            log.debug("jam suggest: gemini call failed for jam '%s' (%s)", name, exc)
            response = None

        suggestions = parse_suggestions(response) if response else None
        validated_candidates: list[dict] = []
        if suggestions:
            # BRAIN-03 hard requirement: EVERY suggestion is re-validated against real
            # YouTube search results before it is ever offered — reused verbatim from
            # the auto-queue validation loop (cogs/ai.py::try_auto_queue).
            for suggestion in suggestions:
                search_query = f"{suggestion['title']} {suggestion['artist']}"
                try:
                    results = await self.bot.youtube_service.async_search(
                        search_query, count=config.AUTO_QUEUE_SEARCH_CANDIDATES
                    )
                except Exception as exc:
                    log.debug(
                        "jam suggest: async_search failed for '%s' (%s)", search_query, exc
                    )
                    continue
                if not results:
                    continue

                validated = None
                for result in results:
                    if validate_youtube_match(
                        result.get("title", ""), suggestion["title"], suggestion["artist"]
                    ):
                        validated = result
                        break

                if validated is None:
                    # No candidate passed validation for this suggestion — drop it,
                    # don't error (D-07).
                    continue

                validated_candidates.append({
                    "title": validated.get("title") or suggestion["title"],
                    "artist": suggestion["artist"],
                    "url": validated.get("url"),
                })

        # D-07: if none survive validation, say so in character and leave the jam
        # snapshot completely untouched — no save_jam call is reachable on this path.
        if not validated_candidates:
            await interaction.followup.send(
                f"nothing landed for \"{name}\" — every suggestion failed the youtube check.",
                ephemeral=True,
            )
            return

        lines = "\n".join(
            f"- {c['title']} by {c['artist']}" for c in validated_candidates
        )
        # Task 2 wires the propose-and-confirm view here (D-07) — placeholder
        # send only, no save_jam call is reachable from this function.
        await interaction.followup.send(
            f"here's what i'd add to \"{name}\":\n{lines}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LibraryCog(bot))
