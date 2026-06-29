"""Pure memory scoring functions: apply_floor, rerank, recency_score, novelty_score.

All functions are deterministic and side-effect-free: no asyncio, no Discord imports,
no database calls, no random, no datetime.now().

Any nondeterministic value (clock) is computed by the calling service and passed in
as a primitive — following the established seam pattern from logic/roasts.py and
database.py:compute_streak.

Phase 11 coverage locked by tests/test_memory.py (MEM-02 / MEM-03).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemoryFact:
    """Immutable snapshot of a user_memories row with its cosine similarity score.

    All datetime fields carry timezone info (TIMESTAMPTZ from Postgres via asyncpg).
    ``similarity`` is the cosine similarity from the ANN search: 1 - (embedding <=> query).
    """
    id: int
    fact: str
    salience: float
    hit_count: int
    created_at: datetime
    last_seen_at: datetime
    last_surfaced_at: datetime | None   # None = never surfaced (D-05 novelty guard)
    surface_count: int
    similarity: float                   # cosine similarity from ANN (1 - pgvector distance)


# ---------------------------------------------------------------------------
# apply_floor
# ---------------------------------------------------------------------------


def apply_floor(facts: list[MemoryFact], floor: float) -> list[MemoryFact]:
    """Return only facts with similarity >= floor.

    Returns [] when no facts clear the threshold (Pitfall 8: no memory beats
    a wrong memory — inject nothing rather than a low-confidence recall).

    Args:
        facts: Candidate facts from the ANN search (unsorted).
        floor: Minimum cosine similarity; config.MEMORY_SIMILARITY_FLOOR (tuned via 11-02).

    Returns:
        Filtered list preserving input order. May be empty.
    """
    return [f for f in facts if f.similarity >= floor]


# ---------------------------------------------------------------------------
# recency_score
# ---------------------------------------------------------------------------


def recency_score(created_at: datetime, now: datetime) -> float:
    """Return a score in [0, 1] — newer created_at scores higher (monotonic).

    Uses hyperbolic decay: 1 / (1 + days_since_creation).
    - Created at `now`: 1.0
    - Created 1 day ago: ~0.50
    - Created 90 days ago: ~0.011

    Clock is injected via ``now`` — no datetime.now() calls (pure seam).

    Args:
        created_at: When the memory row was first created (TIMESTAMPTZ).
        now:        Reference clock (UTC); injected by the caller.

    Returns:
        Score in [0, 1], monotonically decreasing with age.
    """
    delta_days = max(0.0, (now - created_at).total_seconds() / 86400.0)
    return 1.0 / (1.0 + delta_days)


# ---------------------------------------------------------------------------
# novelty_score
# ---------------------------------------------------------------------------


def novelty_score(last_surfaced_at: datetime | None, now: datetime) -> float:
    """Return a score in [0, 1] — never-surfaced facts score highest (D-05 anti-repeat).

    Anti-repeat penalty: a just-surfaced fact scores 0 (minimum); a fact never
    surfaced scores 1.0 (maximum). The score recovers toward 1.0 asymptotically
    as time passes since last surface — so over many sessions, no single memory
    dominates the callback rotation.

    Formula: 0.0 when last_surfaced_at=now; delta/(delta+1) otherwise; 1.0 when None.

    Args:
        last_surfaced_at: When this fact was last injected into a Gemini prompt.
                          None means it has never been surfaced.
        now:              Reference clock (UTC); injected by the caller.

    Returns:
        Score in [0, 1]. Monotonically increasing with time-since-last-surface.
    """
    if last_surfaced_at is None:
        return 1.0
    delta_days = max(0.0, (now - last_surfaced_at).total_seconds() / 86400.0)
    return delta_days / (delta_days + 1.0)


# ---------------------------------------------------------------------------
# rerank
# ---------------------------------------------------------------------------


def rerank(
    facts: list[MemoryFact],
    *,
    now: datetime | None = None,
    relevance_weight: float = 1.0,
    recency_weight: float = 0.5,
    salience_weight: float = 0.7,
    novelty_weight: float = 0.5,
) -> list[MemoryFact]:
    """Score and sort facts by composite score, descending. Pure — no I/O.

    Composite formula:
        score = relevance_weight * similarity
              + recency_weight   * recency_score(created_at, now)
              + salience_weight  * salience
              + novelty_weight   * novelty_score(last_surfaced_at, now)

    Default weights match config.MEMORY_RERANK_*_WEIGHT (tuned via 11-02 spike).
    Callers pass explicit weights; unit tests pass fixed values so they never
    depend on the chosen constants.

    Args:
        facts:            Memory facts to rank (should already be above the floor).
        now:              Clock reference for recency/novelty. When None, falls back
                          to datetime.now(UTC) — callers should inject for determinism.
        relevance_weight: Weight for cosine similarity.
        recency_weight:   Weight for age of memory (newer = higher).
        salience_weight:  Weight for stored salience score.
        novelty_weight:   Weight for anti-repetition penalty (D-05).

    Returns:
        Facts sorted descending by composite score (highest first). Stable sort
        preserves relative order of equal-score facts.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    def _composite(f: MemoryFact) -> float:
        return (
            relevance_weight * f.similarity
            + recency_weight * recency_score(f.created_at, now)  # type: ignore[arg-type]
            + salience_weight * f.salience
            + novelty_weight * novelty_score(f.last_surfaced_at, now)  # type: ignore[arg-type]
        )

    return sorted(facts, key=_composite, reverse=True)
