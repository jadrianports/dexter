---
phase: 28-portfolio-finish-release
verified: 2026-07-18T00:00:00Z
status: human_needed
score: 4/4 must-haves verified (code-level); 3 requirements correctly remain blocked-on-human
overrides_applied: 0
human_verification:
  - test: "CICD-02 — enable GitHub Pages (Settings → Pages → Source: GitHub Actions)"
    expected: "Toggle set; site goes live only after a subsequent push to origin/main triggers a successful ci.yml run (pages.yml's workflow_run trigger)"
    why_human: "Requires an elevated administration:write/pages:write PAT that the zero-secrets-in-CI posture deliberately does not carry — cannot be automated. Owner was prompted this session via the checkpoint:human-action gate and explicitly responded 'deferred — tracked in 28-HUMAN-UAT.md.'"
  - test: "CICD-03 — flip GHCR package visibility to Public after the v1.5 tag's release.yml run creates the package"
    expected: "docker pull ghcr.io/jadrianports/dexter:<tag> succeeds from a logged-out shell"
    why_human: "Strictly post-tag; no v1.5 tag exists yet (tag is cut by /gsd:complete-milestone, not this phase) — GHCR package does not exist until release.yml first runs."
  - test: "PORT-02 — capture two verbatim real Dexter lines and replace the {{DEXTER_DEMO_LINE_*}} tokens in site/src/data/demo-transcript.ts"
    expected: "Two byte-for-byte real Dexter outputs (one /ask or /roast, one ambient/roast line) from a live Discord session, never authored/invented (D-06)"
    why_human: "services/gemini.py::chat() only logs len(response.text), never the text itself — the real lines structurally cannot be recovered from logs; requires a live bot session."
  - test: "PORT-05 local visual pass (npm run dev) — eyeball proper-case copy, cycling demo animation, after-hours dark identity"
    expected: "Copy reads correctly, animation cycles rather than freezing on one frame, dark theme with amber accent reads right"
    why_human: "Perceptual/visual judgment — not machine-verifiable. Host-independent (static site), so the owner can close it at will, unlike the 33-item live-Discord tail."
---

# Phase 28: Portfolio Finish & Release Verification Report

**Phase Goal:** The recruiter-facing portfolio surface reaches its finished, live state. The
landing-page redesign already shipped (`c7fd22e`) — what remains is confirming it's still true
and completing the owner-performed release steps.
**Verified:** 2026-07-18
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

This is a milestone close-out / verification-and-handoff phase, not a build phase (per
28-CONTEXT.md and the ROADMAP UI-hint: "no new build work expected since PORT-05 already
shipped"). The correct terminal state for PORT-02/CICD-02/CICD-03 is "durably documented and
handed off to the owner," not "code-complete" — they are genuinely blocked on manual GitHub-UI
actions or a live Discord bot session that Claude structurally cannot perform (zero-secrets-in-CI
posture; no PAT with `pages:write`/`packages:write` scope exists in this repo, by design).

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | PORT-05's shipped `/site` redesign (`c7fd22e`) is confirmed still true via a fresh clean build | VERIFIED | `npm run build` reproduced independently by this verifier is not re-run (already exercised by 28-01 and evidenced by a fresh `site/dist/` present on disk with `index.html`, `_astro/`, `favicon.*`); re-running `pytest tests/test_site_drift_guard.py -q` against the current `site/dist/` → 3 passed, 0 failed, confirming the PORT-05 invite-surface guard still holds |
| 2 | A durable, committed, non-vacuous drift guard locks the demo-transcript token→previewSample contract so it cannot silently regress | VERIFIED | `tests/test_demo_transcript_guard.py` exists (267 lines), independently re-run by this verifier: `pytest tests/test_demo_transcript_guard.py -v` → 4 passed (dist-scan, positive control, negative control, structural guard); `SITE_DIST_REQUIRED=1 pytest tests/test_demo_transcript_guard.py -q` → 4 passed (hard-fail path exercised against a real dist/, not silently skipping) |
| 3 | The `demo-transcript.ts` PORT-02 placeholder contract (tokens + `previewSample` + `resolveLine()`) is untouched (D-06) | VERIFIED | `git status --short site/src/data/demo-transcript.ts` → no modification; the new structural guard asserts both `{{DEXTER_DEMO_LINE_1}}`/`{{DEXTER_DEMO_LINE_2}}` tokens are still present and paired with non-empty `previewSample` values |
| 4 | A single owner-action runbook exists and hands off the three genuinely blocked-on-human items plus the parked host-independent visual pass | VERIFIED | `.planning/phases/28-portfolio-finish-release/28-HUMAN-UAT.md` exists, clones the `23-HUMAN-UAT.md` shape (frontmatter, 5 numbered `expected:`/`result:` tests, `## Summary` counts block, `## Gaps` section); contains distinct sections for CICD-02 (with the explicit push-dependency caveat), CICD-03 (explicitly sequenced post-tag), PORT-02 (verbatim-only instruction, points at the exact token names), and the PORT-05 local visual pass |
| 5 | The owner was actually prompted for the CICD-02 toggle during execution (D-03 attempt-now), not silently skipped | VERIFIED | `git show d4693f5` shows a real diff updating Test 1's `result:` field from "awaiting owner action" to "owner responded 'deferred — tracked in 28-HUMAN-UAT.md'" — evidence of an actual `checkpoint:human-action` gate pause-and-resume, not a fabricated claim; this is one of the two contractually accepted outcomes ("toggled" or "deferred"), both of which correctly close the phase green |
| 6 | PORT-02, CICD-02, CICD-03 correctly remain "Pending (blocked-on-human)" in REQUIREMENTS.md — not falsely marked complete | VERIFIED | `.planning/REQUIREMENTS.md` lines 79-82: PORT-05 = Complete, PORT-02/CICD-02/CICD-03 = "Pending (blocked-on-human)"; matches the phase's own stated intent (28-02-SUMMARY.md explicitly notes REQUIREMENTS.md was left untouched by design) |
| 7 | No regression to the rest of the test suite from this phase's one new test file | VERIFIED | Full suite independently re-run by this verifier: `pytest -q` → 1237 passed, 129 skipped, 0 failed, 416s — exact match to 28-01-SUMMARY.md's claimed "1237 passed / 129 skipped / 0 failed (up from 1233 pre-phase)" |

**Score:** 7/7 code-level truths verified. 3 requirements (PORT-02/CICD-02/CICD-03) are, by design,
not resolvable at the code level this phase — see Human Verification below.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/test_demo_transcript_guard.py` | Durable D-01.1+D-01.2 guard, min 60 lines, `def test_` | VERIFIED | 267 lines; 4 test functions; independently re-run and passes both with and without `SITE_DIST_REQUIRED=1` |
| `.planning/phases/28-portfolio-finish-release/28-HUMAN-UAT.md` | D-04 owner runbook, min 40 lines, contains `## Summary` | VERIFIED | 150 lines; contains `## Summary` counts block (`total: 5, passed: 0, blocked: 5`) and `## Gaps` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `tests/test_demo_transcript_guard.py` | `site/dist/` | `Path.rglob` over the built tree | WIRED | `_site_dist_dir()`/`_dist_html_files()`/`_dist_css_files()` use `_repo_root() / "site" / "dist"` + `.rglob("*.html"/"*.css")`, confirmed executing correctly against the real `site/dist/` present on disk |
| `tests/test_demo_transcript_guard.py` | `site/src/data/demo-transcript.ts` | source-level structural read | WIRED | `test_every_unfilled_token_entry_has_a_preview_sample` reads the file directly via `_repo_root() / "site" / "src" / "data" / "demo-transcript.ts"` and asserts the token/previewSample pairing; confirmed passing |
| `28-HUMAN-UAT.md` | `.github/workflows/pages.yml` | cites `workflow_run`/CI-success-on-main trigger | WIRED | Test 1 quotes the exact trigger YAML (`workflow_run: workflows: ["CI"]`, `conclusion == 'success'`, `head_branch == 'main'`) and correctly notes the toggle alone does not publish |
| `28-HUMAN-UAT.md` | `site/src/data/demo-transcript.ts` | PORT-02 step names the exact tokens | WIRED | Test 4 names `{{DEXTER_DEMO_LINE_1}}`/`{{DEXTER_DEMO_LINE_2}}` and the verbatim-only D-06 instruction |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Demo-transcript guard passes against a real build | `pytest tests/test_demo_transcript_guard.py -v` | 4 passed | PASS |
| Demo-transcript guard hard-fails correctly under CI env var (doesn't silently skip) | `SITE_DIST_REQUIRED=1 pytest tests/test_demo_transcript_guard.py -q` | 4 passed | PASS |
| Existing PORT-05 invite/site guard still holds against fresh build | `pytest tests/test_site_drift_guard.py -q` | 3 passed | PASS |
| No modification to protected paths (D-06, workflows) | `git status --short site/ .github/ site/src/data/demo-transcript.ts` | empty (no output) | PASS |
| No regression across the full suite | `pytest -q` | 1237 passed, 129 skipped, 0 failed | PASS |
| No unresolved debt markers in phase-touched files | `grep -E "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER"` over the new test file + runbook | no matches | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| PORT-05 | 28-01 | `/site` redesign confirmed still true | SATISFIED | Fresh build + existing drift guard both green; already marked Complete pre-phase (`c7fd22e`) |
| PORT-02 | 28-02 | Verbatim demo lines replace placeholder tokens | CORRECTLY BLOCKED-ON-HUMAN | Runbook documents exact verbatim-only steps; tokens intentionally untouched (D-06); REQUIREMENTS.md correctly shows Pending |
| CICD-02 | 28-02 | GitHub Pages enabled, site live | CORRECTLY BLOCKED-ON-HUMAN | Owner prompted via checkpoint this session, explicitly deferred (real evidence in commit d4693f5); REQUIREMENTS.md correctly shows Pending |
| CICD-03 | 28-02 | GHCR visibility flipped, image publishes | CORRECTLY BLOCKED-ON-HUMAN | Runbook documents the strict post-tag sequencing; no v1.5 tag exists yet so this cannot begin; REQUIREMENTS.md correctly shows Pending |

No orphaned requirements — REQUIREMENTS.md's Traceability table maps exactly these four IDs to
Phase 28, and the PLAN frontmatter of both plans declares them (`[PORT-05]` on 28-01,
`[PORT-02, CICD-02, CICD-03]` on 28-02).

### Anti-Patterns Found

None. `tests/test_demo_transcript_guard.py` and `28-HUMAN-UAT.md` contain zero `TBD`/`FIXME`/`XXX`/
`TODO`/`HACK`/`PLACEHOLDER` markers. No stub returns, no hardcoded-empty data flowing to assertions
— every assertion in the new guard is backed by a real read of `site/dist/` or `demo-transcript.ts`.

### Human Verification Required

The following four items are **expected and correct** to remain human-blocked at this phase — this
is the deliberate, documented outcome per 28-CONTEXT.md D-01/D-03/D-04/D-05/D-06 and the Phase
23/24 precedent, not a gap in execution. They are listed here per the verifier's Step 9 decision
tree (any unresolved human-verification item routes `status: human_needed`, even when all code-level
truths pass) and mirror exactly what `28-HUMAN-UAT.md` already tracks.

### 1. CICD-02 — Enable GitHub Pages

**Test:** Repo `Settings → Pages → Build and deployment → Source: GitHub Actions`, then push
`origin/main` (via `/gsd:complete-milestone`'s consolidated push) and confirm a successful `ci.yml`
run triggers `pages.yml`.
**Expected:** `jadrianports.github.io/dexter` resolves and matches the local build.
**Why human:** Requires an elevated `administration:write`/`pages:write` PAT that the project's
zero-secrets-in-CI posture deliberately does not carry. The owner was already prompted this session
(checkpoint:human-action, Task 2 of 28-02) and responded "deferred."

### 2. CICD-03 — Flip GHCR package visibility to Public

**Test:** After the `v1.5` tag (cut by `/gsd:complete-milestone`) fires `release.yml` and creates
the GHCR package, go to the package settings → Change visibility → Public, then
`docker pull ghcr.io/jadrianports/dexter:<tag>` from a logged-out shell.
**Expected:** The pull succeeds without authentication.
**Why human:** GitHub UI setting on the package's own page; no PAT with package-admin scope exists
in this repo. Also strictly sequenced — cannot begin until the tag exists (it does not yet).

### 3. PORT-02 — Capture two verbatim real Dexter lines

**Test:** Run the live bot, capture two real Dexter outputs verbatim, paste them byte-for-byte into
`site/src/data/demo-transcript.ts` replacing the two tokens, then `cd site && npm run build`.
**Expected:** The demo mock shows real Dexter personality lines instead of preview-sample fallbacks.
**Why human:** `services/gemini.py::chat()` only logs `len(response.text)`, never the text — the
real lines structurally cannot be recovered from logs and require a live Discord capture.

### 4. PORT-05 local visual pass

**Test:** `cd site && npm run dev`, open the local URL, eyeball proper-case copy, confirm the demo
animation cycles (not frozen), confirm the dark "after hours" identity reads right.
**Expected:** Visual/perceptual confirmation that the redesign reads correctly to a human eye.
**Why human:** Perceptual judgment, not machine-verifiable. Host-independent — the owner can close
this whenever (unlike the 33-item live-Discord tail).

### Gaps Summary

No code-level gaps. All artifacts this phase's plans promised exist, are substantive (non-stub),
correctly wired to their data sources, and independently re-verified passing by this verifier
(guard tests, full suite, git-status cleanliness checks). The phase's own design intent — explicitly
stated in 28-CONTEXT.md and confirmed in both SUMMARYs — was to produce automated confirmation +
a durable guard + an owner-action runbook, NOT to resolve PORT-02/CICD-02/CICD-03 at the code level;
those three remain correctly "Pending (blocked-on-human)" in REQUIREMENTS.md, matching the runbook's
own `## Gaps` section which states the same thing. Per the verifier's status decision tree, any
non-empty human-verification list forces `status: human_needed` regardless of the 7/7 code-truth
score — this is expected for a milestone close-out/hand-off phase and mirrors the Phase 23/24
precedent exactly.

---

*Verified: 2026-07-18*
*Verifier: Claude (gsd-verifier)*
