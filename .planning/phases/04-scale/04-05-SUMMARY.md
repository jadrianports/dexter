---
phase: "04-scale"
plan: "05"
subsystem: "infra/deployment"
tags: ["docker", "docker-compose", "postgres", "arm64", "oracle-cloud", "backup", "keepalive"]
dependency_graph:
  requires: ["04-02"]
  provides: ["SCALE-05"]
  affects: ["hosting", "database", "deployment"]
tech_stack:
  added:
    - "Docker Compose (bot + postgres:16-alpine, arm64)"
    - "Dockerfile (python:3.11-slim-bookworm + ffmpeg + curl)"
    - "scripts/keepalive.sh (curl → Healthchecks.io, Oracle idle-nudge)"
    - "scripts/backup.sh (pg_dump → oci os object put → dexter-backups bucket)"
  patterns:
    - "named Docker volumes for postgres_data / audio_cache / logs (D-10)"
    - "depends_on: condition: service_healthy (healthcheck-gated startup)"
    - "${POSTGRES_PASSWORD} env interpolation (no secrets in committed files)"
    - "~/.pgpass for pg_dump auth (no hardcoded creds in scripts)"
key_files:
  created:
    - "Dockerfile"
    - "docker-compose.yml"
    - "scripts/keepalive.sh"
    - "scripts/backup.sh"
    - ".dockerignore"
  modified:
    - ".env.example (added DATABASE_URL, POSTGRES_PASSWORD, HEALTHCHECK_URL)"
decisions:
  - "D-07: Host = Oracle Cloud Always Free A1 ARM (pure-free, $0/mo); Hetzner (~€4-5/mo) is documented fallback (D-08)"
  - "D-10: Docker Compose packages the full stack; one `docker compose up` rebuilds on any host after Oracle reclaim or migration to Hetzner"
  - "D-11: Postgres runs as a colocated container on the same VM (free); DATABASE_URL points at the `postgres` service hostname"
  - "D-09/D-13: keepalive.sh unifies Oracle idle-nudge (network > 20%) and Healthchecks.io dead-man switch in one cron"
  - "D-12: backup.sh pg_dumps to Oracle Object Storage dexter-backups bucket (Always Free 20 GB); password via ~/.pgpass never hardcoded"
  - "T-04-05 mitigated: .dockerignore excludes .env/data/logs; Dockerfile has no ENV secret; compose uses ${POSTGRES_PASSWORD} interpolation; .env.example ships CHANGE_ME placeholders"
metrics:
  duration: "~5 minutes"
  completed_date: "2026-06-12"
  tasks_completed: 3
  tasks_total: 3
  files_created: 6
  files_modified: 0
---

# Phase 04 Plan 05: Docker Compose Hosting Stack Summary

Docker Compose stack (arm64 Postgres + bot) with keep-alive/dead-man cron and pg_dump backup for Oracle Cloud Always Free A1 ARM — resolves the OPEN hosting decision (SCALE-05).

## What Was Built

### Task 1 — Dockerfile + .dockerignore + .env.example (commit e884c18)

**Dockerfile** builds the bot image from `python:3.11-slim-bookworm`, installs `ffmpeg` and `curl` via apt (arm64-native in Debian Bookworm), pip-installs `requirements.txt` (including `asyncpg==0.31.0` from 04-02), and sets `CMD ["python", "bot.py"]`. No secret literals — image receives env vars at runtime via `env_file`.

**.dockerignore** excludes `.env`, `data/`, `logs/`, `.git/`, `**/__pycache__/`, `.planning/`, `docs/`, `tests/` — secrets and local runtime state never enter an image layer.

**.env.example** extended with Phase 4 variables (`DATABASE_URL`, `POSTGRES_PASSWORD`, `HEALTHCHECK_URL`) alongside the existing Discord/Gemini/Genius vars. All values are placeholders (`CHANGE_ME`, `your-uuid-here`); comment header warns "never commit real secrets."

### Task 2 — docker-compose.yml (commit b0fb935)

Two-service stack:
- **postgres**: `postgres:16-alpine`, `platform: linux/arm64`, healthcheck (`pg_isready -U dexter -d dexter`), named volume `postgres_data:/var/lib/postgresql/data`, `POSTGRES_PASSWORD` interpolated from `.env`.
- **bot**: built from `Dockerfile`, `env_file: .env`, `DATABASE_URL` overrides to `postgresql://dexter:${POSTGRES_PASSWORD}@postgres:5432/dexter` (colocated service, D-11), `depends_on: postgres: condition: service_healthy`, volumes `audio_cache:/app/data/cache` and `logs:/app/logs` (match `config.AUDIO_CACHE_DIR` / `config.LOG_DIR`).

Three named volumes (`postgres_data`, `audio_cache`, `logs`) survive `docker compose down`; only `docker compose down -v` wipes them. `restart: unless-stopped` on both services.

`docker compose config` validated successfully on this machine.

### Task 3 — scripts/keepalive.sh + scripts/backup.sh (commit 9d1b7f5)

**keepalive.sh**: `curl -fsS --max-time 10 "$HEALTHCHECK_URL" > /dev/null 2>&1 || true` — non-fatal on transient failure. Intended crontab: `*/5 * * * *` on the Oracle VM host (outside Docker, D-09). Doubles as Oracle idle-nudge (outbound network > 20%) and Healthchecks.io dead-man switch (D-13). `HEALTHCHECK_URL` sourced from crontab env, never hardcoded.

**backup.sh**: `pg_dump --host=localhost --username=dexter --no-password --format=custom dexter | oci os object put --bucket-name dexter-backups --name "dexter_${TIMESTAMP}.dump" --file - --force`. Postgres password via `~/.pgpass` or `PGPASSWORD` cron env (T-04-05). Requires oci-cli configured (instance principal recommended). Intended crontab: `*/30 * * * *`.

Both scripts passed `bash -n` syntax check.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Dockerfile comment triggered secret-regex false positive**
- **Found during:** Task 1 verify step
- **Issue:** The comment `# ENV TOKEN=... or ARG PASSWORD=... here; baking secrets...` matched the plan's secret-hygiene regex `ENV\s+\w*(TOKEN|PASSWORD|KEY)\s*=\s*\S`
- **Fix:** Rephrased comment to `# never bake token/password/key literals into image layers (T-04-05)` — intent preserved, no regex match
- **Files modified:** `Dockerfile`
- **Commit:** e884c18 (included in same task commit)

No other deviations — plan executed as written.

## Validations Run vs. Deferred

| Validation | Ran? | Notes |
|------------|------|-------|
| `docker compose config` schema validation | **RAN — PASSED** | Docker is available on this Windows dev machine; compose reports valid |
| `bash -n` syntax check on both scripts | **RAN — PASSED** | keepalive.sh and backup.sh both clean |
| Python structural assertions (all 3 tasks) | **RAN — PASSED** | All grep/regex gates passed |
| Secret-hygiene regex gates (Dockerfile, compose, scripts) | **RAN — PASSED** | No literals anywhere |
| Full-stack clean-volume boot on Oracle A1 VM | **DEFERRED — user_setup** | Requires Oracle VM + Docker + real .env; documented in plan's user_setup steps |
| keepalive cron verified against Healthchecks.io | **DEFERRED — user_setup** | Requires live HEALTHCHECK_URL + crontab install on Oracle VM |
| backup.sh verified against Object Storage | **DEFERRED — user_setup** | Requires oci-cli configured + dexter-backups bucket + pg_dump client on host |

## Threat Surface Scan

All security-relevant surface in this plan was covered by the plan's `<threat_model>`:
- T-04-05 (Information Disclosure — secrets in image/committed files): mitigated by `.dockerignore`, `${POSTGRES_PASSWORD}` interpolation, `CHANGE_ME` placeholders, `~/.pgpass` pattern
- T-04-10 (OCI credentials in image): mitigated — `oci-cli` config lives on host, not in image
- T-04-11 (Oracle idle reclaim / undetected downtime): mitigated by `keepalive.sh` + `restart: unless-stopped`
- T-04-12 (backup integrity): accepted per plan

No new threat surface introduced beyond what the plan registered.

## Known Stubs

None. All files are complete and self-contained. The `docker compose up` boot gate and script crontab installation are user_setup steps (require Oracle Cloud account), not stubs in the code.

## Self-Check: PASSED

Files exist:
- `Dockerfile`: FOUND
- `docker-compose.yml`: FOUND
- `scripts/keepalive.sh`: FOUND
- `scripts/backup.sh`: FOUND
- `.dockerignore`: FOUND
- `.env.example` (modified): FOUND

Commits exist:
- e884c18 (Task 1: Dockerfile + .dockerignore + .env.example): FOUND
- b0fb935 (Task 2: docker-compose.yml): FOUND
- 9d1b7f5 (Task 3: scripts/keepalive.sh + scripts/backup.sh): FOUND
