"""LibraryCog — personal favorites management (Phase 7, PLAYER-05).

Commands:
    /favorite  — save the currently-playing song to the invoking user's favorites
    /favorites — show a pick-list select menu; choose to queue or remove a saved song

Favorites are per-user and global (cross-server, D-18), capped at FAVORITES_MAX_PER_USER
(25, D-21), current-song-only (D-19). All responses are ephemeral (D-29, D-30).

Security:
    T-07-03-01 — all DB calls use $N-parameterised asyncpg helpers; no string interpolation.
    T-07-03-02 — every read/write is keyed on str(interaction.user.id); users only touch
                 their own rows.
    T-07-03-03 — FAVORITES_MAX_PER_USER cap enforced before insert; dedupe via PK avoids
                 count inflation.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from database import add_favorite, count_favorites, get_favorites, remove_favorite
from models.queue import Track, QueueFullError
from personality.responses import (
    pick_random,
    FAVORITE_SAVED,
    FAVORITE_DUPLICATE,
    FAVORITE_CAP_HIT,
    FAVORITES_EMPTY,
    NOTHING_PLAYING,
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
            voice_client = await user_channel.connect()

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
                await self.bot.queue_persistence.persist(guild.id, queue)
            except Exception as exc:
                log.debug("favorites: queue persist failed: %s", exc)

        if not queue.is_playing:
            queue.current_index = len(queue.tracks) - 1
            await music_cog._play_track(guild, track)  # type: ignore[attr-defined]
            from cogs.music import NowPlayingView
            embed = embeds.now_playing(track, queue)
            view = NowPlayingView(self.bot)
            msg = await interaction.followup.send(embed=embed, view=view, wait=True)
            queue._now_playing_message_id = msg.id
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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LibraryCog(bot))
