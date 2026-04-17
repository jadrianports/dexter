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


class TestPickRandom:
    def test_returns_string_from_pool(self):
        result = responses.pick_random(responses.ERROR_MESSAGES)
        assert result in responses.ERROR_MESSAGES
