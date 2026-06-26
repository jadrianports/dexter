# Roadmap: Dexter ("Dex")

## Overview

Dexter is a sarcastic, personality-driven Discord bot: a reliable YouTube music player with a Gemini-powered personality (`/ask`, `/imagine`), unprompted "alive" behavior (roasts, reactions, lyrics, history), hardened and scaled to run 24/7 on PostgreSQL behind an `AutoShardedBot`. v1.0 (Phases 1–4) shipped the bot; v1.1 (Phases 5–8) re-targeted the deploy substrate (Koyeb + Neon), killed playback latency, and added player UX + social/ops features. v1.2 "Sharper & Smarter" (Phases 9–12) hardens the reliability gaps, covers the untested critical paths with real tests, gives Dex a durable RAG long-term memory (pgvector on Neon + Gemini embeddings) for callback roasts, and rounds out the music/UX.

## Milestones

- ✅ **v1.0 MVP** — Phases 1–4 (shipped 2026-06-12) — see [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Live & Lethal** — Phases 5–8 (shipped code 2026-06-26; 24/7 deploy ⏸ parked) — see [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)
- 🚧 **v1.2 Sharper & Smarter** — Phases 9–12 (planning)

## Phases

**Phase Numbering:** integer phases are planned milestone work; decimal phases (e.g. 2.5) are urgent insertions, ordered numerically between their surrounding integers. Numbering is continuous across milestones — v1.2 continues at Phase 9.

<details>
<summary>✅ v1.0 MVP (Phases 1–4) — SHIPPED 2026-06-12</summary>

- [x] **Phase 1: Music MVP** — YouTube playback, queue model, cache-first audio, idle leave — completed 2026-04-12
- [x] **Phase 2: Personality + AI** — `/ask`, `/imagine`, mood, auto-queue, global rate limiter — completed 2026-04-13
- [x] **Phase 2.5: Hardening** (INSERTED) — observability, WAL, FFmpeg cleanup, yt-dlp self-heal — completed 2026-06-02
- [x] **Phase 3: Alive** (6/6 plans) — unprompted roasts, reactions, seasonal, status, streaks, `/lyrics`, `/history` — completed 2026-06-11
- [x] **Phase 4: Scale** (5/5 plans) — multi-server, PostgreSQL, sharding, queue persistence, Oracle A1 hosting — completed 2026-06-12

Full phase details, success criteria, decisions, and deferred items archived in
[milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md).

</details>

<details>
<summary>✅ v1.1 Live & Lethal (Phases 5–8) — SHIPPED (code) 2026-06-26 · 24/7 deploy ⏸ PARKED</summary>

- [~] **Phase 5: Ship It Live** (3/3 plans) — deploy re-targeted Oracle A1 → Koyeb WEB + Neon serverless Postgres; Neon-tuned asyncpg pool, `/health`, de-Oracle'd Dockerfile, `docs/DEPLOY-KOYEB.md`, 22-check runbook. Code-complete + code-verified; **LIVE 24/7 deploy PARKED** (YouTube datacenter-IP block → free cloud non-viable; bot runs on the user's PC on demand → Neon Singapore).
- [x] **Phase 6: Speed & Caching** (4/4 plans) — next-track prefetch (zero gap), opus-copy + SponsorBlock, Postgres resolution cache, download-timeout→stream fallback, LFU eviction, `PerfMetrics` in `/stats` — verified live 2026-06-26 (06-UAT).
- [x] **Phase 7: Player UX & Filters** (4/4 plans) — persistent control buttons, `/seek` `/previous` `/jump`, four `/filter` presets, favorites + playlists — verified live 2026-06-24 (07-HUMAN-UAT).
- [x] **Phase 8: Social & Ops** (3/3 plans) — `/roast @user`, `/leaderboard`, `/stats`, `/health`, quota visibility — verified live 2026-06-24 (08-HUMAN-UAT).

**Deferred at close (9 items, all live-deploy-gated):** DEPLOY-02/03/05/08 + 5 UAT / 4 verification gaps — resume when an always-on residential host exists. See STATE.md Deferred Items.

Full phase details, success criteria, and decisions archived in
[milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md).

</details>

### 🚧 v1.2 Sharper & Smarter (Phases 9–12) — IN PLANNING

**Milestone Goal:** Harden Dexter into a trustworthy 24/7-ready bot and give it a real memory — fix the reliability gaps, cover the untested critical paths, then make it smarter (long-term RAG memory) and richer (music/UX polish).

- [ ] **Phase 9: Reliability & Ops Hardening** — truthful `/health`, fire-and-forget failure logging, sync-hang guards, DB query timeouts, search/extract self-heal
- [ ] **Phase 10: Critical-Path Test Coverage** — extract + unit-test MusicCog playback, OpsCog/health metrics, EventsCog ambient-roast logic
- [ ] **Phase 11: RAG Long-Term Memory** — `pgvector` on Neon + Gemini embeddings → durable distilled memory and callback roasts; zero new infra
- [ ] **Phase 12: Richer Music/UX** — per-server playlists, skip-rate analytics, third lyrics fallback, auto-queue hallucination validation

## Phase Details

### Phase 9: Reliability & Ops Hardening

**Goal**: Dexter can no longer fail silently — `/health` tells the truth, background tasks surface their exceptions, startup sync recovers instead of hanging, and slow queries / transient YouTube failures self-heal.
**Depends on**: Phase 8 (first v1.2 phase; builds on the shipped `/health`, background tasks, and youtube service)
**Requirements**: REL-01, REL-02, REL-03, REL-04, REL-05, REL-06
**Success Criteria** (what must be TRUE):

  1. `/health` returns a degraded (non-200) status when a critical cog (e.g. MusicCog) fails to load or a core subsystem is down — it can never report "ok" while broken (REL-01)
  2. A crashing fire-and-forget task (`_prefetch_next_track`, `_post_auto_lyrics`, ambient roasts) surfaces its exception in the logs / error channel via a done-callback instead of vanishing silently (REL-02)
  3. A failed or slow command-tree sync on startup logs and recovers, and a shard crash mid-init can no longer permanently wedge the `on_ready` re-entry guard — the bot always finishes coming online (REL-03, REL-04)
  4. A slow DB query (e.g. leaderboard on a large guild) hits an enforced timeout and is handled instead of blocking the bot (REL-05)
  5. A transient `youtube` search/extract failure retries within a bounded budget and recovers, matching the existing download self-heal path (REL-06)

**Plans**: 4 plans (Wave 1 -> Wave 2 x3 parallel)

> Planned as 4 (not the suggested 5): REL-01 + REL-05 merged into the Wave-1 config-foundation plan
> (both are tiny config-wiring edits to the same `bot.py` + `cogs/ops.py`), which lets Wave 2 run
> three plans fully in parallel with zero `files_modified` overlap (utils+music vs bot.py vs youtube).
> REL-02 spans two plans: create_task surfacing (09-02) and `@loop.error` loop surfacing (09-03).
Plans:
**Wave 1**

- [x] 09-01-PLAN.md - Config foundation + truthful `/health` + enforced DB query-timeout floor (REL-01, REL-05) - Wave 1

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 09-02-PLAN.md - Fire-and-forget `create_task` failure surfacing via `utils/tasks.py` make_task (REL-02) - Wave 2
- [x] 09-03-PLAN.md - Startup sync recovery + un-wedgeable `on_ready` watchdog + `@loop.error` handlers (REL-03, REL-04, REL-02) - Wave 2
- [ ] 09-04-PLAN.md - Bounded retry / self-heal for youtube search + extract (REL-06) - Wave 2

### Phase 10: Critical-Path Test Coverage

**Goal**: The untested critical-path decision logic — playback, health/metrics, ambient roasts — is extracted into pure importable functions and unit-tested, respecting the convention that Discord/process glue stays untested-by-design, with the regression gate green.
**Depends on**: Phase 9 (tests lock in the hardening fixes; the REL-01 degraded-health path is exactly what TEST-02 covers)
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04
**Success Criteria** (what must be TRUE):

  1. MusicCog playback decision logic (queue-from-selection validity guards, next-track/skip selection, queue-persistence restore selection) exists as pure functions with passing unit tests (TEST-01)
  2. OpsCog metrics aggregation and `/health` status-determination logic is pure and unit-tested, covering the REL-01 degraded path (TEST-02)
  3. EventsCog ambient-roast trigger/gating logic (chance, cooldown, eligibility) is pure and unit-tested (TEST-03)
  4. The full test suite stays green and the bot boots clean with no new silent failures in `dexter.log` (regression gate) (TEST-04)

**Plans**: TBD (~4)

Plans:

- [ ] 10-01: Extract + unit-test MusicCog playback decision logic (TEST-01)
- [ ] 10-02: Extract + unit-test OpsCog metrics + `/health` status determination, incl. degraded path (TEST-02)
- [ ] 10-03: Extract + unit-test EventsCog ambient-roast trigger/gating logic (TEST-03)
- [ ] 10-04: Regression gate — full suite green + clean boot, no new silent failures (TEST-04)

### Phase 11: RAG Long-Term Memory

**Goal**: Dexter gains a durable semantic memory layer — `pgvector` on the existing Neon Postgres + `gemini-embedding-001` @ 768d — so it remembers distilled, roast-worthy episodes across restarts and lands callback roasts that pair a live SQL stat with a recalled moment (the **stat × episode** payoff), at zero new infrastructure and zero new monthly cost.
**Depends on**: Phase 9 (background-task failure logging + DB timeouts underpin the priority-2 embedding write path); reuses the pure-logic TDD seam established in Phase 10 for the rerank/dedup functions
**Requirements**: MEM-01, MEM-02, MEM-03, MEM-04, MEM-05, MEM-06, MEM-07
**Success Criteria** (what must be TRUE):

  1. `pgvector` is enabled on Neon with a `user_memories` table (`vector(768)` column), and the vector codec registers cleanly on every pooled connection at boot — `CREATE EXTENSION` runs on a throwaway connection BEFORE pool creation (boot-order-safe; `register_vector` never raises "unknown type") (MEM-01)
  2. Embeddings use `gemini-embedding-001` @ 768d behind a **separate** embedding rate limiter (~60 RPM) — never the shared 15 RPM chat budget — and run off the 3s command-defer critical path (MEM-02)
  3. Retrieval returns the top-k semantically-relevant memories above a similarity floor, reranked (relevance + recency + salience + novelty), capped to 1–3 injected facts, and injects **nothing** when nothing clears the floor (MEM-03)
  4. A write path distills roast-worthy facts on event/session-end triggers (NEVER per-message) with write-time near-duplicate dedup, gated by a sensitivity/PII filter, and never embeds numbers SQL already knows (play counts, streaks) — the accuracy firewall (MEM-04, MEM-05)
  5. Callback roasts inject retrieved memories as optional, backward-compatible "candidate ammo" the model may NOOP, while any hard numbers in the output come from live SQL; memory hygiene ships in-phase — a per-user cap (~150) and a decay/expiry sweep for low-salience facts keep the store bounded (MEM-06, MEM-07)

**Plans**: TBD (~6, plus an opening validation spike)
**Approach**: This is the flagship, research-backed phase (`.planning/research/SUMMARY.md`). It opens with a short **numeric-defaults validation spike** — the priors top-k=8, 0.70 similarity floor, 0.90 dedup threshold, ~150 per-user cap, 90-day decay, and rerank weights (relevance 1.0 / recency 0.5 / salience 0.7 / novelty 0.5) are MEDIUM-confidence tuned starting points to validate empirically against this bot's real scale and budget before retrieval lands. The suggested plan decomposition follows the research's 6 sub-phase dependency chain (schema → embedding → retrieval → write/distill → integration → hygiene). It stays **one** roadmap phase.

Plans:

- [ ] 11-01: Foundation — `CREATE EXTENSION` + `user_memories` in `SCHEMA_SQL`, extension-first bootstrap connection + `init=_register_vector` on `create_pool`, shared 768-dim config constant; opens with the numeric-defaults validation spike (MEM-01)
- [ ] 11-02: Embedding primitive + retrieval read path — `GeminiService.embed()` + separate `_embed_limiter`, `search_memories` scoped ANN, pure `MemoryFact` rerank/recency/novelty (TDD), `MemoryService.recall()` with 0.70 floor → rerank → top 1–3 (MEM-02, MEM-03)
- [ ] 11-03: Write path + dedup — insert/bump/count/evict helpers, `MemoryService.remember()` (distill → embed → >0.90 dedup → insert/bump → cap guard), pure `dedup_decision` (MEM-04 partial)
- [ ] 11-04: Distillation triggers + sensitivity/PII gate — hook `remember()` into event/session-end paths (repeat-song, milestone, late-night, auto-queue ignored-memory, daily batch), accuracy + sensitivity firewalls, never embed SQL-known numbers (MEM-04, MEM-05)
- [ ] 11-05: Prompt injection + callback-roast integration (capstone) — backward-compatible `build_chat_prompt(memories=...)`, wire `recall()` into `/ask`, `/roast`, ambient roasts; candidate-ammo framing, hard numbers from live SQL (MEM-06)
- [ ] 11-06: Hygiene & ops — `delete_expired_memories` decay sweep (~90d low-salience) as a daily background task, contradiction supersede; per-user cap eviction lands in 11-03 (MEM-07)

### Phase 12: Richer Music/UX

**Goal**: Round out the music experience — per-server shared playlists, visible skip-rate analytics, a third lyrics fallback, and hallucination-validated auto-queue — so the existing v1.1 playback/social surfaces get noticeably richer and more trustworthy.
**Depends on**: Phase 9 (search/extract self-heal underpins the auto-queue validation path); builds on the v1.1 favorites/playlists, auto-queue, and `/lyrics` already shipped
**Requirements**: UX-01, UX-02, UX-03, UX-04
**Success Criteria** (what must be TRUE):

  1. A guild's shared playlists ("jams") are scoped per-server and stay distinct from a user's global favorites (UX-01)
  2. Skip-rate analytics are surfaced to users — the tracked skip data becomes visible, e.g. via `/stats` or a dedicated surface (UX-02)
  3. `/lyrics` degrades gracefully through a third fallback source when both Genius and AZLyrics fail (UX-03)
  4. AI auto-queue validates Gemini's suggestions against actual YouTube results and rejects hallucinated tracks before queueing (UX-04)

**Plans**: TBD (~4)

Plans:

- [ ] 12-01: Per-server scoped playlists, distinct from global favorites (UX-01)
- [ ] 12-02: Surface skip-rate analytics to users (UX-02)
- [ ] 12-03: Third lyrics fallback source for graceful `/lyrics` degradation (UX-03)
- [ ] 12-04: Auto-queue hallucination validation against real YouTube results (UX-04)

## Progress

**Execution Order:** Phases execute in numeric order: 9 → 10 → 11 → 12

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Music MVP | v1.0 | shipped (pre-GSD) | Complete | 2026-04-12 |
| 2. Personality + AI | v1.0 | shipped (pre-GSD) | Complete | 2026-04-13 |
| 2.5. Hardening | v1.0 | shipped (pre-GSD) | Complete | 2026-06-02 |
| 3. Alive | v1.0 | 6/6 | Complete | 2026-06-11 |
| 4. Scale | v1.0 | 5/5 | Complete | 2026-06-12 |
| 5. Ship It Live | v1.1 | 3/3 | Code complete — live deploy ⏸ PARKED (YT datacenter-IP block) | 2026-06-15 |
| 6. Speed & Caching | v1.1 | 4/4 | Complete — verified live (06-UAT) | 2026-06-26 |
| 7. Player UX & Filters | v1.1 | 4/4 | Complete — verified live (07-HUMAN-UAT) | 2026-06-18 |
| 8. Social & Ops | v1.1 | 3/3 | Complete — verified live (08-HUMAN-UAT) | 2026-06-19 |
| 9. Reliability & Ops Hardening | v1.2 | 3/4 | In Progress|  |
| 10. Critical-Path Test Coverage | v1.2 | 0/4 | Not started | - |
| 11. RAG Long-Term Memory | v1.2 | 0/6 | Not started | - |
| 12. Richer Music/UX | v1.2 | 0/4 | Not started | - |
