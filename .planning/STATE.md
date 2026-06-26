---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: Sharper & Smarter
status: executing
stopped_at: Phase 9 context gathered
last_updated: "2026-06-26T14:20:21.620Z"
last_activity: 2026-06-26 — v1.2 roadmap created (Phases 9–12, 21/21 requirements mapped)
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-26)

**Core value:** A sarcastic, personality-driven music + AI Discord bot that runs reliably 24/7 — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.
**Current focus:** v1.2 "Sharper & Smarter" roadmapped — Phases 9–12 (reliability hardening → critical-path tests → RAG long-term memory → richer music/UX). Ready to plan Phase 9. The 24/7 live deploy stays parked until an always-on residential host exists.

## Current Position

Phase: 9 of 12 (Reliability & Ops Hardening) — not yet planned
Plan: — of ~5 in Phase 9
Status: Ready to execute
Last activity: 2026-06-26 — v1.2 roadmap created (Phases 9–12, 21/21 requirements mapped)

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed (v1.2): 0
- v1.0 + v1.1: 33 plans shipped across Phases 3–8 (pre-v1.2)

**By Phase (v1.2):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 9. Reliability & Ops Hardening | 0/5 | - | - |
| 10. Critical-Path Test Coverage | 0/4 | - | - |
| 11. RAG Long-Term Memory | 0/6 | - | - |
| 12. Richer Music/UX | 0/4 | - | - |

*Updated after each plan completion. Full v1.1 per-plan timings archived in milestones/v1.1-ROADMAP.md.*

## Accumulated Context

### Decisions

Full decision log lives in PROJECT.md Key Decisions and the milestone roadmaps. Highlights most relevant to v1.2:

- Layered cog → service → model architecture; services wired in `bot.py:_initialize_once`, attached as bot attributes, accessed via `self.bot.*` — Phase 11 `MemoryService` slots in here, no redesign.
- Global Gemini 15 RPM limiter with priority tiers (sliding-window deque) — Phase 11 embeddings get a **separate** ~60 RPM `_embed_limiter`, never this shared budget.
- Neon-tuned asyncpg pool: `ssl='require'`, `statement_cache_size=0`, 240s lifetime (K-04) — Phase 11 registers the pgvector codec via `init=` (a per-connection codec, NOT a prepared statement, so `statement_cache_size=0` is a verified non-issue).
- Gemini-first personality output with guaranteed template fallback; `priority=2` for all background AI — Phase 11 memory writes are priority-2 background work.
- Pure-logic TDD seam: clock-injectable / module-level pure functions (mirrors `compute_streak`, `_build_ffmpeg_opts`) — the convention Phase 10 extracts to and Phase 11's rerank/dedup functions follow.

### Pending Todos

None.

### Blockers/Concerns

- [Phase 11 / research flag] Numeric retrieval defaults (top-k=8, 0.70 similarity floor, 0.90 dedup, ~150 per-user cap, 90-day decay, rerank weights) are MEDIUM-confidence tuned priors — validate via a short spike at the START of Phase 11 before retrieval lands.
- [Phase 11 / correction] PROJECT.md + CLAUDE.md still name the deprecated `text-embedding-004` (sunset 2026-01-14) — Phase 11 uses `gemini-embedding-001` @ 768d; correct the stale references during planning.
- [Parked] All v1.1 deploy/UAT blockers (Koyeb sleep + UptimeRobot, reconnect race, live Neon/Koyeb human-check) remain parked behind the YouTube datacenter-IP block — out of v1.2 scope, resume on a residential host. See Deferred Items.

## Deferred Items

**Acknowledged and deferred at v1.1 milestone close on 2026-06-26.** All 9 are live-Discord /
live-deploy validation that cannot run without an always-on residential host — the 24/7 deploy is
**parked** behind the YouTube datacenter-IP block (free cloud non-viable; bot runs on the user's PC
on demand → Neon Singapore). They resume when a Pi / always-on residential host is acquired.

| Category | Item | Status |
|----------|------|--------|
| requirement | DEPLOY-02 — standing live-UAT checklist executed + passing | Blocked on 24/7 host |
| requirement | DEPLOY-03 — 6 human-UAT scenarios (`04-HUMAN-UAT.md`) passing | Blocked on 24/7 host |
| requirement | DEPLOY-05 — queue + position survive restart, validated live | Blocked on 24/7 host |
| requirement | DEPLOY-08 — keepalive / dead-man cron firing in production | Blocked on 24/7 host |
| uat | Phase 04/05/06 `*-HUMAN-UAT` / `05-UAT-RUNBOOK.md` — pending live checks | Blocked on 24/7 host |
| verification | Phase 03/04/05/06 `*-VERIFICATION.md` — live-Discord / live-deploy checks | Carried into 05-UAT-RUNBOOK.md; blocked on 24/7 host |

Carried-forward engineering items (fixed in code; live gate only):

| Category | Item | Status |
|----------|------|--------|
| reliability | Live-concurrency reconnect race (`cogs/music.py:~609`) | Fixed in code (DEPLOY-04 / P-01); C11 runbook check is the live gate |
| reliability | `clear_persisted()` on idle-leave / reconnect-failure (IN-02) | Fixed (P-02); B2 runbook check is the live gate |
| out-of-scope | Web config dashboard ("maybe" only) | Deferred to a future milestone |

## Session Continuity

Last session: 2026-06-26T13:08:34.860Z
Stopped at: Phase 9 context gathered
Next:

  Plan the first v1.2 phase: `/gsd-plan-phase 9` (Reliability & Ops Hardening). Phase 11 (RAG) is
  the research-backed flagship — open it with the numeric-defaults validation spike. The 24/7 live
  deploy + its deferred DEPLOY/UAT items resume whenever a Pi / always-on residential host is acquired.
