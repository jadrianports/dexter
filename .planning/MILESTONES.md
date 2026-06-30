# Milestones: Dexter ("Dex")

A historical record of shipped versions. Newest first.

---

## v1.2 — Sharper & Smarter

**Shipped (code):** 2026-06-30
**Phases:** 4 (9, 10, 11, 12) · **Plans:** 19 · **Tasks:** 43

**Delivered:** The "Sharper & Smarter" pass — hardened the reliability gaps (truthful `/health`, fire-and-forget failure surfacing, sync-hang guards, DB query timeouts, YouTube self-heal), covered the untested critical-path decision logic with real pure-unit tests, gave Dex a durable **RAG long-term memory** (`pgvector` on the existing Neon Postgres + `gemini-embedding-001` @ 768d → callback roasts that pair a live SQL stat with a recalled episode, at zero new infrastructure), and rounded out the music/UX (per-server `/jam` playlists, `/skips` analytics, a third lyrics fallback, hallucination-validated auto-queue). All code-complete and locally/statically verified; the live-runtime UAT tail (Phase 09/11) is deferred behind the parked 24/7 host.

### Stats

- **Timeline:** 2026-06-26 → 2026-06-30 (~5 days)
- **Commits:** 136 since `v1.1`
- **Diff:** 121 files changed, +24,390 / −302 (includes `.planning/` docs)
- **Git range:** `18806e7` (Phase 9 reliability config) → `2580bf1` (Phase 12 code-review fix report)

### Key Accomplishments

1. **Reliability & Ops Hardening (Phase 9)** — `/health` now returns degraded-503 when MusicCog fails to load (guarded by `_ready_done` to avoid false-degraded during startup); fire-and-forget tasks surface exceptions via a `utils/tasks.py` `make_task` done-callback; an un-wedgeable `on_ready` watchdog + `_sync_retry_active`-guarded startup-sync recovery (`asyncio.TimeoutError` caught before `Exception` per Python 3.11+); config-driven DB query timeouts; and bounded YouTube search/extract self-heal reusing the existing `update_ytdlp` + throttle path.
2. **Critical-Path Test Coverage (Phase 10)** — Extracted the untested decision logic into pure `logic/` modules — `playback.py` (TrackEndAction enum + five keyword-only functions), `health.py` (`determine_health_status` + `assemble_degraded_reasons`), `roasts.py` (`decide_ambient_roast` + `cooldown_elapsed`) — locked by ~83 mock-free unit tests including three named scar regressions (finished-song replay, silent auto-queue, restore index clamp). Regression gate green: full suite + clean boot, no new silent failures.
3. **RAG Long-Term Memory (Phase 11)** — `pgvector` extension-first boot + `user_memories(vector(768))` with per-connection codec registration via `create_pool(init=...)`; `GeminiService.embed()` on a **separate** 60 RPM limiter; the complete read half (pure `MemoryFact` rerank/recency/novelty/floor → `recall()` top 1–3) and write half (`remember()` with near-dup dedup → salience-ranked cap-evict); a sensitivity/PII + numbers-from-SQL accuracy firewall; callback roasts wired at all four surfaces behind a cadence gate; and a daily decay sweep keeping the store bounded. **Zero new infrastructure, zero new monthly cost.** A numeric-defaults spike against live Neon tuned the constants (dedup 0.90→0.92, floor 0.70, keep-768).
4. **Richer Music/UX (Phase 12)** — `guild_jams` table + `/jam` group (save/add/load/list/delete) giving each server a shared mixtape distinct from global favorites; a dedicated `/skips` command surfacing tracked skip data; an LRCLIB third lyrics fallback with `strip_lrc_headers`; and a pure token-set-containment validator (`logic/autoqueue.py`) that rejects hallucinated auto-queue tracks before queueing.

### Quality

- All 21 v1.2 requirements satisfied at the code level (21/21 traceability coverage).
- Phase 10 added ~83 mock-free pure-unit tests with named scar regressions; the full suite stays green and the bot boots clean (TEST-04 regression gate).
- Phase 11 RAG decisions empirically validated by a live-Neon spike before retrieval landed.
- TDD on all pure logic (`logic/playback|health|roasts|autoqueue`, memory rerank/dedup/decay); Discord/process code verified structurally + by clean boot per convention.

### Known Gaps (deferred at close: 13 surfaced by audit — see STATE.md Deferred Items)

The pre-close audit surfaced 13 open items — **all UAT / verification, all `human_needed` live-Discord checks, zero code gaps.** Phases 03–06 are the same parked v1.1 deploy checks carried forward; the two genuinely new v1.2 items are the Phase 09 and Phase 11 live-runtime checks. All resume when a Pi / always-on residential host exists:

- **Phase 09** `09-HUMAN-UAT.md` (6 pending) + `09-VERIFICATION.md` (`human_needed`) — live truthful-`/health` degraded + task-failure surfacing
- **Phase 11** `11-HUMAN-UAT.md` (3 pending) + `11-VERIFICATION.md` (`human_needed`) — live RAG recall + callback-roast behavior
- **Carried from v1.1:** Phases 03/04/05/06 HUMAN-UAT + VERIFICATION + `05-UAT-RUNBOOK.md` — all live-Discord/live-deploy checks superseded by the Koyeb+Neon runbook, pending the parked deploy.

**Archived:** `milestones/v1.2-ROADMAP.md`, `milestones/v1.2-REQUIREMENTS.md`

---

## v1.1 — Live & Lethal

**Shipped (code):** 2026-06-26
**Phases:** 4 (5, 6, 7, 8) · **Plans:** 14 · **Tasks:** 27

**Delivered:** The "Live & Lethal" pass — re-targeted deploy substrate (Oracle A1 → Koyeb + Neon serverless Postgres), a full playback-speed overhaul (prefetch, opus-copy, resolution cache, SponsorBlock, instrumentation), interactive player UX (control buttons, `/seek`/`/previous`/`/jump`, audio filters, favorites + playlists), and a social/ops layer (`/roast`, `/leaderboard`, `/stats`, `/health`). All code-complete and code-verified; Phases 6–8 verified live on the user's PC + Neon. Full 24/7 live deploy is **parked** behind the YouTube datacenter-IP block (see Known Gaps).

### Stats

- **Timeline:** 2026-06-12 → 2026-06-26 (~14 days)
- **Commits:** 114 since `v1.0` (34 `feat`)
- **Diff:** 126 files changed, +23,281 / −251 (includes `.planning/` docs)
- **Git range:** `6c2b34d` (archive v1.0) → `3ee4e54` (Phase 6 live-verified)

### Key Accomplishments

1. **Ship It Live — substrate pivot (Phase 5)** — Re-targeted Oracle A1 → Koyeb WEB + Neon serverless Postgres: Neon-tuned asyncpg pool (`ssl='require'`, 240s lifetime, `statement_cache_size=0`), `sanitize_database_url`, a minimal aiohttp `/health` on `0.0.0.0:8000`, de-Oracle'd Dockerfile + pinned yt-dlp/aiohttp, stdout logging, retired four Oracle ops scripts via `git mv`, and a full Koyeb+Neon+UptimeRobot deploy contract in `docs/DEPLOY-KOYEB.md` + a re-targeted 22-check live-UAT runbook.
2. **Speed & Caching (Phase 6)** — Generation-guarded `_prefetch_next_track` closes the inter-song gap; Postgres `resolution_cache` skips YouTube re-search on repeat queries; a 3-PP SponsorBlock→FFmpegExtractAudio→ModifyChapters chain + codec-path (`copy`|`transcode`) logging; `asyncio.wait_for(DOWNLOAD_TIMEOUT_SECONDS)` → stream fallback; async LFU `cleanup_cache` keyed on play counts with a `protected_video_ids` guard; `PerfMetrics` rolling aggregates surfaced in `/stats`.
3. **Player UX & Filters (Phase 7)** — Persistent 5-button `NowPlayingView` (play/pause, skip, loop, shuffle, stop), `/seek` `/previous` `/jump`, four `/filter` presets (bassboost / nightcore / slowed+reverb / 8d) with opus-passthrough preserved for non-filtered tracks, plus `user_favorites` and JSONB `user_playlists` (save/load named queue snapshots) — all live-DB TDD-tested.
4. **Social & Ops (Phase 8)** — `/roast @user` (Gemini-personalized from tracked history, priority-1, template fallback, `AllowedMentions.none()`), `/leaderboard` (per-guild songs / streaks / skips), owner-only `/stats`, a degraded-but-always-200 `/health`, and `total_errors` tracking at the central error-log site.

### Quality

- All 28 v1.1 requirements satisfied at the code level; 24/28 also live-validated. The 4 open requirements are all live-deploy-gated (see Known Gaps).
- Phases 6, 7, 8 verified live on the user's PC + Neon (06-UAT, 07-HUMAN-UAT, 08-HUMAN-UAT).
- Phase 6 live UAT found + fixed a real blocker (Neon SSL vs Oracle-era local Postgres in `docker-compose`) and shipped a Now-Playing repost-at-bottom UX fix.
- TDD on all pure logic (elapsed tracking, `parse_time`, `_build_ffmpeg_opts`, resolution-cache helpers, leaderboard SQL); Discord/process code verified structurally + by live UAT per convention.

### Known Gaps (deferred at close: 9 — see STATE.md Deferred Items)

The full 24/7 live deploy is **parked**: YouTube blocks datacenter IPs, making free cloud hosting non-viable, and the user has no always-on residential host yet. The bot runs on the user's PC (residential IP) on demand against Neon Singapore. These items resume when a Pi / always-on residential host is acquired:

- **DEPLOY-02** standing live-UAT checklist executed + passing — *blocked on 24/7 host*
- **DEPLOY-03** the 6 human-UAT scenarios (`04-HUMAN-UAT.md`) passing — *blocked on 24/7 host*
- **DEPLOY-05** queue + position survive a restart, validated *live* — *blocked on 24/7 host*
- **DEPLOY-08** keepalive / dead-man cron confirmed firing *in production* — *blocked on 24/7 host*
- 5 UAT gaps + 4 `human_needed` verifications (Phases 03/04/05/06) — all live-Discord/live-deploy checks superseded by the Koyeb+Neon runbook, pending the parked deploy.

**Archived:** `milestones/v1.1-ROADMAP.md`, `milestones/v1.1-REQUIREMENTS.md`

---

## v1.0 — MVP

**Shipped:** 2026-06-12
**Phases:** 5 (1, 2, 2.5, 3, 4) · **GSD-tracked plans:** 11 (Phases 3–4) · Phases 1–2.5 shipped pre-GSD

**Delivered:** The complete first release of Dexter — a sarcastic, personality-driven Discord bot that plays YouTube music, chats and generates images via Gemini, comes alive with unprompted roasts/reactions/lyrics/history, and is hardened + scaled to run 24/7 on PostgreSQL behind an `AutoShardedBot` on Oracle Cloud A1.

### Stats

- **Timeline:** 2026-04-17 → 2026-06-12 (~8 weeks)
- **Commits:** 71
- **Code:** ~7,139 Python LOC across 49 modules
- **Tests:** 20 test files (251+ passing unit/structural tests at Phase 3; 130 pure + 18 Postgres-integration collected at Phase 4)
- **Git range:** `2c5a95d` (Initial commit) → `912b725` (Merge Phase 4)

### Key Accomplishments

1. **Music engine** — `/play` (search + URL + playlist), full transport controls, `current_index` queue with generation-counter race prevention, cache-first opus audio with stream fallback and 2GB atime eviction, 10-min idle auto-leave. (Phase 1)
2. **Gemini personality + AI** — `/ask` with 10-message context + taste injection + mood/seasonal awareness, `/imagine` (`gemini-2.5-flash-image`, 10/day cap), self-feeding auto-queue with "ignored" memory, and one global 15 RPM priority-tiered rate limiter. (Phase 2)
3. **Production-honest hardening** — unsilenced exception handlers, WAL + `busy_timeout`, robust `parse_suggestions` JSON parsing, FFmpeg orphan cleanup, and a self-healing yt-dlp update→retry→stream→error chain. (Phase 2.5)
4. **"Alive" layer** — Gemini-first unprompted voice/late-night/repeat-song roasts with template fallback, message reactions, expanded seasonal branches, 5-min status rotation, startup + idle-loneliness messages, consecutive-day streaks + song milestones, and `/lyrics` (Genius→AZLyrics, paginated) + `/history`. (Phase 3)
5. **Scale pass** — SQLite→PostgreSQL (asyncpg) migration with single-transaction batched logging, `QueueFullError` cap (500), message-buffer TTL eviction, `AutoShardedBot`, queue persistence across restarts with smart-rejoin. (Phase 4)
6. **Hosting resolved + packaged** — Oracle Cloud Always Free A1 ARM decision, Docker Compose stack (arm64, healthcheck-gated, named volumes), keepalive/dead-man cron + `pg_dump` Object Storage backup. (Phase 4)

### Quality

- All 45 v1 requirements satisfied (45/45 traceability coverage).
- Phase 3 verified 10/10 must-haves; Phase 4 verified 4/4 must-haves (static/structural).
- All 3 Critical + 2 Warning Phase-4 code-review findings applied and confirmed.

### Known deferred items at close: 3 (see STATE.md Deferred Items)

All three are live-deploy verification that the Windows dev machine cannot run — they form the day-1 deployment checklist, not scope gaps:

- Phase 04 `04-HUMAN-UAT.md` — 6 pending scenarios (Oracle A1 + Postgres + Discord)
- Phase 03 `03-VERIFICATION.md` — `human_needed`, 9 live-Discord behavioral checks
- Phase 04 `04-VERIFICATION.md` — `human_needed`, 6 live-deploy checks

Plus carried-forward engineering items: the parked live-concurrency reconnect race (`cogs/music.py:~609`) for a dedicated live `/gsd:debug` session, and the `clear_persisted()`-on-idle/reconnect inconsistency (IN-02).

**Archived:** `milestones/v1.0-ROADMAP.md`, `milestones/v1.0-REQUIREMENTS.md`
