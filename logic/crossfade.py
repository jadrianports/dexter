"""Pure crossfade eligibility decision seam (Phase 27 / DJ-03 / D-14).

All functions in this module are deterministic and side-effect-free: no ``discord``,
no ``asyncio``, no ``random``, no ``datetime``, no database access, no I/O.

Any nondeterministic or engine-derived value (whether crossfade is toggled on, whether
a next track exists, loop mode, active filter, cache state, durations, seek offset) is
computed by the calling cog glue and passed in as a primitive — following the
established seam pattern from ``logic/radio.py`` (Phase 26) and ``logic/skip_vote.py``
(Phase 26).

This module implements only the DECISION of whether a transition should fade. The
caller still must:
    - dispatch on the returned ``FadeVerdict`` member and never re-derive this ladder
      itself (Phase 10 D-02 rule),
    - on ``FADE``, wrap the outgoing source in a ``TruncatingSource`` cut at the frame
      returned by ``cut_frame()`` and build the ``CrossfadeSource`` for the incoming
      track (``services/audio.py`` — out of scope for this module),
    - on any other verdict, log ``crossfade: hard cut (<verdict>)`` and pass the source
      through untouched — the room hears today's behaviour, unchanged (D-10b: log only,
      never a visible/audible signal).

Locked by tests/test_crossfade_logic.py (mock-free boundary coverage).
"""

from __future__ import annotations

import enum

import config

# ---------------------------------------------------------------------------
# FadeVerdict
# ---------------------------------------------------------------------------


class FadeVerdict(enum.Enum):
    """What the crossfade glue should do after consulting ``decide_crossfade``.

    Value strings are load-bearing — they are what the D-10b
    ``crossfade: hard cut (%s)`` log line prints, so they must stay stable.
    """

    FADE = "fade"
    """Every condition allows it — wrap the outgoing source in a TruncatingSource
    cut at ``cut_frame(...)`` and build a CrossfadeSource for the handoff."""

    NO_TOGGLE = "no_toggle"
    """Crossfade is disabled (D-08b: off by default) — pass the source through
    untouched, preserving the opus fast path."""

    NO_NEXT_TRACK = "no_next_track"
    """Nothing to fade into — pass the source through untouched."""

    LOOP_SINGLE = "loop_single"
    """Loop mode is SINGLE (D-11b) — self-overlap is phasing, not a blend.
    Loop QUEUE is NOT this verdict; it still fades normally."""

    FILTER_ACTIVE = "filter_active"
    """An FFmpeg -af filter chain is already active — composing it with a
    crossfade mix is out of scope; pass the source through untouched."""

    NOT_CACHED = "not_cached"
    """Either the outgoing or incoming track is not a cached local file (stream
    fallback / cold prefetch) — the tail needs a seekable local file, so the
    caller must pass the source through untouched."""

    SEEKED = "seeked"
    """A nonzero seek/resume offset is active — the cut-frame arithmetic assumes
    playback started at 0, so the caller must pass the source through untouched."""

    TOO_SHORT = "too_short"
    """Either track is under the minimum-track floor, or the outgoing track's
    remaining runway is too short to leave a meaningful main body after the
    fade — pass the source through untouched."""


# ---------------------------------------------------------------------------
# decide_crossfade
# ---------------------------------------------------------------------------


def decide_crossfade(
    *,
    enabled: bool,
    has_next: bool,
    loop_single: bool,
    filter_active: bool,
    outgoing_cached: bool,
    incoming_cached: bool,
    outgoing_duration: int,
    incoming_duration: int,
    seek_offset: int,
    fade_seconds: int = config.CROSSFADE_SECONDS,
    min_track_seconds: int = config.CROSSFADE_MIN_TRACK_SECONDS,
) -> FadeVerdict:
    """Decide whether a track-to-track transition should fade, per D-10b/D-11b.

    Cheapest-gate-first ordering, mirroring ``logic/radio.py`` /
    ``logic/skip_vote.py`` (Phase 26 convention). This IS the fallback ladder —
    an earlier rung wins even when a later rung would also fire, and the order
    below is exactly RESEARCH's "Narrow-go exclusions" table row order.

    1. Toggle gate (D-08b): ``not enabled`` -> ``NO_TOGGLE`` regardless of
       every other arg. Off by default preserves the opus fast path.
    2. Next-track gate: ``not has_next`` -> ``NO_NEXT_TRACK``. Nothing to
       fade into.
    3. Loop-SINGLE gate (D-11b): ``loop_single`` -> ``LOOP_SINGLE``.
       Self-overlap is phasing, not a blend. Loop QUEUE (``loop_single=False``
       with loop-queue semantics upstream) is NOT gated here — it still fades.
    4. Filter gate (D-10b): ``filter_active`` -> ``FILTER_ACTIVE``. Already
       transcoding an -af chain; composing the two is out of scope.
    5. Cache gate (D-03 narrow-go): ``not outgoing_cached or not
       incoming_cached`` -> ``NOT_CACHED``. The tail needs a seekable local
       file.
    6. Seek gate: ``seek_offset > 0`` -> ``SEEKED``. Cut arithmetic assumes
       playback started at 0.
    7. Duration floor: either track's duration under ``min_track_seconds``,
       or ``outgoing_duration <= fade_seconds * 2`` (fading a short clip is
       mostly fade) -> ``TOO_SHORT``.
    8. All gates passed -> ``FADE``.

    Args:
        enabled:           Whether crossfade is toggled on for this playback
                            (glue-resolved; there is no per-guild config
                            surface — D-21).
        has_next:           Whether a next track exists to fade into.
        loop_single:        Whether loop mode is SINGLE for the current track
                             (``queue.loop_mode == LoopMode.SINGLE`` in glue).
        filter_active:      Whether an FFmpeg -af filter chain is active
                             (``queue.active_filter not in (None, "off")`` in
                             glue).
        outgoing_cached:    Whether the outgoing track is a cached local file.
        incoming_cached:    Whether the incoming track is a cached local file.
        outgoing_duration:  The outgoing track's duration in seconds (from
                             YouTube metadata — attacker-influenceable, see
                             threat model; used only for a floor comparison).
        incoming_duration:  The incoming track's duration in seconds.
        seek_offset:        The nonzero-if-seeked/resumed offset in seconds
                             for the outgoing track's current playback
                             position.
        fade_seconds:       The configured fade length (default
                             ``config.CROSSFADE_SECONDS``).
        min_track_seconds:  The configured minimum-track floor (default
                             ``config.CROSSFADE_MIN_TRACK_SECONDS``).

    Returns:
        The ``FadeVerdict`` member naming the outcome. Glue dispatches on
        this and never re-derives the ladder (Phase 10 D-02 rule).
    """
    # Rung 1: toggle (D-08b) — cheapest check, off by default.
    if not enabled:
        return FadeVerdict.NO_TOGGLE

    # Rung 2: next track must exist.
    if not has_next:
        return FadeVerdict.NO_NEXT_TRACK

    # Rung 3: loop SINGLE excluded (D-11b) — loop QUEUE still fades.
    if loop_single:
        return FadeVerdict.LOOP_SINGLE

    # Rung 4: an active -af filter chain excludes crossfade (D-10b).
    if filter_active:
        return FadeVerdict.FILTER_ACTIVE

    # Rung 5: both tracks must be cached local files (D-03 narrow-go).
    if not outgoing_cached or not incoming_cached:
        return FadeVerdict.NOT_CACHED

    # Rung 6: a nonzero seek/resume offset breaks the cut-frame arithmetic.
    if seek_offset > 0:
        return FadeVerdict.SEEKED

    # Rung 7: duration floor — either track too short, or the outgoing
    # track's remaining runway is mostly fade.
    if (
        outgoing_duration < min_track_seconds
        or incoming_duration < min_track_seconds
        or outgoing_duration <= fade_seconds * 2
    ):
        return FadeVerdict.TOO_SHORT

    # Rung 8: every gate passed.
    return FadeVerdict.FADE


# ---------------------------------------------------------------------------
# cut_frame
# ---------------------------------------------------------------------------


def cut_frame(*, outgoing_duration: int, fade_seconds: int, frame_ms: int = 20) -> int:
    """Return the 20ms-frame index at which the outgoing source must exhaust.

    Glue must never re-derive this arithmetic itself (Phase 10 D-02 rule) —
    always call this for the frame that drives ``TruncatingSource``'s cutoff.

    The result is floored at 0 (T-27-01): ``outgoing_duration`` comes from
    YouTube metadata, which is attacker-influenceable and known to disagree
    with the real file (RESEARCH landmine #5). A duration shorter than
    ``fade_seconds`` must never produce a negative frame index — downstream
    that would become an ``-ss`` seek past EOF.

    Args:
        outgoing_duration: The outgoing track's duration in seconds.
        fade_seconds:       The configured fade length in seconds.
        frame_ms:           The Discord audio frame size in milliseconds
                             (default 20, matching the engine's frame rate).

    Returns:
        The frame index, always >= 0.
    """
    frame = (outgoing_duration - fade_seconds) * 1000 // frame_ms
    return max(frame, 0)
