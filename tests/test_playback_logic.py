"""Exhaustive pure-unit tests for logic/playback.py (TEST-01 / D-03 / D-05).

No mocks, no clocks, no RNG — all inputs are plain Python primitives.
If a test needs a mock the cut-line in logic/playback.py is wrong (D-06).

Named scar regression tests (D-05):
  - test_finished_song_returns_stop_and_clear   (scar #1: replay, DEPLOY-06 / IN-02)
  - test_autoqueue_selected_on_voice_client_ground_truth  (scar #2: silent auto-queue)
  - test_stale_index_clamped_into_range         (scar #4: restore clamp, CR-03)
"""

import pytest
import config
from logic.playback import (
    TrackEndAction,
    clamp_restore_index,
    decide_on_track_end,
    exceeds_queue_cap,
    should_smart_rejoin,
    should_start_playback,
)


# ---------------------------------------------------------------------------
# TestDecideOnTrackEnd
# ---------------------------------------------------------------------------


class TestDecideOnTrackEnd:
    """Full branch coverage for decide_on_track_end (D-03)."""

    def test_not_playing_returns_noop(self):
        """Manual stop: is_playing=False → NOOP, no matter what else is true."""
        result = decide_on_track_end(
            is_playing=False,
            has_next=True,
            connected=True,
            humans_present=True,
            aicog_loaded=True,
        )
        assert result == TrackEndAction.NOOP

    def test_has_next_returns_play(self):
        """A next track exists → PLAY."""
        result = decide_on_track_end(
            is_playing=True,
            has_next=True,
            connected=True,
            humans_present=True,
            aicog_loaded=True,
        )
        assert result == TrackEndAction.PLAY

    def test_has_next_overrides_exhaustion(self):
        """Even with no humans/aicog, has_next → PLAY (humans/aicog only matter on exhaustion)."""
        result = decide_on_track_end(
            is_playing=True,
            has_next=True,
            connected=False,
            humans_present=False,
            aicog_loaded=False,
        )
        assert result == TrackEndAction.PLAY

    def test_exhausted_with_humans_and_aicog_returns_autoqueue(self):
        """Exhausted + connected + humans + AICog → AUTOQUEUE."""
        result = decide_on_track_end(
            is_playing=True,
            has_next=False,
            connected=True,
            humans_present=True,
            aicog_loaded=True,
        )
        assert result == TrackEndAction.AUTOQUEUE

    def test_exhausted_no_aicog_returns_stop_and_clear(self):
        """Exhausted + humans present but AICog not loaded → STOP_AND_CLEAR."""
        result = decide_on_track_end(
            is_playing=True,
            has_next=False,
            connected=True,
            humans_present=True,
            aicog_loaded=False,
        )
        assert result == TrackEndAction.STOP_AND_CLEAR

    def test_exhausted_no_humans_returns_stop_and_clear(self):
        """Exhausted + AICog loaded but no humans in voice → STOP_AND_CLEAR."""
        result = decide_on_track_end(
            is_playing=True,
            has_next=False,
            connected=True,
            humans_present=False,
            aicog_loaded=True,
        )
        assert result == TrackEndAction.STOP_AND_CLEAR

    def test_exhausted_not_connected_returns_stop_and_clear(self):
        """Exhausted + not connected to a voice channel → STOP_AND_CLEAR."""
        result = decide_on_track_end(
            is_playing=True,
            has_next=False,
            connected=False,
            humans_present=True,
            aicog_loaded=True,
        )
        assert result == TrackEndAction.STOP_AND_CLEAR

    def test_exhausted_all_false_returns_stop_and_clear(self):
        """Exhausted + no connection, no humans, no AICog → STOP_AND_CLEAR."""
        result = decide_on_track_end(
            is_playing=True,
            has_next=False,
            connected=False,
            humans_present=False,
            aicog_loaded=False,
        )
        assert result == TrackEndAction.STOP_AND_CLEAR

    # ---- Named scar test #1 (D-05) ----------------------------------------

    def test_finished_song_returns_stop_and_clear(self):
        """Scar #1 — finished-song replay (DEPLOY-06 / IN-02).

        Natural queue exhaustion (is_playing=True, has_next=False) with no humans
        must return STOP_AND_CLEAR so the glue calls clear_persisted() and the
        just-finished track is NOT parked on current_index to be replayed on the
        next restart.
        """
        result = decide_on_track_end(
            is_playing=True,
            has_next=False,
            connected=True,
            humans_present=False,  # no humans → no auto-queue → must stop and clear
            aicog_loaded=True,
        )
        assert result == TrackEndAction.STOP_AND_CLEAR


# ---------------------------------------------------------------------------
# TestShouldStartPlayback
# ---------------------------------------------------------------------------


class TestShouldStartPlayback:
    """Full branch coverage for should_start_playback (scar #2, D-03)."""

    def test_voice_idle_with_track_returns_true(self):
        """Connected, track queued, voice not playing, not paused → start playback."""
        result = should_start_playback(
            connected=True,
            voice_is_playing=False,
            voice_is_paused=False,
            has_track=True,
        )
        assert result is True

    def test_voice_playing_returns_false(self):
        """Audio already flowing from voice client → do not start again."""
        result = should_start_playback(
            connected=True,
            voice_is_playing=True,
            voice_is_paused=False,
            has_track=True,
        )
        assert result is False

    def test_voice_paused_returns_false(self):
        """Voice client paused (user pressed pause) → do not interrupt."""
        result = should_start_playback(
            connected=True,
            voice_is_playing=False,
            voice_is_paused=True,
            has_track=True,
        )
        assert result is False

    def test_not_connected_returns_false(self):
        """No voice client → cannot start playback."""
        result = should_start_playback(
            connected=False,
            voice_is_playing=False,
            voice_is_paused=False,
            has_track=True,
        )
        assert result is False

    def test_no_track_returns_false(self):
        """Nothing in the queue to play → do not call _play_track(None)."""
        result = should_start_playback(
            connected=True,
            voice_is_playing=False,
            voice_is_paused=False,
            has_track=False,
        )
        assert result is False

    # ---- Named scar test #2 (D-05) ----------------------------------------

    def test_autoqueue_selected_on_voice_client_ground_truth(self):
        """Scar #2 — silent auto-queue (v1.1 live-UAT).

        After natural queue exhaustion, _on_track_end leaves queue.is_playing=True
        and defers to try_auto_queue ("auto-queue will handle it").  The OLD guard
        `not queue.is_playing` never fired because is_playing was still True.

        should_start_playback intentionally does NOT accept a `queue_is_playing`
        parameter — it keys ONLY on the live voice-client state (voice_is_playing /
        voice_is_paused), which correctly reports False after a track ends.

        This test verifies the gate returns True (start playback) when the voice
        client is idle — regardless of what a stale queue flag might say.
        """
        # Simulate the exact state after natural exhaustion:
        # - voice client is connected but NOT playing or paused (track just ended)
        # - queue.is_playing is stale-True (intentionally NOT an input here)
        # - auto-queue just added new tracks → has_track=True
        result = should_start_playback(
            connected=True,
            voice_is_playing=False,   # ground truth: audio not flowing
            voice_is_paused=False,    # not paused
            has_track=True,           # freshly queued track waiting
        )
        assert result is True


# ---------------------------------------------------------------------------
# TestClampRestoreIndex
# ---------------------------------------------------------------------------


class TestClampRestoreIndex:
    """Full branch + boundary coverage for clamp_restore_index (scar #4, D-03)."""

    def test_in_range_index_passes_through(self):
        """Valid in-range index is returned unchanged."""
        assert clamp_restore_index(2, 5) == 2

    def test_zero_index_passthrough(self):
        """Index 0 is always valid when there are tracks."""
        assert clamp_restore_index(0, 3) == 0

    def test_exact_last_index_passthrough(self):
        """Index == track_count - 1 is the last valid position."""
        assert clamp_restore_index(4, 5) == 4

    def test_above_max_clamped_to_last(self):
        """An index beyond the end is clamped to track_count - 1."""
        assert clamp_restore_index(99, 5) == 4

    def test_negative_index_clamped_to_zero(self):
        """A negative index is clamped to 0."""
        assert clamp_restore_index(-1, 5) == 0

    def test_very_negative_clamped_to_zero(self):
        """A large negative index is still clamped to 0."""
        assert clamp_restore_index(-1000, 10) == 0

    def test_empty_queue_returns_zero(self):
        """An empty queue (track_count=0) always returns 0."""
        assert clamp_restore_index(0, 0) == 0

    def test_empty_queue_with_nonzero_index_returns_zero(self):
        """Out-of-range index on empty queue also returns 0."""
        assert clamp_restore_index(5, 0) == 0

    # ---- Named scar test #4 (D-05) ----------------------------------------

    def test_stale_index_clamped_into_range(self):
        """Scar #4 — restore index clamp (CR-03).

        A stale, non-int, negative, or out-of-range current_index must be clamped
        into a valid range before being set on the queue.  An unclamped index could
        reach get_current() → _play_track(None) and crash playback.
        """
        # non-int
        assert clamp_restore_index("bad", 5) == 0
        assert clamp_restore_index(None, 5) == 0
        assert clamp_restore_index(3.7, 5) == 0
        # negative
        assert clamp_restore_index(-1, 5) == 0
        # above-max
        assert clamp_restore_index(100, 5) == 4
        # empty queue
        assert clamp_restore_index(0, 0) == 0


# ---------------------------------------------------------------------------
# TestShouldSmartRejoin
# ---------------------------------------------------------------------------


class TestShouldSmartRejoin:
    """Full branch coverage for should_smart_rejoin (D-03)."""

    def test_all_conditions_met_returns_true(self):
        """has_current + not already connected + humans present → rejoin."""
        result = should_smart_rejoin(
            has_current=True,
            already_connected=False,
            humans_present=True,
        )
        assert result is True

    def test_already_connected_returns_false(self):
        """Bot already in voice → skip rejoin."""
        result = should_smart_rejoin(
            has_current=True,
            already_connected=True,
            humans_present=True,
        )
        assert result is False

    def test_no_humans_returns_false(self):
        """No humans in the target channel → do not join empty channel."""
        result = should_smart_rejoin(
            has_current=True,
            already_connected=False,
            humans_present=False,
        )
        assert result is False

    def test_no_current_track_returns_false(self):
        """Nothing to play (queue empty or exhausted) → do not rejoin."""
        result = should_smart_rejoin(
            has_current=False,
            already_connected=False,
            humans_present=True,
        )
        assert result is False

    def test_all_conditions_false_returns_false(self):
        """No conditions met → False."""
        result = should_smart_rejoin(
            has_current=False,
            already_connected=True,
            humans_present=False,
        )
        assert result is False


# ---------------------------------------------------------------------------
# TestExceedsQueueCap
# ---------------------------------------------------------------------------


class TestExceedsQueueCap:
    """Full branch + boundary coverage for exceeds_queue_cap (D-03)."""

    def test_count_exceeds_max_returns_true(self):
        """track_count > max_size → needs truncation."""
        assert exceeds_queue_cap(501, 500) is True

    def test_count_equals_max_returns_false(self):
        """Exactly at cap is valid — not exceeded."""
        assert exceeds_queue_cap(500, 500) is False

    def test_count_below_max_returns_false(self):
        """Well under cap → no truncation needed."""
        assert exceeds_queue_cap(3, 500) is False

    def test_empty_does_not_exceed(self):
        """Zero tracks never exceeds cap."""
        assert exceeds_queue_cap(0, config.MAX_QUEUE_SIZE_PER_GUILD) is False

    def test_one_over_exceeds(self):
        """Exactly one over the configured cap → truncation required."""
        assert exceeds_queue_cap(config.MAX_QUEUE_SIZE_PER_GUILD + 1, config.MAX_QUEUE_SIZE_PER_GUILD) is True
