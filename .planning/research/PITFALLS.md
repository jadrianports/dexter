# Pitfalls Research

**Domain:** Adding `pgvector` + Gemini-embeddings RAG long-term memory to an existing discord.py + asyncpg→Neon + google-genai bot (Dexter, v1.2 / Phase 11)
**Researched:** 2026-06-26
**Confidence:** HIGH on integration + budget mechanics (verified via Context7 `/pgvector/pgvector-python`, existing `database.py`/`services/gemini.py`, and STACK.md); MEDIUM on retrieval-quality numeric defaults (tuned to this bot's scale, validate in the research spike).

> **Sub-phase labels used below** (the Phase 11 plan should adopt these as the build order — they follow the FEATURES.md dependency graph):
> - **11.1 Store & Integration** — `CREATE EXTENSION`, `user_memories` schema, asyncpg vector codec in pool `init=`
> - **11.2 Embedding Service** — `gemini-embedding-001` calls + a *separate* embedding rate limiter
> - **11.3 Retrieval** — scoped ANN search, similarity floor, Python re-rank, injection cap
> - **11.4 Write / Distill** — event + session-end fact distillation, write-time dedup
> - **11.5 Callback Roast** — SQL-stat × recalled-episode integration, accuracy guarantee
> - **11.6 Hygiene & Ops** — per-user cap, decay/expiry, contradiction supersede, migration/backfill, index, cold-start

---

## Critical Pitfalls

### Pitfall 1: `register_vector` runs before the `vector` type exists (extension-vs-pool ordering)

**What goes wrong:**
The bot crashes at startup — every connection the pool warms fails its `init=` callback. `register_vector(conn)` raises `ValueError: unknown type: public.vector` because the `vector` type OID can't be introspected. Unlike `halfvec`/`sparsevec` (whose absence pgvector-python suppresses for backward-compat), a missing **`vector`** type is a hard `ValueError` — verified via Context7. With `min_size>=2` the pool tries to register the codec on warm connections immediately, so the failure surfaces on boot, not lazily.

**Why it happens:**
`CREATE EXTENSION vector` and the codec-registering pool are created in the wrong order. The current `init_db()` runs `SCHEMA_SQL` *over the pool* — but if `CREATE EXTENSION` lives only inside `SCHEMA_SQL` and the pool's `init=` already calls `register_vector`, the chicken-and-egg fires: the pool can't warm a connection (init fails) so `init_db()` never gets to run the DDL.

**How to avoid:**
Run `CREATE EXTENSION IF NOT EXISTS vector;` on a **throwaway `asyncpg.connect()`** (or a no-`init` bootstrap pool) *before* creating the long-lived codec-registering pool. Keep the `CREATE EXTENSION` line at the very top of `SCHEMA_SQL` too (idempotent, plain DDL — fits the no-`$N`-params multi-statement constraint), but the extension must be guaranteed present before any `init=register_vector` connection is warmed. Order: `connect()` → `CREATE EXTENSION` → `close()` → `create_pool(init=_init_connection)`.

**Warning signs:**
`ValueError: unknown type: public.vector` in boot logs; pool creation hangs/raises; works on a DB where the extension was manually pre-created but fails on a fresh Neon branch.

**Phase to address:** 11.1 Store & Integration

---

### Pitfall 2: Assuming `statement_cache_size=0` breaks the vector codec (it does NOT — but the misbelief causes hand-rolled serialization)

**What goes wrong:**
A dev "works around" a non-existent problem: believing Neon's required `statement_cache_size=0` (set for PgBouncer transaction mode, K-04) is incompatible with `register_vector`, they skip the codec and hand-serialize vectors as `'[1,2,3,...]'` strings. asyncpg then returns embeddings as **text**, not lists; distance queries silently degrade or comparisons happen against string literals; round-trip float precision is lossy.

**Why it happens:**
Conflation of two unrelated mechanisms. `register_vector` calls `conn.set_type_codec(...)` — a **per-connection codec registration**, NOT a prepared statement. `statement_cache_size=0` only disables prepared-statement caching. They don't interact. The STACK.md verified this; Context7 confirms the codec is registered per-connection in `init=`.

**How to avoid:**
Use the real codec: `from pgvector.asyncpg import register_vector` inside the pool `init=` callback. Pass/receive plain Python `list[float]`. Keep `statement_cache_size=0`, `ssl='require'`, `max_inactive_connection_lifetime=240` exactly as-is — all three coexist with the codec. Never serialize vectors to strings by hand.

**Warning signs:**
`'[...]'` string-building for embeddings anywhere in the codebase; `ORDER BY embedding <=> $1` returning nonsense order; query results where the embedding column is a `str` not a `list`.

**Phase to address:** 11.1 Store & Integration

---

### Pitfall 3: Vector dimension mismatch — default 3072 output vs `vector(768)` column and the 2000-dim ANN cap

**What goes wrong:**
Two distinct failures: (a) `gemini-embedding-001` returns **3072 dims by default**; inserting that into a `vector(768)` column throws `expected 768 dimensions, not 3072` on every write. (b) If someone "fixes" it by making the column `vector(3072)`, the HNSW/IVFFlat index becomes **impossible to create** — pgvector's ANN indexes cap at **2000 dimensions**. Either the feature can't store, or it can't be indexed.

**Why it happens:**
`output_dimensionality` is not set on the `embed_content` config (it defaults to 3072), or it's set inconsistently between the write path (`RETRIEVAL_DOCUMENT`) and the read path (`RETRIEVAL_QUERY`) — a 768-d query vector can't be compared against 3072-d stored vectors.

**How to avoid:**
Set `output_dimensionality=768` on **both** the document-embed and query-embed calls, and pin the column to `vector(768)`. Centralize the dimension in one config constant (`EMBEDDING_DIMS = 768`) used by both the SQL schema and the embed config so they can't drift. 768 is below the 2000-dim ANN cap, so HNSW works; it's also the smallest Google MRL quality tier (cheap + indexable).

**Warning signs:**
`expected N dimensions, not M` insert errors; HNSW `CREATE INDEX` failing with "column cannot have more than 2000 dimensions"; retrieval returning zero or garbage matches because query and stored dims differ.

**Phase to address:** 11.1 Store & Integration (column) + 11.2 Embedding Service (config constant)

---

### Pitfall 4: Embedding on every message — budget burn, noise, and context rot at the source

**What goes wrong:**
Wiring a distill+embed call into `on_message` (or embedding every `/ask` turn) generates a Gemini call per message. Even on the embedding endpoint's higher quota, a busy channel floods it; worse, it fills `user_memories` with thousands of low-value rows ("lol", "skip this") that drown the genuinely roast-worthy facts in retrieval. This is the #1 documented companion-bot failure (context rot).

**Why it happens:**
"More memory = smarter" intuition; the easiest hook is the message event. Distillation cost and retrieval-noise cost are invisible until the store is already polluted.

**How to avoid:**
Two write triggers only (per FEATURES.md): **event-triggered** (milestone, repeat-song roast, striking `/ask`, explicit stated preference — hooks that already fire in `events.py`) and **periodic distillation** (voice-session-end or daily, one batched Gemini call producing 0–3 atomic facts). Never write per message turn.

**Warning signs:**
Embedding/distill call count scales with chat volume; `user_memories` row count growing by hundreds/day; retrieval surfacing trivial filler.

**Phase to address:** 11.4 Write / Distill

---

### Pitfall 5: Embedding facts SQL already answers — accuracy drift + wasted budget

**What goes wrong:**
Storing "carlos has queued 14 songs" as an embedded memory. The number is frozen at write time; the live count keeps changing. At roast time Gemini may read the **stale embedded number** instead of live SQL — a direct Critical-Rule-5 accuracy violation ("never sacrifice factual accuracy"). It also wastes embedding budget on data a `SELECT COUNT(*)` answers exactly.

**Why it happens:**
"It's data about the user, so store it" — failing to separate the deterministic/structured layer (`song_history`, `user_artist_counts`, streaks) from the semantic/episodic layer.

**How to avoid:**
Embed **only** what SQL can't express: stated opinions, reactions, notable one-off events, recurring bits. **Never embed counts, dates, or rankings.** The callback-roast prompt gets numbers from a live `SELECT` passed as ground-truth context; the embedded memory supplies only the *episode* ("right after you swore you were done with the killers"). Number from SQL, color from pgvector.

**Warning signs:**
Memory facts containing digits/counts; roasts citing numbers that disagree with `/history` or `/leaderboard`; distillation prompt asking the model to record statistics.

**Phase to address:** 11.4 Write / Distill (what-to-store rule) + 11.5 Callback Roast (number-from-SQL guarantee)

---

### Pitfall 6: Routing embeddings through the shared 15 RPM chat limiter — starving `/ask`

**What goes wrong:**
Embeddings get fed through the existing `_RateLimiter` (15 RPM, shared by chat + image). Background fact-distillation and retrieval embeds then consume slots that user `/ask` and `/imagine` commands need, making the bot feel laggy or rejecting user commands — for no reason, because embeddings hit a **separate Google quota (~100 RPM)**.

**Why it happens:**
There's already one `_RateLimiter` in `services/gemini.py` and it's tempting to reuse it for "all Gemini calls." But it models *one* quota; embeddings are a *different* quota.

**How to avoid:**
Give embeddings their **own** `_RateLimiter` instance (size conservatively, e.g. 60 RPM, under the 100 RPM ceiling). Keep it entirely off the chat 15-slot window. Treat fact-storage embeds as **priority 2** (skip if saturated — a missed fact-write is harmless). Batch writes: `embed_content(contents=[...])` takes a list, so N facts = 1 call.

**Warning signs:**
`/ask` latency or rate-limit rejections rising after memory ships; `rpm_usage` on the chat limiter climbing during idle (background distillation eating the chat budget).

**Phase to address:** 11.2 Embedding Service

---

### Pitfall 7: Synchronous embed call on the command critical path blows the 3s interaction window

**What goes wrong:**
Retrieval embeds the query *before* responding, inline in a slash command handler. The Gemini embed round-trip (plus a possible Neon cold-start) exceeds Discord's 3s `defer()`/respond deadline → "the application did not respond" error, even though the roast eventually computes.

**Why it happens:**
Retrieval feels like "just one more lookup" and gets dropped into the synchronous part of the handler, before `defer()` or before `interaction.followup`.

**How to avoid:**
`defer()` (or respond) **first**, then do the embed + ANN search + roast generation in the deferred/`followup` path via `asyncio.create_task()` — the same discipline already mandated for `/ask` and `/play`. For ambient (non-interaction) roasts there's no 3s clock, but still run retrieval off the event hot path. The memory layer must add **zero** synchronous latency before the interaction ack.

**Warning signs:**
"application did not respond" on memory-augmented commands; p95 command latency spiking; embed calls located above `await interaction.response.defer()`.

**Phase to address:** 11.3 Retrieval (called from 11.5 Callback Roast)

---

### Pitfall 8: No similarity threshold — garbage recall poisons every roast

**What goes wrong:**
ANN search always returns the top-k *nearest* vectors, even when the nearest is barely related. Without a floor, a roast about someone joining voice pulls "the closest memory" — which might be about a totally different topic — and Dex confidently references something irrelevant. Retrieval *always* finding something is the trap.

**Why it happens:**
`ORDER BY embedding <=> $1 LIMIT k` never returns empty (unless the table is empty), so devs assume "it found a match." Cosine distance has no inherent "too far" cutoff.

**How to avoid:**
Apply a **cosine-similarity floor (~0.70)** after the ANN fetch (fetch top-k=8, drop everything below the floor, keep top 1–3). If nothing clears the floor, inject **nothing** — Dex falls back to the existing taste summary. Make "no memory is better than a wrong memory" an explicit rule.

**Warning signs:**
Roasts referencing events the user never did; callbacks that feel non-sequitur; retrieval logs showing low-similarity rows being injected.

**Phase to address:** 11.3 Retrieval

---

### Pitfall 9: Letting embedded memory override factual accuracy (Critical Rule 5 violation)

**What goes wrong:**
The model treats injected memory text as authoritative fact and invents or contradicts reality — e.g. a stale "loves taylor swift" memory drives a roast even though the user just declared the opposite, or a distilled fact was itself a hallucination from a sloppy distill prompt and is now cited as truth. This breaks the product's core contract (accuracy first, sarcasm second).

**Why it happens:**
Memories are injected as plain prompt text indistinguishable from ground truth; the distillation step can hallucinate facts that then get embedded and recalled as "real."

**How to avoid:**
(a) Numbers always from live SQL, never from memory (see Pitfall 5). (b) Label injected memories in the prompt as *candidate ammo* — instruct Gemini to weave one in "only if it lands," and that it may NOOP rather than force a fact. (c) Constrain the distillation prompt to extract only what was actually stated/observed (third-person, atomic, no inference). (d) Prefer most-recent `created_at` and supersede contradictions on write so stale preferences don't resurface.

**Warning signs:**
Roasts asserting things the user contradicts; distilled facts containing inferred/embellished claims; a memory that's demonstrably false surfacing in output.

**Phase to address:** 11.4 Write / Distill (faithful distillation) + 11.5 Callback Roast (candidate-ammo framing) + 11.6 Hygiene (contradiction supersede)

---

### Pitfall 10: Roasting genuinely sensitive content + storing PII

**What goes wrong:**
The distiller captures and the bot later roasts something it shouldn't — a user venting about a death, a breakup, mental-health disclosure, real address/phone/email. Personality bot + long-term recall makes this far worse than a one-off chat: a sensitive disclosure becomes durable, re-surfaceable roast ammo. Also a privacy/data-retention liability (durable storage of personal data).

**Why it happens:**
The distill prompt extracts "notable events" without a sensitivity filter; CLAUDE.md already says "dial back sarcasm for serious/emotional questions" for live chat, but that guard doesn't automatically extend to what gets *stored*.

**How to avoid:**
(a) Sensitivity gate in the distill prompt: explicitly exclude grief, health, self-harm, relationships-in-distress, financial/identity info, and anything that reads as a vulnerable disclosure — do not store it. (b) PII scrub: never store emails/phones/addresses/real names beyond the Discord handle. (c) Carry the existing "serious/emotional → dial back" rule into both the write gate and the roast prompt. (d) Provide an owner `/forget` control to prune a bad memory.

**Warning signs:**
Memory rows containing emotional/medical/contact content; a roast landing on a sensitive topic in testing; user complaints. Treat any of these as a stop-ship.

**Phase to address:** 11.4 Write / Distill (sensitivity + PII gate) — ship in v1, not "after validation"

---

## Moderate Pitfalls

### Pitfall 11: Prompt bloat — too many memories injected

**What goes wrong:** Injecting top-k raw (5–8 memories) bloats the system prompt, dilutes the personality/few-shot exemplars, costs tokens, and makes roasts unfocused.
**How to avoid:** Inject **1–3** facts max, hard-capped at ~300–500 tokens, slotted into the existing `USER CONTEXT` block of `DEXTER_SYSTEM_PROMPT`. Re-rank in Python and keep only the top few.
**Warning signs:** System prompt length creeping up; roasts trying to reference multiple memories at once; personality feeling diluted.
**Phase to address:** 11.3 Retrieval

### Pitfall 12: No write-time dedup — store fills with near-duplicates

**What goes wrong:** The same fact ("done with the killers") gets distilled and stored 30 times across sessions; retrieval returns 5 copies of it; the corpus bloats.
**How to avoid:** Dedup gate on every write — embed candidate, search that user's top-1 existing memory, if cosine similarity **>0.90** NOOP (bump `hit_count`/`last_seen_at`) instead of inserting (Mem0 ADD/UPDATE/NOOP). Requires retrieval to exist first.
**Warning signs:** Duplicate-looking rows per user; retrieval returning the same fact multiple times.
**Phase to address:** 11.4 Write / Distill (depends on 11.3 Retrieval)

### Pitfall 13: Stale / contradictory memories surfacing

**What goes wrong:** Old preference ("loves country") and new one ("hates country") both stored; retrieval surfaces the stale one and the roast is wrong.
**How to avoid:** On write, if a candidate contradicts an existing fact, UPDATE/supersede rather than keeping both. At retrieval, prefer the most recent `created_at`. Recency term in the re-rank score.
**Warning signs:** Roasts citing outdated preferences; two opposing facts for one user.
**Phase to address:** 11.6 Hygiene & Ops

### Pitfall 14: Unbounded per-user memory growth (context rot)

**What goes wrong:** Memory per user grows forever → retrieval noise rises, ANN slows, embedding/storage cost climbs. Cited as the primary companion-bot failure mode.
**How to avoid:** Per-user cap (~150); on exceed, evict lowest `salience × recency × hit_count`. Decay/expiry: low-salience conversational memories get `expires_at` ≈ 90 days; high-salience persists. Daily sweep deletes expired rows. Ship with v1, not later.
**Warning signs:** Per-user row counts climbing without bound; retrieval quality degrading over weeks; ANN latency rising.
**Phase to address:** 11.6 Hygiene & Ops

### Pitfall 15: Same callback fired every session (anti-repeat missing)

**What goes wrong:** The most-similar memory is also the most-often-surfaced; Dex reuses the same callback every session and it stops being funny / feels broken.
**How to avoid:** Track `last_surfaced_at`/`surface_count`; add a novelty penalty in the re-rank score so recently-fired memories are down-weighted. Surprising-but-relevant beats top-1 similarity.
**Warning signs:** Users noting "it always says the same thing"; one memory dominating `surface_count`.
**Phase to address:** 11.3 Retrieval (re-rank) — P2, add after validation per FEATURES.md

---

## Ops Pitfalls

### Pitfall 16: Migration / backfill against the live Neon DB

**What goes wrong:** Adding the extension + table to the production Neon DB, or backfilling embeddings for historical data, done carelessly: a long-running backfill loop hammers the embedding quota, holds connections through Neon's scale-to-zero, or a non-idempotent migration partially applies.
**How to avoid:** Schema change is pure idempotent DDL (`CREATE EXTENSION IF NOT EXISTS` + `CREATE TABLE IF NOT EXISTS`) in `SCHEMA_SQL` — safe to re-run. **Do not bulk-backfill history** — the design starts the memory store empty and accumulates forward (FEATURES.md). If any backfill is ever wanted, batch it, throttle through the embedding limiter at priority 2, and run it as a one-off script, not in `init_db()`.
**Warning signs:** `init_db()` doing row-level work; a backfill loop in the boot path; embedding quota exhaustion right after deploy.
**Phase to address:** 11.1 Store & Integration (schema) + 11.6 Hygiene & Ops (any backfill)

### Pitfall 17: IVFFlat on an empty/tiny table; premature/expensive index

**What goes wrong:** Creating an IVFFlat index on a near-empty `user_memories` trains centroids on garbage → poor recall, needs a rebuild once data lands. Or cargo-culting any ANN index when a seq scan over a few-hundred-row corpus is already sub-millisecond.
**How to avoid:** At this scale (hundreds–low-thousands of rows) **skip the ANN index** — `ORDER BY embedding <=> $1 LIMIT k` is sub-ms on a seq scan. When an index becomes worthwhile (≫10k rows), use **HNSW** (`vector_cosine_ops`), which needs no training data and works from row zero — never IVFFlat on this corpus. Index only at ≤2000 dims (768 is fine).
**Warning signs:** `CREATE INDEX ... ivfflat` on a small table; index added before measuring; recall worse after indexing.
**Phase to address:** 11.6 Hygiene & Ops (only if/when corpus grows)

### Pitfall 18: Cold-start latency on the first query (Neon scale-to-zero + first embed)

**What goes wrong:** First memory query after idle hits Neon's scale-to-zero wake (seconds) *and* a cold embed call, stacking latency — risky if it lands on a command's 3s window.
**How to avoid:** Pitfall 7's defer-first pattern absorbs it for interactions. The existing pool guards (`min_size>=2`, `max_inactive_connection_lifetime=240`) keep warm connections so the vector codec stays registered and the DB stays awake during activity. Don't run retrieval synchronously before the interaction ack.
**Warning signs:** First-query-after-idle slowness; SSL-EOF on the first memory query (the K-04 Neon failure class — confirm pool tuning is inherited by the codec pool).
**Phase to address:** 11.1 Store & Integration (pool inherits K-04 tuning) + 11.3 Retrieval (off hot path)

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip the ANN index (seq scan) | No index build, no IVFFlat-on-empty risk | Slows >10k rows | **Acceptable now** — sub-ms at this scale; add HNSW later |
| Hand-serialize vectors as `'[..]'` strings | "Avoids" the codec | Text round-trip, lossy, broken distance queries | **Never** — use `register_vector` |
| Embed at 3072 (default) | One less config line | Unindexable (>2000 cap), 4× storage, insert mismatch | **Never** — set 768 |
| Reuse the 15 RPM chat limiter for embeddings | One limiter, less code | Starves `/ask`; conflates two quotas | **Never** — separate limiter |
| No similarity floor on retrieval | Simpler query | Garbage recall, Rule-5 risk | **Never** — floor ~0.70 |
| No per-user cap / decay | Ship faster | Context rot — the #1 companion-bot failure | **Never** — ship cap+decay in v1 |
| No sensitivity/PII gate on writes | Simpler distill prompt | Durable storage of sensitive data; harmful roasts | **Never** — stop-ship |
| Backfill all history at launch | "Instant memory" | Quota burn, partial migration risk | Avoid; start empty, accumulate forward |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| pgvector + asyncpg pool | `register_vector` before `CREATE EXTENSION` → `ValueError: unknown type: public.vector` | Run `CREATE EXTENSION` on a bootstrap connection *before* `create_pool(init=register_vector)` |
| pgvector + Neon PgBouncer | Believing `statement_cache_size=0` breaks the codec | Codec is per-connection (`set_type_codec`), not a prepared stmt — coexists fine |
| `gemini-embedding-001` dims | Leaving default 3072 vs `vector(768)` column | Set `output_dimensionality=768` on **both** doc + query embeds; one shared config constant |
| Embedding task_type | Same task_type for store and query | `RETRIEVAL_DOCUMENT` on write, `RETRIEVAL_QUERY` on read — mismatching degrades recall |
| Gemini quota model | Routing embeds through the 15 RPM chat limiter | Separate ~60 RPM embedding limiter; embeds are a different Google quota (~100 RPM) |
| Discord 3s interaction | Synchronous embed before `defer()` | `defer()` first, embed/search/roast in `followup` via `create_task()` |
| google-genai SDK | Using deprecated `google-generativeai` for embeddings | `client.aio.models.embed_content(...)` on the existing `genai.Client` |
| Embedding model | Using `text-embedding-004` (deprecated 2026-01-14) | `gemini-embedding-001` |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Embedding every message | Quota burn, store bloat | Event + session-end triggers only | Immediately on any active channel |
| No per-user cap | Retrieval noise, slow ANN | ~150/user cap + decay sweep | Weeks of accumulation |
| IVFFlat on tiny corpus | Poor recall, rebuild needed | HNSW or no index | At index-creation time on small data |
| Unbatched fact writes | N calls for N facts | `embed_content(contents=[list])` = 1 call | Multi-fact distillation passes |
| Sync embed on hot path | "Did not respond"; latency spikes | Defer-first + create_task | First-query-after-idle / under load |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Storing PII (email/phone/address/real name) | Durable personal-data liability | PII scrub in distill gate; store only Discord handle |
| Distilling sensitive disclosures (grief, health, self-harm) | Durable, re-surfaceable harmful roast ammo | Sensitivity exclusion list in distill prompt; carry "serious → dial back" into the write gate |
| Hallucinated distilled "facts" stored as truth | Rule-5 accuracy violation; reputational | Constrain distiller to observed/stated, atomic, third-person; no inference |
| Stale embedded numbers vs live SQL | Roast cites wrong count | Never embed counts; numbers from live `SELECT` only |
| No owner prune control | Bad memory poisons roasts permanently | `/forget` owner command |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Same callback every session | Feels broken, stops being funny | `last_surfaced_at` + novelty penalty in re-rank |
| Roast referencing irrelevant memory | Confusing, breaks immersion | Similarity floor ~0.70; inject nothing if nothing clears it |
| Forced memory injection | Awkward shoehorned roasts | Hand memory as *candidate ammo*; let Gemini NOOP |
| Memory overwhelming personality | Loses Dexter's voice | Cap 1–3 facts / ~300–500 tokens in `USER CONTEXT` |

## "Looks Done But Isn't" Checklist

- [ ] **Vector codec:** Works in dev where extension was manually created — verify boot order creates `CREATE EXTENSION` *before* the `init=register_vector` pool on a fresh Neon branch.
- [ ] **Dimensions:** Inserts succeed — verify `output_dimensionality=768` is set on *both* doc and query embeds and matches the `vector(768)` column.
- [ ] **Embedding limiter:** Embeds work — verify they use a *separate* limiter and never touch the 15 RPM chat window (check `/ask` latency unaffected during background distillation).
- [ ] **Similarity floor:** Retrieval returns rows — verify a below-threshold result injects *nothing* rather than a weak match.
- [ ] **Accuracy:** Roast reads well — verify every *number* comes from live SQL, not an embedded memory.
- [ ] **Sensitivity gate:** Distillation runs — verify a test grief/health/PII message is *not* stored.
- [ ] **Hygiene:** Store fills — verify per-user cap eviction and the decay sweep actually delete rows.
- [ ] **3s window:** Memory-augmented command responds — verify `defer()` fires before any embed call.
- [ ] **Dedup:** Repeated facts — verify a >0.90-similar candidate NOOPs instead of inserting a duplicate.
- [ ] **Template fallback:** Embedding API down — verify the roast still fires from the template path (existing Gemini-first discipline).

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Extension/pool ordering crash | LOW | Pre-create extension; reorder boot; redeploy |
| Hand-serialized vectors shipped | MEDIUM | Add `register_vector`; re-read column as list; no data loss if dims correct |
| Embedded stale numbers | MEDIUM | Stop embedding counts; purge number-bearing rows; route numbers to SQL |
| Store polluted (every-message writes) | MEDIUM | Add triggers+dedup; bulk-delete low-salience/duplicate rows; let it re-accumulate |
| Context rot (unbounded growth) | MEDIUM | Apply cap + decay sweep retroactively; re-evaluate retrieval quality |
| Sensitive content stored | LOW–MEDIUM | `/forget` or admin delete; add the gate; audit existing rows |
| 3072-dim column (unindexable) | MEDIUM | Re-embed at 768 into a new `vector(768)` column; or switch to `halfvec`; migrate |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. Extension-vs-pool ordering | 11.1 | Clean boot on a fresh Neon branch (no manual extension) |
| 2. `statement_cache_size` misbelief | 11.1 | Codec returns `list[float]`; `<=>` order correct; K-04 pool flags intact |
| 3. Dimension mismatch / ANN cap | 11.1 + 11.2 | Inserts succeed; HNSW creatable; single dims constant |
| 4. Embedding every message | 11.4 | Write-call count flat vs chat volume |
| 5. Embedding SQL-known facts | 11.4 + 11.5 | No digits in memory rows; numbers match `/history` |
| 6. Sharing the 15 RPM limiter | 11.2 | `/ask` latency unaffected during distillation |
| 7. Sync embed blocks 3s | 11.3 / 11.5 | No "did not respond"; embed after `defer()` |
| 8. No similarity floor | 11.3 | Below-floor result injects nothing |
| 9. Memory overrides accuracy | 11.4 + 11.5 + 11.6 | Numbers from SQL; contradictions superseded; ammo framing |
| 10. Sensitive content / PII | 11.4 | Grief/health/PII test message not stored |
| 11. Prompt bloat | 11.3 | ≤3 facts, ≤~500 tokens injected |
| 12. No write-time dedup | 11.4 (needs 11.3) | >0.90 candidate NOOPs |
| 13. Stale/contradictory memories | 11.6 | Newer fact supersedes; recency in re-rank |
| 14. Unbounded growth | 11.6 | Cap eviction + decay sweep delete rows |
| 15. Repeated callbacks | 11.3 (P2) | Novelty penalty down-weights recent surfaces |
| 16. Live migration/backfill | 11.1 + 11.6 | Idempotent DDL; no backfill in boot path |
| 17. IVFFlat-on-empty / premature index | 11.6 | No index until measured need; HNSW when added |
| 18. Cold-start latency | 11.1 + 11.3 | Warm pool inherits K-04; retrieval off hot path |

## Sources

- Context7 `/pgvector/pgvector-python` — `register_vector(conn, schema)` signature; `ValueError` on missing `vector` type (suppressed only for `halfvec`/`sparsevec`); `init=` pool pattern; per-connection `set_type_codec` — HIGH
- STACK.md (this milestone) — verified asyncpg+pgvector+Neon integration, 768-dim/2000-dim cap, `gemini-embedding-001`, separate 100 RPM embedding quota, `text-embedding-004` deprecation 2026-01-14 — HIGH
- FEATURES.md (this milestone) — write triggers, dedup >0.90, similarity floor 0.70, top-k=8→1–3, per-user cap ~150, 90-day decay, context-rot prior art (Mem0, Generative Agents, companion bots) — HIGH (architecture) / MEDIUM (numeric defaults)
- Existing code: `services/gemini.py` (`_RateLimiter`, priority tiers, defer discipline), `database.py` (`SCHEMA_SQL` plain-DDL constraint, asyncpg pool helpers), CLAUDE.md/PROJECT.md (K-04 Neon pool tuning, Critical Rule 5, 3s interaction rule, serious→dial-back) — HIGH

---
*Pitfalls research for: pgvector + Gemini-embeddings RAG memory on the existing Dexter stack (v1.2 / Phase 11)*
*Researched: 2026-06-26*
