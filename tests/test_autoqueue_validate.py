"""Unit tests for logic.autoqueue.validate_youtube_match (UX-04 / D-12).

Pure, sub-second — no Discord, no asyncio, no DB, no network.
"""

from __future__ import annotations

import pytest

from logic.autoqueue import _normalize_for_match, validate_youtube_match


# ---------------------------------------------------------------------------
# TestNormalizeForMatch — internal helper coverage
# ---------------------------------------------------------------------------


class TestNormalizeForMatch:
    def test_lowercases_and_strips_punct(self):
        result = _normalize_for_match("Hello, World!")
        assert "hello" in result
        assert "world" in result

    def test_drops_noise_tokens(self):
        result = _normalize_for_match("Official Video HD")
        assert "official" not in result
        assert "video" not in result
        assert "hd" not in result

    def test_drops_stop_words(self):
        result = _normalize_for_match("the quick brown fox")
        assert "the" not in result
        assert "quick" in result
        assert "brown" in result

    def test_drops_tokens_shorter_than_two_chars(self):
        # "b" and "c" are single-char — dropped; "do" is 2 chars — kept
        result = _normalize_for_match("b c do")
        assert "do" in result
        assert "b" not in result
        assert "c" not in result

    def test_punctuation_replaced_with_spaces(self):
        # "don't" should split into "don" and "t" — "t" dropped (1 char)
        result = _normalize_for_match("don't stop")
        assert "stop" in result
        assert "don" in result

    def test_empty_string_returns_empty_set(self):
        assert _normalize_for_match("") == set()


# ---------------------------------------------------------------------------
# TestValidateYoutubeMatch — accept/reject/noise behavior cases
# ---------------------------------------------------------------------------


class TestValidateYoutubeMatch:
    def test_accept_noise_stripped_title_and_artist(self):
        """Noise tokens ignored; both title+artist tokens present in YouTube title."""
        assert validate_youtube_match(
            "Taylor Swift - Shake It Off (Official Music Video)",
            "Shake It Off",
            "Taylor Swift",
        ) is True

    def test_reject_clear_mismatch(self):
        """Clear song+artist mismatch is rejected."""
        assert validate_youtube_match(
            "Rick Astley - Never Gonna Give You Up",
            "Bohemian Rhapsody",
            "Queen",
        ) is False

    def test_accept_with_noise_and_punct(self):
        """Noise tokens, punctuation, and brackets tolerated."""
        assert validate_youtube_match(
            "Arctic Monkeys - Do I Wanna Know? (Official Video) [HD]",
            "Do I Wanna Know",
            "Arctic Monkeys",
        ) is True

    def test_accept_short_artist(self):
        """2-char minimum keeps short artists like 'SZA'."""
        assert validate_youtube_match(
            "SZA - Kill Bill",
            "Kill Bill",
            "SZA",
        ) is True

    def test_empty_artist_does_not_force_false(self):
        """Empty suggested_artist: artist check is optional — no false negative."""
        assert validate_youtube_match(
            "Kendrick Lamar - HUMBLE.",
            "HUMBLE",
            "",
        ) is True

    def test_partial_title_mismatch_rejects(self):
        """Title tokens not found in YouTube title — rejected."""
        assert validate_youtube_match(
            "Rick Astley - Never Gonna Give You Up",
            "Stairway to Heaven",
            "Led Zeppelin",
        ) is False

    def test_remastered_noise_ignored(self):
        """'Remastered' is a noise token and should be ignored."""
        assert validate_youtube_match(
            "Pink Floyd - Comfortably Numb (Remastered)",
            "Comfortably Numb",
            "Pink Floyd",
        ) is True

    def test_feat_noise_ignored(self):
        """'feat' and 'featuring' are noise tokens."""
        assert validate_youtube_match(
            "Drake - God's Plan (feat. Future) (Official)",
            "God's Plan",
            "Drake",
        ) is True

    def test_both_empty_inputs_return_true(self):
        """Empty title and artist — both checks pass vacuously."""
        assert validate_youtube_match("Some YouTube Title", "", "") is True
