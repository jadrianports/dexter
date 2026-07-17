"""Source-assertion regression tests for the Phase 26 skip-vote choke-point
unification (DJ-02 / D-15), closing 26-RESEARCH Pitfall 1.

`/skip`'s slash-command body did NOT call `_do_skip` before this phase — it
carried a fully duplicated inline skip body (mark_song_skipped/queue.skip()/
_persist_queue/play-after-skip/_refresh_now_playing), while only
`NowPlayingView.skip_button` called `cog._do_skip(...)` directly. A vote
check placed only in front of `_do_skip` would therefore have left `/skip`
sailing through completely unvoted — the exact hole D-15 exists to close.

These tests use `inspect.getsource` because Discord/process glue is
untested-by-design per `.planning/codebase/TESTING.md` — there is no live
Discord path to exercise here, so the regression lock is structural: it
fails the build if a future edit re-duplicates a skip body, lets a surface
bypass the gate, re-derives the vote arithmetic in glue, memoizes the
listener denominator, adds an admin bypass, or bolts a memory write onto
the skip path.
"""

from __future__ import annotations

import inspect
import pathlib

import cogs.music as music_module
from cogs.music import MusicCog, NowPlayingView
from logic.playback import TrackEndAction


def _skip_command_source() -> str:
    return inspect.getsource(MusicCog.skip.callback)


def _skip_button_source() -> str:
    return inspect.getsource(NowPlayingView.skip_button)


def _try_skip_source() -> str:
    return inspect.getsource(MusicCog._try_skip)


def _do_skip_source() -> str:
    return inspect.getsource(MusicCog._do_skip)


def _music_module_source() -> str:
    return inspect.getsource(music_module)


def _on_track_end_source() -> str:
    return inspect.getsource(MusicCog._on_track_end)


def _radio_start_source() -> str:
    return inspect.getsource(MusicCog.radio_start.callback)


def _radio_stop_source() -> str:
    return inspect.getsource(MusicCog.radio_stop.callback)


def _play_source() -> str:
    return inspect.getsource(MusicCog.play.callback)


def _seek_command_source() -> str:
    return inspect.getsource(MusicCog.seek.callback)


def _loop_command_source() -> str:
    return inspect.getsource(MusicCog.loop.callback)


def _do_loop_cycle_source() -> str:
    return inspect.getsource(MusicCog._do_loop_cycle)


def _stop_command_source() -> str:
    return inspect.getsource(MusicCog.stop.callback)


def _do_stop_source() -> str:
    return inspect.getsource(MusicCog._do_stop)


def _idle_check_source() -> str:
    """inspect.getsource fails directly on a discord.ext.tasks.Loop object —
    the underlying coroutine lives on its .coro attribute. Fall back to a
    plain text read of bot.py if that attribute ever goes away."""
    import bot as bot_module

    try:
        return inspect.getsource(bot_module.idle_check.coro)
    except (TypeError, AttributeError):
        text = pathlib.Path("bot.py").read_text(encoding="utf-8")
        start = text.index("async def idle_check")
        return text[start : start + 2000]


def _non_comment_lines(src: str) -> list[str]:
    """Source lines with comment-only lines filtered out, so a count()-based
    assertion can't be silently invalidated by an explanatory comment quoting
    a banned/gated token (e.g. _try_skip's own docstring/comments legitimately
    discuss "the bot's own id" and "the majority rule" in prose)."""
    return [ln for ln in src.splitlines() if not ln.strip().startswith("#")]


# ---------------------------------------------------------------------------
# TestSkipChokePointUnification — the D-15 / Pitfall 1 lock
# ---------------------------------------------------------------------------


class TestSkipChokePointUnification:
    def test_skip_choke_point_slash_routes_through_try_skip(self):
        assert "_try_skip(" in _skip_command_source()

    def test_skip_choke_point_button_routes_through_try_skip(self):
        assert "_try_skip(" in _skip_button_source()

    def test_skip_choke_point_button_does_not_call_do_skip_directly(self):
        """The button must reach the skip mechanics only through the gate —
        it must never call _do_skip directly again."""
        assert "_do_skip(" not in _skip_button_source()

    def test_skip_choke_point_slash_body_no_longer_duplicated(self):
        """The concrete Pitfall 1 lock: the /skip command used to have a
        fully duplicated inline skip body that never called _do_skip at
        all. None of those tokens may reappear in the slash command's
        source — if they do, the duplication (and the D-15 hole) is back."""
        src = _skip_command_source()
        for token in ("mark_song_skipped(", "queue.skip()", "_persist_queue(", "play-after-skip"):
            assert token not in src, f"duplicated inline skip body token reappeared: {token!r}"

    def test_skip_choke_point_do_skip_called_exactly_once_from_try_skip(self):
        """_do_skip must be reachable through exactly one call site in the
        whole module, and that call site must be inside _try_skip."""
        non_comment = _non_comment_lines(_music_module_source())
        count = sum(ln.count("self._do_skip(") + ln.count("cog._do_skip(") for ln in non_comment)
        assert count == 1, f"expected exactly one _do_skip( call site, found {count}"
        assert "_do_skip(" in _try_skip_source()

    def test_skip_choke_point_both_callers_pass_voter_id(self):
        assert "voter_id=interaction.user.id" in _skip_command_source()
        assert "voter_id=interaction.user.id" in _skip_button_source()


# ---------------------------------------------------------------------------
# TestVoiceMembershipGateOnSkipEntryPoints — CR-01
# ---------------------------------------------------------------------------
# decide_skip's tally (logic/skip_vote.py gate 4) intentionally counts
# len(new_votes) with no intersection against listener_ids (D-17 — a
# departed voter's vote stays counted). That means _try_skip trusts its
# CALLER to only ever pass a voter_id belonging to (or having belonged to)
# the room. NowPlayingView.skip_button always enforced that via
# _guard_in_voice; /skip and /seek's past-end auto-skip did not, so any
# guild member with slash-command access — never having joined voice at
# all — could cast a binding skip vote. These tests lock the fix
# structurally (Discord glue is untested-by-design per
# .planning/codebase/TESTING.md) by asserting both entry points reject a
# non-listener with the same NOT_IN_VOICE guard the button and /filter
# already use, and that the check runs strictly before any vote is cast.


class TestVoiceMembershipGateOnSkipEntryPoints:
    def test_skip_command_checks_user_voice_channel(self):
        src = _skip_command_source()
        assert "interaction.user.voice" in src
        assert "voice_client.channel" in src
        assert "NOT_IN_VOICE" in src

    def test_skip_command_voice_guard_precedes_try_skip_call(self):
        """The membership check must gate entry to _try_skip, not run after
        a vote was already cast."""
        src = _skip_command_source()
        guard_pos = src.index("interaction.user.voice")
        try_skip_pos = src.index("_try_skip(")
        assert guard_pos < try_skip_pos

    def test_seek_past_end_checks_user_voice_channel(self):
        src = _seek_command_source()
        assert "interaction.user.voice" in src
        assert "voice_client.channel" in src
        assert "NOT_IN_VOICE" in src

    def test_seek_past_end_voice_guard_precedes_try_skip_call(self):
        src = _seek_command_source()
        guard_pos = src.index("interaction.user.voice")
        try_skip_pos = src.index("_try_skip(")
        assert guard_pos < try_skip_pos


# ---------------------------------------------------------------------------
# TestPausedTrackSkippableAtEveryEntryPoint — WR-03
# ---------------------------------------------------------------------------
# The button's guard (playpause_button/skip_button) is
# `not is_playing and not is_paused` — a paused track is still
# skippable/votable. /skip and /seek used a bare `not queue.is_playing`,
# which is True while paused, so a paused track's vote could only ever be
# cast through the button, not the other two documented D-15 entry points.


class TestPausedTrackSkippableAtEveryEntryPoint:
    def test_skip_command_allows_paused_tracks(self):
        src = _skip_command_source()
        assert "queue.is_paused" in src

    def test_seek_command_allows_paused_tracks(self):
        src = _seek_command_source()
        assert "queue.is_paused" in src

    def test_skip_button_guard_unchanged_reference_shape(self):
        """Locks the reference shape /skip and /seek were aligned to —
        if the button's own guard ever stops checking is_paused, the
        other two entry points' fix loses its anchor."""
        assert "not queue.is_playing and not queue.is_paused" in _skip_button_source()


# ---------------------------------------------------------------------------
# TestVerdictDispatchedNotReimplemented — Phase 10 D-02 rule
# ---------------------------------------------------------------------------


class TestVerdictDispatchedNotReimplemented:
    def test_try_skip_dispatches_on_decide_skip_and_required_votes(self):
        src = _try_skip_source()
        assert "decide_skip(" in src
        assert "required_votes(" in src

    def test_majority_arithmetic_absent_from_module(self):
        """The arithmetic lives ONLY in logic/skip_vote.py — glue dispatches
        on the returned SkipVerdict and must never re-derive it (Phase 10
        D-02 rule)."""
        joined = "\n".join(_non_comment_lines(_music_module_source()))
        for banned in ("// 2 + 1", "math.floor", "SKIP_VOTE_MAJORITY_RATIO"):
            assert banned not in joined, f"majority arithmetic re-derived in cogs/music.py: {banned!r}"


# ---------------------------------------------------------------------------
# TestFreshListenerRead — D-17 / Pitfall 4
# ---------------------------------------------------------------------------


class TestFreshListenerRead:
    def test_denominator_read_fresh_inside_try_skip(self):
        """The listener set is read inside the gate on every invocation —
        never passed in or cached across votes."""
        assert "for m in voice_client.channel.members if not m.bot" in _try_skip_source()

    def test_no_memoized_listener_snapshot_attribute(self):
        """No cached-listener-set attribute anywhere in the module — a
        per-track snapshot would silently break the threshold the moment
        anyone joins or leaves mid-vote."""
        src = _music_module_source()
        for banned in ("_cached_listener", "_listener_ids"):
            assert banned not in src, f"found what looks like a memoized listener snapshot: {banned!r}"


# ---------------------------------------------------------------------------
# TestNoBypassBackdoor — T-26-05 / D-13a
# ---------------------------------------------------------------------------


class TestNoBypassBackdoor:
    def test_only_bypass_is_the_requester(self):
        assert "requested_by" in _try_skip_source()

    def test_no_admin_or_owner_bypass(self):
        """An admin/owner skip bypass is an explicit scope VIOLATION
        (T-26-05 / D-13a), not a feature — it must never appear."""
        src = _try_skip_source()
        assert "manage_guild" not in src
        assert "is_owner" not in src


# ---------------------------------------------------------------------------
# TestNoNewMemoryKindInSkipPath — D-20 (binding -k no_new_memory_kind selector)
# ---------------------------------------------------------------------------


class TestNoNewMemoryKindInSkipPath:
    def test_no_new_memory_kind_skip_path_try_skip(self):
        """A vote-skipped track records via the EXISTING mark_song_skipped
        and nothing more — no new memory kind, no distill_and_remember
        call, anywhere in the gate."""
        src = _try_skip_source()
        assert "distill_and_remember(" not in src
        assert "kind=" not in src

    def test_no_new_memory_kind_skip_path_do_skip(self):
        src = _do_skip_source()
        assert "distill_and_remember(" not in src
        assert "kind=" not in src


# ---------------------------------------------------------------------------
# TestDoSkipAdvancesBeforeFirstAwait — WR-02
# ---------------------------------------------------------------------------
# _try_skip's own vote decision (decide_skip/record_skip_votes) has no await
# in it, so if _do_skip also advances the queue (queue.skip()) before its
# own first await (mark_song_skipped), the whole "decide SKIP_NOW -> advance
# the queue" sequence is one atomic block with no yield point. Without this
# ordering, a second concurrent _try_skip call — e.g. a different voter
# crossing an already-met threshold while a first call was suspended at the
# mark_song_skipped await — would observe the same not-yet-advanced current
# track and the same pre-skip vote set, independently re-reach SKIP_NOW, and
# double-skip (mark_song_skipped called twice, queue.skip() called twice for
# what the room intended as a single skip). Locked structurally, matching
# the file's existing untested-Discord-glue convention.


class TestDoSkipAdvancesBeforeFirstAwait:
    def test_queue_skip_precedes_mark_song_skipped(self):
        src = _do_skip_source()
        skip_pos = src.index("queue.skip()")
        mark_pos = src.index("mark_song_skipped(")
        assert skip_pos < mark_pos, (
            "queue.skip() must run before the first await (mark_song_skipped) "
            "in _do_skip, or a second concurrent _try_skip call can double-skip (WR-02)"
        )

    def test_no_await_between_current_read_and_queue_skip(self):
        """No new await was introduced ahead of queue.skip() itself — the
        current-track read and the queue advance stay in the same
        synchronous stretch of _do_skip. Comment-stripped so an explanatory
        comment that merely mentions "await" in prose can't false-positive."""
        non_comment = "\n".join(_non_comment_lines(_do_skip_source()))
        current_pos = non_comment.index("current = queue.get_current()")
        skip_pos = non_comment.index("queue.skip()")
        between = non_comment[current_pos:skip_pos]
        assert "await " not in between

    def test_do_skip_still_records_via_mark_song_skipped(self):
        """The existing recording path is intact — not accidentally removed
        during the D-15 unification."""
        assert "mark_song_skipped(" in _do_skip_source()


# ---------------------------------------------------------------------------
# TestRadioLookaheadWiring — 26-05 D-10
# ---------------------------------------------------------------------------


class TestRadioLookaheadWiring:
    def test_on_track_end_calls_should_refill_radio(self):
        assert "should_refill_radio(" in _on_track_end_source()

    def test_on_track_end_dispatches_radio_refill_task(self):
        assert 'name="radio-refill"' in _on_track_end_source()

    def test_autoqueue_branch_forwards_radio_flag(self):
        """Queue exhaustion with radio armed must not hit
        AUTO_QUEUE_MAX_ROUNDS mid-radio — the flag must be forwarded."""
        assert "radio=radio_armed" in _on_track_end_source()

    def test_on_track_end_still_dispatches_on_track_end_action(self):
        """The existing pure dispatch is untouched — radio is an additional
        gate consulted alongside it, never a replacement."""
        src = _on_track_end_source()
        assert "decide_on_track_end(" in src
        assert "TrackEndAction." in src

    def test_track_end_action_has_no_new_radio_member(self):
        """Radio is an additional gate, never a new TrackEndAction enum
        member — logic/playback.py stays byte-identical (26-PATTERNS)."""
        assert {m.name for m in TrackEndAction} == {"NOOP", "PLAY", "AUTOQUEUE", "STOP_AND_CLEAR"}

    def test_on_track_end_source_has_no_radio_enum_member_reference(self):
        assert "TrackEndAction.RADIO" not in _on_track_end_source()

    def test_on_track_end_single_member_enumeration(self):
        """Reuses the existing humans_present computation — no second
        `not m.bot` member-scan was introduced for the lookahead gate."""
        non_comment = "\n".join(_non_comment_lines(_on_track_end_source()))
        assert non_comment.count("not m.bot") == 1


# ---------------------------------------------------------------------------
# TestRadioLifecycleWiring — 26-05 D-06a/D-06b/D-07/D-12
# ---------------------------------------------------------------------------


class TestRadioLifecycleWiring:
    def test_radio_start_arms_and_resets(self):
        src = _radio_start_source()
        assert "arm_radio(" in src
        assert "reset_auto_queue()" in src
        assert "radio=True" in src

    def test_radio_stop_disarms_and_resets(self):
        src = _radio_stop_source()
        assert "disarm_radio()" in src
        assert "reset_auto_queue()" in src

    def test_radio_stop_does_not_clear_the_queue(self):
        """Stopping the station is not stopping the session — already-queued
        tracks must keep playing out (SC-2's honest counterpart to D-12)."""
        assert "queue.clear()" not in _radio_stop_source()

    def test_play_never_disarms_or_arms_radio(self):
        """D-07: a human /play mid-radio only INJECTS a track. One person
        adding one song must not silently kill a mode nobody asked to end."""
        src = _play_source()
        assert "disarm_radio" not in src
        assert "arm_radio" not in src

    def test_radio_start_truncates_seed_before_arming(self):
        """WR-04: an unbounded free-text seed is echoed into a public reply
        AND re-embedded into every subsequent refill prompt for the life of
        the session — it must be capped ONCE, before arm_radio stores it,
        not at each downstream use site."""
        src = _radio_start_source()
        assert "config.RADIO_SEED_MAX_LENGTH" in src
        truncate_pos = src.index("config.RADIO_SEED_MAX_LENGTH")
        arm_pos = src.index("arm_radio(")
        assert truncate_pos < arm_pos

    def test_radio_seed_max_length_is_a_sane_positive_cap(self):
        """A small sanity bound on the knob itself — comfortably below
        Discord's 2000-char message limit once the RADIO_START template's
        own text is accounted for, and comfortably above 0."""
        import config

        assert 0 < config.RADIO_SEED_MAX_LENGTH <= 500


# ---------------------------------------------------------------------------
# TestRadioDisarmsAtEveryTeardown — the SC-2 proof
# ---------------------------------------------------------------------------


class TestRadioDisarmsAtEveryTeardown:
    def test_clear_disarms_radio_behaviourally(self):
        """The concrete SC-2 proof: a /stop that clears a queue radio
        instantly refills would be an unstoppable bot. clear() (26-01) is
        the single line that makes every existing teardown site a disarm
        site, with zero per-site edits needed."""
        from models.queue import MusicQueue

        queue = MusicQueue(guild_id=1)
        queue.arm_radio("some seed")
        assert queue.radio_armed is True

        queue.clear()

        assert queue.radio_armed is False

    def test_stop_command_still_calls_clear(self):
        assert "queue.clear()" in _stop_command_source()

    def test_do_stop_still_calls_clear(self):
        assert "queue.clear()" in _do_stop_source()

    def test_idle_check_still_calls_clear(self):
        assert "queue.clear()" in _idle_check_source()


# ---------------------------------------------------------------------------
# TestLoopRadioMutualExclusionWiring — 26-05 D-11
# ---------------------------------------------------------------------------


class TestLoopRadioMutualExclusionWiring:
    def test_loop_command_routes_through_set_loop_mode(self):
        src = _loop_command_source()
        assert "set_loop_mode(" in src
        assert "RADIO_LOOP_CONFLICT" in src

    def test_loop_cycle_routes_through_set_loop_mode(self):
        assert "set_loop_mode(" in _do_loop_cycle_source()

    def test_loop_command_resets_auto_queue_on_radio_disarm(self):
        """WR-01: a mid-radio /loop disarm must reset the auto-queue
        play/skip counters, mirroring radio_start/radio_stop's own
        lifecycle-boundary reset — otherwise radio-era counts leak into
        the first post-radio auto-queue round's ignored-signal check."""
        src = _loop_command_source()
        assert "radio_disarmed" in src
        assert "reset_auto_queue()" in src

    def test_loop_cycle_resets_auto_queue_on_radio_disarm(self):
        """The other D-11 disarm surface (the now-playing loop button) needs
        the identical reset — the leak otherwise only closes for /loop."""
        src = _do_loop_cycle_source()
        assert "radio_disarmed" in src
        assert "reset_auto_queue()" in src

    def test_no_direct_loop_mode_assignment_remains(self):
        """Both loop surfaces (/loop and the now-playing button) go through
        the one model choke point — no direct queue.loop_mode = assignment
        may remain in cogs/music.py."""
        non_comment = "\n".join(_non_comment_lines(_music_module_source()))
        assert "queue.loop_mode = " not in non_comment


# ---------------------------------------------------------------------------
# TestCrossfadeEngineWiring — 27-05 D-01 / D-10b / D-12c / D-12d
# ---------------------------------------------------------------------------
# This glue is untested-by-design per .planning/codebase/TESTING.md — its
# safety evidence is the spike's D-11 attack artifacts recorded in
# 27-RESEARCH.md §Evidence, not unit tests. These are structural review
# encoded as tests, matching this file's existing convention.
#
# The equivalent of a "_do_skip has exactly one call site" tripwire already
# exists above (test_skip_choke_point_do_skip_called_exactly_once_from_try_skip)
# and is not duplicated here — Phase 26's D-15 invariant only needs to keep
# passing, which the existing test already proves untouched by this plan's
# zero-diff over _try_skip/_do_skip/the vote cache.


def _play_track_source() -> str:
    return inspect.getsource(MusicCog._play_track)


class TestCrossfadeEngineWiring:
    def test_play_track_generation_block_intact(self):
        """D-01 tripwire: _play_track's engine block — increment, capture,
        define the guarded after_callback, and the guard itself — must
        appear in exactly this order. A future edit that reorders or removes
        any of these turns this into a red build."""
        src = _play_track_source()
        gen_incr_pos = src.index("queue._play_generation += 1")
        capture_pos = src.index("current_gen = queue._play_generation")
        callback_def_pos = src.index("def after_callback")
        guard_pos = src.index("queue._play_generation == current_gen")
        assert gen_incr_pos < capture_pos < callback_def_pos < guard_pos

    def test_crossfade_hard_cut_is_log_only(self):
        """D-10b: the non-FADE branch must reach no user-facing send —
        scoped to the crossfade decision block only, since _play_track
        legitimately calls channel.send elsewhere (the skipped-tracks
        summary)."""
        src = _play_track_source()
        start = src.index("decide_crossfade(")
        end = src.index("# Increment generation")
        block = src[start:end]
        for banned in ("channel.send", "followup", "response.send_message"):
            assert banned not in block

    def test_decide_crossfade_called_exactly_once(self):
        assert _play_track_source().count("decide_crossfade(") == 1

    def test_crossfade_consulted_before_generation_increment(self):
        src = _play_track_source()
        decide_pos = src.index("decide_crossfade(")
        gen_incr_pos = src.index("queue._play_generation += 1")
        assert decide_pos < gen_incr_pos

    def test_xf_pending_cleared_where_consumed(self):
        """queue._xf_pending must be read and nulled in the same block —
        it can never be consumed twice."""
        src = _play_track_source()
        read_pos = src.index("xf_pending = queue._xf_pending")
        clear_pos = src.index("queue._xf_pending = None")
        get_source_pos = src.index("self.audio.get_source(")
        assert read_pos < clear_pos < get_source_pos

    def test_filter_active_reuses_resolved_local_not_rederived(self):
        """filter_active must be fed from the already-resolved ffmpeg_filter
        local (:666), never a re-derived queue.active_filter != "off" check
        at the crossfade call site."""
        src = _play_track_source()
        start = src.index("decide_crossfade(")
        end = src.index("# Increment generation")
        block = src[start:end]
        assert "filter_active=ffmpeg_filter is not None" in block
        assert 'queue.active_filter != "off"' not in block


def _on_track_end_source_for_crossfade() -> str:
    return inspect.getsource(MusicCog._on_track_end)


class TestCrossfadeHandoffWiring:
    def test_handoff_reads_position_seconds_not_duration(self):
        """The cut position must come from TruncatingSource.position_seconds
        (an in-process frame count), never from Track.duration_seconds
        (YouTube metadata, attacker-influenceable — RESEARCH landmine #5).
        Comment-stripped so an explanatory comment mentioning the banned
        token in prose can't false-positive (matches this file's existing
        convention)."""
        src = _on_track_end_source_for_crossfade()
        non_comment = "\n".join(_non_comment_lines(src))
        assert "position_seconds" in non_comment
        assert "duration_seconds" not in non_comment

    def test_truncator_cleared_on_every_path(self):
        """queue._xf_truncator must be nulled unconditionally — not only
        inside the cut-short branch — so a naturally-ended truncator never
        lingers into the next track."""
        src = _on_track_end_source_for_crossfade()
        assert "queue._xf_truncator = None" in src
        # The clear must not be nested inside the cut_short conditional body
        # — it is its own statement at the same indent as the `if`.
        lines = src.splitlines()
        if_line = next(i for i, ln in enumerate(lines) if "queue._xf_truncator is not None" in ln and "if " in ln)
        clear_line = next(i for i, ln in enumerate(lines) if "queue._xf_truncator = None" in ln)
        if_indent = len(lines[if_line]) - len(lines[if_line].lstrip())
        clear_indent = len(lines[clear_line]) - len(lines[clear_line].lstrip())
        assert clear_indent == if_indent, "the unconditional clear must not be nested inside the `if` body"

    def test_handoff_precedes_advance(self):
        """The outgoing track must be captured and the handoff computed
        BEFORE advance() moves current_index — advance() changes what
        get_current() would return."""
        src = _on_track_end_source_for_crossfade()
        handoff_pos = src.index("queue._xf_pending = (current,")
        advance_pos = src.index("queue.advance()")
        assert handoff_pos < advance_pos

    def test_on_track_end_still_dispatches_on_track_end_action_with_crossfade_present(self):
        """The crossfade handoff is an addition ahead of the existing pure
        dispatch, never a replacement (Phase 10 D-02) — mirrors the Phase 26
        radio-lookahead precedent of an additional gate, not a new
        TrackEndAction member."""
        src = _on_track_end_source_for_crossfade()
        assert "decide_on_track_end(" in src
        assert "TrackEndAction." in src


class TestCrossfadeSkipChokePointUntouched:
    """D-12c/D-12d: a skip already cuts the fade dead for free via
    _do_skip -> _play_track -> voice_client.stop() (which tears down
    CrossfadeSource's owned decoders). No edit to _try_skip, _do_skip, or
    the vote cache is permitted in this plan — asserted by an empty diff."""

    def test_try_skip_has_no_crossfade_references(self):
        src = inspect.getsource(MusicCog._try_skip)
        assert "crossfade" not in src.lower()
        assert "_xf_" not in src

    def test_do_skip_has_no_crossfade_references(self):
        src = inspect.getsource(MusicCog._do_skip)
        assert "crossfade" not in src.lower()
        assert "_xf_" not in src
