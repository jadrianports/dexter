---
phase: "05-ship-it-live"
plan: "02"
subsystem: "infra/deploy-packaging"
tags: [koyeb, neon, docker, logging, ops-scripts, deploy-doc]
dependency_graph:
  requires: ["05-01"]
  provides: ["05-03"]
  affects: ["requirements.txt", "Dockerfile", "utils/logger.py", ".env.example", "scripts/archive/*", "docs/DEPLOY-KOYEB.md"]
tech_stack:
  added: []
  patterns: ["floor-pin deps (>=) for self-healing tools", "stdout logging for container viewers", "git mv for history-preserving file retirement", "K-13 identical-var-names two-environment contract"]
key_files:
  created: ["docs/DEPLOY-KOYEB.md", "scripts/archive/backup.sh", "scripts/archive/keepalive.sh", "scripts/archive/deploy.sh", "scripts/archive/lifecycle-policy.json"]
  modified: ["requirements.txt", "Dockerfile", "utils/logger.py", ".env.example"]
decisions:
  - "yt-dlp floor-pinned at >=2026.06.09 (latest stable at plan time); floor not exact so daily 4am self-heal can advance beyond it (K-15)"
  - "aiohttp>=3.9.0 made explicit dep to guard against discord.py dropping it as transitive (K-15 / Research open question 1)"
  - "Dockerfile comment-only change: multi-arch/Koyeb header; all functional lines byte-for-byte unchanged"
  - "StreamHandler(sys.stdout) for Docker/Koyeb log convention; import sys added (K-16)"
  - "Four Oracle ops scripts retired via git mv (history preserved) to scripts/archive/; seed_restore_test.py kept for Neon PITR UAT (K-08/K-09/K-11)"
  - "docs/DEPLOY-KOYEB.md is the single authoritative Koyeb+Neon+UptimeRobot contract (9 sections)"
  - ".env.example refreshed to K-13 two-environment contract (identical var names; DATABASE_URL comments for local vs Neon; GENIUS_TOKEN added; POSTGRES_PASSWORD kept for local compose)"
metrics:
  duration: "~12 min"
  completed: "2026-06-15"
  tasks_completed: 2
  tasks_total: 2
  files_created: 5
  files_modified: 4
---

# Phase 05 Plan 02: Deploy Packaging (Koyeb+Neon) Summary

**One-liner:** De-Oracle the Dockerfile + pin yt-dlp/aiohttp, route logs to stdout, retire four Oracle ops scripts via git mv, and write the full Koyeb+Neon+UptimeRobot deploy contract in docs/DEPLOY-KOYEB.md.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Pin deps, de-Oracle Dockerfile, stream logs to stdout | 7e5d66f | requirements.txt, Dockerfile, utils/logger.py |
| 2 | Retire Oracle ops scripts, write Koyeb deploy contract + .env.example | 2a39e7c | scripts/archive/* (4 files), docs/DEPLOY-KOYEB.md, .env.example |

## What Was Built

**Task 1 — Build base + logging:**
- `requirements.txt`: `yt-dlp>=2026.06.09` (floor pin; daily self-heal still runs) + `aiohttp>=3.9.0` (explicit dep); `asyncpg==0.31.0` unchanged
- `Dockerfile`: replaced Oracle A1 ARM / arm64v8 header (lines 1-4, 7-8) with multi-arch / Koyeb-targeted comment; `FROM python:3.11-slim-bookworm` and all build steps unchanged
- `utils/logger.py`: added `import sys`; changed `logging.StreamHandler()` to `logging.StreamHandler(sys.stdout)` — Docker/Koyeb log viewers reliably capture stdout (K-16)

**Task 2 — Script retirement + deploy contract:**
- `git mv` retired four Oracle ops scripts to `scripts/archive/` (backup.sh, keepalive.sh, deploy.sh, lifecycle-policy.json) with full git history preserved; `scripts/seed_restore_test.py` kept
- `docs/DEPLOY-KOYEB.md`: 9-section deploy contract covering: substrate overview, Neon setup (us-east-2 region, pooled endpoint, schema auto-create), Koyeb WEB service config (wdc1 region, Dockerfile build, /health:8000, branch flow), K-13 secrets vs env vars table, UptimeRobot 5-min keep-alive, K-09 dead-man monitoring, K-14 break-glass rule, K-10 runner-swap contingency (HeavenCloud/Wispbyte), archived-scripts note
- `.env.example`: K-13 two-environment contract; DATABASE_URL comments updated for local vs Neon POOLED string; HEALTHCHECK_URL re-commented for bot-side dead-man (not inbound keep-alive); GENIUS_TOKEN moved to required section; POSTGRES_PASSWORD kept for local compose stack

## Verifications Run

- Task 1 automated check: `python -c "assert 'yt-dlp>=2026.06.09' in req ... print('OK')"` → **OK**
- `python -c "import utils.logger"` → exits 0 (no output)
- Task 2 automated check: `python -c "import os; arch='scripts/archive/'; ..."` → **OK**
- K-14 + K-10 content check in DEPLOY-KOYEB.md → **OK**
- Pure-function test suite (`test_config.py`, `test_streak.py`): **18 passed** (pre-existing DB connection failures in `test_database_phase4.py` are unaffected by this plan's changes — no local Postgres on dev machine)
- `docker build` is a user-run optional check (cannot run Docker from this environment); confirmed as human-optional in plan verification section; Koyeb build in Plan 03 UAT is the deploy-time gate

## Deviations from Plan

None. Plan executed exactly as written.

- Task 1: comment-only Dockerfile change confirmed byte-for-byte; all functional lines unchanged
- Task 2: `git mv` succeeded for all four scripts; docs/DEPLOY-KOYEB.md authored with all 9 required sections; .env.example refreshed without committing any real secrets

## Known Stubs

None. This plan produces docs and config changes; no UI rendering or data-source wiring involved.

## Threat Flags

None beyond the plan's pre-catalogued threat register (T-05-06 through T-05-SC). Verified:
- `.env.example` contains only placeholder values (no real tokens/URLs)
- `docs/DEPLOY-KOYEB.md` uses `<service>` / `<id>` placeholder examples throughout
- Dockerfile comment change adds no `ARG`/`ENV` layers (T-05-06 mitigated)

## Self-Check: PASSED

- `requirements.txt` — yt-dlp>=2026.06.09 ✓, aiohttp>=3.9.0 ✓, asyncpg==0.31.0 ✓
- `Dockerfile` — "Koyeb builds this Dockerfile directly" ✓, no arm64v8/Oracle A1 ARM ✓, exactly one FROM ✓
- `utils/logger.py` — `import sys` ✓, `StreamHandler(sys.stdout)` ✓
- `scripts/archive/` — backup.sh ✓, keepalive.sh ✓, deploy.sh ✓, lifecycle-policy.json ✓
- `scripts/backup.sh` absent from scripts/ ✓, `scripts/seed_restore_test.py` present ✓
- `docs/DEPLOY-KOYEB.md` — Neon ✓, WEB service ✓, /health ✓, UptimeRobot ✓, us-east-2 ✓, K-14 break-glass ✓, K-10 runner-swap ✓
- `.env.example` — DATABASE_URL ✓, Neon reference ✓, identical var names ✓
- Commit 7e5d66f: `git log --oneline | grep 7e5d66f` ✓
- Commit 2a39e7c: `git log --oneline | grep 2a39e7c` ✓
