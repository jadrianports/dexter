---
phase: 22-invite-plumbing
reviewed: 2026-07-13T23:54:52Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - bot.py
  - cogs/help.py
  - cogs/invite.py
  - config.py
  - logic/__init__.py
  - logic/invite.py
  - tests/test_invite_cog.py
  - tests/test_invite_drift_guard.py
  - tests/test_invite_logic.py
findings:
  critical: 0
  warning: 3
  info: 1
  total: 4
status: issues_found
---

# Phase 22: Code Review Report

**Reviewed:** 2026-07-13T23:54:52Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Phase 22 wires a least-privilege OAuth2 invite: a single pure URL builder
(`logic/invite.py`), config constants (`config.py`), the `/invite` slash
command (`cogs/invite.py`), dual cog registration + `/help` listing, and a
CI drift-guard test suite. The security-critical surface — the permission
bitfield — is airtight: `test_bitfield_matches_ten_permission_derivation`
proves `INVITE_PERMISSIONS_VALUE` (309240908864) has *exactly* the ten named
bits and no others (constructing the value from ten kwargs and asserting
equality forecloses any hidden dangerous bit), and negative/positive
assertions lock out escalation and silent capability loss. The single-URL-
constructor invariant and drift guard are well-designed, with a mandatory
positive control proving the vacuous pass is not a false green. No critical
issues.

The findings below concern the `client_id` resolution path, which is the one
place correctness depends on runtime/env state rather than committed
constants — and matters specifically because this milestone ("Open House")
is about forks running their own bot instance.

## Warnings

### WR-01: Fork silently inherits the origin bot's client_id — the `application_id` fallback is effectively unreachable

**File:** `cogs/invite.py:39`, `config.py:278`
**Issue:** The cog resolves the client id as
`client_id = config.DISCORD_CLIENT_ID or self.bot.application_id`, and
`config.DISCORD_CLIENT_ID` is `int(os.getenv("DISCORD_CLIENT_ID") or "1492588698364018898")`
— a hardcoded, always-truthy default. Because the default is non-zero, the
left operand of the `or` is essentially never falsy, so the
`self.bot.application_id` "fork fallback" (documented at `cogs/invite.py:36-38`
as the safety net) can only trigger if a fork explicitly sets
`DISCORD_CLIENT_ID=0` in its env — an unintuitive way to opt into "use my real
application id." A fork that simply forgets to set `DISCORD_CLIENT_ID` will
silently emit **the origin author's** client id (1492588698364018898), so
`/invite` in the fork adds Dexter's original bot, not the fork's bot. This
defeats the stated purpose of the constant ("The env override keeps a fork
pointed at its own Discord application," `config.py:276-277`) for the common
forgot-to-configure case. In a multi-tenant/forking milestone this is a real
footgun: the failure is silent and wrong, not loud.
**Fix:** Make the running bot's real application id the authoritative source
and treat the committed constant as the CI/offline fallback (the reverse of
current precedence), so a live fork always self-heals to its own id:
```python
# Prefer the running bot's real application id; fall back to the committed
# constant only when the bot isn't logged in yet (e.g. the CI drift-guard,
# which has no running client).
client_id = self.bot.application_id or config.DISCORD_CLIENT_ID
```
If the current precedence (constant-first) is intentional for drift-guard
parity, then at minimum log a warning at startup when
`bot.application_id` is set and differs from `config.DISCORD_CLIENT_ID`, so a
misconfigured fork is not silent.

### WR-02: `client_id` can resolve to `None`, producing a malformed `client_id=None` invite URL with no guard

**File:** `cogs/invite.py:39-45`, `logic/invite.py:38-67`
**Issue:** When `config.DISCORD_CLIENT_ID` is `0` (explicit env `DISCORD_CLIENT_ID=0`)
**and** `self.bot.application_id` is `None` (bot not yet fully identified),
`client_id` becomes `None`. That `None` is passed to `build_invite_url`, whose
signature annotates `client_id: int` but performs no validation;
`discord.utils.oauth_url(None, ...)` does not raise — it string-interpolates,
yielding a URL containing `client_id=None`. The user gets a silently broken
invite link rather than an error. The docstring and type hint both promise an
`int`, so this violates the function's own contract without any runtime
enforcement.
**Fix:** Validate before building and fail loudly (or fall back deterministically):
```python
client_id = self.bot.application_id or config.DISCORD_CLIENT_ID
if not client_id:
    await interaction.response.send_message(
        "can't build an invite — my client id isn't configured. tell the owner.",
        ephemeral=True,
    )
    return
```
Alternatively add an explicit `if not client_id: raise ValueError(...)` guard at
the top of `build_invite_url` so the contract is enforced at the single seam.

### WR-03: `/invite` is a public reply with no cooldown — channel-flood/spam vector, inconsistent with `/help`

**File:** `cogs/invite.py:24-34, 57`
**Issue:** `/invite` sends a **public** message (`interaction.response.send_message`
with no `ephemeral=True`, deliberate per D-05) and carries **no cooldown**
(comment at lines 24-27: "does zero I/O … nothing to rate-limit"). The
justification only weighs server-side compute — it ignores the channel-spam
dimension: any user can repeatedly invoke `/invite` to flood a channel with the
embed + button. The directly comparable command, `/help` (`cogs/help.py:40`),
is also public but *does* carry `@app_commands.checks.cooldown(1, 5.0)`. Dropping
the cooldown here is an inconsistency that opens a low-grade abuse/annoyance
vector a public bot in the "Open House" milestone will be exposed to.
**Fix:** Mirror `/help`'s cooldown (compute is not the point — flood control is):
```python
@app_commands.command(name="invite", description="Get Dexter's invite link")
@app_commands.checks.cooldown(1, 5.0)
async def invite_command(self, interaction: discord.Interaction) -> None:
    ...
```
If truly no cooldown is wanted, consider making the reply `ephemeral=True` so a
spammer only floods themselves — but that trades away the D-05 "spreading the
bot is the point" intent, so the cooldown is the better fix. Note
`test_invite_command_has_no_cooldown` (`tests/test_invite_cog.py:106-109`) would
need updating; it currently locks in the spammable behavior.

## Info

### IN-01: Drift-guard extension allowlist (`.md`/`.html`/`.txt`) leaves invite URLs in other tracked text formats unguarded

**File:** `tests/test_invite_drift_guard.py:50`
**Issue:** `TEXT_EXTENSIONS = frozenset({".md", ".html", ".txt"})` scopes the doc
drift guard to three extensions. An invite URL pasted into any other tracked,
human-facing text format — e.g. `.rst`, `.json`/`.yml` site config, `.svg`, or a
Dockerfile/label — would drift from the canonical URL without failing CI. The
Python single-constructor guard (`test_logic_invite_is_the_only_url_constructor`)
covers `.py`, and today no such files carry an invite URL, so this is latent
rather than active. Given Phase 23 ("site generator") is named as the future
consumer, a non-`.md`/`.html` asset carrying the link is plausible.
**Fix:** Either broaden `TEXT_EXTENSIONS` to include the formats Phase 23 will
actually emit (e.g. add `.rst`, `.svg`, `.json`) once known, or add a comment at
line 50 explicitly documenting that non-listed extensions are an accepted
coverage gap so a future author knows the boundary is deliberate, not an
oversight.

---

_Reviewed: 2026-07-13T23:54:52Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
