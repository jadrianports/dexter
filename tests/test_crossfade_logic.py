"""Exhaustive pure-unit tests for logic/crossfade.py (Phase 27 / DJ-03 / D-14).

No mocks, no clocks, no RNG — all inputs are plain Python primitives. If a
test needs a mock the cut-line in logic/crossfade.py is wrong.

Two guards exist because a plausible-looking implementation would pass
without them:
  - D-11b: loop QUEUE must still fade — a naive "loop_single" check that
    also swallowed loop QUEUE would pass every other test here but silently
    break the queue-loop crossfade case. test_loop_single_hard_cuts asserts
    BOTH halves of D-11b, not just the SINGLE case.
  - cut_frame's metadata-mismatch floor: YouTube's reported duration can
    disagree with the real file (RESEARCH landmine #5). A cut_frame that
    forgot to floor at 0 would silently produce a negative frame index that
    becomes an -ss seek past EOF downstream. test_cut_frame asserts the
    floor explicitly.
"""

import config
from logic.crossfade import FadeVerdict, cut_frame, decide_crossfade

# ---------------------------------------------------------------------------
# _eligible: baseline fully-FADE-eligible kwargs
# ---------------------------------------------------------------------------


def _eligible(**overrides):
    """Return a fully-FADE-eligible decide_crossfade() kwargs dict.

    Each test overrides exactly the one field under test, keeping the
    ladder tests readable and making precedence testing mechanical.
    """
    base = dict(
        enabled=True,
        has_next=True,
        loop_single=False,
        filter_active=False,
        outgoing_cached=True,
        incoming_cached=True,
        outgoing_duration=200,
        incoming_duration=200,
        seek_offset=0,
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# test_fade_when_eligible
# ---------------------------------------------------------------------------


class TestFadeWhenEligible:
    """Behavior Map row 1: the all-clear baseline."""

    def test_fade_when_eligible(self):
        """Every condition allowing → FADE."""
        result = decide_crossfade(**_eligible())
        assert result == FadeVerdict.FADE


# ---------------------------------------------------------------------------
# test_toggle_off_never_fades
# ---------------------------------------------------------------------------


class TestToggleOffNeverFades:
    """Behavior Map row 2: D-08b off-by-default."""

    def test_toggle_off_never_fades(self):
        """enabled=False → NO_TOGGLE regardless of every other arg."""
        result = decide_crossfade(**_eligible(enabled=False))
        assert result == FadeVerdict.NO_TOGGLE

    def test_toggle_off_wins_even_with_every_other_rung_also_firing(self):
        """enabled=False still wins even when every later rung would also fire."""
        result = decide_crossfade(
            **_eligible(
                enabled=False,
                has_next=False,
                loop_single=True,
                filter_active=True,
                outgoing_cached=False,
                incoming_cached=False,
                seek_offset=5,
                outgoing_duration=1,
                incoming_duration=1,
            )
        )
        assert result == FadeVerdict.NO_TOGGLE


# ---------------------------------------------------------------------------
# test_loop_single_hard_cuts
# ---------------------------------------------------------------------------


class TestLoopSingleHardCuts:
    """Behavior Map row 3: D-11b loop-SINGLE exclusion (both halves)."""

    def test_loop_single_hard_cuts(self):
        """loop_single=True → LOOP_SINGLE."""
        result = decide_crossfade(**_eligible(loop_single=True))
        assert result == FadeVerdict.LOOP_SINGLE

    def test_loop_queue_still_fades(self):
        """loop_single=False with everything else eligible → still FADE (D-11b
        positive half: loop QUEUE is NOT excluded)."""
        result = decide_crossfade(**_eligible(loop_single=False))
        assert result == FadeVerdict.FADE


# ---------------------------------------------------------------------------
# test_filter_hard_cuts
# ---------------------------------------------------------------------------


class TestFilterHardCuts:
    """Behavior Map row 4: D-10b active-filter exclusion."""

    def test_filter_hard_cuts(self):
        """filter_active=True → FILTER_ACTIVE."""
        result = decide_crossfade(**_eligible(filter_active=True))
        assert result == FadeVerdict.FILTER_ACTIVE


# ---------------------------------------------------------------------------
# test_uncached_hard_cuts
# ---------------------------------------------------------------------------


class TestUncachedHardCuts:
    """Behavior Map row 5: D-03 narrow-go cache exclusion, parametrized."""

    def test_uncached_hard_cuts_outgoing(self):
        """outgoing_cached=False → NOT_CACHED."""
        result = decide_crossfade(**_eligible(outgoing_cached=False))
        assert result == FadeVerdict.NOT_CACHED

    def test_uncached_hard_cuts_incoming(self):
        """incoming_cached=False → NOT_CACHED."""
        result = decide_crossfade(**_eligible(incoming_cached=False))
        assert result == FadeVerdict.NOT_CACHED

    def test_uncached_hard_cuts_both(self):
        """Both outgoing and incoming uncached → NOT_CACHED."""
        result = decide_crossfade(**_eligible(outgoing_cached=False, incoming_cached=False))
        assert result == FadeVerdict.NOT_CACHED


# ---------------------------------------------------------------------------
# test_remaining_ladder_rungs
# ---------------------------------------------------------------------------


class TestRemainingLadderRungs:
    """Behavior Map row 6: no-next-track, seeked, and the duration floor."""

    def test_no_next_track(self):
        """has_next=False → NO_NEXT_TRACK."""
        result = decide_crossfade(**_eligible(has_next=False))
        assert result == FadeVerdict.NO_NEXT_TRACK

    def test_seeked(self):
        """seek_offset=5 → SEEKED."""
        result = decide_crossfade(**_eligible(seek_offset=5))
        assert result == FadeVerdict.SEEKED

    def test_too_short_outgoing_under_floor(self):
        """A short outgoing track under min_track_seconds → TOO_SHORT."""
        result = decide_crossfade(**_eligible(outgoing_duration=5))
        assert result == FadeVerdict.TOO_SHORT

    def test_too_short_incoming_under_floor(self):
        """A short incoming track under min_track_seconds → TOO_SHORT."""
        result = decide_crossfade(**_eligible(incoming_duration=5))
        assert result == FadeVerdict.TOO_SHORT

    def test_too_short_outgoing_at_exact_double_fade_boundary(self):
        """outgoing_duration == fade_seconds * 2 → TOO_SHORT (the <= boundary
        is load-bearing — assert it explicitly)."""
        result = decide_crossfade(**_eligible(outgoing_duration=config.CROSSFADE_SECONDS * 2))
        assert result == FadeVerdict.TOO_SHORT

    def test_not_too_short_outgoing_one_second_above_double_fade_boundary(self):
        """outgoing_duration == fade_seconds * 2 + 1 clears the double-fade
        floor → FADE (min_track_seconds isolated via override so only the
        double-fade boundary is under test)."""
        result = decide_crossfade(
            **_eligible(
                outgoing_duration=config.CROSSFADE_SECONDS * 2 + 1,
                min_track_seconds=0,
            )
        )
        assert result == FadeVerdict.FADE


# ---------------------------------------------------------------------------
# test_ladder_precedence
# ---------------------------------------------------------------------------


class TestLadderPrecedence:
    """Behavior Map row 7: an earlier rung wins even when every LATER rung
    would also fire. Walks the full order NO_TOGGLE → NO_NEXT_TRACK →
    LOOP_SINGLE → FILTER_ACTIVE → NOT_CACHED → SEEKED → TOO_SHORT.

    Each test sets ONLY the rungs strictly after the one under test to their
    firing values — an earlier rung's firing kwargs must never be included,
    or the test would trivially prove the wrong thing.
    """

    # Kwargs that make every rung AFTER "loop_single" fire too.
    _AFTER_LOOP_SINGLE = dict(
        filter_active=True,
        outgoing_cached=False,
        incoming_cached=False,
        seek_offset=5,
        outgoing_duration=1,
        incoming_duration=1,
    )
    # Kwargs that make every rung AFTER "filter_active" fire too.
    _AFTER_FILTER_ACTIVE = dict(
        outgoing_cached=False,
        incoming_cached=False,
        seek_offset=5,
        outgoing_duration=1,
        incoming_duration=1,
    )
    # Kwargs that make every rung AFTER "not_cached" fire too.
    _AFTER_NOT_CACHED = dict(
        seek_offset=5,
        outgoing_duration=1,
        incoming_duration=1,
    )

    def test_ladder_precedence_no_toggle_wins_over_everything(self):
        result = decide_crossfade(
            **_eligible(
                enabled=False,
                has_next=False,
                loop_single=True,
                **self._AFTER_LOOP_SINGLE,
            )
        )
        assert result == FadeVerdict.NO_TOGGLE

    def test_ladder_precedence_no_next_track_wins_over_later_rungs(self):
        result = decide_crossfade(
            **_eligible(
                has_next=False,
                loop_single=True,
                **self._AFTER_LOOP_SINGLE,
            )
        )
        assert result == FadeVerdict.NO_NEXT_TRACK

    def test_ladder_precedence_loop_single_wins_over_later_rungs(self):
        result = decide_crossfade(**_eligible(loop_single=True, **self._AFTER_LOOP_SINGLE))
        assert result == FadeVerdict.LOOP_SINGLE

    def test_ladder_precedence_filter_active_wins_over_later_rungs(self):
        result = decide_crossfade(**_eligible(filter_active=True, **self._AFTER_FILTER_ACTIVE))
        assert result == FadeVerdict.FILTER_ACTIVE

    def test_ladder_precedence_not_cached_wins_over_later_rungs(self):
        result = decide_crossfade(
            **_eligible(
                outgoing_cached=False,
                incoming_cached=False,
                **self._AFTER_NOT_CACHED,
            )
        )
        assert result == FadeVerdict.NOT_CACHED

    def test_ladder_precedence_seeked_wins_over_too_short(self):
        result = decide_crossfade(**_eligible(seek_offset=5, outgoing_duration=1, incoming_duration=1))
        assert result == FadeVerdict.SEEKED

    def test_ladder_precedence_too_short_is_last_rung(self):
        """With every earlier rung clear, TOO_SHORT still fires on the floor."""
        result = decide_crossfade(**_eligible(outgoing_duration=1, incoming_duration=1))
        assert result == FadeVerdict.TOO_SHORT


# ---------------------------------------------------------------------------
# test_cut_frame
# ---------------------------------------------------------------------------


class TestCutFrame:
    """Behavior Map row 8: cut_frame arithmetic + the metadata-mismatch guard."""

    def test_cut_frame(self):
        """(200s, 4s) → 9800 (196s at 20ms frames)."""
        result = cut_frame(outgoing_duration=200, fade_seconds=4)
        assert result == 9800

    def test_cut_frame_floors_at_zero_when_duration_shorter_than_fade(self):
        """A duration shorter than fade_seconds must never return negative
        (RESEARCH landmine #5: YouTube metadata != the file's real duration,
        so a negative cut would become an -ss past EOF)."""
        result = cut_frame(outgoing_duration=2, fade_seconds=4)
        assert result == 0
        assert result >= 0
