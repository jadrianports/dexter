"""Source-assertion regression tests for /discover (BRAIN-02, D-04/D-05) — plan 14-04.

No live Discord/DB/Gemini path — these use `inspect.getsource` on
`MusicCog.discover` (and, from Task 2, the confirm-to-queue view) to lock in
the D-04 firewall (SQL picks, Gemini voice-only, never parsed) and the D-05
cold-start / confirm-first contract, mirroring the Phase 14-03 source-assertion
convention in tests/test_autoqueue_wiring.py.
"""

from __future__ import annotations

import inspect

import personality.responses as responses_module
from cogs.music import MusicCog


def _discover_source() -> str:
    # app_commands.command wraps the method in a discord.app_commands.Command;
    # the original coroutine is reachable via .callback.
    return inspect.getsource(MusicCog.discover.callback)


# ---------------------------------------------------------------------------
# Task 1 — anchor -> adjacency -> commentary -> cold-start
# ---------------------------------------------------------------------------


class TestDiscoverNoHistoryResponsePool:
    def test_discover_no_history_exists(self):
        assert hasattr(responses_module, "DISCOVER_NO_HISTORY")

    def test_discover_no_history_is_nonempty_list_of_str(self):
        pool = responses_module.DISCOVER_NO_HISTORY
        assert isinstance(pool, list)
        assert len(pool) > 0
        assert all(isinstance(item, str) for item in pool)


class TestDiscoverSqlDerivedPicks:
    def test_calls_get_user_top_artist(self):
        assert "get_user_top_artist(" in _discover_source()

    def test_calls_get_artist_cooccurrence(self):
        assert "get_artist_cooccurrence(" in _discover_source()

    def test_calls_build_discover_commentary_prompt(self):
        assert "build_discover_commentary_prompt(" in _discover_source()

    def test_does_not_call_parse_suggestions(self):
        """D-04 firewall: Gemini's reply is plain commentary text, never parsed
        into a recommendation — /discover must never import/call
        parse_suggestions."""
        assert "parse_suggestions" not in _discover_source()


class TestDiscoverColdStart:
    def test_cold_start_message_used(self):
        assert "pick_random(DISCOVER_NO_HISTORY)" in _discover_source()

    def test_two_distinct_empty_guards(self):
        """D-05: both an empty-anchor guard and an empty-adjacency guard exist,
        each independently returning the cold-start message rather than raising."""
        src = _discover_source()
        assert src.count("pick_random(DISCOVER_NO_HISTORY)") == 2

    def test_empty_anchor_guard_present(self):
        src = _discover_source()
        assert "if not anchor_rows:" in src

    def test_empty_adjacency_guard_present(self):
        src = _discover_source()
        assert "if not adjacent_rows:" in src
