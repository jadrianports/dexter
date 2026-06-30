# Roadmap: Dexter ("Dex")

## Overview

Dexter is a sarcastic, personality-driven Discord bot: a reliable YouTube music player with a Gemini-powered personality (`/ask`, `/imagine`), unprompted "alive" behavior (roasts, reactions, lyrics, history), hardened and scaled to run 24/7 on PostgreSQL behind an `AutoShardedBot`. v1.0 (Phases 1–4) shipped the bot; v1.1 (Phases 5–8) re-targeted the deploy substrate (Koyeb + Neon), killed playback latency, and added player UX + social/ops features. v1.2 "Sharper & Smarter" (Phases 9–12) hardened the reliability gaps, covered the untested critical paths with real tests, gave Dex a durable RAG long-term memory (pgvector on Neon + Gemini embeddings) for callback roasts, and rounded out the music/UX.

## Milestones

- ✅ **v1.0 MVP** — Phases 1–4 (shipped 2026-06-12) — see [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Live & Lethal** — Phases 5–8 (shipped code 2026-06-26; 24/7 deploy ⏸ parked) — see [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)
- ✅ **v1.2 Sharper & Smarter** — Phases 9–12 (shipped code 2026-06-30) — see [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md)
- 📋 **v1.3** — not yet scoped (run `/gsd-new-milestone`; standing candidate: Vision / multimodal roasting)

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

### 📋 v1.3 (Not Yet Scoped)

Run `/gsd-new-milestone` to define v1.3. Standing candidate: **Vision / multimodal roasting** (VIS-01/02 — Dex reacts to images posted in chat via Gemini vision, with content-safety guardrails). The parked 24/7 live deploy (DEPLOY-02/03/05/08 + the live-UAT/verification tail) also resumes whenever an always-on residential host (Pi) is acquired.

## Progress

**Execution Order:** Phases executed in numeric order: 1 → 2 → 2.5 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12

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
</content>
</invoke>
