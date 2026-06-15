---
phase: 5
slug: ship-it-live
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-15
---

# Phase 5 — Validation Strategy (Koyeb + Neon re-target)

> Per-phase validation contract for feedback sampling during execution.
> Most of Phase 5 is platform integration + live-UAT (Koyeb deploy, Neon behavior,
> Discord behavior) — only the pure `sanitize_database_url()` helper (K-05) is unit-testable.
> Source: 05-RESEARCH.md "## Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing, `tests/`) |
| **Config file** | none beyond existing pytest defaults |
| **Quick run command** | `pytest tests/test_config.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~quick: <2s · full: existing suite |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_config.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd-verify-work`:** Full suite green **AND** all live-UAT checks (05-UAT-RUNBOOK.md) passing on Koyeb+Neon
- **Max feedback latency:** ~2 seconds (unit) · live-UAT is human-paced

---

## Per-Task Verification Map

> Task IDs are finalized by the planner; rows below are the testable units the plans MUST honor.

| Unit | Decision | Wave | Requirement | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|------|----------|------|-------------|-----------------|-----------|-------------------|-------------|--------|
| `sanitize_database_url` strips `?sslmode=require&channel_binding=require` → no query string | K-05 | 0 | DEPLOY-01 | No unrecognized GUC reaches asyncpg; SSL via `ssl='require'` kwarg | unit | `pytest tests/test_config.py::test_sanitize_database_url -x` | ❌ W0 | ⬜ pending |
| `sanitize_database_url` no-op on a clean DSN (no `?`) | K-05 | 0 | DEPLOY-01 | Idempotent; safe for local non-Neon DSN | unit | `pytest tests/test_config.py::test_sanitize_database_url_noop -x` | ❌ W0 | ⬜ pending |
| `sanitize_database_url` strips reversed-order params | K-05 | 0 | DEPLOY-01 | Order-independent | unit | `pytest tests/test_config.py::test_sanitize_database_url_reversed_params -x` | ❌ W0 | ⬜ pending |
| `create_pool` called with `ssl='require'`, `max_inactive_connection_lifetime=240`, `statement_cache_size=0`, `max_size` trimmed | K-04 | 1 | DEPLOY-01 | No SSL-EOF after Neon scale-to-zero; no PgBouncer prepared-stmt errors | structural review | boot + diff of `create_pool` call | inline | ⬜ pending |
| Minimal `/health` returns 200 `{"status":"ok"}` bound to `0.0.0.0:8000` | K-02 | 1 | DEPLOY-01 | No internal state exposed | structural review + boot | `curl localhost:8000/health` | inline | ⬜ pending |
| Existing `tests/test_database.py` (streak logic etc.) still green with tuned pool | K-04 | 1 | — | No regression | unit | `pytest tests/test_database.py -x -q` | ✅ | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `tests/test_config.py` — unit tests for `sanitize_database_url` (the 3 cases above). **New file, must be created in Wave 0.**
- [ ] Confirm existing `tests/test_database.py` passes unchanged with the Neon-tuned asyncpg pool params.

---

## Manual-Only Verifications

> All deploy/runtime behavior is live-UAT (Koyeb + Neon + Discord) — see 05-UAT-RUNBOOK.md (re-targeted per K-18). The phase is verified-live when these pass (K-17), not when code lands.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Bot holds a 24/7 Koyeb WEB-service gateway (health endpoint + UptimeRobot keep-alive defeat 1h sleep) | DEPLOY-01 | Requires live Koyeb account + Discord | 05-UAT-RUNBOOK §A (Koyeb deploy + worker-alive) |
| Redeploy auto-reconnects + restores queue from Neon | DEPLOY-05 | Live Koyeb redeploy + Neon | Push trivial commit → Koyeb rebuilds → `/queue` restored |
| Pool survives Neon 5-min idle scale-to-zero with no SSL-EOF | K-17 #3 | Requires live Neon suspend timing | Idle 6+ min → `/history`/`/play` → query succeeds, no SSL error in logs |
| 9 Phase-3 behavioral + 6 Phase-4 deploy checks fire live | DEPLOY-02 | Live Discord session | 05-UAT-RUNBOOK §C (behavioral) |
| 6 human-UAT scenarios pass | DEPLOY-03 | Live Discord session | 05-HUMAN-UAT.md / 05-UAT-RUNBOOK §C |
| Voice playback survives a live reconnect (P-01) | DEPLOY-04 | Live concurrency only | 05-UAT-RUNBOOK §C; escalate to `/gsd:debug` only if it still races |
| `clear_persisted()` fires on idle-leave + reconnect-failure (P-02) | DEPLOY-06 | Live voice events | 05-UAT-RUNBOOK §C |
| Neon PITR branch-restore confirmed + data verified | DEPLOY-07 | Live Neon console | 05-UAT-RUNBOOK §D (destructive, LAST) |
| Healthchecks.io dead-man ping confirmed firing | DEPLOY-08 | Live outbound ping | Healthchecks.io dashboard shows recent ping |

---

## Validation Sign-Off

- [ ] All non-manual tasks have an `<automated>` verify or a Wave 0 dependency
- [ ] Sampling continuity: no 3 consecutive automatable tasks without automated verify
- [ ] Wave 0 covers `tests/test_config.py` (the K-05 sanitizer)
- [ ] No watch-mode flags
- [ ] Feedback latency < ~2s (unit)
- [ ] `nyquist_compliant: true` set in frontmatter once plans honor this contract

**Approval:** pending
