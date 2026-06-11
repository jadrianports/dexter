# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP

**Shipped:** 2026-06-12
**Phases:** 5 (1, 2, 2.5, 3, 4) | **Plans:** 11 GSD-tracked (Phases 3–4) | **Sessions:** not instrumented

### What Was Built
- A complete sarcastic Discord music + AI bot: `/play` engine, `/ask` + `/imagine` via Gemini, and a global priority-tiered rate limiter (Phases 1–2).
- A production-honest hardening pass — unsilenced handlers, FFmpeg orphan cleanup, robust JSON parsing, yt-dlp self-heal (Phase 2.5).
- An "alive" layer: Gemini-first roasts/reactions, seasonal awareness, status rotation, streaks/milestones, `/lyrics` + `/history` (Phase 3).
- A scale pass: SQLite→PostgreSQL (asyncpg), `AutoShardedBot`, queue persistence with smart-rejoin, and a resolved Oracle Cloud A1 hosting decision + Docker Compose packaging (Phase 4).

### What Worked
- **Pure-logic-seam-then-wire.** Extracting testable pure functions (`compute_streak`, lyrics helpers, `Track.to_dict/from_dict`, `parse_suggestions`) before touching Discord/process code gave clean TDD RED→GREEN and isolated the PostgreSQL swap behind serialization seams.
- **Wave-based parallelization.** Phases 3 and 4 each decomposed into 3 dependency-ordered waves, letting independent plans land without rework.
- **Static verification + code review before any live run.** Caught real criticals (pool never closed, `/history` datetime crash, restore bypassing the queue cap) that would only have surfaced in production.
- **Local-boot-only discipline.** Live-concurrency bugs were parked, not fixed blind — keeping every committed fix verifiable by inspection + clean boot.

### What Was Inefficient
- **Bot work is inherently "human_needed" at verification.** A large live-UAT tail (9 Phase-3 + 6 Phase-4 behavioral checks) can't run on the Windows dev machine and had to be carried to deployment — treated correctly as a checklist, but it means "code-complete" ≠ "validated" until the Oracle VM exists.
- **Pre-GSD phases (1/2/2.5) lack per-plan metrics**, requiring a retroactive ingest/bootstrap to reconstruct roadmap + requirements.
- **SUMMARY one-liner drift.** Several Phase-4 summaries produced malformed/truncated one-liners (code symbols instead of prose), and the 03-04 SUMMARY mis-described the final implementation vs. the actual `build_chat_prompt` code.

### Patterns Established
- **Gemini-first with guaranteed template fallback** for all personality output; `priority=2` for every background/ambient AI call.
- **`AllowedMentions.none()` on all unprompted sends** to prevent stray pings.
- **Guards at the source, not the call site** — e.g. the queue cap lives in `MusicQueue.add()` so the playlist loop is covered automatically.
- **Separate accumulators for distinct timers** — idle-loneliness uses `_idle_loneliness_seconds`, independent of the auto-leave `_idle_seconds`.

### Key Lessons
1. Plan a live-UAT checklist from the start of any bot phase — "human_needed" verification is the norm, not a gap to be closed in-session.
2. Put cap/eviction/validation guards at the data structure's source so every code path (including loops) inherits them.
3. Migrate persistence behind pure serialization seams so a DB engine swap is isolated, testable, and reviewable offline.
4. Run static verification + adversarial code review before the first live boot — it catches lifecycle and type-shape bugs cheaply.

### Cost Observations
- Model mix: not instrumented this milestone.
- Sessions: not tracked (mix of pre-GSD and GSD-tracked work).
- Notable: the most expensive surface was verification reasoning over Discord/process code that cannot be unit-tested — pushing that into static structural checks kept it tractable.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | n/a | 5 | Adopted GSD wave-based planning mid-project (Phases 3–4); earlier phases ingested retroactively |

### Cumulative Quality

| Milestone | Tests | Coverage | Notable Deps Added |
|-----------|-------|----------|--------------------|
| v1.0 | 20 files (251+ passing at Phase 3 close) | Not measured (pure-logic TDD + structural review convention) | lyricsgenius, beautifulsoup4, aiohttp, tzdata, asyncpg |

### Top Lessons (Verified Across Milestones)

1. *(Seeded at v1.0 — confirm or revise at v1.1)* Bot/process code is verified structurally + by live UAT, never by unit tests alone.
2. *(Seeded at v1.0 — confirm or revise at v1.1)* Pure seams first, integration wiring second.
