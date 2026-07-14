---
phase: 24-hosting-honesty-docker
plan: 02
subsystem: infra
tags: [docker, docker-compose, neon, docs, env-template, hosting]

# Dependency graph
requires:
  - phase: 24-01
    provides: deleted dead Oracle-era ops scripts (scripts/archive/*, seed_restore_test.py) and scrubbed Koyeb/Oracle prose from Docker infra comments (docker-compose.yml, Dockerfile, bot.py, config.py, utils/logger.py, utils/embeds.py, tests/test_config.py)
provides:
  - Docker+Neon-framed .env.example (Koyeb-secrets framing removed, K-09/K-13 tags and DATABASE_URL split preserved)
  - Host-honest CLAUDE.md hosting narrative (Tech Stack bullets, Phase-5 build-log, log-viewer note, Phase-1 deferred note, stale scripts/ tree entry)
  - docs/DEPLOY-KOYEB.md removed; docs/DEPLOY-DOCKER.md added as the real Docker+Neon run guide
affects: [24-03-hosting-drift-guard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Targeted prose-reframe over rewrite-from-scratch: relabel Koyeb-specific section
      headers/framing while keeping every real value, safeguard note, and (K-##)/(D-##)
      tag byte-identical (D-04/D-07)"
    - "Deploy-doc replacement: read the sibling doc's front-matter shape (Status/
      Environment/Cost) before git rm, then write a lean ~40-80-line doc that documents
      the ACTUAL running flow (docker compose up -> Neon) rather than porting old content"

key-files:
  created:
    - docs/DEPLOY-DOCKER.md
  modified:
    - .env.example
    - CLAUDE.md
    - docs/DEPLOY-KOYEB.md (removed via git rm)

key-decisions:
  - "Dropped the UptimeRobot inbound-keep-alive paragraph from .env.example entirely (not
    repointed to DEPLOY-DOCKER.md) per D-07 — no scale-to-zero concept applies to a
    residential Docker run, so the note has nothing left to describe"
  - "CLAUDE.md's Phase-5 build-log line 1 rewords 'Oracle A1 -> Koyeb WEB + Neon' to a
    host-neutral 'a first cloud WEB-service attempt -> Neon serverless Postgres' rather
    than naming any provider, since the requirement is zero live Koyeb/Oracle references
    anywhere in tracked prose, not just a relabel"
  - "docs/DEPLOY-DOCKER.md explicitly drops the Neon-account walkthrough, UptimeRobot
    setup, Koyeb secrets-UI walkthrough, HeavenCloud/Wispbyte contingency, and the
    archived-scripts table from the old doc — none of that content applies to the real
    docker compose up -> Neon flow"

requirements-completed: [HOST-01, HOST-02]

# Metrics
duration: 15min
completed: 2026-07-14
---

# Phase 24 Plan 02: Docs & Env Template Host-Honesty Summary

**Reframed .env.example and CLAUDE.md from Koyeb-Secrets/production framing to Docker+Neon,
and replaced the 179-line docs/DEPLOY-KOYEB.md with a lean ~76-line docs/DEPLOY-DOCKER.md
documenting the real `docker compose up -d --build` -> Neon flow.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-14T20:33:00Z (approx)
- **Completed:** 2026-07-14T20:48:22Z
- **Tasks:** 3
- **Files modified:** 4 (.env.example, CLAUDE.md, docs/DEPLOY-KOYEB.md deleted, docs/DEPLOY-DOCKER.md created)

## Accomplishments
- `.env.example` now reads as a Docker+Neon template: Koyeb-encrypted-secrets language
  replaced with local-.env/docker-compose framing; the K-09 Healthchecks.io dead-man note
  and the K-13 tags and the local-Postgres-vs-Neon `DATABASE_URL` split all survive verbatim;
  the UptimeRobot/scale-to-zero paragraph is gone (no longer applicable).
- `CLAUDE.md`'s hosting narrative (Tech Stack Containerization/Hosting bullets, the log-viewer
  note, the Phase-1 deferred-item note, and the Phase-5 build-log) is host-honest with zero
  Koyeb/Oracle references, while all five `K-##` tag occurrences (K-04 x2, K-07 x2, K-16) and
  every Critical Rule are untouched. The stale `scripts/` project-structure tree entry (which
  still listed 5 scripts deleted in plan 24-01) is corrected to the two survivors.
- `docs/DEPLOY-KOYEB.md` removed (`git rm`); `docs/DEPLOY-DOCKER.md` added as a 76-line lean
  run guide: prereqs, `cp .env.example .env` + the four secrets, `docker compose up -d --build`,
  `/health` + log-tail verification, an honest on-demand/residential-IP framing paragraph, and
  the single-Discord-token warning — no real secret values anywhere.

## Task Commits

Each task was committed atomically:

1. **Task 1: Reframe .env.example from Koyeb-Secrets framing to Docker+Neon** - `3245349` (docs)
2. **Task 2: Rewrite CLAUDE.md hosting narrative host-honest + update stale scripts/ tree** - `fe76a18` (docs)
3. **Task 3: git rm docs/DEPLOY-KOYEB.md and write the lean docs/DEPLOY-DOCKER.md** - `a5a0964` (docs)

**Plan metadata:** (this commit, docs: complete plan)

## Files Created/Modified
- `.env.example` - Docker+Neon-framed env template; K-09/K-13 tags and DATABASE_URL split preserved
- `CLAUDE.md` - Host-honest Tech Stack/Hosting bullets, Phase-5 build-log, log-viewer note, Phase-1 deferred note, corrected scripts/ tree; five K-## tags preserved
- `docs/DEPLOY-KOYEB.md` - removed (git rm)
- `docs/DEPLOY-DOCKER.md` - new lean Docker+Neon run guide (76 lines)

## Decisions Made
- Dropped (not repointed) the UptimeRobot inbound-keep-alive paragraph from `.env.example` per D-07 — the concept (defeating Koyeb's scale-to-zero) doesn't map to a residential Docker run.
- CLAUDE.md's Phase-5 build-log rewords the Oracle/Koyeb provider names to host-neutral phrasing rather than naming any specific alternate provider, satisfying the zero-live-reference requirement without inventing new provider claims.
- `docs/DEPLOY-DOCKER.md` deliberately omits the old doc's Neon-account walkthrough, UptimeRobot setup, Koyeb secrets-UI steps, HeavenCloud/Wispbyte runner-swap contingency, and archived-scripts table — none of it applies to the actual `docker compose up` -> Neon flow this doc documents.

## Deviations from Plan

None - plan executed exactly as written. One self-correction during execution: the first draft of `docs/DEPLOY-DOCKER.md` came in at 86 lines, above the plan's ~35-80 line acceptance range, so it was trimmed to 76 lines (condensed prereqs/verify sections) before committing — no content was dropped, only redundant phrasing.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required. `docs/DEPLOY-DOCKER.md` is a run guide for the user to follow when they next stand up the bot locally; no action required as part of this plan's execution.

## Next Phase Readiness
- Both must-have truths for this plan (zero Koyeb/Oracle in `.env.example`/`CLAUDE.md`, K-## tag preservation, DATABASE_URL split intact, `docs/DEPLOY-DOCKER.md` present with all D-06 sections) verified via grep before each commit.
- Plan 24-03 (hosting drift guard + `24-HOST-UAT.md`) can now write `tests/test_hosting_drift_guard.py` against a repo state where `docs/DEPLOY-KOYEB.md` is already gone and `docs/DEPLOY-DOCKER.md` already exists — the drift guard's file-existence assertions will pass against real committed state, not a future promise.
- No blockers.

---
*Phase: 24-hosting-honesty-docker*
*Completed: 2026-07-14*

## Self-Check: PASSED

- FOUND: .env.example
- FOUND: CLAUDE.md
- FOUND: docs/DEPLOY-DOCKER.md
- FOUND (correctly absent): docs/DEPLOY-KOYEB.md
- FOUND: commit 3245349 (Task 1)
- FOUND: commit fe76a18 (Task 2)
- FOUND: commit a5a0964 (Task 3)
