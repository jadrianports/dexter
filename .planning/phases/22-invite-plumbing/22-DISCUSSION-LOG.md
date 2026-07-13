# Phase 22: Invite Plumbing - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-14
**Phase:** 22-invite-plumbing
**Areas discussed:** Permission bitfield policy, Single-source-of-truth mechanism, Client ID sourcing, /invite command UX, Drift-guard scan surface, Developer Portal step, Runtime permission gaps

---

## Permission bitfield policy

| Option | Description | Selected |
|--------|-------------|----------|
| Functional-complete | The 8 perms the code provably uses (view_channel, send_messages, embed_links, attach_files, add_reactions, read_message_history, connect, speak). Zero admin-adjacent perms. Nothing silently breaks on a fresh invite. | ✓ |
| Bare-minimum core | send_messages + embed_links + connect + speak only. /imagine attachments, emoji reactions, now-playing edits silently fail until an admin grants more. | |
| Functional + buffer | The 8 provable perms plus forward-looking extras (send_messages_in_threads, use_external_emojis) that nothing uses today. | |

**User's choice:** Functional-complete
**Notes:** Each permission was grounded in a live code citation before the question was asked — 78 `embed=` sends, `discord.File` in `cogs/imagine.py:69`, three `add_reaction` sites in `cogs/events.py`, `fetch_message` in `cogs/music.py:833`, `voice.channel.connect()` in `cogs/music.py:526`. Grep confirmed zero uses of `manage_messages` or external emojis anywhere.

---

## Bitfield enforcement

| Option | Description | Selected |
|--------|-------------|----------|
| Test-locked | pytest asserts the exact bitfield AND that administrator/manage_guild/manage_roles/manage_channels/ban/kick are all False. INVITE-01's "no Administrator" becomes a regression-locked contract. | ✓ |
| Declared only | A well-commented `Permissions()` in config.py. Nothing stops a future phase from quietly adding manage_guild. | |

**User's choice:** Test-locked
**Notes:** Matches the mock-free `logic/` test discipline from Phase 10.

---

## Single-source-of-truth mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Builder + drift-guard test | One pure `build_invite_url()` is the only URL constructor. A pytest greps every tracked doc for `oauth2/authorize` URLs and asserts each equals the built one. Passes vacuously today; enforces the moment Phase 23 pastes a link. | ✓ |
| Builder + generator script | Same builder plus `scripts/print_invite_url.py` for Phase 23 to run. Nothing catches a later hand-edit. | |
| Builder + docs point at /invite | Bot-only source; docs say "run /invite". Fails SC-2/PORT-01 — a recruiter needs a clickable button. | |

**User's choice:** Builder + drift-guard test
**Notes:** The test makes drift structurally impossible rather than merely discouraged.

---

## Client ID sourcing

| Option | Description | Selected |
|--------|-------------|----------|
| Committed constant + env override | Client IDs are public by design (visible in every invite link). Commit as the config.py default, allow DISCORD_CLIENT_ID to override. CI runs the drift test with zero secrets; Phase 23's static docs need no env. | ✓ |
| Env var only | DISCORD_CLIENT_ID in .env, falling back to bot.application_id. The CI drift test would have to skip (no secrets in Actions) — quietly gutting the guarantee. | |
| Runtime bot.application_id only | Nothing outside a live bot process can build the URL; Phase 23 would hardcode it by hand — exactly the drift SC-3 forbids. | |

**User's choice:** Committed constant + env override
**Notes:** The decisive constraint is that the Phase 18 GitHub Actions CI gate has no `.env` and no secrets.

---

## /invite command UX — presentation

| Option | Description | Selected |
|--------|-------------|----------|
| Public embed + link button | Public embed with a dry one-liner plus a link-style "Add to Discord" button. A link button needs no custom_id and no timeout handling. | ✓ |
| Ephemeral embed + link button | Only the invoker sees it — hides the one command whose purpose is spreading the bot. | |
| Plain public message with raw URL | Simplest, but renders as an ugly link preview. | |

**User's choice:** Public embed + link button

---

## /invite command UX — DMs and home

| Option | Description | Selected |
|--------|-------------|----------|
| DM-allowed, own cogs/invite.py | Zero new plumbing (the Phase 20 choke point already models `has_guild=False`). Own cog matches the one-concern-per-cog convention and keeps INVITE-02 traceable to one file. | ✓ |
| DM-allowed, folded into cogs/help.py | Fewer files, but muddies traceability and grows a cog that had one clean job. | |
| Guild-only, own cog | Pointlessly blocks the natural "DM the bot for its invite link" flow. | |

**User's choice:** DM-allowed, own cogs/invite.py
**Notes:** Verified `bot.py:101-104` computes `has_guild` and `logic/guild_config.py::decide_interaction_allowed` treats DMs as a first-class case before asking.

---

## Drift-guard scan surface

| Option | Description | Selected |
|--------|-------------|----------|
| git-tracked scan, literal URLs only | Walk `git ls-files`, regex any `oauth2/authorize` URL, assert equality. Implicitly forbids shorteners/vanity redirects — a redirect is the untestable indirection SC-3 exists to prevent. Auto-covers whatever files Phase 23 creates. | ✓ |
| Hardcoded file list | Check README.md and site/index.html specifically. Silently misses any new doc Phase 23 adds. | |
| Allow a redirect, check the target | Needs network in CI and couples the gate to an external service. | |

**User's choice:** git-tracked scan, literal URLs only

---

## Developer Portal install link

| Option | Description | Selected |
|--------|-------------|----------|
| Documented human step + UAT item | The portal's install-link field is a web UI, genuinely not code. Ship the code, record a human-verifiable step in 22-HUMAN-UAT.md — the acknowledged-deferred pattern used since Phase 11. | ✓ |
| Out of scope entirely | Leaves SC-3's "publicly-promoted link" with a third unguarded copy. | |

**User's choice:** Documented human step + UAT item

---

## Runtime permission gaps

| Option | Description | Selected |
|--------|-------------|----------|
| Defer to backlog | A permission self-diagnostic (/permcheck, or a startup warning) is a new capability — its own phase. Phase 22's contract is only that the URL *requests* the right perms. | ✓ |
| Fold a minimal check into this phase | On guild join, compare granted vs requested perms and report. Useful, but scope creep into Phase 19's onboarding surface. | |

**User's choice:** Defer to backlog

---

## Claude's Discretion

- `/invite` falls back to `bot.application_id` when the committed client-ID constant is unset (the fork case).
- No cooldown on `/invite` — it returns a static string, so there is nothing to rate-limit (a deliberate departure from `/help`'s 5s cooldown).
- Exact module home for `build_invite_url()` (`logic/invite.py` vs `utils/`) and the precise embed copy.
- Whether scopes are passed to `discord.utils.oauth_url()` as a tuple or built literally; whether `integration_type` must now be explicit given user-install apps exist — researcher to confirm against discord.py 2.7.1.

## Deferred Ideas

- **Runtime permission-gap self-diagnostic** (`/permcheck`, or an on-guild-join granted-vs-requested comparison DM'd to the admin) — a new capability, not a clarification of INVITE-01/02. Backlog.
- **Vanity/short invite link** — ruled out by the literal-match drift guard. Would require redesigning the guard first.
