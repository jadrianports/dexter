# Roadmap: Dexter ("Dex")

## Overview

Dexter is a sarcastic, personality-driven Discord bot: a reliable YouTube music player with a Gemini-powered personality (`/ask`, `/imagine`), unprompted "alive" behavior (roasts, reactions, lyrics, history), hardened and scaled to run 24/7 on PostgreSQL behind an `AutoShardedBot`. v1.0 (Phases 1–4) shipped the bot; v1.1 (Phases 5–8) re-targeted the deploy substrate (Koyeb + Neon), killed playback latency, and added player UX + social/ops features. v1.2 "Sharper & Smarter" (Phases 9–12) hardened the reliability gaps, covered the untested critical paths with real tests, gave Dex a durable RAG long-term memory (pgvector on Neon + Gemini embeddings) for callback roasts, and rounded out the music/UX. v1.3 "Taste Brain" (Phases 13–17) turns listening history into semantic taste memory that powers a smarter DJ, wires RAG into `/roast`/`/ask` with a `/memory` view+forget escape hatch, adds proactive memory callbacks, and closes with vision/multimodal roasting — all on existing infra, zero new dependencies.

## Milestones

- ✅ **v1.0 MVP** — Phases 1–4 (shipped 2026-06-12) — see [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Live & Lethal** — Phases 5–8 (shipped code 2026-06-26; 24/7 deploy ⏸ parked) — see [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)
- ✅ **v1.2 Sharper & Smarter** — Phases 9–12 (shipped code 2026-06-30) — see [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md)
- 🚧 **v1.3 Taste Brain** — Phases 13–17 (planning)

## Phases

**Phase Numbering:** integer phases are planned milestone work; decimal phases (e.g. 2.5) are urgent insertions, ordered numerically between their surrounding integers. Numbering is continuous across milestones — v1.3 continues at Phase 13.

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

<details>
<summary>✅ v1.2 Sharper & Smarter (Phases 9–12) — SHIPPED (code) 2026-06-30</summary>

- [x] **Phase 9: Reliability & Ops Hardening** (4/4 plans) — truthful `/health` (degraded-503), fire-and-forget failure surfacing via `make_task`, un-wedgeable `on_ready` watchdog + startup-sync recovery, DB query timeouts, YouTube search/extract self-heal — completed 2026-06-26
- [x] **Phase 10: Critical-Path Test Coverage** (4/4 plans) — playback/health/roast decision logic extracted to pure `logic/` modules with ~83 mock-free unit tests + three named scar regressions; full-suite-green + clean-boot regression gate — completed 2026-06-27
- [x] **Phase 11: RAG Long-Term Memory** (7/7 plans) — `pgvector` on Neon + `gemini-embedding-001` @ 768d (separate 60 RPM limiter); recall/rerank read + remember/dedup/cap-evict write halves, sensitivity/PII + accuracy firewall, callback roasts at four surfaces, daily decay sweep — zero new infra — completed 2026-06-29
- [x] **Phase 12: Richer Music/UX** (4/4 plans) — per-server `/jam` playlists, `/skips` analytics, LRCLIB third lyrics fallback, token-set auto-queue hallucination validation — completed 2026-06-30

**Deferred at close (4 new v1.2 items, live-runtime-gated):** Phase 09/11 HUMAN-UAT + VERIFICATION — `human_needed` live-Discord checks, resume on an always-on residential host. (The audit also re-surfaced the carried v1.1 Phases 03–06 deploy checks.) See STATE.md Deferred Items.

Full phase details, success criteria, and decisions archived in
[milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md).

</details>

### 🚧 v1.3 Taste Brain (Phases 13–17) — IN PLANNING

**Milestone Goal:** Turn Dexter's listening history into semantic long-term memory that powers a genuinely good DJ (smarter auto-queue, discovery, generative jams), memory-aware `/roast` + `/ask`, and proactive callbacks — plus vision/multimodal roasting — deepening the v1.2 RAG foundation on existing infra (`pgvector` + the separate 60 RPM embed limiter), at zero new cost.

- [x] **Phase 13: Semantic Music Memory** — new number-free `taste_episode` memory kind, its own salience/decay tier, background distillation task distinct from existing loops (foundation for everything below) (completed 2026-07-02)
- [x] **Phase 14: Smarter Music Brain** — taste-aware auto-queue (skip history as negative hint), artist/genre discovery command grounded in SQL co-occurrence, generative "continue this jam" suggestions (completed 2026-07-02)
- [x] **Phase 15: RAG Reach** — `recall()` grounds `/roast @user` (target-scoped) and `/ask`; `/memory` view + `/memory forget` (verified hard-delete, the trust escape hatch) (completed 2026-07-02)
- [x] **Phase 16: Proactive Memory Callbacks** — background surface volunteers a memory at an active moment, rarer than ambient roasts, with a per-user opt-out (completed 2026-07-02)
- [ ] **Phase 17: Vision / Multimodal Roasting** — cadence-gated, safety-guarded image reactions via `gemini-2.5-flash` vision, sequenced last for blast-radius reasons

## Phase Details

### Phase 13: Semantic Music Memory

**Goal**: Dexter's listening history becomes a retrievable long-term memory — a new `taste_episode` kind distilled number-free onto the existing `user_memories` vector store — feeding every downstream consumer in this milestone.
**Depends on**: Phase 12 (first v1.3 phase; extends the Phase 11 `MemoryService`/pgvector infrastructure already shipped, no schema fork)
**Requirements**: TASTE-01, TASTE-02, TASTE-03
**Success Criteria** (what must be TRUE):

  1. Dexter's stored memory for a user includes number-free "taste episode" facts (artist/genre preference narrative) distilled from real listening activity, with no raw counts embedded (TASTE-01)
  2. Taste-episode memories carry their own salience base weight and decay tier, distinct from and tunable separately from Phase 11's general-fact defaults (TASTE-02)
  3. Taste episodes are written by a background task on its own schedule, distinct from the existing distill-batch/decay-sweep loops, without spiking load on the Neon pool (TASTE-03)
  4. Existing memory-backed behavior (ambient callback roasts, current `/roast`/`/ask` wiring) continues to work unchanged — the new memory kind is additive, not disruptive

**Plans**: 4 plans
Plans:
**Wave 1**

- [x] 13-01-PLAN.md — Taste config knobs + salience/decay tier + pure logic/taste.py banding & gate
- [x] 13-02-PLAN.md — song_history aggregate helpers + expires_at refresh helper

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 13-03-PLAN.md — kind-aware decay horizon + self-refresh-on-dedup fix (D-05)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 13-04-PLAN.md — taste_distill_batch @tasks.loop + 3-site boot registration

### Phase 14: Smarter Music Brain

**Goal**: Dexter's auto-queue, discovery, and jam features become taste-aware — using the Phase 13 foundation plus live SQL — a genuinely better DJ, not a bland server-average shuffler.
**Depends on**: Phase 13 (auto-queue negative hints, discovery, and jam suggestions all read taste signal written by the foundation phase)
**Requirements**: BRAIN-01, BRAIN-02, BRAIN-03
**Success Criteria** (what must be TRUE):

  1. Auto-queue measurably stops re-suggesting tracks/artists a user has recently skipped — skip history acts as a negative hint in the Gemini-in-the-loop selection, not a trained model (BRAIN-01)
  2. A discovery command surfaces artist/genre adjacency grounded in real `song_history`/`user_artist_counts` co-occurrence SQL — never a hallucinated recommendation (BRAIN-02)
  3. Dexter can suggest additions to continue a server's `/jam` playlist using taste context + Gemini, and every suggestion passes hallucination validation (reusing `logic/autoqueue.py` token-set containment) before being queued (BRAIN-03)
  4. Discovery and jam-suggestion queries stay multi-user-safe (aggregate/server-scoped), never leaking one user's individual listening data into another user's results

**Plans**: 5 plans
Plans:
**Wave 1** *(shared substrate — parallel, no file overlap)*

- [x] 14-01-PLAN.md — SQL substrate: get_recently_skipped / get_user_top_artist / get_artist_cooccurrence + kind-filtered recall (OQ1) + 6 config knobs
- [x] 14-02-PLAN.md — pure logic seams (is_recently_skipped_artist, select_positive_taste_context) + prompt builders (recommendation extension, discover-commentary, jam-suggestion)

**Wave 2** *(consumer cogs — parallel, blocked on Wave 1)*

- [x] 14-03-PLAN.md — taste-aware auto-queue: negative skip hint + positive room-taste blend + D-02 hard post-filter (BRAIN-01)
- [x] 14-04-PLAN.md — /discover command: invoker-anchored SQL co-occurrence adjacency + confirm-to-queue (BRAIN-02)
- [x] 14-05-PLAN.md — /jam suggest subcommand: validated generative jam assist, propose-and-confirm (BRAIN-03)

### Phase 15: RAG Reach

**Goal**: Long-term memory becomes directly visible and controllable — `/roast` and `/ask` are grounded in real recalled history, and a user can view and irreversibly erase what Dexter remembers about them.
**Depends on**: Phase 14 (memory-driving-a-decision is validated end-to-end via auto-queue before extending memory to direct user-facing read/write surfaces)
**Requirements**: RAG-01, RAG-02, RAG-03, RAG-04
**Success Criteria** (what must be TRUE):

  1. `/roast @user` grounds its roast in the **target user's** own recalled history — never the invoker's — alongside the existing live SQL stat (RAG-01)
  2. `/ask` answers reflect the invoker's recalled memory when relevant, and produce a byte-identical prompt (no behavior change) when no memory clears the recall floor (RAG-02)
  3. A user can run `/memory` to see an in-character, read-only view of what Dexter remembers about them (RAG-03)
  4. A user can run `/memory forget` to delete their stored memories, and the rows **and** their embeddings are verifiably gone — later recall no longer returns them (RAG-04)

**Plans**: 3 plans
Plans:
**Wave 1** *(parallel — no file overlap)*

- [x] 15-01-PLAN.md — DB substrate: list_user_memories + delete_all_user_memories helpers + tests/test_database_phase15.py (static + live-DB remember→forget→recall==[] Success Criterion 4) (RAG-03, RAG-04)
- [x] 15-02-PLAN.md — D-01 cadence: remove MEMORY_CALLBACK_CHANCE gate from /ask & /roast only (ambient surfaces keep it) + tests/test_ambient_recall_cadence.py regression lock (RAG-01, RAG-02)

**Wave 2** *(blocked on 15-01)*

- [x] 15-03-PLAN.md — /memory cog: /memory view (verbatim, ephemeral, paginated) + /memory forget (count preview + danger confirm, nuke-all) + bot.py registration + config knob + tests/test_memory_command.py (RAG-03, RAG-04)

### Phase 16: Proactive Memory Callbacks

**Goal**: Dexter occasionally volunteers a memory unprompted at a well-chosen active moment, never crossing into "the bot is watching me" territory — and any user can turn it off for themselves.
**Depends on**: Phase 15 (hard dependency — `/memory forget` must ship and exist as the escape hatch before an autonomous memory-surfacing surface ships; bad trust ordering otherwise)
**Requirements**: PROACT-01, PROACT-02
**Success Criteria** (what must be TRUE):

  1. Dexter occasionally brings up a remembered detail unprompted, anchored to an active moment in the designated channel — never a cold poll, never a DM (PROACT-01)
  2. Proactive callbacks fire rarer than the existing 0.30–0.35 ambient-roast cadence, bounded by an additive daily cap on top of the probability roll (PROACT-01)
  3. A user can pause proactive callbacks for themselves without deleting their underlying memories — a control distinct from `/memory forget` (PROACT-02)

**Plans**: 4 plans
Plans:
**Wave 1** *(parallel — no file overlap)*

- [x] 16-01-PLAN.md — Pure logic/proactive.py gate (should_fire_proactive_callback) + PROACTIVE_CALLBACK_CHANCE/DAILY_CAP config knobs + mock-free boundary/rarity tests (PROACT-01)
- [x] 16-02-PLAN.md — DB opt-out substrate: user_profiles.proactive_opt_out column + get/set_proactive_opt_out helpers + tests/test_database_phase16.py (signature guards + live-DB round-trip + independence-from-forget) (PROACT-02)

**Wave 2** *(blocked on Wave 1)*

- [x] 16-03-PLAN.md — Events glue: pre_recalled_memories bypass (Pitfall 1) + PROACTIVE_CALLBACK_FALLBACKS pool + _maybe_fire_proactive_callback + on_message designated-channel gate + behavioral tests (PROACT-01, PROACT-02)
- [x] 16-04-PLAN.md — /memory callbacks on|off opt-out subcommand (self-scoped, Choice-constrained, distinct from forget) + tests/test_memory_command.py additions (PROACT-02)

### Phase 17: Vision / Multimodal Roasting

**Goal**: Dexter reacts to images posted in the designated channel with cadence-gated, safety-guarded vision roasts — the highest-blast-radius new surface in the milestone, sequenced last and built on the cadence/safety discipline just proven by Phase 16.
**Depends on**: Phase 16 (sequenced last for blast-radius reasons, not a technical dependency — architecturally independent of the taste-brain track; benefits from freshly-proven cadence-gating discipline)
**Requirements**: VIS-01, VIS-02, VIS-03
**Success Criteria** (what must be TRUE):

  1. Dexter occasionally reacts to / roasts an image posted in the designated channel, gated by chance + per-user cooldown + priority-2 on the shared 15 RPM limiter — not every image, not every channel (VIS-01)
  2. Oversized (`MAX_VISION_IMAGE_BYTES`) or wrong-mime-type images are rejected before download, never reaching the Gemini call (VIS-01)
  3. A safety-blocked image reaction is silently skipped — no visible refusal message, never routed through the generic rate-limit/API-down fallback template used elsewhere (VIS-02)
  4. Explicit `safety_settings` are applied to every Gemini call that can receive user-influenced content, per the in-phase decision on whether to retrofit `/ask`/`/imagine` alongside vision (VIS-03)

**Plans**: 2 plans
Plans:
**Wave 1** *(config-dependent leaf foundations — single owner of config.py, no cross-plan config conflict)*

- [ ] 17-01-PLAN.md — Config knobs + `_build_safety_settings` retrofit across all 3 generate_content sites + image-carrying `chat()` (None-on-block contract preserved) + pure `logic/vision.py` gate + unit tests (VIS-01, VIS-03)

**Wave 2** *(events glue — blocked on 17-01)*

- [ ] 17-02-PLAN.md — `build_vision_prompt` conduct clause + `VISION_ROAST_FALLBACKS` (transport-only) + `cogs/events.py` glue (before-download mime/size gate, dedicated str|None generator, `_maybe_fire_vision_roast`, on_message dispatch, opt-out reuse) + behavioral tests (VIS-01, VIS-02)

## Progress

**Execution Order:** Phases execute in numeric order: 1 → 2 → 2.5 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15 → 16 → 17

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
| 9. Reliability & Ops Hardening | v1.2 | 4/4 | Complete (live-runtime UAT deferred) | 2026-06-26 |
| 10. Critical-Path Test Coverage | v1.2 | 4/4 | Complete | 2026-06-27 |
| 11. RAG Long-Term Memory | v1.2 | 7/7 | Complete (live-runtime UAT deferred) | 2026-06-29 |
| 12. Richer Music/UX | v1.2 | 4/4 | Complete | 2026-06-30 |
| 13. Semantic Music Memory | v1.3 | 4/4 | Complete   | 2026-07-02 |
| 14. Smarter Music Brain | v1.3 | 5/5 | Complete    | 2026-07-02 |
| 15. RAG Reach | v1.3 | 3/3 | Complete    | 2026-07-02 |
| 16. Proactive Memory Callbacks | v1.3 | 4/4 | Complete    | 2026-07-02 |
| 17. Vision / Multimodal Roasting | v1.3 | 0/2 | Planned | - |
