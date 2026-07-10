# Phase 20: Owner Control Plane & Rate Observability - Research

**Researched:** 2026-07-11
**Domain:** discord.py 2.7 command-tree enforcement, asyncpg per-guild state, in-memory rate observability
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

> Every decision below was explicitly selected by the user across nine AskUserQuestion rounds
> (four chosen gray areas, each deep-dived). The user selected the recommended option in every
> round — these are affirmative choices, not AFK adoptions. Copied verbatim (condensed rationale)
> from `20-CONTEXT.md`; see that file for full rejected-alternatives prose per decision.

### Locked Decisions

**Blacklist storage — resolving the D-12 landmine (OWNER-04)**
- **D-01:** the blacklist lives in its OWN `guild_blocklist` table, NOT the `guild_config.is_blocked` column. A dedicated single-purpose table (`guild_id TEXT PRIMARY KEY`, `reason TEXT`, `blocked_at TIMESTAMPTZ DEFAULT now()`) following the `guild_jams`/`resolution_cache` idiom. This resolves the Phase 19 D-12 collision by construction: Phase 21's MEM-04 purge deletes `guild_config`/`guild_queues`/`guild_jams`/guild-scoped `user_memories` freely and never touches `guild_blocklist`.
- **D-02:** the block is READ from an in-memory blocked-set cache — load all blocked `guild_id`s into a `set[str]` at boot, push-invalidate on `/guilds block`/`/guilds unblock`. The two hot paths (`interaction_check` on every slash command; `on_guild_join` re-invite refusal) and the OWNER-06 TOCTOU ambient re-check do an O(1) set membership test with NO Neon round-trip. Block/unblock writes the DB then mutates the set.
- **D-03:** `GuildConfigService` owns the blocked-set; the dead `is_blocked` column is left in place, documented. Extend the existing service with `_blocked: set[str]` + `block_guild(guild_id, reason)`/`unblock_guild(guild_id)`/`is_blocked(guild_id) -> bool`. The `guild_config.is_blocked` column Phase 18 shipped is left unused with its `false` default (harmless) and CLAUDE.md is annotated that `guild_blocklist` is authoritative. No destructive DDL.

**Owner control surface (OWNER-01…06)**
- **D-04:** a single `/guilds` `app_commands.Group` — `/guilds list`, `/guilds silence`, `/guilds unsilence`, `/guilds leave`, `/guilds block`, `/guilds unblock`. Mirrors the `/memory`, `/playlist`, `/jam` group idiom.
- **D-05:** the group lands in `cogs/ops.py`. Phase 19 D-04 explicitly left `ops.py` "clean for Phase 20's owner control plane." `ops.py` is the owner/analytics surface gated by `is_owner()` — the correct home for an owner-gated control group. (`cogs/admin.py` is the guild-admin surface, `manage_guild`-gated — a different audience.)
- **D-06:** global `tree.sync()` + `default_permissions(administrator=True)` as a UI hint ONLY; the real gate is the inline `is_owner()` check. Sync globally like every other command. The command is visible (greyed-out) in other guilds' pickers — accepted.
- **D-07:** destructive actions execute IMMEDIATELY with an in-persona ephemeral echo — no danger-confirm. Both `/guilds leave` and `/guilds block` are reversible (re-invite after leave; `/guilds unblock`), unlike `/memory forget`'s unrecoverable delete. Reply ephemerally, in persona, echoing name + `guild_id` + new guild count.

**RATE-01 usage counter**
- **D-08:** an in-memory `dict[guild_id -> int]` in `GeminiService`, since-boot (per-session), reset on restart. `/guilds list` labels it "this session." Cheap, zero new schema, zero DB writes on the hot AI path.
- **D-09:** an optional `guild_id: str | None = None` keyword on `chat()` and `generate_image()`; count guild-attributable chat/image calls only. Each call site passes its guild (`interaction.guild_id`, `message.guild.id`). Guild-less background calls (the `daily_batch` distill, `/ask` in a DM) pass `None` and are not counted. `embed()` is NOT tagged — it lives on the separate 60 RPM limiter, a different budget the `/guilds` kill-switch cannot remedy.
- **D-10:** `/guilds list` renders one row per guild — name, copy-pasteable `guild_id`, member count, status flags (`configured`/`silenced`/`blocked`), and session AI calls — sorted by AI calls descending. Paginate with the existing char-budget pattern. Ephemeral. No silent truncation.

**Silence & block enforcement / UX (OWNER-02/05/06)**
- **D-11:** `/guilds block` = full force-leave teardown + blacklist insert; `/guilds leave` stays a standalone non-blacklisting exit. `block` runs the OWNER-03 teardown (bump `_play_generation`, clear queue, disconnect voice, `clear_persisted`) then inserts into `guild_blocklist`. `leave` does the same teardown without the blacklist. `unblock` deletes from the blocklist and does not re-join.
- **D-12:** a user in a SILENCED guild gets an in-persona EPHEMERAL notice (e.g. "i've been muted in this server. not my call.") from `interaction_check`. Only the invoker sees it; nobody is publicly dunked on; it avoids Discord's ugly "application did not respond" timeout. Ambient behavior in a silenced guild is total silence — no reply at all.
- **D-13:** `interaction_check` refuses on `silenced OR blocked`, always exempts `is_owner`, and always allows DMs/guild-less interactions. Owner exemption — the owner is never locked out of `/guilds` (even in an edge-case self-silenced guild). DM exemption — `interaction.guild is None` → allow. Both flags checked — blocked is checked defensively even though D-11's block-implies-leave usually means the bot is not present, covering the block-written-while-leave-in-flight window.
- **D-14 (carried as a hard constraint):** the silenced check is a NEW reader inside the pure `logic/guild_config.decide_ambient_channel`, AND is TOCTOU re-checked immediately before the final ambient send (OWNER-06/SC-2). Ambient handlers do seconds-long async Gemini work; a silence issued during that window must take effect on the very next event and never let a stale in-flight response slip through. `silenced` is read from the existing `GuildConfigService` config cache (already hot-path-safe) — no new mechanism. Block need not be added to `decide_ambient_channel` (block force-leaves, so no ambient fires), but the pre-send re-check covers both flags for safety.

### Claude's Discretion

- Exact DDL for `guild_blocklist` — column types, whether `reason` is nullable, any index (the `guild_id` PK suffices). Follow the `guild_jams`/`resolution_cache` idiom; plain param-free DDL in `SCHEMA_SQL`'s single `conn.execute()`.
- DB helper shapes — `load_blocklist()`, `insert_blocklist(guild_id, reason)`, `delete_blocklist(guild_id)`, mirroring the `get/set_proactive_opt_out` upsert-helper shape and `load_all_guild_configs`.
- Silenced get/set helpers + service methods — `silence_guild`/`unsilence_guild`/`is_silenced` on `GuildConfigService`, writing the existing `guild_config.silenced` column and push-invalidating the config cache. Whether `is_silenced` reads the cache row or a derived set.
- Whether the pure `logic/guild_config` seam grows a silenced-aware helper vs adding the `silenced` check inside the existing `decide_ambient_channel` branch — so long as it stays keyword-only, `discord`-free, `datetime`-free, `random`-free, and mock-free tested, and the glue dispatches on the return value (Phase 10 D-02).
- Exact `guild_id` argument type on the subcommands (a `str` parsed to int, since guild IDs exceed Discord's slash-command integer range concerns — verify; the join notice already renders it as copy-pasteable text per Phase 19 D-16).
- The `CommandTree.interaction_check` wiring — whether it is an override on the `DexterBot`/a custom `CommandTree` subclass, or set on `bot.tree`. The service reference must be reachable (`bot.guild_config`) at check time.
- Exact copy for the silenced refusal, the `/guilds list` rows, and the block/leave/silence echoes — subject to the personality rules (lowercase, one emoji max, under 500 chars, sarcasm dialed back for functional info).
- Which exact Gemini call sites pass `guild_id` — the greps in CONTEXT.md's code_context are a starting point (`cogs/ai.py`, `cogs/events.py`, `cogs/music.py`, `cogs/library.py`, `cogs/imagine.py`); verify by call-site. `services/memory.py:383` (`daily_batch` distill) passes `None`.
- `/guilds list` pagination threshold and per-row formatting within the char budget.
- Testing split — mock-free TDD for any new pure logic (silenced-aware resolver, the block-check decision); live-DB tests for the new `guild_blocklist` + silenced helpers; `cogs/ops.py` `/guilds` glue and `interaction_check` are untested-by-design (structural review + clean boot).

### Deferred Ideas (OUT OF SCOPE)

- **MEM-04 guild-data purge on removal** (`guild_config`, `guild_queues`, `guild_jams`, guild-scoped `user_memories`) → Phase 21. Phase 20's `guild_blocklist` table is deliberately OUT of that purge's scope (D-01).
- **Memory guild-scoping** (MEM-01/02/03/05) → Phase 21, under the standing Descope Rule.
- **SCALE-F1 — a soft per-guild rate ceiling on priority-2 Gemini calls** → conditional and future. RATE-01's observability (D-08/D-10) is the prerequisite; the ceiling ships "only if observability proves starvation is real." Not this phase.
- **DB-persisted / historical per-guild usage analytics** — rejected in D-08 as heavier than a live triage view needs.
- **A confirm/undo ceremony on force-leave/block** — rejected in D-07 (reversible ops).
- **`/invite` + least-privilege OAuth2 URL** → Phase 22.
- **Landing page, case-study README, build badge, Pages CD, GHCR** → Phase 23. The kill-switch is PORT-04 disclosure material.
- **Ripping out the dead `guild_config.is_blocked` column** — left in place (D-03); a later cleanup at most, never a Phase 20 blocker.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-------------------|
| OWNER-01 | The owner can list every server Dexter is in, with per-guild AI usage visible | Pattern 5 (`/guilds list` group + char-budget pagination); RATE-01's `GeminiService` per-guild dict is the data source |
| OWNER-02 | The owner can silence a guild — Dexter stays joined but suppresses ambient behavior and commands | Pattern 4 (`decide_ambient_channel` silenced branch) + Pattern 1 (`interaction_check` silenced refusal) |
| OWNER-03 | The owner can force-leave a guild, with teardown mirroring `clear_persisted()` | Pattern 3 (verbatim `/stop` teardown template, adapted for an owner-targeted guild via `bot.get_guild`) + Pitfall 2/3 |
| OWNER-04 | Blocked guilds persist in a blacklist; a re-invite is refused via a block-check-first in the guild-join handler | Pattern 2 (`guild_blocklist` independent table + `_blocked` set) |
| OWNER-05 | A single choke point enforces the block for slash commands and a single seam enforces it for ambient behavior | Pattern 1 (`CommandTree.interaction_check`, verified mechanics) + Pattern 4 (`decide_ambient_channel`) |
| OWNER-06 | Every owner command enforces inline `is_owner()`; the block check is TOCTOU-safe | Pattern 1 (owner-exemption-first predicate) + Pattern 4 (pre-send re-check) + Security Domain STRIDE table |
| RATE-01 | Every Gemini call is tagged with its originating `guild_id`; per-guild usage counters surfaced in `/guilds list` | Code Example on `GeminiService.chat()`/`generate_image()` kwarg + Pitfall 4 (`_build_roast_line` threading gap) + verified call-site inventory |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

Directives this phase must not contradict:

- **Critical Rule 1:** All AI features share the 15 RPM Gemini limiter. RATE-01's per-guild dict counter is purely additive observability alongside the existing `_RateLimiter` — it must NOT introduce a second limiter or gate (D-09 is explicit: "not a quota system").
- **Critical Rule 8/6:** Lowercase everything, one emoji max, dial back sarcasm for functional/serious content — applies to the D-12 silenced refusal and all `/guilds` echo copy.
- **Critical Rule 9:** Designated-channel-only ambient output — the D-14 silenced branch is an additional gate on top of this existing discipline, not a replacement.
- **Implementation Gotcha (asyncpg multi-statement DDL):** `SCHEMA_SQL` is plain, `$N`-param-free DDL applied in a single `conn.execute()` — the new `guild_blocklist CREATE TABLE IF NOT EXISTS` must be appended into that same string, not run separately.
- **Implementation Gotcha (`logic/` pure-seam rule):** glue dispatches on the returned value from `logic/guild_config.py`; it must never re-derive the `silenced`/`configured`/toggle branch logic locally (this is exactly the discipline Anti-Patterns calls out below).
- **Database Schema section:** must be updated when `guild_blocklist` lands, and the running narrative should note `guild_config.is_blocked` is now dead/superseded (D-03).

## Summary

Phase 20 is almost entirely additive plumbing over the seams Phase 18/19 already built: `GuildConfigService`'s cache + push-invalidate discipline, `logic/guild_config.py`'s pure decision seam, the `app_commands.Group` idiom (`/memory`, `/setup`), and the `clear_persisted()` teardown template already exercised by `/stop` and `idle_check`. There is exactly one genuinely new piece of framework mechanics: wiring `CommandTree.interaction_check` as the OWNER-05 slash-command choke point. I verified this directly against the installed `discord.py==2.7.1` package (not training memory) and the mechanics are stricter than the CONTEXT.md canonical-refs section implies — **`interaction_check` returning `False` does NOT dispatch to `bot.tree.error`; it silently short-circuits.** The ephemeral D-12 refusal message MUST be sent from inside `interaction_check` itself, before returning `False`. This resolves the MEDIUM-confidence flag STATE.md carried forward ("verify against the installed discord.py version") to HIGH confidence, and changes the shape of the implementation from "raise CheckFailure, handle in tree.error" to "send the message inline, then return False."

Every other technical question in the phase resolves to: extend an existing service/table/cog with one more concern, following an idiom that already exists three-to-five times in this codebase (the `guild_jams`/`resolution_cache` DDL shape, the get/set-then-push-invalidate service method shape, the `app_commands.Group` + char-budget pagination shape, the `bump-generation → clear → clear_persisted → disconnect` teardown shape). No new dependencies, no new tables beyond `guild_blocklist`, no new limiters — confirmed against `requirements.txt` and the locked CONTEXT.md discretion list.

**Primary recommendation:** Wire a `DexterCommandTree(app_commands.CommandTree)` subclass (passed via `tree_cls=` to the `DexterBot` constructor) whose `interaction_check` performs the full D-13 predicate (owner exempt → DM exempt → blocked-or-silenced refuse-with-message → allow) and returns a bool; never raise `CheckFailure`. Add `guild_blocklist` as a fully independent table (D-01) with its own boot-time `set[str]` cache on `GuildConfigService` (D-02/D-03). Add a `silenced` branch to `decide_ambient_channel` exactly like the existing `configured`/toggle branches (D-14). Thread an optional `guild_id: str | None = None` kwarg through `GeminiService.chat()`/`generate_image()` only, backed by a plain `dict[str, int]` counter (D-08/D-09). Land the `/guilds` `app_commands.Group` in `cogs/ops.py` (D-04/D-05), reusing the `MemoryPageView`/`LyricsPageView` char-budget pagination shape (D-10) and the `/stop` teardown template verbatim (D-11).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Slash-command block/silence enforcement | API/Backend (`CommandTree.interaction_check`) | — | Single choke point ahead of every command dispatch; not a per-cog concern (OWNER-05) |
| Ambient-behavior block/silence enforcement | API/Backend (`logic/guild_config.decide_ambient_channel`) | Service (`GuildConfigService` cache read) | Pure decision seam, mirrors the existing `configured`/toggle branches; no discord I/O |
| Blocklist storage + cache | Database (`guild_blocklist` table) | Service (`GuildConfigService._blocked` set) | O(1) hot-path read, zero Neon round-trip (CONFIG-03 discipline extended) |
| `/guilds` owner command surface | API/Backend (`cogs/ops.py` cog) | — | Discord-glue tier; dispatches on pure-logic/service return values only |
| Per-guild Gemini usage counter | API/Backend (`GeminiService` in-memory dict) | — | Same tier as the existing `_RateLimiter`/`rpm_usage` — in-process, since-boot state |
| Force-leave teardown | API/Backend (`cogs/ops.py` glue, calling `models/queue.py` + `services/queue_persistence.py`) | Client (voice disconnect via discord.py's `VoiceClient`) | Mirrors `/stop`'s existing bump-generation → clear → clear_persisted → disconnect sequence exactly |

## Standard Stack

No new dependencies. This phase extends four already-present modules (`database.py`, `services/guild_config.py`, `services/gemini.py`, `cogs/ops.py`) and adds one new pure-logic branch (`logic/guild_config.py`). `discord.py`, `asyncpg`, and `google-genai` are already pinned in `requirements.txt`.

### Core (already present, extended this phase)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| discord.py | 2.7.1 (installed; `requirements.txt` pins `>=2.3.0`) [VERIFIED: `python -c "import discord; print(discord.__version__)"` in this repo's venv] | `CommandTree` subclassing, `app_commands.Group`, slash commands | Already the project's only Discord library |
| asyncpg | 0.31.0 (per CLAUDE.md) | `guild_blocklist` table + helpers | Already the project's only DB driver |
| google-genai | (pinned, unchanged) | `GeminiService.chat`/`generate_image` guild_id kwarg | No API surface change beyond an added kwarg |

### Supporting
None new. `pgvector`, `beautifulsoup4`, `lyricsgenius` etc. are untouched by this phase.

### Alternatives Considered
Not applicable — every implementation decision in this phase is already locked in 20-CONTEXT.md (D-01 through D-14). Research below verifies the *mechanics* of those decisions rather than proposing alternatives.

**Installation:** None required — zero new packages this phase.

**Version verification:** `discord.py` confirmed installed at 2.7.1 via direct interpreter check in this repo's environment (not the registry) — this is the exact version whose `CommandTree` source was read to resolve the `interaction_check` mechanics below.

## Package Legitimacy Audit

**Not applicable.** This phase installs zero new external packages (confirmed against CONTEXT.md's Discretion list and cross-checked against `requirements.txt` — no additions). The Package Legitimacy Gate protocol is a no-op this phase.

## Architecture Patterns

### System Architecture Diagram

```
                    ┌─────────────────────────────────────────┐
                    │   Discord Gateway (interaction/message)   │
                    └───────────────┬───────────────┬─────────┘
                                    │               │
                     slash command  │               │  message (ambient surfaces)
                                    ▼               ▼
                    ┌───────────────────────┐   ┌─────────────────────────────┐
                    │ DexterCommandTree      │   │ cogs/events.py::on_message  │
                    │ .interaction_check()   │   │  + voice-state handlers     │
                    │  (OWNER-05 choke pt 1) │   │  + cogs/music.py roasts      │
                    └───────────┬───────────┘   └───────────┬─────────────────┘
                                │ allow/refuse                │ resolve_ambient_channel(surface=...)
                                ▼                              ▼
                    ┌───────────────────────┐   ┌─────────────────────────────┐
                    │  command body runs     │   │ GuildConfigService          │
                    │  (existing cogs)       │   │  .resolve_ambient_channel() │
                    └───────────────────────┘   │   → logic.decide_ambient_   │
                                                 │     channel (OWNER-05       │
                                                 │     choke pt 2, D-14 adds   │
                                                 │     `silenced` branch)      │
                                                 └───────────┬─────────────────┘
                                                              │ cache read (O(1), no I/O)
                                                              ▼
                                          ┌───────────────────────────────────┐
                                          │ GuildConfigService in-memory cache │
                                          │  _cache: dict[guild_id -> Record] │
                                          │  _blocked: set[guild_id]  (D-02)   │
                                          └───────────────┬───────────────────┘
                                                           │ boot load_all() + push-invalidate
                                                           ▼
                                          ┌───────────────────────────────────┐
                                          │ Postgres (Neon): guild_config,     │
                                          │  guild_blocklist (NEW, D-01)       │
                                          └───────────────────────────────────┘

  Owner surface:
    /guilds list/silence/unsilence/leave/block/unblock (cogs/ops.py, D-04/D-05)
       ├─ list    → reads GuildConfigService cache + GeminiService per-guild dict (D-08)
       ├─ silence/unsilence → writes guild_config.silenced, push-invalidates cache
       ├─ leave   → bump _play_generation → queue.clear() → clear_persisted() →
       │            voice_client.stop()+disconnect() (D-11, mirrors /stop verbatim)
       └─ block   → same teardown as leave, THEN INSERT INTO guild_blocklist (D-11)
                    push-invalidates _blocked set (D-02)

  Gemini usage tagging (RATE-01):
    cogs/ai.py, events.py, music.py, library.py, imagine.py
       → GeminiService.chat(..., guild_id=str|None) / generate_image(..., guild_id=str|None)
       → self._guild_usage: dict[str, int] += 1  (D-08, in-memory, since-boot)
       → surfaced read-only in /guilds list
```

### Recommended Project Structure

No new files beyond what CONTEXT.md's Integration Points already names. Touched files:

```
database.py                 # + guild_blocklist DDL, load/insert/delete helpers, silenced get/set
services/guild_config.py    # + _blocked set, block_guild/unblock_guild/is_blocked, silence_guild/unsilence_guild
logic/guild_config.py       # + silenced branch inside decide_ambient_channel (or a sibling pure fn)
services/gemini.py          # + guild_id kwarg on chat()/generate_image(), _guild_usage dict, accessor
bot.py                      # + DexterCommandTree subclass + tree_cls= wiring, block-check-first in on_guild_join
cogs/ops.py                 # + /guilds app_commands.Group (list/silence/unsilence/leave/block/unblock)
cogs/ai.py, events.py,      # + guild_id kwarg threaded at each chat()/generate_image() call site
  music.py, library.py,
  imagine.py
```

### Pattern 1: `CommandTree` subclass as the single slash-command choke point

**What:** A `CommandTree` subclass overriding `interaction_check(self, interaction) -> bool`, wired via `tree_cls=` on the bot constructor.

**Verified mechanics** [VERIFIED: discord.py 2.7.1 installed source, `discord/app_commands/tree.py`]:

```python
# discord/app_commands/tree.py (installed package, lines ~1135-1270, paraphrased)
def _from_interaction(self, interaction):
    async def wrapper():
        try:
            await self._call(interaction)
        except AppCommandError as e:
            await self._dispatch_error(interaction, e)   # -> self.on_error(...) -> @bot.tree.error
    self.client.loop.create_task(wrapper(), name='CommandTree-invoker')

async def _call(self, interaction):
    if not await self.interaction_check(interaction):
        interaction.command_failed = True
        return                                            # <-- SILENT. No on_error. No CheckFailure.
    ...
    try:
        await command._invoke_with_namespace(interaction, namespace)
    except AppCommandError as e:
        await command._invoke_error_handlers(interaction, e)
        await self.on_error(interaction, e)
```

This means the CONTEXT.md canonical-refs phrasing ("send... vs raise `app_commands.CheckFailure` handled in `bot.tree.error`") is a false choice — **only the first option works without a code change to `on_error`.** If `interaction_check` returns `False` without having sent a response, Discord shows the generic "This interaction failed" — not technically the "application did not respond" timeout (that specific message is for a 3-second ack timeout), but still an unhandled-looking failure. D-12 requires the ephemeral copy, so the check must respond before returning `False`.

`commands.Bot.__init__` accepts `tree_cls: Type[CommandTree] = CommandTree` [VERIFIED: `inspect.signature(commands.Bot.__init__)` on the installed package shows `tree_cls: 'Type[app_commands.CommandTree[Any]]' = <class 'discord.app_commands.tree.CommandTree'>`].

**Recommended implementation shape:**

```python
# bot.py — new, near the DexterBot class
class DexterCommandTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # D-13: owner exemption first (cheap, and must never lock the owner out)
        if await interaction.client.is_owner(interaction.user):
            return True
        # D-13: DM / guild-less interactions always allowed
        if interaction.guild is None:
            return True

        guild_config = getattr(interaction.client, "guild_config", None)
        if guild_config is None:
            # Structural absence (boot race) — fail OPEN here, not closed. This is
            # NOT the ambient-silence fail-closed rule (D-07): blocking every
            # command bot-wide on a boot race is a worse outcome than a few-second
            # window where a not-yet-blocked guild can still run commands.
            return True

        guild_id = str(interaction.guild.id)
        if guild_config.is_blocked(guild_id) or guild_config.is_silenced(guild_id):
            # D-12: in-persona ephemeral notice, sent HERE (interaction_check has no
            # error-handler round-trip) — must ack before returning False.
            await interaction.response.send_message(
                "i've been muted in this server. not my call.",
                ephemeral=True,
            )
            return False
        return True


def create_bot() -> DexterBot:
    ...
    bot = DexterBot(
        command_prefix="!",
        intents=intents,
        activity=...,
        owner_id=config.OWNER_ID or None,
        tree_cls=DexterCommandTree,   # NEW
    )
    return bot
```

**When to use:** This is the OWNER-05 slash-command choke point. Every existing and future slash command gets enforcement for free — no per-cog decorator, no per-command check.

### Pattern 2: `guild_blocklist` as an independent table (D-01)

**What:** A standalone table, not a column, so Phase 21's MEM-04 purge can `DELETE ... WHERE guild_id = $1` against `guild_config`/`guild_queues`/`guild_jams`/`user_memories` with zero special-casing.

**Example** [VERIFIED: mirrors the `guild_jams`/`resolution_cache` idiom already in `database.py:178-197`]:

```sql
-- database.py SCHEMA_SQL, appended after the guild_config ALTERs (idempotent, param-free)
CREATE TABLE IF NOT EXISTS guild_blocklist (
    guild_id   TEXT PRIMARY KEY,
    reason     TEXT,
    blocked_at TIMESTAMPTZ DEFAULT now()
);
```

Helper shape mirrors `load_all_guild_configs` / `get_proactive_opt_out` / `set_proactive_opt_out`:

```python
async def load_blocklist(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT guild_id, reason, blocked_at FROM guild_blocklist")

async def insert_blocklist(pool: asyncpg.Pool, *, guild_id: str, reason: str | None) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO guild_blocklist (guild_id, reason) VALUES ($1, $2)"
            " ON CONFLICT (guild_id) DO UPDATE SET reason = EXCLUDED.reason",
            guild_id, reason,
        )

async def delete_blocklist(pool: asyncpg.Pool, *, guild_id: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM guild_blocklist WHERE guild_id = $1", guild_id)
```

`GuildConfigService` grows `_blocked: set[str]`, populated in `load_all()` (a second query alongside `load_all_guild_configs`) and push-invalidated in `block_guild`/`unblock_guild` — exactly the D-02 O(1)-read, write-then-mutate discipline.

### Pattern 3: The `/stop` teardown template, verified verbatim (D-11)

**What:** The canonical bump-generation → clear → clear_persisted → disconnect sequence, taken directly from `cogs/music.py`'s `/stop` command [VERIFIED: `cogs/music.py:1714-1727`]:

```python
# cogs/music.py::stop (existing, unmodified — the template OWNER-03 mirrors)
queue._play_generation += 1   # invalidate any pending after-callbacks
queue.clear()                 # also re-bumps _play_generation (models/queue.py:226) — idempotent, monotonic
if hasattr(self.bot, "queue_persistence"):
    await self.bot.queue_persistence.clear_persisted(interaction.guild.id)

if voice_client:
    voice_client.stop()
    await voice_client.disconnect()
```

For `/guilds leave <guild_id>` and `/guilds block <guild_id>`, the target guild is **not** `interaction.guild` (the owner invokes from their home guild) — it must be resolved via `bot.get_guild(int(guild_id))`. If that guild lookup fails (bot already not in it, or a bad id), the command should report "not in that guild" without attempting teardown. Recommended shape:

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
await target_guild.leave()   # discord.py Guild.leave() — the actual force-leave
```

`discord.Guild.leave()` is the standard discord.py method for a bot to leave a guild it's a member of [ASSUMED — standard, stable discord.py API, not re-verified against Context7 this session since it is a simple, unchanged method; flagged for a quick sanity check at implementation time].

### Pattern 4: `decide_ambient_channel`'s new `silenced` branch (D-14)

**What:** A new early-return branch in the existing pure function, following the exact same shape as the `configured` and toggle-column checks already there [VERIFIED: `logic/guild_config.py:104-120`]:

```python
def decide_ambient_channel(*, config_row, surface):
    if config_row is None:
        return None
    if not config_row.get("configured", False):
        return None
    if config_row.get("silenced", False):        # NEW (D-14) — same shape as the toggle check below
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

This is a **direct mutation of the existing function**, not a new sibling — CONTEXT.md's Discretion list explicitly permits either shape ("Whether the pure seam grows a silenced-aware helper vs adding the check inside the existing branch"), and mutating in place is lower-churn and keeps `is_ambient_channel` (which dispatches on `decide_ambient_channel`) automatically silenced-aware with no separate change. `silenced` defaults `False` at the column level (Phase 18 D-11), so `config_row.get("silenced", False)` is a safe default even against a stale/partial mapping in a test.

**TOCTOU re-check (D-14 / OWNER-06):** the pre-send re-check the CONTEXT names is a SECOND, later read of the same cache — not a new mechanism. Recommended shape at the point of an ambient send (after the async Gemini round-trip, immediately before `channel.send(...)`):

```python
# re-resolve right before the send — the guild may have been silenced/blocked
# during the Gemini round-trip (D-14 / OWNER-06 TOCTOU close)
channel = self.bot.guild_config.resolve_ambient_channel(guild, surface=AmbientSurface.ROAST)
if channel is None:
    return
await channel.send(line, allowed_mentions=discord.AllowedMentions.none())
```

Since `resolve_ambient_channel` is already synchronous and cache-only (no I/O), re-calling it a second time immediately before the send is free and requires no new function — just calling the existing resolver twice at the two points in the flow (once to decide whether to even generate a Gemini response, once to decide whether to actually post it).

### Pattern 5: `app_commands.Group` + char-budget pagination (D-04/D-10)

**What:** `/guilds` mirrors `cogs/memory.py::MemoryCog`'s `memory = app_commands.Group(...)` shape [VERIFIED: `cogs/memory.py:238-241`] and its `MemoryPageView` char-budget pagination [VERIFIED: `cogs/memory.py:62-143`] — note the CONTEXT.md canonical-refs calls this "`LyricsPageView`" but the actual reusable-in-`cogs/memory.py` class is `MemoryPageView` (a documented clone of `cogs/music.py::LyricsPageView`, same button/embed/timeout shape). Either is a valid template; `MemoryPageView` is one file closer to where `/guilds` will live if a Group-local page-builder is preferred, but `cogs/ops.py` has no existing pagination — the planner should either import `MemoryPageView`-shaped code or write a small `GuildListPageView` following the identical `_build_embed`/`prev_button`/`next_button`/`on_timeout` shape.

```python
guilds = app_commands.Group(
    name="guilds",
    description="owner-only: list, silence, or remove guilds",
    default_permissions=discord.Permissions(administrator=True),  # UI hint ONLY (D-06)
)

@guilds.command(name="list", description="list every guild with session AI usage")
async def guilds_list(self, interaction: discord.Interaction) -> None:
    if not await self.bot.is_owner(interaction.user):
        return await interaction.response.send_message("not authorized.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    rows = []  # build one row per bot.guilds entry, sorted by usage descending (D-10)
    for g in sorted(self.bot.guilds, key=lambda g: self.bot.gemini_service.guild_usage(g.id), reverse=True):
        cfg = self.bot.guild_config.get(g.id)
        flags = []
        if cfg and cfg["configured"]:
            flags.append("configured")
        if self.bot.guild_config.is_silenced(g.id):
            flags.append("silenced")
        if self.bot.guild_config.is_blocked(g.id):
            flags.append("blocked")
        rows.append(f"{g.name} (`{g.id}`) — {g.member_count} members — "
                     f"{self.bot.gemini_service.guild_usage(g.id)} calls — {', '.join(flags) or 'unconfigured'}")
    # paginate `rows` into char-budget pages, mirroring MemoryPageView/LyricsPageView
```

### Anti-Patterns to Avoid
- **Raising `app_commands.CheckFailure` from `interaction_check` expecting `bot.tree.error` to handle it silently as a "check failed" case:** it works (the exception does propagate to `on_error` via `_dispatch_error`), but the existing `on_app_command_error` handler is generic (`log.error` + "something broke" message) — making this route work would require adding an `isinstance` branch there AND still can't avoid the "response already sent vs not sent" ambiguity `interaction_check` can resolve directly. Simpler and requires zero changes to the existing global error handler: send the message inline in `interaction_check`, return `False`.
- **Re-deriving the `silenced`/`is_blocked` branch logic in `cogs/ops.py` or `bot.py` instead of calling into `decide_ambient_channel`/`GuildConfigService`:** violates the Phase 10 D-02 "glue dispatches on the returned value" rule this codebase enforces everywhere else.
- **A live `SELECT` per interaction_check invocation:** directly contradicts CONFIG-03/D-02's zero-Neon-round-trip-on-hot-path discipline this codebase has held since Phase 18.
- **Tagging `embed()` calls with `guild_id`:** explicitly rejected by D-09 — `embed()` lives on the separate 60 RPM limiter, a budget the kill-switch cannot act on.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Slash-command auth gate | A decorator applied to every `/guilds` subcommand individually | `CommandTree.interaction_check` (one override) | OWNER-05's entire point — a future command gets enforcement for free |
| Paginated embed with Prev/Next | A new `discord.ui.View` from scratch | Clone `MemoryPageView`/`LyricsPageView`'s exact shape | Timeout handling, `AllowedMentions.none()`, and `on_timeout` button-disable are already solved and tested there |
| Guild-scoped teardown | A bespoke leave sequence | The `/stop` command's bump→clear→clear_persisted→disconnect sequence, verbatim | This exact sequence is what prevents the double-play race and the ghost-queue-on-restart bug this codebase has scar tests for |
| Snowflake-safe ID parameter | A raw Discord `INTEGER` slash-command option type | `str` slash parameter, `int(guild_id_str)` at the point of use | Discord's slash-command INTEGER option range does not reliably cover the full 64-bit snowflake space in every client (see Assumptions Log A1) |

**Key insight:** Every "don't hand-roll" item above already has a working, tested implementation somewhere in this codebase from Phases 6–19. Phase 20's job is almost entirely "copy the shape, change the column/table name."

## Common Pitfalls

### Pitfall 1: `interaction_check` returning `False` is silent — no `on_error`, no visible failure unless you send one yourself
**What goes wrong:** A naive port of the CONTEXT.md canonical-refs phrasing ("raise `CheckFailure`, handle in `bot.tree.error`") either doesn't work as expected (requires modifying the shared global error handler) or — if the check just returns `False` without responding — Discord shows a generic interaction-failed state with no D-12 copy at all.
**Why it happens:** `CommandTree._call` checks the boolean return, not an exception, and short-circuits with a bare `return` before entering the `try/except AppCommandError` block that feeds `on_error`.
**How to avoid:** Send the ephemeral response from inside `interaction_check` before returning `False`. Verified directly against the installed `discord.py==2.7.1` source this session.
**Warning signs:** A test or manual check where a silenced guild's command shows Discord's default failure state instead of the sarcastic refusal line.

### Pitfall 2: `queue.clear()` already bumps `_play_generation` again — don't double-count as a bug
**What goes wrong:** `models/queue.py::clear()` re-increments `_play_generation` internally (line 226) after the caller already bumped it once at the top of `/stop`. This looks redundant but is intentional — `clear()`'s docstring explicitly warns against resetting the counter to 0.
**Why it happens:** `clear()` is called from multiple sites (not just `/stop`) and must always leave the counter monotonically higher than any pending stale callback, regardless of what the caller already did.
**How to avoid:** For OWNER-03's force-leave, call the exact same two-line sequence (`queue._play_generation += 1` then `queue.clear()`) even though it looks like it double-bumps — this mirrors `/stop` verbatim and is the tested-safe pattern, not a bug to "fix."

### Pitfall 3: The owner-invoked target guild is not `interaction.guild`
**What goes wrong:** `/guilds leave <guild_id>` / `/guilds block <guild_id>` are invoked from the owner's home guild (or a DM), not the guild being acted on. Using `interaction.guild` anywhere in the teardown resolves the wrong guild (or `None` in a DM).
**Why it happens:** Every existing teardown site (`/stop`, `idle_check`) operates on `interaction.guild`/`vc.guild` because the command runs IN the affected guild. `/guilds` is the first owner-command surface that acts on a guild the invoker isn't currently in.
**How to avoid:** Resolve via `self.bot.get_guild(int(guild_id_str))` and pass that `discord.Guild` object explicitly through the whole teardown chain — never reach for `interaction.guild`.

### Pitfall 4: `_build_roast_line` (cogs/music.py) doesn't currently accept a guild reference
**What goes wrong:** RATE-01 needs `guild_id` threaded to the `gemini_service.chat(...)` call at `cogs/music.py:1246`, but that call lives inside `_build_roast_line(self, user_id, scenario_content, fallback_pool, fallback_kwargs)` [VERIFIED: `cogs/music.py:1182-1246`], which has no `guild`/`guild_id` parameter today.
**Why it happens:** The three call sites of `_build_roast_line` (`cogs/music.py:1305/1340/1376`) all have `guild` in scope at the call site (repeat-song and milestone roasts fire from a guild-scoped context) — the parameter just was never threaded through because nothing needed it before RATE-01.
**How to avoid:** Add a keyword-only `guild_id: str | None = None` parameter to `_build_roast_line`'s signature, have each of the three call sites pass their guild's id, and forward it to the `gemini_service.chat(...)` call inside. This is a small, mechanical signature change — verify the exact caller context at each of the three call sites before editing (their scope was not fully re-verified in this research pass; the function signature and the need are confirmed, the caller-side guild availability is asserted but not individually re-read for all three sites).

### Pitfall 5: A cache-miss on `bot.guild_config` at `interaction_check` time is a structural-absence case, not a "guild has no row" case
**What goes wrong:** Treating a missing `bot.guild_config` attribute (a boot race — the service hasn't been constructed yet) the same as "this guild is silenced" would block every single slash command bot-wide, including `/sync`, during the brief startup window.
**Why it happens:** `bot.guild_config` is constructed inside `_initialize_once()`, which runs after `create_bot()`. Discord won't route real interactions until commands are synced (which happens even later), so this window is narrow — but a defensive `getattr(..., None)` check is still worth writing correctly.
**How to avoid:** `interaction_check` should fail OPEN (allow) only for the specific case of `bot.guild_config` not existing at all — this is distinct from D-07's ambient fail-closed rule, which governs "does this guild have a config row," not "does the config service exist yet."

## Code Examples

### Verified: `interaction_check` mechanics (discord.py 2.7.1, installed package)
```python
# Source: discord/app_commands/tree.py (site-packages, this environment) — read directly, not Context7
async def _call(self, interaction: Interaction[ClientT]) -> None:
    if not await self.interaction_check(interaction):
        interaction.command_failed = True
        return
    ...

def _from_interaction(self, interaction: Interaction[ClientT]) -> None:
    async def wrapper():
        try:
            await self._call(interaction)
        except AppCommandError as e:
            await self._dispatch_error(interaction, e)
    self.client.loop.create_task(wrapper(), name='CommandTree-invoker')
```

### Verified: `tree_cls` constructor kwarg (discord.py 2.7.1, installed package)
```python
# inspect.signature(commands.Bot.__init__) on the installed package shows:
# tree_cls: 'Type[app_commands.CommandTree[Any]]' = <class 'discord.app_commands.tree.CommandTree'>
bot = DexterBot(..., tree_cls=DexterCommandTree)
```

### Existing: the `/stop` teardown template (verbatim, the OWNER-03 model)
```python
# Source: cogs/music.py:1714-1727 (existing, unmodified)
queue._play_generation += 1
queue.clear()
if hasattr(self.bot, "queue_persistence"):
    await self.bot.queue_persistence.clear_persisted(interaction.guild.id)
if voice_client:
    voice_client.stop()
    await voice_client.disconnect()
```

### Existing: `decide_ambient_channel`'s current structure (the D-14 insertion point)
```python
# Source: logic/guild_config.py:104-120 (existing, unmodified — D-14 adds one branch)
if config_row is None:
    return None
if not config_row.get("configured", False):
    return None
toggle_column = "vision_roasts_enabled" if surface is AmbientSurface.VISION else "ambient_roasts_enabled"
if not config_row.get(toggle_column, True):
    return None
channel_id = config_row.get("ambient_channel_id")
...
```

### Existing: `GeminiService.chat()` signature (the D-09 insertion point)
```python
# Source: services/gemini.py:173-181 (existing — add guild_id: str | None = None keyword-only)
async def chat(
    self,
    system_prompt: str,
    conversation: list[dict],
    priority: int = 1,
    *,
    image_bytes: bytes | None = None,
    image_mime_type: str | None = None,
    # NEW: guild_id: str | None = None  — counted in a plain dict[str, int] (D-08)
) -> str | None:
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| No owner control surface | `/guilds` group + two-choke-point enforcement | This phase | First reader of Phase 18's forward-shipped `silenced`/`is_blocked` columns |
| Global Gemini RPM usage only (`/stats`) | Per-guild session usage dict alongside the existing global `_RateLimiter` | This phase | Additive — `rpm_usage`/`rpm_headroom` untouched |

**Deprecated/outdated:** None. This phase does not remove or replace any existing mechanism — it is purely additive over Phase 18/19's seams.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Discord's slash-command `INTEGER` option type does not reliably cover the full 64-bit snowflake range in every client, so `guild_id` should be a `str` parameter parsed with `int()` | Don't Hand-Roll; canonical CONTEXT.md discretion note | LOW — this is already the locked discretion-list direction from CONTEXT.md ("guild IDs exceed Discord's slash-command integer range concerns"); even if the range concern is overstated, `str` is still strictly safe and costs nothing versus `int` |
| A2 | `discord.Guild.leave()` is the correct discord.py 2.7 API for a bot to voluntarily leave a guild | Pattern 3 (force-leave) | LOW — this is a long-stable, simple API; a one-line sanity check (`hasattr(discord.Guild, "leave")`, already true in 2.7.1's source tree structure) at implementation time closes this out |
| A3 | The three `_build_roast_line` call sites (`cogs/music.py:1305/1340/1376`) all have a `guild`/`guild.id` value in scope, making the guild_id threading straightforward | Pitfall 4 | MEDIUM — if any call site lacks a resolvable guild reference (e.g. runs from a background loop with only a `guild_id: str`), the threading is still possible but the exact variable name/type at each site needs a fresh read at plan/implementation time |

**If this table is empty:** N/A — see entries above. All three are low-to-medium risk and do not block planning; they are call-site-verification tasks for the plan/implementation stage, not open architectural questions.

## Open Questions

1. **Exact wording for `/guilds list` per-row rendering and the silenced-refusal line**
   - What we know: CONTEXT.md D-10 names the required fields (name, copy-pasteable `guild_id`, member count, status flags, session AI calls, sorted descending); D-12 gives an example refusal line.
   - What's unclear: Final copy is explicitly planner/implementer discretion per CONTEXT.md.
   - Recommendation: Follow the personality rules (lowercase, one emoji max, sarcasm dialed back for functional info) exactly as `cogs/admin.py`'s existing refusal lines do — they are a directly reusable tonal template.

2. **Whether `_build_roast_line`'s three call sites need any additional context threaded besides `guild_id`**
   - What we know: The function signature and the need for a `guild_id` kwarg are confirmed.
   - What's unclear: Whether all three callers cleanly expose a `guild` object at the exact call line (not individually re-verified all three in this pass — see Assumptions Log A3).
   - Recommendation: A 5-minute grep-and-read pass at plan time (`sed -n '1295,1385p' cogs/music.py`) before writing the task, to lock the exact parameter threading.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| discord.py | `CommandTree` subclass, `app_commands.Group` | Yes | 2.7.1 (installed, verified) | — |
| asyncpg | `guild_blocklist` table + helpers | Yes | 0.31.0 (per CLAUDE.md) | — |
| Local/CI Postgres (`TEST_DATABASE_URL`) | New live-DB tests for blocklist/silenced helpers | Yes (CI: `pgvector/pgvector:pg16` service container, per Phase 18 D-15) | pg16 | Tests skip gracefully if unreachable locally (`tests/conftest.py` skip-on-connection-error) |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None — this phase has no dependency gaps.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing suite; 848+ tests as of Phase 19 close) |
| Config file | none dedicated — `pytest.ini`/`pyproject.toml` `[tool.pytest]` section if present; `.github/workflows/ci.yml` runs `pytest -q` |
| Quick run command | `pytest -q tests/test_guild_config_logic.py tests/test_guild_config_service.py -x` |
| Full suite command | `pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OWNER-01 | `/guilds list` renders sorted, paginated rows | Discord/process glue — untested-by-design | structural review + clean boot | N/A (glue) |
| OWNER-02 | Silence/unsilence flips `guild_config.silenced`, ambient resolver returns `None` when silenced | mock-free TDD (pure) + live-DB (helper) | `pytest -q tests/test_guild_config_logic.py -k silenced` | Missing — Wave 0, add case to `tests/test_guild_config_logic.py` |
| OWNER-03 | Force-leave teardown sequence | Discord/process glue — untested-by-design | structural review + clean boot | N/A (glue) |
| OWNER-04 | Blocked guild refused re-entry via `on_guild_join` block-check-first; blocklist survives independent of `guild_config` | mock-free TDD (pure decision) + live-DB (`guild_blocklist` CRUD) | `pytest -q tests/test_database_phase20.py -k blocklist` | Missing — Wave 0, new `tests/test_database_phase20.py` |
| OWNER-05 | Two-choke-point enforcement: `interaction_check` predicate + `decide_ambient_channel` silenced branch | mock-free TDD (both pure/predicate pieces) | `pytest -q tests/test_guild_config_logic.py -k silenced_or_blocked` | Missing — Wave 0, add predicate function + tests |
| OWNER-06 | Owner exemption, DM exemption, TOCTOU re-check both branches | mock-free TDD (predicate) + Discord glue untested-by-design (`interaction_check` itself) | `pytest -q tests/test_guild_config_logic.py -k owner_exempt` | Missing — Wave 0 |
| RATE-01 | `guild_id`-tagged Gemini counter increments correctly; `None` guild_id not counted | mock-free TDD (`GeminiService` unit, fake client) | `pytest -q tests/test_gemini_service.py -k guild_usage` (file may not exist — check for an existing `test_gemini*.py`) | Missing — Wave 0, verify/create test file |

### Sampling Rate
- **Per task commit:** `pytest -q tests/test_guild_config_logic.py tests/test_guild_config_service.py -x`
- **Per wave merge:** `pytest -q` (full suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`; CI's `pgvector/pgvector:pg16` service container (Phase 18 D-15) exercises the new live-DB blocklist/silenced tests.

### Wave 0 Gaps
- [ ] A test file for the `guild_blocklist` DB helpers (live-DB) — likely `tests/test_database_phase20.py`, mirroring `tests/test_database_phase16.py`'s shape for `proactive_opt_out`.
- [ ] `tests/test_guild_config_logic.py` additions: the `silenced` branch inside `decide_ambient_channel`, plus whatever pure predicate backs `interaction_check` (e.g. a `should_refuse_interaction(*, is_owner, has_guild, silenced, blocked) -> bool` extracted so the choke-point logic itself is mock-free-testable, not just exercised via a live `discord.Interaction`).
- [ ] `tests/test_guild_config_service.py` additions: `_blocked` set load/push-invalidate behavior (fake-pool pattern already established there).
- [ ] Check for an existing Gemini service unit test file before creating a new one — grep `tests/` for `gemini` first.
- [ ] **Known regression surface (not a gap, but must be updated, not newly written):** `tests/test_proactive_events.py` mocks `bot.guild_config.get = MagicMock(...)` in at least 6 places [VERIFIED: grep] — every one of these fixtures needs its returned mapping to include a `silenced` key (or rely on the `.get(..., False)` default) so the new branch doesn't change existing test behavior unexpectedly. Treat this as a call-site inventory, per CONTEXT.md's own instruction.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | yes | `bot.is_owner(interaction.user)` — Discord's own OAuth identity, already the established pattern (`cogs/ops.py:252`, `cogs/admin.py:80`) |
| V3 Session Management | no | Discord interactions are single-shot; no session state to manage |
| V4 Access Control | yes | Owner-only gate on every `/guilds` subcommand (inline, first statement — OWNER-06); `interaction_check`'s owner-exemption-first ordering |
| V5 Input Validation | yes | `guild_id` slash parameter parsed via `int(guild_id_str)` with a try/except — an owner-supplied but still-untrusted-format string; a non-numeric value must not raise an unhandled exception into the interaction |
| V6 Cryptography | no | No new cryptographic surface this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Non-owner invokes `/guilds *` | Elevation of Privilege | Inline `await bot.is_owner(interaction.user)` FIRST, before any data access (OWNER-06, mirrors existing `/stats` discipline) |
| TOCTOU: guild silenced/blocked mid-flight (during a Gemini round-trip) | Tampering (of authorization state) | D-14's pre-send re-check — re-resolve `resolve_ambient_channel`/`is_blocked` immediately before the final send, not just at entry |
| Block written while a force-leave is already in-flight (race between two owner actions) | Tampering / Denial-of-Service-to-self | D-13's "check both flags defensively" — `interaction_check` checks `is_blocked OR is_silenced` even though block normally implies the bot has already left, covering the narrow window |
| Owner accidentally self-locks out via silencing their own home guild | Denial of Service (self-inflicted) | D-13's unconditional owner exemption in `interaction_check` — owner is never refused regardless of guild state |
| Malformed/non-numeric `guild_id` argument to `/guilds leave` | Tampering (malformed input) | `int(guild_id_str)` wrapped in try/except, ephemeral "that's not a valid guild id" reply — never let a `ValueError` propagate into the generic error handler |
| Guild name / owner tag rendered in owner-facing embeds (already solved in Phase 19) | Injection (embed/markdown) | Existing `_build_guild_notice_embed`'s plain-field-value discipline [VERIFIED: `bot.py:633-657`] — `/guilds list` rows should follow the identical convention (plain text, backtick-wrapped IDs, never markdown-interpolated guild names) |

## Sources

### Primary (HIGH confidence)
- Installed `discord.py==2.7.1` source (`site-packages/discord/app_commands/tree.py`, `discord/ext/commands/bot.py`) — read directly via `inspect` in this repo's Python environment. This is the authoritative source for `interaction_check`/`tree_cls`/`_call`/`_from_interaction` mechanics documented above.
- Direct codebase reads: `bot.py`, `database.py`, `services/guild_config.py`, `logic/guild_config.py`, `services/gemini.py`, `cogs/ops.py`, `cogs/memory.py`, `cogs/admin.py`, `models/queue.py`, `services/queue_persistence.py`, `cogs/music.py`, `cogs/ai.py`, `cogs/events.py`, `cogs/library.py`, `cogs/imagine.py`, `tests/test_guild_config_logic.py`, `tests/test_guild_config_service.py`, `tests/test_proactive_events.py`, `tests/conftest.py`, `.github/workflows/ci.yml`.
- `.planning/phases/20-owner-control-plane-rate-observability/20-CONTEXT.md`, `19-CONTEXT.md`, `18-CONTEXT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md` — the locked decision spine for this phase.

### Secondary (MEDIUM confidence)
- Context7 (`/rapptz/discord.py`) query results — did not surface the exact `interaction_check`/`tree_cls` mechanics directly (its indexed snippets cover `GroupCog.interaction_check` and general check-failure patterns, not `CommandTree.interaction_check`'s silent-short-circuit behavior); superseded by the direct installed-source read above, which is more authoritative for this specific mechanic.

### Tertiary (LOW confidence)
- None used as load-bearing claims — every mechanical claim about discord.py behavior was verified against the installed package source rather than left as training-data assumption.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies, all existing and pinned.
- Architecture: HIGH — `interaction_check` mechanics verified against installed source; every other pattern is a direct extension of an existing, already-shipped codebase idiom.
- Pitfalls: HIGH for Pitfalls 1–3 and 5 (verified against source/codebase); MEDIUM for Pitfall 4 (the three `_build_roast_line` call sites' exact local variable names were not individually re-read in full for all three sites — flagged in the Assumptions Log, not blocking).

**Research date:** 2026-07-11
**Valid until:** 30 days (stable — no fast-moving external dependency; the only expiry risk is a discord.py version bump past 2.7.x changing `CommandTree` internals, which would need a re-verification pass)
