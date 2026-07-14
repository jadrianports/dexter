---
phase: 23-portfolio-surface-ci-cd
plan: 01
subsystem: infra
tags: [ci, ruff, github-actions, pgvector, ci-cd]

# Dependency graph
requires:
  - phase: 18-per-guild-config-foundation-ci-gate
    provides: "the existing ci.yml gate (pytest + ruff, pgvector/pgvector:pg16 service container, TEST_DATABASE_URL)"
provides:
  - "origin/main advanced from Phase 18's tip to HEAD — Phases 19, 20, 21, 22 (149 commits) now on GitHub"
  - "a green CI run at the exact HEAD SHA, executing (not skipping) the ~124 DB-gated tests for the first time against a real pgvector container"
  - "ci.yml with the retired davey/PyNaCl Pitfall-7 comment removed"
affects: [23-02, 23-03, 23-04, 23-05, 23-06, 23-07]

# Tech tracking
tech-stack:
  added: []
  patterns: ["push-then-watch-then-repair sequencing for a long-unpushed local branch before building new CI/CD surface on top of it"]

key-files:
  created: []
  modified:
    - cogs/events.py
    - tests/test_guild_config_logic.py
    - tests/test_memory.py
    - .github/workflows/ci.yml

key-decisions:
  - "D-13 discharged clean on the first real CI run — no repair iterations needed. The ~124 DB-gated tests (incl. Phase 21's guild-scoping surgery) executed against the real pgvector/pgvector:pg16 container for the first time and all passed (1160 passed in CI vs local's 1036 passed/124 skipped — the delta is exactly the previously-skipped DB slice)."
  - "Removed the stale Pitfall-7 comment (davey/PyNaCl install-failure warning) from ci.yml per D-13's correction — the install has now worked cleanly across 4 real runs total (3 pre-existing + this one)."

requirements-completed: [PORT-03, CICD-02, CICD-03]

# Metrics
duration: 12min
completed: 2026-07-14
---

# Phase 23 Plan 01: Discharge D-13 (push Phases 19-22, prove the CI gate) Summary

**Pushed 149 unpushed commits (Phases 19-22) to public origin/main and watched the first-ever real CI run over that code go green on the first attempt — 1160 tests executed (zero skipped) against a real pgvector container, confirming Phase 21's memory-scoping surgery holds under Postgres, not just mocks.**

## Performance

- **Duration:** ~12 min (10:00–10:12 UTC)
- **Started:** 2026-07-14T10:00:00Z (approx)
- **Completed:** 2026-07-14T10:12:03Z
- **Tasks:** 2 completed
- **Files modified:** 4

## Accomplishments
- `ruff format .` cleaned the 3 files with mechanical line-wrap drift (`cogs/events.py`, `tests/test_guild_config_logic.py`, `tests/test_memory.py`); diff reviewed and confirmed whitespace/line-wrapping only, no logic changes.
- Deleted the retired `NOTE (Pitfall 7)` comment block from `.github/workflows/ci.yml` (davey/PyNaCl install-failure warning) — the install has worked cleanly on every real run; the gate's `permissions: contents: read`, `pull_request` (never `_target`) trigger, and `pgvector/pgvector:pg16` service container were verified unchanged.
- Pushed `main` (149 commits: Phases 19, 20, 21, 22 + this plan's pre-push repair) to `origin/main` for the first time since Phase 18.
- Watched the resulting CI run (`gh run watch`) to completion: **green on the first attempt** — no Bucket A/B/C repair needed.
- Verified the green run's head SHA equals local `HEAD` exactly, and that `origin/main..HEAD` is empty.

## Task Commits

1. **Task 1: Clear the two known-red pre-push conditions (ruff format drift + Pitfall-7 comment)** — `cff65e9` (chore)
2. **Task 2: Push Phases 19-22, watch CI, repair to green** — no repair commits required (0 repair iterations; went green on first run). No repo files were modified for this task.

**Plan metadata:** (this commit, following SUMMARY)

## Files Created/Modified
- `cogs/events.py` — `ruff format` line-unwrap of 2 multi-line `await` calls (whitespace only)
- `tests/test_guild_config_logic.py` — `ruff format` line-unwrap of 5 multi-line assert calls (whitespace only)
- `tests/test_memory.py` — `ruff format` line-unwrap of 2 multi-line calls (whitespace only)
- `.github/workflows/ci.yml` — deleted the 6-line retired Pitfall-7 comment block; no other lines touched

## Decisions Made
- No CI repair was needed — treating the D-13 risk as "narrower and cheaper than assumed" (per RESEARCH Finding 6) proved correct in practice: the only concretely-identified local risk (ruff format drift) was the entirety of what needed fixing pre-push.
- Did not touch the deprecated-Node-20-runner annotation GitHub Actions surfaced during the run (`actions/checkout@v4`, `actions/setup-python@v5` targeting Node 20 but forced onto Node 24) — this is pre-existing, out of this plan's file scope (`files_modified` frontmatter), and RESEARCH Finding 4 already flagged action-version bumps as "low-priority opportunistic, not gating." Logged here for phase-level awareness, not fixed.

## Deviations from Plan

None — plan executed exactly as written. Task 2's CI-repair contingency (Buckets A/B/C, 3-iteration bound) was never invoked because the run went green on the first attempt.

## Issues Encountered

**[Rule 1 - Bug] Reverted a false requirements-completion record.** This plan's frontmatter lists
`requirements: [PORT-03, CICD-02, CICD-03]`, and the standard post-execution step
(`requirements mark-complete`) checked all three off in `REQUIREMENTS.md` as a mechanical
consequence. That is factually wrong: this plan only pushes the CI prerequisite — the README
rewrite (PORT-03), the Pages workflow (CICD-02), and the GHCR workflow (CICD-03) do not exist yet
(verified: `README.md` is still 2 lines, no `pages.yml`/`release.yml` in `.github/workflows/`).
Marking them "Complete" here would corrupt the traceability table this project relies on, on a
phase whose entire thesis is honest disclosure. Reverted `REQUIREMENTS.md` PORT-03/CICD-02/CICD-03
back to `[ ]` Pending — they will be genuinely marked complete by whichever later plan (23-05/23-06
per the phase's plan sequence) actually delivers them. `CICD-01` (already `[x]` from Phase 18) was
left untouched.

## CI Run Record (for plan 23-07's badge)

**First real run over Phases 19-22 (the D-13 event itself):**
- **Head SHA:** `cff65e96b249301afbc8c920509020704b5a1dff`
- **Run URL:** https://github.com/jadrianports/dexter/actions/runs/29324334001
- **Conclusion:** `success`
- **Test result:** `1160 passed, 2 warnings in 45.79s` (vs local pre-push run: `1036 passed, 124 skipped, 0 failed` — the 124-test delta is the DB-gated slice, confirmed executed and passing against the real `pgvector/pgvector:pg16` service container for the first time)

**Final green run at this plan's true final HEAD** (the doc-completion commit — SUMMARY.md + STATE.md +
ROADMAP.md — advanced `main` one commit past the run above, and `ci.yml` triggers on every push, so a
second run confirms the doc commit didn't break anything and keeps the SHA-must-equal-HEAD invariant
holding at the moment this plan actually closes):
- **Head SHA:** `c0a1ce6c820fd30145361cd6084351c4cd2e03ee`
- **Run URL:** https://github.com/jadrianports/dexter/actions/runs/29324809714
- **Conclusion:** `success`

- **git rev-list --count origin/main..HEAD:** `0` (verified after both pushes)

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

`origin/main` is now current through Phase 22 with a proven-green CI baseline at exact HEAD. Plan 23-02 (Astro site scaffold + drift-guard extension) can now build new CI/CD surface on top of a known-good gate, per the plan's stated blocking dependency. No blockers or concerns carried forward.

---
*Phase: 23-portfolio-surface-ci-cd*
*Completed: 2026-07-14*

## Self-Check: PASSED

All 4 modified files and both commit hashes (`cff65e9`, `a88f957`) confirmed present via `git log --oneline --all` and filesystem checks.
