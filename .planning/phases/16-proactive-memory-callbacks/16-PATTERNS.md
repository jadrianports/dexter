# Phase 16: Proactive Memory Callbacks - Pattern Map

**Mapped:** 2026-07-03
**Files analyzed:** 9 (2 new source, 4 modified source, 3 new tests, 2 modified tests)
**Analogs found:** 9 / 9

All line numbers below were re-confirmed against the live repo this session (not just
copied from RESEARCH.md), per Grep/Read this pass.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|---------------|
| `logic/proactive.py` (NEW) | utility (pure decision gate) | transform | `logic/roasts.py` (`decide_ambient_roast`, `cooldown_elapsed`) | exact |
| `cogs/events.py` (MODIFIED) | controller (event listener) | event-driven | itself — `on_voice_state_update` + `_generate_ambient_roast` (same file, same cog) | exact |
| `database.py` (MODIFIED) | model/query-helper | CRUD | `update_user_profile` (upsert) + Phase 8 `total_errors` `ALTER TABLE` | exact |
| `cogs/memory.py` (MODIFIED) | controller (slash command group) | request-response | `memory_view`/`memory_forget` subcommands, same file | exact |
| `config.py` (MODIFIED) | config | — | Phase 11 `MEMORY_*` knob block | exact |
| `tests/test_proactive_logic.py` (NEW) | test | transform | `tests/test_roast_logic.py` | exact |
| `tests/test_database_phase16.py` (NEW) | test | CRUD/file-I/O | `tests/test_database_phase15.py` | exact |
| `tests/test_proactive_events.py` (NEW) | test | event-driven | `tests/test_ambient_recall_cadence.py` | exact |
| `tests/test_ambient_recall_cadence.py` (MODIFIED) | test | event-driven | itself (extend in place) | exact |
| `tests/test_memory_command.py` (MODIFIED) | test | request-response | itself (extend in place) | exact |

## Pattern Assignments

### `logic/proactive.py` (NEW) — pure gate

**Analog:** `logic/roasts.py` (full file, 145 lines)

**Module docstring / no-side-effects convention** (lines 1-16):
```python
"""Pure ambient-roast decision logic extracted from EventsCog (TEST-03).

All functions in this module are deterministic and side-effect-free: no ``random``,
no ``asyncio``, no ``datetime``, no ``discord``.

Any nondeterministic value (random rolls, monotonic clock delta, local hour) is computed
by the calling cog glue and passed in as a primitive...
"""
from __future__ import annotations

import enum

import config
from personality.roasts import is_late_night
```
→ `logic/proactive.py` should open with the same disclaimer, `import config`, no `random`/`datetime`/`discord` imports.

**Keyword-only gate function shape, short-circuit gate ordering** (lines 74-144, `decide_ambient_roast`):
```python
def decide_ambient_roast(
    *,
    event: str,
    chance_roll: float,
    late_night_roll: float,
    local_hour: int,
    seconds_since_last_roast: float,
    chance: float = config.UNPROMPTED_ROAST_CHANCE,
    late_night_chance: float = config.LATE_NIGHT_ROAST_CHANCE,
    ceiling_seconds: float = config.AMBIENT_ROAST_CEILING_SECONDS,
) -> RoastScenario:
    ...
    # Gate 1: initial chance roll (must be strictly less than chance to proceed)
    if chance_roll >= chance:
        return RoastScenario.NONE
    # Gate 2: per-user cooldown (ceiling_seconds must have elapsed)
    if not cooldown_elapsed(seconds_since_last_roast, ceiling_seconds):
        return RoastScenario.NONE
    ...
```
→ `should_fire_proactive_callback(*, opted_out, chance_roll, daily_count, chance=config.PROACTIVE_CALLBACK_CHANCE, daily_cap=config.PROACTIVE_CALLBACK_DAILY_CAP) -> bool` mirrors this exactly: opt-out check first (cheapest), then `chance_roll >= chance` returns False, then `daily_count >= daily_cap` returns False, else True. Boundary convention: chance uses `>=` to fail / `<` to pass (same as `decide_ambient_roast`); cap uses `>=` to fail (ceiling, inverted from `cooldown_elapsed`'s inclusive floor at line 66: `return seconds_since_last >= ceiling_seconds`).

**Docstring convention for Args/Returns** (lines 100-120) — full Google-style docstring documenting where each primitive is computed in glue (`random.random()`, `ZoneInfo(config.STREAK_TIMEZONE)`, etc.) — replicate exactly for the new gate.

---

### `cogs/events.py` (MODIFIED)

**Analog:** same file — `on_message` (confirmed lines 347-364) is the insertion anchor; `_generate_ambient_roast` (confirmed lines 87-172) is the pipeline to reuse/extend; `on_voice_state_update` (confirmed starting line 176) is the sibling cadence pattern.

**Current `on_message`** (confirmed lines 347-364, verbatim):
```python
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Add non-bot messages to the channel's message buffer, then handle reactions."""
        if message.author.bot:
            return

        # Feed message buffer (existing behavior — must not break)
        if hasattr(self.bot, "message_buffer"):
            self.bot.message_buffer.add(
                channel_id=message.channel.id,
                role="user",
                author=message.author.display_name,
                author_id=str(message.author.id),  # CR-02: real snowflake for distill-batch keying
                content=message.content,
            )

        # Handle reactions / deflecting responses
        await self._handle_message_reactions(message)
```
→ Add the D-01 proactive-gate call as a new statement AFTER `_handle_message_reactions(message)`, guarded on `message.guild is not None` + `config.DEXTER_CHANNEL_ID` channel match (Pitfall 2 — never let a DM/no-guild message reach the gate). Dispatch to a new `_maybe_fire_proactive_callback(message)` method — mirrors the existing `_handle_message_reactions` extraction pattern (a small dedicated async method called from `on_message`, not inlined).

**`_generate_ambient_roast` signature + internal recall gate (Pitfall 1 target)** (confirmed lines 87-172):
```python
    async def _generate_ambient_roast(
        self,
        member: discord.Member,
        scenario: str,
        fallback_pool: list[str],
    ) -> str:
        ...
        amb_memories: list[str] = []
        if random.random() < config.MEMORY_CALLBACK_CHANCE:
            _memory_svc = getattr(self.bot, "memory_service", None)
            if _memory_svc is not None:
                try:
                    amb_memories = await _memory_svc.recall(
                        str(member.id), str(member.guild.id), scenario,
                    )
                except Exception as _mem_err:
                    log.debug("memory.recall failed (non-fatal): %s", _mem_err)

        system_prompt = build_chat_prompt("normal", user_context, "", memories=amb_memories or None)
        ...
        result = await gemini_service.chat(system_prompt, conversation, priority=2)
```
→ Per Pitfall 1 Option B (RESEARCH-recommended, locked): add a new keyword-only parameter `pre_recalled_memories: list[str] | None = None`. When not `None`, skip the internal `if random.random() < config.MEMORY_CALLBACK_CHANCE:` block and internal `_memory_svc.recall(...)` call entirely — use `amb_memories = pre_recalled_memories` directly. Default `None` must preserve byte-identical behavior for the two existing `on_voice_state_update` call sites. The `tests/test_ambient_recall_cadence.py::test_ambient_surfaces_retain_gate` source-inspection assertion for `"MEMORY_CALLBACK_CHANCE" in events_src` must keep passing — do not delete the internal gate, only make it conditionally bypassable.

**Cooldown-dict-on-cog convention** (confirmed line 33):
```python
        self._ambient_roast_times: dict[int, float] = {}
```
→ New `self._proactive_daily_counts: dict[str, tuple[str, int]] = {}` in `EventsCog.__init__` — same per-cog in-memory dict pattern, `str`-keyed (matches `recall()`/`database` string-user-id convention elsewhere, not the `int`-keyed voice dict).

**Reply + AllowedMentions.none() convention** (confirmed line 193-196, inside `on_voice_state_update`'s bot-move branch):
```python
                await channel.send(
                    pick_random(roasts.BOT_MOVED_COMPLAINTS),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
```
→ New code uses `await message.reply(line, allowed_mentions=discord.AllowedMentions.none(), mention_author=False)` instead of `channel.send` — same mention-suppression convention, different delivery primitive per D-04 (reply-anchor, not a channel post).

---

### `database.py` (MODIFIED)

**Analog:** `update_user_profile` (confirmed lines 297-310) for the upsert shape; the Phase 8 additive-column line (confirmed line 171) for the `ALTER TABLE` shape.

**Upsert pattern to clone** (confirmed lines 297-310, verbatim):
```python
async def update_user_profile(
    pool: asyncpg.Pool, *, user_id: str, username: str
) -> None:
    """Create or update a user profile, incrementing their song count."""
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO user_profiles (user_id, username, total_songs_queued)"
            " VALUES ($1, $2, 1)"
            " ON CONFLICT (user_id) DO UPDATE SET"
            "   username = EXCLUDED.username,"
            "   total_songs_queued = user_profiles.total_songs_queued + 1,"
            "   last_active_at = now()",
            user_id, username,
        )
```
→ `set_proactive_opt_out(pool, *, user_id, opted_out)` uses the same `INSERT ... ON CONFLICT (user_id) DO UPDATE SET` shape (Pitfall 3: a bare `UPDATE` silently no-ops for a user with no prior `user_profiles` row, since `username` is `NOT NULL` at line ~90). `get_proactive_opt_out(pool, user_id)` is a plain `SELECT ... WHERE user_id = $1`, defaulting to `False` (opted-in) when no row exists — same `fetchrow`-then-`None`-check idiom used throughout `database.py`'s getters.

**Additive-column precedent** (confirmed line 171, verbatim):
```sql
ALTER TABLE bot_daily_stats ADD COLUMN IF NOT EXISTS total_errors INTEGER DEFAULT 0;
```
→ New line in `SCHEMA_SQL`: `ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS proactive_opt_out BOOLEAN DEFAULT false;` — same idempotent additive-DDL convention, appended near (not necessarily adjacent to) the `user_profiles` `CREATE TABLE` block (confirmed starting line 88).

---

### `cogs/memory.py` (MODIFIED)

**Analog:** `memory_view` / `memory_forget` subcommands + the `memory` Group declaration, same file (confirmed lines 224-292, verbatim read).

**Group declaration + self-scoping convention** (confirmed lines 224-236):
```python
class MemoryCog(commands.Cog):
    """The /memory group: view (RAG-03) and forget (RAG-04)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    memory = app_commands.Group(
        name="memory",
        description="See or forget what Dexter remembers about you",
    )

    @memory.command(name="view", description="See what Dexter remembers about you")
    async def memory_view(self, interaction: discord.Interaction) -> None:
        """/memory view — show the invoker's stored memory facts, verbatim.

        Self-scoped only (str(interaction.user.id)); no target param (V4).
        """
        user_id = str(interaction.user.id)
        ...
```
→ New `memory_callbacks` subcommand follows the exact same shape: `@memory.command(name="callbacks", ...)`, `async def memory_callbacks(self, interaction: discord.Interaction, setting: app_commands.Choice[str]) -> None`, `user_id = str(interaction.user.id)` (no `target` param — V4 self-scoping guard, matches the docstring convention `"Self-scoped only ... no target param (V4)."`), `app_commands.choices(setting=[Choice("on","on"), Choice("off","off")])` for constrained input (V5), and `interaction.response.send_message(msg, ephemeral=True)` for the confirmation — same ephemeral convention as both existing subcommands.

**Empty-state / short in-character response convention** (confirmed lines 250-254, `memory_view`):
```python
        if not rows:
            await interaction.response.send_message(
                "i don't remember anything about you yet.", ephemeral=True
            )
            return
```
→ New subcommand's confirmation strings follow this same short, lowercase, in-character register (CONTEXT.md D-03 suggests: `"fine, i'll keep my mouth shut. your memories are still here though."` / `"back on. don't say i didn't warn you."`).

---

### `config.py` (MODIFIED)

**Analog:** Phase 11 `MEMORY_*` block (per RESEARCH.md, confirmed values `MEMORY_CALLBACK_CHANCE = 0.35`, `MEMORY_SIMILARITY_FLOOR = 0.70` exist in this file's Phase 11 section).

**Pattern:** A new `# --- Phase 16: Proactive Memory Callbacks ---` comment-delimited section (matches every prior phase's section-header convention in this file), holding:
```python
PROACTIVE_CALLBACK_CHANCE = 0.10   # must stay strictly < UNPROMPTED_ROAST_CHANCE (0.30) and < MEMORY_CALLBACK_CHANCE (0.35)
PROACTIVE_CALLBACK_DAILY_CAP = 1   # per-user, per calendar day
```
Insert after the Phase 14 block, before `sanitize_database_url` (RESEARCH.md confirms this insertion point at line ~226/227).

---

### `tests/test_proactive_logic.py` (NEW)

**Analog:** `tests/test_roast_logic.py` — mock-free, pure-function boundary-testing convention (no `pytest.mark.asyncio`, no mocks — plain `assert should_fire_proactive_callback(...) is True/False` calls with explicit keyword args for every branch/boundary). Add one additional static assertion: `config.PROACTIVE_CALLBACK_CHANCE < config.UNPROMPTED_ROAST_CHANCE and config.PROACTIVE_CALLBACK_CHANCE < config.MEMORY_CALLBACK_CHANCE`.

### `tests/test_database_phase16.py` (NEW)

**Analog:** `tests/test_database_phase15.py` — two-tier shape: (1) always-run static/source-inspection tests (e.g. structural signature guard via `inspect.signature(database.set_proactive_opt_out).parameters` asserting the param list is exactly `["pool", "user_id", "opted_out"]`, mirroring that file's `test_delete_all_user_memories_has_single_identity_param`-style guard), and (2) optional live-DB tests using the `pool` fixture from `tests/conftest.py` (skip-without-`TEST_DATABASE_URL` convention), proving the opt-out round-trip and that it never touches `user_memories`.

### `tests/test_proactive_events.py` (NEW)

**Analog:** `tests/test_ambient_recall_cadence.py` — mocked `discord.Message`/`discord.Member`/bot fixture style (`_make_bot` helper). Behavioral assertions: designated-channel gate respected, empty-`recall()` silent no-op, `message.reply` (not `channel.send`) called with `allowed_mentions=discord.AllowedMentions.none()` on fire, daily counter only increments on an actual fire.

### `tests/test_ambient_recall_cadence.py` (MODIFIED)

Extend in place: keep `test_ambient_surfaces_retain_gate` passing unmodified (regression lock on the internal `MEMORY_CALLBACK_CHANCE` gate staying present in `_generate_ambient_roast`'s source); add one new test asserting the new `pre_recalled_memories` parameter, when provided, bypasses the internal chance roll and internal `recall()` call.

### `tests/test_memory_command.py` (MODIFIED)

Extend in place: add `test_memory_callbacks_off_then_on`, `test_memory_callbacks_is_self_scoped` (mirrors this file's existing `test_memory_subcommands_have_no_target_param`-style structural guard, extended to include `callbacks`), `test_memory_callbacks_response_ephemeral`.

## Shared Patterns

### Pure-logic seam (Phase 10 convention)
**Source:** `logic/roasts.py`
**Apply to:** `logic/proactive.py`
Keyword-only, `random`/`datetime`/`discord`-free functions; glue computes nondeterminism and passes primitives in; short-circuit gate ordering, cheapest gate first.

### Ambient-send mention suppression
**Source:** `cogs/events.py:193-196` (`on_voice_state_update` bot-move branch)
**Apply to:** the new `_maybe_fire_proactive_callback` reply
```python
allowed_mentions=discord.AllowedMentions.none()
```

### Additive idempotent schema change
**Source:** `database.py:171` (Phase 8 `total_errors`)
**Apply to:** `database.py` `SCHEMA_SQL` — `ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS proactive_opt_out BOOLEAN DEFAULT false;`

### Upsert-not-bare-UPDATE for lazily-created `user_profiles` rows
**Source:** `database.py:297-310` (`update_user_profile`)
**Apply to:** `set_proactive_opt_out` — `INSERT ... ON CONFLICT (user_id) DO UPDATE SET ...` (Pitfall 3 guard: `username` is `NOT NULL`, a user may run `/memory callbacks` before ever queuing a song).

### Self-scoped, ephemeral, choice-constrained slash subcommand
**Source:** `cogs/memory.py:224-289` (`memory_view`, `memory_forget`)
**Apply to:** `memory_callbacks` — `user_id = str(interaction.user.id)`, no `target` param, `ephemeral=True`, `app_commands.Choice`-constrained input.

### Gemini-first / guaranteed-template-fallback generator (reused wholesale, not duplicated)
**Source:** `cogs/events.py:87-172` (`_generate_ambient_roast`)
**Apply to:** the proactive callback's text generation — D-04 forbids a second recall/Gemini pipeline; extend the signature (`pre_recalled_memories` param) rather than fork.

## No Analog Found

None — every file in scope has a direct, previously-shipped analog in this codebase (Phases 8, 10, 11, 15). This phase is 100% new composition of existing patterns.

## Metadata

**Analog search scope:** `logic/`, `cogs/events.py`, `cogs/memory.py`, `database.py`, `config.py`, `tests/`
**Files scanned (this pass):** `logic/roasts.py` (full), `cogs/events.py` (targeted: lines 1-200, 340-368), `database.py` (targeted: lines 88, 171, 280-320), `cogs/memory.py` (lines 224-292)
**Pattern extraction date:** 2026-07-03
