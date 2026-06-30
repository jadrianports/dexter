"""Pure unit tests for /jam load queue-cap truncation logic (UX-01, Pitfall 7).

No live Discord, no DB, no asyncio — all inputs are plain Python primitives.
Mirrors the Phase 10 pure-unit test style from test_playback_logic.py (TEST-01).

Coverage:
  - Truncation counting: snapshot of M tracks against a cap-N queue yields
    added==N and truncated==M-N (T-12-01-05)
  - Zero-truncation path: M <= N → all tracks added, truncated==0
  - Empty snapshot produces zero adds and zero truncation
  - The QueueFullError exception path is the only truncation trigger
"""

from __future__ import annotations

import pytest

from models.queue import QueueFullError


# ---------------------------------------------------------------------------
# Helpers — stub queue that raises QueueFullError after N adds
# ---------------------------------------------------------------------------


class _StubQueue:
    """Minimal queue stub that raises QueueFullError after `cap` successful adds."""

    def __init__(self, cap: int) -> None:
        self._cap = cap
        self._count = 0

    def add(self, track: object) -> None:  # noqa: ANN001
        """Accept up to self._cap tracks, then raise QueueFullError."""
        if self._count >= self._cap:
            raise QueueFullError("queue full")
        self._count += 1

    @property
    def added(self) -> int:
        return self._count


def _make_track_dicts(m: int) -> list[dict]:
    """Return m minimal track dicts (same shape as Track.to_dict())."""
    return [
        {
            "video_id": f"vid_{i}",
            "title": f"Song {i}",
            "artist": "Artist",
            "url": f"https://youtube.com/watch?v=vid_{i}",
            "duration_seconds": 180,
            "requested_by": 123456,
            "was_auto_queued": False,
            "thumbnail": None,
        }
        for i in range(m)
    ]


def _simulate_jam_load(rows: list[dict], cap: int) -> tuple[int, int]:
    """Simulate the /jam load add-loop and return (added, truncated).

    Mirrors the exact loop in LibraryCog.jam_load:
        added = 0; truncated = 0
        for track_dict in rows:
            try: queue.add(track); added += 1
            except QueueFullError: truncated += 1
    """
    queue = _StubQueue(cap)
    added = 0
    truncated = 0
    for track_dict in rows:
        try:
            queue.add(track_dict)  # stub ignores the object
            added += 1
        except QueueFullError:
            truncated += 1
    return added, truncated


# ---------------------------------------------------------------------------
# TestJamLoadTruncation — core cap-truncation invariants (T-12-01-05)
# ---------------------------------------------------------------------------


class TestJamLoadTruncation:
    """Verify the /jam load add-loop respects the queue cap via QueueFullError."""

    def test_full_truncation_no_tracks_fit(self) -> None:
        """If the queue is already at cap (cap=0), all tracks are truncated."""
        rows = _make_track_dicts(5)
        added, truncated = _simulate_jam_load(rows, cap=0)
        assert added == 0
        assert truncated == 5
        assert added + truncated == len(rows)

    def test_partial_truncation_some_tracks_fit(self) -> None:
        """M=10 tracks against a cap-3 queue: added==3, truncated==7 (T-12-01-05)."""
        m = 10
        n = 3
        rows = _make_track_dicts(m)
        added, truncated = _simulate_jam_load(rows, cap=n)
        assert added == n, f"Expected {n} added, got {added}"
        assert truncated == m - n, f"Expected {m - n} truncated, got {truncated}"
        assert added + truncated == m

    def test_no_truncation_all_fit(self) -> None:
        """M=5 tracks against a cap-10 queue: all 5 added, truncated==0."""
        rows = _make_track_dicts(5)
        added, truncated = _simulate_jam_load(rows, cap=10)
        assert added == 5
        assert truncated == 0

    def test_exact_cap_boundary(self) -> None:
        """M == cap: all tracks fit exactly, truncated==0."""
        m = 7
        rows = _make_track_dicts(m)
        added, truncated = _simulate_jam_load(rows, cap=m)
        assert added == m
        assert truncated == 0

    def test_one_over_cap(self) -> None:
        """M = cap + 1: exactly one track is truncated."""
        cap = 4
        rows = _make_track_dicts(cap + 1)
        added, truncated = _simulate_jam_load(rows, cap=cap)
        assert added == cap
        assert truncated == 1

    def test_empty_snapshot_zero_adds(self) -> None:
        """Empty jam snapshot produces no adds and no truncations."""
        added, truncated = _simulate_jam_load([], cap=500)
        assert added == 0
        assert truncated == 0

    def test_large_snapshot_realistic_cap(self) -> None:
        """Snapshot of 60 tracks against the realistic 500-cap: all 60 added."""
        rows = _make_track_dicts(60)
        added, truncated = _simulate_jam_load(rows, cap=500)
        assert added == 60
        assert truncated == 0

    def test_summary_reflects_truncation(self) -> None:
        """The (added, truncated) values are correct for summary message construction."""
        m, n = 15, 8
        rows = _make_track_dicts(m)
        added, truncated = _simulate_jam_load(rows, cap=n)
        # Verify summary string would mention the right numbers
        summary = f"loaded jam: added {added} track(s)."
        if truncated:
            summary += f" {truncated} track(s) were skipped — queue is at cap."
        assert f"added {n} track(s)" in summary
        assert f"{m - n} track(s) were skipped" in summary


# ---------------------------------------------------------------------------
# TestQueueFullErrorIsTheTruncationTrigger
# ---------------------------------------------------------------------------


class TestQueueFullErrorIsTheTruncationTrigger:
    """Verify QueueFullError is the only path that increments truncated."""

    def test_queuefullerror_increments_truncated_not_added(self) -> None:
        """When QueueFullError is raised, truncated goes up and added stays put."""
        rows = _make_track_dicts(3)
        # cap=1 means first track added, next 2 raise QueueFullError
        added, truncated = _simulate_jam_load(rows, cap=1)
        assert added == 1
        assert truncated == 2

    def test_no_exception_path_increments_only_added(self) -> None:
        """When no QueueFullError is raised, truncated stays 0."""
        rows = _make_track_dicts(3)
        added, truncated = _simulate_jam_load(rows, cap=100)
        assert added == 3
        assert truncated == 0

    def test_totals_always_equal_snapshot_length(self) -> None:
        """added + truncated must always equal len(rows) for any cap."""
        for cap in [0, 1, 5, 10, 50]:
            rows = _make_track_dicts(10)
            added, truncated = _simulate_jam_load(rows, cap=cap)
            assert added + truncated == len(rows), (
                f"cap={cap}: added={added} + truncated={truncated} != {len(rows)}"
            )
