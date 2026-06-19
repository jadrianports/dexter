---
phase: 08
slug: social-ops
status: verified
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-19
validated: 2026-06-19
---

# Phase 08 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Seeded from `08-RESEARCH.md` § Validation Architecture. Task IDs are filled in by the planner/executor; rows below are keyed by requirement until then.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (already present; existing suite runs) |
| **Config file** | none — fixtures live in `tests/conftest.py` (the `pool` fixture drops/recreates tables; `bot_daily_stats` already in its DROP list) |
| **Quick run command** | `pytest tests/test_database_phase8.py tests/test_roast_command.py tests/test_rate_limiter.py -x` |
| **Full suite command** | `pytest tests/ -x` |
| **Estimated runtime** | ~20–40s (live-DB integration tests dominate) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_database_phase8.py tests/test_roast_command.py tests/test_rate_limiter.py -x`
- **After every plan wave:** Run `pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~40 seconds

---

## Per-Task Verification Map

Rows keyed by requirement (planner maps to concrete task IDs and threat refs). `File Exists` ✅ = Wave-0 test file landed. All 17 automated rows confirmed green on 2026-06-19 (unit/mock tests run DB-less; the 8 live-DB integration tests confirmed green against a throwaway `postgres:16-alpine` matching the conftest DSN).

| Req | Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-----|----------|------------|-----------------|-----------|-------------------|-------------|--------|
| SOCIAL-01 | Template fallback fires when Gemini raises rate-limit error | T-08-05 | Rate-limit never blocks the command | unit | `pytest tests/test_roast_command.py::test_roast_template_fallback -x` | ✅ | ✅ green |
| SOCIAL-01 | self / bot / zero-history branches each return a line (no error/decline) | — | Zero-history target does not leak/raise | unit | `pytest tests/test_roast_command.py::test_roast_edge_cases -x` | ✅ | ✅ green |
| SOCIAL-01 | `/roast` calls `gemini.chat()` at priority=1 | T-08-05 | N/A | unit | `pytest tests/test_roast_command.py::test_roast_uses_priority_1 -x` | ✅ | ✅ green |
| SOCIAL-01 | Public roast send uses `AllowedMentions.none()` | T-08-04 (mention-spoof) | No mass-mention via target string | unit | `pytest tests/test_roast_command.py::test_roast_no_mass_mention -x` | ✅ | ✅ green |
| SOCIAL-01 | Roast tone/voice (lowercase, on-brand, guardrails) | T-08-06 | No slurs/protected-class content | human-UAT | — | — | ⬜ manual-UAT pending |
| SOCIAL-02 | `songs_queued` per-guild count excludes other guilds | T-08-01/T-08-10 (sql-inj) | `$N` params only, guild-scoped | integration (live DB) | `pytest tests/test_database_phase8.py::test_leaderboard_songs_guild_scoped -x` | ✅ | ✅ green |
| SOCIAL-02 | `skips` query counts only `was_skipped=true` | — | N/A | integration (live DB) | `pytest tests/test_database_phase8.py::test_leaderboard_skips_filter -x` | ✅ | ✅ green |
| SOCIAL-02 | Streak query returns only guild-active users | T-08-10 | No cross-guild leak | integration (live DB) | `pytest tests/test_database_phase8.py::test_leaderboard_streak_guild_scoped -x` | ✅ | ✅ green |
| SOCIAL-02 | Tie-break by oldest `first_seen_at` (D-16) | — | N/A | integration (live DB) | `pytest tests/test_database_phase8.py::test_leaderboard_tie_break -x` | ✅ | ✅ green |
| SOCIAL-02 | Empty/brand-new server → empty result lists | — | N/A | integration (live DB) | `pytest tests/test_database_phase8.py::test_leaderboard_empty_guild -x` | ✅ | ✅ green |
| SOCIAL-02 | Embed visual layout (labels, 3-section order) | — | N/A | human-UAT | — | — | ⬜ manual-UAT pending |
| OPS-01 | `total_errors` column exists after `init_db` | — | N/A | integration (live DB) | `pytest tests/test_database_phase8.py::test_total_errors_column_exists -x` | ✅ | ✅ green |
| OPS-01 | `increment_daily_stat("total_errors")` upserts (allowlist) | T-08-02 (field-inj) | Allowlist gates field name | integration (live DB) | `pytest tests/test_database_phase8.py::test_total_errors_increment -x` | ✅ | ✅ green |
| OPS-01 | daily-stats row read returns 0s when no row exists | — | N/A | integration (live DB) | `pytest tests/test_database_phase8.py::test_get_daily_stats_row_empty -x` | ✅ | ✅ green |
| OPS-01 | `/stats` owner-only + ephemeral | T-08-09 (owner-bypass) | `bot.is_owner()` authoritative | human-UAT | — | — | ⬜ manual-UAT pending |
| OPS-02 | `/health` returns `{"status":"ok"}` when DB+gateway ready | — | N/A | integration | `pytest tests/test_health_endpoint.py::test_health_ok -x` | ✅ | ✅ green |
| OPS-02 | `/health` returns degraded body when pool fails | T-08-08 (state-leak) | Generic reasons only, no internal state | integration | `pytest tests/test_health_endpoint.py::test_health_degraded_db -x` | ✅ | ✅ green |
| OPS-02 | `/health` always HTTP 200 (no kill-loop) | T-08-11 | N/A | integration | `pytest tests/test_health_endpoint.py::test_health_always_200 -x` | ✅ | ✅ green |
| OPS-03 | `rpm_usage()` returns count after N acquires | — | N/A | unit | `pytest tests/test_rate_limiter.py::test_rpm_usage_getter -x` | ✅ | ✅ green |
| OPS-03 | `rpm_headroom()` = `GEMINI_RPM_LIMIT - rpm_usage()` | — | N/A | unit | `pytest tests/test_rate_limiter.py::test_rpm_headroom_getter -x` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> **Coverage result (2026-06-19):** 17/17 automated behaviors **green**. 3 items are inherent human-UAT (subjective tone, visual embed layout, live-Discord owner ACL) and remain pending live verification — see Manual-Only Verifications. No MISSING or PARTIAL automated gaps.

---

## Wave 0 Requirements

- [x] `tests/test_database_phase8.py` — leaderboard SQL integration tests (3 queries) + `total_errors` column/increment/read tests — **8 tests, green vs live PG**
- [x] `tests/test_roast_command.py` — `/roast` unit tests (mock Gemini fallback, edge-case branches, priority=1, no mass-mention) — **4 tests, green**
- [x] `tests/test_health_endpoint.py` — `/health` ok / degraded / always-200 integration tests — **3 tests, green**
- [x] `tests/test_rate_limiter.py` — **extended** with `test_rpm_usage_getter` + `test_rpm_headroom_getter` — **2 tests, green**

Framework install: none — pytest + pytest-asyncio already present. `conftest.py` `pool` fixture already drops `bot_daily_stats` (covers the new column via full-table DROP).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Roast tone/voice quality | SOCIAL-01 | Subjective — lowercase, dry, harsher-with-guardrails, no cruelty | Run `/roast @someone` with real song history; confirm voice matches Dex and stays about music behavior |
| Leaderboard embed layout | SOCIAL-02 | Visual — 3 sections, top-5, dry commentary line | Run `/leaderboard` on a server with activity; confirm 3 sections render + commentary |
| `/stats` owner-only + ephemeral | OPS-01 | Discord-runtime ACL + ephemeral visibility | Owner runs `/stats` → sees embed; non-owner gets ephemeral refusal |
| Healthchecks.io green / degraded alert | OPS-02 | External dead-man switch dashboard | Confirm `/health` reachable by the cron; dashboard shows green; flip DB to confirm degraded body |
| Koyeb/Neon dashboard link visible | OPS-03 | External platform dashboard (no in-process scraping per D-30) | Confirm `/stats` (or embed footer) links the platform dashboard for CPU/mem |

---

## Validation Audit 2026-06-19

| Metric | Count |
|--------|-------|
| Requirements (automatable) | 17 |
| COVERED (green) | 17 |
| PARTIAL (failing/incomplete) | 0 |
| MISSING (no test) | 0 |
| Human-UAT (inherent manual) | 3 |
| Gaps found | 0 |
| Resolved | 0 (none needed) |
| Escalated | 0 |

**Run command (DB-less unit/mock):** `pytest tests/test_roast_command.py tests/test_rate_limiter.py tests/test_health_endpoint.py` → 13 passed.
**Run command (live DB):** `TEST_DATABASE_URL=postgresql://dexter:dexter@localhost:5432/dexter_test pytest tests/test_database_phase8.py` → 8 passed (throwaway `postgres:16-alpine`, removed after run).

**Auditor:** not spawned — gap analysis found zero automated coverage gaps (all Wave-0 tests landed and green), so the workflow short-circuited to the VALIDATION.md update per Step 3.

### Non-blocking observation
`tests/conftest.py`'s `pool` fixture docstring claims DB tests are "skipped (connection error) when no Postgres is available," but the fixture calls `asyncpg.create_pool()` without catching the connection error — so without a DB the 8 integration tests **ERROR** rather than SKIP. This does not affect coverage (the tests exist and pass against a real DB) but means `pytest tests/ -x` hard-errors in a DB-less environment instead of skipping. Optional hardening: wrap the connect in `try/except (OSError, asyncpg.PostgresError): pytest.skip(...)`. Left as-is (out of scope for this validation audit; no coverage impact).

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (3 new test files + 1 extension) — all landed
- [x] No watch-mode flags
- [x] Feedback latency < 40s
- [x] `nyquist_compliant: true` set in frontmatter (Wave 0 landed + 17/17 green)

**Approval:** verified 2026-06-19 (17/17 automated green; 3 inherent human-UAT items pending live verification)
