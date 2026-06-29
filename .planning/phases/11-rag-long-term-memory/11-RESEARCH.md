# Phase 11: RAG Long-Term Memory - Research

**Researched:** 2026-06-29
**Domain:** Durable semantic/episodic memory (pgvector-on-Neon + Gemini embeddings) bolted onto a shipped discord.py + asyncpg + google-genai bot
**Confidence:** HIGH (integration mechanics, stack, architecture, pitfalls); MEDIUM (numeric retrieval defaults — flagged for an opening validation spike)

> **Provenance note.** This file CONSOLIDATES the authoritative project-level research in `.planning/research/{SUMMARY,STACK,FEATURES,ARCHITECTURE,PITFALLS}.md` (researched 2026-06-26, HIGH confidence, Context7-verified) into the single phase-level file the planner reads, and adds the `## Validation Architecture` section that drives Nyquist `VALIDATION.md` generation. Mechanics claims below were RE-VERIFIED against the live codebase on 2026-06-29 (see `## Live Codebase Verification`). The five research files remain the deeper authority; this file is the planner's entry point.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Sensitivity / PII gate (MEM-05 — stop-ship, ships in v1):**
- **D-01:** The distill-time sensitivity gate blocks **identity & wellbeing** content: mental health, self-harm, medical conditions, sexuality, grief / relationship trauma, real-world PII (names, addresses, phone/email), and **anything said in apparent distress**. When in doubt about these categories, drop the memory.
- **D-02:** Everything else is **fair game** for durable roast ammo: music-taste cringe, hypocrisy, 3am binge sessions, light/comedic drama. The bot stays funny; it doesn't punch at vulnerability.
- **D-03:** This is a **stop-ship** gate (a blocked item is never stored), not a soft filter, and it ships in Phase 11 — never deferred.

**Callback cadence / feel (MEM-06):**
- **D-04:** Recalled memories surface as an **occasional payoff**, NOT on every roast that has ammo. Callbacks hit harder when rarer.
- **D-05:** **Anti-repeat is promoted INTO Phase 11** (research had it as "should-have v1.x"): track `last_surfaced_at` per memory and apply a **novelty / recently-surfaced penalty** so the same callback doesn't go stale. The cadence decision (D-04) depends on this, so it is in-scope here.
- **D-06:** Memories remain **candidate ammo the model may NOOP** — backward-compatible injection; any hard numbers in the output still come from live SQL, never from a memory.

**Salience source (research-flagged gap — resolved):**
- **D-07:** Salience is scored at write time by a **hybrid**: event type sets a **base weight** (milestone > late-night > repeat-song > auto-queue-ignored …), and the **distiller may bump** the score for a genuinely spicy/notable one-off moment. Deterministic floor + LLM flexibility.
- **D-08:** This salience score is what the **decay sweep + per-user cap eviction** rank on (low salience ages out first).

**Write triggers / distill boundary (research-flagged gap — resolved; MEM-04):**
- **D-09:** Two write paths fire the distiller, **never per-message**:
  1. **Notable-event hooks (immediate):** repeat-song, milestone, late-night, auto-queue ignored-memory — the already-firing notable-event paths in `cogs/events.py` / `cogs/music.py`.
  2. **Once-daily batch:** a daily background task (mirrors `cache_cleanup` / `ytdlp_update` `@tasks.loop`) distills the day's banter from message buffers in one priority-2 call.
- **D-10:** **No voice-session-end trigger** — explicitly rejected to avoid a third write path; the daily batch covers session banter.

### Claude's Discretion
- All numeric retrieval defaults (top-k, similarity floor, dedup threshold, per-user cap, decay window, rerank weights, injected-fact count/token budget) are **NOT decided** — they are MEDIUM-confidence tuned priors to be validated by the **opening numeric-defaults validation spike** and observed during 11.2–11.5. Planner owns the spike; defaults from research are the starting points.
- Exact salience base-weights per event type, and the precise distiller-bump mechanism, are implementation detail for 11.3/11.4 planning.
- All boot-ordering, codec registration, prompt-injection site, and sweep-task patterns are research-verified HIGH — follow the canonical refs, no re-litigation.

### Deferred Ideas (OUT OF SCOPE)
- **`/forget` owner command** — research "should-have v1.x". Deferred (decay + cap already bound the store; add later only if real misfires demand it).
- **Cross-user / "server lore" memory** — anti-feature for now (scoping + privacy unresolved). Future milestone if ever.
- **Salience/novelty re-rank deep tuning** beyond the in-phase hybrid + anti-repeat — revisit if callbacks feel obvious/repetitive after the spike + live observation.
- **HNSW ANN index** — not in v1 (seq scan is sub-ms at hundreds–low-thousands of rows). Add `vector_cosine_ops` HNSW only past ~10k rows; never IVFFlat on a tiny/empty table.
- **Embedding every message** / embedding SQL-known numbers / knowledge-graph / reranker model in the loop / historical backfill — all anti-features.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MEM-01 | `pgvector` enabled on Neon; `user_memories` table with `vector(768)` column; codec registered on pooled connections, boot-order-safe (`CREATE EXTENSION` before pool creation) | Standard Stack (pgvector 0.4.x py pkg + ext on Neon); Pattern 3 (extension-first boot); Pitfall 1 (ordering trap) — **verified HIGH** against `bot.py:_initialize_once` + `database.py:SCHEMA_SQL` |
| MEM-02 | `MemoryService.embed()` uses `gemini-embedding-001` @ 768d behind a **separate** embedding rate limiter (never the shared 15 RPM chat budget); off the 3s defer critical path | Pattern 2 (separate `_embed_limiter` cloned from `services/gemini.py:_RateLimiter`); Pitfalls 6, 7 — **verified HIGH** (`_RateLimiter` takes `max_requests` arg; defer discipline already mandated) |
| MEM-03 | Retrieval returns top-k above a similarity floor, reranked (relevance + recency + salience + novelty), capped to 1–3, injects **nothing** when nothing clears the floor | `recall()` flow; pure rerank/recency/novelty fns in `models/memory.py` (TDD seam); Pitfalls 8, 11, 15. **Numeric defaults = spike (MEDIUM)** |
| MEM-04 | Write path distills + stores roast-worthy facts on event/session-end triggers (NEVER per-message) with write-time near-dup dedup | `remember()` flow; D-09 two write paths; pure `dedup_decision`; Pitfalls 4, 12 |
| MEM-05 | Sensitivity/PII gate prevents storing sensitive content; never embeds SQL-known facts (counts, streaks) — preserves Critical Rule 5 | D-01..D-03 stop-ship gate; Pattern 1 accuracy firewall; Pitfalls 5, 9, 10 |
| MEM-06 | Retrieved memories injected as optional backward-compatible "candidate ammo" for callback roasts; hard numbers come from live SQL | `build_chat_prompt(memories=...)` optional kwarg; Pattern 4; accuracy-safe injection site — **verified HIGH** (signature at `prompts.py:91`, 4 callers) |
| MEM-07 | Memory hygiene ships in v1.2 — per-user cap (~150) + decay/expiry sweep for low-salience facts | `sweep()` + `delete_expired_memories` daily `@tasks.loop`; cap eviction in `remember()`; Pitfalls 13, 14 |
</phase_requirements>

## Summary

Phase 11 adds Dexter's **third memory layer**: a durable semantic/episodic store (`pgvector` on the existing Neon Postgres + `gemini-embedding-001` @ 768d) holding distilled, declarative facts (opinions, reactions, notable events, banter) that SQL cannot express. The payoff is the **stat × episode** callback roast: a hard number from live SQL ("mr brightside, 14 plays since april") paired with a recalled pgvector episode ("right after you swore you were done with the killers"). It reuses the existing Neon DB and existing Gemini key: **zero new infrastructure, zero new monthly cost, one new pip dependency (`pgvector`).**

The design is opinionated and converged across all five research files. Integrate, do NOT redesign: one new service (`services/memory.py`), one new model module (`models/memory.py`), one new table (`user_memories`), one new Gemini primitive (`GeminiService.embed()` + a second `_embed_limiter`), and one backward-compatible optional `memories=` kwarg into `build_chat_prompt`. The build order follows a strict dependency chain across 6 sub-phases (schema → embedding/retrieval → write/dedup → distill triggers + gate → callback integration → hygiene), opened by a numeric-defaults validation spike.

The dominant risks are the **accuracy firewall** (never embed numbers SQL already answers — Critical Rule 5), a **boot-ordering trap** (`register_vector` raises `ValueError` if the `vector` type doesn't exist when the pool warms connections), **budget/latency discipline** (separate embedding limiter, defer-first, no per-message writes), and **context rot + sensitivity** (per-user cap + decay sweep + a stop-ship PII/sensitivity gate, all in v1). The `statement_cache_size=0` "breakage" is a **verified MISBELIEF** — `register_vector` is a per-connection `set_type_codec`, not a prepared statement.

**Primary recommendation:** Open with the numeric-defaults spike, then execute 11.1→11.6 exactly per the canonical refs. Mechanics are settled (HIGH); the only genuine open variable is the retrieval-quality numbers, which the spike owns. Correct the stale `text-embedding-004` references in `PROJECT.md`/`CLAUDE.md` to `gemini-embedding-001` @ 768d during planning.

## Live Codebase Verification (2026-06-29)

Every HIGH-confidence mechanics claim from the project research was re-checked against the live files. All confirmed:

| Claim | Verification | Result |
|-------|--------------|--------|
| `build_chat_prompt` signature is 3-param at ~line 91, 4 callers | `personality/prompts.py:91` = `def build_chat_prompt(mood: str, user_summary: str | None, seasonal: str) -> str`. Callers: `cogs/ai.py` (/ask, /roast), `cogs/events.py` (ambient), plus tests. `USER CONTEXT:`/`{user_context}` + trailing `{seasonal_context}` block confirmed at lines 57–60 | **VERIFIED** [VERIFIED: codebase grep] |
| Empty/None `memories=` must render byte-identical | Current builder `.rstrip()`s and `seasonal=""` already renders cleanly (test `test_empty_seasonal_no_artifact`). A `{memory_context}` slot defaulting to `""` preserves byte-identity | **VERIFIED** — add slot + empty fallback |
| `_RateLimiter` is cloneable for a separate limiter | `services/gemini.py:34` `_RateLimiter(max_requests: int | None = None, window_seconds: float = 60.0)` — already parameterized; `_embed_limiter = _RateLimiter(max_requests=config.EMBED_RPM_LIMIT)` is a one-liner. Priority-2 reject-if-wait>10s path confirmed at lines 90–93 | **VERIFIED** [VERIFIED: codebase grep] |
| Pool created in `_initialize_once`; K-04 tuning present | `bot.py:342` `asyncpg.create_pool(... ssl='require', statement_cache_size=config.DB_STATEMENT_CACHE_SIZE (0), max_inactive_connection_lifetime=config.DB_MAX_INACTIVE_CONN_LIFETIME (240))` then `await init_db(bot.pool)` at 351. The `init=` kwarg is NOT yet present — to be added | **VERIFIED** — insert ext-first bootstrap + `init=_register_vector` |
| `SCHEMA_SQL` is plain idempotent DDL, single `conn.execute` | `database.py:67–162`, run via one `conn.execute(SCHEMA_SQL)` at line 170; comment confirms "no $N params" constraint. `CREATE EXTENSION IF NOT EXISTS vector;` + `user_memories` DDL fit this pattern | **VERIFIED** [VERIFIED: codebase grep] |
| `statement_cache_size=0` does NOT break the codec | Per STACK.md §2 + Context7 `/pgvector/pgvector-python`: `register_vector` calls `set_type_codec` (per-connection), not a prepared statement. K-04 flags coexist | **VERIFIED MISBELIEF** [CITED: STACK.md §2 / Context7] |
| Pure-logic TDD seam exists | `database.py:compute_streak` (pure, clock-injectable via tz arg) + `models/user_profile.py` + the Phase 10 `logic/` package (`logic/playback.py`, `logic/health.py`, `logic/roasts.py`) establish the convention `models/memory.py` follows | **VERIFIED** [VERIFIED: codebase grep] |
| Daily `@tasks.loop` template exists | `bot.py` runs `cache_cleanup` / `ytdlp_update` background loops; STATE.md confirms `before_loop`/`wait_until_ready` pattern. Daily distill-batch + daily sweep mirror these | **VERIFIED** [CITED: ARCHITECTURE.md / STATE.md] |
| `pgvector` pip package exists & current | `pip index versions pgvector` → 0.4.2 available (0.3.6–0.4.2 in the recommended `>=0.3.6,<0.5` range); 0.4.2 installed locally | **VERIFIED** [VERIFIED: PyPI] |

**Net:** no research claim was contradicted by the live code. The only deltas vs. research line-number references are cosmetic (file has grown since 2026-06-26); the integration anchors (`build_chat_prompt`, `_RateLimiter`, `create_pool`+`init_db`, `SCHEMA_SQL`) are all exactly where research said.

## Project Constraints (from CLAUDE.md)

The planner must verify every plan against these (same authority as locked decisions):

- **Language/stack fixed:** Python 3.11+, discord.py ≥2.3, asyncpg 0.31.0 → **Neon serverless Postgres** (no colocated Postgres container). `google-genai` SDK (NOT deprecated `google-generativeai`).
- **Critical Rule 5 — never sacrifice factual accuracy for personality.** This is the load-bearing rule for the entire accuracy firewall (numbers from live SQL only). Non-negotiable.
- **Critical Rule 1 — all AI features share the 15 RPM Gemini limit via the global limiter.** Embeddings are the explicit exception: a **separate** ~60 RPM `_embed_limiter` (embeddings hit a different ~100 RPM Google quota). Do not route through the chat limiter.
- **Lowercase personality, one emoji max, dial back sarcasm for serious/emotional questions** — the last extends into the write gate (D-01) and the roast prompt (D-06).
- **3s slash-interaction rule:** `defer()` or respond immediately, then async work via `asyncio.create_task()`. Memory adds zero synchronous latency before the interaction ack.
- **Neon pool tuning (K-04):** `statement_cache_size=0`, `ssl='require'`, bounded `max_inactive_connection_lifetime` (~240s). The new codec-registering pool inherits all of these unchanged.
- **asyncpg multi-statement DDL** only works with no `$N` params — `SCHEMA_SQL` stays plain DDL (the `CREATE EXTENSION` + `user_memories` additions comply).
- **Stale-reference correction required:** `CLAUDE.md` and `.planning/PROJECT.md` still name the deprecated `text-embedding-004` (sunset 2026-01-14). Phase 11 uses `gemini-embedding-001` @ 768d — correct during planning (tracked in STATE.md blockers).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Vector storage + ANN search | Database / Storage (Neon + pgvector) | — | The `vector(768)` column + `<=>` cosine search live in Postgres; reuses existing infra |
| Embedding generation | API / Backend (`GeminiService.embed`) | External (Gemini embeddings endpoint) | Thin SDK wrapper gains a generic `embed()` primitive; separate quota |
| RAG lifecycle (recall/remember/sweep) | API / Backend (`services/memory.py`) | — | Owns the orchestration + embedding limiter; constructed with `(pool, gemini_service)` |
| Pure scoring (rerank/recency/novelty/dedup/salience) | API / Backend pure-logic (`models/memory.py`) | — | Deterministic math, no I/O — the TDD seam |
| Prompt enrichment | API / Backend (`personality/prompts.py`) | — | Optional `memories=` kwarg renders into existing `USER CONTEXT` block |
| Write/read triggering | Cogs (Discord I/O) (`cogs/ai.py`, `cogs/events.py`, `cogs/music.py`) | — | Cogs call `self.bot.memory_service.recall()/remember()` at roast/notable-event surfaces |
| Hard numbers (counts, streaks) | Database / Storage (SQL, existing) | — | Accuracy firewall: numbers ALWAYS from live `SELECT`, never from a vector |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pgvector` (Postgres extension) | 0.8.x (Neon-provided) | `vector` column type + distance operators + ANN index types on the existing Neon DB | Zero new infra — extension on the DB already in use; Neon ships it on all plans. `CREATE EXTENSION IF NOT EXISTS vector;` |
| `pgvector` (Python pkg) | **0.4.x** (pin `>=0.3.6,<0.5`) | `from pgvector.asyncpg import register_vector` codec; pass/receive `list[float]` | Canonical maintained asyncpg integration; removes hand-serialization of vectors. **[VERIFIED: PyPI]** 0.4.2 current |
| `gemini-embedding-001` @ 768d | GA model | Turns fact/query text into 768-d vectors via the existing `google-genai` client | Current GA embedding model; MRL-truncatable to 768/1536/3072; 768 is the indexable sweet spot (ANN cap 2000). Replaces deprecated `text-embedding-004`. `RETRIEVAL_DOCUMENT` on write, `RETRIEVAL_QUERY` on read |
| `asyncpg` | 0.31.0 (already installed) | Pool + per-connection `init=` callback that registers the codec | Already the driver; `create_pool(init=...)` is exactly where `register_vector` runs. No bump |
| `google-genai` | already installed (≥1.x) | `client.aio.models.embed_content(...)` async embeddings | Same SDK + `genai.Client` already wired in `services/gemini.py` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none) | — | The feature needs **only** the `pgvector` pip package | No numpy, no LangChain, no vector-DB client |
| `numpy` (optional) | any | L2-normalize before inner-product `<#>` indexing | **Skip** — recommended cosine `<=>` is scale-invariant, no normalization needed |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `gemini-embedding-001` @ 768d | `text-embedding-004` | **Never** — deprecated 2026-01-14 (past); calls rejected |
| 768 dims | 1536 / 3072 | Only if 768 recall proves weak; 3072 forces `halfvec` to stay indexable (>2000 cap) + 4× storage. Bump to 1536 before 3072 |
| HNSW (or no index) | IVFFlat | IVFFlat trains centroids on data — garbage on a tiny/empty table. HNSW works from row zero. But **no index in v1** at this scale |
| Cosine `<=>` | Inner product `<#>` | Marginal speedup only with pre-normalized vectors + numpy dep — not worth it |
| pgvector on Neon | Pinecone/Qdrant/Chroma/Redis | Violates zero-new-infra / zero-cost; the whole point is reusing Neon |

**Installation:**
```bash
pip install "pgvector>=0.3.6,<0.5"     # add to requirements.txt — the ONLY new dependency
# already present (do NOT bump): asyncpg==0.31.0, google-genai
```
```sql
-- idempotent, plain DDL — top of SCHEMA_SQL; also run on a bootstrap connection BEFORE create_pool(init=...)
CREATE EXTENSION IF NOT EXISTS vector;
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `pgvector` (Python) | PyPI | est. ~3 yrs (0.1.0 → 0.4.2) | high (canonical pgvector binding) | github.com/pgvector/pgvector-python | unavailable | Approved [ASSUMED] |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

> slopcheck could not be installed in this environment ("slopcheck not available"). Per protocol, the one new package is tagged `[ASSUMED]` rather than `[VERIFIED]`, and the planner SHOULD gate the `pip install pgvector` step behind a `checkpoint:human-verify` task before install. Mitigating evidence: `gemini-embedding-001` + pgvector integration was Context7-verified via `/pgvector/pgvector-python` in STACK.md; `pip index versions pgvector` confirms 0.4.2 on PyPI with the expected version history; the package is the canonical binding referenced in official pgvector docs. The package name was discovered from authoritative Context7 docs (not WebSearch), but absent a successful slopcheck run it remains `[ASSUMED]`.

## Architecture Patterns

### System Architecture Diagram

```
                          COGS (Discord I/O)
   cogs/ai.py /ask /roast    cogs/events.py ambient    cogs/music.py notable-event
        │ READ                   │ READ                      │ WRITE (remember)
        │                        │                           │
        ▼                        ▼                           ▼
                    SERVICES (logic, no Discord types)
   ┌───────────────────────────┐         ┌──────────────────────────────┐
   │ services/memory.py  ★NEW  │ chat    │ services/gemini.py (EXISTING) │
   │  recall()  READ           │────────▶│  chat()  (distill, priority 2)│
   │  remember() WRITE         │ embed   │  embed() ★NEW + _embed_limiter│
   │  sweep()                  │◀────────│  (separate ~60 RPM quota)     │
   └─────────┬─────────────────┘         └──────────────────────────────┘
             │ pure scoring fns
             ▼
   ┌───────────────────────────┐    ┌────────────────────────────────┐
   │ models/memory.py    ★NEW  │    │ personality/prompts.py (MOD)   │
   │  MemoryFact + pure        │    │  build_chat_prompt(memories=)  │
   │  rerank/recency/novelty/  │    │   → USER CONTEXT sub-block     │
   │  dedup/salience (TDD)     │    └────────────────────────────────┘
   └─────────┬─────────────────┘
             ▼            DATA (database.py + Neon)
   ┌──────────────────────────────────────────────────────────────┐
   │ database.py (MOD): SCHEMA_SQL += CREATE EXTENSION vector;     │
   │   + user_memories table; insert/search/bump/count/evict/      │
   │     delete_expired helpers                                     │
   │ bot.py (MOD): ext-first bootstrap → create_pool(init=         │
   │   register_vector) → wire memory_service → start sweep loop    │
   └──────────────────────────────────────────────────────────────┘
   song_history / user_profiles (numbers = ground truth)  |  user_memories ★NEW (episodes)
```

**WRITE flow:** notable event → `remember(user_id, guild_id, raw_text)` → distill (gemini.chat, p2 → 0–3 atomic sentences, sensitivity-gated, NO numbers) → embed (RETRIEVAL_DOCUMENT, p2) → dedup (search top-1; sim >threshold → bump else insert) → cap guard (evict lowest salience×recency×hit_count if over cap).

**READ flow:** roast moment → `recall(user_id, guild_id, query_text)` → embed query (RETRIEVAL_QUERY, p1) → ANN search (scoped, top-k) → similarity floor (drop below) → rerank in Python (relevance + recency + salience + novelty) → keep top 1–3 → `build_chat_prompt(memories=facts)`. Empty when nothing clears the floor → byte-identical to today's prompt.

### Recommended Project Structure (delta only)
```
dexter/
├── services/
│   ├── gemini.py     # MOD: + embed(), + second _embed_limiter
│   └── memory.py     # ★NEW: MemoryService (recall/remember/sweep)
├── models/
│   └── memory.py     # ★NEW: MemoryFact + pure scoring fns (TDD)
├── database.py       # MOD: SCHEMA_SQL (+vector ext, +user_memories), + 6 helpers
├── bot.py            # MOD: ext-first ordering, pool init=, wire memory_service, sweep task
├── personality/
│   └── prompts.py    # MOD: build_chat_prompt(memories=...) injection
├── config.py         # MOD: embedding + retrieval + hygiene constants
├── cogs/
│   ├── ai.py         # MOD: /ask + /roast recall; try_auto_queue write hook (optional)
│   ├── events.py     # MOD: ambient-roast recall; notable-event write hook
│   └── music.py      # MOD: auto-queue ignored-memory write hook
└── tests/
    └── test_memory.py # ★NEW: pure rerank/decay/dedup/salience tests (no DB/Discord)
```

### Pattern 1: Three-layer memory — numbers stay in SQL (accuracy firewall)
**What:** RAG is the third layer (after `MessageBuffer` short-term and Postgres structured/deterministic). The firewall rule: the vector store NEVER holds a number a `SELECT COUNT(*)` can answer.
**When to use:** every write decision. "queued mr brightside 14 times" → SQL, do not embed. "swore he was done with the killers" → embed.
**Trade-off:** prevents embedded counts from drifting out of sync with live SQL (a direct Critical-Rule-5 violation). Costs distillation-prompt discipline. **Non-negotiable.** [CITED: ARCHITECTURE.md Pattern 1]

### Pattern 2: Separate embedding rate limiter
**What:** `GeminiService` gets a **second** `_RateLimiter(max_requests=config.EMBED_RPM_LIMIT)` (~60 RPM, under the ~100 RPM endpoint quota). The shared 15 RPM limiter stays for chat + image only.
**Example (verified-compatible with the live `_RateLimiter`):**
```python
# services/gemini.py — GeminiService.__init__
self._rate_limiter = _RateLimiter()                                      # existing 15 RPM (chat+image)
self._embed_limiter = _RateLimiter(max_requests=config.EMBED_RPM_LIMIT)  # NEW

async def embed(self, texts: list[str], *, task_type: str, priority: int = 2) -> list[list[float]]:
    await self._embed_limiter.acquire(priority)            # NOT self._rate_limiter
    resp = await self._client.aio.models.embed_content(
        model=config.EMBEDDING_MODEL,                      # "gemini-embedding-001"
        contents=texts,                                    # LIST → batch N facts in 1 call
        config=types.EmbedContentConfig(
            output_dimensionality=config.EMBED_DIM,        # 768 (indexable)
            task_type=task_type,                           # RETRIEVAL_DOCUMENT | RETRIEVAL_QUERY
        ),
    )
    return [e.values for e in resp.embeddings]
```
[CITED: ARCHITECTURE.md Pattern 2 / STACK.md] — `_RateLimiter(max_requests=...)` signature **[VERIFIED: codebase grep]**

### Pattern 3: pgvector codec registration — extension-first, then `init=` (the one real trap)
**What:** `register_vector(conn)` raises `ValueError: unknown type: public.vector` if the type doesn't exist. The pool's `init=` fires on every connection at pool-creation time — **before** `init_db()` runs `SCHEMA_SQL`. So `CREATE EXTENSION` must run on a throwaway connection first.
**Example (the real `bot.py:_initialize_once` change at ~line 342):**
```python
from pgvector.asyncpg import register_vector

# 1) Ensure the vector type exists BEFORE the codec-registering pool is built.
_boot = await asyncpg.connect(
    dsn=config.sanitize_database_url(config.DATABASE_URL),
    ssl="require", statement_cache_size=0,
)
try:
    await _boot.execute("CREATE EXTENSION IF NOT EXISTS vector;")
finally:
    await _boot.close()

# 2) Long-lived pool registers the codec on every connection.
async def _register_vector(conn: asyncpg.Connection) -> None:
    await register_vector(conn)

bot.pool = await asyncpg.create_pool(
    dsn=config.sanitize_database_url(config.DATABASE_URL),
    min_size=config.DB_POOL_MIN, max_size=config.DB_POOL_MAX,
    command_timeout=config.DB_COMMAND_TIMEOUT_SECONDS, ssl="require",
    max_inactive_connection_lifetime=config.DB_MAX_INACTIVE_CONN_LIFETIME,  # K-04: 240
    statement_cache_size=config.DB_STATEMENT_CACHE_SIZE,                    # K-04: 0
    init=_register_vector,                  # <-- only new line on create_pool
)
await init_db(bot.pool)                     # SCHEMA_SQL also carries the idempotent ext + table
```
**Trade-off:** one extra short-lived connection at boot. `statement_cache_size=0` is verified-compatible (codec is `set_type_codec`, not a prepared statement). [CITED: ARCHITECTURE.md Pattern 3 / Context7 `/pgvector/pgvector-python`] — live pool site **[VERIFIED: codebase grep]**

### Pattern 4: Retrieve-and-inject — zero extra generation call on the user's critical path
**What:** memory adds zero generation calls. The roast generation is the existing `gemini.chat()`; memory only enriches its system prompt. The only added read-path call is one cheap embedding (separate quota), behind `defer()`.
[CITED: ARCHITECTURE.md Pattern 4]

### Accuracy-safe prompt-injection site
**File:** `personality/prompts.py`. **Anchor:** the `USER CONTEXT:` block (lines 57–60), today rendering only `{user_context}` (the SQL taste summary). **[VERIFIED: codebase grep]**
```python
# DEXTER_SYSTEM_PROMPT, USER CONTEXT region — add a slot AFTER {user_context}:
USER CONTEXT:
{user_context}

{memory_context}        # NEW slot, empty string when nothing cleared the floor

def build_chat_prompt(mood, user_summary, seasonal, memories: list[str] | None = None) -> str:
    ...
    if memories:
        memory_context = (
            "THINGS YOU REMEMBER ABOUT THIS USER (episodes/opinions, not stats):\n"
            + "\n".join(f"- {m}" for m in memories)
            + "\nUse at most one of these, and only if it genuinely lands. "
              "Do NOT invent details beyond these lines. "
              "All numbers/counts come from USER CONTEXT above — never from these memories."
        )
    else:
        memory_context = ""
    return DEXTER_SYSTEM_PROMPT.format(..., memory_context=memory_context).rstrip()
```
**Why accuracy-safe:** memories carry no numbers (enforced at write); the instruction pins counts to SQL; empty fallback = byte-identical to today (zero regression for users with no facts); `memories` defaults to `None` so all 4 callers compile unchanged. [CITED: ARCHITECTURE.md] — signature + 4 callers + byte-identity **[VERIFIED: codebase grep]**

### Proposed schema (fits existing `SCHEMA_SQL` conventions)
```sql
CREATE EXTENSION IF NOT EXISTS vector;          -- top of SCHEMA_SQL

CREATE TABLE IF NOT EXISTS user_memories (
    id              BIGSERIAL PRIMARY KEY,
    user_id         TEXT NOT NULL,
    guild_id        TEXT,
    kind            TEXT,                        -- event type for base salience
    fact            TEXT NOT NULL,
    embedding       vector(768) NOT NULL,        -- 768-d gemini-embedding-001
    salience        REAL DEFAULT 0,
    hit_count       INTEGER DEFAULT 1,
    created_at      TIMESTAMPTZ DEFAULT now(),
    last_seen_at    TIMESTAMPTZ DEFAULT now(),
    last_surfaced_at TIMESTAMPTZ,                -- D-05 anti-repeat
    surface_count   INTEGER DEFAULT 0,
    expires_at      TIMESTAMPTZ                  -- decay sweep target
);
CREATE INDEX IF NOT EXISTS idx_user_memories_user ON user_memories(user_id, created_at DESC);
-- HNSW ANN index intentionally omitted at this scale (add past ~10k rows; never IVFFlat).
```
Exact columns are 11.1/11.3 planning detail; the shape above satisfies dedup, rerank, anti-repeat (D-05), salience (D-07/D-08), and decay (MEM-07). [CITED: STACK.md / FEATURES.md §1]

### Anti-Patterns to Avoid
- **Registering the codec before the extension exists** → boot crash. Run `CREATE EXTENSION` first (Pattern 3).
- **Embedding numbers/counts** → vector-SQL drift, Rule-5 violation. Numbers from live SELECT only.
- **Routing embeddings through the 15 RPM chat limiter** → starves `/ask`. Separate limiter.
- **Per-message distillation** → budget burn + context rot. Event + daily-batch only (D-09).
- **Changing `chat()`'s signature / adding a read-path generation call** → breaks thin-wrapper contract + adds latency. Enrich the system prompt; rerank in Python.
- **Unbounded per-user memory** → #1 companion-bot failure. Cap + decay in v1.
- **Hand-serializing vectors as `'[1,2,3]'` strings** (from the `statement_cache_size` misbelief) → text round-trip, broken distance queries. Use `register_vector`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Vector (de)serialization for asyncpg | `'[1,2,3]'` string formatting | `pgvector.asyncpg.register_vector` in pool `init=` | Binary-safe, type-safe, lossless; hand-rolling silently breaks `<=>` ordering |
| Cosine distance / ANN search | Python-side vector math | pgvector `<=> (vector_cosine_ops)` in SQL | DB does it in-engine, sub-ms at this scale; scale-invariant (no normalization) |
| Embedding rate limiting | A new throttle class | Clone the existing `_RateLimiter(max_requests=...)` | Already battle-tested with priority tiers + sliding window |
| Daily background sweep scheduling | Custom timer/thread | `discord.ext.tasks @tasks.loop` + `before_loop wait_until_ready` | Matches `cache_cleanup`/`ytdlp_update`; integrates with the bot lifecycle |
| Fact extraction / distillation | Regex/keyword heuristics | One Gemini `chat()` call with a constrained distill prompt | LLM handles paraphrase, atomicity, third-person; heuristics can't |
| Reranking | A second LLM call ("reranker model") | Pure Python score-and-sort in `models/memory.py` | Marginal gain at top-k=8 over a tiny corpus; wastes budget + adds latency |

**Key insight:** at this scale (hundreds–low-thousands of rows), the database and a small pure-Python rerank do everything a heavyweight RAG stack would — adding LangChain, a vector DB, or a reranker model is pure liability.

## Common Pitfalls

(18 pitfalls fully enumerated in `.planning/research/PITFALLS.md` with per-sub-phase mapping and a "Looks Done But Isn't" checklist. The 8 critical ones, condensed:)

### Pitfall 1: `register_vector` before the `vector` type exists (boot crash)
**What goes wrong:** every pooled connection fails its `init=` with `ValueError: unknown type: public.vector`; boot fails. **Why:** wrong order — codec-registering pool created before `CREATE EXTENSION` ran. **Avoid:** `connect()` → `CREATE EXTENSION` → `close()` → `create_pool(init=...)` (Pattern 3). **Warning signs:** that `ValueError` in boot logs; works on a manually-prepped DB but fails on a fresh Neon branch. **Phase:** 11.1

### Pitfall 2: Believing `statement_cache_size=0` breaks the codec (misbelief → hand-serialization)
**What goes wrong:** dev skips the codec, hand-serializes vectors as strings; asyncpg returns text not lists; distance queries silently degrade. **Avoid:** use `register_vector`; keep K-04 flags as-is — they coexist. **Phase:** 11.1

### Pitfall 3: Dimension mismatch (default 3072 vs `vector(768)`; 2000-dim ANN cap)
**What goes wrong:** insert throws `expected 768 dimensions, not 3072`; "fixing" to `vector(3072)` makes the column unindexable. **Avoid:** `output_dimensionality=768` on **both** doc and query embeds via one shared `EMBED_DIM` constant; column `vector(768)`. **Phase:** 11.1 (column) + 11.2 (constant)

### Pitfall 4: Embedding on every message (budget burn + context rot)
**What goes wrong:** distill per message floods the quota and fills the store with noise. **Avoid:** two write triggers only (D-09: notable-event hooks + daily batch). NEVER per-message. **Phase:** 11.4

### Pitfall 5: Embedding facts SQL already answers (accuracy drift)
**What goes wrong:** embedded count freezes while live SQL keeps counting → stale number cited → Rule-5 violation. **Avoid:** embed only opinions/episodes; numbers from live SELECT. **Phase:** 11.4 + 11.5

### Pitfall 6: Routing embeddings through the 15 RPM chat limiter (starves `/ask`)
**Avoid:** separate ~60 RPM `_embed_limiter`; priority-2 background writes; batch via `contents=[...]`. **Phase:** 11.2

### Pitfall 7: Sync embed blows the 3s interaction window
**What goes wrong:** embed inline before `defer()` → "application did not respond." **Avoid:** `defer()` first, then embed/search/roast in the followup via `create_task()`. **Phase:** 11.3/11.5

### Pitfall 8: No similarity floor (garbage recall)
**What goes wrong:** ANN always returns *something*; without a floor a roast cites an irrelevant memory. **Avoid:** apply the floor after fetch; inject nothing if nothing clears it — "no memory beats a wrong memory." **Phase:** 11.3

**Plus (moderate/ops):** prompt bloat (cap 1–3 facts / ~300–500 tokens), no write-time dedup, stale/contradictory memories (supersede on contradiction), unbounded growth (cap + decay), repeated callbacks (anti-repeat / D-05), live migration/backfill (idempotent DDL, no backfill in boot path), IVFFlat-on-empty / premature index, cold-start latency (defer absorbs it; warm pool inherits K-04). **Sensitivity/PII (Pitfall 10) is stop-ship and ships in 11.4 — see D-01..D-03.**

## Runtime State Inventory

> This is a **greenfield additive** phase (new table, new service, accumulate-forward — explicitly NO historical backfill). A rename/refactor inventory does not strictly apply, but the migration-adjacent items are noted:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `user_memories` starts **empty** and accumulates forward (anti-feature: historical backfill). No existing data to migrate. | None — idempotent `CREATE TABLE IF NOT EXISTS` |
| Live service config | Neon Postgres needs `CREATE EXTENSION vector` — applied idempotently in `SCHEMA_SQL` + a boot bootstrap connection. Neon ships pgvector on all plans (no console toggle needed). | Code-applied DDL; no manual Neon console step |
| OS-registered state | None — no OS-level registrations involved. | None — verified (pure in-process service + DB) |
| Secrets/env vars | Reuses existing `DATABASE_URL` + `GEMINI_API_KEY`. New `config.py` constants are plain module constants, not secrets. No new env var required. | None — verified |
| Build artifacts | One new pip dependency (`pgvector`) → `requirements.txt` update + reinstall. No compiled artifacts. | `pip install "pgvector>=0.3.6,<0.5"`; rebuild Docker image |

## Code Examples

Verified embedding call (write + read sides):
```python
# Source: STACK.md / Context7 /googleapis/python-genai
from google.genai import types

# WRITE (store a fact) — RETRIEVAL_DOCUMENT; contents is a LIST → batch many facts in 1 call
resp = await client.aio.models.embed_content(
    model="gemini-embedding-001",
    contents=[fact_text],
    config=types.EmbedContentConfig(output_dimensionality=768, task_type="RETRIEVAL_DOCUMENT"),
)
vec = resp.embeddings[0].values            # list[float], length 768

# READ (retrieve for a roast) — RETRIEVAL_QUERY (mismatching task_type degrades recall)
resp = await client.aio.models.embed_content(
    model="gemini-embedding-001",
    contents=[roast_context_text],
    config=types.EmbedContentConfig(output_dimensionality=768, task_type="RETRIEVAL_QUERY"),
)
query_vec = resp.embeddings[0].values
```
```python
# Scoped ANN search (cosine) after register_vector — pass/receive plain lists
rows = await conn.fetch(
    "SELECT id, fact, salience, created_at, last_surfaced_at, "
    "       1 - (embedding <=> $2) AS similarity "
    "FROM user_memories WHERE user_id = $1 "
    "ORDER BY embedding <=> $2 LIMIT $3",
    user_id, query_embedding_list, k,
)
# floor + rerank applied in Python (models/memory.py); 1 - cosine_distance = cosine_similarity
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `text-embedding-004` | `gemini-embedding-001` @ 768d | Deprecated 2026-01-14 | **Stale refs in CLAUDE.md + PROJECT.md must be corrected** |
| `google-generativeai` SDK | `google-genai` SDK | project standardized earlier | Use `client.aio.models.embed_content` |
| Default 3072-d embeddings | MRL-truncated 768-d | n/a | 768 indexable (under 2000-dim ANN cap) + cheaper |
| IVFFlat ANN index | HNSW (when needed) / no index at small scale | pgvector maturity | Never IVFFlat on tiny corpus |

**Deprecated/outdated:**
- `text-embedding-004` — sunset 2026-01-14; replaced by `gemini-embedding-001`.
- Hand-serialized vector strings — replaced by the `register_vector` codec.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `pgvector` Python package is legitimate/current (slopcheck unavailable; package name from Context7 docs, version from PyPI) | Package Legitimacy Audit | LOW — Context7-sourced + PyPI-confirmed; planner should still gate install behind `checkpoint:human-verify` |
| A2 | Gemini embeddings free-tier is ~100 RPM (separate quota from chat) → ~60 RPM limiter is safe | Stack / Pattern 2 | MEDIUM — if the real quota is lower, lower `EMBED_RPM_LIMIT`; harmless (writes are priority-2, skip on saturation) |
| A3 | All numeric retrieval defaults (top-k=8, floor 0.70, dedup 0.90, cap ~150, decay 90d, rerank weights rel 1.0/rec 0.5/sal 0.7/nov 0.5, inject 1–3 / ~300–500 tokens) | Validation Architecture / MEM-03 | MEDIUM — these are the central spike question; wrong values degrade recall quality, not correctness. The spike + 11.2–11.5 observation tune them |
| A4 | `text-embedding-004` sunset date 2026-01-14 is exact | State of the Art | LOW — directionally certain it's deprecated; exact date is secondary and doesn't change the recommendation |
| A5 | Salience base-weights per event type and the distiller-bump mechanism (D-07) | (11.3/11.4 planning detail) | LOW — Claude's discretion; tunable, no correctness risk |

**Action:** A1–A2 the planner should surface for confirmation (A1 via install checkpoint). A3 is the explicit spike charter. A4/A5 are low-risk.

## Open Questions

1. **Numeric retrieval defaults (the central validation question)**
   - What we know: research provides MEDIUM-confidence priors converged from Mem0 / Generative Agents / companion-bot prior art.
   - What's unclear: whether they hold at *this* bot's real scale (a few dozen users, hundreds–low-thousands of rows) and 15 RPM budget.
   - Recommendation: the planner-owned **numeric-defaults validation spike** opens Phase 11 (see Validation Architecture). Defaults are starting points; observe during 11.2–11.5.

2. **Daily-batch distill source granularity (D-09 path 2)**
   - What we know: it distills "the day's banter from message buffers" in one priority-2 call.
   - What's unclear: exact buffer/window selection (which channels, how much) — 11.4 planning detail.
   - Recommendation: keep it one batched call; scope to active channels' recent `MessageBuffer`; resolve concretely in 11.4.

3. **Salience base-weight ladder (D-07)**
   - What we know: milestone > late-night > repeat-song > auto-queue-ignored, with a distiller bump.
   - What's unclear: the precise numeric ladder.
   - Recommendation: pick a simple monotonic ladder in 11.3/11.4; it feeds eviction + decay ranking (D-08), so it only needs to be ordinally sane, not perfectly tuned.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Neon Postgres (existing) | MEM-01 store | ✓ | 16 (Neon) | — |
| pgvector extension on Neon | MEM-01 | ✓ (Neon ships on all plans) | 0.8.x | — (blocking if absent; not expected) |
| `pgvector` Python pkg | MEM-01 codec | ✗ (not yet in requirements) | install `>=0.3.6,<0.5` | none — required (gate behind install checkpoint) |
| `google-genai` SDK | MEM-02 embeddings | ✓ | ≥1.x installed | — |
| Gemini API key (`GEMINI_API_KEY`) | MEM-02/04 | ✓ (env) | — | feature degrades gracefully if absent (memory writes/reads skip, template fallback) |
| `pytest` + `pytest-asyncio` | Validation | ✓ | installed (31 test files present) | — |

**Missing dependencies with no fallback:** `pgvector` Python package — must be installed (the one new dependency; gate behind `checkpoint:human-verify`).
**Missing dependencies with fallback:** none material.

## Validation Architecture

> Nyquist validation is **enabled** (config has no `workflow.nyquist_validation: false`). This section drives `VALIDATION.md` generation.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` + `pytest-asyncio` (async tests use `@pytest.mark.asyncio`) |
| Config file | none detected at root — tests run via `python -m pytest tests/` (Wave 0: confirm/add `pytest.ini` or `[tool.pytest]` only if needed) |
| Quick run command | `python -m pytest tests/test_memory.py -x -q` |
| Full suite command | `python -m pytest tests/ -q` |

**Testable-seam philosophy (project convention, verified):** pure decision logic gets TDD; Discord/process/DB glue is untested-by-design. The seam already exists: `database.py:compute_streak`, `models/*`, and the Phase 10 `logic/` package (`logic/playback.py`, `logic/health.py`, `logic/roasts.py`) with `tests/test_*_logic.py`. **`models/memory.py` follows this exactly** — all rerank/recency/novelty/dedup/salience math is pure, clock-injectable (pass `now`), and unit-tested without DB or Discord mocks.

### The Numeric-Defaults Validation Spike (opens Phase 11, planner-owned)
The single highest-value validation artifact. **Charter:**
- **Goal:** convert the MEDIUM-confidence priors (A3) into chosen, recorded constants before 11.2 retrieval lands.
- **Inputs:** a small seeded corpus of representative distilled facts (hand-written or distilled from real `MessageBuffer` samples) per a couple of test users.
- **Method:** a throwaway script / notebook that embeds the seed facts (RETRIEVAL_DOCUMENT) and a set of realistic roast-query strings (RETRIEVAL_QUERY), runs the scoped ANN search, and prints similarity distributions so the team can pick:
  - **similarity floor** (start 0.70) — where do relevant vs. irrelevant facts separate?
  - **top-k** (start 8) and **inject cap** (start 1–3 / ~300–500 tokens)
  - **dedup threshold** (start 0.90) — at what similarity are two facts "the same"?
  - **rerank weights** (start relevance 1.0 / recency 0.5 / salience 0.7 / novelty 0.5)
  - **per-user cap** (start ~150) and **decay window** (start 90d low-salience)
- **Output:** the chosen constants written into `config.py` with a comment noting "tuned via 11 spike," and the pure rerank functions in `models/memory.py` parameterized by these constants (so they remain unit-testable independent of the chosen values).
- **Validation of the spike itself:** the pure functions are tested against *fixed synthetic inputs* (not the live values), so changing a constant never breaks a unit test — the tests assert ordering/monotonicity properties, not magic numbers.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MEM-01 | `CREATE EXTENSION` runs before pool; codec registers; clean boot on fresh Neon branch | manual / smoke (boot) | manual clean-boot check (no automated DB-in-CI) | ❌ Wave 0 (boot checklist) |
| MEM-01 | `SCHEMA_SQL` stays valid plain DDL; `user_memories` shape correct | unit (DDL parse) / integration | `python -m pytest tests/test_database_phase11.py -x` (live-DB integration, opt-in) | ❌ Wave 0 |
| MEM-02 | `embed()` uses `_embed_limiter`, NOT the chat limiter | unit | `pytest tests/test_memory.py::test_embed_uses_separate_limiter -x` (assert it calls `_embed_limiter.acquire`, not `_rate_limiter`) | ❌ Wave 0 |
| MEM-02 | embed runs off the 3s path | manual | defer-before-embed code review + manual command check | ❌ Wave 0 |
| MEM-03 | rerank orders by relevance+recency+salience+novelty (monotonicity) | unit | `pytest tests/test_memory.py::test_rerank_* -x` | ❌ Wave 0 |
| MEM-03 | similarity floor drops below-threshold; empty when nothing clears | unit | `pytest tests/test_memory.py::test_floor_drops_below -x` + `test_recall_empty_when_none_clear` | ❌ Wave 0 |
| MEM-03 | inject cap ≤ 1–3 / token budget | unit | `pytest tests/test_memory.py::test_inject_cap -x` | ❌ Wave 0 |
| MEM-04 | write triggers fire only on events/batch, NEVER per-message | unit (trigger gating) + manual | `pytest tests/test_memory.py::test_no_per_message_write -x` | ❌ Wave 0 |
| MEM-04 | dedup: >threshold → bump (NOOP), else insert | unit | `pytest tests/test_memory.py::test_dedup_decision -x` | ❌ Wave 0 |
| MEM-05 | sensitivity/PII gate: grief/health/PII sample is NOT stored | unit (gate fn) + manual prompt review | `pytest tests/test_memory.py::test_sensitivity_gate_blocks -x` (pure gate fn) | ❌ Wave 0 |
| MEM-05 | accuracy firewall: no digits/counts in stored facts | unit (distill-output validator) | `pytest tests/test_memory.py::test_no_numbers_in_fact -x` | ❌ Wave 0 |
| MEM-06 | `build_chat_prompt(memories=None)` byte-identical to today | unit | `pytest tests/test_prompts.py::test_memories_none_byte_identical -x` (extend existing `test_prompts.py`) | ⚠️ extend existing (`tests/test_prompts.py` ✅) |
| MEM-06 | `memories=[...]` renders accuracy-safe sub-block; numbers-from-SQL instruction present | unit | `pytest tests/test_prompts.py::test_memory_block_rendered -x` | ⚠️ extend existing |
| MEM-07 | per-user cap eviction removes lowest salience×recency×hit_count | unit (eviction-choice fn) | `pytest tests/test_memory.py::test_evict_choice -x` | ❌ Wave 0 |
| MEM-07 | decay sweep selects expired low-salience rows | unit (sweep-predicate fn) + integration | `pytest tests/test_memory.py::test_decay_predicate -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_memory.py tests/test_prompts.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -q` (full suite — 31 existing files + new `test_memory.py`)
- **Phase gate:** full suite green + manual clean-boot check (no new silent failures in `dexter.log`, mirroring the TEST-04 regression gate) before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/test_memory.py` — pure rerank / recency / novelty / dedup_decision / salience / eviction-choice / sweep-predicate / sensitivity-gate / no-numbers tests (covers MEM-02..MEM-05, MEM-07 pure-logic)
- [ ] Extend `tests/test_prompts.py` — `memories=None` byte-identity + `memories=[...]` rendering (MEM-06). (`tests/test_prompts.py` already exists ✅)
- [ ] `tests/test_database_phase11.py` (optional, live-DB integration, opt-in like `test_database_phase4/7/8.py`) — insert/search/bump/count/evict/delete_expired round-trips (MEM-01, MEM-07)
- [ ] Boot checklist entry — manual fresh-Neon-branch boot verifying `CREATE EXTENSION` ordering + codec registration (MEM-01; not automatable without a DB in CI)
- [ ] Numeric-defaults spike script (throwaway; output = chosen constants in `config.py`) — opens the phase
- [ ] Framework: no `pytest.ini` at root — confirm `python -m pytest tests/` collection works as-is (it does; 16/16 `test_prompts.py` passed during verification) or add minimal config only if needed

## Security Domain

> `security_enforcement` not explicitly disabled → enabled. This phase introduces durable storage of user-derived content, so the security domain is material.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No new auth surface (Discord identity reused) |
| V3 Session Management | no | n/a |
| V4 Access Control | yes | Per-user/guild scoping in the `WHERE` clause before vector search — cross-user leakage is a correctness + privacy bug (FEATURES.md). Memories are per-user only (no cross-user "server lore" — anti-feature) |
| V5 Input Validation | yes | Distilled facts are LLM output, not raw user input — but the distill prompt must constrain to observed/stated, atomic, third-person, no inference (prevents hallucinated facts stored as truth) |
| V6 Cryptography | no | No new crypto; DSN/key handling unchanged (never logged — existing T-04-05 / T-03-18 discipline) |
| **Privacy / data retention** | **yes** | **Stop-ship sensitivity/PII gate (D-01..D-03, MEM-05):** durable storage of personal data is a retention liability. Block identity & wellbeing content + PII; store only the Discord handle. Decay sweep bounds retention (~90d low-salience) |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via memory fields | Tampering | Parameterized `$N` asyncpg queries only (existing house style) — never string-build SQL |
| Storing sensitive disclosures as durable roast ammo | Information Disclosure | Sensitivity gate in the distill prompt (stop-ship); carry "serious → dial back" into the write gate |
| Storing PII (email/phone/address/real name) | Information Disclosure | PII scrub in the distill gate; store only the Discord handle |
| Hallucinated distilled "facts" cited as truth | Spoofing (of fact provenance) | Constrain distiller to observed/stated/atomic/third-person, no inference; candidate-ammo framing lets the model NOOP |
| Stale embedded numbers vs live SQL | Tampering (with accuracy) | Never embed counts; numbers from live SELECT only (Critical Rule 5) |
| Cross-user memory leakage | Information Disclosure | `user_id`/`guild_id` filter before ANN search (V4) |
| Secret/DSN exposure in logs | Information Disclosure | Reuse existing `sanitize_database_url` + never-log-DSN/key discipline |

## Sources

### Primary (HIGH confidence)
- `.planning/research/STACK.md` — full asyncpg+pgvector+Neon integration, `register_vector` in `init=`, extension-first bootstrap, `gemini-embedding-001` @ 768d, cosine `<=>`, 2000-dim ANN cap, no index day-one. (Context7 `/pgvector/pgvector-python`, `/googleapis/python-genai` v1.33.0)
- `.planning/research/ARCHITECTURE.md` — verified integration points (`bot.py:_initialize_once`, `database.py` SCHEMA_SQL + K-04, `services/gemini.py` `_RateLimiter`, `personality/prompts.py:build_chat_prompt` + 4 callers, cogs, models), build order, anti-patterns.
- `.planning/research/PITFALLS.md` — 18 pitfalls mapped to sub-phases + "Looks Done But Isn't" checklist.
- `.planning/research/FEATURES.md` — must/should/anti-feature breakdown, "SQL owns numbers, semantic owns episodes," retrieval defaults, hygiene.
- `.planning/research/SUMMARY.md` — executive synthesis, 6-sub-phase decomposition, numeric-defaults flag.
- Live code (re-verified 2026-06-29): `personality/prompts.py:91`, `services/gemini.py:34` `_RateLimiter`, `bot.py:342` pool+`init_db`, `database.py:67` SCHEMA_SQL, `models/user_profile.py`, `logic/` package, `tests/test_prompts.py` (16 passing). **[VERIFIED: codebase grep]**
- `pip index versions pgvector` → 0.4.2 current. **[VERIFIED: PyPI]**

### Secondary (MEDIUM confidence)
- Mem0 (arXiv 2504.19413), Generative Agents (arXiv 2304.03442), companion-bot memory design — patterns converge; exact numeric thresholds tuned to this bot, flagged for the spike.
- TokenMix gemini-embedding-001 guide — free-tier ~100 RPM, dimension tiers.

### Tertiary (LOW confidence)
- `text-embedding-004` deprecation date 2026-01-14 — directionally certain (deprecated); exact date secondary.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pgvector/asyncpg `init=` codec + Gemini embeddings Context7-verified; pgvector pkg PyPI-confirmed.
- Architecture: HIGH — all integration points re-verified against live files 2026-06-29; no contradictions.
- Pitfalls: HIGH (integration/budget) / MEDIUM (retrieval-quality numbers).
- Numeric defaults: MEDIUM — explicit spike charter (A3).

**Research date:** 2026-06-29 (consolidation + live re-verification of 2026-06-26 project research)
**Valid until:** ~2026-07-29 (stable stack; re-check Gemini embedding model status if planning slips past 30 days)

## RESEARCH COMPLETE
