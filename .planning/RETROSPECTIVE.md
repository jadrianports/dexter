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

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | n/a | 5 | Adopted GSD wave-based planning mid-project (Phases 3–4); earlier phases ingested retroactively |
| v1.1 | n/a | 4 | Full GSD per-phase chain throughout; executor=sonnet; deploy substrate re-targeted twice (Oracle → Koyeb → on-demand PC) |

### Cumulative Quality

| Milestone | Tests | Coverage | Notable Deps Added |
|-----------|-------|----------|--------------------|
| v1.0 | 20 files (251+ passing at Phase 3 close) | Not measured (pure-logic TDD + structural review convention) | lyricsgenius, beautifulsoup4, aiohttp, tzdata, asyncpg |
| v1.1 | + Phase 6/7/8 suites (resolution-cache, audio, filters, favorites/playlists, leaderboard — incl. live-DB integration) | Not measured (same convention) | SponsorBlock via yt-dlp postprocessors; aiohttp `/health` server |

### Top Lessons (Verified Across Milestones)

1. **(Confirmed at v1.1)** Bot/process code is verified structurally + by live UAT, never by unit tests alone — v1.1's PC-env UAT caught a blocker static review missed.
2. **(Confirmed at v1.1)** Pure seams first, integration wiring second — held across all four v1.1 phases.
3. *(New at v1.1)* Keep hosting behind a Dockerfile + `DATABASE_URL` seam — it absorbed two deploy pivots as config-only changes.
4. *(New at v1.1)* Validate that the target host can reach the core external dependency before sequencing a milestone around it — the YouTube datacenter-IP block parked the entire deploy premise.
