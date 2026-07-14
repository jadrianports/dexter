---
phase: 23-portfolio-surface-ci-cd
verified: 2026-07-14T21:15:00Z
status: human_needed
score: 8/11 must-haves code-verified; 3 blocked-on-human (expected, not code gaps)
overrides_applied: 0
human_verification:
  - test: "Supply the verbatim Dexter transcript (PORT-02, D-06)"
    expected: "User pastes two real, verbatim Dexter lines into 23-DEMO-TRANSCRIPT.md, then into site/src/data/demo-transcript.ts, replacing {{DEXTER_DEMO_LINE_1}}/{{DEXTER_DEMO_LINE_2}}"
    why_human: "Dexter's real output cannot be sourced from logs (logs/dexter.log only logs response length, never the text) or fabricated without violating D-06 honesty"
  - test: "Render docs/demo.gif from the mock once Test 1 lands"
    expected: "cd site && npm ci && npm run build, then python scripts/render_demo_gif.py produces a committed docs/demo.gif <=2MB"
    why_human: "Blocked on the transcript; script is written and validated end-to-end against a scratch output this session"
  - test: "Enable GitHub Pages (CICD-02)"
    expected: "Repo Settings -> Pages -> Build and deployment -> Source: GitHub Actions"
    why_human: "Manual one-time repo setting; cannot be automated without a PAT this project's zero-secrets-in-CI posture deliberately excludes"
  - test: "First real pages.yml run"
    expected: "After the Pages toggle and the consolidated push, pages.yml runs on push to main and jadrianports.github.io/dexter resolves and matches the local build"
    why_human: "Requires a live GitHub Actions run this verifier cannot trigger"
  - test: "Flip the GHCR package to public, then verify a logged-out docker pull (CICD-03, D-17)"
    expected: "Package visibility flipped to Public on GHCR's own settings page; docker pull ghcr.io/jadrianports/dexter:<tag> succeeds logged-out"
    why_human: "GHCR visibility is a manual UI toggle on the package's own page, unreachable from the publishing workflow without a new PAT this project deliberately does not carry"
  - test: "First real release.yml run"
    expected: "Pushing a v* tag triggers release.yml; multi-arch (amd64+arm64) image builds and publishes to GHCR"
    why_human: "No tag has been pushed yet; requires a live GitHub Actions run"
  - test: "README renders correctly on github.com (PORT-03)"
    expected: "All 5 badges resolve, the mermaid graph TD renders as a diagram not a raw code fence"
    why_human: "GitHub's markdown/mermaid rendering pipeline is not reproducible outside github.com"
  - test: "CI badge is green at the code's real HEAD (PORT-03)"
    expected: "gh run list --branch main --workflow CI --limit 1 reports success at the exact commit SHA the badge describes"
    why_human: "The most recent green run predates plans 23-02..23-07; only proven true after the orchestrator's consolidated push and a fresh run"
  - test: "Landing page visual and copy review (PORT-01, PORT-04)"
    expected: "jadrianports.github.io/dexter reads as disclosure not apology; hosting caveat sits immediately before the closing CTA; demo mock and README tell the same story once the transcript lands"
    why_human: "Taste and honesty-of-tone are not machine-assertable; the page is not yet live to review in deployed form"
---

# Phase 23: Portfolio Surface & CI/CD — Verification Report

**Phase Goal:** Ship a public portfolio landing page (`/site`) and complete the CI/CD story (Pages deploy + GHCR publish) so Dexter is presentable to a recruiter, on top of an honest architecture-case-study README — without misrepresenting anything not yet actually running.

**Verified:** 2026-07-14T21:15:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Summary Verdict

**No code gaps found.** Every requirement that can be resolved by code exists, builds, and is substantively wired — verified directly against the built artifact and a clean local test run, not against SUMMARY.md narration. Three requirements (PORT-02, CICD-02, CICD-03) are genuinely and correctly incomplete pending human/manual action (real Dexter transcript lines; the GitHub Pages source toggle; the GHCR visibility flip + first tag push) — this matches the phase's own honest self-reporting in `23-HUMAN-UAT.md` and `REQUIREMENTS.md`, and matches the `<known_deferred_do_not_flag_as_failures>` guidance given for this verification. These are escalation-gate items, not phase failures.

**Nothing has been pushed to origin/main yet** (26 commits ahead of `origin/main` as of this verification) — "green CI at HEAD over the new site/workflows" is pending the orchestrator's consolidated push, per the phase's own design.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | PORT-01: `site/` Astro project builds and presents hero + feature showcase + Add-to-Discord button | VERIFIED | `cd site && npm ci && npm run build` exits 0, produces `site/dist/index.html`. Verified in the built HTML: exactly 1 `<h1>`, canonical invite URL (`client_id=1492588698364018898...`) appears exactly 2x (Hero + Cta), 6 substantive `.feature-card` entries with real copy (full YouTube playback, AI with opinions, 5-button now-playing panel, long-term memory, unprompted personality, vision roasts) |
| 2 | PORT-02: demo GIF embedded, verbatim Dexter lines | BLOCKED-ON-HUMAN (expected) | `site/src/data/demo-transcript.ts` still carries `{{DEXTER_DEMO_LINE_1}}`/`{{DEXTER_DEMO_LINE_2}}` verbatim (confirmed present 2x each in `dist/index.html`); `docs/demo.gif` deliberately not rendered/committed (D-06/T-23-HONEST — rendering now would ship a placeholder-token GIF). `scripts/render_demo_gif.py` exists (182 lines, syntactically valid, validated end-to-end against a scratch output per SUMMARY). Tracked in `23-DEMO-TRANSCRIPT.md` (status: BLOCKED) and `23-HUMAN-UAT.md` items 1-2. Deferred by the user 2026-07-14 — matches phase context |
| 3 | PORT-03: README rewritten as architecture case study — CI badge, invite link, honest scope section | VERIFIED | `README.md` (181 lines, was 2 lines) has: CI badge pointing at `github.com/jadrianports/dexter/actions/workflows/ci.yml`, 4 tech badges, live-landing-page link, feature list, `mermaid graph TD` architecture diagram, 4 "hard problems" callouts, 4 honest boundaries section, canonical invite link with `logic/invite.py::build_invite_url()` cross-reference. `tests/test_invite_drift_guard.py` confirmed non-vacuous: README.md is in its scanned tracked-doc set, canonical URL found, zero offenders |
| 4 | PORT-04: honest boundaries present matching PROJECT.md facts (100-guild wall, on-demand hosting, savage-personality+kill-switch tradeoff, hybrid memory-scoping) | VERIFIED | All 4 boundaries present in both README.md and the built landing page (`Boundaries.astro` → `dist/index.html`, 4 `.boundary-item` entries confirmed by direct HTML inspection). Content matches CLAUDE.md/PROJECT.md facts: 100-guild verification wall, on-demand/residential-IP hosting (YouTube datacenter-IP block), full-savage personality + reactive kill-switch (2 choke points), hybrid memory scoping explicitly naming `/ask` as global-but-self-scoped (matches Phase 21's flagged requirement in STATE.md) |
| 5 | Invite drift guard (`tests/test_invite_drift_guard.py`) + site drift guard (`tests/test_site_drift_guard.py`) pass and are non-vacuous | VERIFIED | Ran directly: `SITE_DIST_REQUIRED=1 pytest tests/test_site_drift_guard.py tests/test_invite_drift_guard.py` → 12 passed. Non-vacuousness independently confirmed: site guard walks the real built `dist/**/*.html` (not `git ls-files`); has mandatory positive/negative controls (`test_dist_drift_guard_actually_detects_a_mismatch`, `test_dist_drift_guard_accepts_the_canonical_url`); README.md is genuinely in the invite guard's tracked-doc scan (previously vacuous, now real per 23-07 SUMMARY, independently confirmed by code read) |
| 6 | `ci.yml`/`pages.yml`/`release.yml` valid + least-privilege | VERIFIED | Read all 3 files directly. `ci.yml`: top-level `permissions: contents: read`, `pull_request` (never `_target`), `pgvector/pgvector:pg16` service container, new unprivileged `site:` job builds + drift-scans with `SITE_DIST_REQUIRED=1`. `pages.yml`: separate file, `pages: write` + `id-token: write` scoped only here, `workflow_run` dual filter (`conclusion == success && head_branch == main`), explicit `head_sha` checkout. `release.yml`: separate file, `packages: write` only, `push: tags: ["v*"]` trigger only, `GITHUB_TOKEN`-only auth (no new PAT), multi-arch QEMU+buildx build |
| 7 | Full suite green; no invented Dexter lines anywhere; no secrets introduced | VERIFIED | Ran `python -m pytest -q` directly: **1039 passed, 124 skipped (DB-gated, no local Postgres), 0 failed** in 423.6s — matches SUMMARY claims exactly. `ruff check .` and `ruff format --check .` both clean. Grepped `site/src/data/demo-transcript.ts` and `dist/index.html`: only placeholder tokens present, no invented/fabricated Dexter text. `requirements.txt`/`requirements-dev.txt` confirmed absent of `playwright`/`fonttools`/`brotli` (dev-machine-only tools per D-06/T-23-SC). `Dockerfile` confirmed clean — only `COPY requirements.txt` + `COPY . .`, `site/` excluded via `.dockerignore`; `site/node_modules`/`site/dist` confirmed absent from `git ls-files` |

**Score:** 8/8 code-resolvable truths verified; 3 requirement items (PORT-02, CICD-02, CICD-03) correctly and honestly blocked-on-human, matching the phase's own reporting.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `site/` (Astro project) | Buildable static site, hero/features/boundaries/cta | VERIFIED | Builds clean, `npm ci && npm run build` exits 0; all sections present and substantive in built HTML |
| `site/src/data/demo-transcript.ts` | Real Dexter lines | STUB (by design, tracked) | Placeholder tokens intact, correctly incomplete — not a silent stub, explicitly documented and tracked |
| `docs/demo.gif` | Committed GIF ≤2MB | MISSING (by design, tracked) | Deliberately withheld to avoid shipping a placeholder-token GIF; script exists and is validated |
| `README.md` | Architecture case study | VERIFIED | 181 lines, badges/mermaid/boundaries/invite link all present and substantive |
| `.github/workflows/ci.yml` | pytest+lint gate + site build/drift job | VERIFIED | Both jobs present, least-privilege, correct triggers |
| `.github/workflows/pages.yml` | CI-gated Pages deploy | VERIFIED (code); never run | Structurally correct, dual filter, scoped permissions |
| `.github/workflows/release.yml` | Multi-arch GHCR publish on tag | VERIFIED (code); never run | Structurally correct, tag-only trigger, scoped permissions |
| `tests/test_site_drift_guard.py` | Built-artifact drift guard | VERIFIED | 3/3 tests pass, non-vacuous (walks real `dist/`) |
| `tests/test_invite_drift_guard.py` | Tracked-doc drift guard | VERIFIED | 9/9 tests pass, non-vacuous (README.md now genuinely scanned) |
| `scripts/render_demo_gif.py` | GIF render pipeline | VERIFIED (substantive, not a stub) | 182 lines, valid Python, validated end-to-end against a scratch output per SUMMARY (not independently re-run by this verifier since it requires Playwright/ffmpeg install and produces no committable output while blocked) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `site/src/config.ts::INVITE_URL` | `logic/invite.py::build_invite_url()` | drift guard byte-comparison | WIRED | Both drift guards confirm byte-identical canonical URL across README, `/invite` command, and built site |
| `README.md` CI badge | `.github/workflows/ci.yml` | badge URL path | WIRED | Badge references the correct workflow filename in the correct repo |
| `ci.yml` `site:` job | `tests/test_site_drift_guard.py` | `SITE_DIST_REQUIRED=1 pytest` invocation | WIRED | Confirmed present in `ci.yml`; guard correctly converts missing-dist from skip to fail under this env var |
| `pages.yml` | `ci.yml` | `workflow_run` on `workflows: ["CI"]` | WIRED (code); unproven by a real run | Structurally correct trigger binding; name match confirmed (`ci.yml`'s `name: CI`) |
| `release.yml` | GHCR | `docker/build-push-action` + `metadata-action` | WIRED (code); unproven by a real run | Tag set, auth, and platforms all correctly configured; never executed |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `Hero.astro`/`Cta.astro` | `INVITE_URL` | `site/src/config.ts` (mirrors `config.py` constants) | Yes — byte-verified against `build_invite_url()` | FLOWING |
| `Features.astro` | static feature copy | hand-authored, matches real bot capabilities | Yes — cross-checked against CLAUDE.md's actual command/feature list | FLOWING |
| `Boundaries.astro` | static boundary copy | hand-authored, matches PROJECT.md/CLAUDE.md decisions | Yes — cross-checked | FLOWING |
| `DemoMock.astro` | `demoTranscript` | `site/src/data/demo-transcript.ts` | No — placeholder tokens, by design/tracked | STATIC (deliberate, honest) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Site builds | `cd site && npm ci && npm run build` | exit 0, 1 page built | PASS |
| Drift guards non-vacuous and green | `SITE_DIST_REQUIRED=1 pytest tests/test_site_drift_guard.py tests/test_invite_drift_guard.py` | 12 passed | PASS |
| Full suite green | `python -m pytest -q` | 1039 passed, 124 skipped, 0 failed | PASS |
| Lint/format clean | `ruff check .` / `ruff format --check .` | All checks passed / 122 files already formatted | PASS |
| No secrets in tracked site/ files | `git ls-files site/` + review | No `node_modules`/`dist` tracked; no credential patterns in tracked source | PASS |
| Workflow YAML structurally valid | direct read of all 3 workflow files | least-privilege confirmed, correct triggers | PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` convention exists in this project; no probes declared in PLAN/SUMMARY files for this phase. SKIPPED (no probe convention used by this project — pytest suite serves this role and was run directly above).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| PORT-01 | 23-03, 23-05, 23-06 | Landing page: hero + feature showcase + Add-to-Discord | SATISFIED | Verified above |
| PORT-02 | 23-02, 23-06, 23-07 | Demo GIF with real Dexter lines | BLOCKED-ON-HUMAN | Placeholder tokens intact by design, tracked in 23-HUMAN-UAT.md, deferred by user 2026-07-14 |
| PORT-03 | 23-07 | README architecture case study | SATISFIED | Verified above |
| PORT-04 | 23-06, 23-07 | Honest scope boundaries | SATISFIED | Verified above |
| CICD-02 | 23-04 | GitHub Pages auto-deploy | BLOCKED-ON-HUMAN | `pages.yml` code-complete, never run; Pages source toggle deferred by user |
| CICD-03 | 23-04 | GHCR image publish | BLOCKED-ON-HUMAN | `release.yml` code-complete, never run; no tag pushed, GHCR visibility flip deferred |
| CICD-01 | Phase 18 (carried) | pytest+lint CI + badge | SATISFIED (pre-existing, re-verified) | `ci.yml` `test:` job unchanged and green; badge present in README |

No orphaned requirements found — `REQUIREMENTS.md`'s traceability table for Phase 23 (PORT-01..04, CICD-02/03) matches exactly what each plan's `requirements-completed` frontmatter claims, and the final reconciliation commit (`a26dd5e`) correctly marks only PORT-01/03/04 complete.

### Anti-Patterns Found

None blocking. No `TBD`/`FIXME`/`XXX`/`HACK`/`placeholder` (outside the deliberately-tracked demo transcript, which documents its own placeholder status explicitly) found in `site/src/`, `README.md`, `.github/workflows/`, or `scripts/render_demo_gif.py`. The `{{DEXTER_DEMO_LINE_*}}` tokens are the one intentional exception — they are documented, tracked, and correctly reported as incomplete rather than silently shipped.

### Human Verification Required

See frontmatter `human_verification` list (9 items, carried forward from `23-HUMAN-UAT.md`, which this verifier independently read and cross-checked against the actual codebase rather than trusting at face value). Summary:

1. Supply verbatim Dexter transcript lines (PORT-02) — blocks item 2 below
2. Render `docs/demo.gif` once (1) lands
3. Enable GitHub Pages (CICD-02, manual repo setting)
4. Observe first real `pages.yml` run (blocked on 3 + the consolidated push)
5. Flip GHCR package visibility to public (CICD-03, manual UI toggle)
6. Observe first real `release.yml` run (blocked on a `v*` tag push)
7. Confirm README renders correctly on github.com (badges + mermaid diagram)
8. Confirm CI badge is green at the real post-push HEAD
9. Landing page visual/copy/tone review once live

### Gaps Summary

**No code gaps identified.** Every artifact this phase's plans claimed to deliver exists, builds, is substantively wired, and was independently re-verified against the actual filesystem/build output/test run rather than trusted from SUMMARY.md narration. The three incomplete requirements (PORT-02, CICD-02, CICD-03) are correctly and honestly reported as blocked-on-human in both `REQUIREMENTS.md` and `23-HUMAN-UAT.md`, matching the explicit deferred-items guidance given for this verification. This phase's distinguishing discipline — refusing to render a placeholder-token GIF, refusing to mark a requirement complete before its real-run proof exists — held up under independent re-verification.

**Recommendation:** proceed with the orchestrator's consolidated push. After the push, re-run (or have the owner manually run) the CI/Pages/Release workflows and update `23-HUMAN-UAT.md` items 3-8 as they clear; PORT-02/CICD-02/CICD-03 can then move from Pending to Complete in `REQUIREMENTS.md`.

---

*Verified: 2026-07-14T21:15:00Z*
*Verifier: Claude (gsd-verifier)*
