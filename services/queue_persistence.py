"""Queue persistence service — UPSERT on mutation, smart-rejoin restore on boot."""

from __future__ import annotations

import json

import asyncpg

import config
from logic.playback import clamp_restore_index, exceeds_queue_cap, should_smart_rejoin
from models.queue import LoopMode, Track
from utils.logger import log


class QueuePersistenceService:
    """Persists guild queue state to Postgres and restores it on bot boot.

    Usage:
        # Wire in bot.py on_ready (after pool creation, before cog loading):
        bot.queue_persistence = QueuePersistenceService(bot.pool)

        # Persist on mutation (called by cogs/music.py hooks in 04-04):
        await bot.queue_persistence.persist(guild, queue, voice_channel_id)

        # Restore on boot (called in bot.py on_ready after cogs load):
        await restore_queues(bot)  # module-level wrapper
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def persist(
        self,
        guild,
        queue,
        voice_channel_id: int | None,
    ) -> None:
        """UPSERT full queue state to guild_queues. Called on every mutation (D-19).

        Builds a typed jsonb payload from the queue's current state and runs a
        parameterised INSERT … ON CONFLICT DO UPDATE. Failures are caught and
        logged — persistence issues must never crash playback (D-20).

        SECURITY (T-04-06): payload is json.dumps of a typed dict whose keys are
        fixed and whose values come from within the bot (not from user input). The
        guild_id is cast via str(guild.id). Both flow through $N params — no string
        interpolation anywhere.
        """
        payload = {
            "tracks": [t.to_dict() for t in queue.tracks],
            "current_index": queue.current_index,
            "loop_mode": queue.loop_mode.value,
            "text_channel_id": queue._text_channel_id,
            "voice_channel_id": voice_channel_id,
            "active_filter": queue.active_filter,  # Phase 7: persist sticky filter (D-10)
        }
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO guild_queues (guild_id, payload, updated_at)"
                    " VALUES ($1, $2::jsonb, now())"
                    " ON CONFLICT (guild_id)"
                    " DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()",
                    str(guild.id),
                    json.dumps(payload),
                )
        except Exception as exc:
            log.warning("persist_queue failed for guild %s: %s", guild.id, exc)

    async def clear_persisted(self, guild_id: int) -> None:
        """Delete the persisted queue row for a guild.

        Called when the queue is cleared (e.g. /stop) so a cleared queue is not
        restored on next boot. Failures are logged but not fatal.
        """
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM guild_queues WHERE guild_id = $1",
                    str(guild_id),
                )
        except Exception as exc:
            log.warning("clear_persisted failed for guild %s: %s", guild_id, exc)

    async def restore_queues(self, bot) -> None:
        """Restore all guild queues from Postgres on bot boot (D-21).

        Reads every row from guild_queues, reconstructs in-memory MusicQueue state
        for each guild, and performs a smart rejoin: connects to voice and starts
        playback only when the previously-active channel still has a non-bot human
        present. If the channel is empty or gone, the queue is silently restored in
        memory (user can /resume manually).

        Must be called AFTER all cogs are loaded (Pitfall 4 — MusicCog must exist).
        """
        rows = await self._pool.fetch("SELECT guild_id, payload FROM guild_queues")
        music_cog = bot.cogs.get("MusicCog")
        if music_cog is None:
            log.warning("restore_queues: MusicCog not loaded — skipping restore")
            return

        for row in rows:
            guild_id = int(row["guild_id"])

            # Normalise payload — asyncpg may return jsonb as dict or as str
            payload = row["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)

            guild = bot.get_guild(guild_id)
            if guild is None:
                # Bot is no longer in this guild; skip silently
                continue

            queue = music_cog.get_queue(guild_id)

            # Restore in-memory queue state. Respect the per-guild cap on restore
            # (CR-03): persisted data could exceed it after a config change or
            # tampering — truncate defensively rather than bypassing the cap.
            restored = [Track.from_dict(t) for t in payload.get("tracks", [])]
            if exceeds_queue_cap(len(restored), config.MAX_QUEUE_SIZE_PER_GUILD):
                log.warning(
                    "restore_queues: guild %s queue (%d) exceeds cap %d — truncating",
                    guild_id, len(restored), config.MAX_QUEUE_SIZE_PER_GUILD,
                )
                restored = restored[: config.MAX_QUEUE_SIZE_PER_GUILD]
            queue.tracks = restored

            # Clamp current_index into range (CR-03): a stale or non-int index must
            # not reach get_current() -> _play_track(None).
            queue.current_index = clamp_restore_index(
                payload.get("current_index", 0), len(queue.tracks)
            )

            queue.loop_mode = LoopMode(payload.get("loop_mode", "off"))
            queue._text_channel_id = payload.get("text_channel_id")
            queue.active_filter = payload.get("active_filter", "off")  # Phase 7: restore sticky filter (D-10)

            # Smart rejoin (D-21): only connect if humans are already in the channel,
            # we have something to play, and we are not already connected (CR-03).
            vc_id = payload.get("voice_channel_id")
            current = queue.get_current() if queue.tracks else None
            if vc_id:
                vc_channel = guild.get_channel(vc_id)
                if vc_channel and should_smart_rejoin(
                    has_current=current is not None,
                    already_connected=guild.voice_client is not None,
                    humans_present=any(not m.bot for m in vc_channel.members),
                ):
                    try:
                        vc = await vc_channel.connect()
                        log.info("smart-rejoin: connected=%s guild=%s", vc.is_connected(), guild_id)
                        if not vc.is_connected():
                            log.warning("Smart rejoin: vc not connected post-connect() guild=%s", guild_id)
                            continue  # skip THIS guild only — never abort the whole restore loop (CR-01)
                        await music_cog._play_track(guild, current)
                    except Exception as exc:
                        log.warning(
                            "Smart rejoin failed for guild %s: %s", guild_id, exc
                        )
                # else: restore silently — no humans present; user must /play or /resume


# ---------------------------------------------------------------------------
# Module-level wrapper — bot.py imports this name so it can call it directly
# without holding a reference to the service instance.
# ---------------------------------------------------------------------------


async def restore_queues(bot) -> None:
    """Module-level wrapper — delegates to bot.queue_persistence.restore_queues(bot).

    bot.py does:
        from services.queue_persistence import restore_queues
        await restore_queues(bot)
    """
    await bot.queue_persistence.restore_queues(bot)
