# Phase 19: Onboarding & Admin Setup - Context

**Gathered:** 2026-07-10
**Status:** Ready for planning

> **Session note:** Every decision below was **explicitly selected by the user** across five
> AskUserQuestion rounds (four chosen gray areas, then three rounds of user-requested
> follow-on areas). No decision was adopted on the user's behalf. All numeric/structural
> minutiae remain planner discretion per the Phase 11/13/14/15/16/17/18 precedent.
>
> Two latent defects were surfaced *during* discussion and are captured as hard constraints
> below: an **ungated reaction handler** (a live CONFIG-04 hole) and an **OWNER-04 vs MEM-04
> contradiction** that will bite Phase 21 if not designed around now.

<domain>
## Phase Boundary

Phase 19 makes a fresh server **self-serviceable**: a server admin can turn Dexter "on" for
their own guild with zero intervention from the owner. This is the **preventive half of
safety** (Phase 20 is the reactive half).

Phase 18 shipped the seam; Phase 19 is the first **user-facing** consumer of it. Three of
Phase 18's artifacts were built specifically for this phase and currently have **zero
callers**: `resolve_announce_channel` (D-02), `_refresh_cache_entry` (the push-invalidate
hook), and the `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` idiom handed forward by D-12.

**In scope:**
- **ONBOARD-01** — `on_guild_join` posts a welcome/setup-nudge via `resolve_announce_channel`,
  wrapped so a permission failure never crashes the join. Plus a **boot backfill** for guilds
  Dexter was invited to while offline (the normal case under the on-demand hosting model).
- **ONBOARD-02** — `/setup`, gated by an **inline** `manage_guild` check. `default_permissions`
  is a UI hint only, never the gate.
- **ONBOARD-03** — a channel **dropdown picker**, not a raw channel argument.
- **ONBOARD-04** — independent per-guild `ambient_roasts_enabled` / `vision_roasts_enabled`
  toggles, added via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (Phase 18 D-12).
- **ONBOARD-05** — owner notification in `ERROR_LOG_CHANNEL_ID` on every guild join and remove.
- **Closing the CONFIG-04 reaction hole** (D-14) — `_handle_message_reactions` currently fires
  in every channel of every guild, ungated. It slipped through Phase 18 because CONFIG-04's
  scope list never named reactions.

**Out of scope (belongs to later phases):**
- Any **reader or setter** for `silenced` / `is_blocked`, the owner control plane
  (`/guilds`, silence, force-leave), `CommandTree.interaction_check` block enforcement, and
  per-guild Gemini usage tagging → **Phase 20** (OWNER-01…06, RATE-01). Phase 18 D-11 stands.
- **Any DB purge on guild removal** (`guild_config`, `guild_queues`, `guild_jams`,
  `user_memories`) → **Phase 21** (MEM-04). Phase 19's `on_guild_remove` touches **no rows**
  (D-12).
- Memory guild-scoping → Phase 21. Invite URL / `/invite` → Phase 22. Landing page, README
  case study, build badge, Pages CD, GHCR → Phase 23.
- **Per-guild persona intensity dial** — explicitly Out of Scope in REQUIREMENTS.md; conflicts
  with the locked "full-savage everywhere" decision. The two ONBOARD-04 toggles are
  *on/off*, never *intensity*.
- Any change to `OWNER_ID` / `ERROR_LOG_CHANNEL_ID` — these stay **global**.

</domain>

<decisions>
## Implementation Decisions

### `/setup` command shape (ONBOARD-02 / ONBOARD-03)

- **D-01 (user-selected): `/setup` is an `app_commands.Group` with three subcommands** —
  `/setup channel`, `/setup roasts on|off`, `/setup vision on|off`. This is exactly the
  `/memory` group idiom (`cogs/memory.py:238` — `view`/`forget`/`callbacks`) and the
  `/playlist` + `/jam` groups in `cogs/library.py`. Stateless, no view timeouts, each
  subcommand carries its own inline `manage_guild` check, and Phase 20 can extend the group
  without restructuring.
  *(Rejected: a single `/setup` posting an ephemeral panel with a `ChannelSelect` + two toggle
  buttons — an ephemeral `discord.ui.View` cannot be persistent (`timeout=None`) the way
  `NowPlayingView` is, so it needs timeout handling and an interaction-author guard for a
  once-per-guild interaction; a `/setup` + separate `/settings` split — two top-level commands
  for one admin surface, and "settings" is a name that invites future scope.)*

- **D-02 (user-selected): the channel picker is a typed slash-command parameter**
  (`channel: discord.TextChannel`), **not** a `discord.ui.ChannelSelect` view. Discord's
  client renders a typed channel parameter as a native, searchable channel dropdown — it **is**
  the picker, and it pre-filters to channels the invoker can see. ONBOARD-03's target ("rather
  than a raw channel argument") means *not a channel-ID string*.
  > **Note for the verifier:** ONBOARD-03 is satisfied by the native picker. Do not flag the
  > absence of a `ChannelSelect` component as a gap.

  *(Rejected: an explicit `ChannelSelect` view — reads most literally, but costs a stateful
  View with timeout + author-guard handling and a dead interaction after any restart. Only
  warranted if D-01 had gone the panel route.)*

- **D-03 (user-selected): re-running `/setup channel` on an already-configured guild silently
  re-designates.** Update `ambient_channel_id`, push-invalidate via `_refresh_cache_entry`,
  reply with old → new. `configured` stays `true`. Re-pointing a channel is cheap and instantly
  reversible; the danger-confirm ceremony (`ForgetConfirmView`) belongs on destructive,
  unrecoverable operations like `/memory forget`.
  *(Rejected: a confirm button — a click guarding a self-correcting action; a `/setup reset`
  subcommand — a fourth subcommand guarding a non-destructive write, and it hands a guild admin
  a way to reach the `configured=false` state that only Phase 20's owner-silence is meant to own.)*

- **D-04 (user-selected): the admin surface lives in a NEW `cogs/admin.py`.** `cogs/ops.py` is
  the **owner/analytics** surface (`/stats`, `/leaderboard`, `/skips`), gated by `is_owner()`.
  A guild-admin surface is a different audience with a different gate (`manage_guild`). Keeping
  the two permission models in separate modules stops a future contributor from copying the
  wrong gate, and leaves `ops.py` clean for Phase 20's owner control plane.

- **D-05 (user-selected): every `/setup` subcommand echoes the FULL resulting config**
  (channel, roasts, vision) ephemerally and in persona. No fourth `/setup show` subcommand —
  the admin always sees the whole picture immediately after touching any part of it.

- **D-06 (user-selected): `/setup channel` VALIDATES `send_messages` at write time and
  REFUSES.** Check `channel.permissions_for(guild.me).send_messages` **before** writing the
  row. If Dexter cannot post there, refuse with a specific message naming the channel and the
  missing permission, and **write nothing**.

  This is the single most likely real-world setup failure, and Phase 18's D-03 silent-skip makes
  it **invisible**: the admin sees "setup complete" and a bot that never speaks. D-03's
  silent-skip is correctly designed for a channel that *was* valid and later broke — not one
  that was never valid. **Setup is the one moment where failing loudly is right.**
  *(Rejected: validate-warn-write-anyway — leaves a guild in a permanently broken `configured`
  state; write silently and rely on D-03 — functionally indistinguishable, to the admin, from a
  broken bot.)*

- **D-07 (user-selected): `/setup roasts|vision` before `/setup channel` is ACCEPTED, with the
  gap named in the reply.** Store the toggle, reply "noted. i still don't have a channel — run
  `/setup channel` first." The toggles are independent state; refusing a valid write because of
  unrelated missing state is surprising, and `decide_ambient_channel` already returns `None`
  regardless of the toggles. D-05's full-config echo makes the gap obvious.
  *(Rejected: refusing until a channel is designated — makes `/setup channel` a prerequisite of
  two other commands for no structural reason.)*

- **D-08 (user-selected): a non-admin gets an IN-PERSONA EPHEMERAL refusal** (e.g. "nice try.
  go find someone with manage server."). Ephemeral, so nobody is publicly dunked on for trying —
  and a permission-probing stranger gets no public signal.

- **D-09 (user-selected): `@app_commands.guild_only()` on the group AND an inline
  `if interaction.guild is None: return` guard before anything touches permissions.** Defense in
  depth, the same instinct as ONBOARD-02's rule that `default_permissions` is never the gate.
  Two lines.

### Join / remove lifecycle (ONBOARD-01 / ONBOARD-05)

- **D-10 (user-selected): `on_guild_join` INSERTS a `guild_config` row immediately**
  (`configured = false`, `ON CONFLICT (guild_id) DO NOTHING`), then push-invalidates the cache.
  The guild stays structurally silent — `decide_ambient_channel` already returns `None` for
  `configured = false`. This makes `joined_at` (a column Phase 18 shipped and nothing writes)
  real, gives Phase 20's `/guilds` list and `silenced` / `is_blocked` flags a row to mark, and
  gives Phase 21's MEM-04 purge something to delete.

  Phase 20's OWNER-04 must be able to blacklist a guild that **never ran `/setup`** — which is
  precisely the abusive guild most likely to need blocking.
  *(Rejected: no row until `/setup` — `joined_at` never gets a meaningful value and Phase 20
  must upsert-from-nothing to block an unconfigured guild.)*

- **D-11 (user-selected): the welcome is IN-PERSONA + names the exact next command.** A savage
  one-liner that lands the personality, followed by a plain, sarcasm-free line naming
  `/setup channel`. This is the same dial-back-for-functional-information instinct as Critical
  Rule 6. The welcome is the **one** message a stranger sees before deciding whether to keep the
  bot, and ambient-default-OFF means silence is indistinguishable from broken.
  *(Rejected: fully in-persona with no instructions — maximum character, but they just kick the
  bot; a neutral embed with personality held back — safest first impression, but forfeits the
  moment Dexter is most likely to be screenshotted.)*

- **D-12 (user-selected): `on_guild_remove` NOTIFIES the owner and EVICTS the cache entry. It
  touches NO DB rows.** No events arrive for a guild Dexter has left, so the cache entry is
  dead weight; dropping it also stops `bot.guild_config.get()` from returning a row for a guild
  Dexter isn't in (a defense Phase 20's guild-list would otherwise need).

  > **⚠ HARD CONSTRAINT ON PHASE 21 — surfaced during this discussion.**
  > **Phase 21's MEM-04 purges `guild_config` on removal. Phase 20's OWNER-04 requires
  > `is_blocked` to SURVIVE removal so a re-invite is refused. These contradict.**
  > If MEM-04 deletes the `guild_config` row, a guild kicked for abuse can re-invite Dexter
  > and be treated as brand new — silently defeating the entire kill-switch.
  > **Phase 21 MUST either (a) preserve a blocked guild's `guild_config` row while purging
  > everything else, or (b) move the blacklist to its own table.** Phase 19 deliberately
  > touches no rows so that this stays Phase 20/21's decision to make deliberately, not one
  > Phase 19 forecloses.

  *(Rejected: notify + delete the `guild_config` row — self-contained and makes the re-invite
  path immediately correct, and it is exactly the bug above; notify only — leaves a stale cache
  entry for a departed guild.)*

- **D-13 (user-selected): the welcome send is AWAITED INLINE, wrapped in try/except.** The
  handler is short and the steps are ordered: insert row → attempt welcome → send owner notice.
  Because D-16's owner notice reports **whether the welcome posted**, the welcome must be
  awaited — a `make_task` cannot hand its result back. Phase 9's `make_task` is for work spawned
  *out of* a handler (prefetch, auto-queue, auto-lyrics), not for the handler's own body.

  On `resolve_announce_channel` returning `None`, or on `Forbidden` / any send exception:
  **silent skip + `WARNING` to `dexter.log` + the failure annotated into the owner join notice**
  ("welcome not posted — no writable channel"). This satisfies ONBOARD-01's "a permission
  failure never crashes the join" literally, and the owner learns about a guild that invited
  Dexter with no send permission — a real signal, nearly free, since the notice is already being
  sent in the same handler.
  *(Rejected: DM the guild owner as a fallback — highest delivery rate, also an unsolicited bot
  DM to a stranger, which is how bots get reported, and it can raise `Forbidden` too.)*

### Boot backfill (ONBOARD-01 — the on-demand-hosting consequence)

- **D-14 (user-selected): at boot, for each guild in `bot.guilds` with NO row: insert it, and —
  only if the insert ACTUALLY HAPPENED — run the same welcome path as `on_guild_join`.**

  **Rationale:** Dexter runs on the owner's PC on demand, so it is usually **offline when
  someone invites it** and `on_guild_join` never fires. Under this hosting model, backfill is
  the **normal** invite path, not an edge case: a recruiter invites Dexter, sees nothing, and is
  greeted the next time the owner turns it on. "No row" is a precise proxy for "never welcomed",
  so this cannot double-welcome.

  **⚠ Two ordering/correctness constraints the planner MUST honor:**
  1. **Backfill runs AFTER `seed_home_guild`** in `on_ready`. Otherwise the home guild is
     backfilled as `configured = false` **and welcomed** — breaking CONFIG-05.
  2. **The welcome is keyed on the DB insert actually happening, NOT on a cache miss.** Under
     Phase 18's D-07 fail-closed rule, an errored cache reads as *every guild unconfigured* —
     which would welcome-spam every server on a Neon hiccup. `database.py::seed_guild_config_if_absent`
     (`database.py:425`) **cannot currently report this**: it does `INSERT ... ON CONFLICT DO
     NOTHING` followed by a separate `SELECT`, so its return value is identical whether it
     inserted or conflicted. **Phase 19 needs a `RETURNING`-based "did I insert?" signal.** If
     the DB is down the insert raises, no welcome is sent, and fail-closed is preserved.

- **D-15 (user-selected): NO cap on backfill welcomes — sequential, one log line each.** Await
  each send in order; discord.py's own rate limiter paces them. The milestone's scale target is
  single-digit to low-dozens of guilds, so the worst realistic burst is small. A cap here would
  be a **silent truncation** — some guild gets a row and no welcome, and nothing says so. Emit
  one log line per send plus a single owner summary with the count.

### Owner notifications (ONBOARD-05)

- **D-16 (user-selected): the join/leave embed carries everything the kill-switch needs** —
  guild name, **guild ID as copy-pasteable text**, member count, guild owner tag + ID, guild
  created-at, Dexter's new total guild count, and (join only) whether the welcome posted (D-13).

  Phase 20's OWNER-02/03 take a `guild_id` argument; making it one-click copyable from the
  notice is the difference between a kill-switch usable in ten seconds and one you go hunting
  for.
  *(Rejected: minimal name+id — you reach for member count and owner identity the moment you're
  triaging abuse, which is the only reason this notice exists; adding the inviting user from the
  audit log — the most useful triage field, and unavailable, because INVITE-01's least-privilege
  bitfield will not request `View Audit Log`. It would fail silently on most guilds.)*

- **D-17: the notice goes to `ERROR_LOG_CHANNEL_ID`.** Not a gray area — ONBOARD-05 names it
  literally, and REQUIREMENTS.md's blockquote already establishes it as the "private cross-guild
  ops channel." No new env var. On a fresh clone with no error channel set, `log_to_discord`
  no-ops harmlessly.

### Toggle semantics (ONBOARD-04)

- **D-18 (user-selected): `ambient_roasts_enabled` gates ALL non-vision unprompted output.**
  Voice-join / late-night roasts, proactive memory callbacks, idle-loneliness, the startup
  message, the repeat-song and milestone roasts in `cogs/music.py`, **and** emoji reactions
  (D-21). `vision_roasts_enabled` gates image roasts only.

  An admin's mental model is two things — *"does it talk unprompted"* and *"does it look at our
  images"* — which is exactly what a two-toggle requirement should mean.
  *(Rejected: gating only the roast surfaces — an admin who toggles "roasts off" and still gets
  unprompted memory callbacks at 2am will reasonably call that a bug; exempting idle + startup
  as "presence signals" — a guild that disabled ambient output still gets messages it never
  asked for.)*

- **D-19 (user-selected): a fresh `/setup channel` leaves roasts ON and vision OFF.**
  Vision sends **stranger-uploaded images to a third-party API** — a materially different
  consent class from text roasting, which is why Phase 17 gated it hardest (real safety block at
  `BLOCK_MEDIUM_AND_ABOVE`, silent skip, per-user cooldown, chance `0.12`). The asymmetry
  decides it: default-on and an unhappy admin means **the harm already happened**; default-off
  and a keen admin runs one command. The honest PORT-04 disclosure also writes itself.

- **D-20 (user-selected): BOTH new columns are `ADD COLUMN ... NOT NULL DEFAULT true`; the
  default-vision-OFF policy lives in `/setup channel`, NOT in the column default.**

  **This is a trap, surfaced during discussion.** The home guild's row already exists with
  `configured = true`. An `ADD COLUMN vision_roasts_enabled ... DEFAULT false` would **silently
  turn vision roasting OFF in the owner's home guild**, breaking CONFIG-05's "current behavior
  is unchanged after the refactor" promise. So: **both columns default `true`** (every
  pre-existing row keeps today's exact behavior), and `/setup channel` **explicitly writes
  `vision_roasts_enabled = false`** at the moment it flips a guild from
  `configured = false → true` for the first time. Policy lives in code where it is readable and
  testable; the column default exists only to preserve backward compatibility.

  > Note the interaction with D-10: `on_guild_join` creates the row with `configured = false`
  > and both toggles at their `true` defaults. Nothing fires (`decide_ambient_channel` returns
  > `None`), and the first `/setup channel` writes the real policy. The planner must ensure the
  > "first configure" write is distinguishable from D-03's re-designate (which must **not**
  > reset a toggle the admin has since changed).

  *(Rejected: `DEFAULT false` + a one-time `UPDATE ... WHERE configured = true` backfill — a
  data migration in a codebase that has only ever shipped idempotent DDL, and it would also
  "rescue" any guild that had already run `/setup` and deliberately turned vision off; `DEFAULT
  false` + accept the home-guild regression — costs the CONFIG-05 promise and a verifier
  comparing before/after home-guild behavior would correctly flag it.)*

- **D-21 (user-selected): CLOSE THE REACTION HOLE — `_handle_message_reactions` is gated by the
  ambient toggle AND `configured` AND the designated channel.**

  **Discovered during this discussion:** `cogs/events.py:396` calls `_handle_message_reactions`
  on **every message in every channel of every guild**, entirely outside the `is_ambient_channel`
  gate computed 6 lines later. So an unconfigured guild is silent in text while Dexter still
  reacts 👀 / 🫡 / 😐 everywhere. This survived Phase 18's consolidation only because CONFIG-04's
  scope list never named reactions.

  Reactions route through the **same surface-keyed resolver** as every other ambient behavior —
  one seam, one rule, nothing to remember. *"Dexter speaks and reacts where you told him to"* is
  a sentence an admin can hold in their head, and it is the claim PORT-04 gets to make honestly.
  A bot advertising "structurally silent until `/setup`" while visibly reacting in every channel
  cannot make that claim.
  *(Rejected: gate on `configured` but not the channel, so a 👀 still lands in `#music` — a
  second rule, and the ambient seam no longer has exactly one shape; leave it alone — defer the
  finding to Phase 20, at the cost of the PORT-04 claim.)*

### Where the toggle check lives (the structural seam)

- **D-22 (user-selected): a SURFACE-KEYED resolver —
  `resolve_ambient_channel(guild, *, surface: AmbientSurface) -> TextChannel | None`** —
  returns `None` when that surface is disabled for the guild.

  Phase 18's own stated philosophy: *"The seam's safety property should be structural, not
  remembered."* A future ambient surface **literally cannot fire without naming itself**. Phase
  18's D-02 rejected `resolve_channel(guild, allow_fallback: bool)` because *a boolean that
  flips a safety property is exactly the argument a future caller passes wrong* — a **required
  keyword enum with no default** is the opposite of that.

  `AmbientSurface` needs (at least) three members:
  | Member | Gated by | Surfaces |
  |---|---|---|
  | `ROAST` | `ambient_roasts_enabled` | voice-join / late-night roasts, proactive callbacks, repeat-song + milestone roasts, emoji reactions |
  | `VISION` | `vision_roasts_enabled` | image roasts |
  | `PRESENCE` | `ambient_roasts_enabled` | startup message, idle-loneliness |

  `PRESENCE` maps to the same column as `ROAST` today (per D-18) but stays a distinct member —
  it is a different *intent*, it is where D-23's home-guild rule attaches, and Phase 20's
  `silenced` flag will want to treat it separately.

  **Consequence the planner must handle:** `cogs/events.py::on_message` can **no longer compute
  `in_ambient_channel` once and reuse it for both gates** (the WR-02 comment at
  `cogs/events.py:399`). Proactive resolves `surface=ROAST`; vision resolves `surface=VISION`.
  They were already required to stay separate conditionals — now they resolve separately too.
  The `logic/guild_config.py::is_ambient_channel` predicate needs the same surface keying.

  *(Rejected: separate pure predicates each dispatch site must remember to call — zero churn on
  freshly-landed Phase 18 code, but it is precisely the check a future surface can forget, which
  is the failure mode D-01 exists to make impossible; predicates now, fold in later — defers the
  churn and guarantees touching these call sites twice, since Phase 20's `silenced` will want the
  same treatment.)*

### Startup message in a multi-tenant world

- **D-23 (user-selected): the startup message ("i'm back. did you miss me. probably not.") fires
  in the HOME GUILD ONLY.** Idle-loneliness stays per-guild (it responds to real local activity).

  The line is an in-joke for a community that knows Dexter goes down. A stranger's server
  receiving "i'm back" every time the owner opens their laptop is noise — and it advertises the
  on-demand hosting caveat in the least flattering way possible, several times a day.

- **D-24 (user-selected): "home guild" is identified by `GuildConfigService.home_guild_id`,
  set during `seed_home_guild` and `None` when unset/unresolvable.** `seed_home_guild` already
  resolves the guild id; it just remembers it. The startup message asks the service.

  No new column, no env var in a runtime path — preserving Phase 18's rule that a grep for
  `DEXTER_CHANNEL_ID` outside the boot seed returns nothing. On a fresh clone (a recruiter
  running the repo) `home_guild_id` is `None`, so **nobody** gets a startup message, which is
  exactly right.
  *(Rejected: re-resolving `bot.get_channel(DEXTER_CHANNEL_ID).guild.id` at send time —
  duplicates the seed's resolution logic and puts the env var back into a runtime path D-09
  demoted it out of; an `is_home` column — fully derivable from the seed, so it can drift, and
  Phase 18 D-12 established that each phase ships only the columns its requirements name.)*

### Discoverability

- **D-25 (user-selected): the welcome message PLUS a short admin section in `cogs/help.py`**
  listing `/setup` and what it gates. The welcome can be deleted, buried, or land in a channel
  nobody reads. `/help` is what people run when a bot *seems* broken — which, under
  ambient-default-OFF, is exactly how an unconfigured Dexter looks.
  *(Rejected: welcome only — the failure mode of ambient-default-OFF is an admin who never saw
  the welcome; adding a setup nudge on first `/play` in an unconfigured guild — highest delivery,
  but it injects setup chatter into a command flow CONFIG-04 promises "just works immediately on
  join", and it is a new unprompted surface in a phase about not having those.)*

### Testing

- **D-26 (user-selected): the standing convention holds.**
  - **Mock-free TDD** (`tests/test_guild_config_logic.py` and siblings) for the pure logic: the
    `AmbientSurface` enum, the surface-keyed predicate, and the "should I welcome this guild"
    decision derived from the insert result.
  - **Live-DB tests** for the new `database.py` helpers — which Phase 18's CI pgvector service
    container now **actually runs** rather than skips.
  - **Untested-by-design** (structural review + clean boot): `cogs/admin.py` and the
    `on_guild_join` / `on_guild_remove` glue.

  *(Rejected: driving `/setup` through a faked `discord.Interaction` to lock the `manage_guild`
  rejection path — catches a real bug class, but breaks a convention held since Phase 10 and
  imports Discord mocking into a deliberately mock-free suite.)*

  > **Known regression surface:** `tests/test_proactive_events.py` already mocks
  > `bot.guild_config.get()` (updated in Phase 18-06 from patching `DEXTER_CHANNEL_ID`). It will
  > need updating again for D-22's surface-keyed signature. **Treat every test that touches
  > `guild_config` or `is_ambient_channel` as a call-site inventory.**

### Claude's / Planner's Discretion (do NOT re-ask the user)

- **Exact DDL** for `ambient_roasts_enabled` / `vision_roasts_enabled` — `ALTER TABLE
  guild_config ADD COLUMN IF NOT EXISTS ... BOOLEAN NOT NULL DEFAULT true` per D-20, following
  the `bot_daily_stats.total_errors` (Phase 8) / `user_profiles.proactive_opt_out` (Phase 16)
  idiom.
- **Exact signature and member set of `AmbientSurface`** (an `enum.Enum` vs `StrEnum` vs a
  `Literal`), and how many pure functions `logic/guild_config.py` grows — so long as they stay
  keyword-only, `discord`-free, `datetime`-free, `random`-free, and mock-free tested.
- **The `RETURNING`-based "did I insert?" helper** (D-14) — whether it is a new
  `database.py::insert_guild_config_if_absent` returning `bool`/`Record | None`, or a changed
  return contract on `seed_guild_config_if_absent`. Note `seed_home_guild` depends on the
  current shape.
- **Where the boot backfill runs** — inside `on_ready` after `seed_home_guild` (D-14 constraint
  1), guarded by the existing `_ready_done` so a reconnect cannot re-run it. Note `on_ready`
  fires on every reconnect; the "row exists" check is the real idempotency guard.
- **Exact prompt/copy** for the welcome message, the non-admin refusal, the `/setup` echo, and
  the owner join/leave embed — subject to the personality rules (lowercase, one emoji max,
  under 500 chars, sarcasm dialed back for functional instructions).
- **How `/setup channel` distinguishes a first configure from a re-designate** (D-20's note) —
  e.g. branching on the cached row's `configured` value before the write.
- **Whether `/setup` subcommands share a `_require_guild_admin(interaction)` helper** and
  whether `cogs/admin.py` gets its own `AdminCog` or extends an existing class.
- **How `cogs/admin.py` is added to the cog-load list** in `bot.py` and whether the new commands
  need anything beyond the existing `on_ready` global `tree.sync()` / owner `/sync`.
- **Which exact call sites need the surface-keyed resolver** — the greps in `<code_context>` are
  a starting point, not an exhaustive list; verify by call-site (`cogs/music.py`'s repeat-song
  and milestone roasts are named by D-18 but were not enumerated in Phase 18's inventory).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements (this phase)
- `.planning/ROADMAP.md` §"Phase 19: Onboarding & Admin Setup" — goal, dependency on Phase 18,
  and the 4 success criteria.
- `.planning/REQUIREMENTS.md` §"Onboarding & Admin Setup (ONBOARD)" — ONBOARD-01…05, including
  ONBOARD-02's explicit rule that `default_permissions` is a UI hint, never the gate.
- `.planning/REQUIREMENTS.md` §"Per-Guild Configuration (CONFIG)" — the seam this phase consumes,
  and the blockquote that `OWNER_ID` + `ERROR_LOG_CHANNEL_ID` stay **global**.
- `.planning/REQUIREMENTS.md` §"Owner Control Plane / Kill-Switch (OWNER)" — read OWNER-04
  before designing `on_guild_remove` (see D-12's hard constraint).
- `.planning/REQUIREMENTS.md` §"Memory Scoping & Guild Data Lifecycle (MEM)" — MEM-04's purge is
  the other half of D-12's contradiction.
- `.planning/REQUIREMENTS.md` §"Key Decisions (this milestone)" — the locked
  **"Ambient default-OFF until `/setup`"** decision, and **"Personality stays full-savage
  everywhere"** (the ONBOARD-04 toggles are on/off, never an intensity dial).
- `.planning/REQUIREMENTS.md` §"Out of Scope" — per-guild persona intensity dial, per-channel
  ambient config, automated abuse detection.
- `.planning/REQUIREMENTS.md` §"Descope Rule" — standing, user-directed. Applies to every phase.

### The Phase 18 seam this phase is the first consumer of
- `services/guild_config.py::GuildConfigService` — the cache owner. `resolve_announce_channel`
  (`:162`) has **zero callers** and was built for this phase's join-welcome (Phase 18 D-02).
  `_refresh_cache_entry` (`:92`) is the push-invalidate hook `/setup` calls.
  `resolve_ambient_channel` (`:124`) is the function D-22 adds a `surface` kwarg to.
  `seed_home_guild` (`:104`) is where D-24's `home_guild_id` gets remembered.
- `logic/guild_config.py::decide_ambient_channel` / `is_ambient_channel` — the pure seam D-22
  extends. Note `decide_ambient_channel` already returns `None` for `configured = false`, which
  is what makes D-10's row-on-join safe.
- `database.py::seed_guild_config_if_absent` (`:425`) and `load_all_guild_configs` (`:403`) —
  the existing helpers. **`seed_guild_config_if_absent` cannot report whether it inserted**
  (D-14 constraint 2) — it does `INSERT ... DO NOTHING` then a separate `SELECT`.
- `database.py` `SCHEMA_SQL` `guild_config` block (`:204`) — note `joined_at TIMESTAMPTZ DEFAULT
  now()` already exists and nothing writes it; D-10 makes it real. `silenced` / `is_blocked`
  ship with `false` defaults and have **no reader until Phase 20** (Phase 18 D-11) — do not add
  one.
- `bot.py:413-416` — `GuildConfigService` construction + `load_all()`.
  `bot.py:435` — the `seed_home_guild` call site. **D-14's backfill must run after this.**
  `bot.py:529` — the startup-message ambient resolve (D-23 makes it home-guild-only).
  `bot.py:747` — the idle-loneliness ambient resolve (stays per-guild).

### The code being gated (D-18 / D-21 / D-22)
- `cogs/events.py:396` — `await self._handle_message_reactions(message)`: the **ungated**
  reaction call, outside the `is_ambient_channel` gate computed at `:402`. This is D-21.
- `cogs/events.py:399-406` — the WR-02 comment + `in_ambient_channel` single-computation. D-22
  splits this per-surface.
- `cogs/events.py:408-418` — the proactive (`surface=ROAST`) and vision (`surface=VISION`)
  dispatch gates. They must remain **separate independent conditionals** (existing rule).
- `cogs/events.py:222`, `:266`, `:311` — the three voice-roast ambient resolves (`surface=ROAST`).
- `cogs/music.py` — the repeat-song and milestone roast surfaces named by D-18. **Not enumerated
  in Phase 18's inventory — locate by call-site.**

### Command + permission conventions
- `cogs/memory.py:238` — the `app_commands.Group` idiom D-01 mirrors (`view`/`forget`/`callbacks`),
  including ephemeral, self-scoped replies.
- `cogs/library.py:417` / `:620` — `/playlist` and `/jam` groups, the other `Group` precedents.
- `cogs/ops.py:247-252` — the **inline** `await self.bot.is_owner(interaction.user)` check,
  performed FIRST before any data access. D-08/D-09's `manage_guild` gate mirrors this shape
  (different permission, same discipline).
- `cogs/help.py` — where D-25's admin section lands.
- `bot.py:403-405` — `bot.log_to_discord`, the `ERROR_LOG_CHANNEL_ID` embed sink D-16/D-17 use.
  `utils/logger.py::log_to_discord` no-ops safely when the channel is unset.
- `utils/tasks.py::make_task` — Phase 9's fire-and-forget wrapper. **D-13 explicitly does NOT use
  it** for the welcome; it is for work spawned out of a handler.

### Testing + CI
- `tests/test_guild_config_logic.py` — the mock-free lock on the pure seam D-22 extends.
- `tests/test_guild_config_service.py` — the fake-bot service tests (note: the fake bot has no
  `log_to_discord` unless a test opts in).
- `tests/test_proactive_events.py` — **known regression surface**: mocks `bot.guild_config.get()`;
  needs updating for D-22's surface-keyed signature.
- `tests/conftest.py:34-46` — `TEST_DATABASE_URL` + skip-on-connection-error. Phase 18's CI now
  supplies a `pgvector/pgvector:pg16` service container, so live-DB tests **actually run**.
- `.github/workflows/ci.yml` — the blocking Ruff + pytest gate. Every Phase 19 commit runs behind
  it. Ruff lint + format are **blocking**.
- `.planning/codebase/TESTING.md` — the "pure logic gets TDD; Discord/process code is
  untested-by-design" convention D-26 preserves.

### Prior-phase context (conventions this phase inherits)
- `.planning/phases/18-per-guild-config-foundation-ci-gate/18-CONTEXT.md` — **read in full.**
  D-01 (strict resolution), D-02 (two-resolver split; why a boolean safety flag was rejected),
  D-03 (stale channel = silent skip, row intact), D-06 (load-all, cache miss is authoritative),
  D-07 (fail closed), D-08/D-09 (`ON CONFLICT DO NOTHING`, env var demoted), D-11 (forward
  columns unread until Phase 20), D-12 (Phase 19 owns the toggle columns), D-13 (no stopgap
  setter).
- `.planning/phases/17-vision-multimodal-roasting/17-CONTEXT.md` — why vision is gated hardest;
  the basis for D-19's default-OFF.
- `.planning/phases/16-proactive-memory-callbacks/16-CONTEXT.md` — the `proactive_opt_out`
  ALTER precedent; the **per-user** opt-out that composes with (and does not replace) the new
  **per-guild** toggles.
- `.planning/PROJECT.md` §"Key Decisions" — the full decision ledger; §"Context" for the
  cog → service → model layering and the testing convention.
- `CLAUDE.md` §"Critical Rules" — notably Rule 6 (dial back sarcasm for serious/functional
  content — the basis for D-11's plain instruction line), Rule 8 (lowercase), Rule 9 (designated
  channel only).
- `CLAUDE.md` §"Implementation Gotchas" — the `asyncpg` multi-statement DDL rule (`SCHEMA_SQL`
  is plain, param-free DDL in one `conn.execute()`) and the `logic/` pure-seam rule (glue
  dispatches on the returned value; do **not** mirror the branch logic back in the caller).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `services/guild_config.py::resolve_announce_channel` — the preserved 4-step fallback chain,
  built in Phase 18 for exactly this phase's join-welcome. **Zero callers today.** Note step 1
  reads `config.DEXTER_CHANNEL_ID`; on a foreign guild `guild.get_channel(...)` returns `None`
  and it falls through to system-channel → first-writable, which is correct.
- `services/guild_config.py::_refresh_cache_entry` — the push-invalidate seam `/setup` (D-03)
  and `on_guild_join` (D-10) both call after their writes.
- `database.py::seed_guild_config_if_absent` — the `ON CONFLICT DO NOTHING` insert. **Needs a
  `RETURNING`-based sibling** so D-14 can tell an insert from a conflict.
- `database.py::get_proactive_opt_out` / `set_proactive_opt_out` — the get/set upsert-helper
  shape the `/setup` toggle writers should mirror.
- `cogs/memory.py::MemoryCog` — `app_commands.Group` + ephemeral replies + `AllowedMentions.none()`.
  The structural template for `cogs/admin.py`.
- `cogs/ops.py:252` — the inline-permission-check-first discipline.
- `logic/guild_config.py` + `tests/test_guild_config_logic.py` — the pure-seam and mock-free-test
  templates D-22/D-26 extend.

### Established Patterns
- **cog → service → model layering**; services constructed in `bot.py`, attached as bot
  attributes, reached via `self.bot.<name>`. Cogs never construct services.
- **`logic/` is the pure seam** (Phase 10 D-02): nondeterminism and I/O computed in glue and
  passed as primitives; the glue **dispatches on the returned value** and does not mirror the
  branch logic.
- **Idempotent DDL**: `CREATE TABLE IF NOT EXISTS` for new tables;
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for later additions (D-20).
- **"No output beats a wrong output"** — the Phase 17 silent-skip instinct. **D-06 is the one
  deliberate exception**: setup is the single moment where a loud, specific failure beats
  silence.
- **Structural safety over remembered safety** — Phase 18's stated philosophy, which D-22
  extends from "which channel" to "which surface".
- **Testing convention** — pure logic gets mock-free TDD; Discord/process glue is
  untested-by-design, verified by structural review + clean local boot.

### Integration Points
- New `cogs/admin.py` (`/setup` group), added to the cog-load list in `bot.py`.
- `database.py`: two `ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS` statements (D-20), a
  `RETURNING`-based insert helper (D-14), and toggle get/set helpers.
- `services/guild_config.py`: `surface` kwarg on `resolve_ambient_channel` (D-22),
  `home_guild_id` attribute (D-24), toggle write + push-invalidate methods.
- `logic/guild_config.py`: `AmbientSurface` enum + surface-keyed predicate (D-22).
- `bot.py`: `on_guild_join` / `on_guild_remove` handlers (D-10/D-12/D-13/D-16); boot backfill in
  `on_ready` **after** `seed_home_guild` (D-14); startup message gated on `home_guild_id` (D-23).
- `cogs/events.py`: reaction gate (D-21); per-surface resolution replacing the single
  `in_ambient_channel` computation (D-22); three voice-roast resolves take `surface=ROAST`.
- `cogs/music.py`: repeat-song + milestone roast surfaces take `surface=ROAST` (D-18).
- `cogs/help.py`: admin section (D-25).
- **Regression surface:** `tests/test_proactive_events.py` and any test touching
  `bot.guild_config.get()` or `is_ambient_channel`.

</code_context>

<specifics>
## Specific Ideas

- **Setup is the one place Dexter should fail loudly.** Every other uncertainty in this subsystem
  resolves toward silence — D-01's strict resolver, D-03's stale-channel skip, D-07's fail-closed
  cache, Phase 17's silent safety skip. D-06 deliberately breaks that pattern, because a silent
  failure *at the moment of configuration* is indistinguishable from a broken bot, and the admin
  has nowhere to look. "Boring Dexter" is the correct failure mode at runtime; it is the **wrong**
  response to `/setup`.

- **The two toggles are on/off, never an intensity dial.** REQUIREMENTS.md lists "per-guild
  persona intensity dial" as Out of Scope precisely because it conflicts with "full-savage
  everywhere." The toggles answer *whether* Dexter speaks unprompted, never *how hard*.

- **Vision's default-OFF is the phase's honesty dividend.** It is the only surface that ships a
  stranger's uploaded image to a third-party API. Defaulting it off costs one command and buys
  PORT-04 a disclosure that reads as a considered decision rather than an admission.

- **Backfill is the normal path, not an edge case.** Because Dexter runs on demand, it is usually
  offline at the moment of invite. A recruiter clicks "Add to Discord", sees nothing, and is
  greeted the next time the owner turns the bot on. Any design that treats `on_guild_join` as the
  only welcome trigger silently breaks the milestone's headline user journey.

- **`AmbientSurface` is an enum precisely because Phase 18 rejected a boolean.** D-02 of Phase 18
  refused `resolve_channel(guild, allow_fallback: bool)` on the grounds that "a boolean that flips
  a safety property is exactly the argument a future caller passes wrong." A required keyword-only
  enum with no default has the opposite property: the caller cannot omit it, cannot get it wrong
  silently, and a new surface must declare its own intent to fire at all.

- **Two cross-phase landmines are recorded here on purpose.** The OWNER-04/MEM-04 contradiction
  (D-12) and the `vision_roasts_enabled` default trap (D-20) were both found by reading Phase 20
  and Phase 21's requirements against Phase 19's schema work. Neither is fixable later at the same
  cost. Naming them now beats discovering them during memory surgery.

</specifics>

<deferred>
## Deferred Ideas

- **Readers/setters for `silenced` + `is_blocked`, `/guilds`, silence, force-leave,
  `CommandTree.interaction_check` block enforcement, per-guild Gemini `guild_id` tagging** →
  **Phase 20** (OWNER-01…06, RATE-01). Phase 18 D-11 stands: the columns exist, unread.
- **Any DB purge on guild removal** (`guild_config`, `guild_queues`, `guild_jams`,
  guild-scoped `user_memories`) → **Phase 21** (MEM-04). Phase 19's `on_guild_remove` touches no
  rows (D-12) — **and Phase 21 must not delete a blocked guild's `guild_config` row, or move the
  blacklist to its own table.**
- **Memory guild-scoping** (MEM-01/02/03/05) → Phase 21, under the standing Descope Rule.
- **`/invite` + the least-privilege OAuth2 URL** → Phase 22. Noted here because D-16 rejected the
  audit-log "who invited it" field on the grounds that INVITE-01's bitfield will not request
  `View Audit Log` — if Phase 22 changes that, D-16 is worth revisiting.
- **Landing page, case-study README, build badge, Pages CD, GHCR image** → Phase 23. D-19's
  vision-default-OFF and D-12's kill-switch constraint are both PORT-04 disclosure material.
- **A setup nudge on first `/play` in an unconfigured guild** — rejected in D-25 as a new
  unprompted surface. If live UAT shows admins never find `/setup`, revisit.
- **A `/setup reset` / explicit un-configure subcommand** — rejected in D-03. Phase 20's owner
  silence is the intended mechanism; if guild admins ask for a self-serve off-switch, "both
  toggles off" already provides one.
- **Retrying a deferred welcome** — moot under D-15 (no cap, so nothing is ever deferred).

</deferred>

---

*Phase: 19-onboarding-admin-setup*
*Context gathered: 2026-07-10*
