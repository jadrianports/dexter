# Roadmap: Dexter ("Dex")

## Overview

Dexter is a sarcastic, personality-driven Discord bot: a reliable YouTube music player with a Gemini-powered personality (`/ask`, `/imagine`), unprompted "alive" behavior (roasts, reactions, lyrics, history), hardened and scaled to run 24/7 on PostgreSQL behind an `AutoShardedBot`. v1.0 (Phases 1–4) shipped the bot; v1.1 (Phases 5–8) re-targeted the deploy substrate (Koyeb + Neon), killed playback latency, and added player UX + social/ops features. v1.2 "Sharper & Smarter" (Phases 9–12) hardened the reliability gaps, covered the untested critical paths with real tests, gave Dex a durable RAG long-term memory (pgvector on Neon + Gemini embeddings) for callback roasts, and rounded out the music/UX. v1.3 "Taste Brain" (Phases 13–17) turned listening history into semantic taste memory that powers a smarter DJ, wired RAG into `/roast`/`/ask` with a `/memory` view+forget escape hatch, added proactive memory callbacks, and closed with vision/multimodal roasting — all on existing infra, zero new dependencies. v1.4 "Open House" (Phases 18–23) retrofits the single-community bot into a publicly-invitable, multi-tenant-robust portfolio piece: a per-guild config seam replaces the hardcoded single-channel assumption, onboarding + admin `/setup` makes a fresh server "just work" ambient-silent-until-configured, an owner control plane gives the recruiter-facing risk (full-savage personality on public servers) a real reactive kill-switch, memory scoping contains third-party leakage across guilds, invite plumbing ships a least-privilege OAuth2 URL, and a portfolio surface (landing page + case-study README + CI/CD) is the recruiter-facing deliverable — all without changing the on-demand, owner-run hosting model.

## Milestones

- ✅ **v1.0 MVP** — Phases 1–4 (shipped 2026-06-12) — see [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Live & Lethal** — Phases 5–8 (shipped code 2026-06-26; 24/7 deploy ⏸ parked) — see [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)
- ✅ **v1.2 Sharper & Smarter** — Phases 9–12 (shipped code 2026-06-30) — see [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md)
- ✅ **v1.3 Taste Brain** — Phases 13–17 (shipped code 2026-07-03) — see [milestones/v1.3-ROADMAP.md](milestones/v1.3-ROADMAP.md)
- 🚧 **v1.4 Open House** — Phases 18–23 (in progress)

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

### 🚧 v1.4 Open House (Phases 18–23) — IN PROGRESS

**Milestone Goal:** Turn Dexter from a single-community bot into a publicly-invitable, multi-tenant-robust portfolio piece — a recruiter can invite it to any server and it just works — without changing the on-demand, owner-run hosting model.

- [x] **Phase 18: Per-Guild Config Foundation & CI Gate** - Replace the hardcoded single-channel/single-owner-guild assumption with a real per-guild config seam, behind a green CI gate (completed 2026-07-09)
- [x] **Phase 19: Onboarding & Admin Setup** - New servers get a welcome nudge and a self-service `/setup`, ambient-silent until configured (completed 2026-07-10)
- [ ] **Phase 20: Owner Control Plane & Rate Observability** - The owner can list, silence, and force-leave guilds — the abuse kill-switch, with per-guild AI usage visible
- [ ] **Phase 21: Memory Scoping & Guild Data Lifecycle** - Third-party memory stops leaking across guilds and a departed guild's data gets purged (or the documented global-memory fallback ships instead)
- [ ] **Phase 22: Invite Plumbing** - A correct, least-privilege OAuth2 invite link, in-bot and public
- [ ] **Phase 23: Portfolio Surface & CI/CD** - Landing page, case-study README, CI+Pages+GHCR — the recruiter-facing deliverable

## Phase Details

### Phase 18: Per-Guild Config Foundation & CI Gate

**Goal**: Dexter's ambient/unprompted behavior is driven by real per-guild configuration instead of one hardcoded channel — the seam every later v1.4 phase reads from — and every subsequent phase executes behind a green CI gate.
**Depends on**: Nothing (first phase of v1.4; builds on the existing Phase 4 Postgres schema idiom and Phase 9 service-cache pattern)
**Requirements**: CONFIG-01, CONFIG-02, CONFIG-03, CONFIG-04, CONFIG-05, CICD-01
**Success Criteria** (what must be TRUE):

  1. When Dexter joins a brand-new guild, every ambient/unprompted surface (roasts, proactive callbacks, vision roasts, idle + startup messages) stays completely silent there — no config exists for that guild yet.
  2. The owner's existing home guild behaves exactly as before the refactor — same ambient channel, same firing behavior — because it was seeded from the existing `config.DEXTER_CHANNEL_ID`.
  3. Every ambient/unprompted surface resolves its channel through exactly one code path — `bot.py::_resolve_dexter_channel`, `cogs/events.py::_get_ambient_channel`, and the two bare-equality `message.channel.id == config.DEXTER_CHANNEL_ID` gates are gone, replaced by calls into the same consolidated resolver.
  4. Per-guild config reads never issue a live Neon round-trip during normal event handling — an in-memory cache serves them, loaded at boot and push-invalidated only when config changes.
  5. Every push and PR runs the pytest suite + lint in GitHub Actions (CICD-01), so Phases 19–23 — especially Phase 21's surgery on the scarred memory subsystem — all execute behind a green gate. The README build badge may land here or in Phase 23 alongside the rest of the README rewrite.

**Plans**: 7 plans (5 waves)

**Wave 1**

- [x] 18-01-PLAN.md — Ruff adoption + repo-wide lint/format cleanup (own atomic commit)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 18-02-PLAN.md — guild_config schema + boot helpers + conftest pgvector-codec fix
- [x] 18-03-PLAN.md — pure logic/guild_config.py decision seam (mock-free)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 18-04-PLAN.md — GuildConfigService: cache + strict ambient resolver + announce resolver

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 18-05-PLAN.md — bot.py boot wiring + home-guild seed + ambient call-site consolidation
- [x] 18-06-PLAN.md — cogs/events.py consolidation (3 voice sites + 2 on_message gates) + tests

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 18-07-PLAN.md — GitHub Actions CI gate (pytest + Ruff, pgvector service container)

### Phase 19: Onboarding & Admin Setup

**Goal**: A server admin can turn Dexter "on" for their own guild with zero manual intervention from the owner — the preventive half of safety.
**Depends on**: Phase 18
**Requirements**: ONBOARD-01, ONBOARD-02, ONBOARD-03, ONBOARD-04, ONBOARD-05
**Success Criteria** (what must be TRUE):

  1. When Dexter is invited to a new server, it posts a welcome/setup-nudge message in a safely-resolved channel — even a permission failure there never crashes the join.
  2. A server admin can run `/setup`, pick a channel from a dropdown, and ambient behavior in that guild activates immediately after — while a non-admin running `/setup` is rejected regardless of what the command's UI hint implies.
  3. A server admin can independently toggle ambient roasting and vision roasting on or off for their guild.
  4. The owner receives a notification in `ERROR_LOG_CHANNEL_ID` every time Dexter joins or is removed from any server.

**Plans**: 4 plans (3 waves)

**Wave 1**

- [x] 19-01-PLAN.md — guild_config toggle columns + RETURNING insert-if-absent + channel/toggle write helpers

**Wave 2** *(blocked on Wave 1)*

- [x] 19-02-PLAN.md — AmbientSurface surface-keyed seam (logic + service + events reaction/vision split, atomic breaking change)

**Wave 3** *(blocked on Wave 2)*

- [x] 19-03-PLAN.md — on_guild_join/remove + boot backfill + home-guild-only startup + music-roast hole
- [x] 19-04-PLAN.md — /setup admin cog (channel|roasts|vision) + /help admin section

### Phase 20: Owner Control Plane & Rate Observability

**Goal**: The owner can see every server Dexter is in and can shut off or expel a specific guild the moment it becomes an abuse problem — the reactive half of safety, enforced at one choke point instead of scattered per-cog checks.
**Depends on**: Phase 18 (config cache), Phase 19 (guild-join lifecycle to hang the blacklist re-invite check off)
**Requirements**: OWNER-01, OWNER-02, OWNER-03, OWNER-04, OWNER-05, OWNER-06, RATE-01
**Success Criteria** (what must be TRUE):

  1. The owner can list every guild Dexter currently occupies, with each guild's Gemini/AI usage (tagged by `guild_id`) visible in that same view.
  2. The owner can silence a guild — Dexter stays joined but stops firing ambient behavior and responding to commands there — with the silence taking effect on the very next event, never a stale in-flight response slipping through after the block is issued.
  3. The owner can force-leave a guild; the teardown mirrors the existing `clear_persisted()` discipline (bump `_play_generation`, clear queue + voice state) so no ghost state resurrects if that guild re-invites Dexter.
  4. A blocked guild is refused re-entry via a block-check-first in the join handler, and every owner-only command rejects a non-owner caller via an inline `is_owner()` check — never `default_permissions` alone.

**Plans**: TBD

### Phase 21: Memory Scoping & Guild Data Lifecycle

**Goal**: A third party's recalled memory stops leaking across servers, and a departed guild's data can't resurface — without assuming the ideal scoping ships, since the standing Descope Rule applies with particular force here.
**Depends on**: Phase 18 (config), Phase 20 (`on_guild_remove`/force-leave hook to hang the MEM-04 purge off)
**Requirements**: MEM-01, MEM-02, MEM-03, MEM-04, MEM-05
**Success Criteria** (what must be TRUE — MEM-01/03/05 are a hypothesis, not a contract; see Descope Rule):

  1. `/ask` continues to recall the invoker's own memory globally, completely unaffected by any guild-scoping change (MEM-02 — unconditionally shippable regardless of how the rest of this phase resolves).
  2. When Dexter leaves or is force-left from a guild, that guild's `guild_config`, `guild_queues`, `guild_jams`, and guild-scoped `user_memories` rows are purged so stale context cannot resurface on re-invite (MEM-04 — unconditionally shippable).
  3. Either: `/roast @user`, ambient roasts, and proactive callbacks recall only guild-scoped memories — with the legacy `guild_id = NULL` corpus (e.g. `daily_batch`) handled by an explicit, tested backward-compat rule, and with a regression test locking that guild-scoped search cannot corrupt cross-kind dedup or `expires_at` semantics (the Phase 13 CR-01 scar) — or: the documented zero-code fallback ("keep memory global + disclose") ships instead.
  4. Whichever path is taken, the decision and its rationale are recorded in PROJECT.md Key Decisions before the phase closes, so PORT-04 can disclose it honestly.

**Plans**: TBD

### Phase 22: Invite Plumbing

**Goal**: Anyone can invite Dexter to their own server via a correct, least-privilege invite link — with one source of truth, not hand-maintained duplicates.
**Depends on**: Phase 20 (sequenced after the control plane exists — no code dependency, but the abuse-mitigation story must be real before actively promoting the invite)
**Requirements**: INVITE-01, INVITE-02
**Success Criteria** (what must be TRUE):

  1. The invite URL requests only the specific `Permissions()` Dexter's commands actually need — no Administrator, no Manage Server/Roles.
  2. Running `/invite` returns a working invite link that successfully adds Dexter to a server the invoker manages, with `bot` + `applications.commands` scopes.
  3. The in-bot `/invite` link and the publicly-promoted link (Developer Portal / landing page) are the same URL — a single source of truth, not two hand-maintained copies that can drift.

**Plans**: TBD

### Phase 23: Portfolio Surface & CI/CD

**Goal**: A recruiter can land on Dexter's page, see it demonstrated, click "Add to Discord," and read an honest architecture case study — backed by a green CI badge and a pull-able Docker image, with zero new prod hosting.
**Depends on**: Phase 18 (CI workflow to extend with the Pages job), Phase 19 (a real `/setup` walkthrough to prove the claims), Phase 20 (kill-switch as the disclosed mitigation), Phase 22 (working invite link)
**Requirements**: PORT-01, PORT-02, PORT-03, PORT-04, CICD-02, CICD-03
**Success Criteria** (what must be TRUE):

  1. The `/site` landing page is live via GitHub Pages, with a hero, feature showcase, an embedded short demo GIF of the personality, and a working "Add to Discord" button.
  2. The README reads as an architecture case study — tagline, feature list, tech-stack badges, architecture summary, working invite link — with a CI build-status badge that reflects the actual last GitHub Actions run (the workflow itself landed in Phase 18).
  3. A merge to `main` auto-publishes the updated `/site` to GitHub Pages (CICD-02).
  4. A tagged release publishes Dexter's Docker image to GHCR, pullable by a future always-on host with zero build step (CICD-03 — no prod auto-deploy, there is no prod host this milestone).
  5. The README/landing page honestly discloses the 100-guild verification wall, the on-demand hosting caveat (Dexter is offline unless the owner is running it), the full-savage-personality + reactive-kill-switch tradeoff, and whatever memory-scoping decision Phase 21 actually shipped.

**Plans**: TBD
**UI hint**: yes

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
| 20. Owner Control Plane & Rate Observability | v1.4 | 0/TBD | Not started | - |
| 21. Memory Scoping & Guild Data Lifecycle | v1.4 | 0/TBD | Not started | - |
| 22. Invite Plumbing | v1.4 | 0/TBD | Not started | - |
| 23. Portfolio Surface & CI/CD | v1.4 | 0/TBD | Not started | - |
