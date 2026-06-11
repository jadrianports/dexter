"""Tests for personality/roasts.py template pools and is_late_night helper.

Guards enforced here:
  D-02 — no self-deprecation in STARTUP_MESSAGES (scan for "miss me")
  D-03 — no f-bombs in any pool (case-insensitive scan)
"""

import personality.roasts as roasts
from personality.responses import pick_random


# ---------------------------------------------------------------------------
# Pool structure assertions
# ---------------------------------------------------------------------------

class TestPoolsExistAndNonEmpty:
    """Every named pool must be a non-empty list[str]."""

    def _assert_pool(self, pool, name: str) -> None:
        assert isinstance(pool, list), f"{name} is not a list"
        assert len(pool) >= 1, f"{name} is empty"
        for i, item in enumerate(pool):
            assert isinstance(item, str), f"{name}[{i}] is not a str"

    def test_voice_join_roasts(self):
        self._assert_pool(roasts.VOICE_JOIN_ROASTS, "VOICE_JOIN_ROASTS")

    def test_voice_leave_roasts(self):
        self._assert_pool(roasts.VOICE_LEAVE_ROASTS, "VOICE_LEAVE_ROASTS")

    def test_late_night_roasts(self):
        self._assert_pool(roasts.LATE_NIGHT_ROASTS, "LATE_NIGHT_ROASTS")

    def test_bot_moved_complaints(self):
        self._assert_pool(roasts.BOT_MOVED_COMPLAINTS, "BOT_MOVED_COMPLAINTS")

    def test_idle_loneliness_messages(self):
        self._assert_pool(roasts.IDLE_LONELINESS_MESSAGES, "IDLE_LONELINESS_MESSAGES")

    def test_startup_messages(self):
        self._assert_pool(roasts.STARTUP_MESSAGES, "STARTUP_MESSAGES")

    def test_status_lines(self):
        self._assert_pool(roasts.STATUS_LINES, "STATUS_LINES")

    def test_repeat_song_roast_templates(self):
        self._assert_pool(roasts.REPEAT_SONG_ROAST_TEMPLATES, "REPEAT_SONG_ROAST_TEMPLATES")

    def test_milestone_song_templates(self):
        self._assert_pool(roasts.MILESTONE_SONG_TEMPLATES, "MILESTONE_SONG_TEMPLATES")

    def test_milestone_streak_templates(self):
        self._assert_pool(roasts.MILESTONE_STREAK_TEMPLATES, "MILESTONE_STREAK_TEMPLATES")

    def test_no_lyrics_found(self):
        self._assert_pool(roasts.NO_LYRICS_FOUND, "NO_LYRICS_FOUND")


# ---------------------------------------------------------------------------
# pick_random behavior
# ---------------------------------------------------------------------------

class TestPickRandom:
    def test_returns_member_of_pool(self):
        result = pick_random(roasts.VOICE_JOIN_ROASTS)
        assert result in roasts.VOICE_JOIN_ROASTS

    def test_works_on_every_pool(self):
        all_pools = [
            roasts.VOICE_JOIN_ROASTS,
            roasts.VOICE_LEAVE_ROASTS,
            roasts.LATE_NIGHT_ROASTS,
            roasts.BOT_MOVED_COMPLAINTS,
            roasts.IDLE_LONELINESS_MESSAGES,
            roasts.STARTUP_MESSAGES,
            roasts.STATUS_LINES,
            roasts.REPEAT_SONG_ROAST_TEMPLATES,
            roasts.MILESTONE_SONG_TEMPLATES,
            roasts.MILESTONE_STREAK_TEMPLATES,
            roasts.NO_LYRICS_FOUND,
        ]
        for pool in all_pools:
            result = pick_random(pool)
            assert result in pool


# ---------------------------------------------------------------------------
# is_late_night unit tests (PERS-03 seam)
# ---------------------------------------------------------------------------

class TestIsLateNight:
    def test_hour_3_is_late_night(self):
        assert roasts.is_late_night(3) is True

    def test_lower_bound_1_is_late_night(self):
        assert roasts.is_late_night(1) is True

    def test_upper_bound_5_is_late_night(self):
        assert roasts.is_late_night(5) is True

    def test_hour_0_is_not_late_night(self):
        assert roasts.is_late_night(0) is False

    def test_hour_6_is_not_late_night(self):
        assert roasts.is_late_night(6) is False

    def test_hour_12_is_not_late_night(self):
        assert roasts.is_late_night(12) is False

    def test_hour_23_is_not_late_night(self):
        assert roasts.is_late_night(23) is False


# ---------------------------------------------------------------------------
# D-03 guard: no f-bombs in any pool
# ---------------------------------------------------------------------------

# Covers the four-letter root and common censored variants
_FBOMB_PATTERNS = ["fuck", "f*ck", "f**k", "fck", "f u c k"]

class TestNoProfanityViolations:
    def _all_lines(self) -> list[str]:
        all_pools = [
            roasts.VOICE_JOIN_ROASTS,
            roasts.VOICE_LEAVE_ROASTS,
            roasts.LATE_NIGHT_ROASTS,
            roasts.BOT_MOVED_COMPLAINTS,
            roasts.IDLE_LONELINESS_MESSAGES,
            roasts.STARTUP_MESSAGES,
            roasts.STATUS_LINES,
            roasts.REPEAT_SONG_ROAST_TEMPLATES,
            roasts.MILESTONE_SONG_TEMPLATES,
            roasts.MILESTONE_STREAK_TEMPLATES,
            roasts.NO_LYRICS_FOUND,
        ]
        return [line for pool in all_pools for line in pool]

    def test_no_fbombs_in_any_pool(self):
        for line in self._all_lines():
            lower = line.lower()
            for pattern in _FBOMB_PATTERNS:
                assert pattern not in lower, (
                    f"D-03 violation: found '{pattern}' in line: {line!r}"
                )


# ---------------------------------------------------------------------------
# D-02 guard: STARTUP_MESSAGES must be arrogant, not self-deprecating
# ---------------------------------------------------------------------------

class TestStartupMessagesAreArrogant:
    def test_no_miss_me_in_startup(self):
        for line in roasts.STARTUP_MESSAGES:
            assert "miss me" not in line.lower(), (
                f"D-02 violation: self-deprecating startup line: {line!r}"
            )

    def test_startup_has_arrogant_seed_line(self):
        """Canonical arrogant seed line must be present per CONTEXT.md."""
        combined = " ".join(roasts.STARTUP_MESSAGES)
        assert "queue fell apart without me" in combined, (
            "Canonical arrogant startup seed line missing from STARTUP_MESSAGES"
        )
