---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Live & Lethal
status: awaiting-live-uat
stopped_at: Completed 05-03-PLAN.md — consolidated live-UAT runbook (21 checks A→B→C→D) + source doc by-reference updates (D-07)
last_updated: "2026-06-12T11:01:00Z"
last_activity: 2026-06-12 -- Phase 05 plan 03 complete (all three plans done; awaiting Oracle A1 live UAT)
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 3
  completed_plans: 3
  percent: 75
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-12)

**Core value:** A sarcastic, personality-driven music + AI Discord bot that runs reliably 24/7 — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.
**Current focus:** Phase 05 — ship-it-live

## Current Position

Phase: 05 (ship-it-live) — ALL PLANS COMPLETE; awaiting live UAT on Oracle A1
Plan: 3 of 3 (complete)
Status: Awaiting user to run 05-UAT-RUNBOOK.md on Oracle A1 and report results via /gsd-verify-work
Last activity: 2026-06-12 -- Phase 05 plan 03 complete (live-UAT runbook + source doc by-reference updates)

## Accumulated Context

### Decisions

Full decision log lives in PROJECT.md Key Decisions and milestones/v1.0-ROADMAP.md. Highlights:

- Hosting RESOLVED → Oracle Cloud Always Free A1 ARM; Docker Compose for portability (Phase 4)
- Persistence migrated SQLite → PostgreSQL via asyncpg 0.31.0 (Phase 4)
- Queue cap (500) enforced in `MusicQueue.add()`; `log_track_batch` single-transaction logging (Phase 4)
- Gemini-first personality output with guaranteed template fallback; `priority=2` for all background AI (Phase 3)
- [Phase ?]: Mirror /stop template at clear_persisted() gap sites to close ghost-queue-on-restart bug (DEPLOY-06)
- [Phase ?]: DEBUG level for hot per-play _play_track logs, INFO for low-frequency reconnect path
- [Phase ?]: ZoneInfo(config.STREAK_TIMEZONE) for all community-time hour checks; bot.py yt-dlp loop tzinfo deferred (D-06)
- [Phase 05-02]: deploy.sh uses --build bot (not bare --build) — only bot image rebuilt; Postgres never rebuilt
- [Phase 05-02]: pg_restore via docker compose exec (Option B) — version-matched with pg_dump server; avoids host client mismatch
- [Phase 05-02]: build_seed_rows() pure/importable function pattern — separates testable logic from async IO in scripts
- [Phase 05-03]: Strict A→B→C→D runbook ordering — destructive restore (D1) always last; source docs by-reference only, not maintained in parallel

### Pending Todos

None.

### Blockers/Concerns

- [Production risk] Oracle Cloud Always Free carries reclamation/termination risk (idle reclaim, inactivity, A1 capacity) — monitor once running 24/7.
- [Parked] Live-concurrency reconnect race (`cogs/music.py:~609`) needs a live `/gsd:debug` session — cannot be verified by local boot. Assigned to Phase 5 (DEPLOY-04).

## Deferred Items

Items acknowledged and deferred at v1.0 milestone close on 2026-06-12. All three are live-deploy
verification that the Windows dev machine cannot run — they form the day-1 deployment checklist:

| Category | Item | Status |
|----------|------|--------|
| uat | Phase 04 04-HUMAN-UAT.md — 6 pending live scenarios (Oracle A1 + Postgres + Discord) | partial |
| verification | Phase 03 03-VERIFICATION.md — 9 live-Discord behavioral checks | human_needed |
| verification | Phase 04 04-VERIFICATION.md — 6 live-deploy checks (Docker/Postgres/cron) | human_needed |

Carried-forward engineering items (not blockers):

| Category | Item | Status |
|----------|------|--------|
| reliability | Live-concurrency reconnect race (`cogs/music.py:~609`) | Assigned → Phase 5 (DEPLOY-04) |
| reliability | `clear_persisted()` not called on idle-leave / reconnect-failure (IN-02) | Assigned → Phase 5 (DEPLOY-06) |
| out-of-scope | Web config dashboard ("maybe" only) | Not committed |

## Session Continuity

Last session: 2026-06-12T11:01:00Z
Stopped at: Completed 05-03-PLAN.md — consolidated live-UAT runbook (21 checks) + three source docs updated by reference (DEPLOY-01, DEPLOY-02, DEPLOY-03, DEPLOY-05, DEPLOY-08)
Next: User runs 05-UAT-RUNBOOK.md on Oracle A1 and reports results via /gsd-verify-work.

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| Phase 05-ship-it-live P01 | 25 | 3 tasks | 5 files |
| Phase 05-ship-it-live P02 | 6 | 2 tasks (3 commits incl. TDD RED) | 6 files |
| Phase 05-ship-it-live P03 | 6 | 2 tasks | 4 files (1 created, 3 modified) |
