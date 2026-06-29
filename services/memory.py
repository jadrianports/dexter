"""Memory service: embed, recall, remember, sweep. No Discord types.

Lifecycle:
  recall()   — read half: embed query, scoped ANN, floor, rerank, cap, bump last_surfaced_at
  remember() — write half (11-04): distill raw text, embed, insert or dedup-bump
  sweep()    — maintenance (11-04): cap eviction + expired-memory cleanup

This file is the only place that wires together GeminiService.embed(), the
database.search_memories/bump_surfaced helpers, and the pure-logic scoring
functions in models/memory.py.

No Discord types, no asyncio.create_task — those live in the cog layer.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import asyncpg

import config
import database
from models.memory import MemoryFact, apply_floor, rerank, dedup_decision, choose_eviction
from services.gemini import GeminiService, GeminiAPIError, GeminiRateLimitError
from utils.logger import log


class MemoryService:
    """RAG lifecycle: recall, remember, sweep.

    Constructor receives the already-created pool and GeminiService so it can
    slot into the existing bot.py:_initialize_once wiring pattern without any
    new infrastructure (see 11-PATTERNS.md § "bot.py:_initialize_once").

    _embed_limiter lives on GeminiService; MemoryService calls gemini.embed()
    which acquires it — MemoryService does NOT own a second limiter instance.
    """

    def __init__(self, pool: asyncpg.Pool, gemini_service: GeminiService) -> None:
        self._pool = pool
        self._gemini = gemini_service

    # -------------------------------------------------------------------------
    # recall — read half of the RAG loop (MEM-02 / MEM-03)
    # -------------------------------------------------------------------------

    async def recall(
        self,
        user_id: str,
        guild_id: str,
        query_text: str,
    ) -> list[str]:
        """Retrieve the top relevant memories for a user + query pair.

        Full pipeline:
          1. Embed query_text via GeminiService.embed at priority=1 (user critical path)
             using the RETRIEVAL_QUERY task type.
          2. Run scoped cosine ANN via database.search_memories (WHERE user_id only).
          3. Map rows to MemoryFact; drop everything below MEMORY_SIMILARITY_FLOOR.
          4. rerank() with spike-tuned weights from config.
          5. Cap to MEMORY_INJECT_CAP (1–3 facts).
          6. Bump last_surfaced_at on the selected facts (D-05 novelty penalty update).
          7. Return list[str] (the fact texts) — or [] on error / nothing clears floor.

        Degrades gracefully to []:
          - GeminiRateLimitError or GeminiAPIError on embed → []
          - No facts above the similarity floor → []
          - Any unexpected exception (logged at DEBUG) → []

        "No memory beats a wrong memory" (Pitfall 8): never inject below-floor facts.

        Args:
            user_id:    Discord user ID — ANN search scope (T-11-03a / V4).
            guild_id:   Guild ID — reserved for future per-guild memory scoping;
                        currently the ANN scopes to user_id only (cross-server
                        personal facts are desirable: the same user uses the bot
                        on multiple servers and their taste/history is personal).
            query_text: The raw text to embed as a retrieval query (e.g. the /ask
                        question, or the roast context string from events.py).

        Returns:
            List of fact strings (at most MEMORY_INJECT_CAP), or [] when nothing
            useful was found or an error occurred.
        """
        try:
            # Step 1 — embed the query (priority 1 = user path; wait for slot)
            vectors = await self._gemini.embed(
                [query_text],
                task_type="RETRIEVAL_QUERY",
                priority=1,
            )
            query_vec: list[float] = vectors[0]
        except (GeminiRateLimitError, GeminiAPIError) as e:
            log.debug(f"memory.recall: embed failed, returning [] ({type(e).__name__}: {e})")
            return []
        except Exception as e:
            log.debug(f"memory.recall: unexpected embed error, returning [] ({type(e).__name__}: {e})")
            return []

        try:
            # Step 2 — scoped cosine ANN (user_id WHERE clause = cross-user guard T-11-03a)
            rows = await database.search_memories(
                self._pool,
                user_id=user_id,
                query_embedding=query_vec,
                k=config.MEMORY_TOP_K,
            )

            # Step 3 — map rows to MemoryFact dataclass
            facts: list[MemoryFact] = [
                MemoryFact(
                    id=row["id"],
                    fact=row["fact"],
                    salience=float(row["salience"]),
                    hit_count=int(row["hit_count"]),
                    created_at=row["created_at"],
                    last_seen_at=row["last_seen_at"],
                    last_surfaced_at=row["last_surfaced_at"],
                    surface_count=int(row["surface_count"]),
                    similarity=float(row["similarity"]),
                )
                for row in rows
            ]

            # Step 4 — drop below-floor facts (Pitfall 8: no memory beats a wrong memory)
            above_floor = apply_floor(facts, config.MEMORY_SIMILARITY_FLOOR)
            if not above_floor:
                log.debug(
                    f"memory.recall: 0/{len(facts)} facts cleared floor "
                    f"(floor={config.MEMORY_SIMILARITY_FLOOR}) for user={user_id}"
                )
                return []

            # Step 5 — rerank with spike-tuned weights
            now = datetime.now(timezone.utc)
            ranked = rerank(
                above_floor,
                now=now,
                relevance_weight=config.MEMORY_RERANK_RELEVANCE_WEIGHT,
                recency_weight=config.MEMORY_RERANK_RECENCY_WEIGHT,
                salience_weight=config.MEMORY_RERANK_SALIENCE_WEIGHT,
                novelty_weight=config.MEMORY_RERANK_NOVELTY_WEIGHT,
            )

            # Step 6 — cap to MEMORY_INJECT_CAP (1–3)
            top = ranked[: config.MEMORY_INJECT_CAP]

            # Step 7 — bump last_surfaced_at so D-05 novelty penalty applies next call
            await database.bump_surfaced(self._pool, [f.id for f in top])

            log.debug(
                f"memory.recall: {len(top)} facts injected for user={user_id} "
                f"(from {len(facts)} ANN results, {len(above_floor)} above floor)"
            )

            return [f.fact for f in top]

        except Exception as e:
            # Wrap entire retrieval body — a broken recall must never crash the roast path
            log.debug(
                f"memory.recall: retrieval error, returning [] "
                f"({type(e).__name__}: {e})"
            )
            return []

    # -------------------------------------------------------------------------
    # remember — write half of the RAG loop (MEM-04 / MEM-07)
    # -------------------------------------------------------------------------

    async def remember(
        self,
        *,
        user_id: str,
        guild_id: str | None,
        fact_text: str,
        kind: str,
        salience: float,
    ) -> None:
        """Store an already-distilled fact with dedup and per-user cap enforcement.

        ``fact_text`` is an atomic, distilled sentence produced upstream (11-05).
        This method owns the STORAGE pipeline only — it does NOT distill raw text.

        Full pipeline:
          1. Embed fact_text at priority=2 (background) via RETRIEVAL_DOCUMENT task.
             On GeminiRateLimitError: log debug and return (write skips on saturation;
             priority-2 background never blocks a user interaction, T-11-04d).
          2. Search the user's nearest existing memory (k=1).
          3. If a row exists and dedup_decision(row_similarity, threshold) is True:
             bump the existing row's hit_count (near-duplicate — do NOT insert).
          4. Otherwise: insert a new row with a MEMORY_DECAY_DAYS expiry horizon.
          5. After insert: count_user_memories. If count > MEMORY_MAX_PER_USER:
             - Fetch all user facts via get_user_memories_for_eviction.
             - choose_eviction(facts, cap) → ids of lowest-value memories.
             - evict_lowest_salience(..., ids=...) to bring count to cap (D-08).
          6. Any unexpected exception is logged at DEBUG and swallowed — remember()
             is always called via asyncio.create_task (fire-and-forget) from cogs and
             must NEVER raise into the task error handler (T-11-04d / Pitfall 8).

        Args:
            user_id:   Discord user ID — memory owner and ANN/eviction scope key.
            guild_id:  Guild context for the event; None for cross-guild facts.
            fact_text: Already-distilled atomic fact sentence (11-05 produces this).
            kind:      Event kind — must match a key in config.MEMORY_SALIENCE_BASE_WEIGHTS.
            salience:  Hybrid salience score from compute_salience() (D-07); in [0, 1].
        """
        try:
            # Step 1 — embed at priority 2 (background; reject-if-wait>10s)
            try:
                vectors = await self._gemini.embed(
                    [fact_text],
                    task_type="RETRIEVAL_DOCUMENT",
                    priority=2,
                )
                fact_vec: list[float] = vectors[0]
            except GeminiRateLimitError as e:
                log.debug(
                    f"memory.remember: embed rate-limited (priority-2 background skip), "
                    f"user={user_id} kind={kind} ({e})"
                )
                return

            # Step 2 — search nearest existing memory (k=1, user_id scoped)
            rows = await database.search_memories(
                self._pool,
                user_id=user_id,
                query_embedding=fact_vec,
                k=1,
            )

            # Step 3 — dedup check
            if rows:
                nearest_sim = float(rows[0]["similarity"])
                nearest_id = int(rows[0]["id"])
                if dedup_decision(nearest_sim, config.MEMORY_DEDUP_THRESHOLD):
                    # Near-duplicate: bump existing row, skip insert (MEM-04)
                    await database.bump_memory_hit(self._pool, nearest_id)
                    log.debug(
                        f"memory.remember: near-dup detected (sim={nearest_sim:.3f} >= "
                        f"{config.MEMORY_DEDUP_THRESHOLD}), bumped id={nearest_id} "
                        f"user={user_id} kind={kind}"
                    )
                    return

            # Step 4 — insert new row with decay horizon
            expires_at = datetime.now(timezone.utc) + timedelta(days=config.MEMORY_DECAY_DAYS)
            new_id = await database.insert_memory(
                self._pool,
                user_id=user_id,
                guild_id=guild_id,
                kind=kind,
                fact=fact_text,
                embedding=fact_vec,
                salience=salience,
                expires_at=expires_at,
            )
            log.debug(
                f"memory.remember: inserted id={new_id} user={user_id} "
                f"kind={kind} salience={salience:.2f}"
            )

            # Step 5 — cap enforcement: evict lowest-value memories if over cap (D-08)
            count = await database.count_user_memories(self._pool, user_id)
            if count > config.MEMORY_MAX_PER_USER:
                eviction_rows = await database.get_user_memories_for_eviction(
                    self._pool, user_id=user_id
                )
                # Map to MemoryFact for choose_eviction (similarity=0.0, unused by eviction)
                eviction_facts = [
                    MemoryFact(
                        id=int(row["id"]),
                        fact=row["fact"],
                        salience=float(row["salience"]),
                        hit_count=int(row["hit_count"]),
                        created_at=row["created_at"],
                        last_seen_at=row["last_seen_at"],
                        last_surfaced_at=row["last_surfaced_at"],
                        surface_count=int(row["surface_count"]),
                        similarity=0.0,  # not used by choose_eviction
                    )
                    for row in eviction_rows
                ]
                ids_to_evict = choose_eviction(eviction_facts, config.MEMORY_MAX_PER_USER)
                if ids_to_evict:
                    await database.evict_lowest_salience(
                        self._pool, user_id=user_id, ids=ids_to_evict
                    )
                    log.debug(
                        f"memory.remember: evicted {len(ids_to_evict)} memories "
                        f"(count was {count}, cap={config.MEMORY_MAX_PER_USER}) "
                        f"user={user_id}"
                    )

        except Exception as e:
            # Swallow all unexpected errors — remember() is fire-and-forget from cogs.
            # A write failure must NEVER crash the ambient-roast or music event path.
            log.debug(
                f"memory.remember: unexpected error swallowed "
                f"({type(e).__name__}: {e}) user={user_id} kind={kind}"
            )
