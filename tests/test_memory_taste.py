"""Regression lock for the D-05 self-refresh fix (TASTE-02, plan 13-03).

Covers:
  - resolve_decay_days() over the REAL config: taste_episode resolves to the shorter
    TASTE_DECAY_DAYS horizon; Phase 11 kinds (milestone, daily_batch, ...) resolve to
    the unchanged MEMORY_DECAY_DAYS horizon.
  - Map-membership guard: "taste_episode" is in config.MEMORY_DECAY_DAYS_BY_KIND and
    no Phase 11 kind key is present — proving the dedup-refresh branch in
    services/memory.py::remember can never fire for Phase 11 kinds.
  - Integration-style test (mirrors tests/test_memory.py::TestRememberService's
    monkeypatch-database-module seam): a taste_episode dedup-hit calls
    database.refresh_memory_expiry; a milestone dedup-hit does NOT.

Pure-logic seam convention: the resolver assertions are mock-free and read the real
config module directly (no fixtures, no monkeypatching) — the fastest, most faithful
lock on the D-03/D-05 contract.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import config
from logic.taste import resolve_decay_days


# ---------------------------------------------------------------------------
# TestResolveDecayDaysOverRealConfig — D-03: distinct tier, Phase 11 unchanged
# ---------------------------------------------------------------------------


class TestResolveDecayDaysOverRealConfig:
    """resolve_decay_days() wired to the actual config.py values (not fixture ints)."""

    def test_taste_episode_resolves_to_taste_decay_days(self) -> None:
        result = resolve_decay_days(
            "taste_episode",
            default_days=config.MEMORY_DECAY_DAYS,
            kind_overrides=config.MEMORY_DECAY_DAYS_BY_KIND,
        )
        assert result == config.TASTE_DECAY_DAYS

    def test_taste_horizon_is_shorter_than_general_horizon(self) -> None:
        # Proves the tiers are genuinely distinct, not coincidentally equal.
        assert config.TASTE_DECAY_DAYS < config.MEMORY_DECAY_DAYS

    def test_milestone_resolves_to_general_memory_decay_days(self) -> None:
        result = resolve_decay_days(
            "milestone",
            default_days=config.MEMORY_DECAY_DAYS,
            kind_overrides=config.MEMORY_DECAY_DAYS_BY_KIND,
        )
        assert result == config.MEMORY_DECAY_DAYS

    def test_daily_batch_resolves_to_general_memory_decay_days(self) -> None:
        result = resolve_decay_days(
            "daily_batch",
            default_days=config.MEMORY_DECAY_DAYS,
            kind_overrides=config.MEMORY_DECAY_DAYS_BY_KIND,
        )
        assert result == config.MEMORY_DECAY_DAYS

    def test_all_phase11_kinds_resolve_to_general_memory_decay_days(self) -> None:
        phase11_kinds = [
            "milestone", "late_night", "repeat_song",
            "auto_queue_ignored", "daily_batch",
        ]
        for kind in phase11_kinds:
            result = resolve_decay_days(
                kind,
                default_days=config.MEMORY_DECAY_DAYS,
                kind_overrides=config.MEMORY_DECAY_DAYS_BY_KIND,
            )
            assert result == config.MEMORY_DECAY_DAYS, (
                f"Phase 11 kind {kind!r} must keep the 90-day horizon unchanged"
            )


# ---------------------------------------------------------------------------
# TestDecayDaysByKindMapGuard — proves the dedup-refresh branch is taste-only
# ---------------------------------------------------------------------------


class TestDecayDaysByKindMapGuard:
    """config.MEMORY_DECAY_DAYS_BY_KIND membership guards the D-05 refresh gate."""

    def test_taste_episode_is_in_the_override_map(self) -> None:
        assert "taste_episode" in config.MEMORY_DECAY_DAYS_BY_KIND

    def test_no_phase11_kind_is_in_the_override_map(self) -> None:
        phase11_kinds = {
            "milestone", "late_night", "repeat_song",
            "auto_queue_ignored", "daily_batch",
        }
        overlap = phase11_kinds & set(config.MEMORY_DECAY_DAYS_BY_KIND)
        assert overlap == set(), (
            f"Phase 11 kinds must never appear in MEMORY_DECAY_DAYS_BY_KIND "
            f"(self-refresh branch would fire for them): found {overlap}"
        )


# ---------------------------------------------------------------------------
# _DictRecord — minimal asyncpg.Record-like accessor (mirrors tests/test_memory.py)
# ---------------------------------------------------------------------------


class _DictRecord(dict):
    def __getitem__(self, key: str):  # type: ignore[override]
        return super().__getitem__(key)


def _make_service():
    """Build a MemoryService with a mocked GeminiService (embed always succeeds)."""
    from services.memory import MemoryService

    mock_gemini = MagicMock()
    mock_gemini.embed = AsyncMock(return_value=[[0.1] * 768])
    mock_pool = MagicMock()
    return MemoryService(mock_pool, mock_gemini)


# ---------------------------------------------------------------------------
# TestRememberDedupRefreshWiring — integration-style, monkeypatched database module
# ---------------------------------------------------------------------------


class TestRememberDedupRefreshWiring:
    """remember()'s dedup branch calls refresh_memory_expiry for taste, not Phase 11."""

    def test_taste_episode_dedup_hit_refreshes_expiry(self) -> None:
        import database

        now = datetime.now(timezone.utc)
        near_dup_row = {
            "id": 42, "fact": "keeps coming back to Radiohead", "salience": 0.4,
            "hit_count": 1, "created_at": now, "last_seen_at": now,
            "last_surfaced_at": None, "surface_count": 0,
            "similarity": 0.95,  # above MEMORY_DEDUP_THRESHOLD
        }

        svc = _make_service()
        bumped_ids: list = []
        refresh_calls: list = []

        async def fake_search(pool, *, user_id, query_embedding, k):
            return [_DictRecord(near_dup_row)]

        async def fake_bump_hit(pool, memory_id):
            bumped_ids.append(memory_id)

        async def fake_refresh(pool, memory_id, expires_at):
            refresh_calls.append((memory_id, expires_at))

        orig_search = database.search_memories
        orig_bump = database.bump_memory_hit
        orig_refresh = database.refresh_memory_expiry
        database.search_memories = fake_search
        database.bump_memory_hit = fake_bump_hit
        database.refresh_memory_expiry = fake_refresh
        try:
            asyncio.run(svc.remember(
                user_id="u1", guild_id="g1",
                fact_text="keeps coming back to Radiohead",
                kind="taste_episode", salience=0.4,
            ))
        finally:
            database.search_memories = orig_search
            database.bump_memory_hit = orig_bump
            database.refresh_memory_expiry = orig_refresh

        assert bumped_ids == [42], "Dedup hit must still bump hit_count"
        assert len(refresh_calls) == 1, "taste_episode dedup hit must refresh expires_at"
        assert refresh_calls[0][0] == 42

    def test_milestone_dedup_hit_does_not_refresh_expiry(self) -> None:
        import database

        now = datetime.now(timezone.utc)
        near_dup_row = {
            "id": 7, "fact": "hit a songs milestone", "salience": 1.0,
            "hit_count": 1, "created_at": now, "last_seen_at": now,
            "last_surfaced_at": None, "surface_count": 0,
            "similarity": 0.95,
        }

        svc = _make_service()
        bumped_ids: list = []
        refresh_calls: list = []

        async def fake_search(pool, *, user_id, query_embedding, k):
            return [_DictRecord(near_dup_row)]

        async def fake_bump_hit(pool, memory_id):
            bumped_ids.append(memory_id)

        async def fake_refresh(pool, memory_id, expires_at):
            refresh_calls.append((memory_id, expires_at))

        orig_search = database.search_memories
        orig_bump = database.bump_memory_hit
        orig_refresh = database.refresh_memory_expiry
        database.search_memories = fake_search
        database.bump_memory_hit = fake_bump_hit
        database.refresh_memory_expiry = fake_refresh
        try:
            asyncio.run(svc.remember(
                user_id="u1", guild_id="g1",
                fact_text="hit a songs milestone",
                kind="milestone", salience=1.0,
            ))
        finally:
            database.search_memories = orig_search
            database.bump_memory_hit = orig_bump
            database.refresh_memory_expiry = orig_refresh

        assert bumped_ids == [7], "Dedup hit must still bump hit_count"
        assert refresh_calls == [], (
            "milestone (a Phase 11 kind absent from MEMORY_DECAY_DAYS_BY_KIND) "
            "must NEVER call refresh_memory_expiry on dedup"
        )

    def test_taste_episode_insert_uses_taste_decay_horizon(self) -> None:
        """No dedup hit (empty search) → insert path resolves the 30-day horizon."""
        import database

        svc = _make_service()
        inserted_calls: list = []

        async def fake_search(pool, *, user_id, query_embedding, k):
            return []

        async def fake_insert(pool, **kwargs):
            inserted_calls.append(kwargs)
            return 1

        async def fake_count(pool, user_id):
            return 1  # under cap

        orig_search = database.search_memories
        orig_insert = database.insert_memory
        orig_count = database.count_user_memories
        database.search_memories = fake_search
        database.insert_memory = fake_insert
        database.count_user_memories = fake_count
        try:
            before = datetime.now(timezone.utc)
            asyncio.run(svc.remember(
                user_id="u1", guild_id="g1",
                fact_text="new taste episode fact",
                kind="taste_episode", salience=0.4,
            ))
        finally:
            database.search_memories = orig_search
            database.insert_memory = orig_insert
            database.count_user_memories = orig_count

        assert len(inserted_calls) == 1
        expires_at = inserted_calls[0]["expires_at"]
        delta_days = (expires_at - before).days
        # Allow +/-1 day slack for wall-clock execution time around the boundary.
        assert config.TASTE_DECAY_DAYS - 1 <= delta_days <= config.TASTE_DECAY_DAYS, (
            f"taste_episode insert must use the {config.TASTE_DECAY_DAYS}-day horizon, "
            f"got a delta of {delta_days} days"
        )
