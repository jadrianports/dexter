"""Regression test for the silent auto-queue bug.

Root cause: on natural queue exhaustion, `_on_track_end` hands off to
`try_auto_queue` but leaves `queue.is_playing = True` (music.py: "auto-queue
will handle it"). The old playback-start guard `if voice_client and not
queue.is_playing:` then never fired, so auto-queue APPENDED tracks but never
called `_play_track` — the user heard silence.

Fix: gate playback start on the live voice-client state (the ground truth for
"is audio flowing"), not the stale `queue.is_playing` flag.

Mock style mirrors tests/test_roast_command.py (unit mocks, no live DB/Discord).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.queue import MusicQueue, Track


def _existing_track() -> Track:
    return Track(
        video_id="old0",
        title="Already Played",
        artist="Someone",
        url="https://youtu.be/old0",
        duration_seconds=180,
        requested_by=1,
    )


def _extract_data(video_id: str) -> dict:
    return {
        "video_id": video_id,
        "title": f"Rec {video_id}",
        "artist": "Rec Artist",
        "url": f"https://youtu.be/{video_id}",
        "duration": 200,  # under MAX_SONG_DURATION_SECONDS
        "thumbnail": None,
    }


def _make_env(*, queue_is_playing: bool, vc_is_playing: bool):
    """Build (cog, guild, queue, music_cog) for a queue that just exhausted.

    queue_is_playing — the (possibly stale) MusicQueue.is_playing flag.
    vc_is_playing    — what the live voice client reports (ground truth).
    """
    # Real queue with one finished track; index parked on it (exhaustion state).
    queue = MusicQueue(guild_id=100)
    queue.tracks = [_existing_track()]
    queue.current_index = 0
    queue.is_playing = queue_is_playing

    music_cog = MagicMock()
    music_cog.get_queue = MagicMock(return_value=queue)
    music_cog._play_track = AsyncMock()
    music_cog._get_text_channel = MagicMock(return_value=None)  # skip announce send

    voice_client = MagicMock()
    voice_client.is_playing = MagicMock(return_value=vc_is_playing)
    voice_client.is_paused = MagicMock(return_value=False)

    guild = MagicMock()
    guild.id = 100
    guild.voice_client = voice_client

    bot = MagicMock()
    bot.user = SimpleNamespace(id=999)
    bot.server_states = {}
    bot.pool = MagicMock()
    bot.gemini_service = MagicMock()
    bot.gemini_service.chat = AsyncMock(return_value="[ignored — parse is patched]")
    bot.youtube_service = MagicMock()
    bot.youtube_service.async_search = AsyncMock(return_value=[{"url": "https://youtu.be/x"}])
    bot.youtube_service.async_extract = AsyncMock(
        side_effect=[_extract_data("new1"), _extract_data("new2")]
    )
    bot.cogs = {"MusicCog": music_cog}

    from cogs.ai import AICog
    cog = AICog(bot)
    return cog, guild, queue, music_cog


def _patches():
    """Common module-level patches so try_auto_queue reaches its playback branch."""
    state = SimpleNamespace(auto_queue_rounds=0, auto_queue_results={"played": 0, "skipped": 0})
    return (
        patch("cogs.ai.get_server_state", return_value=state),
        patch("cogs.ai.get_recent_songs", new=AsyncMock(return_value=[
            {"title": "Already Played", "artist": "Someone"},
        ])),
        patch("cogs.ai.build_genius_search_query", side_effect=lambda t, a: (t, a)),
        patch("cogs.ai.build_recommendation_prompt", return_value="prompt"),
        patch("cogs.ai.parse_suggestions", return_value=[
            {"title": "Rec new1", "artist": "Rec Artist"},
            {"title": "Rec new2", "artist": "Rec Artist"},
        ]),
    )


@pytest.mark.asyncio
async def test_autoqueue_starts_playback_when_voice_idle_despite_stale_flag():
    """The core regression: queue.is_playing is stale-True but audio has stopped.

    This is the exact live state after the last track ends: _on_track_end left
    is_playing=True, the voice client reports not-playing. Auto-queue MUST start
    playback of the first newly-queued track.
    """
    cog, guild, queue, music_cog = _make_env(queue_is_playing=True, vc_is_playing=False)

    with _patches()[0], _patches()[1], _patches()[2], _patches()[3], _patches()[4]:
        await cog.try_auto_queue(guild)

    # Two recommendations were appended after the one existing track.
    assert len(queue.tracks) == 3, "auto-queue should have appended 2 tracks"
    # Playback MUST have started on the first newly-queued track (index 1).
    music_cog._play_track.assert_awaited_once()
    played_track = music_cog._play_track.await_args.args[1]
    assert played_track is queue.tracks[1]
    assert queue.current_index == 1


@pytest.mark.asyncio
async def test_autoqueue_does_not_double_play_when_audio_already_flowing():
    """Guard the other direction: if audio IS actually playing, do not interrupt."""
    cog, guild, queue, music_cog = _make_env(queue_is_playing=True, vc_is_playing=True)

    with _patches()[0], _patches()[1], _patches()[2], _patches()[3], _patches()[4]:
        await cog.try_auto_queue(guild)

    # Tracks still queued, but no playback start (something is already playing).
    assert len(queue.tracks) == 3
    music_cog._play_track.assert_not_awaited()
