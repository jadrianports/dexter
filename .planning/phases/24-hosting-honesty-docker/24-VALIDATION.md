---
phase: 24
slug: hosting-honesty-docker
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-15
---

# Phase 24 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

This phase is a documentation / comment / config-prose scrub plus one new drift-guard test and one
parked human boot UAT. There is **no runtime code-path change**, so the validation backbone is a
false-positive-free repo-introspection **grep gate** (the phase's own success criterion) promoted
into a permanent CI drift guard (D-12), plus file-existence assertions and the full existing
pytest suite proving zero regression.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing repo-wide suite; no `[tool.pytest.ini_options]` — CI runs bare `pytest` against a `pgvector/pgvector:pg16` service container per `.github/workflows/ci.yml`) |
| **Config file** | none dedicated (`pyproject.toml` configures only `[tool.ruff]`) |
| **Quick run command** | `pytest tests/test_hosting_drift_guard.py tests/test_config.py -x` |
| **Full suite command** | `pytest` |
| **Estimated runtime** | ~1s for the drift guard + config tests; full suite as usual (DB-backed) |

---

## Sampling Rate

- **After every task commit:** Run the grep verification (Part 1 + Part 2 below, <1s) after each
  file's prose is rewritten; once `tests/test_hosting_drift_guard.py` exists, run
  `pytest tests/test_hosting_drift_guard.py -x` instead.
- **After every plan wave:** Run `pytest tests/test_hosting_drift_guard.py tests/test_config.py`
  + `ruff check .` (prose edits inside `.py` files must stay lint-clean).
- **Before `/gsd-verify-work`:** Full `pytest` suite green (proves zero runtime-code-path
  regression, consistent with "NO runtime code paths change") + drift guard green +
  `docs/DEPLOY-KOYEB.md` absent + `docs/DEPLOY-DOCKER.md` present.
- **Max feedback latency:** <5 seconds for the drift guard / config tests.

---

## Verification Grep Command (Validation Backbone)

Two-part, false-positive-free, scoped to tracked files, excluding the D-03 + D-10 sealed paths
(`.planning/`, `milestones/`, `docs/superpowers/`):

- **Part 1 — zero-tolerance (`Koyeb`, `Oracle`):** must return **zero** hits.
  `git grep -niE '\b(Koyeb|Oracle)\b' -- . ':!.planning' ':!milestones' ':!docs/superpowers'`
- **Part 2 — `Render` allowlist diff:** `Render` matches the English word "render/rendering"
  widely; only `bot.py:252,254` are true hosting-target positives (scrubbed by D-01). Enforce as
  an allowlist diff — any `Render` hit NOT in the known-legitimate set (the ~23 "render/rendering"
  occurrences) fails the gate.

`tests/test_hosting_drift_guard.py` (D-12) encodes both parts, mirroring
`tests/test_invite_drift_guard.py` shape, with a **positive control** (inject a fake `Koyeb`
string into a `tmp_path`/synthetic file → assert caught) and a **negative control** (real repo,
post-scrub, passes).

---

## Per-Task Verification Map

*(Planner refines Task IDs; this is the requirement→validation contract.)*

| Requirement | Behavior | Threat Ref | Test Type | Automated Command | File Exists | Status |
|-------------|----------|------------|-----------|-------------------|-------------|--------|
| HOST-01 | Zero live Koyeb/Oracle hosting refs; Render = allowlist-only, in tracked non-archive (non-sealed) files | — | repo-introspection (grep → pytest) | `pytest tests/test_hosting_drift_guard.py -x` | ❌ W0 (guard is new, D-12) | ⬜ pending |
| HOST-02 | `docs/DEPLOY-KOYEB.md` gone; `docs/DEPLOY-DOCKER.md` exists with required sections | — | file-existence + content assertion | `test ! -f docs/DEPLOY-KOYEB.md && test -f docs/DEPLOY-DOCKER.md` (optionally asserted in the drift guard) | ❌ W0 | ⬜ pending |
| HOST-01 (regression) | No runtime code path changed; K-##/D-## tags preserved | — | full suite green | `pytest` | ✅ existing | ⬜ pending |
| HOST-03 | `docker compose up` boots cleanly against Neon | — | manual-only (real secrets, D-08) | N/A — `24-HOST-UAT.md`, human-run | N/A parked | ⬜ parked |
| HOST-04 | Dashboard-side Render service deleted | — | manual-only (owner Render/GitHub UI, D-09) | N/A — no repo config exists | N/A parked | ⬜ parked |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_hosting_drift_guard.py` — new drift guard (D-12); mirrors
      `tests/test_invite_drift_guard.py`. Encodes Part-1 (zero-tolerance Koyeb/Oracle) + Part-2
      (Render allowlist diff), excludes `.planning/`/`milestones/`/`docs/superpowers/` (D-03/D-10),
      with positive + negative controls. This is the automated surface for HOST-01 (and optionally
      HOST-02's file-existence assertion).
- [ ] No framework install needed — pytest already present.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `docker compose up` boots Dexter cleanly against Neon | HOST-03 | Needs real `DISCORD_TOKEN` + Neon `DATABASE_URL` that must not live in this session (D-08) | `24-HOST-UAT.md`: `docker compose up -d --build`; confirm clean startup log, `/health` on `:8000` responds, no new silent failures in `dexter.log` |
| Dashboard-side Render service deleted | HOST-04 | Owner-only Render dashboard UI action; no repo config exists (D-09) | `24-HOST-UAT.md`: owner deletes the Render service so auto-deploy + CI/CD failure emails stop |

---

## Validation Sign-Off

- [x] All requirements have an automated verify (HOST-01/02 via drift guard) or documented parked-UAT (HOST-03/04)
- [x] Sampling continuity: drift guard + full suite cover every automatable behavior
- [x] Wave 0 covers the one MISSING reference (`tests/test_hosting_drift_guard.py`)
- [x] No watch-mode flags
- [x] Feedback latency < 5s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-15
