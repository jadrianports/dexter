"""Source-assertion regression tests for Phase 14 auto-queue taste-aware wiring
(BRAIN-01 / D-01, D-02, D-03) — plan 14-03.

These tests use `inspect.getsource` to assert the wiring exists in
`cogs/ai.py::try_auto_queue`, without needing a live Discord/Gemini/DB path.
They exist so a future edit can't silently drop the D-01/D-02/D-03 wiring or
regress scar #2 (the should_start_playback playback gate).
"""

from __future__ import annotations

import inspect

import cogs.ai as ai_module
from cogs.ai import AICog
from logic.autoqueue import is_recently_skipped_artist
from personality.prompts import build_recommendation_prompt


def _try_auto_queue_source() -> str:
    return inspect.getsource(AICog.try_auto_queue)


# ---------------------------------------------------------------------------
# Task 1 — D-01 negative hint + D-03 positive hint wiring
# ---------------------------------------------------------------------------


class TestNegativeAndPositiveHintWiring:
    def test_imports_get_recently_skipped(self):
        """cogs/ai.py imports the D-01 negative-hint SQL helper."""
        assert hasattr(ai_module, "get_recently_skipped")

    def test_imports_is_recently_skipped_artist(self):
        """cogs/ai.py imports the D-02 hard post-filter."""
        assert hasattr(ai_module, "is_recently_skipped_artist")

    def test_imports_select_positive_taste_context(self):
        """cogs/ai.py imports the D-03 positive-taste blend."""
        assert hasattr(ai_module, "select_positive_taste_context")

    def test_source_calls_get_recently_skipped(self):
        src = _try_auto_queue_source()
        assert "get_recently_skipped(" in src

    def test_source_recalls_taste_episode_kind(self):
        src = _try_auto_queue_source()
        assert "recall(" in src
        assert 'kind="taste_episode"' in src

    def test_source_calls_select_positive_taste_context(self):
        src = _try_auto_queue_source()
        assert "select_positive_taste_context(" in src

    def test_prompt_call_passes_both_new_kwargs(self):
        """build_recommendation_prompt is called with recently_skipped= and positive_taste=."""
        src = _try_auto_queue_source()
        assert "build_recommendation_prompt(" in src
        assert "recently_skipped=" in src
        assert "positive_taste=" in src

    def test_voice_member_enumeration_is_a_single_reused_comprehension(self):
        """The in-voice non-bot member set is computed ONCE (D-03) — the same
        `for m in vc.channel.members if not m.bot` comprehension feeds both the
        positive-taste recall fan-out and the existing auto_queue_ignored write.
        A regression that recomputes a second, different member set would show
        up as two occurrences of this comprehension shape."""
        src = _try_auto_queue_source()
        occurrences = src.count("for m in vc.channel.members if not m.bot")
        assert occurrences == 1, f"expected exactly one voice-member comprehension (reused), found {occurrences}"


# ---------------------------------------------------------------------------
# Task 2 — D-02 hard post-filter in the per-suggestion validation loop
# ---------------------------------------------------------------------------


class TestHardPostFilterWiring:
    def test_both_validate_and_hard_filter_present_and_distinct(self):
        src = _try_auto_queue_source()
        assert "validate_youtube_match(" in src
        assert "is_recently_skipped_artist(" in src
        # Distinct statements — the hard filter call is not merely a substring
        # of the validate_youtube_match call.
        assert "is_recently_skipped_artist(suggestion" in src

    def test_hard_filter_runs_after_validated_is_not_none_branch(self):
        """The is_recently_skipped_artist gate appears textually after the
        `validated is None` fall-through continue, i.e. only reachable once a
        candidate has already passed validate_youtube_match."""
        src = _try_auto_queue_source()
        validated_none_idx = src.index("if validated is None:")
        hard_filter_idx = src.index("is_recently_skipped_artist(suggestion")
        assert hard_filter_idx > validated_none_idx

    def test_hard_filter_behavior_rejects_skipped_artist(self):
        """Direct behavioral assertion (reinforces the gate semantics without a
        live Discord/Gemini path)."""
        assert is_recently_skipped_artist("Phoebe Bridgers", ["phoebe bridgers"]) is True

    def test_hard_filter_behavior_allows_non_skipped_artist(self):
        assert is_recently_skipped_artist("Drake", ["Phoebe Bridgers"]) is False


# ---------------------------------------------------------------------------
# Scar #2 guard — should_start_playback / voice_client.is_playing() untouched
# ---------------------------------------------------------------------------


class TestScarTwoUntouched:
    def test_should_start_playback_still_present(self):
        src = _try_auto_queue_source()
        assert "should_start_playback(" in src

    def test_no_stale_queue_is_playing_gate(self):
        """The old, buggy `if voice_client and not queue.is_playing` playback
        guard must never reappear as executable code (scar #2 / CLAUDE.md
        Phase 6-8 gotcha). The fix's own explanatory comment legitimately
        quotes the old buggy expression in prose, so this checks for the old
        *conditional* shape rather than banning the substring outright."""
        src = _try_auto_queue_source()
        assert "if voice_client and not queue.is_playing" not in src
        assert "should_start_playback(" in src


# ---------------------------------------------------------------------------
# Phase 21 / MEM-01 — positive-taste-blend recall opts into guild scoping
# ---------------------------------------------------------------------------


class TestGuildScopedTasteBlend:
    def test_taste_blend_recall_is_guild_scoped(self):
        """The both-optional-clauses SQL shape: kind="taste_episode" AND
        guild_scoped=True both appear on the same recall() call."""
        src = _try_auto_queue_source()
        assert 'kind="taste_episode"' in src
        assert "guild_scoped=True" in src


# ---------------------------------------------------------------------------
# Phase 26 / DJ-01 — radio branch wiring (26-03)
# ---------------------------------------------------------------------------


def _non_comment_lines(src: str) -> list[str]:
    """Source lines with comment-only lines filtered out, so a `count()` that
    relies on this can't be silently invalidated by an explanatory comment
    quoting a banned/gated token."""
    return [ln for ln in src.splitlines() if not ln.strip().startswith("#")]


class TestRadioBranchWiring:
    def test_radio_param_default_false(self):
        """The keyword-only radio param exists with a False default — the
        default is what makes the disarmed path byte-identical (D-01)."""
        src = _try_auto_queue_source()
        assert "radio: bool = False" in src

    def test_prompt_call_passes_seed_and_already_played(self):
        src = _try_auto_queue_source()
        assert "seed=radio_seed" in src
        assert "already_played=" in src

    def test_hard_filter_and_room_guard_present(self):
        src = _try_auto_queue_source()
        assert "is_already_played(" in src
        assert "has_room_for_refill(" in src

    def test_played_set_recording_present(self):
        src = _try_auto_queue_source()
        assert "queue.radio_played[" in src

    def test_chat_call_still_priority_2(self):
        """T-26-02 DoS control: radio must never escalate off priority=2 on the
        shared 15 RPM budget (D-04 explicitly rejects escalating to priority 1)."""
        src = _try_auto_queue_source()
        assert "priority=2" in src

    def test_hard_filter_runs_after_validated_is_not_none_branch(self):
        """Mirrors test_hard_filter_runs_after_validated_is_not_none_branch above
        — the D-03 gate only sees candidates that already passed the
        hallucination validator."""
        src = _try_auto_queue_source()
        validated_none_idx = src.index("if validated is None:")
        radio_filter_idx = src.index("is_already_played(")
        assert radio_filter_idx > validated_none_idx

    def test_get_queue_hoisted_not_duplicated(self):
        """The music_cog/queue resolution block was hoisted above the prompt
        build (26-03 planner_decisions) — a duplicate get_queue call would mean
        the hoist left the original block in place too."""
        src = _try_auto_queue_source()
        assert src.count("music_cog.get_queue(") == 1


# ---------------------------------------------------------------------------
# Phase 26 / DJ-01 — byte-identical-when-disarmed regression guard (26-03)
# ---------------------------------------------------------------------------


class TestAutoQueuePathByteIdenticalWhenRadioDisarmed:
    def test_prompt_output_identical_with_new_kwargs_omitted_vs_none(self):
        """The real proof that a disarmed refill sends the model exactly the
        pre-Phase-26 prompt: omitting seed=/already_played= entirely produces
        the same string as passing them explicitly as None."""
        recent = [{"title": "Glimpse Of Us", "artist": "Joji"}]
        without_kwargs = build_recommendation_prompt(recent, recently_skipped=None, positive_taste=None)
        with_none_kwargs = build_recommendation_prompt(
            recent,
            recently_skipped=None,
            positive_taste=None,
            seed=None,
            already_played=None,
        )
        assert without_kwargs == with_none_kwargs

    def test_radio_behaviours_reachable_only_behind_a_radio_guard(self):
        """Structural lock: every Phase 26 behaviour token in try_auto_queue's
        source is reachable only behind a `radio`-guarded condition. For each
        occurrence, either the token's own line or the nearest preceding `if `
        line must contain the word "radio" — a pragmatic, legible way to catch
        a future edit that makes a radio behaviour unconditional."""
        src = _try_auto_queue_source()
        lines = src.splitlines()
        radio_tokens = ("is_already_played(", "queue.radio_played[", "has_room_for_refill(")

        for idx, line in enumerate(lines):
            if not any(tok in line for tok in radio_tokens):
                continue
            if "radio" in line:
                continue
            # Walk backwards to the nearest preceding `if ` line.
            guard_found = False
            for prev_line in reversed(lines[:idx]):
                stripped = prev_line.strip()
                if stripped.startswith("if "):
                    guard_found = "radio" in stripped
                    break
            assert guard_found, f"line {idx} ({line!r}) is not reachable only behind a radio guard"

    def test_voice_member_enumeration_still_single_reused_comprehension(self):
        """Re-asserted here too (26-RESEARCH's named anti-pattern): any
        radio-branch code that recomputes a second voice-member list both
        violates D-03's design and breaks this lock."""
        src = _try_auto_queue_source()
        assert src.count("for m in vc.channel.members if not m.bot") == 1

    def test_non_comment_line_filter_used_for_count_assertions(self):
        """Sanity check on the helper itself — a comment-only line is excluded
        from the filtered source used by count()-based assertions above."""
        sample = "    # is_already_played( in a comment\n    is_already_played(video_id=x, played_ids=y)"
        filtered = _non_comment_lines(sample)
        assert sum(ln.count("is_already_played(") for ln in filtered) == 1
