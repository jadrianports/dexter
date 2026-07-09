"""Dexter Discord bot — entry point, service wiring, and background tasks."""

from __future__ import annotations

import argparse
import asyncio
import datetime
import os
import sys
import time

import asyncpg
import discord
from aiohttp import web as _aio_web
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from pgvector.asyncpg import register_vector

import config
import database
from database import init_db
from logic import taste as logic_taste
from logic.health import determine_health_status
from models.message_buffer import MessageBuffer
from models.server_state import ServerState
from services.audio import AudioService
from services.metrics import PerfMetrics
from services.youtube import YouTubeService
from utils.logger import log

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")


def _require_discord_token() -> None:
    """Exit if no token is configured. Called from main(), never at import.

    Importing this module must never terminate the interpreter — the test suite
    and any tooling that inspects bot.py import it without a token present.
    """
    if not DISCORD_TOKEN:
        log.error("DISCORD_TOKEN not set in .env")
        sys.exit(1)


class DexterBot(commands.AutoShardedBot):
    """AutoShardedBot subclass that tears down the asyncpg pool on shutdown.

    discord.py has no `on_close` event (CR-01) — resource cleanup must override
    close(), which the library invokes exactly once during shutdown. Without this
    the pool leaks a full set of Postgres connections on every restart cycle.
    """

    async def setup_hook(self) -> None:
        """Register persistent views so buttons survive a bot restart (D-03, PLAYER-01).

        setup_hook is called once before on_ready. Registering NowPlayingView here
        lets Discord route presses on pre-restart messages to the live handler.
        Import is inside the method to avoid a circular import at module load time
        (bot.py is imported by cogs; cogs import bot only via TYPE_CHECKING).
        """
        from cogs.music import NowPlayingView

        self.add_view(NowPlayingView(self))
        log.info("Registered persistent NowPlayingView")

    async def close(self) -> None:
        pool = getattr(self, "pool", None)
        if pool is not None:
            try:
                await pool.close()
            except Exception as exc:
                log.warning("Error closing asyncpg pool on shutdown: %s", exc)
        await super().close()


def create_bot() -> DexterBot:
    """Create and configure the bot instance."""
    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True
    intents.guilds = True
    intents.members = True

    bot = DexterBot(
        command_prefix="!",  # unused but required by commands.Bot
        intents=intents,
        activity=discord.Activity(type=discord.ActivityType.listening, name="music"),
        owner_id=config.OWNER_ID or None,  # wire configured owner so /sync auth works (WR-07)
    )

    return bot


bot = create_bot()


# ──────────────────────────── STATUS ROTATION HELPERS ────────────────────────────

# Module-level index counter that increments on each status_rotation tick.
# Starts at -1 so the first tick yields index 0.
_status_index: int = -1


def _pick_next_status() -> str:
    """Cycle through the status pool, returning the next status string.

    Pool order (round-robin across all guilds' data):
      0: current-song line (if anything is playing in any active queue)
      1: server-count line
      2: static personality line from STATUS_LINES pool
      3: seasonal line (if one applies today, else fall through to personality)

    Falls back gracefully if any pool entry is empty or unavailable.
    """
    from personality.roasts import STATUS_LINES, pick_random
    from personality.seasonal import get_seasonal_context

    global _status_index
    _status_index += 1

    # Build the pool dynamically each tick so it reflects current state.
    pool: list[str] = []

    # Slot 0: current-song line (pick from any actively-playing queue)
    current_song_text: str | None = None
    music_cog = bot.cogs.get("MusicCog")
    if music_cog is not None:
        for guild in bot.guilds:
            queue = music_cog.get_queue(guild.id)
            track = queue.get_current() if hasattr(queue, "get_current") else None
            if track and getattr(queue, "is_playing", False):
                title = getattr(track, "title", None) or str(track)
                current_song_text = title[:80]  # cap for presence display
                break
    if current_song_text:
        pool.append(current_song_text)

    # Slot 1: server-count line
    n = len(bot.guilds)
    pool.append(f"{n} server{'s' if n != 1 else ''} that don't deserve me")

    # Slot 2: static personality line
    pool.append(pick_random(STATUS_LINES))

    # Slot 3: seasonal line (append only when non-empty)
    seasonal = get_seasonal_context()
    if seasonal:
        # Use a short excerpt — presence name is capped at 128 chars by Discord
        seasonal_short = seasonal.split(".")[0][:80]
        pool.append(seasonal_short)

    return pool[_status_index % len(pool)]


# ──────────────────────────── HEALTH ENDPOINT ────────────────────────────

# Module-level handle for the single health-server task. Lets on_ready re-fires
# skip a second launch (WR-02) and lets a done-callback surface failures (WR-01).
_health_server_task = None

# Single-flight guard: only one background sync-retry chain runs at a time (REL-03 / Pitfall 5).
# Multiple shards each fire READY; without this guard each would spawn its own retry.
_sync_retry_active: bool = False


async def _run_health_server() -> None:
    """Minimal HTTP health check endpoint for Koyeb WEB service.

    Koyeb free tier requires a WEB service (not Worker) and performs HTTP
    health checks. Also enables UptimeRobot pings to prevent 1-hour sleep.
    Binds to 0.0.0.0 so Koyeb's health checker can reach it (not localhost).
    Returns the minimal {"status":"ok"} — no internal state exposed (T-05-01).
    """

    async def health(request: _aio_web.Request) -> _aio_web.Response:
        # Import at request time (function-scope) to avoid circular import at module load.
        # Matches the existing pattern for `from services.queue_persistence import restore_queues`.
        # Pitfall 6: health may fire before cogs are loaded → broad try/except fallback.
        try:
            from cogs.ops import gather_bot_metrics

            metrics = await gather_bot_metrics(bot)
            reasons = metrics.get("degraded_reasons", [])
        except Exception:
            reasons = ["metrics gatherer unavailable"]

        # D-01: HEALTH_STRICT_STATUS (default True) → 503 when degraded; False → legacy 200.
        # D-27: body exposes ONLY status + generic reason strings (no guild/shard/pool internals).
        # D-02: single source of truth — logic.health.determine_health_status owns the decision.
        status, body = determine_health_status(reasons, getattr(config, "HEALTH_STRICT_STATUS", True))

        return _aio_web.Response(
            text=body,
            content_type="application/json",
            status=status,
        )

    app = _aio_web.Application()
    app.router.add_get("/health", health)
    runner = _aio_web.AppRunner(app)
    await runner.setup()
    try:
        # Render injects $PORT and routes its public URL to it; default 8000 keeps
        # Railway / PC / local working unchanged. The /health route + an external
        # pinger (UptimeRobot) is what keeps a Render free web service from sleeping.
        _health_port = int(os.environ.get("PORT", "8000"))
        site = _aio_web.TCPSite(runner, "0.0.0.0", _health_port)
        await site.start()
        log.info("Health endpoint listening on 0.0.0.0:%s/health", _health_port)
        # Keep the coroutine alive so the TCPSite is not torn down on return.
        # Cancellable: asyncio.CancelledError propagates out of asyncio.Event.wait().
        await asyncio.Event().wait()
    finally:
        # WR-03: release the bound port + aiohttp resources on cancel/shutdown.
        # Latent leak only on in-process restart; harmless under Koyeb SIGTERM-exit.
        await runner.cleanup()


# ──────────────────────────── SERVICE WIRING ────────────────────────────


async def _cleanup_partial_init() -> None:
    """Tear down a partially-initialized boot so the next READY retries cleanly (WR-04).

    Loops stopped: idle_check, cache_cleanup, ytdlp_update, status_rotation,
    memory_distill_batch (Phase 11 / D-09 path 2), memory_sweep (Phase 11 / MEM-07),
    taste_distill_batch (Phase 13 / TASTE-03).

    _initialize_once starts the background loops + health server BEFORE the
    fail-prone steps (DB ready, restore_queues). If init then hangs (watchdog
    TimeoutError) or raises, leaving those loops running keeps firing them against
    the about-to-be-closed pool — e.g. idle_check → queue_persistence.clear_persisted()
    raises every 60s until a retry succeeds, and live cogs reading self.bot.pool
    hit AttributeError. Stop the pool-bound loops and drop the pool-bound service
    so the retry re-wires everything atomically. The health server is intentionally
    left running: it reads bot.pool live and degrades gracefully when it is absent.
    """
    # Stop loops bound to the dying pool (each guarded — may not have started).
    # Loops stopped: idle_check, cache_cleanup, ytdlp_update, status_rotation,
    # memory_distill_batch (Phase 11 / D-09 path 2), memory_sweep (Phase 11 / MEM-07),
    # taste_distill_batch (Phase 13 / TASTE-03).
    for _loop in (
        idle_check,
        cache_cleanup,
        ytdlp_update,
        status_rotation,
        memory_distill_batch,
        memory_sweep,
        taste_distill_batch,
    ):
        try:
            if _loop.is_running():
                _loop.cancel()
        except Exception:
            pass

    # Drop the pool-bound persistence service; _initialize_once recreates it.
    if hasattr(bot, "queue_persistence"):
        del bot.queue_persistence

    # Close + drop the pool last, after nothing else references it.
    _pool = getattr(bot, "pool", None)
    if _pool is not None:
        try:
            await _pool.close()
        except Exception:
            pass
        if hasattr(bot, "pool"):
            del bot.pool


@bot.event
async def on_ready():
    """Initialize services, database, and cogs once the bot is connected."""
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")

    # One-time init guard (Pitfall 2 / T-04-07 + WR-01). AutoShardedBot fires
    # on_ready on every shard connection and on reconnects. `_ready_done` is set
    # only AFTER a successful init, so a transient failure (e.g. cold Postgres)
    # retries on the next ready event instead of dead-locking permanently.
    # `_ready_initializing` blocks concurrent re-entry while the first init is
    # still awaiting (multiple shards each fire READY).
    if getattr(bot, "_ready_done", False) or getattr(bot, "_ready_initializing", False):
        return
    bot._ready_initializing = True
    try:
        await asyncio.wait_for(
            _initialize_once(),
            timeout=config.INIT_WATCHDOG_TIMEOUT_SECONDS,
        )
        bot._ready_done = True
    except asyncio.TimeoutError:
        log.error(
            "on_ready init hung for %ss; cleaning up to retry on next READY event",
            config.INIT_WATCHDOG_TIMEOUT_SECONDS,
        )
        await _cleanup_partial_init()
        return
    except Exception:
        log.exception("on_ready init failed; cleaning up to retry on next ready event")
        await _cleanup_partial_init()
        return
    finally:
        bot._ready_initializing = False

    await _post_startup_messages()


async def _register_vector(conn) -> None:
    """Per-connection pgvector codec registration (Phase 11 / T-11-01).

    Passed as `init=` to asyncpg.create_pool so every pooled connection has the
    vector type codec registered. This is a per-connection set_type_codec call —
    NOT a prepared statement — so it is fully compatible with statement_cache_size=0
    (K-04 / Pitfall 2). Must run AFTER CREATE EXTENSION vector (see extension-first
    throwaway connect in _initialize_once).
    """
    await register_vector(conn)


async def _initialize_once() -> None:
    """One-time boot init: pool, services, cogs, queue restore.

    Raises on failure so on_ready can clean up and allow a retry (WR-01). Cog
    loads are idempotent so a retry after a partial init never double-loads.
    """
    # Phase 11 / T-11-01: Extension-first boot ordering.
    # Open a throwaway connection and ensure the vector extension exists BEFORE
    # creating the pool. This prevents "unknown type: public.vector" ValueErrors
    # that would otherwise fire on the first pooled connection that hits user_memories
    # (Pitfall 1). The throwaway is closed in a finally block so it never leaks.
    _ext_dsn = config.sanitize_database_url(config.DATABASE_URL)
    _ext_conn = await asyncpg.connect(
        dsn=_ext_dsn,
        ssl="require",  # K-04: match pool ssl setting
        statement_cache_size=0,  # K-04: disable prepared stmts for PgBouncer
    )
    try:
        await _ext_conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        log.info("pgvector extension ensured (CREATE EXTENSION IF NOT EXISTS vector)")
    finally:
        await _ext_conn.close()

    # Database — asyncpg connection pool (Phase 4 / SCALE-02)
    # SECURITY (T-04-05): DSN comes from config.DATABASE_URL (env, git-ignored);
    # the pool object and DSN string are never logged here.
    bot.pool = await asyncpg.create_pool(
        dsn=config.sanitize_database_url(config.DATABASE_URL),
        min_size=config.DB_POOL_MIN,
        max_size=config.DB_POOL_MAX,  # now 5 via K-04 constant update
        command_timeout=config.DB_COMMAND_TIMEOUT_SECONDS,
        ssl="require",  # K-05: explicit ssl, not via DSN string
        max_inactive_connection_lifetime=config.DB_MAX_INACTIVE_CONN_LIFETIME,  # K-04: 240s
        statement_cache_size=config.DB_STATEMENT_CACHE_SIZE,  # K-04: 0
        init=_register_vector,  # Phase 11: register vector codec on every pooled connection
    )
    await init_db(bot.pool)

    # Services
    bot.youtube_service = YouTubeService()
    bot.audio_service = AudioService(youtube_service=bot.youtube_service)

    # Phase 6: Rolling performance metrics aggregate (PERF-06 / D-18)
    bot.perf_metrics = PerfMetrics(config.PERF_ROLLING_WINDOW)

    # Phase 2: Message buffer + server states
    bot.message_buffer = MessageBuffer()
    bot.server_states: dict[int, ServerState] = {}

    # Phase 2: Gemini service (only if API key is available)
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        from services.gemini import GeminiService

        bot.gemini_service = GeminiService(api_key=gemini_key)
        log.info("Gemini service initialized")
    else:
        log.warning("GEMINI_API_KEY not set — AI features disabled")

    # Phase 11 / CR-01: long-term memory service (depends on Gemini for embeddings).
    # Guarded on gemini_service so memory features are silently disabled when no key.
    # Constructed (pool, gemini_service) per services/memory.py and 11-PATTERNS.md;
    # the asyncpg pool already has the pgvector codec registered via init=_register_vector,
    # and statement_cache_size=0 (Neon/K-04) is set on the pool above.
    if hasattr(bot, "gemini_service"):
        from services.memory import MemoryService

        bot.memory_service = MemoryService(bot.pool, bot.gemini_service)
        log.info("Memory service initialized")

    # Phase 3: Lyrics service (wired unconditionally — LyricsService degrades
    # gracefully when GENIUS_TOKEN is missing: Genius path disabled, AZLyrics still works)
    # SECURITY (T-03-18): token passed to LyricsService(); never logged here.
    genius_token = os.getenv("GENIUS_TOKEN")
    from services.lyrics import LyricsService

    bot.lyrics_service = LyricsService(genius_token)
    log.info("Lyrics service initialized")

    # Phase 2: Error log channel helper
    from utils.logger import log_to_discord as _log_to_discord

    bot.log_to_discord = lambda embed: _log_to_discord(bot, embed)

    # Phase 18 / CONFIG-03/05: per-guild config cache (D-04, D-06/D-07, D-08/D-09).
    # Constructed unconditionally — unlike the Gemini-gated services above, every
    # guild needs to resolve its ambient config regardless of which optional
    # services are wired. load_all() already fails closed internally (D-07): do
    # NOT wrap it in a boot-aborting try — an empty cache just means every guild
    # reads as unconfigured (ambient-silent) until a restart succeeds.
    from services.guild_config import GuildConfigService

    bot.guild_config = GuildConfigService(bot.pool, bot)
    await bot.guild_config.load_all()

    # Home-guild seed (CONFIG-05 / D-08/D-09): config.DEXTER_CHANNEL_ID is now a
    # one-time bootstrap input with no ongoing authority. Unset or unresolvable
    # is a silent INFO skip (D-10) — a fresh clone / CI with no env var boots
    # fine and stays ambient-silent. No owner-only setter or second-guild write
    # path is added here (D-13) — this seed is the ONLY writer this phase.
    if not config.DEXTER_CHANNEL_ID:
        log.info("DEXTER_CHANNEL_ID unset — no home guild seeded; ambient-silent until /setup")
    else:
        _seed_channel = bot.get_channel(config.DEXTER_CHANNEL_ID)
        _seed_guild = getattr(_seed_channel, "guild", None)
        if _seed_guild is None:
            log.info(
                "DEXTER_CHANNEL_ID %s did not resolve to a guild channel — no home guild seeded",
                config.DEXTER_CHANNEL_ID,
            )
        else:
            try:
                await bot.guild_config.seed_home_guild(
                    guild_id=str(_seed_guild.id),
                    ambient_channel_id=str(_seed_channel.id),
                )
            except Exception as exc:
                log.warning("Home-guild config seed failed: %s", exc)

    # Phase 4: Queue persistence service (wired before cog loading so the service
    # exists on bot before MusicCog setup() runs)
    from services.queue_persistence import QueuePersistenceService

    bot.queue_persistence = QueuePersistenceService(bot.pool)

    # Load cogs (idempotent — a retry after a partial init must not double-load)
    for _ext in ("cogs.music", "cogs.help", "cogs.events", "cogs.library", "cogs.ops", "cogs.memory"):
        if _ext not in bot.extensions:
            await bot.load_extension(_ext)
    if hasattr(bot, "gemini_service"):
        for _ext in ("cogs.ai", "cogs.imagine"):
            if _ext not in bot.extensions:
                await bot.load_extension(_ext)

    # Start background tasks
    if not idle_check.is_running():
        idle_check.start()
    if not cache_cleanup.is_running():
        cache_cleanup.start()
    if not ytdlp_update.is_running():
        ytdlp_update.start()
    if not status_rotation.is_running():
        status_rotation.start()
    # Phase 11 / D-09 path 2: once-daily distill-batch (memory_service guarded inside)
    if not memory_distill_batch.is_running():
        memory_distill_batch.start()
    # Phase 11 / MEM-07: once-daily decay sweep (memory_service guarded inside)
    if not memory_sweep.is_running():
        memory_sweep.start()
    # Phase 13 / TASTE-03: once-daily taste distill batch (memory_service guarded inside)
    if not taste_distill_batch.is_running():
        taste_distill_batch.start()

    # K-02: Minimal HTTP health endpoint for Koyeb WEB service.
    # No before_loop guard — endpoint must be up early so Koyeb's health check
    # passes on first deploy.
    # WR-02: on_ready can re-fire (per-shard / reconnect / init retry); launch
    # the server only once — a second bind on :8000 would raise "address in use".
    global _health_server_task
    if _health_server_task is None or _health_server_task.done():
        _health_server_task = asyncio.ensure_future(_run_health_server())

        def _on_health_server_done(task) -> None:
            # WR-01: surface a startup failure (e.g. port bind) to the error log;
            # a bare ensure_future would swallow it and Koyeb's health check would
            # just time out with no actionable cause in the logs.
            if task.cancelled():
                return
            exc = task.exception()
            if exc is not None:
                log.error("Health server task failed: %s", exc, exc_info=exc)

        _health_server_task.add_done_callback(_on_health_server_done)
        log.info("Health server task scheduled")

    log.info("Dexter is ready.")

    # Phase 4: Restore persisted queues — MUST run after load_extension so MusicCog
    # is registered (Pitfall 4). Runs before startup message so the bot is fully
    # ready before announcing itself (Anti-Pattern ordering).
    from services.queue_persistence import restore_queues

    await restore_queues(bot)

    # Phase 8: Monotonic uptime anchor — set after full init so gather_bot_metrics
    # reports time since the bot was fully ready, not since module load.
    import time as _time

    bot._start_monotonic = _time.monotonic()


async def _post_startup_messages() -> None:
    """Post the arrogant startup message to each guild (best-effort)."""
    # Phase 3: Startup message — MUST be last (after all load_extension calls and
    # background-task starts) so commands are registered first (Pitfall 5).
    # Uses STARTUP_MESSAGES (arrogant, D-02) — never self-deprecating.
    # SECURITY (T-03-19): allowed_mentions=none() prevents mention injection.
    from personality.roasts import STARTUP_MESSAGES
    from personality.roasts import pick_random as _pick_random

    # WR-03: try/except lives INSIDE the loop body so one guild's send failure
    # (e.g. discord.Forbidden after a permission change, a transient
    # discord.HTTPException) is logged and skipped without aborting the
    # startup announcement for every other guild.
    for guild in bot.guilds:
        try:
            channel = bot.guild_config.resolve_ambient_channel(guild)
            if channel:
                await channel.send(
                    _pick_random(STARTUP_MESSAGES),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except Exception as exc:
            log.warning("Startup message post failed for guild %s: %s", guild.id, exc)


async def _background_sync_retry() -> None:
    """Background retry helper for command-tree sync (REL-03 / D-05).

    Attempts up to 3 syncs with increasing backoff (60s, 120s, 180s between attempts).
    Resets _sync_retry_active on exit (success or exhaustion) so a future failure
    can spawn a new chain. Modeled on the _post_startup_messages best-effort pattern.
    """
    global _sync_retry_active
    for attempt in range(1, 4):  # attempts 1, 2, 3
        await asyncio.sleep(60 * attempt)
        try:
            synced = await asyncio.wait_for(bot.tree.sync(), timeout=config.SYNC_TIMEOUT_SECONDS)
            log.info(
                "Command sync succeeded on retry attempt %d (%d commands)",
                attempt,
                len(synced),
            )
            _sync_retry_active = False
            return
        except Exception as exc:
            log.warning("Command sync retry %d/3 failed: %s", attempt, exc)
    log.error("Command sync failed after all retry attempts; slash commands may be stale")
    _sync_retry_active = False


# ──────────────────────────── GLOBAL ERROR HANDLER ────────────────────────────


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    """Global error handler for all slash commands."""
    if isinstance(error, app_commands.CommandOnCooldown):
        if not interaction.response.is_done():
            await interaction.response.send_message(
                f"slow down. try again in {error.retry_after:.0f}s.",
                ephemeral=True,
            )
        return

    # Log unexpected errors
    log.error(f"Unhandled command error: {error}", exc_info=error)
    if hasattr(bot, "log_to_discord"):
        embed = discord.Embed(
            title="Unhandled Command Error",
            description=f"Command: {interaction.command.name if interaction.command else 'unknown'}\nError: {error}",
            color=0xFF0000,
        )
        await bot.log_to_discord(embed)

    if not interaction.response.is_done():
        await interaction.response.send_message(
            "something broke and it wasn't my fault. probably.",
            ephemeral=True,
        )
    else:
        await interaction.followup.send(
            "something broke and it wasn't my fault. probably.",
        )


# ──────────────────────────── OWNER COMMANDS ────────────────────────────


@bot.tree.command(name="sync", description="Sync slash commands (owner only)")
@app_commands.describe(guild_id="Guild ID to sync to (omit for global)")
async def sync_commands(interaction: discord.Interaction, guild_id: str | None = None):
    global _sync_retry_active
    if not await bot.is_owner(interaction.user):
        return await interaction.response.send_message("Not authorized.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    if guild_id:
        guild = discord.Object(id=int(guild_id))
        bot.tree.copy_global_to(guild=guild)
        try:
            synced = await asyncio.wait_for(bot.tree.sync(guild=guild), timeout=config.SYNC_TIMEOUT_SECONDS)
            await interaction.followup.send(f"Synced {len(synced)} commands to guild {guild_id}.")
            log.info("Synced %d commands to guild %s", len(synced), guild_id)
        except Exception as exc:
            log.warning(
                "Command sync failed (%s); coming online with existing commands; retrying in background",
                exc,
            )
            if not _sync_retry_active:
                _sync_retry_active = True
                asyncio.create_task(_background_sync_retry(), name="sync-retry")
            await interaction.followup.send(f"Sync failed: {exc}. Retrying in background.")
    else:
        try:
            synced = await asyncio.wait_for(bot.tree.sync(), timeout=config.SYNC_TIMEOUT_SECONDS)
            await interaction.followup.send(f"Synced {len(synced)} commands globally.")
            log.info("Synced %d commands globally", len(synced))
        except Exception as exc:
            log.warning(
                "Command sync failed (%s); coming online with existing commands; retrying in background",
                exc,
            )
            if not _sync_retry_active:
                _sync_retry_active = True
                asyncio.create_task(_background_sync_retry(), name="sync-retry")
            await interaction.followup.send(f"Sync failed: {exc}. Retrying in background.")


# ──────────────────────────── BACKGROUND TASKS ────────────────────────────

# Dedup map for _post_loop_error: keyed on "{loop_name}:{ExcTypeName}".
# Mirrors the _UPDATE_THROTTLE_SECONDS monotonic pattern in services/youtube.py.
_last_loop_error_post: dict[str, float] = {}


async def _post_loop_error(loop_name: str, error: Exception) -> None:
    """Post a throttled, sanitized embed to the Discord error channel for a loop crash.

    Dedups per (loop_name, exc_type) within TASK_ERROR_CHANNEL_COOLDOWN_SECONDS so a
    recurring loop failure cannot flood the error channel. Every occurrence is already
    logged by the @loop.error handler before this is called.

    Security (T-09-04): embed carries loop name + type(error).__name__ + truncated
    message only — no guild IDs, user data, tokens, or DSNs.
    """
    key = f"{loop_name}:{type(error).__name__}"
    now = time.monotonic()
    if now - _last_loop_error_post.get(key, 0.0) < config.TASK_ERROR_CHANNEL_COOLDOWN_SECONDS:
        return
    _last_loop_error_post[key] = now
    if not hasattr(bot, "log_to_discord"):
        return
    # Truncate message to avoid embed limit; type + message only (T-09-04)
    desc = f"{type(error).__name__}: {str(error)[:500]}"
    embed = discord.Embed(
        title=f"Background Loop Error: {loop_name}",
        description=desc,
        color=0xFF6600,
    )
    try:
        await bot.log_to_discord(embed)
    except Exception:
        pass  # never let the error reporter crash the loop


@tasks.loop(seconds=60)
async def idle_check():
    """Check for idle voice connections and disconnect after timeout."""
    for vc in bot.voice_clients:
        guild = vc.guild
        music_cog = bot.cogs.get("MusicCog")
        if not music_cog:
            continue

        queue = music_cog.get_queue(guild.id)

        # Count human members in the channel
        human_members = [m for m in vc.channel.members if not m.bot]

        if len(human_members) == 0:
            if not hasattr(vc, "_idle_seconds"):
                vc._idle_seconds = 0
            vc._idle_seconds += 60

            if vc._idle_seconds >= config.IDLE_TIMEOUT_SECONDS:
                log.info(f"Idle timeout in guild {guild.id}, disconnecting")
                queue._play_generation += 1  # invalidate stale after-callbacks (mirrors /stop template)
                vc.stop()
                await vc.disconnect()
                queue.clear()
                if hasattr(bot, "queue_persistence"):
                    await bot.queue_persistence.clear_persisted(guild.id)

                channel = music_cog._get_text_channel(guild)
                if channel:
                    await channel.send("Left the voice channel after being alone for too long.")
        else:
            # Reset the auto-leave idle timer (humans are present)
            if hasattr(vc, "_idle_seconds"):
                vc._idle_seconds = 0

            # Phase 3 — Idle-loneliness (PERS-08): post a lonely message once after
            # IDLE_LONELINESS_THRESHOLD_SECONDS of silence while humans are in voice.
            #
            # SEPARATE accumulator (vc._idle_loneliness_seconds) — must NOT touch
            # vc._idle_seconds so the auto-leave timer is completely unaffected.
            # Reset the loneliness window whenever a new track starts playing
            # (track title change signals fresh activity in the channel).
            current_track = queue.get_current() if hasattr(queue, "get_current") else None
            current_title = getattr(current_track, "title", None) if current_track else None

            if not hasattr(vc, "_idle_loneliness_seconds"):
                vc._idle_loneliness_seconds = 0
                vc._loneliness_posted = False
                vc._loneliness_last_title = current_title

            # Detect a new song started → reset loneliness window
            if current_title != vc._loneliness_last_title:
                vc._idle_loneliness_seconds = 0
                vc._loneliness_posted = False
                vc._loneliness_last_title = current_title

            if not vc._loneliness_posted:
                vc._idle_loneliness_seconds += 60

                if vc._idle_loneliness_seconds >= config.IDLE_LONELINESS_THRESHOLD_SECONDS:
                    # Only post once per silence window
                    vc._loneliness_posted = True
                    try:
                        from personality.roasts import IDLE_LONELINESS_MESSAGES
                        from personality.roasts import pick_random as _pr

                        channel = bot.guild_config.resolve_ambient_channel(guild)
                        if channel:
                            await channel.send(
                                _pr(IDLE_LONELINESS_MESSAGES),
                                # SECURITY (T-03-19): prevent mention injection
                                allowed_mentions=discord.AllowedMentions.none(),
                            )
                    except Exception as exc:
                        log.warning("Idle-loneliness post failed: %s", exc)


@idle_check.before_loop
async def before_idle_check():
    await bot.wait_until_ready()


@idle_check.error
async def on_idle_check_error(error: Exception) -> None:
    log.error("idle_check task error: %s", error, exc_info=error)
    await _post_loop_error("idle_check", error)


@tasks.loop(hours=1)
async def cache_cleanup():
    """Hourly cache size check and cleanup (Phase 6: LFU with protected-set guard)."""
    if not hasattr(bot, "audio_service") or not hasattr(bot, "pool"):
        return

    # Build protected set: currently queued + prefetched video IDs across all guilds.
    # Prevents LFU eviction from removing a track that is currently playing,
    # queued for upcoming playback, or being prefetched (PERF-05 / D-12/D-13).
    protected_video_ids: set[str] = set()
    music_cog = bot.cogs.get("MusicCog")
    if music_cog is not None:
        for queue in music_cog.queues.values():
            # Include current track and all upcoming tracks
            for t in queue.tracks[queue.current_index :]:
                protected_video_ids.add(t.video_id)
            # Include in-flight prefetch slot
            if queue._prefetch_video_id:
                protected_video_ids.add(queue._prefetch_video_id)

    await bot.audio_service.cleanup_cache(bot.pool, protected_video_ids)
    log.info("Cache cleanup check completed (protected=%d)", len(protected_video_ids))


@cache_cleanup.before_loop
async def before_cache_cleanup():
    await bot.wait_until_ready()


@cache_cleanup.error
async def on_cache_cleanup_error(error: Exception) -> None:
    log.error("cache_cleanup task error: %s", error, exc_info=error)
    await _post_loop_error("cache_cleanup", error)


@tasks.loop(time=datetime.time(hour=4, minute=0))
async def ytdlp_update():
    """Proactively update yt-dlp daily at 04:00 (it breaks often)."""
    from services.youtube import update_ytdlp

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, update_ytdlp)


@ytdlp_update.before_loop
async def before_ytdlp_update():
    await bot.wait_until_ready()


@ytdlp_update.error
async def on_ytdlp_update_error(error: Exception) -> None:
    log.error("ytdlp_update task error: %s", error, exc_info=error)
    await _post_loop_error("ytdlp_update", error)


@tasks.loop(time=datetime.time(hour=config.MEMORY_DISTILL_BATCH_HOUR, minute=0))
async def memory_distill_batch() -> None:
    """Daily batch: distill the day's message-buffer banter into memory facts (D-09 path 2).

    Fires once daily at config.MEMORY_DISTILL_BATCH_HOUR UTC (default 03:00).
    Iterates all active channel buffers in bot.message_buffer, collects the
    recent banter for each channel, and calls memory_service.distill_and_remember
    per channel in one batched pass at priority=2 (never contends with user /ask).

    This is path 2 of D-09 (the daily batch); path 1 is the notable-event hooks
    in cogs/events.py and cogs/music.py. No voice-session-end trigger (D-10).

    Guards: no-op when memory_service or message_buffer are absent (GEMINI_API_KEY
    unset or partial init). Never raises — degrades silently on any error.
    """
    memory_service = getattr(bot, "memory_service", None)
    message_buffer = getattr(bot, "message_buffer", None)
    if memory_service is None or message_buffer is None:
        return

    # Collect all active channel buffers (evict_stale already removed expired ones)
    active_channels = list(message_buffer._buffers.keys())
    if not active_channels:
        return

    log.info(
        "memory_distill_batch: processing %d active channel(s)",
        len(active_channels),
    )

    for channel_id in active_channels:
        history = message_buffer.get_history(channel_id)
        if not history:
            continue

        # Group messages by user so we generate a distilled fact per user, not
        # per channel — memory is per-user scoped (T-11-03a / user_id WHERE guard).
        # Build a per-user raw_text by concatenating their messages from the buffer.
        #
        # CR-02: key on the real Discord snowflake (msg["author_id"]), NEVER the
        # display name. Display names are user-controllable; keying on them both
        # makes the memory unrecallable (recall scopes on str(user.id)) and lets a
        # user poison another user's memory scope by setting their nickname to a
        # victim's Discord ID. The display name is still carried into raw_text purely
        # as distiller context — it never becomes an owner key.
        user_texts: dict[str, tuple[str, list[str]]] = {}  # user_id (snowflake) → (display_name, [msgs])
        for msg in history:
            if msg.get("role") != "user":
                continue
            user_id = msg.get("author_id")
            if not user_id or not user_id.isdigit():
                continue  # never accept a non-snowflake (or missing id) as an owner key
            display_name = msg.get("author", "someone")
            content = msg.get("content", "")
            if content:
                if user_id not in user_texts:
                    user_texts[user_id] = (display_name, [])
                user_texts[user_id][1].append(content)

        for user_id, (display_name, messages) in user_texts.items():
            if not messages:
                continue
            # Batch the user's messages into a single context string for the distiller.
            raw_text = f"{display_name} said in chat: " + " | ".join(messages[-5:])  # last 5 msgs
            try:
                # Fire a single batched priority-2 distill call per user per channel,
                # keyed on the real Discord snowflake so the fact is recallable and
                # scoped to its true owner (CR-02).
                await memory_service.distill_and_remember(
                    user_id=user_id,
                    guild_id=None,  # channel_id doesn't map to guild_id in message_buffer
                    raw_text=raw_text,
                    kind="daily_batch",
                    base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS["daily_batch"],
                )
            except Exception as exc:
                log.debug(
                    "memory_distill_batch: error for user=%s channel=%d: %s",
                    user_id,
                    channel_id,
                    exc,
                )

    log.info("memory_distill_batch: batch pass complete")


@memory_distill_batch.before_loop
async def before_memory_distill_batch() -> None:
    await bot.wait_until_ready()


@memory_distill_batch.error
async def on_memory_distill_batch_error(error: Exception) -> None:
    log.error("memory_distill_batch task error: %s", error, exc_info=error)
    await _post_loop_error("memory_distill_batch", error)


@tasks.loop(time=datetime.time(hour=2, minute=30))
async def memory_sweep() -> None:
    """Daily decay sweep: delete expired low-salience memories (MEM-07 / D-08).

    Fires once daily at 02:30 UTC — distinct from cache_cleanup (hourly),
    ytdlp_update (04:00 UTC), and memory_distill_batch (03:00 UTC) to avoid
    thundering-herd on the Neon pool.

    Calls MemoryService.sweep() which removes user_memories rows where
    expires_at < now() AND salience < MEMORY_DECAY_SALIENCE_FLOOR. High-salience
    episodes (milestone, late_night, repeat_song) are retained regardless of age.

    Guards: no-op when memory_service is absent (GEMINI_API_KEY unset or partial
    init). sweep() itself swallows all errors — this loop never raises (T-11-07c).
    """
    memory_service = getattr(bot, "memory_service", None)
    if memory_service is None:
        return
    await memory_service.sweep()


@memory_sweep.before_loop
async def before_memory_sweep() -> None:
    await bot.wait_until_ready()


@memory_sweep.error
async def on_memory_sweep_error(error: Exception) -> None:
    log.error("memory_sweep task error: %s", error, exc_info=error)
    await _post_loop_error("memory_sweep", error)


@tasks.loop(time=datetime.time(hour=config.TASTE_DISTILL_BATCH_HOUR, minute=0))
async def taste_distill_batch() -> None:
    """Daily batch: turn structured song_history into number-free taste_episode facts (TASTE-01/03).

    Fires once daily at config.TASTE_DISTILL_BATCH_HOUR UTC (default 05:00) — distinct
    from cache_cleanup (hourly), memory_sweep (02:30), memory_distill_batch (03:00), and
    ytdlp_update (04:00) so this extra daily pass never thundering-herds the Neon pool
    (D-06/D-07/T-13-05).

    Reads ONLY structured song_history via the plan 13-02 aggregate helpers — never the
    message buffer (that is memory_distill_batch's job, a separate kind). For every
    (guild_id, user_id) pair active in the rolling TASTE_LOOKBACK_DAYS window: skip users
    below TASTE_MIN_ACTIVITY_TRACKS (D-08 gate), pull per-artist window/baseline counts,
    and pre-bucket them to number-free phrases via logic.taste.summarize_taste (D-02) —
    numbers never reach the Gemini distiller. Writes exactly ONE kind, "taste_episode"
    (D-09 — no taste_shift this phase), carrying guild_id through (taste is guild-scoped
    listening, unlike daily_batch's None).

    Guards: no-op when memory_service or pool are absent (GEMINI_API_KEY unset or partial
    init). A single user's distill failure is swallowed (log.debug) and never aborts the
    rest of the batch (T-13-08 / restore_queues per-guild continue discipline).
    """
    memory_service = getattr(bot, "memory_service", None)
    pool = getattr(bot, "pool", None)
    if memory_service is None or pool is None:
        return

    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=config.TASTE_LOOKBACK_DAYS)
    baseline_since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=config.TASTE_BASELINE_DAYS)

    candidates = await database.get_active_taste_users(pool, since=since)
    if not candidates:
        return

    log.info("taste_distill_batch: processing %d candidate user(s)", len(candidates))

    for row in candidates:
        guild_id = row["guild_id"]
        user_id = row["user_id"]
        tracks_in_window = row["tracks_in_window"]

        # D-08 gate: skip users below the min-activity floor for this window.
        if not logic_taste.has_min_activity(tracks_in_window, min_tracks=config.TASTE_MIN_ACTIVITY_TRACKS):
            continue

        # Per-user isolation (T-13-08 / restore_queues per-guild continue discipline):
        # the raise-prone DB round-trip lives INSIDE the try so one user's transient
        # Neon hiccup (scale-to-zero / pool exhaustion / dropped conn) does a `continue`
        # instead of aborting the whole batch. distill_and_remember already swallows its
        # own errors, but get_user_artist_activity does not (WR-13-01).
        try:
            artist_rows = await database.get_user_artist_activity(
                pool,
                guild_id=guild_id,
                user_id=user_id,
                since=since,
                baseline_since=baseline_since,
            )

            # D-02 pre-bucketing: number-free phrases only, before any Gemini call.
            phrases = logic_taste.summarize_taste(
                artist_rows,
                obsession_min=config.TASTE_OBSESSION_MIN_PLAYS,
                new_arrival_min=config.TASTE_NEW_ARRIVAL_MIN_PLAYS,
                steady_min_baseline=config.TASTE_STEADY_MIN_BASELINE,
            )
            if not phrases:
                continue

            # raw_text is built ONLY from summarize_taste's digit-free phrases — never
            # interpolate a raw count here (accuracy firewall, Critical Rule 12).
            raw_text = "Listening activity this week: " + "; ".join(phrases)

            # Write exactly ONE kind, taste_episode (D-09 — taste_shift stays deferred).
            # guild_id is carried through (unlike daily_batch's None) since taste is
            # guild-scoped listening (13-PATTERNS.md).
            await memory_service.distill_and_remember(
                user_id=user_id,
                guild_id=guild_id,
                raw_text=raw_text,
                kind="taste_episode",
                base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS["taste_episode"],
            )
        except Exception as exc:
            log.debug(
                "taste_distill_batch: error for guild=%s user=%s: %s",
                guild_id,
                user_id,
                exc,
            )
            continue

    log.info("taste_distill_batch: batch pass complete")


@taste_distill_batch.before_loop
async def before_taste_distill_batch() -> None:
    await bot.wait_until_ready()


@taste_distill_batch.error
async def on_taste_distill_batch_error(error: Exception) -> None:
    log.error("taste_distill_batch task error: %s", error, exc_info=error)
    await _post_loop_error("taste_distill_batch", error)


@tasks.loop(seconds=config.STATUS_ROTATION_INTERVAL_SECONDS)
async def status_rotation():
    """Rotate bot presence every STATUS_ROTATION_INTERVAL_SECONDS through the status pool."""
    try:
        status_text = _pick_next_status()
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=status_text,
            )
        )
    except Exception as exc:
        log.warning("status_rotation: change_presence failed: %s", exc)


@status_rotation.before_loop
async def before_status_rotation():
    await bot.wait_until_ready()


@status_rotation.error
async def on_status_rotation_error(error: Exception) -> None:
    log.error("status_rotation task error: %s", error, exc_info=error)
    await _post_loop_error("status_rotation", error)


# ──────────────────────────── FIRST-RUN & MAIN ────────────────────────────


async def first_run(guild_id: str | None = None):
    """Sync commands and exit. Used for initial slash command registration."""

    @bot.event
    async def on_ready():
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            bot.tree.copy_global_to(guild=guild)
            try:
                synced = await asyncio.wait_for(bot.tree.sync(guild=guild), timeout=config.SYNC_TIMEOUT_SECONDS)
                log.info(f"First-run: synced {len(synced)} commands to guild {guild_id}")
            except Exception as exc:
                log.warning(
                    "First-run: command sync failed (%s); proceeding to close",
                    exc,
                )
        else:
            try:
                synced = await asyncio.wait_for(bot.tree.sync(), timeout=config.SYNC_TIMEOUT_SECONDS)
                log.info(f"First-run: synced {len(synced)} commands globally")
            except Exception as exc:
                log.warning(
                    "First-run: command sync failed (%s); proceeding to close",
                    exc,
                )

        await bot.close()

    # Load cogs so their commands are registered before sync.
    # IMPORTANT: this non-AI list MUST stay in sync with the cog tuple in
    # _initialize_once. If they drift, --first-run syncs a different command set
    # than the running bot exposes — Phase 8 UAT surfaced /leaderboard, /stats,
    # and the library commands missing because cogs.ops and cogs.library were
    # absent here while present in normal startup.
    # Mirror on_ready: only load AI cogs when a Gemini key is configured,
    # otherwise their setup references a gemini_service that won't exist.
    await bot.load_extension("cogs.music")
    await bot.load_extension("cogs.help")
    await bot.load_extension("cogs.events")
    await bot.load_extension("cogs.library")
    await bot.load_extension("cogs.ops")
    await bot.load_extension("cogs.memory")
    if os.getenv("GEMINI_API_KEY"):
        await bot.load_extension("cogs.ai")
        await bot.load_extension("cogs.imagine")
    else:
        log.warning("GEMINI_API_KEY not set — skipping AI cogs during first-run sync")
    await bot.start(DISCORD_TOKEN)


def main():
    _require_discord_token()

    parser = argparse.ArgumentParser(description="Dexter Discord Bot")
    parser.add_argument("--first-run", action="store_true", help="Sync commands and exit")
    parser.add_argument("--guild", type=str, help="Guild ID for dev sync")
    args = parser.parse_args()

    if args.first_run:
        asyncio.run(first_run(args.guild))
    else:
        bot.run(DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
