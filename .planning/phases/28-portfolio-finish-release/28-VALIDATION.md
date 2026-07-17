---
phase: 28
slug: portfolio-finish-release
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-18
---

# Phase 28 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (existing repo suite) |
| **Config file** | pyproject.toml (ruff) — no separate pytest config |
| **Quick run command** | `pytest tests/test_demo_transcript_guard.py tests/test_site_drift_guard.py -q` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | ~7 min (full) / ~5 s (site guards only) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_demo_transcript_guard.py tests/test_site_drift_guard.py -q`
- **After every plan wave:** Run `pytest -q` (full suite; run FOREGROUND — backgrounded runs get killed ~15%)
- **Before `/gsd-verify-work`:** Full suite must be green, AND
  `SITE_DIST_REQUIRED=1 pytest tests/test_demo_transcript_guard.py tests/test_site_drift_guard.py -q`
  run at least once locally against a built `dist/` (proves the hard-fail path, not just the soft-skip)
- **Max feedback latency:** ~10 seconds (site-guard-only run)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 28-01-T1 | 28-01 | 1 | PORT-05 | — | Fresh clean build; existing PORT-05 invite guard still green | build + integration | `cd site && npm run build && cd .. && pytest tests/test_site_drift_guard.py -q` | ✅ (existing guard) | ⬜ pending |
| 28-01-T2 | 28-01 | 1 | PORT-05 | T-28-01 | No raw `{{...}}` token in shipped `dist/`; previews + proper-case + `0a0c11`/`ffb454` present; positive control non-vacuous; source token/preview pairing locked | integration (dist scan) + unit (controls) + structural | `pytest tests/test_demo_transcript_guard.py -q` | ❌ W0 — new file this phase | ⬜ pending |
| 28-02-T1 | 28-02 | 1 | PORT-02, CICD-02, CICD-03 | T-28-02 | Owner runbook documents all three blocked-on-human items + parked visual pass; verbatim-only contract stated | doc guard (grep) | `grep -q "Source: GitHub Actions" .../28-HUMAN-UAT.md && grep -q "release.yml" ... && grep -q "DEXTER_DEMO_LINE" ... && grep -q "## Summary" ...` | ❌ W0 — new file this phase | ⬜ pending |
| 28-02-T2 | 28-02 | 1 | CICD-02 | — | Owner prompted for the Pages toggle (attempt-now); accepts toggled/deferred | manual-only (checkpoint:human-action) | N/A — owner GitHub-UI action (automation ruled out: elevated PAT not carried) | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_demo_transcript_guard.py` — the D-01.1 + D-01.2 committed guard; locks the
      `resolveLine()` token→previewSample invariant over the built `site/dist/` (dist-scan, no raw
      `{{...}}` token, previews + proper-case copy + `0a0c11`/`ffb454` identity present), with a
      mandatory positive control and a build-independent source-level structural guard. Does not exist yet.
- [ ] `.planning/phases/28-portfolio-finish-release/28-HUMAN-UAT.md` — the D-04 owner runbook. Does not
      exist yet.
- [ ] No framework install needed — pytest and Astro are both already present and verified working.

*Note: both Wave 0 artifacts are created inside Wave 1 execution (this is a light verification+handoff
phase with no pre-existing scaffolding gap to fill before other work).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Demo animation cycles (non-frozen) + "after hours" identity reads right | PORT-05 | Perceptual; host-INDEPENDENT (static site, `npm run dev`) — owner-closable at will | D-01.3 local visual pass (28-HUMAN-UAT.md) |
| Two verbatim real Dexter lines replace `{{DEXTER_DEMO_LINE}}` tokens | PORT-02 | Needs live bot to capture real output (DEPLOY-F1-gated) | 28-HUMAN-UAT.md — parked |
| GitHub Pages live at public URL | CICD-02 | Owner GitHub-UI toggle + push to origin/main + CI success | 28-HUMAN-UAT.md — do-now (attempt-now checkpoint 28-02-T2) |
| GHCR image published + visibility set | CICD-03 | Owner GitHub-UI, post `v1.5` tag (cut by /gsd:complete-milestone) | 28-HUMAN-UAT.md — post-tag sequenced |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (28-02-T2 is a checkpoint:human-action — manual by design, automation ruled out)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (2026-07-18) — automated PORT-05 confirmation (28-01) plus the D-04 owner runbook
(28-02); the three genuinely blocked-on-human items are manual-only by design, matching the Phase 23/24
precedent.
