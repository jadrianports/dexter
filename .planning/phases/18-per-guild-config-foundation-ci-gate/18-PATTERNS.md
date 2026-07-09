# Phase 18: Per-Guild Config Foundation & CI Gate - Pattern Map

**Mapped:** 2026-07-10
**Files analyzed:** 14 (8 new, 6 modified)
**Analogs found:** 14 / 14

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `services/guild_config.py` | service (cache-owning) | CRUD + in-memory cache | `services/memory.py` (I/O + async recall/remember), `services/metrics.py` (in-memory-state) | role-match (composite) |
| `logic/guild_config.py` | pure decision seam | transform (sync, no I/O) | `logic/proactive.py::should_fire_proactive_callback` | exact |
| `models/guild_config.py` (discretionary) | model (frozen dataclass) | transform | `models/memory.py::MemoryFact` | exact |
| `tests/test_guild_config_logic.py` | test (pure/mock-free) | — | `tests/test_roast_logic.py` | exact |
| `tests/test_guild_config_service.py` | test (service, spy pool) | — | none exact — closest is `tests/test_memory.py` (service test with fake pool) | role-match |
| `tests/test_database_phase18.py` | test (schema + live-DB) | CRUD | `tests/test_database_phase16.py` | exact |
| `pyproject.toml` | config | — | none (greenfield) | no analog |
| `.github/workflows/ci.yml` | config (CI) | — | none (greenfield) | no analog |
| `database.py` (guild_config additions) | model/DDL + CRUD helpers | CRUD | `guild_jams`/`resolution_cache` DDL; `get_proactive_opt_out`/`set_proactive_opt_out` helper pair | exact |
| `bot.py` (boot wiring + call-site rewrites) | controller/glue (bootstrap) | event-driven (on_ready) | `bot.py::_initialize_once`'s own `memory_service` wiring block | exact (self-analog) |
| `cogs/events.py` (call-site rewrites) | controller/glue (cog) | event-driven | `cogs/events.py::_maybe_fire_proactive_callback` (D-02 gate ordering) | exact |
| `tests/conftest.py` (pool fixture fix) | test fixture | file-I/O + DB setup | `bot.py::_initialize_once` lines 362-391 (extension-first + `init=register_vector`) | exact |
| `tests/test_proactive_events.py` (patch-target update) | test | — | itself (lines 183, 202) | exact (in-place) |
| `CLAUDE.md` §Database Schema | docs | — | existing Phase 16/12 ALTER/CREATE narrative entries | exact |

## Pattern Assignments

### `services/guild_config.py` (service, CRUD + cache)

**Analogs:** `services/memory.py` (constructor + pool wiring shape), `services/metrics.py` (in-memory state owner)

**Bot-wiring pattern to mirror** (from `bot.py` lines 414-422, the `MemoryService` construction block — copy this shape verbatim for `GuildConfigService`):
```python
# Phase 11 / CR-01: long-term memory service (depends on Gemini for embeddings).
# Guarded on gemini_service so memory features are silently disabled when no key.
# Constructed (pool, gemini_service) per services/memory.py and 11-PATTERNS.md;
# the asyncpg pool already has the pgvector codec registered via init=_register_vector,
# and statement_cache_size=0 (Neon/K-04) is set on the pool above.
if hasattr(bot, "gemini_service"):
    from services.memory import MemoryService
    bot.memory_service = MemoryService(bot.pool, bot.gemini_service)
    log.info("Memory service initialized")
```
`GuildConfigService` is **unconditional** (no gemini_key guard) — construct it right after `await init_db(bot.pool)` (bot.py line 392), before the Gemini-guarded services, since CONFIG-03/D-06 requires the cache loaded before any cog that might reference it is set up. Then:
```python
bot.guild_config = GuildConfigService(bot.pool)
await bot.guild_config.load_all()  # D-06: ONE round-trip, ever, in the hot path
```
followed immediately by the home-guild seed (D-08), which needs `bot.get_channel(...)` — this MUST run inside `_initialize_once` (called from `on_ready`), never `setup_hook` (Pitfall 5 — `bot.get_channel` returns `None` before the gateway cache fills).

**Resolver pattern** (D-01/D-02/D-03) — dispatches on `logic.guild_config.decide_ambient_channel`, does not re-derive:
```python
def resolve_ambient_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
    row = self._cache.get(str(guild.id))
    channel_id = decide_ambient_channel(config_row=row)  # pure — logic/guild_config.py
    if channel_id is None:
        return None
    ch = guild.get_channel(channel_id)
    if ch is None or not isinstance(ch, discord.TextChannel):
        log.warning("guild_config: configured ambient channel %s in guild %s no longer resolves", channel_id, guild.id)
        return None
    if not ch.permissions_for(guild.me).send_messages:
        log.warning("guild_config: lost send_messages in configured channel %s (guild %s)", channel_id, guild.id)
        return None
    return ch
```
`resolve_announce_channel(guild)` is the SECOND, separately named method — its body is a straight copy of the OLD fallback chain (see "Fallback-chain body to relocate, unmodified" below). **It must have ZERO callers added in this phase** (Pitfall 2 in RESEARCH.md) — Phase 19 wires it up.

**Cache-miss semantics (D-06/D-07 FAIL CLOSED):** a missing/errored `load_all()` must leave `self._cache` as an empty dict (or equivalent), never raise into `_initialize_once` in a way that aborts boot — every guild reads as unconfigured, core commands keep working, error surfaces to `dexter.log` + `ERROR_LOG_CHANNEL_ID` (mirrors the existing `except Exception` + `log.warning` idiom seen in `_post_startup_messages` and `idle_check`, both below).

**Error-handling idiom to copy** (from `bot.py::_post_startup_messages`, lines 512-522 — wrap in try/except, log and continue, never abort):
```python
try:
    from personality.roasts import STARTUP_MESSAGES, pick_random as _pick_random
    for guild in bot.guilds:
        channel = _resolve_dexter_channel(guild)
        if channel:
            await channel.send(
                _pick_random(STARTUP_MESSAGES),
                allowed_mentions=discord.AllowedMentions.none(),
            )
except Exception as exc:
    log.warning("Startup message post failed: %s", exc)
```

---

### `logic/guild_config.py` (pure decision seam)

**Analog:** `logic/proactive.py` in full (below) — the exact template: module docstring stating "no random, no asyncio, no datetime, no discord", keyword-only params, one gate function per decision, boundary-condition comments (`>=` fails, strictly-less passes).

**Full analog file** (`logic/proactive.py`):
```python
"""Pure proactive-callback firing-decision gate (Phase 16 / PROACT-01 / D-02).

All functions in this module are deterministic and side-effect-free: no ``random``,
no ``asyncio``, no ``datetime``, no ``discord``.
...
"""

from __future__ import annotations

import config


def should_fire_proactive_callback(
    *,
    opted_out: bool,
    chance_roll: float,
    daily_count: int,
    chance: float = config.PROACTIVE_CALLBACK_CHANCE,
    daily_cap: int = config.PROACTIVE_CALLBACK_DAILY_CAP,
) -> bool:
    # Gate 1: opt-out (cheapest check, and the user's explicit preference wins)
    if opted_out:
        return False
    # Gate 2: chance roll (must be strictly less than chance to proceed)
    if chance_roll >= chance:
        return False
    # Gate 3: per-user daily cap (inclusive ceiling — at-cap fails)
    if daily_count >= daily_cap:
        return False
    return True
```

**Target shape for `logic/guild_config.py`** (RESEARCH.md's proposed skeleton — adopt verbatim as starting point, mock-free tested in `tests/test_guild_config_logic.py`):
```python
from __future__ import annotations
from typing import Mapping


def decide_ambient_channel(*, config_row: Mapping | None) -> int | None:
    """D-01: pure decision. None (no row) or configured=False -> None (silence)."""
    if config_row is None:
        return None
    if not config_row.get("configured", False):
        return None
    channel_id = config_row.get("ambient_channel_id")
    return int(channel_id) if channel_id is not None else None


def is_ambient_channel(*, config_row: Mapping | None, channel_id: int) -> bool:
    """CONFIG-02: replaces the two bare-equality gates in events.py::on_message."""
    decided = decide_ambient_channel(config_row=config_row)
    return decided is not None and decided == channel_id
```
**No `resolve_announce_channel` logic belongs here** — the fallback chain does discord/guild I/O (`guild.get_channel`, `guild.system_channel`, `permissions_for`) and stays entirely in the service tier, not the pure `logic/` seam.

---

### `models/guild_config.py` (discretionary dataclass)

**Analog:** `models/memory.py::MemoryFact` — frozen dataclass shape. (Not read in full this session; RESEARCH.md already recommends a frozen dataclass mirroring it. Planner may instead use a raw `asyncpg.Record` in the cache per "Claude's Discretion.")

---

### `database.py` — `guild_config` DDL + helpers

**Analog DDL #1 — `resolution_cache`** (database.py lines 178-186, verbatim):
```sql
CREATE TABLE IF NOT EXISTS resolution_cache (
    query_key   TEXT PRIMARY KEY,
    video_id    TEXT NOT NULL,
    title       TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rescache_expires ON resolution_cache(expires_at);
```

**Analog DDL #2 — `guild_jams`** (database.py lines 188-197, verbatim — THE closest analog: guild-keyed, TEXT PRIMARY KEY on `guild_id`, `updated_at TIMESTAMPTZ DEFAULT now()`):
```sql
CREATE TABLE IF NOT EXISTS guild_jams (
    guild_id   TEXT NOT NULL,
    name       TEXT NOT NULL,
    snapshot   JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (guild_id, name)
);

CREATE INDEX IF NOT EXISTS idx_jams_guild ON guild_jams(guild_id, updated_at DESC);
```
`guild_config` differs from `guild_jams` in that `guild_id` alone is the PK (one row per guild, not per guild+name) — RESEARCH.md's proposed DDL (already verified against this idiom) is the concrete target:
```sql
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id            TEXT PRIMARY KEY,
    ambient_channel_id  TEXT,
    configured          BOOLEAN NOT NULL DEFAULT false,
    silenced            BOOLEAN NOT NULL DEFAULT false,   -- Phase 20 reader only (D-11)
    is_blocked          BOOLEAN NOT NULL DEFAULT false,   -- Phase 20 reader only (D-11)
    joined_at           TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);
```
Insert this block into `SCHEMA_SQL` — it is plain, param-free DDL appended before the final `"""` closing the string (database.py line 198), preserving the asyncpg multi-statement single-`conn.execute()` rule.

**Analog helper pair — `get_proactive_opt_out` / `set_proactive_opt_out`** (database.py lines 318-376, verbatim, the get/set upsert-helper shape to mirror for `load_all_guild_configs` / `seed_guild_config_if_absent`):
```python
async def set_proactive_opt_out(
    pool: asyncpg.Pool, *, user_id: str, opted_out: bool
) -> None:
    """... Must be an upsert (INSERT ... ON CONFLICT DO UPDATE), never a bare
    UPDATE (Pitfall 3 / T-16-06) ...
    """
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO user_profiles (user_id, username, proactive_opt_out)"
            " VALUES ($1, $1, $2)"
            " ON CONFLICT (user_id) DO UPDATE SET"
            "   proactive_opt_out = EXCLUDED.proactive_opt_out",
            user_id, opted_out,
        )


async def get_proactive_opt_out(pool: asyncpg.Pool, user_id: str) -> bool:
    """Return whether user_id has paused proactive callbacks (PROACT-02).
    ...
    Returns:
        True if the user has opted out. False (opted-in, the default) when
        the user has no profile row yet or has never opted out.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT proactive_opt_out FROM user_profiles WHERE user_id = $1",
            user_id,
        )
    if row is None:
        return False
    return bool(row["proactive_opt_out"])
```
**SCAR WARNING — D-09 CONFLICTS with this pattern's `ON CONFLICT DO UPDATE` idiom.** `set_proactive_opt_out` uses `DO UPDATE` because re-asserting a user's opt-out preference on every call is exactly the desired behavior. The `guild_config` home-guild seed (`seed_guild_config_if_absent`) must use **`ON CONFLICT (guild_id) DO NOTHING`** instead — D-09 explicitly rejects `DO UPDATE` here because the env var is bootstrap-only and must never silently override a later `/setup` write. Do not copy the `DO UPDATE` clause from this analog for the seed helper; RESEARCH.md's `seed_guild_config_if_absent` (Code Examples section) is already correct — use it as-is:
```python
async def seed_guild_config_if_absent(
    pool: asyncpg.Pool, *, guild_id: str, ambient_channel_id: str
) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO guild_config (guild_id, ambient_channel_id, configured)"
            " VALUES ($1, $2, true)"
            " ON CONFLICT (guild_id) DO NOTHING",
            guild_id, ambient_channel_id,
        )
        return await conn.fetchrow(
            "SELECT guild_id, ambient_channel_id, configured, silenced,"
            "       is_blocked, joined_at, updated_at"
            " FROM guild_config WHERE guild_id = $1",
            guild_id,
        )
```
A parallel `load_all_guild_configs(pool) -> list[asyncpg.Record]` (a plain `SELECT *`, no params) is the D-06 boot-load helper — no existing analog does a full-table load-all in this codebase (closest precedent conceptually is `restore_queues` iterating `guild_queues`, but that is row-by-row restore logic, not a flat select — do not force that pattern here; a bare `conn.fetch("SELECT ... FROM guild_config")` is correct and sufficient).

---

### `bot.py` — deletion + call-site rewrites

**Function to DELETE in full** (`_resolve_dexter_channel`, lines 103-143 — verbatim, this exact body becomes `GuildConfigService.resolve_announce_channel`'s implementation, per D-02):
```python
def _resolve_dexter_channel(guild: discord.Guild) -> discord.TextChannel | None:
    """Resolve the Dexter ambient channel for a guild via D-09/D-10 fallback.

    Order:
      1. config.DEXTER_CHANNEL_ID (explicit env designation)
      2. Last active music channel (MusicCog queue._text_channel_id)
      3. guild.system_channel (if the bot can send there)
      4. First writable text channel

    Mirrors EventsCog._get_ambient_channel exactly; kept local to bot.py to
    preserve file-ownership boundaries (duplication is acceptable per plan).
    """
    # Step 1: explicit designation
    if config.DEXTER_CHANNEL_ID:
        ch = guild.get_channel(config.DEXTER_CHANNEL_ID)
        if ch and isinstance(ch, discord.TextChannel):
            return ch

    # Step 2: last active music channel
    music_cog = bot.cogs.get("MusicCog")
    if music_cog is not None:
        queue = music_cog.get_queue(guild.id)
        channel_id = getattr(queue, "_text_channel_id", None)
        if channel_id is not None:
            ch = guild.get_channel(channel_id)
            if ch and isinstance(ch, discord.TextChannel):
                return ch

    # Step 3: system channel
    if guild.system_channel is not None:
        perms = guild.system_channel.permissions_for(guild.me)
        if perms.send_messages:
            return guild.system_channel

    # Step 4: first writable text channel
    for ch in guild.text_channels:
        perms = ch.permissions_for(guild.me)
        if perms.send_messages:
            return ch

    return None
```

**Call site #1 — startup message** (`_post_startup_messages`, line 515):
```python
channel = _resolve_dexter_channel(guild)
```
→ becomes:
```python
channel = bot.guild_config.resolve_ambient_channel(guild)
```

**Call site #2 — idle-loneliness** (`idle_check` loop, line 739):
```python
channel = _resolve_dexter_channel(guild)
```
→ becomes:
```python
channel = bot.guild_config.resolve_ambient_channel(guild)
```
(Note: research's line numbers 515/739 confirmed exactly on read; both sites are inside `try/except Exception: log.warning(...)` blocks that must be preserved unchanged.)

**Boot-wiring insertion point** — `_initialize_once`, lines 356-392, extension-first pgvector block (quote verbatim as the pattern `tests/conftest.py` must mirror):
```python
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
        ssl='require',                   # K-04: match pool ssl setting
        statement_cache_size=0,          # K-04: disable prepared stmts for PgBouncer
    )
    try:
        await _ext_conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        log.info("pgvector extension ensured (CREATE EXTENSION IF NOT EXISTS vector)")
    finally:
        await _ext_conn.close()

    bot.pool = await asyncpg.create_pool(
        dsn=config.sanitize_database_url(config.DATABASE_URL),
        min_size=config.DB_POOL_MIN,
        max_size=config.DB_POOL_MAX,
        command_timeout=config.DB_COMMAND_TIMEOUT_SECONDS,
        ssl='require',
        max_inactive_connection_lifetime=config.DB_MAX_INACTIVE_CONN_LIFETIME,
        statement_cache_size=config.DB_STATEMENT_CACHE_SIZE,
        init=_register_vector,
    )
    await init_db(bot.pool)

    # Services
    bot.youtube_service = YouTubeService()
    bot.audio_service = AudioService(youtube_service=bot.youtube_service)
    bot.perf_metrics = PerfMetrics(config.PERF_ROLLING_WINDOW)
    bot.message_buffer = MessageBuffer()
    bot.server_states: dict[int, ServerState] = {}
    # <-- INSERT bot.guild_config construction + load_all() + home-guild seed HERE,
    #     right after init_db(bot.pool) and before the Gemini-guarded services,
    #     since guild_config has no external-key dependency (unconditional wiring).
```
`bot.get_channel(config.DEXTER_CHANNEL_ID)` for the home-guild seed is only safe to call from inside `_initialize_once` (invoked from `on_ready`, after gateway guild/channel caches populate) — **never from `setup_hook`** (Pitfall 5).

Cog-load block (lines 442-448) is unaffected structurally but is the reference for how `cogs.events` participates in the same idempotent load-once loop — no change needed here, only context for where `bot.guild_config` must already exist before `cogs.events` setup runs (it is constructed earlier in the same function).

---

### `cogs/events.py` — deletion + 4 call-site rewrites + 2 bare-equality-gate rewrites

**Function to DELETE in full** (`_get_ambient_channel`, lines 98-137 — byte-identical body to `bot.py`'s, becomes dead after consolidation; its body is NOT duplicated into the new module — `resolve_announce_channel` lives once, in `services/guild_config.py`):
```python
async def _get_ambient_channel(
    self, guild: discord.Guild
) -> discord.TextChannel | None:
    """Resolve the channel for ambient posts via the D-09/D-10 fallback chain.
    ...
    """
    if config.DEXTER_CHANNEL_ID:
        ch = guild.get_channel(config.DEXTER_CHANNEL_ID)
        if ch and isinstance(ch, discord.TextChannel):
            return ch
    music_cog = self.bot.cogs.get("MusicCog")
    if music_cog is not None:
        queue = music_cog.get_queue(guild.id)
        channel_id = getattr(queue, "_text_channel_id", None)
        if channel_id is not None:
            ch = guild.get_channel(channel_id)
            if ch and isinstance(ch, discord.TextChannel):
                return ch
    if guild.system_channel is not None:
        perms = guild.system_channel.permissions_for(guild.me)
        if perms.send_messages:
            return guild.system_channel
    for ch in guild.text_channels:
        perms = ch.permissions_for(guild.me)
        if perms.send_messages:
            return ch
    return None
```

**Call site #1 — bot-moved complaint** (line 266, inside `on_voice_state_update`, D-12 always-fires branch):
```python
channel = await self._get_ambient_channel(member.guild)
```
→ `channel = self.bot.guild_config.resolve_ambient_channel(member.guild)` — **NOTE: the new resolver is SYNCHRONOUS** (cache-only read, D-06 — no `await` needed); dropping `await` here is intentional, not a bug, and every call site must drop the `await` keyword when switching over.

**Call site #2 — voice-join roast** (line 310):
```python
channel = await self._get_ambient_channel(guild)
```
→ `channel = self.bot.guild_config.resolve_ambient_channel(guild)`

**Call site #3 — voice-leave roast** (line 356):
```python
channel = await self._get_ambient_channel(guild)
```
→ `channel = self.bot.guild_config.resolve_ambient_channel(guild)`

**Bare-equality gate #1 — proactive callback dispatch** (lines 443-448, verbatim):
```python
# Phase 16 / PROACT-01: proactive callback gate — designated channel only,
# never a DM (Pitfall 2). message.author.bot already returned above.
if (
    message.guild is not None
    and config.DEXTER_CHANNEL_ID
    and message.channel.id == config.DEXTER_CHANNEL_ID
):
    await self._maybe_fire_proactive_callback(message)
```
→ becomes:
```python
if (
    message.guild is not None
    and is_ambient_channel(
        config_row=self.bot.guild_config.get(message.guild.id),
        channel_id=message.channel.id,
    )
):
    await self._maybe_fire_proactive_callback(message)
```
(`is_ambient_channel` imported from `logic.guild_config`; `self.bot.guild_config.get(guild_id)` is a service accessor into the cache — planner decides exact method name, e.g. `.get_config(guild_id)` or `._cache.get(str(guild_id))` via a public getter.)

**Bare-equality gate #2 — vision-roast dispatch** (lines 454-460, verbatim):
```python
# Phase 17 / VIS-01: vision-roast gate — a FOURTH independent cadence
# (do NOT merge with the proactive gate). Designated channel only, and
# only when the message actually carries attachments (the structural
# mime/size gate runs inside _maybe_fire_vision_roast).
if (
    message.guild is not None
    and config.DEXTER_CHANNEL_ID
    and message.channel.id == config.DEXTER_CHANNEL_ID
    and message.attachments
):
    await self._maybe_fire_vision_roast(message)
```
→ same `is_ambient_channel(...)` predicate substituted for the two `config.DEXTER_CHANNEL_ID`-based conditions, `and message.attachments` preserved unchanged. **Do NOT merge this gate with the proactive gate** — the comment's instruction still applies verbatim after the resolver swap.

**Cross-reference for the D-02 gate-ordering convention** (`_maybe_fire_proactive_callback`, line 464+, opt-out → pure-gate → recall-floor ordering) — this is the established "cheapest gate first" idiom `logic/guild_config.py`'s callers should also follow if any async opt-out/DB check is ever layered on top (not required by D-11 in Phase 18, but the ordering convention is worth preserving for consistency):
```python
async def _maybe_fire_proactive_callback(self, message: discord.Message) -> None:
    """Evaluate and, rarely, fire a proactive memory callback (PROACT-01/02).

    D-02 firing order, short-circuit cheapest-first:
      1. Opt-out check (database.get_proactive_opt_out).
      2. Pure gate (should_fire_proactive_callback): chance roll + daily cap.
      ...
    """
```

---

### `tests/conftest.py` — pool fixture fix (prerequisite for CICD-01, Open Question 2)

**Current gap:** the fixture calls `asyncpg.create_pool(dsn)` with no `init=`, and never runs `CREATE EXTENSION IF NOT EXISTS vector` on a throwaway connection first. Compare to the verbatim `bot.py::_initialize_once` block quoted above (lines 362-391) — that IS the exact pattern to port into the fixture. RESEARCH.md's proposed fix (already verified against this analog) is copy-ready:
```python
from pgvector.asyncpg import register_vector

@pytest_asyncio.fixture
async def pool():
    dsn = os.getenv("TEST_DATABASE_URL", "postgresql://dexter:dexter@localhost:5432/dexter_test")
    try:
        _ext_conn = await asyncpg.connect(dsn=dsn)
        try:
            await _ext_conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        finally:
            await _ext_conn.close()

        p = await asyncpg.create_pool(dsn, init=register_vector)
    except Exception as exc:
        pytest.skip(f"Postgres unavailable ({exc}); skipping live-DB test")
        return
    await init_db(p)
    yield p
    async with p.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS guild_queues, song_history,"
            " user_artist_counts, image_generation_log,"
            " bot_daily_stats, user_profiles,"
            " user_favorites, user_playlists,"
            " resolution_cache, guild_jams, guild_config,"
            " user_memories CASCADE"
        )
    await p.close()
```
Note the teardown DROP list must ALSO gain `guild_config` (and pre-existing gap `user_memories`, per RESEARCH.md) — both are additive to the existing DROP statement, not a rewrite.

---

### `tests/test_proactive_events.py` — patch-target update (regression surface)

**Exact current patch form** (lines 183 and 202, both inside `with (...)` blocks around `on_message` tests):
```python
patch("cogs.events.config.DEXTER_CHANNEL_ID", 500),
```
This must change to patch the new resolver seam instead — e.g. patching `cog.bot.guild_config.get` (or whatever accessor is chosen) to return a config row with `configured=True, ambient_channel_id=500`, OR patching `cogs.events.is_ambient_channel` directly to return `True`/`False` per test case. **Grep every test file for `DEXTER_CHANNEL_ID`, `_get_ambient_channel`, and `_resolve_dexter_channel`** before finalizing — this file is confirmed to have exactly 2 hits; RESEARCH.md's Call-Site Inventory did not claim to have exhaustively grepped all test files, only `bot.py`/`cogs/events.py` source.

## Shared Patterns

### Cog → Service → Model layering (D-04)
**Source:** `services/memory.py` + its `bot.py` wiring (lines 414-422, quoted above)
**Apply to:** `services/guild_config.py` construction + `bot.guild_config` attribute + every cog reaching it via `self.bot.guild_config`

### Pure decision seam, glue dispatches without re-deriving (Phase 10 D-02 convention)
**Source:** `logic/proactive.py` (full file, quoted above), `logic/vision.py::should_fire_vision_roast` (not re-quoted, same shape)
**Apply to:** `logic/guild_config.py::decide_ambient_channel` / `is_ambient_channel`; every call site in `bot.py`/`cogs/events.py` must use the returned value directly, never re-check `config_row.get("configured")` itself.

### Idempotent upsert helper pairs
**Source:** `database.py::get_proactive_opt_out` / `set_proactive_opt_out` (lines 318-376, quoted above)
**Apply to:** `load_all_guild_configs` / `seed_guild_config_if_absent` — **but note the SCAR WARNING above: `set_proactive_opt_out`'s `DO UPDATE` idiom must NOT be copied for the seed helper; `seed_guild_config_if_absent` requires `DO NOTHING` per D-09.**

### Fire-and-forget / silent-skip on uncertainty ("boring Dexter over broken Dexter")
**Source:** `bot.py::_post_startup_messages` (try/except + `log.warning`, quoted above); Phase 17's vision silent-skip precedent (not re-quoted, referenced in CONTEXT.md)
**Apply to:** `GuildConfigService.resolve_ambient_channel`'s stale-channel/no-permission branches (D-03) — `log.warning`, return `None`, row untouched.

### Extension-first pgvector boot ordering
**Source:** `bot.py::_initialize_once` lines 362-391 (quoted in full above)
**Apply to:** `tests/conftest.py`'s `pool` fixture fix — this is a structural prerequisite for CICD-01, not optional polish (Pitfall 1 in RESEARCH.md: skipping this turns 9 currently-skipped tests into CI failures, not passes).

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `pyproject.toml` | config | — | No lint config of any kind exists anywhere in the repo (greenfield adoption, D-14). RESEARCH.md's proposed `[tool.ruff]` block is the concrete starting point. |
| `.github/workflows/ci.yml` | CI config | — | No `.github/` directory exists in the repo today (greenfield, CICD-01). RESEARCH.md's proposed workflow YAML (pgvector service container + Ruff + pytest) is the concrete starting point. |
| `tests/test_guild_config_service.py` | test (service, spy pool) | — | No existing test in this codebase asserts "zero `.acquire()` calls after a cache load" — closest conceptual precedent is `tests/test_memory.py`'s fake-pool pattern, but that tests I/O correctness, not cache-only-read enforcement. Planner will need to construct a spy/counting pool wrapper from scratch. |

## Metadata

**Analog search scope:** `bot.py` (full), `cogs/events.py` (relevant sections: 90-140, 255-365, 430-470), `database.py` (relevant sections: schema block 170-198, helper pair 318-376), `logic/proactive.py` (full), `tests/test_proactive_events.py` (grep + context), `tests/conftest.py` (referenced via RESEARCH.md's Open Question 2, not re-read — RESEARCH.md already quotes the current gap and proposed fix verbatim with verified line numbers 26-58).
**Files scanned:** 6 source files read directly this session; `services/memory.py`, `services/metrics.py`, `models/memory.py`, `logic/vision.py`, `tests/test_roast_logic.py` referenced via RESEARCH.md's own verified reads (not re-read to avoid duplicate token spend — RESEARCH.md's Sources section confirms full-file reads of all of these at research time).
**Pattern extraction date:** 2026-07-10
