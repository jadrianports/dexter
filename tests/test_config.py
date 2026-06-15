"""Tests for config.py pure helpers: sanitize_database_url.

These tests do NOT touch the DB, Discord, or any network — sanitize_database_url
is a pure string function and must stay that way. (K-05)
"""

import pytest

from config import sanitize_database_url


class TestSanitizeDatabaseUrl:
    def test_strips_query_string_with_neon_params(self):
        raw = "postgresql://user:pass@host-pooler.neon.tech/db?sslmode=require&channel_binding=require"
        result = sanitize_database_url(raw)
        assert result == "postgresql://user:pass@host-pooler.neon.tech/db"

    def test_noop_when_no_query_string(self):
        raw = "postgresql://user:pass@host/db"
        result = sanitize_database_url(raw)
        assert result == raw

    def test_strips_reversed_param_order(self):
        raw = "postgresql://user:pass@host/db?channel_binding=require&sslmode=require"
        result = sanitize_database_url(raw)
        assert result == "postgresql://user:pass@host/db"


# ---------------------------------------------------------------------------
# Flat-name aliases for 05-VALIDATION.md automated command compatibility
# (pytest tests/test_config.py::test_sanitize_database_url -x etc.)
# ---------------------------------------------------------------------------


def test_sanitize_database_url():
    """Alias: strips Neon query string with sslmode + channel_binding params."""
    t = TestSanitizeDatabaseUrl()
    t.test_strips_query_string_with_neon_params()


def test_sanitize_database_url_noop():
    """Alias: no-op when DSN has no query string."""
    t = TestSanitizeDatabaseUrl()
    t.test_noop_when_no_query_string()


def test_sanitize_database_url_reversed_params():
    """Alias: strips entire query string regardless of param order."""
    t = TestSanitizeDatabaseUrl()
    t.test_strips_reversed_param_order()
