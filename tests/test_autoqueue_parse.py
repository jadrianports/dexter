"""Tests for the robust auto-queue suggestion parser."""

from cogs.ai import parse_suggestions

VALID = [{"title": "Blinding Lights", "artist": "The Weeknd"},
         {"title": "Tadow", "artist": "Masego"}]


class TestParseSuggestions:
    def test_clean_array(self):
        assert parse_suggestions('[{"title":"Blinding Lights","artist":"The Weeknd"},'
                                 '{"title":"Tadow","artist":"Masego"}]') == VALID

    def test_json_fenced(self):
        text = '```json\n[{"title":"Blinding Lights","artist":"The Weeknd"},' \
               '{"title":"Tadow","artist":"Masego"}]\n```'
        assert parse_suggestions(text) == VALID

    def test_plain_fenced(self):
        text = '```\n[{"title":"Blinding Lights","artist":"The Weeknd"},' \
               '{"title":"Tadow","artist":"Masego"}]\n```'
        assert parse_suggestions(text) == VALID

    def test_leading_prose(self):
        text = 'Here are 3 songs for you:\n[{"title":"Blinding Lights","artist":"The Weeknd"},' \
               '{"title":"Tadow","artist":"Masego"}]'
        assert parse_suggestions(text) == VALID

    def test_trailing_prose_and_whitespace(self):
        text = '[{"title":"Blinding Lights","artist":"The Weeknd"},' \
               '{"title":"Tadow","artist":"Masego"}]\n\nEnjoy!  '
        assert parse_suggestions(text) == VALID

    def test_object_wrapped_array(self):
        text = '{"songs": [{"title":"Blinding Lights","artist":"The Weeknd"},' \
               '{"title":"Tadow","artist":"Masego"}]}'
        assert parse_suggestions(text) == VALID

    def test_drops_items_missing_fields(self):
        text = '[{"title":"Good","artist":"A"},{"title":"No Artist"},{"artist":"No Title"}]'
        assert parse_suggestions(text) == [{"title": "Good", "artist": "A"}]

    def test_malformed_returns_none(self):
        assert parse_suggestions("not json at all") is None

    def test_empty_returns_none(self):
        assert parse_suggestions("") is None

    def test_empty_array_returns_none(self):
        assert parse_suggestions("[]") is None
