"""Pure playback decision logic extracted from MusicCog / AICog / restore_queues (TEST-01).

All functions in this module are deterministic and side-effect-free: no Discord imports,
no asyncio, no database calls, no random, no datetime.now(), no time.monotonic().

Any nondeterministic value (voice-client state, clock readings, RNG) is computed by the
calling cog glue and passed in as a primitive — following the established seam pattern
from personality/roasts.py ``is_late_night(hour)`` (D-06).

Decision functions here are the single source of truth for the following live code paths
(D-01/D-02):
  - ``cogs/music.py`` ``_on_track_end``  — advance/loop/auto-queue-vs-stop dispatch
  - ``cogs/ai.py`` ``try_auto_queue``    — playback-start gate (voice-client ground truth)
  - ``services/queue_persistence.py`` ``restore_queues`` — cap-truncate, index clamp,
    smart-rejoin gate

Phase 10 scar regressions covered by tests/test_playback_logic.py (D-05):
  - scar #1  finished-song replay (DEPLOY-06 / IN-02)
  - scar #2  silent auto-queue (v1.1 live-UAT)
  - scar #4  restore index clamp (CR-03)
"""

from __future__ import annotations

import enum

# ---------------------------------------------------------------------------
# Enum: possible outcomes from _on_track_end decision
# ---------------------------------------------------------------------------


class TrackEndAction(enum.Enum):
    """What the ``_on_track_end`` glue should do after consulting ``decide_on_track_end``."""

    NOOP = "noop"
    """Queue was already stopped manually — do nothing."""

    PLAY = "play"
    """A next track exists — start playing it."""

    AUTOQUEUE = "autoqueue"
    """Queue exhausted but humans are present and AICog is loaded — trigger auto-queue.
    The glue must NOT set ``is_playing = False`` on this path; auto-queue will handle it.
    """

    STOP_AND_CLEAR = "stop_and_clear"
    """Queue genuinely exhausted with no auto-queue fallback.
    The glue must set ``is_playing = False`` and call ``clear_persisted()`` so the
    just-finished track is not replayed on the next restart (scar #1 / DEPLOY-06 / IN-02).
    """


# ---------------------------------------------------------------------------
# 1. decide_on_track_end
# ---------------------------------------------------------------------------


def decide_on_track_end(
    *,
    is_playing: bool,
    has_next: bool,
    connected: bool,
    humans_present: bool,
    aicog_loaded: bool,
) -> TrackEndAction:
    """Decide what ``_on_track_end`` should do next.

    Mirrors the branch tree at ``cogs/music.py:732-780`` exactly (D-02 true extraction).

    Args:
        is_playing:     ``queue.is_playing`` at the time the track ended.
                        False means the queue was stopped manually — return NOOP.
        has_next:       True if ``queue.advance()`` returned a track (a next track exists).
        connected:      True if the guild has a voice client with a channel
                        (``voice_client and voice_client.channel``).
        humans_present: True if at least one non-bot member is in the voice channel.
        aicog_loaded:   True if ``bot.cogs.get("AICog")`` is not None.

    Returns:
        A ``TrackEndAction`` the glue dispatches on.
    """
    if not is_playing:
        return TrackEndAction.NOOP

    if has_next:
        return TrackEndAction.PLAY

    # Queue exhausted — try auto-queue before stopping.
    if connected and humans_present and aicog_loaded:
        return TrackEndAction.AUTOQUEUE

    # No auto-queue fallback (not connected, no humans, or no AICog).
    # Glue must tear down the persisted row (scar #1).
    return TrackEndAction.STOP_AND_CLEAR


# ---------------------------------------------------------------------------
# 2. should_start_playback
# ---------------------------------------------------------------------------


def should_start_playback(
    *,
    connected: bool,
    voice_is_playing: bool,
    voice_is_paused: bool,
    has_track: bool,
) -> bool:
    """Return True if auto-queue should start playback after queueing new tracks.

    Scar #2 (silent auto-queue): this gate keys on the live voice-client state
    (``voice_client.is_playing()`` / ``voice_client.is_paused()``), NEVER the
    ``queue.is_playing`` flag.

    On the natural-exhaustion path ``_on_track_end`` leaves ``queue.is_playing = True``
    and defers to auto-queue ("auto-queue will handle it"), so a ``not queue.is_playing``
    guard never fires — the freshly-queued tracks sit silent.  The voice client is the
    only ground truth for "audio is flowing" (CLAUDE.md Phase 6–8 gotcha).

    Args:
        connected:       True if ``voice_client is not None``.
        voice_is_playing: ``voice_client.is_playing()`` result (from the live client).
        voice_is_paused:  ``voice_client.is_paused()`` result (from the live client).
        has_track:       True if ``queue.get_current() is not None``.

    Returns:
        True if the cog glue should call ``_play_track``.
    """
    return connected and has_track and not voice_is_playing and not voice_is_paused


# ---------------------------------------------------------------------------
# 3. clamp_restore_index
# ---------------------------------------------------------------------------


def clamp_restore_index(raw_index, track_count: int) -> int:
    """Clamp a persisted ``current_index`` into a valid range.

    Mirrors ``services/queue_persistence.py:128-135`` exactly (D-02 true extraction,
    scar #4 / CR-03): a stale, non-int, negative, or out-of-range index must not reach
    ``get_current()`` → ``_play_track(None)``.

    Args:
        raw_index:   The raw value from the persisted payload (may be any type).
        track_count: ``len(queue.tracks)`` after restoration.

    Returns:
        A valid ``current_index`` integer in ``[0, track_count - 1]``, or 0 for an
        empty queue.
    """
    if not isinstance(raw_index, int):
        raw_index = 0
    if track_count <= 0:
        return 0
    return max(0, min(raw_index, track_count - 1))


# ---------------------------------------------------------------------------
# 4. should_smart_rejoin
# ---------------------------------------------------------------------------


def should_smart_rejoin(
    *,
    has_current: bool,
    already_connected: bool,
    humans_present: bool,
) -> bool:
    """Return True if restore_queues should attempt a smart rejoin for this guild.

    Mirrors the gate at ``services/queue_persistence.py:144-147`` (D-02).
    The ``vc_id`` presence check, channel resolution, ``connect()`` call, and per-guild
    ``continue`` error-isolation all remain in the glue (CR-01).

    Args:
        has_current:       True if ``queue.get_current() is not None`` (something to play).
        already_connected: True if ``guild.voice_client is not None``.
        humans_present:    True if at least one non-bot member is in the target channel.

    Returns:
        True if the glue should proceed with ``vc_channel.connect()``.
    """
    return has_current and not already_connected and humans_present


# ---------------------------------------------------------------------------
# 5. exceeds_queue_cap
# ---------------------------------------------------------------------------


def exceeds_queue_cap(track_count: int, max_size: int) -> bool:
    """Return True if a restored track list exceeds the per-guild cap.

    Mirrors the truncation check at ``services/queue_persistence.py:120`` (D-02).

    Args:
        track_count: Number of tracks in the restored list.
        max_size:    ``config.MAX_QUEUE_SIZE_PER_GUILD``.

    Returns:
        True if truncation is needed.
    """
    return track_count > max_size
