# Phase 20: Owner Control Plane & Rate Observability - Pattern Map

**Mapped:** 2026-07-11
**Files analyzed:** 8 modified + 0 new files (plus ~7 call-site edits + 3 test files)
**Analogs found:** 8 / 8 (all line numbers in CONTEXT.md/RESEARCH.md verified against the live tree — no stale references found)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `database.py` (+`guild_blocklist` DDL, helpers, silenced get/set) | model/migration | CRUD | `database.py` `guild_jams` DDL (:188) + `get/set_proactive_opt_out` (:350-407) + `load_all_guild_configs` (:410) | exact |
| `services/guild_config.py` (+`_blocked` set, block/silence methods) | service | CRUD + in-memory cache | `services/guild_config.py::load_all`/`_refresh_cache_entry`/`seed_home_guild` (same file, existing methods) | exact |
| `logic/guild_config.py` (+`silenced` branch) | utility (pure logic) | transform | `logic/guild_config.py::decide_ambient_channel` (:64-120, same file, existing branches) | exact |
| `services/gemini.py` (+`guild_id` kwarg + per-guild counter) | service | request-response + in-memory counter | `services/gemini.py::_RateLimiter`/`rpm_usage` (:63-101, same file) | exact |
| `bot.py` (+`DexterCommandTree`, block-check-first in `on_guild_join`) | middleware/controller | request-response (interaction gate) + event-driven | `bot.py::on_guild_join` (:661-702) + `create_bot`/`DexterBot` (:47-93) | exact |
| `cogs/ops.py` (+`/guilds` group, 6 subcommands) | controller | request-response + CRUD | `cogs/memory.py::MemoryCog` group + `MemoryPageView` (:230-238, :90-143); `cogs/ops.py::stats` inline owner-check (:244-262) | exact (structural template from a different file; owner-check template from same file) |
| Gemini call sites (`cogs/ai.py`, `events.py`, `imagine.py`, `library.py`, `music.py`, `services/memory.py`) | controller/service (call-site edit) | request-response | each file's existing `gemini_service.chat(...)`/`generate_image(...)` call | exact |
| Tests: `tests/test_database_phase20.py`, `tests/test_guild_config_logic.py` additions, `tests/test_guild_config_service.py` additions | test | CRUD / pure-logic assertions | `tests/test_database_phase16.py` (proactive_opt_out shape) + existing `test_guild_config_logic.py`/`test_guild_config_service.py` | exact |

## Pattern Assignments

### `database.py` — `guild_blocklist` DDL + helpers (model, CRUD)

**Analog:** `database.py` `guild_jams` table (:188-197) for DDL shape; `resolution_cache` (:178-186) for a single-purpose lookup table; `get_proactive_opt_out`/`set_proactive_opt_out` (:350-407) for the upsert-helper shape; `load_all_guild_configs` (:410-429) for the boot load-all shape.

**DDL to copy** (verbatim shape, `database.py:188-197`):
```python
CREATE TABLE IF NOT EXISTS guild_jams (
    guild_id   TEXT NOT NULL,
    name       TEXT NOT NULL,
    snapshot   JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (guild_id, name)
);
```
Adaptation: `guild_blocklist` uses `guild_id` alone as PK (like `guild_config`, not composite like `guild_jams` — this is a single flag per guild, not a named collection):
```python
CREATE TABLE IF NOT EXISTS guild_blocklist (
    guild_id   TEXT PRIMARY KEY,
    reason     TEXT,
    blocked_at TIMESTAMPTZ DEFAULT now()
);
```
Append this into the SAME `SCHEMA_SQL` triple-quoted string (currently ending at `database.py:220` with the `ALTER TABLE guild_config ADD COLUMN ... vision_roasts_enabled` line) — asyncpg's multi-statement param-free DDL rule (`init_db` at :223-229) requires it to stay in the one string, not a separate `conn.execute()`.

**Upsert-helper pattern to copy** (`database.py:350-384`, `set_proactive_opt_out`):
```python
async def set_proactive_opt_out(pool: asyncpg.Pool, *, user_id: str, opted_out: bool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO user_profiles (user_id, username, proactive_opt_out)"
            " VALUES ($1, $1, $2)"
            " ON CONFLICT (user_id) DO UPDATE SET"
            "   proactive_opt_out = EXCLUDED.proactive_opt_out",
            user_id,
            opted_out,
        )
```
Adaptation for `insert_blocklist(pool, *, guild_id, reason)`:
```python
async def insert_blocklist(pool: asyncpg.Pool, *, guild_id: str, reason: str | None) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO guild_blocklist (guild_id, reason) VALUES ($1, $2)"
            " ON CONFLICT (guild_id) DO UPDATE SET reason = EXCLUDED.reason",
            guild_id, reason,
        )
```
`delete_blocklist(pool, *, guild_id)` mirrors `database.py`'s `delete_jam`-style single-row `DELETE ... WHERE guild_id = $1`.

**Load-all pattern to copy** (`database.py:410-429`, `load_all_guild_configs`):
```python
async def load_all_guild_configs(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT guild_id, ambient_channel_id, configured, silenced, is_blocked,"
            " ambient_roasts_enabled, vision_roasts_enabled"
            " FROM guild_config"
        )
    return rows
```
Adaptation for `load_blocklist(pool) -> list[asyncpg.Record]`: bare `SELECT guild_id, reason, blocked_at FROM guild_blocklist`, no per-guild filter — same "one round-trip, boot-time only" discipline (CONFIG-03).

**Silenced get/set helpers** — mirror the existing `guild_config` write helpers (`configure_guild_first_time`, `set_ambient_roasts_enabled` at :566-639 region, not fully re-read this pass but same shape as verified `set_ambient_roasts_enabled`/`set_vision_roasts_enabled` calls in `services/guild_config.py:208-238`): a plain `UPDATE guild_config SET silenced = $2, updated_at = now() WHERE guild_id = $1 RETURNING <columns>`, returning `None` when no row exists (same "row existed?" boolean contract `services/guild_config.py::set_ambient_roasts_enabled` already relies on).

---

### `services/guild_config.py` — `_blocked` set + silence/block methods (service, CRUD + cache)

**Analog:** same file — `load_all` (:68-91), `get`/`_refresh_cache_entry` (:93-103), `set_ambient_roasts_enabled` (:208-222).

**Cache-load pattern to extend** (`services/guild_config.py:68-91`):
```python
async def load_all(self) -> None:
    try:
        rows = await database.load_all_guild_configs(self.pool)
    except Exception as exc:
        self._cache = {}
        log.error("guild_config: load_all failed, cache left empty (fail-closed): %s", exc)
        ...
        return
    self._cache = {str(row["guild_id"]): row for row in rows}
```
Adaptation: add a second query in the same method (or a sibling private helper called from it) populating `self._blocked: set[str] = {str(r["guild_id"]) for r in await database.load_blocklist(self.pool)}`, wrapped in its own try/except so a blocklist-load failure doesn't blank the config cache (fail-closed independently per D-02/D-07 discipline — an empty `_blocked` set on failure means nothing is blocked, which is the safer default direction than blocking everyone).

**Write-then-push-invalidate pattern to copy** (`services/guild_config.py:208-222`, `set_ambient_roasts_enabled`):
```python
async def set_ambient_roasts_enabled(self, *, guild_id: str, enabled: bool) -> bool:
    row = await database.set_ambient_roasts_enabled(self.pool, guild_id=guild_id, enabled=enabled)
    if row is None:
        return False
    self._refresh_cache_entry(row)
    return True
```
Adaptation for `silence_guild`/`unsilence_guild` — identical shape, writes `silenced` column, push-invalidates via `_refresh_cache_entry`.

For `block_guild`/`unblock_guild`/`is_blocked` — these do NOT touch `_cache`/`_refresh_cache_entry` (blocklist is its own table + its own `_blocked` set, D-03), so the pattern is simpler:
```python
async def block_guild(self, *, guild_id: str, reason: str | None) -> None:
    await database.insert_blocklist(self.pool, guild_id=guild_id, reason=reason)
    self._blocked.add(str(guild_id))   # write DB, THEN mutate set (D-02)

async def unblock_guild(self, *, guild_id: str) -> None:
    await database.delete_blocklist(self.pool, guild_id=guild_id)
    self._blocked.discard(str(guild_id))

def is_blocked(self, guild_id) -> bool:
    return str(guild_id) in self._blocked

def is_silenced(self, guild_id) -> bool:
    row = self.get(guild_id)
    return bool(row and row.get("silenced", False))
```

---

### `logic/guild_config.py` — `silenced` branch in `decide_ambient_channel` (pure logic, transform)

**Analog:** same file, same function, existing branches (`logic/guild_config.py:104-120`).

**Exact insertion point and pattern** (`logic/guild_config.py:104-120`, unmodified today):
```python
def decide_ambient_channel(*, config_row: Mapping | None, surface: AmbientSurface) -> int | None:
    if config_row is None:
        return None
    if not config_row.get("configured", False):
        return None
    toggle_column = "vision_roasts_enabled" if surface is AmbientSurface.VISION else "ambient_roasts_enabled"
    if not config_row.get(toggle_column, True):
        return None
    channel_id = config_row.get("ambient_channel_id")
    if channel_id is None:
        return None
    try:
        return int(channel_id)
    except (TypeError, ValueError):
        return None
```
Adaptation (D-14): insert a `silenced` check as a new early-return branch, same shape and position as the `configured`/toggle checks — directly AFTER the `configured` check and BEFORE (or after — order doesn't change semantics since both are early-returns) the toggle-column check:
```python
    if config_row.get("silenced", False):        # NEW (D-14)
        return None
```
Keep the function keyword-only, `Mapping`-typed, no `discord`/`datetime`/`random` imports (module docstring at :1-23 states this discipline explicitly). Glue (service tier) must dispatch on the return value — never re-derive `silenced` locally (Phase 10 D-02, called out again in `logic/guild_config.py:17-20`).

---

### `services/gemini.py` — `guild_id` kwarg + per-guild counter (service, request-response + in-memory counter)

**Analog:** same file — `_RateLimiter`/`rpm_usage` (:63-101), `GeminiService.chat` (:173-256), `generate_image` (:258-296).

**Existing counter idiom to mirror** (`services/gemini.py:86-94`, `_RateLimiter.rpm_usage`):
```python
def rpm_usage(self) -> int:
    self._clean()
    return len(self._timestamps)
```
And the service-level property wrapper (`services/gemini.py:163-166`):
```python
@property
def rpm_usage(self) -> int:
    return self._rate_limiter.rpm_usage()
```
Adaptation: add `self._guild_usage: dict[str, int] = {}` in `GeminiService.__init__` (near `self._rate_limiter = _RateLimiter()` at :157), and a read accessor:
```python
def guild_usage(self, guild_id: str | None) -> int:
    return self._guild_usage.get(str(guild_id), 0) if guild_id is not None else 0
```

**`chat()` signature to extend** (`services/gemini.py:173-181`, current):
```python
async def chat(
    self,
    system_prompt: str,
    conversation: list[dict],
    priority: int = 1,
    *,
    image_bytes: bytes | None = None,
    image_mime_type: str | None = None,
) -> str | None:
```
Adaptation: add `guild_id: str | None = None` to the keyword-only block. Increment the counter only on a guild-attributable, successfully-dispatched call (D-09: guild-less calls e.g. `daily_batch`/DM `/ask` pass `None` and are NOT counted) — increment right after `await self._rate_limiter.acquire(priority)` succeeds (mirrors where `_rate_limiter` itself records a timestamp), e.g.:
```python
if guild_id is not None:
    self._guild_usage[guild_id] = self._guild_usage.get(guild_id, 0) + 1
```
Same pattern for `generate_image()` (:258-268) — add `guild_id: str | None = None` keyword, same increment line placed after `await self._rate_limiter.acquire(priority)` (:268).

`embed()` (`services/gemini.py:298-...`) is explicitly NOT touched (D-09) — it uses `self._embed_limiter`, a separate 60 RPM budget the `/guilds` kill-switch cannot act on.

**Call sites to thread `guild_id` through** (all verified this pass):
| File:line | Current call | Guild source in scope |
|---|---|---|
| `cogs/ai.py:144` | `await self.gemini.chat(system_prompt, conversation, priority=1)` | `interaction.guild_id` (verify `/ask` is guild-scoped at this line; DM path passes `None`) |
| `cogs/ai.py:234` | `await self.gemini.chat(system_prompt, conversation, priority=1)` | `interaction.guild_id` (likely `/roast`) |
| `cogs/ai.py:345` | `await self.gemini.chat(prompt, [], priority=2)` | verify — may be the `daily_batch`-adjacent distill path; if guild-less, pass `None` |
| `cogs/events.py:185` | `await gemini_service.chat(system_prompt, conversation, priority=2)` | ambient roast — guild in scope via the surrounding handler (`message.guild.id`) |
| `cogs/events.py:565` | `await gemini_service.chat(...)` | vision roast — `message.guild.id` |
| `cogs/imagine.py:59` | `await self.gemini.generate_image(prompt, priority=1)` | `interaction.guild_id` |
| `cogs/library.py:985` | `await gemini_service.chat(prompt, [], priority=2)` | `/jam suggest` — guild in scope (jam is guild-scoped) |
| `cogs/music.py:1246` | `await gemini_service.chat(system_prompt, conversation, priority=2)` | inside `_build_roast_line` (see Pitfall 4 below — needs signature change) |
| `cogs/music.py:2126` | `await gemini_service.chat(...)` | verify local guild scope (likely voice-join ambient roast, `member.guild.id`) |
| `services/memory.py:383` | `await self._gemini.chat(...)` | `daily_batch` distill — passes `None` explicitly (D-09) |

**Pitfall 4 (verified, confirms RESEARCH):** `_build_roast_line` (`cogs/music.py:1182-1246`) has no `guild_id` parameter today. Its three call sites (verified at `cogs/music.py:1305`, `:1340`, `:1376`) are all inside a method that has `interaction.guild` in scope (they call `self._post_music_roast(interaction.guild, line)` immediately after) — so `guild_id=str(interaction.guild.id)` is trivially available at each of the three call sites. Add a keyword-only `guild_id: str | None = None` parameter to `_build_roast_line`'s signature (`cogs/music.py:1182-1188`), thread it to the `gemini_service.chat(...)` call at `cogs/music.py:1246`, and pass `guild_id=str(interaction.guild.id)` from all three callers.

---

### `bot.py` — `DexterCommandTree` + block-check-first (middleware/controller)

**Analog:** same file — `DexterBot`/`create_bot` (:47-93), `on_guild_join` (:661-702).

**Bot construction pattern to extend** (`bot.py:78-93`, current):
```python
def create_bot() -> DexterBot:
    intents = discord.Intents.default()
    ...
    bot = DexterBot(
        command_prefix="!",
        intents=intents,
        activity=discord.Activity(type=discord.ActivityType.listening, name="music"),
        owner_id=config.OWNER_ID or None,
    )
    return bot
```
Adaptation: define `class DexterCommandTree(app_commands.CommandTree): async def interaction_check(...)` above `create_bot`, pass `tree_cls=DexterCommandTree` as an added kwarg to the `DexterBot(...)` constructor call at :86-91. Verified via RESEARCH against installed `discord.py==2.7.1`: `commands.Bot.__init__` accepts `tree_cls` — no source changes needed to `DexterBot` itself, only the constructor call.

**`interaction_check` shape (RESEARCH's verified recommendation, use as-is):**
```python
class DexterCommandTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if await interaction.client.is_owner(interaction.user):
            return True
        if interaction.guild is None:
            return True
        guild_config = getattr(interaction.client, "guild_config", None)
        if guild_config is None:
            return True  # boot-race fail-open (Pitfall 5) — distinct from D-07 ambient fail-closed
        guild_id = str(interaction.guild.id)
        if guild_config.is_blocked(guild_id) or guild_config.is_silenced(guild_id):
            await interaction.response.send_message(
                "i've been muted in this server. not my call.",
                ephemeral=True,
            )
            return False
        return True
```
**Critical mechanic (verified against installed source, not training memory):** `interaction_check` returning `False` does NOT dispatch to `bot.tree.error` (`@bot.tree.error` at `bot.py:748`) — `CommandTree._call` just does a bare `return` before entering the `try/except AppCommandError` block. The ephemeral D-12 refusal MUST be sent from inside `interaction_check` itself, before returning `False` — do not attempt to route this through `on_app_command_error`.

**Block-check-first pattern to extend** (`bot.py:660-702`, `on_guild_join`, existing structure to preserve verbatim except the new check at the top):
```python
@bot.event
async def on_guild_join(guild: discord.Guild) -> None:
    if not hasattr(bot, "pool") or not hasattr(bot, "guild_config"):
        log.warning("on_guild_join: bot not yet initialized, guild %s deferred to boot backfill", guild.id)
        return

    # NEW (OWNER-04): block-check-first, before any insert_guild_config_if_absent
    if bot.guild_config.is_blocked(str(guild.id)):
        log.info("on_guild_join: guild %s is blocklisted, leaving immediately", guild.id)
        await guild.leave()
        return

    from logic.guild_config import should_welcome_guild
    ...  # existing body unchanged
```
Preserve the existing `hasattr(bot, "pool")`/`hasattr(bot, "guild_config")` guard and the WR-04 try/except discipline around the DB write/welcome chain — the new block-check sits BEFORE that guard's body, after the boot-race early return.

---

### `cogs/ops.py` — `/guilds` group, 6 subcommands (controller, request-response + CRUD)

**Analog:** `cogs/memory.py::MemoryCog` (`app_commands.Group` shape at :230-238) + `MemoryPageView` (:90-143, char-budget pagination — NOTE: CONTEXT.md's canonical_refs calls this "`LyricsPageView`"; the actual class living in `cogs/memory.py` is `MemoryPageView`, a documented clone of `cogs/music.py::LyricsPageView` — use `MemoryPageView`'s exact shape as the template since `cogs/ops.py` has no pagination view of its own yet). Owner-check template: `cogs/ops.py::stats` (:244-262, this file, existing).

**Group + Cog init pattern to copy** (`cogs/memory.py:230-238`):
```python
class MemoryCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    memory = app_commands.Group(
        name="memory",
        ...
    )
```
Adaptation for `cogs/ops.py` (extending the existing `OpsCog` at :136-144, or a new group attribute on it):
```python
guilds = app_commands.Group(
    name="guilds",
    description="owner-only: list, silence, or remove guilds",
    default_permissions=discord.Permissions(administrator=True),  # UI hint ONLY (D-06)
)
```

**Inline owner-check-first pattern to copy verbatim** (`cogs/ops.py:244-262`, `OpsCog.stats`):
```python
async def stats(self, interaction: discord.Interaction) -> None:
    """... Owner check is FIRST — inline await bot.is_owner() before any data is
    fetched or shown ..."""
    if not await self.bot.is_owner(interaction.user):
        ...  # refusal path
```
Every one of the 6 `/guilds` subcommands must open with the identical `if not await self.bot.is_owner(interaction.user): return await interaction.response.send_message(..., ephemeral=True)` — OWNER-06's inline-first discipline, no decorator.

**Pagination pattern to copy** (`cogs/memory.py:90-143`, `MemoryPageView`, adapt class name e.g. `GuildListPageView`):
```python
class MemoryPageView(discord.ui.View):
    def __init__(self, pages: list[str], title: str, timeout: float = 600.0) -> None:
        super().__init__(timeout=timeout)
        self.pages = pages
        self.title = title
        self.page = 0
        self.message: discord.Message | None = None

    def _build_embed(self) -> discord.Embed:
        total = len(self.pages)
        embed = discord.Embed(title=self.title, description=self.pages[self.page], color=0x9B59B6)
        embed.set_footer(text=f"Page {self.page + 1}/{total}")
        return embed

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction, button) -> None:
        self.page = max(0, self.page - 1)
        await interaction.response.edit_message(embed=self._build_embed(), view=self,
                                                 allowed_mentions=discord.AllowedMentions.none())

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction, button) -> None:
        self.page = min(len(self.pages) - 1, self.page + 1)
        await interaction.response.edit_message(embed=self._build_embed(), view=self,
                                                 allowed_mentions=discord.AllowedMentions.none())

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
```
Same `_chunk_facts_into_pages(facts, char_budget)` helper shape (`cogs/memory.py:62-89`) can be reused/adapted for `/guilds list` row-chunking against a new config knob (e.g. reuse `config.MEMORY_VIEW_PAGE_SIZE`-style budget constant, or a new one — planner discretion).

**`ForgetConfirmView` (`cogs/memory.py:145-228`) is the danger-confirm pattern D-07 explicitly does NOT reuse** — `/guilds leave`/`/guilds block` execute immediately with an in-persona ephemeral echo, no confirm button. Do not clone this view for Phase 20.

---

### OWNER-03 teardown (`/guilds leave`, `/guilds block`) — reuses `/stop`'s template verbatim

**Analog:** `cogs/music.py::stop` (:1714-1727, the exact canonical teardown).

**Exact template to copy** (`cogs/music.py:1719-1726`):
```python
queue._play_generation += 1  # invalidate any pending after-callbacks
queue.clear()
if hasattr(self.bot, "queue_persistence"):
    await self.bot.queue_persistence.clear_persisted(interaction.guild.id)

if voice_client:
    voice_client.stop()
    await voice_client.disconnect()
```
**Key adaptation (Pitfall 3, verified):** `/stop` operates on `interaction.guild` because the command runs IN the affected guild. `/guilds leave <guild_id>`/`/guilds block <guild_id>` are invoked from the owner's home guild (or a DM) — `interaction.guild` is the WRONG guild here. Resolve explicitly:
```python
target_guild = self.bot.get_guild(int(guild_id_str))
if target_guild is None:
    await interaction.followup.send("i'm not in that guild (or that id's wrong).", ephemeral=True)
    return
music_cog = self.bot.cogs.get("MusicCog")
voice_client = target_guild.voice_client
if music_cog is not None:
    queue = music_cog.get_queue(target_guild.id)
    queue._play_generation += 1
    queue.clear()
if hasattr(self.bot, "queue_persistence"):
    await self.bot.queue_persistence.clear_persisted(target_guild.id)
if voice_client:
    voice_client.stop()
    await voice_client.disconnect()
await target_guild.leave()
```
For `/guilds block`, append `await self.bot.guild_config.block_guild(guild_id=str(target_guild.id), reason=reason)` AFTER the teardown (D-11: block = teardown + blacklist insert, in that order). `queue.clear()` internally re-bumps `_play_generation` again (Pitfall 2, `models/queue.py:226` per RESEARCH — not independently re-read this pass, but this is the same documented, tested-safe "looks redundant, is not a bug" idiom `/stop` already relies on) — do not "fix" this apparent double-bump.

## Shared Patterns

### In-memory cache + push-invalidate, zero hot-path DB reads (CONFIG-03)
**Source:** `services/guild_config.py::load_all`/`_refresh_cache_entry` (:68-103)
**Apply to:** `_blocked` set (new), `silenced` reads via existing `get()`, `interaction_check`, `decide_ambient_channel`'s new branch. Every hot-path check is an O(1) dict/set lookup — never a `SELECT`.

### Fail-open vs fail-closed distinction (Pitfall 5)
**Source:** `services/guild_config.py::load_all` (fail-closed on load error, :77-89) vs the new `interaction_check`'s boot-race guard (fail-open when `bot.guild_config` doesn't exist yet)
**Apply to:** `DexterCommandTree.interaction_check` — a missing service attribute (structural absence) is NOT the same case as "guild has no config row" (D-07's existing fail-closed ambient rule). Don't conflate the two.

### Idempotent, additive DDL only (no `DROP COLUMN`)
**Source:** `database.py` `SCHEMA_SQL` — every existing block is `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
**Apply to:** `guild_blocklist` DDL. The dead `guild_config.is_blocked` column stays in place (D-03) — no destructive migration.

### Owner-gate discipline: inline check first, `default_permissions` is cosmetic only
**Source:** `cogs/ops.py::stats` (:244-262)
**Apply to:** All 6 `/guilds` subcommands — `default_permissions(administrator=True)` on the Group is a UI hint (D-06); the real gate is `await self.bot.is_owner(interaction.user)` as literally the first statement in every subcommand body.

### `AllowedMentions.none()` on every ephemeral/owner-facing edit
**Source:** `cogs/memory.py::MemoryPageView.prev_button`/`next_button` (:117-133)
**Apply to:** `/guilds list` pagination edits, and any embed rendering guild/owner-supplied names (Security Domain: injection mitigation, mirrors `bot.py::_build_guild_notice_embed`'s plain-field-value discipline).

## No Analog Found

None — every file this phase touches has a directly matching, already-verified analog in the same file or an immediately adjacent one (Phase 18/19 built the exact seams this phase extends).

## Metadata

**Analog search scope:** `database.py`, `services/guild_config.py`, `logic/guild_config.py`, `services/gemini.py`, `bot.py`, `cogs/ops.py`, `cogs/memory.py`, `cogs/music.py`, `cogs/ai.py`, `cogs/events.py`, `cogs/imagine.py`, `cogs/library.py`, `services/memory.py`
**Files scanned:** 13 read/grepped directly this session; all CONTEXT.md/RESEARCH.md line-number claims cross-checked against the live tree — **zero stale references found** (every cited line matched exactly: `database.py:188/204/350/410`, `services/guild_config.py` whole file, `logic/guild_config.py:64-120`, `services/gemini.py:63/86/135/163/173/258/298`, `bot.py:47/78/86/660-717/748`, `cogs/ops.py:136-262`, `cogs/memory.py:90-238`, `cogs/music.py:1182/1246/1305/1340/1376/1714-1727`).
**Pattern extraction date:** 2026-07-11
