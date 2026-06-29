"""Tests for personality prompt builders."""

from personality.prompts import (
    build_chat_prompt,
    build_recommendation_prompt,
    DEXTER_SYSTEM_PROMPT,
    MOOD_CONTEXTS,
)


class TestBuildChatPrompt:
    def test_includes_mood_context(self):
        result = build_chat_prompt(mood="tired", user_summary=None, seasonal="")
        assert MOOD_CONTEXTS["tired"] in result

    def test_includes_user_summary_when_provided(self):
        summary = "User 'jake': 50 songs. Top: The Weeknd (20)."
        result = build_chat_prompt(mood="normal", user_summary=summary, seasonal="")
        assert summary in result

    def test_excludes_user_section_when_none(self):
        result = build_chat_prompt(mood="normal", user_summary=None, seasonal="")
        assert "No data on this user yet" in result

    def test_includes_seasonal_when_provided(self):
        seasonal = "It's December. Christmas music is your nemesis."
        result = build_chat_prompt(mood="normal", user_summary=None, seasonal=seasonal)
        assert seasonal in result

    def test_empty_seasonal_no_artifact(self):
        result = build_chat_prompt(mood="normal", user_summary=None, seasonal="")
        assert "\n\n\n" not in result

    def test_fumes_mood(self):
        result = build_chat_prompt(mood="fumes", user_summary=None, seasonal="")
        assert MOOD_CONTEXTS["fumes"] in result

    def test_base_prompt_present(self):
        result = build_chat_prompt(mood="normal", user_summary=None, seasonal="")
        assert "sarcastic" in result.lower()


class TestDexterSystemPromptStructure:
    """Assertions that the rewritten DEXTER_SYSTEM_PROMPT meets D-06 requirements."""

    def test_contains_all_format_placeholders(self):
        """build_chat_prompt depends on all five placeholder tokens."""
        for token in [
            "{max_length}", "{mood_context}", "{user_context}",
            "{seasonal_context}", "{memory_context}",
        ]:
            assert token in DEXTER_SYSTEM_PROMPT, (
                f"Missing placeholder {token!r} in DEXTER_SYSTEM_PROMPT"
            )

    def test_contains_at_least_four_dexter_exemplar_markers(self):
        """D-06: few-shot section requires ≥4 DEXTER: exemplar markers."""
        count = DEXTER_SYSTEM_PROMPT.count("DEXTER:")
        assert count >= 4, (
            f"Expected ≥4 'DEXTER:' markers in system prompt; found {count}"
        )

    def test_contains_canonical_formula_line(self):
        """The locked canonical exemplar from CONTEXT.md must be present."""
        assert "impressive commitment to being boring" in DEXTER_SYSTEM_PROMPT

    def test_banned_mode_language_present(self):
        """Explicit banned-mode rules must be stated in the prompt."""
        lower = DEXTER_SYSTEM_PROMPT.lower()
        # At least one of the banned-mode markers must appear
        assert any(
            phrase in lower
            for phrase in ["banned", "never reference", "do not", "fourth wall", "self-deprecat"]
        ), "Banned-mode rules not found in DEXTER_SYSTEM_PROMPT"

    def test_build_chat_prompt_no_unfilled_placeholders(self):
        """build_chat_prompt must not leave any of the five known keys unfilled."""
        result = build_chat_prompt("normal", "top artist: drake", "It's December.")
        assert result, "build_chat_prompt returned empty string"
        for key in ["max_length", "mood_context", "user_context", "seasonal_context", "memory_context"]:
            assert "{" + key + "}" not in result, (
                f"Unfilled placeholder {{{key}}} in build_chat_prompt output"
            )

    def test_build_chat_prompt_no_key_error(self):
        """build_chat_prompt must not raise KeyError on valid inputs."""
        # Would raise KeyError if any literal { } in the prompt are unescaped
        try:
            result = build_chat_prompt("normal", None, "")
            assert result
        except KeyError as e:
            raise AssertionError(
                f"build_chat_prompt raised KeyError: {e} — check for unescaped braces in DEXTER_SYSTEM_PROMPT"
            )


class TestBuildChatPromptMemories:
    """Tests for the memories= kwarg (Phase 11 / MEM-06)."""

    def test_memories_none_byte_identical(self):
        """memories=None must produce byte-identical output to omitting the arg entirely."""
        without_arg = build_chat_prompt("normal", "top: drake", "It is December.")
        with_none = build_chat_prompt("normal", "top: drake", "It is December.", memories=None)
        assert without_arg == with_none, (
            "memories=None changed the output — byte-identity broken (T-11-06d)"
        )

    def test_memories_empty_list_byte_identical(self):
        """memories=[] (falsy) must also produce byte-identical output."""
        without_arg = build_chat_prompt("normal", "top: drake", "It is December.")
        with_empty = build_chat_prompt("normal", "top: drake", "It is December.", memories=[])
        assert without_arg == with_empty, (
            "memories=[] changed the output — byte-identity broken"
        )

    def test_memory_block_rendered_fact_present(self):
        """memories=[...] must include the fact text in the rendered prompt."""
        result = build_chat_prompt(
            "normal", "top: drake", "",
            memories=["swore he was done with the killers"],
        )
        assert "killers" in result, "Memory fact not rendered in prompt"

    def test_memory_block_rendered_user_context_anchor(self):
        """Numbers-from-SQL instruction must reference USER CONTEXT (T-11-06b)."""
        result = build_chat_prompt(
            "normal", "top: drake", "",
            memories=["swore he was done with the killers"],
        )
        assert "USER CONTEXT" in result, (
            "USER CONTEXT accuracy anchor missing from memory block"
        )

    def test_memory_block_rendered_never_instruction(self):
        """The 'never from memories' accuracy firewall must be present (D-06)."""
        result = build_chat_prompt(
            "normal", "top: drake", "",
            memories=["swore he was done with the killers"],
        )
        assert "never" in result.lower(), (
            "'never from memories' accuracy instruction missing"
        )

    def test_memories_none_no_triple_newline(self):
        """memories=None with non-empty seasonal must not produce triple-newlines."""
        result = build_chat_prompt("normal", None, "It is December.", memories=None)
        assert "\n\n\n" not in result, "Triple-newline artifact with memories=None"

    def test_memories_block_no_triple_newline(self):
        """memories=[...] with non-empty seasonal must not produce triple-newlines."""
        result = build_chat_prompt(
            "normal", None, "It is December.",
            memories=["swore he was done with the killers"],
        )
        assert "\n\n\n" not in result, "Triple-newline artifact with memories block"


class TestBuildRecommendationPrompt:
    def test_includes_song_list(self):
        songs = [
            {"title": "Blinding Lights", "artist": "The Weeknd"},
            {"title": "Tadow", "artist": "Masego"},
        ]
        result = build_recommendation_prompt(songs)
        assert "Blinding Lights" in result
        assert "Masego" in result

    def test_asks_for_json(self):
        songs = [{"title": "Test", "artist": "Artist"}]
        result = build_recommendation_prompt(songs)
        assert "JSON" in result or "json" in result

    def test_asks_for_three_songs(self):
        songs = [{"title": "Test", "artist": "Artist"}]
        result = build_recommendation_prompt(songs)
        assert "3" in result
