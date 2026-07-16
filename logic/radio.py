"""Pure radio refill-gate decision seam (Phase 26 / DJ-01 / D-19).

All functions in this module are deterministic and side-effect-free: no ``discord``,
no ``asyncio``, no ``random``, no ``datetime``, no database access.

Any nondeterministic or I/O-derived value (whether radio is armed, whether humans
are present in voice, how many tracks remain in the queue, the session's played-set)
is computed by the calling cog glue and passed in as a primitive — following the
established seam pattern from ``logic/proactive.py`` (Phase 16) and ``logic/vision.py``
(Phase 17).

This module implements only the DECISION of whether/what to gate. The caller still
must:
    - dispatch the actual ``try_auto_queue(guild, radio=True)`` call when
      ``should_refill_radio`` returns True (this module does not touch the queue,
      Gemini, or YouTube),
    - resolve each candidate against YouTube and re-check ``is_already_played``
      AFTER resolution (before the video_id is known, only the prompt hint can
      steer Gemini away from a repeat — D-03),
    - check ``has_room_for_refill`` BEFORE requesting suggestions, not after.

Locked by tests/test_radio_logic.py (mock-free boundary coverage).
"""

from __future__ import annotations

import config

# ---------------------------------------------------------------------------
# should_refill_radio
# ---------------------------------------------------------------------------


def should_refill_radio(
    *,
    armed: bool,
    humans_present: bool,
    upcoming_count: int,
    lookahead_depth: int = config.RADIO_LOOKAHEAD_DEPTH,
) -> bool:
    """Decide whether an armed radio session should request a refill batch.

    Cheapest-gate-first ordering, mirroring ``logic/proactive.py`` /
    ``logic/vision.py`` (Phase 16/17 convention):

    1. Armed gate: ``not armed`` -> False immediately (the most common case —
       SC-2/D-07: a disarmed radio never refills, full stop).
    2. Humans-present gate: ``not humans_present`` -> False (never burn the
       shared 15 RPM Gemini budget refilling for an empty voice channel —
       T-26-02; mirrors the ``humans_present`` gate
       ``logic.playback.decide_on_track_end`` already applies to AUTOQUEUE).
    3. Runway gate: ``upcoming_count > lookahead_depth`` -> False (still enough
       tracks queued — Phase 6's prefetch only needs one next track to exist,
       so there is no dead-air risk yet).
    4. All gates passed -> True: refill while tracks remain, never on empty
       (D-10). The caller still must dispatch the actual
       ``try_auto_queue(guild, radio=True)`` call — this function only decides.

    Args:
        armed:           Whether radio mode is currently armed for this guild
                          (``MusicQueue.radio_armed`` in glue).
        humans_present:  Whether any non-bot member is in the voice channel.
                          Compute the same way ``_on_track_end`` already does
                          for ``decide_on_track_end`` (glue, free to reuse).
        upcoming_count:  Number of tracks remaining after the current one
                          (``len(queue.upcoming())`` in glue).
        lookahead_depth: Runway threshold — refill triggers once
                          ``upcoming_count`` drops to this value or below
                          (default ``config.RADIO_LOOKAHEAD_DEPTH`` = 2).

    Returns:
        True only if armed, humans are present, and remaining runway is at or
        below ``lookahead_depth``. False (including the empty-queue case,
        ``upcoming_count=0``) is covered by gate 3 — an armed radio with zero
        upcoming tracks still refills, since 0 <= lookahead_depth.
    """
    # Gate 1: armed (cheapest check — SC-2/D-07: disarmed never refills)
    if not armed:
        return False

    # Gate 2: humans present (never burn budget refilling an empty room — T-26-02)
    if not humans_present:
        return False

    # Gate 3: runway — refill while tracks remain, trigger at/below the lookahead depth
    if upcoming_count > lookahead_depth:
        return False

    return True


# ---------------------------------------------------------------------------
# is_already_played
# ---------------------------------------------------------------------------


def is_already_played(*, video_id: str, played_ids: frozenset[str]) -> bool:
    """Return True if ``video_id`` was already queued this radio session.

    This is D-03's INDEPENDENT hard post-filter, applied AFTER YouTube
    resolution (once a real ``video_id`` exists) — mirroring
    ``logic.autoqueue.is_recently_skipped_artist``'s role as a second gate
    behind ``validate_youtube_match`` (Phase 14 D-02). The prompt's
    already-played HINT (``personality.prompts.build_recommendation_prompt``'s
    ``already_played=`` kwarg) is advisory only — Gemini can still suggest a
    repeat; this membership check is what actually enforces no-repeats.

    Args:
        video_id:   The resolved YouTube video_id of a refill candidate.
        played_ids: The session's played video_ids
                    (``frozenset(queue.radio_played.keys())`` in glue).

    Returns:
        True if ``video_id`` is a member of ``played_ids``, else False.
        An empty ``played_ids`` (a fresh session) always returns False.
    """
    return video_id in played_ids


# ---------------------------------------------------------------------------
# has_room_for_refill
# ---------------------------------------------------------------------------


def has_room_for_refill(
    *,
    queue_size: int,
    batch_size: int = config.AUTO_QUEUE_SONGS_PER_ROUND,
    cap: int = config.MAX_QUEUE_SIZE_PER_GUILD,
) -> bool:
    """Return True if adding a refill batch would not exceed the queue cap.

    An indefinitely-refilling radio must not fight ``MAX_QUEUE_SIZE_PER_GUILD``:
    ``MusicQueue.add`` raises ``QueueFullError`` once the cap is hit, and a
    refill running inside ``make_task`` would surface that as an unhandled
    exception to the error channel. Radio glue must check this BEFORE
    requesting suggestions from Gemini, not after — there is no point paying
    for a recommendation the queue can't hold.

    Args:
        queue_size: Current number of tracks in the queue
                    (``len(queue)`` in glue).
        batch_size: Number of tracks a refill would add (default
                    ``config.AUTO_QUEUE_SONGS_PER_ROUND`` — no radio-specific
                    batch-size knob; radio reuses the existing auto-queue
                    round size).
        cap:        The hard queue-size ceiling (default
                    ``config.MAX_QUEUE_SIZE_PER_GUILD``).

    Returns:
        True if ``queue_size + batch_size <= cap``, else False.
    """
    return queue_size + batch_size <= cap
