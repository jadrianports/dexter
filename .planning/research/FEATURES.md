# Feature Research — RAG Long-Term Memory for a Personality Chatbot

**Domain:** Durable semantic long-term memory for a single-community, personality-driven Discord bot (Dexter, v1.2 Phase 11). Memory exists to power *callback roasts* — Dex referencing real past behavior/banter across restarts.
**Researched:** 2026-06-26
**Confidence:** HIGH on architecture/patterns (Mem0, Generative Agents, companion-bot design all converge); MEDIUM on exact numeric defaults (tuned to this bot's scale + 15 RPM budget, validate in the research spike).

---

## Framing: what "memory" means *here*

Dexter already has two memory layers. The RAG layer is a **third**, and the design must not duplicate the other two:

| Layer | Mechanism | Good at | Already exists |
|-------|-----------|---------|----------------|
| Short-term | `MessageBuffer` (10 msgs/channel, 24h TTL, in-RAM) | live conversational context | ✅ v1.0 |
| Structured / deterministic | Postgres (`song_history`, `user_artist_counts`, `user_profiles`, streaks) | **exact counts, dates, rankings** | ✅ v1.0–v1.1 |
| **Semantic / episodic (NEW)** | `pgvector` + Gemini embeddings | **fuzzy recall of stated opinions, notable events, banter** | ⏳ Phase 11 |

**Load-bearing principle:** the structured layer is the source of truth for *numbers*; the semantic layer recalls *episodes and opinions* that SQL can't express. The killer roast pairs them: a hard stat from SQL ("mr brightside, 14 plays since april") + a recalled moment from pgvector ("right after you swore you were 'done with the killers'"). **Never embed what a `SELECT COUNT(*)` already answers** — it wastes the budget and risks the vector store drifting from ground truth (a direct Critical-Rule-5 accuracy violation if Gemini reads a stale embedded number instead of live SQL).

---

## Feature Landscape

### Table Stakes (Users Expect These)

For the feature to feel like real "long-term memory" rather than a gimmick.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Durable cross-restart store | "Long-term" is the whole pitch; in-RAM dies on restart | LOW | New `user_memories` table on existing Neon Postgres + `pgvector` extension; zero new infra (matches v1.2 decision) |
| **Distilled declarative facts**, not raw logs | Industry consensus (Mem0, MemoryBank, companion bots): store "carlos is a father" not "carlos said X at 3:02" | MEDIUM | One Gemini call distills an event/session into 0–3 atomic, third-person sentences. Embed the sentence. |
| Per-user (+per-guild) scoping | Roasts must be about *the right person*; cross-user leakage is a correctness + privacy bug | LOW | `user_id`/`guild_id` filter in the `WHERE` before the vector search |
| Semantic retrieval (top-k + threshold) | Recall the *relevant* memory for the moment, not a random one | LOW | top-k ANN search with a similarity floor (defaults below) |
| Write-time dedup | Without it the store fills with 50 copies of the same fact → context rot | MEDIUM | Mem0 ADD/UPDATE/NOOP: embed candidate, compare to top-1 existing; if too similar, bump `hit_count` instead of inserting |
| Accuracy guarantee | Critical Rule 5 — never sacrifice facts for a joke; a roast citing a wrong number is worse than no roast | LOW | All *numbers* in a callback come from SQL and are passed to Gemini as ground-truth context, never invented by the model |

### Differentiators (What Makes Dexter's Memory *Funny*)

These align with Core Value: personality is the product. This is where to spend effort.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Callback roast** (stat × episode) | The payoff: "you've queued mr brightside 14 times since april" lands because it's specific, true, and surprising | MEDIUM | Deterministic stat from SQL + recalled episode from pgvector, both handed to Gemini as candidate ammo |
| Salience/novelty-weighted retrieval | Surfacing a *surprising-but-relevant* memory beats surfacing the most-similar one | MEDIUM | Generative-Agents score: `α_rel·relevance + α_rec·recency + α_imp·salience`, plus a **novelty bonus** that penalizes recently-surfaced memories so callbacks feel fresh |
| Surface-cooldown / anti-repeat | A callback reused every session stops being funny and feels broken | LOW | `last_surfaced_at` + `surface_count`; down-weight or skip recently-fired memories |
| Temporal phrasing ("since april") | Time-anchored roasts feel like genuine memory, not a lookup | LOW | Store `created_at`/`first_seen`; compute spans at retrieval, hand to Gemini |
| Periodic banter distillation | Turn /ask exchanges and chat into reusable roast ammo, not just music stats | MEDIUM | On voice-session end or daily, distill `MessageBuffer`/recent activity into 0–3 facts (one low-priority batched call) |
| Opt-in/owner forget controls | Lets the owner prune a memory that's stale or misfired | LOW | `/forget` (owner) or admin delete; cheap insurance against a bad memory poisoning roasts |

### Anti-Features (Tempting, but Problematic Here)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Store/embed **every message** | "More memory = smarter" | Blows the 15 RPM budget, fills the store with noise, causes context rot, costs embeddings | Write only on notable events + periodic distillation (see triggers) |
| Embed song counts / play history | It's "data about the user" | SQL already answers it exactly; embedding risks a stale number contradicting ground truth | Keep numbers in SQL; embed only opinions/episodes |
| Let the LLM recall the *numbers* from memory | One-step "just ask the model" | Hallucinated stats = accuracy violation; embeddings drift from live counts | Numbers always from a live `SELECT`; model only phrases them |
| Real-time write on every message turn | "Remember instantly" | Per-message Gemini distill call is unaffordable at 15 RPM and mostly stores nothing worth keeping | Event-trigger + session-end batch |
| Unbounded per-user memory | "Never forget" | Context rot, retrieval noise, slow ANN, cost; companion bots explicitly cite this as the #1 failure | Per-user cap + decay/eviction |
| Knowledge-graph / multi-hop memory (Mem0-Graph) | State of the art in papers | Massive overkill for one community of a few dozen users; ops burden | Flat fact table + vector index is plenty at this scale |
| Cross-user "what does the server think" memory | Fun idea | Scoping/privacy ambiguity, contradictory blends | Keep per-user; aggregate stats already live in `/leaderboard` |
| Reranker model in the retrieval loop | "Better RAG" best practice | Another model call against the 15 RPM budget for marginal gain at top-k=5 over a tiny corpus | Score-and-sort in Python; skip the reranker |

---

## Behavioral Design Decisions (the six sub-questions, with concrete defaults)

### 1. WHAT to store
- **Unit:** one atomic, declarative, third-person sentence per memory ("marcus said he's 'done with the killers'", "alex rage-quit after the auto-queue played country"). Short declarative statements retrieve and read best.
- **Eligible content:** stated opinions/preferences, reactions to roasts, notable one-off events, self-owns, recurring bits — i.e. things SQL *can't* express. **Not** raw counts, not full transcripts.
- **Embed:** the fact sentence, optionally prefixed with the subject/user for retrieval sharpness. Store alongside structured metadata: `user_id, guild_id, kind, fact_text, embedding, salience, created_at, last_seen_at, hit_count, last_surfaced_at, surface_count, expires_at`.

### 2. WHEN to write
- **Not every message.** Two triggers only:
  - **Event-triggered (synchronous-ish, rare):** milestone hits, repeat-song roast, a striking /ask exchange, an explicitly stated preference. These already fire elsewhere in `events.py` — hook a distill+write there.
  - **Periodic distillation (batched, low priority):** on voice-session end (or once daily), distill the channel's recent `MessageBuffer` / activity into **0–3** facts via a single Gemini call at **priority 2** (the existing "reject if wait >10s" tier), so it never starves user commands.
- **Dedup gate on every write:** embed candidate → search that user's top-1 existing memory → if cosine similarity **> 0.90**, NOOP and bump `last_seen_at`/`hit_count` (and optionally UPDATE if it's a newer phrasing of the same fact); else ADD.

### 3. WHEN / HOW to retrieve
- **Trigger:** any roast/response moment that already builds context — `/ask`, voice-join roast, repeat/ milestone roast, auto-queue commentary.
- **Query:** embed the triggering context text (the question, or a synthesized line like "marcus joined the voice channel"), filter by `user_id`/`guild_id`, ANN search.
- **Defaults:** fetch **top-k = 8** candidates, apply **cosine-similarity floor ≈ 0.70** (drop everything below), then **re-rank in Python** by
  `score = 1.0·relevance + 0.5·recency + 0.7·salience + 0.5·novelty`
  (novelty = penalty for recent `last_surfaced_at`; recency = exponential decay on `created_at`). Keep the **top 1–3** after re-rank.
- Skip a reranker model and skip semantic search entirely when the moment is purely numeric (let SQL handle it).

### 4. HOW MUCH to inject
- **1–3 memory facts**, as a short bullet list, slotted into the existing `USER CONTEXT` block of `DEXTER_SYSTEM_PROMPT` (next to `get_user_summary`).
- **Hard cap ~300–500 tokens** for the memory section so it never dwarfs the personality prompt or the few-shot exemplars. If nothing clears the threshold, inject nothing — Dex falls back to the existing taste summary.

### 5. Memory hygiene
- **Dedup:** write-time similarity gate (>0.90 → NOOP/UPDATE).
- **Decay/expiry:** low-salience conversational memories get `expires_at` ≈ **90 days**; high-salience (milestones, strong stated preferences) persist. A daily sweep deletes expired rows.
- **Per-user cap:** **~150 memories/user**. On exceed, evict the lowest `salience × recency × hit_count` score.
- **Contradiction:** prefer the most recent `created_at` at retrieval; on write, if a new fact contradicts an existing one, UPDATE/supersede (Mem0 update phase) rather than keeping both — avoids "context rot" where stale preferences silently poison roasts.
- **Anti-repeat:** track `last_surfaced_at`/`surface_count`; the novelty term in the retrieval score keeps callbacks fresh.

### 6. The callback-roast pattern
- **Goal:** surprising-but-relevant. Achieved by the salience+novelty re-rank, not raw top-1 similarity (top-1 is usually the *obvious* fact, not the funny one).
- **Construction:** hand Gemini **(a)** the deterministic stat from SQL and **(b)** the 1–3 recalled facts as *candidate ammo* in the prompt, with an instruction to weave one in **only if it lands** — let the model NOOP rather than force every fact. This mirrors the existing Gemini-first / template-fallback discipline.
- **Accuracy:** the number is always real (from SQL); the model only phrases it. This honors Critical Rule 5 and the persona's "specific recall of real play counts" identity in `prompts.py`.

### Budget awareness (15 RPM)
- **Embeddings run on a separate Gemini endpoint** (`text-embedding-004`) with its own, far higher free-tier quota — keep embedding calls *off* the chat 15 RPM limiter, but still throttle them defensively.
- A **retrieval** costs **1 embedding call** (cheap). A **write/distill** costs 1 generation call — batch these at session-end, priority 2.
- The roast generation itself is the existing /ask-style call already inside the 15 RPM limiter at user priority. The memory layer adds *no* extra generation call to the user's critical path — it only enriches the prompt.

---

## Feature Dependencies

```
pgvector extension on Neon
    └──requires──> user_memories table + embedding column + ANN index
                       └──enables──> Semantic retrieval (top-k + threshold)
                                         └──enables──> Callback roast (stat × episode)

Fact distillation (Gemini) ──feeds──> user_memories
    └──requires──> MessageBuffer / event hooks (already exist)

Write-time dedup ──requires──> Semantic retrieval (must search before insert)

Salience/novelty re-rank ──enhances──> Callback roast
Surface-cooldown ──enhances──> Callback roast

Decay/expiry + per-user cap ──protect──> Semantic retrieval quality (anti context-rot)

Embedding endpoint ──conflicts──> chat 15 RPM limiter (keep on separate quota/throttle)
```

### Dependency Notes
- **Retrieval requires the store + index first** — schema/extension is the earliest sub-phase.
- **Dedup depends on retrieval** — you must be able to search before you can dedup-on-write; build retrieval before write.
- **Callback roast depends on both SQL stats (exist) and semantic recall (new)** — it's the integration capstone, last.
- **Decay/cap aren't optional polish** — companion-bot post-mortems cite unbounded memory as the primary cause of degraded recall; ship them with v1, not later.

---

## MVP Definition

### Launch With (Phase 11 v1)
- [ ] `pgvector` + `user_memories` table on Neon — durable store, zero new infra
- [ ] Fact distillation (event-trigger + session-end batch, 0–3 facts/call, priority 2)
- [ ] Per-user/guild-scoped semantic retrieval (top-k=8 → floor 0.70 → top 1–3)
- [ ] Write-time dedup (>0.90 → NOOP/UPDATE)
- [ ] Callback roast: SQL stat + recalled episode handed to Gemini as ammo, accuracy guaranteed
- [ ] Memory hygiene baseline: per-user cap (~150) + decay sweep (90d on low salience)

### Add After Validation (v1.x)
- [ ] Salience/novelty re-rank tuning — trigger: callbacks feel repetitive or obvious
- [ ] Surface-cooldown — trigger: same callback fires too often
- [ ] `/forget` owner control — trigger: a misfired memory needs pruning

### Future Consideration (v1.3+)
- [ ] Multimodal/image-derived memories — gated on the v1.3 vision feature + the parked 24/7 host
- [ ] Cross-user "server lore" memory — defer; scoping/privacy unresolved

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| pgvector store + schema | HIGH | LOW | P1 |
| Fact distillation (triggers) | HIGH | MEDIUM | P1 |
| Scoped semantic retrieval | HIGH | LOW | P1 |
| Write-time dedup | HIGH | MEDIUM | P1 |
| Callback roast integration | HIGH | MEDIUM | P1 |
| Per-user cap + decay | MEDIUM | LOW | P1 |
| Salience/novelty re-rank | MEDIUM | MEDIUM | P2 |
| Surface-cooldown | MEDIUM | LOW | P2 |
| `/forget` owner control | LOW | LOW | P2 |
| Knowledge-graph memory | LOW | HIGH | P3 (likely never) |
| Reranker model | LOW | MEDIUM | P3 (skip) |

## Competitor / Prior-Art Analysis

| Pattern | Mem0 | Generative Agents | Companion bots (Kindroid/Replika-style) | Dexter's Approach |
|---------|------|-------------------|------------------------------------------|-------------------|
| What to store | atomic facts, ADD/UPDATE/DELETE/NOOP, temporal metadata | NL "memory stream" of observations | declarative "model of who you are" | atomic third-person facts; numbers stay in SQL |
| When to write | extract per exchange + rolling summary | every observation | selective save | event-trigger + session-end batch (budget-driven) |
| Retrieval | vector top-k + LLM update decision | recency×relevance×importance, fit context window | RAG top-k | top-k=8 → 0.70 floor → relevance+recency+salience+novelty re-rank → top 1–3 |
| Hygiene | dedup via similarity, temporal supersede | decay 0.995/step | expire/decay/archive; warn against memory noise | dedup>0.90, 90d decay, ~150 cap, supersede on contradiction |

## Sources

- Mem0: Production-Ready Long-Term Memory — extraction/update phases, ADD/UPDATE/DELETE/NOOP, similarity dedup: https://arxiv.org/abs/2504.19413 , https://memo.d.foundation/breakdown/mem0
- Generative Agents — recency×relevance×importance retrieval scoring, exponential recency decay: https://ar5iv.labs.arxiv.org/html/2304.03442 , https://dl.acm.org/doi/fullHtml/10.1145/3586183.3606763
- RAG retrieval defaults — top-k 5–8, cosine-similarity threshold ~0.7, threshold filtering, confidence gate, pgvector cosine distance: https://meisinlee.medium.com/better-rag-retrieval-similarity-with-threshold-a6dbb535ef9e , https://www.sarahglasmacher.com/how-to-use-cosine-similarity-in-pgvector/
- Companion-bot memory design — distilled declarative facts vs logs, decay/archive, "context rot" from unbounded saves: https://lizlis.ai/blog/ai-memory-systems-explained-2026-why-chatbots-forget-companions-remember-and-stories-evolve/ , https://digitalhumancorp.com/en/research/why-ai-companion-forgets-you
- MemoryBank — long-term memory with decay for LLMs: https://arxiv.org/pdf/2305.10250

---
*Feature research for: RAG long-term memory in a personality Discord bot (Dexter v1.2, Phase 11)*
*Researched: 2026-06-26*
