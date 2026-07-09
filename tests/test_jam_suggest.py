"""Source-assertion regression tests for /jam suggest (BRAIN-03, D-06/D-07) — plan 14-05.

No live Discord/DB/Gemini/YouTube path — these use `inspect.getsource` on
`LibraryCog.jam_suggest` (and, from Task 2, the propose-and-confirm view) to
lock in the D-06 seed-from-existing-tracks contract, the BRAIN-03 hard
validation-gate requirement, and the D-07 propose-and-confirm / snapshot-
untouched-until-confirm contract. Mirrors the tests/test_discover.py
`inspect.getsource` convention (plan 14-04).
"""

from __future__ import annotations

import inspect

from cogs.library import JamSuggestConfirmView, LibraryCog


def _jam_suggest_source() -> str:
    # @jam.command wraps the method in an app_commands.Command; the original
    # coroutine is reachable via .callback (same shape as app_commands.command,
    # confirmed in tests/test_discover.py for MusicCog.discover).
    return inspect.getsource(LibraryCog.jam_suggest.callback)


def _confirm_view_class_source() -> str:
    return inspect.getsource(JamSuggestConfirmView)


def _confirm_button_source() -> str:
    # discord.ui.button decorates the function in place (unlike app_commands.command,
    # which wraps it in a separate Command object) — directly inspectable, same as
    # DiscoverQueueView.queue_button in tests/test_discover.py.
    return inspect.getsource(JamSuggestConfirmView.confirm_button)


def _cancel_button_source() -> str:
    return inspect.getsource(JamSuggestConfirmView.cancel_button)


# ---------------------------------------------------------------------------
# Task 1 — seed -> generate -> validate
# ---------------------------------------------------------------------------


class TestJamSuggestExists:
    def test_jam_suggest_method_exists(self):
        assert hasattr(LibraryCog, "jam_suggest")


class TestJamSuggestSourceGrounding:
    def test_calls_get_jam(self):
        assert "get_jam(" in _jam_suggest_source()

    def test_calls_build_jam_suggestion_prompt(self):
        assert "build_jam_suggestion_prompt(" in _jam_suggest_source()

    def test_calls_parse_suggestions(self):
        assert "parse_suggestions(" in _jam_suggest_source()

    def test_calls_validate_youtube_match(self):
        assert "validate_youtube_match(" in _jam_suggest_source()

    def test_does_not_use_difflib(self):
        """BRAIN-03 / D-12: reuse validate_youtube_match verbatim — no second
        similarity implementation, no difflib anywhere in the file."""
        import cogs.library as library_module

        assert "import difflib" not in inspect.getsource(library_module)


class TestJamSuggestNonExistentJamGuard:
    def test_non_existent_jam_branch_present(self):
        src = _jam_suggest_source()
        assert "if existing is None:" in src

    def test_non_existent_jam_branch_returns_before_save_jam(self):
        """D-06: a jam that doesn't exist yet has nothing to riff on — the
        non-existent-jam branch must return before any save_jam call. Since
        jam_suggest itself never calls save_jam directly (that only happens
        inside the Task 2 confirm view, gated on user confirmation), this
        also verifies save_jam is unreachable from this function body."""
        src = _jam_suggest_source()
        assert "save_jam(" not in src
        guard_idx = src.index("if existing is None:")
        guard_block = src[guard_idx : src.index("\n\n", guard_idx)]
        assert "return" in guard_block


class TestJamSuggestNoneSurviveGuard:
    def test_none_survive_branch_present(self):
        src = _jam_suggest_source()
        assert "if not validated_candidates:" in src

    def test_none_survive_branch_returns_before_save_jam(self):
        """D-07: if nothing survives validation, Dex says so in character and
        the jam snapshot is left untouched — no save_jam call reachable."""
        src = _jam_suggest_source()
        assert "save_jam(" not in src
        guard_idx = src.index("if not validated_candidates:")
        guard_block = src[guard_idx : src.index("\n\n", guard_idx)]
        assert "return" in guard_block

    def test_none_survive_guard_comes_after_validation_loop(self):
        """The none-survive guard must be checked AFTER the per-suggestion
        validation loop has had a chance to populate validated_candidates."""
        src = _jam_suggest_source()
        loop_idx = src.index("for suggestion in suggestions:")
        guard_idx = src.index("if not validated_candidates:")
        assert guard_idx > loop_idx


class TestJamSuggestValidationLoop:
    def test_iterates_all_suggestions(self):
        assert "for suggestion in suggestions:" in _jam_suggest_source()

    def test_uses_async_search(self):
        assert "async_search(" in _jam_suggest_source()

    def test_drops_suggestion_with_no_passing_candidate(self):
        """A suggestion with no validated candidate is dropped (continue),
        never offered — matches the try_auto_queue validation-loop shape."""
        src = _jam_suggest_source()
        assert "if validated is None:" in src
        idx = src.index("if validated is None:")
        block = src[idx : src.index("\n\n", idx)]
        assert "continue" in block


class TestJamSuggestImports:
    def test_imports_validate_youtube_match_from_logic_autoqueue(self):
        import cogs.library as library_module

        assert library_module.validate_youtube_match is not None

    def test_imports_parse_suggestions_from_cogs_ai(self):
        import cogs.ai as ai_module
        import cogs.library as library_module

        assert library_module.parse_suggestions is ai_module.parse_suggestions

    def test_imports_build_jam_suggestion_prompt(self):
        import cogs.library as library_module

        assert library_module.build_jam_suggestion_prompt is not None


# ---------------------------------------------------------------------------
# Task 2 — propose-and-confirm view + snapshot append (D-07)
# ---------------------------------------------------------------------------


class TestJamSuggestConfirmViewIsOneShot:
    def test_view_class_exists(self):
        assert JamSuggestConfirmView is not None

    def test_view_uses_finite_timeout_not_none(self):
        """This is a one-shot confirm view — it must NOT use timeout=None,
        which is reserved for NowPlayingView's persistent, setup_hook-registered
        controller."""
        src = _confirm_view_class_source()
        assert "timeout=None" not in src
        assert "def __init__" in src
        assert "timeout: float" in src or "timeout=60" in src or "timeout: float = 60.0" in src

    def test_view_not_registered_in_setup_hook(self):
        """JamSuggestConfirmView must never appear in bot.py's setup_hook —
        unlike NowPlayingView, it is not a persistent view."""
        import bot as bot_module

        setup_hook_src = inspect.getsource(bot_module.DexterBot.setup_hook)
        assert "JamSuggestConfirmView" not in setup_hook_src


class TestJamSuggestConfirmCallback:
    def test_confirm_calls_save_jam(self):
        assert "save_jam(" in _confirm_button_source()

    def test_confirm_reloads_snapshot_via_get_jam(self):
        """Defensive reload against a concurrent edit between propose and confirm."""
        assert "get_jam(" in _confirm_button_source()

    def test_confirm_appends_to_existing_snapshot(self):
        """Append semantics identical to /jam add — the reloaded existing
        snapshot is extended, never replaced wholesale."""
        src = _confirm_button_source()
        assert "existing" in src
        assert "snapshot.append(" in src or "snapshot +" in src or ".append(" in src

    def test_confirm_checks_duration_cap(self):
        assert "MAX_SONG_DURATION_SECONDS" in _confirm_button_source()


class TestJamSuggestCancelCallback:
    def test_cancel_does_not_call_save_jam(self):
        assert "save_jam(" not in _cancel_button_source()


class TestJamSuggestAttachesViewOnlyOnSurvivorsPath:
    def test_view_attached_after_none_survive_guard(self):
        """JamSuggestConfirmView is constructed textually after the
        none-survive cold-start guard — i.e. only reachable once at least one
        candidate survived validation."""
        src = _jam_suggest_source()
        guard_idx = src.index("if not validated_candidates:")
        view_construction_idx = src.index("JamSuggestConfirmView(")
        assert view_construction_idx > guard_idx

    def test_view_attached_after_non_existent_jam_guard(self):
        src = _jam_suggest_source()
        guard_idx = src.index("if existing is None:")
        view_construction_idx = src.index("JamSuggestConfirmView(")
        assert view_construction_idx > guard_idx

    def test_cold_start_paths_do_not_construct_view(self):
        """Neither early-return branch (non-existent jam, none-survive) can
        reach JamSuggestConfirmView construction — both return before it."""
        src = _jam_suggest_source()
        non_existent_guard_idx = src.index("if existing is None:")
        non_existent_return_idx = src.index("return", non_existent_guard_idx)
        view_construction_idx = src.index("JamSuggestConfirmView(")
        assert non_existent_return_idx < view_construction_idx
