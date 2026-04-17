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
