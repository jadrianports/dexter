---
phase: 05-ship-it-live
plan: 02
subsystem: infra
tags: [bash, docker-compose, postgres, oci, pg_restore, asyncpg, pytest]

# Dependency graph
requires:
  - phase: 05-ship-it-live plan 01
    provides: pre-deploy bug fixes (clear_persisted gaps, reconnect race guard, TZ-correctness)
provides:
  - scripts/deploy.sh: D-13 git-pull + --build-bot rebuild workflow with down -v guard
  - scripts/backup.sh: 6-hour cron cadence (0 */6 * * *)
  - scripts/lifecycle-policy.json: 14-day OCI Object Storage auto-delete rule for dexter_ prefix
  - scripts/seed_restore_test.py: D-15 non-destructive seed → backup → restore-verify → teardown (throwaway DB only)
  - tests/test_seed_restore.py: pure pytest for build_seed_rows() data shape (17 tests green)
affects: [05-ship-it-live plan 03 runbook, DEPLOY-01, DEPLOY-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "scripts/__init__.py: makes scripts/ importable as a Python package for pure-function tests"
    - "build_seed_rows() pure importable function: no IO, unit-tested without DB"
    - "docker compose exec postgres pg_restore (Option B): version-matched restore avoids host pg_restore mismatch"
    - "THROWAWAY_DB constant: security guard preventing live DB from being passed to pg_restore/dropdb"

key-files:
  created:
    - scripts/deploy.sh
    - scripts/lifecycle-policy.json
    - scripts/seed_restore_test.py
    - scripts/__init__.py
    - tests/test_seed_restore.py
  modified:
    - scripts/backup.sh

key-decisions:
  - "deploy.sh uses --build bot (not --build) to rebuild only the bot image; Postgres image is pinned and never rebuilt"
  - "OCI lifecycle policy scoped to dexter_ prefix only — other bucket objects unaffected"
  - "pg_restore runs via docker compose exec (Option B) to guarantee version parity with pg_dump server"
  - "build_seed_rows() is pure (no IO) so tests can import and validate shape with no DB connection"
  - "scripts/__init__.py added as deviation (Rule 3) because tests could not import from scripts package without it"

patterns-established:
  - "Pure importable helper in a script: separate build_seed_rows() from main() so the shape is unit-testable"
  - "Throwaway DB safety: THROWAWAY_DB constant + acceptance grep ensure live DB name never reaches destructive ops"
  - "Dump integrity guard: check MIN_DUMP_SIZE_BYTES before asserting restore success (guards Pitfall 5)"

requirements-completed: [DEPLOY-01, DEPLOY-07]

# Metrics
duration: 6min
completed: 2026-06-12
---

# Phase 05 Plan 02: deploy.sh + backup cadence + OCI lifecycle + seed/restore-verify Summary

**deploy.sh (D-13), 6-hour backup cron + 14-day OCI lifecycle policy (D-14), and non-destructive pg_restore round-trip script with pure pytest (D-15) — all five helper artifacts verified syntax-clean and test-green on the dev machine**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-12T10:38:45Z
- **Completed:** 2026-06-12T10:44:54Z
- **Tasks:** 2 (Task 1: 3 files; Task 2 TDD: 3 commits — RED, GREEN, impl)
- **Files modified/created:** 6

## Accomplishments

- `scripts/deploy.sh`: D-13 update workflow — git pull → `docker compose up -d --build bot` → tail logs → healthcheck ping; loud multi-line `down -v` warning; no secrets hardcoded
- `scripts/backup.sh`: cadence comment updated from `*/30 * * * *` to `0 */6 * * *` (4 dumps/day); no functional code change
- `scripts/lifecycle-policy.json`: valid OCI Object Storage lifecycle JSON; 14-day DELETE rule scoped to `dexter_` prefix; user applies via `oci os object-lifecycle-policy put`
- `scripts/seed_restore_test.py`: D-15 non-destructive restore proof — seeds 1 user_profiles + 3 song_history + 2 user_artist_counts, runs backup.sh, downloads newest OCI dump, validates size, restores into `dexter_restore_test` via `docker compose exec` (version-matched), asserts row counts, drops throwaway DB
- `tests/test_seed_restore.py`: 17 pure tests (TestSeedData + TestTzAwareHour) — green with no asyncpg, no DB fixture, no pytest.mark.asyncio

## Task Commits

1. **Task 1: deploy.sh + backup.sh cadence + lifecycle-policy.json** - `307739d` (feat)
2. **Task 2 RED: failing test for seed-row shape** - `96d8c4a` (test)
3. **Task 2 GREEN: seed_restore_test.py implementation** - `73c66b8` (feat)

## Files Created/Modified

- `scripts/deploy.sh` — D-13 git-pull + rebuild bot workflow; healthcheck ping; down -v guard
- `scripts/backup.sh` — cadence comment updated to `0 */6 * * *` (2 lines only)
- `scripts/lifecycle-policy.json` — OCI 14-day auto-delete lifecycle rule for dexter_ prefix
- `scripts/seed_restore_test.py` — D-15 non-destructive seed → backup → restore-verify script; `build_seed_rows()` is pure/importable
- `scripts/__init__.py` — makes scripts/ a Python package (deviation, see below)
- `tests/test_seed_restore.py` — 17 pure pytest tests; imports build_seed_rows() from scripts package

## Decisions Made

- `deploy.sh` uses `--build bot` specifically — never bare `--build` — so Postgres is never rebuilt and named volumes are safe
- `docker compose exec postgres pg_restore` (Option B) chosen over host pg_restore to guarantee version parity with the pg_dump server inside the container (Pitfall 4 from RESEARCH.md)
- `build_seed_rows()` extracted as a pure function importable by tests; `main()` is the async IO orchestrator — clean separation of pure logic and side effects
- Dump size guard (`MIN_DUMP_SIZE_BYTES = 1024`) added to catch the pipe-masks-failure pitfall (Pitfall 5)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added scripts/__init__.py to make scripts/ importable as a Python package**
- **Found during:** Task 2 (GREEN phase — running pytest)
- **Issue:** `from scripts.seed_restore_test import build_seed_rows` requires `scripts/` to be a Python package with `__init__.py`. Without it, the import would fail at test collection.
- **Fix:** Created `scripts/__init__.py` with a one-line docstring comment.
- **Files modified:** `scripts/__init__.py` (new)
- **Verification:** `python -m pytest tests/test_seed_restore.py -q` passes 17 tests
- **Committed in:** `73c66b8` (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 — blocking import)
**Impact on plan:** Required for the test import to work; zero functional scope change.

## Issues Encountered

None — all acceptance criteria passed on first run.

## User Setup Required

**External services require manual configuration (from plan frontmatter):**

- **Oracle Cloud Infrastructure OCI CLI:** Apply the 14-day lifecycle policy once to the `dexter-backups` bucket:
  ```bash
  NAMESPACE=$(oci os ns get --query 'data' --raw-output)
  oci os object-lifecycle-policy put \
    --namespace-name "${NAMESPACE}" \
    --bucket-name dexter-backups \
    --items file://scripts/lifecycle-policy.json
  ```
- **HEALTHCHECK_URL:** Set in the Oracle VM crontab environment (used by `deploy.sh` success ping):
  ```
  HEALTHCHECK_URL=https://hc-ping.com/<your-uuid>
  ```

Live execution of all scripts (deploy.sh, backup.sh crontab update, seed_restore_test.py) is deferred to the runbook (Plan 03) — the user runs these on Oracle.

## Known Stubs

None — all files are ready-to-run scripts and a pure test. No UI rendering or data-source stubs.

## Threat Flags

No new network endpoints, auth paths, or trust boundaries introduced. Threat mitigations confirmed:

| Threat | Mitigation |
|--------|-----------|
| T-05-05: pg_restore over live DB | THROWAWAY_DB constant + grep check confirm live DB name never passed to pg_restore/dropdb/createdb |
| T-05-06: Secrets hardcoded | deploy.sh reads HEALTHCHECK_URL from env; no token/password literals; scripts/__init__.py carries no secrets |
| T-05-08: pg_restore version mismatch | docker compose exec postgres pg_restore (Option B) — version-matched |
| T-05-09: docker compose down -v during deploy | deploy.sh never calls down -v; loud WARNING echo at end |

## Next Phase Readiness

- All five helper artifacts verified on dev machine (syntax-clean, test-green)
- Plan 03 (live-UAT runbook) can be executed; all prerequisite scripts are ready
- User runs deploy.sh, updates crontab to `0 */6 * * *`, applies OCI lifecycle policy, and runs seed_restore_test.py on Oracle per the runbook

## Self-Check

### Files exist:
- `scripts/deploy.sh` — created
- `scripts/backup.sh` — modified (cadence only)
- `scripts/lifecycle-policy.json` — created
- `scripts/seed_restore_test.py` — created
- `scripts/__init__.py` — created
- `tests/test_seed_restore.py` — created

### Commits exist:
- `307739d` — feat(05-02): deploy.sh + backup.sh 6h cadence + OCI lifecycle policy
- `96d8c4a` — test(05-02): add failing test for seed_restore_test pure seed-row shape
- `73c66b8` — feat(05-02): seed_restore_test.py — D-15 non-destructive restore-verify

## Self-Check: PASSED

---
*Phase: 05-ship-it-live*
*Completed: 2026-06-12*
