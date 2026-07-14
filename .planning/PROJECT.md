# Dexter ("Dex")

## What This Is

Dexter is a sarcastic, personality-driven Discord bot. It plays music from YouTube (yt-dlp + FFmpeg), chats via Google Gemini (gemini-2.5-flash), and generates images, while tracking user behavior to roast them. The persona is lowercase, dry, accurate-first-sarcastic-second, and uses at most one emoji per message. Built as a solo-developer project with Claude as the implementer. As of v1.3 it was a complete, code-finished bot — music + AI + an "alive" unprompted-behavior layer — hardened and scaled to run on PostgreSQL behind an `AutoShardedBot`, with a durable RAG long-term memory (pgvector) including a semantic "taste brain": listening history distilled into memory that powers a smarter DJ (taste-aware auto-queue, `/discover`, `/jam suggest`), grounds `/roast` + `/ask`, is inspectable/erasable via `/memory`, and surfaces through proactive callbacks and `gemini-2.5-flash` vision roasts. **As of v1.4 "Open House" it is a publicly-invitable, multi-tenant-robust portfolio piece:** the hardcoded single-community assumption is gone — per-guild configuration (`guild_config` + a boot-loaded cache), a `/setup` onboarding flow so any admin can turn Dexter on for their own server, an owner control plane / kill-switch (list / silence / force-leave / blocklist, enforced at one choke point), hybrid guild-scoped memory that stops third-party recall leaking between servers, a least-privilege OAuth2 `/invite`, and a recruiter-facing portfolio surface (landing page + architecture-case-study README) — all behind a green CI gate. The on-demand, owner-run hosting model is unchanged.

## Core Value

A sarcastic, personality-driven music + AI Discord bot that runs reliably 24/7 — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.

## Current State

**Shipped: v1.0 MVP (2026-06-12)** — Phases 1, 2, 2.5, 3, 4. All 45 v1 requirements satisfied at the code/structural level.

**Shipped (code): v1.1 "Live & Lethal" (2026-06-26)** — Phases 5–8, 14 plans, 27 tasks. All 28 v1.1 requirements met at the code level; 24/28 also live-validated. Delivered:
- **Phase 5 (Ship It Live):** deploy substrate re-targeted Oracle A1 → **Koyeb WEB + Neon serverless Postgres** — Neon-tuned asyncpg pool, `sanitize_database_url`, aiohttp `/health`, de-Oracle'd Dockerfile, stdout logging, `docs/DEPLOY-KOYEB.md`, 22-check live-UAT runbook.
- **Phase 6 (Speed & Caching):** generation-guarded next-track prefetch (zero inter-song gap), opus-copy codec-path logging + SponsorBlock, a Postgres `resolution_cache` (survives restart, URL-bypass), download-timeout→stream fallback, LFU eviction protecting in-use tracks, `PerfMetrics` in `/stats`.
- **Phase 7 (Player UX & Filters):** persistent 5-button now-playing view, `/seek` `/previous` `/jump`, four `/filter` presets (opus-passthrough preserved for non-filtered tracks), `user_favorites` + JSONB `user_playlists`.
- **Phase 8 (Social & Ops):** `/roast @user`, per-guild `/leaderboard`, owner-only `/stats`, degraded-but-always-200 `/health`, central `total_errors` tracking.

**The 24/7 live deploy is PARKED.** YouTube blocks datacenter IPs → free cloud hosting is non-viable, and there is no always-on residential host yet. The bot runs on the **user's PC (residential IP) on demand against Neon Singapore**; Phases 6/7/8 were live-verified that way. The 4 open DEPLOY requirements + remaining live-UAT/verification items (9 total) are deferred until a Pi / always-on residential host is acquired — see STATE.md Deferred Items.

**Shipped (code): v1.2 "Sharper & Smarter" (2026-06-30)** — Phases 9–12, 19 plans, 43 tasks. All 21 v1.2 requirements met at the code level. Delivered:
- **Phase 9 (Reliability & Ops Hardening):** truthful `/health` (degraded-503 on MusicCog load failure, `_ready_done`-guarded), fire-and-forget failure surfacing via `utils/tasks.py` `make_task`, un-wedgeable `on_ready` watchdog + `_sync_retry_active`-guarded startup-sync recovery, config-driven DB query timeouts, bounded YouTube search/extract self-heal.
- **Phase 10 (Critical-Path Test Coverage):** extracted the untested decision logic into pure `logic/` modules (`playback.py` TrackEndAction + five fns, `health.py`, `roasts.py`, later `autoqueue.py`) locked by ~83 mock-free unit tests with three named scar regressions; full-suite-green + clean-boot regression gate.
- **Phase 11 (RAG Long-Term Memory):** `pgvector` on Neon + `gemini-embedding-001` @ 768d behind a separate 60 RPM limiter; full read (recall/rerank/floor) + write (remember/dedup/cap-evict) halves, sensitivity/PII + numbers-from-SQL accuracy firewall, callback roasts at four surfaces, daily decay sweep — **zero new infrastructure**.
- **Phase 12 (Richer Music/UX):** per-server `/jam` shared playlists, `/skips` analytics, LRCLIB third lyrics fallback, token-set auto-queue hallucination validation.

The Phase 09/11 live-runtime UAT/verification tail (4 items) is deferred behind the same parked host — see STATE.md Deferred Items.

**Shipped (code): v1.3 "Taste Brain" (2026-07-03)** — Phases 13–17, 18 plans, 42 tasks. All 15 v1.3 requirements met at the code level. Delivered:
- **Phase 13 (Semantic Music Memory):** a number-free `taste_episode` memory kind distilled from `song_history` onto the existing `user_memories` pgvector store (no schema fork), with its own below-floor salience (0.4) + 30-day decay tier (`MEMORY_DECAY_DAYS_BY_KIND`) and self-refresh-on-dedup (D-05); a dedicated daily `taste_distill_batch` @ 05:00 UTC. **Zero new tables.**
- **Phase 14 (Smarter Music Brain):** taste-aware auto-queue (recently-skipped artists as a negative hint + an independent hard post-filter, blended with an unattributed room-taste positive signal), `/discover` (100%-SQL invoker-anchored co-occurrence adjacency, multi-user-safe), `/jam suggest` (validated generative additions) — all read-only over taste + live SQL, byte-identical when signals are empty.
- **Phase 15 (RAG Reach):** `recall()` grounds `/roast @user` (target-scoped) and `/ask` (D-01 removed the callback gate from these two only; ambient surfaces keep it); new `cogs/memory.py` `/memory view` (verbatim, ephemeral, paginated) + `/memory forget` (verified hard-delete of rows **and** embeddings — the trust escape hatch).
- **Phase 16 (Proactive Memory Callbacks):** a third, rarest ambient cadence volunteering a chat-anchored memory unprompted (`PROACTIVE_CALLBACK_CHANCE=0.10` + daily cap 1), reply-anchored with mentions suppressed; per-user opt-out via `/memory callbacks on|off` (`proactive_opt_out` column, zero `user_memories` touched); `pre_recalled_memories` bypass keeps ambient cadence byte-identical.
- **Phase 17 (Vision / Multimodal Roasting):** a fourth independent cadence — cadence-gated (`VISION_ROAST_CHANCE=0.12` + per-user cooldown, priority-2) image roasts via `gemini-2.5-flash` vision, before-download mime/size gate, safety-block = silent skip (never a fallback template), plus an explicit `safety_settings` retrofit across all three user-content `generate_content` sites.

Every phase passed verification (4/4 or 10/10 code-level) and code review; the goal-blocking Phase 16 WR-03 (content-free recall anchor) and the Phase 17 vision-input guards were fixed before close. Suite green at 848 pass / 108 skip / 0 fail. The Phase 14–17 live-Discord UAT tail (plus the carried v1.1/v1.2 checks) is deferred behind the same parked residential host — 24 items acknowledged at close, all `human_needed`, zero code gaps (see STATE.md Deferred Items).

**Shipped (code): v1.4 "Open House" (2026-07-14)** — Phases 18–23, 32 plans, all 6 phases code-complete. **28/31 v1.4 requirements met at the code level; 3 deferred as blocked-on-human** (PORT-02 demo-GIF Dexter lines, CICD-02 GitHub Pages toggle, CICD-03 GHCR flip — manual GitHub-UI / live-bot steps, no code work). All CONFIG-01…05 + CICD-01 (Phase 18), ONBOARD-01…05 (Phase 19), OWNER-01…06 + RATE-01 (Phase 20), MEM-01…05 (Phase 21), INVITE-01/02 (Phase 22), and PORT-01/03/04 (Phase 23) validated at the code level. Delivered:
- **Phase 18 (Per-Guild Config Foundation & CI Gate):** the hardcoded single-channel assumption is gone. A `guild_config` table + pure `logic/guild_config.py` decision seam + cache-owning `services/guild_config.py::GuildConfigService` (loaded once at boot, fail-closed, zero per-event round-trips) now drive every ambient surface. `bot.py::_resolve_dexter_channel` and `cogs/events.py::_get_ambient_channel` are deleted and both bare-equality `DEXTER_CHANNEL_ID` gates are replaced — the env var no longer appears anywhere under `cogs/`, demoted to a one-time home-guild bootstrap seed (`ON CONFLICT DO NOTHING`). **An unconfigured guild is structurally silent.** Ruff adopted repo-wide as a blocking lint/format gate, and `.github/workflows/ci.yml` runs ruff + pytest against a `pgvector/pgvector:pg16` service container on every push and PR, with zero repo secrets.
- **Phase 19 (Onboarding & Admin Setup):** a server admin can turn Dexter "on" for their own guild with zero owner intervention. Two per-guild toggle columns (`ambient_roasts_enabled`, `vision_roasts_enabled`) + race-safe DB write helpers (incl. a `RETURNING` insert-if-absent signal and a single-guild `get_guild_config` fetch); a **required keyword-only `AmbientSurface`** threaded through the pure/service seam so a surface must name itself to fire and per-guild toggles can silence ROAST/PRESENCE vs VISION independently (also closed the CONFIG-04 emoji-reaction hole); guild-lifecycle glue (`on_guild_join`/`on_guild_remove`, boot backfill that welcomes offline-invited guilds exactly once keyed on the DB insert, home-guild-only startup, owner join/leave notices); and a new `cogs/admin.py` `/setup` group (`channel`/`roasts`/`vision`) with an inline `manage_guild` gate + send/view permission validation + `/help` admin section. Code review found 1 blocker (cache-consistency on re-invite-after-kick) + 4 warnings — all fixed and independently re-verified. Suite 936 passed / 0 failed (1054 against a live pgvector container). 6 live-Discord UAT items parked per standing precedent.
- **Phase 20 (Owner Control Plane & Rate Observability):** the owner can see every server Dexter is in and shut off or expel a specific guild the moment it becomes an abuse problem — enforced at ONE choke point, not scattered per-cog checks. A dedicated `guild_blocklist` table (own table, D-01 — so Phase 21's config purge stays a clean `DELETE` with no "except if blocked" carve-out; `guild_config.is_blocked` is now dead/superseded) + blocklist CRUD + first reader/writer of `guild_config.silenced`; a pure `silenced` early-return branch in `decide_ambient_channel` (every ambient surface goes silent for free) + a `decide_interaction_allowed` predicate; a `DexterCommandTree.interaction_check` single choke point (block/silence enforced for every slash command, owner-bypassed) + `on_guild_join` block-check-first re-invite refusal; `GuildConfigService` extended with an O(1) `_blocked` set + silence reads (cache-only, zero Neon on the hot path) + write-then-invalidate setters; TOCTOU pre-send re-checks closing the silence-mid-flight window on the reply-after-Gemini proactive/vision paths; per-guild AI-usage observability (`guild_id` tagged + counted on `chat()`/`generate_image()`, `embed()` untagged — observability, not a quota); and a `/guilds` owner group (list/silence/unsilence/leave/block/unblock) rendering per-guild fleet rows sorted by usage. Code review found 0 blockers + 2 warnings (WR-01 latent autocomplete-interaction guard, WR-02 refusal-copy conflation) + 4 info — none goal-blocking. Suite 982 passed / 0 failed. 4 live-Discord UAT items parked per standing precedent.
- **Phase 21 (Memory Scoping & Guild Data Lifecycle):** a third party's memory stops leaking across servers, and a departed guild's data is purged. The `user_memories` ANN read path (`recall()`/`search_memories()`) gained an **explicit per-call-site `guild_scoped=True` opt-in** that adds a `(guild_id = $N OR guild_id IS NULL)` clause — every unprompted/ambient surface (`/roast`, ambient roasts, proactive callbacks, the music-command callback, the auto-queue taste blend) opts in, while `/ask` stays deliberately global (MEM-02); the legacy `guild_id IS NULL` corpus stays globally recallable. The write path (dedup, cap-eviction) is untouched — still fully `user_id`-scoped (CR-13-01 scar not reopened). A `database.purge_guild_data(pool, guild_id=...)` hard-deletes a departed guild's rows from exactly four tables (`guild_config`, `guild_queues`, `guild_jams`, guild-stamped `user_memories`) in one transaction from `bot.py::on_guild_remove` (best-effort, never crashes removal); `guild_blocklist` is excluded by design so a kicked abuser's block survives (the Phase 20 D-01 dividend). Four-table DELETE list is hardcoded SQL literals (reviewability is the control, T-21-03).
- **Phase 22 (Invite Plumbing):** anyone can invite Dexter to their own server via a correct, least-privilege OAuth2 link with ONE source of truth. A `logic/invite.py::build_invite_url()` (the sole invite-URL constructor, the one documented `import discord` exception in `logic/`) wraps `discord.utils.oauth_url()` over a config bitfield (`INVITE_PERMISSIONS_VALUE=309240908864` — ten named permissions, negatively asserted free of Administrator/Manage Guild/Manage Roles); a public `/invite` slash command (`cogs/invite.py`) returns an embed + "Add to Discord" link button built only from that function, works in DMs, is listed in `/help`, registered at both `bot.py` load sites, and (post-review) prefers `bot.application_id` so forks emit their OWN client id + carries a 5s cooldown; and a CI drift-guard (`tests/test_invite_drift_guard.py`) that fails the build if any git-tracked doc's invite URL drifts from `build_invite_url()`'s output, with a positive control against a false green. Code review found 0 blockers + 3 warnings (WR-01 fork client-id fallback, WR-02 unresolved-client-id guard, WR-03 missing cooldown) + 1 info — WR-01/02/03 fixed before close (IN-01 drift-guard allowlist deferred to Phase 23). Suite 1036 passed / 0 failed. 4 live-Discord OAuth2 UAT items parked per standing precedent.
- **Phase 23 (Portfolio Surface & CI/CD):** the recruiter-facing deliverable. A static `/site` landing page (hero, feature showcase, "Add to Discord" button wired to the same `build_invite_url()` source of truth), the README rewritten as an architecture case study (tagline, feature list, tech-stack badges, architecture summary, CI status badge, working invite link), and honest scope boundaries documented rather than hidden (the 100-guild verification wall, the on-demand hosting caveat, the full-savage-personality + reactive-kill-switch tradeoff, the hybrid memory-scoping decision — PORT-04). CI/CD scaffolding shipped: a `pages.yml` GitHub Pages deploy workflow and a `release.yml` GHCR image-publish workflow on `v*` tags, plus a `site_drift_guard` test extending the Phase 22 pattern. **Three requirements deliberately deferred as blocked-on-human** (tracked in `23-HUMAN-UAT.md`): PORT-02 needs two verbatim real Dexter personality lines from a live bot (placeholder tokens intact — no invented lines), CICD-02 needs the owner to enable GitHub Pages (Settings→Pages), CICD-03 needs the GHCR package-visibility flip + first `v*` tag run. Verifier confirmed 8/8 code truths; suite green at HEAD.

**CI is green on `main`** ([run 29056570511](https://github.com/jadrianports/dexter/actions/runs/29056570511) — 1017 passed, 0 skipped). This is the first milestone where the ~111 live-DB tests actually execute rather than skip: the gate's first run caught a sentinel collision that would have made CI silently skip them, plus two latent pre-existing bugs invisible on a long-uptime dev box (an import-time `sys.exit` in `bot.py`, and a `0.0`-vs-monotonic-clock sentinel that suppressed vision roasts for 10 minutes and yt-dlp self-heal for an hour after any reboot). All fixed and locked by `tests/test_fresh_boot_regressions.py`. Phases 19–23 now execute behind a real green gate. Phase 18's 3 remaining live-Discord UAT items are deferred behind the same parked host.

## Current Milestone: none — v1.4 shipped, next milestone unplanned

**v1.4 "Open House" closed 2026-07-14** (tag `v1.4`). No milestone is currently active. Next step is `/gsd-new-milestone` (questioning → research → requirements → roadmap). Candidate directions for the next cycle:

- **Resume the parked 24/7 deploy** (DEPLOY-F1) — host-gated; closes DEPLOY-02/03/05/08 + the entire live-UAT tail once an always-on residential host (Pi) exists. This is the single biggest lever — it converts ~33 deferred `human_needed` items into runnable checks.
- **Salience reinforcement** (MEM-F1) — surfaced/hit memories gain durability (deferred out of v1.3).
- **Vision → RAG memory** (MEM-F2) — persist a distilled fact from a vision roast.
- **Full guild-scoped recall / opt-in cross-guild sharing** (MEM-F3) — revisit if Dexter outgrows modest scale.
- **Discord bot verification + privileged-intent approval** (SCALE-F2) — required past 100 guilds / 10k unique users; only if scale demand appears.

> **Also carried into the next milestone:** the 3 blocked-on-human v1.4 requirements (PORT-02 demo-GIF Dexter lines, CICD-02 GitHub Pages toggle, CICD-03 GHCR flip) — no code work, just owner-performed GitHub/live-bot steps. See STATE.md Deferred Items.

<details>
<summary>Previous: v1.4 "Open House" milestone framing (archived — shipped 2026-07-14)</summary>

**Goal:** Turn Dexter from a single-community bot into a publicly-invitable, multi-tenant-robust portfolio piece — a recruiter can invite it to any server and it just works — without changing the on-demand, owner-run hosting model (music keeps working on the residential IP; the bot responds when the owner has it running).

**Target features:** multi-tenancy / fresh-server UX (per-guild config, join onboarding, admin `/setup`); owner control plane / kill-switch (list / silence / force-leave); invite plumbing (least-privilege OAuth2 `/invite`); portfolio surface (landing page + architecture-case-study README + CI/CD).

**Key context / decisions:** hosting model unchanged (owner's PC, residential IP, on demand — sidesteps the datacenter-IP block); scale target modest (invitable & robust, NOT 100+ servers or bot verification); personality stays full-savage everywhere, with the owner kill-switch as the stated abuse mitigation.

</details>

<details>
<summary>Previous: v1.3 "Taste Brain" milestone framing (archived — shipped 2026-07-03)</summary>

**Goal:** Turn Dexter's listening history into semantic long-term memory that powers a genuinely good DJ (smarter auto-queue, discovery, generative jams), memory-aware `/roast` + `/ask`, and proactive callbacks — plus vision/multimodal roasting — deepening the v1.2 RAG foundation on existing infra (`pgvector` + the separate 60 RPM embed limiter), at zero new cost. Continued phase numbering at Phase 13.

**Target features:** semantic music memory (foundation `taste_episode` kind), smarter music brain (taste-aware auto-queue + `/discover` + `/jam suggest`), RAG reach (`/roast`+`/ask` grounding + `/memory` view/forget), proactive callbacks, vision/multimodal roasting.

**Explicitly out of v1.3:** salience reinforcement (→ v1.4), `/setavatar` (avatar set manually via the Developer Portal), and the parked 24/7 deploy (host-gated).

</details>

<details>
<summary>Previous: v1.2 "Sharper & Smarter" milestone framing (archived — shipped 2026-06-30)</summary>

**Goal:** Harden Dexter into a trustworthy 24/7-ready bot and give it a real memory — fix the reliability gaps, cover the untested critical paths, then make it smarter (long-term RAG memory) and richer (music/UX polish). Continued phase numbering at Phase 9.

**Target features:**
- **Reliability & ops hardening** — health endpoint can no longer report "ok" while degraded, fire-and-forget tasks log failures, `first_run`/`on_ready` sync no longer hangs silently, DB query timeouts, search/extract retry/self-heal.
- **Critical-path test coverage** — the untested MusicCog playback flow, OpsCog/health metrics, and EventsCog ambient-roast logic get real tests.
- **RAG long-term memory** — `pgvector` on the existing Neon Postgres + Gemini `gemini-embedding-001` @ 768d, so Dex remembers across restarts and lands callback roasts referencing real history. **Zero new infrastructure or monthly cost.** Includes a research spike.
- **Richer music/UX** — per-server playlists, skip-rate analytics command, third lyrics fallback, auto-queue hallucination validation.

</details>

<details>
<summary>Previous: v1.1 "Live & Lethal" milestone framing (archived)</summary>

**Goal:** Take Dexter from code-complete-on-a-laptop to running 24/7 — fast, polished, and genuinely fun — by deploying it for real, killing playback latency, and surfacing the control, filter, and roast features that make it a joy to use.

Sequenced deploy-first so every speed gain is measured against live numbers. The one tradeoff resolved in the roadmap: `/filter` forces a re-encode, mutually exclusive with opus-copy → opus-copy by default, transcode only when a filter is active per-track. **Reality check:** the deploy-first sequencing was inverted in practice — the live deploy parked behind the YouTube IP block, so speed/UX/social phases shipped and were verified against the on-demand PC run env instead.

</details>

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ Music playback: `/play` (search + URL + playlist), `/skip`, `/pause`, `/resume`, `/stop`, `/queue`, `/shuffle`, `/loop`, `/nowplaying`, `/replay`, `/help` — v1.0 (Phase 1)
- ✓ Per-server queue model with loop modes, generation-counter race prevention, cache-first audio with stream fallback — v1.0 (Phase 1)
- ✓ `/ask` with Gemini, 10-message context buffer, mood system, user-taste injection, seasonal awareness — v1.0 (Phase 2)
- ✓ `/imagine` with daily cap, AI auto-queue, "ignored" memory, global Gemini rate limiter, Discord error-log channel — v1.0 (Phase 2)
- ✓ Production-honest hardening: unsilenced exception handlers, WAL + busy_timeout, robust auto-queue JSON parse, FFmpeg orphan cleanup, yt-dlp self-heal — v1.0 (Phase 2.5)
- ✓ Unprompted "alive" behavior: voice-join/leave roasts, late-night roasts, repeat-song roasts, emoji reactions, expanded seasonal awareness — v1.0 (Phase 3)
- ✓ Status rotation, startup message, idle-loneliness, streak tracking + milestone roasts, `/lyrics` (Genius + AZLyrics), `/history` — v1.0 (Phase 3)
- ✓ Scale: multi-server hardening, SQLite→PostgreSQL, `AutoShardedBot`, queue persistence, Oracle Cloud A1 hosting decision — v1.0 (Phase 4)
- ✓ Deploy substrate re-targeted Oracle A1 → Koyeb WEB + Neon serverless Postgres: Neon-tuned asyncpg pool, `sanitize_database_url`, aiohttp `/health`, de-Oracle'd Dockerfile, stdout logging, `docs/DEPLOY-KOYEB.md`, 22-check runbook — v1.1 (Phase 5, code; 24/7 deploy parked)
- ✓ Speed & caching: next-track prefetch (zero gap), opus-copy codec path + SponsorBlock, Postgres resolution cache, download-timeout→stream fallback, LFU eviction, `PerfMetrics` in `/stats` — v1.1 (Phase 6)
- ✓ Player UX & filters: persistent control-button view, `/seek` `/previous` `/jump`, four `/filter` presets (opus-passthrough preserved), favorites + named playlists — v1.1 (Phase 7)
- ✓ Social & ops: `/roast @user`, per-guild `/leaderboard`, owner-only `/stats`, `/health` endpoint, Gemini RPM headroom + `total_errors` visibility — v1.1 (Phase 8)
- ✓ Reliability & ops hardening: truthful `/health` (degraded-503, `_ready_done`-guarded), fire-and-forget failure surfacing via `make_task`, un-wedgeable `on_ready` watchdog + startup-sync recovery, config-driven DB query timeouts, bounded YouTube search/extract self-heal — v1.2 (Phase 9; live-runtime UAT in 09-HUMAN-UAT.md)
- ✓ Critical-path test coverage: playback/health/roast/auto-queue decision logic extracted to pure `logic/` modules with ~83 mock-free unit tests + three named scar regressions; full-suite-green + clean-boot regression gate — v1.2 (Phase 10)
- ✓ RAG long-term memory: `pgvector` on Neon + `gemini-embedding-001` @ 768d, scoped cosine recall with rerank/dedup, constrained distillation with sensitivity/number safety gates, prompt injection at four roast surfaces, per-user cap + daily decay sweep — v1.2 (Phase 11; 3 live-runtime UAT items tracked in 11-HUMAN-UAT.md)
- ✓ Richer music/UX: per-server `/jam` shared playlists (distinct from global favorites), `/skips` analytics, LRCLIB third lyrics fallback, token-set auto-queue hallucination validation — v1.2 (Phase 12)
- ✓ Semantic music memory: number-free `taste_episode` kind on the existing pgvector store, own salience/decay tier + self-refresh-on-dedup, dedicated `taste_distill_batch` @ 05:00 UTC — zero new tables — v1.3 (Phase 13; TASTE-01/02/03)
- ✓ Smarter music brain: taste-aware auto-queue (recently-skipped negative hint + hard post-filter + room-taste blend), `/discover` SQL co-occurrence adjacency, `/jam suggest` validated generative additions — v1.3 (Phase 14; BRAIN-01/02/03; live-runtime UAT in 14-HUMAN-UAT.md)
- ✓ RAG reach: `recall()` grounds `/roast @user` (target-scoped) + `/ask`, `/memory view` (verbatim, ephemeral) + `/memory forget` (verified hard-delete of rows + embeddings) — v1.3 (Phase 15; RAG-01/02/03/04; live-runtime UAT in 15-HUMAN-UAT.md)
- ✓ Proactive memory callbacks: rarest ambient cadence volunteering a chat-anchored memory unprompted (chance 0.10 + daily cap 1), per-user `proactive_opt_out` via `/memory callbacks` — v1.3 (Phase 16; PROACT-01/02; live-runtime UAT in 16-HUMAN-UAT.md)
- ✓ Vision / multimodal roasting: cadence-gated image roasts via `gemini-2.5-flash` (before-download mime/size gate, silent-skip on safety block), `safety_settings` retrofit across all 3 generate_content sites — v1.3 (Phase 17; VIS-01/02/03; live-runtime UAT in 17-HUMAN-UAT.md)
- ✓ Per-guild config foundation & CI gate: `guild_config` table + pure `logic/guild_config.py` seam + boot-loaded `GuildConfigService` cache driving every ambient surface (hardcoded `DEXTER_CHANNEL_ID` demoted to a home-guild bootstrap seed), unconfigured guilds structurally silent; ruff + pytest CI against a `pgvector/pgvector:pg16` service container on every push/PR — v1.4 (Phase 18; CONFIG-01…05, CICD-01)
- ✓ Onboarding & admin setup: `/setup` group (channel/roasts/vision) with inline `manage_guild` gate + permission validation, required keyword-only `AmbientSurface` threading (a surface must name itself to fire), independent per-guild roast/vision toggles, guild-lifecycle glue (join welcome once, home-guild startup, owner join/leave notices) — v1.4 (Phase 19; ONBOARD-01…05; live-runtime UAT in 19-HUMAN-UAT.md)
- ✓ Owner control plane & rate observability: `guild_blocklist` table + `/guilds` owner group (list/silence/unsilence/leave/block/unblock), single `DexterCommandTree.interaction_check` choke point + block-check-first re-invite refusal, cache-only silence/block reads with TOCTOU pre-send re-checks, per-guild Gemini usage tagging + counters — v1.4 (Phase 20; OWNER-01…06, RATE-01; live-runtime UAT in 20-HUMAN-UAT.md)
- ✓ Memory scoping & guild data lifecycle: explicit per-call-site `guild_scoped=True` opt-in narrowing ANN recall to `(guild_id = $N OR guild_id IS NULL)` for unprompted surfaces (`/ask` stays global/self-scoped), legacy NULL corpus grandfathered, `purge_guild_data` four-table hard-delete on `on_guild_remove` (blocklist excluded by design), write path untouched — v1.4 (Phase 21; MEM-01…05; live-runtime UAT in 21-HUMAN-UAT.md)
- ✓ Invite plumbing: `logic/invite.py::build_invite_url()` sole least-privilege OAuth2 constructor (bitfield free of Administrator/Manage Guild/Manage Roles), public `/invite` command + CI drift-guard failing the build on any doc URL drift — v1.4 (Phase 22; INVITE-01/02; live-runtime UAT in 22-HUMAN-UAT.md)
- ✓ Portfolio surface: static `/site` landing page (hero + feature showcase + "Add to Discord" from the same invite source of truth), README rewritten as an architecture case study with CI badge + working invite link, honest scope-boundary documentation — v1.4 (Phase 23; PORT-01/03/04; PORT-02 + CICD-02/03 deferred blocked-on-human)

> Phase 3 & 4 items (v1.0) and Phase 5–6 live checks (v1.1), plus the Phase 09/11 live-runtime checks (v1.2) and the Phase 14–22 live-Discord checks (v1.3/v1.4), are code-complete and statically/locally verified; their live-deploy/live-Discord UAT is carried forward as the deployment checklist (STATE.md Deferred Items), not as open scope. Phases 6/7/8 were live-verified on the user's PC + Neon; v1.4 is the first milestone whose ~111 live-DB tests actually execute in CI.

### Active

<!-- No active milestone — v1.4 shipped 2026-07-14. Next scope defined by /gsd-new-milestone (fresh REQUIREMENTS.md). -->

**No active milestone.** v1.4 "Open House" shipped; requirements archived to `milestones/v1.4-REQUIREMENTS.md`. Run `/gsd-new-milestone` to define the next scope.

Blocked-on-human v1.4 tail (no code work — owner-performed GitHub/live-bot steps, carried until done):
- [ ] PORT-02 — embed two verbatim real Dexter personality lines in the demo GIF (needs live bot; placeholder tokens intact)
- [ ] CICD-02 — enable GitHub Pages (Settings→Pages→Source=GitHub Actions) + first `pages.yml` run
- [ ] CICD-03 — GHCR package-visibility flip + first `v*` tag `release.yml` run

Candidate directions for the next milestone (carried, not committed):
- [ ] Resume the parked 24/7 live deploy once an always-on residential host exists → closes DEPLOY-02/03/05/08 + the entire live-UAT tail (Phases 03–06 v1.1, Phase 09/11 v1.2, Phases 14–22 v1.3/v1.4)
- [ ] Salience reinforcement (MEM-F1) — surfaced/hit memories gain durability
- [ ] Vision → RAG memory (MEM-F2) — persist a distilled fact from a vision roast
- [ ] Discord bot verification + privileged-intent approval (SCALE-F2) — only past 100 guilds / 10k users

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- `/volume` command / `PCMVolumeTransformer` — Discord's per-user volume slider covers it; opus passthrough keeps CPU low
- Prefix commands / hybrid commands — pure `app_commands` slash commands only, by design
- Spotify/Apple Music as audio sources — YouTube via yt-dlp is the single source of truth
- Web config dashboard — "maybe" since Phase 4, never committed; `/stats` in-Discord covers the owner need. Deferred to a future milestone, not killed.
- Datacenter/cloud hosting for the 24/7 deploy — YouTube blocks datacenter IPs, so free cloud is non-viable. Resolution is a residential always-on host (Pi), not a cloud provider.

## Context

- **v1.0–v1.4 are code-complete and shipped to `main`** (tags `v1.0`…`v1.4`). Layered cog → service → model architecture, plus the pure `logic/` decision seam (Phase 10+). Services wired in `bot.py`, attached as bot attributes; cogs access via `self.bot`. CLAUDE.md is the north-star feature spec; `.planning/codebase/` reflects the built state. v1.4 added ~45k LOC of diff across 274 files (incl. `.planning/` docs + the new `/site`, `.github/workflows/`, `cogs/admin.py`, `cogs/invite.py`, `services/guild_config.py`, `logic/guild_config.py`/`invite.py`) over 231 commits, 2026-07-10 → 2026-07-14. Test suite runs green in CI against a `pgvector/pgvector:pg16` service container (~1017 pass, ~111 live-DB tests now actually execute rather than skip).
- **The bot runs on the user's PC (residential IP) on demand against Neon Singapore.** Phases 6/7/8 were live-verified that way. A true 24/7 deploy is parked: YouTube blocks datacenter IPs (free cloud non-viable) and there is no always-on residential host yet. The remaining live-UAT/verification tail (33 items across Phases 03–06/09/11/14–22, plus 3 blocked-on-human v1.4 GitHub-UI/live-bot steps) is deferred to that future host — see STATE.md Deferred Items.
- **Personality is the product.** Lowercase, dry, one-emoji-max. Accuracy first, sarcasm second; sarcasm dials back for serious/emotional questions. Mood shifts with daily command count; seasonal context injected into the Gemini system prompt. All personality output is Gemini-first with a guaranteed template fallback.
- **Testing convention:** pure logic gets TDD (`tests/`); Discord/process code (cogs, `bot.py`) is untested-by-design, verified by structural review + clean local boot. Regression gate: full suite green + clean boot with no new silent failures in `dexter.log`.
- **Git convention:** as of 2026-06-19 the user allows Claude to perform git operations (commit / merge / push) — the earlier hands-off default is reversed. Still confirm before destructive/irreversible ops.

## Constraints

- **Tech stack**: Python 3.11+, discord.py (+ davey for DAVE voice encryption), yt-dlp + FFmpeg (opus 192kbps), **PostgreSQL via asyncpg** (migrated from SQLite/aiosqlite in Phase 4), Google Gemini via the `google-genai` SDK (NOT the deprecated `google-generativeai`) — fixed per CLAUDE.md, do not deviate
- **AI model**: `GEMINI_MODEL = "gemini-2.5-flash"` for chat; all AI features share a single global 15 RPM rate limiter (`GEMINI_RPM_LIMIT = 15`), priority 1 = user commands (wait ≤60s), priority 2 = background/auto-queue (reject if wait >10s)
- **Image model**: `gemini-2.5-flash-image` with `response_modalities=["IMAGE"]`; `MAX_IMAGES_PER_USER_PER_DAY = 10`
- **Music limits**: `MAX_SONG_DURATION_SECONDS = 900` (reject longer), reject livestreams, `MAX_PLAYLIST_IMPORT = 50` (truncate + inform), `IDLE_TIMEOUT_SECONDS = 600` auto-leave, `AUDIO_CACHE_MAX_MB = 512` (LFU eviction by `song_history` play count, protects in-use tracks, hourly cleanup — Phase 6/K-07; was 2048-by-atime pre-v1.1), `MAX_QUEUE_SIZE_PER_GUILD = 500` (cap enforced in `MusicQueue.add()`)
- **Reliability**: explicit FFmpeg/voice cleanup on skip/stop/error/leave to avoid orphans; yt-dlp self-heals (daily 04:00 update + on-failure update→retry throttled ≤once/hour→stream fallback→error)
- **Discord interaction timeout**: must `defer()` or respond within 3s, then do async work via `asyncio.create_task()` / `interaction.followup`
- **Hosting**: re-targeted Oracle A1 → **Koyeb WEB + Neon serverless Postgres** (v1.1, Phase 5) → **24/7 deploy PARKED** (YouTube blocks datacenter IPs; free cloud non-viable). Current run env: **user's PC (residential IP) on demand → Neon Singapore**. Resume the 24/7 deploy on an always-on residential host (Pi). Code is substrate-agnostic (Dockerfile + `DATABASE_URL`), so the host swap is config-only.

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Image-gen model = `gemini-2.5-flash-image` (resolved during ingest, not ADR-locked) | Two equal-precedence SPECs diverged; tie broken by ground truth — shipped `config.py:36` | ✓ Good (matches shipped code) |
| Layered cog → service → model architecture, services wired in `bot.py` | Decoupling, testability of pure logic, "grow into the spec" | ✓ Good |
| `current_index` queue (no popping) instead of pop-on-play | Enables `/replay`, `/previous`, loop wrap, `/history` | ✓ Good |
| Global Gemini rate limiter with priority tiers (sliding-window deque) | All AI features share one 15 RPM budget; user commands must not starve | ✓ Good |
| Phase 2.5 parks live-concurrency bugs rather than fixing blind | Bot booted locally only; fixes must be verifiable by inspection + local boot | ✓ Good |
| Hosting → Oracle Cloud Always Free A1 ARM (Phase 4) | Always-free ARM capacity fits a single-community bot; Docker Compose keeps Hetzner portability open | ✓ Resolved — ⚠ monitor reclamation/termination risk in production |
| Persistence → PostgreSQL via asyncpg 0.31.0 (Phase 4) | SQLite sufficient for v1–v3; multi-server scale needs real concurrency + durable queue persistence; raw `CREATE TABLE IF NOT EXISTS` over Alembic for a start-fresh schema | ✓ Resolved (static); live round-trip pending deploy |
| Queue cap enforced in `MusicQueue.add()` (Phase 4) | Guard at the source covers the playlist loop and every add path automatically | ✓ Good |
| Gemini-first personality output with guaranteed template fallback (Phase 3) | Never let rate limits or API errors block a roast/response | ✓ Good |
| Re-target deploy Oracle A1 → Koyeb WEB + Neon serverless Postgres (Phase 5) | Oracle reclamation risk + no card; Koyeb free WEB + Neon free fit a single-community bot | ⚠️ Revisit — superseded by the parked-deploy decision below |
| **Park the 24/7 live deploy; run on the user's PC (residential IP) → Neon on demand (v1.1)** | YouTube blocks datacenter IPs, breaking yt-dlp from any free cloud host; no card, no Pi yet | — Pending — resume on an always-on residential host |
| Neon-tuned asyncpg pool: `ssl='require'`, `statement_cache_size=0`, 240s lifetime (Phase 5) | Survive Neon's scale-to-zero without SSL-EOF / prepared-statement crashes through PgBouncer | ✓ Good |
| Generation-guarded fire-and-forget next-track prefetch (Phase 6) | Kill the inter-song silence gap without racing skip/stop teardown | ✓ Good |
| opus-copy by default, transcode only when a `/filter` is active per-track (Phase 6/7) | Resolve the filter-vs-opus-copy tradeoff — keep the fast path for the common case | ✓ Good |
| LFU cache eviction keyed on `song_history` play counts, with `protected_video_ids` (Phase 6) | `atime` is unreliable on `noatime` mounts; never evict an in-use track | ✓ Good |
| Persistent views via `timeout=None` + stable `custom_id`s registered in `setup_hook` (Phase 7) | Correct discord.py pattern so buttons survive restarts | ✓ Good |
| Shared `_do_*` helpers route slash command + button through one path (Phase 7) | Eliminate divergence between the two invocation surfaces | ✓ Good |
| Truthful `/health` returns degraded-503, guarded by `_ready_done` (Phase 9) | A health endpoint that reports "ok" while broken is worse than none; the guard prevents false-degraded during legitimate startup (Pitfall 3) | ✓ Good |
| Fire-and-forget tasks attach a `make_task` done-callback (Phase 9) | Background-task exceptions must surface to logs/error channel instead of vanishing silently (REL-02) | ✓ Good |
| Extract decision logic into pure `logic/` modules; Discord/process glue stays untested-by-design (Phase 10) | Test the branches that matter without mocking Discord; ~83 mock-free tests + named scar regressions lock the critical paths | ✓ Good |
| RAG memory = `pgvector` on the existing Neon DB, not Redis/knowledge-graph (Phase 11) | A new table on infra already in use → zero new cost/infra; top-k + heuristic rerank suffices for a single-community bot | ✓ Good |
| Embeddings on a **separate** 60 RPM limiter, never the shared 15 RPM chat budget (Phase 11) | Memory writes are background work that must not starve user-facing `/ask`/`/imagine` | ✓ Good |
| Accuracy firewall: never embed SQL-known numbers; hard numbers in output come from live SQL (Phase 11) | Stale embedded counts/streaks would violate Critical Rule 5 (accuracy-first); memory is roast *ammo*, not a number source | ✓ Good |
| Numeric retrieval defaults validated by a live-Neon spike before retrieval landed (Phase 11) | MEDIUM-confidence priors (floor/dedup/dims) tuned empirically (dedup 0.90→0.92, floor 0.70, keep-768) rather than shipped on assumption | ✓ Good |
| Token-set-containment over difflib for auto-queue validation (Phase 12) | YouTube titles are longer than clean names; subset check is the semantically correct rejection test for hallucinated tracks | ✓ Good |
| `taste_episode` is a new memory `kind`, not a new table (Phase 13) | `MemoryService.recall/remember/distill` is kind-agnostic by design → zero schema fork, reuses the whole Phase 11 pgvector pipeline | ✓ Good |
| `MEMORY_DECAY_DAYS_BY_KIND` new mapping + below-floor salience (0.4) + self-refresh-on-dedup (Phase 13, D-05) | Fads must age out while still-true favorites survive; a new mapping (not a mutation of `MEMORY_DECAY_DAYS`) keeps every Phase 11 kind byte-identical | ✓ Good |
| `/discover` anchor from guild-scoped `song_history`, not guild-less `user_artist_counts` (Phase 14, OQ2 Option B) | Discovery must be per-guild and multi-user-safe — co-occurrence is a same-guild-calendar-day aggregate with no per-user attribution | ✓ Good |
| D-01: drop the `MEMORY_CALLBACK_CHANCE` gate from `/ask` + `/roast` only; ambient surfaces keep it (Phase 15) | Explicit commands should always attempt recall; ambient roasts stay rare. Locked by a four-site regression test so the split can't silently drift | ✓ Good |
| `/memory forget` must ship + be verified as a real hard-delete BEFORE proactive callbacks (Phase 15→16) | Trust ordering: an autonomous memory-surfacing feature can't ship before the user has a proven escape hatch. Hard dependency, do not reorder | ✓ Good |
| Proactive callback is an additive 3rd cadence (chance 0.10 < ambient) with a `pre_recalled_memories` bypass (Phase 16) | Rarer than ambient roasts by construction; the bypass stops the reused ambient generator from triple-gating, keeping ambient cadence byte-identical | ✓ Good |
| Vision safety = real block; `/ask`/`/imagine` permissive-but-explicit; safety-block = silent skip (Phase 17, VIS-02/03) | Gemini 2.5 defaults safety OFF, so set it explicitly everywhere; a blocked image roast must leave no trace (dedicated `str\|None` generator), while edgy text output must not regress | ✓ Good |
| Hybrid memory scoping SHIPPED — read path only, explicit per-call opt-in (Phase 21, D-01/D-02/D-04) | The Descope Rule's tripwires never fired: ambient/unprompted recall (`/roast @user`, ambient voice roasts, proactive callbacks, the music-command callback, and the auto-queue taste blend) now passes `guild_scoped=True` (or `bool(guild_id)`) into `recall()`, narrowing to `(guild_id = $N OR guild_id IS NULL)` — the current guild plus the legacy grandfathered NULL corpus (D-01, `daily_batch`'s only writer). `/ask` deliberately stays global and self-scoped (MEM-02: recalls only the invoker's own memory, so no cross-user exposure is possible) — the opt-in is per-call-site, never inferred from `guild_id` presence, because `/ask` also has a real `guild_id` in scope. Write path (`remember()`/dedup/eviction) stays fully `user_id`-scoped and byte-identical (D-02) — the Phase 13 CR-01-scarred path was never touched | ✓ Good |
| Guild-data purge on `on_guild_remove`, `guild_blocklist` excluded (Phase 21, D-03 / MEM-04) | `database.purge_guild_data` deletes `guild_id = $1` rows from four tables (`guild_config`, `guild_queues`, `guild_jams`, `user_memories`) in one transaction, called from the single existing `bot.py::on_guild_remove` hook (both natural kick/leave and the Phase 20 `/guilds leave`/`/guilds block` force-leave paths fire it via `guild.leave()` — no second purge site). Best-effort: wrapped in try/except, a purge failure logs and is swallowed, never crashes guild removal. `guild_blocklist` is NEVER purged (Phase 20 D-01 / OWNER-04) — a kicked abuser's block outlives their data, so a re-invite is still refused | ✓ Good |
| Per-guild config via a boot-loaded `GuildConfigService` cache, never a per-event DB round-trip (Phase 18, CONFIG-03) | Ambient surfaces fire on `on_message`/voice events — a Neon round-trip per event would be latency + cost death. Cache loaded once at boot, push-invalidated on change, fail-closed. Hardcoded `DEXTER_CHANNEL_ID` demoted to a one-time home-guild seed (`ON CONFLICT DO NOTHING`) | ✓ Good |
| Ambient default-OFF until `/setup` runs (Phase 18/19, CONFIG-04) | The existing fallback chain (system channel → first writable) would fire roasts/vision-roasts at strangers within minutes of an invite — the exact abuse surface the kill-switch only mitigates reactively. Unconfigured = structurally silent; core commands still work immediately | ✓ Good |
| Required keyword-only `AmbientSurface` enum threaded through the pure/service seam (Phase 19) | A surface must *name itself* to fire, so per-guild toggles can silence ROAST/PRESENCE vs VISION independently and no new ambient surface can be added that silently bypasses the toggle gate (also closed the CONFIG-04 emoji-reaction hole) | ✓ Good |
| One choke point for the block: `DexterCommandTree.interaction_check` for commands + the CONFIG-02 resolver for ambient (Phase 20, OWNER-05) | Scattering per-cog block checks guarantees one gets forgotten. A single `interaction_check` (owner-bypassed) gates every slash command; the ambient resolver's `silenced` early-return gates every unprompted surface for free. TOCTOU-safe via pre-send re-checks on the reply-after-Gemini paths | ✓ Good |
| Rate-limit *observability*, not a per-guild quota system (Phase 20, RATE-01) | A soft per-guild ceiling would throttle priority-2 traffic that already self-rejects at >10s wait, while the likely hog (priority-1 `/ask` spam) is untouched and already bounded by per-user cooldowns. `guild_id`-tagged usage counters surfaced in `/guilds` compose with the kill-switch instead of duplicating it | ✓ Good |
| `guild_blocklist` gets its OWN table, separate from `guild_config` (Phase 20, D-01) | So Phase 21's guild-data purge runs as a clean `DELETE WHERE guild_id = $1` over four tables with no "except if blocked" carve-out — a kicked abuser's block survives the purge and a re-invite is refused. `guild_config.is_blocked` is now dead/superseded, left in place (additive-only DDL) | ✓ Good |
| `build_invite_url()` is the single source of truth for the invite URL, locked by a CI drift-guard (Phase 22, INVITE-02) | Hand-maintained invite URLs in docs rot silently. One constructor over a config bitfield (the one documented `import discord` exception in `logic/`), and a build-failing test if any git-tracked doc's URL drifts from its output (with a positive control against a false green) | ✓ Good |
| No prod auto-deploy; ship CI + Pages CD + GHCR image instead (Phase 18/23) | There is no prod host (24/7 deploy parked behind the YouTube datacenter-IP block). A green CI badge is the highest recruiter signal per unit of effort; GHCR makes the future always-on host a `docker pull` config step. PORT-02/CICD-02/CICD-03 deferred as blocked-on-human (manual GitHub-UI / live-bot steps, no code) | ✓ Good (3 items owner-blocked) |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-14 after v1.4 "Open House" milestone (Phases 18–23, 28/31 requirements shipped, 3 deferred blocked-on-human)*
