# Phase 8: Social & Ops - Research

**Researched:** 2026-06-19
**Domain:** Discord bot social features + ops/observability on top of existing Python/asyncpg/Gemini stack
**Confidence:** HIGH (all findings grounded in actual source files read this session)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**`/roast @user` (SOCIAL-01)**
- D-01: Output is **public**.
- D-02: Anyone is targetable — self-roast, bot/bots, zero-history user each have special lines.
- D-03: Roast data is **global per-user** — reuse `get_user_summary()` as-is.
- D-04: **30s per-invoker cooldown** (no per-target limit).
- D-05: Gemini call at **priority-1** with **guaranteed template fallback** — never block on rate limit.
- D-06: Tone = harsher than ambient, stays about music behavior, no slurs/protected-class content.
- D-07: Prompt = reuse `DEXTER_SYSTEM_PROMPT` + "roast this user" scenario (events.py path), NOT a separate prompt.
- D-08: Respects mood system — reuse existing mood injection like `/ask`.
- D-09: Lives in **`cogs/ai.py`**.

**`/leaderboard` (SOCIAL-02)**
- D-10: Ranking is **per-server (guild-scoped)**.
- D-11: **One embed, three sections**: most songs queued · longest streak · most-skipped songs.
- D-12: "Most-skipped" = **songs (titles)** — rank tracks by skip count.
- D-13: **Top 5 per section + one dry Dexter commentary line** (lowercase, on-brand).
- D-14: Data from **per-guild aggregates from `song_history`** — `user_profiles.total_songs_queued` is GLOBAL, cannot be used for per-guild "most queued."
- D-15: Streak section ranks **users who are active in this guild** by their **global** streak from `user_profiles`.
- D-16: **Ties → secondary sort by oldest `first_seen_at`** (OG ranks higher).
- D-17: Empty/new server → a **dry personality empty-state line**, not an empty embed.
- D-18: **Exclude zeros** — ≥1 queued song or ≥1 skip to appear.
- D-19: Output is **public**.
- D-20: Lives in **`cogs/ops.py`** (new cog).

**`/stats` (OPS-01) + Gemini quota (OPS-03)**
- D-21: **Owner-only** via inline `await bot.is_owner(interaction.user)` check (the `/sync` pattern at `bot.py:437`).
- D-22: **Today-only window** — today's `bot_daily_stats` row.
- D-23: **Add `total_errors` column to `bot_daily_stats`**; increment at `utils/logger.py log_to_discord` / exception handlers. Only net-new persistence this phase.
- D-24: **Gemini RPM headroom** (`X/15`) + today's image-cap usage in `/stats` embed; needs public getter on `_RateLimiter`.
- D-25: `/stats` is **bot-wide / global**.
- D-26: Lives in **`cogs/ops.py`**.

**Rich health & observability (OPS-02)**
- D-27: Rich metrics live **only in `/stats`** — NOT on public `/health`.
- D-28: `/health` returns **`{"status":"degraded","reasons":[...]}`** when DB unreachable / gateway not ready, but stays **HTTP 200** always.
- D-29: Build with **state available today** — leave hooks for Phase-6 pipeline metrics.
- D-30: Host CPU/mem via **linked Koyeb/Neon dashboard** — no `psutil`.
- D-31: A **shared metrics-gatherer helper** feeds both `/stats` and `/health` degraded check.

**Cross-cutting**
- D-32: All user-facing text in **Dexter's voice** — lowercase, dry, one-emoji-max.
- D-33: Error/empty/no-op responses are **ephemeral**; successful public actions stay public.

### Claude's Discretion

- Exact `total_errors` column definition + any new index for leaderboard aggregates (D-23/D-14).
- Exact SQL for per-guild leaderboard aggregates and guild-active global-streak ranking query.
- The rate-limiter public getter signature.
- Embed field layout / ordering for `/stats` and `/leaderboard`; `COLOR_*` choices.
- Slash-command names/parameters; whether `/roast` aliases or `@user` is required.
- Roast scenario wording + self / bot / zero-history special-case lines.
- The shared metrics-gatherer helper's exact home + signature.
- Whether ties need a tertiary sort beyond `first_seen_at`.

### Deferred Ideas (OUT OF SCOPE)

- Most-skipped USERS board (biggest skippers).
- `/stats` 7-day trend / sparkline.
- Rich metrics on public HTTP endpoint / token-gated `/metrics`.
- Non-200 degraded health.
- In-process `psutil` host metrics.
- Phase-6-instrumented pipeline metrics in `/stats` or `/health`.
- Per-target roast cooldown / anti-harassment limit.
- Maximum-savage roast / dedicated roast prompt.
- Switchable leaderboard category view (dropdown/buttons).

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SOCIAL-01 | User can `/roast @user` — personalized roast from tracked history | D-05/D-07/D-09 covered by `_generate_ambient_roast` + `_build_roast_line` patterns; priority-1 + fallback path fully documented |
| SOCIAL-02 | User can view a `/leaderboard` for the server | Concrete SQL provided for all 3 sections; embed builder pattern documented |
| OPS-01 | Owner can view a `/stats` dashboard in Discord | `bot_daily_stats` read pattern + owner check pattern (`bot.py:437`) documented |
| OPS-02 | A health endpoint exposes bot liveness | `_run_health_server` (`bot.py:197`) documented; degraded body spec and metrics helper specified |
| OPS-03 | Gemini and quota/usage observable before limits hit | `_RateLimiter` getter spec + `image_generation_log` query for daily image counts documented |

</phase_requirements>

---

## Summary

Phase 8 is pure brownfield extension — all data already exists in Postgres, all AI/personality infrastructure already runs. There is no new data collection pipeline. The two genuinely new pieces of work are: (1) the per-guild leaderboard SQL aggregates (new queries against existing tables) and (2) the `total_errors` column addition to `bot_daily_stats`.

Every other feature wires together existing infrastructure. `/roast` mirrors the `_generate_ambient_roast` path in `cogs/events.py` and `_build_roast_line` in `cogs/music.py`, running at priority-1 with a 30s cooldown. `/stats` reads the existing `bot_daily_stats` row plus two new getters (rate-limiter RPM count, image log daily total). The `/health` degraded body is a trivial aiohttp handler extension. The shared metrics gatherer is a pure async helper that both `/stats` and `/health` call.

The only moderately complex design decision left for the planner is the `total_errors` increment site: `log_to_discord` in `utils/logger.py` is the central error-log sink, but it is a coroutine that takes `bot` as a parameter — the increment call must not create recursion if Postgres is the thing that is failing. The recursion guard is to check the error reason before trying to increment: if the DB pool is unreachable, skip the `total_errors` increment silently.

**Primary recommendation:** Execute in wave order — Wave 0: schema migration (`total_errors` column + leaderboard index) + tests skeleton; Wave 1: `/roast`; Wave 2: `/leaderboard`; Wave 3: `/stats` + rate-limiter getter; Wave 4: degraded `/health` + shared metrics helper.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `/roast @user` generation | API / Backend (Gemini service) | cogs/ai.py (command layer) | Gemini call with rate-limiter; cog is thin glue |
| `/roast` personality fallback | cogs/ai.py | personality/roasts.py | Fallback pool lives in roasts.py; cog renders it |
| `/leaderboard` SQL aggregates | Database / Storage | cogs/ops.py | New GROUP BY queries against song_history + user_profiles |
| `/leaderboard` embed render | cogs/ops.py | utils/embeds.py | Embed builder in embeds.py; cog drives the call |
| `/stats` daily row read | Database / Storage | cogs/ops.py | Read from bot_daily_stats; owner check in cog |
| Gemini RPM getter | API / Backend (services/gemini.py) | cogs/ops.py (consumer) | Getter lives on _RateLimiter owned by GeminiService |
| `total_errors` increment | API / Backend (utils/logger.py) | database.py | increment_daily_stat is the upsert; call site is log_to_discord |
| `/health` degraded body | API / Backend (bot.py aiohttp) | — | Health server is a module-level aiohttp coroutine in bot.py |
| Shared metrics gatherer | cogs/ops.py (or utils/) | bot.py, database.py | Pure async helper; feeds both /stats and /health |

---

## Standard Stack

### Core (all already in requirements.txt — no new installs)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| discord.py | ≥2.3 (installed) | `app_commands`, `discord.Member`, embed builder | Project mandates this; all cogs use it |
| asyncpg | 0.31.0 (installed) | Parameterized Postgres queries | Project mandates; all DB helpers use it |
| google-genai | installed | `GeminiService.chat()` | Project mandates; AI features use it |
| aiohttp | installed | `_run_health_server` web endpoint | Already wired in `bot.py` |

**No new packages.** Phase 8 adds zero external dependencies.

### Package Legitimacy Audit

No new packages are installed in this phase. This section is not applicable.

---

## Implementation Patterns

### 1. `/roast` Call Flow (SOCIAL-01)

**Authoritative pattern:** `cogs/events.py:92 _generate_ambient_roast` + `cogs/music.py:862 _build_roast_line`.

Key differences for `/roast` vs ambient roast:
- **Priority: 1** (not 2) — user-invoked command, waits up to 60s for a slot.
- **Mood injection** — call `await get_mood(self.bot.pool)` exactly as `/ask` does at `cogs/ai.py:101`.
- **Seasonal context** — call `get_seasonal_context()` and pass it to `build_chat_prompt()` (matches `/ask` pattern).
- **Cooldown: 30s per invoker** — `@app_commands.checks.cooldown(1, 30.0, key=lambda i: i.user.id)`.
- **Target parameter type: `discord.Member`** — enables Discord's built-in user autocomplete; resolves in the same guild [VERIFIED: discordpy docs].

**Exact flow (in `cogs/ai.py`):**

```python
@app_commands.command(name="roast", description="Roast a user based on their music history")
@app_commands.describe(target="The user to roast")
@app_commands.checks.cooldown(1, config.ROAST_COOLDOWN_SECONDS, key=lambda i: i.user.id)
async def roast(self, interaction: discord.Interaction, target: discord.Member) -> None:
    await interaction.response.defer()   # must respond within 3s

    # 1. Resolve edge cases first (D-02)
    if target == self.bot.user or target.bot:
        scenario = "someone tried to roast the bot itself"
        fallback_pool = ROAST_BOT_LINES          # new pool in personality/roasts.py
    elif target.id == interaction.user.id:
        scenario = "someone tried to roast themselves"
        fallback_pool = ROAST_SELF_LINES         # new pool
    else:
        user_summary = await get_user_summary(self.bot.pool, str(target.id))
        if user_summary is None:
            scenario = f"{target.display_name} has no music history in this bot"
            fallback_pool = ROAST_NO_HISTORY_LINES   # new pool
        else:
            scenario = f"roast {target.display_name}: {user_summary}"
            fallback_pool = ROAST_COMMAND_LINES      # new pool (harsher than ambient)

    # 2. Mood + seasonal context injection (D-08) — same as /ask
    mood = await get_mood(self.bot.pool)
    seasonal = get_seasonal_context()
    system_prompt = build_chat_prompt(mood, user_summary, seasonal)

    # 3. Gemini call at priority-1 (D-05) + guaranteed template fallback
    fallback_line = pick_random(fallback_pool)
    if "{name}" in fallback_line:
        fallback_line = fallback_line.format(name=target.display_name)

    try:
        conversation = [{
            "role": "user",
            "content": (
                f"{scenario}. respond with exactly one roast line in your voice — "
                "under 200 characters, lowercase, no preamble. harsher than usual."
            ),
        }]
        result = await self.gemini.chat(system_prompt, conversation, priority=1)
        if result:
            result = result.strip()
            if len(result) > 500:
                result = result[:497] + "..."
            if result and result[0].isupper():
                result = result[0].lower() + result[1:]
            await interaction.followup.send(result)  # public (D-01)
        else:
            await interaction.followup.send(fallback_line)
    except (GeminiRateLimitError, GeminiAPIError):
        await interaction.followup.send(fallback_line)  # guaranteed fallback (D-05)

    # 4. Stats + error logging
    await increment_daily_stat(self.bot.pool, "total_commands")
    await increment_daily_stat(self.bot.pool, "total_ai_queries")
```

**Variable `user_summary` scoping note:** In the self/bot/zero-history branches, `user_summary` is `None`. The `build_chat_prompt(mood, user_summary, seasonal)` call handles `None` correctly — it passes `None` and `build_chat_prompt` renders it as "No data on this user yet." [VERIFIED: `personality/prompts.py:91`].

**New personality pools needed in `personality/roasts.py`:**
- `ROAST_COMMAND_LINES` — harsher than `VOICE_JOIN_ROASTS`, music-behavior only (D-06); 4-6 lines with `{name}` placeholder.
- `ROAST_SELF_LINES` — "roasting yourself, bleak" tone; 3-4 lines.
- `ROAST_BOT_LINES` — Dex turns it back on the invoker; 3-4 lines.
- `ROAST_NO_HISTORY_LINES` — "who even are you"; 3-4 lines with `{name}` placeholder.

**`config.py` addition:** `ROAST_COOLDOWN_SECONDS = 30` (CONTEXT.md already names this constant).

### 2. Leaderboard SQL (SOCIAL-02, D-14/D-15/D-16/D-18)

**Schema ground truth** (verified in `database.py:66-149`):
- `song_history`: `guild_id TEXT`, `user_id TEXT`, `title TEXT`, `was_skipped BOOLEAN`, `queued_at TIMESTAMPTZ`
- `user_profiles`: `user_id TEXT PK`, `username TEXT`, `first_seen_at TIMESTAMPTZ`, `current_streak INTEGER`, `longest_streak INTEGER`
- Index: `idx_history_guild ON song_history(guild_id, queued_at DESC)` — supports the guild-filtered scans.

**Note on username resolution:** `user_profiles.username` is the stored display name (updated on each `/play` via `log_track_batch` → `update_user_profile`). Use this for leaderboard display — do NOT try to resolve via Discord API at render time (async fetch per user is slow and may fail for absent members). [VERIFIED: `database.py:200-208`]

**Query A — Most songs queued (per-guild):**

```sql
-- Groups song_history by user_id within the guild.
-- Ties broken by oldest first_seen_at (OG wins, D-16).
-- up.username is the stored display name.
SELECT
    sh.user_id,
    up.username,
    COUNT(*) AS songs_queued
FROM song_history sh
JOIN user_profiles up USING (user_id)
WHERE sh.guild_id = $1
GROUP BY sh.user_id, up.username
HAVING COUNT(*) >= 1
ORDER BY songs_queued DESC, up.first_seen_at ASC
LIMIT 5
```

Parameterized: `pool.acquire() conn.fetch(sql, guild_id)`.

**Query B — Most-skipped songs (titles, per-guild):**

```sql
-- Groups by normalized title within the guild.
-- was_skipped=true rows only; excludes titles with 0 skips (D-18).
-- Tie-break: count DESC only (no author tie for songs — title is the entity).
SELECT
    title,
    COUNT(*) AS skip_count
FROM song_history
WHERE guild_id = $1
  AND was_skipped = true
GROUP BY title
HAVING COUNT(*) >= 1
ORDER BY skip_count DESC
LIMIT 5
```

**Query C — Longest streak among guild-active users (D-15):**

```sql
-- Step 1: collect DISTINCT user_ids active in this guild
-- Step 2: join to user_profiles for global streak
-- Tie-break: oldest first_seen_at (D-16).
SELECT
    up.user_id,
    up.username,
    up.longest_streak
FROM user_profiles up
WHERE up.user_id IN (
    SELECT DISTINCT user_id
    FROM song_history
    WHERE guild_id = $1
)
  AND up.longest_streak >= 1
ORDER BY up.longest_streak DESC, up.first_seen_at ASC
LIMIT 5
```

**Index recommendation:** A partial index on `song_history(user_id)` WHERE `guild_id = constant` is not possible in Postgres (guild_id varies). The existing `idx_history_guild(guild_id, queued_at DESC)` supports Query A and B's `WHERE guild_id = $1` filter well. For Query C's subquery (`DISTINCT user_id WHERE guild_id = $1`), the existing index is sufficient — the `guild_id` prefix is indexed. No new index needed.

**Empty-state handling (D-17):** Each query returns 0 rows on a new server. The embed builder should check `if not rows` and render a single personality line (e.g., "nobody's done anything worth ranking yet.").

**Three-section embed layout:**

```python
# In utils/embeds.py — new function leaderboard()
def leaderboard(
    songs_rows: list[dict],
    skips_rows: list[dict],
    streaks_rows: list[dict],
) -> discord.Embed:
    embed = discord.Embed(title="Leaderboard", color=COLOR_LEADERBOARD)
    # Section 1: Most queued
    if songs_rows:
        lines = [f"{i+1}. {r['username']} — {r['songs_queued']} songs"
                 for i, r in enumerate(songs_rows)]
        commentary = pick_random(LEADERBOARD_SONGS_COMMENTARY)
        embed.add_field(name="most songs queued", value="\n".join(lines) + f"\n\n{commentary}", inline=False)
    else:
        embed.add_field(name="most songs queued", value="nobody's done anything worth ranking yet.", inline=False)
    # Section 2: Longest streak
    if streaks_rows:
        lines = [f"{i+1}. {r['username']} — {r['longest_streak']} days"
                 for i, r in enumerate(streaks_rows)]
        commentary = pick_random(LEADERBOARD_STREAK_COMMENTARY)
        embed.add_field(name="longest streak", value="\n".join(lines) + f"\n\n{commentary}", inline=False)
    else:
        embed.add_field(name="longest streak", value="no streaks to speak of.", inline=False)
    # Section 3: Most-skipped songs
    if skips_rows:
        lines = [f"{i+1}. {r['title']} — {r['skip_count']} skips"
                 for i, r in enumerate(skips_rows)]
        commentary = pick_random(LEADERBOARD_SKIPS_COMMENTARY)
        embed.add_field(name="most-skipped songs", value="\n".join(lines) + f"\n\n{commentary}", inline=False)
    else:
        embed.add_field(name="most-skipped songs", value="nobody's skipped enough to make the board. yet.", inline=False)
    return embed
```

Discord embed constraints [VERIFIED: discordpy docs]: 25 fields maximum, 1024 chars per field value, 6000 chars total. A 3-field leaderboard embed is well under all limits.

**Commentary pools (new, in `personality/responses.py`):**
- `LEADERBOARD_SONGS_COMMENTARY` — dry roast of the leader (e.g. "the bar was low. {winner} tripped over it anyway.").
- `LEADERBOARD_STREAK_COMMENTARY` — e.g. "dedication. unfortunately.".
- `LEADERBOARD_SKIPS_COMMENTARY` — e.g. "these songs had exactly one chance.".

### 3. Rate-Limiter Public Getter (D-24, OPS-03)

**Current `_RateLimiter` internals** (verified `services/gemini.py:34-86`):

- `self._timestamps: deque[float]` — monotonic timestamps of recent requests
- `self._max_requests: int` — `config.GEMINI_RPM_LIMIT` (15)
- `self._window: float` — 60.0 seconds
- `self._lock: asyncio.Lock` — acquired during `acquire()` and during pruning
- `_clean()` — pops timestamps older than `now - window` (called inside the lock in `acquire()`)

**Proposed getters on `_RateLimiter`:**

```python
def rpm_usage(self) -> int:
    """Return the number of requests made in the current sliding window.

    Calls _clean() to prune stale timestamps before counting, ensuring the
    returned value reflects the window at this moment. Safe to call from the
    async event loop without holding the lock — _clean() + len() on a deque
    are not awaited, and the deque is only mutated inside the lock in acquire().
    Reading len() outside the lock is a benign data race: the value may be
    off by 1 if acquire() fires concurrently, but for a dashboard display
    this is acceptable. If strict accuracy is required, add an asyncio.Lock
    acquire here (but DO NOT use asyncio.Lock.acquire() synchronously from a
    sync method — make this an async method instead).
    """
    self._clean()
    return len(self._timestamps)

def rpm_headroom(self) -> int:
    """Return remaining requests available in the current sliding window."""
    return max(0, self._max_requests - self.rpm_usage())
```

**Recommendation:** Make `rpm_usage()` and `rpm_headroom()` synchronous (not async) since they only call `_clean()` (sync) and read `len()` (sync). The minor race condition is tolerable for a dashboard display. Do NOT add a second `asyncio.Lock` call here — that would require `await` and complicate callers.

**Accessor on `GeminiService`:**

```python
@property
def rpm_usage(self) -> int:
    return self._rate_limiter.rpm_usage()

@property
def rpm_headroom(self) -> int:
    return self._rate_limiter.rpm_headroom()
```

**Usage in `/stats`:**

```python
rpm = self.bot.gemini_service.rpm_usage    # int, current usage
rpm_max = config.GEMINI_RPM_LIMIT          # 15
```

### 4. `total_errors` Column Addition (D-23, OPS-01)

**`bot_daily_stats` schema** (verified `database.py:111-117`):

```sql
CREATE TABLE IF NOT EXISTS bot_daily_stats (
    date                   TEXT PRIMARY KEY,
    total_commands         INTEGER DEFAULT 0,
    total_songs_played     INTEGER DEFAULT 0,
    total_ai_queries       INTEGER DEFAULT 0,
    total_images_generated INTEGER DEFAULT 0
    -- total_errors not yet present
);
```

**`increment_daily_stat` allowlist** (verified `database.py:272-277`):

```python
allowed_fields = {
    "total_commands",
    "total_songs_played",
    "total_ai_queries",
    "total_images_generated",
}
```

**Two changes required:**

1. Add column to `SCHEMA_SQL` in `database.py` — the idempotent approach for a column add is:

```python
# In SCHEMA_SQL (within the SCHEMA_SQL string, added after the CREATE TABLE):
ALTER TABLE bot_daily_stats ADD COLUMN IF NOT EXISTS total_errors INTEGER DEFAULT 0;
```

Note: `CREATE TABLE IF NOT EXISTS ... ALTER TABLE ... ADD COLUMN IF NOT EXISTS` is valid in Postgres 9.6+ and is the project convention (the schema string applies DDL idempotently). The `init_db()` call executes `SCHEMA_SQL` as a multi-statement string — since there are no `$N` params, asyncpg accepts it as one `conn.execute()` call (Pitfall 1, verified `database.py:155-158`).

2. Add `"total_errors"` to the `allowed_fields` set in `increment_daily_stat`:

```python
allowed_fields = {
    "total_commands",
    "total_songs_played",
    "total_ai_queries",
    "total_images_generated",
    "total_errors",              # Phase 8 addition
}
```

**Increment site — `utils/logger.py:log_to_discord`** (verified `utils/logger.py:52-65`):

```python
async def log_to_discord(bot, embed: discord.Embed) -> None:
    """Send an error embed to the Discord error log channel."""
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

**Addition:** after `await channel.send(embed=embed)` (success), call `increment_daily_stat`:

```python
    try:
        await channel.send(embed=embed)
        # Phase 8: count errors surfaced to the Discord log channel
        pool = getattr(bot, "pool", None)
        if pool is not None:
            try:
                from database import increment_daily_stat
                await increment_daily_stat(pool, "total_errors")
            except Exception:
                pass  # never let total_errors tracking break the logger
    except Exception as e:
        log.error(f"Failed to log to Discord error channel: {e}")
```

**Recursion guard:** The increment attempt is inside its own `try/except Exception: pass` block. If Postgres is down, the increment fails silently — it does NOT call `log_to_discord` again, so there is no recursion risk.

**Also increment at `bot.py:on_app_command_error`** (verified `bot.py:396-428`): The global command error handler calls `await bot.log_to_discord(embed)` which will auto-increment via the call above. No additional change needed at the error handler itself — `log_to_discord` is the single central increment site.

### 5. Degraded `/health` + Shared Metrics Helper (OPS-02, D-27/D-28/D-31)

**Current `_run_health_server`** (verified `bot.py:197-229`): Returns `{"status":"ok"}` always; no degraded logic; minimal aiohttp app.

**Shared metrics gatherer helper — home: `cogs/ops.py`:**

```python
async def gather_bot_metrics(bot) -> dict:
    """Collect current bot-state metrics for /stats embed and /health degraded check.

    Returns a dict with keys:
        guild_count: int
        voice_count: int      # active voice connections
        queue_count: int      # guilds with non-empty queues
        uptime_seconds: float # time.monotonic() - bot._start_monotonic
        db_ok: bool           # True if DB pool is reachable
        gateway_ready: bool   # True if bot.is_ready()
        shard_count: int
        degraded_reasons: list[str]  # empty = healthy
    """
    metrics = {
        "guild_count": len(bot.guilds),
        "voice_count": len(bot.voice_clients),
        "queue_count": 0,
        "uptime_seconds": 0.0,
        "db_ok": False,
        "gateway_ready": bot.is_ready(),
        "shard_count": bot.shard_count or 1,
        "degraded_reasons": [],
    }

    # Queue count
    music_cog = bot.cogs.get("MusicCog")
    if music_cog is not None:
        for guild in bot.guilds:
            queue = music_cog.get_queue(guild.id)
            if queue.tracks:
                metrics["queue_count"] += 1

    # Uptime (requires bot._start_monotonic set on startup)
    import time
    if hasattr(bot, "_start_monotonic"):
        metrics["uptime_seconds"] = time.monotonic() - bot._start_monotonic

    # DB probe
    pool = getattr(bot, "pool", None)
    if pool is not None:
        try:
            async with pool.acquire() as conn:
                await conn.execute("SELECT 1")
            metrics["db_ok"] = True
        except Exception:
            metrics["db_ok"] = False
            metrics["degraded_reasons"].append("database unreachable")
    else:
        metrics["degraded_reasons"].append("database pool not initialized")

    if not metrics["gateway_ready"]:
        metrics["degraded_reasons"].append("discord gateway not ready")

    return metrics
```

**Note:** `bot._start_monotonic` must be set at the end of `_initialize_once()` in `bot.py`:

```python
import time
bot._start_monotonic = time.monotonic()
```

**Health handler modification in `bot.py`:**

```python
async def health(request: _aio_web.Request) -> _aio_web.Response:
    # Import here to avoid circular import — bot is module-level
    try:
        from cogs.ops import gather_bot_metrics
        metrics = await gather_bot_metrics(bot)
        reasons = metrics.get("degraded_reasons", [])
    except Exception:
        reasons = ["metrics gatherer unavailable"]

    if reasons:
        body = json.dumps({"status": "degraded", "reasons": reasons})
    else:
        body = '{"status":"ok"}'

    return _aio_web.Response(
        text=body,
        content_type='application/json',
    )   # always HTTP 200 (D-28)
```

Import `json` at top of `bot.py` if not already present.

**Circular import risk:** `cogs/ops.py` imports `bot` indirectly via `self.bot`. The health handler calls `gather_bot_metrics(bot)` with the module-level `bot` instance as argument — no import of the `ops` cog module at load time. The `from cogs.ops import gather_bot_metrics` inside the handler function body fires at request time, after all cogs are loaded. This matches the existing pattern in `bot.py` where cog modules are imported inside function bodies (e.g., `from services.queue_persistence import restore_queues` at line 369). [ASSUMED: no circular import at function-scope import since ops.py doesn't import bot.py at module level]

### 6. `/stats` Embed (OPS-01, OPS-03)

**Daily stats read — new helper in `database.py`:**

```python
async def get_daily_stats_row(pool: asyncpg.Pool) -> dict:
    """Return today's bot_daily_stats row as a dict (all fields, 0 if no row)."""
    today = date.today().isoformat()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT total_commands, total_songs_played, total_ai_queries,"
            "       total_images_generated, total_errors"
            " FROM bot_daily_stats WHERE date = $1",
            today,
        )
    if row is None:
        return {
            "total_commands": 0,
            "total_songs_played": 0,
            "total_ai_queries": 0,
            "total_images_generated": 0,
            "total_errors": 0,
        }
    return dict(row)
```

**Image-cap usage (OPS-03):** The `get_images_today()` helper (verified `database.py:337-345`) counts images for a specific `user_id`. For a global bot-wide daily count for `/stats`, we need:

```sql
SELECT COUNT(*) AS cnt FROM image_generation_log
WHERE generated_at::date = CURRENT_DATE
```

New helper `get_images_today_global(pool)` returns this count.

**Owner check (D-21):** Verified pattern from `bot.py:437`:

```python
if not await bot.is_owner(interaction.user):
    return await interaction.response.send_message(
        "not authorized.", ephemeral=True
    )
```

**`/stats` embed layout in `utils/embeds.py`:**

```python
def stats_embed(
    daily: dict,
    rpm_usage: int,
    rpm_max: int,
    images_today_global: int,
    metrics: dict,   # from gather_bot_metrics
) -> discord.Embed:
    embed = discord.Embed(title="dexter system status", color=COLOR_STATS)

    # Today's activity
    embed.add_field(name="commands today", value=str(daily["total_commands"]), inline=True)
    embed.add_field(name="songs played", value=str(daily["total_songs_played"]), inline=True)
    embed.add_field(name="ai queries", value=str(daily["total_ai_queries"]), inline=True)
    embed.add_field(name="images generated", value=str(daily["total_images_generated"]), inline=True)
    embed.add_field(name="errors logged", value=str(daily["total_errors"]), inline=True)

    # Gemini quota
    embed.add_field(
        name="gemini rpm",
        value=f"{rpm_usage}/{rpm_max}",
        inline=True,
    )
    embed.add_field(
        name="images today (all users)",
        value=f"{images_today_global} total",
        inline=True,
    )

    # Bot state
    uptime_min = int(metrics["uptime_seconds"] // 60)
    embed.add_field(name="uptime", value=f"{uptime_min}m", inline=True)
    embed.add_field(name="guilds", value=str(metrics["guild_count"]), inline=True)
    embed.add_field(name="voice connections", value=str(metrics["voice_count"]), inline=True)
    embed.add_field(name="shards", value=str(metrics["shard_count"]), inline=True)

    # DB + gateway health
    db_status = "ok" if metrics["db_ok"] else "unreachable"
    gw_status = "ready" if metrics["gateway_ready"] else "not ready"
    embed.add_field(name="database", value=db_status, inline=True)
    embed.add_field(name="gateway", value=gw_status, inline=True)

    # Phase-6 hook (D-29)
    # embed.add_field(name="cache hit rate", value="(phase 6)", inline=True)
    # embed.add_field(name="time to first audio", value="(phase 6)", inline=True)

    # Koyeb/Neon dashboard link (D-30)
    embed.set_footer(text="host metrics: koyeb dashboard | neon console")

    return embed
```

Total fields: 14. Well under Discord's 25-field limit. [VERIFIED: discord.py embed limits are 25 fields, 1024 chars/field, 6000 chars total — confirmed from discord.py docs]

**New color constant in `utils/embeds.py`:**
- `COLOR_LEADERBOARD = 0xFFD700` — gold (competitive/social feel)
- `COLOR_STATS = 0x7289DA` — Discord blurple (ops/system feel)

### 7. discord.py 2.x Specifics

**`discord.Member` parameter** [VERIFIED: discordpy docs]: Used in slash commands as a type annotation — Discord shows a user picker in the UI. Resolves to a guild member (has `.display_name`, `.id`, `.bot`). Falls back to `discord.User` if the user left the guild. For `/roast`, use `discord.Member` (guild-scoped).

```python
async def roast(self, interaction: discord.Interaction, target: discord.Member) -> None:
```

**Cooldown per-user key** [VERIFIED: discordpy docs]:

```python
@app_commands.checks.cooldown(1, 30.0, key=lambda i: i.user.id)
```

This applies a per-user (invoker) cooldown globally, consistent with the D-04 requirement.

**Ephemeral response** [VERIFIED: discordpy docs]:

```python
await interaction.response.send_message("error message here", ephemeral=True)
# Or after defer:
await interaction.followup.send("error message here", ephemeral=True)
```

**3-second response rule (CLAUDE.md):** `/roast`, `/leaderboard`, and `/stats` all involve DB queries or Gemini calls. All must `await interaction.response.defer()` first, then use `interaction.followup.send()`.

**Owner check pattern** (confirmed `bot.py:437-438`):

```python
if not await self.bot.is_owner(interaction.user):
    await interaction.response.send_message("not authorized.", ephemeral=True)
    return
await interaction.response.defer(ephemeral=True)  # /stats response is ephemeral (owner only)
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Gemini rate-limit backoff for user commands | Custom wait loop | `_rate_limiter.acquire(priority=1)` + `GeminiRateLimitError` catch | Already handles priority queuing, backoff, and rejection correctly |
| Personality text injection | String concatenation | `build_chat_prompt(mood, user_context, seasonal)` | Handles DEXTER_SYSTEM_PROMPT template, all format vars |
| User taste summary | Manual DB queries | `get_user_summary(pool, user_id)` | Returns ready-to-inject string with all taste data |
| Mood computation | Read + compute manually | `get_mood(pool)` (`models/server_state.py:36`) | Already reads `bot_daily_stats.total_commands` and maps to mood strings |
| Template fallback selection | `random.choice()` inline | `pick_random(pool)` (`personality/responses.py:9`) | Project convention, keeps fallback pools in personality modules |
| Schema migration via raw psql | Manual ALTER outside init_db | `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `SCHEMA_SQL` | `init_db()` already applies SCHEMA_SQL idempotently on every boot |

---

## Common Pitfalls

### Pitfall 1: Using `user_profiles.total_songs_queued` for per-guild leaderboard

**What goes wrong:** `total_songs_queued` on `user_profiles` is a GLOBAL counter (incremented on every `/play` in any server). Using it for the per-guild "most queued" board shows server-wide activity, not this guild's.

**Why it happens:** The field name is misleadingly similar to what we want.

**How to avoid:** Always query `COUNT(*) FROM song_history WHERE guild_id = $1 GROUP BY user_id` (Query A above). `user_profiles.total_songs_queued` is ONLY appropriate for the global milestone roast checks. [VERIFIED: `database.py:200-208`, `CONTEXT.md D-14`]

### Pitfall 2: `increment_daily_stat` allowlist not updated

**What goes wrong:** Calling `await increment_daily_stat(pool, "total_errors")` raises `ValueError: Invalid stat field: total_errors` because `"total_errors"` is not in the hardcoded `allowed_fields` set.

**How to avoid:** Add `"total_errors"` to the set at `database.py:272` before writing any call site. [VERIFIED: `database.py:269-288`]

### Pitfall 3: Priority-2 Gemini call for a user-invoked `/roast`

**What goes wrong:** Using `priority=2` for `/roast` means if 15 other requests are in-flight, the roast is immediately rejected with `GeminiRateLimitError` instead of waiting up to 60s.

**How to avoid:** Use `priority=1` for all user-invoked slash commands (D-05). `priority=2` is for background auto-queue only. [VERIFIED: `services/gemini.py:57-85`]

### Pitfall 4: `asyncio.Lock` inside a sync getter on `_RateLimiter`

**What goes wrong:** If `rpm_usage()` is made async and acquires `self._lock`, calling it from a synchronous context (e.g., a property) causes a `RuntimeError`.

**How to avoid:** Make `rpm_usage()` and `rpm_headroom()` synchronous — they only call `_clean()` (sync) and read `len()`. The benign race condition is acceptable for a dashboard display. [VERIFIED: `services/gemini.py:34-86`]

### Pitfall 5: Recursion in `total_errors` increment

**What goes wrong:** If `increment_daily_stat(pool, "total_errors")` raises an exception (e.g., DB is down), and that exception is logged via `log_to_discord`, which calls `increment_daily_stat` again → infinite recursion.

**How to avoid:** Wrap the `increment_daily_stat` call inside `log_to_discord` in its own `try/except Exception: pass` block. Never let the error counter increment itself cause another error log. [VERIFIED: pattern analysis; `utils/logger.py:52-65`]

### Pitfall 6: Health endpoint degraded body before cogs load

**What goes wrong:** `_run_health_server` starts before `_initialize_once()` completes (K-02 design). If `gather_bot_metrics` is called before the `ops` cog is loaded, the import in the health handler fails or `bot.pool` is `None`.

**How to avoid:** The health handler wraps the `gather_bot_metrics` import and call in a broad `try/except` and falls back to `{"status":"degraded","reasons":["metrics gatherer unavailable"]}`. This is always HTTP 200 and never crashes the health server. [VERIFIED: `bot.py:197-229`, `bot.py:269-349`]

### Pitfall 7: `/stats` defer must be ephemeral

**What goes wrong:** `await interaction.response.defer()` (non-ephemeral) shows the followup message publicly. Owner-only `/stats` output leaks to the channel.

**How to avoid:** Use `await interaction.response.defer(ephemeral=True)` for `/stats`. [VERIFIED: discord.py docs, D-27]

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact on Phase 8 |
|---|---|---|---|
| SQLite aiosqlite | PostgreSQL asyncpg | Phase 4 | All new queries use asyncpg pool.acquire() + $N params |
| Oracle A1 hosting | Koyeb + Neon | Phase 5 | D-30: no psutil; Neon pool has 5-min scale-to-zero (Neon pool tuning already in config.py K-04) |
| `cogs/library.py` did not exist | Phase 7 added `cogs/library.py` | Phase 7 | Load `cogs.ops` alongside it in `_initialize_once` |
| No persistent views | Phase 7 added `NowPlayingView` registered in `setup_hook` | Phase 7 | `cogs/ops.py` has no persistent views — no `setup_hook` registration needed |

---

## Runtime State Inventory

This is a code + schema extension phase (not a rename/refactor), so this section covers only the one net-new persistence change.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `bot_daily_stats` table missing `total_errors` column | `ALTER TABLE bot_daily_stats ADD COLUMN IF NOT EXISTS total_errors INTEGER DEFAULT 0` in `SCHEMA_SQL`; existing rows get `DEFAULT 0` automatically |
| Live service config | No changes to env vars, Koyeb config, or n8n workflows | None |
| OS-registered state | No task scheduler, no PM2 config changes | None |
| Secrets/env vars | No new secrets; `GEMINI_API_KEY`, `DATABASE_URL`, `ERROR_LOG_CHANNEL_ID`, `OWNER_ID` all pre-existing | None |
| Build artifacts | No new packages; no egg-info changes | None |

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL (Neon) | All DB queries | ✓ (live on Neon) | 16 | degraded /health body |
| discord.py ≥2.3 | All slash commands | ✓ (installed) | ≥2.3 | — |
| google-genai | /roast Gemini call | ✓ (installed) | installed | template fallback (D-05) |
| aiohttp | /health server | ✓ (installed, in bot.py) | installed | — |
| asyncpg 0.31.0 | All DB helpers | ✓ (installed) | 0.31.0 | — |

**Missing dependencies with no fallback:** None.

---

## Validation Architecture

Nyquist validation is enabled (no explicit `false` in `.planning/config.json`).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | None detected (uses conftest.py fixtures) |
| Quick run command | `pytest tests/test_database_phase8.py -x` |
| Full suite command | `pytest tests/ -x` |
| Live DB run | `TEST_DATABASE_URL=... pytest tests/test_database_phase8.py` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | Notes |
|--------|----------|-----------|-------------------|-------|
| SOCIAL-01 | `/roast` template fallback fires when Gemini raises `GeminiRateLimitError` | unit | `pytest tests/test_roast_command.py::test_roast_template_fallback -x` | Mock `GeminiService.chat` to raise; verify fallback line returned |
| SOCIAL-01 | self-roast, bot-roast, zero-history branches each return a line | unit | `pytest tests/test_roast_command.py::test_roast_edge_cases -x` | Pure logic, no DB needed |
| SOCIAL-01 | `/roast` calls `gemini.chat()` at priority=1 | unit | `pytest tests/test_roast_command.py::test_roast_uses_priority_1 -x` | Inspect mock call args |
| SOCIAL-01 | Roast tone/voice quality (lowercase, on-brand) | human-UAT | — | Subjective; cannot be automated |
| SOCIAL-02 | `songs_queued` query returns correct per-guild count, excludes other guilds | integration (live DB) | `pytest tests/test_database_phase8.py::test_leaderboard_songs_guild_scoped -x` | Insert rows for 2 guilds; verify only guild_id=$1 rows counted |
| SOCIAL-02 | `skips` query counts only `was_skipped=true` rows | integration (live DB) | `pytest tests/test_database_phase8.py::test_leaderboard_skips_filter -x` | Insert mix of skipped/not; verify count |
| SOCIAL-02 | Streak query returns only users active in guild | integration (live DB) | `pytest tests/test_database_phase8.py::test_leaderboard_streak_guild_scoped -x` | Insert history for user in guild A; verify user not returned for guild B |
| SOCIAL-02 | Tie-break by oldest `first_seen_at` (D-16) | integration (live DB) | `pytest tests/test_database_phase8.py::test_leaderboard_tie_break -x` | Two users, same count, different first_seen_at; verify ordering |
| SOCIAL-02 | Empty server → empty result lists | integration (live DB) | `pytest tests/test_database_phase8.py::test_leaderboard_empty_guild -x` | Query guild with no history; verify 0 rows |
| SOCIAL-02 | Embed visual layout (field labels, section order) | human-UAT | — | Subjective; must be seen in Discord |
| OPS-01 | `total_errors` column exists after `init_db` | integration (live DB) | `pytest tests/test_database_phase8.py::test_total_errors_column_exists -x` | Check `information_schema.columns` |
| OPS-01 | `increment_daily_stat("total_errors")` upserts correctly | integration (live DB) | `pytest tests/test_database_phase8.py::test_total_errors_increment -x` | Call twice; verify count=2 |
| OPS-01 | `get_daily_stats_row` returns 0 for all fields when no row exists | integration (live DB) | `pytest tests/test_database_phase8.py::test_get_daily_stats_row_empty -x` | New test DB; verify dict with 0s |
| OPS-01 | `/stats` embed only visible to owner (ephemeral) | human-UAT | — | Must be tested in live Discord |
| OPS-02 | `/health` returns `{"status":"ok"}` when DB reachable + gateway ready | integration | `pytest tests/test_health_endpoint.py::test_health_ok -x` | Mock bot with pool+is_ready; verify response body |
| OPS-02 | `/health` returns `{"status":"degraded","reasons":["database unreachable"]}` when pool fails | integration | `pytest tests/test_health_endpoint.py::test_health_degraded_db -x` | Mock pool to raise on execute; verify degraded body |
| OPS-02 | `/health` always returns HTTP 200 | integration | `pytest tests/test_health_endpoint.py::test_health_always_200 -x` | Verify status code with db down |
| OPS-03 | `rpm_usage()` returns correct count after N acquires | unit | `pytest tests/test_rate_limiter.py::test_rpm_usage_getter -x` | Add to existing test file |
| OPS-03 | `rpm_headroom()` = `GEMINI_RPM_LIMIT - rpm_usage()` | unit | `pytest tests/test_rate_limiter.py::test_rpm_headroom_getter -x` | Add to existing test file |

### Wave 0 Gaps

- [ ] `tests/test_database_phase8.py` — leaderboard SQL integration tests (3 queries × test cases above)
- [ ] `tests/test_roast_command.py` — `/roast` unit tests (mock Gemini, edge cases)
- [ ] `tests/test_health_endpoint.py` — degraded `/health` integration tests

Extend existing files:
- [ ] `tests/test_rate_limiter.py` — add `test_rpm_usage_getter` and `test_rpm_headroom_getter`

Framework install: pytest + pytest-asyncio already present (existing test suite confirmed running).

Conftest.py `pool` fixture already drops and recreates tables — new `test_database_phase8.py` can use it directly. The `conftest.py` `DROP TABLE` list at `tests/conftest.py:43` does NOT need to be updated — `bot_daily_stats` is already dropped there, and the new column is part of the same table.

### Sampling Rate

- **Per task commit:** `pytest tests/test_database_phase8.py tests/test_roast_command.py tests/test_rate_limiter.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | — |
| V3 Session Management | No | — |
| V4 Access Control | Yes | `await bot.is_owner(interaction.user)` for `/stats` (inline check, no decorator — project pattern) |
| V5 Input Validation | Yes | All SQL uses asyncpg `$N` parameterized queries — no string interpolation of user input |
| V6 Cryptography | No | — |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via `title` in leaderboard GROUP BY | Tampering | asyncpg `$N` params throughout; `title` is read-back, never interpolated |
| `total_errors` field name injection in `increment_daily_stat` | Tampering | Allowlist validation already present in `increment_daily_stat`; adding `"total_errors"` to the allowlist is the correct extension pattern |
| Internal bot state leak via public `/health` | Information Disclosure | D-27: rich metrics in `/stats` only (owner-only ephemeral); `/health` body stays `ok` or `degraded` with generic reasons only |
| Owner check bypass on `/stats` | Elevation of Privilege | `await bot.is_owner(interaction.user)` uses `bot.owner_id` wired at `create_bot()` via `config.OWNER_ID` (verified `bot.py:80`); the check is authoritative |
| Roast target injection (mentions, embed formatting) | Spoofing | `allowed_mentions=discord.AllowedMentions.none()` on public send; `target.display_name` is a string, not a mention tag |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | No circular import at function-scope `from cogs.ops import gather_bot_metrics` inside health handler | Section 5 (Degraded /health) | Import would fail at first health request; fix: move helper to `utils/` instead of `cogs/ops.py` |
| A2 | `conftest.py` `pool` fixture teardown drops `bot_daily_stats` (covering the new `total_errors` column) without schema changes needed | Validation Architecture | If teardown doesn't handle the new column, integration tests may leave dirty state; fix: teardown drops whole table, not individual columns — this is safe |

**Both assumptions are LOW risk.** A1's fallback (move `gather_bot_metrics` to `utils/metrics.py`) is documented explicitly. A2 is safe because `DROP TABLE` removes columns implicitly.

---

## Sources

### Primary (HIGH confidence — verified in source files this session)

- `database.py` (read entire file) — schema, `increment_daily_stat`, `init_db`, all helper signatures
- `services/gemini.py` (read entire file) — `_RateLimiter` internals, `GeminiService.chat()` signature
- `cogs/events.py` (read entire file) — `_generate_ambient_roast` exact flow and fallback pattern
- `cogs/ai.py` (read entire file) — `/ask` call flow, mood injection, stat increment sites
- `models/user_profile.py` (read entire file) — `get_user_summary()` return format
- `personality/prompts.py` (read entire file) — `DEXTER_SYSTEM_PROMPT`, `build_chat_prompt()`, `MOOD_CONTEXTS`
- `personality/roasts.py` (read entire file) — existing template pools and voice constraints
- `personality/responses.py` (read entire file) — `pick_random()`, existing pools for reference
- `bot.py` (read lines 1-452) — `_run_health_server`, `on_app_command_error`, `/sync` owner check, `_initialize_once`, cog loading
- `utils/logger.py` (read entire file) — `log_to_discord` signature and body
- `utils/embeds.py` (read entire file) — embed builders, `COLOR_*` constants
- `config.py` (read entire file) — all constants, `GEMINI_RPM_LIMIT`, `MAX_IMAGES_PER_USER_PER_DAY`
- `models/server_state.py` (read entire file) — `get_mood()` call pattern
- `cogs/music.py:835-923` (read roast helper section) — `_build_roast_line` exact signature
- `tests/conftest.py` (read entire file) — pool fixture, teardown, DSN pattern
- `tests/test_database_phase4.py` (read entire file) — integration test style
- `tests/test_rate_limiter.py` (read entire file) — existing rate limiter test style

### Secondary (MEDIUM confidence — from official docs via Context7)

- `/websites/discordpy_readthedocs_io_en` [VERIFIED: discordpy docs] — `discord.Member` slash param, `@app_commands.checks.cooldown(key=...)`, ephemeral response, embed limits (25 fields / 1024 chars / 6000 total)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; all existing dependencies confirmed in source
- Architecture: HIGH — all patterns grounded in actual source files read this session
- SQL queries: HIGH — schema verified line-by-line in `database.py`
- Rate-limiter getter: HIGH — `_RateLimiter` internals fully read; getter design is additive
- `total_errors` migration: HIGH — `increment_daily_stat` allowlist and `SCHEMA_SQL` verified
- Pitfalls: HIGH — all derived from actual source code contradictions and CONTEXT.md warnings
- discord.py 2.x API: MEDIUM (HIGH source, but embed total-char limit not explicitly in Context7 docs returned — 6000 is from CLAUDE.md + training knowledge)

**Research date:** 2026-06-19
**Valid until:** 2026-07-19 (stable Python/asyncpg stack; discord.py API stable)
