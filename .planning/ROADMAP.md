# Roadmap: Dexter ("Dex")

## Overview

Dexter is a sarcastic, personality-driven Discord bot: a reliable YouTube music player with a Gemini-powered personality (`/ask`, `/imagine`), unprompted "alive" behavior (roasts, reactions, lyrics, history), hardened and scaled to run 24/7 on PostgreSQL behind an `AutoShardedBot`. v1.0 (Phases 1–4) shipped the bot; v1.1 (Phases 5–8) re-targeted the deploy substrate (Koyeb + Neon), killed playback latency, and added player UX + social/ops features. v1.2 "Sharper & Smarter" (Phases 9–12) hardened the reliability gaps, covered the untested critical paths with real tests, gave Dex a durable RAG long-term memory (pgvector on Neon + Gemini embeddings) for callback roasts, and rounded out the music/UX. v1.3 "Taste Brain" (Phases 13–17) turned listening history into semantic taste memory that powers a smarter DJ, wired RAG into `/roast`/`/ask` with a `/memory` view+forget escape hatch, added proactive memory callbacks, and closed with vision/multimodal roasting — all on existing infra, zero new dependencies. v1.4 "Open House" (Phases 18–23) retrofits the single-community bot into a publicly-invitable, multi-tenant-robust portfolio piece: a per-guild config seam replaces the hardcoded single-channel assumption, onboarding + admin `/setup` makes a fresh server "just work" ambient-silent-until-configured, an owner control plane gives the recruiter-facing risk (full-savage personality on public servers) a real reactive kill-switch, memory scoping contains third-party leakage across guilds, invite plumbing ships a least-privilege OAuth2 URL, and a portfolio surface (landing page + case-study README + CI/CD) is the recruiter-facing deliverable — all without changing the on-demand, owner-run hosting model.

## Milestones

- ✅ **v1.0 MVP** — Phases 1–4 (shipped 2026-06-12) — see [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Live & Lethal** — Phases 5–8 (shipped code 2026-06-26; 24/7 deploy ⏸ parked) — see [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)
- ✅ **v1.2 Sharper & Smarter** — Phases 9–12 (shipped code 2026-06-30) — see [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md)
- ✅ **v1.3 Taste Brain** — Phases 13–17 (shipped code 2026-07-03) — see [milestones/v1.3-ROADMAP.md](milestones/v1.3-ROADMAP.md)
- ✅ **v1.4 Open House** — Phases 18–23 (shipped code 2026-07-14) — see [milestones/v1.4-ROADMAP.md](milestones/v1.4-ROADMAP.md)

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

## Progress

**Execution Order:** Phases executed in numeric order: 1 → 2 → 2.5 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15 → 16 → 17 → 18 → 19 → 20 → 21 → 22 → 23

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
