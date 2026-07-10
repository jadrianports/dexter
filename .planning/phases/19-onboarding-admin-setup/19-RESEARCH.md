# Phase 19: Onboarding & Admin Setup - Research

**Researched:** 2026-07-10
**Domain:** discord.py 2.7.1 slash-command UX (typed channel params, permission gating, guild-only
enforcement), asyncpg 0.31.0 INSERT…RETURNING idempotency signaling, multi-tenant lifecycle events
(`on_guild_join`/`on_guild_remove`/boot backfill) on top of the Phase 18 `GuildConfigService` seam.
**Confidence:** HIGH — every mandatory verification target was confirmed by reading the actual
installed library source (`.venv/Lib/site-packages/discord/…`, `asyncpg` docstrings) and the actual
codebase, not from training-data recall. Zero new external dependencies this phase.

## Summary

Phase 19 is glue work over a seam Phase 18 already built correctly. All three "mandatory
verification target" premises in CONTEXT.md are **VERIFIED true** against discord.py 2.7.1 and
asyncpg 0.31.0 — none of the 26 locked decisions need to be reopened. The two hazards worth the
planner's close attention are not in the three flagged assumptions; they're in two live code
findings this research turned up:

1. **`cogs/music.py`'s three roast sites are not merely "unenumerated" — they don't call the
   config seam at all.** `_post_music_roast` (`cogs/music.py:1168`) still resolves its channel via
   `_get_text_channel` (`:973`), the pre-Phase-18 "wherever `/play` was last run" fallback. It was
   never touched by Phase 18's consolidation. Repeat-song and both milestone roasts
   (`cogs/music.py:1288/1329/1358`, all funneling through `_post_music_roast` at `:1311/1342/1381`)
   currently fire in an **unconfigured guild** the moment someone plays music — a live CONFIG-04
   hole exactly like D-21's reaction hole, just not named as one. Phase 19 must swap this call to
   `resolve_ambient_channel(guild, surface=AmbientSurface.ROAST)`, not just add a `surface` kwarg
   to an existing call.
2. **`_post_startup_messages` (`bot.py:514-536`) currently sends to every guild `resolve_ambient_channel`
   returns a channel for** — not the home guild only. D-23 requires narrowing this to
   `home_guild_id`, which is a real behavior change to existing Phase 18 code, not a net-new
   conditional.

Both are flagged explicitly in Architecture Patterns / Integration Points below so the planner
budgets tasks for them, not just for the three officially-enumerated `AmbientSurface` grep hits.

**Primary recommendation:** Build `AmbientSurface` as a plain `enum.Enum` (matching
`logic/roasts.py::RoastScenario`), thread it as a required keyword-only arg through
`decide_ambient_channel`/`is_ambient_channel`/`resolve_ambient_channel`, and treat every one of the
9 concrete call sites found by exhaustive repo grep (listed in the Call-Site Inventory below) as
one atomic task — do not let any surface through unnamed.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `/setup` command + permission gate | API / Backend (Discord Gateway app-command handler) | — | Slash commands are Dexter's only "API surface"; `cogs/admin.py` is the handler |
| Channel picker UI | Browser / Client (Discord's own client renders it) | API / Backend (declares `channel_types` in the option payload) | Discord's client renders the picker; Dexter only declares the type constraint server-side |
| `guild_config` toggle writes | Database / Storage | API / Backend (`GuildConfigService` write + cache push-invalidate) | Postgres is system of record; cache is a read-optimization, never authoritative on write |
| `on_guild_join` / `on_guild_remove` | API / Backend (gateway event handler in `bot.py`) | Database / Storage (row insert), CDN/Static n/a | Pure backend lifecycle glue; no client or CDN involvement |
| Boot backfill | API / Backend (`on_ready` glue) | Database / Storage | Runs once at process boot, not per-request |
| Owner join/leave notification | API / Backend (`log_to_discord` → `ERROR_LOG_CHANNEL_ID`) | — | Global, not guild-scoped; reuses the existing Phase 2 error-log sink |
| `AmbientSurface` gating predicate | API / Backend (pure `logic/` seam) | — | Zero I/O, zero Discord objects — a pure decision function per Phase 10 convention |

## Verification of Mandatory Targets

All three verified directly against the installed `.venv/Lib/site-packages/discord` (2.7.1) and
`asyncpg` (0.31.0) source — not training-data recall.

### 1. D-02 — typed channel parameter renders a native picker — **VERIFIED**

`channel: discord.TextChannel` maps to `BUILT_IN_TRANSFORMERS[TextChannel] = BaseChannelTransformer(TextChannel)`
(`transformers.py:763`), whose `.type` property returns `AppCommandOptionType.channel`
(`transformers.py:654`) and whose `channel_types` property returns
`CHANNEL_TO_TYPES[TextChannel] = [ChannelType.text, ChannelType.news]` (`transformers.py:744`).
This `channel_types` list is serialized into the command's JSON option payload
(`app_commands/models.py:1073`: `'channel_types': [channel_type.value for channel_type in self.channel_types]`)
— sent to Discord's API, which is what makes the client render a **type-filtered, searchable
channel dropdown** rather than a free-text field. This is server-declared, not a client
convention Dexter has to hope for.

**Runtime object gotcha — CONFIRMED, and it does NOT threaten D-06.** `BaseChannelTransformer.transform`
(`transformers.py:661-665`) calls `value.resolve()` on the raw interaction payload and returns the
**resolved object from the client's cache** (a genuine `discord.TextChannel`, not an
`AppCommandChannel` proxy) *if* `TextChannel` is the annotated type. Only `AppCommandChannel` /
`app_commands.AppCommandChannel` annotations return the lightweight proxy (via
`RawChannelTransformer`, which skips `.resolve()` — `transformers.py:668-672`). Since D-02 specifies
`channel: discord.TextChannel` (not `AppCommandChannel`), the callback receives a full
`TextChannel` with `.permissions_for(guild.me)` available exactly as D-06 assumes.
**Correct annotation for "text channels only": `discord.TextChannel`** — this is exactly what
D-02 already specifies; no change needed. (`Union[discord.TextChannel, discord.VoiceChannel]` or
`app_commands.Transform` are not needed for this use case.)

One second-order risk worth flagging: `.resolve()` returns `None` if the channel is somehow not in
the client's cache (`transformers.py:663` raises `TransformerError` in that case, which discord.py
surfaces as a generic "command failed" to the user). Given `intents.guilds = True` is already
enabled (`bot.py:83`), all guild channels are populated via `GUILD_CREATE`, so this is a
non-issue in practice — noted for completeness, not a blocker.

### 2. D-09 — `@app_commands.guild_only()` enforcement — **VERIFIED, with one important shape correction**

Confirmed **server-side enforced**, straight from the docstring
(`commands.py:2503`): *"This is **not** implemented as a `check`, and is instead verified by Discord
server side. Therefore, there is no error handler called when a command is used within a private
message."* Mechanically: `guild_only=True` sets `unwrapped.guild_only = True` and merges it into
`allowed_contexts`, which flows into `base['dm_permission'] = not self.guild_only` on the command
JSON payload (`commands.py:1758` for `Group`, `:790` for `Command`) sent to Discord at sync time.

**Shape correction the planner must apply:** the decorator docstring states explicitly
(`commands.py:2508`): *"Due to a Discord limitation, this decorator does nothing in subcommands and
is ignored."* D-01's `/setup` is a `Group` with subcommands — `@app_commands.guild_only()` **must
not** be applied to the subcommand methods (`setup_channel`, `setup_roasts`, `setup_vision`); it is
inert there. The correct application point, confirmed at `commands.py:1489-1618`
(`Group.__init_subclass__`/`Group.__init__`), is the **`guild_only=True` kwarg on the `Group` itself**
— exactly the same kwarg-passing mechanism `cogs/memory.py:238`'s attribute-style
`app_commands.Group(name=..., description=...)` already uses for `name`/`description`. This works
identically whether the Group is declared as a Cog class attribute (`cogs/memory.py`'s pattern) or
as a `Group` subclass — both forms accept `guild_only` in `__init__`/`__init_subclass__`. Concretely:

```python
setup_group = app_commands.Group(
    name="setup",
    description="configure dexter for this server",
    guild_only=True,
)
```

`default_permissions=discord.Permissions(manage_guild=True)` can be passed alongside on the same
`Group` call — also confirmed harmless as a UI-only hint (see finding 4 below) — but per D-01/D-02
it must never be the enforcement mechanism.

**Can `interaction.guild` still be `None` with `guild_only()` applied?** In steady state, no — the
`dm_permission=False` payload prevents Discord from ever routing the interaction to Dexter outside
a guild. The defense-in-depth guard D-09 also mandates (`if interaction.guild is None: return`) is
correctly framed as belt-and-suspenders in CONTEXT.md, not as compensating for a real gap: it
protects against a stale command registration still live in Discord's cache before a `tree.sync()`
propagates the new `guild_only`/`dm_permission` flag, and against a bare type-checker's
`Optional[Guild]` signature. No refutation — D-09 is confirmed exactly as decided.

### 3. D-14 — `RETURNING`-based "did I insert?" signal — **VERIFIED**

Confirmed via `asyncpg.Connection.fetchrow.__doc__` (installed 0.31.0): *"The first row as a
`Record` instance, or **None** if no records were returned by the query."* Standard Postgres
`INSERT … ON CONFLICT (guild_id) DO NOTHING RETURNING *` returns **zero rows on conflict** and
**exactly one row on a genuine insert** — this is core Postgres semantics, not asyncpg-specific,
and the asyncpg docstring confirms the driver-level contract matches (`fetchrow` → `None` on empty
result set).

`database.py::seed_guild_config_if_absent` (`database.py:425-464`) is confirmed **exactly** as
CONTEXT.md describes: it does a bare `INSERT … ON CONFLICT (guild_id) DO NOTHING` via
`conn.execute()` (discards the result entirely — `execute()` doesn't even report affected rows in
a usable form here) followed by a **separate** `SELECT … WHERE guild_id = $1` via `conn.fetchrow()`.
Its return value is a `Record` in both the "I just inserted this guild" and "this guild already
existed" cases — **indistinguishable**, confirming D-14's premise precisely.

**Recommended restructuring** (planner's discretion per CONTEXT.md, but this shape is the
minimal-risk one, verified compatible with existing callers):

```python
async def insert_guild_config_if_absent(
    pool: asyncpg.Pool, *, guild_id: str
) -> asyncpg.Record | None:
    """INSERT-RETURNING sibling to seed_guild_config_if_absent (D-14).

    Returns the freshly-inserted Record on a genuine insert, None on conflict
    (row already existed). Unlike seed_guild_config_if_absent this does NOT
    set ambient_channel_id or configured=true — on_guild_join/backfill rows
    are born configured=false with both toggles at their column defaults
    (D-10/D-20), distinct from seed_home_guild's configured=true seed.
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "INSERT INTO guild_config (guild_id) VALUES ($1)"
            " ON CONFLICT (guild_id) DO NOTHING"
            " RETURNING guild_id, ambient_channel_id, configured, silenced,"
            "           is_blocked, joined_at, updated_at",
            guild_id,
        )
```

Keep `seed_guild_config_if_absent` byte-identical (it has its own live-DB idempotency test at
`tests/test_database_phase18.py:138-161` locking the `ON CONFLICT DO NOTHING`/never-`DO UPDATE`
shape) — add a **new sibling function** rather than changing its return contract, since
`seed_home_guild` (`services/guild_config.py:104-118`) depends on the current
"Record whether inserted or pre-existing" shape to always refresh its cache entry. This also keeps
the D-20 column-default distinction clean: `seed_guild_config_if_absent` writes
`configured = true` explicitly (home-guild bootstrap); the new sibling writes only `guild_id`,
letting `configured`, `ambient_roasts_enabled`, `vision_roasts_enabled` all fall through to their
schema defaults (`false`, `true`, `true` respectively per D-10/D-20).

**`DB_STATEMENT_CACHE_SIZE = 0` / Neon PgBouncer interaction:** none. The new query is a normal
parameterized statement (`$1`) executed via `fetchrow`, identical in shape to every other
parameterized query already running fine against the Neon pool with
`statement_cache_size=0` (`bot.py:356`). Adding a `RETURNING` clause does not introduce a prepared
statement or change how asyncpg dispatches the query — this is purely a return-payload difference,
not a protocol/caching difference. No special interaction, no risk.

## Additional Research Findings

### 4. Permission check idiom — **VERIFIED**: `interaction.permissions.manage_guild`

`Interaction.permissions` (`interactions.py:318-324`) returns `Permissions(self._permissions)`,
populated from the **`member.permissions` field Discord itself computes server-side** in the
interaction payload — *"the resolved permissions of the member in the channel, including
overwrites."* This already accounts for guild ownership and the Administrator implication (Discord
computes it the same way `Member.guild_permissions` does per that property's own docstring,
`member.py:716-729`: *"This does take into consideration guild ownership, the administrator
implication..."*), so a guild owner with no explicit `manage_guild` role permission still passes.

**Recommended idiom** (simpler than `interaction.user.guild_permissions`, and correct without any
`isinstance(interaction.user, discord.Member)` narrowing, since `interaction.permissions` degrades
to an all-`False` `Permissions(0)` in a non-guild context rather than raising):

```python
if not interaction.permissions.manage_guild:
    await interaction.response.send_message(
        "nice try. go find someone with manage server.", ephemeral=True
    )
    return
```

`interaction.user.guild_permissions.manage_guild` also works but requires `interaction.user` to be
narrowed/known as a `Member` (guaranteed under `guild_only()`, but `interaction.permissions` avoids
the type-narrowing question entirely and is the discord.py-recommended idiom for exactly this
check). Either satisfies ONBOARD-02's "inline check" requirement — `interaction.permissions` is
marginally preferred for brevity and directness.

**`default_permissions` alongside the inline check — CONFIRMED harmless, exactly as CONTEXT.md
assumes.** `default_permissions`'s own docstring (`commands.py:2838-2853`) states plainly: *"an
administrator can change the permissions needed to execute this command using the official
client... this only serves as a hint... members are not required to have the permissions given to
actually execute this command."* Also subject to the identical *"does nothing in subcommands"*
limitation as `guild_only` — if used at all (optional; D-02 does not require it), it must be set on
the `Group`, not per-subcommand, or it silently no-ops.

### 5. `on_guild_join` / `on_guild_remove` — **VERIFIED**

Both are standard `Client`/`AutoShardedClient` events, gated on the `guilds` intent (already
enabled, `bot.py:83`) — no additional intent required.

**Spurious-join risk during initial connect — VERIFIED ABSENT for the normal case, and D-14's
design is robust even in the abnormal case.** `ConnectionState.parse_guild_create`
(`state.py:1314-1334`) explicitly funnels every `GUILD_CREATE` arriving **during the initial READY
sequence** into `_add_ready_state` (`state.py:1322-1323`: *"We're waiting for the ready event, put
the rest on hold"*) and returns **without dispatching `guild_join`**. Those queued guilds are
processed by `_delay_ready` (`state.py:606-637`), which dispatches `guild_available` (not
`guild_join`) for every guild whose `unavailable` flag is `False` — the normal case for a guild the
bot is already a stable member of. **`guild_join` only fires for a genuinely new join
post-`READY`**, or for a guild transitioning from a previously-`unavailable` state
(`state.py:1331-1334`, `parse_guild_create`'s live post-READY path) — an edge case (a Discord-side
partial outage recovering) that is not "the bot was invited while offline."

**Even so, D-14's design does not depend on this distinction being airtight.** Because both
`on_guild_join` and the boot backfill route through the **same** insert-if-absent helper
(finding #3 above), any hypothetical spurious `guild_join` for an already-configured guild is a
no-op: the `INSERT … ON CONFLICT DO NOTHING RETURNING *` conflicts, `fetchrow` returns `None`, and
no welcome fires. The idempotency lives in the database, not in trusting the gateway event's
firing semantics — this is the correct defense and needs no changes.

`on_guild_remove` fires from `parse_guild_delete` (`state.py:1345-1365`) whenever Discord sends
`GUILD_DELETE` with `unavailable` falsy — **confirmed to cover both** the bot being kicked/banned
and the guild itself being deleted (both produce an indistinguishable `unavailable: false` payload
from Dexter's perspective). A Discord-side outage marking a guild temporarily unavailable instead
dispatches `guild_unavailable` (`state.py:1351-1356`) — **not** `guild_remove` — so a transient
Discord incident correctly does NOT trigger a "removed" notification. No refutation of D-12.

**One genuine open question (not a refutation of any locked decision):** `AutoShardedBot.on_ready`
is documented to fire once all shards report ready, and at Dexter's stated scale
(single-digit-to-low-dozens guilds) the bot almost certainly runs as a single shard in practice, so
`bot.guilds` is fully populated by the time `_initialize_once`'s backfill step would run. Flagged
under Open Questions as a LOW-risk edge case for multi-shard deployments, not a blocker.

### 6. Backfill ordering + `on_ready` re-entry — **VERIFIED, exact insertion point identified**

`bot.py::_initialize_once` (called from `on_ready`, guarded by `_ready_done`/`_ready_initializing`
at `bot.py:285-306`) has this exact structure relevant to D-14:

- `bot.py:413-416` — `GuildConfigService` constructed + `load_all()` awaited.
- `bot.py:418-440` — the home-guild seed block (`seed_home_guild` call at `:435-438`, wrapped in
  `try/except` that only logs a warning on failure).
- `bot.py:442+` — queue-persistence service wiring, then cog loading (`:448-455`).

**The backfill loop must be inserted immediately after line 440** (after the home-guild seed
`try/except` block closes), and **before** cog loading if the welcome send is meant to work
immediately (cogs aren't required for a raw `channel.send()`, but inserting after cogs load is also
safe — the constraint is strictly "after seed_home_guild", not "before cogs"). Placing it before
cog loading keeps the boot-sequence narrative linear (config seam fully settled → then feature
surfaces spin up) and matches the existing comment style at `bot.py:500-502` ("Restore persisted
queues — MUST run after load_extension... Runs before startup message").

`_ready_done` **does** prevent a reconnect from re-running the backfill: it's set to `True` only
after `_initialize_once` returns successfully (`bot.py:293`), and the very next line of `on_ready`
(`bot.py:285-286`) short-circuits on `_ready_done` being truthy. A reconnect that re-fires
`on_ready` never re-enters `_initialize_once`, hence never re-runs backfill — confirmed exactly as
CONTEXT.md's Claude's-Discretion section states.

**The "row exists" check is genuinely the real idempotency guard**, not `_ready_done` — this
matters because `_ready_done` only stops a *reconnect* from re-running backfill within the same
process lifetime; a full **process restart** (the actual on-demand-hosting scenario D-14 exists
for) resets `_ready_done` to unset and re-runs backfill fresh every boot. That re-run must be safe,
and it is: every already-configured guild's `INSERT … ON CONFLICT DO NOTHING RETURNING *` conflicts
and returns `None`, so only genuinely-new guilds get welcomed on any given boot.

**No code path lets a fail-closed cache masquerade as "every guild needs a welcome" — but only if
the backfill loop's welcome decision reads the INSERT's own return value, never `bot.guild_config.get()`.**
This is the one place a straightforward-looking implementation goes wrong: it would be natural to
write `for guild in bot.guilds: if bot.guild_config.get(guild.id) is None: welcome(guild)` — but
under Phase 18 D-07 fail-closed, a Neon hiccup during `load_all()` leaves the cache **empty**
(`services/guild_config.py:72-84`), making `get()` return `None` for **every** guild, including
ones with a real row in Postgres. The correct loop calls the new insert-if-absent helper for every
guild (optionally pre-filtered by a cache miss as a cheap skip for the common case — safe as an
optimization since a false-negative pre-filter just means "does the INSERT anyway," never "skips a
needed insert"), and welcomes **only** when that call's own `Record | None` result is not `None`.
If the DB itself is unreachable, the `INSERT` call raises inside the loop's own try/except, the
exception is caught, no welcome fires, and D-14's "fail-closed is preserved" holds.

### 7. Surface-keyed resolver — call-site inventory (D-22) — **EXHAUSTIVE, repo-wide grep confirmed**

Full-repo grep for `resolve_ambient_channel`, `resolve_announce_channel`, and `is_ambient_channel`
(excluding `tests/`, `logic/guild_config.py`, `services/guild_config.py` themselves) returns
exactly these 9 sites — no others exist anywhere in `cogs/`, `bot.py`, `services/`, `personality/`,
or `logic/`:

| # | File:Line | Current call | Surface it must declare | Notes |
|---|-----------|--------------|--------------------------|-------|
| 1 | `bot.py:529` | `bot.guild_config.resolve_ambient_channel(guild)` | `PRESENCE` | Startup message loop — **also needs the D-23 home-guild-only restriction; this is a behavior change, not just a kwarg add** (see Architecture Patterns) |
| 2 | `bot.py:747` | `bot.guild_config.resolve_ambient_channel(guild)` | `PRESENCE` | Idle-loneliness — stays per-guild (D-23) |
| 3 | `cogs/events.py:222` | `self.bot.guild_config.resolve_ambient_channel(member.guild)` | `ROAST` | Bot-moved-channel complaint. **Not explicitly named in D-22's table** ("voice-join/late-night roasts") but structurally identical to the join/leave roasts one line below — same voice-ambient-complaint family. Treat as `ROAST`; flag to the user only if this reads as a scope surprise |
| 4 | `cogs/events.py:266` | `self.bot.guild_config.resolve_ambient_channel(guild)` | `ROAST` | Voice-join / late-night roast |
| 5 | `cogs/events.py:311` | `self.bot.guild_config.resolve_ambient_channel(guild)` | `ROAST` | Voice-leave roast |
| 6 | `cogs/events.py:402` | `is_ambient_channel(config_row=..., channel_id=...)` (single computation, `in_ambient_channel`) | **split into two calls** | Currently reused at both `:412` (proactive) and `:419` (vision) — D-22 requires each dispatch site to resolve its own surface independently; the shared `in_ambient_channel` var must be replaced by two separately-computed booleans |
| 7 | `cogs/events.py:412` (via #6) | proactive-callback dispatch gate | `ROAST` | |
| 8 | `cogs/events.py:419` (via #6) | vision-roast dispatch gate | `VISION` | |
| 9 | **NEW** `cogs/music.py::_post_music_roast` (`:1168-1176`) | currently `self._get_text_channel(guild)` — **not `resolve_ambient_channel` at all** | `ROAST` | **See Summary finding #1 — this is a live gap, not an enumeration gap.** Repeat-song (`:1288-1327`) and both milestone roasts (`:1329-1356`, `:1358-1395`) all funnel through this one method (call sites `:1311`, `:1342`, `:1381`) |

Plus one new call site the plan must add: `cogs/admin.py`'s reaction-hole close (D-21) needs
`is_ambient_channel(..., surface=ROAST)` (or an equivalent `resolve_ambient_channel(...,
surface=ROAST) is not None` check) gating `_handle_message_reactions` — this isn't in the table
above because it's a wholly new call, not an existing one being retrofitted.

**`resolve_announce_channel`** (`services/guild_config.py:162-205`) has **zero existing callers**
anywhere in the repo (confirmed by the same grep) — it is a pure net-new integration point for
`on_guild_join`'s welcome (D-13) and, per CONTEXT.md, "owner-facing notices" — though D-16/D-17
route the owner notice to the fixed `ERROR_LOG_CHANNEL_ID` via `log_to_discord`
(`utils/logger.py:52-76`), not through `resolve_announce_channel`, so in practice
`resolve_announce_channel`'s only Phase 19 caller is the join-welcome path itself (both
`on_guild_join` and the boot backfill reuse it, per D-14's "run the same welcome path").

### 8. The reaction hole (D-21) — **CONFIRMED exactly as CONTEXT.md describes**

`cogs/events.py::on_message` (`:378-395`) calls `await self._handle_message_reactions(message)` at
line 395 **unconditionally**, before either ambient gate is computed (`in_ambient_channel` isn't
derived until line 402, six lines later). `_handle_message_reactions` (`:324-376`) does three
things, none gated:

1. React 👀 on any message containing a YouTube/Spotify domain string.
2. React 🫡 (saluting face) on "goodnight"/"gn" (word-boundary regex).
3. Reply "...you're welcome. don't get used to it." (or react 😐 neutral-face on a bare mention)
   when the bot is `@`-mentioned.

A channel+toggle gate would change behavior precisely as D-21 states: an unconfigured guild
(`configured = false`, no row) currently gets 👀/🫡/😐 reactions and the deflecting-warmth reply in
**every channel**, while all other ambient surfaces are already silent there. Gating this behind
`is_ambient_channel(config_row=..., channel_id=..., surface=ROAST)` makes reactions consistent with
every other `ambient_roasts_enabled`-gated surface — a guild that never ran `/setup`, or that
toggled roasts off, stops reacting entirely, matching the "structurally silent until configured"
claim PORT-04 wants to make.

### 9. Test regression surface — **exhaustive, confirmed via targeted + broad grep**

Files that mock/patch `bot.guild_config.get()`, `resolve_ambient_channel`, `is_ambient_channel`, or
`DEXTER_CHANNEL_ID`:

- `tests/test_guild_config_logic.py` — mock-free, direct calls to `is_ambient_channel`/
  `decide_ambient_channel`. **Every call site in this file needs a `surface=` kwarg added** once
  D-22 makes it required.
- `tests/test_guild_config_service.py` — direct calls to `service.resolve_ambient_channel(guild)`
  at 5 sites (`:144`, `:145`, `:194`, `:207`, `:221`, `:241`) — same required-kwarg update.
- `tests/test_proactive_events.py` — `bot.guild_config.get = MagicMock(...)` at `:42` and `:222`;
  comments at `:182`/`:201`/`:219` describing the surface-agnostic `is_ambient_channel` gate this
  file locks. **Named as the "known regression surface" by CONTEXT.md itself — confirmed.**

**Broader grep found no additional hits** beyond what CONTEXT.md already named. Three adjacent
files reference *unrelated* mocking of `MusicCog._get_text_channel` (not the guild_config seam) and
must **not** be conflated with the guild_config regression surface:

- `tests/test_autoqueue_playback.py:62` — mocks `_get_text_channel` to suppress an announce send;
  unrelated to repeat-song/milestone roasts.
- `tests/test_now_playing_refresh.py:78,105` — mocks `_get_text_channel` for now-playing embed
  refresh; unrelated.

**No existing test currently locks `_post_music_roast`'s channel-resolution behavior** (confirmed:
no test file references `_post_music_roast`, `REPEAT_SONG_ROAST` roast-firing, or
`MILESTONE_SONG_TEMPLATES` roast-firing through the cog glue layer — only the pure `logic/roasts.py`
decision functions and `database.py` helper functions are tested). This means finding #9 in the
Summary (music.py's ROAST gate) is a pure glue change with **zero pre-existing test breakage** —
consistent with D-26's "Discord/process glue is untested-by-design" convention, and a clean
opportunity for the planner to leave it untested-by-design too (structural review only), matching
every other roast dispatch site.

### 10. Ruff / CI ruleset — **CONFIRMED**

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

`E`/`W` = pycodestyle errors/warnings, `F` = pyflakes (unused imports/vars, undefined names — **not**
suppressed outside `tests/*.py`), `I` = isort import-ordering. Line length 120 (not the default 88)
— generous but not unlimited; the verbose docstring style already used throughout the codebase
(e.g. `logic/guild_config.py`'s module docstring) fits comfortably. `.github/workflows/ci.yml`
confirms both `ruff check .` and `ruff format --check .` run as separate blocking steps before
`pytest -q` — a new `cogs/admin.py`, new `logic/guild_config.py` additions, and the `database.py`
helper must all pass unused-import and import-ordering checks; run `ruff check .` and
`ruff format .` locally before considering any plan-generated code complete.

## Standard Stack

No new external dependencies this phase (confirmed: every decision in CONTEXT.md explicitly notes
"zero new deps"). All work uses libraries already pinned in `requirements.txt`:

| Library | Version (verified installed) | Purpose this phase |
|---------|-------------------------------|---------------------|
| `discord.py` | 2.7.1 (verified: `python -c "import discord; print(discord.__version__)"`) | `app_commands.Group`, typed channel params, `guild_only()`, `on_guild_join`/`on_guild_remove` |
| `asyncpg` | 0.31.0 (verified: `python -c "import asyncpg; print(asyncpg.__version__)"`) | `INSERT … RETURNING` insert-if-absent helper |

## Package Legitimacy Audit

**N/A — this phase installs zero external packages.** No `pip install` / `requirements.txt` change
is part of any of the 26 locked decisions or the Claude's-Discretion list. Skip the legitimacy
gate entirely; nothing to audit.

## Architecture Patterns

### System Architecture Diagram

```
                         ┌─────────────────────────┐
                         │   Discord Gateway        │
                         └────────────┬─────────────┘
                                      │
        ┌─────────────────────────────┼──────────────────────────────┐
        │                             │                              │
        ▼                             ▼                              ▼
 GUILD_CREATE (new join)      Slash command: /setup <sub>     GUILD_DELETE (kick/leave)
        │                             │                              │
        ▼                             ▼                              ▼
 bot.py::on_guild_join         cogs/admin.py::SetupGroup      bot.py::on_guild_remove
        │                       (inline manage_guild gate)           │
        ├─ insert-if-absent            │                              ├─ notify owner
        │   (RETURNING helper)         ▼                              │   (log_to_discord →
        ├─ if inserted:         GuildConfigService                    │    ERROR_LOG_CHANNEL_ID)
        │   resolve_announce_    .write + _refresh_cache_entry        └─ evict cache entry
        │   channel → welcome           │                                (NO row delete — D-12)
        └─ notify owner                 ▼
            (join/leave embed,   guild_config (Postgres)
             D-16 fields)         + in-memory cache
                                        │
                    ┌───────────────────┼────────────────────┐
                    ▼                   ▼                    ▼
           logic/guild_config.py  services/guild_config.py  Ambient surfaces
           (pure decision seam:   .resolve_ambient_channel   (9 call sites,
            decide_ambient_        (guild, surface=X)         see inventory)
            channel/is_ambient_          │                         │
            channel + surface     returns TextChannel|None  ──────┘
            kwarg, AmbientSurface        │
            enum)                        ▼
                                   channel.send(roast/vision/
                                   presence line) — or silence
                                   if surface disabled/unconfigured

              Boot path (on_ready, AFTER seed_home_guild):
              for guild in bot.guilds:
                  insert-if-absent(guild.id)  ─┐
                  if inserted (Record, not None):│ same helper +
                      welcome via                │ same welcome path
                      resolve_announce_channel   │ as on_guild_join
                  # conflict → None → skip ──────┘ (idempotent re-boot)
```

### Recommended Project Structure

```
cogs/
├── admin.py              # NEW: SetupGroup (/setup channel|roasts|vision), manage_guild gate
├── events.py              # MODIFIED: reaction gate (D-21), per-surface is_ambient_channel calls
                            #   replacing the single in_ambient_channel var (D-22), 3 voice sites
                            #   pass surface=ROAST
├── music.py                # MODIFIED: _post_music_roast switches from _get_text_channel to
                            #   resolve_ambient_channel(guild, surface=ROAST) — see Summary #1
├── help.py                # MODIFIED: admin section listing /setup (D-25)
logic/
├── guild_config.py         # MODIFIED: AmbientSurface enum + surface kwarg on
                            #   decide_ambient_channel/is_ambient_channel
services/
├── guild_config.py         # MODIFIED: surface kwarg on resolve_ambient_channel; home_guild_id
                            #   attribute (D-24); toggle write + push-invalidate methods
database.py                 # MODIFIED: 2x ALTER TABLE (ambient_roasts_enabled/vision_roasts_enabled),
                            #   new insert_guild_config_if_absent (RETURNING), toggle get/set helpers
bot.py                       # MODIFIED: on_guild_join / on_guild_remove handlers; boot backfill
                            #   loop (after seed_home_guild); _post_startup_messages narrowed to
                            #   home_guild_id (D-23) — a BEHAVIOR CHANGE, see Summary #2
tests/
├── test_guild_config_logic.py     # MODIFIED: surface= kwarg on every existing call
├── test_guild_config_service.py   # MODIFIED: surface= kwarg on every existing call
├── test_proactive_events.py       # MODIFIED: surface-aware bot.guild_config.get() mocks
├── test_database_phase19.py       # NEW: live-DB tests for the new helpers (mirrors
                                    #   test_database_phase18.py's skip-guard + structural-check
                                    #   + live-DB split)
├── test_guild_lifecycle_logic.py  # NEW (or added to test_guild_config_logic.py): mock-free
                                    #   "should I welcome" decision derived from insert result
```

### Pattern 1: Required-keyword enum threading (D-22)

**What:** `AmbientSurface` is a plain `enum.Enum` (mirroring `logic/roasts.py::RoastScenario`,
`logic/playback.py::TrackEndAction`), passed as a **required keyword-only** argument through every
layer — pure decision function, service resolver, and glue call site.

**When to use:** Any time a safety-relevant branch (which surface may fire) must be structurally
impossible to omit, per Phase 18's own D-02 precedent (rejecting a boolean `allow_fallback` flag
for exactly this reason).

**Example:**
```python
# Source: logic/roasts.py:30 (existing enum convention in this codebase)
import enum


class AmbientSurface(enum.Enum):
    """Which ambient behavior category a call site belongs to (D-22)."""

    ROAST = "roast"
    """Gated by ambient_roasts_enabled: voice-join/late-night roasts, proactive
    callbacks, repeat-song + milestone roasts, emoji reactions, bot-moved complaint."""

    VISION = "vision"
    """Gated by vision_roasts_enabled: image roasts only."""

    PRESENCE = "presence"
    """Gated by ambient_roasts_enabled (same column as ROAST today, D-18) but a
    distinct member — startup message (home-guild-only, D-23), idle-loneliness."""


# logic/guild_config.py — pure decision function signature
def decide_ambient_channel(*, config_row: Mapping | None, surface: AmbientSurface) -> int | None:
    ...
```

### Pattern 2: `Group`-level `guild_only` + inline permission gate (D-01/D-09)

**What:** A stateless `app_commands.Group` with subcommands, defense-in-depth guild enforcement at
the Group level (never per-subcommand, since the decorator/kwarg is a no-op there), and an inline
permission check as the very first statement of every subcommand body.

**Example:**
```python
# Source: verified against discord.py 2.7.1 (commands.py:1489-1618, 2500-2535) +
# cogs/memory.py:238 (existing attribute-style Group idiom in this codebase)
import discord
from discord import app_commands
from discord.ext import commands


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    setup_group = app_commands.Group(
        name="setup",
        description="configure dexter for this server",
        guild_only=True,  # server-enforced (dm_permission=False) — VERIFIED
        default_permissions=discord.Permissions(manage_guild=True),  # UI hint ONLY — VERIFIED
    )

    @setup_group.command(name="channel", description="pick dexter's ambient channel")
    @app_commands.describe(channel="the text channel dexter should post in")
    async def setup_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        # Defense-in-depth (D-09) — belt-and-suspenders for guild_only=True
        if interaction.guild is None:
            return
        # Inline permission gate — THE actual enforcement (ONBOARD-02)
        if not interaction.permissions.manage_guild:
            await interaction.response.send_message(
                "nice try. go find someone with manage server.", ephemeral=True
            )
            return
        # D-06: validate send_messages BEFORE writing, refuse loudly on failure
        if not channel.permissions_for(interaction.guild.me).send_messages:
            await interaction.response.send_message(
                f"can't post in {channel.mention} — i don't have send messages there.",
                ephemeral=True,
            )
            return
        # ... write row, push-invalidate cache, D-05 full-config echo ...
```

### Pattern 3: `INSERT … RETURNING` insert-if-absent (D-14)

**What:** A single round-trip that both writes and reports whether the write actually happened,
replacing a two-step "INSERT-then-SELECT" that cannot distinguish insert from conflict.

**Example:**
```python
# Source: verified via asyncpg 0.31.0 fetchrow docstring + standard Postgres RETURNING semantics
async def insert_guild_config_if_absent(
    pool: asyncpg.Pool, *, guild_id: str
) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "INSERT INTO guild_config (guild_id) VALUES ($1)"
            " ON CONFLICT (guild_id) DO NOTHING"
            " RETURNING guild_id, ambient_channel_id, configured, silenced,"
            "           is_blocked, joined_at, updated_at",
            guild_id,
        )
    # Record  -> genuine insert happened this call -> welcome
    # None    -> guild_id already had a row         -> no welcome
```

### Anti-Patterns to Avoid

- **Deciding "should I welcome" from a cache miss instead of the INSERT's own result** (finding #6)
  — under Phase 18's fail-closed cache (D-07), an errored `load_all()` makes every guild look
  unconfigured, which would welcome-spam every existing server on a Neon hiccup.
- **Adding `surface` as an optional kwarg with a default** — defeats the entire point of D-22; must
  be required keyword-only so a new call site cannot compile without declaring its surface.
- **Applying `@app_commands.guild_only()` or `@app_commands.default_permissions(...)` to individual
  `/setup` subcommand methods** — confirmed inert there; both must be set on the `Group` itself.
- **Reusing `_generate_ambient_roast`'s always-`str` contract for anything that needs a silent-skip
  outcome** — not directly relevant to Phase 19's own surfaces, but the same collapsing-two-outcomes
  mistake Phase 17 already scarred on (`_generate_ambient_roast` vs `_generate_vision_roast`) is
  worth remembering if any Phase 19 copy generation needs a silent path.
- **Computing `in_ambient_channel` once and reusing it across the proactive and vision dispatch
  gates** — this is precisely the WR-02 pattern D-22 retires; each gate must resolve its own
  surface independently even though today (pre-Phase-19) they'd evaluate to the same boolean.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Channel picker UI | A `discord.ui.ChannelSelect` view with timeout/author-guard handling | A typed `channel: discord.TextChannel` slash-command parameter | Discord's client renders the native picker for free once the option type is declared; a `ChannelSelect` view is strictly more code for an equivalent-or-worse UX (D-02, verified) |
| "Did my INSERT actually insert" signal | A `SELECT` before the `INSERT` (TOCTOU race) or comparing timestamps | `INSERT … ON CONFLICT DO NOTHING RETURNING *` via `fetchrow` | Single round-trip, race-free (Postgres evaluates the conflict atomically), and the `None`/`Record` return is exactly the boolean signal needed |
| Guild-only enforcement | A `@app_commands.check` coroutine that inspects `interaction.guild` | `@app_commands.guild_only()` / `Group(guild_only=True)` | Server-side enforced by Discord itself (`dm_permission=False`) — a custom check only fires after Discord has already routed the interaction, and per the docstring "there is no error handler called" for the guild_only path, so a custom check adds nothing but complexity |
| Permission checking | Manually walking `interaction.user.roles` and summing permission bits | `interaction.permissions.manage_guild` | Discord computes this server-side (including owner/admin implication and channel overwrites) and hands it to Dexter directly in the interaction payload |

**Key insight:** every "don't hand-roll" item in this phase is a case where discord.py or Postgres
already computes the exact signal Dexter needs server-side — the temptation is always to re-derive
it client-side (a custom channel-select view, a pre-INSERT existence check, a manual permission
walk), which is strictly more code and introduces exactly the races/inconsistencies the
server-side primitive was built to avoid.

## Common Pitfalls

### Pitfall 1: Treating `cogs/music.py`'s roast sites as "add a kwarg" instead of "fix a live gap"

**What goes wrong:** A plan that only greps for `resolve_ambient_channel(` call sites and adds
`surface=ROAST` to each will silently skip `cogs/music.py` entirely, because it doesn't call that
function today — it calls `_get_text_channel`, an unrelated, ungated resolver.

**Why it happens:** D-18/D-22's own framing ("not enumerated in Phase 18's inventory") reads like
an omission in a list, inviting a search-and-replace mental model rather than a "does this surface
even reach the seam yet" audit.

**How to avoid:** Treat `_post_music_roast` (`cogs/music.py:1168-1176`) as a **new integration
point**, not an existing call site to update — it needs `self._get_text_channel(guild)` replaced
with `self.bot.guild_config.resolve_ambient_channel(guild, surface=AmbientSurface.ROAST)`.

**Warning signs:** A plan/task list that has exactly 8 call-site edits (matching the pre-existing
`resolve_ambient_channel`/`is_ambient_channel` grep count) with nothing under `cogs/music.py`.

### Pitfall 2: Narrowing the startup message to home-guild-only as a "new feature" instead of a fix to existing Phase 18 code

**What goes wrong:** `_post_startup_messages` (`bot.py:514-536`) already iterates `bot.guilds` and
calls `resolve_ambient_channel` for each — this loop predates Phase 18's D-23 concern and, under
today's code, sends "i'm back..." to **every configured guild**, not just the home guild. A plan
that adds `AmbientSurface.PRESENCE` without also adding the `guild.id == home_guild_id` filter
ships D-22's typing improvement while leaving D-23's actual behavioral requirement unmet.

**Why it happens:** The two changes (surface kwarg + home-guild restriction) touch the same 5 lines
and are easy to conflate as one edit when they're actually two independent requirements (D-22 and
D-23) that happen to collide at the same call site.

**How to avoid:** Explicitly verify post-implementation that `_post_startup_messages` iterates
`[bot.get_guild(int(bot.guild_config.home_guild_id))]` (or an equivalent single-guild lookup) rather
than `bot.guilds`, in addition to passing `surface=PRESENCE`.

**Warning signs:** A diff on `bot.py:527` (`for guild in bot.guilds:`) that only touches the
`resolve_ambient_channel(...)` call inside the loop and leaves the loop header untouched.

### Pitfall 3: Deciding "welcome or not" from a cache read instead of the INSERT's return value

**What goes wrong:** (Detailed in finding #6 above.) A fail-closed empty cache during a Neon hiccup
makes `bot.guild_config.get(guild.id)` return `None` for every guild, including already-configured
ones — a backfill loop keyed on that would welcome-spam the whole home fleet on a bad boot.

**Why it happens:** `bot.guild_config.get()` is the obvious, already-familiar API for "does this
guild have a row" — reaching for it here feels natural and is exactly what every other ambient
surface does.

**How to avoid:** The welcome decision must read the return value of the new
`insert_guild_config_if_absent` call directly (`Record` → welcome, `None` → skip), never
`bot.guild_config.get()`.

**Warning signs:** A backfill implementation with an `if bot.guild_config.get(guild.id) is None:`
guard anywhere near the welcome-send call.

### Pitfall 4: `guild_only()` / `default_permissions` applied to subcommands instead of the Group

**What goes wrong:** Both decorators/kwargs silently no-op when applied to a `Group.command()`
method rather than the `Group` itself — confirmed by both decorators' own docstrings
(`commands.py:2508`, `:2847`). A plan that decorates `setup_channel`/`setup_roasts`/`setup_vision`
individually ships code that *looks* guild-gated but isn't server-enforced at all — the only real
protection left would be the inline `if interaction.guild is None` guard, which is defense-in-depth
for a primary mechanism that silently isn't there.

**Why it happens:** Per-subcommand decoration is the more common discord.py pattern for other
decorators (`@app_commands.describe`, `@app_commands.checks.cooldown`), so applying `guild_only()`
the same way is a natural but wrong generalization.

**How to avoid:** Set `guild_only=True` (and, optionally, `default_permissions=...`) as `__init__`
kwargs on the `app_commands.Group(...)` declaration itself — never on the subcommand methods.

**Warning signs:** `@app_commands.guild_only()` appearing directly above any of the three
`async def setup_*` method definitions rather than inside the `Group(...)` constructor call.

## Code Examples

### Toggle get/set helper (mirrors `get_proactive_opt_out`/`set_proactive_opt_out`)

```python
# Source: modeled on database.py:380-400 (get_proactive_opt_out) — the get/set upsert-helper
# shape CONTEXT.md names as the pattern to mirror for the guild_config toggles.
async def set_ambient_roasts_enabled(pool: asyncpg.Pool, *, guild_id: str, enabled: bool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE guild_config SET ambient_roasts_enabled = $2, updated_at = now()"
            " WHERE guild_id = $1",
            guild_id,
            enabled,
        )
```

### `on_guild_join` handler skeleton (D-10/D-13/D-16)

```python
# Source: composed from verified findings #3/#5/#6 above + services/guild_config.py:104-118's
# seed_home_guild as the structural template for "insert then refresh cache entry".
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

    # D-16: owner notice — always sent, regardless of welcome outcome (D-13)
    embed = discord.Embed(title=f"joined: {guild.name}", color=0x2ECC71)
    embed.add_field(name="guild id", value=f"`{guild.id}`", inline=True)
    embed.add_field(name="members", value=str(guild.member_count), inline=True)
    embed.add_field(name="owner", value=f"{guild.owner or 'unknown'} (`{guild.owner_id}`)", inline=False)
    embed.add_field(name="created", value=discord.utils.format_dt(guild.created_at, "R"), inline=True)
    embed.add_field(name="total guilds", value=str(len(bot.guilds)), inline=True)
    embed.add_field(name="welcome posted", value="yes" if welcome_posted else "no", inline=True)
    await bot.log_to_discord(embed)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|-------------------|---------------|--------|
| `config.DEXTER_CHANNEL_ID` bare-equality gates + 4-step fallback chain in the ambient path | `GuildConfigService.resolve_ambient_channel` (strict, cache-only, D-01) | Phase 18 | Phase 19 is the first phase whose *new* code must be written against the new seam from the start — no legacy pattern to accidentally copy for genuinely new call sites (only `cogs/music.py`'s pre-existing `_get_text_channel` usage is legacy debt to retire) |
| `discord.ui.ChannelSelect` for channel pickers (considered, rejected in D-02) | Typed `channel: discord.TextChannel` slash-command parameter | This phase (D-02, verified) | Simpler code, no view lifecycle to manage, native Discord-rendered picker |

**Deprecated/outdated:** None — discord.py 2.7.1 and asyncpg 0.31.0 are both current; no API used
in this research is flagged deprecated in either library's source.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|----------------|
| A1 | `AutoShardedBot.on_ready` fires only after all shards report ready, so `bot.guilds` is fully populated before backfill runs | Finding #5 / Open Questions | If false on a genuinely multi-shard deployment, some guilds could be missed by backfill on that boot and never welcomed until a later reconnect re-triggers gateway resume (not a full `on_ready` re-init, since `_ready_done` blocks that) — LOW risk given Dexter's single-digit-to-low-dozens guild scale target almost certainly keeps it single-shard in practice |
| A2 | Bot-moved-channel complaint (`cogs/events.py:222`) belongs to `AmbientSurface.ROAST`, though D-22's table doesn't name it explicitly | Finding #7, row 3 | If the user actually wants this treated as a distinct/PRESENCE-like surface, the planner should surface this specific call site back to the user rather than silently deciding — flagged explicitly in the table for that reason |

**If this table is empty:** N/A — two low-risk items logged above; neither blocks planning.

## Open Questions

1. **Does the boot backfill loop need a cache pre-filter, or should it always call
   `insert_guild_config_if_absent` for every guild in `bot.guilds`?**
   - What we know: Both are safe (finding #6) — the pre-filter is a pure optimization since the
     INSERT itself is the authoritative "should I welcome" signal either way.
   - What's unclear: At Dexter's scale (single-digit-to-low-dozens guilds), the optimization has no
     measurable benefit — a bare loop calling the RETURNING helper for every guild is simpler code
     with identical correctness.
   - Recommendation: Skip the pre-filter. Always call the helper for every `bot.guilds` entry;
     let the DB be the single source of truth with no cache read in the decision path at all.

2. **Multi-shard `bot.guilds` completeness at backfill time (A1 above).**
   - What we know: Confirmed non-issue for single-shard operation (the deployed reality per the
     milestone's stated scale target).
   - What's unclear: Exact `AutoShardedClient` multi-shard `on_ready` gating semantics were not
     traced to the bottom (would require reading `shard.py`'s `launch_shards` in full).
   - Recommendation: Don't invest further research time here — Dexter is not deployed multi-shard
     at this scale, and the existing `_ready_done` guard + per-boot-idempotent backfill design
     degrades safely (worst case: a guild's welcome is delayed to the next full restart, never
     lost, never duplicated) even if this assumption is wrong.

## Environment Availability

Skipped — no external tools/services/runtimes beyond what's already verified installed
(`discord.py` 2.7.1, `asyncpg` 0.31.0, the existing Neon Postgres connection, the existing CI
pgvector service container). No new environment dependency is introduced by this phase.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio (unpinned, `requirements.txt:8-9`) |
| Config file | none — `pyproject.toml` has no `[tool.pytest.ini_options]` section; implicit defaults |
| Quick run command | `pytest tests/test_guild_config_logic.py tests/test_guild_config_service.py -x` |
| Full suite command | `pytest -q` (blocking CI step, `.github/workflows/ci.yml`, runs against the `pgvector/pgvector:pg16` service container so all live-DB tests execute, not skip) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|--------------|
| ONBOARD-01 | `on_guild_join` posts welcome via `resolve_announce_channel`, never crashes on send failure; boot backfill welcomes only newly-inserted guilds | mock-free unit (the "should I welcome" decision) + untested-by-design glue | `pytest tests/test_guild_lifecycle_logic.py -x` (new) | ❌ Wave 0 — new pure decision function + test file needed |
| ONBOARD-02 | `/setup` inline `manage_guild` gate rejects non-admins regardless of `default_permissions` | untested-by-design (Discord interaction mocking is out of convention per D-26) — verified by structural code review only | n/a (structural review) | n/a |
| ONBOARD-03 | Channel dropdown via typed `discord.TextChannel` param | untested-by-design (Discord-rendered UI) — verified by structural review (parameter type annotation present) | n/a (structural review) | n/a |
| ONBOARD-04 | `ambient_roasts_enabled`/`vision_roasts_enabled` toggles independently gate `AmbientSurface.ROAST`/`.VISION` | mock-free unit (`logic/guild_config.py` surface-keyed predicate) + live-DB (`database.py` toggle get/set helpers) | `pytest tests/test_guild_config_logic.py -x` + `pytest tests/test_database_phase19.py -x` | ❌ Wave 0 for both — surface kwarg + toggle helper tests |
| ONBOARD-05 | Owner notified in `ERROR_LOG_CHANNEL_ID` on join and remove | untested-by-design (Discord glue: `log_to_discord`, embed construction) — verified by structural review + clean local boot | n/a (structural review) | n/a |

### Sampling Rate
- **Per task commit:** `pytest tests/test_guild_config_logic.py tests/test_guild_config_service.py -x` (fast, mock-free, no DB needed)
- **Per wave merge:** `pytest -q` (full suite; live-DB tests actually run under CI's pgvector container per Phase 18 D-15)
- **Phase gate:** Full suite green (`pytest -q`) + `ruff check .` + `ruff format --check .` all passing before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_guild_lifecycle_logic.py` (or added to `tests/test_guild_config_logic.py`) —
  mock-free coverage for a new pure function deciding "should this guild be welcomed" from an
  insert-result primitive (e.g. `should_welcome_guild(*, insert_result: Mapping | None) -> bool`),
  keeping the actual DB call and Discord send in glue while locking the decision itself. This is
  the one piece of ONBOARD-01 that genuinely deserves a `logic/` seam — everything else in
  `on_guild_join`/backfill is Discord I/O glue, untested-by-design per D-26.
- [ ] `tests/test_database_phase19.py` — mirrors `test_database_phase18.py`'s structure exactly:
  static `SCHEMA_SQL`/source-inspection checks (new columns present, `insert_guild_config_if_absent`
  uses `RETURNING`/`ON CONFLICT DO NOTHING`) + live-DB tests (a genuine insert returns a `Record`,
  a conflict returns `None`, the two new toggle columns default `true` on a pre-existing row).
- [ ] `tests/test_guild_config_logic.py` and `tests/test_guild_config_service.py` — every existing
  call to `is_ambient_channel`/`decide_ambient_channel`/`resolve_ambient_channel` needs a `surface=`
  argument added once D-22 makes it required (breaking-change update, not new coverage).
- [ ] `tests/test_proactive_events.py` — `bot.guild_config.get()` mocks need updating to return rows
  shaped for the surface-keyed predicate (confirmed as the CONTEXT.md-named regression surface).
- No framework install needed — pytest/pytest-asyncio already present; CI's pgvector container
  already exists from Phase 18.

## Security / Threat Model Inputs

ASVS L1. This phase adds a privileged admin command surface, an unprompted send into arbitrary
third-party guilds, and an owner-facing notification carrying attacker-influenceable strings.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|-----------------|---------|--------------------|
| V2 Authentication | No | Discord's own OAuth2/gateway auth; out of Dexter's control surface |
| V3 Session Management | No | N/A — stateless slash-command interactions |
| V4 Access Control | **Yes** | Inline `interaction.permissions.manage_guild` check, first statement in every `/setup` subcommand, before any data access — mirrors the existing `cogs/ops.py:252` `is_owner()`-first discipline. `default_permissions` is UI-hint-only and MUST NOT be the sole gate (verified finding #4) |
| V5 Input Validation | **Yes** | Guild name / owner tag are attacker-influenceable strings (any Discord user can rename their own guild before inviting Dexter) rendered into the owner's D-16 join/leave embed. See threat table below |
| V6 Cryptography | No | No new secrets, tokens, or crypto operations this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| Permission-check bypass via `default_permissions` alone (a user with the Discord "Manage Server" UI restriction turned off by a server owner could still invoke, since `default_permissions` is never enforced by Discord itself) | Elevation of Privilege | Inline `interaction.permissions.manage_guild` check as the actual gate — never `default_permissions` alone (ONBOARD-02, verified finding #4) |
| Markdown/embed injection via `guild.name` into the owner's join/leave notification (an attacker can name their guild anything before inviting Dexter — e.g. a string containing a deceptive markdown link, or backticks that break out of an inline-code span) | Tampering / Spoofing | Render `guild.name` as a **plain embed field value** (no markdown wrapping, no hyperlink construction from it). Render `guild.id`/`guild.owner_id` (always-numeric snowflakes) inside inline-code spans (`` `id` ``) since numeric IDs cannot contain backticks or break the span. Never construct a clickable link using guild-controlled text as the link label. Note: Discord embeds do **not** parse `@everyone`/`@here`/user mentions from field text into pings (mention parsing only applies to message `content`, confirmed by the existing pervasive `AllowedMentions.none()` convention being applied to `content` sends, not embed fields) — so this is a spoofing/social-engineering risk for the owner reading the embed, not a ping-injection risk |
| Welcome-message spam on repeated join/leave/re-invite cycling (an attacker could kick-and-reinvite Dexter repeatedly to flood the target guild's welcome channel or the owner's error-log channel) | Denial of Service | Out of Phase 19's mitigation scope by design — D-12 explicitly defers the blacklist/re-invite-refusal mechanism to Phase 20's OWNER-04. Phase 19 ships the join/leave *notification* only; repeated-invite abuse is the stated reactive-half problem Phase 20 solves. Note this limitation explicitly if PORT-04 disclosure is drafted early |
| Confused-deputy: a toggle write or channel designation applied to the wrong guild | Elevation of Privilege / Tampering | Every `/setup` write must derive `guild_id` exclusively from `interaction.guild.id` (server-provided, un-spoofable within a single interaction) — never from a user-supplied parameter. No `/setup` subcommand takes a `guild` or `guild_id` argument per D-01's three-subcommand shape; this is structurally enforced by the command signature, not a runtime check to remember |
| `send_messages` permission validated at read-time but revoked between check and write (TOCTOU on D-06's refusal check) | Tampering | Low severity, self-healing: D-03's silent-skip-with-log already covers a channel that *becomes* unwritable after a successful `/setup channel` — the D-06 check-then-write window is milliseconds and a subsequent permission revocation is caught by the very next ambient send attempt through the existing `resolve_ambient_channel` D-03 path, not a new gap |

## Sources

### Primary (HIGH confidence — read directly from installed source / actual codebase)

- `.venv/Lib/site-packages/discord/app_commands/transformers.py` (discord.py 2.7.1) — channel-type
  transformer mapping, `BaseChannelTransformer`/`RawChannelTransformer` resolve behavior
- `.venv/Lib/site-packages/discord/app_commands/commands.py` (discord.py 2.7.1) — `guild_only`,
  `default_permissions`, `Group.__init__`/`__init_subclass__` kwarg handling, `to_dict()`
  `dm_permission`/`contexts` serialization
- `.venv/Lib/site-packages/discord/interactions.py` (discord.py 2.7.1) — `Interaction.permissions`,
  `Interaction.guild` properties
- `.venv/Lib/site-packages/discord/member.py` (discord.py 2.7.1) — `Member.guild_permissions`
  docstring (owner/administrator implication)
- `.venv/Lib/site-packages/discord/state.py` (discord.py 2.7.1) — `parse_guild_create`,
  `parse_guild_delete`, `_delay_ready`, `_add_ready_state` dispatch semantics
- `.venv/Lib/site-packages/discord/guild.py` (discord.py 2.7.1) — `owner`, `owner_id`,
  `member_count`, `created_at` attribute availability
- `.venv/Lib/site-packages/discord/errors.py` (discord.py 2.7.1) — `Forbidden < HTTPException <
  DiscordException` hierarchy
- `asyncpg.Connection.fetchrow.__doc__` (asyncpg 0.31.0, introspected live) — `None`-on-empty-result
  contract
- `database.py:204-211, 380-464` — `guild_config` schema, `seed_guild_config_if_absent`,
  `get_proactive_opt_out`/`set_proactive_opt_out` idioms
- `services/guild_config.py` (full file) — `GuildConfigService`, both resolvers, cache/seed methods
- `logic/guild_config.py` (full file) — `decide_ambient_channel`, `is_ambient_channel`
- `bot.py:270-536, 700-756` — `on_ready`/`_initialize_once`/`_post_startup_messages`/idle-loneliness
  boot and event glue
- `cogs/events.py:97-629` — ambient roast generation, voice events, reaction hole, on_message gates,
  proactive/vision dispatch
- `cogs/music.py:960-1177, 1260-1396` — `_get_text_channel`, `_post_music_roast`, repeat-song and
  milestone roast call sites
- `cogs/memory.py:230-269`, `cogs/ops.py:240-254` — Group idiom + inline permission-check precedent
- `tests/test_database_phase18.py`, `tests/test_guild_config_logic.py`,
  `tests/test_guild_config_service.py`, `tests/test_proactive_events.py` — existing test structure
  + regression-surface confirmation
- `pyproject.toml`, `.github/workflows/ci.yml` — Ruff ruleset + CI gate structure
- `utils/logger.py:52-77` — `log_to_discord` no-op-on-unset behavior

### Secondary (MEDIUM confidence)

None — every claim in this document was verified against primary sources (installed library code
or the actual repository) rather than relying on web search or training-data recall.

### Tertiary (LOW confidence)

None.

## Metadata

**Confidence breakdown:**
- Mandatory verification targets (D-02/D-09/D-14): HIGH — confirmed against installed discord.py
  2.7.1 / asyncpg 0.31.0 source, not training data
- Call-site inventory (D-22): HIGH — exhaustive repo-wide grep, cross-checked against CONTEXT.md's
  own canonical_refs line numbers (all matched)
- Live-code findings (music.py gap, startup-message scope) : HIGH — read directly from current
  `main` branch source
- Shard/multi-shard `on_ready` gating (A1): MEDIUM — inferred from documented `AutoShardedClient`
  behavior and the existing `_ready_done` comment, not traced to `shard.py`'s full implementation;
  flagged as an Open Question, not asserted as fact

**Research date:** 2026-07-10
**Valid until:** 30 days (stable libraries; discord.py/asyncpg pins unlikely to change mid-milestone)
