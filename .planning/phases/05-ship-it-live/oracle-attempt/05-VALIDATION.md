---
phase: 5
slug: ship-it-live
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-12
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `05-RESEARCH.md` § Validation Architecture. Phase 5 is a **deploy + validate**
> phase: most success criteria are **live-UAT-only** (Oracle A1 + live Discord + Postgres) and
> cannot run on the Windows dev machine. Only the TZ helper, the queue invariant, and the
> seed-data shape logic are unit-testable.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | none — default discovery |
| **Quick run command** | `pytest tests/test_queue.py tests/test_streak.py tests/test_roasts.py tests/test_seasonal.py tests/test_prompts.py -q` |
| **Full suite command** | `pytest tests/ -q --ignore=tests/test_database_phase4.py` |
| **Estimated runtime** | ~10 seconds (pure-unit subset; `test_database_phase4.py` needs live Postgres) |

---

## Sampling Rate

- **After every task commit:** Run quick run command (fast pure-unit subset)
- **After every plan wave:** Run full suite command (125+ pure tests)
- **Before `/gsd-verify-work`:** Full pure suite green on dev machine **AND** all 21 live-UAT checks passing on Oracle A1
- **Max feedback latency:** ~10 seconds (dev-machine pure tests)

---

## Per-Task Verification Map

> Phase 5's automated surface is small by nature. The rows below are the **only** units with
> dev-machine automated verification; task IDs are bound to these during planning. Everything
> else is live-UAT (see Manual-Only Verifications).

| Item | Requirement | Test Type | Automated Command | File Exists | Status |
|------|-------------|-----------|-------------------|-------------|--------|
| TZ-aware hour computation (`datetime.now(tz=ZoneInfo(STREAK_TIMEZONE)).hour`) | D-06 (supports DEPLOY-02) | unit | `pytest tests/test_streak.py -q` | ✅ (add 1 test) | ⬜ pending |
| `_play_generation` stale-callback invariant (reconnect guard does not regress) | DEPLOY-04 | unit | `pytest tests/test_queue.py -q` | ✅ | ⬜ pending |
| Seed-data shape (pure row-construction logic, no DB) | DEPLOY-07 | unit | `pytest tests/test_seed_restore.py -q` | ❌ W0 | ⬜ pending |
| `clear_persisted()` insertion compiles (idle-leave + reconnect-failure sites) | DEPLOY-06 | structural | `python -m py_compile bot.py cogs/music.py` | ✅ | ⬜ pending |
| Reconnect-path source assertion (`is_connected()` guard present at queue_persistence.py:147) | DEPLOY-04 | structural | `grep -n "is_connected" services/queue_persistence.py` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_streak.py` — add `test_tz_aware_hour_is_integer()`: assert `datetime.now(tz=ZoneInfo(STREAK_TIMEZONE)).hour` returns an int in `[0,23]` (covers the D-06 TZ-fix pattern)
- [ ] `tests/test_seed_restore.py` — **new file**: pure tests for seed-row data structure (user/streak/song_history/artist-count row shapes), no DB connection

*Existing pytest infrastructure is in place; no new framework setup needed.*

---

## Manual-Only Verifications

> These are the live-UAT checks consolidated into the Phase 5 runbook (D-07). They require
> Oracle A1 + live Discord + live Postgres + external accounts (OCI, Healthchecks.io) and
> **cannot** be automated on the dev machine. The phase is verified when these pass live.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Bot + Postgres boot via `docker compose up`; survives host reboot | DEPLOY-01 | Needs Oracle A1 + Docker + real `DISCORD_TOKEN` | Runbook boot section: `docker compose up -d` → confirm startup message in Discord → `sudo reboot` → confirm repost + `systemctl is-enabled docker` |
| 9 Phase-3 behavioral checks fire | DEPLOY-02 | Live Discord gateway + voice + probabilistic events | Runbook behavioral section: voice roasts, startup msg, status rotation, /lyrics, /history, reactions, repeat-song roast, streak milestones, idle loneliness |
| 6 Phase-4 deploy/human checks pass | DEPLOY-03 | Oracle host + live Discord | Runbook deploy section: clean-boot, queue round-trip, over-cap rejection, Postgres integration, keepalive cron, backup cron |
| Reconnect race does not double-play/silent-fail under live concurrency | DEPLOY-04 | Live-concurrency network/gateway timing | Runbook: trigger a live voice reconnect; inspect new diagnostic logs (generation/connection-state trail); escalate to `/gsd:debug` only if it still races |
| Queue + position survive restart; smart-rejoin works | DEPLOY-05 | Live Discord bot + Postgres | Runbook: queue songs → restart container → confirm `/queue` restored + playback rejoins |
| `clear_persisted()` clears on idle-leave + reconnect-failure | DEPLOY-06 | Discord voice-state events + live `guild_queues` table | Runbook: force idle-leave and reconnect-failure → confirm persisted queue row cleared |
| `pg_dump` → OCI upload → restore into throwaway DB matches row counts | DEPLOY-07 | OCI Object Storage round-trip; live Postgres | Runbook destructive section (LAST): seed rows → `backup.sh` → download → restore into `dexter_restore_test` → assert row counts; **never touch live DB** |
| Keepalive cron fires; Healthchecks.io shows green; alert routes to Discord+email | DEPLOY-08 | Oracle crontab + live Healthchecks.io account | Runbook: confirm `*/5` keepalive ping → dashboard green → kill bot → confirm Discord webhook + email alert |

---

## Validation Sign-Off

- [ ] All automatable tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: live-UAT-heavy phase — automated coverage limited to the 5 rows above by design (documented, not a gap)
- [ ] Wave 0 covers both MISSING references (`test_streak.py` add, `test_seed_restore.py` new)
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
