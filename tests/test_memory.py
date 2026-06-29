"""Pure-logic unit tests for Phase 11 RAG long-term memory (MEM-02 / MEM-03).

Covers: models/memory.py pure scoring functions and services/memory.py recall().

Pure-logic seam convention (mirrors compute_streak, logic/roasts.py):
  - All testable functions are clock-injectable / dependency-free
  - No asyncpg, no Discord, no Gemini client required in pure-logic tests
  - Tests run in any env with just `python -m pytest tests/test_memory.py`

Test classes:
  - TestApplyFloor    — apply_floor() keeps >= floor, drops below, returns [] when none clear
  - TestRecencyScore  — recency_score() is monotonic: newer created_at scores higher
  - TestNoveltyScore  — novelty_score(): None=1.0 (max), just-surfaced=0 (D-05 anti-repeat)
  - TestRerank        — rerank() composite ordering with injectable weights + clock
  - TestRecallService — MemoryService.recall() integration (mocked embed + fake pool)
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.memory import MemoryFact, apply_floor, novelty_score, rerank, recency_score

# Skip TestRecallService until services/memory.py is created in plan 11-03 Task 3.
_SERVICES_MEMORY_AVAILABLE = importlib.util.find_spec("services.memory") is not None


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

_EPOCH = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)   # fixed "now" for all tests


def _fact(
    *,
    id: int = 1,
    fact: str = "test fact",
    salience: float = 0.5,
    hit_count: int = 1,
    created_at: datetime | None = None,
    last_seen_at: datetime | None = None,
    last_surfaced_at: datetime | None = None,
    surface_count: int = 0,
    similarity: float = 0.80,
) -> MemoryFact:
    """Build a MemoryFact with sensible defaults (clock-injectable via created_at)."""
    return MemoryFact(
        id=id,
        fact=fact,
        salience=salience,
        hit_count=hit_count,
        created_at=created_at or _EPOCH,
        last_seen_at=last_seen_at or _EPOCH,
        last_surfaced_at=last_surfaced_at,
        surface_count=surface_count,
        similarity=similarity,
    )


# ---------------------------------------------------------------------------
# TestApplyFloor
# ---------------------------------------------------------------------------


class TestApplyFloor:
    """apply_floor drops below-threshold facts; returns [] when none clear."""

    def test_all_above_floor_returned(self) -> None:
        facts = [_fact(id=1, similarity=0.80), _fact(id=2, similarity=0.75)]
        result = apply_floor(facts, 0.70)
        assert len(result) == 2

    def test_exactly_at_floor_included(self) -> None:
        """Boundary is inclusive (>= floor), not strict (> floor)."""
        result = apply_floor([_fact(similarity=0.70)], 0.70)
        assert len(result) == 1

    def test_below_floor_excluded(self) -> None:
        result = apply_floor([_fact(similarity=0.69)], 0.70)
        assert result == []

    def test_empty_input_returns_empty(self) -> None:
        assert apply_floor([], 0.70) == []

    def test_mixed_above_and_below(self) -> None:
        facts = [
            _fact(id=1, similarity=0.80),
            _fact(id=2, similarity=0.65),   # below the 0.70 floor
            _fact(id=3, similarity=0.72),
        ]
        result = apply_floor(facts, 0.70)
        assert len(result) == 2
        ids = {f.id for f in result}
        assert 2 not in ids

    def test_none_clear_floor_returns_empty(self) -> None:
        facts = [_fact(id=1, similarity=0.60), _fact(id=2, similarity=0.55)]
        assert apply_floor(facts, 0.70) == []


# ---------------------------------------------------------------------------
# TestRecencyScore
# ---------------------------------------------------------------------------


class TestRecencyScore:
    """recency_score is monotonic — newer created_at scores higher."""

    def test_created_exactly_at_now_scores_one(self) -> None:
        """0 age → 1/(1+0) = 1.0."""
        score = recency_score(_EPOCH, _EPOCH)
        assert score == pytest.approx(1.0)

    def test_older_scores_lower_than_newer(self) -> None:
        """Monotonicity: fact created 1 day ago < fact created now."""
        now = _EPOCH
        score_new = recency_score(now, now)
        score_old = recency_score(now - timedelta(days=1), now)
        assert score_old < score_new

    def test_monotonic_over_ascending_ages(self) -> None:
        """Ordering is strictly preserved: 1d > 7d > 30d > 90d (older → lower)."""
        now = _EPOCH
        scores = [recency_score(now - timedelta(days=d), now) for d in [1, 7, 30, 90]]
        for earlier, later in zip(scores, scores[1:]):
            assert earlier > later, f"Expected monotone decay but got {scores}"

    def test_score_in_unit_interval(self) -> None:
        """Score must always be in [0, 1]."""
        now = _EPOCH
        assert 0 <= recency_score(now - timedelta(days=365), now) <= 1.0
        assert 0 <= recency_score(now, now) <= 1.0

    def test_very_old_fact_scores_near_zero(self) -> None:
        """A fact 1000 days old should be very low but still >= 0."""
        score = recency_score(_EPOCH - timedelta(days=1000), _EPOCH)
        assert 0.0 <= score < 0.01


# ---------------------------------------------------------------------------
# TestNoveltyScore
# ---------------------------------------------------------------------------


class TestNoveltyScore:
    """novelty_score: None=1.0 (max), just-surfaced≈0 (D-05 anti-repeat penalty)."""

    def test_never_surfaced_scores_max(self) -> None:
        """last_surfaced_at=None → maximum novelty (1.0)."""
        score = novelty_score(None, _EPOCH)
        assert score == 1.0

    def test_just_surfaced_scores_zero(self) -> None:
        """Surfaced at `now` → 0.0 / (0.0 + 1.0) = 0.0 (D-05 anti-repeat minimum)."""
        score = novelty_score(_EPOCH, _EPOCH)
        assert score == pytest.approx(0.0)

    def test_old_surfaced_scores_higher_than_recent(self) -> None:
        """More time since last surfaced → higher novelty (recovering toward 1.0)."""
        now = _EPOCH
        score_week_ago = novelty_score(now - timedelta(days=7), now)
        score_yesterday = novelty_score(now - timedelta(days=1), now)
        assert score_week_ago > score_yesterday

    def test_monotonic_ordering(self) -> None:
        """None > 7d > 1d > 0h (descending time-since-surface = descending novelty)."""
        now = _EPOCH
        score_never = novelty_score(None, now)
        score_week = novelty_score(now - timedelta(days=7), now)
        score_day = novelty_score(now - timedelta(days=1), now)
        score_now_ = novelty_score(now, now)
        assert score_never > score_week > score_day > score_now_

    def test_score_in_unit_interval(self) -> None:
        """Score must always be in [0, 1]."""
        now = _EPOCH
        assert 0 <= novelty_score(None, now) <= 1.0
        assert 0 <= novelty_score(now - timedelta(days=30), now) <= 1.0
        assert 0 <= novelty_score(now, now) <= 1.0


# ---------------------------------------------------------------------------
# TestRerank
# ---------------------------------------------------------------------------


class TestRerank:
    """rerank is deterministic, weight-correct, and clock-injectable."""

    def test_empty_input_returns_empty(self) -> None:
        assert rerank([], now=_EPOCH) == []

    def test_single_fact_returned_unchanged(self) -> None:
        f = _fact()
        assert rerank([f], now=_EPOCH) == [f]

    def test_higher_similarity_wins_when_novelty_and_recency_zeroed(self) -> None:
        """When novelty/recency weights are 0, similarity alone drives order."""
        now = _EPOCH
        low_sim = _fact(id=1, similarity=0.70)
        high_sim = _fact(id=2, similarity=0.90)
        result = rerank(
            [low_sim, high_sim],
            now=now,
            relevance_weight=1.0,
            recency_weight=0.0,
            salience_weight=0.0,
            novelty_weight=0.0,
        )
        assert result[0].id == high_sim.id

    def test_novelty_dominates_over_higher_similarity(self) -> None:
        """A higher-similarity-but-recently-surfaced fact ranks below a fresh
        relevant fact when novelty_weight dominates (D-05 ordering property)."""
        now = _EPOCH
        # Fact A: high similarity but surfaced just now → novelty = 0
        fact_a = _fact(id=1, similarity=0.95, last_surfaced_at=now)
        # Fact B: lower similarity but never surfaced → novelty = 1.0
        fact_b = _fact(id=2, similarity=0.75, last_surfaced_at=None)

        result = rerank(
            [fact_a, fact_b],
            now=now,
            relevance_weight=0.1,   # tiny weight: A gets 0.1*0.95=0.095, B gets 0.1*0.75=0.075
            recency_weight=0.0,
            salience_weight=0.0,
            novelty_weight=1.0,     # large weight: A gets 1.0*0=0, B gets 1.0*1.0=1.0
        )
        # composite(A) = 0.095 + 0 = 0.095
        # composite(B) = 0.075 + 1.0 = 1.075  → B wins
        assert result[0].id == fact_b.id, (
            "Fresh (never-surfaced) fact must outrank recently-surfaced high-similarity "
            "fact when novelty_weight dominates (D-05 anti-repeat penalty)"
        )

    def test_sorted_descending_by_composite(self) -> None:
        """Result is always descending by composite score regardless of input order."""
        now = _EPOCH
        f_high = _fact(id=1, similarity=0.9, salience=0.9, last_surfaced_at=None)
        f_low = _fact(id=2, similarity=0.5, salience=0.5, last_surfaced_at=now)
        result = rerank([f_low, f_high], now=now)   # f_low first in input
        assert result[0].id == f_high.id

    def test_now_is_clock_injectable(self) -> None:
        """rerank with different `now` yields different recency scores — pure seam."""
        # Two facts: f_recent created at EPOCH, f_old created 90 days before EPOCH
        f_recent = _fact(id=1, created_at=_EPOCH, similarity=0.80)
        f_old = _fact(id=2, created_at=_EPOCH - timedelta(days=90), similarity=0.80)

        # With only recency weight at EPOCH: f_recent (0 days old) beats f_old (90 days)
        result = rerank(
            [f_recent, f_old],
            now=_EPOCH,
            relevance_weight=0.0,
            recency_weight=1.0,
            salience_weight=0.0,
            novelty_weight=0.0,
        )
        assert result[0].id == f_recent.id

    def test_default_weights_produce_stable_ordering(self) -> None:
        """Default weights (from PATTERNS.md) produce a deterministic ordering."""
        now = _EPOCH
        f1 = _fact(id=1, similarity=0.9, salience=0.9, last_surfaced_at=None, created_at=now)
        f2 = _fact(id=2, similarity=0.6, salience=0.3, last_surfaced_at=now - timedelta(hours=1), created_at=now - timedelta(days=1))
        result1 = rerank([f1, f2], now=now)
        result2 = rerank([f2, f1], now=now)
        # Same order regardless of input order
        assert [f.id for f in result1] == [f.id for f in result2]


# ---------------------------------------------------------------------------
# TestRecallService
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TestEmbedLimiter
# ---------------------------------------------------------------------------


class TestEmbedLimiter:
    """GeminiService.embed() uses _embed_limiter, not _rate_limiter (MEM-02 / T-11-03b)."""

    def test_embed_acquires_embed_limiter_not_rate_limiter(self) -> None:
        """embed() must call self._embed_limiter.acquire, never self._rate_limiter.acquire."""
        import inspect
        import services.gemini as g

        src = inspect.getsource(g.GeminiService.embed)
        assert "_embed_limiter" in src, "embed() must reference _embed_limiter"
        assert "_rate_limiter" not in src, (
            "embed() must NOT reference _rate_limiter (T-11-03b: never consume chat budget)"
        )

    def test_embed_uses_configured_embedding_model(self) -> None:
        """embed() must use config.EMBEDDING_MODEL (gemini-embedding-001), not GEMINI_MODEL."""
        import inspect
        import services.gemini as g
        import config

        src = inspect.getsource(g.GeminiService.embed)
        assert "EMBEDDING_MODEL" in src, "embed() must reference config.EMBEDDING_MODEL"
        # Must NOT hardcode the model name; must use the config constant
        assert config.EMBEDDING_MODEL == "gemini-embedding-001"

    def test_embed_uses_correct_output_dimensionality(self) -> None:
        """embed() must pass output_dimensionality=config.EMBED_DIM (768)."""
        import inspect
        import services.gemini as g
        import config

        src = inspect.getsource(g.GeminiService.embed)
        assert "output_dimensionality" in src
        assert config.EMBED_DIM == 768

    def test_embed_limiter_is_separate_instance(self) -> None:
        """GeminiService must have two separate _RateLimiter instances."""
        from services.gemini import GeminiService

        svc = GeminiService(api_key="fake-key-for-test")
        assert hasattr(svc, "_embed_limiter"), "GeminiService must have _embed_limiter"
        assert hasattr(svc, "_rate_limiter"), "GeminiService must still have _rate_limiter"
        assert svc._embed_limiter is not svc._rate_limiter, (
            "_embed_limiter and _rate_limiter must be distinct instances"
        )


@pytest.mark.skipif(
    not _SERVICES_MEMORY_AVAILABLE,
    reason="services.memory not yet implemented (added in 11-03 Task 3)",
)
class TestRecallService:
    """MemoryService.recall() unit tests with mocked embed + fake pool rows."""

    def _make_service(self, embed_return=None, search_rows=None, embed_raises=None):
        """Build a MemoryService with mocked dependencies."""
        import asyncio
        import database
        from services.memory import MemoryService
        from services.gemini import GeminiRateLimitError, GeminiAPIError

        # Mock GeminiService.embed
        mock_gemini = MagicMock()
        if embed_raises is not None:
            mock_gemini.embed = AsyncMock(side_effect=embed_raises)
        else:
            vec = embed_return or [[0.1] * 768]
            mock_gemini.embed = AsyncMock(return_value=vec)

        # Mock database.search_memories and database.bump_surfaced
        mock_pool = MagicMock()

        # We'll patch database-level functions via monkeypatching in tests
        svc = MemoryService(mock_pool, mock_gemini)
        return svc, mock_gemini, mock_pool

    def test_returns_empty_on_rate_limit_error(self) -> None:
        """GeminiRateLimitError from embed → recall returns [] (no memory beats wrong memory)."""
        import asyncio
        from services.gemini import GeminiRateLimitError

        svc, _, _ = self._make_service(embed_raises=GeminiRateLimitError("rate limited"))

        async def run():
            return await svc.recall("user1", "guild1", "what music do i like")

        result = asyncio.get_event_loop().run_until_complete(run()) if asyncio.get_event_loop().is_running() else asyncio.run(run())
        assert result == []

    def test_returns_empty_on_gemini_api_error(self) -> None:
        """GeminiAPIError from embed → recall returns [] (graceful degrade)."""
        import asyncio
        from services.gemini import GeminiAPIError

        svc, _, _ = self._make_service(embed_raises=GeminiAPIError("api error"))

        async def run():
            return await svc.recall("user1", "guild1", "test query")

        result = asyncio.run(run())
        assert result == []

    def test_returns_empty_when_nothing_clears_floor(self) -> None:
        """When all search results are below the similarity floor, returns []."""
        import asyncio
        import database

        svc, _, _ = self._make_service()

        # Patch database.search_memories to return rows below the floor
        now = datetime.now(timezone.utc)
        below_floor_rows = [
            {
                "id": 1, "fact": "likes hip hop", "salience": 0.5,
                "hit_count": 1, "created_at": now, "last_seen_at": now,
                "last_surfaced_at": None, "surface_count": 0,
                "similarity": 0.50,   # below 0.70 floor
            }
        ]

        async def fake_search(pool, *, user_id, query_embedding, k):
            return [_DictRecord(row) for row in below_floor_rows]

        async def fake_bump(pool, ids):
            pass  # no-op

        orig_search = database.search_memories
        orig_bump = database.bump_surfaced
        database.search_memories = fake_search
        database.bump_surfaced = fake_bump
        try:
            result = asyncio.run(svc.recall("user1", "guild1", "test query"))
        finally:
            database.search_memories = orig_search
            database.bump_surfaced = orig_bump

        assert result == []

    def test_returns_capped_facts_when_some_clear_floor(self) -> None:
        """Returns at most MEMORY_INJECT_CAP facts when some clear the floor."""
        import asyncio
        import config
        import database

        svc, _, _ = self._make_service()

        now = datetime.now(timezone.utc)
        # Return MEMORY_INJECT_CAP + 2 rows above the floor
        cap = config.MEMORY_INJECT_CAP
        above_floor_rows = [
            {
                "id": i, "fact": f"fact {i}", "salience": 0.5,
                "hit_count": 1, "created_at": now, "last_seen_at": now,
                "last_surfaced_at": None, "surface_count": 0,
                "similarity": 0.80,   # above 0.70 floor
            }
            for i in range(1, cap + 3)  # cap+2 rows
        ]

        bumped_ids = []

        async def fake_search(pool, *, user_id, query_embedding, k):
            return [_DictRecord(row) for row in above_floor_rows]

        async def fake_bump(pool, ids):
            bumped_ids.extend(ids)

        orig_search = database.search_memories
        orig_bump = database.bump_surfaced
        database.search_memories = fake_search
        database.bump_surfaced = fake_bump
        try:
            result = asyncio.run(svc.recall("user1", "guild1", "test query"))
        finally:
            database.search_memories = orig_search
            database.bump_surfaced = orig_bump

        assert len(result) <= cap
        assert len(bumped_ids) == len(result)   # bump called for each returned fact
        assert all(isinstance(s, str) for s in result)   # returns strings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DictRecord(dict):
    """Minimal asyncpg.Record-like dict accessor for unit tests."""

    def __getitem__(self, key: str):  # type: ignore[override]
        return super().__getitem__(key)
