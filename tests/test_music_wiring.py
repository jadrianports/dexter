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

import cogs.music as music_module
from cogs.music import MusicCog, NowPlayingView


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

    def test_do_skip_still_records_via_mark_song_skipped(self):
        """The existing recording path is intact — not accidentally removed
        during the D-15 unification."""
        assert "mark_song_skipped(" in _do_skip_source()
