# Phase 20: Owner Control Plane & Rate Observability - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning

> **Session note:** Every decision below was **explicitly selected by the user** across nine
> AskUserQuestion rounds (four chosen gray areas, each deep-dived). The user selected the
> recommended option in every round — these are affirmative choices, not AFK adoptions. All
> numeric/structural minutiae remain planner discretion per the Phase 11/13/14/15/16/17/18/19
> precedent.
>
> This phase RESOLVES the D-12 cross-phase landmine that Phase 19 recorded as a hard constraint:
> the blacklist moves to its **own table** (D-01 below), so Phase 21's MEM-04 purge of
> `guild_config` can no longer defeat the kill-switch.

<domain>
## Phase Boundary

Phase 20 builds the **reactive half of safety**: an abuse kill-switch the owner operates from one
place. The owner can (1) list every guild Dexter is in with per-guild Gemini usage visible, (2)
**silence** a guild (stay joined, go quiet), (3) **force-leave** a guild with the full
`clear_persisted()` teardown, and (4) **block** a guild — a persistent blacklist that refuses
re-invite. Enforcement lives at **two choke points only** (OWNER-05): `CommandTree.interaction_check`
for slash commands, and the pure `logic/guild_config.decide_ambient_channel` resolver for ambient
behavior — never scattered per-cog checks.

Phase 18 shipped the `guild_config` seam and the `silenced`/`is_blocked` forward columns (unread).
Phase 19 shipped `on_guild_join` / `on_guild_remove` and the owner join/leave notice with a
copy-pasteable `guild_id`. Phase 20 is the first **reader** of the safety flags and the first
**owner-facing control surface** over the multi-tenant fleet.

**In scope:**
- **OWNER-01 + RATE-01** — `/guilds list`: every guild with per-guild session Gemini usage, sorted
  by usage descending, paginated, ephemeral.
- **OWNER-02** — `/guilds silence` / `/guilds unsilence`: a guild-level mute enforced at both choke
  points, taking effect on the very next event (SC-2 — no stale in-flight response slips through).
- **OWNER-03** — `/guilds leave`: force-leave with teardown mirroring the `clear_persisted()`
  discipline (bump `_play_generation`, clear queue, disconnect voice, clear persisted state).
- **OWNER-04** — a **new `guild_blocklist` table** + a block-check-first in `on_guild_join`;
  `/guilds block` (which also force-leaves) / `/guilds unblock`.
- **OWNER-05** — the two-choke-point enforcement: `CommandTree.interaction_check` (slash) and the
  `decide_ambient_channel` resolver (ambient), reading silenced + blocked from an in-memory cache.
- **OWNER-06** — inline `is_owner()` on every `/guilds` subcommand; TOCTOU-safe silence/block
  check (evaluated at the ambient entry point AND re-checked immediately before the final send).
- **RATE-01** — per-guild `guild_id`-tagged Gemini call counting surfaced in `/guilds list`.

**Out of scope (belongs to later phases):**
- **Any DB purge on guild removal** (`guild_config`, `guild_queues`, `guild_jams`,
  `user_memories`) → **Phase 21** (MEM-04). Phase 20's `/guilds leave`/`block` teardown touches
  runtime/voice/queue state and the blocklist — **not** the persistent guild-data rows.
- Memory guild-scoping (MEM-01/02/03/05) → Phase 21.
- `/invite` + the least-privilege OAuth2 URL → Phase 22.
- Landing page, case-study README, build badge, Pages CD, GHCR → Phase 23. PORT-04's honest
  disclosure of the "full-savage + reactive-kill-switch" tradeoff is Phase 23 material, seeded by
  this phase.
- **SCALE-F1** (soft per-guild rate ceiling on priority-2 Gemini calls) — explicitly conditional
  in REQUIREMENTS.md ("only if observability proves starvation is real"). RATE-01 ships the
  observability; the ceiling itself is NOT in this phase.
- Any change to `OWNER_ID` / `ERROR_LOG_CHANNEL_ID` — these stay **global**.
- Automated abuse detection — Out of Scope in REQUIREMENTS.md. The kill-switch is manual and
  owner-driven by design.

</domain>

<decisions>
## Implementation Decisions

### Blacklist storage — resolving the D-12 landmine (OWNER-04)

- **D-01 (user-selected): the blacklist lives in its OWN `guild_blocklist` table, NOT the
  `guild_config.is_blocked` column.** A dedicated single-purpose table
  (`guild_id TEXT PRIMARY KEY`, `reason TEXT`, `blocked_at TIMESTAMPTZ DEFAULT now()`) following
  the `guild_jams` / `resolution_cache` idiom. This **resolves the Phase 19 D-12 collision by
  construction**: Phase 21's MEM-04 purge deletes `guild_config` / `guild_queues` / `guild_jams` /
  guild-scoped `user_memories` freely and **never touches `guild_blocklist`**, so a kicked abuser's
  block survives removal and a re-invite is refused. "Block" is an owner-abuse concept, not
  per-guild config — separating the tables keeps Phase 21 free of any special-case carve-out logic
  in the exact memory surgery it is most scarred around.
  *(Rejected: keeping the `is_blocked` column — then MEM-04 must special-case "purge everything
  except a blocked guild's row" or "keep the row, null the other columns, retain the flag": a
  tested exception bolted onto the Phase 13 CR-01 `expires_at`-scarred code path, exactly the
  fragility a dedicated table avoids.)*

- **D-02 (user-selected): the block is READ from an in-memory blocked-set cache** — load all
  blocked `guild_id`s into a `set[str]` at boot, push-invalidate on `/guilds block` / `/guilds
  unblock`. The two hot paths (`interaction_check` on every slash command; `on_guild_join`
  re-invite refusal) and the OWNER-06 TOCTOU ambient re-check do an **O(1) set membership test
  with NO Neon round-trip** — the same CONFIG-03 discipline Phase 18 established for config reads.
  Block/unblock writes the DB **then** mutates the set.
  *(Rejected: a live `SELECT FROM guild_blocklist` per check — a Neon round-trip on the command hot
  path, the exact thing CONFIG-03 forbade, made worse by scale-to-zero latency.)*

- **D-03 (user-selected): `GuildConfigService` owns the blocked-set; the dead `is_blocked` column
  is left in place, documented.** Extend the existing service with `_blocked: set[str]` +
  `block_guild(guild_id, reason)` / `unblock_guild(guild_id)` / `is_blocked(guild_id) -> bool` —
  it already owns load-all-at-boot + push-invalidate, so the discipline is identical and cogs reach
  it via `self.bot.guild_config`. The `guild_config.is_blocked` column Phase 18 shipped is **left
  unused with its `false` default** (harmless) and CLAUDE.md is annotated that `guild_blocklist` is
  authoritative. **No destructive DDL** — the codebase has only ever shipped additive idempotent
  DDL; a `DROP COLUMN` would be a new and unnecessary precedent.
  *(Rejected: a separate `GuildBlocklistService` + `DROP COLUMN is_blocked` — a second boot-load
  and a destructive migration for a purely cosmetic gain.)*

### Owner control surface (OWNER-01…06)

- **D-04 (user-selected): a single `/guilds` `app_commands.Group`** —
  `/guilds list`, `/guilds silence`, `/guilds unsilence`, `/guilds leave`, `/guilds block`,
  `/guilds unblock`. Mirrors the `/memory`, `/playlist`, `/jam` group idiom already in the
  codebase. One cohesive owner surface, easy to extend, each subcommand carries its own inline
  `is_owner()` check (OWNER-06).
  *(Rejected: six separate top-level commands — clutter the global command space and each appears
  in every guild's picker; folding into `/stats` — conflates read-only analytics with destructive
  kill-switch actions.)*

- **D-05 (user-selected): the group lands in `cogs/ops.py`.** Phase 19 D-04 explicitly left
  `ops.py` "clean for Phase 20's owner control plane." `ops.py` is the owner/analytics surface
  (`/stats`, `/leaderboard`, `/skips`), gated by `is_owner()` — the correct home for an
  owner-gated control group. (`cogs/admin.py` is the *guild-admin* surface, `manage_guild`-gated —
  a different audience; keeping the two permission models in separate modules stops a future
  contributor copying the wrong gate.)

- **D-06 (user-selected): global `tree.sync()` + `default_permissions(administrator=True)` as a UI
  hint ONLY; the real gate is the inline `is_owner()` check.** Sync globally like every other
  command (the bot already does one global `tree.sync()` in `on_ready`). The command is visible
  (greyed-out) in other guilds' pickers — that is **accepted**: a curious admin seeing it and
  getting an in-persona ephemeral refusal is harmless, and `default_permissions` is never the gate
  (the same rule ONBOARD-02 established for `/setup`).
  *(Rejected: owner-guild-only sync (`copy_global_to(guild=home)`) — truly hides it but adds a
  second sync path distinct from the global sync, needs `home_guild_id` resolved at sync time, and
  breaks if the owner ever operates from a different guild.)*

- **D-07 (user-selected): destructive actions execute IMMEDIATELY with an in-persona ephemeral
  echo — no danger-confirm.** This is a kill-switch; when a guild is actively a problem, speed
  matters and a confirm ceremony is friction. Both `/guilds leave` and `/guilds block` are
  **reversible** (re-invite after leave; `/guilds unblock`), unlike `/memory forget`'s
  unrecoverable delete — so the `ForgetConfirmView` danger-button pattern does not apply. Reply
  ephemerally, in persona, echoing name + `guild_id` + new guild count.
  *(Rejected: a danger-confirm button — treats a reversible op like an unrecoverable one and adds
  a click to an urgent action; confirm-on-leave-only — force-leave is still recoverable via
  re-invite, so the ceremony is unwarranted.)*

### RATE-01 usage counter

- **D-08 (user-selected): an in-memory `dict[guild_id -> int]` in `GeminiService`, since-boot
  (per-session), reset on restart.** `/guilds list` labels it "this session". Cheap, **zero new
  schema, zero DB writes on the hot AI path**. Under the on-demand hosting model the owner runs
  the bot in one session anyway, so "this session" is exactly the actionable window for spotting a
  **live** budget hog to kill-switch.
  *(Rejected: a DB-persisted per-guild daily counter — durable history at the cost of a DB write
  on every Gemini call plus new schema, heavier than a triage view needs; a rolling-window RPM per
  guild — a momentary RPM reading is a worse abuse signal than a cumulative session total, and it
  is more moving parts.)*

- **D-09 (user-selected): an optional `guild_id: str | None = None` keyword on `chat()` and
  `generate_image()`; count guild-attributable chat/image calls only.** Each call site passes its
  guild (`interaction.guild_id`, `message.guild.id`). Guild-less background calls (the `daily_batch`
  distill, `/ask` in a DM) pass `None` and are **not counted** — the kill-switch only acts on
  guilds, so untagged calls are not actionable. **`embed()` is NOT tagged** — it lives on the
  separate 60 RPM limiter, a different budget the `/guilds` kill-switch cannot remedy, and it is
  not user-abuse-driven.
  *(Rejected: tagging everything including embeds and bucketing `None` as a "system" pseudo-row —
  more complete accounting, but embeds are on a limiter `/guilds` can't act on and a "system" row
  adds noise to an abuse-triage view.)*

- **D-10 (user-selected): `/guilds list` renders one row per guild** — name, **copy-pasteable
  `guild_id`**, member count, status flags (`configured` / `silenced` / `blocked`), and session AI
  calls — **sorted by AI calls descending** so the budget hog is line one (the whole point of
  RATE-01). Paginate with the existing `LyricsPageView` char-budget pattern. Ephemeral. **No silent
  truncation** — the "no silent caps" discipline (Phase 19 D-15) holds.
  *(Rejected: sorting by name/join-date — buries the high-usage guild you're hunting; a single
  embed with top-N + "…and N more" — silently truncates, violating the established no-silent-caps
  rule.)*

### Silence & block enforcement / UX (OWNER-02/05/06)

- **D-11 (user-selected): `/guilds block` = full force-leave teardown + blacklist insert;
  `/guilds leave` stays a standalone non-blacklisting exit.** `block` runs the OWNER-03 teardown
  (bump `_play_generation`, clear queue, disconnect voice, `clear_persisted`) **then** inserts into
  `guild_blocklist`. `leave` does the same teardown **without** the blacklist (a benign departure —
  the guild can re-invite). `unblock` deletes from the blocklist and does **not** re-join. You never
  want to blacklist a guild you're still sitting in, and a bare leave without a block invites
  instant re-invite.
  *(Rejected: fully independent flags — leaves the footgun of a blocked-but-still-present guild
  ("block then forget to leave" under pressure); block-implies-leave with no standalone leave —
  OWNER-03 explicitly requires a force-leave capability and you lose the ability to leave a test
  server benignly without permanently blacklisting it.)*

- **D-12 (user-selected): a user in a SILENCED guild gets an in-persona EPHEMERAL notice**
  (e.g. "i've been muted in this server. not my call.") from `interaction_check`. Only the invoker
  sees it, nobody is publicly dunked on, and it **avoids Discord's ugly "application did not
  respond" timeout**. Ambient behavior in a silenced guild is **total silence — no reply at all**.
  Mirrors Phase 19 D-08's in-persona ephemeral non-admin refusal.
  *(Rejected: truly silent slash refusal — indistinguishable from a crashed bot, worse UX than an
  honest one-liner; ephemeral neutral notice — forfeits the persona where a dry one-liner costs
  nothing.)*

- **D-13 (user-selected): `interaction_check` refuses on `silenced OR blocked`, always exempts
  `is_owner`, and always allows DMs / guild-less interactions.** One predicate, one choke point
  (OWNER-05):
  - **Owner exemption** — the owner is **never** locked out of `/guilds` (even in an edge-case
    self-silenced guild). `is_owner` is already cheap to compute.
  - **DM exemption** — `interaction.guild is None` → allow (owner `/ask` in a DM, etc.).
  - **Both flags checked** — blocked is checked defensively even though D-11's block-implies-leave
    usually means the bot is not present, covering the block-written-while-leave-in-flight window
    that OWNER-05's "enforce the block for slash commands" literally asks for.
  *(Rejected: no owner exemption — a soft footgun (owner silences home guild, loses `/guilds
  unsilence`) with no upside; silenced-only — drops the defense-in-depth OWNER-05 names.)*

- **D-14 (user-selected, carried as a hard constraint): the silenced check is a NEW reader inside
  the pure `logic/guild_config.decide_ambient_channel`** (the ambient choke point OWNER-05 names),
  AND is **TOCTOU re-checked immediately before the final ambient send** (OWNER-06 / SC-2). Ambient
  handlers do seconds-long async Gemini work; a silence issued during that window must take effect
  on the **very next event and never let a stale in-flight response slip through**. `silenced` is
  read from the existing `GuildConfigService` config cache (already hot-path-safe) — no new
  mechanism. Block need not be added to `decide_ambient_channel` (block force-leaves, so no ambient
  fires), but the pre-send re-check covers both flags for safety.

### Claude's / Planner's Discretion (do NOT re-ask the user)

- **Exact DDL** for `guild_blocklist` — column types, whether `reason` is nullable, any index
  (the `guild_id` PK suffices for point lookups). Follow the `guild_jams` / `resolution_cache`
  idiom; plain param-free DDL in `SCHEMA_SQL`'s single `conn.execute()` (asyncpg multi-statement
  rule).
- **DB helper shapes** — `load_blocklist()` (boot load-all), `insert_blocklist(guild_id, reason)`,
  `delete_blocklist(guild_id)`, mirroring the `get/set_proactive_opt_out` upsert-helper shape and
  the existing `load_all_guild_configs`.
- **Silenced get/set helpers + service methods** — `silence_guild` / `unsilence_guild` /
  `is_silenced` on `GuildConfigService`, writing the existing `guild_config.silenced` column and
  push-invalidating the config cache. Whether `is_silenced` reads the cache row or a derived set.
- **Whether the pure `logic/guild_config` seam grows a silenced-aware helper** vs adding the
  `silenced` check inside the existing `decide_ambient_channel` branch — so long as it stays
  keyword-only, `discord`-free, `datetime`-free, `random`-free, and mock-free tested, and the glue
  dispatches on the return value (Phase 10 D-02).
- **Exact `guild_id` argument type** on the subcommands (a `str` parsed to int, since guild IDs
  exceed Discord's slash-command integer range concerns — verify; the join notice already renders
  it as copy-pasteable text per Phase 19 D-16).
- **The `CommandTree.interaction_check` wiring** — whether it is an override on the `DexterBot` /
  a custom `CommandTree` subclass, or set on `bot.tree`. The service reference must be reachable
  (`bot.guild_config`) at check time.
- **Exact copy** for the silenced refusal, the `/guilds list` rows, and the block/leave/silence
  echoes — subject to the personality rules (lowercase, one emoji max, under 500 chars, sarcasm
  dialed back for functional info).
- **Which exact Gemini call sites pass `guild_id`** — the greps in `<code_context>` are a starting
  point (`cogs/ai.py`, `cogs/events.py`, `cogs/music.py`, `cogs/library.py`, `cogs/imagine.py`);
  verify by call-site. `services/memory.py:383` (`daily_batch` distill) passes `None`.
- **`/guilds list` pagination threshold** and per-row formatting within the `LyricsPageView`
  char budget.
- **Testing split** — mock-free TDD for any new pure logic (silenced-aware resolver, the
  block-check decision); live-DB tests for the new `guild_blocklist` + silenced helpers (CI's
  pgvector service container now runs these); `cogs/ops.py` `/guilds` glue and `interaction_check`
  are untested-by-design (structural review + clean boot).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements (this phase)
- `.planning/ROADMAP.md` §"Phase 20: Owner Control Plane & Rate Observability" — goal, dependencies
  (Phase 18 config cache, Phase 19 guild-join lifecycle), and the 4 success criteria (SC-2's "never
  a stale in-flight response" is D-14; SC-3 names the `clear_persisted()` teardown discipline).
- `.planning/REQUIREMENTS.md` §"Owner Control Plane / Kill-Switch (OWNER)" — OWNER-01…06 verbatim.
  OWNER-05 names the two choke points; OWNER-06 names the inline `is_owner()` + TOCTOU rule.
- `.planning/REQUIREMENTS.md` §"Rate Limiting & Observability (RATE)" — RATE-01, and **SCALE-F1**
  (the conditional soft ceiling — explicitly NOT this phase; RATE-01 only ships the observability).
- `.planning/REQUIREMENTS.md` §"Out of Scope" — automated abuse detection, per-guild persona
  intensity dial. §"Key Decisions" — "full-savage everywhere" + reactive-kill-switch tradeoff
  (PORT-04 disclosure material). §"Descope Rule" — standing, user-directed.

### The D-12 landmine this phase resolves (READ BEFORE DESIGNING THE BLOCKLIST)
- `.planning/phases/19-onboarding-admin-setup/19-CONTEXT.md` §D-12 — the **hard constraint**: a
  blocked guild's blacklist entry MUST survive `on_guild_remove`, but Phase 21's MEM-04 purges
  `guild_config`. **D-01 above resolves this by moving the blacklist to its own table.** Phase 21
  now purges `guild_config` freely.
- `bot.py:706-717` — `on_guild_remove`: currently evicts the cache entry only, touches NO DB rows
  (Phase 19 D-12). The MEM-04 purge Phase 21 adds here must NOT touch `guild_blocklist`.
- `bot.py:661-703` — `on_guild_join`: the block-check-first (OWNER-04) hangs at the TOP of this
  handler, before `insert_guild_config_if_absent`. Note the existing `hasattr(bot, "pool")` /
  `guild_config` init guard and the WR-04 try/except discipline.

### Enforcement choke points (OWNER-05)
- `bot.py:47` — `class DexterBot(commands.AutoShardedBot)` and `bot.py:86` — its construction.
  The `CommandTree.interaction_check` override (D-13) attaches here (subclass a `CommandTree`, or
  set the check on `bot.tree`). `bot.tree.error` at `bot.py:748` — where a `CheckFailure` from the
  refused interaction is swallowed/handled.
- `logic/guild_config.py::decide_ambient_channel` (`:64`) — the pure ambient resolver D-14 adds the
  `silenced` check to. Note it already returns `None` for unconfigured/toggled-off — silenced is a
  new branch of the same shape. `AmbientSurface` (`:35`) and `is_ambient_channel` (`:128`) are the
  surrounding pure seam (Phase 19 D-22).
- `services/guild_config.py::GuildConfigService` — the cache owner (D-03/D-14). `resolve_ambient_channel`
  (`:133`) dispatches on `decide_ambient_channel`. `_refresh_cache_entry` (`:92`) is the
  push-invalidate hook the silence/block setters call. `home_guild_id` (`:58`), `get()` (cache read).
- `tests/test_guild_config_logic.py` / `tests/test_guild_config_service.py` — the mock-free pure-seam
  and fake-bot service test conventions to extend.

### RATE-01 (Gemini tagging + counter)
- `services/gemini.py::GeminiService.chat` (`:173`) and `generate_image` (`:258`) — add the
  `guild_id: str | None = None` keyword (D-09). `embed()` (`:298`) is deliberately NOT tagged.
- `services/gemini.py::_RateLimiter` (`:63`) + `rpm_usage` (`:86`/`:164`) — the existing global
  in-memory sliding window; the per-guild `dict` counter (D-08) lives alongside it in `GeminiService`.
- Gemini call sites to thread `guild_id` through (verify by call-site — not exhaustive):
  `cogs/ai.py:144/234/345`, `cogs/events.py:185/565`, `cogs/imagine.py:59`, `cogs/library.py:985`,
  `cogs/music.py:1246/2126`. `services/memory.py:383` (`daily_batch` distill) passes `None`.

### Owner-command + view conventions
- `cogs/ops.py:247-262` — the **inline `await self.bot.is_owner(interaction.user)` FIRST** discipline
  (`/stats`), and `self.bot.gemini_service.rpm_usage` — the existing global-usage read `/guilds list`
  extends per-guild. `/guilds` group lands in this file (D-05).
- `cogs/memory.py:238` — the `app_commands.Group` idiom D-04 mirrors (`view`/`forget`/`callbacks`),
  ephemeral + `AllowedMentions.none()`. `cogs/library.py:417`/`:620` — `/playlist` + `/jam` groups.
- `cogs/memory.py` `LyricsPageView` (char-budget pagination, repurposed in Phase 15) — the D-10
  pagination pattern for `/guilds list`. `cogs/memory.py` `ForgetConfirmView` — the danger-confirm
  pattern D-07 **deliberately does NOT reuse**.
- The OWNER-03 teardown template — the `clear_persisted()` discipline: search `clear_persisted`,
  `_play_generation`, `/stop` in `cogs/music.py` + `models/queue.py` + `services/queue_persistence.py`
  for the canonical bump-generation → clear-queue → clear-persisted sequence D-11 mirrors.

### Schema + DB idiom
- `database.py` `SCHEMA_SQL` `guild_config` block (`:204` region) — `silenced` / `is_blocked`
  columns ship with `false` defaults (Phase 18 D-11). Phase 20 reads `silenced`; leaves `is_blocked`
  dead (D-03). Add the new `guild_blocklist` `CREATE TABLE IF NOT EXISTS` here.
- `database.py::insert_guild_config_if_absent` (`:425` region) / `get_guild_config` /
  `load_all_guild_configs` (`:403`) — the existing guild_config helpers the blocklist/silenced
  helpers mirror. `get_proactive_opt_out` / `set_proactive_opt_out` — the get/set upsert shape.
- `CLAUDE.md` §"Database Schema (PostgreSQL)" — update the running schema narrative when
  `guild_blocklist` lands; annotate `guild_config.is_blocked` as dead (D-03).

### Testing + CI
- `tests/conftest.py:34-46` — `TEST_DATABASE_URL` + skip-on-connection-error. Phase 18's CI now
  supplies a `pgvector/pgvector:pg16` service container, so the new live-DB blocklist/silenced tests
  **actually run**.
- `.github/workflows/ci.yml` — the blocking Ruff + pytest gate every Phase 20 commit runs behind.
- `.planning/codebase/TESTING.md` — "pure logic gets mock-free TDD; Discord/process glue is
  untested-by-design (structural review + clean boot)".
- **Known regression surface:** `tests/test_proactive_events.py` and any test that mocks
  `bot.guild_config.get()` or exercises `decide_ambient_channel` — the added `silenced` branch is a
  call-site inventory. Treat any test touching `interaction_check` behavior similarly.

### Prior-phase context (conventions this phase inherits)
- `.planning/phases/18-per-guild-config-foundation-ci-gate/18-CONTEXT.md` — D-06 (load-all cache,
  miss is authoritative — the model D-02's blocked-set copies), D-07 (fail-closed), D-11 (forward
  columns unread until this phase). "Structural safety over remembered safety" — the philosophy
  OWNER-05's single-choke-point enforcement extends.
- `.planning/phases/19-onboarding-admin-setup/19-CONTEXT.md` — **read in full.** D-12 (the landmine),
  D-16 (copy-pasteable `guild_id` in the join notice, which `/guilds` subcommands consume), D-22
  (the surface-keyed ambient resolver `decide_ambient_channel` D-14 extends), D-08 (in-persona
  ephemeral refusal — the model for D-12's silenced notice).
- `.planning/PROJECT.md` §"Key Decisions" — the full decision ledger; §"Context" for cog → service
  → model layering.
- `CLAUDE.md` §"Critical Rules" (Rule 6 dial-back-sarcasm, Rule 8 lowercase, Rule 9 designated
  channel) + §"Implementation Gotchas" (asyncpg multi-statement DDL; the `logic/` pure-seam rule:
  glue dispatches on the return value, does not mirror the branch).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `services/guild_config.py::GuildConfigService` — the cache owner extended with `_blocked` set +
  silenced/block methods (D-03). `_refresh_cache_entry` is the push-invalidate hook the setters call.
- `services/gemini.py::GeminiService` — add the per-guild `dict` counter + `guild_id` kwargs (D-08/D-09).
  `_RateLimiter` + `rpm_usage` already model the in-memory-counter idiom.
- `cogs/ops.py` — the owner-gated home for the `/guilds` group (`is_owner()`-first discipline).
- `cogs/memory.py::MemoryCog` (`app_commands.Group` + ephemeral) + `LyricsPageView` — structural
  templates for the `/guilds` group and its paginated list.
- `database.py::get/set_proactive_opt_out` + `load_all_guild_configs` — the helper shapes for the
  blocklist + silenced helpers.
- The `clear_persisted()` / `_play_generation` / `/stop` teardown template — the OWNER-03 force-leave
  discipline D-11 mirrors.
- `bot.py::on_guild_join` (`:661`) — the block-check-first hangs at the top (OWNER-04).

### Established Patterns
- **cog → service → model layering**; services constructed in `bot.py`, attached as bot attributes,
  reached via `self.bot.<name>`.
- **`logic/` is the pure seam** (Phase 10 D-02): the silenced check goes into `decide_ambient_channel`;
  the glue dispatches on the return value and does not mirror the branch (D-14).
- **In-memory cache + push-invalidate, no hot-path DB read** (CONFIG-03) — the blocked-set (D-02) and
  the silenced read (D-14) both obey it.
- **Idempotent additive DDL** — `CREATE TABLE IF NOT EXISTS guild_blocklist`; no `DROP COLUMN` (D-03).
- **Inline `is_owner()` first, `default_permissions` is a UI hint not the gate** (D-06, OWNER-06).
- **No silent caps** (Phase 19 D-15) — `/guilds list` paginates, never truncates (D-10).
- **"No output beats a wrong output"** — ambient in a silenced guild is total silence (D-12).

### Integration Points
- New `guild_blocklist` table in `database.py::SCHEMA_SQL` + load-all / insert / delete helpers.
- New `silenced` get/set helpers in `database.py`; new `_blocked` set + silence/block methods on
  `GuildConfigService`; both loaded at boot in the existing service `load_all()` path.
- `logic/guild_config.py::decide_ambient_channel` — new `silenced` branch (D-14).
- `services/gemini.py` — `guild_id` kwargs on `chat()`/`generate_image()` + per-guild `dict` counter
  + a read accessor for `/guilds list` (D-08/D-09).
- `bot.py` — `CommandTree.interaction_check` override (D-13); block-check-first in `on_guild_join`
  (OWNER-04); `tree.error` handling for the refused-interaction `CheckFailure`.
- `cogs/ops.py` — the `/guilds` `app_commands.Group` (six subcommands) with inline `is_owner()` +
  `LyricsPageView` pagination.
- Gemini call sites across `cogs/ai.py`, `events.py`, `music.py`, `library.py`, `imagine.py` — pass
  `guild_id`; `services/memory.py:383` passes `None`.
- **Regression surface:** every test mocking `bot.guild_config.get()` / exercising
  `decide_ambient_channel` / `interaction_check`.

</code_context>

<specifics>
## Specific Ideas

- **The blocklist's own table is the load-bearing decision.** Everything else in this phase is
  additive plumbing; D-01 is the one choice that reaches across a phase boundary. Moving the
  blacklist out of `guild_config` is what lets Phase 21's memory surgery stay a clean `DELETE ...
  WHERE guild_id = $1` with no "except if blocked" carve-out — and it is why a kicked abuser can
  never launder their block by re-inviting. Every other option re-introduces the exact fragility
  Phase 19 D-12 warned about.

- **Two choke points, zero per-cog checks — that is the whole point of OWNER-05.** A future
  contributor adding a new slash command gets block/silence enforcement for free from
  `interaction_check`; a new ambient surface gets it from `decide_ambient_channel`. If a reviewer
  ever has to ask "did you remember to check silenced here?", the design failed — the same
  structural-safety instinct Phase 18 D-01 and Phase 19 D-22 established.

- **Silence's honesty beats silence's silence.** A muted guild's members seeing "i've been muted
  in this server. not my call." learn the truth in one ephemeral line; a truly-silent refusal is
  indistinguishable from a crashed bot. The ambient path stays fully quiet (no reply is the correct
  ambient behavior), but a *command* deserves an answer — even a refusing one.

- **"This session" is the right window for a kill-switch, not a limitation.** The counter resets on
  restart precisely because the owner is triaging a *live* session. A guild that hammered the API
  yesterday and went quiet is not the guild you reach for the kill-switch over; the one lighting up
  the top of `/guilds list` right now is. Durable history is a different (unbuilt) feature.

- **`block` = `leave` + blacklist is a deliberate coupling, `leave` alone is deliberately preserved.**
  You never blacklist a guild you're still in, and you sometimes leave a guild (a test server) you'd
  never blacklist. Collapsing them either way loses a real capability — hence two commands with one
  shared teardown.

- **PORT-04's disclosure is being earned here.** The honest "full-savage personality + reactive
  kill-switch" tradeoff Phase 23 discloses is only true if the kill-switch is real, fast, and
  re-invite-proof. D-01 + D-11 + D-13 are what make that sentence defensible.

</specifics>

<deferred>
## Deferred Ideas

- **MEM-04 guild-data purge on removal** (`guild_config`, `guild_queues`, `guild_jams`,
  guild-scoped `user_memories`) → **Phase 21**. Phase 20's `guild_blocklist` table is deliberately
  OUT of that purge's scope (D-01) — Phase 21 must delete guild data freely while the blacklist
  survives.
- **Memory guild-scoping** (MEM-01/02/03/05) → Phase 21, under the standing Descope Rule.
- **SCALE-F1 — a soft per-guild rate ceiling on priority-2 Gemini calls** → conditional and future.
  RATE-01's observability (D-08/D-10) is the prerequisite; the ceiling ships "only if observability
  proves starvation is real" (REQUIREMENTS.md). Not this phase.
- **DB-persisted / historical per-guild usage analytics** — rejected in D-08 as heavier than a live
  triage view needs. If the owner ever wants cross-session usage trends, revisit.
- **A confirm/undo ceremony on force-leave/block** — rejected in D-07 (reversible ops). If a
  fat-fingered `guild_id` ever causes a real incident, revisit.
- **`/invite` + least-privilege OAuth2 URL** → Phase 22 (sequenced after this control plane exists,
  per ROADMAP — the abuse-mitigation story must be real before promoting the invite).
- **Landing page, case-study README, build badge, Pages CD, GHCR** → Phase 23. The kill-switch is
  PORT-04 disclosure material.
- **Ripping out the dead `guild_config.is_blocked` column** — left in place (D-03); a later cleanup
  at most, never a Phase 20 blocker.

None of the above are lost — each has a named home in a later v1.4 phase.

### Reviewed Todos (not folded)
None — no pending todos matched this phase's scope.

</deferred>

---

*Phase: 20-owner-control-plane-rate-observability*
*Context gathered: 2026-07-11*
