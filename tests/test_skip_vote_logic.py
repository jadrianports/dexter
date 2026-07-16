"""Exhaustive pure-unit tests for logic/skip_vote.py (DJ-02 / D-19).

No mocks, no clocks, no RNG, no Discord — all inputs are plain Python
primitives. If a test needs a mock the cut-line in logic/skip_vote.py is
wrong (mirrors tests/test_radio_logic.py's / tests/test_playback_logic.py's
discipline).

Task 2 (models/queue.py per-track vote state) adds a MusicQueue-level class
to this same file (`-k reset_on_track_change`) — mock-free since
models/queue.py imports no Discord either.

Test method names deliberately embed their `-k` selector substring
(`majority`, `solo`, `requester_bypass`, `idempotent`, `departed_voter`,
`reset_on_track_change`) literally, since pytest's `-k` is a plain substring
match with no underscore-fuzzing.
"""

import config
from logic.skip_vote import SkipVerdict, decide_skip, required_votes
from models.queue import MusicQueue, Track


def _make_track(video_id: str, requested_by: int = 1) -> Track:
    return Track(
        video_id=video_id,
        title=f"Title {video_id}",
        artist="Some Artist",
        url=f"https://youtube.com/watch?v={video_id}",
        duration_seconds=180,
        requested_by=requested_by,
    )


# ---------------------------------------------------------------------------
# TestRequiredVotesMajority  (-k majority)
# ---------------------------------------------------------------------------


class TestRequiredVotesMajority:
    """D-09c's locked strict-majority table + the config-ratio knob (-k majority)."""

    def test_majority_table_listener_count_1(self):
        assert required_votes(listener_count=1) == 1

    def test_majority_table_listener_count_2(self):
        assert required_votes(listener_count=2) == 2

    def test_majority_table_listener_count_3(self):
        assert required_votes(listener_count=3) == 2

    def test_majority_table_listener_count_4(self):
        assert required_votes(listener_count=4) == 3

    def test_majority_nondefault_ratio_honours_the_knob(self):
        """ratio=0.75 must change the threshold — proves n // 2 + 1 is NOT used."""
        # floor(4 * 0.75) + 1 = 3 + 1 = 4 (unanimity at 4 listeners, ratio 0.75)
        assert required_votes(listener_count=4, majority_ratio=0.75) == 4
        # floor(3 * 0.75) + 1 = 2 + 1 = 3 (clamped to 3, still meaningfully different from ratio=0.5's 2)
        assert required_votes(listener_count=3, majority_ratio=0.75) == 3

    def test_majority_clamp_at_ratio_one_degrades_to_unanimity_not_impossible(self):
        """ratio=1.0 at n=3 clamps to 3, NOT floor(3*1)+1=4 (T-26-08 wedge guard)."""
        assert required_votes(listener_count=3, majority_ratio=1.0) == 3

    def test_majority_never_returns_zero_for_zero_listeners(self):
        assert required_votes(listener_count=0) >= 1

    def test_majority_never_returns_zero_for_negative_listeners(self):
        assert required_votes(listener_count=-1) >= 1

    def test_majority_end_to_end_three_listeners_needs_two_votes(self):
        """3-listener sequence: vote 1 -> VOTE_RECORDED, vote 2 -> SKIP_NOW."""
        listener_ids = frozenset({1, 2, 3})
        verdict1, votes1 = decide_skip(
            voter_id=1,
            is_requester=False,
            listener_ids=listener_ids,
            existing_votes=frozenset(),
        )
        assert verdict1 == SkipVerdict.VOTE_RECORDED
        assert votes1 == frozenset({1})

        verdict2, votes2 = decide_skip(
            voter_id=2,
            is_requester=False,
            listener_ids=listener_ids,
            existing_votes=votes1,
        )
        assert verdict2 == SkipVerdict.SKIP_NOW
        assert votes2 == frozenset({1, 2})

    def test_majority_end_to_end_four_listeners_needs_three_votes(self):
        listener_ids = frozenset({1, 2, 3, 4})
        votes = frozenset()
        verdicts = []
        for voter in (1, 2, 3):
            verdict, votes = decide_skip(
                voter_id=voter,
                is_requester=False,
                listener_ids=listener_ids,
                existing_votes=votes,
            )
            verdicts.append(verdict)
        assert verdicts == [
            SkipVerdict.VOTE_RECORDED,
            SkipVerdict.VOTE_RECORDED,
            SkipVerdict.SKIP_NOW,
        ]
        assert votes == frozenset({1, 2, 3})

    def test_majority_config_default_matches_point_five(self):
        assert config.SKIP_VOTE_MAJORITY_RATIO == 0.5


# ---------------------------------------------------------------------------
# TestDecideSkipSolo  (-k solo)
# ---------------------------------------------------------------------------


class TestDecideSkipSolo:
    """SC-4: a solo listener's skip is instant — no vote, no tally (-k solo)."""

    def test_solo_single_listener_skips_instantly(self):
        verdict, votes = decide_skip(
            voter_id=1,
            is_requester=False,
            listener_ids=frozenset({1}),
            existing_votes=frozenset(),
        )
        assert verdict == SkipVerdict.SKIP_NOW
        assert votes == frozenset()

    def test_solo_empty_listener_ids_also_skips_instantly(self):
        """Defensive: an empty listener_ids also yields SKIP_NOW."""
        verdict, votes = decide_skip(
            voter_id=1,
            is_requester=False,
            listener_ids=frozenset(),
            existing_votes=frozenset(),
        )
        assert verdict == SkipVerdict.SKIP_NOW
        assert votes == frozenset()


# ---------------------------------------------------------------------------
# TestDecideSkipRequesterBypass  (-k requester_bypass)
# ---------------------------------------------------------------------------


class TestDecideSkipRequesterBypass:
    """D-13a requester bypass + D-13b bot-queued-never-bypasses (-k requester_bypass)."""

    def test_requester_bypass_skips_instantly_with_four_listeners_zero_votes(self):
        verdict, votes = decide_skip(
            voter_id=1,
            is_requester=True,
            listener_ids=frozenset({1, 2, 3, 4}),
            existing_votes=frozenset(),
        )
        assert verdict == SkipVerdict.SKIP_NOW
        assert votes == frozenset()

    def test_requester_bypass_still_skips_even_after_already_voting(self):
        """A requester who already voted still bypasses (D-13a escape hatch)."""
        verdict, votes = decide_skip(
            voter_id=1,
            is_requester=True,
            listener_ids=frozenset({1, 2, 3, 4}),
            existing_votes=frozenset({1}),
        )
        assert verdict == SkipVerdict.SKIP_NOW
        assert votes == frozenset({1})

    def test_requester_bypass_non_requester_on_bot_queued_track_never_bypasses(self):
        """D-13b: is_requester=False (voter_id != bot_id) on a bot-queued track
        never bypasses — 3 listeners, first vote -> VOTE_RECORDED, not SKIP_NOW."""
        verdict, votes = decide_skip(
            voter_id=2,
            is_requester=False,
            listener_ids=frozenset({1, 2, 3}),
            existing_votes=frozenset(),
        )
        assert verdict == SkipVerdict.VOTE_RECORDED
        assert votes == frozenset({2})


# ---------------------------------------------------------------------------
# TestDecideSkipIdempotent  (-k idempotent)
# ---------------------------------------------------------------------------


class TestDecideSkipIdempotent:
    """D-14: a repeat skip from the same user does not stack (-k idempotent)."""

    def test_idempotent_same_voter_twice_returns_already_voted_unchanged(self):
        listener_ids = frozenset({1, 2, 3})
        verdict1, votes1 = decide_skip(
            voter_id=1,
            is_requester=False,
            listener_ids=listener_ids,
            existing_votes=frozenset(),
        )
        assert verdict1 == SkipVerdict.VOTE_RECORDED
        assert votes1 == frozenset({1})

        verdict2, votes2 = decide_skip(
            voter_id=1,
            is_requester=False,
            listener_ids=listener_ids,
            existing_votes=votes1,
        )
        assert verdict2 == SkipVerdict.ALREADY_VOTED
        assert votes2 == votes1

    def test_idempotent_different_voter_after_repeat_still_records(self):
        listener_ids = frozenset({1, 2, 3})
        _, votes1 = decide_skip(
            voter_id=1,
            is_requester=False,
            listener_ids=listener_ids,
            existing_votes=frozenset(),
        )
        # voter 1 repeats — no-op
        verdict_repeat, votes_repeat = decide_skip(
            voter_id=1,
            is_requester=False,
            listener_ids=listener_ids,
            existing_votes=votes1,
        )
        assert verdict_repeat == SkipVerdict.ALREADY_VOTED
        # a different voter still records fine
        verdict2, votes2 = decide_skip(
            voter_id=2,
            is_requester=False,
            listener_ids=listener_ids,
            existing_votes=votes_repeat,
        )
        assert verdict2 == SkipVerdict.SKIP_NOW
        assert votes2 == frozenset({1, 2})


# ---------------------------------------------------------------------------
# TestDecideSkipDepartedVoter  (-k departed_voter)
# ---------------------------------------------------------------------------


class TestDecideSkipDepartedVoter:
    """D-17: a departed voter's vote stays counted (-k departed_voter)."""

    def test_departed_voter_still_counts_toward_threshold(self):
        """Voter 9 already voted and is no longer in listener_ids; the tally
        must still count them (would fail under the `& listener_ids` sketch)."""
        verdict, votes = decide_skip(
            voter_id=2,
            is_requester=False,
            listener_ids=frozenset({1, 2, 3}),
            existing_votes=frozenset({9}),
        )
        assert verdict == SkipVerdict.SKIP_NOW
        assert votes == frozenset({9, 2})

    def test_no_ampersand_listener_ids_intersection_in_source(self):
        """Static guard: the D-17-violating `& listener_ids` pattern must never
        reappear in the tally arithmetic."""
        import inspect

        import logic.skip_vote as skip_vote_module

        source = inspect.getsource(skip_vote_module)
        assert "new_votes & listener_ids" not in source


# ---------------------------------------------------------------------------
# TestSkipVotesResetOnTrackChange  (-k reset_on_track_change)
# ---------------------------------------------------------------------------


class TestSkipVotesResetOnTrackChange:
    """D-17: per-track vote state on MusicQueue resets structurally on any
    track-identity change (-k reset_on_track_change)."""

    def test_reset_on_track_change_fresh_queue_returns_empty_frozenset(self):
        """No current track (empty queue) -> frozenset(), no exception."""
        queue = MusicQueue(guild_id=1)
        assert queue.skip_votes_for_current() == frozenset()

    def test_reset_on_track_change_round_trip_same_track(self):
        """record_skip_votes then skip_votes_for_current on the SAME track
        round-trips the set unchanged."""
        queue = MusicQueue(guild_id=1)
        queue.add(_make_track("aaa"))
        queue.record_skip_votes(frozenset({7}))
        assert queue.skip_votes_for_current() == frozenset({7})

    def test_reset_on_track_change_skip_clears_votes(self):
        queue = MusicQueue(guild_id=1)
        queue.add(_make_track("aaa"))
        queue.add(_make_track("bbb"))
        queue.record_skip_votes(frozenset({1, 2}))
        assert queue.skip_votes_for_current() == frozenset({1, 2})

        queue.skip()
        assert queue.skip_votes_for_current() == frozenset()

    def test_reset_on_track_change_previous_does_not_resurrect_old_votes(self):
        """Going back to track 0 after a skip does NOT bring the old votes
        back — the reset already happened, votes do not resurrect."""
        queue = MusicQueue(guild_id=1)
        queue.add(_make_track("aaa"))
        queue.add(_make_track("bbb"))
        queue.record_skip_votes(frozenset({1, 2}))
        queue.skip()
        assert queue.skip_votes_for_current() == frozenset()

        queue.previous()
        assert queue.skip_votes_for_current() == frozenset()

    def test_reset_on_track_change_jump_to_yields_empty_set(self):
        queue = MusicQueue(guild_id=1)
        queue.add(_make_track("aaa"))
        queue.add(_make_track("bbb"))
        queue.record_skip_votes(frozenset({1}))
        queue.jump_to(1)
        assert queue.skip_votes_for_current() == frozenset()

    def test_reset_on_track_change_clear_leaves_empty_set(self):
        queue = MusicQueue(guild_id=1)
        queue.add(_make_track("aaa"))
        queue.record_skip_votes(frozenset({1}))
        queue.clear()
        assert queue.skip_votes_for_current() == frozenset()

    def test_reset_on_track_change_same_video_id_different_indices_independent(self):
        """The same video_id present at two different indices keeps
        independent votes — current_index is part of the key, not just
        video_id."""
        queue = MusicQueue(guild_id=1)
        queue.add(_make_track("same_id"))
        queue.add(_make_track("other"))
        queue.add(_make_track("same_id"))
        queue.record_skip_votes(frozenset({1}))
        assert queue.skip_votes_for_current() == frozenset({1})

        queue.jump_to(2)
        assert queue.skip_votes_for_current() == frozenset()
        queue.record_skip_votes(frozenset({2, 3}))
        assert queue.skip_votes_for_current() == frozenset({2, 3})

        # Back at index 0: the single-slot vote cache has already moved on to
        # index 2's key, so index 0's earlier votes are gone (not resurrected)
        # — same "no resurrection" rule as the previous() test above, proving
        # index 2's same-video_id session never polluted index 0's votes.
        queue.jump_to(0)
        assert queue.skip_votes_for_current() == frozenset()

    def test_reset_on_track_change_record_skip_votes_noop_on_empty_queue(self):
        """record_skip_votes must not raise when there is no current track."""
        queue = MusicQueue(guild_id=1)
        queue.record_skip_votes(frozenset({1}))
        assert queue.skip_votes_for_current() == frozenset()
