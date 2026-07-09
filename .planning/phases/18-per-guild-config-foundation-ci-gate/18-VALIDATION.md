---
phase: 18
slug: per-guild-config-foundation-ci-gate
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-10
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `18-RESEARCH.md` §"Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 1.4.0 (strict mode — explicit `@pytest.mark.asyncio` on every async test; no `asyncio_mode` config needed) |
| **Config file** | None today (no `pytest.ini` / `setup.cfg`). Phase 18 adds `pyproject.toml` for **Ruff only** — pytest config stays absent. |
| **Quick run command** | `pytest -q -k "guild_config"` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | ~15s quick · ~60s full (956 tests: 848 pass / 108 skip / 0 fail at v1.3 close baseline) |

**Live-DB tests:** ~107 tests take the `pool` fixture and skip on connection error
(`TEST_DATABASE_URL`, default `postgresql://dexter:dexter@localhost:5432/dexter_test`). 9 of those
carry an additional `_SKIP_LIVE` module-level pre-skip. Both mechanisms key off the same env var,
so setting `TEST_DATABASE_URL` in CI unskips both categories simultaneously — **but only after the
`tests/conftest.py` pgvector-codec fix lands** (see Wave 0).

---

## Sampling Rate

- **After every task commit:** `pytest -q -k "guild_config"`
- **After every plan wave:** `pytest -q` (full suite)
- **Before `/gsd-verify-work`:** Full suite green locally (0 fail); no regression in pass count vs. the 848/108/0 baseline
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

Task IDs are assigned by the planner. This map is keyed by requirement; the planner MUST ensure every
task inherits the row matching the requirement it addresses.

| Requirement | Wave | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|------|------------|-----------------|-----------|-------------------|-------------|--------|
| CONFIG-01 | 1 | T-18-SQLI | All `guild_config` reads/writes use `$N` asyncpg parameters — no f-string SQL | unit (schema introspection, mirrors `test_database_phase16.py`) | `pytest tests/test_database_phase18.py -x` | ❌ W0 | ⬜ pending |
| CONFIG-02 | 2 | — | The strict resolver is the only ambient path; no caller can re-derive the fallback chain | unit (mock-free pure logic) + structural (`DEXTER_CHANNEL_ID` absent from `cogs/`) | `pytest tests/test_guild_config_logic.py -x` | ❌ W0 | ⬜ pending |
| CONFIG-03 | 1 | T-18-XGUILD | Cache keyed by `guild_id`; `get()` cannot return another guild's row | unit (spy pool asserting zero `.acquire()` calls after `load_all()`) | `pytest tests/test_guild_config_service.py -x` | ❌ W0 | ⬜ pending |
| CONFIG-04 | 2 | T-18-AMBIENT | Unconfigured guild → every ambient surface silent; cache miss is authoritative, no DB read | unit (all 6 call sites; mirrors `test_proactive_events.py` `_make_bot`/`_make_message`) | `pytest tests/test_proactive_events.py tests/test_vision_events.py tests/test_ambient_recall_cadence.py -x` | ✅ (needs update) | ⬜ pending |
| CONFIG-05 | 1 | T-18-SEED | Seed derives `guild_id` from a config value, never user input; `ON CONFLICT DO NOTHING` so `.env` cannot override a deliberate `/setup` | live-DB round-trip + structural assert on `ON CONFLICT (guild_id) DO NOTHING` | `pytest tests/test_database_phase18.py -x` (live portion needs `TEST_DATABASE_URL`) | ❌ W0 | ⬜ pending |
| CICD-01 | 1 | T-18-CIPRIV | `pull_request` (never `pull_request_target`); top-level `permissions: contents: read`; zero repo secrets referenced | **manual-only** — the workflow's correctness cannot be asserted from inside the suite it runs | N/A — first push/PR IS the verification | N/A | ⬜ pending |
| CICD-01 (fixture prereq) | 1 | — | Live-DB tests pass rather than error once `TEST_DATABASE_URL` is set | unit (live-DB) | `TEST_DATABASE_URL=... pytest tests/test_database_phase11.py -x` | ✅ (needs fix) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — **fix the `pool` fixture**: extension-first throwaway connection running
      `CREATE EXTENSION IF NOT EXISTS vector;`, then `create_pool(dsn, init=_register_vector)`.
      Mirrors `bot.py::_initialize_once` (lines 356-392). **Prerequisite for CICD-01** — without it,
      enabling `TEST_DATABASE_URL` in CI converts ~9 skipped tests into errors, not passes
      (RESEARCH Open Question 2).
- [ ] `tests/test_database_phase18.py` — stubs for CONFIG-01, CONFIG-05
- [ ] `tests/test_guild_config_logic.py` — stubs for CONFIG-02 (pure, mock-free)
- [ ] `tests/test_guild_config_service.py` — stubs for CONFIG-03
- [ ] `pyproject.toml` `[tool.ruff]` — new file, no existing lint config to extend
- [ ] `.github/workflows/ci.yml` — new file, no existing workflow to extend

*Framework install: not needed — pytest + pytest-asyncio already present. Ruff must be added to a
dev-requirements surface.*

---

## Manual-Only Verifications

The 24/7 live-Discord host remains **parked** (residential-IP-only, per the standing v1.1→v1.3
precedent). These carry forward to `18-HUMAN-UAT.md` at phase close, consistent with Phases
11/13/14/15/16/17.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Workflow actually runs and blocks on push + PR | CICD-01 | A workflow YAML's correctness is only observable from GitHub's runner, not from the suite it executes | Push the branch; confirm the `CI` check appears, runs pytest + Ruff, and that a deliberately-broken commit turns the check red |
| Home guild behaves identically after the refactor | CONFIG-05 / SC-2 | Requires a live Discord connection + the real `DEXTER_CHANNEL_ID` guild | Boot against the real token; confirm the startup message posts to the same channel as before, and that a voice-join roast still fires there |
| A brand-new guild is completely ambient-silent | CONFIG-04 / SC-1 | Requires inviting the bot to a second live guild | Invite Dexter to a fresh guild; run `/play` (must work); join voice, post an image, chat in any channel — confirm zero unprompted output, and a clean `dexter.log` |
| Stale/unwritable configured channel → silent skip + `WARNING` log | CONFIG-02 / D-03 | Requires revoking `send_messages` on a live channel | Revoke `send_messages` on the configured ambient channel; trigger a voice-join roast; confirm no message, one `WARNING` in `dexter.log`, and `configured` still `true` in the DB |

*Everything else — the resolver's decision logic, the cache's no-round-trip property, the schema,
and the seed's idempotence — is automated above.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (conftest fix → 18-02; test scaffolds → 18-02/03/04; pyproject → 18-01; ci.yml → 18-07)
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved — 7 plans across 5 waves; every task carries an <automated> verify (checkpoint tasks excepted); CICD-01 first-push check is parked manual-only per host precedent.
