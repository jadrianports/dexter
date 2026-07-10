# Phase 19: Onboarding & Admin Setup - Pattern Map

**Mapped:** 2026-07-10
**Files analyzed:** 12 (3 new, 9 modified)
**Analogs found:** 12 / 12

## Ruff / CI ruleset (report per task instructions)

`pyproject.toml`:
```toml
[tool.ruff]
target-version = "py311"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "W", "I"]
ignore = []

[tool.ruff.lint.per-file-ignores]
"tests/*.py" = ["F401"]
```
`E`/`W` pycodestyle, `F` pyflakes (unused imports/names — enforced everywhere except
`tests/*.py`), `I` isort ordering. `.github/workflows/ci.yml` runs `ruff check .` and
`ruff format --check .` as separate **blocking** steps before `pytest -q`. Run
`ruff check .` + `ruff format .` locally before considering any task done. 120-col line
length is generous — match the existing verbose-docstring style (e.g.
`logic/guild_config.py`'s module docstring) rather than compressing.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `cogs/admin.py` | controller (slash-command group) | request-response | `cogs/memory.py` (`MemoryCog`, `Group` idiom) | exact |
| `database.py` (ALTER + RETURNING insert + toggle get/set) | model / DB helper | CRUD | `database.py::get_proactive_opt_out`/`set_proactive_opt_out` + `seed_guild_config_if_absent` | exact |
| `services/guild_config.py` (surface kwarg, `home_guild_id`, toggle writes) | service | CRUD + cache | itself (Phase 18 baseline, extend in place) | exact |
| `logic/guild_config.py` (`AmbientSurface` enum + surface kwarg) | pure logic | transform | itself (Phase 18 baseline) + `logic/proactive.py` (enum/gate convention) | exact |
| `bot.py` (`on_guild_join`/`on_guild_remove`/backfill/startup narrowing) | event handler (glue) | event-driven | `bot.py::seed_home_guild` call site + `_post_startup_messages` (existing) | exact |
| `cogs/events.py` (reaction gate, per-surface split) | event handler (glue) | event-driven | itself (Phase 18 `on_message` baseline) | exact |
| `cogs/music.py` (`_post_music_roast` → `resolve_ambient_channel`) | controller/glue | event-driven | `cogs/events.py`'s existing `resolve_ambient_channel(..., surface=...)` call sites (once added) | role-match |
| `cogs/help.py` (admin section) | controller | request-response | itself (`COMMANDS_INFO` list) | exact |
| `tests/test_database_phase19.py` | test | CRUD (DB) | `tests/test_database_phase18.py` | exact |
| `tests/test_guild_lifecycle_logic.py` (or appended to `test_guild_config_logic.py`) | test | transform | `tests/test_guild_config_logic.py` + `tests/test_proactive_logic.py` (mock-free gate test shape) | exact |
| `tests/test_guild_config_logic.py` (surface kwarg update) | test | transform | itself | exact |
| `tests/test_guild_config_service.py` / `tests/test_proactive_events.py` (surface-kwarg regressions) | test | transform/event | itself | exact |

## Pattern Assignments

### `cogs/admin.py` (controller, request-response)

**Analog:** `cogs/memory.py` (`MemoryCog`, `Group` idiom, lines 230-309) + `cogs/ops.py:247-254` (permission-first discipline)

**Imports pattern** (mirror `cogs/memory.py` top-of-file, adapt names):
```python
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
import database
from logic.guild_config import AmbientSurface
```

**Group + guild_only + default_permissions (Group-level ONLY — verified inert on subcommands)**
(from RESEARCH.md finding #2, `cogs/memory.py:238` attribute-style idiom):
```python
class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    setup_group = app_commands.Group(
        name="setup",
        description="configure dexter for this server",
        guild_only=True,                                            # D-09, server-enforced
        default_permissions=discord.Permissions(manage_guild=True),  # UI hint ONLY — never the gate
    )
```

**Inline permission-check-first discipline** (`cogs/ops.py:251-254`, adapted to `manage_guild`
per RESEARCH.md finding #4 — `interaction.permissions.manage_guild`, not
`interaction.user.guild_permissions`):
```python
    @setup_group.command(name="channel", description="pick dexter's ambient channel")
    @app_commands.describe(channel="the text channel dexter should post in")
    async def setup_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        # Defense-in-depth (D-09) — belt-and-suspenders for guild_only=True
        if interaction.guild is None:
            return
        # Inline permission gate FIRST — before any data access (mirrors ops.py:252)
        if not interaction.permissions.manage_guild:
            await interaction.response.send_message(
                "nice try. go find someone with manage server.", ephemeral=True
            )
            return
        # D-06: validate send_messages BEFORE writing, refuse loudly on failure —
        # the one deliberate break from the "silence over wrong output" convention.
        if not channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(
                f"can't post in {channel.mention} — i don't have send messages there.",
                ephemeral=True,
            )
            return
        # ... write row via database helper, push-invalidate via
        # self.bot.guild_config._refresh_cache_entry(row), D-05 full-config echo ...
```

**Ephemeral self-scoped reply + `AllowedMentions.none()`** (`cogs/memory.py:261-267`):
```python
        await interaction.response.send_message(
            "...",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
```

**Toggle subcommand shape** — mirror `cogs/memory.py:291-320`'s `memory_callbacks` (Choice-based
on|off), applied to `setup roasts` / `setup vision`:
```python
    @setup_group.command(name="roasts", description="turn ambient roasts on or off")
    @app_commands.describe(setting="on to enable, off to disable")
    @app_commands.choices(
        setting=[
            app_commands.Choice(name="on", value="on"),
            app_commands.Choice(name="off", value="off"),
        ]
    )
    async def setup_roasts(
        self, interaction: discord.Interaction, setting: app_commands.Choice[str]
    ) -> None:
        if interaction.guild is None:
            return
        if not interaction.permissions.manage_guild:
            await interaction.response.send_message(
                "nice try. go find someone with manage server.", ephemeral=True
            )
            return
        # D-07: accepted even with no channel yet — gap named in the reply
        ...
```

**Setup skeleton at load** — `setup(bot)` function pattern (every cog file ends this way,
see `cogs/help.py:49-51`):
```python
async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
```
Then add `"cogs.admin"` to the extension tuple at `bot.py:449`
(`for _ext in ("cogs.music", "cogs.help", "cogs.events", "cogs.library", "cogs.ops", "cogs.memory")`).

---

### `database.py` — new helpers (model, CRUD)

**Analog A — `RETURNING`-based insert-if-absent** (D-14). Sibling to
`seed_guild_config_if_absent` (`database.py:425-464`) — do NOT change that function's contract
(it has its own live-DB idempotency test at `tests/test_database_phase18.py:138-161`):
```python
async def insert_guild_config_if_absent(
    pool: asyncpg.Pool, *, guild_id: str
) -> asyncpg.Record | None:
    """INSERT-RETURNING sibling to seed_guild_config_if_absent (D-14).

    Returns the freshly-inserted Record on a genuine insert, None on conflict
    (row already existed). Unlike seed_guild_config_if_absent this does NOT
    set ambient_channel_id or configured=true — on_guild_join/backfill rows
    are born configured=false with both toggles at their column defaults
    (D-10/D-20).
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "INSERT INTO guild_config (guild_id) VALUES ($1)"
            " ON CONFLICT (guild_id) DO NOTHING"
            " RETURNING guild_id, ambient_channel_id, configured, silenced,"
            "           is_blocked, joined_at, updated_at,"
            "           ambient_roasts_enabled, vision_roasts_enabled",
            guild_id,
        )
```

**Analog B — toggle get/set upsert-helper shape** (mirrors `database.py:369-400`
`get_proactive_opt_out`/`set_proactive_opt_out`, but this is a plain `UPDATE` since the row
always already exists by the time `/setup` runs — unlike the `user_profiles` upsert):
```python
async def set_ambient_roasts_enabled(pool: asyncpg.Pool, *, guild_id: str, enabled: bool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE guild_config SET ambient_roasts_enabled = $2, updated_at = now()"
            " WHERE guild_id = $1",
            guild_id,
            enabled,
        )
```
(Sibling `set_vision_roasts_enabled` identical shape, different column. Getters are unnecessary
if `/setup` reads from `bot.guild_config.get(guild_id)`'s cached row post-refresh — mirror
`GuildConfigService.get()` rather than adding a redundant DB getter, per the "cog never
re-derives, service owns cache" convention.)

**Analog C — `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` idiom** (D-20; mirrors
`bot_daily_stats.total_errors` Phase 8 / `user_profiles.proactive_opt_out` Phase 16, and the
`guild_config` table block itself at `database.py:199-212`):
```python
-- Phase 19: per-guild ambient toggles (ONBOARD-04). Both default TRUE so every
-- pre-existing row (the home guild) keeps today's exact behavior unchanged
-- (CONFIG-05's promise) — the default-vision-OFF *policy* lives in /setup
-- channel's first-configure write path, NOT in the column default (D-20).
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS ambient_roasts_enabled BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS vision_roasts_enabled BOOLEAN NOT NULL DEFAULT true;
```
Append to `SCHEMA_SQL` string (plain param-free DDL, one `conn.execute()` call in `init_db` —
the asyncpg multi-statement rule, `database.py:216-222`). Do not touch
`seed_guild_config_if_absent`'s SELECT column list unless it also needs the two new columns for
the home-guild seed path to see them (it likely does — extend the `SELECT` there too, matching
`load_all_guild_configs`'s column list at `database.py:403-422`, which must ALSO grow the two
new columns since it feeds the boot-time cache).

---

### `services/guild_config.py` (service, CRUD + cache)

**Analog:** itself — extend the existing `GuildConfigService` in place, following its own
established idioms exactly.

**Surface kwarg on `resolve_ambient_channel`** (extends `services/guild_config.py:124-160`):
```python
def resolve_ambient_channel(
    self, guild: discord.Guild, *, surface: AmbientSurface
) -> discord.TextChannel | None:
    """STRICT, cache-only ambient-channel resolver (D-01), now surface-keyed (D-22).

    Dispatches on logic.guild_config.decide_ambient_channel(config_row=row, surface=surface)
    — does not re-derive the toggle branch here (Phase 10 D-02 convention).
    """
    row = self.get(guild.id)
    channel_id = decide_ambient_channel(config_row=row, surface=surface)
    if channel_id is None:
        return None
    # ... existing guild.get_channel / permissions_for(send_messages) checks unchanged ...
```

**`home_guild_id` attribute** (D-24) — set inside `seed_home_guild`
(`services/guild_config.py:104-118`), mirroring how `_cache` is set in `__init__`:
```python
def __init__(self, pool: asyncpg.Pool, bot) -> None:
    self.pool = pool
    self._bot = bot
    self._cache: dict[str, asyncpg.Record] = {}
    self.home_guild_id: str | None = None   # D-24 — set only by seed_home_guild

async def seed_home_guild(self, *, guild_id, ambient_channel_id) -> None:
    row = await database.seed_guild_config_if_absent(...)
    if row is not None:
        self._refresh_cache_entry(row)
    self.home_guild_id = str(guild_id)   # set even on ON CONFLICT DO NOTHING — the seed still resolved
```

**Toggle write + push-invalidate methods** (D-03/D-22) — mirror the `_refresh_cache_entry`
call already used by `seed_home_guild`; `/setup` calls the DB helper then this:
```python
async def set_ambient_roasts_enabled(self, *, guild_id: str, enabled: bool) -> None:
    await database.set_ambient_roasts_enabled(self.pool, guild_id=guild_id, enabled=enabled)
    row = await database.get_guild_config_row(self.pool, guild_id=guild_id)  # or re-fetch via existing helper
    if row is not None:
        self._refresh_cache_entry(row)
```

---

### `logic/guild_config.py` (pure logic, transform)

**Analog:** itself (Phase 18 baseline, `decide_ambient_channel`/`is_ambient_channel`) +
`logic/proactive.py`'s enum/pure-gate convention (no discord/asyncio/datetime/random).

**`AmbientSurface` enum** (mirrors `logic/roasts.py::RoastScenario` per RESEARCH.md Pattern 1):
```python
import enum


class AmbientSurface(enum.Enum):
    """Which ambient behavior category a call site belongs to (D-22)."""

    ROAST = "roast"       # ambient_roasts_enabled: voice roasts, proactive callbacks,
                           # repeat-song + milestone roasts, emoji reactions, moved-channel complaint
    VISION = "vision"      # vision_roasts_enabled: image roasts only
    PRESENCE = "presence"  # ambient_roasts_enabled (same column as ROAST, D-18); distinct
                           # member for startup message (home-guild-only, D-23) + idle-loneliness
```

**Surface-keyed `decide_ambient_channel`** (extends `logic/guild_config.py:34-74` — required
keyword-only, no default, per the anti-pattern warning against optional-with-default):
```python
def decide_ambient_channel(*, config_row: Mapping | None, surface: AmbientSurface) -> int | None:
    if config_row is None:
        return None
    if not config_row.get("configured", False):
        return None
    toggle_column = "vision_roasts_enabled" if surface is AmbientSurface.VISION else "ambient_roasts_enabled"
    if not config_row.get(toggle_column, True):   # fail-open default=True mirrors column DEFAULT true
        return None
    channel_id = config_row.get("ambient_channel_id")
    if channel_id is None:
        return None
    try:
        return int(channel_id)
    except (TypeError, ValueError):
        return None
```

**Surface-keyed `is_ambient_channel`** (extends `logic/guild_config.py:82-101`, same shape,
thread `surface` through to `decide_ambient_channel`):
```python
def is_ambient_channel(*, config_row: Mapping | None, channel_id: int, surface: AmbientSurface) -> bool:
    decided = decide_ambient_channel(config_row=config_row, surface=surface)
    return decided is not None and decided == channel_id
```

**Pure "should I welcome" decision** (D-26, new function for `test_guild_lifecycle_logic.py`,
mirrors `logic/proactive.py::should_fire_proactive_callback`'s pure/keyword-only shape):
```python
def should_welcome_guild(*, inserted_row: object | None) -> bool:
    """Pure wrapper naming the D-14 rule: welcome iff the INSERT actually inserted.

    Deliberately trivial — the substance is the anti-pattern it encodes (never
    derive this from a cache-miss check, see RESEARCH.md Pitfall 3).
    """
    return inserted_row is not None
```

---

### `bot.py` (event handler / glue, event-driven)

**Analog:** existing `seed_home_guild` call site (`bot.py:407-440`) for insert-then-refresh
shape; existing `_post_startup_messages` (`bot.py:514-536`) for the try/except-per-guild loop
shape to narrow (Pitfall 2) and to model `on_guild_remove`'s notify-and-continue shape on.

**`on_guild_join` skeleton** (D-10/D-13/D-16; from RESEARCH.md Code Examples, verified against
`services/guild_config.py`'s own `_refresh_cache_entry` seam):
```python
@bot.event
async def on_guild_join(guild: discord.Guild) -> None:
    row = await database.insert_guild_config_if_absent(bot.pool, guild_id=str(guild.id))
    if row is not None:
        bot.guild_config._refresh_cache_entry(row)

    welcome_posted = False
    try:
        channel = bot.guild_config.resolve_announce_channel(guild)
        if channel is not None:
            await channel.send(WELCOME_LINE, allowed_mentions=discord.AllowedMentions.none())
            welcome_posted = True
        else:
            log.warning("on_guild_join: no writable channel found in guild %s", guild.id)
    except discord.HTTPException as exc:
        log.warning("on_guild_join: welcome send failed in guild %s: %s", guild.id, exc)

    embed = discord.Embed(title=f"joined: {guild.name}", color=0x2ECC71)
    embed.add_field(name="guild id", value=f"`{guild.id}`", inline=True)
    embed.add_field(name="members", value=str(guild.member_count), inline=True)
    embed.add_field(name="owner", value=f"{guild.owner or 'unknown'} (`{guild.owner_id}`)", inline=False)
    embed.add_field(name="created", value=discord.utils.format_dt(guild.created_at, "R"), inline=True)
    embed.add_field(name="total guilds", value=str(len(bot.guilds)), inline=True)
    embed.add_field(name="welcome posted", value="yes" if welcome_posted else "no", inline=True)
    await bot.log_to_discord(embed)
```

**`on_guild_remove`** (D-12 — notify + cache-evict only, NO row delete):
```python
@bot.event
async def on_guild_remove(guild: discord.Guild) -> None:
    bot.guild_config._cache.pop(str(guild.id), None)   # evict only — no DB write (D-12)
    embed = discord.Embed(title=f"removed: {guild.name}", color=0xE74C3C)
    embed.add_field(name="guild id", value=f"`{guild.id}`", inline=True)
    embed.add_field(name="total guilds", value=str(len(bot.guilds)), inline=True)
    await bot.log_to_discord(embed)
```

**Boot backfill** — insert immediately after the existing home-guild seed `try/except` closes
(`bot.py:440`), before `# Phase 4: Queue persistence service` at `:442` (RESEARCH.md finding #6
exact insertion point). Reuses `insert_guild_config_if_absent` + the same welcome path as
`on_guild_join` — **decision keyed on the insert's own return value, never `bot.guild_config.get()`**
(Pitfall 3):
```python
    for guild in bot.guilds:
        try:
            row = await database.insert_guild_config_if_absent(bot.pool, guild_id=str(guild.id))
        except Exception as exc:
            log.warning("Boot backfill insert failed for guild %s: %s", guild.id, exc)
            continue
        if row is None:
            continue  # already had a row — not a new join, no welcome (D-14)
        bot.guild_config._refresh_cache_entry(row)
        # ... same try/except welcome-send + owner-notice-summary as on_guild_join ...
```

**`_post_startup_messages` narrowed to home guild** (D-23 — a BEHAVIOR CHANGE to existing
Phase 18 code, Pitfall 2). Existing loop at `bot.py:527-536`:
```python
# BEFORE (Phase 18): for guild in bot.guilds: ...
# AFTER (D-23):
    home_guild = bot.get_guild(int(bot.guild_config.home_guild_id)) if bot.guild_config.home_guild_id else None
    if home_guild is not None:
        try:
            channel = bot.guild_config.resolve_ambient_channel(home_guild, surface=AmbientSurface.PRESENCE)
            if channel:
                await channel.send(
                    _pick_random(STARTUP_MESSAGES),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except Exception as exc:
            log.warning("Startup message post failed for home guild %s: %s", home_guild.id, exc)
```
Idle-loneliness at `bot.py:747` stays per-guild — only add `surface=AmbientSurface.PRESENCE` to
its existing `resolve_ambient_channel(guild)` call, no loop-narrowing.

---

### `cogs/events.py` (event handler / glue, event-driven)

**Analog:** itself — the existing `on_message` (`cogs/events.py:378-420`) is both the pattern
to preserve (separate independent conditionals) and the code being fixed (D-21 reaction gate,
D-22 surface split).

**D-21 — gate `_handle_message_reactions`** (currently unconditional at `:395`, before either
ambient gate is computed at `:402`):
```python
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        if hasattr(self.bot, "message_buffer"):
            self.bot.message_buffer.add(...)  # unchanged

        # D-22: each surface resolves its own predicate independently — do NOT
        # reuse a single `in_ambient_channel` across gates (retires WR-02).
        roast_channel_ok = message.guild is not None and is_ambient_channel(
            config_row=self.bot.guild_config.get(message.guild.id),
            channel_id=message.channel.id,
            surface=AmbientSurface.ROAST,
        )
        vision_channel_ok = message.guild is not None and is_ambient_channel(
            config_row=self.bot.guild_config.get(message.guild.id),
            channel_id=message.channel.id,
            surface=AmbientSurface.VISION,
        )

        # D-21: reactions now gated — closes the CONFIG-04 hole
        if roast_channel_ok:
            await self._handle_message_reactions(message)

        if roast_channel_ok:
            await self._maybe_fire_proactive_callback(message)

        if vision_channel_ok and message.attachments:
            await self._maybe_fire_vision_roast(message)
```

**Three voice-roast resolve sites** (`cogs/events.py:222`, `:266`, `:311`) — add
`surface=AmbientSurface.ROAST` to each existing
`self.bot.guild_config.resolve_ambient_channel(guild)` call, no other change:
```python
channel = self.bot.guild_config.resolve_ambient_channel(guild, surface=AmbientSurface.ROAST)
```

---

### `cogs/music.py` (controller/glue, event-driven) — LIVE GAP, not a kwarg add

**Analog:** `cogs/events.py`'s (post-fix) `resolve_ambient_channel(..., surface=ROAST)` call
shape — `_post_music_roast` currently does NOT call the config seam at all (RESEARCH.md
Summary finding #1 / Pitfall 1). It calls the pre-Phase-18 `_get_text_channel` fallback
(`cogs/music.py:973`, used at `:1170`).

**Fix** (`cogs/music.py:1168-1176`):
```python
    async def _post_music_roast(self, guild: discord.Guild, line: str) -> None:
        # Phase 19 / D-18: route through the config seam like every other ambient
        # surface — was self._get_text_channel(guild), the pre-Phase-18 fallback
        # that ignores /setup and configured=false (a live CONFIG-04 hole).
        channel = self.bot.guild_config.resolve_ambient_channel(guild, surface=AmbientSurface.ROAST)
        if channel is None:
            return
        ...
```
Call sites feeding `_post_music_roast` are unchanged (`:1311` repeat-song, `:1342`/`:1381`
milestones) — they already pass `(interaction.guild, line)`. Per D-26/RESEARCH finding #9, this
is untested-by-design glue (no existing test locks `_post_music_roast`'s resolution behavior) —
structural review only, matching every other roast dispatch site.

---

### `cogs/help.py` (controller, request-response)

**Analog:** itself — `COMMANDS_INFO` list (`cogs/help.py:9-23`) + `help_command`
(`cogs/help.py:32-46`). Additive change only.

**D-25 admin section**:
```python
ADMIN_COMMANDS_INFO = [
    ("/setup channel <#channel>", "Pick where dexter posts (admin only)"),
    ("/setup roasts <on|off>", "Toggle ambient roasts (admin only)"),
    ("/setup vision <on|off>", "Toggle image roasts (admin only)"),
]

# in help_command, after the existing Commands field:
admin_lines = [f"**`{cmd}`** — {desc}" for cmd, desc in ADMIN_COMMANDS_INFO]
embed.add_field(name="Admin", value="\n".join(admin_lines), inline=False)
```

---

### `tests/test_database_phase19.py` (test, CRUD)

**Analog:** `tests/test_database_phase18.py` (full file structure, lines 1-80+ read) — mirror
exactly:
- Same `_SKIP_LIVE` / `TEST_DATABASE_URL` skip-guard block (lines 20-40).
- A `TestGuildConfigSchemaShape`-equivalent static class asserting
  `"ambient_roasts_enabled" in database.SCHEMA_SQL` and
  `"vision_roasts_enabled" in database.SCHEMA_SQL` (inverse of Phase 18's own
  `test_guild_config_no_phase19_columns` guard — that Phase 18 test intentionally asserts
  these columns are ABSENT; Phase 19 does not touch that test, it is a permanent regression
  lock for Phase 18's scope, and this phase's own file asserts them PRESENT).
- `test_boot_helpers_exist` equivalent: `hasattr(database, "insert_guild_config_if_absent")`.
- Live-DB tests: insert-if-absent returns a `Record` on first call, `None` on second call for
  the same `guild_id` (the D-14 core contract); toggle get/set round-trip.

### `tests/test_guild_lifecycle_logic.py` (test, transform) or appended to
`tests/test_guild_config_logic.py`

**Analog:** `tests/test_guild_config_logic.py` (mock-free direct calls) +
`tests/test_proactive_logic.py`'s boundary-testing shape for `should_fire_proactive_callback`
(gate-by-gate table tests). Apply the same shape to `should_welcome_guild` and to every
`decide_ambient_channel`/`is_ambient_channel` call now requiring `surface=`.

---

## Shared Patterns

### Pure-logic seam discipline (Phase 10 D-02, extended by every P16/17/18 module)
**Source:** `logic/proactive.py`, `logic/vision.py`, `logic/guild_config.py`
**Apply to:** `logic/guild_config.py`'s new `AmbientSurface` + surface-keyed functions
```python
# No random, asyncio, datetime, or discord imports. Keyword-only args. Dispatches
# on Mapping/primitive inputs the caller (service or glue) computed/fetched.
```

### Cog → service → model layering; cogs never construct services
**Source:** `cogs/memory.py` (`self.bot.pool`, no `MemoryService()` construction in the cog),
`bot.py:413-416` (`bot.guild_config = GuildConfigService(...)`)
**Apply to:** `cogs/admin.py` — reach `self.bot.guild_config` / `self.bot.pool`, never
instantiate `GuildConfigService` locally.

### Inline permission-check-first discipline
**Source:** `cogs/ops.py:251-254`
**Apply to:** Every `/setup` subcommand — the `manage_guild` check must be the first
statement (after the `interaction.guild is None` guard), before any DB read.

### Ephemeral in-persona refusal + `AllowedMentions.none()`
**Source:** `cogs/memory.py:254-267`, `cogs/ops.py:253`
**Apply to:** Non-admin refusal (D-08), all `/setup` echoes (D-05), welcome message send.

### Idempotent DDL — `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
**Source:** `database.py` `SCHEMA_SQL` (Phase 8 `total_errors`, Phase 16
`proactive_opt_out`, and the `guild_config` block itself at `:199-212`)
**Apply to:** The two new `guild_config` boolean columns (D-20). Append to `SCHEMA_SQL`,
never a separate migration file — `init_db()` applies the whole string in one
`conn.execute()` (asyncpg multi-statement, param-free rule).

### `INSERT ... ON CONFLICT DO NOTHING RETURNING` for insert-if-absent signaling
**Source:** RESEARCH.md finding #3, sibling to `database.py::seed_guild_config_if_absent`
**Apply to:** `database.py::insert_guild_config_if_absent` — the single new pattern this
phase introduces; every other DB helper in this phase (toggle get/set) reuses existing
upsert/plain-UPDATE shapes already in the codebase.

### Push-invalidate cache after every write
**Source:** `services/guild_config.py::_refresh_cache_entry` (`:92-98`), called from
`seed_home_guild` (`:104-118`)
**Apply to:** `/setup channel`'s write, `/setup roasts|vision`'s toggle writes,
`on_guild_join`'s insert, boot backfill's insert.

## No Analog Found

None — every file in scope has a direct or role-match analog already in the codebase; this
phase is explicitly "glue work over a seam Phase 18 already built" (RESEARCH.md Summary).

## Metadata

**Analog search scope:** `cogs/`, `services/`, `logic/`, `database.py`, `bot.py`, `tests/`
**Files scanned:** `cogs/memory.py`, `cogs/ops.py`, `cogs/help.py`, `cogs/events.py`,
`cogs/music.py` (targeted), `database.py` (targeted ranges), `services/guild_config.py` (full),
`logic/guild_config.py` (full), `logic/proactive.py` (full), `bot.py` (targeted range 400-540),
`tests/test_database_phase18.py` (targeted)
**Pattern extraction date:** 2026-07-10
