"""Tests for config.py pure helpers: sanitize_database_url.

These tests do NOT touch the DB, Discord, or any network — sanitize_database_url
is a pure string function and must stay that way. (K-05)
"""

import pytest

import config
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


# ---------------------------------------------------------------------------
# Phase 9: Reliability & Ops Hardening constants
# ---------------------------------------------------------------------------


class TestPhase9Constants:
    """Assert Phase 9 config constants exist with correct default types and values."""

    def test_health_strict_status_default_true(self):
        """HEALTH_STRICT_STATUS defaults to True (env var absent)."""
        assert isinstance(config.HEALTH_STRICT_STATUS, bool)
        assert config.HEALTH_STRICT_STATUS is True

    def test_db_command_timeout_seconds(self):
        assert isinstance(config.DB_COMMAND_TIMEOUT_SECONDS, int)
        assert config.DB_COMMAND_TIMEOUT_SECONDS == 30

    def test_init_watchdog_timeout_seconds(self):
        assert isinstance(config.INIT_WATCHDOG_TIMEOUT_SECONDS, int)
        assert config.INIT_WATCHDOG_TIMEOUT_SECONDS == 120

    def test_sync_timeout_seconds(self):
        assert isinstance(config.SYNC_TIMEOUT_SECONDS, int)
        assert config.SYNC_TIMEOUT_SECONDS == 30

    def test_task_error_channel_cooldown_seconds(self):
        assert isinstance(config.TASK_ERROR_CHANNEL_COOLDOWN_SECONDS, int)
        assert config.TASK_ERROR_CHANNEL_COOLDOWN_SECONDS == 300

    def test_ytdlp_retry_backoff_seconds(self):
        assert isinstance(config.YTDLP_RETRY_BACKOFF_SECONDS, float)
        assert config.YTDLP_RETRY_BACKOFF_SECONDS == 1.0

    def test_ytdlp_max_quick_retries(self):
        assert isinstance(config.YTDLP_MAX_QUICK_RETRIES, int)
        assert config.YTDLP_MAX_QUICK_RETRIES == 2

    def test_health_strict_status_env_override(self, monkeypatch):
        """HEALTH_STRICT_STATUS honors HEALTH_STRICT_STATUS=false env override."""
        import importlib

        monkeypatch.setenv("HEALTH_STRICT_STATUS", "false")
        import config as cfg_mod

        importlib.reload(cfg_mod)
        assert cfg_mod.HEALTH_STRICT_STATUS is False
        # Restore to default for other tests
        monkeypatch.delenv("HEALTH_STRICT_STATUS", raising=False)
        importlib.reload(cfg_mod)

    def test_existing_k04_constants_unchanged(self):
        """K-04 Neon pool tuning constants must remain byte-identical."""
        assert config.DB_MAX_INACTIVE_CONN_LIFETIME == 240
        assert config.DB_STATEMENT_CACHE_SIZE == 0


# ---------------------------------------------------------------------------
# Flat-name aliases for Phase 9 (pytest -k "test_phase9" etc.)
# ---------------------------------------------------------------------------


def test_phase9_health_strict_status_default():
    """Phase 9: HEALTH_STRICT_STATUS defaults True."""
    t = TestPhase9Constants()
    t.test_health_strict_status_default_true()


def test_phase9_db_command_timeout():
    """Phase 9: DB_COMMAND_TIMEOUT_SECONDS == 30."""
    t = TestPhase9Constants()
    t.test_db_command_timeout_seconds()


def test_phase9_all_constants_exist():
    """Phase 9: All seven Phase 9 constants exist with correct default values."""
    assert config.HEALTH_STRICT_STATUS is True
    assert config.DB_COMMAND_TIMEOUT_SECONDS == 30
    assert config.INIT_WATCHDOG_TIMEOUT_SECONDS == 120
    assert config.SYNC_TIMEOUT_SECONDS == 30
    assert config.TASK_ERROR_CHANNEL_COOLDOWN_SECONDS == 300
    assert config.YTDLP_RETRY_BACKOFF_SECONDS == 1.0
    assert config.YTDLP_MAX_QUICK_RETRIES == 2


# ---------------------------------------------------------------------------
# Phase 14: Smarter Music Brain constants
# ---------------------------------------------------------------------------


class TestPhase14Constants:
    """Assert Phase 14 config constants exist as positive ints with correct defaults."""

    def test_auto_queue_skip_lookback_days(self):
        assert isinstance(config.AUTO_QUEUE_SKIP_LOOKBACK_DAYS, int)
        assert config.AUTO_QUEUE_SKIP_LOOKBACK_DAYS > 0
        assert config.AUTO_QUEUE_SKIP_LOOKBACK_DAYS == 7

    def test_auto_queue_skip_hint_cap(self):
        assert isinstance(config.AUTO_QUEUE_SKIP_HINT_CAP, int)
        assert config.AUTO_QUEUE_SKIP_HINT_CAP > 0
        assert config.AUTO_QUEUE_SKIP_HINT_CAP == 15

    def test_auto_queue_positive_taste_cap(self):
        assert isinstance(config.AUTO_QUEUE_POSITIVE_TASTE_CAP, int)
        assert config.AUTO_QUEUE_POSITIVE_TASTE_CAP > 0
        assert config.AUTO_QUEUE_POSITIVE_TASTE_CAP == 4

    def test_discover_adjacent_count(self):
        assert isinstance(config.DISCOVER_ADJACENT_COUNT, int)
        assert config.DISCOVER_ADJACENT_COUNT > 0
        assert config.DISCOVER_ADJACENT_COUNT == 3

    def test_discover_cooccurrence_window_days(self):
        assert isinstance(config.DISCOVER_COOCCURRENCE_WINDOW_DAYS, int)
        assert config.DISCOVER_COOCCURRENCE_WINDOW_DAYS > 0
        assert config.DISCOVER_COOCCURRENCE_WINDOW_DAYS == 90

    def test_jam_suggest_candidate_count(self):
        assert isinstance(config.JAM_SUGGEST_CANDIDATE_COUNT, int)
        assert config.JAM_SUGGEST_CANDIDATE_COUNT > 0
        assert config.JAM_SUGGEST_CANDIDATE_COUNT == 3


def test_phase14_all_constants_exist():
    """Phase 14: All six Phase 14 constants exist with correct default values."""
    assert config.AUTO_QUEUE_SKIP_LOOKBACK_DAYS == 7
    assert config.AUTO_QUEUE_SKIP_HINT_CAP == 15
    assert config.AUTO_QUEUE_POSITIVE_TASTE_CAP == 4
    assert config.DISCOVER_ADJACENT_COUNT == 3
    assert config.DISCOVER_COOCCURRENCE_WINDOW_DAYS == 90
    assert config.JAM_SUGGEST_CANDIDATE_COUNT == 3
