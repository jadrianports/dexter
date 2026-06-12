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

- [ ] **Phase 5: Ship It Live** — Oracle A1 + Docker standup, full live-UAT checklist, reconnect race fix, backup/restore validated
- [ ] **Phase 6: Speed & Caching** — prefetch, opus-copy, resolution cache, download timeout, frequency eviction, pipeline instrumentation, SponsorBlock
- [ ] **Phase 7: Player UX & Filters** — control buttons, `/seek`, `/previous`, `/jump`, favorites, playlists, `/filter` effects
- [ ] **Phase 8: Social & Ops** — `/roast @user`, `/leaderboard`, `/stats` dashboard, health endpoint, quota visibility

## Phase Details

### Phase 5: Ship It Live

**Goal**: Dexter is running 24/7 on Oracle A1 and every v1.0 behavioral and deploy check has been validated in production
**Depends on**: Phase 4 (code-complete bot, Docker Compose stack, Postgres schema, keepalive/backup scripts — all done)
**Requirements**: DEPLOY-01, DEPLOY-02, DEPLOY-03, DEPLOY-04, DEPLOY-05, DEPLOY-06, DEPLOY-07, DEPLOY-08
**Success Criteria** (what must be TRUE):

  1. `docker compose up` on the Oracle A1 VM brings up Postgres + bot; the bot posts its startup message to Discord and stays connected through at least one host reboot
  2. All 9 Phase-3 behavioral checks (voice roasts, startup message, status rotation, /lyrics, /history, reactions, repeat-song roast, streak milestones, idle loneliness) are confirmed firing in a live Discord session
  3. All 6 Phase-4 deploy checks (Docker clean-boot, queue persistence round-trip, over-cap rejection, Postgres integration tests, keepalive cron, backup cron) pass on the Oracle host
  4. Voice playback survives a live reconnect event without the race at `cogs/music.py:~609` causing a double-play or silent failure, and `clear_persisted()` fires correctly on idle-leave and reconnect-failure paths
  5. A `pg_dump` backup is produced, uploaded to OCI Object Storage, and restored end-to-end on the Oracle host

**Plans**: 3 plansPlans:
**Wave 1**

- [x] 05-01-PLAN.md — Three code fixes: clear_persisted gaps (DEPLOY-06), reconnect-race guard + instrumentation (DEPLOY-04), TZ-correct late-night hour + Wave-0 TZ test (D-06)
- [x] 05-02-PLAN.md — Helper scripts: deploy.sh + 6h backup cadence + OCI lifecycle (DEPLOY-01), non-destructive seed/restore-verify + pure seed test (DEPLOY-07)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 05-03-PLAN.md — Consolidated ordered live-UAT runbook (21 checks A→B→C→D) + by-reference source-doc updates (DEPLOY-01/02/03/05/08)

### Phase 6: Speed & Caching

**Goal**: Playback is noticeably faster with no inter-song gap, and every pipeline stage is instrumented so gains are measured against live Oracle numbers
**Depends on**: Phase 5 (bot must be running live so instrumentation captures real-world latency, not laptop numbers)
**Requirements**: PERF-01, PERF-02, PERF-03, PERF-04, PERF-05, PERF-06, PERF-07
**Success Criteria** (what must be TRUE):

  1. The next track begins playing immediately after the current one ends — no audible download gap between songs when the queue is non-empty
  2. Playing a previously-cached song skips the re-encode step; the bot's logs confirm an opus-copy path rather than a transcode path for that track
  3. Queuing the same search query twice within a session hits the resolution cache — the second `/play` shows a cache-hit in instrumentation output with no YouTube re-search
  4. A download that exceeds `DOWNLOAD_TIMEOUT_SECONDS` falls back to the stream URL rather than hanging indefinitely, and the bot continues playback
  5. Cache eviction removes least-played tracks (not oldest-by-atime) when the 2GB limit is reached, observable in eviction log output; SponsorBlock segments are silently skipped during YouTube video playback

**Plans**: TBD

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
| 5. Ship It Live | v1.1 | 3/3 | Awaiting Live UAT |  |
| 6. Speed & Caching | v1.1 | 0/TBD | Not started | - |
| 7. Player UX & Filters | v1.1 | 0/TBD | Not started | - |
| 8. Social & Ops | v1.1 | 0/TBD | Not started | - |
