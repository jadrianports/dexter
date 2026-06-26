# Phase 9: Reliability & Ops Hardening - Research

**Researched:** 2026-06-26
**Domain:** Python asyncio resilience, asyncpg pool tuning, discord.py task lifecycle, yt-dlp error handling
**Confidence:** HIGH (all critical claims grounded in live codebase reads + verified API docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**REL-01 — Truthful `/health` (D-01, D-02)**
- `/health` returns a configurable HTTP status. Add `HEALTH_STRICT_STATUS` (default `true`). When strict + degraded → HTTP 503; healthy → 200; flag `false` → legacy always-200.
- "Critical / degraded" set = MusicCog-failed-to-load + DB-unreachable + gateway-not-ready. AI/Imagine cogs excluded (load conditionally on `GEMINI_API_KEY`).

**REL-02 — Background-task failure visibility (D-03, D-04)**
- Every fire-and-forget task attaches a done-callback that logs to `dexter.log` AND posts to `ERROR_LOG_CHANNEL_ID`.
- Discord channel posting is rate-limited/deduped (mirror `_UPDATE_THROTTLE_SECONDS` pattern). Logs record every occurrence; channel posts are throttled.

**REL-03 / REL-04 — Startup sync + un-wedgeable `on_ready` (D-05, D-06)**
- `bot.tree.sync` wrapped in a timeout. On failure/timeout: log, come online anyway (existing commands keep working), then background-retry sync.
- `_initialize_once()` wrapped in `asyncio.wait_for`. On timeout: log, clean up pool, reset `_ready_initializing` guard, allow next ready event to retry.

**REL-05 — DB query timeout (D-07)**
- Pool-wide default `command_timeout` (cheap floor covering every query). Timeout message is personality-flavored. Per-query overrides allowed on top.

**REL-06 — YouTube search/extract self-heal (D-08)**
- On transient failure: quick bounded retry first (1-2x, short backoff), then — only if still failing — fall back to throttled yt-dlp self-update + retry (reusing existing `download()` tier). Reuse `update_ytdlp()` + `_UPDATE_THROTTLE_SECONDS`.

### Claude's Discretion
- Exact timeout values (sync timeout, `_initialize_once` watchdog, pool `command_timeout`, retry backoff)
- Exact dedup mechanism for D-04 (time window vs error-signature set vs both)
- Whether REL-05 adds per-query timeouts on top of pool default
- Per-task choice of done-callback helper shape for D-03 (shared utility vs inline)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope. Test extraction is Phase 10; RAG memory is Phase 11.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REL-01 | `/health` reports degraded (non-200) when critical cog failed to load or core subsystem is down | D-01/D-02: `HEALTH_STRICT_STATUS` flag + MusicCog-load check added to `gather_bot_metrics` |
| REL-02 | Fire-and-forget tasks attach done-callback for exception logging | D-03/D-04: `_make_task` helper with done-callback + channel dedup |
| REL-03 | Command-tree sync handles failure/timeout without hanging | D-05: `asyncio.wait_for(bot.tree.sync(), timeout=...)` + background retry |
| REL-04 | `on_ready` re-entry guard cannot get permanently stuck | D-06: `asyncio.wait_for(_initialize_once(), timeout=...)` converts hang to TimeoutError |
| REL-05 | Database queries enforce a timeout | D-07: pool `command_timeout` already hardcoded 30s; move to config + catch `asyncio.TimeoutError` in handlers |
| REL-06 | `youtube` search/extract self-heal on transient failure | D-08: retry loop in `async_search`/`async_extract` with `_is_transient` heuristic + update fallback |
</phase_requirements>

---

## Summary

Phase 9 hardens existing v1.1 surfaces without adding features. All six requirements target failure modes that currently produce silent hangs, missing error visibility, or always-green health checks that lie. The work is almost entirely additive — a few config constants, wrapper calls, and callback attachments around code that already exists.

The most important discovery is that **`command_timeout=30` is already hardcoded** in `_initialize_once` (bot.py:300). REL-05 is therefore a narrow scope: move to a config constant, and catch `asyncio.TimeoutError` in cog command handlers to emit a personality message instead of the generic error. No pool plumbing changes needed.

The second discovery is that `_post_auto_lyrics` and the `try_auto_queue` fire-and-forget tasks already have internal `try/except` but do NOT post to the Discord error channel, and `_prefetch_next_track` only logs at `debug` level. REL-02 upgrades their visibility via done-callbacks while leaving the internal swallowing intact (the tasks must not affect playback).

The `_ready_initializing` guard analysis confirms REL-04: the `finally` block in `on_ready` always resets the flag on exceptions, but a true hang (coroutine suspended indefinitely without raising) leaves `finally` unreachable. `asyncio.wait_for` converts any hang into a `TimeoutError`, making `finally` reachable again.

**Primary recommendation:** Implement as five focused edits — `config.py` (constants), `bot.py` (watchdog + health status code), `cogs/ops.py` (MusicCog check), `services/youtube.py` (retry loop), and a shared done-callback helper — rather than as a single large patch.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `/health` HTTP status truthfulness | Bot process / health handler | External monitor (UptimeRobot) | Health handler owns status code; monitor reacts to it |
| Done-callback exception surfacing | Bot process (asyncio task) | Discord error channel | asyncio task lifecycle is in-process; channel is just the notification sink |
| Command-tree sync resilience | Bot startup path | Discord gateway | Sync is a one-shot startup HTTP call; already-registered commands live on Discord's side |
| `on_ready` hang protection | Bot startup path (asyncio.wait_for) | — | Pure asyncio timeout; no external dependency |
| DB query timeout | asyncpg pool (client-side) | Neon serverless Postgres | `command_timeout` is a client-side asyncio mechanism; Neon is unaware of it |
| YouTube search/extract self-heal | Service layer (YouTubeService) | Bot process (thread pool) | yt-dlp runs in executor threads; retry logic belongs in the async wrapper |

---

## Standard Stack

### Core (already present — no new installs)
| Library | Version (in requirements.txt) | Purpose | Role in Phase 9 |
|---------|-------------------------------|---------|-----------------|
| asyncpg | 0.31.0 | PostgreSQL async driver | Pool `command_timeout` kwarg (REL-05) |
| discord.py | ≥2.3 | Discord API wrapper | `CommandTree.sync`, `tasks.loop`, `Task.add_done_callback` (REL-02/03) |
| aiohttp | installed (health server) | HTTP server for `/health` | Status code 503 (REL-01) |
| yt-dlp | latest (daily auto-update) | YouTube download/search | Retry on `async_search`/`async_extract` (REL-06) |

### No new packages are introduced in Phase 9.

**Installation:** None required — all dependencies already installed.

---

## Package Legitimacy Audit

No new packages installed in this phase.

| Package | Registry | Disposition |
|---------|----------|-------------|
| (none) | — | No new installs |

---

## Architecture Patterns

### System Architecture Diagram

```
Discord READY event
        |
        v
 on_ready() guard check
 [_ready_done? _ready_initializing?]
        |
        v (first ready only)
 asyncio.wait_for(
   _initialize_once(),
   timeout=INIT_WATCHDOG_TIMEOUT_SECONDS    ← REL-04: converts hang → TimeoutError
 )
        |
   TimeoutError/Exception ──────────────────► cleanup pool, del bot.pool
        |                                     _ready_initializing = False (finally)
        | (success)                           allow next READY to retry
        v
 bot.tree.sync() ── wrapped in wait_for(timeout=SYNC_TIMEOUT_SECONDS)
        |                                     ← REL-03: log failure, come online
        | fail/timeout ──────────────────────► background_retry_sync() task
        |
        v
 HTTP health server (already running)
        |
 GET /health
        |
        v
 gather_bot_metrics(bot)
 [db_ok, gateway_ready, MusicCog loaded?]   ← REL-01: add MusicCog check
        |
        | degraded_reasons non-empty + HEALTH_STRICT_STATUS
        v
 HTTP 503 {"status":"degraded","reasons":[...]}
 HTTP 200 {"status":"ok"} (healthy or flag=false)


asyncio.create_task(some_coro) ────────────► Task runs
        |                                         |
        | (D-03) attach done-callback             | exception?
        |                                         v
        |                             _on_task_done(task)
        |                                   |          |
        |                              log.error    post to ERROR_LOG_CHANNEL_ID
        |                                           (rate-limited by D-04 dedup)


YouTubeService.async_search/async_extract
        |
    [attempt 1] ──fail/transient──► [attempt 2, +1s backoff]
                                         |
                                    still failing?
                                         |
                               [throttled update_ytdlp()]
                                         |
                                    [attempt 3]
                                         |
                                    still failing? → raise
```

### Recommended Project Structure
No structural changes — all edits are within existing files:
```
dexter/
├── config.py           ← add HEALTH_STRICT_STATUS, DB_COMMAND_TIMEOUT_SECONDS,
│                          SYNC_TIMEOUT_SECONDS, INIT_WATCHDOG_TIMEOUT_SECONDS,
│                          TASK_ERROR_CHANNEL_COOLDOWN_SECONDS, YTDLP_RETRY_BACKOFF_SECONDS
├── bot.py              ← health status code, watchdog wrap, sync timeout + retry
├── cogs/ops.py         ← MusicCog-load check in gather_bot_metrics
├── cogs/music.py       ← done-callbacks on create_task calls
├── cogs/events.py      ← done-callbacks (if any create_task is added)
├── services/youtube.py ← retry loop in async_search / async_extract
└── utils/logger.py     ← (no change needed — log_to_discord already exists)
```

---

## Critical Discovery: `command_timeout` Already Set

**`bot.py` line 300–301 (verified from live code read):**
```python
bot.pool = await asyncpg.create_pool(
    dsn=config.sanitize_database_url(config.DATABASE_URL),
    min_size=config.DB_POOL_MIN,
    max_size=config.DB_POOL_MAX,
    command_timeout=30,          # ALREADY PRESENT — hardcoded
    ssl='require',
    max_inactive_connection_lifetime=config.DB_MAX_INACTIVE_CONN_LIFETIME,
    statement_cache_size=config.DB_STATEMENT_CACHE_SIZE,
)
```

REL-05 scope is therefore: (1) replace hardcoded `30` with `config.DB_COMMAND_TIMEOUT_SECONDS`, and (2) catch `asyncio.TimeoutError` in cog command handlers to deliver a personality-flavored message instead of the generic `on_app_command_error` fallback. No asyncpg pool plumbing changes are required.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Hang detection in async init | A polling loop or watchdog thread | `asyncio.wait_for` | Standard library; converts any coroutine hang to `TimeoutError` cleanly; cancels the wrapped coro with `CancelledError` so `finally` blocks run |
| Task exception surfacing | A subclass of asyncio.Task | `Task.add_done_callback` | Standard library hook; zero overhead; works with `asyncio.create_task` unmodified |
| Error dedup state machine | A complex dedup system | A dict of `{error_key: last_post_time}` | Mirrors the existing `_last_ytdlp_update` float pattern already in `youtube.py`; same semantics |
| YouTube retry with backoff | Custom exponential backoff | Simple `asyncio.sleep(n * BACKOFF)` for 1-2 retries | Only 2-3 attempts; full exponential is over-engineered for this scale |

**Key insight:** Everything in Phase 9 has a standard library or existing-codebase pattern. The risk is building custom machinery where a one-liner exists.

---

## Runtime State Inventory

SKIPPED — this is a hardening phase, not a rename/refactor/migration. No stored string data changes.

---

## Common Pitfalls

### Pitfall 1: `task.exception()` raises `CancelledError` if task was cancelled
**What goes wrong:** A done-callback calls `task.exception()` without first checking `task.cancelled()`. On bot shutdown, asyncio cancels all pending tasks, causing the callback to raise `CancelledError` itself.
**Why it happens:** `asyncio.Task.exception()` raises `asyncio.CancelledError` if the task was cancelled — it does not return `None`.
**How to avoid:** Always guard with `if task.cancelled(): return` before calling `task.exception()`.
**Warning signs:** Tracebacks in logs during shutdown mentioning `CancelledError` from inside a done-callback.

```python
# CORRECT pattern [CITED: docs.python.org/3/library/asyncio-task.html]
def _on_task_done(task: asyncio.Task) -> None:
    if task.cancelled():
        return  # cancellation is normal (shutdown, skip, etc.)
    exc = task.exception()
    if exc is not None:
        log.error("Task %r failed: %s", task.get_name(), exc, exc_info=exc)
        # rate-limited channel post here
```

### Pitfall 2: `asyncio.wait_for` cancels the wrapped coroutine — partial init state
**What goes wrong:** `asyncio.wait_for(_initialize_once(), timeout=120)` times out. The wrapped coroutine is sent `CancelledError`, its `finally` blocks run, but asyncpg pool may have been created and is now in limbo.
**Why it happens:** `_initialize_once` creates the pool early (step 1). If it hangs at a later step (e.g., `init_db`), the pool exists on `bot.pool` but DB schema initialization is incomplete.
**How to avoid:** The `on_ready` cleanup path already handles this: check for `getattr(bot, 'pool', None)`, call `await pool.close()`, `del bot.pool`. This cleanup runs in the `except` block. Crucially, `asyncio.wait_for` raises `TimeoutError` (not `CancelledError`) TO THE CALLER, so the existing `except Exception` branch catches it. Add a specific `except asyncio.TimeoutError` before the generic one to emit a clearer log message.
**Warning signs:** Pool connection count metrics staying non-zero after a failed init.

### Pitfall 3: Health check fires before `_ready_done` — false "MusicCog missing" degraded
**What goes wrong:** The health endpoint starts early in `_initialize_once` (before cog loading). A health probe during early startup would find `"MusicCog" not in bot.cogs` and report degraded when the bot is actually still initializing.
**Why it happens:** `_health_server_task` starts before `load_extension("cogs.music")` in `_initialize_once`.
**How to avoid:** Guard the MusicCog check with `getattr(bot, '_ready_done', False)`. Only report MusicCog-missing as degraded after init is confirmed complete. During startup, a missing MusicCog is not yet an error.
**Warning signs:** External monitors triggering "degraded" alerts immediately on bot restart before the bot finishes loading.

### Pitfall 4: `_play_track` fire-and-forget tasks should NOT get error-channel callbacks
**What goes wrong:** Adding done-callbacks to `asyncio.create_task(self._play_track(...))` causes Discord channel spam when a track fails to play (a normal occurrence for unavailable tracks).
**Why it happens:** `_play_track` raises exceptions for unavailable tracks as part of normal flow. These are already handled gracefully inside `_play_track` itself.
**How to avoid:** Apply done-callbacks only to the true "invisible" tasks: `_post_auto_lyrics`, `_prefetch_next_track`, `try_auto_queue`. The `_play_track` tasks already have full internal handling; adding a done-callback would double-log handled errors.
**Warning signs:** Discord error channel flooded with "Track unavailable" messages on every skip or failed track.

### Pitfall 5: `bot.tree.sync()` background retry creating multiple concurrent retries
**What goes wrong:** Multiple READY events fire (per-shard or reconnects) and each triggers a background retry task, resulting in N concurrent sync attempts.
**Why it happens:** AutoShardedBot fires `on_ready` once per shard; if sync fails, each shard's ready handler spawns a retry.
**How to avoid:** Use a module-level flag (`_sync_retry_active: bool = False`) to gate the background retry, similar to the `_health_server_task` guard. Only one retry chain runs at a time.
**Warning signs:** Multiple "sync succeeded on retry attempt N" log lines firing within seconds of each other.

### Pitfall 6: asyncpg `command_timeout` raises `asyncio.TimeoutError`, not `asyncpg.exceptions.*`
**What goes wrong:** Catch block targets `asyncpg.exceptions.QueryCanceledError` expecting to catch client-side timeouts. The block is never reached.
**Why it happens:** `QueryCanceledError` is raised when the POSTGRESQL SERVER cancels the query (server-side `statement_timeout`). `asyncio.TimeoutError` is what asyncpg raises when the CLIENT-SIDE `command_timeout` fires.
**How to avoid:** Catch `asyncio.TimeoutError` for command_timeout. Only catch `asyncpg.exceptions.QueryCanceledError` if you also set a server-side `statement_timeout`.
**Warning signs:** Handlers never show the personality timeout message despite the 30s limit being hit.

### Pitfall 7: yt-dlp `ExtractorError.expected=True` should NOT be retried
**What goes wrong:** The retry loop retries a "Video unavailable" or age-restricted video, burning 3 attempts and updating yt-dlp unnecessarily.
**Why it happens:** All yt-dlp errors look the same (`Exception`) without inspecting `ExtractorError.expected`.
**How to avoid:** Import `from yt_dlp.utils import ExtractorError` and check `isinstance(exc, ExtractorError) and exc.expected`. If `True`, this is a permanent failure (content unavailable) — skip retry and propagate immediately.
**Warning signs:** yt-dlp auto-update triggering on "Video unavailable" messages.

---

## Code Examples

Verified patterns from official sources and live codebase:

### REL-04: `asyncio.wait_for` watchdog wrapping `_initialize_once`
```python
# Source: docs.python.org/3/library/asyncio-task.html + live bot.py on_ready analysis
INIT_WATCHDOG_TIMEOUT_SECONDS = 120  # in config.py

# In on_ready() — replaces bare `await _initialize_once()`
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
    # existing pool cleanup...
    return
finally:
    bot._ready_initializing = False  # now ALWAYS resets (hang + exception + success)
```

### REL-03: `bot.tree.sync()` with timeout + background retry
```python
# Source: discordpy.readthedocs.io/en/latest/interactions/api.html (CommandTree.sync)
# sync() raises discord.HTTPException, CommandSyncFailure, Forbidden, MissingApplicationID

SYNC_TIMEOUT_SECONDS = 30  # in config.py
_sync_retry_active: bool = False  # module-level guard

async def _sync_with_timeout(guild=None) -> list:
    """Attempt bot.tree.sync() with timeout. Returns synced list or raises."""
    coro = bot.tree.sync(guild=guild) if guild else bot.tree.sync()
    return await asyncio.wait_for(coro, timeout=config.SYNC_TIMEOUT_SECONDS)

async def _background_sync_retry() -> None:
    """Retry sync in background after failure — called via asyncio.create_task."""
    global _sync_retry_active
    for attempt in range(1, 4):  # 3 retries: 60s, 120s, 180s
        await asyncio.sleep(60 * attempt)
        try:
            synced = await _sync_with_timeout()
            log.info("Command sync succeeded on retry attempt %d (%d commands)", attempt, len(synced))
            _sync_retry_active = False
            return
        except Exception as exc:
            log.warning("Command sync retry %d/%d failed: %s", attempt, 3, exc)
    log.error("Command sync failed after all retry attempts; commands may be stale")
    _sync_retry_active = False

# In _initialize_once(), replace bare await bot.tree.sync():
try:
    synced = await _sync_with_timeout()
    log.info("Synced %d commands globally", len(synced))
except Exception as exc:
    log.warning("Command sync failed (%s); coming online with existing commands; retrying in background", exc)
    if not _sync_retry_active:
        _sync_retry_active = True
        asyncio.create_task(_background_sync_retry(), name="sync-retry")
```

### REL-02: Done-callback helper (D-03/D-04)
```python
# Source: docs.python.org/3/library/asyncio-task.html (Task.add_done_callback pattern)
# Location: new shared helper, e.g. in utils/tasks.py or inline in each cog

# Module-level dedup state (mirrors _UPDATE_THROTTLE_SECONDS in youtube.py)
_last_task_error_post: dict[str, float] = {}
TASK_ERROR_CHANNEL_COOLDOWN_SECONDS = 300  # 5 minutes per (task_name, exc_type) key

# Keep strong references so GC doesn't collect mid-flight tasks
_background_tasks: set[asyncio.Task] = set()


def make_task(coro, *, name: str | None = None, bot=None) -> asyncio.Task:
    """Create a fire-and-forget task with exception surfacing.

    Done-callback logs exceptions to dexter.log (always) and posts to the Discord
    error channel (rate-limited by TASK_ERROR_CHANNEL_COOLDOWN_SECONDS per error key).
    CancelledError is silently ignored (normal on shutdown/skip).
    """
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    task.add_done_callback(functools.partial(_on_task_done, bot=bot))
    return task


def _on_task_done(task: asyncio.Task, *, bot=None) -> None:
    if task.cancelled():
        return  # normal: shutdown, skip, or generation-change cancellation
    exc = task.exception()
    if exc is None:
        return  # success
    task_name = task.get_name() or "unknown"
    log.error("Background task %r raised: %s", task_name, exc, exc_info=exc)
    if bot is None:
        return
    # Rate-limit channel posts per (task_name, exc_type) to avoid flooding
    key = f"{task_name}:{type(exc).__name__}"
    now = time.monotonic()
    last = _last_task_error_post.get(key, 0.0)
    if now - last < TASK_ERROR_CHANNEL_COOLDOWN_SECONDS:
        return  # already posted this error type recently; log is sufficient
    _last_task_error_post[key] = now
    # Must schedule the async post — done-callbacks are synchronous
    asyncio.ensure_future(_post_task_error(bot, task_name, exc))


async def _post_task_error(bot, task_name: str, exc: Exception) -> None:
    if not hasattr(bot, "log_to_discord"):
        return
    embed = discord.Embed(
        title=f"Background Task Error: {task_name}",
        description=f"{type(exc).__name__}: {exc}",
        color=0xFF6600,
    )
    try:
        await bot.log_to_discord(embed)
    except Exception:
        pass  # never let the error reporter break things
```

### REL-02 call-site replacement
```python
# Before (music.py:621 / 628 / 763):
asyncio.create_task(self._post_auto_lyrics(guild, track))
asyncio.create_task(self._prefetch_next_track(guild, next_tracks[0], current_gen))
asyncio.create_task(ai_cog.try_auto_queue(guild))

# After — import make_task from utils.tasks (or define inline):
make_task(self._post_auto_lyrics(guild, track), name="auto-lyrics", bot=self.bot)
make_task(self._prefetch_next_track(guild, next_tracks[0], current_gen), name="prefetch", bot=self.bot)
make_task(ai_cog.try_auto_queue(guild), name="auto-queue", bot=self.bot)

# NOTE: do NOT add done-callbacks to _play_track fire-and-forget tasks (Pitfall 4)
# _play_track has full internal handling; its failures are handled errors, not invisible ones
```

### REL-01: `/health` status code + MusicCog check
```python
# In cogs/ops.py, gather_bot_metrics() — add after gateway check:

# MusicCog load check (REL-01 / D-02)
# Guard: only report missing as degraded after full init (_ready_done).
# During startup, MusicCog is absent by design (cog loads after pool/services).
if getattr(bot, "_ready_done", False):
    if bot.cogs.get("MusicCog") is None:
        metrics["degraded_reasons"].append("MusicCog not loaded")

# In bot.py health() handler — replace the always-200 aio_web.Response:
# D-01: HEALTH_STRICT_STATUS flag (default True) controls whether degraded → 503
strict = getattr(config, "HEALTH_STRICT_STATUS", True)
if reasons:
    body = json.dumps({"status": "degraded", "reasons": reasons})
    status = 503 if strict else 200
else:
    body = '{"status":"ok"}'
    status = 200
return _aio_web.Response(text=body, content_type='application/json', status=status)
```

### REL-05: config.py additions + handler catch
```python
# config.py (move hardcoded 30 from bot.py):
DB_COMMAND_TIMEOUT_SECONDS = 30        # floor for every query; raise per-query as needed

# bot.py _initialize_once() — replace hardcoded 30:
command_timeout=config.DB_COMMAND_TIMEOUT_SECONDS,

# In cog command handlers (e.g. /leaderboard, /stats, any DB-heavy command):
# Add asyncio.TimeoutError to the except clause for DB errors:
try:
    rows = await get_leaderboard_songs(self.pool, guild_id=guild_id)
    ...
except asyncio.TimeoutError:
    await interaction.followup.send(
        "database is being slow. try again in a bit.", ephemeral=True
    )
    return
except Exception as exc:
    log.error("/leaderboard DB error: %s", exc)
    await interaction.followup.send(
        "couldn't load the leaderboard right now. try again in a bit.",
        ephemeral=True,
    )
    return
```

### REL-06: yt-dlp retry loop in async wrappers
```python
# services/youtube.py — replaces async_search and async_extract
# Source: live codebase analysis + yt-dlp ExtractorError.expected attribute [ASSUMED]

from yt_dlp.utils import ExtractorError as _ExtractorError

YTDLP_RETRY_BACKOFF_SECONDS = 1.0  # in config.py
YTDLP_MAX_QUICK_RETRIES = 2        # in config.py (attempts 1+2 before update path)


def _is_transient_ytdlp_error(exc: Exception) -> bool:
    """Return True if the error is plausibly transient (network blip / extractor update needed).

    Permanent failures (video unavailable, age restriction, etc.) have
    ExtractorError.expected = True and must not be retried.
    """
    if isinstance(exc, _ExtractorError) and exc.expected:
        return False  # permanent: content unavailable, not a yt-dlp bug
    return True  # network errors, unexpected extractor failures = transient candidates


async def async_search(self, query: str, count: int | None = None) -> list[dict]:
    """Run search with bounded retry + throttled self-heal (REL-06 / D-08)."""
    loop = asyncio.get_running_loop()
    last_exc: Exception | None = None
    for attempt in range(YTDLP_MAX_QUICK_RETRIES + 1):  # 0, 1, 2
        try:
            return await loop.run_in_executor(
                None, functools.partial(self.search, query, count)
            )
        except Exception as exc:
            last_exc = exc
            if not _is_transient_ytdlp_error(exc):
                raise  # permanent failure — don't retry
            if attempt < YTDLP_MAX_QUICK_RETRIES:
                log.warning(
                    "search attempt %d/%d failed (transient): %s",
                    attempt + 1, YTDLP_MAX_QUICK_RETRIES + 1, exc,
                )
                await asyncio.sleep(config.YTDLP_RETRY_BACKOFF_SECONDS * (attempt + 1))
            else:
                # All quick retries exhausted — try throttled update + final attempt
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
    raise last_exc  # unreachable but satisfies type checker
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Always HTTP 200 from `/health` (D-28 Koyeb kill-loop workaround) | `HEALTH_STRICT_STATUS` flag: 503 when degraded (strict), 200 always (flag off) | Enables real external monitoring while preserving escape hatch |
| Fire-and-forget tasks silently swallow exceptions | Done-callbacks log to file + Discord error channel | Failures become visible without affecting playback |
| `_ready_initializing` only resets on raised exception, hangs permanently if coro hangs | `asyncio.wait_for` watchdog converts any hang to `TimeoutError` | Self-healing startup on stuck DB connections |
| `bot.tree.sync()` hangs/fails → bot unusable | Timeout + background retry → already-registered commands keep working | Startup resilience without user-visible impact |
| `command_timeout=30` hardcoded, no user-facing message | Config constant + `asyncio.TimeoutError` catch in handlers | Personality-flavored timeout message instead of generic error |
| `search()`/`extract()` fail once and propagate | Quick retry + update fallback (matching `download()` behavior) | Self-healing on network blips without paying update cost every time |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `ExtractorError.expected` attribute reliably distinguishes permanent vs transient yt-dlp failures | REL-06 code example | Could over-retry permanent failures (wasted update calls) or under-retry transient ones |
| A2 | `_is_transient_ytdlp_error` treating all non-`expected=True` errors as transient is safe for search/extract (unlike download where content-unavailable is permanent) | REL-06 pattern | Network errors from search should retry; video-unavailable from extract with no `expected` flag might incorrectly retry once |
| A3 | `asyncio.wait_for` on `_initialize_once` correctly cancels it mid-flight, with all internal `finally` blocks running | REL-04 | If yt-dlp or asyncpg have C-level blocking calls that don't respond to `CancelledError`, cleanup may not complete; practical risk is low for pure Python paths |

**If this table is empty of HIGH-risk items:** The critical implementation decisions (exception type, guard pattern, dedup mechanism) are all verified against live code or official docs.

---

## Open Questions

1. **Where to place `make_task` / `_on_task_done` helper (D-03)**
   - What we know: It needs to be importable by both `cogs/music.py` and (potentially) `cogs/events.py` without circular imports.
   - What's unclear: `utils/tasks.py` is the cleanest location; alternatively it can be module-level in `bot.py` and passed as a callable (more coupling).
   - Recommendation: Create `utils/tasks.py` with `make_task` + dedup state. Both cogs import from utils without circularity.

2. **`first_run` path — sync timeout needed there too?**
   - What we know: `first_run` calls `await bot.tree.sync()` bare (bot.py:638/641). It then calls `await bot.close()`.
   - What's unclear: `first_run` is a one-shot CLI op; hanging is annoying but not a production outage.
   - Recommendation: Yes, apply the same `wait_for` wrapper for consistency. A 60s timeout is fine here (user can Ctrl-C if it hangs).

3. **`tasks.loop` background loops — `@loop.error` vs done-callbacks?**
   - What we know: `idle_check`, `cache_cleanup`, `ytdlp_update`, `status_rotation` are `@tasks.loop` decorated. They are NOT `asyncio.create_task` fire-and-forget tasks. The `@loop.error` decorator is the idiomatic hook for these.
   - What's unclear: D-03 says "any other `asyncio.create_task` / `tasks.loop` background work" — this implies `tasks.loop` loops also get visibility hardening.
   - Recommendation: Add `@loop.error` handlers on the four `bot.py` loops that post to the Discord error channel (with the same dedup). The planner should include this as a separate sub-task from `create_task` done-callbacks.

---

## Environment Availability

No new external dependencies. All tools already confirmed present in the running environment.

| Dependency | Required By | Available | Fallback |
|------------|------------|-----------|----------|
| asyncpg 0.31.0 | REL-05 (command_timeout) | confirmed in requirements.txt | — |
| discord.py ≥2.3 | REL-02/03/04 | confirmed in requirements.txt | — |
| aiohttp | REL-01 (health status code) | confirmed (already used for health server) | — |
| yt-dlp | REL-06 | confirmed (daily auto-update running) | — |

---

## Validation Architecture

> `workflow.nyquist_validation` is absent from `.planning/config.json` — treated as enabled.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing `tests/` directory) |
| Config file | `tests/` directory present; check for pytest.ini or pyproject.toml |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | Notes |
|--------|----------|-----------|-------------------|-------|
| REL-01 | `gather_bot_metrics` returns MusicCog degraded reason when cog missing | unit | `pytest tests/test_ops.py::test_gather_metrics_musiccog_missing -x` | Phase 10 extracts pure logic; Phase 9 ships the change, Phase 10 tests it |
| REL-02 | `_on_task_done` callback logs exception, skips on cancel | unit | `pytest tests/test_tasks.py::test_on_task_done -x` | Pure callback — no Discord mock needed |
| REL-03 | Sync failure → log + background retry without blocking | integration-lite | Manual verify via logs | Discord HTTP mock required for full unit test; Phase 10 scope |
| REL-04 | `asyncio.wait_for` on `_initialize_once` resets `_ready_initializing` on timeout | unit | `pytest tests/test_bot_init.py::test_ready_guard_resets_on_timeout -x` | Pure asyncio — mockable |
| REL-05 | `asyncio.TimeoutError` from DB handler → personality message sent | unit | `pytest tests/test_ops.py::test_leaderboard_db_timeout -x` | Mock pool raising TimeoutError |
| REL-06 | `async_search` retries on transient error, not on `ExtractorError.expected=True` | unit | `pytest tests/test_youtube.py::test_search_retry_transient -x` | Mock `search()` raising controlled exceptions |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x -q`
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_tasks.py` — covers REL-02 callback behavior
- [ ] `tests/test_bot_init.py` — covers REL-04 watchdog guard reset
- [ ] `tests/test_youtube.py::test_search_retry_*` — covers REL-06 retry logic

*(Existing `tests/` directory may have some coverage — inspect before creating new files to avoid duplication.)*

---

## Security Domain

> `security_enforcement` absent from config — treated as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | n/a for this hardening phase |
| V3 Session Management | no | n/a |
| V4 Access Control | no | n/a |
| V5 Input Validation | no | No new user inputs in this phase |
| V6 Cryptography | no | No crypto changes |

### Phase-Specific Security Notes

**D-27 preserved (no new data in `/health` body):** The `degraded_reasons` strings exposed in the 503 body are generic ("MusicCog not loaded", "database unreachable", "discord gateway not ready"). No guild IDs, shard IDs, pool internals, or user data are exposed. This is the same restriction already documented in `cogs/ops.py` (D-27/T-08-08).

**Done-callback `_post_task_error` embeds:** The Discord error channel post should include task name and exception type/message. It must NOT include guild IDs or user data from the exception context (follow the existing `on_app_command_error` pattern which logs only command name and error string).

**Error dedup dict has no PII risk:** `_last_task_error_post` keys are `"{task_name}:{ExceptionType}"` — no user or guild data.

---

## Sources

### Primary (HIGH confidence)
- Live `bot.py` (verified line-by-line) — `_initialize_once`, `on_ready` guard, health handler, `command_timeout=30` at line 300
- Live `cogs/ops.py` (verified) — `gather_bot_metrics` current check set
- Live `cogs/music.py` (verified) — exact `create_task` call sites at lines 621, 628, 763, 888, 1480
- Live `services/youtube.py` (verified) — `_UPDATE_THROTTLE_SECONDS`, `update_ytdlp()`, `async_search`/`async_extract` wrappers
- Live `database.py` (verified) — pool kwargs, query helper shapes
- [asyncpg create_pool docs](https://magicstack.github.io/asyncpg/current/_modules/asyncpg/pool.html) — `command_timeout` kwarg, acquire timeout behavior
- [Python asyncio docs](https://docs.python.org/3/library/asyncio-task.html) — `Task.add_done_callback`, `asyncio.wait_for` cancellation semantics, GC strong-reference warning
- [discord.py CommandTree.sync](https://discordpy.readthedocs.io/en/latest/interactions/api.html) — sync raises HTTPException/CommandSyncFailure/Forbidden/MissingApplicationID
- [discord.ext.tasks docs](https://discordpy.readthedocs.io/en/latest/ext/tasks/index.html) — `@loop.error` signature, `reconnect=True` behavior, `add_exception_type`

### Secondary (MEDIUM confidence)
- asyncpg GitHub pool.py source read — confirms `compat.wait_for` used internally; connection returned to pool after timeout; `asyncio.TimeoutError` raised to caller
- [GitHub asyncpg issue #633](https://github.com/MagicStack/asyncpg/issues/633) — confirms `asyncio.TimeoutError` vs `QueryCanceledError` distinction

### Tertiary (LOW confidence / [ASSUMED])
- `yt_dlp.utils.ExtractorError.expected` attribute behavior — confirmed class exists and has `expected` bool, but the precise set of errors that set `expected=True` vs `False` is based on yt-dlp source read (not official documentation, as yt-dlp has no formal API docs)

---

## Metadata

**Confidence breakdown:**
- Standard stack / current code state: HIGH — verified against live files
- API contracts (asyncpg timeout exception type, asyncio.wait_for cancellation): HIGH — verified via official docs + source
- yt-dlp `ExtractorError.expected` transient heuristic: MEDIUM — confirmed class attribute exists; semantics inferred from GitHub source
- Recommended timeout values (30s pool, 30s sync, 120s watchdog, 5min dedup cooldown): MEDIUM — reasoned from observed latencies; tunable post-deploy

**Research date:** 2026-06-26
**Valid until:** 2026-09-26 (stable — no fast-moving dependencies; asyncpg 0.31.0 is pinned; discord.py ≥2.3 is stable)
