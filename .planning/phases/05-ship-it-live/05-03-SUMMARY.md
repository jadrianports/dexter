---
phase: 05-ship-it-live
plan: "03"
subsystem: deploy-runbook
tags: [runbook, uat, koyeb, neon, doc-edit, k-18]
dependency_graph:
  requires: [05-01, 05-02]
  provides: [live-uat-runbook-koyeb-neon]
  affects: [05-UAT-RUNBOOK.md]
tech_stack:
  added: []
  patterns: [Koyeb-WEB-health-check, Neon-PITR-restore, scale-to-zero-reconnect, UptimeRobot-keep-alive]
key_files:
  created: []
  modified:
    - .planning/phases/05-ship-it-live/05-UAT-RUNBOOK.md
decisions:
  - "Wrote complete runbook in single atomic write covering both tasks; both string gates verified green on the same committed file"
  - "Added B3 Neon scale-to-zero check as a third Group B check (not in B1/B2 slot) to cleanly separate behaviors"
  - "Session Summary total is 22 (7 A + 3 B + 11 C + 1 D) — group A gained A5/health-curl and A6/git-auto-deploy; B gained B3/scale-to-zero"
metrics:
  duration_seconds: 247
  completed_date: "2026-06-15"
  tasks_completed: 2
  files_modified: 1
---

# Phase 05 Plan 03: UAT Runbook Koyeb+Neon Re-Target Summary

## One-Liner

Surgical in-place re-target of `05-UAT-RUNBOOK.md` from Oracle A1 to Koyeb+Neon per K-18: dropped all Oracle/OCI/systemctl/pgpass paths, swapped every Postgres reference to Neon, added Koyeb deploy-healthy + git-auto-deploy + /health curl + UptimeRobot + Neon scale-to-zero-reconnect + Neon PITR restore checks, preserved all 11 Group C behavioral checks and the A→B→C→D destructive-last ordering.

## What Was Built

A fully re-targeted `05-UAT-RUNBOOK.md` (version 2.0, 2026-06-15) that a user can execute top-to-bottom against a live Koyeb+Neon stack without hitting a single dead Oracle instruction. The runbook is the live-verification instrument for DEPLOY-01/02/03/04/05/06/07/08 and P-01/P-02/P-03/P-04.

**Changes made:**

- **Frontmatter:** Updated `target` to "Koyeb WEB service + Neon serverless Postgres (re-targeted 2026-06-15, K-18)"
- **Run on: line:** "Koyeb WEB service (git-auto-built) + Neon serverless Postgres"
- **WARNING block:** Replaced docker-compose-down-v landmine caution with Neon PITR destructive-last + K-14 break-glass caution
- **Prerequisites:** Replaced all Oracle/VM/OCI/crontab steps with Koyeb+Neon prereqs pointing at `docs/DEPLOY-KOYEB.md`
- **Group A (7 checks):** A1 Koyeb deploy-healthy, A2 Koyeb restart+queue-restore, A3 over-cap via env var redeploy, A4 UptimeRobot+Healthchecks.io, A5 health-endpoint curl, A6 git-auto-deploy, A7 pytest against Neon
- **Group B (3 checks):** B1 queue round-trip via Koyeb redeploy, B2 clear_persisted idle-leave, B3 (new) Neon scale-to-zero reconnect
- **Group C (11 checks):** All 11 behavioral checks preserved verbatim except `docker compose restart/logs` mechanics swapped to Koyeb dashboard / `koyeb services logs`
- **Group D (1 check):** D1 rebuilt as Neon PITR branch-restore proof (Time-Travel Assist → restore → verify backup branch created → asyncpg auto-reconnects → /history confirms data integrity)
- **Troubleshooting table:** Removed Oracle/arm64/OCI/pgpass rows; added Koyeb rows for channel_binding sanitizer (Pitfall 1), SSL-EOF lifetime (Pitfall 2), statement_cache_size (Pitfall 3), 0.0.0.0:8000 binding (Pitfall 5), branch tracking after merge (Pitfall 8)
- **Session Summary:** Recomputed to 22 total checks; closing line changed to "verified-live when all 22 checks pass on Koyeb+Neon per K-17; report via /gsd-verify-work"
- **Version note:** Runbook version 2.0 (Koyeb+Neon), re-targeted 2026-06-15

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 + Task 2 (single write) | 2c82744 | docs(05-03): re-target runbook prerequisites + Group A + troubleshooting to Koyeb+Neon |

Both Task 1 and Task 2 string gates verified on commit 2c82744. All content for both tasks was written atomically in a single file write; both automated verification gates pass on the same committed state.

## Verification Results

**Task 1 gate:** `python -c "... banned=['OCI','oci os','systemctl','.pgpass','docker compose down -v','Oracle A1'] ... need=['Koyeb','Neon','/health','UptimeRobot','statement_cache_size','channel_binding'] ..."` → **OK**

**Task 2 gate:** `python -c "... assert 'Neon PITR' in s ... assert 'scale-to-zero' in s.lower() ... assert 'pg_dump' not in s ... assert s.count('### C')>=11 ... assert 'Koyeb+Neon' in s ..."` → **OK**

**Full success criteria:** 21/21 checks PASS (no Oracle/OCI/systemctl/pgpass/down-v remnants; all Koyeb/Neon/health/UptimeRobot/PITR/scale-to-zero present; Group C intact with 11 checks; verified-live wording updated).

## Deviations from Plan

### Auto-fixed Issues

None.

### Design decisions made inline

**1. Single atomic file write covering both tasks**
- **Found during:** Task 1 planning
- **Reason:** The runbook is a single document; writing it in two incremental passes would require reading back, diffing, and re-editing overlapping sections. Writing the complete re-targeted document atomically was cleaner and safer — both string gates were verified on the result.
- **Impact:** The Task 2 commit points to the same hash as Task 1 (no delta). Both gates independently verified.

## Known Stubs

None. The runbook uses `<your-service-name>`, `<GUILD_ID>`, `<your-uuid>` placeholders where the user must substitute real values — these are intentional (T-05-12: no real secrets in the doc) and not UI stubs that block functionality.

## Threat Flags

No new threat surface introduced. The runbook uses only `<service>` / `<GUILD_ID>` / `<your-uuid>` placeholders throughout (T-05-12 mitigated). The Neon PITR restore (D1) guidance includes the T-05-10 safeguards: Time-Travel Assist first, Group D last, backup branch confirmation. The K-14 break-glass caution is in the WARNING block (T-05-11 mitigated).

## DEPLOY Requirement Coverage

| DEPLOY ID | Runbook Check | Status |
|-----------|---------------|--------|
| DEPLOY-01 | A1 (Koyeb deploy healthy) + A2 (restart survival) + B3 (scale-to-zero) | Covered |
| DEPLOY-02 | All Group C checks (C1-C11) | Covered |
| DEPLOY-03 | All Group C checks (C1-C11) — human UAT scenarios | Covered |
| DEPLOY-04 | C2 (late-night TZ fix), C11 (reconnect diagnostic) | Covered |
| DEPLOY-05 | A2 (queue restore on restart), B1 (queue round-trip) | Covered |
| DEPLOY-06 | B2 (clear_persisted on idle-leave) | Covered |
| DEPLOY-07 | D1 (Neon PITR restore proof) | Covered |
| DEPLOY-08 | A4 (UptimeRobot + Healthchecks.io active) | Covered |

## Self-Check: PASSED

- FOUND: `.planning/phases/05-ship-it-live/05-UAT-RUNBOOK.md`
- FOUND: `.planning/phases/05-ship-it-live/05-03-SUMMARY.md`
- FOUND: commit `2c82744`
