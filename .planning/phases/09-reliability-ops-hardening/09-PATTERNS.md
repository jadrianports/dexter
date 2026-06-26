# Phase 9: Reliability & Ops Hardening - Pattern Map

**Mapped:** 2026-06-26
**Files analyzed:** 7 existing files + 1 new (utils/tasks.py)
**Analogs found:** 7 / 8 (utils/tasks.py has partial analog in existing _on_health_server_done)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `config.py` | config | — | `config.py` itself (additive) | exact |
| `bot.py` | startup/health | request-response + event-driven | `bot.py` lines 207–228 (health handler) + lines 265–283 (on_ready guard) | exact |
| `cogs/ops.py` | service/utility | request-response | `cogs/ops.py` lines 94–109 (existing degraded-reasons producer) | exact |
| `cogs/music.py` | controller | event-driven | `bot.py` lines 373–383 (`_on_health_server_done` done-callback) | role-match |
| `cogs/events.py` | controller | event-driven | `bot.py` lines 484–619 (`@tasks.loop` blocks) | role-match |
| `services/youtube.py` | service | request-response | `services/youtube.py` lines 203–227 (`download()` self-heal retry) | exact |
| `database.py` | config (pool kwarg) | — | `bot.py` lines 297–305 (pool creation site) | exact |
| `utils/tasks.py` (NEW) | utility | event-driven | `bot.py` lines 373–383 (`_on_health_server_done` pattern) | role-match |

---

## Pattern Assignments

### `config.py` (config, additive)

**Analog:** `config.py` existing Phase 4/5/6 constant blocks (lines 88–135)

**Existing constant block pattern** (lines 102–104):
```python
# --- Phase 5: Neon pool tuning (K-04) ---
DB_MAX_INACTIVE_CONN_LIFETIME = 240      # recycle before Neon 5-min scale-to-zero (K-04)
DB_STATEMENT_CACHE_SIZE = 0             # disable prepared stmts for PgBouncer tx-mode (K-04)
```

**Add a new Phase 9 block after the Phase 8 block (after line 139). Pattern to follow:**
```python
# --- Phase 9: Reliability & Ops Hardening ---
HEALTH_STRICT_STATUS: bool = os.getenv("HEALTH_STRICT_STATUS", "true").lower() != "false"
DB_COMMAND_TIMEOUT_SECONDS: int = 30        # replaces hardcoded 30 in bot.py line 301
INIT_WATCHDOG_TIMEOUT_SECONDS: int = 120    # asyncio.wait_for wrap on _initialize_once
SYNC_TIMEOUT_SECONDS: int = 30             # asyncio.wait_for wrap on bot.tree.sync()
TASK_ERROR_CHANNEL_COOLDOWN_SECONDS: int = 300   # dedup window per (task_name, exc_type)
YTDLP_RETRY_BACKOFF_SECONDS: float = 1.0   # per-attempt sleep in search/extract retry
YTDLP_MAX_QUICK_RETRIES: int = 2           # attempts before falling through to update path
```

**Key note:** `HEALTH_STRICT_STATUS` is a bool derived from env, matching the `DEXTER_CHANNEL_ID` pattern at line 57:
```python
DEXTER_CHANNEL_ID = int(os.getenv("DEXTER_CHANNEL_ID") or "0") or None
```

---

### `bot.py` — health handler (request-response, REL-01)

**Analog:** `bot.py` lines 207–228 (the existing `health()` handler to be modified)

**Existing pattern** (lines 218–228) — the D-28 always-200 block to replace:
```python
# D-28: always HTTP 200 — non-200 causes Koyeb kill-loop and Neon 5-min restart cascade.
# D-27: body exposes ONLY status + generic reason strings (no guild/shard/pool internals).
if reasons:
    body = json.dumps({"status": "degraded", "reasons": reasons})
else:
    body = '{"status":"ok"}'

return _aio_web.Response(
    text=body,
    content_type='application/json',
)
```

**Replace with** (D-01: configurable status code):
```python
# D-01: HEALTH_STRICT_STATUS (default True) → 503 when degraded; False → legacy 200.
# D-27: body exposes ONLY status + generic reason strings (no guild/shard/pool internals).
if reasons:
    body = json.dumps({"status": "degraded", "reasons": reasons})
    status = 503 if getattr(config, "HEALTH_STRICT_STATUS", True) else 200
else:
    body = '{"status":"ok"}'
    status = 200

return _aio_web.Response(
    text=body,
    content_type='application/json',
    status=status,
)
```

---

### `bot.py` — on_ready / _initialize_once watchdog (event-driven, REL-04)

**Analog:** `bot.py` lines 254–283 (existing on_ready guard — the exact code to wrap)

**Existing pattern** (lines 265–283):
```python
if getattr(bot, "_ready_done", False) or getattr(bot, "_ready_initializing", False):
    return
bot._ready_initializing = True
try:
    await _initialize_once()
    bot._ready_done = True
except Exception:
    log.exception("on_ready init failed; cleaning up to retry on next ready event")
    _pool = getattr(bot, "pool", None)
    if _pool is not None:
        try:
            await _pool.close()
        except Exception:
            pass
        if hasattr(bot, "pool"):
            del bot.pool
    return
finally:
    bot._ready_initializing = False
```

**Replace bare `await _initialize_once()` with** (D-06):
```python
bot._ready_initializing = True
try:
    await asyncio.wait_for(
        _initialize_once(),
        timeout=config.INIT_WATCHDOG_TIMEOUT_SECONDS,
    )
    bot._ready_done = True
except asyncio.TimeoutError:
    log.error(
        "on_ready init hung for %ss; cleaning up pool to retry on next READY event",
        config.INIT_WATCHDOG_TIMEOUT_SECONDS,
    )
    _pool = getattr(bot, "pool", None)
    if _pool is not None:
        try:
            await _pool.close()
        except Exception:
            pass
        if hasattr(bot, "pool"):
            del bot.pool
    return
except Exception:
    log.exception("on_ready init failed; cleaning up to retry on next ready event")
    _pool = getattr(bot, "pool", None)
    if _pool is not None:
        try:
            await _pool.close()
        except Exception:
            pass
        if hasattr(bot, "pool"):
            del bot.pool
    return
finally:
    bot._ready_initializing = False  # now resets on hang, exception, AND success
```

**Critical:** `asyncio.TimeoutError` must be caught BEFORE the generic `except Exception` (it IS a subclass of Exception in Python 3.11+). The `finally` clause already handles `_ready_initializing = False` correctly — the bug REL-04 fixes is that a bare coroutine hang never reaches `finally` at all; `wait_for` converts the hang to `TimeoutError` so `finally` runs.

---

### `bot.py` — tree.sync with timeout + retry (startup, REL-03)

**Analog:** `bot.py` lines 461–478 (`sync_commands` slash command — same `bot.tree.sync()` call)

**Existing bare sync call in `_initialize_once`** (line 472 area — add `_sync_with_timeout` wrapper):

The `first_run` path also has bare syncs at lines 638 and 641. Same wrapper applies.

**Module-level guard to add** (mirrors `_health_server_task` guard at line 196):
```python
_sync_retry_active: bool = False   # guard: only one background retry chain runs at a time
```

**Replace bare `await bot.tree.sync()` calls in `_initialize_once` with:**
```python
try:
    synced = await asyncio.wait_for(bot.tree.sync(), timeout=config.SYNC_TIMEOUT_SECONDS)
    log.info("Synced %d commands globally", len(synced))
except Exception as exc:
    log.warning(
        "Command sync failed (%s); coming online with existing commands; retrying in background",
        exc,
    )
    global _sync_retry_active
    if not _sync_retry_active:
        _sync_retry_active = True
        asyncio.create_task(_background_sync_retry(), name="sync-retry")
```

**Background retry helper** (modeled on `_post_startup_messages` best-effort pattern, lines 400–417):
```python
async def _background_sync_retry() -> None:
    global _sync_retry_active
    for attempt in range(1, 4):  # 3 retries at 60s, 120s, 180s
        await asyncio.sleep(60 * attempt)
        try:
            synced = await asyncio.wait_for(bot.tree.sync(), timeout=config.SYNC_TIMEOUT_SECONDS)
            log.info("Command sync succeeded on retry attempt %d (%d commands)", attempt, len(synced))
            _sync_retry_active = False
            return
        except Exception as exc:
            log.warning("Command sync retry %d/3 failed: %s", attempt, exc)
    log.error("Command sync failed after all retry attempts; slash commands may be stale")
    _sync_retry_active = False
```

---

### `bot.py` — pool creation (REL-05)

**Analog:** `bot.py` lines 297–305 (the pool creation block to modify)

**Existing** (line 301):
```python
bot.pool = await asyncpg.create_pool(
    dsn=config.sanitize_database_url(config.DATABASE_URL),
    min_size=config.DB_POOL_MIN,
    max_size=config.DB_POOL_MAX,
    command_timeout=30,           # ← hardcoded; replace with config constant
    ssl='require',
    max_inactive_connection_lifetime=config.DB_MAX_INACTIVE_CONN_LIFETIME,
    statement_cache_size=config.DB_STATEMENT_CACHE_SIZE,
)
```

**Change only line 301** (additive, no other pool kwarg changes — Neon K-04 tuning must not be disturbed):
```python
    command_timeout=config.DB_COMMAND_TIMEOUT_SECONDS,
```

---

### `bot.py` — @tasks.loop error handlers (REL-02, tasks.loop path)

**Analog:** `bot.py` lines 484–619 (four `@tasks.loop` decorated functions: `idle_check`, `cache_cleanup`, `ytdlp_update`, `status_rotation`)

**Existing `before_loop` pattern** (lines 560–562):
```python
@idle_check.before_loop
async def before_idle_check():
    await bot.wait_until_ready()
```

**Add `@loop.error` handlers after each `@loop.before_loop` block, following the same naming convention:**
```python
@idle_check.error
async def on_idle_check_error(error: Exception) -> None:
    log.error("idle_check task error: %s", error, exc_info=error)
    # Rate-limited channel post (mirrors _UPDATE_THROTTLE_SECONDS pattern in youtube.py)
    await _post_loop_error("idle_check", error)

# Same pattern for cache_cleanup, ytdlp_update, status_rotation
```

**`_post_loop_error` helper** (modeled on `on_app_command_error` embed at lines 438–445):
```python
_last_loop_error_post: dict[str, float] = {}

async def _post_loop_error(loop_name: str, error: Exception) -> None:
    import time
    key = f"{loop_name}:{type(error).__name__}"
    now = time.monotonic()
    if now - _last_loop_error_post.get(key, 0.0) < config.TASK_ERROR_CHANNEL_COOLDOWN_SECONDS:
        return
    _last_loop_error_post[key] = now
    if not hasattr(bot, "log_to_discord"):
        return
    embed = discord.Embed(
        title=f"Background Loop Error: {loop_name}",
        description=f"{type(error).__name__}: {error}",
        color=0xFF6600,
    )
    try:
        await bot.log_to_discord(embed)
    except Exception:
        pass
```

---

### `cogs/ops.py` — gather_bot_metrics MusicCog check (REL-01, D-02)

**Analog:** `cogs/ops.py` lines 94–109 (existing DB + gateway degraded-reasons producer)

**Existing gateway check pattern** (lines 107–109) — copy this structure:
```python
# Gateway check
if not metrics["gateway_ready"]:
    metrics["degraded_reasons"].append("discord gateway not ready")
```

**Add MusicCog check immediately after gateway check** (lines ~109–111):
```python
# MusicCog load check (REL-01 / D-02)
# Guard: only report missing as degraded after full init (_ready_done).
# During startup, MusicCog is absent by design — cogs load after pool/services.
if getattr(bot, "_ready_done", False):
    if bot.cogs.get("MusicCog") is None:
        metrics["degraded_reasons"].append("MusicCog not loaded")
```

**Key note:** The `bot.cogs.get("MusicCog")` call at line 80 already exists for queue counting — the pattern is proven and safe to reuse for the degraded check.

---

### `cogs/music.py` — done-callbacks on fire-and-forget tasks (REL-02, D-03/D-04)

**Analog:** `bot.py` lines 373–383 (`_on_health_server_done` — the only existing done-callback in the codebase)

**Existing done-callback pattern** (lines 373–383):
```python
def _on_health_server_done(task) -> None:
    # WR-01: surface a startup failure to the error log
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.error("Health server task failed: %s", exc, exc_info=exc)

_health_server_task.add_done_callback(_on_health_server_done)
```

**Target call sites in music.py** (lines 621, 628, 763):
```python
# Line 621 — auto lyrics
asyncio.create_task(self._post_auto_lyrics(guild, track))
# Line 628 — prefetch
asyncio.create_task(self._prefetch_next_track(guild, next_tracks[0], current_gen))
# Line 763 — auto queue
asyncio.create_task(ai_cog.try_auto_queue(guild))
```

**Replace with** (import `make_task` from `utils.tasks`):
```python
# Line 621
make_task(self._post_auto_lyrics(guild, track), name="auto-lyrics", bot=self.bot)
# Line 628
make_task(self._prefetch_next_track(guild, next_tracks[0], current_gen), name="prefetch", bot=self.bot)
# Line 763
make_task(ai_cog.try_auto_queue(guild), name="auto-queue", bot=self.bot)
```

**DO NOT add done-callbacks to:**
- Line 888: `asyncio.create_task(self._play_track(guild, next_track))` — has full internal handling
- Line 1480: `asyncio.create_task(self._play_track(interaction.guild, next_track))` — same

---

### `cogs/events.py` — done-callbacks (REL-02)

**Analog:** same `_on_health_server_done` pattern as music.py above.

Grep for `create_task` in events.py returned no matches — events.py currently has no `asyncio.create_task` calls. The `@tasks.loop` error handling for events.py ambient loops (if any) is handled via the bot.py `@loop.error` pattern above. No changes needed here unless a future audit finds create_task calls.

---

### `services/youtube.py` — bounded retry in async_search / async_extract (REL-06)

**Analog:** `services/youtube.py` lines 203–227 (`download()` self-heal retry — the exact pattern to replicate)

**Existing retry pattern in `download()`** (lines 203–227):
```python
except Exception as e:
    log.error(f"Download failed for {video_id}: {e}")
    # Self-heal: yt-dlp breaks often. Update (throttled) and retry once.
    global _last_ytdlp_update
    now = time.monotonic()
    if now - _last_ytdlp_update < _UPDATE_THROTTLE_SECONDS:
        return None
    _last_ytdlp_update = now
    log.warning(f"Attempting yt-dlp self-update after download failure for {video_id}")
    if not update_ytdlp():
        return None
    try:
        ...  # retry download
    except Exception as retry_error:
        log.error(f"Retry after update failed for {video_id}: {retry_error}")
    return None
```

**Existing async wrappers to replace** (lines 229–237):
```python
async def async_search(self, query: str, count: int | None = None) -> list[dict]:
    """Run search in a thread pool to avoid blocking the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(self.search, query, count))

async def async_extract(self, url: str) -> dict:
    """Run extract in a thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, self.extract, url)
```

**Add above `async_search`** (permanent-failure guard, Pitfall 7):
```python
from yt_dlp.utils import ExtractorError as _ExtractorError

def _is_transient_ytdlp_error(exc: Exception) -> bool:
    """Return True if the error is plausibly transient.

    ExtractorError.expected=True means content unavailable (permanent) — don't retry.
    All other errors (network, unexpected extractor failures) are transient candidates.
    """
    if isinstance(exc, _ExtractorError) and exc.expected:
        return False
    return True
```

**Replace `async_search` with** (D-08 retry loop, mirrors `download()` throttle logic):
```python
async def async_search(self, query: str, count: int | None = None) -> list[dict]:
    """Run search with bounded retry + throttled self-heal (REL-06 / D-08)."""
    loop = asyncio.get_running_loop()
    last_exc: Exception | None = None
    for attempt in range(config.YTDLP_MAX_QUICK_RETRIES + 1):  # 0, 1, 2
        try:
            return await loop.run_in_executor(
                None, functools.partial(self.search, query, count)
            )
        except Exception as exc:
            last_exc = exc
            if not _is_transient_ytdlp_error(exc):
                raise  # permanent (video unavailable etc.) — don't retry
            if attempt < config.YTDLP_MAX_QUICK_RETRIES:
                log.warning(
                    "search attempt %d/%d failed (transient): %s",
                    attempt + 1, config.YTDLP_MAX_QUICK_RETRIES + 1, exc,
                )
                await asyncio.sleep(config.YTDLP_RETRY_BACKOFF_SECONDS * (attempt + 1))
            else:
                # All quick retries exhausted — throttled update + final attempt
                global _last_ytdlp_update
                now = time.monotonic()
                if now - _last_ytdlp_update >= _UPDATE_THROTTLE_SECONDS:
                    log.warning("search exhausted quick retries; attempting yt-dlp update")
                    await loop.run_in_executor(None, update_ytdlp)
                try:
                    return await loop.run_in_executor(
                        None, functools.partial(self.search, query, count)
                    )
                except Exception as final_exc:
                    log.error("search failed after update: %s", final_exc)
                    raise
    raise last_exc  # unreachable; satisfies type checker
```

**Replace `async_extract` with identical structure** (substituting `self.extract` for `self.search`).

---

### `utils/tasks.py` (NEW — utility, event-driven, REL-02)

**Analog:** `bot.py` lines 373–383 (`_on_health_server_done` done-callback — the existing pattern to generalize)

**Full file pattern:**
```python
"""Shared fire-and-forget task helper with exception surfacing (REL-02 / D-03/D-04)."""
from __future__ import annotations

import asyncio
import functools
import time
from typing import Any

import discord

import config
from utils.logger import log

# Strong-reference set prevents GC collecting mid-flight tasks (asyncio docs warning)
_background_tasks: set[asyncio.Task] = set()

# Dedup state: mirrors _last_ytdlp_update float pattern in services/youtube.py line 21
_last_task_error_post: dict[str, float] = {}


def make_task(coro, *, name: str | None = None, bot=None) -> asyncio.Task:
    """Create a fire-and-forget task with exception surfacing.

    Done-callback logs exceptions to dexter.log (always) and posts to the Discord
    error channel (rate-limited per TASK_ERROR_CHANNEL_COOLDOWN_SECONDS per error key).
    CancelledError is silently ignored (normal on shutdown/skip/generation-change).
    """
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    task.add_done_callback(functools.partial(_on_task_done, bot=bot))
    return task


def _on_task_done(task: asyncio.Task, *, bot=None) -> None:
    # Pitfall 1: cancelled() MUST be checked before exception() — cancelled tasks
    # raise CancelledError from exception(), not return None.
    if task.cancelled():
        return
    exc = task.exception()
    if exc is None:
        return
    task_name = task.get_name() or "unknown"
    log.error("Background task %r raised: %s", task_name, exc, exc_info=exc)
    if bot is None:
        return
    # Rate-limit channel posts per (task_name, exc_type) — mirrors _UPDATE_THROTTLE_SECONDS
    key = f"{task_name}:{type(exc).__name__}"
    now = time.monotonic()
    if now - _last_task_error_post.get(key, 0.0) < config.TASK_ERROR_CHANNEL_COOLDOWN_SECONDS:
        return
    _last_task_error_post[key] = now
    # done-callbacks are synchronous — must schedule the async channel post
    asyncio.ensure_future(_post_task_error(bot, task_name, exc))


async def _post_task_error(bot: Any, task_name: str, exc: Exception) -> None:
    """Post a task failure embed to the Discord error channel (best-effort)."""
    if not hasattr(bot, "log_to_discord"):
        return
    # Security: task name + exception type/message only — no guild IDs or user data
    embed = discord.Embed(
        title=f"Background Task Error: {task_name}",
        description=f"{type(exc).__name__}: {exc}",
        color=0xFF6600,
    )
    try:
        await bot.log_to_discord(embed)
    except Exception:
        pass  # never let the error reporter crash things
```

**Import in music.py** (add to top-level imports):
```python
from utils.tasks import make_task
```

---

## Shared Patterns

### Error channel posting
**Source:** `bot.py` lines 438–445 (`on_app_command_error` embed builder)
**Apply to:** `utils/tasks.py` `_post_task_error`, `bot.py` `_post_loop_error`
```python
embed = discord.Embed(
    title="...",
    description=f"...",
    color=0xFF6600,  # orange for warnings; 0xFF0000 for critical
)
await bot.log_to_discord(embed)
```

### Throttled rate-limit (dedup) using monotonic float
**Source:** `services/youtube.py` lines 21–22, 207–210
**Apply to:** `utils/tasks.py` `_last_task_error_post`, `bot.py` `_last_loop_error_post`
```python
_last_ytdlp_update: float = 0.0
_UPDATE_THROTTLE_SECONDS: float = 3600.0

now = time.monotonic()
if now - _last_ytdlp_update < _UPDATE_THROTTLE_SECONDS:
    return None
_last_ytdlp_update = now
```

### Pool cleanup in error paths
**Source:** `bot.py` lines 273–281 (existing `on_ready` cleanup — exact structure to reuse for TimeoutError branch)
```python
_pool = getattr(bot, "pool", None)
if _pool is not None:
    try:
        await _pool.close()
    except Exception:
        pass
    if hasattr(bot, "pool"):
        del bot.pool
```

### Function-scope import to avoid circular import
**Source:** `bot.py` lines 212–213 (health handler, comment at line 208–209)
**Apply to:** Keep this pattern whenever touching the health handler or any code that imports from cogs at runtime.
```python
# Import at request time (function-scope) to avoid circular import at module load.
from cogs.ops import gather_bot_metrics
```

### Personality-flavored user-facing error
**Source:** `bot.py` line 449 + `cogs/ops.py` lines 159–163
**Apply to:** `asyncio.TimeoutError` catch in `/leaderboard` and any other DB-heavy handler (REL-05)
```python
except asyncio.TimeoutError:
    await interaction.followup.send(
        "database is being slow. try again in a bit.", ephemeral=True
    )
    return
```

---

## No Analog Found

| File | Role | Reason |
|------|------|--------|
| (none) | — | All Phase 9 patterns have existing analogs in the live codebase |

---

## Metadata

**Analog search scope:** `bot.py`, `cogs/ops.py`, `cogs/music.py`, `cogs/events.py`, `services/youtube.py`, `config.py`, `database.py`
**Files scanned:** 7
**Pattern extraction date:** 2026-06-26
