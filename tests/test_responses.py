"""Tests for personality response pools."""

import personality.responses as responses


class TestResponsePools:
    """Every response pool should be a non-empty list of strings."""

    def test_rate_limit_messages(self):
        assert len(responses.RATE_LIMIT_MESSAGES) >= 3
        assert all(isinstance(m, str) for m in responses.RATE_LIMIT_MESSAGES)

    def test_auto_queue_announce(self):
        assert len(responses.AUTO_QUEUE_ANNOUNCE) >= 3
        assert all(isinstance(m, str) for m in responses.AUTO_QUEUE_ANNOUNCE)

    def test_auto_queue_cap_reached(self):
        assert len(responses.AUTO_QUEUE_CAP_REACHED) >= 3
        assert all(isinstance(m, str) for m in responses.AUTO_QUEUE_CAP_REACHED)

    def test_image_refusal_messages(self):
        assert len(responses.IMAGE_REFUSAL_MESSAGES) >= 3
        assert all(isinstance(m, str) for m in responses.IMAGE_REFUSAL_MESSAGES)

    def test_image_cap_messages(self):
        assert len(responses.IMAGE_CAP_MESSAGES) >= 3
        assert all(isinstance(m, str) for m in responses.IMAGE_CAP_MESSAGES)

    def test_error_messages(self):
        assert len(responses.ERROR_MESSAGES) >= 3
        assert all(isinstance(m, str) for m in responses.ERROR_MESSAGES)

    def test_ai_empty_response(self):
        assert len(responses.AI_EMPTY_RESPONSE) >= 3
        assert all(isinstance(m, str) for m in responses.AI_EMPTY_RESPONSE)

    def test_auto_queue_ignored(self):
        assert len(responses.AUTO_QUEUE_IGNORED) >= 2
        assert all(isinstance(m, str) for m in responses.AUTO_QUEUE_IGNORED)


class TestPhase7ResponsePools:
    """Phase 7 response pools must be non-empty; pick_random returns a member."""

    PHASE7_POOLS = [
        "FILTER_APPLIED",
        "FILTER_CLEARED",
        "FAVORITE_SAVED",
        "FAVORITE_DUPLICATE",
        "FAVORITE_CAP_HIT",
        "FAVORITES_EMPTY",
        "PLAYLIST_SAVED",
        "PLAYLIST_LOADED",
        "PLAYLIST_NOT_FOUND",
        "PLAYLIST_CAP_HIT",
        "NOT_IN_VOICE",
        "NOTHING_PLAYING",
    ]

    def test_pools_are_non_empty(self):
        for name in self.PHASE7_POOLS:
            pool = getattr(responses, name)
            assert len(pool) >= 1, f"{name} is empty"
            assert all(isinstance(m, str) for m in pool), f"{name} contains non-str"

    def test_pick_random_returns_member(self):
        for name in self.PHASE7_POOLS:
            pool = getattr(responses, name)
            result = responses.pick_random(pool)
            assert result in pool, f"pick_random did not return a member of {name}"


class TestPickRandom:
    def test_returns_string_from_pool(self):
        result = responses.pick_random(responses.ERROR_MESSAGES)
        assert result in responses.ERROR_MESSAGES


class TestPhase26ResponsePools:
    """Phase 26 (DJ-01/DJ-02) response pools: skip_vote tally + radio lifecycle."""

    ZERO_ARG_POOLS = [
        "RADIO_STOP",
        "RADIO_LOOP_CONFLICT",
        "RADIO_NOT_ARMED",
    ]

    ALL_PHASE26_POOLS = [
        "SKIP_VOTE_TALLY",
        "RADIO_START",
        "RADIO_STOP",
        "RADIO_LOOP_CONFLICT",
        "RADIO_NOT_ARMED",
    ]

    def test_pools_are_non_empty_lists_of_str(self):
        for name in self.ALL_PHASE26_POOLS:
            pool = getattr(responses, name)
            assert len(pool) >= 3, f"{name} has fewer than 3 entries"
            assert all(isinstance(m, str) for m in pool), f"{name} contains non-str"

    def test_pick_random_returns_member_skip_vote_and_radio_pools(self):
        for name in self.ALL_PHASE26_POOLS:
            pool = getattr(responses, name)
            result = responses.pick_random(pool)
            assert result in pool, f"pick_random did not return a member of {name}"

    def test_skip_vote_tally_every_entry_contains_both_placeholders(self):
        for entry in responses.SKIP_VOTE_TALLY:
            assert "{votes}" in entry
            assert "{required}" in entry

    def test_skip_vote_tally_every_entry_formats_without_raising(self):
        for entry in responses.SKIP_VOTE_TALLY:
            formatted = entry.format(votes=2, required=3)
            assert "{" not in formatted

    def test_radio_start_every_entry_contains_seed_placeholder(self):
        for entry in responses.RADIO_START:
            assert "{seed}" in entry

    def test_radio_start_every_entry_formats_without_raising(self):
        for entry in responses.RADIO_START:
            formatted = entry.format(seed="daft punk")
            assert "{" not in formatted

    def test_all_phase26_pool_entries_are_lowercase(self):
        for name in self.ALL_PHASE26_POOLS:
            pool = getattr(responses, name)
            for entry in pool:
                assert entry == entry.lower(), f"{name} entry not lowercase: {entry!r}"

    def test_no_gemini_import_in_responses_module(self):
        import inspect

        source = inspect.getsource(responses)
        assert "import google" not in source
