---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 04 Plan 03 complete
last_updated: "2026-06-12T21:37:00Z"
last_activity: 2026-06-12 -- Phase 04 Plan 03 (AutoShardedBot + asyncpg pool + queue_persistence) executed
progress:
  total_phases: 5
  completed_phases: 1
  total_plans: 11
  completed_plans: 8
  percent: 27
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-11)

**Core value:** A sarcastic, personality-driven music + AI Discord bot that runs reliably 24/7 — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.
**Current focus:** Phase 04 — scale

## Current Position

Phase: 04 (scale) — EXECUTING
Plan: 4 of 5
Status: Executing Phase 04 (Plan 03 complete)
Last activity: 2026-06-12 -- Phase 04 Plan 03 (AutoShardedBot + asyncpg pool + queue_persistence) complete

Progress: [███████░░░] 65% (3 of 5 phases complete — Phase 4 executing, Plan 2/5 done)

## Performance Metrics

**Velocity:**

- Total plans completed: 0 (phases 1/2/2.5 shipped pre-GSD, no per-plan metrics captured)
- Average duration: n/a
- Total execution time: n/a

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Music MVP | shipped | - | - |
| 2. Personality + AI | shipped | - | - |
| 2.5. Hardening | shipped | - | - |

**Recent Trend:**

- Last 5 plans: n/a (pre-GSD shipped work)
- Trend: Stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Resolved] Image-gen model = `gemini-2.5-flash-image` (ground-truth tie-break vs. divergent SPECs; matches shipped `config.py:36`)
- [Phase 1/2] Layered cog → service → model architecture; `current_index` queue (no popping); global Gemini rate limiter with priority tiers
- [Phase 2.5] Live-concurrency bugs are PARKED, not fixed blind — bot booted locally only; fixes must be verifiable by inspection + local boot
- [Open → Phase 4] Hosting / 24/7 deployment is undecided (Oracle Cloud Always Free is a candidate but carries reclamation/termination risk); stay hosting-agnostic until Phase 4
- [Pending → Phase 4] SQLite sufficient for v1–v3; PostgreSQL migration deferred to Phase 4
- [03-06] idle-loneliness uses vc._idle_loneliness_seconds (not vc._idle_seconds) to avoid interfering with the auto-leave timer
- [03-06] _resolve_dexter_channel is bot.py-local (small duplication vs cogs/events.py) to preserve strict file ownership
- [03-06] startup message post wrapped in try/except so channel-resolution failure does not abort on_ready
- [04-01] MAX_QUEUE_SIZE_PER_GUILD=500 (mid-range of D-04 allowed 500-1000)
- [04-01] cap guard placed in MusicQueue.add() not cog so playlist loop is covered at source (Pitfall 3)
- [04-01] MESSAGE_BUFFER_TTL_HOURS=24 per D-05; DB_POOL_MIN=2, DB_POOL_MAX=10 per D-01
- [04-02] asyncpg==0.31.0 chosen (built-in pool, $N params, arm64 wheels, single-package)
- [04-02] Raw SQL CREATE TABLE IF NOT EXISTS chosen over Alembic (start-fresh per D-14)
- [04-02] log_track_batch wraps 3 per-/play inserts in one transaction (D-06/SCALE-01)
- [04-02] guild_queues table (jsonb payload, TEXT PK) added for SCALE-04 queue persistence
- [04-02] migrate_add_streak_columns deleted; streak cols baked into CREATE TABLE (D-16)
- [04-03] _ready_once guard placed immediately after login log line to cover all subsequent on_ready init (pool, cogs, services) on AutoShardedBot reconnect
- [04-03] module-level restore_queues() wrapper in queue_persistence.py for clean bot.py import pattern
- [04-03] asyncpg jsonb payload normalised with isinstance check to handle both dict and str returns across asyncpg versions

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 4] Hosting/24/7 deployment provider is OPEN — must be resolved in Phase 4 before claiming reliable 24/7 operation
- [Parked] Reconnect race (`cogs/music.py:~609`) needs a live `/gsd:debug` session once running 24/7; cannot be verified by local boot

## Deferred Items

Items acknowledged and carried forward:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Scale | Multi-statement DB transactions / queue caps / buffer eviction under contention | Deferred | Phase 2.5 |
| Hosting | 24/7 deployment provider decision | Open | Phase 2.5 |
| Reliability | Live-concurrency reconnect race (`cogs/music.py:~609`) | Parked | Phase 2.5 |
| Out of scope | Web config dashboard ("maybe" only) | Not committed | Phase 4 |

## Session Continuity

Last session: 2026-06-12T21:37:00Z
Stopped at: Phase 04 Plan 03 complete — next: 04-04-PLAN.md (cog consumers: db→pool migration, batched /play logging, persist-on-mutation hooks) and 04-05-PLAN.md (Dockerfile + docker-compose infra) [wave 2+3]
Resume file: .planning/phases/04-scale/04-04-PLAN.md
