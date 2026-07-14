---
phase: 24-hosting-honesty-docker
plan: 03
subsystem: testing
tags: [pytest, drift-guard, ci, repo-introspection, hosting]

# Dependency graph
requires:
  - phase: 24-01
    provides: scrubbed Koyeb/Oracle prose from runtime code + deleted dead Oracle-era scripts
  - phase: 24-02
    provides: docs/DEPLOY-KOYEB.md removed, docs/DEPLOY-DOCKER.md added, .env.example + CLAUDE.md host-honest
provides:
  - tests/test_hosting_drift_guard.py — permanent CI backstop against Koyeb/Oracle reintroduction (zero-tolerance) and un-allowlisted Render references (allowlist diff)
  - .planning/phases/24-hosting-honesty-docker/24-HOST-UAT.md — parked owner checklist for HOST-03 Docker boot + HOST-04 Render-dashboard deletion
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Repo-introspection drift guard: git ls-files -> exclude sealed archive prefixes + self -> regex scan -> assert zero offenders, with a mandatory positive control proving the scan isn't vacuously passing (established in tests/test_invite_drift_guard.py, now reused for hosting-term drift)"
    - "Zero-tolerance term vs. allowlist-diff term: dead/unambiguous terms (Koyeb, Oracle) get a hard zero-offenders assert; ambiguous terms that double as legitimate English words (Render) get a hardcoded, reviewable (file, line) allowlist instead of a blanket ban"

key-files:
  created:
    - tests/test_hosting_drift_guard.py
    - .planning/phases/24-hosting-honesty-docker/24-HOST-UAT.md

key-decisions:
  - "RENDER_ALLOWLIST derived fresh from the actual post-scrub repo via git grep -niE '\\brender[a-z]*\\b' rather than copied from 24-PATTERNS.md's pre-scrub line-number guesses -- line numbers shifted after the 24-01/24-02 edits, and two files present in the pattern-map's draft list (docs/superpowers/plans/... and README.md) were confirmed either excluded-by-prefix or absent post-scrub, so the final allowlist has 29 entries across 18 files, not the pattern-map's 23"
  - "The 'milestones/' sealed prefix is defensive/currently-vacuous in this repo: milestone docs live nested under .planning/milestones/ (already covered by the .planning/ prefix), so no tracked file starts with a bare top-level 'milestones/' path today. Kept in EXCLUDED_PREFIXES per the plan's literal-string acceptance criterion and documented inline as forward-looking, rather than dropped or faked with a synthetic top-level file"
  - "Guard's self-exclusion check uses filesystem existence (Path.exists()), not git ls-files membership, for its own file -- the guard file is necessarily uncommitted/untracked at the moment its own test first runs (before the introducing commit lands), so a git-tracked-membership assertion would fail on first execution"

requirements-completed: [HOST-01, HOST-02, HOST-03, HOST-04]

# Metrics
duration: 30min
completed: 2026-07-15
---

# Phase 24 Plan 03: Hosting Drift Guard & Parked UAT Summary

**A permanent, non-vacuous pytest guard (7 tests) now fails CI on any future Koyeb/Oracle
reference and enforces an explicit allowlist for the 29 legitimate "render/rendering" English-word
hits across 18 files, backstopped by a parked owner checklist for the Docker boot + Render
dashboard cleanup that can't run in this session.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-07-15 (approx, see git log)
- **Completed:** 2026-07-15
- **Tasks:** 2 completed
- **Files modified:** 2 created (1 test file, 1 UAT doc)

## Accomplishments
- `tests/test_hosting_drift_guard.py` mirrors `tests/test_invite_drift_guard.py`'s shape: a
  `_repo_root()` + `_tracked_non_archive_files()` helper pair (excluding `.planning/`,
  `milestones/`, `docs/superpowers/`, and the guard's own file), a zero-tolerance
  Koyeb/Oracle scan with independent positive controls for both terms, an allowlisted Render
  diff (29 hardcoded `(file, line)` pairs derived from the real post-scrub repo), and a
  guard-of-the-guard test proving the sealed prefixes are tracked-but-excluded, not vacuously
  absent. All 7 tests pass on the real repo; `ruff check` is clean.
- `.planning/phases/24-hosting-honesty-docker/24-HOST-UAT.md` documents the HOST-03 Docker
  boot checklist (env fill, `docker compose up -d --build`, log tail, `/health` curl,
  `dexter.log` silent-failure regression check, drift-guard self-verify) and the HOST-04
  Render-dashboard deletion as blocked-on-human (D-09: zero Render config exists in the repo,
  the connection is entirely dashboard-side).
- Full pytest suite green post-scrub: **1029 passed, 124 skipped, 0 failed** — confirms zero
  runtime-code-path regression across all three Phase 24 plans.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create tests/test_hosting_drift_guard.py** - `1c5ba5c` (test)
2. **Task 2: Write 24-HOST-UAT.md** - `ebe1639` (docs)

_No TDD tasks in this plan (the drift guard is a stdlib repo-introspection test with its own
built-in positive/negative controls, not a behavior-under-test in the traditional RED/GREEN
sense; the UAT doc is documentation-only)._

## Files Created/Modified
- `tests/test_hosting_drift_guard.py` - New: `_repo_root`, `_tracked_non_archive_files`,
  `_scan_for_zero_tolerance_terms`, `KOYEB_ORACLE_PATTERN`, `RENDER_PATTERN`,
  `RENDER_ALLOWLIST` (29 entries), plus 7 test functions (zero-tolerance scan, Render
  allowlist diff, 2 positive controls, 1 negative control, guard-of-the-guard, HOST-02
  file-swap backstop)
- `.planning/phases/24-hosting-honesty-docker/24-HOST-UAT.md` - New: parked HOST-03/HOST-04
  checklist following the established `*-HUMAN-UAT.md` convention

## Decisions Made
- Derived `RENDER_ALLOWLIST` fresh from `git grep -niE '\brender[a-z]*\b'` against the actual
  post-scrub repo rather than copying `24-PATTERNS.md`'s draft line numbers (which predated
  the 24-01/24-02 scrub and would have been stale/wrong).
- Kept the `milestones/` sealed prefix in `EXCLUDED_PREFIXES` per the plan's literal-string
  requirement even though it's currently vacuous in this repo layout (milestone docs live
  under `.planning/milestones/`) — documented inline rather than silently dropped, and the
  guard-of-the-guard test only requires actual tracked content for the two prefixes that have
  it (`.planning/`, `docs/superpowers/`).
- Used filesystem existence rather than git-tracked-membership for the guard's own
  self-exclusion assertion, since the file is necessarily untracked at the moment its own
  test suite first runs (before this plan's own introducing commit).

## Deviations from Plan

None - plan executed exactly as written. One self-correction during execution: the initial
`test_sealed_archives_are_excluded` implementation asserted a tracked file existed directly
under a bare top-level `milestones/` prefix, which failed because milestone docs are actually
nested under `.planning/milestones/` in this repo (already covered by the `.planning/`
prefix) — fixed by scoping that specific assertion to the two prefixes that have real
top-level tracked content and documenting the `milestones/` entry as defensive/forward-looking
in both the test docstring and this summary. No plan-scope change; this was a
test-implementation correction caught by running the test itself (Rule 1 — bug in my own
first draft, not a deviation from the plan's instructions).

## Issues Encountered

- Windows/Git Bash's `git grep -qF <pattern> tests/test_hosting_drift_guard.py` initially
  returned exit 1 because the file was still untracked (git grep only searches the index/tree
  by default, not the raw working directory, unless `--no-index` is used) — resolved by
  `git add`-ing the file before running the acceptance-criteria verification command. No code
  change required; this was a verification-tooling nuance (same category as Phase 24-01's
  `cp1252`-encoding nuance), not a defect.

## User Setup Required

None - no external service configuration required for this plan's own artifacts.
`24-HOST-UAT.md` itself is a checklist the owner will run at a later, separate time (outside
this execution session), per D-08/D-09.

## Next Phase Readiness
- Phase 24 (Hosting Honesty & Docker) is now fully code-complete: all three plans (24-01
  scrub + delete dead scripts, 24-02 docs/env reframe, 24-03 drift guard + parked UAT) are
  committed. HOST-01/02/03/04 are all satisfied at the code level (HOST-03/04 additionally
  parked as human-run/blocked-on-human per D-08/D-09, consistent with every prior phase's
  live-verification precedent).
- The drift guard (`tests/test_hosting_drift_guard.py`) now runs in every future `pytest`
  invocation (including CI) and will fail the build the moment any future phase reintroduces
  a dead Koyeb/Oracle reference or an un-allowlisted Render mention — this closes the loop the
  phase's `<objective>` opened: the 24-01/24-02 scrub is no longer a one-time cleanup with no
  backstop.
- No blockers. Phase 24 ready for phase-level close-out (`/gsd-transition` / phase completion).

---
*Phase: 24-hosting-honesty-docker*
*Completed: 2026-07-15*

## Self-Check: PASSED

- FOUND: tests/test_hosting_drift_guard.py
- FOUND: .planning/phases/24-hosting-honesty-docker/24-HOST-UAT.md
- FOUND: commit 1c5ba5c (Task 1)
- FOUND: commit ebe1639 (Task 2)
- `python -m pytest tests/test_hosting_drift_guard.py -x -q`: 7 passed
- `python -m pytest -q` (full suite): 1029 passed, 124 skipped, 0 failed
- `ruff check .`: All checks passed
