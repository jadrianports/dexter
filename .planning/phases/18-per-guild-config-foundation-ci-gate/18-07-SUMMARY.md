---
phase: 18-per-guild-config-foundation-ci-gate
plan: 07
subsystem: infra
tags: [github-actions, ci, ruff, pytest, pgvector]

# Dependency graph
requires:
  - phase: 18-01
    provides: Ruff adoption + requirements-dev.txt pin (ruff>=0.15,<0.16) + repo-wide clean lint/format
  - phase: 18-02
    provides: tests/conftest.py pgvector codec registration fix (register_vector, extension-first ordering) — the prerequisite that makes the live-DB suite pass rather than error under this CI workflow
  - phase: 18-03..18-06
    provides: guild_config seam (schema, service, logic, bot.py/events.py wiring) — the repo state this workflow gates going forward
provides:
  - .github/workflows/ci.yml — GitHub Actions CI: pytest + Ruff, both blocking, on every push and pull_request
  - pgvector/pgvector:pg16 service container wired to TEST_DATABASE_URL so the ~107 previously-skipped live-DB tests now run in CI
  - Least-privilege workflow trigger/permissions posture (pull_request not pull_request_target, contents: read, zero secrets)
affects: [19-onboarding-admin-setup, 20-owner-control-plane-rate-observability, 21-memory-scoping-guild-data-lifecycle, 23-portfolio-surface-cicd]

# Tech tracking
tech-stack:
  added: [GitHub Actions (.github/workflows/ci.yml)]
  patterns: ["Single combined lint+test CI job", "Service-container-backed live-DB testing with zero secrets", "pull_request (never pull_request_target) + top-level permissions: contents: read as the standing least-privilege CI posture"]

key-files:
  created: [.github/workflows/ci.yml]
  modified: []

key-decisions:
  - "Single combined `test` job (lint + pytest) rather than splitting into parallel jobs — both are fast enough that the extra job-matrix complexity isn't worth it yet (planner's discretion per 18-CONTEXT.md, easy to split later)"
  - "pgvector/pgvector:pg16 image chosen over a plain postgres:16 + manual extension build — the pgvector image ships the extension prebuilt, avoiding an extra apt/build step in CI for zero benefit"
  - "No apt-get build-deps step added preemptively for davey/PyNaCl (Pitfall 7) — the plan explicitly calls for treating the first real CI run as the actual verification, with the fallback step documented as an inline comment instead of speculative code"

requirements-completed: [CICD-01]

# Metrics
duration: 12min
completed: 2026-07-10
---

# Phase 18 Plan 07: GitHub Actions CI Gate Summary

**GitHub Actions workflow gating every push/PR on pytest + Ruff (lint + format check), backed by a pgvector/pgvector:pg16 service container that unskips the ~107 live-DB tests with zero secrets and zero Neon traffic.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-10T (session start)
- **Completed:** 2026-07-10T (this commit)
- **Tasks:** 1
- **Files modified:** 1 (created)

## Accomplishments
- Shipped `.github/workflows/ci.yml`, the last plan of Phase 18 — the green gate every subsequent v1.4 phase (especially Phase 21's memory-subsystem surgery) now executes behind.
- Workflow triggers on `push` and `pull_request` (never `pull_request_target`), declares top-level `permissions: contents: read`, and references zero `secrets.*` — verified via the plan's automated acceptance check.
- Stood up a `pgvector/pgvector:pg16` service container with a `pg_isready` health check and `TEST_DATABASE_URL` pointed at it, so the live-DB test suite (previously skipping on missing `TEST_DATABASE_URL`) now actually runs against a real pgvector-enabled Postgres in CI — made safe by 18-02's earlier `tests/conftest.py` codec-registration fix.
- Three blocking gates in sequence: `ruff check .`, `ruff format --check .`, `pytest -q`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create .github/workflows/ci.yml** - `6beff8c` (feat)

**Plan metadata:** (this commit, docs)

_Note: single-task plan, no TDD split needed (pure YAML infra file)._

## Files Created/Modified
- `.github/workflows/ci.yml` - New GitHub Actions workflow: `test` job on `ubuntu-latest`, `pgvector/pgvector:pg16` service container, Python 3.11 with pip cache, installs `requirements.txt` + `requirements-dev.txt`, runs `ruff check .` / `ruff format --check .` / `pytest -q`, all blocking.

## Decisions Made
- Single combined job rather than split lint/test jobs — matches the research's proposed structure and CONTEXT.md's explicit planner discretion; easy to split into parallel jobs later if CI time grows.
- Kept the Pitfall 7 (davey/PyNaCl native-build) mitigation as a documented comment only, not a preemptive `apt-get` step — per the plan's explicit instruction to treat the first real run as the actual verification.
- No README badge, GitHub Pages job, or GHCR job added — those are explicitly Phase 23's job (D-17, CICD-02/03).

## Deviations from Plan

**1. [Verification-only, no code deviation] Adjusted explanatory YAML comments to avoid literal substring collisions with the plan's automated `no pull_request_target` / `no gemini` acceptance checks**
- **Found during:** Task 1 initial verification run
- **Issue:** The first draft included comments explaining *why* `pull_request_target` and `GEMINI_API_KEY` are absent (e.g., "Deliberately `pull_request`, NEVER `pull_request_target`" and "No `GEMINI_API_KEY` here"). The plan's `python -c` acceptance check does a raw substring search for those exact strings anywhere in the file, so the explanatory comments themselves tripped the "not present" assertions even though the actual `on:` trigger and `env:` block were correct.
- **Fix:** Reworded the two comments to convey the same intent without the literal substrings ("NEVER its `_target` variant", "No Gemini API key here") — no change to any functional YAML (triggers, permissions, env, steps unchanged).
- **Files modified:** `.github/workflows/ci.yml`
- **Verification:** Re-ran the plan's exact `python -c` acceptance check — all 8 checks pass (`no pull_request_target`, `push+PR`, `contents read`, `pgvector`, `TEST_DATABASE_URL`, `three gates`, `no secrets`, `no gemini`). Also independently parsed the file with `yaml.safe_load` to confirm valid YAML, and grepped for `badge|Pages|ghcr|GHCR` to confirm none present.
- **Committed in:** `6beff8c` (part of Task 1 commit — comment wording was finalized before the single commit was made, not a separate follow-up commit)

---

**Total deviations:** 1 (verification-driven wording fix, no functional/behavioral change)
**Impact on plan:** None on scope or behavior — purely a comment-wording adjustment discovered while running the plan's own acceptance check before committing.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required. The workflow's actual green-on-runner behavior is manual-only (parked behind an eventual push to a remote), tracked in `18-HUMAN-UAT.md` at phase close per the standing Phase 11/13/14/15/16/17 precedent — not a code gate for this plan.

## Next Phase Readiness
- Phase 18 (Per-Guild Config Foundation & CI Gate) is now code-complete across all 7 plans (18-01 through 18-07).
- CICD-01 is satisfied at the code level; the workflow's actual green run on GitHub's runners (confirming the pgvector container, the ~107 previously-skipped live-DB tests, ruff/pytest gates, and the deliberately-broken-commit red-check proof) remains a manual/human-verified step once the branch is pushed — consistent with every other v1.4/v1.3 live-infrastructure check parked behind the host/push boundary.
- Phase 19 (Onboarding & Admin Setup) can now build `/setup` on top of the `guild_config` seam this phase shipped, executing behind this same CI gate.

---
*Phase: 18-per-guild-config-foundation-ci-gate*
*Completed: 2026-07-10*

## Self-Check: PASSED

- FOUND: `.github/workflows/ci.yml`
- FOUND: `.planning/phases/18-per-guild-config-foundation-ci-gate/18-07-SUMMARY.md`
- FOUND: commit `6beff8c` (feat: add CI workflow)
- FOUND: commit `4075883` (docs: add plan summary)
