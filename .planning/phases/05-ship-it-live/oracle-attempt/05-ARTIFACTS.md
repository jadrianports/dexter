# Phase 5: Ship It Live — Artifacts This Phase Produces

> Newly-created symbols/files/constants for this phase. Drift verification MUST exclude these
> from "does this symbol already exist" checks — they are net-new in Phase 5.

## New files

| Path | Plan | Kind | Purpose |
|------|------|------|---------|
| `scripts/deploy.sh` | 05-02 | shell script | D-13 manual git-pull + `docker compose up -d --build bot` update workflow with down -v guard |
| `scripts/lifecycle-policy.json` | 05-02 | JSON | OCI Object Storage 14-day DELETE lifecycle rule (dexter_ prefix) — D-14 |
| `scripts/seed_restore_test.py` | 05-02 | Python script | D-15 non-destructive seed → backup → restore-verify (throwaway `dexter_restore_test` DB) |
| `tests/test_seed_restore.py` | 05-02 | pytest | Wave-0 pure tests for seed-row data shape (no DB) |
| `.planning/phases/05-ship-it-live/05-UAT-RUNBOOK.md` | 05-03 | markdown | Consolidated ordered live-UAT runbook (21 checks, A→B→C→D, prereqs, troubleshooting) |

## New symbols (functions / identifiers)

| Symbol | File | Plan | Notes |
|--------|------|------|-------|
| `test_tz_aware_hour_is_integer` | `tests/test_streak.py` | 05-01 | Wave-0 TZ smoke test (D-06) |
| `build_seed_rows()` (pure) | `scripts/seed_restore_test.py` | 05-02 | DB-free seed-row builder; imported by `tests/test_seed_restore.py` |
| `SEED_USER_ID` | `scripts/seed_restore_test.py` | 05-02 | obviously-fake snowflake `"999999999999999999"` |
| `THROWAWAY_DB` | `scripts/seed_restore_test.py` | 05-02 | `"dexter_restore_test"` — restore target; never the live DB |
| `TestSeedData` (class) | `tests/test_seed_restore.py` | 05-02 | pure seed-shape assertions |

## New log statements (DEPLOY-04 instrumentation, D-03)

| Location | Level | Plan |
|----------|-------|------|
| `cogs/music.py` reconnect loop (~1194-1199): "reconnect attempt %d/3", "reconnect: vc.is_connected()=%s gen=%d" | INFO | 05-01 |
| `cogs/music.py` `_play_track` (~346-370): "gen=%d → %d", "stopping current playback gen=%d", "play() called gen=%d connected=%s" | DEBUG | 05-01 |
| `services/queue_persistence.py` smart-rejoin (~147): "smart-rejoin: connected=%s", "Smart rejoin: vc not connected post-connect()" | INFO / WARNING | 05-01 |

## Modified files (existing symbols, not net-new — listed for completeness)

| Path | Plan | Change |
|------|------|--------|
| `bot.py` | 05-01 | clear_persisted() added on idle-leave (~399); bot.py:467 yt-dlp loop deliberately UNCHANGED (D-06 discretion) |
| `cogs/music.py` | 05-01 | clear_persisted() on reconnect-failure (~1206) + diagnostic logs |
| `cogs/events.py` | 05-01 | late-night hour → `datetime.now(tz=ZoneInfo(config.STREAK_TIMEZONE)).hour` (~197) |
| `services/queue_persistence.py` | 05-01 | is_connected() guard after connect() in smart-rejoin (~147) |
| `scripts/backup.sh` | 05-02 | cadence comment `*/30` → `0 */6 * * *` (comment only; no functional change) |

## New config constants

None. Per 05-PATTERNS.md, no new `config.py` constants are required for Phase 5 (backup cadence/retention are encoded in the cron + lifecycle JSON, not parameterized). `STREAK_TIMEZONE` (config.py:58) is reused, not added.

---

## Multi-Source Coverage Audit

All four source artifact types audited. Every item is COVERED by a plan; nothing omitted or silently simplified.

### GOAL (ROADMAP Phase 5 success criteria)

| # | Success criterion | Covered by |
|---|-------------------|------------|
| 1 | `docker compose up` boots Postgres+bot, posts startup msg, survives reboot | 05-02 (deploy.sh) + 05-03 (runbook A1/A2) |
| 2 | 9 Phase-3 behavioral checks confirmed firing live | 05-03 (runbook group C) + 05-01 (events.py TZ fix supports C2) |
| 3 | 6 Phase-4 deploy checks pass on Oracle | 05-03 (runbook group A + B) |
| 4 | Voice playback survives reconnect without the race; clear_persisted fires on idle-leave + reconnect-failure | 05-01 (DEPLOY-04 guard+logs, DEPLOY-06 clear_persisted) + 05-03 (runbook B2 + DEPLOY-04 log-trail check) |
| 5 | pg_dump → OCI → restore end-to-end | 05-02 (seed_restore_test.py, backup.sh, lifecycle) + 05-03 (runbook D1) |

### REQ (REQUIREMENTS.md phase_req_ids)

| ID | Covered by plan(s) |
|----|--------------------|
| DEPLOY-01 | 05-02, 05-03 |
| DEPLOY-02 | 05-03 (+ 05-01 events.py TZ supports C2) |
| DEPLOY-03 | 05-03 |
| DEPLOY-04 | 05-01, 05-03 |
| DEPLOY-05 | 05-03 |
| DEPLOY-06 | 05-01, 05-03 |
| DEPLOY-07 | 05-02, 05-03 |
| DEPLOY-08 | 05-03 |

Every DEPLOY-01…08 appears in at least one plan's `requirements` frontmatter. ✓

### RESEARCH (05-RESEARCH.md focus areas / features)

| Focus Area | Covered by |
|------------|------------|
| 1 Reconnect race (guard + instrumentation) | 05-01 Task 2 |
| 2 clear_persisted fix | 05-01 Task 1 |
| 3 Timezone correctness (events.py) | 05-01 Task 3 |
| 4 Backup/restore round-trip | 05-02 Task 2 (+ lifecycle in Task 1) |
| 5 Dead-man alert routing | 05-03 (runbook prereqs A4) |
| 6 Deploy mechanics (deploy.sh, troubleshooting, sync, reboot) | 05-02 Task 1 + 05-03 |
| 7 Runbook consolidation | 05-03 Task 1 |

### CONTEXT (D-01…D-15)

| Decision | Covered by |
|----------|------------|
| D-01 (labor split, runbook is the verification surface) | 05-03 objective + all plans' "live = user-executed" framing |
| D-02 (defensive reconnect guard) | 05-01 Task 2 |
| D-03 (reconnect instrumentation) | 05-01 Task 2 |
| D-04 (verify live, escalate only if needed) | 05-03 DEPLOY-04 runbook check |
| D-05 (clear_persisted at two sites) | 05-01 Task 1 |
| D-06 (TZ-explicit; events.py fixed, bot.py:467 deferred by discretion) | 05-01 Task 3 |
| D-07 (one ordered runbook, A→B→C→D, by-reference source updates) | 05-03 Task 1 + Task 2 |
| D-08 (per-guild command sync) | 05-03 prereqs (--first-run --guild) |
| D-09 (reboot survival check) | 05-03 runbook A2 (systemctl is-enabled docker) |
| D-10 (manual .env / .pgpass / .oci, no secret manager) | 05-03 prereqs |
| D-11 (troubleshooting table + fix-forward) | 05-03 Task 1 |
| D-12 (Healthchecks.io → Discord webhook + email) | 05-03 prereqs (DEPLOY-08) |
| D-13 (deploy.sh manual git-pull + rebuild) | 05-02 Task 1 |
| D-14 (6h backup cadence + 14-day lifecycle) | 05-02 Task 1 |
| D-15 (non-destructive restore proof) | 05-02 Task 2 |

Deferred Ideas (Redis, GHCR/CI-CD, log-shipping, bot.py:467 tzinfo, mid-song resume, etc.) — correctly NOT planned. ✓

**Audit result: no unplanned items, no scope reduction, no PHASE SPLIT needed.**
