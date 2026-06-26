# Architecture Research

**Domain:** RAG long-term memory integrated into a shipped, layered discord.py bot (cogs → services → models, asyncpg→Neon, google-genai). Milestone v1.2 / Phase 11.
**Researched:** 2026-06-26
**Confidence:** HIGH — integration points verified against the real files (`bot.py`, `database.py`, `services/gemini.py`, `personality/prompts.py`, `cogs/ai.py`, `cogs/events.py`, `models/*`). Stack/feature decisions inherited from the sibling STACK.md / FEATURES.md (HIGH).

> **Mandate:** integrate, do NOT redesign. The existing layered architecture (cogs call services via `self.bot`, services wired in `bot.py:_initialize_once`, `database.py` owns the pool + idempotent `SCHEMA_SQL`, `prompts.py` builds the system prompt, Gemini-first-with-template-fallback discipline) is fixed. RAG memory bolts on as **one new service + one new model module + one new table + four touched call sites**.

---

## Standard Architecture

### System Overview (where the new pieces live)

```
┌──────────────────────────────────────────────────────────────────────┐
│                          COGS (Discord I/O)                            │
│  ┌────────────┐   ┌────────────┐   ┌───────────────────────────────┐  │
│  │ cogs/ai.py │   │cogs/events │   │ cogs/ai.py try_auto_queue     │  │
│  │ /ask /roast│   │ ambient    │   │ (banter distill trigger, opt) │  │
│  └─────┬──────┘   │ roast      │   └──────────────┬────────────────┘  │
│        │          └─────┬──────┘                  │  WRITE trigger     │
│  READ  │  READ          │  READ                   │  (distill+store)   │
├────────┼────────────────┼─────────────────────────┼───────────────────┤
│        ▼                ▼                          ▼                    │
│              SERVICES (logic, no Discord types)                        │
│  ┌──────────────────────────┐      ┌──────────────────────────────┐   │
│  │ services/memory.py  ★NEW │─────▶│ services/gemini.py (EXISTING)│   │
│  │  MemoryService           │ chat │  GeminiService.chat (distill)│   │
│  │  - recall()  READ        │ embed│  + embed_content (NEW method)│   │
│  │  - remember() WRITE      │◀─────│  own _RateLimiter (embeddings)│   │
│  │  - dedup, rerank, sweep  │      └──────────────────────────────┘   │
│  └──────────┬───────────────┘                                         │
│             │ uses pure scoring fns                                    │
│             ▼                                                          │
│  ┌──────────────────────────┐   ┌────────────────────────────────┐    │
│  │ models/memory.py    ★NEW │   │ personality/prompts.py (MOD)   │    │
│  │  MemoryFact dataclass +  │   │  build_chat_prompt(...,         │    │
│  │  pure rerank/decay fns   │   │     memories=) → USER CONTEXT  │    │
│  │  (TDD seam)              │   └────────────────────────────────┘    │
│  └──────────┬───────────────┘                                         │
├─────────────┼──────────────────────────────────────────────────────── ┤
│             ▼            DATA (database.py + Neon)                      │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │ database.py (MOD): SCHEMA_SQL += CREATE EXTENSION vector;     │     │
│  │   + user_memories table; + insert/search/bump/sweep helpers   │     │
│  │ bot.py (MOD): create_pool(init=register_vector) + ext-first   │     │
│  └──────────────────────────────────────────────────────────────┘     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐      │
│  │ song_history │  │ user_profiles│  │ user_memories  ★NEW       │      │
│  │ (numbers=    │  │ (numbers=    │  │ (episodes/opinions =      │      │
│  │  ground truth)│  │  ground truth)│  │  vector recall)          │      │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘      │
└────────────────────────────────────────────────────────────────────────┘
```

The new service sits exactly where every other service sits — wired in `bot.py:_initialize_once()`, attached as `bot.memory_service`, accessed by cogs via `self.bot.memory_service`. No layer is restructured.

### Component Responsibilities

| Component | New / Mod | Responsibility | Implementation |
|-----------|-----------|----------------|----------------|
| `services/memory.py` `MemoryService` | **NEW** | Owns the RAG lifecycle: `recall()` (embed query → search → rerank → top 1–3), `remember()` (distill → embed → dedup → insert/bump), `sweep()` (decay + per-user cap). Holds its own embedding `_RateLimiter`. | Class, constructed with `pool` + `gemini_service`, mirrors `QueuePersistenceService(bot.pool)` wiring. |
| `models/memory.py` | **NEW** | `MemoryFact` dataclass (the record type) + **pure** scoring functions: `rerank(candidates, now)`, `recency_weight(created_at)`, `novelty_penalty(last_surfaced_at)`, `dedup_decision(similarity)`. No DB, no Discord — the unit-test seam (mirrors `database.py:compute_streak` / `models/server_state` patterns). | dataclass + module-level pure fns. |
| `database.py` | **MOD** | Add `CREATE EXTENSION IF NOT EXISTS vector;` + `user_memories` DDL to `SCHEMA_SQL`. Add query helpers: `insert_memory`, `search_memories`, `bump_memory`, `delete_expired_memories`, `count_memories`, `evict_memories`. All `$N`-parameterised, pool-acquire style. | Same conventions as existing favorites/playlist helpers. |
| `bot.py:_initialize_once` | **MOD** | (1) Run `CREATE EXTENSION` **before** the codec-registering pool exists; (2) pass `init=_register_vector` to `create_pool`; (3) wire `bot.memory_service = MemoryService(bot.pool, bot.gemini_service)`; (4) start the daily memory-sweep background task. | Minimal additions to the existing init sequence. |
| `services/gemini.py` `GeminiService` | **MOD** | Add `embed(texts, task_type, priority)` async method (`client.aio.models.embed_content`, `gemini-embedding-001`, `output_dimensionality=768`) backed by a **separate** `_RateLimiter` instance (NOT the shared 15 RPM chat limiter). | New method + second limiter field. |
| `personality/prompts.py` `build_chat_prompt` | **MOD** | Accept optional `memories: list[str] | None = None`; render them into a labelled sub-block inside the existing `USER CONTEXT:` section with an accuracy-safe instruction. | Backward-compatible optional param. |
| `config.py` | **MOD** | New constants: `EMBEDDING_MODEL`, `EMBED_DIM=768`, `EMBED_RPM_LIMIT`, `MEMORY_TOP_K`, `MEMORY_SIM_FLOOR`, `MEMORY_DEDUP_THRESHOLD`, `MEMORY_PER_USER_CAP`, `MEMORY_DECAY_DAYS`, rerank weights, `MEMORY_INJECT_MAX`. | Plain module constants. |
| `cogs/ai.py`, `cogs/events.py` | **MOD** | Call `recall()` before building the prompt (READ); call `remember()` on notable events (WRITE). | Touch 4 build sites + ≥1 write hook. |

---

## Recommended Project Structure (delta only)

```
dexter/
├── services/
│   ├── gemini.py          # MOD: + embed(), + second _RateLimiter
│   └── memory.py          # ★NEW: MemoryService (recall/remember/sweep)
├── models/
│   └── memory.py          # ★NEW: MemoryFact dataclass + pure scoring fns (TDD)
├── database.py            # MOD: SCHEMA_SQL (+vector ext, +user_memories), + helpers
├── bot.py                 # MOD: ext-first ordering, pool init=, wire memory_service, sweep task
├── personality/
│   └── prompts.py         # MOD: build_chat_prompt(memories=...) injection
├── config.py              # MOD: embedding + retrieval + hygiene constants
├── cogs/
│   ├── ai.py              # MOD: /ask + /roast recall; try_auto_queue write hook
│   └── events.py          # MOD: ambient-roast recall; notable-event write hook
└── tests/
    └── test_memory.py     # ★NEW: pure rerank/decay/dedup tests (no DB/Discord)
```

### Structure Rationale

- **`services/memory.py` (not extending `gemini.py`):** the RAG lifecycle (distill→embed→dedup→store→retrieve→rerank) is its own concern with its own state (embedding limiter, scoring policy). `gemini.py` stays a thin SDK wrapper — it only gains a generic `embed()` primitive, consistent with its "no personality logic" docstring. This mirrors how `queue_persistence.py` is a service distinct from `database.py`.
- **`models/memory.py` separates pure logic from I/O:** the project's testing convention is "pure logic gets TDD; Discord/process code is untested-by-design." Rerank/recency/novelty/dedup math is pure and deterministic → it lives in `models/` next to `server_state`/`user_profile`, exactly like `database.py:compute_streak` lives apart from the DB write. `MemoryService` orchestrates; `models/memory.py` decides.
- **DB stays in `database.py`:** new helpers join `add_favorite`/`save_playlist`/`set_resolution_cache` — same pool-acquire, `$N`-param, idempotent-DDL house style. No new persistence layer.

---

## Architectural Patterns

### Pattern 1: Three-layer memory, numbers stay in SQL (accuracy firewall)

**What:** Dexter already has short-term (`MessageBuffer`) and structured/deterministic (`song_history`, `user_profiles`) memory. RAG is the **third, episodic** layer. The firewall rule: **the vector store NEVER holds numbers a `SELECT COUNT(*)` can answer.** It holds opinions/episodes/banter only.
**When to use:** every write decision. If the fact is "queued mr brightside 14 times" → that's SQL, do not embed. If it's "swore he was done with the killers" → embed.
**Trade-offs:** prevents the embedded store from drifting out of sync with live counts (a direct Critical-Rule-5 accuracy violation). Costs a little discipline in the distillation prompt. This is non-negotiable per `prompts.py` ("Accurate first... Reference the user's music history... real play counts").

### Pattern 2: Separate embedding rate limiter (don't touch the 15 RPM budget)

**What:** `GeminiService` gets a **second** `_RateLimiter` instance for embeddings, sized to the embedding endpoint's ~100 RPM quota (configure conservatively, e.g. 60 RPM). The existing single shared 15 RPM limiter stays exclusively for chat + image generation.
**When to use:** every `embed()` call.
**Trade-offs:** embeddings hit a *different Google quota*, so funnelling them through the 15-slot chat window would needlessly starve `/ask`. Cost: one more `_RateLimiter` field + a `priority` arg on `embed()`. Write/distill embeds = priority 2 (skip if saturated; a missed fact is harmless). Retrieval embed = priority 1-ish but has a template fallback.

**Example:**
```python
# services/gemini.py — GeminiService.__init__
self._rate_limiter = _RateLimiter()                       # existing, 15 RPM (chat+image)
self._embed_limiter = _RateLimiter(max_requests=config.EMBED_RPM_LIMIT)  # NEW

async def embed(self, texts: list[str], *, task_type: str, priority: int = 2) -> list[list[float]]:
    await self._embed_limiter.acquire(priority)            # NOT self._rate_limiter
    resp = await self._client.aio.models.embed_content(
        model=config.EMBEDDING_MODEL,                      # "gemini-embedding-001"
        contents=texts,                                    # LIST → batch many in one call
        config=types.EmbedContentConfig(
            output_dimensionality=config.EMBED_DIM,        # 768 (indexable)
            task_type=task_type,                           # RETRIEVAL_DOCUMENT | RETRIEVAL_QUERY
        ),
    )
    return [e.values for e in resp.embeddings]
```

### Pattern 3: pgvector codec registration — extension-first, then `init=` (the one real trap)

**What:** `register_vector(conn)` raises `ValueError` if the `vector` type does not yet exist on the connection. The pool's `init=` callback fires on **every** connection at pool-creation time — *before* `init_db()` runs `SCHEMA_SQL`. So `CREATE EXTENSION` must run on a throwaway connection **before** `create_pool(init=...)`.
**When to use:** boot, exactly once, in `_initialize_once()`.
**Trade-offs:** one extra short-lived connection at startup. Verified compatible with the existing Neon pool tuning — `register_vector` is a per-connection `set_type_codec`, NOT a prepared statement, so `statement_cache_size=0` does not break it (STACK.md §2).

**Example (the real `bot.py:_initialize_once` change, lines ~297–306):**
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

# 2) Now the long-lived pool can register the codec on every connection.
async def _register_vector(conn: asyncpg.Connection) -> None:
    await register_vector(conn)

bot.pool = await asyncpg.create_pool(
    dsn=config.sanitize_database_url(config.DATABASE_URL),
    min_size=config.DB_POOL_MIN, max_size=config.DB_POOL_MAX,
    command_timeout=30, ssl="require",
    max_inactive_connection_lifetime=config.DB_MAX_INACTIVE_CONN_LIFETIME,
    statement_cache_size=config.DB_STATEMENT_CACHE_SIZE,
    init=_register_vector,                  # <-- only new line on create_pool
)
await init_db(bot.pool)                     # SCHEMA_SQL also has the idempotent ext + table
```
> Note: `SCHEMA_SQL` *also* carries `CREATE EXTENSION IF NOT EXISTS vector;` (idempotent, harmless second run) so a fresh DB created another way is still correct. The bootstrap connection only exists to satisfy the `init=` ordering on the very first boot.

### Pattern 4: Retrieve-and-inject, no extra generation call on the user's critical path

**What:** the memory layer adds **zero** generation calls to a roast/`/ask` response. The roast generation is the *existing* `gemini.chat()` call; memory only enriches its system prompt. The only added call on the read path is **one cheap embedding** (separate quota).
**When to use:** every READ.
**Trade-offs:** keeps the 15 RPM budget untouched for user-facing latency; the embedding adds ~one network round-trip, acceptable behind a `defer()`.

---

## Data Flow

### WRITE flow (event → distilled fact → vector store)

```
notable event in a cog
  (repeat-song roast / milestone / striking /ask exchange / voice-session-end batch)
        │
        ▼
cogs/* calls  bot.memory_service.remember(user_id, guild_id, raw_context_text)
        │
        ▼  MemoryService.remember():
   1. distill:   gemini_service.chat(DISTILL_PROMPT, [raw_context], priority=2)
                 → 0–3 atomic, third-person, declarative sentences (NO numbers)
   2. embed:     gemini_service.embed(facts, task_type="RETRIEVAL_DOCUMENT", priority=2)
   3. dedup:     for each fact → database.search_memories(user_id, vec, k=1)
                 → if top-1 cosine sim > MEMORY_DEDUP_THRESHOLD (~0.90):
                       database.bump_memory(id)   # NOOP/UPDATE: ++hit_count, touch last_seen_at
                   else:
                       database.insert_memory(user_id, guild_id, fact, vec, salience, ...)
   4. cap guard: if database.count_memories(user_id) > MEMORY_PER_USER_CAP:
                       database.evict_memories(user_id)   # lowest salience×recency×hit_count
        │
        ▼
   user_memories row(s) committed to Neon
```
- **Triggers (FEATURES.md §2):** event-triggered (rare, already-firing hooks in `events.py`/`ai.py`) + periodic session-end batch (one priority-2 call). NEVER per-message.
- **Priority 2 throughout** — distill + embed both background; a missed write is harmless and must never starve `/ask`.

### READ flow (roast moment → recall → prompt injection)

```
roast / response moment
  (/ask, /roast, ambient voice-join roast, repeat/milestone roast)
        │
        ▼
cog calls  facts = await bot.memory_service.recall(user_id, guild_id, query_text)
        │
        ▼  MemoryService.recall():
   1. embed query:  gemini_service.embed([query_text], task_type="RETRIEVAL_QUERY", priority=1)
   2. ANN search:   database.search_memories(user_id, guild_id, qvec, k=MEMORY_TOP_K≈8)
                    →  WHERE user_id=$1 [AND guild_id=$2]
                       ORDER BY embedding <=> $qvec   (cosine distance)
                       LIMIT $k
   3. floor:        drop rows with cosine similarity < MEMORY_SIM_FLOOR (~0.70)
   4. rerank:       models.memory.rerank(rows, now)
                    score = 1.0·relevance + 0.5·recency + 0.7·salience + 0.5·novelty
                    → keep top MEMORY_INJECT_MAX (1–3) fact strings
   5. (optional)    database.bump_memory(...) last_surfaced_at/surface_count for anti-repeat
        │
        ▼
   cog calls  build_chat_prompt(mood, user_summary, seasonal, memories=facts)
        │
        ▼
   gemini_service.chat(system_prompt, conversation, priority=1)   ← EXISTING call, unchanged signature on chat()
```
- If nothing clears the floor → `recall()` returns `[]` → `build_chat_prompt(..., memories=None)` → identical to today's behavior (graceful degrade).
- The embedding query is the only added call; everything else is the existing chat path.

### Key Data Flows

1. **Stat × episode callback (the payoff):** SQL provides the true number (`get_user_summary` / a `COUNT`), pgvector provides the recalled episode; both are handed to Gemini as *candidate ammo* with "weave one in only if it lands; never invent specifics." Numbers always real, phrasing from the model.
2. **Dedup-on-write requires read-first:** `remember()` calls `search_memories` before inserting — retrieval must be built before write (dependency below).

---

## Exact Prompt-Injection Site (accuracy-rule-safe)

**File:** `personality/prompts.py`. **Anchor:** the existing `USER CONTEXT:` block of `DEXTER_SYSTEM_PROMPT` (lines 57–60), which today renders only `{user_context}` (the SQL taste summary from `get_user_summary`).

**Change:** add an optional `memories` param to `build_chat_prompt` and render a clearly-labelled sub-block **after** `{user_context}`, inside the same section. Keep `{user_context}` (the numbers) first so it remains the dominant, authoritative context.

```python
# personality/prompts.py  (DEXTER_SYSTEM_PROMPT, USER CONTEXT region)
USER CONTEXT:
{user_context}

{memory_context}        # <-- NEW slot, empty string when no memories cleared the floor
```

```python
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

**Why this is accuracy-safe (Critical Rule 5):**
- Memories are episodic/opinion sentences with **no numbers** (enforced at write time, Pattern 1). The model cannot read a stale count from them.
- The injected instruction explicitly pins numbers to the SQL `USER CONTEXT` block and forbids inventing detail — reinforcing `DEXTER_SYSTEM_PROMPT`'s existing "Accurate first... do not make things up."
- Empty-string fallback means the no-memory path is byte-identical to today's prompt → zero regression risk for users with no stored facts.
- **Backward-compatible signature:** `memories` defaults to `None`, so the four existing `build_chat_prompt` callers compile unchanged; they opt in by passing the recalled list.

---

## Call Sites That Change (against the real files)

| File:Site | Current | Change | Direction |
|-----------|---------|--------|-----------|
| `cogs/ai.py:ask` (build at L119) | `build_chat_prompt(mood, user_summary, seasonal)` | `facts = await self.bot.memory_service.recall(uid, gid, question)` → pass `memories=facts` | READ |
| `cogs/ai.py:roast` (build at L179) | `build_chat_prompt(mood, user_summary, seasonal)` | recall on `target.id` using scenario text → pass `memories=facts` | READ |
| `cogs/ai.py:try_auto_queue` (L252) | recommendation prompt only | optional: distill auto-queue skip outcome ("ignored memory") into a fact | WRITE (optional, P2) |
| `cogs/events.py:_generate_ambient_roast` (build at L131) | `build_chat_prompt("normal", user_context, "")` | recall on `member.id` using `scenario` → pass `memories=facts` | READ |
| `cogs/events.py:on_voice_state_update` / repeat-song / milestone hooks | fire roast | add `await self.bot.memory_service.remember(...)` on notable events | WRITE |
| `cogs/events.py:on_message` (L305) | feeds `MessageBuffer` | (session-end batch) distill recent buffer → facts; trigger lives here or in a bg task | WRITE (batch) |
| `personality/prompts.py:build_chat_prompt` (L91) | 3 params | + `memories` param + injection | MOD (core) |
| `bot.py:_initialize_once` (L297–306) | pool create + `init_db` | ext-first bootstrap, `init=_register_vector`, wire `bot.memory_service`, start sweep task | MOD |
| `database.py:SCHEMA_SQL` (L67) + helpers | tables + helpers | + `CREATE EXTENSION vector` + `user_memories` + 6 helpers | MOD |
| `services/gemini.py:GeminiService` | chat + image | + `embed()` + `_embed_limiter` | MOD |
| `config.py` | — | + embedding/retrieval/hygiene constants | MOD |

**`build_chat_prompt` is the linchpin** — it has exactly four callers (`/ask`, `/roast`, ambient roast, and itself), all discoverable by grep. The optional-param strategy means changing it cannot silently break a caller.

---

## Suggested Build Order (Phase 11 sub-phases)

Ordered to respect the dependency chain in FEATURES.md (`schema → retrieval → write/dedup → distillation triggers → callback integration → hygiene`). Each sub-phase is independently verifiable (pure-logic TDD + clean boot).

**11.1 — Foundation: schema + extension + codec + config (NEW, no behavior change)**
- `database.py`: `CREATE EXTENSION IF NOT EXISTS vector;` + `user_memories` table + index in `SCHEMA_SQL`.
- `bot.py`: extension-first bootstrap connection + `init=_register_vector` on `create_pool`.
- `config.py`: all new constants.
- Verify: clean boot against Neon, table + extension present, codec registered, no regression. **No retrieval/write yet.**

**11.2 — Embedding primitive + retrieval read path (depends on 11.1)**
- `services/gemini.py`: `embed()` + separate `_embed_limiter`.
- `database.py`: `search_memories` (ANN, scoped, floor applied in Python).
- `models/memory.py`: `MemoryFact` + pure `rerank`/`recency_weight`/`novelty_penalty` (TDD — `tests/test_memory.py`).
- `services/memory.py`: `recall()` (embed query → search → floor → rerank → top 1–3). Returns `[]` cleanly when empty.
- Verify: unit tests green; `recall()` returns sane facts against seeded rows.

**11.3 — Write path + dedup (depends on 11.2 — must search before inserting)**
- `database.py`: `insert_memory`, `bump_memory`, `count_memories`, `evict_memories`.
- `services/memory.py`: `remember()` distill→embed→dedup(>0.90 NOOP/bump else insert)→cap-guard.
- `models/memory.py`: `dedup_decision(similarity)` pure fn (TDD).
- Verify: dedup unit tests; a repeated fact bumps `hit_count` instead of duplicating.

**11.4 — Distillation triggers (depends on 11.3)**
- Hook `remember()` into the already-firing notable-event paths in `cogs/events.py` (repeat-song, milestone, late-night) and `cogs/ai.py` (`try_auto_queue` ignored-memory).
- Add the session-end / daily batch distill (one priority-2 call over `MessageBuffer`).
- Verify: events produce 0–3 facts; no per-message writes; priority-2 never blocks `/ask`.

**11.5 — Prompt injection + callback-roast integration (capstone; depends on 11.2 for recall, 11.4 for content)**
- `personality/prompts.py`: `memories` param + `USER CONTEXT` injection (accuracy-safe).
- Wire `recall()` + `memories=` into `/ask`, `/roast`, `_generate_ambient_roast`.
- Verify: a roast cites a true SQL stat AND a recalled episode; no-memory users get the unchanged prompt.

**11.6 — Hygiene (ship with v1, not later — FEATURES.md flags unbounded memory as the #1 failure)**
- `database.py`: `delete_expired_memories` (decay sweep, ~90d on low salience).
- `bot.py`: daily memory-sweep background task (mirrors `cache_cleanup`/`ytdlp_update` `@tasks.loop` + `before_loop` `wait_until_ready` pattern).
- Per-user cap eviction already in `remember()` (11.3); sweep handles decay.
- Verify: expired rows deleted; cap holds; ANN recall quality stable.

> **Why this order:** retrieval (11.2) precedes write (11.3) because dedup *is* a retrieval call. Distillation triggers (11.4) need the write path to exist. The callback-roast (11.5) is the integration capstone — it needs both recall (11.2) and real stored content (11.4). Hygiene (11.6) is last only in build order, but is in-scope for v1, not deferred polish.

---

## Anti-Patterns

### Anti-Pattern 1: Registering the vector codec before the extension exists
**What people do:** add `init=register_vector` to `create_pool` and rely on `init_db`/`SCHEMA_SQL` to create the extension afterwards.
**Why it's wrong:** `init=` fires on every connection *during* `create_pool`, before `init_db` runs → `register_vector` raises `ValueError` (type missing) → boot fails.
**Do this instead:** run `CREATE EXTENSION IF NOT EXISTS vector;` on a throwaway `asyncpg.connect()` **before** `create_pool(init=...)` (Pattern 3).

### Anti-Pattern 2: Embedding numbers / counts (vector-SQL drift)
**What people do:** embed "queued mr brightside 14 times" because it's "data about the user."
**Why it's wrong:** the embedded number freezes; live SQL keeps counting. Gemini may roast with the stale embedded number → accuracy violation (Critical Rule 5) + context rot.
**Do this instead:** numbers always from a live `SELECT`; embed only opinions/episodes/banter (Pattern 1).

### Anti-Pattern 3: Routing embeddings through the shared 15 RPM chat limiter
**What people do:** reuse `self._rate_limiter` for `embed()`.
**Why it's wrong:** embeddings have a separate ~100 RPM quota; sharing the 15-slot window starves `/ask` for no benefit.
**Do this instead:** a second `_RateLimiter` for embeddings (Pattern 2).

### Anti-Pattern 4: Per-message distillation / writing on every turn
**What people do:** call `remember()` on every `on_message`.
**Why it's wrong:** a Gemini distill per message is unaffordable at 15 RPM and mostly stores noise → context rot, slow ANN.
**Do this instead:** event-trigger + session-end batch only (11.4).

### Anti-Pattern 5: Changing `chat()`'s signature or adding a generation call on the read path
**What people do:** thread memory through a new `gemini.chat()` variant or make a second LLM call to "rerank."
**Why it's wrong:** breaks the existing thin-wrapper contract and adds latency/budget to the user's critical path.
**Do this instead:** enrich the *system prompt* via `build_chat_prompt(memories=...)`; rerank in Python (`models/memory.py`); the only added read-path call is one cheap embedding (Pattern 4).

### Anti-Pattern 6: Unbounded per-user memory
**What people do:** "never forget" — no cap, no decay.
**Why it's wrong:** companion-bot post-mortems cite this as the #1 recall-degradation cause; retrieval noise + slow ANN + drift.
**Do this instead:** per-user cap (~150) + decay sweep (~90d low-salience), shipped in v1 (11.6).

---

## Scaling Considerations

| Scale (fact corpus) | Architecture |
|---------------------|--------------|
| Hundreds–low thousands (expected) | **No ANN index needed** — seq scan over 768-d vectors with `ORDER BY embedding <=> $1 LIMIT k` is sub-millisecond. Don't cargo-cult an index. |
| ~10k+ rows | Add `HNSW (vector_cosine_ops)` index — works from row zero (no training), unlike IVFFlat. Index only at ≤2000 dims (768 is fine). |
| Much larger / multi-community | Revisit `halfvec`, partitioning by guild, or a dedicated vector DB — explicitly out of scope for a single-community bot. |

### Scaling Priorities
1. **First "bottleneck" is recall quality, not speed** — tune the 0.70 floor + rerank weights before touching indexes. At this scale latency is a non-issue.
2. **Second is the 15 RPM chat budget** — already protected by the separate embedding limiter + priority-2 writes; the read path adds no generation call.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Gemini embeddings (`gemini-embedding-001`) | `gemini_service.embed()` → `client.aio.models.embed_content`, 768-d MRL, `task_type` per direction | Separate 100 RPM quota; own limiter; `RETRIEVAL_DOCUMENT` on write, `RETRIEVAL_QUERY` on read (mismatching degrades recall). |
| Neon Postgres + pgvector | `register_vector` in pool `init=`; `vector(768)` column; `<=>` cosine | Extension-first ordering (Pattern 3); `statement_cache_size=0` verified compatible; cosine is scale-invariant → no numpy normalisation. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| cogs ↔ `MemoryService` | `self.bot.memory_service.recall()/remember()` | Same `self.bot.<service>` access pattern as `youtube_service`, `gemini_service`, `queue_persistence`. |
| `MemoryService` ↔ `GeminiService` | constructor injection (`MemoryService(pool, gemini_service)`) | Reuses the one wired `genai.Client`; no second SDK client. |
| `MemoryService` ↔ `database.py` helpers | direct `await database.search_memories(pool, ...)` | Same pool-acquire/`$N` style as favorites/playlists. |
| `MemoryService` ↔ `models/memory.py` | pure function calls (rerank/decay/dedup) | The TDD seam; no I/O crosses this boundary. |
| cogs ↔ `prompts.build_chat_prompt(memories=)` | optional kwarg | Backward-compatible; empty path == today's prompt. |

## Sources

- Existing code (HIGH): `bot.py:_initialize_once` (pool wiring L297–306, `@tasks.loop` + `before_loop` patterns), `database.py` (`SCHEMA_SQL`, idempotent DDL, `$N` helper style, `compute_streak` pure-fn seam), `services/gemini.py` (`GeminiService`, `_RateLimiter`, `aio.models` async pattern), `personality/prompts.py` (`DEXTER_SYSTEM_PROMPT` `USER CONTEXT` block, `build_chat_prompt` 4 callers), `cogs/ai.py` (`/ask` L119, `/roast` L179, `try_auto_queue` L252), `cogs/events.py` (`_generate_ambient_roast` L131, voice/notable-event hooks), `models/user_profile.py` + `models/server_state.py` (model-layer conventions).
- Sibling research (HIGH): `.planning/research/STACK.md` (pgvector/asyncpg `init=` codec, `gemini-embedding-001` @768, separate embedding limiter, extension-first trap), `.planning/research/FEATURES.md` (three-layer memory, accuracy firewall, write triggers, retrieval defaults, hygiene, dependency order).
- Mem0 / Generative Agents / companion-bot prior art (MEDIUM, via FEATURES.md) — distilled-facts, dedup, decay, recency×relevance×salience rerank.

---
*Architecture research for: RAG long-term memory integration into the Dexter Discord bot (v1.2 / Phase 11)*
*Researched: 2026-06-26*
