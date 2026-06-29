"""Pure memory scoring functions: apply_floor, rerank, recency_score, novelty_score,
dedup_decision, compute_salience, choose_eviction, decay_predicate.

All functions are deterministic and side-effect-free: no asyncio, no Discord imports,
no database calls, no random, no datetime.now().

Any nondeterministic value (clock) is computed by the calling service and passed in
as a primitive — following the established seam pattern from logic/roasts.py and
database.py:compute_streak.

Phase 11 coverage locked by tests/test_memory.py (MEM-02 / MEM-03 / MEM-04 / MEM-07).
"""

from __future__ import annotations

import re
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


# ---------------------------------------------------------------------------
# dedup_decision  (MEM-04)
# ---------------------------------------------------------------------------


def dedup_decision(existing_sim: float, threshold: float) -> bool:
    """Return True (bump existing row) when existing_sim is at or above threshold.

    Used by MemoryService.remember() to decide whether a new fact is a near-
    duplicate of the user's closest existing memory. True → bump hit_count on
    the existing row, skip the insert. False → insert a new row.

    The threshold is config.MEMORY_DEDUP_THRESHOLD (0.92 — tuned via 11-02 spike).
    Near-dup pairs scored 0.937/0.955; distinct facts maxed at 0.79, so a threshold
    of 0.92 gives a clean separation with zero ambiguous region.

    Args:
        existing_sim: Cosine similarity of the new fact against the nearest
                      existing memory (``1 - (embedding <=> query)``).
        threshold:    Dedup threshold; use config.MEMORY_DEDUP_THRESHOLD.

    Returns:
        True  — near-duplicate: bump existing row, do NOT insert.
        False — distinct fact: insert new row.
    """
    return existing_sim >= threshold


# ---------------------------------------------------------------------------
# compute_salience  (MEM-07 / D-07)
# ---------------------------------------------------------------------------


def compute_salience(base_weight: float, distiller_bump: float = 0.0) -> float:
    """Return the hybrid salience score for a memory: base event weight + optional bump.

    D-07 hybrid salience: the base weight comes from the event kind (see
    config.MEMORY_SALIENCE_BASE_WEIGHTS) and the distiller bump is an optional
    uplift from the distillation pass (11-05) when the distiller judges a fact
    particularly significant. Both are additive, result clamped to [0.0, 1.0].

    Ordinal ladder (milestone highest, daily_batch lowest) is enforced by the
    config dict — this function only computes the sum+clamp, not the ordering.

    Args:
        base_weight:    Event-kind base from config.MEMORY_SALIENCE_BASE_WEIGHTS.
        distiller_bump: Optional uplift from the distillation pass (default 0.0).

    Returns:
        Combined salience score in [0.0, 1.0].
    """
    return max(0.0, min(1.0, base_weight + distiller_bump))


# ---------------------------------------------------------------------------
# choose_eviction  (MEM-07 / D-08)
# ---------------------------------------------------------------------------


def choose_eviction(facts: list[MemoryFact], cap: int) -> list[int]:
    """Return the ids of the lowest-value memories to remove when over cap.

    Called by MemoryService.remember() after a count_user_memories check shows
    the user has exceeded config.MEMORY_MAX_PER_USER. Returns the ids of the
    (len(facts) - cap) facts to delete.

    Eviction ranking (D-08 — "low-salience-old-cold ages out first"):
      1. Lowest salience first (primary — most important).
      2. Oldest created_at (secondary tie-break — stale memories go first).
      3. Lowest hit_count (tertiary tie-break — cold / rarely-surfaced goes first).

    Args:
        facts: All of the user's current memory facts (MemoryFact dataclass).
               Only id, salience, created_at, hit_count fields are used.
        cap:   config.MEMORY_MAX_PER_USER — the maximum allowed count.

    Returns:
        List of memory ids to delete. Empty list when len(facts) <= cap.
        Length is exactly max(0, len(facts) - cap).
    """
    if len(facts) <= cap:
        return []

    n_evict = len(facts) - cap
    # Sort ascending: lowest salience → oldest → fewest hits (first = worst)
    candidates = sorted(
        facts,
        key=lambda f: (f.salience, f.created_at, f.hit_count),
    )
    return [f.id for f in candidates[:n_evict]]


# ---------------------------------------------------------------------------
# is_sensitive  (MEM-05 / D-01 stop-ship gate)
# ---------------------------------------------------------------------------

# Keywords for blocked D-01 categories (mental health, self-harm, medical,
# sexuality, grief/trauma, PII markers, apparent-distress cues).
# These are SUBSTRING matches against the lowercased fact text.
# Conservative: ambiguous cases → True (drop).
_SENSITIVE_KEYWORDS: frozenset[str] = frozenset({
    # Mental health / self-harm
    "depress",          # depression, depressed
    "suicide",
    "suicidal",
    "self-harm",
    "self harm",
    "selfharm",
    "overdose",
    "eating disorder",
    "anorex",           # anorexia, anorexic
    "bulimi",           # bulimia, bulimic
    "mental illness",
    "mental health",
    "panic attack",
    "psychiatr",        # psychiatrist, psychiatric
    "bipolar",
    "schizophren",      # schizophrenia, schizophrenic
    "ptsd",
    # Grief / loss / bereavement
    "griev",            # grief, grieving
    "bereave",          # bereaved, bereavement
    "mourn",            # mourning
    "passed away",
    "death of",
    "lost a loved",
    # Distress phrases (D-01: "anything said in apparent distress")
    "want to die",
    "wanting to die",
    "wanna die",
    "don't want to live",
    "don't want to be here",
    "feel worthless",
    "feel hopeless",
    "can't go on",
    "give up on life",
    "no reason to live",
    # Abuse / violence
    # NOTE: "rape" is matched via _SENSITIVE_WORD_RE (word-boundary), not here —
    # substring matching it caught "grape"/"drape"/"scrape" (WR-02).
    "sexually assault",
    "domestic abuse",
    "domestic violence",
    # Sexuality / gender identity (private categories per D-01)
    # NOTE: "gay" is matched via _SENSITIVE_WORD_RE (word-boundary), not here —
    # substring matching it caught "marvin gaye"/"gayle" (WR-02).
    "sexual orientation",
    "coming out",
    "lesbian",
    "bisexual",
    "transgender",
    "nonbinary",
    "non-binary",
})

# Short/ambiguous identity & violence terms — matched on WORD BOUNDARIES only
# (WR-02). Naive substring matching of these short tokens produced false positives
# inside common, innocuous music vocabulary:
#   "gay"  → "marvin gaye", "gayle" (the artist behind "abcdefu")
#   "rape" → "grape", "drape", "scrape"
# Word boundaries match the standalone term while leaving those tokens alone.
# Longer, unambiguous stems (depress, suicid, schizophren, ...) stay as substrings
# in _SENSITIVE_KEYWORDS above.
_SENSITIVE_WORD_RE: re.Pattern[str] = re.compile(
    r"\b(?:gay|rape)\b",
    re.IGNORECASE,
)

# PII regex patterns
_EMAIL_RE: re.Pattern[str] = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)
_PHONE_RE: re.Pattern[str] = re.compile(
    r"\+?\d[\d\s\-\.]{7,}\d"
)
_ADDRESS_RE: re.Pattern[str] = re.compile(
    r"\d{1,5}\s+[a-zA-Z\s]{3,30}\s+"
    r"(?:street|st|avenue|ave|road|rd|drive|dr|lane|ln|blvd|boulevard|court|ct)\b",
    re.IGNORECASE,
)

# Written count words (used by contains_number backstop)
_NUMBER_WORDS_RE: re.Pattern[str] = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
    r"hundred|thousand|million)\b",
    re.IGNORECASE,
)


def is_sensitive(text: str) -> bool:
    """Return True if text matches blocked identity/wellbeing/PII categories (D-01/D-02).

    Conservative: when ambiguous on a blocked category, return True (drop the memory).
    The LLM DISTILL_PROMPT is the primary gate; this is the deterministic backstop.

    Blocked (D-01): mental health, self-harm, medical, sexuality, grief/relationship
    trauma, real-world PII (email/phone/address), apparent distress.
    Passes (D-02): music-taste cringe, hypocrisy, 3am binges, light comedic drama.

    Args:
        text: A candidate distilled fact string.

    Returns:
        True — blocked (matches a D-01 category); do NOT store this memory.
        False — passes (D-02 territory); safe to store.
    """
    text_lower = text.lower()

    for kw in _SENSITIVE_KEYWORDS:
        if kw in text_lower:
            return True

    # Short/ambiguous terms: word-boundary match to avoid music-token false positives (WR-02)
    if _SENSITIVE_WORD_RE.search(text):
        return True

    if _EMAIL_RE.search(text):
        return True
    if _PHONE_RE.search(text):
        return True
    if _ADDRESS_RE.search(text):
        return True

    return False


# ---------------------------------------------------------------------------
# contains_number  (MEM-05 / accuracy firewall — Critical Rule 5)
# ---------------------------------------------------------------------------


def contains_number(text: str) -> bool:
    """Return True if text contains a digit or written count word (accuracy firewall).

    SQL already tracks play counts, streak days, and song totals. Storing those
    same numbers in the vector store would risk stale-count drift when the live
    SQL changes (Pitfall 5 / Critical Rule 5).

    The DISTILL_PROMPT forbids numbers; this is the deterministic backstop.
    Any digit or written count word → drop the fact before it reaches remember().

    Args:
        text: A candidate distilled fact string.

    Returns:
        True — contains a number (digit or count word); do NOT store this memory.
        False — number-free; safe to pass through.
    """
    # Any digit is an unambiguous SQL-competing figure
    if re.search(r"\d", text):
        return True
    # Written count words (conservative: drop any fact containing them)
    if _NUMBER_WORDS_RE.search(text):
        return True
    return False


# ---------------------------------------------------------------------------
# decay_predicate  (MEM-07 / D-08 — time-based decay sweep)
# ---------------------------------------------------------------------------


def decay_predicate(
    fact: MemoryFact,
    now: datetime,
    decay_days: int | float,
    salience_floor: float = 0.5,
) -> bool:
    """Return True if this fact should be swept: expired + low-salience.

    D-08: low-salience facts age out first. High-salience episodes survive
    indefinitely — a fact that was personally significant is never auto-deleted
    just because it is old.

    Selection predicate (both conditions must hold):
      1. Age > decay_days — past the decay window (equivalent to expires_at < now
         for rows inserted with expires_at = created_at + MEMORY_DECAY_DAYS).
      2. salience < salience_floor — low intrinsic value (daily_batch=0.2,
         auto_queue_ignored=0.4 age out; repeat_song=0.5, late_night=0.7,
         milestone=1.0 are retained).

    Pure + clock-injectable: no datetime.now() calls, no I/O (T-11-07b).

    Args:
        fact:          MemoryFact to evaluate.
        now:           Reference clock (UTC); injected by the caller (sweep or test).
        decay_days:    Decay window in days; use config.MEMORY_DECAY_DAYS (90).
        salience_floor: Salience threshold below which a fact is "low-salience".
                        Default 0.5 retains repeat_song=0.5 and above; sweeps
                        auto_queue_ignored=0.4 and daily_batch=0.2 when expired.

    Returns:
        True  — select for sweep (expired AND low-salience).
        False — retain (recent OR high-salience).
    """
    # High-salience facts are always retained regardless of age (D-08)
    if fact.salience >= salience_floor:
        return False
    # Past the decay horizon?  Strictly > so the boundary day is retained.
    age_days = (now - fact.created_at).total_seconds() / 86400.0
    return age_days > decay_days
