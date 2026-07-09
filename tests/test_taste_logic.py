"""Pure unit tests for logic/taste.py (TASTE-01 / TASTE-02, D-01/D-02/D-03/D-08).

No mocks, no fixtures, no DB — all inputs are plain Python primitives / dicts.
Locks classification precedence, the min-activity floor, the decay resolver, and
the number-free accuracy-firewall guarantee (Critical Rule 12).

Coverage:
  - has_min_activity: below / at / above the floor (D-08)
  - classify_artist: every branch — OBSESSION, NEW_ARRIVAL, STEADY, DROPPED_OFF, NONE
  - summarize_taste: phrase emission per pattern, NONE omission, empty input, never-raises
  - Digit-free firewall: no summarize_taste phrase ever contains a digit (D-02)
  - resolve_decay_days: taste_episode -> 30, milestone -> 90 (real config values, D-03)
"""

from __future__ import annotations

import re

import config
from logic.taste import (
    TastePattern,
    classify_artist,
    has_min_activity,
    resolve_decay_days,
    select_positive_taste_context,
    summarize_taste,
)

THRESHOLDS = dict(obsession_min=5, new_arrival_min=3, steady_min_baseline=5)


class TestHasMinActivity:
    """D-08 min-activity gate floor behavior."""

    def test_below_floor_returns_false(self):
        assert has_min_activity(3, min_tracks=5) is False

    def test_at_floor_returns_true(self):
        assert has_min_activity(5, min_tracks=5) is True

    def test_above_floor_returns_true(self):
        assert has_min_activity(10, min_tracks=5) is True

    def test_zero_tracks_zero_floor_returns_true(self):
        assert has_min_activity(0, min_tracks=0) is True


class TestClassifyArtist:
    """Branch coverage for classify_artist precedence (D-01)."""

    def test_obsession_when_plays_in_window_at_threshold(self):
        result = classify_artist(5, 0, 0, **THRESHOLDS)
        assert result == TastePattern.OBSESSION

    def test_obsession_when_plays_in_window_above_threshold(self):
        result = classify_artist(9, 2, 1, **THRESHOLDS)
        assert result == TastePattern.OBSESSION

    def test_new_arrival_when_zero_baseline_and_at_threshold(self):
        result = classify_artist(3, 0, 0, **THRESHOLDS)
        assert result == TastePattern.NEW_ARRIVAL

    def test_new_arrival_not_triggered_below_threshold(self):
        # plays_in_window below new_arrival_min, baseline zero -> NONE
        result = classify_artist(2, 0, 0, **THRESHOLDS)
        assert result == TastePattern.NONE

    def test_steady_when_baseline_at_threshold_and_still_playing(self):
        result = classify_artist(1, 5, 0, **THRESHOLDS)
        assert result == TastePattern.STEADY

    def test_steady_when_baseline_above_threshold_and_still_playing(self):
        result = classify_artist(4, 20, 2, **THRESHOLDS)
        assert result == TastePattern.STEADY

    def test_dropped_off_when_baseline_at_threshold_and_zero_plays(self):
        result = classify_artist(0, 5, 0, **THRESHOLDS)
        assert result == TastePattern.DROPPED_OFF

    def test_none_when_no_pattern_matches(self):
        # Below all thresholds: not obsessed, not new (baseline nonzero but below
        # steady floor), not steady/dropped (baseline below steady_min_baseline).
        result = classify_artist(1, 2, 0, **THRESHOLDS)
        assert result == TastePattern.NONE

    def test_none_for_all_zero_inputs(self):
        result = classify_artist(0, 0, 0, **THRESHOLDS)
        assert result == TastePattern.NONE

    def test_obsession_takes_precedence_over_new_arrival(self):
        # plays_in_window satisfies both obsession_min and new_arrival_min with
        # zero baseline -> OBSESSION wins per documented precedence order.
        result = classify_artist(5, 0, 0, **THRESHOLDS)
        assert result == TastePattern.OBSESSION

    def test_skips_in_window_does_not_affect_classification(self):
        # skips_in_window is accepted but not consulted by current precedence rules.
        low_skips = classify_artist(5, 0, 0, **THRESHOLDS)
        high_skips = classify_artist(5, 0, 999, **THRESHOLDS)
        assert low_skips == high_skips == TastePattern.OBSESSION


class TestSummarizeTaste:
    """summarize_taste phrase emission, NONE omission, empty/never-raises."""

    def test_empty_input_returns_empty_list(self):
        assert summarize_taste([], **THRESHOLDS) == []

    def test_none_classified_artist_omitted(self):
        rows = [
            {"artist": "boring band", "plays_in_window": 1, "plays_before_window": 2, "skips_in_window": 0},
        ]
        assert summarize_taste(rows, **THRESHOLDS) == []

    def test_obsession_phrase_contains_artist_name(self):
        rows = [
            {"artist": "the killers", "plays_in_window": 5, "plays_before_window": 0, "skips_in_window": 0},
        ]
        phrases = summarize_taste(rows, **THRESHOLDS)
        assert len(phrases) == 1
        assert "the killers" in phrases[0]

    def test_all_patterns_fixture_produces_four_phrases(self):
        rows = [
            # OBSESSION
            {"artist": "the killers", "plays_in_window": 6, "plays_before_window": 1, "skips_in_window": 0},
            # NEW_ARRIVAL
            {"artist": "phonk artist", "plays_in_window": 3, "plays_before_window": 0, "skips_in_window": 0},
            # STEADY
            {"artist": "mac demarco", "plays_in_window": 2, "plays_before_window": 8, "skips_in_window": 1},
            # DROPPED_OFF
            {"artist": "old band", "plays_in_window": 0, "plays_before_window": 6, "skips_in_window": 0},
            # NONE (omitted)
            {"artist": "meh band", "plays_in_window": 1, "plays_before_window": 2, "skips_in_window": 0},
        ]
        phrases = summarize_taste(rows, **THRESHOLDS)
        assert len(phrases) == 4

    def test_never_raises_for_valid_rows(self):
        rows = [
            {"artist": "a", "plays_in_window": 0, "plays_before_window": 0, "skips_in_window": 0},
            {"artist": "b", "plays_in_window": 100, "plays_before_window": 100, "skips_in_window": 100},
        ]
        summarize_taste(rows, **THRESHOLDS)  # must not raise


class TestDigitFreeFirewall:
    """D-02 / Critical Rule 12: no summarize_taste phrase ever contains a digit."""

    def test_no_phrase_contains_a_digit(self):
        # Note: artist names themselves are not sanitized by this firewall (out of
        # scope — D-02 guards against leaking raw COUNTS, not user-controlled artist
        # strings that may legitimately contain digits, e.g. "Blink-182"/"Sum 41").
        # This fixture deliberately spans all four notable patterns with digit-free
        # artist names to isolate the count-leakage guarantee under test.
        rows = [
            {"artist": "the killers", "plays_in_window": 6, "plays_before_window": 1, "skips_in_window": 0},
            {"artist": "phonk artist", "plays_in_window": 3, "plays_before_window": 0, "skips_in_window": 0},
            {"artist": "mac demarco", "plays_in_window": 2, "plays_before_window": 8, "skips_in_window": 1},
            {"artist": "old band", "plays_in_window": 0, "plays_before_window": 6, "skips_in_window": 0},
        ]
        phrases = summarize_taste(rows, **THRESHOLDS)
        assert phrases  # sanity: fixture actually produced output
        for phrase in phrases:
            assert re.search(r"\d", phrase) is None, f"digit leaked into phrase: {phrase!r}"


class TestSelectPositiveTasteContext:
    """D-03 blend/cap: round-robin interleave, dedup, cap, unattributed collective output."""

    def test_positive_taste_round_robin_interleave_order(self):
        result = select_positive_taste_context([["a", "b"], ["c", "d"]], cap=3)
        assert result == ["a", "c", "b"]

    def test_positive_taste_dedup_across_members(self):
        # "shared" appears in both members' lists — emitted once.
        result = select_positive_taste_context([["shared", "a"], ["shared", "b"]], cap=10)
        assert result.count("shared") == 1

    def test_positive_taste_cap_zero_returns_empty_list(self):
        assert select_positive_taste_context([["a", "b"], ["c"]], cap=0) == []

    def test_positive_taste_empty_input_returns_empty_list(self):
        assert select_positive_taste_context([], cap=5) == []

    def test_positive_taste_members_with_empty_lists_skipped_without_error(self):
        result = select_positive_taste_context([[], ["x", "y"]], cap=5)
        assert result == ["x", "y"]

    def test_positive_taste_never_raises_and_respects_cap_length(self):
        member_facts = [["a", "b", "c"], ["d", "e"], []]
        result = select_positive_taste_context(member_facts, cap=2)
        assert len(result) <= 2


class TestResolveDecayDays:
    """D-03: per-kind decay horizon resolution using real config values."""

    def test_taste_episode_resolves_to_taste_decay_days(self):
        result = resolve_decay_days(
            "taste_episode",
            default_days=config.MEMORY_DECAY_DAYS,
            kind_overrides=config.MEMORY_DECAY_DAYS_BY_KIND,
        )
        assert result == config.TASTE_DECAY_DAYS == 30

    def test_milestone_falls_back_to_default_days(self):
        result = resolve_decay_days(
            "milestone",
            default_days=config.MEMORY_DECAY_DAYS,
            kind_overrides=config.MEMORY_DECAY_DAYS_BY_KIND,
        )
        assert result == config.MEMORY_DECAY_DAYS == 90

    def test_explicit_literals_match_signature_contract(self):
        assert resolve_decay_days("taste_episode", default_days=90, kind_overrides={"taste_episode": 30}) == 30
        assert resolve_decay_days("milestone", default_days=90, kind_overrides={"taste_episode": 30}) == 90
