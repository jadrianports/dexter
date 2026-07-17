---
phase: 28-portfolio-finish-release
plan: 01
subsystem: testing
tags: [pytest, astro, drift-guard, static-site, ci]

# Dependency graph
requires:
  - phase: 23-portfolio-surface-ci-cd
    provides: "site/ Astro static landing page + test_site_drift_guard.py dist-scan convention"
provides:
  - "tests/test_demo_transcript_guard.py — durable committed regression guard locking the
    resolveLine() token->previewSample invariant over the built site/dist/, plus a
    build-independent source-level structural guard over demo-transcript.ts"
  - "Confirmed PORT-05 (the c7fd22e /site redesign) is still true: npm run build boots clean and
    the existing test_site_drift_guard.py still passes 3/3 against a fresh build"
affects: [28-02, portfolio-finish-release]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dist-scan drift guard (SITE_DIST_REQUIRED skip/fail split) applied to a second artifact
      (demo-transcript contract), reusing the exact env var name and skip/fail discipline
      test_site_drift_guard.py established"
    - "Build-independent structural guard as a defense-in-depth companion to a dist-scan guard —
      catches the underlying data-contract violation even without npm run build"

key-files:
  created: [tests/test_demo_transcript_guard.py]
  modified: []

key-decisions:
  - "New sibling test file, not an extension of test_site_drift_guard.py — matches the repo's
    1-topic-per-guard-file convention (test_invite_drift_guard.py, test_site_drift_guard.py,
    test_hosting_drift_guard.py are all single-purpose)"
  - "Asserted the after-hours visual identity via surviving hex values (0a0c11/ffb454), never the
    literal phrase \"after hours\" — that phrase lives only in a stripped CSS comment and would be
    a guaranteed permanent false-failure on a correct build (28-RESEARCH.md Pitfall 1)"
  - "HTML-unescape the built dist/ text before comparing against previewSample strings — Astro's
    templating HTML-entity-escapes apostrophes (I'm -> I&#39;m), so a literal-string comparison
    without unescaping produces a false negative on a correct build"
  - "Build-independent structural guard uses a hardcoded-pair assertion over the 2 known
    dexter-speaker entries (28-RESEARCH.md Open Question 2 recommendation) rather than a generic
    TS parser — proportionate for 2 known array entries"

patterns-established:
  - "_raw_tokens_in(text) -> list[str]: a pure detector function taking an explicit string, fed by
    both the real dist-scan and synthetic tmp_path-shaped positive/negative control strings —
    mirrors the _collect_offenders(paths, canonical) seam from test_invite_drift_guard.py"

requirements-completed: [PORT-05]

# Metrics
duration: 27min
completed: 2026-07-18
---

# Phase 28 Plan 01: Demo-Transcript Drift Guard Summary

**New `tests/test_demo_transcript_guard.py` durably locks the resolveLine() token->previewSample contract over a fresh `site/dist/` build, confirming PORT-05 is still true and closing the "manual grep has zero durability" gap.**

## Performance

- **Duration:** 27 min
- **Started:** 2026-07-18T01:33:00Z (approx, local)
- **Completed:** 2026-07-18T01:47:00Z (approx, local)
- **Tasks:** 2 completed
- **Files modified:** 1 created (`tests/test_demo_transcript_guard.py`)

## Accomplishments
- Confirmed PORT-05's shipped `/site` redesign (`c7fd22e`) is still true: `npm run build` boots
  clean (1 page built) and the existing `tests/test_site_drift_guard.py` passes 3/3 against the
  fresh build.
- Added a new, committed, non-vacuous drift guard (`tests/test_demo_transcript_guard.py`, 4 tests)
  that will fail the build the moment a future edit lets a raw `{{DEXTER_DEMO_LINE_*}}` token (or
  any `{{...}}`-shaped placeholder) leak into shipped `site/dist/` HTML.
- Added a build-independent structural guard over `site/src/data/demo-transcript.ts` that locks
  the token->previewSample pairing invariant even without running `npm run build`.
- Verified the guard is non-vacuous with a mandatory positive control (feeds a literal
  `{{DEXTER_DEMO_LINE_1}}` token through the real detector and asserts it's caught) and a negative
  control (feeds the real resolved `previewSample` strings through the same detector and asserts
  zero false positives).

## Task Commits

1. **Task 1: Build the site clean and confirm the existing PORT-05 guard still holds** - no
   committed file change (produces the gitignored `site/dist/` the new guard reads; verified via
   `npm run build` exit 0 + `pytest tests/test_site_drift_guard.py -q` -> 3 passed)
2. **Task 2: Create tests/test_demo_transcript_guard.py** - `94a78bb` (test)

**Plan metadata:** committed as part of this SUMMARY (see final commit below).

## Files Created/Modified
- `tests/test_demo_transcript_guard.py` - New drift guard: `test_no_raw_token_in_built_demo`
  (dist-scan, D-01.1/D-01.2), `test_dist_scan_detects_a_leaked_token` (mandatory positive
  control), `test_dist_scan_accepts_resolved_preview_samples` (negative control),
  `test_every_unfilled_token_entry_has_a_preview_sample` (build-independent structural guard).

## Decisions Made
- Reused `_repo_root()` from `tests.test_invite_drift_guard` rather than duplicating it (the
  helper is already imported elsewhere in the repo for the same purpose); duplicated the small
  `_site_dist_dir()`/`_dist_html_files()` shape locally plus a new `_dist_css_files()` (needed for
  the hex-identity assertions, which `test_site_drift_guard.py` doesn't currently expose) rather
  than importing across two analog modules — kept the new file self-contained for its own
  dist-scan needs while still sharing the one true `_repo_root()` implementation.
- Generalized the raw-token regex to `\{\{[A-Z0-9_]+\}\}` (any `{{TOKEN}}`-shaped placeholder)
  rather than hardcoding only `DEXTER_DEMO_LINE_*`, so a future differently-named token in the
  same file would still be caught by the identical detector.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] HTML-entity-escaped apostrophe broke the previewSample string comparison**
- **Found during:** Task 2 (writing `test_no_raw_token_in_built_demo`)
- **Issue:** The initial implementation compared the raw `previewSample` string (containing `I'm`)
  directly against the built `dist/index.html` text. Astro's templating HTML-entity-escapes
  apostrophes at build time (`I'm` -> `I&#39;m`), so the literal-string `in` check failed on a
  correct, unregressed build — a false negative that would have made the guard permanently red.
- **Fix:** Added `html.unescape()` around the concatenated dist HTML text before the `in`
  comparison, so the check operates on the decoded plain-text form the browser actually renders.
- **Files modified:** `tests/test_demo_transcript_guard.py`
- **Verification:** `pytest tests/test_demo_transcript_guard.py -q` -> 4 passed (was 1 failed / 3
  passed before the fix).
- **Committed in:** `94a78bb` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Necessary for the guard to be correct against a real Astro build rather than
a false-negative-permanently-red test. No scope creep — the fix stayed entirely within the new
test file the plan already specified.

## Issues Encountered
None beyond the auto-fixed HTML-escaping issue above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- PORT-05's confirmation half (D-01.1/D-01.2) is now durably automated and committed — no further
  action needed for this requirement.
- Plan 28-02 (the D-04 owner runbook for PORT-02/CICD-02/CICD-03) is unblocked and can proceed
  independently; it does not depend on anything this plan produced beyond the phase directory
  already existing.
- Full suite green at 1237 passed / 129 skipped / 0 failed (up from 1233 pre-phase — the 4 new
  tests account for the delta exactly, confirming zero regressions elsewhere).

---
*Phase: 28-portfolio-finish-release*
*Completed: 2026-07-18*

## Self-Check: PASSED

- FOUND: tests/test_demo_transcript_guard.py
- FOUND: .planning/phases/28-portfolio-finish-release/28-01-SUMMARY.md
- FOUND commit: 94a78bb (test(28-01): add demo-transcript token->preview drift guard)
- FOUND commit: 48c6378 (docs(28-01): add plan summary)
