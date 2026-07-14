---
phase: 23-portfolio-surface-ci-cd
plan: 04
subsystem: infra
tags: [github-actions, ci-cd, github-pages, ghcr, docker, workflow_run, multi-arch]

requires:
  - phase: 23-portfolio-surface-ci-cd (plan 23-03)
    provides: "site/ Astro project, tests/test_site_drift_guard.py, package.json engines >=22.12.0"
provides:
  - "ci.yml site: job — unprivileged Astro build + D-02 drift scan (SITE_DIST_REQUIRED=1), every push/PR"
  - "pages.yml — CI-gated GitHub Pages deploy skeleton, dual if: filter, head_sha checkout"
  - "release.yml — multi-arch (amd64+arm64) GHCR publish skeleton on v* tags"
affects: [23-05, 23-06, 23-07, milestone-close]

tech-stack:
  added: []
  patterns:
    - "Three-workflow permission-ceiling split: contents:read gate (ci.yml) / pages:write+id-token:write deploy (pages.yml) / packages:write publish (release.yml), never combined via an if: guard"
    - "workflow_run dual-filter gate (conclusion==success AND head_branch==main) + explicit head_sha checkout"

key-files:
  created:
    - .github/workflows/pages.yml
    - .github/workflows/release.yml
  modified:
    - .github/workflows/ci.yml

key-decisions:
  - "Real-run proof (pushing to main, tagging v1.4.0-rc1, curling the Pages URL, observing a skipped gate run) is DEFERRED to the orchestrator's single consolidated phase-end push — this plan is commit-only per explicit executor instructions, so CICD-02/CICD-03 are proven structurally (YAML validity, permission ceilings, trigger correctness) but NOT proven by a real GitHub Actions run in this plan."
  - "setup-python@v6 pinned for the NEW site: job (current latest, re-verified via gh api at execution time); the pre-existing test: job's checkout@v4/setup-python@v5 pins were left untouched per the plan's explicit 'do not touch' instruction."
  - "release.yml tag set: type=ref,event=tag (literal vX.Y.Z-rcN) + semver + sha, flavor latest=auto — a prerelease tag never gets :latest, matching the plan's smoke-test safety requirement."

requirements-completed: []  # PORT-01/CICD-02/CICD-03 intentionally NOT marked — see Deviations

# Metrics
duration: 15min
completed: 2026-07-14
---

# Phase 23 Plan 04: CI/CD Three-Workflow Topology Summary

**Added an unprivileged site-build+drift-scan job to `ci.yml`, and wrote `pages.yml` (CI-gated Pages deploy) + `release.yml` (multi-arch GHCR publish) — all three workflows are structurally correct and locally YAML-validated, but none has actually run yet because this plan is commit-only (no push) by explicit executor instruction.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-14T10:57:10Z
- **Tasks:** 3 (all type="auto")
- **Files modified:** 3 (1 modified, 2 created)

## Accomplishments

- `ci.yml` gained a second job, `site:`, that builds the Astro site (`setup-node` → `npm ci` → `npm run build`) and then runs `tests/test_site_drift_guard.py` with `SITE_DIST_REQUIRED=1` so a missing `dist/` hard-fails instead of silently skipping (D-02). The existing `test:` job's diff is empty — confirmed via `git diff --stat` showing 42 insertions, 0 deletions.
- `pages.yml` created: `workflow_run` on `workflows: ["CI"]` / `types: [completed]`, dual `if:` filter (`conclusion == 'success' && head_branch == 'main'`), explicit `ref: ${{ github.event.workflow_run.head_sha }}` checkout, `pages: write` + `id-token: write` scoped to this file only, `upload-pages-artifact` (`site/dist`) → `deploy-pages` into the `github-pages` environment.
- `release.yml` created: `push: tags: ["v*"]` only, `packages: write` only, QEMU + buildx multi-arch build (`linux/amd64,linux/arm64`), `docker/login-action` against `ghcr.io` using `secrets.GITHUB_TOKEN` only (no new PAT), `metadata-action` tag set (`type=ref,event=tag` + `type=semver` + `type=sha`, `flavor: latest=auto`) so a prerelease tag never becomes `:latest`.
- Action majors re-confirmed live via `gh api repos/<org>/<repo>/releases/latest` at execution time (not just the research snapshot): `checkout@v7`, `setup-node@v7`, `setup-python@v6`, `upload-pages-artifact@v5`, `deploy-pages@v5`, `setup-qemu-action@v4`, `setup-buildx-action@v4`, `login-action@v4`, `metadata-action@v6`, `build-push-action@v7`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the site-build + drift-scan job to ci.yml** - `5d2e927` (feat)
2. **Task 2: pages.yml — the privileged, CI-gated Pages deploy** - `163993f` (feat)
3. **Task 3: release.yml — multi-arch GHCR publish on v* tags** - `7f8b229` (feat)

_No TDD tasks in this plan (pure workflow-config authoring)._

## Files Created/Modified

- `.github/workflows/ci.yml` - new `site:` job (unprivileged, every push/PR); `test:` job byte-identical
- `.github/workflows/pages.yml` - new; CI-gated Pages deploy, main-only, `pages: write`/`id-token: write`
- `.github/workflows/release.yml` - new; multi-arch GHCR publish on `v*` tags, `packages: write`

## Decisions Made

- **Real-run proof deferred, not skipped.** The plan's acceptance criteria call for pushing to `main`, watching a real `Deploy Pages` run, curling `jadrianports.github.io/dexter`, pushing a throwaway branch to observe a **skipped** deploy job, tagging `v1.4.0-rc1`, and watching a real `Release Image` run. This executor was explicitly instructed to commit **locally only** — "Validate workflow YAML locally (e.g. parse it) since you will not push to see it run" — because the orchestrator performs a single consolidated push at phase end (this plan is not the designated push plan; that was 23-01). So this plan delivers structurally-correct, locally-validated workflow files; the real-run proof is the orchestrator's/a later plan's responsibility once the consolidated push happens.
- **setup-python pin for the new job only.** The plan's Task 1 explicitly forbids touching the existing `test:` job's `actions/checkout@v4` / `actions/setup-python@v5` pins (keeps the D-13 baseline signal clean). The new `site:` job's own `actions/setup-python` use was pinned to the current latest major (`v6`, confirmed via `gh api` at execution time) since it is a brand-new action use, not a modification of an existing one.
- **GHCR tag set.** Per D-16/planner's-call, `metadata-action` emits the literal tag ref, semver, and a short-SHA, with `flavor: latest=auto` so a `-rc` prerelease tag is excluded from `:latest` — matching the plan's stated smoke-test safety requirement.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Comment text falsely tripped the `ci.yml` least-privilege grep check**
- **Found during:** Task 1 (verifying acceptance criteria after writing the `site:` job)
- **Issue:** The header comment explaining why the Pages deploy lives in its own file originally read "...needs `pages: write` + `id-token: write`, which this PR-triggered workflow must never grant" — this is prose, but the acceptance check `grep -cE 'pages: write|id-token: write|packages: write' .github/workflows/ci.yml` (correctly, per its own literal design) matches any occurrence of those substrings, including comments, and returned 1 instead of the required 0.
- **Fix:** Reworded the comment to "...needs elevated Pages/OIDC permissions this PR-triggered workflow must never grant" — same meaning, no longer contains the literal grep-target substrings.
- **Files modified:** `.github/workflows/ci.yml`
- **Verification:** Re-ran the grep; now returns `0`. Re-ran the full YAML-parse verification script; still passes.
- **Committed in:** `5d2e927` (Task 1 commit — fixed before commit, not as a follow-up)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** No scope creep — a wording fix caught by the plan's own acceptance grep before commit.

**Scope note (not a deviation, a plan-vs-orchestrator conflict, resolved per orchestrator instruction):** The plan's Tasks 2 and 3 acceptance criteria require real GitHub Actions runs (push to `main`, a throwaway probe branch, a `v1.4.0-rc1` tag push) that this commit-only executor cannot perform without violating the explicit "do NOT push" instruction. This is not an auto-fix under Rules 1-3 (nothing was broken or blocking) — it is a structural constraint from the orchestrator that supersedes the plan's assumption that pushing was available. Resolved by delivering everything provable without a push (YAML validity, permission ceilings, trigger correctness, all grep-based acceptance checks that don't require a live run) and explicitly flagging what remains unproven below.

## Issues Encountered

None beyond the comment-wording fix above.

## What CICD-02 and CICD-03 do NOT yet prove (read this before marking either complete)

Per the plan's own Task 3 instruction ("do not read a green run as CICD-03 done") and the orchestrator's critical_notes, this plan proves the **build/config half** only:

- **CICD-02 (Pages deploy):** `pages.yml` is structurally correct (dual filter, `head_sha` checkout, correct permissions, never PR-triggered) and passes local YAML validation. It has **never run**. Whether it actually publishes a reachable page at `jadrianports.github.io/dexter`, and whether the gate actually skips on a non-`main`/failed run, is unverified until the consolidated push happens and a real `CI` → `Deploy Pages` run completes. **Also structurally blocked-on-human independent of the push:** if the Pages source toggle (plan 23-02 Task 3, "Settings → Pages → Build and deployment → Source: GitHub Actions") was deferred, the first real run of this workflow is expected to fail on the missing `github-pages` environment (Pitfall 5) — that is an acknowledged-deferred `23-HUMAN-UAT.md` item, not a bug in this file.
- **CICD-03 (GHCR publish):** `release.yml` is structurally correct (tags-only trigger, `packages: write` only, multi-arch platforms, `GITHUB_TOKEN`-only auth) and passes local YAML validation. It has **never run** — no `v1.4.0-rc1` tag has been pushed, so the multi-arch build/push has not been observed to actually succeed. Separately, and by design (D-17), the **logged-out-pull half** of CICD-03 can never be proven by this workflow at all — GHCR packages are private by default and visibility is a manual UI flip, carried to `23-HUMAN-UAT.md`.

**REQUIREMENTS bookkeeping:** Per this plan's explicit critical_notes, `PORT-01`, `CICD-02`, and `CICD-03` are **NOT** marked complete in `REQUIREMENTS.md` by this plan. `CICD-02`/`CICD-03` remain blocked on both (a) the orchestrator's consolidated push and a real run, and (b) `CICD-02`'s Pages-source toggle / `CICD-03`'s GHCR-visibility flip, both of which are human/manual steps. `PORT-01` lands in later waves (23-05/23-06) and was never in scope for this plan's file set.

## User Setup Required

None from this plan directly. Two pre-existing acknowledged-deferred items (Pages source toggle, GHCR visibility flip) remain outstanding and will be recorded in `23-HUMAN-UAT.md` at phase close, per D-17 and Pitfall 5.

## Next Phase Readiness

- All three workflow files exist, are locally YAML-valid, and satisfy every acceptance check that does not require a live GitHub Actions run (permission ceilings, trigger scoping, absence of `pull_request_target`, dual-filter presence, tag-set safety).
- **Blocker for the orchestrator/later plan:** the real-run proof (push, observe green `CI` + `Deploy Pages`, observe a skipped gate on a probe branch, tag `v1.4.0-rc1`, observe green `Release Image`) still needs to happen once the consolidated phase-end push lands. Until then, CICD-02 and CICD-03 are code-complete but not evidence-complete.
- 23-05/23-06 (landing page content, README case study) can proceed independently of this plan's real-run proof — they don't depend on Pages/GHCR having actually deployed yet, only on the workflow files existing (which they now do).

---
*Phase: 23-portfolio-surface-ci-cd*
*Completed: 2026-07-14*
