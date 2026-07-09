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
