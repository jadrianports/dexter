---
gsd_state_version: 1.0
milestone: v1.3
milestone_name: Taste Brain
status: executing
stopped_at: Completed 15-01-PLAN.md
last_updated: "2026-07-02T17:51:09.053Z"
last_activity: 2026-07-02 -- Phase 15 execution started
progress:
  total_phases: 5
  completed_phases: 2
  total_plans: 12
  completed_plans: 10
  percent: 40
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-02)

**Core value:** A sarcastic, personality-driven music + AI Discord bot that runs reliably — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.
**Current focus:** Phase 15 — rag-reach

## Current Position

Phase: 15 (rag-reach) — EXECUTING
Plan: 2 of 3
Status: Ready to execute
Last activity: 2026-07-02 -- Phase 15 execution started

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed (v1.3): 0
- v1.0 + v1.1 + v1.2: 52 plans shipped across Phases 1-12 (pre-v1.3) — full per-plan timings archived in milestones/v1.1-ROADMAP.md and milestones/v1.2-ROADMAP.md

**By Phase (v1.3):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 13. Semantic Music Memory | 0/TBD | - | - |
| 14. Smarter Music Brain | 0/TBD | - | - |
| 15. RAG Reach | 0/TBD | - | - |
| 16. Proactive Memory Callbacks | 0/TBD | - | - |
| 17. Vision / Multimodal Roasting | 0/TBD | - | - |
| 14 | 5 | - | - |

*Updated after each plan completion. Plan counts refined during /gsd-plan-phase.*
| Phase 13 P01 | 12min | 2 tasks | 3 files |
| Phase 13 P02 | 10min | 2 tasks | 2 files |
| Phase 13 P03 | 12min | 2 tasks | 2 files |
| Phase 13 P04 | 11min | 2 tasks | 1 files |
| Phase 14 P01 | 25min | 3 tasks | 6 files |
| Phase 14 P02 | 18min | 3 tasks | 6 files |
| Phase 14 P03 | 20min | 2 tasks | 2 files |
| Phase 14 P04 | 15min | 2 tasks | 3 files |
| Phase 14 P05 | 15min | 2 tasks | 2 files |
| Phase 15 P01 | 5min | 3 tasks | 2 files |

## Accumulated Context

### Decisions

Full decision log lives in PROJECT.md Key Decisions and the milestone roadmaps. Highlights most relevant to v1.3:

- Layered cog → service → model architecture; services wired in `bot.py:_initialize_once` — `TasteService` (Phase 14) and `cogs/vision.py` (Phase 17) slot in the same way, no redesign.
- `MemoryService.recall/remember/distill` (Phase 11) is kind-agnostic by design — taste episodes (Phase 13) are just a new `kind`, zero code change needed in `services/memory.py`/`models/memory.py`.
- Flavor-vs-numbers split / accuracy firewall (Phase 11, reaffirmed for v1.3): qualitative narrative flows through vector memory; anything that drives a ranking decision (auto-queue, taste-graph adjacency) comes from live SQL, never embedded text.
- Global Gemini 15 RPM limiter with priority tiers; embeddings use a **separate** ~60 RPM limiter (Phase 11) — vision (Phase 17) shares the 15 RPM chat budget at priority 2, not the embed limiter.
- Gemini 2.5-series models default `safety_settings` to OFF when unspecified — vision (Phase 17) must set them explicitly; whether to retrofit `/ask`/`/imagine` is an open decision for that phase (VIS-03).
- `/memory forget` (Phase 15) must ship and be verified as a real hard-delete before proactive callbacks (Phase 16) — the required escape hatch; hard dependency, do not reorder.
- Pure-logic TDD seam (`logic/*.py`, Phase 10 convention): `logic/taste.py` (Phase 14) and `logic/vision.py` (Phase 17) follow the same mock-free pattern.
- [Phase 13]: taste_episode salience weight set to 0.4, below MEMORY_DECAY_SALIENCE_FLOOR (0.5) per D-04, so taste rows are sweep-eligible and fads age out per D-05 self-refresh intent
- [Phase 13]: MEMORY_DECAY_DAYS_BY_KIND introduced as a new mapping (not a modification to MEMORY_DECAY_DAYS) so Phase 11 kinds fall back unchanged
- [Phase 13]: classify_artist precedence is OBSESSION greater than NEW_ARRIVAL greater than STEADY greater than DROPPED_OFF greater than NONE; skips_in_window accepted for future-proofing but not consulted yet
- [Phase 13]: get_active_taste_users is a deliberately global aggregate (not guild-scoped) — each row carries its own guild_id/user_id so no cross-user merge occurs
- [Phase 13]: refresh_memory_expiry is the D-05 self-refresh primitive: an expires_at-only UPDATE sibling to bump_memory_hit, verified via test to leave hit_count/salience/last_seen_at untouched
- [Phase 13]: remember() dedup/insert branches gate strictly on kind in MEMORY_DECAY_DAYS_BY_KIND (D-05 fix) so taste_episode self-refreshes expires_at on dedup while all Phase 11 kinds stay byte-identical
- [Phase ?]: [Phase 13]: taste_distill_batch scheduled at TASTE_DISTILL_BATCH_HOUR (05:00 UTC), the only free slot distinct from cache_cleanup/memory_sweep/memory_distill_batch/ytdlp_update, per D-06/D-07
- [Phase ?]: [Phase 13]: taste_distill_batch carries guild_id through to distill_and_remember (unlike daily_batch's None) since taste is guild-scoped listening
- [Phase 14]: OQ2 anchor discrepancy resolved as Option B - get_user_top_artist derives the /discover anchor from guild-scoped song_history, not the guild-less user_artist_counts table
- [Phase 14]: OQ1 resolved - search_memories/recall kind param defaults to None and omits the SQL clause entirely when unset (never kind IS NULL), byte-identical to pre-Phase-14 behavior
- [Phase 14]: get_artist_cooccurrence co-occurrence = same-guild-calendar-day bucket join over song_history, a guild-wide aggregate with no per-user attribution
- [Phase 14]: select_positive_taste_context checks the cap BEFORE appending (not after, as in the RESEARCH.md reference snippet) so cap=0 returns [] instead of one item — Fixes an off-by-one bug found while writing the cap=0 test case (Rule 1)
- [Phase 14]: Auto-queue positive-taste recall anchor fixed to a stable string (music taste and listening preferences) per OQ#3 discretion
- [Phase 14]: /discover cold-start guards call the bare pick_random (re-exported from personality.roasts -> personality.responses) rather than the file's pick_random_r alias, since both resolve to the identical function object
- [Phase 14]: DiscoverQueueView confirm-to-queue button seeds only the top adjacent artist (adjacent_artists[0]), a single unambiguous one-shot action rather than a multi-select
- [Phase ?]: [Phase 14]: jam_suggest collects lightweight title/artist/url candidates during search/validate, deferring full async_extract (duration/thumbnail) to the Confirm callback -- mirrors try_auto_queue's search-then-extract split
- [Phase ?]: [Phase 14]: /jam suggest is the second and final Phase 14 surface to reuse the one-shot confirm-view pattern established by /discover (14-04) -- finite timeout, not setup_hook-registered
- [Phase 15]: list_user_memories caller must pass config.MEMORY_MAX_PER_USER, never MEMORY_INJECT_CAP, so the /memory view never truncates below what forget erases — Pitfall 2 / T-15-04 guard

### Pending Todos

None.

### Blockers/Concerns

- [Parked] The 24/7 live deploy remains parked behind the YouTube datacenter-IP block; unrelated to v1.3 scope. See Deferred Items.
- Phase 16 (proactive callbacks) is hard-blocked on Phase 15's `/memory forget` shipping and being verified as a real deletion — do not reorder or parallelize past this gate.

## Deferred Items

Carried forward from v1.2 milestone close (2026-07-01) — all UAT/verification, all `human_needed` live-Discord checks, zero code gaps. None are in v1.3 scope; all resume when a Pi / always-on residential host exists.

| Category | Item | Status |
|----------|------|--------|
| uat | Phase 09 — `09-HUMAN-UAT.md` (6 pending: truthful `/health` degraded, task-failure surfacing live) | Blocked on live Discord/host |
| uat | Phase 11 — `11-HUMAN-UAT.md` (3 pending: live RAG recall + callback-roast behavior) | Blocked on live Discord/host |
| verification | Phase 09/11 — `*-VERIFICATION.md` (`human_needed`) | Blocked on live Discord/host |
| requirement | DEPLOY-02/03/05/08 — standing live-UAT, human-UAT scenarios, restart persistence, keepalive cron all live-in-production | Blocked on 24/7 host |
| uat/verification | Phases 03-06 `*-HUMAN-UAT`/`*-VERIFICATION`/`05-UAT-RUNBOOK.md` — carried v1.1 live-deploy checks | Blocked on 24/7 host |

Full detail (13 items) in MILESTONES.md v1.2 "Known Gaps" section.

## Session Continuity

Last session: 2026-07-02T17:51:09.040Z
Stopped at: Completed 15-01-PLAN.md
Next: Phase 14 complete (5/5 plans) — ready for `/gsd-verify-phase 14`
</content>
