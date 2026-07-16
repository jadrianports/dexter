"""Exhaustive pure-unit tests for logic/radio.py (DJ-01 / D-19).

No mocks, no clocks, no RNG, no Discord — all inputs are plain Python
primitives. If a test needs a mock the cut-line in logic/radio.py is wrong
(mirrors tests/test_proactive_logic.py's discipline).

Task 2 (models/queue.py radio armed-state) adds MusicQueue-level classes to
this same file (`-k disarm`, `-k loop_exclusion`) — mock-free since
models/queue.py imports no Discord either.

Test method names deliberately embed their `-k` selector substring
(`should_refill`, `played_set`, `human_play_injects`) literally, since
pytest's `-k` is a plain substring match with no underscore-fuzzing.
"""

import config
from logic.radio import has_room_for_refill, is_already_played, should_refill_radio
from models.queue import LoopMode, MusicQueue

# ---------------------------------------------------------------------------
# TestShouldRefillRadio  (-k should_refill)
# ---------------------------------------------------------------------------


class TestShouldRefillRadio:
    """Full branch + boundary coverage for should_refill_radio (D-10/T-26-02)."""

    # -- armed gate (SC-2 lock) ---------------------------------------------

    def test_should_refill_disarmed_never_refills_regardless_of_other_inputs(self):
        """armed=False -> False no matter what humans_present/upcoming_count are."""
        result = should_refill_radio(
            armed=False,
            humans_present=True,
            upcoming_count=0,
        )
        assert result is False

    def test_should_refill_disarmed_never_refills_even_with_zero_upcoming_and_humans(self):
        """Disarmed + empty queue + humans present still never refills (SC-2)."""
        result = should_refill_radio(
            armed=False,
            humans_present=True,
            upcoming_count=0,
        )
        assert result is False

    def test_should_refill_disarmed_never_refills_with_favorable_upcoming_count(self):
        """Disarmed short-circuits even when upcoming_count is well under lookahead."""
        result = should_refill_radio(
            armed=False,
            humans_present=True,
            upcoming_count=1,
        )
        assert result is False

    # -- humans-present gate (T-26-02) ---------------------------------------

    def test_should_refill_no_humans_present_never_refills_even_when_armed(self):
        """armed=True but humans_present=False -> False (never burn the RPM budget)."""
        result = should_refill_radio(
            armed=True,
            humans_present=False,
            upcoming_count=0,
        )
        assert result is False

    def test_should_refill_no_humans_present_never_refills_regardless_of_upcoming(self):
        """Empty room suppresses refill even at the exact lookahead boundary."""
        result = should_refill_radio(
            armed=True,
            humans_present=False,
            upcoming_count=config.RADIO_LOOKAHEAD_DEPTH,
        )
        assert result is False

    # -- runway / lookahead gate (D-10) --------------------------------------

    def test_should_refill_upcoming_exactly_at_lookahead_depth_refills(self):
        """upcoming_count == lookahead_depth -> True (boundary: at-depth REFILLS)."""
        result = should_refill_radio(
            armed=True,
            humans_present=True,
            upcoming_count=config.RADIO_LOOKAHEAD_DEPTH,
        )
        assert result is True

    def test_should_refill_upcoming_one_above_lookahead_depth_does_not_refill(self):
        """upcoming_count == lookahead_depth + 1 -> False (still enough runway)."""
        result = should_refill_radio(
            armed=True,
            humans_present=True,
            upcoming_count=config.RADIO_LOOKAHEAD_DEPTH + 1,
        )
        assert result is False

    def test_should_refill_upcoming_below_lookahead_depth_refills(self):
        """upcoming_count below lookahead_depth -> True (runway is thinner than the trigger)."""
        result = should_refill_radio(
            armed=True,
            humans_present=True,
            upcoming_count=max(config.RADIO_LOOKAHEAD_DEPTH - 1, 0),
        )
        assert result is True

    def test_should_refill_upcoming_zero_refills_when_armed_and_humans_present(self):
        """An armed radio with zero upcoming tracks still refills (0 <= lookahead_depth)."""
        result = should_refill_radio(
            armed=True,
            humans_present=True,
            upcoming_count=0,
        )
        assert result is True

    def test_should_refill_upcoming_well_above_lookahead_depth_does_not_refill(self):
        """upcoming_count comfortably above lookahead_depth -> False."""
        result = should_refill_radio(
            armed=True,
            humans_present=True,
            upcoming_count=config.RADIO_LOOKAHEAD_DEPTH + 10,
        )
        assert result is False

    # -- default-arg proof (reads from config) -------------------------------

    def test_should_refill_default_lookahead_depth_is_read_from_config(self):
        """Omitting lookahead_depth uses config.RADIO_LOOKAHEAD_DEPTH, not a hardcoded value."""
        result_default = should_refill_radio(
            armed=True,
            humans_present=True,
            upcoming_count=config.RADIO_LOOKAHEAD_DEPTH,
        )
        result_explicit = should_refill_radio(
            armed=True,
            humans_present=True,
            upcoming_count=config.RADIO_LOOKAHEAD_DEPTH,
            lookahead_depth=config.RADIO_LOOKAHEAD_DEPTH,
        )
        assert result_default == result_explicit is True

    def test_should_refill_custom_lookahead_depth_override_respected(self):
        """Passing a custom lookahead_depth is respected, not hard-coded to config."""
        result = should_refill_radio(
            armed=True,
            humans_present=True,
            upcoming_count=5,
            lookahead_depth=10,
        )
        assert result is True

    def test_should_refill_custom_lookahead_depth_override_still_fails_above_it(self):
        """Custom lookahead_depth override still fails when upcoming exceeds it."""
        result = should_refill_radio(
            armed=True,
            humans_present=True,
            upcoming_count=11,
            lookahead_depth=10,
        )
        assert result is False

    # -- human /play injection does not disarm (D-07) ------------------------

    def test_should_refill_human_play_injects_suppresses_refill_but_stays_armed(self):
        """A human /play pushing upcoming_count above lookahead suppresses refill
        while `armed` conceptually stays True — injecting does not disarm (D-07).
        This function only decides refill; disarming is a MusicQueue concern
        (Task 2), so this asserts the gate output, not queue state.
        """
        result = should_refill_radio(
            armed=True,
            humans_present=True,
            upcoming_count=config.RADIO_LOOKAHEAD_DEPTH + 5,
        )
        assert result is False

    def test_should_refill_human_play_injects_then_drains_back_to_refilling(self):
        """After injected tracks drain back down to the lookahead boundary, refill
        resumes — armed never flipped, this models the same call with a lower count."""
        result = should_refill_radio(
            armed=True,
            humans_present=True,
            upcoming_count=config.RADIO_LOOKAHEAD_DEPTH,
        )
        assert result is True


# ---------------------------------------------------------------------------
# TestIsAlreadyPlayed  (-k played_set)
# ---------------------------------------------------------------------------


class TestIsAlreadyPlayed:
    """Full coverage for is_already_played (D-03 hard post-filter)."""

    def test_played_set_member_video_id_returns_true(self):
        """video_id present in played_ids -> True."""
        result = is_already_played(
            video_id="abc123",
            played_ids=frozenset({"abc123", "def456"}),
        )
        assert result is True

    def test_played_set_non_member_video_id_returns_false(self):
        """video_id absent from played_ids -> False."""
        result = is_already_played(
            video_id="zzz999",
            played_ids=frozenset({"abc123", "def456"}),
        )
        assert result is False

    def test_played_set_empty_returns_false(self):
        """A fresh session (empty played_ids) always returns False."""
        result = is_already_played(
            video_id="abc123",
            played_ids=frozenset(),
        )
        assert result is False


# ---------------------------------------------------------------------------
# TestHasRoomForRefill
# ---------------------------------------------------------------------------


class TestHasRoomForRefill:
    """Boundary coverage for has_room_for_refill (queue-cap guard)."""

    def test_has_room_for_refill_exactly_at_cap_returns_true(self):
        """queue_size + batch_size == cap -> True (<= is inclusive: filling to
        exactly the ceiling still fits, it just leaves zero headroom after)."""
        result = has_room_for_refill(
            queue_size=config.MAX_QUEUE_SIZE_PER_GUILD - config.AUTO_QUEUE_SONGS_PER_ROUND,
            batch_size=config.AUTO_QUEUE_SONGS_PER_ROUND,
            cap=config.MAX_QUEUE_SIZE_PER_GUILD,
        )
        assert result is True

    def test_has_room_for_refill_one_over_cap_returns_false(self):
        """queue_size + batch_size == cap + 1 -> False (one over the ceiling)."""
        result = has_room_for_refill(
            queue_size=config.MAX_QUEUE_SIZE_PER_GUILD - config.AUTO_QUEUE_SONGS_PER_ROUND + 1,
            batch_size=config.AUTO_QUEUE_SONGS_PER_ROUND,
            cap=config.MAX_QUEUE_SIZE_PER_GUILD,
        )
        assert result is False

    def test_has_room_for_refill_one_under_cap_returns_true(self):
        """queue_size + batch_size == cap - 1 -> True (still room)."""
        result = has_room_for_refill(
            queue_size=config.MAX_QUEUE_SIZE_PER_GUILD - config.AUTO_QUEUE_SONGS_PER_ROUND - 1,
            batch_size=config.AUTO_QUEUE_SONGS_PER_ROUND,
            cap=config.MAX_QUEUE_SIZE_PER_GUILD,
        )
        assert result is True

    def test_has_room_for_refill_default_args_read_from_config(self):
        """Omitting batch_size/cap uses config.AUTO_QUEUE_SONGS_PER_ROUND / config.MAX_QUEUE_SIZE_PER_GUILD."""
        result_default = has_room_for_refill(queue_size=0)
        result_explicit = has_room_for_refill(
            queue_size=0,
            batch_size=config.AUTO_QUEUE_SONGS_PER_ROUND,
            cap=config.MAX_QUEUE_SIZE_PER_GUILD,
        )
        assert result_default == result_explicit is True

    def test_has_room_for_refill_zero_queue_size_has_room(self):
        """An empty queue always has room for a single default batch."""
        result = has_room_for_refill(queue_size=0)
        assert result is True


# ---------------------------------------------------------------------------
# TestRadioDisarm  (-k disarm)  — mock-free: models/queue.py imports no Discord
# ---------------------------------------------------------------------------


class TestRadioDisarm:
    """clear()/disarm_radio() coverage for MusicQueue radio state (SC-2/D-07/D-08)."""

    def test_disarm_clear_disarms_armed_radio_and_empties_played_set(self):
        """clear() disarms an armed radio and empties radio_played (D-07/D-08)."""
        q = MusicQueue(guild_id=1)
        q.arm_radio("daft punk")
        q.radio_played["abc123"] = "One More Time by Daft Punk"
        q.clear()
        assert q.radio_armed is False
        assert q.radio_played == {}

    def test_disarm_clear_resets_radio_seed_to_none(self):
        """A disarmed queue's radio_seed is None after clear()."""
        q = MusicQueue(guild_id=1)
        q.arm_radio("daft punk")
        q.clear()
        assert q.radio_seed is None

    def test_disarm_radio_is_idempotent(self):
        """Calling disarm_radio() on an already-disarmed queue is a safe no-op."""
        q = MusicQueue(guild_id=1)
        assert q.radio_armed is False
        q.disarm_radio()
        assert q.radio_armed is False
        assert q.radio_seed is None
        assert q.radio_played == {}

    def test_disarm_radio_directly_clears_all_three_fields(self):
        """disarm_radio() alone (without clear()) resets armed/seed/played."""
        q = MusicQueue(guild_id=1)
        q.arm_radio("phonk")
        q.radio_played["xyz"] = "Some Track by Someone"
        q.disarm_radio()
        assert q.radio_armed is False
        assert q.radio_seed is None
        assert q.radio_played == {}

    def test_disarm_new_queue_defaults_to_disarmed(self):
        """A fresh MusicQueue starts disarmed with no seed and an empty played-set."""
        q = MusicQueue(guild_id=1)
        assert q.radio_armed is False
        assert q.radio_seed is None
        assert q.radio_played == {}

    def test_disarm_never_persisted_in_queue_persistence_payload(self):
        """D-08: no 'radio' key exists anywhere in services/queue_persistence.py."""
        import pathlib

        src = pathlib.Path("services/queue_persistence.py").read_text(encoding="utf-8")
        assert "radio" not in src


# ---------------------------------------------------------------------------
# TestRadioLoopExclusion  (-k loop_exclusion)  — D-11 mutual exclusion
# ---------------------------------------------------------------------------


class TestRadioLoopExclusion:
    """arm_radio()/set_loop_mode() mutual-exclusion coverage (D-11)."""

    def test_loop_exclusion_arm_radio_forces_loop_off_and_returns_true_when_loop_was_on(self):
        """arm_radio() forces loop_mode to OFF and returns True when loop was on."""
        q = MusicQueue(guild_id=1)
        q.loop_mode = LoopMode.QUEUE
        result = q.arm_radio("daft punk")
        assert result is True
        assert q.loop_mode == LoopMode.OFF
        assert q.radio_armed is True

    def test_loop_exclusion_arm_radio_returns_false_when_loop_already_off(self):
        """arm_radio() returns False when loop was already off (no conflict to announce)."""
        q = MusicQueue(guild_id=1)
        assert q.loop_mode == LoopMode.OFF
        result = q.arm_radio("daft punk")
        assert result is False
        assert q.loop_mode == LoopMode.OFF

    def test_loop_exclusion_set_loop_mode_queue_disarms_armed_radio(self):
        """set_loop_mode(QUEUE) on an armed queue disarms radio and returns True."""
        q = MusicQueue(guild_id=1)
        q.arm_radio("daft punk")
        result = q.set_loop_mode(LoopMode.QUEUE)
        assert result is True
        assert q.radio_armed is False
        assert q.loop_mode == LoopMode.QUEUE

    def test_loop_exclusion_set_loop_mode_single_disarms_armed_radio(self):
        """set_loop_mode(SINGLE) on an armed queue also disarms radio and returns True."""
        q = MusicQueue(guild_id=1)
        q.arm_radio("daft punk")
        result = q.set_loop_mode(LoopMode.SINGLE)
        assert result is True
        assert q.radio_armed is False
        assert q.loop_mode == LoopMode.SINGLE

    def test_loop_exclusion_set_loop_mode_off_leaves_armed_radio_armed(self):
        """set_loop_mode(OFF) on an armed queue is NOT a conflict — stays armed, returns False."""
        q = MusicQueue(guild_id=1)
        q.arm_radio("daft punk")
        result = q.set_loop_mode(LoopMode.OFF)
        assert result is False
        assert q.radio_armed is True

    def test_loop_exclusion_set_loop_mode_on_disarmed_queue_returns_false(self):
        """set_loop_mode() on a never-armed queue simply sets loop_mode, returns False."""
        q = MusicQueue(guild_id=1)
        result = q.set_loop_mode(LoopMode.QUEUE)
        assert result is False
        assert q.loop_mode == LoopMode.QUEUE
        assert q.radio_armed is False

    def test_loop_exclusion_arm_radio_twice_resets_played_set_between_sessions(self):
        """arm_radio() called twice resets radio_played between sessions (Pitfall 3)."""
        q = MusicQueue(guild_id=1)
        q.arm_radio("a")
        q.radio_played["vid1"] = "Track One by Artist"
        assert q.radio_played != {}
        q.arm_radio("b")
        assert q.radio_played == {}
        assert q.radio_seed == "b"
