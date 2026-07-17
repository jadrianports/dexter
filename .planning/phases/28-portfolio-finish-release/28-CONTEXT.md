# Phase 28: Portfolio Finish & Release - Context

**Gathered:** 2026-07-18
**Status:** Ready for planning

> **Session note:** The user launched `/gsd:discuss-phase 28`, was presented three phase-specific
> gray areas (verification method, release-tag sequencing, blocked-on-human hand-off) and answered
> all three with an affirmative selection (not an AFK adoption): **verify = automated/guard checks +
> a host-independent local visual pass**, **tag = leave to `/gsd:complete-milestone`**, **hand-off =
> attempt what's doable now**. During the discussion Claude surfaced an ordering dependency between
> the last two answers and reconciled it inline (see D-05) — the user did not revise.
>
> This is the **v1.5 milestone close-out phase.** PORT-05 already shipped (`c7fd22e`); the phase may
> legitimately close having written **little or no new feature code** — its deliverables are a
> verification pass, a small durable guard, and an owner-action runbook.

<domain>
## Phase Boundary

Phase 28 **confirms the already-shipped portfolio surface is still true and produces the owner-action
release runbook** — it is a *verification + hand-off* phase, not a build phase.

**In scope:**
- **PORT-05 confirmation** — verify the shipped `/site` landing-page redesign (`c7fd22e`) still holds:
  proper-case copy in the site's own voice, a working (non-frozen) staged demo animation, and a
  distinct "after hours" visual identity. Verification is **automated checks + a durable guard test +
  a parked (host-independent) local visual pass** (D-01).
- **A single owner-action runbook** (`28-HUMAN-UAT.md`, following the Phase 23/24 precedent) with
  exact step-by-step instructions for the three blocked-on-human items (D-04).
- **CICD-02 (GitHub Pages) attempted during the phase** — it is host-independent and has no tag
  dependency, so the owner is prompted to perform the one GitHub-UI toggle during/after execution
  (D-03/D-05).

**Out of scope:**
- **Cutting the `v1.5` release tag** — deliberately left to `/gsd:complete-milestone`, which runs
  after this phase; the tag is a milestone artifact, not a Phase 28 deliverable (D-02). The `release.yml`
  run (and therefore CICD-03's image publish) fires from that tag, so it lands at/after milestone
  close, not inside this phase (D-05).
- **PORT-02's real demo lines** — needs a live bot to capture two verbatim Dexter lines; stays parked
  (DEPLOY-F1-gated), documented in the runbook. The `{{DEXTER_DEMO_LINE_*}}` tokens + `previewSample`
  scaffolding stay untouched by design (D-06).
- **Any redesign / new build work on `/site`** — PORT-05 is done; this phase confirms, it does not
  rebuild.
- **The 33 carried live-Discord / verification tail items** — remain parked behind the residential host.

</domain>

<decisions>
## Implementation Decisions

### PORT-05 verification method

- **D-01 (user-selected): automated checks + a durable guard test + a host-independent local visual
  pass.** Concretely:
  1. **Automated:** `npm run build` in `site/` boots clean; `pytest tests/test_site_drift_guard.py`
     stays green; a grep pass over the built `site/dist/` asserts (a) no raw `{{DEXTER_DEMO_LINE`
     token leaked into rendered HTML, (b) proper-case hero/feature copy present, (c) the "after hours"
     dark visual identity is present.
  2. **Guard test:** a small **committed** regression test locking the `resolveLine()` invariant —
     while a `text` field still holds an unfilled `{{...}}` token, `resolveLine()` returns the labeled
     `previewSample`, and **no raw `{{` token ever reaches rendered output.** This makes the
     token-vs-preview contract durable against future edits rather than a one-time manual check.
  3. **Parked local visual pass:** an owner checklist item (`npm run dev` in `site/`, eyeball
     proper-case copy, confirm the demo animation cycles rather than sits frozen, confirm the dark
     "after hours" identity) — **host-independent** (a static site needs no Discord/residential host),
     so unlike the other 33 parked items this one *can* be closed by the owner at will.
  *(Rejected: **automated checks only** — fastest and matches the "confirm it's still true" framing,
  but leaves the token/preview contract unguarded against future edits. Rejected: **guard test without
  the visual pass** — durable, but "working, non-frozen animation" and "after hours identity" are
  perceptual and warrant one human look, cheaply, since no host is needed.)*

### Release-tag sequencing

- **D-02 (user-selected): Phase 28 does NOT cut the `v1.5` tag — `/gsd:complete-milestone` does.**
  Phase 28 verifies, writes the runbook, and closes green; the actual `v1.5` git tag (which fires
  `.github/workflows/release.yml` on `tags: ["v*"]` → CICD-03's image publish) is cut by
  `/gsd:complete-milestone` afterward. Keeps phase and milestone concerns separate and matches how
  v1.0–v1.4 were tagged at milestone close.
  *(Rejected: **Phase 28 cuts the tag** — more self-contained, but conflates milestone tagging with
  phase work and pre-empts `complete-milestone`, which expects to own the tag.)*

### Blocked-on-human hand-off

- **D-03 (user-selected): attempt what's doable now; runbook covers the rest.** Write the runbook
  (D-04), and during/after phase execution prompt the owner to perform the **CICD-02 GitHub Pages
  toggle** (host-independent, no tag dependency). **CICD-03 and PORT-02 cannot fully complete inside
  the phase** (see D-05) and stay in the runbook as sequenced/parked.
  *(Rejected: **single runbook, all three deferred** — cleanest close and matches Phase 23/24
  precedent exactly, but leaves CICD-02 parked when it is genuinely actionable now with zero host
  dependency.)*

- **D-04: one owner-action runbook — `28-HUMAN-UAT.md`.** Follows the `23-HUMAN-UAT.md` /
  `24-HOST-UAT.md` precedent. Exact step-by-step for all three items so the owner can execute without
  further guidance:
  - **CICD-02:** `Settings → Pages → Source = GitHub Actions`; the already-wired `pages.yml` deploys
    on the next CI-success-on-`main` (it triggers on `workflow_run: ["CI"] completed` + success +
    `head_branch == main`); verify the public URL renders.
  - **CICD-03:** after the `v1.5` tag fires `release.yml`, flip the GHCR package visibility, then
    verify the published image (see D-05 for why this is post-tag).
  - **PORT-02:** run the bot, capture **two verbatim** real Dexter lines (`/ask` or `/roast` + an
    ambient/roast line), paste them into the `text` fields of `site/src/data/demo-transcript.ts`
    replacing the `{{DEXTER_DEMO_LINE_1/2}}` tokens — **do not author or "improve" lines**; rebuild.

- **D-05 (Claude-surfaced, user-affirmed inline): the tag-deferral (D-02) and "attempt now" (D-03)
  reconcile by ordering.**
  - **CICD-02** truly completes now — no tag dependency, host-independent.
  - **CICD-03** is gated on the `v*` tag, which D-02 defers to `/gsd:complete-milestone`; and GHCR
    package visibility can only be flipped **after** that first `release.yml` run creates the package.
    So CICD-03 sequences **immediately after the milestone tag**, not inside Phase 28. The runbook
    documents it in that order; it stays deferred but with a concrete "do this right after the tag" step.
  - **PORT-02** stays parked (needs the live bot).

- **D-06: PORT-02's `previewSample` scaffolding stays untouched until the live capture.** The
  `demo-transcript.ts` PLACEHOLDER CONTRACT is intentional: tokens are the source of truth, and
  `previewSample` renders the finished component during development without claiming real output. The
  phase must **not** substitute invented lines to "finish" PORT-02 — that would violate the contract
  (legitimacy rests on the words being real).

### Claude's / Planner's Discretion (do NOT re-ask the user)

- **Exact guard-test shape and location** for the D-01.2 `resolveLine()` / no-leaked-token invariant —
  follow the existing `tests/test_site_drift_guard.py` pattern (a Python test asserting over the
  built `site/dist/` and/or the TS source), or a lightweight node/vitest test if the site already has
  a test runner. Whichever matches the repo's existing site-testing convention; keep it mock-free and
  non-vacuous (a positive control proving it would fail if a raw token leaked).
- **Exact grep assertions** for the D-01.1 automated dist checks (which strings prove "proper-case"
  and "after hours" identity) — planner's discretion, grounded in the shipped `c7fd22e` copy.
- **Runbook wording/format** for `28-HUMAN-UAT.md` — match the `23-HUMAN-UAT.md` / `24-HOST-UAT.md`
  structure.
- **Whether a PORT-02 "tokens replaced" drift guard** is worth adding (a test that flips from
  green-on-tokens to green-on-real-lines) — optional; only if it's cheap and non-vacuous. Not required.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements (this phase's authority)
- `.planning/ROADMAP.md` §"Phase 28: Portfolio Finish & Release" — the goal + all four success
  criteria (SC-1 PORT-05 confirmation; SC-2 PORT-02; SC-3 CICD-02; SC-4 CICD-03) and the "UI hint:
  yes — no new build work expected" note.
- `.planning/REQUIREMENTS.md` §"Portfolio" — **PORT-05** (done, `c7fd22e`), **PORT-02**, **CICD-02**,
  **CICD-03** verbatim (all three carried from v1.4, blocked-on-human); §"Traceability" (all four →
  Phase 28).
- `.planning/STATE.md` §"Deferred Items → Blocked-on-human v1.5 requirements" — the exact status of
  PORT-02 / CICD-02 / CICD-03 (and HOST-04); §"Deferred Items" preamble (36 carried items, zero code
  gaps, CI green at HEAD).

### The `/site` landing page (PORT-05 / PORT-02 surface)
- `site/src/data/demo-transcript.ts` — **the PORT-02 PLACEHOLDER CONTRACT.** `{{DEXTER_DEMO_LINE_1}}`
  / `{{DEXTER_DEMO_LINE_2}}` tokens + labeled `previewSample` fallbacks + `resolveLine()` (returns
  `previewSample` while a token is unfilled). **D-01.2's guard test subject; D-06's untouchable
  scaffolding.**
- `site/src/components/DemoMock.astro` + `site/src/components/DemoMessage.astro` — the staged demo
  animation (SC-1 "working, non-frozen animation"). `DemoMock.astro:7` documents the preview-sample
  render.
- `site/src/components/Hero.astro`, `Features.astro`, `FeatureCard.astro`, `Boundaries.astro`,
  `Cta.astro`, `Footer.astro` — the redesigned proper-case copy + "after hours" identity (SC-1).
- `site/src/styles/global.css` + `site/src/layouts/Layout.astro` — the dark "after hours" visual
  identity.
- `site/package.json` — `npm run build` (D-01.1 clean-build check) and `npm run dev` (D-01.3 local
  visual pass); `site/astro.config.mjs` — the GitHub Pages `/dexter` subpath base.

### CI/CD workflows (CICD-02 / CICD-03)
- `.github/workflows/pages.yml` — **CICD-02's deploy path.** Triggers on `workflow_run: ["CI"]
  completed` + `conclusion == success` + `head_branch == main` (already wired — the only missing
  piece is the owner's `Settings → Pages → Source = GitHub Actions` toggle).
- `.github/workflows/release.yml` — **CICD-03's publish path.** Triggers on `push: tags: ["v*"]`,
  `permissions: packages: write`, `push: true` to GHCR. Fires from the `v1.5` tag that D-02 defers to
  `/gsd:complete-milestone`.
- `.github/workflows/ci.yml` — the blocking Ruff + pytest gate (pgvector service container) whose
  success on `main` is what triggers `pages.yml`.

### Verification / test precedent
- `tests/test_site_drift_guard.py` — **the existing site guard D-01.2 extends/mirrors** (asserts over
  the built site). Keep new guards non-vacuous with a positive control.
- `tests/test_invite_drift_guard.py` — the invite-URL drift guard (Phase 22/23), extended to
  `site/dist/`; the "non-vacuous with positive control" convention.
- `.planning/phases/23-portfolio-surface-ci-cd/23-HUMAN-UAT.md` — **the owner-runbook precedent D-04
  follows** (the original home of PORT-02 / CICD-02 / CICD-03 before they carried to v1.5).
- `.planning/phases/24-hosting-honesty-docker/24-HOST-UAT.md` — the second owner-runbook precedent
  (HOST-04 Render-deletion checklist shape).

### CLAUDE.md invariants this phase must honor
- §"Build Phases → Phase 23" — PORT-02/CICD-02/CICD-03 are the **deferred blocked-on-human** trio;
  the drift guard + `/site` + invite source-of-truth context.
- §"Critical Rules" 7/8 (lowercase, ≤1 emoji) — applies only if any Dexter-voice copy is touched
  (it should not be — PORT-02 lines are captured verbatim, not authored).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`site/src/data/demo-transcript.ts::resolveLine()`** — already implements the token→previewSample
  fallback; D-01.2's guard just locks its behavior, no new logic needed.
- **`tests/test_site_drift_guard.py`** — an existing Python test that builds/reads the site; the
  natural home (or sibling) for the D-01.2 token-leak guard.
- **`.github/workflows/pages.yml` + `release.yml`** — both CI/CD paths are already authored and
  wired; the only remaining work is owner-side GitHub-UI toggles (CICD-02/CICD-03), not repo code.
- **`.planning/phases/23-portfolio-surface-ci-cd/23-HUMAN-UAT.md`** — a ready template for the
  `28-HUMAN-UAT.md` runbook.

### Established Patterns
- **Blocked-on-human items → a `*-HUMAN-UAT.md` / `*-HOST-UAT.md` owner checklist, marked deferred,
  phase closes green** (Phase 23/24) — D-04.
- **Non-vacuous drift guards with a positive control** (Phase 22/23 invite guard) — D-01.2.
- **Milestone tags are cut at `/gsd:complete-milestone`, not inside a phase** (v1.0–v1.4) — D-02.
- **The demo-line PLACEHOLDER CONTRACT: real verbatim output only, never authored** — D-06.

### Integration Points
- `site/dist/` (build output) — D-01.1 grep assertions + D-01.2 guard read from here.
- `tests/` — the D-01.2 guard test lands here (Python, mirroring `test_site_drift_guard.py`).
- `28-HUMAN-UAT.md` (new, in the phase dir) — the D-04 owner runbook.
- **No changes** to `demo-transcript.ts` tokens (D-06), to `release.yml`/`pages.yml` (already wired),
  or to any Dexter-voice copy.

</code_context>

<specifics>
## Specific Ideas

- **"This phase confirms, it doesn't rebuild."** PORT-05 shipped at `c7fd22e`; Phase 28's job is to
  prove it's still true and hand off the owner steps — a light close-out, by design.
- **The one parked item that isn't host-gated.** Every other parked check needs the residential
  Discord host; the D-01.3 local visual pass runs against a static site with `npm run dev`, so the
  owner can close it whenever — it does not join the 33-item live-Discord tail.
- **CICD-02 is a single toggle away.** `pages.yml` is fully wired; the only missing piece is
  `Settings → Pages → Source = GitHub Actions`. That asymmetry is why D-03 attempts it now.
- **CICD-03 can't beat its own tag.** The GHCR package doesn't exist until `release.yml` runs, and
  `release.yml` needs the `v1.5` tag D-02 defers to milestone-complete — so the visibility flip is
  strictly post-tag (D-05), not a Phase 28 in-flight action.
- **Verbatim or nothing (PORT-02).** The demo's legitimacy rests on the words being real; the phase
  must resist the temptation to "finish" PORT-02 with plausible-sounding invented lines (D-06).

</specifics>

<deferred>
## Deferred Ideas

- **PORT-02 real demo lines** → parked behind the live bot (DEPLOY-F1); runbook-documented (D-04/D-06).
- **CICD-03 GHCR visibility flip + first `release.yml` run** → sequenced immediately after the
  `/gsd:complete-milestone` `v1.5` tag (D-05); not a Phase 28 in-flight action.
- **HOST-04 (delete the dashboard-side Render service)** → a separate carried blocked-on-human item
  (owner Render-UI step); not in Phase 28's scope, tracked in STATE.md.
- **A PORT-02 "tokens replaced" drift guard** → optional planner's-discretion item (D-06 discretion
  note); add only if cheap and non-vacuous.
- **The 33 live-Discord / verification tail items** → remain parked behind the residential host;
  unchanged by this phase.

### Reviewed Todos (not folded)
None — `todo.match-phase 28` returned zero matches (`todo_count: 0`).

</deferred>

---

*Phase: 28-portfolio-finish-release*
*Context gathered: 2026-07-18*
