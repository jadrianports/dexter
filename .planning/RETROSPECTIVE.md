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

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | n/a | 5 | Adopted GSD wave-based planning mid-project (Phases 3–4); earlier phases ingested retroactively |
| v1.1 | n/a | 4 | Full GSD per-phase chain throughout; executor=sonnet; deploy substrate re-targeted twice (Oracle → Koyeb → on-demand PC) |
| v1.2 | n/a | 4 | First milestone with a dedicated test-coverage phase (10) and a research-backed flagship phase (11) gated by a validation spike; pure-logic seam graduated to a `logic/` package |
| v1.3 | n/a | 5 | Longest milestone by phase count; every phase built additively on the Phase 11 memory store (zero schema forks); trust-ordered sequencing (forget before proactive); adversarial review caught a goal-blocking no-op unit tests missed |

### Cumulative Quality

| Milestone | Tests | Coverage | Notable Deps Added |
|-----------|-------|----------|--------------------|
| v1.0 | 20 files (251+ passing at Phase 3 close) | Not measured (pure-logic TDD + structural review convention) | lyricsgenius, beautifulsoup4, aiohttp, tzdata, asyncpg |
| v1.1 | + Phase 6/7/8 suites (resolution-cache, audio, filters, favorites/playlists, leaderboard — incl. live-DB integration) | Not measured (same convention) | SponsorBlock via yt-dlp postprocessors; aiohttp `/health` server |
| v1.2 | + ~83 mock-free `logic/` unit tests (playback/health/roasts) with named scar regressions + Phase 11 memory rerank/dedup/decay suites | Not measured (same convention; first explicit regression-gate phase) | `pgvector` (Neon extension) + `pgvector` Python codec; `gemini-embedding-001` embeddings |
| v1.3 | + `logic/taste|proactive|vision` suites, kind-aware memory + DB aggregate helper tests, cadence rarity-invariants, live-DB forget-proof — suite green at 848 pass / 108 skip | Not measured (same convention) | **None** — zero new deps/tables/limiters; all built on the existing pgvector + Gemini stack |

### Top Lessons (Verified Across Milestones)

1. **(Confirmed at v1.1)** Bot/process code is verified structurally + by live UAT, never by unit tests alone — v1.1's PC-env UAT caught a blocker static review missed.
2. **(Confirmed across v1.0→v1.2)** Pure seams first, integration wiring second — held every milestone, and at v1.2 graduated into a dedicated `logic/` package downstream phases import from.
3. *(New at v1.1)* Keep hosting behind a Dockerfile + `DATABASE_URL` seam — it absorbed two deploy pivots as config-only changes.
4. *(New at v1.1)* Validate that the target host can reach the core external dependency before sequencing a milestone around it — the YouTube datacenter-IP block parked the entire deploy premise.
5. *(New at v1.2)* Spike MEDIUM-confidence numeric/ML priors against real data before building on them — cheap validation beats shipped assumptions in a flagship feature.
6. *(New at v1.2, compounded at v1.3)* Give each workload class its own rate budget — separate 60 RPM embeddings from the 15 RPM chat budget so background work never starves user commands. A kind-agnostic memory store designed in v1.2 then absorbed all of v1.3's new features with zero schema forks.
7. *(New at v1.3)* Extend a shared hot path additively — new signal is byte-identical-when-empty and pinned by a regression test — to make multi-phase expansion safe.
8. *(New at v1.3)* Don't mock the exact output you're validating, and lean on adversarial review for goal-level no-ops — Phase 16's all-mocked `recall()` hid a feature-killing anchor bug the green suite never flagged.
