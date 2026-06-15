---
phase: 05-ship-it-live
reviewed: 2026-06-15T00:00:00Z
depth: deep
files_reviewed: 6
files_reviewed_list:
  - config.py
  - bot.py
  - utils/logger.py
  - requirements.txt
  - Dockerfile
  - tests/test_config.py
findings:
  critical: 0
  warning: 3
  info: 6
  total: 9
status: issues_found
---

# Phase 5: Code Review Report (Koyeb + Neon Re-target)

**Reviewed:** 2026-06-15
**Depth:** deep
**Files Reviewed:** 6
**Diff base:** `fb32826~1..HEAD`
**Status:** issues_found (0 critical, 3 warnings, 6 info — no blockers)

---

## Summary

Phase 5's net-new application code covers four areas: (1) `sanitize_database_url` pure function and Neon pool constants in `config.py`, (2) the tuned `asyncpg.create_pool()` call and `_run_health_server()` aiohttp coroutine in `bot.py`, (3) `StreamHandler(sys.stdout)` in `utils/logger.py`, and (4) dependency floor pins in `requirements.txt`.

The core correctness story is sound: the Neon-required parameters (`ssl='require'`, `max_inactive_connection_lifetime=240`, `statement_cache_size=0`) are all wired via config constants; `sanitize_database_url` correctly strips the query string for the documented Neon use cases; and the health endpoint binds to `0.0.0.0:8000`, returns only `{"status":"ok"}`, and exposes no internal state.

Three warnings were found, all in `bot.py`'s `_run_health_server()` task launch pattern. No critical or blocking issues were found. The advisory note states these findings are non-blocking for the phase.

---

## Warnings

### WR-01: Health server task exception silently swallowed — startup failure goes unlogged at ERROR level

**File:** `bot.py:320`
**Issue:** `asyncio.ensure_future(_run_health_server())` returns a `Task` object that is immediately discarded. If `runner.setup()` or `site.start()` raises (e.g., `OSError: [Errno 98] Address already in use`, permission error on port 8000, or an aiohttp internal error), the exception is stored on the Task but never retrieved. Python 3.12 will emit an `asyncio` warning to stderr ("Task exception was never retrieved") — but this warning goes to the *logging* stderr stream, not to Koyeb's structured log viewer via the `log` object. The `_initialize_once` call continues as though the health endpoint started successfully, and the Koyeb health check then times out, causing a deployment failure with no clear cause in bot logs.

**Fix:** Store the task and add an `add_done_callback` that logs any exception through the bot's logger:
```python
_health_task = asyncio.ensure_future(_run_health_server())
_health_task.add_done_callback(
    lambda t: log.error("Health server task failed: %s", t.exception())
    if not t.cancelled() and t.exception() is not None else None
)
log.info("Health server task scheduled")
```

Or, simpler: use `asyncio.create_task` (preferred in Python 3.7+) and store the reference on `bot` so it is not garbage-collected prematurely:
```python
bot._health_task = asyncio.create_task(_run_health_server(), name="health-server")
bot._health_task.add_done_callback(
    lambda t: log.error("Health server crashed: %s", t.exception())
    if not t.cancelled() and t.exception() is not None else None
)
```

---

### WR-02: Double-bind port conflict on _initialize_once retry produces confusing unhandled exception

**File:** `bot.py:320` and `bot.py:225–260`
**Issue:** `asyncio.ensure_future(_run_health_server())` is called inside `_initialize_once()`. The retry guard in `on_ready` resets `bot._ready_done = False` on failure, so the next `on_ready` event re-enters `_initialize_once()`. If the first `_initialize_once()` call reaches the `ensure_future` line (health server started, port 8000 bound) and then fails on a *later* step — specifically `await restore_queues(bot)` (which can raise if the Neon pool is degraded) — the `on_ready` exception handler cleans up the pool but does **not** cancel the running health server task. On the next `on_ready`, a second `_run_health_server()` task is launched and fails immediately with `OSError: [Errno 98] Address already in use`. This unhandled exception goes to the discarded Task, producing a Python warning. The first health server task continues serving port 8000 correctly, so the endpoint is not actually broken — but the error log is misleading and makes the failure hard to diagnose.

This scenario is triggered by: DB pool creation succeeds → health server task starts → `restore_queues` fails. Under a Neon cold-start delay or transient Neon error, `restore_queues` could fail on a fresh Koyeb deploy.

**Fix (preferred):** Track a module-level flag so the health server is launched only once, regardless of how many times `_initialize_once` runs:
```python
_health_server_started = False  # module level

# inside _initialize_once, replace the ensure_future block:
global _health_server_started
if not _health_server_started:
    _health_server_started = True
    bot._health_task = asyncio.create_task(_run_health_server(), name="health-server")
    log.info("Health server task scheduled")
```

**Fix (minimal):** Catch the `OSError` inside `_run_health_server()` at startup and log a clear message rather than letting it propagate as an unhandled Task exception.

---

### WR-03: AppRunner and TCPSite not cleaned up on task cancellation

**File:** `bot.py:181–204`
**Issue:** `_run_health_server()` uses `await asyncio.Event().wait()` as a perpetual sleep. When the Task is cancelled (e.g., via `bot.close()` or a process signal), `CancelledError` is raised from `Event.wait()` and propagates out of the coroutine. `runner.cleanup()` is never called. For the Koyeb deployment pattern (SIGTERM kills the process), OS-level cleanup reclaims the port on exit — so this is not a production correctness issue. However, it becomes a real problem in any scenario where the bot restarts *within the same process* (not applicable now, but the pattern is a latent defect), and it is inconsistent with aiohttp's documented cleanup contract.

**Fix:** Wrap the keepalive in a `try/finally`:
```python
await runner.setup()
site = _aio_web.TCPSite(runner, '0.0.0.0', 8000)
await site.start()
log.info("Health endpoint listening on 0.0.0.0:8000/health")
try:
    await asyncio.Event().wait()
finally:
    await runner.cleanup()
    log.info("Health endpoint shut down")
```

---

## Info

### IN-01: Misleading comment — health endpoint comes up *after* Discord connects, not before

**File:** `bot.py:317–319`
**Issue:** The comment reads: `# No before_loop guard — endpoint must be up before Discord connects so Koyeb's health check passes on first deploy.` This is factually incorrect: `_initialize_once()` is called from `on_ready`, which fires *after* the Discord gateway connection is established. The endpoint comes up after Discord is already connected. The intent is correct (no `wait_until_ready` guard, so the endpoint starts as early as possible), but the comment misstates the timing.

**Fix:** Update the comment to reflect reality:
```python
# K-02: No before_loop guard — endpoint starts during on_ready (Discord already
# connected at this point) and must be reachable before Koyeb's health check
# deadline. ensure_future lets it start concurrently without blocking cog init.
```

---

### IN-02: Logger docstring says "stderr" but code uses stdout

**File:** `utils/logger.py:17`
**Issue:** The `setup_logger` docstring reads `"Also logs to console (stderr) during development."` The K-16 change switched the handler to `sys.stdout`, making the docstring stale. Note: the change itself is correct — Python's `logging.StreamHandler.emit()` calls `self.flush()` after each record, so stdout buffering is not an issue regardless of `PYTHONUNBUFFERED`.

**Fix:** Update the docstring:
```python
- Logs to console (stdout) so Koyeb/Docker log viewers capture output (K-16).
```

---

### IN-03: `import re` inside function body — performance micro-waste on every call

**File:** `config.py:118`
**Issue:** `import re` is placed inside `sanitize_database_url()` rather than at module level. Python caches module imports in `sys.modules` so the lookup on repeated calls is O(1) dict access — not a true performance issue. However, the rationale in the plan ("minimal-import convention from database.py") applies to `database.py`'s pure helpers which avoid heavy-ish transitive imports. `re` is a stdlib module always loaded as a transitive dependency by dozens of other modules; putting it inside the function buys nothing and misleads readers into thinking `re` is an expensive or unusual import.

**Fix:** Move to module-level imports:
```python
import re  # at top of config.py

def sanitize_database_url(dsn: str) -> str:
    ...
    return re.sub(r'\?.*$', '', dsn)
```

---

### IN-04: `sanitize_database_url` strips on first `?` — would corrupt auth info if password contained a literal `?`

**File:** `config.py:119`
**Issue:** `re.sub(r'\?.*$', '', dsn)` strips everything from the first `?` to the end of the string. If a PostgreSQL password contained a literal, unencoded `?` character (e.g., `postgresql://user:p?ssw0rd@host/db?sslmode=require`), the sanitizer would strip `?ssw0rd@host/db?sslmode=require`, producing a broken DSN. In practice this cannot happen with Neon-generated connection strings: Neon URL-encodes special characters in passwords (a literal `?` would appear as `%3F`), and the plan's research acknowledges this risk. Documented here per the focus areas request.

**Fix (if desired):** Use `urllib.parse.urlsplit`/`urlunsplit` to surgically remove only the query component:
```python
from urllib.parse import urlsplit, urlunsplit

def sanitize_database_url(dsn: str) -> str:
    """..."""
    parts = urlsplit(dsn)
    return urlunsplit(parts._replace(query='', fragment=''))
```
This is immune to `?` in the password and also strips fragments. For the current Neon use case the regex is safe; upgrade if the credential rotation policy ever permits special characters.

---

### IN-05: `pytest` imported but not used in `tests/test_config.py`

**File:** `tests/test_config.py:7`
**Issue:** `import pytest` appears at line 7 but no `pytest.*` symbols are referenced anywhere in the file. There are no `pytest.mark.*` decorators, no `pytest.raises`, no fixtures, and no `pytest.param` usage. pytest discovers and runs the tests correctly without this import being used. Harmless (pytest is already a test dependency), but a lint tool (`ruff`, `flake8`) will flag `F401: 'pytest' imported but unused`.

**Fix:** Remove the unused import, or keep it if `pytest.mark` decorators are planned for future parameterisation:
```python
# Remove line 7: import pytest
```

---

### IN-06: `command_timeout=30` is a hardcoded magic number in `create_pool`

**File:** `bot.py:257`
**Issue:** The new Neon pool parameters are all wired through named config constants (`config.DB_MAX_INACTIVE_CONN_LIFETIME`, `config.DB_STATEMENT_CACHE_SIZE`, `config.DB_POOL_MAX`, `config.DB_POOL_MIN`), but `command_timeout=30` remains a hardcoded literal. This is a pre-existing inconsistency that the phase 5 changes did not introduce, but they highlight it by contrast: the surrounding new params all use constants. A future tuning of the command timeout (e.g., for Neon cold-start headroom) would require finding this magic number in `bot.py` rather than changing `config.py`.

**Fix:** Add `DB_COMMAND_TIMEOUT = 30` to the Phase 5 Neon tuning block in `config.py` and reference it:
```python
# config.py
DB_COMMAND_TIMEOUT = 30  # seconds; 30s is ample for Neon cold-start (~800ms) (K-04)

# bot.py
command_timeout=config.DB_COMMAND_TIMEOUT,
```

---

## Scope-Limited Checks (docs/infra — light pass)

**Dockerfile (`Dockerfile`):** Comment-only change. `FROM python:3.11-slim-bookworm` unchanged. No secrets baked into layers. Oracle/arm64 references removed. No issues.

**`.env.example`:** No real credentials present. Placeholder values only. DATABASE_URL comment correctly distinguishes local vs Neon. HEALTHCHECK_URL example uses `https://hc-ping.com/your-uuid-here` (non-functional placeholder). No issues.

**`docs/DEPLOY-KOYEB.md`:** Not reviewed in detail (out of primary scope). Light glance: no real tokens or credentials detected; `<service>` placeholder used consistently.

**`scripts/archive/`:** Oracle ops scripts moved (not deleted). Disposition consistent with K-08/K-09/K-11.

---

## Key Confirmations (focus areas explicitly checked)

| Check | Result |
|-------|--------|
| `sanitize_database_url` strips Neon query string in all 3 test cases | PASS |
| `sanitize_database_url` is a no-op when no query string present | PASS |
| `re.sub(r'\?.*$', ...)` strips by first `?` — order-independent for query params | PASS (works because entire query string removed) |
| `ssl='require'` passed explicitly (not via DSN), wired to... | PASS — `ssl='require'` literal in `create_pool` |
| `statement_cache_size=config.DB_STATEMENT_CACHE_SIZE` (0) wired | PASS |
| `max_inactive_connection_lifetime=config.DB_MAX_INACTIVE_CONN_LIFETIME` (240) wired | PASS |
| `max_size=config.DB_POOL_MAX` (5) wired | PASS |
| Health endpoint binds `'0.0.0.0'` not `'localhost'` | PASS |
| Health response is exactly `'{"status":"ok"}'` with no internal state | PASS |
| `asyncio.Event().wait()` used as keepalive — cancellable via `CancelledError` | PASS (cancellable; `runner.cleanup()` missing, see WR-03) |
| DATABASE_URL / DSN never logged | PASS — existing T-04-05 SECURITY comment at `bot.py:251` preserved |
| `ssl='require'` with local postgres:16-alpine (break-glass path) | SAFE — asyncpg's `sslmode=require` sets `verify_mode=CERT_NONE` and `check_hostname=False`; postgres:16-alpine generates a self-signed cert by default (`ssl=on`), so SSLRequest receives `b'S'` and the connection succeeds |
| DB_POOL_MAX 10→5 regression risk | LOW — `min_size=2`, `max_size=5` is adequate for a single-community bot; reduces Neon connection count as intended |

---

_Reviewed: 2026-06-15_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
