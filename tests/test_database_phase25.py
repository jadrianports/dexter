"""Phase 25 PostgreSQL integration tests — MEM-06 expiry reinforcement +
MEM-07 vision-roast memory.

These tests require a live PostgreSQL instance with the pgvector extension
enabled (same requirement as tests/test_database_phase11.py). Set
TEST_DATABASE_URL to a pgvector-enabled database before running. The default
`postgresql://dexter:dexter@localhost:5432/dexter_test` is treated as "no
live DB configured" — live-DB tests skip automatically.

Autonomous gate (no live DB needed): TestReinforceMemoryExpiryExists runs
everywhere via source-inspection (mirrors tests/test_database_phase11.py's
TestWriteHelpersExist pattern).

Phase 25 write helper (25-01):
  - TestReinforceMemoryExpiryExists: signature/source-inspection, no live DB
  - test_reinforced_fact_survives_sweep_unreinforced_does_not: SC-1 live round-trip
  - test_recall_does_not_mutate_salience_or_hit_count: SC-3 byte-identical guard

Phase 25 vision memory (25-02):
  - TestVisionRoastMemory: SC-2 live-DB write-through-firewall round-trip —
    a safe roast line produces exactly one vision_roast row (low salience,
    ~TASTE_DECAY_DAYS horizon); a number-bearing or sensitive roast line is
    firewalled to ZERO rows (exempt_numbers=False, full firewall, since
    vision_roast != taste_episode).
"""

from __future__ import annotations

import inspect
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

import database
from services.memory import MemoryService

# ---------------------------------------------------------------------------
# Skip guard — mirrors tests/test_database_phase11.py convention
# ---------------------------------------------------------------------------

_LOCAL_DEFAULT = "postgresql://dexter:dexter@localhost:5432/dexter_test"
_TEST_DSN = os.getenv("TEST_DATABASE_URL", _LOCAL_DEFAULT)
_SKIP_LIVE = os.getenv("TEST_DATABASE_URL") is None

_skip_reason = (
    "Live pgvector DB not configured — set TEST_DATABASE_URL to run Phase 25 "
    "integration tests (e.g. a pgvector-enabled Postgres such as Neon)"
)


# ---------------------------------------------------------------------------
# Static write-helper checks — always run, no live DB needed (25-01 Task 1)
# ---------------------------------------------------------------------------


class TestReinforceMemoryExpiryExists:
    """Verify reinforce_memory_expiry exists, is parameterized, and is extend-only."""

    def test_reinforce_memory_expiry_exists(self) -> None:
        assert hasattr(database, "reinforce_memory_expiry"), (
            "reinforce_memory_expiry must exist in database.py"
        )

    def test_reinforce_memory_expiry_signature(self) -> None:
        sig = inspect.signature(database.reinforce_memory_expiry)
        params = list(sig.parameters)
        assert params == ["pool", "ids", "expires_at"], (
            f"reinforce_memory_expiry must have signature (pool, ids, expires_at), got {params}"
        )

    def test_reinforce_memory_expiry_uses_any_binding(self) -> None:
        src = inspect.getsource(database.reinforce_memory_expiry)
        assert "ANY($1)" in src, "reinforce_memory_expiry must bind ids via ANY($1) array binding"

    def test_reinforce_memory_expiry_uses_greatest(self) -> None:
        src = inspect.getsource(database.reinforce_memory_expiry)
        assert "GREATEST(expires_at, $2)" in src, (
            "reinforce_memory_expiry must use GREATEST(expires_at, $2) — extend-only, never shorten"
        )

    def test_reinforce_memory_expiry_never_computes_datetime_in_sql(self) -> None:
        src = inspect.getsource(database.reinforce_memory_expiry)
        assert "interval" not in src, (
            "reinforce_memory_expiry must never compute expires_at in SQL (e.g. now() + interval) — "
            "the caller computes the datetime in Python and passes it as $2"
        )


# ---------------------------------------------------------------------------
# Live-DB round-trip tests (25-01 Task 3)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_reinforced_fact_survives_sweep_unreinforced_does_not(pool) -> None:
    """SC-1: a reinforced sweep-eligible fact survives the daily sweep while an
    equally-old, unreinforced sweep-eligible fact does not.

    Uses a sweep-eligible kind (salience < MEMORY_DECAY_SALIENCE_FLOOR = 0.5) —
    NEVER milestone (Pitfall 1: a milestone-kind test would pass vacuously,
    since high-salience rows are never swept regardless of expires_at).
    """
    import config

    user_id = "test-phase25-sc1-sweep"
    embedding = [0.5] * config.EMBED_DIM
    now = datetime.now(timezone.utc)
    past = now - timedelta(days=1)  # already expired

    # Two equal-age, sweep-eligible (daily_batch, salience 0.2) facts, both
    # already past their expiry horizon.
    id_reinforced = await database.insert_memory(
        pool,
        user_id=user_id,
        guild_id=None,
        kind="daily_batch",
        fact="the reinforced fact — kept getting surfaced",
        embedding=embedding,
        salience=0.2,
        expires_at=past,
    )
    id_unreinforced = await database.insert_memory(
        pool,
        user_id=user_id,
        guild_id=None,
        kind="daily_batch",
        fact="the unreinforced fact — never surfaced again",
        embedding=embedding,
        salience=0.2,
        expires_at=past,
    )

    # Simulate recall() step 7b surfacing exactly one of the two facts:
    # push its expires_at out into the future.
    await database.reinforce_memory_expiry(pool, [id_reinforced], now + timedelta(days=30))

    # Run the daily sweep referenced at `now`.
    await database.delete_expired_memories(pool, now=now)

    async with pool.acquire() as conn:
        row_reinforced = await conn.fetchrow(
            "SELECT id FROM user_memories WHERE id = $1", id_reinforced
        )
        row_unreinforced = await conn.fetchrow(
            "SELECT id FROM user_memories WHERE id = $1", id_unreinforced
        )

    assert row_reinforced is not None, (
        "The reinforced fact must survive the sweep (its expires_at was pushed out)"
    )
    assert row_unreinforced is None, (
        "The unreinforced, equally-old fact must be swept (its expires_at stayed in the past)"
    )


@pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
@pytest.mark.asyncio
async def test_recall_does_not_mutate_salience_or_hit_count(pool) -> None:
    """SC-3: surfacing a fact (bump_surfaced + reinforce_memory_expiry, the two
    recall() step-7 calls) never mutates salience, hit_count, or last_seen_at —
    only expires_at/last_surfaced_at/surface_count may change.

    Uses a high-salience kind (milestone, salience >= 0.5) so the byte-identical
    guarantee is exercised on a fact type every other subsystem keys on.
    """
    import config

    user_id = "test-phase25-sc3-no-mutate"
    embedding = [0.6] * config.EMBED_DIM
    expires_at = datetime.now(timezone.utc) + timedelta(days=90)

    memory_id = await database.insert_memory(
        pool,
        user_id=user_id,
        guild_id=None,
        kind="milestone",
        fact="hit 500 songs queued",
        embedding=embedding,
        salience=1.0,
        expires_at=expires_at,
    )

    async with pool.acquire() as conn:
        before = await conn.fetchrow(
            "SELECT salience, hit_count, last_seen_at FROM user_memories WHERE id = $1",
            memory_id,
        )

    # The two recall() step-7 calls, in order (7a then 7b).
    await database.bump_surfaced(pool, [memory_id])
    await database.reinforce_memory_expiry(
        pool, [memory_id], datetime.now(timezone.utc) + timedelta(days=90)
    )

    async with pool.acquire() as conn:
        after = await conn.fetchrow(
            "SELECT salience, hit_count, last_seen_at, expires_at, last_surfaced_at, surface_count"
            " FROM user_memories WHERE id = $1",
            memory_id,
        )

    assert float(after["salience"]) == float(before["salience"]), (
        "salience must be byte-identical after surfacing (D-01 expiry-only restraint)"
    )
    assert after["hit_count"] == before["hit_count"], (
        "hit_count must be byte-identical after surfacing — recall() never bumps it"
    )
    assert after["last_seen_at"] == before["last_seen_at"], (
        "last_seen_at must be byte-identical after surfacing — recall() never touches it"
    )
    # Fields that ARE expected to change on surface:
    assert after["last_surfaced_at"] is not None, "last_surfaced_at must be set by bump_surfaced"
    assert after["surface_count"] == 1, "surface_count must increment by bump_surfaced"


# ---------------------------------------------------------------------------
# MEM-07: vision_roast write-through-firewall round-trip (25-02 Task 2, SC-2)
# ---------------------------------------------------------------------------


def _fake_gemini(chat_return: str) -> MagicMock:
    """A minimal fake GeminiService: chat() returns a canned distill response,
    embed() returns a deterministic vector — no real Gemini API call, no key
    needed. Mirrors the mock_gemini pattern already used throughout
    tests/test_memory.py (MagicMock + AsyncMock method stubs)."""
    fake = MagicMock()
    fake.chat = AsyncMock(return_value=chat_return)
    fake.embed = AsyncMock(return_value=[[0.42] * 768])
    return fake


class TestVisionRoastMemory:
    """SC-2: a vision roast line round-trips through distill_and_remember under
    the new vision_roast kind, subject to the FULL is_sensitive + contains_number
    firewall (exempt_numbers=False — vision_roast != taste_episode, D-04).

    Drives distill_and_remember with a real live pool (real insert/dedup/cap
    SQL) but a fake GeminiService (deterministic chat()/embed(), no live API
    call needed) — same "real DB, fake Gemini" split as the existing
    MemoryService unit tests in tests/test_memory.py, extended here to a real
    Postgres round-trip so the stored row's kind/salience/expires_at can be
    asserted directly (tests/test_memory.py's mocked pool cannot do this).
    """

    @pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
    @pytest.mark.asyncio
    async def test_safe_vision_roast_line_stores_one_vision_roast_row(self, pool) -> None:
        import config

        user_id = "test-phase25-sc2-vision-safe"
        guild_id = "917000000000000001"
        safe_line = '["they posted a blurry gym pic and got clowned for the lighting"]'
        svc = MemoryService(pool, _fake_gemini(safe_line))

        await svc.distill_and_remember(
            user_id=user_id,
            guild_id=guild_id,
            raw_text="dex roasted a blurry gym pic",
            kind="vision_roast",
            base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS["vision_roast"],
        )

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT kind, salience, expires_at FROM user_memories WHERE user_id = $1",
                user_id,
            )

        assert len(rows) == 1, f"expected exactly one vision_roast row, got {len(rows)}"
        row = rows[0]
        assert row["kind"] == "vision_roast"
        assert float(row["salience"]) < config.MEMORY_DECAY_SALIENCE_FLOOR, (
            "vision_roast salience must be < 0.5 (sweep-eligible, D-04)"
        )
        expected_horizon = datetime.now(timezone.utc) + timedelta(days=config.TASTE_DECAY_DAYS)
        delta_seconds = abs((row["expires_at"] - expected_horizon).total_seconds())
        assert delta_seconds < 60 * 60 * 24, (
            f"expires_at must be ~TASTE_DECAY_DAYS ({config.TASTE_DECAY_DAYS}d) out, "
            f"was off by {delta_seconds}s"
        )

    @pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
    @pytest.mark.asyncio
    async def test_number_bearing_line_is_firewalled_to_zero_rows(self, pool) -> None:
        import config

        user_id = "test-phase25-sc2-vision-firewall-number"
        guild_id = "917000000000000002"
        number_line = '["they posted a pic that got 47 replies in an hour"]'
        svc = MemoryService(pool, _fake_gemini(number_line))

        await svc.distill_and_remember(
            user_id=user_id,
            guild_id=guild_id,
            raw_text="dex roasted a pic",
            kind="vision_roast",
            base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS["vision_roast"],
        )

        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT id FROM user_memories WHERE user_id = $1", user_id)
        assert rows == [], (
            "a number-bearing vision roast line must be firewalled to ZERO rows "
            "(exempt_numbers=False — full firewall, unlike taste_episode)"
        )

    @pytest.mark.skipif(_SKIP_LIVE, reason=_skip_reason)
    @pytest.mark.asyncio
    async def test_sensitive_line_is_firewalled_to_zero_rows(self, pool) -> None:
        import config

        user_id = "test-phase25-sc2-vision-firewall-sensitive"
        guild_id = "917000000000000003"
        sensitive_line = '["they posted a pic while venting about their mental health struggles"]'
        svc = MemoryService(pool, _fake_gemini(sensitive_line))

        await svc.distill_and_remember(
            user_id=user_id,
            guild_id=guild_id,
            raw_text="dex saw a heavy post",
            kind="vision_roast",
            base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS["vision_roast"],
        )

        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT id FROM user_memories WHERE user_id = $1", user_id)
        assert rows == [], "a sensitive vision roast line must be firewalled to ZERO rows (is_sensitive)"
