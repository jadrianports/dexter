# Requirements: Dexter ("Dex") — v1.2 "Sharper & Smarter"

**Defined:** 2026-06-26
**Core Value:** A sarcastic, personality-driven music + AI Discord bot that runs reliably 24/7 — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.

## v1.2 Requirements

Requirements for the v1.2 milestone. Each maps to a roadmap phase (9–12). v1.0/v1.1 requirements
are archived in `milestones/`. The RAG category (MEM) is research-backed (`.planning/research/`);
the others derive from the v1.2 codebase-analysis pass.

### Reliability & Ops Hardening (Phase 9)

- [x] **REL-01**: `/health` reports a degraded (non-200) status when a critical cog (e.g. MusicCog) failed to load or a core subsystem is down — it can no longer return "ok" while broken
- [x] **REL-02**: Fire-and-forget background tasks (`_prefetch_next_track`, `_post_auto_lyrics`, ambient roasts) attach a done-callback that logs any exception instead of failing silently
- [x] **REL-03**: Command-tree sync on startup (`first_run` / `on_ready`) handles a sync failure or timeout without hanging the bot silently — it logs and recovers
- [x] **REL-04**: The `on_ready` re-entry guard cannot get permanently stuck (a shard crash mid-init no longer blocks all future ready-handling)
- [x] **REL-05**: Database queries enforce a timeout so a slow query (e.g. leaderboard on a large guild) cannot block the bot
- [x] **REL-06**: `youtube` search/extract self-heal on transient failure (bounded retry), matching the existing download self-heal path

### Critical-Path Test Coverage (Phase 10)

> Respects the project convention: Discord/process glue stays untested-by-design; these requirements
> extract the *decision logic* from the critical paths into pure, importable functions and test those.

- [x] **TEST-01**: The MusicCog playback decision logic (queue-from-selection validity guards, next-track/skip selection, queue-persistence restore selection) is extracted as pure functions and unit-tested
- [x] **TEST-02**: The OpsCog metrics aggregation and `/health` status-determination logic is pure and unit-tested (covering the REL-01 degraded path)
- [x] **TEST-03**: The EventsCog ambient-roast trigger/gating logic (chance, cooldown, eligibility) is pure and unit-tested
- [x] **TEST-04**: Full suite stays green and the bot boots clean with no new silent failures in `dexter.log` (regression gate)

### RAG Long-Term Memory (Phase 11)

> Research-backed (`.planning/research/SUMMARY.md`). Zero new infrastructure / zero new monthly cost:
> `pgvector` on the existing Neon Postgres + `gemini-embedding-001` @ 768d via the existing API key.

- [x] **MEM-01**: `pgvector` is enabled on Neon and a `user_memories` table (with a `vector(768)` column) exists; the vector codec is registered on pooled connections, boot-order-safe (`CREATE EXTENSION` before pool creation)
- [x] **MEM-02**: A `MemoryService.embed()` path uses `gemini-embedding-001` @ 768d behind a **separate** embedding rate limiter — never the shared 15 RPM chat budget — and runs off the 3s command-defer critical path
- [x] **MEM-03**: Retrieval returns the top-k semantically-relevant memories above a similarity floor, reranked (relevance + recency + salience + novelty), capped to 1–3 injected memories
- [x] **MEM-04**: A write path distills and stores roast-worthy facts on event/session-end triggers (NOT per-message), with near-duplicate dedup at write time
- [x] **MEM-05**: A sensitivity/PII gate prevents storing genuinely sensitive content, and the system never embeds facts SQL already knows (play counts, streaks) — preserving Critical Rule 5 (accuracy-first)
- [x] **MEM-06**: Retrieved memories are injected into the personality prompt as optional "candidate ammo" (backward-compatible) for callback roasts; any hard numbers in the output come from live SQL, not from memory
- [x] **MEM-07**: Memory hygiene ships in v1.2 — a per-user memory cap (~150) and a decay/expiry sweep for low-salience facts

### Richer Music / UX (Phase 12)

- [x] **UX-01**: Favorites/playlists can be scoped per-server (a guild's "jams" are distinct from a user's global favorites)
- [x] **UX-02**: Skip-rate analytics are surfaced to users (the tracked skip data becomes visible, e.g. via `/stats` or a dedicated view)
- [ ] **UX-03**: A third lyrics fallback exists for when both Genius and AZLyrics fail, so `/lyrics` degrades gracefully
- [x] **UX-04**: AI auto-queue validates Gemini's suggestions against actual YouTube results before queueing, rejecting hallucinated tracks

## Future Requirements (v1.3+)

Deferred. Tracked but not in the v1.2 roadmap.

### Vision / Multimodal (v1.3 candidate)

- **VIS-01**: Dexter reacts to/roasts images posted in chat via Gemini vision (`gemini-2.0-flash` multimodal)
- **VIS-02**: Content-safety guardrails so vision roasting skips genuinely sensitive images

### Deploy (host-gated — resumes on a Pi / always-on residential host)

- **DEPLOY-02**: Standing live-UAT checklist executed + passing
- **DEPLOY-03**: The 6 human-UAT scenarios (`04-HUMAN-UAT.md`) passing
- **DEPLOY-05**: Queue + position survive a restart, validated *live*
- **DEPLOY-08**: Keepalive / dead-man cron confirmed firing *in production*

## Out of Scope

Explicitly excluded for v1.2. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Railway / any datacenter-cloud 24/7 host | YouTube blocks datacenter IPs (free cloud non-viable); $1/mo ≠ 24/7. Stay on PC (residential) → Neon on demand until a Pi exists. |
| Vision / multimodal roasting | Deferred to v1.3 — leans hardest on the 15 RPM budget, needs safety guardrails, pays off most with the parked 24/7 host. |
| Redis (for RAG or anything) | RAG's vector store is Postgres (`pgvector`); no in-memory KV store is needed. |
| Embedding every message | Budget burn + context rot — write only distilled, event-triggered facts. |
| Embedding SQL-known numbers (play counts, streaks) | Stale embedded numbers would violate accuracy Rule 5 — numbers come from live SQL. |
| Knowledge-graph / reranker-model memory | Over-engineered for a single-community bot; pgvector top-k + heuristic rerank suffices. |
| Cross-user "server lore" memory | v1.2 memory is per-user; shared lore is a separate, larger design. |
| Historical memory backfill | Start empty and accumulate forward — avoids quota burn and partial-migration risk. |
| Web config dashboard | `/stats` in-Discord covers the owner need; deferred (not killed). |

## Traceability

Confirmed by the v1.2 roadmap (`.planning/ROADMAP.md`, Phases 9–12).

| Requirement | Phase | Status |
|-------------|-------|--------|
| REL-01 | Phase 9 | Complete |
| REL-02 | Phase 9 | Complete |
| REL-03 | Phase 9 | Complete |
| REL-04 | Phase 9 | Complete |
| REL-05 | Phase 9 | Complete |
| REL-06 | Phase 9 | Complete |
| TEST-01 | Phase 10 | Complete |
| TEST-02 | Phase 10 | Complete |
| TEST-03 | Phase 10 | Complete |
| TEST-04 | Phase 10 | Complete |
| MEM-01 | Phase 11 | Complete |
| MEM-02 | Phase 11 | Complete |
| MEM-03 | Phase 11 | Complete |
| MEM-04 | Phase 11 | Complete |
| MEM-05 | Phase 11 | Complete |
| MEM-06 | Phase 11 | Complete |
| MEM-07 | Phase 11 | Complete |
| UX-01 | Phase 12 | Complete |
| UX-02 | Phase 12 | Complete |
| UX-03 | Phase 12 | Pending |
| UX-04 | Phase 12 | Complete |

**Coverage:**

- v1.2 requirements: 21 total
- Mapped to phases: 21 (100% — confirmed by roadmap)
- Unmapped: 0

---
*Requirements defined: 2026-06-26*
*Last updated: 2026-06-26 after v1.2 roadmap creation (Phases 9–12 mapped, 21/21 coverage)*
