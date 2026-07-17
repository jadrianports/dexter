# Phase 28: Portfolio Finish & Release - Research

**Researched:** 2026-07-18
**Domain:** Static-site build verification (Astro), drift-guard test conventions, GitHub Actions release wiring, owner-runbook authoring
**Confidence:** HIGH

## Summary

Phase 28 is a verification + hand-off phase, not a build phase. PORT-05 (the `/site` redesign)
shipped at `c7fd22e` and is still true today — this was confirmed directly in this research
session, not assumed: `npm run build` in `site/` completes clean (1.57s, 1 page), the existing
`pytest tests/test_site_drift_guard.py` passes 3/3 non-vacuously against the fresh build, and a
manual grep of the built `site/dist/index.html` + `site/dist/_astro/*.css` confirms (a) zero raw
`{{DEXTER_DEMO_LINE` tokens leak into shipped HTML, (b) all proper-case copy strings from
`Hero.astro`/`Features.astro`/`Boundaries.astro` are present verbatim in the built output, and
(c) the "after hours" dark identity's actual *color values* (`#0a0c11` background, `#ffb454`
amber accent) survive the build into the shipped CSS — **the literal English phrase "after
hours" does NOT survive the build** (it lives only in a stripped CSS comment), which is a
load-bearing finding for how the D-01.1 grep assertions must be written (see Pitfall 1).

There is no JS/Node test runner in `site/` (`package.json` has no `vitest`/`jest`/test script —
only `dev`/`build`/`preview`/`astro`), so the D-01.2 `resolveLine()` guard test must follow the
existing Python-over-built-`dist/` convention `tests/test_site_drift_guard.py` already
established, reusing its skip/fail split (`SITE_DIST_REQUIRED` env var) so the guard can never
silently vanish in CI. This research also independently confirmed the two owner-facing CI/CD
facts the runbook depends on: GitHub Pages is genuinely NOT yet enabled for this repo
(`gh api repos/.../pages` → 404, checked live), and no `v1.5` tag exists yet (`gh api
repos/.../tags` → tip is `v1.4`) — both facts ground D-04's runbook steps in verified current
state, not assumption.

**Primary recommendation:** Write one new test file (`tests/test_demo_transcript_guard.py`) that
(1) mirrors `test_site_drift_guard.py`'s dist-scan pattern with the same `SITE_DIST_REQUIRED`
skip/fail split, asserting no raw `{{` token and both current `previewSample` strings appear in
`site/dist/index.html`, backed by a positive-control helper test on `tmp_path` fixtures (mirroring
`test_dist_drift_guard_actually_detects_a_mismatch`); and (2) adds a fast, build-independent
source-level structural guard reading `site/src/data/demo-transcript.ts` directly, asserting the
"any unfilled `{{...}}` token must have a non-empty `previewSample`" invariant so the contract is
locked even without running `npm run build`. Ground every D-01.1 grep assertion in the exact
strings captured in this document's Code Examples section — do not invent new ones. Template
`28-HUMAN-UAT.md` on `23-HUMAN-UAT.md`'s structure (numbered tests, `expected:`/`result:` pairs,
a Summary counts block, a Gaps section) with the three items from D-04, explicitly noting the
push-before-Pages-fires dependency (Pitfall 2).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Static site build verification | Build/CI tooling | — | `npm run build` + pytest are local/CI toolchain concerns, not app runtime tiers |
| Demo-transcript token/preview contract | Frontend (Astro build-time) | Test suite | `resolveLine()` runs at Astro build time (SSG, zero client JS for this logic); the guard is a test-tier consumer of that build-time contract |
| GitHub Pages deploy | CDN / Static hosting | CI/CD (GitHub Actions) | `pages.yml` publishes the built `dist/` artifact to GitHub Pages' CDN; the trigger logic lives in CI/CD |
| GHCR image publish | CI/CD (GitHub Actions) | Container registry | `release.yml` builds + pushes to GHCR; visibility flip is a registry-side (GitHub UI) setting, not app code |
| Owner runbook | Documentation | — | `28-HUMAN-UAT.md` is a planning-doc artifact, not a runtime component |

This phase touches no Discord/API/database tier at all — it is entirely build-tooling, static-site,
and CI/CD-adjacent, which is why the map above skips Browser/API/DB rows present in typical phases.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Astro | ^7.0.9 (installed, confirmed via `site/package.json`) | Static site generator for `/site` | Already the project's SSG since Phase 23; zero new dependency for this phase |
| pytest | pinned in `requirements-dev.txt` (already installed; suite green at HEAD) | Test runner for the new D-01.2 guard | Matches every existing drift-guard test (`test_site_drift_guard.py`, `test_invite_drift_guard.py`, `test_hosting_drift_guard.py`) |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Node.js | ≥22.12.0 (repo pins 22 in CI; local machine has v24.16.0, which satisfies the `>=22.12.0` engines constraint) | Runs `astro build` | Only needed for the D-01.1 automated build check and D-01.3 local visual pass |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python dist-scan guard test (recommended) | A Vitest/Playwright test inside `site/` | Would require adding a brand-new JS test runner + dependency just for one guard — disproportionate for a single invariant, and breaks the repo's established "Python asserts over built `dist/`" convention (`test_site_drift_guard.py`, D-02's own docstring explains why this pattern was chosen for Astro specifically) |
| Manual grep-only verification (no committed test) | Ad hoc `grep` commands run once during this phase | Rejected by the user's own D-01 decision — a manual check has zero durability against a future edit; the whole point of D-01.2 is a **committed** regression test |

**Installation:** No new packages required. `site/` already has `astro` installed;
`requirements-dev.txt` already has `pytest`. This phase adds one new test file, no new
dependencies.

**Version verification:** Confirmed directly in this session — `site/package.json` pins
`"astro": "^7.0.9"`; `node --version` → `v24.16.0` (satisfies `engines.node: ">=22.12.0"`);
`npm run build` completed successfully with no errors or warnings.

## Package Legitimacy Audit

**Not applicable — this phase installs zero new packages.** No `npm install` / `pip install` of
any new dependency is in scope; the guard test uses only stdlib (`pathlib`, `os`) plus the
already-installed `pytest`, exactly like the three existing drift-guard test files it mirrors.

## Architecture Patterns

### System Architecture Diagram

```
site/src/data/demo-transcript.ts (source of truth: text + previewSample tokens)
        │
        │  resolveLine(entry) — Astro build-time function
        ▼
site/src/components/DemoMock.astro  (imports resolveLine, calls it 2x)
        │
        │  npm run build  (astro build, static output)
        ▼
site/dist/index.html + site/dist/_astro/*.css  (the shipped artifact)
        │
        ├──► tests/test_site_drift_guard.py       (existing: invite-URL byte-check)
        ├──► tests/test_demo_transcript_guard.py  (NEW, this phase: token-leak + preview-shown)
        │
        ▼
.github/workflows/ci.yml `site` job  (npm run build + pytest, on every push/PR)
        │  on success, on main
        ▼
.github/workflows/pages.yml  (workflow_run trigger, rebuilds independently, deploys to Pages)
        │
        ▼
jadrianports.github.io/dexter  (public URL — LIVE only after the owner's one-time
                                 Settings → Pages → Source = GitHub Actions toggle, D-04)

separately:
git tag v1.5 (cut by /gsd:complete-milestone, NOT this phase — D-02)
        ▼
.github/workflows/release.yml  (push: tags ["v*"] trigger)
        ▼
ghcr.io/jadrianports/dexter:<tag>  (image exists, but PRIVATE until owner flips
                                     package visibility — D-04/D-05, sequenced post-tag)
```

A reader can trace: source contract → build-time resolution → shipped artifact → two independent
test scans of that artifact → CI gate → deploy trigger → public URL. The tag/GHCR path is
deliberately drawn as a separate branch since D-02/D-05 sequence it entirely outside this phase.

### Recommended Project Structure
```
tests/
├── test_site_drift_guard.py          # existing — invite-URL byte-check over dist/
├── test_invite_drift_guard.py        # existing — source-level invite-URL check + helpers reused above
├── test_hosting_drift_guard.py       # existing — Koyeb/Oracle/Render scrub check (pattern precedent)
└── test_demo_transcript_guard.py     # NEW (this phase) — D-01.2 resolveLine()/token-leak guard
.planning/phases/28-portfolio-finish-release/
└── 28-HUMAN-UAT.md                   # NEW (this phase) — the D-04 owner runbook
```

### Pattern 1: Dist-scan drift guard with SITE_DIST_REQUIRED skip/fail split
**What:** A pytest test that reads `site/dist/**/*.html` (never `git ls-files` — dist/ is
gitignored). If `dist/` is missing: skip locally, hard-`fail()` when `SITE_DIST_REQUIRED=1`
(set only inside `ci.yml`'s `site` job) so CI can never silently pass by skipping.
**When to use:** Any guard that must assert something about the *shipped bytes*, not the
`.astro`/`.ts` source — exactly the D-01.2 requirement (the resolved output, not the token).
**Example:**
```python
# Source: tests/test_site_drift_guard.py (existing, verified passing 3/3 against a fresh build
# in this research session)
def _site_dist_dir() -> Path:
    return _repo_root() / "site" / "dist"

def _dist_html_files(dist_dir: Path) -> list[Path]:
    if not dist_dir.exists():
        return []
    return list(dist_dir.rglob("*.html"))

def test_no_drift_in_built_site():
    files = _dist_html_files(_site_dist_dir())
    if not files:
        if os.getenv("SITE_DIST_REQUIRED"):
            pytest.fail("site/dist/ is empty but SITE_DIST_REQUIRED=1 — ...")
        pytest.skip("site/dist/ not built (local run, no `npm run build`)")
    offenders = _collect_offenders(files, _canonical_url())
    assert offenders == []
```
The new `tests/test_demo_transcript_guard.py` should import `_repo_root`, `_site_dist_dir`-style
helpers (or literally reuse `_dist_html_files`/`_site_dist_dir` by importing them from
`test_site_drift_guard` — that module doesn't currently export them as reusable as
`test_invite_drift_guard` does, so either duplicate the ~6-line helper or add the import; either
is small enough to be the planner's discretion call).

### Pattern 2: Positive/negative control via an explicit-path helper function
**What:** The actual detection logic (e.g., "does this text contain a drifted URL / a raw
token?") lives in a small pure function that takes an explicit list of paths or a string,
never internally re-deriving what to scan. Tests then feed synthetic `tmp_path` fixtures through
that exact function to prove a positive case is caught and a negative case is accepted —
without needing to run a real Astro build for the control tests themselves.
**When to use:** Every drift guard in this repo (`_collect_offenders` in
`test_invite_drift_guard.py`, reused unmodified by `test_site_drift_guard.py`). D-01.2 should
follow the identical shape: a `_contains_raw_token(html_text: str) -> bool` (or similar) helper,
exercised by `test_dist_scan_actually_detects_a_leaked_token(tmp_path)` (positive control,
writes a fake HTML file containing a literal `{{DEXTER_DEMO_LINE_1}}` and asserts detection) and
a negative control asserting the real `previewSample` strings do NOT trip it.
**Example:**
```python
# Source: tests/test_site_drift_guard.py:118-131 (verified present, passing)
def test_dist_drift_guard_actually_detects_a_mismatch(tmp_path):
    fake_html = tmp_path / "index.html"
    fake_html.write_text(
        '<a href="...permissions=8...">Add</a>',
        encoding="utf-8",
    )
    offenders = _collect_offenders([fake_html], _canonical_url())
    assert offenders, "dist/ scanner failed to catch a deliberately-wrong invite URL"
```

### Pattern 3: Build-independent structural guard (source-level, no `npm run build` needed)
**What:** A test that reads `site/src/data/demo-transcript.ts` as text (or a small hardcoded
mirror of its current entries) and asserts a structural invariant directly, without requiring a
built artifact. This complements Pattern 1 by catching the underlying data-contract violation
(a token with no fallback) instantly, in environments with no Node/Astro toolchain installed at
all (e.g. a Python-only CI runner, or a contributor without `npm ci` run).
**When to use:** As a defense-in-depth companion to the dist-scan guard, not a replacement — the
dist-scan proves the *shipped bytes* are clean; the structural guard proves the *source contract*
itself can't regress even before a build exists.
**Example (recommended shape, not yet written):**
```python
# NEW pattern for this phase — no direct precedent file, but same spirit as the
# `_CONSTRUCTOR_MARKERS` "small, hardcoded, reviewable literal" discipline used in
# tests/test_invite_drift_guard.py:222 and tests/test_hosting_drift_guard.py:54-60
import re
from pathlib import Path

TOKEN_PATTERN = re.compile(r"\{\{[A-Z_]+\}\}")

def test_every_unfilled_token_has_a_preview_sample():
    src = (_repo_root() / "site" / "src" / "data" / "demo-transcript.ts").read_text(encoding="utf-8")
    # crude but sufficient: each `text: "{{...}}"` object literal in the array must be
    # followed by a `previewSample:` key before the next `text:` — parsed via a small
    # regex/state-machine rather than a full TS parser (planner's discretion on exact
    # parse strategy; the invariant is what matters, not the parser sophistication)
    ...
```

### Anti-Patterns to Avoid
- **Testing only the `.ts` source and never the built `dist/`:** would miss a regression where
  `DemoMock.astro` stops calling `resolveLine()` correctly, or a future Astro/Vite upgrade changes
  how the fallback renders. The dist-scan is the ground truth for "what a browser actually
  receives" (this is literally why `test_site_drift_guard.py` exists as a *separate* file from
  `test_invite_drift_guard.py` — see that file's own docstring, read in this session).
- **Grepping the built CSS for the literal phrase "after hours":** confirmed in this session that
  the phrase lives only inside a CSS comment (`global.css:38`) which is stripped by the Astro/Vite
  minifier at build time (`grep -c "after hours" dist/_astro/*.css` → 0). A D-01.1 assertion
  written against that literal string would be a guaranteed, permanent false failure. Assert
  against the actual surviving identity markers instead — the color hex values (see Code Examples).
- **A bare `pytest.skip()` with no `SITE_DIST_REQUIRED`-style fail path:** would silently
  recreate the exact "vacuous pass forever" hole `test_site_drift_guard.py`'s own docstring
  describes closing for the invite guard — CI must hard-fail if `dist/` is missing, never skip.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Detecting drift between built artifact and source contract | A new bespoke file-walking/HTML-parsing utility | Reuse `_dist_html_files`/`_site_dist_dir`-style helpers already proven in `test_site_drift_guard.py` | Identical problem already solved once for the invite-URL guard; a second, slightly-different implementation risks silently drifting from the first (exactly the failure mode `test_site_drift_guard.py`'s docstring warns about for the invite guard) |
| Verifying GitHub Pages is enabled | A script that polls `gh api repos/.../pages` in CI | Manual `Settings → Pages → Source = GitHub Actions` UI toggle, documented in the runbook | Enabling Pages via API requires an elevated PAT (`administration:write`/`pages:write`) that this project's zero-secrets-in-CI posture (Phase 22 D-04) deliberately does not carry — confirmed as still true: this session's `gh auth status` token scopes are `gist, read:org, repo, workflow` (no `admin:repo_hooks`/Pages-admin scope), and `gh api repos/.../pages` returns 404 live, matching 23-RESEARCH.md's Finding 4 exactly |

**Key insight:** every "don't hand-roll" item in this phase is really "don't reinvent a pattern
this repo already established for an isomorphic problem one phase earlier." Phase 28's entire job
is applying the Phase 22/23 drift-guard discipline to one more artifact, not inventing new
verification machinery.

## Common Pitfalls

### Pitfall 1: The literal phrase "after hours" is not present in the built site
**What goes wrong:** A grep assertion like `assert "after hours" in dist_html` (or the CSS)
will fail permanently — not because the identity is missing, but because it only ever existed
as a source-code comment.
**Why it happens:** `global.css:38`'s `/* Color — warm "after hours" dark. */` comment is
stripped by Astro/Vite's CSS minifier during `npm run build`. Verified directly in this session:
`grep -c "after hours" dist/_astro/*.css dist/index.html` → both return `0` (exit code 1, no
matches) even on a fresh, correct build.
**How to avoid:** Assert against the actual surviving visual-identity markers instead — the
literal hex color values that ARE present in the built CSS: `#0a0c11` (near-black `--color-bg`)
and `ffb454` (amber `--color-accent`), both confirmed present (`grep -c` → `1` each) in
`dist/_astro/index.DdY3oldB.css` in this session.
**Warning signs:** A guard test that references `"after hours"` as a string literal against
`site/dist/` output will be red from the moment it's written, on a correct, unregressed build.

### Pitfall 2: "GitHub Pages toggle done now" ≠ "page live now" — a push-to-main gap exists
**What goes wrong:** D-04/D-05 correctly frame the `Settings → Pages → Source = GitHub Actions`
toggle as doable immediately with zero tag dependency. But `pages.yml` only fires on
`workflow_run: ["CI"] completed` — which itself only fires on a push/PR to the repo. Confirmed
in this session: the local `main` branch is **92 commits ahead of `origin/main`**
(`git rev-list --count origin/main..HEAD` → `92`), meaning `ci.yml` has not run against any of
that work, and `pages.yml` therefore cannot have fired for it either, independent of whether the
Pages source is set.
**Why it happens:** The toggle and the deploy are two separate preconditions that both must be
true (Pages source = GitHub Actions AND a successful CI run on `main`) before the site goes live;
D-04's runbook already implies this via "the already-wired pages.yml deploys on the next
CI-success-on-main" but the planner should make the push dependency an explicit, separate
runbook step so the owner doesn't conclude the toggle alone is sufficient.
**How to avoid:** In `28-HUMAN-UAT.md`, sequence the CICD-02 test as: (1) toggle Pages source now
— host-independent, doable immediately; (2) note explicitly that step 1 alone does not publish
anything — the first real `pages.yml` run additionally needs a push to `origin/main` that passes
`ci.yml` (a repo-wide event, not scoped to this phase); (3) once both have happened, verify the
public URL.
**Warning signs:** Owner reports "I flipped the toggle but the site isn't live" — expected until
the next successful push-triggered CI run on `main`.

### Pitfall 3: No `v1.5` tag exists yet — CICD-03 literally cannot be attempted
**What goes wrong:** Attempting to "flip GHCR visibility" before a tag exists has nothing to
flip — the package doesn't exist on GHCR until `release.yml` runs at least once.
**Why it happens:** Confirmed in this session via `gh api repos/jadrianports/dexter/tags` — the
most recent tag is `v1.4`; no `v1.5` tag exists. `release.yml` triggers only on `push: tags:
["v*"]`.
**How to avoid:** This matches D-02/D-05 exactly — do not attempt CICD-03 inside Phase 28. The
runbook documents it as the *first thing to do right after* `/gsd:complete-milestone` cuts the
`v1.5` tag, not as a Phase 28 action item to execute now.
**Warning signs:** None expected — this is already correctly scoped out by D-02/D-05; flagged
here only as confirmation the assumption behind that decision is accurate at research time.

## Code Examples

Verified strings and values from the actual built artifact (this session's `npm run build` +
grep, not invented):

### Confirmed absent from `site/dist/` (the D-01.1 "no raw token" assertion target)
```
$ grep -o "DEXTER_DEMO_LINE" dist/index.html dist/_astro/*.css dist/_astro/*.js
(no output — zero matches)
$ grep -o "{{[A-Za-z_]*}}" dist/index.html dist/_astro/*.css dist/_astro/*.js
(no output — zero matches)
```

### Confirmed present in `site/dist/index.html` (proper-case copy — the D-01.1 "proper case" assertion targets)
```
Add to Discord
An AI with opinions
Dexter plays your music
Full YouTube playback
Full-savage
Known limits
Long-term memory
Unprompted personality
Vision roasts
Watch it work
What it actually does
judges your taste                 # (part of "and judges your taste." — deliberately lowercase continuation of a sentence, not a case violation)
A five-button now-playing panel
```
Also present (previewSample fallback text, proving `resolveLine()` resolved correctly at build
time — useful for the D-01.2 "preview shown when token unfilled" assertion):
```
Seventeen songs and four of them are the same sad boy. Bold curatorial vision.
Third time today. I'm keeping notes. For later.
```

### Confirmed present in built CSS (the D-01.1 "after hours" identity assertion targets — see Pitfall 1)
```
$ grep -c "0a0c11" dist/_astro/index.DdY3oldB.css   # near-black background
1
$ grep -c "ffb454" dist/_astro/index.DdY3oldB.css   # amber accent
1
```

### `resolveLine()` — the exact function under test (verbatim from `site/src/data/demo-transcript.ts`)
```typescript
// Source: site/src/data/demo-transcript.ts:41-44
export function resolveLine(entry: { text: string; previewSample?: string }): string {
  const unfilled = entry.text.includes("{{");
  return unfilled && entry.previewSample ? entry.previewSample : entry.text;
}
```

### `pages.yml` trigger condition (verbatim, confirms the runbook's CICD-02 claim)
```yaml
# Source: .github/workflows/pages.yml:14-32
on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
# ...
    if: >
      github.event.workflow_run.conclusion == 'success' &&
      github.event.workflow_run.head_branch == 'main'
```

### `release.yml` trigger condition (verbatim, confirms the runbook's CICD-03 claim)
```yaml
# Source: .github/workflows/release.yml:7-9
on:
  push:
    tags: ["v*"]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| N/A | N/A | N/A | This phase makes no technology choice changes — it verifies an already-shipped stack (Astro ^7.0.9, existing CI/CD workflows) exactly as-is. No new library, pattern, or deprecated API applies. |

**Deprecated/outdated:** None relevant to this phase's scope.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The Node.js version installed on whatever machine eventually runs this plan's tasks will satisfy `engines.node: ">=22.12.0"` | Standard Stack | Low — this session's machine (v24.16.0) satisfies it; if a different/older machine is used, `npm run build` would fail loudly and obviously, not silently |
| A2 | Reusing `_dist_html_files`/`_site_dist_dir` from `test_site_drift_guard.py` by direct import (vs. duplicating the ~6-line helper) is safe and won't create an import-order/circularity issue | Pattern 1 | Low — both are pure functions with no shared mutable state; worst case the planner chooses to duplicate the tiny helper instead, which is explicitly called out as an acceptable discretion call above |

**If this table is empty:** N/A — see above. Everything else in this document (dist contents,
build success, CI/CD trigger conditions, Pages/tag live state) was directly verified via tool
calls in this research session (`npm run build`, `pytest`, `grep`, `gh api`), not assumed from
training data.

## Open Questions

1. **Should the D-01.2 guard live as new tests inside `tests/test_site_drift_guard.py` or as a
   new sibling file `tests/test_demo_transcript_guard.py`?**
   - What we know: CONTEXT.md's `<code_context>` section explicitly says "the D-02-02 guard test
     lands here" pointing at `tests/` generally, and separately says it should "mirror" the
     existing pattern. `test_site_drift_guard.py`'s own docstring is scoped tightly to the
     invite-URL problem (its module docstring is titled "Built-artifact drift guard for
     Dexter's invite URL").
   - What's unclear: whether the planner should extend that file's scope or keep guards
     single-purpose per file (matching the existing 1-guard-per-file convention:
     `test_invite_drift_guard.py`, `test_site_drift_guard.py`, `test_hosting_drift_guard.py` are
     all topically separate files).
   - Recommendation: new sibling file (`tests/test_demo_transcript_guard.py`) — matches the
     repo's established 1-topic-per-guard-file convention and keeps `test_site_drift_guard.py`'s
     docstring accurate (it would become misleading if it silently grew a second, unrelated
     guard). This is explicitly flagged as CONTEXT's own "Claude's/Planner's Discretion" item, so
     either choice is valid — this is a recommendation, not a locked decision.

2. **Exact parsing strategy for the build-independent structural guard (Pattern 3)?**
   - What we know: `demo-transcript.ts` currently has exactly 2 dexter-speaker entries, both with
     both a `text: "{{...}}"` token and a `previewSample:` fallback — a full TS/AST parse is
     overkill for 2 known entries.
   - What's unclear: whether to (a) hardcode the 2 expected entries and assert their shape
     directly (simplest, but silently misses a 3rd entry added later without its own test
     update), or (b) write a small regex/state-machine that generically pairs each `text:` with
     its nearest following `previewSample:` before the next `text:` (more robust, more code).
   - Recommendation: Planner's discretion, explicitly named optional in CONTEXT.md ("Whether a
     PORT-02 'tokens replaced' drift guard is worth adding... optional; only if it's cheap and
     non-vacuous. Not required."). Given CONTEXT frames the *dist-scan* half (Pattern 1) as the
     required D-01.2 deliverable and this structural half (Pattern 3) as a bonus, a cheap
     hardcoded-pair assertion is proportionate; don't over-invest in a generic TS parser for 2
     known array entries.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|--------------|-----------|---------|----------|
| Node.js | `npm run build` (D-01.1), `npm run dev` (D-01.3) | Yes (verified this session) | v24.16.0 | — |
| npm | package install/build | Yes (verified this session) | 11.13.0 | — |
| pytest | D-01.2 guard test, existing drift guards | Yes (already in `requirements-dev.txt`, suite green) | pinned in repo | — |
| gh CLI | Confirming live Pages/tag state (research-only; not required for the phase's committed deliverables) | Yes (verified this session, authenticated as `jadrianports`) | 2.93.0 | Owner performs the Settings-UI steps manually regardless — gh CLI is not a phase dependency, only a research convenience used here |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None — all tooling this phase needs was confirmed
present and working in this research session.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (already the repo standard; `requirements-dev.txt`) |
| Config file | none dedicated — repo-root `pytest.ini`/`pyproject.toml` config (pre-existing, unchanged by this phase) |
| Quick run command | `pytest -q tests/test_demo_transcript_guard.py` (new file, this phase) |
| Full suite command | `pytest -q` (repo convention; ~1233 tests pre-Phase-28 per STATE.md) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|-------------|
| PORT-05 (confirm) | `npm run build` boots clean | build check | `cd site && npm run build` | N/A — build step, not a pytest file |
| PORT-05 (confirm) | Existing invite drift guard still green against a fresh build | integration | `pytest -q tests/test_site_drift_guard.py` | ✅ (existing, verified passing 3/3 this session) |
| PORT-05 (confirm, D-01.1) | No raw `{{DEXTER_DEMO_LINE` token in `dist/`; proper-case + identity markers present | integration (dist scan) | `pytest -q tests/test_demo_transcript_guard.py::test_no_drift_in_built_demo` | ❌ Wave 0 — new file, this phase |
| PORT-05 (confirm, D-01.2) | `resolveLine()` invariant locked with positive control | integration + unit | `pytest -q tests/test_demo_transcript_guard.py` | ❌ Wave 0 — new file, this phase |
| CICD-02 | Pages source toggled + first live run resolves | manual-only | N/A — owner GitHub-UI action | N/A |
| CICD-03 | GHCR visibility flipped + image pullable | manual-only | N/A — owner GitHub-UI action, post-tag | N/A |
| PORT-02 | Verbatim lines captured, tokens replaced | manual-only | N/A — owner live-bot capture | N/A |

### Sampling Rate
- **Per task commit:** `pytest -q tests/test_demo_transcript_guard.py tests/test_site_drift_guard.py`
  (fast, scoped to the site surface this phase touches)
- **Per wave merge:** `pytest -q` (full suite — this phase should not regress anything else;
  zero non-test, non-doc code changes are expected outside `tests/` and
  `28-HUMAN-UAT.md`/planning docs)
- **Phase gate:** Full suite green before `/gsd-verify-work`; `SITE_DIST_REQUIRED=1 pytest -q
  tests/test_demo_transcript_guard.py tests/test_site_drift_guard.py` run at least once locally
  (mirroring what `ci.yml`'s `site` job does) to prove the hard-fail path, not just the
  soft-skip path, is exercised before relying on CI to catch it for the first time

### Wave 0 Gaps
- [ ] `tests/test_demo_transcript_guard.py` — the entire D-01.2 deliverable; does not exist yet
- [ ] `.planning/phases/28-portfolio-finish-release/28-HUMAN-UAT.md` — the D-04 runbook; does not
      exist yet
- [ ] No framework install needed — pytest and Astro are both already present and verified
      working in this session

*(If this phase's success criteria are almost entirely manual-only per the table above, that is
expected and correct — PORT-02/CICD-02/CICD-03 are explicitly blocked-on-human by design; only
PORT-05's confirmation half is automatable, and that automation is exactly what D-01.1/D-01.2
scope.)*

## Security Domain

No `security_enforcement` key is set in `.planning/config.json` (absent = enabled), so this
section is included per protocol — but its content is necessarily thin: **this phase introduces
no new attack surface.** It adds one test file (reads local build artifacts only, no network, no
user input) and one documentation file. No new auth, session, input-validation, or cryptography
code path is touched.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|-------------------|
| V2 Authentication | No | No auth code touched |
| V3 Session Management | No | No session code touched |
| V4 Access Control | No | No access-control code touched |
| V5 Input Validation | No | The new test reads only repo-local, developer-controlled files (`site/dist/`, `demo-transcript.ts`) — not user-supplied input |
| V6 Cryptography | No | No crypto code touched |

### Known Threat Patterns for this phase's actual surface

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| A future edit removes `previewSample` from an entry while its `text` still holds an unfilled `{{...}}` token, and that raw token ships to production as visible page content | Information Disclosure (of an internal placeholder, not a secret — low severity, but a real "looks broken/unprofessional" regression) | Exactly what D-01.2's guard test exists to prevent — this IS the threat model for this phase, framed as a data-integrity/regression concern rather than a classical security vulnerability |
| PORT-02 execution invents a plausible-sounding Dexter line instead of capturing a real one (violates D-06's contract) | Spoofing (of authentic bot output) | Not machine-enforceable — mitigated by the runbook's explicit "do not author or 'improve' lines" instruction (D-04) and D-06's documented rationale, not a test |

## Sources

### Primary (HIGH confidence — verified directly via tool calls in this research session)
- `site/package.json`, `site/astro.config.mjs` — confirmed Astro version, base-path config, no JS test runner present
- `npm run build` (executed live in this session) — confirmed clean build, no env/base-path handling needed locally
- `pytest -q tests/test_site_drift_guard.py` (executed live in this session, 3 passed) — confirmed existing guard non-vacuous against a fresh build
- `site/dist/index.html`, `site/dist/_astro/*.css` (grepped live in this session) — the source of every Code Examples string; grounds Pitfall 1's finding directly
- `.github/workflows/pages.yml`, `.github/workflows/release.yml`, `.github/workflows/ci.yml` — read verbatim, confirms trigger conditions cited above
- `gh api repos/jadrianports/dexter/pages` (executed live) — confirmed 404, Pages genuinely not yet enabled
- `gh api repos/jadrianports/dexter/tags` (executed live) — confirmed no `v1.5` tag exists yet (tip is `v1.4`)
- `git rev-list --count origin/main..HEAD` (executed live) — confirmed 92 unpushed commits, grounding Pitfall 2
- `tests/test_invite_drift_guard.py`, `tests/test_hosting_drift_guard.py` — read in full, established the repo's drift-guard conventions (positive/negative control, hardcoded reviewable literal lists, skip/fail split)
- `.planning/phases/23-portfolio-surface-ci-cd/23-HUMAN-UAT.md`, `.planning/phases/24-hosting-honesty-docker/24-HOST-UAT.md` — read in full, the runbook structure precedent

### Secondary (MEDIUM confidence)
None — every claim in this document traces to a direct tool-call verification in this session
or a verbatim read of an existing repo file. No WebSearch was needed for this phase (zero new
libraries, zero external API surface).

### Tertiary (LOW confidence)
None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies; existing stack directly re-verified (build ran, tests ran)
- Architecture: HIGH — every diagram edge traces to a file read or command executed in this session
- Pitfalls: HIGH — all three pitfalls are directly reproduced/confirmed findings (grep counts, `gh api` responses, `git rev-list` output), not inferred

**Research date:** 2026-07-18
**Valid until:** Short shelf-life — this document embeds a point-in-time snapshot (92 unpushed
commits, no `v1.5` tag, Pages not enabled) that will change the moment the next push/tag/toggle
happens. The *patterns and code examples* (drift-guard conventions, `resolveLine()` source,
workflow trigger YAML) are stable and valid until the underlying files change; the *live-state
facts* (Pitfalls 2/3, Open Questions context) should be re-verified at plan/execution time if
more than a few days pass, since a push or tag could land between now and execution.
