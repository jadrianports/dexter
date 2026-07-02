# Requirements: Dexter ("Dex") — v1.3 "Taste Brain"

**Defined:** 2026-07-02
**Core Value:** A sarcastic, personality-driven music + AI Discord bot that runs reliably — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.

Milestone goal: turn listening history into semantic long-term memory that powers a genuinely good DJ, memory-aware `/roast` + `/ask`, proactive callbacks, and vision/multimodal roasting — deepening the v1.2 RAG foundation on existing infra (`pgvector` + the separate 60 RPM embed limiter), at zero new dependency/infra/cost.

Research basis: `.planning/research/SUMMARY.md` (+ STACK/FEATURES/ARCHITECTURE/PITFALLS). All four researchers converged on **zero new dependencies**, the **flavor-vs-numbers split** (vector memory for narrative/ammo; live SQL for ranking decisions — honors the accuracy firewall), and **vision-last** sequencing for blast radius.

## v1 Requirements

Requirements for the v1.3 milestone. Each maps to a roadmap phase (13–17).

### Semantic Music Memory *(foundation — Phase 13)*

- [x] **TASTE-01**: Dexter distills a user's listening activity into number-free "taste episode" facts and stores them as a new `kind` in the existing `user_memories` vector store (no schema fork; accuracy firewall preserved — no counts embedded).
- [x] **TASTE-02**: Taste-episode memories use their own salience base weight and decay tier (deliberately set for taste, not inherited from the Phase 11 general-fact defaults).
- [x] **TASTE-03**: A background task writes taste episodes on a schedule distinct from the existing distill-batch/sweep loops (no thundering-herd on the Neon pool), following the module-scope `@tasks.loop` + `make_task` failure-surfacing convention.

### Smarter Music Brain *(Phase 14)*

- [x] **BRAIN-01**: Auto-queue is taste-aware — it incorporates the user's recent taste and `was_skipped` history as negative hints so it stops re-queueing tracks the user skips (Gemini-in-the-loop + SQL, not an ML model).
- [x] **BRAIN-02**: A discovery command surfaces artist/genre adjacency from listening history via grounded co-occurrence SQL over `song_history`/`user_artist_counts` (multi-user-safe aggregate query; zero hallucination, zero cost).
- [x] **BRAIN-03**: Generative jam assist — Dexter can "continue this jam" / suggest additions to a server jam using taste context + Gemini, with hallucination validation (reuse `logic/autoqueue.py` token-set containment).

### RAG Reach *(Phase 15)*

- [ ] **RAG-01**: `/roast @user` pulls the **target user's** recalled history (recall scoped to the target's `user_id`, never the invoker's) to ground the roast alongside the existing live SQL stat.
- [ ] **RAG-02**: `/ask` incorporates the invoker's recalled memory via the existing `build_chat_prompt(memories=...)` seam, so long-term memory informs answers (byte-identical prompt when no memory clears the floor).
- [x] **RAG-03**: A `/memory` command lets a user view what Dexter remembers about them (in-character, read-only view).
- [x] **RAG-04**: `/memory forget` lets a user delete their stored memories — the rows **and** their embeddings are actually removed (verified deletion, the escape hatch that must exist before proactive callbacks ship).

### Proactive Memory Callbacks *(Phase 16)*

- [ ] **PROACT-01**: A background surface occasionally volunteers a recalled memory at an **active moment** (anchored, never a poll, never a DM), gated behind `/memory forget` existing, firing **rarer** than the 0.30–0.35 ambient-roast rates, with an additive daily cap — the sarcastic voice is the anti-creepy mechanism.
- [ ] **PROACT-02**: A user can opt out of proactive callbacks (a "pause callbacks for me" control), distinct from full memory deletion.

### Vision / Multimodal Roasting *(Phase 17 — last, isolated blast radius)*

- [ ] **VIS-01**: Dexter reacts to / roasts images posted in the designated chat via `gemini-2.5-flash` vision input (`types.Part.from_bytes`), cadence-gated (chance + per-user cooldown + priority-2), with a `MAX_VISION_IMAGE_BYTES` size guard and mime-type check before download.
- [ ] **VIS-02**: Content-safety guardrails — explicit `safety_settings` on the vision call **plus** an app-level hard-rule layer; a safety block on an unprompted reaction **silently skips** (no visible refusal, never routed through the generic template fallback used for rate-limit/API-down cases).
- [ ] **VIS-03**: `safety_settings` are applied consistently to Gemini calls that can receive user-influenced content; decide during the phase whether to retrofit `/ask` + `/imagine` (Gemini 2.5 defaults safety OFF) or scope strictly to vision.

## v2 Requirements

Deferred to a future release. Tracked, not in this roadmap.

### Memory refinement

- **MEM-R1**: Salience reinforcement — frequently-recalled memories decay slower (deferred from v1.3 to keep scope tight).
- **MEM-R2**: Whether image-derived vision reactions should feed RAG memory (needs its own safety-gate design first — explicitly out of v1.3).

### Cosmetic

- **AVATAR-1**: Generative `/setavatar` owner command (Dex makes his own face via `/imagine`). Base avatar is set manually via the Developer Portal, so this is optional flourish only.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Any new pip dependency (Pillow, networkx, a vector DB, a scheduler lib) | All four research agents confirmed the shipped stack (`google-genai` 2.8.0 + `asyncpg` + `pgvector`) covers everything; a new dep is a smell |
| ML recommender / trained taste model | Gemini-in-the-loop + co-occurrence SQL is right-sized for one small community; ML is over-engineering |
| Embedding SQL-known numbers into taste memory | Violates the accuracy firewall (Critical Rule 12); numbers come from live SQL only |
| Proactive callbacks via polling loop or DM | The "bot is watching me" failure mode; callbacks must anchor to active moments in the designated channel only |
| Vision reactions feeding memory / manual avatar via code | Deferred (see v2); avatar is a manual Developer Portal action |
| Resuming the 24/7 deploy | Host-gated (YouTube datacenter-IP block); unchanged from v1.1/v1.2 — not this milestone |

## Traceability

Which phases cover which requirements. Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| TASTE-01 | Phase 13 | Complete |
| TASTE-02 | Phase 13 | Complete |
| TASTE-03 | Phase 13 | Complete |
| BRAIN-01 | Phase 14 | Complete |
| BRAIN-02 | Phase 14 | Complete |
| BRAIN-03 | Phase 14 | Complete |
| RAG-01 | Phase 15 | Pending |
| RAG-02 | Phase 15 | Pending |
| RAG-03 | Phase 15 | Complete |
| RAG-04 | Phase 15 | Complete |
| PROACT-01 | Phase 16 | Pending |
| PROACT-02 | Phase 16 | Pending |
| VIS-01 | Phase 17 | Pending |
| VIS-02 | Phase 17 | Pending |
| VIS-03 | Phase 17 | Pending |

**Coverage:**

- v1.3 requirements: 15 total
- Mapped to phases: 15/15 ✓ (confirmed by roadmapper — see ROADMAP.md Phases 13-17)
- Unmapped: 0
- Orphaned requirements: none
- Duplicate mappings: none

---
*Requirements defined: 2026-07-02*
*Last updated: 2026-07-02 after v1.3 roadmap creation (ROADMAP.md Phases 13-17)*
</content>
