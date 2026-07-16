"""Tests for personality prompt builders."""

from cogs.ai import parse_suggestions
from personality.prompts import (
    DEXTER_SYSTEM_PROMPT,
    MOOD_CONTEXTS,
    MUSIC_RECOMMENDATION_PROMPT,
    build_chat_prompt,
    build_discover_commentary_prompt,
    build_jam_suggestion_prompt,
    build_recommendation_prompt,
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
            "{max_length}",
            "{mood_context}",
            "{user_context}",
            "{seasonal_context}",
            "{memory_context}",
        ]:
            assert token in DEXTER_SYSTEM_PROMPT, f"Missing placeholder {token!r} in DEXTER_SYSTEM_PROMPT"

    def test_contains_at_least_four_dexter_exemplar_markers(self):
        """D-06: few-shot section requires ≥4 DEXTER: exemplar markers."""
        count = DEXTER_SYSTEM_PROMPT.count("DEXTER:")
        assert count >= 4, f"Expected ≥4 'DEXTER:' markers in system prompt; found {count}"

    def test_contains_canonical_formula_line(self):
        """The locked canonical exemplar from CONTEXT.md must be present."""
        assert "impressive commitment to being boring" in DEXTER_SYSTEM_PROMPT

    def test_banned_mode_language_present(self):
        """Explicit banned-mode rules must be stated in the prompt."""
        lower = DEXTER_SYSTEM_PROMPT.lower()
        # At least one of the banned-mode markers must appear
        assert any(
            phrase in lower for phrase in ["banned", "never reference", "do not", "fourth wall", "self-deprecat"]
        ), "Banned-mode rules not found in DEXTER_SYSTEM_PROMPT"

    def test_build_chat_prompt_no_unfilled_placeholders(self):
        """build_chat_prompt must not leave any of the five known keys unfilled."""
        result = build_chat_prompt("normal", "top artist: drake", "It's December.")
        assert result, "build_chat_prompt returned empty string"
        for key in ["max_length", "mood_context", "user_context", "seasonal_context", "memory_context"]:
            assert "{" + key + "}" not in result, f"Unfilled placeholder {{{key}}} in build_chat_prompt output"

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
        assert without_arg == with_none, "memories=None changed the output — byte-identity broken (T-11-06d)"

    def test_memories_empty_list_byte_identical(self):
        """memories=[] (falsy) must also produce byte-identical output."""
        without_arg = build_chat_prompt("normal", "top: drake", "It is December.")
        with_empty = build_chat_prompt("normal", "top: drake", "It is December.", memories=[])
        assert without_arg == with_empty, "memories=[] changed the output — byte-identity broken"

    def test_memory_block_rendered_fact_present(self):
        """memories=[...] must include the fact text in the rendered prompt."""
        result = build_chat_prompt(
            "normal",
            "top: drake",
            "",
            memories=["swore he was done with the killers"],
        )
        assert "killers" in result, "Memory fact not rendered in prompt"

    def test_memory_block_rendered_user_context_anchor(self):
        """Numbers-from-SQL instruction must reference USER CONTEXT (T-11-06b)."""
        result = build_chat_prompt(
            "normal",
            "top: drake",
            "",
            memories=["swore he was done with the killers"],
        )
        assert "USER CONTEXT" in result, "USER CONTEXT accuracy anchor missing from memory block"

    def test_memory_block_rendered_never_instruction(self):
        """The 'never from memories' accuracy firewall must be present (D-06)."""
        result = build_chat_prompt(
            "normal",
            "top: drake",
            "",
            memories=["swore he was done with the killers"],
        )
        assert "never" in result.lower(), "'never from memories' accuracy instruction missing"

    def test_memories_none_no_triple_newline(self):
        """memories=None with non-empty seasonal must not produce triple-newlines."""
        result = build_chat_prompt("normal", None, "It is December.", memories=None)
        assert "\n\n\n" not in result, "Triple-newline artifact with memories=None"

    def test_memories_block_no_triple_newline(self):
        """memories=[...] with non-empty seasonal must not produce triple-newlines."""
        result = build_chat_prompt(
            "normal",
            None,
            "It is December.",
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


class TestBuildRecommendationPromptPhase14Kwargs:
    """Phase 14 / BRAIN-01: recently_skipped= / positive_taste= kwargs (Pattern 1)."""

    RECENT = [
        {"title": "Blinding Lights", "artist": "The Weeknd"},
        {"title": "Tadow", "artist": "Masego"},
    ]

    def test_byte_identical_when_both_kwargs_omitted(self):
        """Omitting both new kwargs must equal the pre-Phase-14 .format() output."""
        lines = [f"- {s['title']} by {s['artist']}" for s in self.RECENT]
        pre_change_output = MUSIC_RECOMMENDATION_PROMPT.format(recent_songs="\n".join(lines))
        assert build_recommendation_prompt(self.RECENT) == pre_change_output

    def test_byte_identical_when_both_kwargs_none(self):
        without_kwargs = build_recommendation_prompt(self.RECENT)
        with_none_kwargs = build_recommendation_prompt(self.RECENT, recently_skipped=None, positive_taste=None)
        assert without_kwargs == with_none_kwargs

    def test_byte_identical_when_both_kwargs_empty_list(self):
        without_kwargs = build_recommendation_prompt(self.RECENT)
        with_empty_kwargs = build_recommendation_prompt(self.RECENT, recently_skipped=[], positive_taste=[])
        assert without_kwargs == with_empty_kwargs

    def test_recently_skipped_appends_avoid_block(self):
        result = build_recommendation_prompt(
            self.RECENT,
            recently_skipped=[{"title": "Song X", "artist": "Artist X"}],
        )
        assert "AVOID these" in result
        assert "Song X" in result
        assert "Artist X" in result

    def test_positive_taste_appends_room_tends_to_like_block(self):
        result = build_recommendation_prompt(
            self.RECENT,
            positive_taste=["keeps coming back to the killers"],
        )
        assert "THE ROOM TENDS TO LIKE" in result
        assert "keeps coming back to the killers" in result

    def test_both_blocks_present_together(self):
        result = build_recommendation_prompt(
            self.RECENT,
            recently_skipped=[{"title": "Song X", "artist": "Artist X"}],
            positive_taste=["keeps coming back to the killers"],
        )
        assert "AVOID these" in result
        assert "THE ROOM TENDS TO LIKE" in result


class TestBuildRecommendationPromptPhase26Kwargs:
    """Phase 26 / DJ-01: seed= / already_played= kwargs (D-02/D-03)."""

    RECENT = [
        {"title": "Blinding Lights", "artist": "The Weeknd"},
        {"title": "Tadow", "artist": "Masego"},
    ]

    def test_byte_identical_when_both_new_kwargs_omitted(self):
        """Omitting seed/already_played must equal the pre-Phase-26 two-kwarg call."""
        pre_change_output = build_recommendation_prompt(self.RECENT)
        assert build_recommendation_prompt(self.RECENT, seed=None, already_played=None) == pre_change_output

    def test_byte_identical_when_both_new_kwargs_none(self):
        without_kwargs = build_recommendation_prompt(self.RECENT)
        with_none_kwargs = build_recommendation_prompt(self.RECENT, seed=None, already_played=None)
        assert without_kwargs == with_none_kwargs

    def test_byte_identical_when_seed_empty_string_and_already_played_empty_list(self):
        """seed='' and already_played=[] (falsy-empty) render byte-identical to omitted,
        matching the recently_skipped/positive_taste falsy-empty convention."""
        without_kwargs = build_recommendation_prompt(self.RECENT)
        with_empty_kwargs = build_recommendation_prompt(self.RECENT, seed="", already_played=[])
        assert without_kwargs == with_empty_kwargs

    def test_seed_appends_anchor_text_with_raw_seed_verbatim(self):
        result = build_recommendation_prompt(self.RECENT, seed="daft punk")
        assert "daft punk" in result

    def test_already_played_renders_one_line_per_entry(self):
        result = build_recommendation_prompt(
            self.RECENT,
            already_played=["X by Y", "Z by W"],
        )
        assert "- X by Y" in result
        assert "- Z by W" in result

    def test_seed_and_already_played_present_together_with_existing_blocks(self):
        """A radio refill call can carry all four optional blocks at once; the
        seed anchor lands last (closest to the model's most recent attention)."""
        result = build_recommendation_prompt(
            self.RECENT,
            recently_skipped=[{"title": "Song X", "artist": "Artist X"}],
            positive_taste=["keeps coming back to the killers"],
            already_played=["X by Y"],
            seed="daft punk",
        )
        assert "AVOID these" in result
        assert "THE ROOM TENDS TO LIKE" in result
        assert "ALREADY PLAYED THIS SESSION" in result
        assert "- X by Y" in result
        assert "START FROM THIS AND DRIFT NATURALLY" in result
        assert "daft punk" in result
        # seed anchor is the LAST block appended
        assert result.rindex("daft punk") > result.rindex("ALREADY PLAYED THIS SESSION")


class TestBuildDiscoverCommentaryPrompt:
    """Phase 14 / BRAIN-02 / D-04 firewall: Gemini wraps SQL-supplied names only."""

    def test_includes_anchor_and_adjacent_artists(self):
        result = build_discover_commentary_prompt("Drake", ["Future", "21 Savage"])
        assert "Drake" in result
        assert "Future" in result
        assert "21 Savage" in result

    def test_instructs_no_invented_artists(self):
        result = build_discover_commentary_prompt("Drake", ["Future"])
        lower = result.lower()
        assert "do not invent" in lower or "not invent" in lower


class TestBuildJamSuggestionPrompt:
    """Phase 14 / BRAIN-03 / D-06: parse_suggestions-compatible {title, artist} contract."""

    def test_includes_existing_tracks_and_count(self):
        tracks = [
            {"title": "Blinding Lights", "artist": "The Weeknd"},
            {"title": "Tadow", "artist": "Masego"},
        ]
        result = build_jam_suggestion_prompt(tracks, 3)
        assert "Blinding Lights" in result
        assert "Masego" in result
        assert "3" in result

    def test_asks_for_json(self):
        result = build_jam_suggestion_prompt([{"title": "Test", "artist": "Artist"}], 2)
        assert "JSON" in result or "json" in result

    def test_parse_suggestions_round_trip(self):
        """A well-formed model reply matching this prompt's contract parses non-empty."""
        model_reply = (
            '[{"title": "Midnight City", "artist": "M83"}, {"title": "Redbone", "artist": "Childish Gambino"}]'
        )
        # Sanity: build the prompt (contract compatibility, not literal reply generation).
        build_jam_suggestion_prompt([{"title": "Existing", "artist": "Someone"}], 2)
        result = parse_suggestions(model_reply)
        assert result
        assert result == [
            {"title": "Midnight City", "artist": "M83"},
            {"title": "Redbone", "artist": "Childish Gambino"},
        ]
