---
gsd_state_version: 1.0
milestone: v1.2
milestone_name: Sharper & Smarter
status: Awaiting next milestone
stopped_at: Phase 12 Plan 04 complete (auto-queue hallucination validation)
last_updated: "2026-06-30T16:21:02.297Z"
last_activity: 2026-06-30 — Milestone v1.2 completed and archived
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 19
  completed_plans: 19
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-01)

**Core value:** A sarcastic, personality-driven music + AI Discord bot that runs reliably 24/7 — playing music, answering `/ask`, and generating images without crashes or orphaned FFmpeg processes.
**Current focus:** Awaiting next milestone (v1.3 — run `/gsd-new-milestone`; standing candidate: Vision / multimodal roasting)

## Current Position

Phase: Milestone v1.2 complete
Plan: —
Status: Awaiting next milestone
Last activity: 2026-06-30 — Milestone v1.2 completed and archived

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
| 09 | 4 | - | - |
| 10 | 4 | - | - |
| 11 | 7 | - | - |

*Updated after each plan completion. Full v1.1 per-plan timings archived in milestones/v1.1-ROADMAP.md.*
| Phase 09 P01 | 613 | 3 tasks | 5 files |
| Phase 09 P02 | 620 | 2 tasks | 3 files |
| Phase 09 P03 | 780 | 3 tasks | 1 files |
| Phase 09 P04 | 546 | 1 tasks | 2 files |
| Phase 10 P01 | 30 | 3 tasks | 6 files |
| Phase 10 P02 | 12 | 2 tasks | 4 files |
| Phase 11 P02 | 17 | 3 tasks | 2 files |
| Phase 11 P03 | 35 | 3 tasks | 5 files |
| Phase 11 P04 | 14 | 3 tasks | 6 files |
| Phase 11-rag-long-term-memory P05 | 1680 | 3 tasks | 8 files |
| Phase 11 P06 | 10 | 3 tasks | 5 files |
| Phase 11 P07 | 28 | 3 tasks | 7 files |
| Phase 12 P02 | 80 | 2 tasks | 6 files |
| Phase 12 P03 | 300 | 2 tasks | 2 files |
| Phase 12-richer-music-ux P04 | 408 | 2 tasks | 4 files |

## Accumulated Context

### Decisions

Full decision log lives in PROJECT.md Key Decisions and the milestone roadmaps. Highlights most relevant to v1.2:

- Layered cog → service → model architecture; services wired in `bot.py:_initialize_once`, attached as bot attributes, accessed via `self.bot.*` — Phase 11 `MemoryService` slots in here, no redesign.
- Global Gemini 15 RPM limiter with priority tiers (sliding-window deque) — Phase 11 embeddings get a **separate** ~60 RPM `_embed_limiter`, never this shared budget.
- Neon-tuned asyncpg pool: `ssl='require'`, `statement_cache_size=0`, 240s lifetime (K-04) — Phase 11 registers the pgvector codec via `init=` (a per-connection codec, NOT a prepared statement, so `statement_cache_size=0` is a verified non-issue).
- Gemini-first personality output with guaranteed template fallback; `priority=2` for all background AI — Phase 11 memory writes are priority-2 background work.
- Pure-logic TDD seam: clock-injectable / module-level pure functions (mirrors `compute_streak`, `_build_ffmpeg_opts`) — the convention Phase 10 extracts to and Phase 11's rerank/dedup functions follow.
- [Phase ?]: HEALTH_STRICT_STATUS defaults true via env-derived bool so Koyeb deployments can opt out without code change
- [Phase ?]: MusicCog degraded check guarded by _ready_done to prevent false-degraded during startup (Pitfall 3)
- [Phase ?]: asyncio.TimeoutError caught before Exception in DB handlers: asyncpg client-side timeout raises TimeoutError not QueryCanceledError
- [Phase ?]: Use -inf sentinel in dedup dict: first post always goes through regardless of clock value in tests
- [Phase ?]: _play_track create_task calls stay as bare asyncio.create_task (Pitfall 4): they handle failures internally, a callback would double-log track errors
- [Phase ?]: asyncio.TimeoutError caught before generic except Exception in on_ready — mandatory in Python 3.11+ where TimeoutError is subclass of Exception (REL-04)
- [Phase ?]: _sync_retry_active module-level bool guard prevents multiple READY shards from spawning concurrent sync-retry chains (Pitfall 5 / REL-03)
- [Phase ?]: first_run sync failure logs and proceeds to bot.close() without background retry — one-shot CLI op has no running event loop to retry into
- [Phase ?]: _is_transient_ytdlp_error returns False only for ExtractorError.expected=True — conservative fallback treats all other errors as transient (A1/A2 [ASSUMED])
- [Phase ?]: async_search/async_extract bounded retry reuses existing update_ytdlp() + _UPDATE_THROTTLE_SECONDS — no second update path added
- [Phase ?]: logic/ top-level package established as the pure-logic seam Phase 11 imports from (D-01 / TEST-01)
- [Phase ?]: Keyword-only primitives for all five playback.py signatures (D-07): each fn stays small, cohesive, and easy to test without mocks
- [Phase ?]: D-02 true extraction: live cog dispatches on TrackEndAction enum — no duplicated/mirrored logic remains in callers
- [Phase ?]: D-02 true extraction: logic/health.py is single source of truth for /health status decision and degraded-reason assembly
- [Phase ?]: logic/health.py keyword-only primitives (D-07): pool_present, db_ok, gateway_ready, ready_done, musiccog_loaded passed from async glue to pure function (D-06 seam)
- [Phase ?]: MEMORY_DEDUP_THRESHOLD raised 0.90→0.92: near-dup pairs 0.937/0.955, distinct max 0.79
- [Phase ?]: MEMORY_SIMILARITY_FLOOR kept 0.70 (high-precision): gemini-embedding-001 compresses scores, strict floor over recall
- [Phase ?]: EMBED_DIM=768 confirmed (keep-768): scoped cosine ANN sufficient — 11-03 uses vector(768), no migration
- [Phase ?]: 11-04
- [Phase ?]: 11-04
- [Phase ?]: 11-04
- [Phase ?]: 11-04
- [Phase ?]: memories=None renders byte-identical prompt; {memory_context} slot with empty-string fallback, no whitespace artifact (T-11-06d)
- [Phase ?]: Cadence gate (random.random() < MEMORY_CALLBACK_CHANCE=0.35) applied per-surface for occasional stat x episode callback (D-04); guild_id='' safe in _build_roast_line (ANN scopes to user_id only)
- [Phase ?]: keeps pure function side-effect-free while giving DB layer a named constant
- [Phase ?]: mirrors decay_predicate; prevents over-broad delete of high-salience expired facts
- [Phase ?]: distinct from ytdlp_update (04:00) and memory_distill_batch (03:00) to avoid thundering-herd on Neon pool
- [Phase 12 P03]: Use /api/search (not /api/get) for LRCLIB — robust to missing duration; returns relevance-sorted array (Pitfall 2)
- [Phase 12 P03]: strip_lrc_headers runs BEFORE sanitize_lyrics — sanitize only handles HTML/@mentions, not LRC metadata lines (Pitfall 1 / T-12-03-04)
- [Phase ?]: Token-set containment over difflib for auto-queue validation (UX-04): YouTube titles are longer than clean names; subset check is semantically correct (D-12)

### Pending Todos

None.

### Blockers/Concerns

- [Parked] All v1.1 deploy/UAT blockers (Koyeb sleep + UptimeRobot, reconnect race, live Neon/Koyeb human-check) plus the new v1.2 Phase 09/11 live-runtime UAT/verification checks remain parked behind the YouTube datacenter-IP block — resume on an always-on residential host. See Deferred Items.

> Resolved at v1.2 close: the Phase 11 numeric-defaults research flag (validated by the 11-02 spike against live Neon) and the `text-embedding-004` → `gemini-embedding-001` correction (applied in Phase 11).

## Deferred Items

**Re-acknowledged and deferred at v1.2 milestone close on 2026-07-01.** The pre-close audit surfaced
13 open items — all UAT / verification, all `human_needed` live-Discord checks. The Phase 03–06 items
are the same parked v1.1 deploy checks (carried below); the two genuinely new v1.2 items are the
Phase 09 and Phase 11 live-runtime checks. None are code gaps — Phases 9–12 are code-complete and
locally/statically verified. All resume when a Pi / always-on residential host exists.

| Category | Item | Status |
|----------|------|--------|
| uat | Phase 09 — `09-HUMAN-UAT.md` (6 pending: truthful `/health` degraded, task-failure surfacing live) | Blocked on live Discord/host |
| uat | Phase 11 — `11-HUMAN-UAT.md` (3 pending: live RAG recall + callback-roast behavior) | Blocked on live Discord/host |
| verification | Phase 09 — `09-VERIFICATION.md` (`human_needed`) | Blocked on live Discord/host |
| verification | Phase 11 — `11-VERIFICATION.md` (`human_needed`) | Blocked on live Discord/host |

**Carried from v1.1 (acknowledged + deferred at v1.1 milestone close on 2026-06-26).** All are live-Discord /
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

Last session: 2026-06-30T11:01:59.358Z
Stopped at: Phase 12 Plan 04 complete (auto-queue hallucination validation)
Next: Execute Phase 12 Plan 04 (auto-queue hallucination validation)

## Operator Next Steps

- Start the next milestone with /gsd-new-milestone
