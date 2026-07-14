# Roadmap: Dexter ("Dex")

## Overview

Dexter is a sarcastic, personality-driven Discord bot: a reliable YouTube music player with a Gemini-powered personality (`/ask`, `/imagine`), unprompted "alive" behavior (roasts, reactions, lyrics, history), hardened and scaled to run 24/7 on PostgreSQL behind an `AutoShardedBot`. v1.0 (Phases 1–4) shipped the bot; v1.1 (Phases 5–8) re-targeted the deploy substrate (Koyeb + Neon), killed playback latency, and added player UX + social/ops features. v1.2 "Sharper & Smarter" (Phases 9–12) hardened the reliability gaps, covered the untested critical paths with real tests, gave Dex a durable RAG long-term memory (pgvector on Neon + Gemini embeddings) for callback roasts, and rounded out the music/UX. v1.3 "Taste Brain" (Phases 13–17) turned listening history into semantic taste memory that powers a smarter DJ, wired RAG into `/roast`/`/ask` with a `/memory` view+forget escape hatch, added proactive memory callbacks, and closed with vision/multimodal roasting — all on existing infra, zero new dependencies. v1.4 "Open House" (Phases 18–23) retrofits the single-community bot into a publicly-invitable, multi-tenant-robust portfolio piece: a per-guild config seam replaces the hardcoded single-channel assumption, onboarding + admin `/setup` makes a fresh server "just work" ambient-silent-until-configured, an owner control plane gives the recruiter-facing risk (full-savage personality on public servers) a real reactive kill-switch, memory scoping contains third-party leakage across guilds, invite plumbing ships a least-privilege OAuth2 URL, and a portfolio surface (landing page + case-study README + CI/CD) is the recruiter-facing deliverable — all without changing the on-demand, owner-run hosting model. v1.5 "Deep Cuts" (Phases 24–28) cleans the deploy story down to one honest Docker path, deepens the taste brain (salience reinforcement + vision-sourced memories), adds real DJ muscle (radio mode, skip-voting, spike-gated crossfade), and closes out the remaining portfolio release steps — the landing-page redesign already shipped.

## Milestones

- ✅ **v1.0 MVP** — Phases 1–4 (shipped 2026-06-12) — see [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Live & Lethal** — Phases 5–8 (shipped code 2026-06-26; 24/7 deploy ⏸ parked) — see [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)
- ✅ **v1.2 Sharper & Smarter** — Phases 9–12 (shipped code 2026-06-30) — see [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md)
- ✅ **v1.3 Taste Brain** — Phases 13–17 (shipped code 2026-07-03) — see [milestones/v1.3-ROADMAP.md](milestones/v1.3-ROADMAP.md)
- ✅ **v1.4 Open House** — Phases 18–23 (shipped code 2026-07-14) — see [milestones/v1.4-ROADMAP.md](milestones/v1.4-ROADMAP.md)
- 🚧 **v1.5 Deep Cuts** — Phases 24–28 (in progress — roadmap drafted 2026-07-15)

## Phases

**Phase Numbering:** integer phases are planned milestone work; decimal phases (e.g. 2.5) are urgent insertions, ordered numerically between their surrounding integers. Numbering is continuous across milestones.

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

<details>
<summary>✅ v1.3 Taste Brain (Phases 13–17) — SHIPPED (code) 2026-07-03</summary>

- [x] **Phase 13: Semantic Music Memory** (4/4 plans) — number-free `taste_episode` memory kind on the existing pgvector store, own salience/decay tier (`MEMORY_DECAY_DAYS_BY_KIND`), self-refresh-on-dedup (D-05), dedicated `taste_distill_batch` @ 05:00 UTC — zero new tables — completed 2026-07-02
- [x] **Phase 14: Smarter Music Brain** (5/5 plans) — taste-aware auto-queue (recently-skipped negative hint + hard post-filter + room-taste positive blend), `/discover` (invoker-anchored SQL co-occurrence adjacency), `/jam suggest` (validated generative additions) — read-only over taste + live SQL — completed 2026-07-02
- [x] **Phase 15: RAG Reach** (3/3 plans) — `recall()` grounds `/roast @user` (target-scoped) + `/ask` (D-01 gate removed from both, ambient keeps it); new `cogs/memory.py` `/memory view` + `/memory forget` (verified hard-delete of rows + embeddings, the trust escape hatch) — completed 2026-07-02
- [x] **Phase 16: Proactive Memory Callbacks** (4/4 plans) — pure `should_fire_proactive_callback` gate (chance 0.10 + daily cap 1) volunteering a chat-anchored memory unprompted; `proactive_opt_out` column + `/memory callbacks on|off`; `pre_recalled_memories` bypass keeps ambient cadence byte-identical — completed 2026-07-02
- [x] **Phase 17: Vision / Multimodal Roasting** (2/2 plans) — cadence-gated image roasts via `gemini-2.5-flash` vision (before-download mime/size gate, silent-skip on safety block), `safety_settings` retrofit across all 3 `generate_content` sites — completed 2026-07-02

**Deferred at close (24 items, all live-Discord/host-gated):** Phases 14–17 HUMAN-UAT + VERIFICATION (`human_needed` live-Discord checks) + carried v1.1/v1.2 checks + 3 stale CONTEXT question markers — resume when an always-on residential host exists. Zero code gaps. See STATE.md Deferred Items.

Full phase details, success criteria, and decisions archived in
[milestones/v1.3-ROADMAP.md](milestones/v1.3-ROADMAP.md).

</details>

<details>
<summary>✅ v1.4 Open House (Phases 18–23) — SHIPPED (code) 2026-07-14</summary>

**Milestone Goal:** Turn Dexter from a single-community bot into a publicly-invitable, multi-tenant-robust portfolio piece — a recruiter can invite it to any server and it just works — without changing the on-demand, owner-run hosting model.

- [x] **Phase 18: Per-Guild Config Foundation & CI Gate** (7/7 plans) — `guild_config` table + pure `logic/guild_config.py` seam + boot-loaded `GuildConfigService` cache replaces the hardcoded single-channel assumption (unconfigured guilds structurally silent); ruff + pytest CI against a `pgvector/pgvector:pg16` container on every push/PR — completed 2026-07-09
- [x] **Phase 19: Onboarding & Admin Setup** (4/4 plans) — `/setup` group (channel/roasts/vision) with `manage_guild` gate + independent per-guild toggles, required keyword-only `AmbientSurface` threading, guild-lifecycle glue (join-welcome-once, owner join/leave notices) — completed 2026-07-10
- [x] **Phase 20: Owner Control Plane & Rate Observability** (7/7 plans) — `guild_blocklist` table + `/guilds` list/silence/leave/block/unblock at ONE `interaction_check` choke point + block-check-first re-invite refusal, cache-only silence/block reads, per-guild Gemini usage counters (RATE-01) — completed 2026-07-13
- [x] **Phase 21: Memory Scoping & Guild Data Lifecycle** (4/4 plans) — explicit per-call-site `guild_scoped=True` opt-in narrows ANN recall for unprompted surfaces (`/ask` stays global), legacy NULL corpus grandfathered, `purge_guild_data` four-table hard-delete on removal (blocklist excluded) — completed 2026-07-13
- [x] **Phase 22: Invite Plumbing** (3/3 plans) — `logic/invite.py::build_invite_url()` sole least-privilege OAuth2 constructor + public `/invite` + CI drift-guard failing the build on any doc URL drift — completed 2026-07-14
- [x] **Phase 23: Portfolio Surface & CI/CD** (7/7 plans) — static `/site` landing page + architecture-case-study README + honest scope-boundary docs; `pages.yml`/`release.yml` CI/CD scaffolded — completed 2026-07-14

**Deferred at close (3 blocked-on-human reqs + 36 audit items):** PORT-02 (demo-GIF Dexter lines), CICD-02 (GitHub Pages toggle), CICD-03 (GHCR flip) need owner-performed GitHub-UI / live-bot steps; the 36 audit items (Phases 14–22 HUMAN-UAT + `human_needed` VERIFICATION + 3 stale CONTEXT markers) are live-Discord/host-gated. Zero code gaps. See STATE.md Deferred Items.

Full phase details, success criteria, and decisions archived in
[milestones/v1.4-ROADMAP.md](milestones/v1.4-ROADMAP.md).

</details>

### 🚧 v1.5 Deep Cuts (Phases 24–28) — IN PROGRESS

**Milestone Goal:** Clean the deploy story down to one honest Docker path, deepen the taste brain (durable memory + vision-sourced memories), add real DJ muscle (radio, skip-voting, crossfade), and finish the recruiter-facing surface. Continues phase numbering at Phase 24. Hosting model unchanged — the 24/7 deploy stays parked; this milestone makes Docker the clean, honest run path, not a 24/7 standup.

- [x] **Phase 24: Hosting Honesty & Docker** - Purge every dead cloud-host reference and replace the Koyeb deploy doc with a verified Docker run guide (completed 2026-07-14)
- [ ] **Phase 25: Smarter Memory** - Salience reinforcement (surfaced memories gain durability) + vision-sourced memory facts, additive on the existing pgvector store
- [ ] **Phase 26: Radio Mode & Skip Democracy** - Endless taste-brain-driven radio mode + vote-gated `/skip` so the queue isn't one user's toy
- [ ] **Phase 27: Crossfade Playback (Spike-Gated)** - Smooth track transitions, contingent on a plan-time spike proving playback-engine safety; descopes to a fast-follow if the spike shows instability
- [ ] **Phase 28: Portfolio Finish & Release** - Verify the shipped landing-page redesign and close out the remaining owner-performed release steps

## Phase Details

### Phase 24: Hosting Honesty & Docker

**Goal**: Dexter's deploy story is one honest, working Docker path — every dead cloud-host reference (Render, Koyeb, Oracle) is gone from code and docs, and a documented `docker compose up` run against Neon is verified to boot cleanly.
**Depends on**: Nothing (first phase of v1.5; independent, low-risk cleanup — mostly comments, config, and docs plus one local-boot verification)
**Requirements**: HOST-01, HOST-02, HOST-03, HOST-04
**Success Criteria** (what must be TRUE):

  1. Grepping the repo (code comments, `config.py`, `Dockerfile`, `docker-compose.yml`, `.env.example`, docs) for "Render", "Koyeb", or "Oracle" turns up zero live hosting-target references — only the host-agnostic `$PORT` read and Docker/residential-host framing remain.
  2. `docs/DEPLOY-KOYEB.md` no longer exists; a new Docker run guide documents `docker compose up` on a local/residential machine — env setup, the Neon `DATABASE_URL`, and how to verify the bot is alive.
  3. `docker compose up` builds the image and boots Dexter locally against Neon end-to-end: clean startup log, `/health` responds, no new silent failures appear in `dexter.log`.
  4. *(blocked-on-human, HOST-04)* The owner deletes the dashboard-side Render service so the repo stops auto-deploying and the CI/CD failure emails stop — there is no Render config in the repo to remove; the connection lives in the Render dashboard.**Plans**: 3 plans (2 waves)

**Wave 1**

- [x] 24-01-PLAN.md — Scrub Koyeb/Oracle from code, config & infra comments; delete dead Oracle-era scripts (HOST-01)
- [x] 24-02-PLAN.md — Reframe .env.example + CLAUDE.md host-honest; replace DEPLOY-KOYEB.md with a lean DEPLOY-DOCKER.md (HOST-01/02)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 24-03-PLAN.md — Permanent hosting drift guard + parked 24-HOST-UAT.md boot/Render-deletion checklist (HOST-01/02/03/04)

### Phase 25: Smarter Memory

**Goal**: Dexter's long-term memory gets more durable and richer — memories that keep proving relevant survive the daily decay sweep longer, and a vision roast now leaves behind a lasting memory of its own.
**Depends on**: Nothing new (additive on the existing Phase 11/13 pgvector `user_memories` store; no new tables, no schema fork)
**Requirements**: MEM-06, MEM-07
**Success Criteria** (what must be TRUE):

  1. A memory that has been recalled/surfaced multiple times shows measurably reinforced salience/expiry compared to an equally-old, never-surfaced memory — the daily decay sweep evicts the unsurfaced one first.
  2. A vision roast persists a distilled, number-free fact into `user_memories` under its own memory kind, gated by the same sensitivity/PII + accuracy-firewall checks every other kind goes through — no raw counts or SQL-known numbers get embedded (Critical Rule 12/13).
  3. Both changes are additive: zero new tables, zero schema fork, kind-agnostic `MemoryService` untouched — every pre-existing memory kind's salience baseline, decay, and dedup behavior stays byte-identical when the new reinforcement/vision-kind paths aren't exercised.

**Plans**: TBD

### Phase 26: Radio Mode & Skip Democracy

**Goal**: Dexter can DJ a room indefinitely off the taste brain, and skipping a track stops being one user's unilateral call.
**Depends on**: Nothing new (radio mode reads the existing taste-brain substrate from Phases 13/14; skip-voting is additive over the existing queue/playback engine)
**Requirements**: DJ-01, DJ-02
**Success Criteria** (what must be TRUE):

  1. A user can start radio/endless mode seeded from a track or an artist, and the queue keeps refilling off the taste brain — no manual `/play` needed — until a user stops it.
  2. Stopping radio mode returns the bot to normal manual queueing with no leftover auto-refill behavior.
  3. With more than one listener in voice, `/skip` requires reaching a configurable vote threshold (or listener majority) before the track actually skips, and Dexter narrates the running tally in response to each vote.
  4. A solo listener's `/skip` still skips instantly — vote-gating doesn't regress the single-listener case.

**Plans**: TBD

### Phase 27: Crossfade Playback (Spike-Gated)

**Goal**: Track transitions blend smoothly into each other — contingent on a plan-time research spike proving the existing playback engine (generation counter, `/skip`, prefetch) can support it safely. If the spike shows engine instability, this phase closes by formally descoping DJ-03 to a fast-follow instead of forcing a broken feature (standing Descope Rule).
**Depends on**: Phase 26 (shares the same playback-engine surface; sequencing after the other music-engine changes contains the spike risk to its own phase rather than compounding it with radio/skip-voting work)
**Requirements**: DJ-03
**Success Criteria** (what must be TRUE):

  1. A plan-time research spike prototypes crossfade against the real generation-counter/`/skip`/prefetch playback engine and produces an explicit go/no-go verdict *before* full implementation starts.
  2. **If go:** the tail of the outgoing track audibly blends into the head of the incoming track, and firing `/skip` mid-crossfade does not double-play audio, orphan an FFmpeg process, or desync the generation counter.
  3. **If no-go:** DJ-03 is formally moved to Future Requirements as DJ-F2 with the spike's findings documented in REQUIREMENTS.md/ROADMAP.md, and the phase closes clean rather than shipping an unstable engine change.

**Spike required**: yes — this phase cannot proceed past a plan-time research spike (`/skip`-mid-crossfade + generation-counter safety proof); a failed spike descopes DJ-03 per the standing Descope Rule (REQUIREMENTS.md) rather than forcing the workaround. Prior art exists (custom PCM-mixing `AudioSource` — `veloura-audio`, `discord-ext-music`); crossfade forfeits opus-copy during the fade and needs an `audioop`→`numpy` note for Python 3.13.

**Plans**: TBD

### Phase 28: Portfolio Finish & Release

**Goal**: The recruiter-facing portfolio surface reaches its finished, live state. The landing-page redesign already shipped (`c7fd22e`) — what remains is confirming it's still true and completing the owner-performed release steps.
**Depends on**: Nothing new (independent of the music/memory/hosting work; sequenced last as the milestone close-out)
**Requirements**: PORT-05 (already complete), PORT-02, CICD-02, CICD-03
**Success Criteria** (what must be TRUE):

  1. The `/site` landing page shows proper-case copy in its own voice, a working (non-broken) staged demo animation, and a distinct "after hours" visual identity — **already shipped** (`c7fd22e`); this phase confirms it's still true at milestone close. (PORT-05)
  2. *(blocked-on-human, PORT-02)* The demo mock shows two verbatim real Dexter personality lines in place of the `{{DEXTER_DEMO_LINE}}` placeholder tokens — needs a live bot; no invented lines.
  3. *(blocked-on-human, CICD-02)* GitHub Pages is enabled (`Settings → Pages → Source = GitHub Actions`) and the landing page is live at its public URL.
  4. *(blocked-on-human, CICD-03)* GHCR package visibility is set and the first `v*`-tag `release.yml` run publishes the image.

**UI hint**: yes (this phase concerns the `/site` landing page — no new build work is expected since PORT-05 already shipped; the annotation is flagged for downstream consistency only, verification/owner-action is the actual remaining scope)

**Plans**: TBD

## Progress

**Execution Order:** Phases execute in numeric order: 1 → 2 → 2.5 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15 → 16 → 17 → 18 → 19 → 20 → 21 → 22 → 23 → 24 → 25 → 26 → 27 → 28

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
| 13. Semantic Music Memory | v1.3 | 4/4 | Complete | 2026-07-02 |
| 14. Smarter Music Brain | v1.3 | 5/5 | Complete (live-runtime UAT deferred) | 2026-07-02 |
| 15. RAG Reach | v1.3 | 3/3 | Complete (live-runtime UAT deferred) | 2026-07-02 |
| 16. Proactive Memory Callbacks | v1.3 | 4/4 | Complete (live-runtime UAT deferred) | 2026-07-02 |
| 17. Vision / Multimodal Roasting | v1.3 | 2/2 | Complete (live-runtime UAT deferred) | 2026-07-02 |
| 18. Per-Guild Config Foundation & CI Gate | v1.4 | 7/7 | Complete    | 2026-07-09 |
| 19. Onboarding & Admin Setup | v1.4 | 4/4 | Complete    | 2026-07-10 |
| 20. Owner Control Plane & Rate Observability | v1.4 | 7/7 | Complete    | 2026-07-13 |
| 21. Memory Scoping & Guild Data Lifecycle | v1.4 | 4/4 | Complete   | 2026-07-13 |
| 22. Invite Plumbing | v1.4 | 3/3 | Complete    | 2026-07-14 |
| 23. Portfolio Surface & CI/CD | v1.4 | 7/7 | Complete   | 2026-07-14 |
| 24. Hosting Honesty & Docker | v1.5 | 3/3 | Complete    | 2026-07-14 |
| 25. Smarter Memory | v1.5 | 0/TBD | Not started | - |
| 26. Radio Mode & Skip Democracy | v1.5 | 0/TBD | Not started | - |
| 27. Crossfade Playback (spike-gated) | v1.5 | 0/TBD | Not started | - |
| 28. Portfolio Finish & Release | v1.5 | 0/TBD | Not started | - |
