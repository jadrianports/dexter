---
phase: 24-hosting-honesty-docker
plan: 01
subsystem: infra
tags: [docker, comments, cleanup, host-agnostic]

# Dependency graph
requires: []
provides:
  - Zero live Koyeb/Oracle references in bot.py, config.py, utils/logger.py, utils/embeds.py, Dockerfile, docker-compose.yml
  - Dead Oracle-era ops scripts (backup.sh, deploy.sh, keepalive.sh, lifecycle-policy.json) removed
  - Dead scripts/seed_restore_test.py + orphaned tests/test_seed_restore.py removed
  - Clean pytest collection with the removed module gone
affects: [24-02-docs-templates, 24-03-drift-guard]

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - bot.py
    - config.py
    - utils/logger.py
    - utils/embeds.py
    - Dockerfile
    - docker-compose.yml
    - scripts/__init__.py

key-decisions:
  - "Deleted tests/test_seed_restore.py (not explicitly a research-identified D-11 target) because it is the sole importer of scripts/seed_restore_test.py — required to keep pytest collection green; documented in the plan itself as 'the necessary completion of D-11, not new scope'"
  - "Left CLAUDE.md and docs/DEPLOY-KOYEB.md references to seed_restore_test/backup.sh untouched — those are doc-only and explicitly owned by plan 24-02 per the phase's non-doc/doc split"

patterns-established: []

requirements-completed: [HOST-01]

# Metrics
duration: 12min
completed: 2026-07-15
---

# Phase 24 Plan 01: Scrub Host-Name Prose from Runtime Code & Delete Dead Scripts Summary

**Zero live Koyeb/Oracle references remain in Dexter's runtime Python/Docker files, and five dead Oracle-era-only files (four ops scripts + one orphaned restore-proof test) are gone from the repo.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-15T00:00:00Z (approx, see git log)
- **Completed:** 2026-07-15
- **Tasks:** 3 completed
- **Files modified:** 7 (6 edited, 1 comment-fixed) + 6 deleted

## Accomplishments
- Reworded every hosting-target comment in `bot.py` (health-endpoint docstring, `$PORT` comment block, SIGTERM-cleanup note, K-02 comments), `config.py` (K-07 512MB cap comment), `utils/logger.py` (K-16), and `utils/embeds.py` (D-19) to host-agnostic prose — every `(K-##)`/`(D-##)` tag stayed byte-identical and the `os.environ.get("PORT", "8000")` read + `0.0.0.0:8000` bind are unchanged.
- Reworded `Dockerfile`'s header (K-11/K-12 tags preserved) and `docker-compose.yml`'s Oracle-era-legacy comment to host-neutral phrasing — zero service/volume/env_file changes; `docker compose config -q` still parses clean.
- Deleted the four dead Oracle-era ops scripts (`scripts/archive/backup.sh`, `deploy.sh`, `keepalive.sh`, `lifecycle-policy.json`), the dead `scripts/seed_restore_test.py`, and its sole consumer `tests/test_seed_restore.py`; fixed the now-dangling comment in `scripts/__init__.py`. `pytest --collect-only` still collects 1146 tests with 0 errors.

## Task Commits

Each task was committed atomically:

1. **Task 1: Scrub host-name prose from Python runtime/util comments** - `0795509` (docs)
2. **Task 2: Scrub host-name prose from Dockerfile + docker-compose.yml** - `cc37376` (docs)
3. **Task 3: git rm dead Oracle-era scripts + orphaned test; fix package comment** - `b817f06` (chore)

_No TDD tasks in this plan (prose/deletion only, not behavior-adding)._

## Files Created/Modified
- `bot.py` - Reworded 4 hosting-name comment sites (health docstring, `$PORT` block, SIGTERM note, K-02 block); `$PORT` read and health bind untouched
- `config.py` - Reworded K-07 comment (Koyeb 2GB → 512MB cap, host-neutral)
- `utils/logger.py` - Reworded K-16 comment (Docker/Koyeb → Docker/container)
- `utils/embeds.py` - Reworded D-19 comment (No Oracle/CPU label → No host-CPU label)
- `Dockerfile` - Reworded header (Koyeb-builds-from-git → CI/any-Docker-host), K-11/K-12 preserved
- `docker-compose.yml` - Reworded Oracle-era-legacy comment (comment-only, no service change)
- `scripts/__init__.py` - Reworded package-marker comment to drop the reference to the deleted `seed_restore_test` module
- `scripts/archive/backup.sh` (deleted)
- `scripts/archive/deploy.sh` (deleted)
- `scripts/archive/keepalive.sh` (deleted)
- `scripts/archive/lifecycle-policy.json` (deleted)
- `scripts/seed_restore_test.py` (deleted)
- `tests/test_seed_restore.py` (deleted)

## Decisions Made
- Deleted `tests/test_seed_restore.py` alongside `scripts/seed_restore_test.py` even though the plan's file-modified list already named it — this was called out in the plan itself as the "necessary completion of D-11" since it is the sole importer of the deleted module and pytest collection would otherwise error.
- Left the CLAUDE.md project-structure comment and `docs/DEPLOY-KOYEB.md`'s reference to `seed_restore_test.py`/`backup.sh` untouched by design — this plan's objective explicitly scopes the doc/template half of the scrub to plan 24-02.

## Deviations from Plan

None - plan executed exactly as written. All three tasks matched their `<action>` blocks precisely; no Rule 1-4 auto-fixes were needed.

## Issues Encountered

- The plan's Task 1 acceptance criterion `python -c "import ast; ..."` failed on Windows due to the default `cp1252` console encoding choking on em-dash characters in the source files when reading without an explicit encoding. Re-ran with `encoding='utf-8'` in the `open()` calls (a verification-tooling nuance, not a code issue) — all four files parsed cleanly. No source change required.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Plan 24-02 (docs/templates half of the scrub, replacing `docs/DEPLOY-KOYEB.md` with `docs/DEPLOY-DOCKER.md`) can now proceed — CLAUDE.md and docs/DEPLOY-KOYEB.md still carry the last live Koyeb/Oracle/seed_restore_test references, all deliberately left for that plan.
- Plan 24-03's drift-guard test (`tests/test_hosting_drift_guard.py`) will have a clean baseline to scan against for this plan's six files.
- No blockers.

---
*Phase: 24-hosting-honesty-docker*
*Completed: 2026-07-15*

## Self-Check: PASSED

- All 3 task commits (`0795509`, `cc37376`, `b817f06`) found in git log.
- All 7 modified files (`bot.py`, `config.py`, `utils/logger.py`, `utils/embeds.py`, `Dockerfile`, `docker-compose.yml`, `scripts/__init__.py`) exist on disk.
- All 6 deleted files confirmed gone (`scripts/archive/{backup,deploy,keepalive}.sh`, `scripts/archive/lifecycle-policy.json`, `scripts/seed_restore_test.py`, `tests/test_seed_restore.py`).
