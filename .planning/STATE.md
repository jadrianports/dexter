---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Live & Lethal
status: executing
stopped_at: 05-01-PLAN.md complete (Neon DB wiring + health endpoint); ready for 05-02
last_updated: "2026-06-15T08:09:44Z"
last_activity: 2026-06-15 -- 05-01 executed (sanitize_database_url + pool tuning + /health)
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 3
  completed_plans: 1
  percent: 33
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-12)

**Core value:** A sarcastic, personality-driven music + AI Discord bot that runs reliably 24/7 — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.
**Current focus:** Phase 05 — ship-it-live

## Current Position

Phase: 05 (ship-it-live) — EXECUTING
Plan: 2 of 3
Status: Executing Phase 05 (Plan 01 complete; Plan 02 next)
Last activity: 2026-06-15 -- 05-01 executed (sanitize_database_url + pool tuning + /health)

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
- [Phase 05 review]: 7 of 14 review findings fixed pre-verification (CR-01 restore-loop continue; CR-02 seed-row live-DB teardown; WR-01 backup temp+size-guard; WR-02 deploy dirty-tree/ff-only; WR-05/06 seed-test cleanup; WR-07 /sync owner_id wiring). WR-03 deferred to DEPLOY-04 live debug; WR-04 + 5 Info advisory
- [Phase 05-01]: sanitize_database_url strips entire query string (not per-param) — simpler + safe; SSL handled via ssl='require' kwarg (K-05)
- [Phase 05-01]: DB_POOL_MAX=5, AUDIO_CACHE_MAX_MB=512, DB_MAX_INACTIVE_CONN_LIFETIME=240, DB_STATEMENT_CACHE_SIZE=0 (K-04/K-07)
- [Phase 05-01]: _run_health_server uses asyncio.Event().wait() for cancellable keep-alive on 0.0.0.0:8000 (K-02 amendment)

### Pending Todos

None.

### Blockers/Concerns

- [Production risk] Koyeb free WEB service sleep-after-1h requires UptimeRobot keep-alive; K-10 runner swap (HeavenCloud/Wispbyte) is the contingency if pings prove ineffective (K-02 amended).
- [Parked] Live-concurrency reconnect race (`cogs/music.py:~609`) needs a live `/gsd:debug` session — cannot be verified by local boot. Assigned to Phase 5 (DEPLOY-04 / P-01).
- [Human-check pending] Local boot + `curl localhost:8000/health` not yet verified (requires docker compose break-glass with local Postgres).

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

Last session: 2026-06-15T08:09:44Z
Stopped at: 05-01-PLAN.md complete (Neon DB wiring + health endpoint)
Next:

  1. Execute 05-02-PLAN.md (deploy packaging: yt-dlp/aiohttp pins, Dockerfile de-Oracle, stdout logging, archive Oracle scripts, DEPLOY-KOYEB.md).
  2. Execute 05-03-PLAN.md (surgical UAT runbook re-target to Koyeb+Neon).
  3. User runs 05-UAT-RUNBOOK.md live on Koyeb+Neon, reports via /gsd-verify-work 05.
  4. User reviews + merges → main (user owns the merge).

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| Phase 05-ship-it-live P01 (Koyeb+Neon re-planned) | ~8 min | 2 tasks (3 commits incl. TDD RED) | 3 files (1 created, 2 modified) |
