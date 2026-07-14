---
phase: 23-portfolio-surface-ci-cd
plan: 03
subsystem: infra
tags: [astro, static-site-generation, oauth2, drift-guard, ci-cd, github-pages]

requires:
  - phase: 23-01
    provides: green CI on origin/main (pushed Phases 19-22) — the baseline this plan builds on
  - phase: 23-02
    provides: human-verified package legitimacy sign-off for `astro` (npm), sanctioning the first npm install in this repo
provides:
  - A building Astro static site skeleton in site/ configured for the /dexter GitHub Pages project-page subpath
  - site/src/config.ts — the one sanctioned cross-language mirror of config.py's invite-URL constants
  - tests/test_site_drift_guard.py — the rebuilt D-02 drift guard that scans BUILT dist/**/*.html instead of tracked source, closing the vacuous-pass hole Astro's SSG choice opened
  - .gitignore/.dockerignore hardening so the Node toolchain can never reach the bot's Docker image
affects: [23-04, 23-05, 23-06, 23-07]

tech-stack:
  added: ["astro@7.0.9 (create-astro@5.2.2 scaffold, minimal template)"]
  patterns:
    - "Built-artifact drift scanning (filesystem rglob over dist/, not git ls-files) as a stronger, SSG-agnostic alternative to source-extension allowlisting"
    - "SITE_DIST_REQUIRED env-var gate converting a graceful local pytest.skip() into a hard CI pytest.fail() — the standard way to make a conditional guard un-skippable in exactly one environment"
    - "Astro set:html on a raw HTML fragment string to bypass attribute-value entity-escaping, when a build-time literal (not client JS) must reach the DOM byte-identically"

key-files:
  created:
    - site/package.json
    - site/package-lock.json
    - site/astro.config.mjs
    - site/src/config.ts
    - site/src/layouts/Layout.astro
    - tests/test_site_drift_guard.py
  modified:
    - site/src/pages/index.astro
    - .gitignore
    - .dockerignore

key-decisions:
  - "Confirmed empirically (not assumed): Astro entity-escapes `&` in interpolated href attributes; fixed with `set:html` on a raw HTML fragment, exactly as UI-SPEC's HARD VERIFICATION GATE anticipated."
  - "Astro resolved to 7.0.9 (create-astro 5.2.2) at scaffold time — newer than RESEARCH's astro_6.3.1-era snapshot, confirming the 'moving target' framing was correct."
  - "package.json's engines field (Astro's own scaffold output) pins Node >=22.12.0 — this is the CI Node version 23-04 should use, not a hardcoded guess from RESEARCH."
  - "tests/test_site_drift_guard.py imports _canonical_url/_collect_offenders directly from tests.test_invite_drift_guard (no extraction to a shared _url_scan.py needed) — the import worked cleanly on the first try since tests/__init__.py already makes tests a real package."

patterns-established:
  - "D-02 built-artifact drift guard: any future generated/templated surface that must carry a policy-controlled literal (URLs, IDs, config values) should be scanned at the rendered-output level, not the template-source level, when the templating layer can fragment or escape the literal."

requirements-completed: [PORT-01, CICD-02]

duration: ~25min
completed: 2026-07-14
---

# Phase 23 Plan 03: Astro Scaffold, Invite URL Wiring, and the Rebuilt Drift Guard Summary

**Stood up an Astro 7.0.9 static site at the `/dexter` GitHub Pages subpath, wired the canonical Discord invite URL into the built HTML via `set:html` (Astro escapes `&` in interpolated attributes — confirmed empirically), and rebuilt Phase 22's drift guard to scan `site/dist/**/*.html` directly instead of tracked source, since Astro's SSG choice made the old `git ls-files`-based guard structurally blind.**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-07-14
- **Tasks:** 3/3
- **Files modified:** 12 (9 new, 3 modified)

## Accomplishments

- `site/` builds cleanly with `npm ci && npm run build`, producing `dist/index.html` with zero client-side JS, configured for the GitHub Pages project-page subpath (`site: 'https://jadrianports.github.io'` + `base: '/dexter'`, D-14).
- The canonical invite URL (`https://discord.com/oauth2/authorize?client_id=1492588698364018898&scope=bot+applications.commands&permissions=309240908864`) reaches the built HTML byte-identically, twice (hero + closing CTA), as static build-time text — never client-side-JS-constructed.
- Rebuilt `tests/test_site_drift_guard.py` to close the vacuous-pass hole: it walks the actual built `dist/` tree (never git-tracked source) and reuses Phase 22's exact comparison seam (`_canonical_url`/`_collect_offenders`, imported not re-declared).
- Proved the guard is a real gate, not a comment: verified both the skip-locally/fail-in-CI split and a deliberately-corrupted invite URl going red, by direct experiment (not by assertion alone).
- `.gitignore`/`.dockerignore` closed before the first `npm install` — `node_modules/` never touched git-staged state.

## Task Commits

Each task was committed atomically:

1. **Task 1: Scaffold the Astro project at the correct subpath** — `9e90339` (feat)
2. **Task 2: Wire the invite URL into the built HTML** — `4a84463` (feat)
3. **Task 3: Rebuild the drift guard against the BUILT artifact (D-02)** — `e67a603` (test)

_No plan-metadata commit yet — created after this SUMMARY, per protocol._

## Files Created/Modified

- `site/package.json`, `site/package-lock.json` — Astro 7.0.9 dependency manifest; lockfile committed (`npm ci` requires it, consumed by 23-04's CI)
- `site/astro.config.mjs` — `site:`/`base: '/dexter'` for correct subpath asset resolution
- `site/src/config.ts` — exports `INVITE_URL`, mirroring `config.py`'s three invite constants with a back-reference comment naming both `config.py` and `logic/invite.py::build_invite_url()`
- `site/src/layouts/Layout.astro` — minimal shell (full head lands in plan 23-05)
- `site/src/pages/index.astro` — renders both CTA anchors via `set:html` on a raw HTML fragment (real content lands in plans 23-05/23-06)
- `tests/test_site_drift_guard.py` — the D-02 built-artifact drift guard + positive/negative controls
- `.gitignore` — added `node_modules/`, `site/dist/`
- `.dockerignore` — added `site/`, `**/node_modules/`

## Decisions Made

- **Astro/Node versions recorded:** `npm view astro version` → `7.0.9`; `create-astro` scaffolder → `5.2.2`. Node pin for CI comes from `site/package.json`'s `engines: { "node": ">=22.12.0" }` (Astro's own scaffold output), not a value hardcoded from RESEARCH's `astro_6.3.1`-era snapshot.
- **`&`-escaping gate outcome (HARD VERIFICATION GATE, settled empirically):** Building with plain `href={INVITE_URL}` interpolation produced `&amp;` in `dist/index.html` (`grep -cF` for the raw canonical string returned 0; `grep -c 'amp;'` returned 1). Fixed per UI-SPEC's prescribed remedy — `Fragment set:html={ctaHtml}` with a raw HTML string built from `INVITE_URL` — which bypasses Astro's attribute-escaping entirely. Post-fix: `grep -oF` for the raw canonical URL in `dist/index.html` returns 2 occurrences (both CTAs); `grep -o 'amp;'` returns 0 anywhere in the file.
- **No extraction to `tests/_url_scan.py` needed:** `from tests.test_invite_drift_guard import _canonical_url, _collect_offenders, _repo_root` imported cleanly on the first try (verified directly, `tests/__init__.py` already makes `tests` a real package) — the RESEARCH-flagged fallback extraction path was not required.
- **Docstring wording avoided the literal substring `discord\.com`-adjacent phrasing** outside the positive control's fake URL, mirroring the Phase 21/22 docstring-avoidance precedent, so the plan's `grep -c 'discord\\.com' tests/test_site_drift_guard.py` acceptance check returns exactly 1 (the positive control only).

## Deviations from Plan

None - plan executed exactly as written. The `&`-escaping fork and the Node-version/Astro-version discretion points were explicitly anticipated by the plan as things to settle empirically at execution time, not deviations from it.

## Issues Encountered

- **Docstring literal-substring collision (self-caught, not a deviation):** the module docstring's first draft quoted a literal URL fragment (`https://discord.com/oauth2/authorize?client_id=${DISCORD_CLIENT_ID}`) to explain why widening the source-scan allowlist wouldn't work. This tripped the plan's own acceptance check (`grep -c 'discord\\.com' tests/test_site_drift_guard.py` expected to return 0 outside the positive control). Reworded the sentence to convey the same explanation without the literal substring; re-verified the grep count dropped from 2 to 1 (the positive control's fake URL only).

## User Setup Required

None - no external service configuration required. (`npm install`/`npm create astro@latest` were already human-verified as legitimate in plan 23-02.)

## Next Phase Readiness

- `site/` is buildable and subpath-correct; `site/src/config.ts::INVITE_URL` is ready for `Hero.astro`/`Cta.astro` to import in plan 23-05.
- `tests/test_site_drift_guard.py` + the `SITE_DIST_REQUIRED` mechanism are ready for plan 23-04's `ci.yml` site job (`npm ci` → `npm run build` → `SITE_DIST_REQUIRED=1 pytest tests/test_site_drift_guard.py`).
- Full suite verified green: 1039 passed, 124 skipped (DB-dependent tests skip locally without `TEST_DATABASE_URL`, consistent with pre-existing project behavior), 0 failed. `tests/test_invite_drift_guard.py` (Phase 22) unchanged, still 9/9 green.
- No blockers for 23-04 (CI/CD workflow wiring).

---
*Phase: 23-portfolio-surface-ci-cd*
*Completed: 2026-07-14*
