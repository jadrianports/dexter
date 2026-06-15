---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Live & Lethal
status: executing
stopped_at: 05-03-PLAN.md complete (UAT runbook re-targeted to Koyeb+Neon per K-18); ready for user live UAT
last_updated: "2026-06-15T10:31:00Z"
last_activity: 2026-06-15 -- 05-03 executed (05-UAT-RUNBOOK.md surgically re-targeted from Oracle A1 to Koyeb+Neon; all 3 plans complete)
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 3
  completed_plans: 3
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-12)

**Core value:** A sarcastic, personality-driven music + AI Discord bot that runs reliably 24/7 — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.
**Current focus:** Phase 05 — ship-it-live (all 3 plans complete; awaiting user live UAT on Koyeb+Neon)

## Current Position

Phase: 05 (ship-it-live) — ALL PLANS COMPLETE, awaiting live UAT
Plan: 3 of 3 (COMPLETE)
Status: All Phase 05 plans executed; runbook ready for user live execution on Koyeb+Neon
Last activity: 2026-06-15 -- 05-03 executed (UAT runbook surgically re-targeted from Oracle A1 to Koyeb+Neon per K-18)

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
- [Phase 05-03]: Runbook version 2.0 (Koyeb+Neon) — 22 checks across A(7)/B(3)/C(11)/D(1); verified-live bar is K-17 (all 22 pass on Koyeb+Neon, reported via /gsd-verify-work)

### Pending Todos

None.

### Blockers/Concerns

- [Production risk] Koyeb free WEB service sleep-after-1h requires UptimeRobot keep-alive; K-10 runner swap (HeavenCloud/Wispbyte) is the contingency if pings prove ineffective (K-02 amended).
- [Parked] Live-concurrency reconnect race (`cogs/music.py:~609`) needs a live `/gsd:debug` session — cannot be verified by local boot. Assigned to Phase 5 (DEPLOY-04 / P-01); C11 + C2 runbook checks are the live-observation gate.
- [Human-check pending] User must create Neon project, Koyeb WEB service, UptimeRobot monitor, and run the 05-UAT-RUNBOOK.md end-to-end on live infra before Phase 5 is verified (K-17).

## Deferred Items

Items acknowledged and deferred at v1.0 milestone close on 2026-06-12. All three are live-deploy
verification that the Windows dev machine cannot run — they form the day-1 deployment checklist:

| Category | Item | Status |
|----------|------|--------|
| uat | Phase 04 04-HUMAN-UAT.md — 6 pending live scenarios (Oracle A1 + Postgres + Discord) | superseded by 05-UAT-RUNBOOK.md v2.0 (Koyeb+Neon) |
| verification | Phase 03 03-VERIFICATION.md — 9 live-Discord behavioral checks | carried into 05-UAT-RUNBOOK.md C1-C11 |
| verification | Phase 04 04-VERIFICATION.md — 6 live-deploy checks (Docker/Postgres/cron) | carried into 05-UAT-RUNBOOK.md A/B/D groups |

Carried-forward engineering items (not blockers):

| Category | Item | Status |
|----------|------|--------|
| reliability | Live-concurrency reconnect race (`cogs/music.py:~609`) | Assigned → Phase 5 (DEPLOY-04); C11 runbook check is the live gate |
| reliability | `clear_persisted()` not called on idle-leave / reconnect-failure (IN-02) | Fixed (P-02, Plan 05-01); B2 runbook check is the live gate |
| out-of-scope | Web config dashboard ("maybe" only) | Not committed |

## Session Continuity

Last session: 2026-06-15T10:31:00Z
Stopped at: 05-03-PLAN.md complete (all Phase 05 plans executed; UAT runbook re-targeted to Koyeb+Neon)
Next:

  1. User creates Neon project (us-east-2) + Koyeb WEB service (wdc1) + UptimeRobot monitor per `docs/DEPLOY-KOYEB.md`.
  2. User runs `05-UAT-RUNBOOK.md` live on Koyeb+Neon (A→B→C→D order; D1 last).
  3. User reports results via `/gsd-verify-work 05`.
  4. User reviews branch `gsd/phase-5-ship-it-live` and merges → main (user owns the merge).
  5. After merge, update Koyeb tracked branch from `gsd/phase-5-ship-it-live` to `main`.

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| Phase 05-ship-it-live P01 (Koyeb+Neon re-planned) | ~8 min | 2 tasks (3 commits incl. TDD RED) | 3 files (1 created, 2 modified) |
| Phase 05-ship-it-live P02 (deploy packaging) | ~12 min | 2 tasks (2 commits) | 9 files (5 created/moved, 4 modified) |
| Phase 05-ship-it-live P03 (runbook re-target) | ~4 min | 2 tasks (1 commit) | 1 file modified |
