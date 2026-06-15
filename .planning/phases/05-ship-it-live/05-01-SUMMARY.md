---
phase: "05"
plan: "01"
subsystem: database-layer / health-endpoint
tags: [neon, asyncpg, koyeb, pool-tuning, health-endpoint, tdd]
dependency_graph:
  requires: []
  provides:
    - config.sanitize_database_url
    - config.DB_MAX_INACTIVE_CONN_LIFETIME
    - config.DB_STATEMENT_CACHE_SIZE
    - bot._run_health_server
    - tuned-asyncpg-create_pool
  affects:
    - bot.py (create_pool call site, health endpoint task)
    - config.py (constants + pure sanitizer function)
    - tests/test_config.py (Wave-0 unit tests)
tech_stack:
  added: []
  patterns:
    - "pure function in config.py with import inside body (minimal-import convention)"
    - "asyncio.ensure_future for one-shot background coroutine"
    - "aiohttp.web.Application with AppRunner + TCPSite for minimal HTTP server"
    - "TDD RED→GREEN cycle for pure-function unit test"
key_files:
  created:
    - tests/test_config.py
  modified:
    - config.py
    - bot.py
decisions:
  - "DB_POOL_MAX lowered 10->5 for Neon free single-worker (K-04)"
  - "AUDIO_CACHE_MAX_MB lowered 2048->512 for Koyeb 2GB ephemeral disk (K-07)"
  - "sanitize_database_url strips entire query string with re.sub — simpler and safe; all Neon query params are SSL/auth hints asyncpg handles via ssl= kwarg (K-05)"
  - "_run_health_server uses asyncio.Event().wait() to stay alive and remain cancellable (K-02 amendment)"
  - "No before_loop guard on health server — must be reachable before Discord connects so Koyeb's health check passes on first deploy"
  - "Flat-name alias functions added at module level in test_config.py for 05-VALIDATION.md automated command compatibility"
metrics:
  duration: "~8 minutes"
  completed: "2026-06-15T08:09:44Z"
  tasks: 2
  commits: 3
  files_created: 1
  files_modified: 2
---

# Phase 05 Plan 01: Neon DB Layer + Koyeb Health Endpoint Summary

**One-liner:** Neon-tuned asyncpg pool (ssl='require', 240s lifetime, statement_cache_size=0) + sanitize_database_url pure function + minimal aiohttp /health on 0.0.0.0:8000 for Koyeb WEB service.

---

## What Was Built

This plan wired Dexter's database layer and HTTP liveness for the Koyeb + Neon substrate:

1. **`config.sanitize_database_url(dsn)`** — pure function that strips the entire query string from a Neon console connection string (`?sslmode=require&channel_binding=require`) before asyncpg ever sees it. asyncpg treats unrecognized DSN params as Postgres GUCs; `channel_binding` would cause `unrecognized configuration parameter` errors. Stripping the query string is simpler and safe because SSL is handled via explicit `ssl='require'` kwarg.

2. **New config constants (K-04/K-07):**
   - `DB_MAX_INACTIVE_CONN_LIFETIME = 240` — recycles connections before Neon's 5-min scale-to-zero
   - `DB_STATEMENT_CACHE_SIZE = 0` — disables prepared statement caching for PgBouncer transaction mode
   - `DB_POOL_MAX = 5` (was 10) — trimmed for Neon free single-worker
   - `AUDIO_CACHE_MAX_MB = 512` (was 2048) — safe for Koyeb's 2GB ephemeral disk

3. **Tuned `asyncpg.create_pool` call** in `bot.py._initialize_once()` — added `ssl='require'`, `max_inactive_connection_lifetime=config.DB_MAX_INACTIVE_CONN_LIFETIME`, `statement_cache_size=config.DB_STATEMENT_CACHE_SIZE`, and `dsn=config.sanitize_database_url(config.DATABASE_URL)`.

4. **`_run_health_server()` background coroutine** — minimal aiohttp GET /health returning `{"status":"ok"}` bound to `0.0.0.0:8000` (not localhost, per Pitfall 5). Launched via `asyncio.ensure_future()` inside `_initialize_once()` after background tasks start, before `restore_queues`. Stays alive via `asyncio.Event().wait()` and is cancellable.

5. **`tests/test_config.py`** — Wave-0 unit tests (TDD RED→GREEN): 3 class-based tests in `TestSanitizeDatabaseUrl` + 3 flat-name aliases for VALIDATION.md automated command compatibility. All 6 pass.

---

## Commits

| Hash | Type | Description |
|------|------|-------------|
| `fb32826` | test | TDD RED — failing Wave-0 tests for sanitize_database_url |
| `93d3ff5` | feat | TDD GREEN — sanitize_database_url + Neon constants in config.py |
| `0fc4f6e` | feat | Tuned create_pool + _run_health_server() in bot.py |

---

## Verification Status

| Check | Status |
|-------|--------|
| `pytest tests/test_config.py -x -q` | PASSED (6 tests) |
| `pytest tests/test_streak.py -q` | PASSED (12 tests, no regression) |
| `python -c "import ast; ast.parse(open('bot.py').read())"` | PASSED |
| AST acceptance check (health server + ssl kwarg + stmt_cache + 0.0.0.0) | PASSED |
| `python -c "import config; print(config.sanitize_database_url('...'))"` | PASSED |
| Local boot + `curl localhost:8000/health` | **PENDING** (human-check; requires local Postgres via docker compose break-glass) |
| Full suite (`pytest tests/ -q`) | Pre-existing failures only (google/yt_dlp modules not installed on Windows host; test_database_phase4 requires live Postgres connection — ConnectionRefusedError since Docker not running). Zero new failures introduced. |

---

## Deviations from Plan

None — plan executed exactly as written.

The test_database_phase4.py and google/yt_dlp test failures observed during full-suite run are pre-existing (require Docker+Postgres and google-genai/yt-dlp packages not installed on the Windows dev host). Confirmed pre-existing by checking the same test suite at the prior commit.

---

## Known Stubs

None. All wired with real config constants.

---

## Threat Flags

No new threat surface beyond what the plan's threat model already covers. The `/health` endpoint returns only `{"status":"ok"}` with no internal state exposed (T-05-01 mitigated). SSL is forced via explicit kwarg (T-05-03 mitigated). DSN not logged (T-05-02 mitigated).

---

## Pending Human Check

The plan's `<human-check>` for Task 2 — boot the bot locally against local Postgres (docker compose break-glass) and run `curl localhost:8000/health` to confirm `{"status":"ok"}` with HTTP 200 — is not an autonomous task. The live Koyeb+Neon verification (scale-to-zero reconnect, deploy-healthy) is captured in `05-UAT-RUNBOOK.md` (Plan 03) and executed by the user.

---

## Self-Check: PASSED

- `tests/test_config.py` — FOUND
- `config.py` contains `def sanitize_database_url(` — FOUND
- `config.py` contains `DB_MAX_INACTIVE_CONN_LIFETIME = 240` — FOUND
- `config.py` contains `DB_STATEMENT_CACHE_SIZE = 0` — FOUND
- `config.py` contains `DB_POOL_MAX = 5` — FOUND
- `config.py` contains `AUDIO_CACHE_MAX_MB = 512` — FOUND
- `bot.py` contains `_run_health_server` — FOUND
- `bot.py` contains `ssl='require'` — FOUND
- Commits fb32826, 93d3ff5, 0fc4f6e — FOUND in git log
