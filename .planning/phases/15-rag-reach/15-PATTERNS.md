# Phase 15: RAG Reach - Pattern Map

**Mapped:** 2026-07-03
**Files analyzed:** 7 (2 modified, 2 new source, 3 new test)
**Analogs found:** 7 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|------------------|----------------|
| `cogs/ai.py` (modify: 2 gate removals) | controller (slash command) | request-response | itself (surgical edit, no analog needed) | exact |
| `database.py` (add 2 helpers) | model/DB helper | CRUD (scoped SELECT/DELETE) | `evict_lowest_salience` (:1115) / `get_user_memories_for_eviction` (:1080) | exact |
| `cogs/memory.py` (new) | controller (slash command group + views) | request-response | `cogs/library.py` `/playlist` `app_commands.Group` (:460) + `JamSuggestConfirmView` (:1179) + `cogs/music.py::LyricsPageView` (:148) | exact (composite) |
| `tests/test_ambient_recall_cadence.py` (new) | test | event-driven (mock-patched cadence) | `tests/test_roast_command.py` fake-bot/interaction helpers | role-match |
| `tests/test_memory_command.py` (new) | test | request-response | `tests/test_roast_command.py` (`_make_bot`/`_make_interaction`/`_invoke_*`) | exact |
| `tests/test_database_phase15.py` (new) | test | CRUD + live-DB integration | `tests/test_database_phase11.py` (two-half static+live-DB structure) | exact |

## Pattern Assignments

### `cogs/ai.py` (controller, request-response) — MODIFY ONLY, no new file

**Change 1 — `/ask` at lines 128-142.** Delete the `if random.random() < config.MEMORY_CALLBACK_CHANCE:` wrapper, un-indent the body one level. Current code:
```python
# cogs/ai.py:128-142 (BEFORE)
memories: list[str] = []
if random.random() < config.MEMORY_CALLBACK_CHANCE:
    _memory_svc = getattr(self.bot, "memory_service", None)
    if _memory_svc is not None:
        try:
            memories = await _memory_svc.recall(
                str(interaction.user.id),
                str(interaction.guild_id),
                question,
            )
        except Exception as _mem_err:
            log.debug("memory.recall failed (non-fatal): %s", _mem_err)
```
After (D-01): drop the `if random.random() < ...` line, un-indent everything below it by 4 spaces. Everything else (the `getattr` guard, try/except, `memories or None` fallback at line 145) is untouched.

**Change 2 — `/roast` at lines 206-220.** Identical transformation, but this call recalls `str(target.id)` — **not** `str(interaction.user.id)` — already correct today, do not alter the argument:
```python
# cogs/ai.py:206-220 (BEFORE)
roast_memories: list[str] = []
if random.random() < config.MEMORY_CALLBACK_CHANCE:
    _memory_svc = getattr(self.bot, "memory_service", None)
    if _memory_svc is not None:
        try:
            roast_memories = await _memory_svc.recall(
                str(target.id),
                str(interaction.guild_id),
                scenario,
            )
        except Exception as _mem_err:
            ...
```
Delete the gate line, un-indent the body.

**Do NOT touch** (regression targets, keep the gate exactly as-is):
- `cogs/events.py:128` (`_generate_ambient_roast`)
- `cogs/music.py:1272` (`_build_roast_line`)

**Verification checklist:** after the edit, `grep -rn MEMORY_CALLBACK_CHANCE cogs/` must return exactly 2 matches (`cogs/events.py` and `cogs/music.py`), never 0 or 4.

---

### `database.py` — add two new helpers near the Phase 11 memory section (around :1080-1171)

**Analog 1 (for `list_user_memories`):** `get_user_memories_for_eviction` (:1080) for shape/docstring convention — but note research explicitly warns **do not reuse its ordering** (worst-first); this is a *display* query, ordered best-first.

**Analog 2 (for `delete_all_user_memories`):** `evict_lowest_salience` (:1115-1142) — the scoped-DELETE template to clone:
```python
# database.py:1115-1142 — scoped-DELETE template (T-11-04c pattern)
async def evict_lowest_salience(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    ids: list[int],
) -> None:
    """Delete the given memory ids — scoped to user_id (T-11-04c cross-user guard).
    ...
    """
    if not ids:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM user_memories WHERE user_id = $1 AND id = ANY($2)",
            user_id, ids,
        )
```

**New helper 1 — `list_user_memories`** (research-provided exact code, place near `get_user_memories_for_eviction`):
```python
async def list_user_memories(
    pool: asyncpg.Pool,
    *,
    user_id: str,
    limit: int,
) -> list[asyncpg.Record]:
    """Return up to `limit` of a user's memory rows for the /memory view (RAG-03).

    Unlike search_memories (ANN relevance recall) this is a plain listing query:
    no embedding call, no similarity floor, no per-request cap tied to prompt
    injection budget. Ordered salience DESC, created_at DESC so the most
    notable / most recent facts surface first across pagination pages.

    Security (T-11-04c pattern): WHERE user_id = $1 — same cross-user guard as
    every other user_memories query. No caller may pass a different user's id
    (the /memory command never accepts a target-user argument).

    Args:
        pool:    asyncpg connection pool.
        user_id: Discord user ID — sole scope, always interaction.user.id.
        limit:   Row cap — use config.MEMORY_MAX_PER_USER (150) so a full view
                 can never silently truncate below what forget would erase.

    Returns:
        Rows with: id, fact, kind, salience, created_at. May be empty.
    """
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT id, fact, kind, salience, created_at"
            " FROM user_memories"
            " WHERE user_id = $1"
            " ORDER BY salience DESC, created_at DESC"
            " LIMIT $2",
            user_id, limit,
        )
```
**CRITICAL (Pitfall 2):** the caller in `cogs/memory.py` must pass `config.MEMORY_MAX_PER_USER` (150), never `config.MEMORY_INJECT_CAP` (1-3) — a view capped at the injection budget would break the D-02 transparency promise.

**New helper 2 — `delete_all_user_memories`** (place near `evict_lowest_salience`):
```python
async def delete_all_user_memories(pool: asyncpg.Pool, user_id: str) -> int:
    """Hard-delete every user_memories row for user_id. Returns rows deleted.

    RAG-04 escape hatch (D-03 nuke-all). Scoped WHERE user_id = $1 — the ONLY
    filter, by design (T-11-04c pattern): a bug here can never touch another
    user's rows because there is no second parameter to get wrong. Deleting
    the row deletes its embedding column value in the same operation (pgvector
    stores the vector in-row, not in a separate structure the app must also
    clean) — "rows AND embeddings gone" is inherent to a single DELETE.

    Args:
        pool:    asyncpg connection pool.
        user_id: Discord user ID — sole scope. Always interaction.user.id;
                 /memory forget must never accept a target-user argument.

    Returns:
        Number of rows deleted (0 if the user had no stored memories).
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM user_memories WHERE user_id = $1",
            user_id,
        )
    return int(result.split()[-1])
```
**No second parameter, ever** — structurally prevents a future accidental cross-user forget (V4 access control requirement).

**Existing helper to reuse as-is (no new helper needed):** `count_user_memories(pool, user_id)` (:1057) for the forget-confirmation count preview.

---

### `cogs/memory.py` (new file) — controller, request-response

**Imports pattern** (mirror `cogs/library.py` top-of-file / `cogs/ai.py` imports):
```python
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config
import database
from personality.responses import pick_random   # if any templated lines needed
```

**Group scaffold** (analog: `cogs/library.py:460` `/playlist` group):
```python
# cogs/library.py:458-464 — the app_commands.Group + subcommand pattern to clone
# ---- /playlist group -------------------------------------------------

playlist = app_commands.Group(
    name="playlist",
    description="Save and load named playlists",
)

@playlist.command(name="save", description="Save the current queue as a named playlist")
@app_commands.describe(name="Name for the playlist (max 60 chars)")
async def playlist_save(
    self, interaction: discord.Interaction, name: str
) -> None:
    ...
```
Apply identically for a `memory = app_commands.Group(name="memory", description="See or forget what Dexter remembers about you")` with `@memory.command(name="view", ...)` and `@memory.command(name="forget", ...)` subcommands, no `target` parameter on either.

**`/memory view` handler skeleton** (research-provided, mirrors `cogs/library.py::playlist_load` + `LyricsPageView` usage):
```python
@memory.command(name="view", description="See what Dexter remembers about you")
async def memory_view(self, interaction: discord.Interaction) -> None:
    user_id = str(interaction.user.id)
    rows = await database.list_user_memories(
        self.bot.pool, user_id=user_id, limit=config.MEMORY_MAX_PER_USER
    )
    if not rows:
        await interaction.response.send_message(
            "i don't remember anything about you yet.", ephemeral=True
        )
        return

    facts = [row["fact"] for row in rows]
    pages = _chunk_facts_into_pages(facts, per_page=10)
    view = MemoryPageView(pages, title=f"{interaction.user.display_name}'s file")
    await interaction.response.send_message(
        "fine, here's what i've got on you.",
        embed=view._build_embed(),
        view=view,
        ephemeral=True,
    )
```

**Pagination view — clone `LyricsPageView`, NOT `QueuePageView`** (`cogs/music.py:148-207`, full source below is the exact shape to copy — rename class to e.g. `MemoryPageView`, swap embed title/color):
```python
class LyricsPageView(discord.ui.View):
    """Paginated lyrics view with Previous/Next buttons.

    Takes pre-chunked pages (list[str]) rather than a MusicQueue — avoids
    the QueuePageView coupling issue. Stores a reference to the interaction
    message so on_timeout can visually disable buttons.

    All sends/edits use allowed_mentions=discord.AllowedMentions.none() as
    defense-in-depth against mention injection.
    """

    def __init__(self, pages: list[str], title: str, timeout: float = 600.0) -> None:
        super().__init__(timeout=timeout)
        self.pages = pages
        self.title = title
        self.page = 0
        self.message: discord.Message | None = None  # set after send

    def _build_embed(self) -> discord.Embed:
        total = len(self.pages)
        embed = discord.Embed(
            title=f"Lyrics — {self.title}",
            description=self.pages[self.page],
            color=0x5865F2,
        )
        embed.set_footer(text=f"Page {self.page + 1}/{total}")
        return embed

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction, button) -> None:
        self.page = max(0, self.page - 1)
        await interaction.response.edit_message(
            embed=self._build_embed(), view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction, button) -> None:
        self.page = min(len(self.pages) - 1, self.page + 1)
        await interaction.response.edit_message(
            embed=self._build_embed(), view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
```
Use `ephemeral=True` on the initial send (D-02 requirement) — `LyricsPageView` itself is sent non-ephemeral today in `/lyrics`, so this is the one deliberate deviation: `/memory view`'s send call must add `ephemeral=True` where `/lyrics` doesn't.

**Confirm-view for `/memory forget` — clone `JamSuggestConfirmView`** (`cogs/library.py:1179-1268` full shape; adapt to a simpler single-DELETE body, no per-track extract loop):
```python
class JamSuggestConfirmView(discord.ui.View):
    """One-shot propose-and-confirm view (trust discipline).

    Finite timeout, never registered in bot.py's setup_hook — a one-shot
    confirm, not NowPlayingView's persistent always-on controller.
    """

    def __init__(self, bot, guild_id, jam_name, candidates, timeout: float = 60.0) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        ...
        self.message: discord.Message | None = None
        self._used = False

    @discord.ui.button(label="confirm", style=discord.ButtonStyle.success)
    async def confirm_button(self, interaction, button) -> None:
        if self._used:
            await interaction.response.send_message("already handled that.", ephemeral=True)
            return
        self._used = True
        for child in self.children:
            child.disabled = True
        await interaction.response.defer(ephemeral=True)
        # ... do the mutating work, then interaction.followup.send(...)
```

**Adapted `ForgetConfirmView` (research-provided target shape for this phase):**
```python
class ForgetConfirmView(discord.ui.View):
    def __init__(self, bot, user_id: str, count: int, timeout: float = 60.0) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.user_id = user_id
        self.count = count
        self.message: discord.Message | None = None
        self._used = False

    @discord.ui.button(label="wipe it all", style=discord.ButtonStyle.danger)  # danger=red, NOT success — the one irreversible confirm in the family
    async def confirm_button(self, interaction, button) -> None:
        if self._used:
            await interaction.response.send_message("already handled that.", ephemeral=True)
            return
        self._used = True
        for child in self.children:
            child.disabled = True
        await interaction.response.defer(ephemeral=True)
        deleted = await database.delete_all_user_memories(self.bot.pool, self.user_id)
        await interaction.followup.send(
            f"gone. all {deleted} of them. i've got nothing on you now.",
            ephemeral=True,
        )
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="never mind", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction, button) -> None:
        # mirrors JamSuggestConfirmView.cancel_button exactly
        ...

    async def on_timeout(self) -> None:
        # mirrors JamSuggestConfirmView.on_timeout exactly
        ...
```

**`/memory forget` command handler — count preview + empty-state skip (Pitfall 5):**
```python
@memory.command(name="forget", description="Wipe everything Dexter remembers about you")
async def memory_forget(self, interaction: discord.Interaction) -> None:
    user_id = str(interaction.user.id)
    count = await database.count_user_memories(self.bot.pool, user_id)
    if count == 0:
        await interaction.response.send_message(
            "already got nothing on you.", ephemeral=True
        )
        return
    view = ForgetConfirmView(self.bot, user_id, count)
    await interaction.response.send_message(
        f"i've got {count} things on you. wipe them all? no takebacks.",
        view=view,
        ephemeral=True,
    )
    view.message = await interaction.original_response()
```

---

## Shared Patterns

### Discord ephemeral + AllowedMentions defense-in-depth
**Source:** `cogs/music.py::LyricsPageView` (all `edit_message`/`send_message` calls)
**Apply to:** All `/memory` view/forget responses — `ephemeral=True` always; `allowed_mentions=discord.AllowedMentions.none()` on pagination edits as defense-in-depth (fact text ultimately derives from banter).

### Scoped `user_id`-only DELETE/SELECT (T-11-04c cross-user guard)
**Source:** `database.py::evict_lowest_salience` (:1115), `database.py::delete_expired_memories` (:1171)
**Apply to:** Both new `database.py` helpers. Bound `$N` params only, never string interpolation, never a second identity parameter. `delete_all_user_memories` signature must remain exactly `(pool, user_id)` — no `target`/second-id argument, structurally enforced.

### Finite-timeout confirm-view (not persistent/setup_hook-registered)
**Source:** `cogs/library.py::JamSuggestConfirmView` (:1179)
**Apply to:** `ForgetConfirmView` in `cogs/memory.py`. `_used` guard + immediate `child.disabled = True` before async work + `on_timeout` disables buttons + never registered via `bot.add_view`/`setup_hook` (contrast with `NowPlayingView`, which IS persistent).

### Fake-bot / fake-interaction test helpers
**Source:** `tests/test_roast_command.py:33-75` (`_make_bot`, `_make_interaction`, `_make_target`, `_invoke_roast`)
```python
def _make_bot(bot_user_id: int = 999) -> MagicMock:
    bot = MagicMock()
    bot_user = MagicMock(spec=discord.User)
    bot_user.id = bot_user_id
    bot_user.bot = True
    bot.user = bot_user
    bot.pool = MagicMock()
    return bot

def _make_interaction(user_id: int = 1, guild_id: int = 100) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    user = MagicMock(spec=discord.Member)
    user.id = user_id
    user.display_name = "Invoker"
    user.bot = False
    interaction.user = user
    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    interaction.guild = guild
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction
```
**Apply to:** `tests/test_memory_command.py`, `tests/test_ambient_recall_cadence.py` — reuse `_make_bot`/`_make_interaction` shape (import or reproduce locally per test-file convention already used across `tests/test_*_command.py`), add `bot.memory_service = AsyncMock()` for recall-cadence assertions.

### Deterministic cadence testing via `patch("random.random", ...)`
**Source:** research-derived pattern following `unittest.mock.patch` convention in `test_roast_command.py`
```python
with patch("cogs.events.random.random", return_value=0.99):
    # invoke _generate_ambient_roast(...)
    memory_service.recall.assert_not_called()

with patch("cogs.ai.random.random", return_value=0.99):
    await _invoke_ask(...)
    memory_service.recall.assert_called_once()
    await _invoke_roast(...)
    memory_service.recall.assert_called_once_with(str(target.id), ANY, ANY)
```
**Apply to:** `tests/test_ambient_recall_cadence.py` (new file, no pre-existing lock per RESEARCH.md Open Question 2 finding — must be written from scratch, not adjusted).

### Static source-inspection test convention (no live DB)
**Source:** `tests/test_database_phase11.py` `TestWriteHelpersExist`-style class
**Apply to:** `tests/test_database_phase15.py` first half — `inspect.getsource`/`inspect.signature` assertions that `list_user_memories`/`delete_all_user_memories` exist, are `user_id`-scoped (substring checks for `"user_id"`, `"$1"`), and `delete_all_user_memories` has exactly one non-`pool` parameter (no second id — structural enforcement of the "never accepts a target" constraint).

### Live-DB integration test skip-guard
**Source:** `tests/test_database_phase11.py` (`@pytest.mark.skipif(_SKIP_LIVE, ...)`, `pool` fixture from `tests/conftest.py`)
**Apply to:** `tests/test_database_phase15.py::test_remember_forget_recall_empty` — the Success Criterion 4 proof (`remember → forget → recall == []`), using real `insert_memory`/`search_memories`/`delete_all_user_memories` against a real pgvector column, not mocked.

## No Analog Found

None — every file in scope has a direct, concrete analog in the existing codebase (this phase's entire premise per RESEARCH.md: 100% intra-repo pattern reuse, zero new dependencies).

## Metadata

**Analog search scope:** `cogs/ai.py`, `cogs/events.py`, `cogs/music.py`, `cogs/library.py`, `database.py`, `tests/test_roast_command.py`, `tests/test_database_phase11.py`
**Files scanned:** 7 read directly (plus RESEARCH.md's own exhaustive prior reads, reused rather than re-fetched)
**Pattern extraction date:** 2026-07-03
