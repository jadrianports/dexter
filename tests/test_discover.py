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
from cogs.music import DiscoverQueueView, MusicCog


def _discover_source() -> str:
    # app_commands.command wraps the method in a discord.app_commands.Command;
    # the original coroutine is reachable via .callback.
    return inspect.getsource(MusicCog.discover.callback)


def _discover_view_class_source() -> str:
    return inspect.getsource(DiscoverQueueView)


def _discover_view_button_source() -> str:
    # Unlike app_commands.command, discord.ui.button decorates the function
    # in place (setting __discord_ui_model_type__) rather than wrapping it in
    # a separate Command object, so the plain function is directly inspectable.
    return inspect.getsource(DiscoverQueueView.queue_button)


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


# ---------------------------------------------------------------------------
# Task 2 — confirm-to-queue view (D-05 confirm-first)
# ---------------------------------------------------------------------------


class TestDiscoverQueueViewIsOneShot:
    def test_view_class_exists(self):
        assert DiscoverQueueView is not None

    def test_view_uses_finite_timeout_not_none(self):
        """This view is a one-shot confirm — it must NOT use timeout=None
        (that's reserved for NowPlayingView's persistent, setup_hook-registered
        controller)."""
        src = _discover_view_class_source()
        assert "timeout=None" not in src
        assert "def __init__" in src
        assert "timeout: float" in src or "timeout=60" in src or "timeout: float = 60.0" in src

    def test_view_not_registered_in_setup_hook(self):
        """DiscoverQueueView must never appear in bot.py's setup_hook —
        unlike NowPlayingView, it is not a persistent view."""
        import bot as bot_module

        setup_hook_src = inspect.getsource(bot_module.DexterBot.setup_hook)
        assert "DiscoverQueueView" not in setup_hook_src


class TestDiscoverQueueViewButtonCallback:
    def test_button_calls_async_search(self):
        assert "async_search(" in _discover_view_button_source()

    def test_button_calls_async_extract(self):
        assert "async_extract(" in _discover_view_button_source()

    def test_button_calls_queue_add(self):
        assert "queue.add(" in _discover_view_button_source()

    def test_button_checks_duration_cap(self):
        assert "MAX_SONG_DURATION_SECONDS" in _discover_view_button_source()

    def test_button_never_uses_stale_queue_is_playing_gate(self):
        """Scar #2: the playback-start gate must key on the live voice-client
        state via should_start_playback, never the stale `queue.is_playing`
        flag."""
        src = _discover_view_button_source()
        assert "should_start_playback(" in src
        assert "not queue.is_playing" not in src


class TestDiscoverAttachesViewOnlyWhenAdjacencyNonEmpty:
    def test_view_attached_after_adjacency_check(self):
        """DiscoverQueueView is constructed textually after the empty-adjacency
        cold-start guard, i.e. only reachable once adjacent_rows is non-empty."""
        src = _discover_source()
        adjacency_guard_idx = src.index("if not adjacent_rows:")
        view_construction_idx = src.index("DiscoverQueueView(")
        assert view_construction_idx > adjacency_guard_idx

    def test_view_seeded_with_top_adjacent_artist(self):
        src = _discover_source()
        assert "adjacent_artists[0]" in src

    def test_cold_start_paths_do_not_construct_view(self):
        """Both cold-start `return` statements occur before any DiscoverQueueView
        construction — the view must never appear on those early-return paths."""
        src = _discover_source()
        first_cold_start_idx = src.index("if not anchor_rows:")
        view_construction_idx = src.index("DiscoverQueueView(")
        assert view_construction_idx > first_cold_start_idx
