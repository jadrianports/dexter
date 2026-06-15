---
phase: 05-ship-it-live
plan: 03
subsystem: documentation
tags: [live-uat, runbook, deploy-validation, oracle-a1, docker, postgres, healthchecks]

# Dependency graph
requires:
  - phase: 05-ship-it-live plan 01
    provides: pre-deploy code fixes (clear_persisted, reconnect guard, TZ-correctness)
  - phase: 05-ship-it-live plan 02
    provides: deploy.sh, seed_restore_test.py, lifecycle-policy.json, backup.sh cadence
provides:
  - ".planning/phases/05-ship-it-live/05-UAT-RUNBOOK.md: consolidated ordered live-UAT runbook (21 checks, A→B→C→D)"
  - "03-VERIFICATION.md + 04-VERIFICATION.md + 04-HUMAN-UAT.md: by-reference banners pointing to master runbook"
affects: [DEPLOY-01, DEPLOY-02, DEPLOY-03, DEPLOY-05, DEPLOY-08, user-UAT-session]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "A→B→C→D locked ordering: destructive checks always last so restore failure cannot corrupt earlier UAT state"
    - "By-reference consolidation: source docs kept as provenance record; master runbook is the live-execution surface"
    - "result: [pending] capture fields on every check — consistent with 04-HUMAN-UAT.md frontmatter pattern"

key-files:
  created:
    - ".planning/phases/05-ship-it-live/05-UAT-RUNBOOK.md"
  modified:
    - ".planning/phases/04-scale/04-HUMAN-UAT.md"
    - ".planning/phases/04-scale/04-VERIFICATION.md"
    - ".planning/phases/03-alive/03-VERIFICATION.md"

key-decisions:
  - "Strict A→B→C→D ordering with destructive restore (D1) LAST — per D-07 locked order; restore failure cannot invalidate A/B/C results"
  - "21 checks: A(6 boot+infra) + B(2 persistence) + C(11 behavioral) + D(1 destructive) — includes streak/milestone (HV-8, omitted from RESEARCH C-table) and DEPLOY-04 reconnect diagnostic"
  - "By-reference banners are additive only — original check bodies, result: fields, and status frontmatter untouched in all three source docs"
  - "pg_dump --version prereq check added as an explicit result: field — RESEARCH explicitly called this out as a runbook step"
  - "down -v WARNING placed before any check and reinforced in troubleshooting table — T-05-10 mitigated"

patterns-established:
  - "One master runbook; source docs point by reference — never maintained in parallel"
  - "Prereqs checklist with result: capture field for infrastructure setup steps that need confirmation"

requirements-completed: [DEPLOY-01, DEPLOY-02, DEPLOY-03, DEPLOY-05, DEPLOY-08]

# Metrics
duration: 6min
completed: 2026-06-12
---

# Phase 5 Plan 03: Live-UAT Runbook Consolidation Summary

**Consolidated all 21 standing checks from three source documents into one ordered master runbook (05-UAT-RUNBOOK.md) with prerequisites, troubleshooting table, and the prominent down -v warning; updated the three source docs with by-reference banners pointing to the master runbook**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-12T10:54:45Z
- **Completed:** 2026-06-12
- **Tasks:** 2
- **Files created:** 1 (05-UAT-RUNBOOK.md)
- **Files modified:** 3 (source verification docs)

## Accomplishments

- **05-UAT-RUNBOOK.md created** (D-07): 269 lines, 21 checks in the locked A→B→C→D order:
  - Group A (A1–A6): Boot + Infra — Docker clean boot (references `scripts/deploy.sh`), reboot survival (`systemctl is-enabled docker`), over-cap rejection, keepalive/Healthchecks.io, backup cron manual run, Postgres integration tests
  - Group B (B1–B2): Queue Persistence — round-trip restart (DEPLOY-05), `clear_persisted` idle-leave verification (DEPLOY-06 / IN-02 fix from Plan 01)
  - Group C (C1–C11): Behavioral — 9 Phase-3 checks + streak/milestone roast (HV-8, previously not in RESEARCH C-table) + DEPLOY-04 reconnect diagnostic with `/gsd:debug` escalation path
  - Group D (D1): Destructive — non-destructive restore proof via `scripts/seed_restore_test.py` (Plan 02 script), ALWAYS LAST
  - Prominent `down -v` WARNING block before any check (T-05-10 mitigation)
  - Prerequisites checklist: VM timezone, docker systemctl, `.env`, `~/.pgpass`, `oci setup config`, lifecycle policy, crontab entries, `--first-run --guild`, Healthchecks.io setup + Discord webhook + email
  - 9-row troubleshooting table (arm64 manifest, pool-acquire, pg_dump auth, oci NotAuthenticated, etc.)
  - All 21 checks are user-executed instructions with `result: [pending]` capture fields
  - Session summary table at the end for the user to record final pass/fail counts

- **Three source docs updated by reference** (D-07): additive-only banners near the top of each pointing to `05-UAT-RUNBOOK.md`; original check bodies, `result:` fields, and frontmatter status values are unchanged (they remain provenance records)

## Task Commits

1. **Task 1: Author the consolidated ordered live-UAT runbook** — `a51bb9a`
2. **Task 2: Update source verification docs by reference** — `b993ed4`

## Files Created/Modified

- `.planning/phases/05-ship-it-live/05-UAT-RUNBOOK.md` — new; 21 checks, A→B→C→D; prereqs; troubleshooting; `down -v` warning
- `.planning/phases/04-scale/04-HUMAN-UAT.md` — by-reference banner added after frontmatter
- `.planning/phases/04-scale/04-VERIFICATION.md` — by-reference banner added after frontmatter
- `.planning/phases/03-alive/03-VERIFICATION.md` — by-reference banner added after frontmatter

## Decisions Made

- Strict A→B→C→D ordering per D-07 — the destructive restore (D1) is always executed last so its failure cannot invalidate A/B/C UAT state
- 21 total checks: the RESEARCH Focus Area 7 table enumerated 18 (A6+B2+C9+D1), but 03-VERIFICATION HV-8 (streak/milestone roasts) was omitted from the C-group table; adding C10 (streak/milestone) + C11 (DEPLOY-04 diagnostic) + pg_dump version prereq = 21 capture fields
- By-reference edits are strictly additive — no deletions, no rewrites, no `result:` field changes in source docs
- `down -v` warning is a block-level callout at the top of the runbook (before the prereqs checklist, before any check) to maximize visibility

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — the runbook is a documentation artifact with `result: [pending]` capture fields by design. The pending fields are not stubs; they are fill-in-on-Oracle fields that the user populates during the live UAT session.

## Threat Flags

No new network endpoints, auth paths, or trust boundaries introduced by this documentation plan.

Threat mitigations confirmed in the runbook:

| Threat | Mitigation |
|--------|-----------|
| T-05-10: operator runs `docker compose down -v` | Prominent WARNING block before any check; troubleshooting table reinforces it |
| T-05-11: destructive restore corrupts earlier UAT state | D-group ordering enforced — D1 is ALWAYS LAST; restore targets `dexter_restore_test` only (per scripts/seed_restore_test.py from Plan 02) |
| T-05-12: runbook embeds real secrets | All sensitive values use placeholders: `<GUILD_ID>`, `<your-uuid>`, `YOUR_POSTGRES_PASSWORD`; `chmod 600` instructed for `.env`/`.pgpass` |
| T-05-13: owner /sync by non-owners | Existing guard documented (runbook notes owner-only usage) |

## Next Phase Readiness

- All three Phase 5 wave-2 deliverables complete: code fixes (Plan 01), deploy scripts (Plan 02), live-UAT runbook (Plan 03)
- Phase 5 is verified when the user executes the 21 checks on Oracle A1 and all pass — the phase is NOT verified by code landing (D-01)
- User runs the runbook via `/gsd-verify-work` on Oracle; results captured there

## Self-Check: PASSED

- `05-UAT-RUNBOOK.md` exists — FOUND
- `grep -c "result:"` returns 21 — CONFIRMED
- A→B→C→D ordering: A (line 62), B (line 112), C (line 130), D (line 220) — CONFIRMED
- `grep -c "down -v"` returns 3 (warning block × 2 + troubleshooting table) — CONFIRMED
- `grep -c "timedatectl"` returns >= 1 in prereqs — CONFIRMED
- All three source docs reference `05-UAT-RUNBOOK` — CONFIRMED
- Banners appear immediately after frontmatter in each source doc — CONFIRMED
- Original check bodies unchanged (additive-only edits confirmed by `git show --stat`) — CONFIRMED
- Commits a51bb9a and b993ed4 — FOUND in git log

---
*Phase: 05-ship-it-live*
*Completed: 2026-06-12*
