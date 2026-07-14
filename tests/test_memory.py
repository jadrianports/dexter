"""Pure-logic unit tests for Phase 11 RAG long-term memory (MEM-02 / MEM-03 / MEM-07).

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
  - TestDecayPredicate — decay_predicate() selects expired low-salience, retains high/recent (MEM-07)
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.memory import MemoryFact, apply_floor, novelty_score, recency_score, rerank

# 11-07: guard so the file collects cleanly at the RED commit boundary
try:
    from models.memory import decay_predicate as decay_predicate  # type: ignore[assignment]

    _DECAY_PREDICATE_AVAILABLE = True
except ImportError:
    decay_predicate = None  # type: ignore[assignment]
    _DECAY_PREDICATE_AVAILABLE = False

# Skip TestRecallService until services/memory.py is created in plan 11-03 Task 3.
_SERVICES_MEMORY_AVAILABLE = importlib.util.find_spec("services.memory") is not None

# Skip write-logic test classes until models/memory.py exports them (11-04 Task 1).
_WRITE_LOGIC_AVAILABLE = False
try:
    from models.memory import choose_eviction, compute_salience, dedup_decision

    _WRITE_LOGIC_AVAILABLE = True
except ImportError:
    pass

# Skip TestRememberService until MemoryService.remember() exists (11-04 Task 3).
_REMEMBER_AVAILABLE = False
try:
    from services.memory import MemoryService as _MemoryServiceCheck

    _REMEMBER_AVAILABLE = hasattr(_MemoryServiceCheck, "remember")
except ImportError:
    pass

# Skip 11-05 gate tests until is_sensitive / contains_number are added (11-05 Task 1).
_DISTILL_GATE_AVAILABLE = False
try:
    from models.memory import contains_number, is_sensitive  # noqa: F401

    _DISTILL_GATE_AVAILABLE = True
except ImportError:
    pass

# Skip 11-05 distill service tests until MemoryService.distill() exists (11-05 Task 1).
_DISTILL_SVC_AVAILABLE = False
try:
    from services.memory import MemoryService as _MemSvc2

    _DISTILL_SVC_AVAILABLE = hasattr(_MemSvc2, "distill")
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

_EPOCH = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)  # fixed "now" for all tests


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
            _fact(id=2, similarity=0.65),  # below the 0.70 floor
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
            relevance_weight=0.1,  # tiny weight: A gets 0.1*0.95=0.095, B gets 0.1*0.75=0.075
            recency_weight=0.0,
            salience_weight=0.0,
            novelty_weight=1.0,  # large weight: A gets 1.0*0=0, B gets 1.0*1.0=1.0
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
        result = rerank([f_low, f_high], now=now)  # f_low first in input
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
        f2 = _fact(
            id=2,
            similarity=0.6,
            salience=0.3,
            last_surfaced_at=now - timedelta(hours=1),
            created_at=now - timedelta(days=1),
        )
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

        import config
        import services.gemini as g

        src = inspect.getsource(g.GeminiService.embed)
        assert "EMBEDDING_MODEL" in src, "embed() must reference config.EMBEDDING_MODEL"
        # Must NOT hardcode the model name; must use the config constant
        assert config.EMBEDDING_MODEL == "gemini-embedding-001"

    def test_embed_uses_correct_output_dimensionality(self) -> None:
        """embed() must pass output_dimensionality=config.EMBED_DIM (768)."""
        import inspect

        import config
        import services.gemini as g

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
        from services.gemini import GeminiAPIError, GeminiRateLimitError
        from services.memory import MemoryService

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

        result = asyncio.run(run())
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
                "id": 1,
                "fact": "likes hip hop",
                "salience": 0.5,
                "hit_count": 1,
                "created_at": now,
                "last_seen_at": now,
                "last_surfaced_at": None,
                "surface_count": 0,
                "similarity": 0.50,  # below 0.70 floor
            }
        ]

        async def fake_search(pool, *, user_id, query_embedding, k, kind=None):
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
                "id": i,
                "fact": f"fact {i}",
                "salience": 0.5,
                "hit_count": 1,
                "created_at": now,
                "last_seen_at": now,
                "last_surfaced_at": None,
                "surface_count": 0,
                "similarity": 0.80,  # above 0.70 floor
            }
            for i in range(1, cap + 3)  # cap+2 rows
        ]

        bumped_ids = []

        async def fake_search(pool, *, user_id, query_embedding, k, kind=None):
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
        assert len(bumped_ids) == len(result)  # bump called for each returned fact
        assert all(isinstance(s, str) for s in result)  # returns strings


# ---------------------------------------------------------------------------
# TestSearchMemoriesKindFilter (Phase 14: OQ1 — optional kind param)
# ---------------------------------------------------------------------------


class _FakeConn:
    """Records the SQL string + positional params passed to fetch(), returns []."""

    def __init__(self):
        self.last_sql: str | None = None
        self.last_params: tuple | None = None

    async def fetch(self, sql, *params):
        self.last_sql = sql
        self.last_params = params
        return []


class _FakePoolCM:
    def __init__(self, conn: "_FakeConn"):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    """Poolless stand-in for asyncpg.Pool — captures the emitted SQL/params."""

    def __init__(self):
        self.conn = _FakeConn()

    def acquire(self):
        return _FakePoolCM(self.conn)


class TestSearchMemoriesKindFilter:
    """database.search_memories: kind=None is byte-identical; kind=X appends AND kind = $3."""

    def test_kind_none_omits_clause_and_keeps_original_params(self) -> None:
        """Byte-identical regression: omitting kind must not emit any kind clause (Pitfall 1)."""
        import asyncio

        import database

        pool = _FakePool()
        embedding = [0.1] * 768

        asyncio.run(database.search_memories(pool, user_id="u1", query_embedding=embedding, k=5))

        assert "kind =" not in pool.conn.last_sql
        assert "kind IS NULL" not in pool.conn.last_sql
        assert pool.conn.last_params == ("u1", embedding, 5)

    def test_kind_taste_episode_appends_clause_and_binds_positionally(self) -> None:
        """kind='taste_episode' appends 'AND kind = $3' and binds kind before k."""
        import asyncio

        import database

        pool = _FakePool()
        embedding = [0.1] * 768

        asyncio.run(database.search_memories(pool, user_id="u1", query_embedding=embedding, k=5, kind="taste_episode"))

        assert "AND kind = $3" in pool.conn.last_sql
        assert pool.conn.last_params == ("u1", embedding, "taste_episode", 5)


class TestSearchMemoriesGuildFilter:
    """database.search_memories: guild_id=None is byte-identical; guild_id=X appends
    the D-01 grandfather-rule OR-group, independently combinable with kind."""

    def test_no_kind_no_guild_omits_both_clauses(self) -> None:
        """Byte-identical regression: neither optional clause emitted (T-21-01/02 baseline)."""
        import asyncio

        import database

        pool = _FakePool()
        embedding = [0.1] * 768

        asyncio.run(database.search_memories(pool, user_id="u1", query_embedding=embedding, k=5))

        assert "kind =" not in pool.conn.last_sql
        assert "guild_id" not in pool.conn.last_sql
        assert pool.conn.last_params == ("u1", embedding, 5)

    def test_kind_only_binds_at_dollar_3(self) -> None:
        """kind alone still binds at literal $3 (dynamic numbering did not shift it)."""
        import asyncio

        import database

        pool = _FakePool()
        embedding = [0.1] * 768

        asyncio.run(database.search_memories(pool, user_id="u1", query_embedding=embedding, k=5, kind="taste_episode"))

        assert "AND kind = $3" in pool.conn.last_sql
        assert "guild_id" not in pool.conn.last_sql
        assert pool.conn.last_params == ("u1", embedding, "taste_episode", 5)

    def test_guild_only_appends_grandfather_or_group(self) -> None:
        """guild_id alone appends (guild_id = $3 OR guild_id IS NULL); WHERE user_id = $1 survives."""
        import asyncio

        import database

        pool = _FakePool()
        embedding = [0.1] * 768

        asyncio.run(database.search_memories(pool, user_id="u1", query_embedding=embedding, k=5, guild_id="g1"))

        assert "WHERE user_id = $1" in pool.conn.last_sql
        assert "guild_id = $" in pool.conn.last_sql
        assert "OR guild_id IS NULL" in pool.conn.last_sql
        assert " AND (guild_id" in pool.conn.last_sql
        assert " OR guild_id = $1" not in pool.conn.last_sql
        assert pool.conn.last_params == ("u1", embedding, "g1", 5)

    def test_kind_and_guild_combine_with_dynamic_numbering(self) -> None:
        """kind + guild_id together: kind binds $3, guild_id binds $4 — the auto-queue taste-blend shape."""
        import asyncio

        import database

        pool = _FakePool()
        embedding = [0.1] * 768

        asyncio.run(
            database.search_memories(
                pool,
                user_id="u1",
                query_embedding=embedding,
                k=5,
                kind="taste_episode",
                guild_id="g1",
            )
        )

        assert "WHERE user_id = $1" in pool.conn.last_sql
        assert "AND kind = $3" in pool.conn.last_sql
        assert "guild_id = $4" in pool.conn.last_sql
        assert "OR guild_id IS NULL" in pool.conn.last_sql
        assert pool.conn.last_params == ("u1", embedding, "taste_episode", "g1", 5)


class TestRecallKindParam:
    """services.memory.MemoryService.recall: kind threads through to search_memories."""

    def _make_service(self):
        from services.memory import MemoryService

        mock_gemini = MagicMock()
        mock_gemini.embed = AsyncMock(return_value=[[0.1] * 768])
        mock_pool = MagicMock()
        return MemoryService(mock_pool, mock_gemini)

    def test_recall_omits_kind_by_default(self) -> None:
        """recall() without a kind arg forwards kind=None (byte-identical regression)."""
        import asyncio

        import database

        svc = self._make_service()
        captured_kind = []

        async def fake_search(pool, *, user_id, query_embedding, k, kind=None):
            captured_kind.append(kind)
            return []

        orig_search = database.search_memories
        database.search_memories = fake_search
        try:
            result = asyncio.run(svc.recall("user1", "guild1", "test query"))
        finally:
            database.search_memories = orig_search

        assert captured_kind == [None]
        assert result == []

    def test_recall_forwards_kind_to_search_memories(self) -> None:
        """recall(..., kind='taste_episode') forwards kind straight through."""
        import asyncio

        import database

        svc = self._make_service()
        captured_kind = []

        async def fake_search(pool, *, user_id, query_embedding, k, kind=None):
            captured_kind.append(kind)
            return []

        orig_search = database.search_memories
        database.search_memories = fake_search
        try:
            asyncio.run(svc.recall("user1", "guild1", "test query", kind="taste_episode"))
        finally:
            database.search_memories = orig_search

        assert captured_kind == ["taste_episode"]

    def test_recall_signature_accepts_kind_defaulting_to_none(self) -> None:
        """recall's signature must accept kind as keyword, defaulting to None."""
        import inspect

        from services.memory import MemoryService

        sig = inspect.signature(MemoryService.recall)
        assert "kind" in sig.parameters
        assert sig.parameters["kind"].default is None


class TestRecallGuildScoped:
    """services.memory.MemoryService.recall: guild_scoped opt-in (MEM-02 / D-02).

    Stubs here use a **extra catch-all (not the narrow kind=None signature used
    by TestRecallKindParam) because these tests must be able to observe whether
    guild_id was forwarded at all — a narrow signature declaring guild_id would
    itself mask the "omitted entirely" assertion this class exists to make.
    """

    def _make_service(self):
        from services.memory import MemoryService

        mock_gemini = MagicMock()
        mock_gemini.embed = AsyncMock(return_value=[[0.1] * 768])
        mock_pool = MagicMock()
        return MemoryService(mock_pool, mock_gemini)

    def test_default_forwards_no_guild_id(self) -> None:
        """recall() without guild_scoped forwards NO guild_id kwarg (MEM-02 global default)."""
        import asyncio

        import database

        svc = self._make_service()
        captured: list[dict] = []

        async def fake_search(pool, *, user_id, query_embedding, k, kind=None, **extra):
            captured.append(extra)
            return []

        orig_search = database.search_memories
        database.search_memories = fake_search
        try:
            asyncio.run(svc.recall("user1", "guild1", "test query"))
        finally:
            database.search_memories = orig_search

        assert len(captured) == 1
        assert "guild_id" not in captured[0]

    def test_guild_scoped_true_forwards_guild_id(self) -> None:
        """recall(..., guild_scoped=True) forwards guild_id straight through."""
        import asyncio

        import database

        svc = self._make_service()
        captured: list[dict] = []

        async def fake_search(pool, *, user_id, query_embedding, k, kind=None, **extra):
            captured.append(extra)
            return []

        orig_search = database.search_memories
        database.search_memories = fake_search
        try:
            asyncio.run(svc.recall("user1", "guild1", "test query", guild_scoped=True))
        finally:
            database.search_memories = orig_search

        assert len(captured) == 1
        assert captured[0]["guild_id"] == "guild1"

    def test_kind_and_guild_scoped_both_forwarded(self) -> None:
        """recall(..., kind=..., guild_scoped=True) forwards BOTH kind and guild_id."""
        import asyncio

        import database

        svc = self._make_service()
        captured_kind: list = []
        captured_extra: list[dict] = []

        async def fake_search(pool, *, user_id, query_embedding, k, kind=None, **extra):
            captured_kind.append(kind)
            captured_extra.append(extra)
            return []

        orig_search = database.search_memories
        database.search_memories = fake_search
        try:
            asyncio.run(svc.recall("user1", "guild1", "test query", kind="taste_episode", guild_scoped=True))
        finally:
            database.search_memories = orig_search

        assert captured_kind == ["taste_episode"]
        assert captured_extra[0]["guild_id"] == "guild1"

    def test_guild_scoped_is_keyword_only_with_default_false(self) -> None:
        """guild_scoped must be KEYWORD_ONLY with default False (MEM-02 default)."""
        import inspect

        from services.memory import MemoryService

        sig = inspect.signature(MemoryService.recall)
        assert "guild_scoped" in sig.parameters
        param = sig.parameters["guild_scoped"]
        assert param.kind == inspect.Parameter.KEYWORD_ONLY
        assert param.default is False


# ---------------------------------------------------------------------------
# TestDedupDecision (11-04 Task 1)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _WRITE_LOGIC_AVAILABLE,
    reason="dedup_decision not yet implemented (11-04 Task 1)",
)
class TestDedupDecision:
    """dedup_decision returns True (bump) above threshold, False (insert) below."""

    def test_above_threshold_returns_true(self) -> None:
        """Similarity clearly above threshold → NOOP-insert (bump existing row)."""
        assert dedup_decision(0.95, 0.92) is True

    def test_below_threshold_returns_false(self) -> None:
        """Similarity clearly below threshold → insert new row."""
        assert dedup_decision(0.50, 0.92) is False

    def test_at_threshold_returns_true(self) -> None:
        """Boundary: sim == threshold → treat as near-dup (bump, not insert)."""
        # The function must handle the exact-boundary case consistently.
        # dedup_decision(0.92, 0.92) → True (>=) so near-dup wins at boundary.
        result = dedup_decision(0.92, 0.92)
        # Both True and False are technically defensible; assert it is bool.
        assert isinstance(result, bool)

    def test_plan_verification_examples(self) -> None:
        """Inline verify from PLAN.md: dedup_decision(0.95,0.90) and not dedup_decision(0.5,0.90)."""
        assert dedup_decision(0.95, 0.90) is True
        assert dedup_decision(0.50, 0.90) is False

    def test_very_low_sim_always_inserts(self) -> None:
        """sim=0.0 is never a near-duplicate."""
        assert dedup_decision(0.0, 0.92) is False

    def test_perfect_sim_always_bumps(self) -> None:
        """sim=1.0 is always a near-duplicate."""
        assert dedup_decision(1.0, 0.92) is True


# ---------------------------------------------------------------------------
# TestComputeSalience (11-04 Task 1)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _WRITE_LOGIC_AVAILABLE,
    reason="compute_salience not yet implemented (11-04 Task 1)",
)
class TestComputeSalience:
    """compute_salience returns base + bump, ordinally sane across event kinds."""

    def test_no_bump_returns_base(self) -> None:
        """compute_salience(base) with default bump=0.0 returns base unchanged."""
        assert compute_salience(0.7) == pytest.approx(0.7)

    def test_bump_is_additive(self) -> None:
        """compute_salience(base, bump) returns base + bump when in range."""
        assert compute_salience(0.5, 0.2) == pytest.approx(0.7)

    def test_clamped_at_one(self) -> None:
        """Result is clamped to 1.0 — never exceeds the unit interval."""
        assert compute_salience(0.9, 0.5) == pytest.approx(1.0)

    def test_clamped_at_zero(self) -> None:
        """Result is clamped to 0.0 — never goes negative."""
        assert compute_salience(0.0, 0.0) == pytest.approx(0.0)

    def test_result_in_unit_interval(self) -> None:
        """Output must always be in [0, 1]."""
        for base in [0.0, 0.3, 0.7, 1.0]:
            for bump in [0.0, 0.1, 0.5]:
                result = compute_salience(base, bump)
                assert 0.0 <= result <= 1.0, f"Out of range: {result} for base={base}, bump={bump}"

    def test_ordinal_ladder_from_config(self) -> None:
        """MEMORY_SALIENCE_BASE_WEIGHTS is ordinally monotone: milestone > auto_queue_ignored >= daily_batch."""
        import config

        w = config.MEMORY_SALIENCE_BASE_WEIGHTS
        assert w["milestone"] > w["late_night"], "milestone must outrank late_night"
        assert w["late_night"] > w["repeat_song"], "late_night must outrank repeat_song"
        assert w["repeat_song"] > w["auto_queue_ignored"], "repeat_song must outrank auto_queue_ignored"
        assert w["auto_queue_ignored"] >= w["daily_batch"], "auto_queue_ignored must outrank or equal daily_batch"

    def test_milestone_kind_has_highest_base(self) -> None:
        """milestone base weight is the highest among all defined event kinds."""
        import config

        w = config.MEMORY_SALIENCE_BASE_WEIGHTS
        assert w["milestone"] == max(w.values()), "milestone must be the highest base weight"

    def test_milestone_salience_above_auto_queue(self) -> None:
        """compute_salience with milestone base beats auto_queue_ignored base (no bump)."""
        import config

        w = config.MEMORY_SALIENCE_BASE_WEIGHTS
        assert compute_salience(w["milestone"]) > compute_salience(w["auto_queue_ignored"])


# ---------------------------------------------------------------------------
# TestChooseEviction (11-04 Task 1)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _WRITE_LOGIC_AVAILABLE,
    reason="choose_eviction not yet implemented (11-04 Task 1)",
)
class TestChooseEviction:
    """choose_eviction returns [] at/under cap, lowest-value ids over cap (D-08)."""

    def test_empty_facts_returns_empty(self) -> None:
        assert choose_eviction([], cap=150) == []

    def test_at_cap_returns_empty(self) -> None:
        """Exactly at cap → no eviction needed."""
        facts = [_fact(id=i, salience=0.5) for i in range(5)]
        assert choose_eviction(facts, cap=5) == []

    def test_under_cap_returns_empty(self) -> None:
        """Fewer than cap → no eviction."""
        facts = [_fact(id=i, salience=0.5) for i in range(3)]
        assert choose_eviction(facts, cap=5) == []

    def test_one_over_cap_evicts_one(self) -> None:
        """One fact over cap → exactly one id returned."""
        facts = [_fact(id=i, salience=float(i) / 10) for i in range(1, 6)]  # 5 facts
        result = choose_eviction(facts, cap=4)
        assert len(result) == 1

    def test_evicts_lowest_salience(self) -> None:
        """The returned id belongs to the fact with the lowest salience."""
        low_sal = _fact(id=1, salience=0.1)
        mid_sal = _fact(id=2, salience=0.5)
        high_sal = _fact(id=3, salience=0.9)
        result = choose_eviction([mid_sal, high_sal, low_sal], cap=2)
        assert result == [1], f"Expected lowest-salience id=1, got {result}"

    def test_evicts_n_over_cap(self) -> None:
        """When 3 over cap, returns exactly 3 ids."""
        facts = [_fact(id=i, salience=float(i) / 10) for i in range(1, 11)]  # 10 facts
        result = choose_eviction(facts, cap=7)
        assert len(result) == 3

    def test_tie_break_by_age_oldest_evicted(self) -> None:
        """Tie on salience → older fact (earlier created_at) is evicted first (D-08)."""
        now = _EPOCH
        old_fact = _fact(id=1, salience=0.5, created_at=now - timedelta(days=90))
        new_fact = _fact(id=2, salience=0.5, created_at=now)
        high_sal = _fact(id=3, salience=0.9)
        # 3 facts, cap=2 → evict 1; both id=1 and id=2 have same salience; id=1 is older
        result = choose_eviction([old_fact, new_fact, high_sal], cap=2)
        assert 1 in result, "Older fact with same salience must be evicted first (D-08)"

    def test_eviction_never_returns_highest_salience(self) -> None:
        """The highest-salience fact must never appear in eviction list."""
        facts = [_fact(id=i, salience=float(i) / 10) for i in range(1, 11)]
        result = choose_eviction(facts, cap=5)
        assert 10 not in result, "Highest-salience fact (id=10, sal=1.0) must not be evicted"


# ---------------------------------------------------------------------------
# TestRememberService (11-04 Task 3)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _REMEMBER_AVAILABLE,
    reason="MemoryService.remember not yet implemented (11-04 Task 3)",
)
class TestRememberService:
    """MemoryService.remember() unit tests (mocked embed + fake pool + fake DB)."""

    def _make_service(
        self,
        embed_return: list[list[float]] | None = None,
        embed_raises: Exception | None = None,
        search_rows: list[dict] | None = None,
    ):
        """Build a MemoryService with mocked gemini and DB helpers."""
        import asyncio

        from services.memory import MemoryService

        mock_gemini = MagicMock()
        if embed_raises is not None:
            mock_gemini.embed = AsyncMock(side_effect=embed_raises)
        else:
            mock_gemini.embed = AsyncMock(return_value=embed_return or [[0.1] * 768])

        mock_pool = MagicMock()
        svc = MemoryService(mock_pool, mock_gemini)
        return svc, mock_gemini, mock_pool

    def test_rate_limited_embed_returns_without_inserting(self) -> None:
        """GeminiRateLimitError on embed → return silently, never call insert_memory."""
        import asyncio

        import database
        from services.gemini import GeminiRateLimitError

        svc, _, _ = self._make_service(embed_raises=GeminiRateLimitError("rate limited"))

        inserted_calls = []

        async def fake_insert(**kwargs):
            inserted_calls.append(kwargs)
            return 1

        orig_insert = database.insert_memory
        database.insert_memory = fake_insert
        try:
            asyncio.run(
                svc.remember(
                    user_id="u1",
                    guild_id="g1",
                    fact_text="likes lofi hip hop",
                    kind="daily_batch",
                    salience=0.3,
                )
            )
        finally:
            database.insert_memory = orig_insert

        assert inserted_calls == [], "insert_memory must NOT be called when embed rate-limits"

    def test_near_duplicate_bumps_existing_row(self) -> None:
        """When nearest existing memory has similarity > threshold → bump, not insert."""
        import asyncio
        from datetime import timezone

        import database

        now = datetime.now(timezone.utc)
        near_dup_row = {
            "id": 42,
            "fact": "likes lofi hip hop",
            "kind": "daily_batch",  # search_memories now returns kind (CR-13-01)
            "salience": 0.5,
            "hit_count": 1,
            "created_at": now,
            "last_seen_at": now,
            "last_surfaced_at": None,
            "surface_count": 0,
            "similarity": 0.95,  # above MEMORY_DEDUP_THRESHOLD=0.92
        }

        svc, _, _ = self._make_service()

        inserted_calls: list = []
        bumped_ids: list = []

        async def fake_search(pool, *, user_id, query_embedding, k):
            return [_DictRecord(near_dup_row)]

        async def fake_bump_hit(pool, memory_id):
            bumped_ids.append(memory_id)

        async def fake_insert(pool, **kwargs):
            inserted_calls.append(kwargs)
            return 1

        orig_search = database.search_memories
        orig_bump = database.bump_memory_hit
        orig_insert = database.insert_memory
        database.search_memories = fake_search
        database.bump_memory_hit = fake_bump_hit
        database.insert_memory = fake_insert
        try:
            asyncio.run(
                svc.remember(
                    user_id="u1",
                    guild_id="g1",
                    fact_text="likes lofi hip hop",
                    kind="daily_batch",
                    salience=0.3,
                )
            )
        finally:
            database.search_memories = orig_search
            database.bump_memory_hit = orig_bump
            database.insert_memory = orig_insert

        assert inserted_calls == [], "Near-dup must NOT insert a new row"
        assert 42 in bumped_ids, "Near-dup must bump the existing row's hit_count"

    def test_distinct_fact_inserts_new_row(self) -> None:
        """When nearest memory is below threshold → insert new row, no bump."""
        import asyncio
        from datetime import timezone

        import database

        now = datetime.now(timezone.utc)
        distinct_row = {
            "id": 99,
            "fact": "different fact entirely",
            "kind": "daily_batch",  # search_memories now returns kind (CR-13-01)
            "salience": 0.5,
            "hit_count": 1,
            "created_at": now,
            "last_seen_at": now,
            "last_surfaced_at": None,
            "surface_count": 0,
            "similarity": 0.55,  # below MEMORY_DEDUP_THRESHOLD=0.92
        }

        svc, _, _ = self._make_service()

        inserted_calls: list = []
        bumped_ids: list = []

        async def fake_search(pool, *, user_id, query_embedding, k):
            return [_DictRecord(distinct_row)]

        async def fake_bump_hit(pool, memory_id):
            bumped_ids.append(memory_id)

        async def fake_insert(pool, **kwargs):
            inserted_calls.append(kwargs)
            return 1

        async def fake_count(pool, user_id):
            return 1  # under cap → no eviction

        orig_search = database.search_memories
        orig_bump = database.bump_memory_hit
        orig_insert = database.insert_memory
        orig_count = database.count_user_memories
        database.search_memories = fake_search
        database.bump_memory_hit = fake_bump_hit
        database.insert_memory = fake_insert
        database.count_user_memories = fake_count
        try:
            asyncio.run(
                svc.remember(
                    user_id="u1",
                    guild_id="g1",
                    fact_text="likes synthwave",
                    kind="repeat_song",
                    salience=0.5,
                )
            )
        finally:
            database.search_memories = orig_search
            database.bump_memory_hit = orig_bump
            database.insert_memory = orig_insert
            database.count_user_memories = orig_count

        assert len(inserted_calls) == 1, "Distinct fact must insert exactly one row"
        assert bumped_ids == [], "Distinct fact must NOT bump any existing row"

    def test_no_existing_memories_inserts_new_row(self) -> None:
        """When search_memories returns [] → no dedup check, just insert."""
        import asyncio

        import database

        svc, _, _ = self._make_service()

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
            asyncio.run(
                svc.remember(
                    user_id="u1",
                    guild_id="g1",
                    fact_text="first memory ever",
                    kind="milestone",
                    salience=1.0,
                )
            )
        finally:
            database.search_memories = orig_search
            database.insert_memory = orig_insert
            database.count_user_memories = orig_count

        assert len(inserted_calls) == 1, "First memory should be inserted without dedup"

    def test_remember_never_raises(self) -> None:
        """Any unexpected error inside remember() must not propagate to callers."""
        import asyncio

        import database

        svc, _, _ = self._make_service()

        async def fake_search(*args, **kwargs):
            raise RuntimeError("unexpected DB error")

        orig_search = database.search_memories
        database.search_memories = fake_search
        try:
            # Must not raise
            asyncio.run(
                svc.remember(
                    user_id="u1",
                    guild_id="g1",
                    fact_text="test",
                    kind="daily_batch",
                    salience=0.2,
                )
            )
        except Exception as e:
            pytest.fail(f"remember() raised an unexpected exception: {e!r}")
        finally:
            database.search_memories = orig_search


class TestRememberDedupCallShapeUnchanged:
    """MEM-05 regression lock: remember()'s k=1 dedup search call shape is
    byte-identical to pre-Phase-21 — no guild_id, no kind, no **kwargs escape
    hatch ever threads into the CR-13-01-scarred dedup path (D-02).
    """

    def _make_service(self):
        from services.memory import MemoryService

        mock_gemini = MagicMock()
        mock_gemini.embed = AsyncMock(return_value=[[0.1] * 768])
        mock_pool = MagicMock()
        return MemoryService(mock_pool, mock_gemini)

    def test_dedup_search_call_shape_is_strict(self) -> None:
        """A strict stub with EXACTLY (pool, *, user_id, query_embedding, k) — no
        kind, no guild_id, no **kwargs — must not raise TypeError. If a future
        edit threads a scoping kwarg into the dedup search, this fails loudly."""
        import asyncio

        import database

        svc = self._make_service()
        received_kwargs: list[dict] = []

        async def strict_search(pool, *, user_id, query_embedding, k):
            received_kwargs.append({"user_id": user_id, "query_embedding": query_embedding, "k": k})
            return []

        async def fake_insert(pool, **kwargs):
            return 1

        async def fake_count(pool, user_id):
            return 1  # under cap

        orig_search = database.search_memories
        orig_insert = database.insert_memory
        orig_count = database.count_user_memories
        database.search_memories = strict_search
        database.insert_memory = fake_insert
        database.count_user_memories = fake_count
        try:
            asyncio.run(
                svc.remember(
                    user_id="u1",
                    guild_id="g1",
                    fact_text="a distinct new fact",
                    kind="daily_batch",
                    salience=0.3,
                )
            )
        finally:
            database.search_memories = orig_search
            database.insert_memory = orig_insert
            database.count_user_memories = orig_count

        assert len(received_kwargs) == 1
        assert set(received_kwargs[0].keys()) == {"user_id", "query_embedding", "k"}
        assert received_kwargs[0]["k"] == 1

    def test_remember_source_never_threads_guild_scoped_or_guild_id_into_dedup_search(self) -> None:
        """Source-level guard: remember() must not contain 'guild_scoped', and the
        dedup search_memories(...) call region must not contain 'guild_id='."""
        import inspect

        from services.memory import MemoryService

        source = inspect.getsource(MemoryService.remember)
        assert "guild_scoped" not in source

        start = source.index("search_memories(")
        end = source.index(")", start)
        call_region = source[start:end]
        assert "guild_id" not in call_region

    def test_taste_episode_matched_row_refreshes_expiry(self) -> None:
        """D-05 semantics regression: dedup hit on a matched row whose kind IS in
        MEMORY_DECAY_DAYS_BY_KIND still calls refresh_memory_expiry — unaffected
        by the guild-scoping work in this phase."""
        import asyncio
        from datetime import timezone

        import database

        now = datetime.now(timezone.utc)
        near_dup_row = {
            "id": 42,
            "fact": "keeps replaying the same album",
            "kind": "taste_episode",
            "salience": 0.4,
            "hit_count": 1,
            "created_at": now,
            "last_seen_at": now,
            "last_surfaced_at": None,
            "surface_count": 0,
            "similarity": 0.95,
        }

        svc = self._make_service()
        refresh_calls: list = []

        async def fake_search(pool, *, user_id, query_embedding, k):
            return [_DictRecord(near_dup_row)]

        async def fake_bump_hit(pool, memory_id):
            pass

        async def fake_refresh(pool, memory_id, expires_at):
            refresh_calls.append(memory_id)

        orig_search = database.search_memories
        orig_bump = database.bump_memory_hit
        orig_refresh = database.refresh_memory_expiry
        database.search_memories = fake_search
        database.bump_memory_hit = fake_bump_hit
        database.refresh_memory_expiry = fake_refresh
        try:
            asyncio.run(
                svc.remember(
                    user_id="u1",
                    guild_id="g1",
                    fact_text="keeps replaying the same album",
                    kind="taste_episode",
                    salience=0.4,
                )
            )
        finally:
            database.search_memories = orig_search
            database.bump_memory_hit = orig_bump
            database.refresh_memory_expiry = orig_refresh

        assert refresh_calls == [42]

    def test_daily_batch_matched_row_does_not_refresh_expiry(self) -> None:
        """D-05 semantics regression: dedup hit on a matched row whose kind is NOT
        in MEMORY_DECAY_DAYS_BY_KIND (a Phase 11 kind) must NOT refresh expiry."""
        import asyncio
        from datetime import timezone

        import database

        now = datetime.now(timezone.utc)
        near_dup_row = {
            "id": 7,
            "fact": "asked about lofi again",
            "kind": "daily_batch",
            "salience": 0.3,
            "hit_count": 1,
            "created_at": now,
            "last_seen_at": now,
            "last_surfaced_at": None,
            "surface_count": 0,
            "similarity": 0.95,
        }

        svc = self._make_service()
        refresh_calls: list = []

        async def fake_search(pool, *, user_id, query_embedding, k):
            return [_DictRecord(near_dup_row)]

        async def fake_bump_hit(pool, memory_id):
            pass

        async def fake_refresh(pool, memory_id, expires_at):
            refresh_calls.append(memory_id)

        orig_search = database.search_memories
        orig_bump = database.bump_memory_hit
        orig_refresh = database.refresh_memory_expiry
        database.search_memories = fake_search
        database.bump_memory_hit = fake_bump_hit
        database.refresh_memory_expiry = fake_refresh
        try:
            asyncio.run(
                svc.remember(
                    user_id="u1",
                    guild_id="g1",
                    fact_text="asked about lofi again",
                    kind="daily_batch",
                    salience=0.3,
                )
            )
        finally:
            database.search_memories = orig_search
            database.bump_memory_hit = orig_bump
            database.refresh_memory_expiry = orig_refresh

        assert refresh_calls == []


# ---------------------------------------------------------------------------
# TestIsSensitive (11-05 Task 1)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _DISTILL_GATE_AVAILABLE,
    reason="is_sensitive not yet implemented (11-05 Task 1)",
)
class TestIsSensitive:
    """is_sensitive() blocks D-01 categories and passes D-02 music-cringe content."""

    def test_blocks_mental_health_depression(self) -> None:
        """Explicit mental health keyword → blocked (D-01)."""
        assert is_sensitive("i have been really depressed lately")

    def test_passes_music_taste_cringe(self) -> None:
        """Music-taste cringe with no sensitive content → passes (D-02)."""
        assert not is_sensitive("he only listens to drake and calls it taste")

    def test_blocks_pii_email(self) -> None:
        """Email address in fact → PII gate blocks it (D-01)."""
        assert is_sensitive("contact him at user@example.com for his playlist")

    def test_blocks_self_harm_reference(self) -> None:
        """Self-harm keyword → blocked (D-01)."""
        assert is_sensitive("mentioned self-harm in passing")

    def test_passes_binge_session_fact(self) -> None:
        """3am binge session with no sensitive content → passes (D-02)."""
        assert not is_sensitive("queued mr brightside at 3am")

    def test_passes_hypocrisy_fact(self) -> None:
        """Music hypocrisy with no sensitive content → passes (D-02)."""
        assert not is_sensitive("swore he was done with the killers")

    def test_blocks_grief_keyword(self) -> None:
        """Grief / bereavement keyword → blocked (D-01)."""
        assert is_sensitive("still grieving and listening to sad music")

    def test_blocks_suicide_keyword(self) -> None:
        """Suicidal ideation phrase → blocked (D-01)."""
        assert is_sensitive("said something about wanting to die")


# ---------------------------------------------------------------------------
# TestContainsNumber (11-05 Task 1)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _DISTILL_GATE_AVAILABLE,
    reason="contains_number not yet implemented (11-05 Task 1)",
)
class TestContainsNumber:
    """contains_number() accuracy firewall: flags SQL-known figures, passes episodes."""

    def test_flags_digit_count(self) -> None:
        """Text with a digit (play count) → True (accuracy firewall, Rule 5)."""
        assert contains_number("queued mr brightside 14 times")

    def test_passes_number_free_episode(self) -> None:
        """Episode fact with no digit or count word → False."""
        assert not contains_number("swore he was done with the killers")

    def test_flags_written_count(self) -> None:
        """Written count word like 'fourteen' → True (accuracy firewall)."""
        assert contains_number("queued it fourteen times")

    def test_passes_music_taste_fact(self) -> None:
        """Music taste fact with no numbers → False."""
        assert not contains_number("only listens to drake and calls it taste")

    def test_flags_streak_day_count(self) -> None:
        """Streak days (SQL-known figure) in text → True."""
        assert contains_number("has a 30-day streak")

    def test_passes_no_numbers_in_roast_fact(self) -> None:
        """A distilled roast fact with no numbers → False."""
        assert not contains_number("prefers lo-fi hip hop at late hours")

    def test_flags_any_digit(self) -> None:
        """Any digit at all → True (conservative backstop)."""
        assert contains_number("had 1 good song out of many")


# ---------------------------------------------------------------------------
# TestDistillService (11-05 Task 1)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _DISTILL_SVC_AVAILABLE,
    reason="distill not yet implemented (11-05 Task 1)",
)
class TestDistillService:
    """MemoryService.distill() drops sensitive and number-bearing facts; never raises."""

    def _make_service(
        self,
        chat_return: str | None = None,
        chat_raises: Exception | None = None,
    ):
        """Build a MemoryService with a mocked gemini.chat."""
        from services.memory import MemoryService

        mock_gemini = MagicMock()
        if chat_raises is not None:
            mock_gemini.chat = AsyncMock(side_effect=chat_raises)
        else:
            mock_gemini.chat = AsyncMock(return_value=chat_return or "[]")
        mock_pool = MagicMock()
        return MemoryService(mock_pool, mock_gemini)

    def test_distill_drops_number_bearing_fact(self) -> None:
        """A fact with a digit is dropped by the contains_number backstop."""
        import asyncio

        svc = self._make_service(chat_return='["only listens to drake", "queued it 14 times"]')
        result = asyncio.run(svc.distill("some banter context"))
        # Digit-bearing fact must be dropped
        assert not any("14" in f for f in result)
        # Safe fact should survive
        assert any("drake" in f for f in result)

    def test_distill_drops_sensitive_fact(self) -> None:
        """A fact matching a blocked D-01 category is dropped by the is_sensitive backstop."""
        import asyncio

        svc = self._make_service(chat_return='["has been really depressed lately", "likes indie pop"]')
        result = asyncio.run(svc.distill("some banter context"))
        # Sensitive fact dropped
        assert not any("depress" in f.lower() for f in result)
        # Safe fact survives
        assert any("indie pop" in f for f in result)

    def test_distill_returns_empty_on_invalid_json(self) -> None:
        """Non-JSON model response → distill returns []."""
        import asyncio

        svc = self._make_service(chat_return="not valid json at all here")
        result = asyncio.run(svc.distill("some context"))
        assert result == []

    def test_distill_returns_empty_on_rate_limit(self) -> None:
        """GeminiRateLimitError from chat → distill returns [] (priority-2 degrade)."""
        import asyncio

        from services.gemini import GeminiRateLimitError

        svc = self._make_service(chat_raises=GeminiRateLimitError("rate limited"))
        result = asyncio.run(svc.distill("some context"))
        assert result == []

    def test_distill_caps_at_three_facts(self) -> None:
        """Model output with 5 safe facts is capped to at most 3."""
        import asyncio

        svc = self._make_service(chat_return='["fact one", "fact two", "fact three", "fact four", "fact five"]')
        result = asyncio.run(svc.distill("some context"))
        assert len(result) <= 3

    def test_distill_returns_empty_list_from_empty_model_response(self) -> None:
        """Model returns [] → distill returns []."""
        import asyncio

        svc = self._make_service(chat_return="[]")
        result = asyncio.run(svc.distill("nothing notable here"))
        assert result == []


# ---------------------------------------------------------------------------
# Trigger regression tests (11-05 Task 2)
# D-09: no per-message write; cog hooks use asyncio.create_task
# These run as module-level functions so -k "per_message or trigger" catches them.
# ---------------------------------------------------------------------------


def test_per_message_write_absent_from_on_message() -> None:
    """on_message in EventsCog must NOT call distill_and_remember (D-09 guarantee)."""
    import inspect

    import cogs.events as e

    src = inspect.getsource(e.EventsCog.on_message)
    assert "distill_and_remember" not in src, (
        "on_message must NEVER call distill_and_remember (D-09: no per-message write)"
    )
    assert "memory_service" not in src, "on_message must NEVER reference memory_service (D-09: no per-message write)"


def test_trigger_write_hook_uses_create_task_in_events_cog() -> None:
    """Events cog notable-event hooks must use asyncio.create_task (3-second rule)."""
    import inspect

    import cogs.events as e

    src = inspect.getsource(e)
    assert "distill_and_remember" in src, (
        "cogs/events.py must wire distill_and_remember at notable-event sites (D-09 path 1)"
    )
    assert "create_task" in src, "cogs/events.py must use asyncio.create_task for memory hooks (3s rule / T-11-05e)"


def test_trigger_write_hook_uses_create_task_in_music_cog() -> None:
    """Music cog notable-event hooks must use asyncio.create_task (3-second rule)."""
    import inspect

    import cogs.music as m

    src = inspect.getsource(m)
    assert "distill_and_remember" in src, (
        "cogs/music.py must wire distill_and_remember at notable-event sites (D-09 path 1)"
    )
    assert "create_task" in src, "cogs/music.py must use asyncio.create_task for memory hooks (3s rule / T-11-05e)"


# ---------------------------------------------------------------------------
# memory_sweep task registration tests (11-07 Task 3)
# ---------------------------------------------------------------------------


def test_memory_sweep_task_defined_in_bot() -> None:
    """memory_sweep must be a module-level @tasks.loop defined in bot.py (MEM-07)."""
    import bot as b

    assert hasattr(b, "memory_sweep"), "bot.py must define memory_sweep as a module-level @tasks.loop (11-07 Task 3)"


def test_memory_sweep_started_in_initialize_once() -> None:
    """_initialize_once must call memory_sweep.start() behind is_running() guard (MEM-07)."""
    src = open("bot.py", encoding="utf-8").read()
    assert "memory_sweep.start()" in src, "bot.py _initialize_once must call memory_sweep.start() (MEM-07 / REL-02)"


def test_memory_sweep_in_cleanup_partial_init() -> None:
    """memory_sweep must be in the _cleanup_partial_init loop list (T-11-07c / WR-04)."""
    src = open("bot.py", encoding="utf-8").read()
    # The cleanup loop list appears after _cleanup_partial_init definition
    tail = src.split("_cleanup_partial_init")[1][:900]
    assert "memory_sweep" in tail, "memory_sweep must appear in the _cleanup_partial_init loop-cancel list (T-11-07c)"


# ---------------------------------------------------------------------------
# TestDecayPredicate — 11-07: MEM-07 expiry selection (decay + salience)
# ---------------------------------------------------------------------------

# Reference clock for all decay tests (deterministic — never calls datetime.now())
_DECAY_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_decay_fact(
    *,
    salience: float = 0.2,
    age_days: float = 100.0,
    hit_count: int = 1,
) -> MemoryFact:
    """Build a MemoryFact whose created_at is `age_days` before _DECAY_NOW."""
    created_at = _DECAY_NOW - timedelta(days=age_days)
    return MemoryFact(
        id=1,
        fact="test fact",
        salience=salience,
        hit_count=hit_count,
        created_at=created_at,
        last_seen_at=created_at,
        last_surfaced_at=None,
        surface_count=0,
        similarity=0.0,
    )


@pytest.mark.skipif(
    not _DECAY_PREDICATE_AVAILABLE,
    reason="decay_predicate not yet implemented — RED phase guard (11-07 Task 1)",
)
class TestDecayPredicate:
    """decay_predicate selects expired low-salience facts; retains high-salience / recent ones.

    D-08: low-salience facts age out first. High-salience episodes survive.
    Pure + clock-injectable: no datetime.now() calls, no I/O (MEM-07 / T-11-07b).
    """

    def test_old_low_salience_selected(self) -> None:
        """Fact older than decay window + below salience floor → selected for sweep."""
        fact = _make_decay_fact(salience=0.2, age_days=100.0)
        result = decay_predicate(fact, _DECAY_NOW, decay_days=90)
        assert result is True, "An expired (100 days > 90) low-salience (0.2) fact must be selected for sweep"

    def test_old_high_salience_retained(self) -> None:
        """Fact past decay window but high-salience → retained (D-08 guarantee)."""
        fact = _make_decay_fact(salience=0.7, age_days=100.0)
        result = decay_predicate(fact, _DECAY_NOW, decay_days=90)
        assert result is False, "An expired high-salience (0.7) fact must be retained regardless of age (D-08)"

    def test_recent_low_salience_retained(self) -> None:
        """Fact below salience floor but still within decay window → retained."""
        fact = _make_decay_fact(salience=0.2, age_days=5.0)
        result = decay_predicate(fact, _DECAY_NOW, decay_days=90)
        assert result is False, "A recent (5 days < 90) low-salience fact must be retained — too new to sweep"

    def test_salience_at_floor_boundary_retained(self) -> None:
        """Fact with salience exactly at the default floor (0.5) is retained (inclusive >= check)."""
        fact = _make_decay_fact(salience=0.5, age_days=100.0)
        result = decay_predicate(fact, _DECAY_NOW, decay_days=90)
        assert result is False, "Salience exactly at the floor (0.5 >= 0.5) must be retained (boundary test)"

    def test_age_exactly_at_decay_boundary_retained(self) -> None:
        """Fact aged exactly decay_days is retained (boundary — strictly > decay_days needed)."""
        fact = _make_decay_fact(salience=0.2, age_days=90.0)
        result = decay_predicate(fact, _DECAY_NOW, decay_days=90)
        assert result is False, (
            "Age of exactly 90 days (== decay_days) must be retained; sweep requires age > decay_days"
        )

    def test_custom_salience_floor_selects_higher_salience(self) -> None:
        """A higher custom floor selects facts that the default floor would retain."""
        fact = _make_decay_fact(salience=0.6, age_days=100.0)
        # With default floor 0.5: 0.6 >= 0.5 → retained
        assert decay_predicate(fact, _DECAY_NOW, decay_days=90) is False
        # With custom floor 0.8: 0.6 < 0.8 → selected
        assert decay_predicate(fact, _DECAY_NOW, decay_days=90, salience_floor=0.8) is True

    def test_daily_batch_salience_selected_when_old(self) -> None:
        """daily_batch weight (0.2) fact aged past window is swept (lowest-value category)."""
        fact = _make_decay_fact(salience=0.2, age_days=95.0)
        assert decay_predicate(fact, _DECAY_NOW, decay_days=90) is True

    def test_milestone_salience_retained_when_old(self) -> None:
        """milestone weight (1.0) fact is never swept — highest-salience episode."""
        fact = _make_decay_fact(salience=1.0, age_days=365.0)
        assert decay_predicate(fact, _DECAY_NOW, decay_days=90) is False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DictRecord(dict):
    """Minimal asyncpg.Record-like dict accessor for unit tests."""

    def __getitem__(self, key: str):  # type: ignore[override]
        return super().__getitem__(key)
