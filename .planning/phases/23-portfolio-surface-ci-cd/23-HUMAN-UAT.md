---
status: partial
phase: 23-portfolio-surface-ci-cd
source: [23-VALIDATION.md, 23-02-SUMMARY.md, 23-04-SUMMARY.md, 23-06-SUMMARY.md, 23-CONTEXT.md D-17]
started: 2026-07-14T00:00:00Z
updated: 2026-07-14T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Supply the verbatim Dexter transcript (PORT-02, D-06)
expected: `logs/dexter.log` structurally cannot supply real Gemini-generated output —
`services/gemini.py::chat()` logs `len(response.text)`, never the text itself, at every call
site (23-RESEARCH.md Finding 1, confirmed by direct code inspection, not an absent grep). The
user pastes a handful of real `/ask`/`/roast`/`/play`/ambient-roast responses copied verbatim
from a live Discord session into `.planning/phases/23-portfolio-surface-ci-cd/
23-DEMO-TRANSCRIPT.md`, replacing the `{{DEXTER_DEMO_LINE_1}}` / `{{DEXTER_DEMO_LINE_2}}`
tokens, then copies them byte-for-byte into `site/src/data/demo-transcript.ts`.
result: **NOT DONE.** Deferred by the user on 2026-07-14 ("placeholder for now, remind me
later" — 23-02-SUMMARY.md Task 2). `23-DEMO-TRANSCRIPT.md` status is still `BLOCKED`;
`site/src/data/demo-transcript.ts` still carries both placeholder tokens verbatim (confirmed
present in `site/dist/index.html`, 2x each, by 23-06-SUMMARY.md's post-build check).
**PORT-02 is reported INCOMPLETE, not passed** — the demo mock renders, but its content is not
yet the real thing PORT-02 promises.

### 2. Render docs/demo.gif from the mock (PORT-02/PORT-03, D-07) — blocked on Test 1
expected: Once Test 1 supplies real lines and the placeholder tokens are gone from
`site/src/data/demo-transcript.ts`, run `cd site && npm ci && npm run build` then
`python scripts/render_demo_gif.py` (one-time local setup: `pip install playwright &&
playwright install chromium`, documented in the script's own header). Produces a committed
`docs/demo.gif` (~1MB at the script's default 12fps/640px settings, verified below the 2MB
budget) showing the real conversation.
result: **NOT DONE — correctly deferred, not a bug.** `scripts/render_demo_gif.py` is written
and was validated end-to-end this session against the current (placeholder-token) build: it
successfully recorded a `.webm` via Playwright's browser-context video recording and converted
it to a 0.95MB GIF at 12fps/640px via the two-pass ffmpeg palette pipeline — proving the
mechanism works. That scratch output was discarded, not committed, and no `docs/demo.gif` was
written to the repo: rendering the current build would visibly show the
`{{DEXTER_DEMO_LINE_*}}` tokens in a public, permanently-cached README asset, which is a worse
failure mode than shipping no GIF at all (T-23-HONEST). Re-run the two commands above the
moment Test 1 lands.

### 3. Enable GitHub Pages (CICD-02)
expected: Repo Settings → Pages → Build and deployment → Source: **GitHub Actions**. This is a
manual, once-only toggle — `actions/configure-pages`'s own `enablement: true` input requires a
PAT with `administration:write`/`pages:write` scope, which this project's zero-secrets-in-CI
posture (Phase 22 D-04) deliberately does not carry, so it cannot be automated from the
workflow itself (23-RESEARCH.md Finding 4).
result: **NOT DONE.** `gh api repos/jadrianports/dexter/pages` returned `404` (Pages not
enabled), confirmed both at 23-02 execution time and again during this plan's execution.
Until this is set, `pages.yml`'s `deploy-pages` step will fail outright on a missing
`github-pages` environment — an expected failure mode, not a bug in the workflow file, the
first time `pages.yml` actually runs.

### 4. First real `pages.yml` run — blocked on Test 3 and the orchestrator's consolidated push
expected: After Test 3 and the phase-end push land, `pages.yml` runs on the next push to
`main`, publishes `site/dist/` via `actions/deploy-pages`, and `jadrianports.github.io/dexter`
resolves and matches the local build.
result: **NOT DONE.** `pages.yml` is structurally correct and locally YAML-validated
(23-04-SUMMARY.md) but has never executed — this plan is commit-only (no push), matching the
orchestrator's stated single-consolidated-push protocol. 23 commits are currently unpushed
ahead of `origin/main` (verified via `git rev-list --count origin/main..HEAD` = 23 at the time
this file was written).

### 5. Flip the GHCR package to public, then verify a logged-out pull (CICD-03, D-17)
expected: Package page (`github.com/users/jadrianports/packages/container/dexter/settings`) →
Change visibility → Public. Then, from a logged-out shell:
`docker logout ghcr.io && docker pull ghcr.io/jadrianports/dexter:v1.4.0` (or whichever tag is
cut) succeeds. GHCR packages are private by default regardless of the source repo's own
visibility, and the toggle is a GitHub UI setting on the package's own page — it genuinely
cannot be reached from the publishing workflow without a new PAT with package-admin scope, which
this project deliberately does not carry (23-RESEARCH.md Finding 5, cross-referenced across 3
independent sources).
result: **NOT DONE.** No `v*` tag has been pushed yet, so `release.yml` has never run and no
package exists on GHCR to flip. Until this step happens, **CICD-03's "pullable with zero build
step" claim is not yet true** — `docker pull` fails for everyone except (after auth) the owner.
This is expected, not a bug, and mirrors Phase 22's identical Dev Portal acknowledged-deferred
pattern exactly.

### 6. First real `release.yml` run — blocked on a `v*` tag push
expected: Tagging e.g. `v1.4.0-rc1` (or the real milestone tag) and pushing it triggers
`release.yml`: QEMU + buildx multi-arch build (`linux/amd64` + `linux/arm64`), pushed to
`ghcr.io/jadrianports/dexter`. `docker manifest inspect` lists both architectures.
result: **NOT DONE.** `release.yml` is structurally correct and locally YAML-validated
(23-04-SUMMARY.md) — tags-only trigger, `packages: write` only, `GITHUB_TOKEN`-only auth — but
has never executed; no tag has been pushed.

### 7. README renders correctly on github.com (PORT-03)
expected: After the push, view the rendered README at `github.com/jadrianports/dexter`. All
five badges resolve (the CI badge shows a real, current run status — not "no status"/stale);
the mermaid `graph TD` diagram renders as a real diagram, not a raw code fence.
result: **NOT DONE — cannot be verified locally.** GitHub's markdown/mermaid rendering pipeline
is not reproducible outside github.com itself. All content-level checks that *can* run locally
were run and passed this plan (badge markdown present, `workflows/ci.yml/badge.svg` literal
present, mermaid fenced block present, canonical invite URL present and drift-guard-verified
non-vacuous — see this plan's SUMMARY).

### 8. CI badge is green at the code's real HEAD (PORT-03)
expected: `gh run list --branch main --workflow CI --limit 1` reports `success` at the exact
commit SHA the README badge is describing.
result: **NOT DONE — sequencing, not a failure.** The most recent real CI run
(`29324950877`, `success`, 2026-07-14T10:19:46Z) is at Phase 23 plan 01's final HEAD — it has
not yet seen plans 23-02 through this plan (23-07). The badge will report truthfully on
whatever `origin/main`'s tip is once the orchestrator's consolidated push lands; do not treat
today's green run as proof for the code shipped in this plan.

### 9. Landing page visual and copy review (PORT-01, PORT-04)
expected: Load `jadrianports.github.io/dexter` once Tests 3–4 land. Confirm the four PORT-04
boundaries read as *disclosure*, not apology; confirm the hosting caveat sits immediately
before the closing CTA (D-05's whole reason for that ordering); confirm the demo mock and the
README tell the same story once Test 1/2 land.
result: **NOT DONE — blocked on Tests 1, 3, and 4.** Taste and honesty-of-tone are not
machine-assertable; the page is not yet live to review in its deployed form.

## Summary

total: 9
passed: 0
issues: 0
pending: 0
skipped: 0
blocked: 9

## Gaps

- **PORT-02 is incomplete**, not merely unstyled — it depends entirely on Test 1 (the user
  supplying real verbatim Dexter lines). Nothing in this plan can close it; the demo mock and
  its derived README GIF are both mechanically ready to go the moment Test 1 lands.
- **CICD-02 is code-complete but not evidence-complete** — blocked on Test 3 (the Pages source
  toggle, a repo setting) and Test 4 (a real run, which additionally needs the orchestrator's
  consolidated push).
- **CICD-03 is code-complete but not evidence-complete** — blocked on Test 6 (a `v*` tag push,
  needing the consolidated push first) and Test 5 (the GHCR visibility flip, which cannot even
  begin until Test 6 has produced a package to flip).
- **PORT-01/PORT-03 are structurally complete and locally verified** wherever a local check
  exists (build succeeds, drift guard non-vacuous, badges/mermaid/boundaries present in
  source) — the two genuinely unverifiable-locally items are Tests 7 and 9 (GitHub's own
  rendering, and taste/tone review of a page that isn't live yet).
- **Requirement traceability:** per this plan's explicit instruction, `.planning/REQUIREMENTS.md`
  is left untouched — the orchestrator reconciles PORT-01…04/CICD-02/03 completion during phase
  verification, using this file as the evidence ledger for what is proven versus what remains
  human-blocked.
