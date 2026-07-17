---
status: partial
phase: 28-portfolio-finish-release
source: [28-CONTEXT.md D-01/D-04/D-05/D-06, 28-RESEARCH.md, 23-HUMAN-UAT.md]
started: 2026-07-18T00:00:00Z
updated: 2026-07-18T00:00:00Z
---

## Current Test

[Test 1 (CICD-02) resolved: owner responded "deferred — tracked in 28-HUMAN-UAT.md" 2026-07-18;
Tests 2-4 remain correctly deferred/parked]

## Tests

### 1. Enable GitHub Pages (CICD-02, do-now, host-independent)
expected: Repo `Settings → Pages → Build and deployment → Source: GitHub Actions`. This is a
manual, once-only toggle — enabling Pages via API requires an elevated
`administration:write`/`pages:write` PAT, which this project's zero-secrets-in-CI posture
(Phase 22 D-04) deliberately does not carry, so Claude cannot perform it via CLI/API
(28-RESEARCH.md "Don't Hand-Roll"). D-03 selects "attempt what's doable now" for this specific
item because, unlike CICD-03, it has no tag dependency.

**The toggle alone publishes nothing (28-RESEARCH.md Pitfall 2).** `.github/workflows/pages.yml`
fires only on:
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
i.e. a successful `ci.yml` run triggered by a push/PR to `main`. At research time, local `main`
was **92 commits ahead of `origin/main`** (`git rev-list --count origin/main..HEAD` → `92`) — so
`ci.yml` has not run against any of that work yet, and `pages.yml` cannot have fired regardless
of whether the Pages source is set. The site goes live only after those commits are pushed
(the consolidated push is `/gsd:complete-milestone`'s job, not this phase's) and a subsequent
`ci.yml` run on `main` succeeds.

result: **BLOCKED-ON-HUMAN — do-now, prompted this session, owner deferred.** The owner was
prompted during Phase 28 execution (Task 2, D-03) to perform this toggle and responded
"deferred — tracked in 28-HUMAN-UAT.md" (2026-07-18). This is one of the two accepted outcomes
("toggled" or "deferred") and closes the phase green per the Phase 23/24 precedent. The toggle
remains unset; whenever the owner performs it, the toggle by itself still does not make the site
live — that additionally needs the push + CI-success step described in Test 2 below.

### 2. First real `pages.yml` run — blocked on Test 1 and the consolidated push
expected: After Test 1's toggle is set AND the milestone-close consolidated push lands on
`origin/main` with a successful `ci.yml` run, `pages.yml` fires automatically (see the trigger
condition above), publishes `site/dist/` via `actions/deploy-pages`, and
`jadrianports.github.io/dexter` resolves and matches the local build.
result: **NOT DONE — sequencing, not a bug.** No push to `origin/main` has happened from this
phase (commit-only, matching the single-consolidated-push protocol); the consolidated push is
`/gsd:complete-milestone`'s responsibility, not Phase 28's.

### 3. Flip the GHCR package to public, then verify a logged-out pull (CICD-03, post-tag, sequenced)
expected: **Only after** the `v1.5` tag — cut by `/gsd:complete-milestone`, NOT this phase
(D-02/D-05) — fires `release.yml`:
```yaml
# Source: .github/workflows/release.yml:7-9
on:
  push:
    tags: ["v*"]
```
and creates the package on GHCR, go to
`github.com/users/jadrianports/packages/container/dexter/settings` → Change visibility →
Public. Then, from a logged-out shell: `docker logout ghcr.io && docker pull
ghcr.io/jadrianports/dexter:v1.5` (or whichever tag was cut) should succeed. GHCR packages are
private by default regardless of the source repo's own visibility, and the toggle is a GitHub UI
setting on the package's own page — it cannot be reached from the publishing workflow without a
new PAT carrying package-admin scope, which this project deliberately does not carry
(28-RESEARCH.md, cross-referenced against 23-RESEARCH.md's identical finding).

**Ordering is strict, not optional (28-RESEARCH.md Pitfall 3):** at research time no `v1.5` tag
existed yet (`gh api repos/jadrianports/dexter/tags` — tip is `v1.4`), so there is nothing on
GHCR to flip visibility on until the first `release.yml` run creates the package. Do this
immediately **after** the milestone tag lands, never before.
result: **BLOCKED-ON-HUMAN — correctly parked, post-tag.** No `v1.5` tag exists yet, so
`release.yml` has never run and there is no package to flip. This step cannot begin until
`/gsd:complete-milestone` cuts the tag.

### 4. Supply two verbatim real Dexter lines for the demo (PORT-02, parked, needs live bot)
expected: Run the bot, capture two real Dexter outputs verbatim — one `/ask` or `/roast`
response, one ambient/roast line — from a live Discord session. Paste them byte-for-byte
(no edits, no "improvements") into the `text` fields of `site/src/data/demo-transcript.ts`,
replacing the `{{DEXTER_DEMO_LINE_1}}` / `{{DEXTER_DEMO_LINE_2}}` tokens, then rebuild
(`cd site && npm run build`).

**Do NOT author or "improve" lines (D-06).** The demo's legitimacy rests entirely on the words
being real — the phase must resist the temptation to substitute plausible-sounding invented text
to "finish" this item. The `previewSample` scaffolding in `demo-transcript.ts` stays untouched
until the real capture happens; `resolveLine()` already falls back to the labeled preview sample
while a token is unfilled, so the site never silently ships a fake line as if it were real.
result: **BLOCKED-ON-HUMAN — parked, needs the live bot (DEPLOY-F1-gated).** Neither token has
been replaced. `services/gemini.py::chat()` logs `len(response.text)`, never the text itself, at
every call site, so `logs/dexter.log` structurally cannot supply this — it must come from a live
Discord capture (23-RESEARCH.md Finding 1, still true). Once real lines are captured, re-run
`docs/scripts/render_demo_gif.py`'s local setup if a refreshed `docs/demo.gif` is also desired
(Phase 23 precedent).

### 5. Local visual pass (PORT-05 confirmation, parked, host-INDEPENDENT, owner-closable at will)
expected: `cd site && npm run dev`, open the local URL, and eyeball three things: the
proper-case hero/feature copy reads in the site's own voice; the staged demo animation CYCLES
through messages rather than sitting frozen on one frame; the dark "after hours" visual identity
reads right (not a generic light theme).
result: **BLOCKED-ON-HUMAN — parked, but NOT part of the 33-item live-Discord tail.** This is
the one parked check in the whole v1.5 deferred-items list that needs no residential Discord
host — `/site` is a static build, so the owner can close this whenever, with zero host
dependency. The automated half of this confirmation (drift-guard grep assertions over
`site/dist/` + the `resolveLine()` token-vs-preview regression guard) is NOT part of this file —
see `## Gaps` below.

## Summary

total: 5
passed: 0
issues: 0
pending: 0
skipped: 0
blocked: 5

## Gaps

- **This file covers only the genuinely manual, human-only items** — CICD-02 (do-now, prompted
  this session), CICD-03 (post-tag, sequenced), PORT-02 (parked, needs live bot), and the PORT-05
  local visual pass (parked, host-independent). It does not re-document anything machine-checkable.
- **PORT-05's automated confirmation half (D-01.1/D-01.2) is NOT in this runbook.** It is the
  committed guard suite from plan 28-01: `npm run build` in `site/` boots clean, the drift-guard
  grep assertions over the built `site/dist/` (no leaked `{{DEXTER_DEMO_LINE` tokens, proper-case
  copy present, "after hours" identity present), and the `resolveLine()` token-vs-preview
  regression guard (`tests/test_demo_transcript_guard.py`) — all of which run in CI, not by an
  owner's hand.
- **CICD-02 is the one item this phase attempted "now"** per D-03 — the owner was prompted during
  execution (Task 2). Whether the answer was "toggled" or "deferred", the toggle alone does not
  publish the site; Test 2 (the actual live `pages.yml` run) remains blocked on the milestone's
  consolidated push, independent of the owner's Test 1 answer.
- **CICD-03 cannot even begin until the `v1.5` tag exists** — sequencing, not a failure. Nothing
  in Phase 28 can close it; `/gsd:complete-milestone` cutting the tag is the unblock.
- **PORT-02 stays intentionally incomplete** — the demo mock and its `resolveLine()` fallback are
  mechanically ready to accept real lines the moment the owner supplies them; nothing in this
  phase invents placeholder text to "finish" it, by design (D-06).
- **Requirement traceability:** per the Phase 28 plan's instruction, `.planning/REQUIREMENTS.md`
  is left untouched by this file — the orchestrator reconciles PORT-02/CICD-02/CICD-03 completion
  during phase verification and at milestone close, using this file as the evidence ledger for
  what is proven versus what remains human-blocked.
</content>
