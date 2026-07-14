# Phase 24: Hosting Honesty & Docker - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-15
**Phase:** 24-hosting-honesty-docker
**Areas discussed:** Scrub blast radius, Replacement doc, HOST-03 verification, .env.example reframe, K-## tags

---

## Scrub blast radius

| Option | Description | Selected |
|--------|-------------|----------|
| Live + narrative, tracked only | Strip operative refs + rewrite CLAUDE.md hosting narrative/Phase-5 log; delete dead scripts/archive Oracle scripts; leave .planning/milestones archives + gitignored dexter-architecture.md alone | ✓ |
| Operative only, keep history | Strip live config/comments/docs, leave CLAUDE.md build history verbatim, keep archive scripts | |
| Maximal scrub | Also rewrite .planning/, milestones/, and the gitignored architecture doc | |

**User's choice:** Live + narrative, tracked only
**Notes:** Balances honesty (CLAUDE.md is the authoritative spec, must read host-honest) against not rewriting sealed historical record. Untracked file excluded because grep-'the repo' means tracked files.

---

## Replacement doc

| Option | Description | Selected |
|--------|-------------|----------|
| docs/DEPLOY-DOCKER.md, lean-complete | Mirrors DEPLOY-* convention; prereqs → .env → `docker compose up` → verify /health + dexter.log; keeps parked-24-7/residential framing; git rm old Koyeb doc | ✓ |
| docs/RUNNING.md, minimal | Barest quickstart, breaks DEPLOY-* convention | |
| docs/DEPLOY.md, full runbook | 179-line-style depth; more to maintain for on-demand personal deploy | |

**User's choice:** docs/DEPLOY-DOCKER.md, lean-complete
**Notes:** Old DEPLOY-KOYEB.md is `git rm`'d, not left behind.

---

## HOST-03 verification

| Option | Description | Selected |
|--------|-------------|----------|
| Park as human-run UAT | Boot needs real DISCORD_TOKEN + Neon DATABASE_URL; ship a HOST-UAT checklist, owner runs on their PC. Matches Phase 03–22 parked-UAT precedent | ✓ |
| Claude attempts now if creds present | Claude runs the boot during execution if Docker + real .env are local | |

**User's choice:** Park as human-run UAT
**Notes:** docker-compose.yml already bot-only → Neon, so the boot is genuinely runnable; no compose change needed for it.

---

## .env.example reframe

| Option | Description | Selected |
|--------|-------------|----------|
| Reframe local-vs-Docker, keep split | Relabel Koyeb/production → Docker on your PC + Neon; drop Secrets/scale-to-zero/UptimeRobot; keep local-vs-Neon distinction + Healthchecks.io outbound note | ✓ |
| Collapse to one local+Neon story | Remove prod/local duality entirely; loses the local-Postgres break-glass path | |

**User's choice:** Reframe local-vs-Docker, keep split
**Notes:** Healthchecks.io outbound dead-man (K-09) is host-agnostic and stays.

---

## K-## tags

| Option | Description | Selected |
|--------|-------------|----------|
| Keep tags, rewrite prose only | Treat K-## as opaque scar-IDs; leave intact (cross-referenced by archives, grep-'Koyeb' never matches them); rewrite only surrounding prose | ✓ |
| Strip the tags entirely | Rename/remove all K-## tags; high churn across 8 files + tests, breaks audit trail, no grep-honesty payoff | |
| Keep tags verbatim, no prose change | Leave both tags and 'Koyeb' prose — rejected, fails success criterion | |

**User's choice:** Keep tags, rewrite prose only
**Notes:** 12 distinct tags (~28 live occurrences after Koyeb doc dies). Example: `# Koyeb 2GB ephemeral disk (K-07)` → `# 512MB cap on ephemeral disk (K-07)`.

---

## Claude's Discretion

- Exact host-honest wording of rewritten comments/narrative (subject to the grep success gate).
- Section ordering and exact prose of `docs/DEPLOY-DOCKER.md` within the agreed lean-complete shape.

## Deferred Ideas

None — discussion stayed within phase scope. `dexter-architecture.md` (gitignored) was considered and explicitly excluded, not deferred.
