# Phase 19: Onboarding & Admin Setup - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-10
**Phase:** 19-onboarding-admin-setup
**Areas discussed:** `/setup` command shape, Join-welcome behavior, Toggle semantics, Owner join/leave notice, plus three user-requested follow-on rounds (permission/testing conventions, invisible-failure traps, dispatch mechanics)

**Selection method:** User chose all four initially-offered gray areas, then chose "Explore more gray areas" three consecutive times. Every decision was explicitly selected by the user; none were adopted on their behalf.

---

## Area 1 — `/setup` command shape

### Q1: What shape should `/setup` take?

| Option | Description | Selected |
|--------|-------------|----------|
| Subcommand group | `/setup channel|roasts|vision` — the `/memory` group idiom; stateless, no view timeouts, per-subcommand `manage_guild` check | ✓ |
| One command + panel view | Ephemeral `ChannelSelect` + toggle buttons; prettiest, but ephemeral views can't be persistent across restarts | |
| `/setup` + separate `/settings` | Two top-level commands for one admin surface | |

**User's choice:** Subcommand group (recommended)
**Notes:** → D-01. Precedent: `cogs/memory.py:238`, `cogs/library.py:417/620`.

### Q2: How should ONBOARD-03's "channel dropdown picker" be read?

| Option | Description | Selected |
|--------|-------------|----------|
| Typed `channel: discord.TextChannel` param | Discord renders it as a native searchable picker; zero custom UI, no timeout, no author guard | ✓ |
| Explicit `discord.ui.ChannelSelect` view | Most literal reading; costs a stateful View, dead after restart | |

**User's choice:** Typed channel param (recommended)
**Notes:** → D-02. Includes an explicit note for the verifier that ONBOARD-03 is satisfied by the native picker.

### Q3: Re-running `/setup` on an already-configured guild?

| Option | Description | Selected |
|--------|-------------|----------|
| Silent re-designate | Update, push-invalidate, reply old → new; `configured` stays true | ✓ |
| Require a confirm button | Mirrors `ForgetConfirmView`; a click guarding a self-correcting action | |
| Add `/setup reset` | A fourth subcommand guarding a non-destructive write | |

**User's choice:** Silent re-designate (recommended)
**Notes:** → D-03. Danger-confirm ceremony reserved for unrecoverable ops like `/memory forget`.

### Q4: Where does the admin command live?

| Option | Description | Selected |
|--------|-------------|----------|
| New `cogs/admin.py` | Separates `manage_guild`-gated from `is_owner`-gated surfaces; leaves `ops.py` clean for Phase 20 | ✓ |
| Extend `cogs/ops.py` | Fewer files; mixes two permission models in one module | |
| You decide | Planner's discretion | |

**User's choice:** New `cogs/admin.py` (recommended)
**Notes:** → D-04.

---

## Area 2 — Join-welcome behavior

### Q1: Does `on_guild_join` insert a `guild_config` row immediately?

| Option | Description | Selected |
|--------|-------------|----------|
| Insert on join (`configured=false`) | Makes `joined_at` real; gives Phase 20's blacklist a row to mark; gives Phase 21's purge something to delete | ✓ |
| No row until `/setup` | Fewer writes; Phase 20 must upsert-from-nothing to block an unconfigured guild | |

**User's choice:** Insert on join (recommended)
**Notes:** → D-10. Still structurally silent — `decide_ambient_channel` returns `None` for `configured=false`.

### Q2: Welcome message tone?

| Option | Description | Selected |
|--------|-------------|----------|
| In-persona + explicit next step | Savage one-liner, then a plain line naming `/setup channel` | ✓ |
| Fully in-persona, no instructions | Maximum character; they kick the bot | |
| Neutral embed, personality after setup | Safest first impression; forfeits the screenshot moment | |

**User's choice:** In-persona + explicit next step (recommended)
**Notes:** → D-11. Same dial-back-for-functional-content instinct as CLAUDE.md Critical Rule 6.

### Q3: `resolve_announce_channel` returns `None`, or the send raises `Forbidden`?

| Option | Description | Selected |
|--------|-------------|----------|
| Silent skip + log + owner notice | Annotate the ONBOARD-05 notice (already firing) with "welcome not posted" | ✓ |
| Silent skip + log only | Simplest; discards nearly-free information | |
| DM the guild owner | Highest delivery; an unsolicited bot DM to a stranger | |

**User's choice:** Silent skip + log + owner notice (recommended)
**Notes:** → D-13. This choice is what forces the welcome to be awaited rather than `make_task`'d (see follow-on round 3).

### Q4: Boot backfill — Dexter is usually offline when invited, so `on_guild_join` never fires

| Option | Description | Selected |
|--------|-------------|----------|
| Backfill row + post welcome | Insert missing rows at boot; welcome only if the insert actually happened. Under the on-demand hosting model this is the NORMAL invite path | ✓ |
| Backfill row, no welcome | Zero risk of a welcome burst; an offline-invited guild never learns `/setup` exists | |
| No backfill at all | Least code; a guild invited while offline is invisible to Phase 20's owner list | |

**User's choice:** Backfill row + post welcome (recommended)
**Notes:** → D-14. Two constraints surfaced immediately after: backfill must run **after** `seed_home_guild` (or the home guild gets welcomed), and the welcome must key on the **DB insert result**, not a cache miss (a fail-closed empty cache would welcome-spam every guild). `seed_guild_config_if_absent` can't currently report insertion — needs a `RETURNING` signal.

---

## Area 3 — Toggle semantics

**Live finding surfaced before this round:** `_handle_message_reactions` (`cogs/events.py:396`) fires on every message in every channel of every guild, outside the `is_ambient_channel` gate computed six lines later. It survived Phase 18 because CONFIG-04's scope list never named reactions.

### Q1: What does `ambient_roasts_enabled` gate?

| Option | Description | Selected |
|--------|-------------|----------|
| All non-vision unprompted output | Voice roasts, proactive callbacks, idle, startup, milestone/repeat-song, reactions | ✓ |
| Roast surfaces only | An admin who turns "roasts off" still gets 2am memory callbacks | |
| Roasts + callbacks, not idle/startup | Presence signals exempt; a muted guild still gets unrequested messages | |

**User's choice:** All non-vision unprompted output (recommended)
**Notes:** → D-18. Admin mental model: "does it talk unprompted" vs "does it look at our images".

### Q2: Defaults on a fresh `/setup channel`?

| Option | Description | Selected |
|--------|-------------|----------|
| roasts ON, vision OFF | Vision ships stranger-uploaded images to a third-party API — a different consent class. Asymmetry: default-on means the harm already happened | ✓ |
| Both ON | `/setup` is already the consent step; simplest to explain | |
| Both OFF | Maximum consent; a configured guild that hears nothing looks broken | |

**User's choice:** roasts ON, vision OFF (recommended)
**Notes:** → D-19. Consistent with Phase 17 gating vision hardest (real safety block, silent skip, per-user cooldown, chance 0.12).

### Q3: Where does the toggle check live?

| Option | Description | Selected |
|--------|-------------|----------|
| Surface-keyed resolver | `resolve_ambient_channel(guild, surface=AmbientSurface.…)` returns `None` when that surface is off. A required enum has no dangerous default | ✓ |
| Separate pure predicates | Zero churn on Phase 18 code; a check a future surface can forget | |
| Predicates now, fold in later | Defers churn; guarantees touching these call sites twice | |

**User's choice:** Surface-keyed resolver (recommended)
**Notes:** → D-22. Phase 18's D-02 rejected a *boolean* safety flag; a required keyword enum is the opposite. Consequence: `on_message` can no longer compute `in_ambient_channel` once for both gates (the WR-02 comment at `cogs/events.py:399`).

### Q4: The ungated reaction handler?

| Option | Description | Selected |
|--------|-------------|----------|
| Gate by ambient toggle + configured | Close the CONFIG-04 hole; one guard on one call site | ✓ |
| Gate by configured, not by the roast toggle | Preserves the charming 👀; a second rule | |
| Leave it alone | Out of stated scope; PORT-04 can't then claim "silent until /setup" | |

**User's choice:** Gate by ambient toggle + configured (recommended)
**Notes:** → D-21. Scope of "gated" clarified in the next round (designated channel only).

---

## Area 4 — Owner join/leave notice

*(`ERROR_LOG_CHANNEL_ID` was not offered as a question — ONBOARD-05 names it literally. Recorded as D-17.)*

### Q1: Embed contents?

| Option | Description | Selected |
|--------|-------------|----------|
| Everything the kill-switch needs | Name, copy-pasteable guild ID, member count, owner tag+ID, created-at, total guild count, welcome-posted flag | ✓ |
| Minimal | Name, ID, join/leave, timestamp | |
| Everything + who invited | Requires `View Audit Log`, which INVITE-01's least-privilege bitfield won't request | |

**User's choice:** Everything the kill-switch needs (recommended)
**Notes:** → D-16. The "who invited" option was rejected on a Phase 22 dependency — flagged in Deferred Ideas as worth revisiting if INVITE-01's bitfield changes.

### Q2: `on_guild_remove` — the OWNER-04 vs MEM-04 contradiction

*Surfaced during analysis: Phase 21's MEM-04 purges `guild_config` on removal; Phase 20's OWNER-04 requires `is_blocked` to survive removal so a re-invite is refused. These contradict.*

| Option | Description | Selected |
|--------|-------------|----------|
| Notify + evict cache; flag the conflict | Touch no DB rows; write the contradiction into CONTEXT.md as a hard constraint on Phase 21 | ✓ |
| Notify + delete the `guild_config` row | Self-contained; destroys `is_blocked`, letting a kicked guild re-invite as brand new | |
| Notify only | Leaves a stale cache entry for a departed guild | |

**User's choice:** Notify + evict cache; flag the conflict (recommended)
**Notes:** → D-12. Phase 19 deliberately forecloses nothing; Phase 21 must preserve a blocked guild's row or move the blacklist to its own table.

### Q3: Reaction scope (carried back from Area 3)

| Option | Description | Selected |
|--------|-------------|----------|
| Designated channel only | One seam, one rule; the claim PORT-04 gets to make honestly | ✓ |
| Anywhere in the guild, if roasts are on | Reactions are silent and delightful precisely where unexpected; a second rule | |

**User's choice:** Designated channel only (recommended)
**Notes:** → D-21.

### Q4: How does an admin see current config?

| Option | Description | Selected |
|--------|-------------|----------|
| Every subcommand echoes full state | No fourth subcommand, no extra permission check | ✓ |
| Add `/setup show` | Most discoverable; a fourth subcommand | |
| You decide | Planner's discretion | |

**User's choice:** Every subcommand echoes full state (recommended)
**Notes:** → D-05.

---

## Follow-on round 1 — permission, DM guard, testing, and the vision-default trap

| Question | Options | Choice |
|---|---|---|
| Non-admin rejection | In-persona ephemeral refusal ✓ / Plain ephemeral error | In-persona (→ D-08) |
| DM / no-guild guard | `guild_only()` decorator + inline guard ✓ / decorator only | Both (→ D-09) |
| Testing | Standing convention ✓ / also mock the Interaction | Standing convention (→ D-26) |
| **Vision default trap** | Columns default `true`, `/setup` writes the policy ✓ / default `false` + one-time backfill UPDATE / default `false`, accept the regression | Columns default `true` (→ D-20) |

**Notes:** The trap: the home guild's row already has `configured=true`, so `ADD COLUMN vision_roasts_enabled DEFAULT false` would silently disable vision roasting there, breaking CONFIG-05's "current behavior unchanged" promise. Resolution puts the policy in `/setup channel` and leaves the column default backward-compatible. Also recorded: `tests/test_proactive_events.py` is a known regression surface for D-22's signature change.

---

## Follow-on round 2 — invisible failures and multi-tenant noise

| Question | Options | Choice |
|---|---|---|
| **`/setup channel` picks an unwritable channel** | Validate at write time, refuse ✓ / validate-warn-write-anyway / write silently and rely on D-03 | Validate + refuse (→ D-06) |
| Startup message across guilds | Home guild only ✓ / every configured guild, toggle-gated / drop it in foreign guilds as a hard rule | Home guild only (→ D-23) |
| `/setup roasts` before `/setup channel` | Accept, name the gap in the reply ✓ / refuse until a channel is set | Accept (→ D-07) |
| Discoverability | Welcome + `/help` admin section ✓ / welcome only / welcome + nudge on first `/play` | Welcome + `/help` (→ D-25) |

**Notes:** D-06 is the phase's one deliberate exception to "no output beats a wrong output" — D-03's silent-skip is designed for a channel that *was* valid and later broke, not one that was never valid. A silent failure at the moment of configuration is indistinguishable, to the admin, from a broken bot.

---

## Follow-on round 3 — dispatch mechanics

| Question | Options | Choice |
|---|---|---|
| Welcome dispatch | Awaited inline in try/except ✓ / `make_task` fire-and-forget | Awaited (→ D-13) |
| Backfill welcome cap | No cap, sequential, log each ✓ / hard cap with explicit log | No cap (→ D-15) |
| Home-guild identification | Service remembers what it seeded ✓ / re-resolve from env at send time / an `is_home` column | `home_guild_id` on the service (→ D-24) |

**Notes:** The welcome must be awaited *because* D-13 has the owner notice report whether it posted — a `make_task` can't hand its result back. A backfill cap would be a silent truncation ("some guild got a row and no welcome, and nothing says so"). `home_guild_id` keeps `DEXTER_CHANNEL_ID` out of every runtime path, per Phase 18 D-09's demotion; it is `None` on a fresh clone, so a recruiter running the repo gets no startup message anywhere — which is correct.

---

## Claude's Discretion

Explicitly handed to the planner (do not re-ask):

- Exact DDL for the two toggle columns (`ALTER TABLE ... ADD COLUMN IF NOT EXISTS ... BOOLEAN NOT NULL DEFAULT true`).
- Exact shape and member set of `AmbientSurface`, and how many pure functions `logic/guild_config.py` grows.
- Whether the `RETURNING`-based "did I insert?" signal is a new helper or a changed contract on `seed_guild_config_if_absent`.
- Where the boot backfill runs within `on_ready` (after `seed_home_guild`, guarded by `_ready_done`).
- All prompt/copy for the welcome, the non-admin refusal, the `/setup` echo, and the owner embeds.
- How `/setup channel` distinguishes a first configure from a re-designate.
- Whether `/setup` subcommands share a `_require_guild_admin` helper; cog class naming and load-list wiring.
- The exhaustive call-site inventory for the surface-keyed resolver (`cogs/music.py`'s repeat-song and milestone roasts were named but never enumerated in Phase 18).

The user selected "You decide" on zero questions — every offered decision was made explicitly.

## Deferred Ideas

- Readers/setters for `silenced` + `is_blocked`, `/guilds`, silence, force-leave, `CommandTree.interaction_check` block enforcement, per-guild Gemini `guild_id` tagging → **Phase 20**.
- Any DB purge on guild removal → **Phase 21**, constrained by D-12's recorded contradiction.
- Memory guild-scoping (MEM-01/02/03/05) → **Phase 21**, under the standing Descope Rule.
- `/invite` + the least-privilege OAuth2 URL → **Phase 22**. If its bitfield ever requests `View Audit Log`, D-16's rejected "who invited it" field is worth revisiting.
- Landing page, case-study README, build badge, Pages CD, GHCR → **Phase 23**. D-19 and D-12 are both PORT-04 disclosure material.
- A setup nudge on first `/play` in an unconfigured guild — rejected in D-25; revisit if live UAT shows admins never find `/setup`.
- A `/setup reset` / explicit un-configure subcommand — rejected in D-03; "both toggles off" already serves as a self-serve off-switch.
- Retrying a deferred welcome — moot under D-15 (no cap, so nothing is ever deferred).
