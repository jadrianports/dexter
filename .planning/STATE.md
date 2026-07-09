---
gsd_state_version: '1.0'
milestone: v1.4
milestone_name: Open House
status: planning
last_updated: "2026-07-10T00:00:00.000Z"
last_activity: 2026-07-10
progress:
  total_phases: 6
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-10)

**Core value:** A sarcastic, personality-driven music + AI Discord bot that runs reliably — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.
**Current focus:** Phase 18 — Per-Guild Config Foundation

## Current Position

Phase: 18 of 23 (Per-Guild Config Foundation)
Plan: — of TBD in current phase
Status: Ready to plan
Last activity: 2026-07-10 — ROADMAP.md created for v1.4 "Open House" (Phases 18–23, 31/31 requirements mapped)

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed (v1.3): 18/18 (Phases 13–17) — milestone shipped 2026-07-03
- v1.0 + v1.1 + v1.2: 52 plans shipped across Phases 1-12 — full per-plan timings archived in milestones/v1.1-ROADMAP.md and milestones/v1.2-ROADMAP.md
- v1.4 (Phases 18–23): not yet planned — no timings yet

**By Phase (v1.4) — roadmap only, plans TBD:**

| Phase | Plans |
|-------|-------|
| 18. Per-Guild Config Foundation | 0/TBD |
| 19. Onboarding & Admin Setup | 0/TBD |
| 20. Owner Control Plane & Rate Observability | 0/TBD |
| 21. Memory Scoping & Guild Data Lifecycle | 0/TBD |
| 22. Invite Plumbing | 0/TBD |
| 23. Portfolio Surface & CI/CD | 0/TBD |

## Accumulated Context

### Decisions

The full pre-v1.4 decision log (architecture, per-phase highlights, every prior-milestone implementation decision) is preserved in **PROJECT.md Key Decisions** and `milestones/v1.1/v1.2/v1.3-ROADMAP.md`. This milestone's own decisions live in **REQUIREMENTS.md Key Decisions (this milestone)**. Enduring cross-milestone invariants worth carrying forward:

- `MemoryService.recall/remember/distill` is kind-agnostic — new memory kinds/scoping dimensions should be additive where possible (Phase 11/13; tested again in Phase 21's guild-scoping work).
- Accuracy firewall: qualitative narrative flows through vector memory; any number that drives a ranking decision comes from live SQL, never embedded text (Phase 11).
- Rate budgets: shared 15 RPM chat limiter (priority tiers) vs a separate ~60 RPM embed limiter — background work never starves user commands. v1.4 adds `guild_id` tagging for observability (RATE-01), not a new limiter.
- Gemini 2.5 defaults `safety_settings` OFF — set them explicitly on every user-content `generate_content` call (Phase 17).
- Pure-logic TDD seam (`logic/*.py`): all decision logic mock-free-tested before Discord wiring; glue stays untested-by-design.
- **v1.4 sequencing lock (from research + roadmap):** Phase 18 (config seam) blocks everything; Phase 19 (onboarding, preventive) before Phase 20 (owner control plane, reactive); Phase 21 (memory scoping) sequenced after Phase 20 because MEM-04's purge hangs off the force-leave/`on_guild_remove` hook; Phase 22 (invite) sequenced after Phase 20 so the abuse mitigation is real before promoting invites; Phase 23 (portfolio) is strictly last — it needs a real second-guild walkthrough to be honest.
- **Standing Descope Rule (REQUIREMENTS.md):** if plan-time research proves a requirement infeasible, descope rather than force it — applies with particular force to MEM-01/03/05, whose documented zero-code fallback is "keep memory global + disclose."

### Pending Todos

None.

### Blockers/Concerns

- [Parked] The 24/7 live deploy remains parked behind the YouTube datacenter-IP block. Not scoped to v1.4 — hosting model is intentionally unchanged this milestone (owner's PC, on demand).
- [Watch] MEM category (Phase 21) touches `services/memory.py::search_memories`/`recall()` — the exact subsystem whose `user_id`-only scoping caused the Phase 13 CR-01 blocker. Needs research at plan time; may descope per the standing Descope Rule.
- [Watch] `tree_cls`/`CommandTree.interaction_check` exact constructor kwarg (Phase 20) is MEDIUM confidence per research — verify against the installed discord.py version before implementation.

## Deferred Items

Acknowledged and deferred at v1.3 milestone close (2026-07-03) — 24 open items from the pre-close artifact audit, all `human_needed` live-Discord checks or stale planning markers, **zero code gaps**. All resume when a Pi / always-on residential host exists. (Unrelated to and not blocking v1.4 scope.)

| Category | Item | Status |
|----------|------|--------|
| uat | Phase 14 — `14-HUMAN-UAT.md` (4 pending: taste-aware auto-queue, `/discover`, `/jam suggest` feel) | Blocked on live Discord/host |
| uat | Phase 15 — `15-HUMAN-UAT.md` (4 pending: live-DB `remember→forget→recall==[]` proof + 3 `/memory` UX) | Blocked on live Discord/host |
| uat | Phase 16 — `16-HUMAN-UAT.md` (2 pending: proactive "feel" + `/memory callbacks off` UX) | Blocked on live Discord/host |
| uat | Phase 17 — `17-HUMAN-UAT.md` (3 pending: vision cadence feel, real safety-block leaves no trace, `/ask`+`/imagine` unregressed) | Blocked on live Discord/host |
| verification | Phases 14/15/16/17 — `*-VERIFICATION.md` (`human_needed`) | Blocked on live Discord/host |
| uat/verification | Phase 09/11 — `*-HUMAN-UAT`/`*-VERIFICATION` (carried v1.2: truthful `/health`, task surfacing, live RAG recall/callback roasts) | Blocked on live Discord/host |
| requirement | DEPLOY-02/03/05/08 — standing live-UAT, restart persistence, keepalive cron (carried v1.1) | Blocked on 24/7 host |
| uat/verification | Phases 03-06 `*-HUMAN-UAT`/`*-VERIFICATION`/`05-UAT-RUNBOOK.md` — carried v1.1 live-deploy checks | Blocked on 24/7 host |
| planning | Phases 13/14/15 — 3 stale `*-CONTEXT.md` open-question markers (all resolved during research/planning; code shipped + verified) | Doc-only, no action |

Prior-milestone detail also in MILESTONES.md v1.2 "Known Gaps"; v1.3 accomplishments + close in MILESTONES.md v1.3 entry.

## Session Continuity

Last session: 2026-07-10 — v1.4 "Open House" ROADMAP.md created (Phases 18–23), STATE.md reset for the new milestone, REQUIREMENTS.md traceability filled in (31/31 mapped)
Stopped at: Roadmap drafted and written; awaiting user approval
Resume file: None

## Operator Next Steps

- Review the roadmap draft (Phases 18–23) and approve, or give feedback for revision
- Once approved: `/gsd-plan-phase 18` to plan the Per-Guild Config Foundation phase
