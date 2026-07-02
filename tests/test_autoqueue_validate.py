"""Unit tests for logic.autoqueue.validate_youtube_match (UX-04 / D-12).

Pure, sub-second — no Discord, no asyncio, no DB, no network.
"""

from __future__ import annotations

import pytest

from logic.autoqueue import (
    _normalize_for_match,
    is_recently_skipped_artist,
    validate_youtube_match,
)


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


# ---------------------------------------------------------------------------
# Function-level aliases — make `-k validate_youtube_match` discoverable
# ---------------------------------------------------------------------------


def test_validate_youtube_match_accepts_valid():
    """Sanity: accept a well-formed title+artist match."""
    assert validate_youtube_match(
        "Taylor Swift - Shake It Off (Official Music Video)",
        "Shake It Off",
        "Taylor Swift",
    ) is True


def test_validate_youtube_match_rejects_mismatch():
    """Sanity: reject a clear title+artist mismatch."""
    assert validate_youtube_match(
        "Rick Astley - Never Gonna Give You Up",
        "Bohemian Rhapsody",
        "Queen",
    ) is False


# ---------------------------------------------------------------------------
# TestIsRecentlySkippedArtist — D-02 hard post-filter (Phase 14 / BRAIN-01)
# ---------------------------------------------------------------------------


class TestIsRecentlySkippedArtist:
    def test_subset_match_returns_true(self):
        """Normalized token subset match is a positive hit."""
        assert is_recently_skipped_artist(
            "Phoebe Bridgers", ["phoebe bridgers"]
        ) is True

    def test_no_overlap_returns_false(self):
        """No token overlap between candidate and skip list."""
        assert is_recently_skipped_artist("Drake", ["Phoebe Bridgers"]) is False

    def test_empty_candidate_never_blocks(self):
        """Empty candidate artist -> False, vacuous (never blocks)."""
        assert is_recently_skipped_artist("", ["Phoebe Bridgers"]) is False

    def test_empty_skip_list_never_blocks(self):
        """Empty skipped_artists list -> False, vacuous (never blocks)."""
        assert is_recently_skipped_artist("Drake", []) is False

    def test_noise_and_stop_word_tokens_ignored(self):
        """Noise/stop-word tokens (official, video, the) are ignored via
        _normalize_for_match, same as validate_youtube_match."""
        assert is_recently_skipped_artist(
            "The Official Drake Video", ["drake"]
        ) is True


# ---------------------------------------------------------------------------
# TestAutoQueueFallThroughLoop — mocked fall-through coverage (Task 2 / D-14)
# ---------------------------------------------------------------------------


class TestAutoQueueFallThroughLoop:
    """Exercise the widened-search + validate + fall-through loop logic using
    stubs — no live Gemini, YouTube, or Discord.  All inputs are deterministic.

    The loop under test (simplified extract of the cogs/ai.py logic):

        tracks_added = []
        for suggestion in suggestions:
            if len(tracks_added) >= SONGS_PER_ROUND:
                break
            results = stub_search(suggestion)
            validated = None
            for result in results:
                if validate_youtube_match(result["title"], suggestion["title"], suggestion["artist"]):
                    validated = result
                    break
            if validated is None:
                continue   # fall-through — D-14
            tracks_added.append(validated)
    """

    # Inline the loop logic so the test is a pure unit with no cog imports.
    @staticmethod
    def _run_loop(suggestions: list[dict], search_map: dict[str, list[dict]], songs_per_round: int) -> list[dict]:
        """Pure re-implementation of the loop body from cogs/ai.py try_auto_queue."""
        tracks_added: list[dict] = []
        for suggestion in suggestions:
            if len(tracks_added) >= songs_per_round:
                break
            results = search_map.get(suggestion["title"], [])
            if not results:
                continue
            validated = None
            for result in results:
                if validate_youtube_match(
                    result.get("title", ""),
                    suggestion["title"],
                    suggestion["artist"],
                ):
                    validated = result
                    break
            if validated is None:
                continue  # D-14: fall through to next suggestion
            tracks_added.append(validated)
        return tracks_added

    def test_valid_suggestion_is_added(self):
        """A suggestion whose candidate passes validation is added to tracks_added."""
        suggestions = [{"title": "Shake It Off", "artist": "Taylor Swift"}]
        search_map = {
            "Shake It Off": [{"title": "Taylor Swift - Shake It Off (Official Music Video)", "url": "u1"}],
        }
        result = self._run_loop(suggestions, search_map, songs_per_round=3)
        assert len(result) == 1
        assert result[0]["url"] == "u1"

    def test_fall_through_when_first_suggestion_all_candidates_fail(self):
        """When all candidates for suggestion #1 fail, loop falls to suggestion #2."""
        suggestions = [
            {"title": "Bohemian Rhapsody", "artist": "Queen"},   # will be rejected
            {"title": "Kill Bill", "artist": "SZA"},              # will be accepted
        ]
        search_map = {
            # Candidates for suggestion #1 are Rick Astley — all will fail validate
            "Bohemian Rhapsody": [
                {"title": "Rick Astley - Never Gonna Give You Up", "url": "u_wrong"},
            ],
            # Candidate for suggestion #2 matches
            "Kill Bill": [
                {"title": "SZA - Kill Bill (Official Music Video)", "url": "u2"},
            ],
        }
        result = self._run_loop(suggestions, search_map, songs_per_round=3)
        assert len(result) == 1
        assert result[0]["url"] == "u2"  # filled from suggestion #2, not suggestion #1

    def test_count_never_exceeds_songs_per_round(self):
        """Loop breaks when len(tracks_added) >= songs_per_round (D-14 cap)."""
        suggestions = [
            {"title": "Song A", "artist": "Artist A"},
            {"title": "Song B", "artist": "Artist B"},
            {"title": "Song C", "artist": "Artist C"},
            {"title": "Song D", "artist": "Artist D"},  # 4th should never be added if cap=3
        ]
        search_map = {
            "Song A": [{"title": "Artist A - Song A", "url": "ua"}],
            "Song B": [{"title": "Artist B - Song B", "url": "ub"}],
            "Song C": [{"title": "Artist C - Song C", "url": "uc"}],
            "Song D": [{"title": "Artist D - Song D", "url": "ud"}],
        }
        result = self._run_loop(suggestions, search_map, songs_per_round=3)
        assert len(result) == 3
        # Songs A, B, C were queued; D was never reached
        urls = {r["url"] for r in result}
        assert "ud" not in urls

    def test_no_results_continues_to_next_suggestion(self):
        """Empty search results for a suggestion are skipped; later suggestion fills the round."""
        suggestions = [
            {"title": "Ghost Song", "artist": "Nobody"},   # no results
            {"title": "Kill Bill", "artist": "SZA"},        # has results
        ]
        search_map = {
            "Ghost Song": [],
            "Kill Bill": [{"title": "SZA - Kill Bill (Official Music Video)", "url": "u2"}],
        }
        result = self._run_loop(suggestions, search_map, songs_per_round=1)
        assert len(result) == 1
        assert result[0]["url"] == "u2"

    def test_first_passing_candidate_chosen_from_multiple(self):
        """Among multiple candidates, the first passing one is selected."""
        suggestions = [{"title": "Never Gonna Give You Up", "artist": "Rick Astley"}]
        search_map = {
            "Never Gonna Give You Up": [
                {"title": "Someone Else - Wrong Song", "url": "u_wrong"},  # fails
                {"title": "Rick Astley - Never Gonna Give You Up", "url": "u_right"},  # passes
                {"title": "Rick Astley - Never Gonna Give You Up (Live)", "url": "u_third"},  # also passes but not first
            ],
        }
        result = self._run_loop(suggestions, search_map, songs_per_round=1)
        assert len(result) == 1
        assert result[0]["url"] == "u_right"  # second candidate (first passing)
