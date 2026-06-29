# Phase 11: RAG Long-Term Memory - Pattern Map

**Mapped:** 2026-06-29
**Files analyzed:** 8 (2 new, 6 modified)
**Analogs found:** 8 / 8

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `services/memory.py` | service | request-response + batch | `services/gemini.py` | exact (thin wrapper + rate limiter + priority tiers) |
| `models/memory.py` | model / pure-logic | transform | `logic/roasts.py`, `logic/health.py`, `database.py:compute_streak` | exact (pure-logic TDD seam) |
| `database.py` (MODIFY) | model / storage | CRUD | `database.py` itself (`SCHEMA_SQL`, `init_db`, query helpers) | self-analog |
| `bot.py:_initialize_once` (MODIFY) | config / wiring | event-driven | `bot.py:_initialize_once` (lines 333–407) + `cache_cleanup`/`ytdlp_update` loops | self-analog |
| `personality/prompts.py` (MODIFY) | utility | transform | `personality/prompts.py:build_chat_prompt` (lines 91–104) | self-analog |
| `cogs/ai.py` (MODIFY) | controller | request-response | `cogs/ai.py` `/ask` + `/roast` (lines ~100–180) | self-analog |
| `cogs/events.py` (MODIFY) | controller | event-driven | `cogs/events.py:_generate_ambient_roast` (lines 87–116) | self-analog |
| `cogs/music.py` (MODIFY) | controller | event-driven | `cogs/music.py:_post_music_roast` (~line 1061) + `_build_roast_line` (~line 1073) | self-analog |

---

## Pattern Assignments

### `services/memory.py` (NEW — service, request-response + batch)

**Analog:** `services/gemini.py`

**Imports pattern** (lines 1–14):
```python
"""Memory service: embed, recall, remember, sweep. No Discord types."""

from __future__ import annotations

import asyncpg
from google.genai import types

import config
from services.gemini import GeminiService, GeminiRateLimitError
from utils.logger import log
```

**Rate limiter clone pattern** (`services/gemini.py` lines 34–49 and 130–131):
```python
# In GeminiService.__init__ — add alongside the existing self._rate_limiter:
self._rate_limiter = _RateLimiter()                                      # existing 15 RPM chat+image
self._embed_limiter = _RateLimiter(max_requests=config.EMBED_RPM_LIMIT)  # NEW ~60 RPM embeddings

# _RateLimiter signature (verified at line 41):
def __init__(
    self,
    max_requests: int | None = None,   # None → falls back to config.GEMINI_RPM_LIMIT
    window_seconds: float = 60.0,
) -> None:
```

**Service constructor pattern** (`services/gemini.py` line 108–131):
```python
class MemoryService:
    """RAG lifecycle: recall, remember, sweep. Owns the _embed_limiter."""

    def __init__(self, pool: asyncpg.Pool, gemini_service: GeminiService) -> None:
        self._pool = pool
        self._gemini = gemini_service
        # NOTE: _embed_limiter lives on GeminiService, accessed via self._gemini._embed_limiter
        # — MemoryService does not own a second limiter instance; it calls gemini.embed()
```

**Priority-2 background pattern** (`services/gemini.py` lines 90–93, priority usage):
```python
# Priority 2 = background: reject-if-wait>10s (GeminiRateLimitError raised)
# Priority 1 = recall on user command: wait for slot

# recall() — called on the user's roast critical path (priority 1 embed):
async def recall(self, user_id: str, guild_id: str, query_text: str) -> list[str]:
    try:
        [query_vec] = await self._gemini.embed([query_text], task_type="RETRIEVAL_QUERY", priority=1)
    except GeminiRateLimitError:
        return []   # no memory beats a wrong memory; degrade gracefully

# remember() — notable-event / daily-batch write path (priority 2 embed):
async def remember(self, user_id: str, guild_id: str, raw_text: str, kind: str, base_salience: float) -> None:
    try:
        ...
        await self._gemini.embed([distilled], task_type="RETRIEVAL_DOCUMENT", priority=2)
    except GeminiRateLimitError:
        log.debug("memory.remember: embed rate limited, skipping write")
        return
```

**Error handling pattern** (`services/gemini.py` lines 193–200):
```python
try:
    ...
except errors.APIError as e:
    log.error(f"Memory embed API error (code={e.code}): {e.message}")
    raise GeminiAPIError(str(e)) from e
except Exception as e:
    log.error(f"Memory unexpected error ({type(e).__name__}): {e}", exc_info=True)
    raise
```

---

### `models/memory.py` (NEW — model, pure-logic transform)

**Analog:** `logic/roasts.py`, `logic/health.py`, `database.py:compute_streak`

**Module docstring convention** (`logic/roasts.py` lines 1–16):
```python
"""Pure memory scoring functions: rerank, recency, novelty, dedup, salience, eviction.

All functions are deterministic and side-effect-free: no asyncio, no Discord imports,
no database calls, no random, no datetime.now().

Any nondeterministic value (clock, random roll) is computed by the calling service
and passed in as a primitive — following the established seam pattern from
logic/roasts.py and database.py:compute_streak.

Phase 11 coverage locked by tests/test_memory.py.
"""
```

**Pure-function + clock-injectable pattern** (`database.py` lines 30–60):
```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass(frozen=True)
class MemoryFact:
    id: int
    fact: str
    salience: float
    hit_count: int
    created_at: datetime
    last_seen_at: datetime
    last_surfaced_at: datetime | None
    surface_count: int
    similarity: float   # cosine similarity from ANN search (1 - distance)

def rerank(
    facts: list[MemoryFact],
    *,
    now: datetime | None = None,           # clock-injectable for unit tests
    relevance_weight: float = 1.0,
    recency_weight: float = 0.5,
    salience_weight: float = 0.7,
    novelty_weight: float = 0.5,
) -> list[MemoryFact]:
    """Score and sort facts by composite score. Pure — no I/O."""
    ...

def apply_floor(facts: list[MemoryFact], floor: float) -> list[MemoryFact]:
    """Drop facts below similarity floor. Returns [] when nothing clears."""
    return [f for f in facts if f.similarity >= floor]

def dedup_decision(existing_sim: float, threshold: float) -> bool:
    """Return True (bump, NOOP) when existing_sim > threshold; False (insert)."""
    return existing_sim > threshold
```

**Enum pattern** (`logic/roasts.py` lines 31–44):
```python
import enum

class EvictionReason(enum.Enum):
    CAP_EXCEEDED = "cap_exceeded"
    EXPIRED = "expired"
```

---

### `database.py` (MODIFY — model/storage, CRUD)

**Analog:** `database.py` itself — self-analog for schema and helper patterns.

**SCHEMA_SQL plain-DDL pattern** (lines 67–162):
```python
# RULE: plain DDL only — no $N params anywhere in SCHEMA_SQL.
# asyncpg accepts multi-statement DDL strings only when there are no positional params.
# New additions go at the TOP (CREATE EXTENSION must precede CREATE TABLE):

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;          -- Phase 11: pgvector, top of SCHEMA_SQL

CREATE TABLE IF NOT EXISTS user_memories (
    id               BIGSERIAL PRIMARY KEY,
    user_id          TEXT NOT NULL,
    guild_id         TEXT,
    kind             TEXT,
    fact             TEXT NOT NULL,
    embedding        vector(768) NOT NULL,
    salience         REAL DEFAULT 0,
    hit_count        INTEGER DEFAULT 1,
    created_at       TIMESTAMPTZ DEFAULT now(),
    last_seen_at     TIMESTAMPTZ DEFAULT now(),
    last_surfaced_at TIMESTAMPTZ,
    surface_count    INTEGER DEFAULT 0,
    expires_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_user_memories_user ON user_memories(user_id, created_at DESC);

-- (existing tables below unchanged)
CREATE TABLE IF NOT EXISTS user_profiles ( ...
```

**Query helper pattern** (`database.py` lines 179–230):
```python
# Parameterized $N queries, pool.acquire() context manager, no string interpolation

async def insert_memory(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    guild_id: str | None,
    kind: str,
    fact: str,
    embedding: list[float],   # plain list after register_vector; asyncpg handles codec
    salience: float,
    expires_at: datetime,
) -> int:
    """Insert a new memory row. Returns the new id."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO user_memories
               (user_id, guild_id, kind, fact, embedding, salience, expires_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               RETURNING id""",
            user_id, guild_id, kind, fact, embedding, salience, expires_at,
        )
    return row["id"]

async def search_memories(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    query_embedding: list[float],
    k: int,
) -> list[asyncpg.Record]:
    """Cosine ANN search scoped to user_id. Returns up to k rows."""
    async with pool.acquire() as conn:
        return await conn.fetch(
            """SELECT id, fact, salience, hit_count, created_at, last_seen_at,
                      last_surfaced_at, surface_count,
                      1 - (embedding <=> $2) AS similarity
               FROM user_memories WHERE user_id = $1
               ORDER BY embedding <=> $2 LIMIT $3""",
            user_id, query_embedding, k,
        )
```

**boot-ordering extension pattern** (`bot.py` lines 342–351, with Phase 11 additions):
```python
# Pattern 3 from RESEARCH.md — extension-first, then pool with init=
from pgvector.asyncpg import register_vector

_boot = await asyncpg.connect(
    dsn=config.sanitize_database_url(config.DATABASE_URL),
    ssl="require", statement_cache_size=0,
)
try:
    await _boot.execute("CREATE EXTENSION IF NOT EXISTS vector;")
finally:
    await _boot.close()

async def _register_vector(conn: asyncpg.Connection) -> None:
    await register_vector(conn)

bot.pool = await asyncpg.create_pool(
    dsn=config.sanitize_database_url(config.DATABASE_URL),
    min_size=config.DB_POOL_MIN,
    max_size=config.DB_POOL_MAX,
    command_timeout=config.DB_COMMAND_TIMEOUT_SECONDS,
    ssl='require',
    max_inactive_connection_lifetime=config.DB_MAX_INACTIVE_CONN_LIFETIME,  # K-04: 240s
    statement_cache_size=config.DB_STATEMENT_CACHE_SIZE,                     # K-04: 0
    init=_register_vector,   # ONLY new line vs. current create_pool call
)
await init_db(bot.pool)
```

---

### `bot.py:_initialize_once` (MODIFY — config/wiring, event-driven)

**Analog:** `bot.py` service-wiring block (lines 353–388) + `cache_cleanup`/`ytdlp_update` task pattern.

**Service wiring pattern** (lines 364–388):
```python
# After pool creation and gemini_service init, wire memory_service:
if hasattr(bot, "gemini_service"):
    from services.memory import MemoryService
    bot.memory_service = MemoryService(bot.pool, bot.gemini_service)
    log.info("Memory service initialized")
```

**Daily @tasks.loop pattern** (`bot.py` lines 701–752 — `cache_cleanup` + `ytdlp_update`):
```python
# Template for both daily distill-batch and daily memory-sweep:

@tasks.loop(time=datetime.time(hour=3, minute=0))   # e.g. 3am for distill-batch
async def memory_distill_batch():
    """Daily distill of the day's message-buffer banter into episodic memories."""
    memory_service = getattr(bot, "memory_service", None)
    if memory_service is None:
        return
    # ... iterate active guilds' MessageBuffers, call memory_service.remember() priority 2

@memory_distill_batch.before_loop
async def before_memory_distill_batch():
    await bot.wait_until_ready()

@memory_distill_batch.error
async def on_memory_distill_batch_error(error: Exception) -> None:
    log.error("memory_distill_batch task error: %s", error, exc_info=error)
    await _post_loop_error("memory_distill_batch", error)

# Same pattern for memory_sweep (daily, different hour):
@tasks.loop(time=datetime.time(hour=2, minute=30))
async def memory_sweep():
    """Daily per-user cap eviction + low-salience decay sweep."""
    memory_service = getattr(bot, "memory_service", None)
    if memory_service is None:
        return
    await memory_service.sweep()

@memory_sweep.before_loop
async def before_memory_sweep():
    await bot.wait_until_ready()
```

**Start task guard pattern** (`bot.py` lines 399–406):
```python
if not memory_distill_batch.is_running():
    memory_distill_batch.start()
if not memory_sweep.is_running():
    memory_sweep.start()
```

**Cleanup in `_cleanup_partial_init` pattern** (`bot.py` lines 274–283):
```python
# Add to the loop list in _cleanup_partial_init:
for _loop in (idle_check, cache_cleanup, ytdlp_update, status_rotation,
              memory_distill_batch, memory_sweep):   # <-- add new loops
    try:
        if _loop.is_running():
            _loop.cancel()
    except Exception:
        pass
```

---

### `personality/prompts.py` (MODIFY — utility, transform)

**Analog:** `personality/prompts.py:build_chat_prompt` (lines 91–104)

**Current signature** (line 91):
```python
def build_chat_prompt(mood: str, user_summary: str | None, seasonal: str) -> str:
```

**Backward-compatible kwarg addition pattern** — add `memories=` with `None` default:
```python
def build_chat_prompt(
    mood: str,
    user_summary: str | None,
    seasonal: str,
    memories: list[str] | None = None,   # NEW — None renders byte-identical to today
) -> str:
    """Assemble the full system prompt for /ask."""
    import config

    mood_context = MOOD_CONTEXTS.get(mood, MOOD_CONTEXTS["normal"])
    user_context = user_summary or "No data on this user yet."
    seasonal_context = seasonal if seasonal else ""

    if memories:
        memory_context = (
            "THINGS YOU REMEMBER ABOUT THIS USER (episodes/opinions, not stats):\n"
            + "\n".join(f"- {m}" for m in memories)
            + "\nUse at most one of these, and only if it genuinely lands. "
              "Do NOT invent details beyond these lines. "
              "All numbers/counts come from USER CONTEXT above — never from these memories."
        )
    else:
        memory_context = ""   # empty string → byte-identical (no new whitespace artifact)

    return DEXTER_SYSTEM_PROMPT.format(
        max_length=config.MAX_AI_RESPONSE_LENGTH,
        mood_context=mood_context,
        user_context=user_context,
        seasonal_context=seasonal_context,
        memory_context=memory_context,    # NEW slot added to DEXTER_SYSTEM_PROMPT template
    ).rstrip()
```

**Template slot placement** — in `DEXTER_SYSTEM_PROMPT` string (after line 58):
```python
# After {user_context}, before closing:
USER CONTEXT:
{user_context}

{memory_context}

{seasonal_context}
```

**4 callers compile unchanged** — all existing `build_chat_prompt(mood, user_summary, seasonal)` calls remain valid because `memories` defaults to `None`.

---

### `cogs/ai.py` (MODIFY — controller, request-response)

**Analog:** `cogs/ai.py` `/ask` handler + `cogs/events.py:_generate_ambient_roast`

**Recall wiring pattern** — insert after user_summary lookup, before `build_chat_prompt`:
```python
# Current pattern (cogs/ai.py ~line 119):
system_prompt = build_chat_prompt(mood, user_summary, seasonal)

# Modified pattern — recall() fires off defer (already deferred above):
memories: list[str] = []
memory_service = getattr(self.bot, "memory_service", None)
if memory_service is not None:
    try:
        memories = await memory_service.recall(
            str(interaction.user.id),
            str(interaction.guild_id),
            question,   # the user's /ask query text as the recall anchor
        )
    except Exception as mem_err:
        log.debug(f"memory.recall failed (non-fatal): {mem_err}")

system_prompt = build_chat_prompt(mood, user_summary, seasonal, memories=memories or None)
```

**Graceful degrade pattern** (`cogs/events.py` lines 104–116):
```python
# Always guard with getattr(..., None) — memory_service absent when GEMINI_API_KEY unset
memory_service = getattr(self.bot, "memory_service", None)
if memory_service is None:
    return fallback   # degrade silently
```

---

### `cogs/events.py` (MODIFY — controller, event-driven)

**Analog:** `cogs/events.py:_generate_ambient_roast` (lines 87–116)

**Recall wiring into `_generate_ambient_roast`** — add memories kwarg before `build_chat_prompt` call (see the self-analog pattern above; same placement as /ask). The scenario string (e.g. `"{name} just joined the voice channel"`) doubles as the recall query text after name substitution.

**Notable-event write hook pattern** — fire `remember()` at the already-existing notable-event dispatch sites inside `on_voice_state_update`:
```python
# After the roast line is sent (fire-and-forget, never block the event handler):
memory_service = getattr(self.bot, "memory_service", None)
if memory_service is not None:
    asyncio.create_task(
        memory_service.remember(
            user_id=str(member.id),
            guild_id=str(guild.id),
            raw_text=f"{member.display_name} joined at {local_hour}:00",
            kind="late_night",
            base_salience=0.6,   # placeholder; exact values are 11.3/11.4 detail
        )
    )
```

---

### `cogs/music.py` (MODIFY — controller, event-driven)

**Analog:** `cogs/music.py:_post_music_roast` (~line 1061) and `_build_roast_line` (~line 1073)

**Notable-event write hook pattern** (same `asyncio.create_task` fire-and-forget):
```python
# At the auto-queue ignored-memory site and repeat-song/milestone sites:
memory_service = getattr(self.bot, "memory_service", None)
if memory_service is not None:
    asyncio.create_task(
        memory_service.remember(
            user_id=str(user_id),
            guild_id=str(guild_id),
            raw_text=raw_event_text,   # distiller reduces to an atomic sentence
            kind="repeat_song",        # or "milestone", "auto_queue_ignored"
            base_salience=0.5,         # placeholder; 11.3/11.4 detail
        )
    )
```

**Recall wiring into `_build_roast_line`** — same as `/ask`: recall before `build_chat_prompt`, pass `memories=` kwarg.

---

## Shared Patterns

### Rate limiter clone (for `GeminiService.embed()`)
**Source:** `services/gemini.py` lines 34–49 (`_RateLimiter`) and line 130 (`self._rate_limiter = _RateLimiter()`)
**Apply to:** `services/gemini.py` (add `self._embed_limiter`) + `services/memory.py` (calls `gemini.embed()`)
```python
# In GeminiService.__init__, one new line:
self._embed_limiter = _RateLimiter(max_requests=config.EMBED_RPM_LIMIT)  # ~60 RPM
```

### Async pool query helpers
**Source:** `database.py` lines 179–230 (`log_track_batch`, `get_user_summary`, etc.)
**Apply to:** `database.py` new memory helpers (`insert_memory`, `search_memories`, `bump_memory_hit`, `count_user_memories`, `evict_lowest_salience`, `delete_expired_memories`)
- Always `async with pool.acquire() as conn:`
- Always `$N` parameterized — never string-build SQL
- Transactions only when multiple writes must be atomic

### `asyncio.create_task` fire-and-forget write
**Source:** bot.py `_initialize_once` task pattern + CLAUDE.md "Slash command interactions must respond within 3s"
**Apply to:** all `remember()` calls in cogs — never `await memory_service.remember()` inline; always `asyncio.create_task(memory_service.remember(...))`

### Graceful-degrade / getattr guard
**Source:** `cogs/events.py` line 104 (`gemini_service = getattr(self.bot, "gemini_service", None)`)
**Apply to:** every access to `bot.memory_service` in cogs
```python
memory_service = getattr(self.bot, "memory_service", None)
if memory_service is None:
    ...  # degrade gracefully
```

### `before_loop` + `.error` task decoration
**Source:** `bot.py` lines 725–733 (`cache_cleanup.before_loop` + `cache_cleanup.error`)
**Apply to:** both new `@tasks.loop` tasks (`memory_distill_batch`, `memory_sweep`)

### Pure-logic TDD seam
**Source:** `logic/roasts.py` module docstring convention, `database.py:compute_streak` clock-injectable signature
**Apply to:** `models/memory.py` — all scoring functions take clock as a parameter, no I/O, covered by `tests/test_memory.py`

---

## No Analog Found

No files in this phase lack a codebase analog. All integration points were verified against live code on 2026-06-29 (RESEARCH.md §"Live Codebase Verification").

---

## Metadata

**Analog search scope:** `services/`, `models/`, `logic/`, `bot.py`, `database.py`, `personality/`, `cogs/`
**Files scanned:** 12 (services/gemini.py, models/user_profile.py, logic/roasts.py, logic/health.py, database.py, bot.py, personality/prompts.py, cogs/ai.py, cogs/events.py + 3 secondary reads)
**Pattern extraction date:** 2026-06-29

---

## PATTERN MAPPING COMPLETE

**Phase:** 11 - rag-long-term-memory
**Files classified:** 8
**Analogs found:** 8 / 8

### Coverage
- Files with exact analog: 2 (`services/memory.py` → `services/gemini.py`; `models/memory.py` → `logic/roasts.py` + `database.py:compute_streak`)
- Files with self-analog (modify existing): 6 (`database.py`, `bot.py`, `personality/prompts.py`, `cogs/ai.py`, `cogs/events.py`, `cogs/music.py`)
- Files with no analog: 0

### Key Patterns Identified
- All services are constructed `(pool, gemini_service)` and wired in `bot.py:_initialize_once` as `bot.<name>_service`; accessed in cogs via `getattr(self.bot, "<name>_service", None)` with graceful degrade
- `_RateLimiter(max_requests=...)` is a one-liner clone — the existing class is already parameterized; `_embed_limiter` is a second instance at ~60 RPM, never the shared 15 RPM `_rate_limiter`
- All daily background tasks use `@tasks.loop(time=...)` + `before_loop wait_until_ready` + `.error` handler + `is_running()` guard in `_initialize_once` + cancel in `_cleanup_partial_init`
- `models/memory.py` follows the `logic/` pure-logic convention: no I/O, clock-injectable via `now=` kwarg, all decision math unit-testable without mocks
- `build_chat_prompt` gains `memories: list[str] | None = None`; all 4 existing callers compile unchanged; empty/None renders byte-identical (empty string slot, no new whitespace)
- Every `remember()` call in cogs is wrapped in `asyncio.create_task()` — zero synchronous latency added to any slash interaction
- Boot ordering: throwaway `asyncpg.connect()` → `CREATE EXTENSION` → `close()` → `create_pool(init=_register_vector)` → `init_db()` — the only safe sequence

### File Created
`.planning/phases/11-rag-long-term-memory/11-PATTERNS.md`

### Ready for Planning
Pattern mapping complete. Planner can now reference analog patterns in PLAN.md files.
