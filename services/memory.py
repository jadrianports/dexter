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

import json
import re as _re
from datetime import datetime, timedelta, timezone

import asyncpg

import config
import database
from logic.taste import resolve_decay_days
from models.memory import (
    MemoryFact,
    apply_floor,
    choose_eviction,
    compute_salience,
    contains_number,
    dedup_decision,
    is_sensitive,
    rerank,
)
from personality.prompts import DISTILL_PROMPT
from services.gemini import GeminiAPIError, GeminiRateLimitError, GeminiService
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
        kind: str | None = None,
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
            kind:       Phase 14 (OQ1) — optional exact-match filter forwarded
                        straight to database.search_memories, e.g.
                        "taste_episode" for D-03's positive-taste blend. Defaults
                        to None, which is byte-identical to pre-Phase-14 recall()
                        (no kind clause emitted at all — T-14-03: this can only
                        narrow the existing user_id scope, never widen it).

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
                kind=kind,
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
            log.debug(f"memory.recall: retrieval error, returning [] ({type(e).__name__}: {e})")
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
             bump the existing row's hit_count (near-duplicate — do NOT insert). When
             the MATCHED ROW's own kind is present in config.MEMORY_DECAY_DAYS_BY_KIND
             (e.g. taste_episode) also refresh that row's expires_at to a fresh
             short-decay horizon (D-05 self-refresh). Gating on the matched row's kind
             — not the incoming write's kind — keeps Phase 11 rows (absent from that
             map) untouched even when a taste_episode near-dups one (CR-13-01).
          4. Otherwise: insert a new row with a kind-aware expiry horizon — resolved
             via resolve_decay_days(kind, ...) so taste_episode inserts at the shorter
             TASTE_DECAY_DAYS while every Phase 11 kind keeps MEMORY_DECAY_DAYS (D-03).
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
                nearest_kind = rows[0]["kind"]
                if dedup_decision(nearest_sim, config.MEMORY_DEDUP_THRESHOLD):
                    # Near-duplicate: bump existing row, skip insert (MEM-04)
                    await database.bump_memory_hit(self._pool, nearest_id)
                    refresh_note = ""
                    # D-05 self-refresh: short-decay kinds (e.g. taste_episode) reset their
                    # expiry horizon on every re-distillation instead of aging out under a
                    # shorter TASTE_DECAY_DAYS while remaining true. Gated strictly on the
                    # MATCHED ROW's kind — not the incoming write's kind (CR-13-01). The
                    # k=1 ANN search is scoped by user_id only, so a taste_episode write
                    # can near-dup an existing Phase 11 row (e.g. daily_batch); refreshing
                    # that row's expires_at would silently violate the "Phase 11 kinds are
                    # never touched" invariant (defeat decay / shorten horizon). Gating on
                    # nearest_kind guarantees only rows that ARE short-decay kinds refresh.
                    if nearest_kind in config.MEMORY_DECAY_DAYS_BY_KIND:
                        new_expires = datetime.now(timezone.utc) + timedelta(
                            days=config.MEMORY_DECAY_DAYS_BY_KIND[nearest_kind]
                        )
                        await database.refresh_memory_expiry(self._pool, nearest_id, new_expires)
                        refresh_note = ", refreshed expires_at (D-05 self-refresh)"
                    log.debug(
                        f"memory.remember: near-dup detected (sim={nearest_sim:.3f} >= "
                        f"{config.MEMORY_DEDUP_THRESHOLD}), bumped id={nearest_id} "
                        f"user={user_id} kind={kind}{refresh_note}"
                    )
                    return

            # Step 4 — insert new row with decay horizon (D-03: kind-aware, e.g. taste_episode
            # gets the shorter TASTE_DECAY_DAYS horizon via config.MEMORY_DECAY_DAYS_BY_KIND;
            # every other kind falls back to config.MEMORY_DECAY_DAYS, byte-identical to Phase 11)
            expires_at = datetime.now(timezone.utc) + timedelta(
                days=resolve_decay_days(
                    kind,
                    default_days=config.MEMORY_DECAY_DAYS,
                    kind_overrides=config.MEMORY_DECAY_DAYS_BY_KIND,
                )
            )
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
            log.debug(f"memory.remember: inserted id={new_id} user={user_id} kind={kind} salience={salience:.2f}")

            # Step 5 — cap enforcement: evict lowest-value memories if over cap (D-08)
            count = await database.count_user_memories(self._pool, user_id)
            if count > config.MEMORY_MAX_PER_USER:
                eviction_rows = await database.get_user_memories_for_eviction(self._pool, user_id=user_id)
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
                    await database.evict_lowest_salience(self._pool, user_id=user_id, ids=ids_to_evict)
                    log.debug(
                        f"memory.remember: evicted {len(ids_to_evict)} memories "
                        f"(count was {count}, cap={config.MEMORY_MAX_PER_USER}) "
                        f"user={user_id}"
                    )

        except Exception as e:
            # Swallow all unexpected errors — remember() is fire-and-forget from cogs.
            # A write failure must NEVER crash the ambient-roast or music event path.
            log.debug(
                f"memory.remember: unexpected error swallowed ({type(e).__name__}: {e}) user={user_id} kind={kind}"
            )

    # -------------------------------------------------------------------------
    # distill — LLM-based episode extraction with stop-ship safety gates (MEM-05)
    # -------------------------------------------------------------------------

    async def distill(self, raw_text: str, *, exempt_numbers: bool = False) -> list[str]:
        """Distill raw_text into 0-3 atomic, third-person, number-free episode facts.

        Full pipeline:
          1. Send raw_text to Gemini using DISTILL_PROMPT as the system instruction
             (priority=2 — background, never contends with user /ask at priority=1).
          2. Parse the JSON array response tolerantly (strip fences, find array in prose).
          3. Apply stop-ship backstop: drop any fact where is_sensitive() is True; also
             drop contains_number() facts UNLESS exempt_numbers is set — the
             deterministic double-check after the LLM primary gate (T-11-05a / T-11-05b
             / D-01..D-03).
          4. Enforce 0-3 cap and return surviving facts.

        Returns [] when:
          - GeminiRateLimitError or GeminiAPIError (priority-2 background skip),
          - Response is not parseable JSON, or
          - All produced facts are blocked by the safety gates.

        Never raises — always degrades to [].

        Args:
            raw_text: The raw banter / notable-event context to distill. May
                      contain counts or PII — the distiller and backstop will drop them.
            exempt_numbers: When True, skip the contains_number() backstop (is_sensitive
                      still applies). Set only for kinds whose raw_text is number-free by
                      construction and whose sole digit source is a legitimate artist name
                      — e.g. taste_episode, where summarize_taste never interpolates a
                      count so a digit can only come from an artist like "Blink-182" or
                      "Twenty One Pilots" (WR-13-02). The taste accuracy firewall lives in
                      summarize_taste's number-free templates, not here.

        Returns:
            List of 0–3 atomic, safe fact strings (number-free unless exempt_numbers).
        """
        try:
            raw = await self._gemini.chat(
                DISTILL_PROMPT,
                [{"role": "user", "content": raw_text}],
                priority=2,
            )
        except (GeminiRateLimitError, GeminiAPIError) as e:
            log.debug(f"memory.distill: Gemini error, returning [] ({type(e).__name__}: {e})")
            return []
        except Exception as e:
            log.debug(f"memory.distill: unexpected Gemini error, returning [] ({type(e).__name__}: {e})")
            return []

        if not raw or not raw.strip():
            return []

        # Tolerant JSON parse (mirrors cogs/ai.py:parse_suggestions style)
        text = raw.strip()
        # Strip optional leading/trailing code fences (```json ... ```)
        text = _re.sub(r"^```(?:json)?\s*", "", text)
        text = _re.sub(r"\s*```$", "", text).strip()

        candidates: list[str] = [text]
        # Fallback: extract arrays from surrounding prose (non-greedy)
        candidates.extend(_re.findall(r"\[.*?\]", text, _re.DOTALL))

        facts: list | None = None
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            if isinstance(parsed, list):
                facts = parsed
                break

        if facts is None:
            log.debug("memory.distill: could not parse JSON array from model response")
            return []

        # Stop-ship backstop: drop sensitive or number-bearing facts (T-11-05a/b)
        safe: list[str] = []
        for f in facts:
            if not isinstance(f, str):
                continue
            f = f.strip()
            if not f:
                continue
            if is_sensitive(f):
                log.debug(f"memory.distill: is_sensitive blocked: {f!r}")
                continue
            if contains_number(f):
                if exempt_numbers:
                    # taste_episode (WR-13-02): the digit is an artist name, not an
                    # SQL-competing count — keep the fact but log the exemption so the
                    # decision stays observable.
                    log.debug(f"memory.distill: contains_number exempt (kept): {f!r}")
                else:
                    log.debug(f"memory.distill: contains_number blocked: {f!r}")
                    continue
            safe.append(f)
            if len(safe) >= 3:  # enforce 0-3 cap before returning
                break

        log.debug(f"memory.distill: produced {len(safe)} fact(s) from {len(facts)} model output(s)")
        return safe

    # -------------------------------------------------------------------------
    # distill_and_remember — orchestrate distill → remember (D-09 path 1 / MEM-04)
    # -------------------------------------------------------------------------

    async def distill_and_remember(
        self,
        *,
        user_id: str,
        guild_id: str | None,
        raw_text: str,
        kind: str,
        base_salience: float,
    ) -> None:
        """Distill raw_text into facts and store each surviving one via remember().

        Orchestration:
          1. distill(raw_text) → 0-3 safe, number-free facts (or []).
          2. For each surviving fact: remember(user_id, guild_id, fact, kind, salience).
             salience = compute_salience(base_salience) — the D-07 hybrid score.

        Always called via asyncio.create_task from cogs (fire-and-forget). Catches
        all errors silently so it NEVER raises into the task error handler (T-11-05e).

        Args:
            user_id:       Discord user ID — memory owner.
            guild_id:      Guild context for the event; None for cross-guild facts.
            raw_text:      Raw banter / event description to distill.
            kind:          Event kind; must be a key in config.MEMORY_SALIENCE_BASE_WEIGHTS.
            base_salience: Base salience weight from config.MEMORY_SALIENCE_BASE_WEIGHTS[kind].
        """
        try:
            # taste_episode facts derive from summarize_taste's number-free templates,
            # so any digit in a produced fact is a legitimate artist name (e.g.
            # "Blink-182", "Twenty One Pilots") rather than an SQL-known count. Exempt
            # them from the contains_number backstop so those artists are not silently
            # dropped (WR-13-02); is_sensitive still applies. Phase 11 kinds keep the
            # full firewall unchanged.
            facts = await self.distill(raw_text, exempt_numbers=(kind == "taste_episode"))
            salience = compute_salience(base_salience)
            for fact in facts:
                await self.remember(
                    user_id=user_id,
                    guild_id=guild_id,
                    fact_text=fact,
                    kind=kind,
                    salience=salience,
                )
        except Exception as e:
            log.debug(
                f"memory.distill_and_remember: error swallowed ({type(e).__name__}: {e}) user={user_id} kind={kind}"
            )

    # -------------------------------------------------------------------------
    # sweep — daily decay backstop (MEM-07 / D-08 / T-11-07a,b,c)
    # -------------------------------------------------------------------------

    async def sweep(self) -> int:
        """Delete expired low-salience memories; return the count deleted.

        Called daily by bot.py:memory_sweep @tasks.loop (2:30 UTC) to enforce
        the time-based decay backstop (MEM-07). Pairs with the write-time cap
        eviction in remember() (11-04) to keep the store permanently bounded.

        Sweeps rows where expires_at < now() AND salience < MEMORY_DECAY_SALIENCE_FLOOR
        — mirroring the decay_predicate logic in models/memory.py. High-salience
        facts (milestone, late_night, repeat_song) survive even when past expiry (D-08).

        Error handling (T-11-07c): all exceptions are caught and 0 is returned.
        The sweep NEVER raises into the daily loop — a transient DB error must not
        kill the background task (REL-02 discipline, mirrors ytdlp_update pattern).

        Returns:
            Number of rows deleted (0 on error or when nothing is eligible).
        """
        try:
            now = datetime.now(timezone.utc)
            deleted = await database.delete_expired_memories(self._pool, now=now)
            if deleted:
                log.info("memory.sweep: deleted %d expired low-salience memories", deleted)
            else:
                log.debug("memory.sweep: no expired memories found")
            return deleted
        except Exception as e:
            log.warning(
                "memory.sweep: error swallowed (%s: %s) — sweep will retry tomorrow",
                type(e).__name__,
                e,
            )
            return 0
