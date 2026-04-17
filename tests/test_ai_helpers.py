"""Tests for AI cog helper functions."""

from cogs.ai import AICog


class TestParseSuggestions:
    def setup_method(self):
        self.cog = AICog.__new__(AICog)

    def test_parses_valid_json(self):
        response = '[{"title": "Song", "artist": "Artist"}]'
        result = self.cog._parse_suggestions(response)
        assert result == [{"title": "Song", "artist": "Artist"}]

    def test_parses_markdown_wrapped(self):
        response = '```json\n[{"title": "Song", "artist": "Artist"}]\n```'
        result = self.cog._parse_suggestions(response)
        assert result is not None
        assert result[0]["title"] == "Song"

    def test_returns_none_for_invalid(self):
        result = self.cog._parse_suggestions("not json at all")
        assert result is None

    def test_returns_none_for_missing_fields(self):
        result = self.cog._parse_suggestions('[{"title": "Song"}]')
        assert result is None

    def test_parses_three_suggestions(self):
        response = '[{"title": "A", "artist": "1"}, {"title": "B", "artist": "2"}, {"title": "C", "artist": "3"}]'
        result = self.cog._parse_suggestions(response)
        assert len(result) == 3
