# Project Research Summary

**Project:** Dexter Discord Bot — v1.2 / Phase 11 (RAG long-term memory)
**Domain:** Durable semantic long-term memory (pgvector-on-Neon + Gemini embeddings) bolted onto a shipped, layered discord.py + asyncpg + google-genai bot
**Researched:** 2026-06-26
**Confidence:** HIGH (integration mechanics + stack); MEDIUM (retrieval-quality numeric defaults — flagged for a validation spike)

> **Scope note:** This research covers ONLY the RAG/pgvector feature (Phase 11). The rest of v1.2 — reliability hardening, test coverage, music/UX polish — is work on known code and was deliberately NOT researched. The roadmapper should treat Phase 11 as the researched slice and structure the other v1.2 work from existing knowledge.

## Executive Summary

Phase 11 adds a **third memory layer** to Dexter. The bot already has short-term memory (MessageBuffer, 10 msgs/channel, in-RAM) and structured/deterministic memory (Postgres: song_history, user_artist_counts, streaks). The new layer is **semantic/episodic** — pgvector + Gemini embeddings storing distilled, declarative facts (opinions, reactions, notable events, banter) that SQL cannot express, retrieved at roast time to power callback roasts. The payoff pattern is **stat x episode**: a hard number from SQL (mr brightside, 14 plays since april) paired with a recalled moment from pgvector (right after you swore you were done with the killers). The design reuses the existing Neon Postgres and the existing Gemini API key: **zero new infrastructure, zero new monthly cost, one new pip dependency.**

The recommended approach is opinionated and well-converged across the four research files. Embed with **gemini-embedding-001 at 768 dimensions** (NOT the deprecated text-embedding-004, sunset 2026-01-14 — the brief/PROJECT.md still name it and it must be corrected). Add **pgvector (>=0.3.6,<0.5)** as the only new dependency, enable the extension on Neon, and register the asyncpg vector codec in the pool init= callback. Embeddings get their **own rate limiter** (~60 RPM under the ~100 RPM endpoint quota), kept entirely off the shared 15 RPM chat budget, and run off the 3s interaction critical path. The feature integrates as **one new service (services/memory.py), one new model module (models/memory.py), one new table (user_memories), one new Gemini primitive (embed()), and a backward-compatible optional memories= kwarg** into the prompt builder — the layered architecture is not restructured.

The dominant risks are an **accuracy firewall** (Critical Rule 5: never embed numbers SQL already answers — the embedded count freezes while live SQL keeps counting; numbers always come from a live SELECT, memories are only candidate ammo the model may NOOP), a **boot-ordering trap** (register_vector raises ValueError if the vector type does not exist yet — run CREATE EXTENSION on a throwaway connection BEFORE create_pool(init=...)), **budget/latency discipline** (separate embedding limiter, defer-first, no per-message writes), and **context rot + sensitivity** (per-user cap + decay sweep + a PII/sensitivity gate all ship in v1, not deferred). statement_cache_size=0 (the Neon/PgBouncer requirement) is a verified NON-issue — the codec is a per-connection set_type_codec, not a prepared statement.

## Key Findings

### Recommended Stack

The only new dependency is the pgvector Python package; everything else (asyncpg 0.31.0, google-genai, the Neon pool) is already wired. The extension lives on the existing Neon Postgres. At the expected corpus size (hundreds to low-thousands of rows) a **sequential scan is sub-millisecond — no ANN index is needed on day one**; if/when it grows past ~10k rows, add **HNSW** (vector_cosine_ops), never IVFFlat (centroid training is garbage on a tiny/empty table). Index only at <=2000 dims, which 768 satisfies.

**Core technologies:**
- **gemini-embedding-001 @ 768 dims** (output_dimensionality=768): embedding model — current GA model; text-embedding-004 is DEPRECATED (2026-01-14). 768 is the indexable MRL sweet spot (ANN cap is 2000 dims; default 3072 would be unindexable). Use RETRIEVAL_DOCUMENT task_type on write, RETRIEVAL_QUERY on read.
- **pgvector extension on Neon Postgres** + **pgvector>=0.3.6,<0.5 pip package**: register_vector in the pool init= callback registers the codec so you pass/receive plain list[float]. Cosine (<=>, vector_cosine_ops) — scale-invariant, so no numpy normalization needed.
- **Separate embedding _RateLimiter** (~60 RPM): embeddings hit a different ~100 RPM Google quota; never route through the shared 15 RPM chat limiter (would starve /ask). Batch writes (embed_content(contents=[...]) produces N facts in 1 call).

See `.planning/research/STACK.md` for the full asyncpg+pgvector+Neon integration pattern.

### Expected Features

Memory exists to power callback roasts, not to be a generic knowledge store. The load-bearing principle: **structured SQL owns numbers; the semantic layer owns episodes/opinions.** See `.planning/research/FEATURES.md`.

**Must have (table stakes / Phase 11 v1):**
- Durable cross-restart store (user_memories on Neon + pgvector)
- Distilled declarative facts (0-3 atomic third-person sentences per event/session), NOT raw logs
- Per-user (+per-guild) scoped semantic retrieval (top-k=8 -> 0.70 similarity floor -> top 1-3)
- Write-time dedup (cosine sim >0.90 -> NOOP/bump, else insert)
- Callback roast: SQL stat + recalled episode handed to Gemini as candidate ammo, accuracy guaranteed
- Memory hygiene baseline: per-user cap (~150) + decay sweep (~90d on low salience) — **ships in v1, NOT deferred**
- Sensitivity/PII gate in the distill prompt — **ships in v1 (stop-ship), NOT deferred**

**Should have (add after validation, v1.x):**
- Salience/novelty re-rank tuning (trigger: callbacks feel obvious/repetitive)
- Surface-cooldown / anti-repeat (last_surfaced_at + novelty penalty)
- /forget owner control to prune a misfired memory

**Defer / out of scope (anti-features):**
- Embedding every message; embedding play counts/numbers
- Knowledge-graph / multi-hop memory; a reranker model in the loop
- Cross-user "server lore" memory (scoping/privacy unresolved)
- Historical backfill — **start empty, accumulate forward**

### Architecture Approach

Integrate, do NOT redesign. The new service sits exactly where every other service sits (wired in bot.py:_initialize_once, attached as bot.memory_service, accessed via self.bot.memory_service). The read path adds **zero generation calls** to the user critical path — the roast generation is the existing gemini.chat() call; memory only enriches the system prompt, plus one cheap embedding (separate quota, behind defer()). See `.planning/research/ARCHITECTURE.md`.

**Major components:**
1. **services/memory.py (MemoryService)** — NEW: owns the RAG lifecycle (recall(), remember(), sweep()) and the embedding limiter; constructed with (pool, gemini_service).
2. **models/memory.py** — NEW: MemoryFact dataclass + PURE rerank/recency/novelty/dedup functions (the TDD seam, mirrors compute_streak).
3. **user_memories table in SCHEMA_SQL** + 6 query helpers in database.py (insert/search/bump/delete_expired/count/evict); CREATE EXTENSION IF NOT EXISTS vector at the top (idempotent, plain DDL).
4. **services/gemini.py** — MOD: generic embed(texts, task_type, priority) + a second _embed_limiter.
5. **personality/prompts.py:build_chat_prompt** — MOD: optional backward-compatible memories= kwarg rendering a labelled sub-block in the existing USER CONTEXT region (empty-string fallback = byte-identical to today prompt).

### Critical Pitfalls

Top items from `.planning/research/PITFALLS.md` (18 total, mapped to sub-phases):

1. **Extension-vs-pool ordering** — register_vector raises ValueError: unknown type: public.vector if the type is not there when the pool warms connections. Run CREATE EXTENSION on a throwaway asyncpg.connect() BEFORE create_pool(init=...). (11.1)
2. **Embedding SQL-known numbers** — freezes a count that live SQL keeps changing, a Critical Rule 5 violation. Never embed counts/dates/rankings; numbers always from a live SELECT, memories supply only the episode. (11.4/11.5)
3. **Dimension mismatch** — default 3072 vs vector(768) column throws on insert; a vector(3072) fix is unindexable (2000-dim cap). Set output_dimensionality=768 on BOTH doc and query embeds via one shared config constant. (11.1/11.2)
4. **Sharing the 15 RPM chat limiter** — starves /ask for no reason (embeddings are a separate quota). Separate ~60 RPM limiter, priority-2 background writes. (11.2)
5. **No similarity floor** — ANN always returns something; without a ~0.70 floor a roast cites an irrelevant memory. No memory beats a wrong memory — inject nothing if nothing clears the floor. (11.3)
6. **Sync embed blows the 3s window** — defer() first, then embed/search/roast via create_task(). (11.3/11.5)
7. **Sensitive content / PII stored as durable roast ammo** — sensitivity + PII gate in the distill prompt, stop-ship, ships in v1. (11.4)
8. **Unbounded growth / context rot** — the #1 documented companion-bot failure. Per-user cap + decay sweep in v1. (11.6)

Note: statement_cache_size=0 breaking the codec is a **verified MISBELIEF** — do not hand-serialize vectors to strings.

## Implications for Roadmap

Phase 11 decomposes into **6 sub-phases** following the dependency chain (schema -> embedding -> retrieval -> write/distill -> integration -> hygiene). Each is independently verifiable (pure-logic TDD + clean boot). This ordering is consistent across STACK, FEATURES, ARCHITECTURE, and PITFALLS.

### Phase 11.1: Foundation — schema + extension + codec + config
**Rationale:** Everything depends on the store existing and the codec registering cleanly on boot; the extension-vs-pool ordering trap must be solved first.
**Delivers:** CREATE EXTENSION + user_memories in SCHEMA_SQL; extension-first bootstrap connection + init=_register_vector on create_pool; new config constants. No retrieval/write behavior yet.
**Avoids:** Pitfalls 1 (ordering), 2 (statement_cache_size misbelief), 3 (dims constant), 16 (idempotent DDL, no backfill), 18 (pool inherits K-04 tuning).

### Phase 11.2: Embedding primitive + retrieval read path
**Rationale:** Retrieval must exist before write, because dedup IS a retrieval call.
**Delivers:** GeminiService.embed() + separate _embed_limiter; database.search_memories (scoped ANN); MemoryFact + pure rerank/recency/novelty (TDD); MemoryService.recall() (embed query -> search -> 0.70 floor -> rerank -> top 1-3, returns empty cleanly when nothing clears).
**Uses:** gemini-embedding-001 @ 768, RETRIEVAL_QUERY, cosine <=>.
**Avoids:** Pitfalls 4 (separate limiter), 6 (defer-aware), 8 (floor), 11 (<=3 facts).

### Phase 11.3: Write path + dedup
**Rationale:** Depends on 11.2 — must be able to search before inserting.
**Delivers:** insert/bump/count/evict_memories helpers; MemoryService.remember() (distill -> embed -> dedup >0.90 -> insert/bump -> cap guard); pure dedup_decision.
**Avoids:** Pitfall 12 (dedup), and the cap half of 14.

### Phase 11.4: Distillation triggers + sensitivity gate
**Rationale:** Needs the write path; this is where the accuracy + sensitivity firewalls land.
**Delivers:** Hook remember() into already-firing notable-event paths (repeat-song, milestone, late-night, auto-queue ignored-memory) + a session-end/daily batch distill (one priority-2 call). Sensitivity + PII exclusion in the distill prompt. NEVER per-message.
**Avoids:** Pitfalls 4 (every message), 5 (embedding numbers), 9 (faithful distillation), 10 (sensitivity/PII — stop-ship).

### Phase 11.5: Prompt injection + callback-roast integration (capstone)
**Rationale:** Needs recall (11.2) and real stored content (11.4); this is the payoff.
**Delivers:** build_chat_prompt(memories=...) optional kwarg + accuracy-safe USER CONTEXT injection; wire recall() into /ask, /roast, _generate_ambient_roast. Roast cites a true SQL stat AND a recalled episode; memories framed as candidate ammo the model may NOOP.
**Avoids:** Pitfalls 7 (defer-first), 9 (ammo framing), 11 (cap).

### Phase 11.6: Hygiene & ops
**Rationale:** Last in build order but **in-scope for v1, not deferred polish** — unbounded memory is the #1 companion-bot failure.
**Delivers:** delete_expired_memories decay sweep (~90d low-salience); daily memory-sweep background task (mirrors cache_cleanup/ytdlp_update @tasks.loop); contradiction supersede. Per-user cap eviction already lands in 11.3.
**Avoids:** Pitfalls 13 (stale/contradictory), 14 (unbounded growth), 17 (premature/IVFFlat index).

### Phase Ordering Rationale

- **Retrieval before write** because dedup is itself a retrieval call (hard dependency).
- **Distillation triggers before the callback capstone** because the roast integration needs real stored content to surface.
- **Hygiene last in build order but shipped in v1** — research is unanimous that cap + decay + sensitivity gate are not optional polish.
- **No ANN index in v1** — seq scan is sub-ms at the expected scale; cargo-culting an index (especially IVFFlat on an empty table) is an anti-pattern.

### Research Flags

**Recommend a short research/validation spike at the START of Phase 11** (before 11.2 retrieval lands) to tune the numeric priors against this bot real scale and budget. All of the following are **tuned priors, not verified constants** (MEDIUM confidence): top-k=8, similarity floor 0.70, dedup threshold 0.90, per-user cap ~150, 90-day decay, rerank weights (relevance 1.0 + recency 0.5 + salience 0.7 + novelty 0.5), inject 1-3 facts / ~300-500 tokens.

- **Phase 11.2 / 11.3:** numeric defaults (floor, top-k, dedup threshold, rerank weights) — validate empirically; they are starting points.
- **Phase 11.1, 11.5, 11.6:** standard patterns, well-documented against the real files — **skip research-phase**; the integration points, boot ordering, prompt site, and sweep task pattern are all verified HIGH.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | pgvector/asyncpg init= codec + Gemini embeddings verified via Context7; text-embedding-004 deprecation + 100 RPM quota via Google docs. |
| Features | HIGH (architecture) / MEDIUM (numeric defaults) | Mem0, Generative Agents, companion-bot design converge on patterns; exact thresholds tuned to this bot, flagged for the spike. |
| Architecture | HIGH | All integration points verified against the real files (bot.py, database.py, gemini.py, prompts.py, cogs/ai.py, cogs/events.py, models/*). |
| Pitfalls | HIGH (integration/budget) / MEDIUM (retrieval-quality defaults) | Boot ordering, codec, dims, limiter verified; quality thresholds tuned. |

**Overall confidence:** HIGH for the mechanics and build order; MEDIUM only on the tunable retrieval-quality numbers, which are explicitly flagged for a validation spike.

### Gaps to Address

- **Numeric defaults (floor 0.70, top-k 8, dedup 0.90, cap 150, decay 90d, rerank weights):** tuned priors. Handle with a short empirical spike at the start of Phase 11 and observe retrieval quality during 11.2-11.5.
- **Stale text-embedding-004 reference:** the milestone brief and PROJECT.md still name it. Correct to gemini-embedding-001 during planning.
- **Salience scoring source:** how salience is assigned at write time (event type vs. distiller-judged) is under-specified — resolve in 11.3/11.4 planning.
- **Session-end trigger boundary:** exactly where the batch distill fires (voice-session-end vs. daily bg task vs. on_message hook) needs a concrete decision in 11.4.

## Sources

### Primary (HIGH confidence)
- Context7 /pgvector/pgvector-python — register_vector signature, asyncpg pool init= pattern, per-connection set_type_codec, ValueError on missing vector type, HNSW vector_cosine_ops, <=> operator.
- Context7 /googleapis/python-genai (v1.33.0) — aio.models.embed_content, EmbedContentConfig(output_dimensionality=, task_type=), gemini-embedding-001.
- Gemini API embeddings docs + Google Developers Blog — model GA status, MRL 768/1536/3072 tiers, default 3072.
- Existing code (verified): bot.py:_initialize_once, database.py (SCHEMA_SQL, K-04 pool tuning), services/gemini.py (_RateLimiter, priority tiers), personality/prompts.py (USER CONTEXT, 4 build_chat_prompt callers), cogs/ai.py, cogs/events.py, models/*.

### Secondary (MEDIUM confidence)
- Mem0 (arXiv 2504.19413) — ADD/UPDATE/DELETE/NOOP, similarity dedup, temporal supersede.
- Generative Agents (arXiv 2304.03442) — recency x relevance x importance retrieval, exponential decay.
- Companion-bot memory design + RAG retrieval-default write-ups — distilled facts, ~0.7 cosine threshold, decay/archive, context rot from unbounded saves.
- TokenMix gemini-embedding-001 guide — free-tier ~100 RPM, dimension tiers.

### Tertiary (LOW confidence)
- text-embedding-004 deprecation date 2026-01-14 (Google deprecation notice, corroborated by community thread) — directionally certain (deprecated), exact date secondary.

---
*Research completed: 2026-06-26*
*Ready for roadmap: yes*
