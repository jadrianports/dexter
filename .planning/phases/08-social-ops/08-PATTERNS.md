# Phase 8: Social & Ops - Pattern Map

**Mapped:** 2026-06-19
**Files analyzed:** 11 new/modified files + 4 test files
**Analogs found:** 11 / 11 (all have strong codebase analogs)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `cogs/ops.py` (NEW) | cog / controller | request-response + CRUD | `cogs/library.py` (cog skeleton) + `bot.py:437` (owner check) | role-match |
| `cogs/ai.py` (MODIFY) | cog / controller | request-response | `cogs/ai.py` `/ask` command (same file) | exact |
| `database.py` (MODIFY) | data access | CRUD | `database.py` `increment_daily_stat` + `get_daily_command_count` | exact |
| `services/gemini.py` (MODIFY) | service | request-response | `services/gemini.py` `_RateLimiter._clean()` (same file) | exact |
| `bot.py` (MODIFY) | entrypoint / middleware | request-response | `bot.py:197` `_run_health_server` (same file) | exact |
| `utils/embeds.py` (MODIFY) | utility | transform | `utils/embeds.py` `queue_list()` + `COLOR_*` constants (same file) | exact |
| `utils/logger.py` (MODIFY) | utility | event-driven | `utils/logger.py:52` `log_to_discord` (same file) | exact |
| `personality/roasts.py` (MODIFY) | personality | transform | `personality/roasts.py` `VOICE_JOIN_ROASTS` pool (same file) | exact |
| `personality/responses.py` (MODIFY) | personality | transform | `personality/responses.py` `AUTO_QUEUE_ANNOUNCE` pool (same file) | exact |
| `config.py` (MODIFY) | config | — | `config.py` `ASK_COOLDOWN_SECONDS` block (same file) | exact |
| `utils/metrics.py` OR `cogs/ops.py` helper (NEW) | utility | request-response | `bot.py:269` `_initialize_once` bot-state reads + `database.py` pool pattern | role-match |
| `tests/test_database_phase8.py` (NEW) | test | CRUD | `tests/test_database_phase4.py` integration style | exact |
| `tests/test_roast_command.py` (NEW) | test | request-response | `tests/test_rate_limiter.py` unit mock style | role-match |
| `tests/test_health_endpoint.py` (NEW) | test | request-response | `tests/test_rate_limiter.py` async unit style | role-match |
| `tests/test_rate_limiter.py` (EXTEND) | test | — | same file — add 2 test methods to existing `TestRateLimiter` class | exact |

---

## Pattern Assignments

### `cogs/ops.py` (NEW — `/leaderboard` + `/stats` + `gather_bot_metrics`)

**Analogs:** `cogs/library.py` (cog skeleton), `bot.py:434-438` (owner-check), `cogs/ai.py:77-90` (bot property accessors)

**Cog skeleton / imports pattern** (`cogs/library.py` lines 28-45):
```python
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
from database import (
    # import the new helpers added in database.py
)
from personality.responses import pick_random, LEADERBOARD_SONGS_COMMENTARY, ...
from utils.embeds import leaderboard_embed, stats_embed
from utils.logger import log
```

**Cog class + bot accessors** (`cogs/ai.py` lines 77-89):
```python
class OpsCog(commands.Cog):
    """Handles /leaderboard and /stats."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def pool(self):
        return self.bot.pool
```

**Owner-only check pattern** (`bot.py` lines 437-438):
```python
if not await self.bot.is_owner(interaction.user):
    await interaction.response.send_message("not authorized.", ephemeral=True)
    return
await interaction.response.defer(ephemeral=True)   # /stats must be ephemeral (D-27/Pitfall 7)
```

**3s-defer pattern for DB-backed slash commands** (`cogs/ai.py` line 97):
```python
await interaction.response.defer()   # public for /leaderboard; ephemeral for /stats
```

**setup() function pattern** (`cogs/ai.py` lines 257-258, `cogs/library.py`):
```python
async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OpsCog(bot))
```

**Cog registration in `bot.py:_initialize_once`** (line 324 pattern — add `"cogs.ops"` alongside `"cogs.library"`):
```python
for _ext in ("cogs.music", "cogs.help", "cogs.events", "cogs.library", "cogs.ops"):
    if _ext not in bot.extensions:
        await bot.load_extension(_ext)
```

**`gather_bot_metrics` home:** Place as a module-level async function in `cogs/ops.py` (not a method). Import it inside `bot.py`'s health handler at call time (function-scope import) to avoid circular import — same pattern as `bot.py:369` `from services.queue_persistence import restore_queues`.

---

### `cogs/ai.py` — add `/roast` command (MODIFY)

**Analog:** `/ask` command in the same file (`cogs/ai.py` lines 93-138) + `cogs/events.py:92` `_generate_ambient_roast`

**Imports to add** (at top of `cogs/ai.py`, alongside existing imports):
```python
from personality.roasts import (
    ROAST_COMMAND_LINES,
    ROAST_SELF_LINES,
    ROAST_BOT_LINES,
    ROAST_NO_HISTORY_LINES,
)
```

**Cooldown decorator pattern** (`cogs/ai.py` line 95 — existing `/ask` uses a simpler form; `/roast` needs per-user key):
```python
@app_commands.command(name="roast", description="Roast a user based on their music history")
@app_commands.describe(target="The user to roast")
@app_commands.checks.cooldown(1, config.ROAST_COOLDOWN_SECONDS, key=lambda i: i.user.id)
async def roast(self, interaction: discord.Interaction, target: discord.Member) -> None:
    await interaction.response.defer()   # public response (D-01)
```

**Mood + seasonal injection pattern** (copy from `cogs/ai.py` lines 101-113 — `/ask`):
```python
mood = await get_mood(self.bot.pool)
user_summary = await get_user_summary(self.bot.pool, str(target.id))
seasonal = get_seasonal_context()
system_prompt = build_chat_prompt(mood, user_summary, seasonal)
```

**Gemini call at priority=1 with guaranteed fallback** (from `cogs/ai.py` lines 114-137 + `cogs/events.py` lines 104-161):
```python
try:
    result = await self.gemini.chat(system_prompt, conversation, priority=1)
    if result:
        result = result.strip()
        if len(result) > 500:
            result = result[:497] + "..."
        if result and result[0].isupper():
            result = result[0].lower() + result[1:]
        await interaction.followup.send(result,
            allowed_mentions=discord.AllowedMentions.none())
    else:
        await interaction.followup.send(fallback_line,
            allowed_mentions=discord.AllowedMentions.none())
except (GeminiRateLimitError, GeminiAPIError):
    await interaction.followup.send(fallback_line,
        allowed_mentions=discord.AllowedMentions.none())
```

**Stats increment pattern** (`cogs/ai.py` lines 130-131):
```python
await increment_daily_stat(self.bot.pool, "total_commands")
await increment_daily_stat(self.bot.pool, "total_ai_queries")
```

**Edge-case branching pattern** (from `cogs/events.py` lines 104-161 `_generate_ambient_roast`):
```python
# Resolve edge cases first (D-02), BEFORE mood/Gemini setup
if target == self.bot.user or target.bot:
    scenario = "someone tried to roast the bot itself"
    fallback_pool = ROAST_BOT_LINES
elif target.id == interaction.user.id:
    scenario = "someone tried to roast themselves"
    fallback_pool = ROAST_SELF_LINES
else:
    user_summary = await get_user_summary(self.bot.pool, str(target.id))
    if user_summary is None:
        scenario = f"{target.display_name} has no music history in this bot"
        fallback_pool = ROAST_NO_HISTORY_LINES
    else:
        scenario = f"roast {target.display_name}: {user_summary}"
        fallback_pool = ROAST_COMMAND_LINES

fallback_line = pick_random(fallback_pool)
if "{name}" in fallback_line:
    fallback_line = fallback_line.format(name=target.display_name)
```

**Note on `user_summary` scoping:** In the `bot`/self/zero-history branches, `user_summary` is `None`. `build_chat_prompt(mood, None, seasonal)` handles `None` correctly per `personality/prompts.py:91`.

**`allowed_mentions` guard:** Always pass `allowed_mentions=discord.AllowedMentions.none()` on the public `/roast` followup send — `target.display_name` is safe but the security model calls for none().

---

### `database.py` (MODIFY)

**Analogs:** `database.py:111-117` (SCHEMA_SQL block), `database.py:269-288` (`increment_daily_stat`), `database.py:300-320` (existing fetch helpers)

**`total_errors` column — add to SCHEMA_SQL** after the `bot_daily_stats` CREATE TABLE block (line 117). The `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` pattern is idempotent and accepted by asyncpg in a no-`$N`-param multi-statement string (`database.py:152-157`):
```python
SCHEMA_SQL = """
...existing tables...

ALTER TABLE bot_daily_stats ADD COLUMN IF NOT EXISTS total_errors INTEGER DEFAULT 0;
"""
```

**`increment_daily_stat` allowlist extension** (`database.py` lines 272-277 — add one entry):
```python
allowed_fields = {
    "total_commands",
    "total_songs_played",
    "total_ai_queries",
    "total_images_generated",
    "total_errors",              # Phase 8 addition (D-23)
}
```

**New `get_daily_stats_row` helper** — copy pattern from existing `get_daily_command_count` (line 348 area), which uses `conn.fetchrow` + today's ISO date as `$1`:
```python
async def get_daily_stats_row(pool: asyncpg.Pool) -> dict:
    today = date.today().isoformat()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT total_commands, total_songs_played, total_ai_queries,"
            "       total_images_generated, total_errors"
            " FROM bot_daily_stats WHERE date = $1",
            today,
        )
    if row is None:
        return {"total_commands": 0, "total_songs_played": 0,
                "total_ai_queries": 0, "total_images_generated": 0,
                "total_errors": 0}
    return dict(row)
```

**New leaderboard aggregate helper — Query A** (per-guild songs, `pool.acquire()` + `$N` params, `conn.fetch` returns a list of `Record`):
```python
async def get_leaderboard_songs(pool: asyncpg.Pool, guild_id: str) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT sh.user_id, up.username, COUNT(*) AS songs_queued"
            " FROM song_history sh"
            " JOIN user_profiles up USING (user_id)"
            " WHERE sh.guild_id = $1"
            " GROUP BY sh.user_id, up.username"
            " HAVING COUNT(*) >= 1"
            " ORDER BY songs_queued DESC, up.first_seen_at ASC"
            " LIMIT 5",
            guild_id,
        )
```

**Query B (most-skipped songs)** — same `conn.fetch` + `$1` pattern, `was_skipped = true` filter.

**Query C (streak board)** — same pattern, subquery to filter guild-active users.

**New `get_images_today_global` helper** — copy from `get_images_today` (line 337) but without `user_id` filter:
```python
async def get_images_today_global(pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) AS cnt FROM image_generation_log"
            " WHERE generated_at::date = CURRENT_DATE"
        )
    return row["cnt"] if row else 0
```

---

### `services/gemini.py` (MODIFY)

**Analog:** `_RateLimiter._clean()` method in the same file (lines 51-55)

**Public getters to add on `_RateLimiter`** (synchronous — see Pitfall 4 in RESEARCH.md):
```python
def rpm_usage(self) -> int:
    """Current request count in the sliding window (benign race — acceptable for dashboard)."""
    self._clean()
    return len(self._timestamps)

def rpm_headroom(self) -> int:
    """Remaining request slots in the current sliding window."""
    return max(0, self._max_requests - self.rpm_usage())
```

**Properties to add on `GeminiService`** (after `__init__`, before `chat()`):
```python
@property
def rpm_usage(self) -> int:
    return self._rate_limiter.rpm_usage()

@property
def rpm_headroom(self) -> int:
    return self._rate_limiter.rpm_headroom()
```

**Usage in `cogs/ops.py`:**
```python
rpm = self.bot.gemini_service.rpm_usage   # int
rpm_max = config.GEMINI_RPM_LIMIT         # 15
```

---

### `bot.py` (MODIFY)

**Analog:** `bot.py:197-229` `_run_health_server` (same file) + `bot.py:369` function-scope import pattern

**Degraded health handler** — replace the inner `health` coroutine (lines 205-209) with:
```python
async def health(request: _aio_web.Request) -> _aio_web.Response:
    import json as _json
    try:
        from cogs.ops import gather_bot_metrics
        metrics = await gather_bot_metrics(bot)
        reasons = metrics.get("degraded_reasons", [])
    except Exception:
        reasons = ["metrics gatherer unavailable"]

    if reasons:
        body = _json.dumps({"status": "degraded", "reasons": reasons})
    else:
        body = '{"status":"ok"}'

    return _aio_web.Response(
        text=body,
        content_type='application/json',
    )  # always HTTP 200 (D-28)
```

**`_start_monotonic` — add to `_initialize_once`** at the end of the function (after `restore_queues`):
```python
import time as _time
bot._start_monotonic = _time.monotonic()
```

**Circular import guard:** The `from cogs.ops import gather_bot_metrics` import lives inside the `health()` function body — fires at request time, not import time. This is the same function-scope import pattern used at `bot.py:369` (`from services.queue_persistence import restore_queues`). The `ops` cog module does NOT import `bot.py` at its module level, so no cycle.

---

### `utils/embeds.py` (MODIFY)

**Analog:** `utils/embeds.py:75-111` `queue_list()` (multi-section embed with field adds) and `utils/embeds.py:1-16` (COLOR constants block)

**New color constants** (add after line 16):
```python
COLOR_LEADERBOARD = 0xFFD700   # gold — competitive/social
COLOR_STATS = 0x7289DA         # Discord blurple — ops/system
```

**`leaderboard_embed` function** — copy `queue_list()` structural pattern (create Embed, conditional `add_field` calls, lines 82-111):
```python
def leaderboard_embed(
    songs_rows: list,
    skips_rows: list,
    streaks_rows: list,
) -> discord.Embed:
    embed = discord.Embed(title="leaderboard", color=COLOR_LEADERBOARD)
    # Section 1 — most queued (add_field inline=False for each section)
    if songs_rows:
        lines = [f"{i+1}. {r['username']} — {r['songs_queued']} songs"
                 for i, r in enumerate(songs_rows)]
        commentary = pick_random(LEADERBOARD_SONGS_COMMENTARY)
        embed.add_field(name="most songs queued",
                        value="\n".join(lines) + f"\n\n{commentary}",
                        inline=False)
    else:
        embed.add_field(name="most songs queued",
                        value="nobody's done anything worth ranking yet.", inline=False)
    # ... repeat pattern for streaks_rows and skips_rows
    return embed
```

**`stats_embed` function** — copy the `add_field(inline=True)` grid pattern from `now_playing()` (lines 43-45):
```python
def stats_embed(daily: dict, rpm_usage: int, rpm_max: int,
                images_today_global: int, metrics: dict) -> discord.Embed:
    embed = discord.Embed(title="dexter system status", color=COLOR_STATS)
    embed.add_field(name="commands today", value=str(daily["total_commands"]), inline=True)
    # ... 14 fields total (verified under Discord's 25-field limit)
    embed.set_footer(text="host metrics: koyeb dashboard | neon console")
    return embed
```

**Import `pick_random`** at the top of `utils/embeds.py` — add alongside existing imports:
```python
from personality.responses import pick_random, LEADERBOARD_SONGS_COMMENTARY, \
    LEADERBOARD_STREAK_COMMENTARY, LEADERBOARD_SKIPS_COMMENTARY
```

---

### `utils/logger.py` (MODIFY)

**Analog:** `utils/logger.py:52-65` `log_to_discord` (same file — modify in-place)

**Current body** (lines 52-65):
```python
async def log_to_discord(bot, embed: discord.Embed) -> None:
    if not config.ERROR_LOG_CHANNEL_ID:
        return
    channel = bot.get_channel(config.ERROR_LOG_CHANNEL_ID)
    if not channel:
        return
    try:
        await channel.send(embed=embed)
    except Exception as e:
        log.error(f"Failed to log to Discord error channel: {e}")
```

**Modified body** — add `total_errors` increment after the successful send (Pitfall 5: inner try/except prevents recursion):
```python
    try:
        await channel.send(embed=embed)
        # Phase 8: track errors surfaced to Discord (D-23)
        pool = getattr(bot, "pool", None)
        if pool is not None:
            try:
                from database import increment_daily_stat
                await increment_daily_stat(pool, "total_errors")
            except Exception:
                pass  # never let counter tracking break the logger
    except Exception as e:
        log.error(f"Failed to log to Discord error channel: {e}")
```

---

### `personality/roasts.py` (MODIFY)

**Analog:** `personality/roasts.py:41-60` `VOICE_JOIN_ROASTS` pool (same file) — copy list structure, `{name}` placeholder convention, voice constraints in the module docstring

**New pools to add** (after existing pools, same file structure):
```python
# ---------------------------------------------------------------------------
# /roast command pools (Phase 8 — SOCIAL-01)
# Harsher than ambient; stays about music behavior (D-06).
# 4-6 lines each. {name} placeholder for .format() at call site.
# ---------------------------------------------------------------------------

ROAST_COMMAND_LINES: list[str] = [
    # Copy voice constraints: lowercase, ≤500 chars, one-emoji max, {name} ok
    ...  # 4-6 harsher-than-ambient lines
]

ROAST_SELF_LINES: list[str] = [
    # "roasting yourself, bleak" tone
    ...  # 3-4 lines
]

ROAST_BOT_LINES: list[str] = [
    # Dex turns it back on the invoker (no {name} needed here)
    ...  # 3-4 lines
]

ROAST_NO_HISTORY_LINES: list[str] = [
    # "who even are you" — {name} placeholder
    ...  # 3-4 lines with {name}
]
```

**Export via `__all__`** — add all four new pool names to the existing `__all__` list (lines 20-34).

---

### `personality/responses.py` (MODIFY)

**Analog:** `personality/responses.py:21-38` `AUTO_QUEUE_ANNOUNCE` + `AUTO_QUEUE_IGNORED` pools (same file) — copy list-of-strings structure

**New pools to add**:
```python
# ---------------------------------------------------------------------------
# /leaderboard commentary pools (Phase 8 — SOCIAL-02, D-13)
# ---------------------------------------------------------------------------

LEADERBOARD_SONGS_COMMENTARY: list[str] = [
    # dry roast of the leader — lowercase, on-brand
    ...  # 3-4 lines, may include {winner} placeholder
]

LEADERBOARD_STREAK_COMMENTARY: list[str] = [
    ...  # 3-4 lines
]

LEADERBOARD_SKIPS_COMMENTARY: list[str] = [
    ...  # 3-4 lines
]

# ---------------------------------------------------------------------------
# /leaderboard empty-state (D-17)
# ---------------------------------------------------------------------------
LEADERBOARD_EMPTY: list[str] = [
    "nobody's done anything worth ranking yet.",
    ...
]
```

---

### `config.py` (MODIFY)

**Analog:** `config.py:32-35` cooldown constants block, `config.py:37-40` AI constants block

**New constants to add** (in the Cooldowns block, adjacent to `ASK_COOLDOWN_SECONDS = 5`):
```python
ROAST_COOLDOWN_SECONDS = 30          # Phase 8: /roast per-invoker cooldown (D-04)
LEADERBOARD_TOP_N = 5                # Phase 8: top-N per section (D-13)
```

---

## Shared Patterns

### Authentication / Owner Check
**Source:** `bot.py` lines 437-438
**Apply to:** `/stats` command in `cogs/ops.py`
```python
if not await self.bot.is_owner(interaction.user):
    await interaction.response.send_message("not authorized.", ephemeral=True)
    return
await interaction.response.defer(ephemeral=True)
```

### 3-Second Defer Rule
**Source:** `cogs/ai.py` line 97
**Apply to:** ALL three new slash commands (`/roast`, `/leaderboard`, `/stats`) — all involve DB or Gemini calls
```python
await interaction.response.defer()          # /roast, /leaderboard (public)
await interaction.response.defer(ephemeral=True)  # /stats (owner-only)
```

### Ephemeral Error Responses
**Source:** `bot.py:401-406` (cooldown error), `cogs/ai.py` pattern (D-33)
**Apply to:** All error/no-op paths in new commands
```python
await interaction.followup.send("error message", ephemeral=True)
# OR before defer:
await interaction.response.send_message("error", ephemeral=True)
```

### asyncpg Query Pattern
**Source:** `database.py` lines 184-208 (transaction) and lines 228-234 (simple fetch)
**Apply to:** All three new leaderboard queries + `get_daily_stats_row` + `get_images_today_global`
```python
async with pool.acquire() as conn:
    rows = await conn.fetch("SELECT ... WHERE field = $1", param)
# $N positional params only — no string interpolation of user input
```

### Gemini Priority + Fallback
**Source:** `cogs/events.py` lines 113-160 (`_generate_ambient_roast`) + `cogs/ai.py` lines 114-137
**Apply to:** `/roast` command in `cogs/ai.py`
- User commands: `priority=1`
- Background auto-queue: `priority=2`
- Always wrap in `try/except (GeminiRateLimitError, GeminiAPIError)` with `pick_random(fallback_pool)` fallback

### `allowed_mentions` Guard
**Source:** `cogs/events.py` lines 184, 220, 239 (all public ambient sends)
**Apply to:** All public sends in `/roast` (target's display_name could contain formatted text)
```python
await interaction.followup.send(line, allowed_mentions=discord.AllowedMentions.none())
```

### Personality Voice Enforcement
**Source:** `cogs/events.py` lines 146-153
**Apply to:** All Gemini responses before sending (lowercase first char, 500-char truncation)
```python
result = result.strip()
if len(result) > 500:
    result = result[:497] + "..."
if result and result[0].isupper():
    result = result[0].lower() + result[1:]
```

---

## No Analog Found

All Phase 8 files have strong codebase analogs. No "no analog" entries.

| File | Notes |
|------|-------|
| `gather_bot_metrics()` helper | No existing metrics gatherer, but pattern pieces exist: `bot.py` `len(bot.guilds)`, `len(bot.voice_clients)`, `pool.acquire()` probe — stitch from those. Place in `cogs/ops.py` as module-level async function, import inside `bot.py` health handler at call time. |

---

## Metadata

**Analog search scope:** `cogs/`, `database.py`, `services/gemini.py`, `utils/`, `personality/`, `bot.py`, `config.py`, `tests/`
**Files read:** 15 source files
**Pattern extraction date:** 2026-06-19

### Key Pitfalls (from RESEARCH.md — enforce in planning tasks)
1. **`total_songs_queued` is GLOBAL** — leaderboard "most queued" MUST use `COUNT(*) FROM song_history WHERE guild_id = $1`, never `user_profiles.total_songs_queued`.
2. **`increment_daily_stat` allowlist** — add `"total_errors"` to `allowed_fields` set BEFORE writing any call site or it raises `ValueError`.
3. **`priority=1` for `/roast`** — user-invoked command waits up to 60s; `priority=2` rejects immediately if >10s wait.
4. **`rpm_usage()` must be synchronous** — `_RateLimiter._lock` is an `asyncio.Lock`; do NOT add a second acquire in a sync getter.
5. **Recursion guard in `log_to_discord`** — wrap the `increment_daily_stat` call in its own `try/except Exception: pass` so a DB-down scenario does not loop.
6. **`/stats` defer must be ephemeral** — `interaction.response.defer(ephemeral=True)` or the owner dashboard leaks publicly.
7. **Circular import guard** — `from cogs.ops import gather_bot_metrics` belongs inside the `health()` function body in `bot.py`, not at module level.
