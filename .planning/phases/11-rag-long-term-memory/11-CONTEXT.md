# Phase 11: RAG Long-Term Memory - Context

**Gathered:** 2026-06-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Dexter gains a **third memory layer**: a durable semantic/episodic store (`pgvector` on the
existing Neon Postgres + `gemini-embedding-001` @ 768d) that remembers distilled, roast-worthy
*episodes* across restarts and powers **callback roasts** — the **stat × episode** payoff: a hard
number from live SQL (e.g. "mr brightside, 14 plays since april") paired with a recalled moment from
pgvector (e.g. "right after you swore you were done with the killers").

Reuses existing Neon Postgres + existing Gemini API key: **zero new infrastructure, zero new monthly
cost, one new pip dependency (`pgvector`).** The layered architecture is **not restructured** — one
new service, one new model module, one new table, one new Gemini primitive, one backward-compatible
prompt kwarg.

**Load-bearing principle:** structured SQL owns *numbers*; the semantic layer owns *episodes/opinions*.
Numbers always come from a live SELECT; memories are only candidate ammo the model may NOOP.

**In scope:** the 6-sub-phase RAG loop (schema → embedding → retrieval → write/distill → integration →
hygiene), all per MEM-01…MEM-07. Accuracy firewall, sensitivity/PII gate, and hygiene (cap + decay)
**all ship in this phase, not deferred.**

**Out of scope (anti-features):** embedding every message; embedding SQL-known numbers; knowledge-graph
/ multi-hop memory; a reranker model in the loop; cross-user "server lore"; historical backfill (start
empty, accumulate forward). `/forget` owner command deferred to v1.x.

</domain>

<decisions>
## Implementation Decisions

These are the **vision/tone/feel** decisions made in discussion. They sit on top of the
research-locked mechanics (see Canonical References) — they do not override them.

### Sensitivity / PII Gate (MEM-05 — stop-ship, ships in v1)
- **D-01:** The distill-time sensitivity gate blocks **identity & wellbeing** content: mental health,
  self-harm, medical conditions, sexuality, grief / relationship trauma, real-world PII (names,
  addresses, phone/email), and **anything said in apparent distress**. When in doubt about these
  categories, drop the memory.
- **D-02:** Everything else is **fair game** for durable roast ammo: music-taste cringe, hypocrisy,
  3am binge sessions, light/comedic drama. The bot stays funny; it doesn't punch at vulnerability.
- **D-03:** This is a **stop-ship** gate (a blocked item is never stored), not a soft filter, and it
  ships in Phase 11 — never deferred.

### Callback Cadence / Feel (MEM-06)
- **D-04:** Recalled memories surface as an **occasional payoff**, NOT on every roast that has ammo.
  Callbacks hit harder when rarer.
- **D-05:** **Anti-repeat is promoted INTO Phase 11** (research had it as "should-have v1.x"): track
  `last_surfaced_at` per memory and apply a **novelty / recently-surfaced penalty** so the same
  callback doesn't go stale. The cadence decision (D-04) depends on this, so it is in-scope here.
- **D-06:** Memories remain **candidate ammo the model may NOOP** — backward-compatible injection; any
  hard numbers in the output still come from live SQL, never from a memory.

### Salience Source (research-flagged gap — resolved)
- **D-07:** Salience is scored at write time by a **hybrid**: event type sets a **base weight**
  (milestone > late-night > repeat-song > auto-queue-ignored …), and the **distiller may bump** the
  score for a genuinely spicy/notable one-off moment. Deterministic floor + LLM flexibility.
- **D-08:** This salience score is what the **decay sweep + per-user cap eviction** rank on (low
  salience ages out first).

### Write Triggers / Distill Boundary (research-flagged gap — resolved; MEM-04)
- **D-09:** Two write paths fire the distiller, **never per-message**:
  1. **Notable-event hooks (immediate):** repeat-song, milestone, late-night, auto-queue
     ignored-memory — the already-firing notable-event paths in `cogs/events.py` / `cogs/music.py`.
  2. **Once-daily batch:** a daily background task (mirrors `cache_cleanup` / `ytdlp_update`
     `@tasks.loop`) distills the day's banter from message buffers in one priority-2 call.
- **D-10:** **No voice-session-end trigger** — explicitly rejected to avoid a third write path; the
  daily batch covers session banter.

### Claude's Discretion
- All numeric retrieval defaults (top-k, similarity floor, dedup threshold, per-user cap, decay
  window, rerank weights, injected-fact count/token budget) are **NOT decided here** — they are
  MEDIUM-confidence tuned priors to be validated by the **opening numeric-defaults validation spike**
  and observed during 11.2–11.5. Planner owns the spike; defaults from research are the starting points.
- Exact salience base-weights per event type, and the precise distiller-bump mechanism, are
  implementation detail for 11.3/11.4 planning.
- All boot-ordering, codec registration, prompt-injection site, and sweep-task patterns are
  research-verified HIGH — follow the canonical refs, no re-litigation.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.** This is the flagship,
research-backed phase — the research files below are authoritative for the mechanics and are MORE
binding than this CONTEXT.md on anything technical.

### Phase 11 research (authoritative — read all five)
- `.planning/research/SUMMARY.md` — executive synthesis: stack, architecture, build order, pitfalls,
  the 6 sub-phase decomposition, and the numeric-defaults research flag.
- `.planning/research/STACK.md` — full asyncpg + pgvector + Neon integration pattern (`register_vector`
  in pool `init=`, extension-first bootstrap, `gemini-embedding-001` @ 768d, cosine `<=>`, no ANN
  index day-one).
- `.planning/research/FEATURES.md` — must/should/anti-feature breakdown; the "SQL owns numbers,
  semantic owns episodes" principle; stat × episode payoff.
- `.planning/research/ARCHITECTURE.md` — verified integration points (`bot.py:_initialize_once`,
  `database.py` SCHEMA_SQL + K-04 pool tuning, `services/gemini.py` `_RateLimiter`/priorities,
  `personality/prompts.py:build_chat_prompt` + its 4 callers, `cogs/ai.py`, `cogs/events.py`,
  `models/*`).
- `.planning/research/PITFALLS.md` — 18 pitfalls mapped to sub-phases (boot-ordering trap, embedding
  SQL-known numbers, dimension mismatch, shared-limiter starvation, no similarity floor, sync-embed 3s
  blowout, sensitive-content storage, unbounded growth, IVFFlat-on-empty-table).

### Roadmap / requirements
- `.planning/ROADMAP.md` §"Phase 11: RAG Long-Term Memory" — goal, success criteria, 7-plan
  decomposition (11-01…11-07).
- `.planning/REQUIREMENTS.md` — MEM-01 … MEM-07 (the seven requirements this phase satisfies).

### Code to correct during planning (stale references)
- `.planning/PROJECT.md` and `CLAUDE.md` still name the **deprecated** `text-embedding-004` (sunset
  2026-01-14). Phase 11 uses **`gemini-embedding-001` @ 768d** — correct the stale references during
  planning (tracked in STATE.md blockers).

</canonical_refs>

<code_context>
## Existing Code Insights

(Integration points are verified in `.planning/research/ARCHITECTURE.md`; summary below.)

### Reusable Assets
- `services/gemini.py` `_RateLimiter` + priority tiers — clone the limiter pattern for a **separate**
  `_embed_limiter` (~60 RPM), never the shared 15 RPM chat budget.
- `models/` pure-logic TDD seam (e.g. `compute_streak`, and the Phase 10 rerank/dedup seam) — model
  for `models/memory.py` `MemoryFact` + pure rerank/recency/novelty/dedup functions.
- `@tasks.loop` daily background tasks (`cache_cleanup`, `ytdlp_update`) — template for the daily
  distill-batch task and the daily memory-sweep task.
- `database.py` `SCHEMA_SQL` (idempotent plain DDL) + K-04 Neon pool tuning (`statement_cache_size=0`,
  `ssl='require'`, bounded `max_inactive_connection_lifetime`) — new pool keeps this tuning; the
  pgvector codec is a per-connection `set_type_codec`, NOT a prepared statement (the
  `statement_cache_size=0` "breakage" is a verified MISBELIEF).

### Established Patterns
- Services wired in `bot.py:_initialize_once`, attached as `bot.memory_service`, accessed via
  `self.bot.memory_service` — `services/memory.py MemoryService(pool, gemini_service)` follows this.
- `personality/prompts.py:build_chat_prompt(mood, user_summary, seasonal)` (line ~91, 4 callers) —
  add an **optional backward-compatible** `memories=` kwarg; empty/None must render byte-identical to
  today's prompt.
- Roast surfaces to wire `recall()` into: `/ask` (`cogs/ai.py`), `/roast` (`cogs/ai.py:149`),
  `_generate_ambient_roast` (`cogs/events.py:87`), and the notable-event roasts in `cogs/music.py`
  (`_post_music_roast` ~1061, `_build_roast_line` ~1073).

### Integration Points
- **Write hooks (D-09):** the notable-event paths already firing in `cogs/events.py`
  (`on_voice_state_update` late-night, milestone, repeat) and `cogs/music.py` (auto-queue
  ignored-memory) — `MemoryService.remember()` hangs off these.
- **Boot ordering (Pitfall 1):** `CREATE EXTENSION IF NOT EXISTS vector` runs on a throwaway
  `asyncpg.connect()` BEFORE `create_pool(init=_register_vector)`.

</code_context>

<specifics>
## Specific Ideas

- **Signature payoff to design toward:** the **stat × episode** callback roast — a true live-SQL
  number paired with a recalled pgvector episode (research SUMMARY's "mr brightside / done with the
  killers" example). This is the phase's reason to exist; retrieval quality is judged by whether this
  lands.
- Tone target for the sensitivity gate (D-01/D-02): punch at *choices and hypocrisy*, never at
  *vulnerability*.

</specifics>

<deferred>
## Deferred Ideas

- **`/forget` owner command** (prune a misfired memory on demand) — research "should-have v1.x".
  Deferred: decay sweep + per-user cap already bound the store and a misfire ages out; add later only
  if real misfires demand it.
- **Cross-user / "server lore" memory** — anti-feature for now (scoping + privacy unresolved). Future
  milestone if ever.
- **Salience/novelty re-rank deep tuning** beyond the in-phase hybrid + anti-repeat — revisit if
  callbacks feel obvious/repetitive after the validation spike + live observation.
- **HNSW ANN index** — not in v1 (seq scan is sub-ms at hundreds–low-thousands of rows). Add
  `vector_cosine_ops` HNSW only past ~10k rows; never IVFFlat on a tiny/empty table.

</deferred>

---

*Phase: 11-rag-long-term-memory*
*Context gathered: 2026-06-29*
