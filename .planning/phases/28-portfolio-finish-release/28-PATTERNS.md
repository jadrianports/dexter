# Phase 28: Portfolio Finish & Release - Pattern Map

**Mapped:** 2026-07-18
**Files analyzed:** 2 (new)
**Analogs found:** 2 / 2

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `tests/test_demo_transcript_guard.py` | test (drift guard) | file-I/O (reads built `site/dist/` + `site/src/data/demo-transcript.ts`) | `tests/test_site_drift_guard.py` | exact (same repo, same dist-scan + skip/fail-split + positive/negative control convention) |
| `.planning/phases/28-portfolio-finish-release/28-HUMAN-UAT.md` | doc/runbook | request-response (owner-executed manual steps) | `.planning/phases/23-portfolio-surface-ci-cd/23-HUMAN-UAT.md` | exact (same phase family, same three blocked-on-human items carried forward) |

## Pattern Assignments

### `tests/test_demo_transcript_guard.py` (test, file-I/O)

**Analog:** `tests/test_site_drift_guard.py` (full file read; 144 lines)

**Module docstring convention** (lines 1-60 of analog): every guard file in this repo opens with
a docstring explaining (a) why the guard exists as its own file rather than extending an existing
one, (b) the exact collection strategy (`git ls-files` vs `Path.rglob` over `dist/`) and why, (c)
the `SITE_DIST_REQUIRED` skip/fail split rationale, and (d) a "Tests:" list naming each test and
which threat/requirement it discharges. Follow this shape for the new file's docstring, framing it
around D-01.2 / the token-leak threat named in RESEARCH.md's Security Domain section.

**Imports pattern** (lines 62-69):
```python
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.test_invite_drift_guard import _canonical_url, _collect_offenders, _repo_root
```
For the new file, import (or duplicate — RESEARCH.md Assumption A2 says either is safe)
`_repo_root` and, if reused, `_site_dist_dir`/`_dist_html_files` from `tests.test_site_drift_guard`
rather than re-deriving repo-root logic.

**Helper pattern — cwd-independent dist dir + file collection** (lines 76-90):
```python
def _site_dist_dir() -> Path:
    return _repo_root() / "site" / "dist"

def _dist_html_files(dist_dir: Path) -> list[Path]:
    if not dist_dir.exists():
        return []
    return list(dist_dir.rglob("*.html"))
```
Reuse verbatim (import) or duplicate this exact shape — never `git ls-files` (dist/ is gitignored).

**Core pattern — SITE_DIST_REQUIRED skip/fail split** (lines 98-115):
```python
def test_no_drift_in_built_site():
    files = _dist_html_files(_site_dist_dir())
    if not files:
        if os.getenv("SITE_DIST_REQUIRED"):
            pytest.fail(
                "site/dist/ is empty but SITE_DIST_REQUIRED=1 — the Astro build step did not run or produced no output"
            )
        pytest.skip("site/dist/ not built (local run, no `npm run build`)")
    offenders = _collect_offenders(files, _canonical_url())
    assert offenders == [], f"drifted invite URL(s) in built site: {offenders}"
```
Mirror this exactly for the new guard's `test_no_drift_in_built_demo`: same missing-dist
skip/fail branching, same `os.getenv("SITE_DIST_REQUIRED")` env var (do not invent a new env
var name), same assertion-with-message shape. Replace the offender-detection logic with a
`{{`-token scan of `dist/index.html` plus assertions that the two known `previewSample` strings
(verified present in RESEARCH.md Code Examples: `"Seventeen songs and four of them are the same
sad boy. Bold curatorial vision."` and `"Third time today. I'm keeping notes. For later."`) ARE
present — proving `resolveLine()` resolved correctly at build time, not just that no raw token
leaked.

**Error handling / assertion style:** `assert x == [], f"... {x}"` — always assert with a
descriptive f-string message naming what leaked, never a bare `assert`.

**Positive control pattern (mandatory)** (lines 118-131):
```python
def test_dist_drift_guard_actually_detects_a_mismatch(tmp_path):
    fake_html = tmp_path / "index.html"
    fake_html.write_text(
        '<a href="...permissions=8...">Add</a>',
        encoding="utf-8",
    )
    offenders = _collect_offenders([fake_html], _canonical_url())
    assert offenders, "dist/ scanner failed to catch a deliberately-wrong invite URL"
```
For the new guard: write a `tmp_path` fixture HTML file containing a literal
`{{DEXTER_DEMO_LINE_1}}` token and assert the detection function flags it. This is non-negotiable
per D-01 ("non-vacuous with a positive control") and CLAUDE.md's repo-wide drift-guard discipline.

**Negative control pattern** (lines 134-144):
```python
def test_dist_drift_guard_accepts_the_canonical_url(tmp_path):
    canonical = _canonical_url()
    fake_html = tmp_path / "index.html"
    fake_html.write_text(f'<a href="{canonical}">add to discord</a>', encoding="utf-8")
    offenders = _collect_offenders([fake_html], canonical)
    assert offenders == []
```
Mirror with the real `previewSample` strings run through the detector, asserting zero offenders —
proves the guard doesn't false-positive on legitimate resolved output.

**Build-independent structural companion (Pattern 3 from RESEARCH.md, no direct file precedent —
new pattern, planner's discretion on parse strategy):**
```python
# Subject under test — verbatim from site/src/data/demo-transcript.ts:41-44
export function resolveLine(entry: { text: string; previewSample?: string }): string {
  const unfilled = entry.text.includes("{{");
  return unfilled && entry.previewSample ? entry.previewSample : entry.text;
}
```
A source-level test reading `site/src/data/demo-transcript.ts` as text and asserting each
`text: "{{...}}"` entry is followed by a non-empty `previewSample:` before the next `text:` key —
runs without requiring `npm run build`. Given there are currently exactly 2 dexter-speaker
entries (both already paired), a hardcoded-pair assertion is proportionate (RESEARCH.md Open
Question 2 recommendation) — do not over-invest in a generic TS parser.

**CRITICAL pitfall to avoid** (RESEARCH.md Pitfall 1, directly verified this session): do NOT
assert the literal phrase `"after hours"` against any built artifact — it lives only in a CSS
comment stripped by the Astro/Vite minifier (`grep -c "after hours" dist/_astro/*.css` → 0). If
this new guard (or its D-01.1 sibling assertions run outside pytest) needs to prove visual
identity, assert against the surviving hex values instead: `#0a0c11` (near-black bg) and
`ffb454` (amber accent), both confirmed present in `dist/_astro/index.*.css`.

---

### `.planning/phases/28-portfolio-finish-release/28-HUMAN-UAT.md` (doc/runbook)

**Analog:** `.planning/phases/23-portfolio-surface-ci-cd/23-HUMAN-UAT.md` (full file read, 147 lines)

**Frontmatter pattern** (lines 1-7):
```yaml
---
status: partial
phase: 23-portfolio-surface-ci-cd
source: [23-VALIDATION.md, 23-02-SUMMARY.md, 23-04-SUMMARY.md, 23-06-SUMMARY.md, 23-CONTEXT.md D-17]
started: 2026-07-14T00:00:00Z
updated: 2026-07-14T00:00:00Z
---
```
Reuse this exact frontmatter shape for `28-HUMAN-UAT.md`, updating `phase:`, `source:` (point at
`28-CONTEXT.md` D-01/D-04/D-05, `28-RESEARCH.md`), and timestamps.

**Per-test structure** (repeated pattern, e.g. lines 15-28, 47-58):
```markdown
### N. <short title> (<REQ-ID>, <decision ref>)
expected: <precise, falsifiable expectation, citing exact commands/paths/settings>
result: **NOT DONE.** <why, citing exact verification evidence — command output, file state>
```
Every test entry states a concrete `expected:` (often literally the exact UI path, e.g.
`Repo Settings → Pages → Build and deployment → Source: GitHub Actions`) and a `result:` that is
evidence-grounded (`gh api ... returned 404`), never a vague "TBD".

**The three items to carry into `28-HUMAN-UAT.md`, sourced from 28-CONTEXT.md D-04 + RESEARCH.md
Pitfalls 2/3:**
1. **CICD-02** — mirror analog Tests 3-4 (lines 47-67): the Pages-source toggle (host-independent,
   doable now) PLUS the explicit note that the toggle alone does not publish anything — a
   push-triggered `ci.yml` success on `main` must also happen (RESEARCH.md Pitfall 2). Cite the
   exact trigger condition:
   ```yaml
   # .github/workflows/pages.yml:14-32
   on:
     workflow_run:
       workflows: ["CI"]
       types: [completed]
   #...
       if: >
         github.event.workflow_run.conclusion == 'success' &&
         github.event.workflow_run.head_branch == 'main'
   ```
2. **CICD-03** — mirror analog Tests 5-6 (lines 69-90): sequenced strictly AFTER the `v1.5` tag
   (cut by `/gsd:complete-milestone`, not this phase — D-02/D-05), since the GHCR package doesn't
   exist until `release.yml`'s first run. Cite:
   ```yaml
   # .github/workflows/release.yml:7-9
   on:
     push:
       tags: ["v*"]
   ```
3. **PORT-02** — mirror analog Test 1 (lines 15-28): verbatim-only capture instruction ("do NOT
   author or improve lines"), pointing at the exact tokens in `site/src/data/demo-transcript.ts`
   (`{{DEXTER_DEMO_LINE_1}}` / `{{DEXTER_DEMO_LINE_2}}`) and the D-06 rationale for why the
   scaffolding stays untouched otherwise.

**Summary block pattern** (lines 119-127):
```markdown
## Summary

total: 9
passed: 0
issues: 0
pending: 0
skipped: 0
blocked: 9
```
Reuse this exact counts-block shape (total/passed/issues/pending/skipped/blocked).

**Gaps section pattern** (lines 128-146): bulleted list, one bullet per still-open item, explicit
about WHY it's blocked and what unblocks it — never silent about a known limitation. For
`28-HUMAN-UAT.md`, note explicitly that PORT-05's confirmation half (D-01.1/D-01.2) is NOT in this
runbook — it's automated/committed elsewhere (the new guard test), and this file covers only the
three genuinely manual items.

## Shared Patterns

### Drift-guard discipline (repo-wide convention)
**Source:** `tests/test_site_drift_guard.py`, `tests/test_invite_drift_guard.py`,
`tests/test_hosting_drift_guard.py`
**Apply to:** `tests/test_demo_transcript_guard.py`
- Never `git ls-files` for build-output scanning — always `Path.rglob` over the actual built
  `dist/` tree (dist/ is gitignored).
- `SITE_DIST_REQUIRED` env var (exact name, already established) — skip locally, hard-fail in CI.
- Every guard ships BOTH a positive control (proves it catches a real regression) and a negative
  control (proves it doesn't false-positive on legitimate output) — never a guard with only a
  "green" assertion.
- Detection logic lives in a small pure helper function taking explicit paths/strings, never
  internally re-deriving what to scan — so tests can feed synthetic `tmp_path` fixtures through it.

### Owner-runbook discipline
**Source:** `.planning/phases/23-portfolio-surface-ci-cd/23-HUMAN-UAT.md`,
`.planning/phases/24-hosting-honesty-docker/24-HOST-UAT.md`
**Apply to:** `28-HUMAN-UAT.md`
- Frontmatter: `status`, `phase`, `source` (list of doc refs), `started`/`updated` timestamps.
- Numbered tests: `expected:` (falsifiable, cites exact command/UI path) / `result:` (evidence-
  grounded, not speculative).
- Summary counts block, then a Gaps section explaining every still-open item honestly.

## No Analog Found

None — both new artifacts have exact, structurally-identical analogs already in the repo.

## Metadata

**Analog search scope:** `tests/*drift_guard*.py`, `.planning/phases/23-*/23-HUMAN-UAT.md`,
`.planning/phases/24-*/24-HOST-UAT.md`, `site/src/data/demo-transcript.ts`
**Files scanned:** 4 (full reads: `test_site_drift_guard.py`, `23-HUMAN-UAT.md`,
`demo-transcript.ts`; RESEARCH.md already contained verified excerpts of the remaining sources —
`.github/workflows/pages.yml`, `.github/workflows/release.yml`, `test_invite_drift_guard.py`)
**Pattern extraction date:** 2026-07-18
