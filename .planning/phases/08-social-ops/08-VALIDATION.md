---
phase: 08
slug: social-ops
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-19
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

Rows keyed by requirement (planner maps to concrete task IDs and threat refs). `File Exists` ❌ W0 = test file is a Wave-0 dependency that must be created before the behavior task.

| Req | Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-----|----------|------------|-----------------|-----------|-------------------|-------------|--------|
| SOCIAL-01 | Template fallback fires when Gemini raises rate-limit error | — | Rate-limit never blocks the command | unit | `pytest tests/test_roast_command.py::test_roast_template_fallback -x` | ❌ W0 | ⬜ pending |
| SOCIAL-01 | self / bot / zero-history branches each return a line (no error/decline) | — | Zero-history target does not leak/raise | unit | `pytest tests/test_roast_command.py::test_roast_edge_cases -x` | ❌ W0 | ⬜ pending |
| SOCIAL-01 | `/roast` calls `gemini.chat()` at priority=1 | — | N/A | unit | `pytest tests/test_roast_command.py::test_roast_uses_priority_1 -x` | ❌ W0 | ⬜ pending |
| SOCIAL-01 | Public roast send uses `AllowedMentions.none()` | T-mention-spoof | No mass-mention via target string | unit | `pytest tests/test_roast_command.py::test_roast_no_mass_mention -x` | ❌ W0 | ⬜ pending |
| SOCIAL-01 | Roast tone/voice (lowercase, on-brand, guardrails) | — | No slurs/protected-class content | human-UAT | — | — | ⬜ pending |
| SOCIAL-02 | `songs_queued` per-guild count excludes other guilds | T-sql-inj | `$N` params only, guild-scoped | integration (live DB) | `pytest tests/test_database_phase8.py::test_leaderboard_songs_guild_scoped -x` | ❌ W0 | ⬜ pending |
| SOCIAL-02 | `skips` query counts only `was_skipped=true` | — | N/A | integration (live DB) | `pytest tests/test_database_phase8.py::test_leaderboard_skips_filter -x` | ❌ W0 | ⬜ pending |
| SOCIAL-02 | Streak query returns only guild-active users | — | No cross-guild leak | integration (live DB) | `pytest tests/test_database_phase8.py::test_leaderboard_streak_guild_scoped -x` | ❌ W0 | ⬜ pending |
| SOCIAL-02 | Tie-break by oldest `first_seen_at` (D-16) | — | N/A | integration (live DB) | `pytest tests/test_database_phase8.py::test_leaderboard_tie_break -x` | ❌ W0 | ⬜ pending |
| SOCIAL-02 | Empty/brand-new server → empty result lists | — | N/A | integration (live DB) | `pytest tests/test_database_phase8.py::test_leaderboard_empty_guild -x` | ❌ W0 | ⬜ pending |
| SOCIAL-02 | Embed visual layout (labels, 3-section order) | — | N/A | human-UAT | — | — | ⬜ pending |
| OPS-01 | `total_errors` column exists after `init_db` | — | N/A | integration (live DB) | `pytest tests/test_database_phase8.py::test_total_errors_column_exists -x` | ❌ W0 | ⬜ pending |
| OPS-01 | `increment_daily_stat("total_errors")` upserts (allowlist) | T-field-inj | Allowlist gates field name | integration (live DB) | `pytest tests/test_database_phase8.py::test_total_errors_increment -x` | ❌ W0 | ⬜ pending |
| OPS-01 | daily-stats row read returns 0s when no row exists | — | N/A | integration (live DB) | `pytest tests/test_database_phase8.py::test_get_daily_stats_row_empty -x` | ❌ W0 | ⬜ pending |
| OPS-01 | `/stats` owner-only + ephemeral | T-owner-bypass | `bot.is_owner()` authoritative | human-UAT | — | — | ⬜ pending |
| OPS-02 | `/health` returns `{"status":"ok"}` when DB+gateway ready | — | N/A | integration | `pytest tests/test_health_endpoint.py::test_health_ok -x` | ❌ W0 | ⬜ pending |
| OPS-02 | `/health` returns degraded body when pool fails | T-state-leak | Generic reasons only, no internal state | integration | `pytest tests/test_health_endpoint.py::test_health_degraded_db -x` | ❌ W0 | ⬜ pending |
| OPS-02 | `/health` always HTTP 200 (no kill-loop) | — | N/A | integration | `pytest tests/test_health_endpoint.py::test_health_always_200 -x` | ❌ W0 | ⬜ pending |
| OPS-03 | `rpm_usage()` returns count after N acquires | — | N/A | unit | `pytest tests/test_rate_limiter.py::test_rpm_usage_getter -x` | ✅ extend | ⬜ pending |
| OPS-03 | `rpm_headroom()` = `GEMINI_RPM_LIMIT - rpm_usage()` | — | N/A | unit | `pytest tests/test_rate_limiter.py::test_rpm_headroom_getter -x` | ✅ extend | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_database_phase8.py` — leaderboard SQL integration tests (3 queries) + `total_errors` column/increment/read tests
- [ ] `tests/test_roast_command.py` — `/roast` unit tests (mock Gemini fallback, edge-case branches, priority=1, no mass-mention)
- [ ] `tests/test_health_endpoint.py` — `/health` ok / degraded / always-200 integration tests
- [ ] `tests/test_rate_limiter.py` — **extend** with `test_rpm_usage_getter` + `test_rpm_headroom_getter`

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

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (3 new test files + 1 extension)
- [ ] No watch-mode flags
- [ ] Feedback latency < 40s
- [ ] `nyquist_compliant: true` set in frontmatter (after Wave 0 lands)

**Approval:** pending
