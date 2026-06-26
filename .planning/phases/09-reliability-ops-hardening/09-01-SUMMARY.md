---
phase: "09"
plan: "01"
subsystem: reliability-ops
tags: [health-endpoint, config, asyncpg, timeout, degraded-status]
dependency_graph:
  requires: []
  provides:
    - config.HEALTH_STRICT_STATUS
    - config.DB_COMMAND_TIMEOUT_SECONDS
    - config.INIT_WATCHDOG_TIMEOUT_SECONDS
    - config.SYNC_TIMEOUT_SECONDS
    - config.TASK_ERROR_CHANNEL_COOLDOWN_SECONDS
    - config.YTDLP_RETRY_BACKOFF_SECONDS
    - config.YTDLP_MAX_QUICK_RETRIES
    - gather_bot_metrics MusicCog degraded reason
    - /health HTTP 503 on degraded (strict mode)
    - asyncio.TimeoutError personality handler in /leaderboard and /stats
  affects:
    - bot.py health handler
    - cogs/ops.py gather_bot_metrics
    - cogs/ops.py /leaderboard and /stats commands
    - asyncpg pool create_pool command_timeout
tech_stack:
  added: []
  patterns:
    - HEALTH_STRICT_STATUS env-derived bool (matching DEXTER_CHANNEL_ID pattern)
    - asyncio.TimeoutError caught before generic Exception in DB handlers (Pitfall 6)
    - getattr(bot, "_ready_done", False) guard for MusicCog degraded check (Pitfall 3)
    - config.DB_COMMAND_TIMEOUT_SECONDS replacing hardcoded pool kwarg
key_files:
  created: []
  modified:
    - config.py (Phase 9 block — seven constants)
    - bot.py (health handler status code + config-driven pool timeout)
    - cogs/ops.py (MusicCog degraded check + asyncio import + TimeoutError handlers)
    - tests/test_config.py (Phase 9 constant assertions)
    - tests/test_health_endpoint.py (MusicCog-missing, startup-no-false-degraded, 503/200 tests)
decisions:
  - "HEALTH_STRICT_STATUS defaults true via env-derived bool (not plain constant) so Koyeb legacy deployments can opt out without code change"
  - "MusicCog degraded check guarded by _ready_done to prevent false-degraded during startup (Pitfall 3)"
  - "asyncio.TimeoutError caught before Exception in /leaderboard and /stats — asyncpg client-side timeout raises TimeoutError not QueryCanceledError (Pitfall 6)"
  - "All seven Phase 9 constants defined in plan 01 so Wave 2 plans (09-02/09-03/09-04) can read them without editing config.py"
metrics:
  duration_seconds: 613
  completed_date: "2026-06-26"
  tasks_completed: 3
  tasks_total: 3
  files_changed: 5
---

# Phase 9 Plan 01: Reliability Foundation Summary

Phase 9 wave-1 foundation: seven config constants for the full hardening phase, a truthful `/health` endpoint returning HTTP 503 on degraded state (with a legacy always-200 escape hatch via `HEALTH_STRICT_STATUS=false`), and a config-driven DB query timeout floor with personality-flavored error messages in `/leaderboard` and `/stats`.

## What Was Built

### Task 1 — Phase 9 config block (config.py)

Added a `# --- Phase 9: Reliability & Ops Hardening ---` block after the Phase 8 `LEADERBOARD_TOP_N` line. Seven constants:

- `HEALTH_STRICT_STATUS` — env-derived bool (default `true`), drives 503 vs 200 in health handler
- `DB_COMMAND_TIMEOUT_SECONDS = 30` — replaces hardcoded `30` in `bot.py` `create_pool`
- `INIT_WATCHDOG_TIMEOUT_SECONDS = 120` — consumed by 09-03 `asyncio.wait_for(_initialize_once())`
- `SYNC_TIMEOUT_SECONDS = 30` — consumed by 09-03 `asyncio.wait_for(bot.tree.sync())`
- `TASK_ERROR_CHANNEL_COOLDOWN_SECONDS = 300` — consumed by 09-02 and 09-03 done-callback dedup
- `YTDLP_RETRY_BACKOFF_SECONDS = 1.0` — consumed by 09-04 search/extract retry
- `YTDLP_MAX_QUICK_RETRIES = 2` — consumed by 09-04 search/extract retry

Extended `tests/test_config.py` with 8 new assertions (class + flat-name aliases) covering default types, default values, env override, and K-04 unchanged guard.

### Task 2 — Truthful /health (REL-01)

**`cogs/ops.py` `gather_bot_metrics`:** Added MusicCog-load degraded check immediately after the gateway check. Guarded by `getattr(bot, "_ready_done", False)` so the check only fires post-init — prevents false-degraded alerts during startup when MusicCog is legitimately absent (Pitfall 3).

**`bot.py` `health()` handler:** Replaced the always-200 `_aio_web.Response` (D-28 Koyeb workaround) with a configurable status code:
- `reasons` non-empty + `HEALTH_STRICT_STATUS=True` → `status=503`
- `reasons` non-empty + `HEALTH_STRICT_STATUS=False` → `status=200` (legacy escape hatch)
- `reasons` empty → `status=200`

Kept D-27 comment (body exposes only generic reason strings, no guild/shard/pool internals).

**`tests/test_health_endpoint.py`:** Added four new test cases:
- `test_musiccog_missing_post_init` — `_ready_done=True`, empty cogs → `"MusicCog not loaded"` present
- `test_startup_no_false_degraded` — `_ready_done=False`, empty cogs → `"MusicCog not loaded"` absent
- `test_status_503_strict_mode` — strict + degraded → `status=503`
- `test_status_200_legacy_mode` — `HEALTH_STRICT_STATUS=False` + degraded → `status=200`

Updated `_make_fake_bot` helper to accept `ready_done` and `music_cog_loaded` params.

### Task 3 — Config-driven DB timeout + personality catch (REL-05)

**`bot.py`:** `command_timeout=30` → `command_timeout=config.DB_COMMAND_TIMEOUT_SECONDS` (single kwarg change; all K-04 kwargs — `ssl='require'`, `statement_cache_size`, `max_inactive_connection_lifetime` — byte-identical).

**`cogs/ops.py`:** Added `import asyncio`. In both `/leaderboard` and `/stats` command handlers, added `except asyncio.TimeoutError:` branch positioned BEFORE `except Exception:`:
- `/leaderboard` timeout message: `"database is being slow. try again in a bit."`
- `/stats` timeout message: `"stats are taking too long. try again in a bit."`
- Both `ephemeral=True` matching existing handler style
- Both log at `warning` level with command name only (T-09-02: no exc interpolation, no SQL, no DSN)

## Verification

- `python -m pytest tests/test_config.py -q` — 18 passed
- `python -m pytest tests/test_health_endpoint.py -q` — 7 passed
- `python -m pytest tests/ -q -k "not integration"` — 328 passed, 64 skipped
- `python -c "import config, ast; ast.parse(open('bot.py', encoding='utf-8').read())"` — exits 0
- All 7 Phase 9 constants verified via `-c "import config; assert ..."` — exits 0
- Env override `HEALTH_STRICT_STATUS=false` verified — exits 0

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — no stubs or placeholder data introduced.

## Threat Flags

No new threat surface beyond what the plan's threat model covers. The `/health` degraded body is limited to generic reason strings (D-27 preserved, enforced by existing test assertions). `asyncio.TimeoutError` messages are static strings with no interpolated data (T-09-02).

## Self-Check: PASSED

Files verified:
- `config.py` — HEALTH_STRICT_STATUS block present, all 7 constants confirmed
- `bot.py` — `HEALTH_STRICT_STATUS` present in health handler, `DB_COMMAND_TIMEOUT_SECONDS` in create_pool
- `cogs/ops.py` — `import asyncio` present, MusicCog check present, TimeoutError handlers present in both commands
- `tests/test_config.py` — Phase 9 assertions present and passing
- `tests/test_health_endpoint.py` — 4 new test cases present and passing

Commits verified:
- `18806e7` feat(09-01): add Phase 9 reliability config block
- `b7aa948` feat(09-01): truthful /health — 503 on degraded + MusicCog load check (REL-01)
- `c136a8e` feat(09-01): config-driven DB timeout + personality catch in /leaderboard and /stats (REL-05)
