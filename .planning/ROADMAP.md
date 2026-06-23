# Roadmap: Dexter ("Dex")

## Overview

Dexter is a sarcastic, personality-driven Discord bot: a reliable YouTube music player with a Gemini-powered personality (`/ask`, `/imagine`), unprompted "alive" behavior (roasts, reactions, lyrics, history), hardened and scaled to run 24/7 on PostgreSQL behind an `AutoShardedBot`. v1.0 (Phases 1–4) is shipped; v1.1 "Live & Lethal" (Phases 5–8) takes it live and adds speed, player UX, and social features.

## Milestones

- ✅ **v1.0 MVP** — Phases 1–4 (shipped 2026-06-12) — see [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- ▶ **v1.1 Live & Lethal** — Phases 5–8 (in progress)

## Phases

**Phase Numbering:** integer phases are planned milestone work; decimal phases (e.g. 2.5) are urgent insertions, ordered numerically between their surrounding integers.

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

### v1.1 Live & Lethal (Phases 5–8)

- [~] **Phase 5: Ship It Live** — code-complete + code-verified; ⏸ LIVE 24/7 deploy PARKED (YouTube blocks datacenter IPs → cloud non-viable for free; no credit card; no Raspberry Pi yet). Bot runs on user PC (residential IP) on demand → Neon Singapore. Resume when a Pi / always-on residential host is acquired.
- [x] **Phase 6: Speed & Caching** — prefetch, opus-copy, resolution cache, download timeout, frequency eviction, pipeline instrumentation, SponsorBlock — code complete 2026-06-24; live verification pending
- [→] **Phase 7: Player UX & Filters** (NEXT) — control buttons, `/seek`, `/previous`, `/jump`, favorites, playlists, `/filter` effects
- [x] **Phase 8: Social & Ops** — `/roast @user`, `/leaderboard`, `/stats` dashboard, health endpoint, quota visibility (code complete + verified 12/12 on 2026-06-19; live UAT pending → 08-HUMAN-UAT.md)

## Phase Details

### Phase 5: Ship It Live

> **Re-targeted 2026-06-15 (Oracle A1 → Koyeb + Neon).** The substrate changed; the Phase-5 goal (take Dexter live 24/7 with every v1.0 behavior + deploy/restore validated in production) did not. Original Oracle plans archived under `oracle-attempt/`. See 05-CONTEXT.md (K-01…K-18) for the pivot rationale.

**Goal**: Dexter is running 24/7 on a free Koyeb WEB service backed by Neon serverless Postgres, and every v1.0 behavioral and deploy check has been validated live (K-17)
**Depends on**: Phase 4 (code-complete bot, Docker image, Postgres schema — all done); the 3 substrate-agnostic code fixes (P-01…P-03) + per-guild sync (P-04) already committed on `gsd/phase-5-ship-it-live`
**Requirements**: DEPLOY-01, DEPLOY-02, DEPLOY-03, DEPLOY-04, DEPLOY-05, DEPLOY-06, DEPLOY-07, DEPLOY-08
**Success Criteria** (what must be TRUE):

  1. The bot deploys as a Koyeb WEB service (git-auto-built from the Dockerfile), serves `GET /health` → `{"status":"ok"}` on `0.0.0.0:8000`, and holds the Discord gateway 24/7 with an UptimeRobot ping defeating Koyeb free's 1-hour scale-to-zero; a Koyeb restart/redeploy auto-reconnects and restores the queue from Neon
  2. All 9 Phase-3 behavioral checks (voice roasts, startup message, status rotation, /lyrics, /history, reactions, repeat-song roast, streak milestones, idle loneliness) are confirmed firing in a live Discord session
  3. All Phase-4 deploy-equivalent checks pass on Koyeb+Neon (Koyeb clean deploy-healthy, queue persistence round-trip via redeploy, over-cap rejection, Postgres integration tests against Neon, UptimeRobot + Healthchecks.io ping confirmed)
  4. Voice playback survives a live reconnect event without the race at `cogs/music.py:~609` causing a double-play or silent failure (P-01), and `clear_persisted()` fires correctly on idle-leave and reconnect-failure paths (P-02)
  5. The asyncpg pool survives Neon's 5-minute idle scale-to-zero with no SSL-EOF / channel_binding / prepared-statement crash, and a Neon PITR branch-restore is confirmed end-to-end within the 6-hour window

**Plans**: 3 plans (replanned 2026-06-15 for Koyeb + Neon)
**Wave 1** *(parallel — zero file overlap)*

- [x] 05-01-PLAN.md — Neon DB wiring: `sanitize_database_url` + Wave-0 tests (K-05), asyncpg pool tuning (K-04), cache cap (K-07), minimal `/health` endpoint (K-02) — `config.py`, `tests/test_config.py`, `bot.py` (DEPLOY-01, DEPLOY-05) — COMPLETE 2026-06-15
- [x] 05-02-PLAN.md — Deploy packaging: yt-dlp/aiohttp pins (K-15), de-Oracle Dockerfile (K-11/12), stdout logging (K-16), archive Oracle scripts (K-08/09/11), `docs/DEPLOY-KOYEB.md` + `.env.example` (K-13) (DEPLOY-01, DEPLOY-08) — COMPLETE 2026-06-15

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 05-03-PLAN.md — Surgical re-target of `05-UAT-RUNBOOK.md` to Koyeb+Neon in place (K-18): drop OCI/host-cron, swap Postgres→Neon, add Koyeb-deploy/git-deploy/health/UptimeRobot/Neon-scale-to-zero/Neon-PITR checks, keep A→B→C→D + behavioral checks (DEPLOY-01…08; P-01…P-04 live-verify) — COMPLETE 2026-06-15

### Phase 6: Speed & Caching

**Goal**: Playback is noticeably faster with no inter-song gap, and every pipeline stage is instrumented so gains are measured against the bot's actual run environment (user's PC, residential IP — NOT Oracle, per 06-CONTEXT.md D-19)
**Depends on**: Phase 5 code (the audio/cache/asyncpg substrate). Live 24/7 deploy is PARKED (YT datacenter-IP block); instrumentation baselines against the on-demand PC run env, not Oracle (D-19).
**Requirements**: PERF-01, PERF-02, PERF-03, PERF-04, PERF-05, PERF-06, PERF-07
**Success Criteria** (what must be TRUE):

  1. The next track begins playing immediately after the current one ends — no audible download gap between songs when the queue is non-empty
  2. Playing a previously-cached song skips the re-encode step; the bot's logs confirm an opus-copy path rather than a transcode path for that track
  3. Queuing the same search query twice within a session hits the resolution cache — the second `/play` shows a cache-hit in instrumentation output with no YouTube re-search
  4. A download that exceeds `DOWNLOAD_TIMEOUT_SECONDS` falls back to the stream URL rather than hanging indefinitely, and the bot continues playback
  5. Cache eviction removes least-played tracks (lowest song_history play_count, not oldest-by-atime) when the `AUDIO_CACHE_MAX_MB` limit is reached (512MB per K-07; the 2GB figure in CLAUDE.md is stale), observable in eviction log output; SponsorBlock segments are silently skipped during YouTube video playback
**Plans**: 4 plans (3 waves)
**Wave 1**

- [x] 06-01-PLAN.md — Foundation: Phase-6 config constants, `resolution_cache` table + asyncpg helpers (`normalize_search_query`/`get`/`set`), `PerfMetrics` rolling aggregate, queue prefetch fields, Wave-0 test scaffold (`tests/test_phase6_perf.py` + conftest teardown) — `config.py`, `database.py`, `models/queue.py`, `services/metrics.py`, `tests/conftest.py`, `tests/test_phase6_perf.py` (PERF-03, PERF-06) — Wave 1

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 06-02-PLAN.md — Download pipeline: SponsorBlock 2-PP chain (`when=after_filter`) + codec-path logging via `postprocessor_hooks` in `DOWNLOAD_OPTS`/`download()` — `services/youtube.py`, `tests/test_youtube.py` (PERF-02, PERF-07) — Wave 2
- [x] 06-03-PLAN.md — Audio/cache layer: `DOWNLOAD_TIMEOUT_SECONDS` via `asyncio.wait_for` → stream fallback in `get_source`; LFU `cleanup_cache(pool, protected_video_ids)` rewrite — `services/audio.py`, `tests/test_audio.py` (PERF-04, PERF-05) — Wave 2

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 06-04-PLAN.md — Controller wiring: fire-and-forget `_prefetch_next_track` (generation-guarded) + trigger, resolution-cache intercept in `play()`, `PerfMetrics` into `/stats` embed — `cogs/music.py`, `bot.py`, `utils/embeds.py`, `cogs/ops.py`, `tests/test_phase6_perf.py` (PERF-01, PERF-03, PERF-06) — Wave 3 — COMPLETE 2026-06-24

### Phase 7: Player UX & Filters

**Goal**: Users have full interactive control over playback from the now-playing embed and can apply audio effects and save personal favorites
**Depends on**: Phase 5 (live deploy required for Discord button interaction testing); Phase 6 (audio pipeline must be stable before adding filter re-encode path)
**Requirements**: PLAYER-01, PLAYER-02, PLAYER-03, PLAYER-04, PLAYER-05, PLAYER-06, PLAYER-07, PLAYER-08

**Design note — filter vs. opus-copy tradeoff (PLAYER-07 / PERF-02):** The `/filter` command forces an FFmpeg re-encode (e.g. `bass=g=5`, `atempo`, `aecho`), which is mutually exclusive with the opus-copy fast-path introduced in Phase 6. The intended resolution is: **opus-copy by default; transcode only when a filter is active for the current track**. Phase 7 must wire a per-track `active_filter` flag so the audio pipeline selects the correct path. Do not remove the opus-copy fast-path for non-filtered tracks.

**Success Criteria** (what must be TRUE):

  1. The now-playing embed shows interactive buttons (play/pause, skip, loop toggle, shuffle, stop) that respond to button clicks without requiring a slash command
  2. `/seek 1:30` jumps playback to 1 minute 30 seconds into the current track; `/previous` restarts the prior queue entry; `/jump 3` begins playing the third queue slot
  3. A user can `/filter bassboost` (or nightcore / slowed+reverb / 8d), hear the effect applied, then `/filter off` to restore normal playback — opus-copy resumes for the next non-filtered track
  4. A user can save a currently-playing song to their personal favorites and retrieve it via `/favorites` in a later session
  5. A user can save the current queue as a named playlist and load it back in a new session, restoring the track list

**Plans**: TBD

### Phase 8: Social & Ops

**Goal**: Users can roast each other and compete on a leaderboard; the owner has a single-command view of bot health, usage, and API quota headroom
**Depends on**: Phase 5 (live deploy needed to accumulate real usage data for leaderboard and /stats); Phase 6 (health endpoint should report instrumented metrics)
**Requirements**: SOCIAL-01, SOCIAL-02, OPS-01, OPS-02, OPS-03
**Success Criteria** (what must be TRUE):

  1. `/roast @user` generates and posts a Gemini-personalized roast referencing that user's song history, streak, and top artists — with a template fallback if Gemini is rate-limited
  2. `/leaderboard` displays a server ranking by most songs queued, longest active streak, and most-skipped songs, pulling from live Postgres data
  3. `/stats` (owner-only) shows a Discord embed with today's command count, songs played, AI queries, images generated, and recent error count — sourced from `bot_daily_stats`
  4. A GET `/health` endpoint responds with `{"status": "ok"}` (or degraded state) and is reachable by the dead-man switch cron; the Healthchecks.io dashboard shows it as green
  5. Gemini RPM usage and Oracle CPU/memory are visible before limits are hit — either via the `/stats` embed or a linked external dashboard

**Plans**: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Music MVP | v1.0 | shipped (pre-GSD) | Complete | 2026-04-12 |
| 2. Personality + AI | v1.0 | shipped (pre-GSD) | Complete | 2026-04-13 |
| 2.5. Hardening | v1.0 | shipped (pre-GSD) | Complete | 2026-06-02 |
| 3. Alive | v1.0 | 6/6 | Complete | 2026-06-11 |
| 4. Scale | v1.0 | 5/5 | Complete | 2026-06-12 |
| 5. Ship It Live | v1.1 | 3/3 | Code complete — live deploy ⏸ PARKED (YT datacenter-IP block; resume on a Pi) | - |
| 6. Speed & Caching | v1.1 | 3/4 | In Progress|  |
| 7. Player UX & Filters | v1.1 | 4/4 | Complete   | 2026-06-18 |
| 8. Social & Ops | v1.1 | 3/3 | Code complete + verified — live UAT pending (08-HUMAN-UAT) | 2026-06-19 |
