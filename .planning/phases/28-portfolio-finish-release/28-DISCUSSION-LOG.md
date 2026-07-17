# Phase 28: Portfolio Finish & Release - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-18
**Phase:** 28-portfolio-finish-release
**Areas discussed:** PORT-05 verification method, Release-tag sequencing, Blocked-on-human hand-off

---

## PORT-05 verification method

| Option | Description | Selected |
|--------|-------------|----------|
| Automated checks only | `npm run build` clean + site drift-guard green + grep asserts (proper-case, no leaked `{{...}}` tokens, "after hours" identity). No new test code, no human eyeball. | |
| Add a regression guard | Automated checks PLUS a committed test locking the `resolveLine()` token→previewSample invariant and no-raw-token-in-HTML. | |
| + local visual pass | Automated/guard checks PLUS a parked host-independent local visual pass (`npm run dev`, eyeball copy/animation/identity). | ✓ |

**User's choice:** + local visual pass
**Notes:** Captured as automated dist checks + the durable `resolveLine()` guard test (the "guard" in "automated/guard checks") + a parked but host-independent local visual pass. The visual pass is the one parked item that does NOT need the residential Discord host — a static site runs under `npm run dev`.

---

## Release-tag sequencing

| Option | Description | Selected |
|--------|-------------|----------|
| Leave tag to complete-milestone | Phase 28 verifies + documents runbook + closes green; the `v1.5` tag (fires `release.yml` → CICD-03) is cut by `/gsd:complete-milestone` afterward. Matches v1.0–v1.4. | ✓ |
| Phase 28 cuts the tag | Phase 28 pushes the `v1.5` tag itself so `release.yml` fires in-phase. More self-contained but conflates milestone tagging with phase work. | |

**User's choice:** Leave tag to complete-milestone
**Notes:** The tag is a milestone artifact, not a phase deliverable. Consequence surfaced inline: CICD-03's `release.yml` run therefore lands at/after milestone close, not inside Phase 28 (see reconciliation under hand-off).

---

## Blocked-on-human hand-off

| Option | Description | Selected |
|--------|-------------|----------|
| Single owner runbook, deferred | One `28-HUMAN-UAT.md` with exact steps for PORT-02/CICD-02/CICD-03, all marked deferred, close green (Phase 23/24 precedent). | |
| Attempt what's doable now | Same runbook, but the phase also prompts the owner to perform the pure GitHub-UI steps (Pages toggle; GHCR visibility) now; only PORT-02 (needs live bot) stays parked. | ✓ |

**User's choice:** Attempt what's doable now
**Notes:** Claude surfaced and the user affirmed an ordering reconciliation between this and the tag decision: **CICD-02** (Pages toggle) truly completes now — host-independent, no tag dependency. **CICD-03** cannot fully complete in-phase — the GHCR package only exists after the first `release.yml` run, which needs the `v1.5` tag deferred to `/gsd:complete-milestone`; so the visibility flip sequences immediately after that tag. **PORT-02** stays parked (needs the live bot). The `demo-transcript.ts` tokens + `previewSample` scaffolding stay untouched — no invented lines (PLACEHOLDER CONTRACT).

---

## Claude's Discretion

- Exact guard-test shape/location for the `resolveLine()` / no-leaked-token invariant (mirror `tests/test_site_drift_guard.py`, non-vacuous with a positive control).
- Exact grep assertions proving "proper-case" and "after hours" identity in `site/dist/`.
- `28-HUMAN-UAT.md` runbook wording/format (match `23-HUMAN-UAT.md` / `24-HOST-UAT.md`).
- Whether an optional PORT-02 "tokens replaced" drift guard is worth adding — only if cheap and non-vacuous.

## Deferred Ideas

- PORT-02 real demo lines → parked behind the live bot (DEPLOY-F1); runbook-documented.
- CICD-03 GHCR visibility flip + first `release.yml` run → sequenced right after the milestone `v1.5` tag.
- HOST-04 (delete dashboard-side Render service) → separate carried blocked-on-human item, tracked in STATE.md.
- A PORT-02 "tokens replaced" drift guard → optional planner's-discretion item.
- The 33 live-Discord / verification tail items → remain parked behind the residential host.
