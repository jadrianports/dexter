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

from datetime import datetime, timezone

import asyncpg

import config
import database
from models.memory import MemoryFact, apply_floor, rerank
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
