# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP

**Shipped:** 2026-06-12
**Phases:** 5 (1, 2, 2.5, 3, 4) | **Plans:** 11 GSD-tracked (Phases 3–4) | **Sessions:** not instrumented

### What Was Built
- A complete sarcastic Discord music + AI bot: `/play` engine, `/ask` + `/imagine` via Gemini, and a global priority-tiered rate limiter (Phases 1–2).
- A production-honest hardening pass — unsilenced handlers, FFmpeg orphan cleanup, robust JSON parsing, yt-dlp self-heal (Phase 2.5).
- An "alive" layer: Gemini-first roasts/reactions, seasonal awareness, status rotation, streaks/milestones, `/lyrics` + `/history` (Phase 3).
- A scale pass: SQLite→PostgreSQL (asyncpg), `AutoShardedBot`, queue persistence with smart-rejoin, and a resolved Oracle Cloud A1 hosting decision + Docker Compose packaging (Phase 4).

### What Worked
- **Pure-logic-seam-then-wire.** Extracting testable pure functions (`compute_streak`, lyrics helpers, `Track.to_dict/from_dict`, `parse_suggestions`) before touching Discord/process code gave clean TDD RED→GREEN and isolated the PostgreSQL swap behind serialization seams.
- **Wave-based parallelization.** Phases 3 and 4 each decomposed into 3 dependency-ordered waves, letting independent plans land without rework.
- **Static verification + code review before any live run.** Caught real criticals (pool never closed, `/history` datetime crash, restore bypassing the queue cap) that would only have surfaced in production.
- **Local-boot-only discipline.** Live-concurrency bugs were parked, not fixed blind — keeping every committed fix verifiable by inspection + clean boot.

### What Was Inefficient
- **Bot work is inherently "human_needed" at verification.** A large live-UAT tail (9 Phase-3 + 6 Phase-4 behavioral checks) can't run on the Windows dev machine and had to be carried to deployment — treated correctly as a checklist, but it means "code-complete" ≠ "validated" until the Oracle VM exists.
- **Pre-GSD phases (1/2/2.5) lack per-plan metrics**, requiring a retroactive ingest/bootstrap to reconstruct roadmap + requirements.
- **SUMMARY one-liner drift.** Several Phase-4 summaries produced malformed/truncated one-liners (code symbols instead of prose), and the 03-04 SUMMARY mis-described the final implementation vs. the actual `build_chat_prompt` code.

### Patterns Established
- **Gemini-first with guaranteed template fallback** for all personality output; `priority=2` for every background/ambient AI call.
- **`AllowedMentions.none()` on all unprompted sends** to prevent stray pings.
- **Guards at the source, not the call site** — e.g. the queue cap lives in `MusicQueue.add()` so the playlist loop is covered automatically.
- **Separate accumulators for distinct timers** — idle-loneliness uses `_idle_loneliness_seconds`, independent of the auto-leave `_idle_seconds`.

### Key Lessons
1. Plan a live-UAT checklist from the start of any bot phase — "human_needed" verification is the norm, not a gap to be closed in-session.
2. Put cap/eviction/validation guards at the data structure's source so every code path (including loops) inherits them.
3. Migrate persistence behind pure serialization seams so a DB engine swap is isolated, testable, and reviewable offline.
4. Run static verification + adversarial code review before the first live boot — it catches lifecycle and type-shape bugs cheaply.

### Cost Observations
- Model mix: not instrumented this milestone.
- Sessions: not tracked (mix of pre-GSD and GSD-tracked work).
- Notable: the most expensive surface was verification reasoning over Discord/process code that cannot be unit-tested — pushing that into static structural checks kept it tractable.

---

## Milestone: v1.1 — Live & Lethal

**Shipped (code):** 2026-06-26
**Phases:** 4 (5, 6, 7, 8) | **Plans:** 14 | **Tasks:** 27 | **Commits:** 114 since v1.0

### What Was Built
- A deploy-substrate pivot: Oracle A1 → Koyeb WEB + Neon serverless Postgres — Neon-tuned asyncpg pool, `sanitize_database_url`, aiohttp `/health`, de-Oracle'd Dockerfile, stdout logging, deploy contract + 22-check runbook (Phase 5).
- A playback-speed overhaul: generation-guarded prefetch (zero inter-song gap), opus-copy + SponsorBlock, Postgres resolution cache, download-timeout→stream fallback, LFU eviction, `PerfMetrics` in `/stats` (Phase 6).
- Interactive player UX: persistent 5-button now-playing view, `/seek` `/previous` `/jump`, four `/filter` presets (opus-passthrough preserved), favorites + JSONB playlists (Phase 7).
- A social/ops layer: `/roast @user`, per-guild `/leaderboard`, owner-only `/stats`, degraded-but-always-200 `/health`, `total_errors` tracking (Phase 8).

### What Worked
- **Substrate-agnostic code paid off.** Because hosting lives behind the Dockerfile + `DATABASE_URL`, re-targeting Oracle → Koyeb → "user's PC + Neon" was config-only — no code rewrite when the deploy plan changed twice.
- **Wave-0 test scaffolds as contracts.** Phase 6/8 landed a failing/xfail scaffold first so downstream plans built against stable interfaces — clean parallel waves with no rework.
- **Pure-seam-first held again.** Clock-injectable elapsed tracking, `parse_time`, `_build_ffmpeg_opts`, resolution-cache + leaderboard SQL all unit-tested before Discord wiring.
- **Live UAT on the on-demand PC env caught a real blocker** (Neon SSL vs Oracle-era local Postgres in `docker-compose`) that static review missed — and surfaced a UX gap (Now-Playing repost-at-bottom).

### What Was Inefficient
- **Deploy-first sequencing inverted.** The milestone was scoped deploy-first so speed gains measure against live numbers — but the live deploy parked behind the YouTube datacenter-IP block, so Phases 6–8 shipped first and were validated against the PC run env instead. The premise didn't survive contact with hosting reality.
- **External constraint discovered late.** The YouTube-blocks-datacenter-IPs reality (the whole reason the deploy is parked) only surfaced during Phase 5, after the milestone was framed around free cloud hosting. A hosting feasibility spike up front would have re-shaped the plan.
- **A growing "human_needed" tail.** 9 live-validation items now sit deferred across two milestones — correct to carry, but the gap between "code-complete" and "validated" keeps widening without a standing host.

### Patterns Established
- **Persistent views:** `timeout=None` + stable `custom_id`s registered in `setup_hook` (not `on_ready`); a shared `_do_*` helper routes slash command + button through one path.
- **opus-copy default, transcode only when a filter is active** — keep the fast path for the common case.
- **LFU eviction keyed on play counts with a `protected_video_ids` guard** — never trust `atime`, never evict an in-use track.
- **Generation-guarded fire-and-forget** for background work (prefetch) so teardown on skip/stop can't be raced.

### Key Lessons
1. Validate hosting feasibility (can the audio source even be reached from the target host?) before sequencing a milestone "deploy-first."
2. Keep hosting behind a Dockerfile + `DATABASE_URL` seam — it turned two disruptive deploy pivots into config changes.
3. Land a Wave-0 test scaffold as the inter-plan contract when waves run in parallel.
4. An on-demand local run env is a legitimate live-UAT surface — it caught a blocker pure static review didn't.

### Cost Observations
- Model mix: not instrumented this milestone (executor=sonnet per memory; orchestration on opus).
- Sessions: not tracked.
- Notable: the parked deploy means the most expensive *unrealized* cost is the deferred live-UAT tail — bounded correctly as a checklist, not re-litigated each phase.

---

## Milestone: v1.2 — Sharper & Smarter

**Shipped (code):** 2026-06-30
**Phases:** 4 (9, 10, 11, 12) | **Plans:** 19 | **Tasks:** 43 | **Commits:** 136 since v1.1

### What Was Built
- Reliability & ops hardening: truthful degraded-503 `/health`, fire-and-forget failure surfacing via `make_task`, un-wedgeable `on_ready` watchdog + startup-sync recovery, DB query timeouts, YouTube search/extract self-heal (Phase 9).
- Critical-path test coverage: playback/health/roast decision logic extracted to pure `logic/` modules with ~83 mock-free unit tests + three named scar regressions; full-suite-green + clean-boot regression gate (Phase 10).
- A durable RAG long-term memory: `pgvector` on the existing Neon Postgres + `gemini-embedding-001` @ 768d behind a separate 60 RPM limiter — recall/rerank read + remember/dedup/cap-evict write halves, a sensitivity/PII + numbers-from-SQL accuracy firewall, callback roasts at four surfaces, daily decay sweep — at zero new infra (Phase 11).
- Richer music/UX: per-server `/jam` playlists, `/skips` analytics, an LRCLIB third lyrics fallback, token-set auto-queue hallucination validation (Phase 12).

### What Worked
- **Pure-seam-first graduated into a `logic/` package.** Phase 10 formalized the long-standing convention into a top-level `logic/` package (`playback`/`health`/`roasts`), which Phases 11–12 then imported from for rerank/dedup/decay and auto-queue validation — the seam became shared infrastructure, not a per-phase habit.
- **Spike-before-commit on ML priors.** Phase 11 ran a numeric-defaults validation spike against live Neon *before* retrieval landed, tuning MEDIUM-confidence priors empirically (dedup 0.90→0.92, floor 0.70 kept, keep-768) instead of shipping assumptions — the flagship phase's riskiest guesses were de-risked cheaply up front.
- **Disjoint-file wave parallelization held.** Phase 9 Wave 2 (utils+music vs bot.py vs youtube), Phase 10 Wave 1 (three disjoint `logic/` modules), and Phase 12 (all Wave 1, append-only `database.py`/`config.py`) ran with zero file-overlap rework.
- **Accuracy firewall designed in, not bolted on.** Memory never embeds SQL-known numbers; hard numbers in output come from live SQL — Critical Rule 5 survived the RAG addition intact.

### What Was Inefficient
- **The "human_needed" tail grew again.** Four new v1.2 live-runtime items (Phase 09 truthful-health + task-surfacing, Phase 11 RAG recall + callback-roast behavior) join the parked v1.1 deploy checks. RAG's real payoff — recall quality and whether callback roasts actually land — genuinely needs a live community the parked host still blocks.
- **Decision-log provenance drifted.** Many STATE.md decisions were logged as `[Phase ?]` or bare `11-04` placeholders, and several Phase-09 SUMMARYs produced empty one-liners — the per-decision phase attribution decayed over a long, fast milestone.
- **A requirement checkbox went stale.** UX-03 (LRCLIB fallback) stayed unchecked in REQUIREMENTS.md despite 12-03 shipping it — caught and corrected at milestone close rather than at the Phase 12 transition.

### Patterns Established
- **A top-level `logic/` package** is the canonical home for extracted pure decision logic (`playback`, `health`, `roasts`, `autoqueue`) — keyword-only primitives, mock-free tests, Discord/process glue stays out.
- **One rate budget per workload class** — 60 RPM embeddings vs the shared 15 RPM chat budget, so background memory writes can never starve user-facing `/ask`/`/imagine`.
- **Spike-to-lock-constants** — validate MEDIUM-confidence numeric/ML priors against real data before building retrieval on them.
- **RAG accuracy firewall** — memory is optional roast *ammo* the model may NOOP; any hard number in the output comes from live SQL, never from an embedded fact.

### Key Lessons
1. Extract critical-path decision logic into a pure `logic/` package early — it makes the branches testable without mocking Discord, and later phases import from it instead of re-deriving.
2. Spike numeric/ML priors against real data before building on them — a half-day validation beats shipping tuned-by-assumption constants into a flagship feature.
3. Give each workload class its own rate budget so background work can't starve user commands.
4. Reconcile requirement checkboxes at each phase transition, not at milestone close — stale traceability state accumulates silently across a fast milestone.

### Cost Observations
- Model mix: not instrumented this milestone.
- Sessions: not tracked.
- Notable: Phase 11 P05 (distillation prompt + sensitivity/number gates + write-hooks + daily batch) was the heavyweight — the largest single plan by the STATE.md per-plan metrics (~8 files). The RAG write-producer half carried the milestone's most concentrated complexity.

---

## Milestone: v1.3 — Taste Brain

**Shipped (code):** 2026-07-03
**Phases:** 5 (13, 14, 15, 16, 17) | **Plans:** 18 | **Tasks:** 42 | **Commits:** 146 since v1.2

### What Was Built
- Semantic music memory: a number-free `taste_episode` kind distilled from `song_history` onto the existing pgvector store, with its own salience/decay tier + self-refresh-on-dedup and a dedicated 05:00 UTC distill batch — zero new tables (Phase 13).
- A smarter music brain: taste-aware auto-queue (recently-skipped negative hint + hard post-filter + room-taste positive blend), `/discover` (SQL co-occurrence adjacency), `/jam suggest` (validated generative additions) (Phase 14).
- RAG reach: `recall()` grounding `/roast @user` (target-scoped) + `/ask`, and a `/memory` cog with a verbatim view and an irreversible hard-delete `forget` (Phase 15).
- A third proactive ambient cadence (chance 0.10 + daily cap) volunteering a chat-anchored memory, with a per-user opt-out column distinct from forget (Phase 16).
- A fourth vision cadence: cadence-gated `gemini-2.5-flash` image roasts with a before-download mime/size gate, silent-skip on safety block, and a `safety_settings` retrofit across all three user-content generate_content sites (Phase 17).

### What Worked
- **Kind-agnostic memory paid off enormously.** Phase 13 added `taste_episode` as pure config + a new `kind` with zero change to `services/memory.py`/`models/memory.py` — and Phases 14/15/16 then read it without touching the store. The Phase 11 design decision compounded across four downstream phases.
- **Additive + byte-identical-when-empty + regression-lock.** Every new signal (taste blend, proactive callback, vision cadence) defaults to a no-op when its input is empty and is pinned by a test proving prior behavior unchanged (the four-site cadence test, the `pre_recalled_memories` bypass). This is what made a five-phase expansion of a shared hot path (the auto-queue prompt, the ambient cadence) safe.
- **Trust ordering enforced as a hard dependency.** `/memory forget` (Phase 15) shipped and was verified as a real rows+embeddings hard-delete *before* the autonomous proactive surface (Phase 16) — the roadmap refused to reorder past that gate.
- **The pure-logic seam scaled to three more modules.** `logic/taste`, `logic/proactive`, `logic/vision` kept the milestone's riskiest content — cadence rarity and safety gating — testable mock-free before any Discord wiring.
- **Adversarial review caught a goal-blocker unit tests couldn't.** Phase 16 WR-03 (the proactive recall anchored on a content-free string → the feature was effectively a no-op) was caught independently by both reviewer and verifier; every P16 test mocked `recall()`, so nothing in the suite would have surfaced it.

### What Was Inefficient
- **The `human_needed` tail grew by 13 more items (now 24 at close).** Phases 14–17 each added live-Discord UAT that can't run without a standing host — a third straight milestone where "code-complete" outran "validated," and RAG/proactive/vision are precisely the features whose real payoff needs a live community.
- **Decision-log provenance drifted again.** Many STATE.md decisions landed double-prefixed (`[Phase ?]: [Phase 1X]`) — the same attribution decay flagged at v1.2 recurred over another long, fast milestone.
- **Test-mocking masked a real gap.** Because all Phase 16 tests mocked `recall()`, the WR-03 no-op anchor passed the entire suite green; only adversarial review caught it. A single test exercising the real anchor string would have caught it at execution time.

### Patterns Established
- **Additive-signal + byte-identical-when-empty + regression-lock** — the safe way to extend a shared decision path (auto-queue prompt, ambient cadence) without risking prior behavior.
- **Kind-tiered memory** — per-kind decay/salience via a *new* mapping (`MEMORY_DECAY_DAYS_BY_KIND`), never a mutation of the base default, so existing kinds stay provably unchanged.
- **Trust-ordered sequencing** — ship the user's control/escape-hatch before the autonomous surface that depends on it.
- **Silent-skip vs fallback split** — a safety-blocked *unprompted* output leaves no trace (dedicated `str|None` generator), distinct from a transport-failure fallback that still speaks.

### Key Lessons
1. When extending a shared decision path, make the new signal additive + byte-identical-when-empty and lock the old behavior with a regression test — it converts a risky hot-path change into a safe one.
2. Sequence the user's escape hatch before the autonomous feature that depends on it — trust ordering is a real dependency, not a nicety.
3. Don't mock the exact thing whose output you're validating — Phase 16's all-mocked `recall()` hid a no-op anchor that only adversarial review caught.
4. Add per-kind tiers via a new mapping, not a mutation of the base — it keeps every prior kind's behavior provably unchanged.

### Cost Observations
- Model mix: executor/verifier/reviewer/fixer = sonnet; orchestration + planning = opus (per session memory). Not otherwise instrumented.
- Sessions: not tracked.
- Notable: the flagship *risk* this milestone was cadence/safety tuning, not an ML prior — de-risked by pure-logic gates + adversarial review rather than a data spike (contrast v1.2's Phase 11 numeric-defaults spike). Phase 14 was the heaviest by plan count (5) and file spread.

---

## Milestone: v1.4 — Open House

**Shipped (code):** 2026-07-14
**Phases:** 6 (18, 19, 20, 21, 22, 23) | **Plans:** 32 | **Tasks:** 78 | **Commits:** 231 since v1.3 | **Timeline:** 2026-07-10 → 2026-07-14 (5 days)

### What Was Built
- A per-guild config seam: `guild_config` table + pure `logic/guild_config.py` + boot-loaded, fail-closed `GuildConfigService` cache that replaced the hardcoded `DEXTER_CHANNEL_ID` single-channel assumption everywhere; an unconfigured guild is *structurally* silent (Phase 18).
- A real green CI gate: ruff (lint+format) + pytest against a `pgvector/pgvector:pg16` service container on every push/PR, zero secrets — the first milestone where the ~111 live-DB tests actually run rather than skip (Phase 18).
- Self-serve onboarding: `/setup` (channel/roasts/vision) with a `manage_guild` gate + independent per-guild toggles, a required keyword-only `AmbientSurface` enum, and guild-lifecycle glue (Phase 19).
- An owner kill-switch at one choke point: `/guilds` list/silence/leave/block/unblock via `DexterCommandTree.interaction_check` + block-check-first re-invite refusal + per-guild Gemini usage counters, backed by a purge-proof `guild_blocklist` table (Phase 20).
- Hybrid memory scoping: an explicit per-call-site `guild_scoped=True` opt-in narrowing ANN recall for unprompted surfaces while `/ask` stays global, plus a four-table `purge_guild_data` on guild removal (Phase 21).
- The recruiter-facing surface: a single least-privilege `build_invite_url()` + public `/invite` + CI drift-guard, an Astro static `/site` landing page, an architecture-case-study README, and honest scope-boundary docs (Phases 22–23).

### What Worked
- **The CI gate earned its keep on the first real run.** Standing up the pgvector service container turned ~111 always-skipped live-DB tests into executing tests — and immediately caught a sentinel collision that would have silently kept them skipping, plus two latent fresh-boot bugs (an import-time `sys.exit`, and a `0.0`-vs-monotonic clock sentinel that suppressed vision roasts / yt-dlp self-heal after any reboot) invisible on a long-uptime dev box. All locked by `test_fresh_boot_regressions.py`.
- **Deliberate table separation paid a downstream dividend.** Giving `guild_blocklist` its OWN table in Phase 20 (D-01) is exactly what let Phase 21's `purge_guild_data` be a clean four-table `DELETE` with no "except if blocked" carve-out — a decision made one phase early to unblock the next.
- **The Descope Rule held as a real safety valve.** MEM-01/03/05 touched the Phase 13 CR-01-scarred `search_memories` path; research was run at plan time precisely because of that scar, the tripwires never fired, and the read-path-only opt-in shipped without reopening the write path.
- **Structural silence over remembered-to-guard.** The pure `logic/guild_config.py` seam + required `AmbientSurface` enum make it impossible to add an ambient surface that forgets to check per-guild config — the same "make the invariant structural" move that worked for the pure-logic seam in prior milestones.
- **The drift-guard pattern generalized.** Phase 22's CI test failing the build on any doc invite-URL drift extended cleanly to Phase 23's site build — a reusable "single source of truth, enforced by a build-failing test with a positive control" shape.

### What Was Inefficient
- **Executors over-marked requirement status three separate times.** Requirement checkboxes were flipped to complete ahead of reality, forcing a central reconciliation pass on REQUIREMENTS.md before close could be trusted. A single writer of requirement status (the verifier, not the executor) would have avoided it.
- **`commit_docs` was effectively false, so planning-doc commits fell to the orchestrator by hand.** The auto-commit-docs path didn't fire, so `.planning/` updates had to be committed manually throughout — quiet friction repeated across all six phases.
- **The `human_needed` tail grew again — now 36 at close** (up from 24 at v1.3). Every new multi-tenant surface (`/setup`, kill-switch, guild-scoped recall, `/invite`) added live-Discord UAT that can't run without a standing host. A fourth straight milestone where "code-complete" outran "validated."
- **Three requirements couldn't close at all without manual GitHub-UI steps.** PORT-02 (live-bot Dexter lines), CICD-02 (Pages toggle), CICD-03 (GHCR flip) are owner-performed, not code — a foreseeable shape that could have been split into their own explicitly-human phase rather than deferred at the end.
- **North-star doc drift.** CLAUDE.md's Build Phases section stopped at Phase 17 and its milestone-status line still claimed "v1.3 pending close" — the spec fell a whole milestone behind the code before anyone refreshed it.

### Patterns Established
- **CI as a correctness gate, not just a lint pass** — a service-container-backed suite that runs the previously-skipped integration tests catches fresh-boot/environment bugs a long-uptime dev box hides.
- **Own-table-for-purge-safety** — data that must survive a lifecycle purge (a blocklist) gets its own table so the purge stays a literal, reviewable `DELETE` list with no carve-outs.
- **Structural silence** — gate a cross-cutting behavior (ambient output) at one pure seam + a required self-identifying enum, so no new call site can bypass it.
- **Single-source-of-truth + drift-guard** — one constructor for a value that appears in many places (invite URL), locked by a build-failing test with a positive control.

### Key Lessons
1. Turn on the integration tests in CI *early* — the environment differences a service container exposes (fresh boot, real Postgres) surface bugs that a long-running dev box and all-mocked unit tests both hide.
2. Make requirement *status* have a single writer (the verifier), not the executor — over-eager completion marks cost a reconciliation pass three times this milestone.
3. Separate owner-performed steps into their own explicitly-human work item up front — PORT-02/CICD-02/CICD-03 were never code and shouldn't have ridden a code phase to the end.
4. Refresh the north-star spec (CLAUDE.md) at each milestone close, not opportunistically — it silently fell a full milestone behind the code.

### Cost Observations
- Model mix: executor/verifier/reviewer/fixer = sonnet; orchestration + planning = opus (per session memory). Not otherwise instrumented.
- Sessions: not tracked.
- Notable: the flagship *risk* this milestone was multi-tenancy correctness + abuse-surface control on public servers, de-risked structurally (pure seams, one choke point, own-table purge) rather than by a data spike. Phases 18 and 20 were the heaviest by plan count (7 each); Phase 23 (portfolio) was the only phase to close with requirements it structurally couldn't finish in code.

---

## Milestone: v1.5 — Deep Cuts

**Shipped (code):** 2026-07-18
**Phases:** 5 (24, 25, 26, 27, 28) | **Plans:** 17 | **Tasks:** 47 | **Commits:** 102 since v1.4 | **Timeline:** 2026-07-14 → 2026-07-18 (5 days)

### What Was Built
- Hosting honesty: every dead cloud-host reference (Render/Koyeb/Oracle) purged from code + config + docs, five dead Oracle-era files deleted, `DEPLOY-KOYEB.md` → a lean `DEPLOY-DOCKER.md`, and a permanent CI drift guard against regrowth (Phase 24).
- Durable + richer memory: salience/expiry reinforcement at the single `recall()` chokepoint (GREATEST-guarded, kind-grouped) so frequently-relevant facts outlive one-offs under the decay sweep, plus a `vision_roast` memory kind persisted through the accuracy/PII firewall — additive on the pgvector store, zero new tables (Phase 25).
- Radio mode: `/radio start|stop` endless taste-brain DJ via a keyword-only `radio=True` branch behind a pure `logic/radio.py` gate + in-memory `MusicQueue` armed-state, with lookahead refill, loop mutual-exclusion, and structural disarm on every `clear()` (Phase 26, DJ-01).
- Skip democracy: vote-gated `/skip` with a narrated tally at ONE `_try_skip` choke point (pure `logic/skip_vote.py`, config-honouring majority, requester bypass, solo-instant) — `_do_skip` called exactly once (Phase 26, DJ-02).
- Crossfade: DJ-03 shipped after a plan-time spike returned GO/suppressed — the fade lives inside the incoming track's own `AudioSource` (`CrossfadeSource`/`TruncatingSource` equal-power `audioop` mix, one `cleanup()` owning both decoders), `/crossfade on|off`, silent hard-cut fallback, two mandatory D-17 rails (Phase 27).
- Portfolio finish: PORT-05's shipped redesign confirmed still true + locked as a durable build-scanning `test_demo_transcript_guard.py`; owner runbook handing off the three blocked-on-human items (Phase 28).

### What Worked
- **The spike gate did its job — and returned GO the safe way.** Phase 27's plan-time spike attacked the real generation-counter/`/skip`/prefetch engine before any implementation, and the verdict (GO / *suppressed*) reshaped the design: instead of touching the delicate per-track `play()` engine (which would have tripped D-01), the fade was pushed inside the incoming track's own `AudioSource`, so the engine stayed byte-identical. The Descope Rule's escape hatch was ready but unneeded.
- **Adversarial code review caught a requirement-defeating Critical.** In Phase 26, `/skip` and `/seek` counted skip votes from users *not in the voice channel* (the button gated; those two didn't) — which would have silently defeated DJ-02 entirely. Because `decide_skip` deliberately doesn't filter by live membership (D-17), membership gating is the caller's job, and two of three callers skipped it. Review + regression lock closed it.
- **Execution surfaced a skip surface no planning doc listed.** `/seek 99:99` past-end auto-skip called `_do_skip` directly — a full vote bypass. Routing it through `_try_skip` (required by the plan's own "exactly one `_do_skip` call site" criterion) closed a hole discovery-during-execution found, not planning.
- **Additive-on-existing-substrate held for a fifth milestone.** MEM-06/07 rode the Phase 11/13 pgvector store with zero new tables and a kind-agnostic write path; the byte-identical-when-unexercised guard kept every prior kind's decay/salience intact.
- **API-crash / session-limit resume was handled surgically, not blindly.** Two executors died mid-Task on "Connection closed mid-response"; the Phase 27-05 executor died on a session limit mid-Task-3 with work staged + green but uncommitted. Each was recovered by spot-checking partial state (commits? SUMMARY? staged diff?) and resuming, never blind-redispatched.

### What Was Inefficient
- **The `human_needed` tail kept growing — 44 at close** (up from 36 at v1.4). Radio cadence feel, multi-listener tally narration, crossfade blend smoothness, `/skip`-mid-crossfade — every new audible/interactive surface added live-Discord UAT that can't run without a standing host. A fifth straight milestone where "code-complete" outran "validated."
- **The full suite had to run foreground (~7 min) — backgrounded runs got killed ~15% in.** A real friction tax on every verify pass; the `1233↔1232` count flip (a `site/dist` skip, not a regression) also cost a diagnostic detour before it was understood as benign.
- **`phase.complete` left the REQUIREMENTS traceability row stale, and `milestone.complete` dumped 15 unstructured accomplishment bullets into MILESTONES.md** — both required a hand-fix at close (the same class of CLI-output-needs-curation friction seen at v1.4).
- **Commits stayed unpushed across the whole milestone** — the local-main-only workflow means the entire v1.5 stack sat unpushed until close, so CI never saw the intermediate phases.

### Patterns Established
- **Spike-then-redesign** — a plan-time spike against the real engine doesn't just gate go/no-go, it can relocate the whole implementation (crossfade moved *inside* the AudioSource) so the risky surface is never touched.
- **One choke point for a cross-cutting gate, with membership filtering pushed to callers by contract** — `_do_skip` called from exactly one place, and the deliberate D-17 "count departed voters" decision makes the caller responsible for live-membership filtering (a contract a reviewer must check every caller against).
- **Suppress-with-rails over patch-and-hope** — the `send_silence` monkeypatch shipped only with a fail-soft wrapper *and* a CI drift guard asserting the real `_do_run` call site (with a positive control), so a discord.py upgrade that moves the call site fails the build.

### Key Lessons
1. Run the spike against the *real* engine and let the verdict reshape the design, not just gate it — GO/suppressed moved crossfade off the dangerous surface entirely.
2. When a decision intentionally under-filters (D-17 counts departed voters), make "the caller filters" an explicit reviewed contract — two of three callers forgot, and it was a Critical.
3. Discovery-during-execution finds entry points planning misses — the "exactly one `_do_skip` call site" acceptance criterion is what forced the third skip surface into the light.
4. Budget for foreground suite time and CLI-output curation at close — the 7-min foreground suite and the MILESTONES/REQUIREMENTS hand-fixes are now predictable, not surprises.

### Cost Observations
- Model mix: executor/verifier/reviewer/fixer = sonnet; orchestration + planning = opus (per session memory). Not otherwise instrumented.
- Sessions: not tracked; at least three sessions saw executor API-crash / session-limit interruptions, all recovered orchestrator-side.
- Notable: the flagship *risk* this milestone was the playback-engine surface (radio refill + skip-voting + crossfade all touching the generation-counter/`/skip`/prefetch machinery). Containing crossfade to its own spike-gated phase *after* radio/skip-voting kept the engine risk from compounding — the sequencing lock from roadmap creation paid off.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | n/a | 5 | Adopted GSD wave-based planning mid-project (Phases 3–4); earlier phases ingested retroactively |
| v1.1 | n/a | 4 | Full GSD per-phase chain throughout; executor=sonnet; deploy substrate re-targeted twice (Oracle → Koyeb → on-demand PC) |
| v1.2 | n/a | 4 | First milestone with a dedicated test-coverage phase (10) and a research-backed flagship phase (11) gated by a validation spike; pure-logic seam graduated to a `logic/` package |
| v1.3 | n/a | 5 | Longest milestone by phase count; every phase built additively on the Phase 11 memory store (zero schema forks); trust-ordered sequencing (forget before proactive); adversarial review caught a goal-blocking no-op unit tests missed |
| v1.4 | n/a | 6 | First real green CI gate (service-container pgvector) unskipping ~111 live-DB tests + catching latent fresh-boot bugs; multi-tenancy retrofit (config seam + cache) with structural silence; owner kill-switch at one choke point; portfolio pivot — first milestone to close with requirements it structurally couldn't finish in code (owner-performed GitHub steps) |
| v1.5 | n/a | 5 | First spike-gated phase where the GO verdict *relocated* the implementation (crossfade inside the AudioSource) to keep the engine untouched; playback-engine-heavy milestone sequenced to contain risk (radio/skip before crossfade); adversarial review caught a requirement-defeating Critical (skip votes from non-listeners); multiple executor API-crash/session-limit resumes recovered orchestrator-side |

### Cumulative Quality

| Milestone | Tests | Coverage | Notable Deps Added |
|-----------|-------|----------|--------------------|
| v1.0 | 20 files (251+ passing at Phase 3 close) | Not measured (pure-logic TDD + structural review convention) | lyricsgenius, beautifulsoup4, aiohttp, tzdata, asyncpg |
| v1.1 | + Phase 6/7/8 suites (resolution-cache, audio, filters, favorites/playlists, leaderboard — incl. live-DB integration) | Not measured (same convention) | SponsorBlock via yt-dlp postprocessors; aiohttp `/health` server |
| v1.2 | + ~83 mock-free `logic/` unit tests (playback/health/roasts) with named scar regressions + Phase 11 memory rerank/dedup/decay suites | Not measured (same convention; first explicit regression-gate phase) | `pgvector` (Neon extension) + `pgvector` Python codec; `gemini-embedding-001` embeddings |
| v1.3 | + `logic/taste|proactive|vision` suites, kind-aware memory + DB aggregate helper tests, cadence rarity-invariants, live-DB forget-proof — suite green at 848 pass / 108 skip | Not measured (same convention) | **None** — zero new deps/tables/limiters; all built on the existing pgvector + Gemini stack |
| v1.4 | + `logic/guild_config|invite` suites, GuildConfigService no-round-trip regressions, blocklist/silence/purge live-DB tests, invite + site drift-guards — **~1017 pass in CI, ~111 live-DB tests now execute** (not skip) against a pgvector service container | Not measured (same convention; first CI-enforced gate) | ruff (dev tooling); Astro (site build, isolated in `/site`) — **no new bot runtime deps/tables/limiters** |
| v1.5 | + `logic/radio\|skip_vote\|crossfade` suites (incl. 24-row crossfade ladder), `MusicQueue` radio/vote/xf state guards, `TruncatingSource`/`CrossfadeSource` tests, `send_silence` + hosting + demo-transcript drift-guards — suite green at **1238 pass / 129 skip / 0 fail** | Not measured (same convention) | **None** — `audioop` is stdlib on the pinned 3.11 (numpy rejected); zero new tables/limiters/runtime deps |

### Top Lessons (Verified Across Milestones)

1. **(Confirmed at v1.1)** Bot/process code is verified structurally + by live UAT, never by unit tests alone — v1.1's PC-env UAT caught a blocker static review missed.
2. **(Confirmed across v1.0→v1.2)** Pure seams first, integration wiring second — held every milestone, and at v1.2 graduated into a dedicated `logic/` package downstream phases import from.
3. *(New at v1.1)* Keep hosting behind a Dockerfile + `DATABASE_URL` seam — it absorbed two deploy pivots as config-only changes.
4. *(New at v1.1)* Validate that the target host can reach the core external dependency before sequencing a milestone around it — the YouTube datacenter-IP block parked the entire deploy premise.
5. *(New at v1.2)* Spike MEDIUM-confidence numeric/ML priors against real data before building on them — cheap validation beats shipped assumptions in a flagship feature.
6. *(New at v1.2, compounded at v1.3)* Give each workload class its own rate budget — separate 60 RPM embeddings from the 15 RPM chat budget so background work never starves user commands. A kind-agnostic memory store designed in v1.2 then absorbed all of v1.3's new features with zero schema forks.
7. *(New at v1.3)* Extend a shared hot path additively — new signal is byte-identical-when-empty and pinned by a regression test — to make multi-phase expansion safe.
8. *(New at v1.3)* Don't mock the exact output you're validating, and lean on adversarial review for goal-level no-ops — Phase 16's all-mocked `recall()` hid a feature-killing anchor bug the green suite never flagged.
9. *(New at v1.4)* Turn the integration tests on in CI early — a service-container gate surfaced fresh-boot/environment bugs that both a long-uptime dev box and all-mocked unit tests hid, and made every subsequent phase execute behind a real green gate.
10. *(New at v1.4)* Give requirement *status* a single writer (the verifier, not the executor) and split owner-performed steps into their own explicitly-human work item — over-eager completion marks forced three reconciliation passes, and three requirements rode a code phase to the end without ever being code.
