# Phase 22: Invite Plumbing - Research

**Researched:** 2026-07-14
**Domain:** discord.py 2.7.1 OAuth2 invite-URL construction, Discord permission bitfields, git-tracked-doc drift-guard testing
**Confidence:** HIGH (all discord.py API claims verified against the installed 2.7.1 package source + Context7 docs; permission-set completeness verified by direct repo grep; drift-guard design verified against the actual current repo contents, not a hypothetical)

## Summary

Phase 22 is small and mechanical: one pure URL builder, one config constant, one cog, one bitfield-lock test, one drift-guard test. All of discord.py 2.7.1's relevant API surface was verified directly against the installed package (`pip show discord.py` confirms 2.7.1 is what's installed, matching `requirements.txt`'s `>=2.3.0` floor) — `discord.utils.oauth_url()`'s exact signature, `discord.Permissions`' full flag list, and `discord.ui.Button(style=link)`'s behavior were all inspected via `inspect.signature`/`inspect.getsource` on the live install, not recalled from training data.

Two findings materially change the plan from what CONTEXT.md assumed. First, the D-01 permission scan **missed one real call site**: `cogs/music.py:938`'s `parent.create_thread(...)` (the `/autolyrics` feature) requires `create_public_threads` on the parent channel, and posting into that thread (`thread.send(...)` at lines 950/958/965) requires `send_messages_in_threads` — neither is in the 8-permission table, and `/autolyrics` is a real, shipped, documented command, not speculative. Second, and more importantly, **CONTEXT.md's "the drift-guard test passes vacuously today" claim is false** — `dexter-architecture.md:824` (a git-tracked, non-`.planning/` file) already contains a literal, stale, hand-built invite URL (`permissions=3491904`, includes an `integration_type=0` query param discord.py's `oauth_url()` never emits, and is missing `view_channel`/`attach_files` while including unneeded `external_emojis`). Any drift-guard test written to CONTEXT.md's literal spec will fail immediately on introduction, not enforce silently — this must be fixed in the same phase or the CI gate goes red.

**A separate, unrelated, and more urgent finding:** the same `dexter-architecture.md` file contains what appears to be a literal live Discord bot token, application ID, and a guild ID in plaintext (lines 819–826, adjacent to the stale invite URL), committed to git. This is a real secret already in git history. See **Common Pitfalls → Pitfall 0 (Security)** — flagged for immediate rotation regardless of Phase 22 scope, and especially urgent given Phase 23 makes this repository/README a public portfolio piece.

**Primary recommendation:** Build `logic/invite.py::build_invite_url()` as a pure keyword-only function wrapping `discord.utils.oauth_url()`; commit `DISCORD_CLIENT_ID = 1492588698364018898` (the real, already-public app ID found in `dexter-architecture.md`) to `config.py` with an env override; lock the bitfield at `3263552` (8 perms) or `309240908864` (10 perms, if `/autolyrics`'s thread permissions are added — recommended); scope the drift-guard to exclude `.planning/**` and fix `dexter-architecture.md`'s stale line in the same phase.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Invite URL construction (`build_invite_url`) | API/Backend (`logic/` seam) | — | Pure function of (client_id, permissions, scopes); no Discord I/O, no network — textbook `logic/` tier per Phase 10 D-02 convention |
| `/invite` command response | API/Backend (`cogs/invite.py`) | Discord client rendering (embed+button) | Discord.py cog glue calls the pure builder and renders it; no business logic lives in the cog |
| Permission bitfield definition | API/Backend (`config.py` + test lock) | — | Static, deploy-time constant; test-locked, not runtime-derived |
| Drift-guard (git doc scan) | CI / Dev tooling | — | Pure repo-introspection test; runs in GitHub Actions, no Discord/DB dependency |
| Developer Portal install-link field | External service (Discord) | — | Explicitly out-of-code (D-08); human-verified, not automatable |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `discord.py` | 2.7.1 (installed; `requirements.txt` pins `>=2.3.0`) [VERIFIED: pip show discord.py] | `discord.utils.oauth_url()`, `discord.Permissions`, `discord.ui.Button` | Already the project's sole Discord SDK; no new dependency |

No new packages are introduced by this phase — `## Package Legitimacy Audit` is not applicable (zero new installs).

**Version verification:** `pip show discord.py` on the project's active environment returned `Version: 2.7.1`, matching CONTEXT.md's assumption exactly. [VERIFIED: pip show discord.py, run 2026-07-14]

## Package Legitimacy Audit

Not applicable — Phase 22 installs no new packages. All work uses the already-installed `discord.py` (stdlib to the project) plus `logic:0` new external code.

## Architecture Patterns

### System Architecture Diagram

```
User runs /invite (guild OR DM)
        |
        v
DexterCommandTree.interaction_check  (existing Phase 20 choke point — NO changes needed for D-06;
        |                             has_guild=False already resolves to True/allowed for DMs)
        v
cogs/invite.py :: invite_command(interaction)
        |
        v
logic/invite.py :: build_invite_url(client_id, permissions, scopes)  <-- PURE, no I/O
        |                                     ^
        |                                     |
        +---- config.DISCORD_CLIENT_ID -------+
        +---- config.INVITE_PERMISSIONS (Permissions object / int) --+
        +---- ("bot", "applications.commands") -----------------------+
        |
        v
discord.utils.oauth_url(...)  -->  "https://discord.com/oauth2/authorize?client_id=...&permissions=...&scope=bot+applications.commands"
        |
        v
Public embed + discord.ui.Button(style=link, url=<that string>)  -->  interaction.response.send_message(embed=, view=)

Separately, offline (CI / pytest, no Discord connection):
git ls-files (repo root)
   -> filter to text-doc extensions, exclude .planning/**
   -> regex-scan each file for discord.com/(api/)?oauth2/authorize URLs
   -> assert every found URL == build_invite_url()'s output   <-- the D-03 drift guard
```

### Recommended Project Structure

```
logic/
├── invite.py            # NEW: build_invite_url() — pure, mock-free, keyword-only
cogs/
├── invite.py             # NEW: /invite slash command, DM-allowed, public reply
config.py                 # + DISCORD_CLIENT_ID, + INVITE_PERMISSIONS (or the 8/10-tuple), + INVITE_SCOPES
tests/
├── test_invite_logic.py         # NEW: pure builder tests + bitfield negative-assertion lock (D-02)
├── test_invite_drift_guard.py   # NEW: git ls-files scan + positive-control + vacuous-pass proof (D-03)
```

### Pattern 1: Pure builder wrapping `discord.utils.oauth_url()`

**What:** `logic/invite.py::build_invite_url(*, client_id: int, permissions: int, scopes: tuple[str, ...] = ("bot", "applications.commands")) -> str` calls `discord.utils.oauth_url(client_id, permissions=discord.Permissions(permissions), scopes=scopes)`.

**When to use:** The single place any invite URL is ever constructed (D-03). `cogs/invite.py` calls it; nothing else may hand-build a query string.

**Verified signature (installed discord.py 2.7.1, via `inspect.signature`):**
```python
def oauth_url(
    client_id: Union[int, str],
    *,
    permissions: Permissions = MISSING,
    guild: Snowflake = MISSING,
    redirect_uri: str = MISSING,
    scopes: Optional[Iterable[str]] = MISSING,   # defaults to ('bot', 'applications.commands') if omitted
    disable_guild_select: bool = False,
    state: str = MISSING,
) -> str
```
[VERIFIED: raw.githubusercontent.com/Rapptz/discord.py/v2.7.1/discord/utils.py, fetched 2026-07-14]

There is **no `integration_type` parameter** on `oauth_url()` in 2.7.1 — confirmed by inspecting the live signature. User-installable-app support in discord.py 2.7.1 is a *separate* mechanism (`app_commands.allowed_installs()`, `app_commands.guild_install()`, `app_commands.user_install()` — server-side hints on individual slash commands, unrelated to the bot-invite OAuth2 URL). Since INVITE-01/02 want a **bot install** (add Dexter to a guild with `bot`+`applications.commands` scopes), not a **user install**, `integration_type` is not applicable to this phase's URL and should NOT be passed — there is nowhere to pass it. [VERIFIED: Context7 /websites/discordpy_readthedocs_io_en — "Support for user-installable apps... `app_commands.allowed_installs`... `app_commands.user_install()`"]

### Pattern 2: Permissions object → integer bitfield

**What:** `discord.Permissions(**kwargs)` is fully keyword-constructible; `.value` gives the integer bitfield discord.py's `oauth_url()` embeds in the query string.

```python
# Source: verified by executing against the installed discord.py 2.7.1 package
import discord
p = discord.Permissions(
    view_channel=True, send_messages=True, embed_links=True, attach_files=True,
    add_reactions=True, read_message_history=True, connect=True, speak=True,
)
p.value  # == 3263552
```
[VERIFIED: executed locally against installed discord.py 2.7.1, 2026-07-14]

All 8 keyword names in D-01's table are confirmed valid `Permissions` flags: `view_channel` (a `@permission_alias` for the "View Channels" bit — not a `@flag_value` itself, but a fully valid constructor kwarg and attribute), `send_messages`, `embed_links`, `attach_files`, `add_reactions`, `read_message_history`, `connect`, `speak` all confirmed as real flags via direct enumeration of `discord.Permissions.VALID_FLAGS`. [VERIFIED: raw.githubusercontent.com/Rapptz/discord.py/v2.7.1/discord/permissions.py]

### Anti-Patterns to Avoid

- **Hand-concatenating the query string:** `discord.utils.oauth_url()` already does this correctly (URL-encoding, scope joining with `+`) — do not string-format a URL manually anywhere, including in `dexter-architecture.md` (see Pitfall 2).
- **Passing `scopes=` as a bare string:** `oauth_url()` takes `Optional[Iterable[str]]` — a bare `"bot applications.commands"` string would iterate character-by-character. Use a tuple: `("bot", "applications.commands")` — this also matches discord.py's own internal default representation (a tuple), so an explicit pass and the omitted-default behavior are byte-identical. [VERIFIED: default value is literally the tuple `('bot', 'applications.commands')` per the docstring]
- **`integration_type` in the query string:** Not a discord.py-emitted parameter; the stale `dexter-architecture.md` URL has one anyway (`integration_type=0`, almost certainly hand-added via the Developer Portal UI, not the docs-recommended bot-install flow) — a rebuilt URL from `oauth_url()` will simply omit it, which is correct and expected, not a regression.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OAuth2 URL query-string construction | A manual f-string / urlencode call | `discord.utils.oauth_url()` | Already handles scope-joining (`+`-delimited), permission-value formatting, and param ordering exactly as Discord expects; a hand-rolled version is the exact kind of "second URL constructor" D-07 prohibits |
| Permission bitfield arithmetic | Manually summing bit values by hand | `discord.Permissions(**kwargs).value` | Self-documenting (keyword names, not magic numbers) and immune to bit-position drift across discord.py versions |

**Key insight:** This phase's entire "don't hand-roll" surface is one library call. The risk isn't reinventing a wheel — it's a second, informally-drifted copy of the same wheel (exactly what `dexter-architecture.md`'s stale line already is).

## Common Pitfalls

### Pitfall 0: A live secret is already committed to `dexter-architecture.md` (SECURITY — not gated on Phase 22, but discovered here)

**What goes wrong:** `dexter-architecture.md` lines 819–826 (immediately above/around the stale invite-URL line the drift-guard will scan) contain what reads as a literal Discord bot token in the canonical three-part format (`<base64 app id>.<base64 timestamp>.<HMAC>`), the numeric application ID, and a guild ("server") ID, each labeled in plain prose (`- bot token`, `- app id`, `-- server id for --first sync run`). This file is git-tracked (`git ls-files` confirms it) and is explicitly referenced from `CLAUDE.md` ("Read `dexter-architecture.md` for full context") — meaning it is a real, in-repo, in-history artifact, not a throwaway scratch file.

**Why it happens:** Looks like an early Phase-1 setup transcript/notes dump that was never scrubbed before committing.

**How to avoid:** This is independent of Phase 22's requirements (INVITE-01/02) but was surfaced by researching this exact file for the drift-guard. Recommend, out of band from this phase's plan (or as an explicit zero-requirement cleanup task folded into this phase since the file is being touched anyway): **rotate the bot token immediately in the Discord Developer Portal** (Bot → Reset Token) and update the runtime `.env`, then redact/remove the leaked lines from `dexter-architecture.md` in a follow-up commit. This is materially more urgent given Phase 23 turns this repository into a public-facing portfolio piece — a token left in git history before a public push is a live compromise vector even after the file's current content is edited (history retains it). A full history scrub (`git filter-repo` / BFG) would be needed if the repo is ever made public with its existing history intact; simply editing the file in a new commit is NOT sufficient once pushed publicly.

**Warning signs:** Anyone who clones the repo (or, after Phase 23, anyone who forks/views it on GitHub) has the token.

*(This finding does not block Phase 22 planning — INVITE-01/02 do not depend on it — but it must reach the user/PROJECT.md and ideally be resolved before Phase 23's public push. Recorded here because the D-03 drift-guard's file scan is exactly what surfaced it.)*

### Pitfall 1: The D-03 drift-guard does NOT "pass vacuously today" — it will fail on introduction unless `dexter-architecture.md` is fixed in this same phase

**What goes wrong:** CONTEXT.md states "This test passes vacuously today (no doc contains a link yet)." That premise is false: `dexter-architecture.md:824` already contains a literal, tracked, non-`.planning/` invite URL:
```
https://discord.com/oauth2/authorize?client_id=1492588698364018898&permissions=3491904&integration_type=0&scope=bot+applications.commands
```
[VERIFIED: grep of the live repo, 2026-07-14] Decoding `permissions=3491904` shows it currently grants `add_reactions, send_messages, embed_links, read_message_history, external_emojis, use_external_emojis (alias), connect, speak` — missing `view_channel` and `attach_files` (which the bot definitely needs, per D-01), while carrying `external_emojis`, which D-01 explicitly says is used nowhere in the codebase. It is also missing entirely from `view_channel`. A rebuilt canonical URL will not equal this string (different `permissions` value, no `integration_type` param) — so if the drift-guard test is written and run before this line is fixed, **it fails immediately, not vacuously**.

**Why it happens:** The researcher/planner reasonably assumed "no doc has a link yet" without grepping the one non-`.planning/` prose doc in the repo that predates this milestone.

**How to avoid:** Add an explicit task in this phase's plan: update (or delete) `dexter-architecture.md:824`'s stale invite-URL line — either replace it with the literal output of the new `build_invite_url()` call (so the drift-guard passes for real, not vacuously) or delete the line/paragraph if it's judged stale scratch content unworthy of updating. Given Pitfall 0's finding, the surrounding lines (818–826, the bot-token/app-id/server-id block) are prime candidates for deletion entirely rather than "fixing."

**Warning signs:** CI goes red the moment the drift-guard test is merged, with no code change having touched the invite feature itself — a confusing failure mode if not anticipated.

### Pitfall 2: The `.planning/` corpus contains legitimate non-canonical example URLs that must NOT be scanned

**What goes wrong:** Three `.planning/`-tree files already contain the substring `oauth2/authorize`:
- `.planning/phases/22-invite-plumbing/22-CONTEXT.md` and `22-DISCUSSION-LOG.md` — prose *describing* the regex pattern (`discord.com/…oauth2/authorize…`), not a real URL.
- `.planning/research/STACK.md` (and its milestone-archive copies under `.planning/codebase/STACK.md`, `.planning/research/archive-v1.3/STACK.md`) — a **placeholder** URL, `https://discord.com/oauth2/authorize?client_id=<APP_ID>`, used as a documentation example. `<APP_ID>` is not a real client ID and this string will never equal `build_invite_url()`'s output — if scanned, this is a permanent, unfixable false-positive failure.

**Why it happens:** A naive "scan every git-tracked text file" implementation (as CONTEXT.md's D-03 literally describes) does not distinguish "a doc mentioning the URL pattern" from "a doc that promotes an actual clickable invite link."

**How to avoid:** Scope the drift-guard's file scan to **exclude the entire `.planning/` tree** (a directory-prefix denylist, not a per-file allowlist). This is a clean, simple rule that:
1. Resolves all three current false-positive risks in one shot.
2. Still satisfies D-07's "auto-covers whatever new docs Phase 23 creates" guarantee, since Phase 23's README/`/site` additions live outside `.planning/`.
3. Matches the spirit of SC-3 ("the in-bot link and the publicly-promoted link... Developer Portal / landing page") — `.planning/` is neither.

Recommended implementation: `[f for f in git_ls_files() if not f.startswith(".planning/")]`, further filtered to a small text-extension allowlist (`.md`, `.html`, `.txt`) to sidestep any future binary asset Phase 23 might commit (a demo GIF, a favicon) without needing decode-error handling.

**Warning signs:** A `pytest -q` run failing on the very first commit that adds the drift-guard test, pointing at `STACK.md` or `22-CONTEXT.md`.

### Pitfall 3: A permission-requiring call site was missed by the D-01 discussion-time scan — `/autolyrics`'s thread creation

**What goes wrong:** `cogs/music.py:938` calls `parent.create_thread(name="🎵 lyrics", type=discord.ChannelType.public_thread)` — a `TextChannel.create_thread()` call that creates a genuinely new public thread (not a message-anchored thread). This requires the **`create_public_threads`** permission on the parent channel. The three subsequent `thread.send(...)` calls (lines 950, 958, 965) that post lyrics into that thread require **`send_messages_in_threads`** (posting into an *existing* thread you're not a member of, via a bot, is gated by this flag in the parent channel's permissions — distinct from the plain `send_messages` flag, which does not cover threads). [VERIFIED: raw.githubusercontent.com/Rapptz/discord.py/v2.7.1/discord/channel.py + discordpy migrating.rst: "A guild member can send messages in a public thread if they possess the send_messages_in_threads permission... Editing a thread requires manage_threads"]

Neither permission is in D-01's 8-permission table. `/autolyrics` is a real, shipped, documented slash command (`cogs/music.py:1806`, listed in CLAUDE.md's Music command table) that a user can turn on per-queue (`/autolyrics on`) — on a freshly-invited server missing these two permissions, every `/autolyrics on` session silently fails (the whole call is wrapped in a blanket `try/except Exception: log.warning(...)` at `_post_auto_lyrics`, so the failure is invisible to the Discord user — exactly the "worst possible first impression" scenario D-01's own rationale describes for `attach_files`/`add_reactions`).

**Why it happens:** The discussion-time scan's stated coverage ("reactions, file sends, voice connect, message-history fetch, embeds") did not include thread-creation as a category to check.

**How to avoid:** Flag for the planner/user: add `create_public_threads` and `send_messages_in_threads` to the permission set. This is not a "forward-looking buffer" (which D-01 correctly rejected) — it is a proven-by-code call site exactly like the other 8, just missed. Computed value with all 10 permissions:
```python
discord.Permissions(
    view_channel=True, send_messages=True, embed_links=True, attach_files=True,
    add_reactions=True, read_message_history=True, connect=True, speak=True,
    create_public_threads=True, send_messages_in_threads=True,
).value  # == 309240908864
```
[VERIFIED: executed locally against installed discord.py 2.7.1, 2026-07-14]

If the user/planner decides `/autolyrics` is low-priority enough to accept the existing silent-failure risk (it is opt-in, off by default, and the "one command silently no-ops instead of a music/roast/embed core feature breaking" bar is arguably lower than D-01's rejected buffer items), the 8-permission set (`3263552`) remains internally consistent — but this must be a **conscious** decision recorded in the plan, not an accidental omission. This researcher's recommendation: include it — it is code-proven, not speculative, and costs nothing (both permissions are as unprivileged as the other 8; neither implies moderation/admin capability).

**Warning signs:** A test asserting the bitfield exactly-equals `3263552` (D-02's negative-assertion lock) that a future contributor "fixes" by adding thread perms without realizing it's a deliberate value — recommend the lock test's comment explain which 8-or-10 permissions were chosen and why, so a future diff is legible as intentional.

### Pitfall 4: `discord.ui.Button(style=link, url=...)` combined with `label=` — a Context7-sourced doc snippet incorrectly implies incompatibility

**What goes wrong:** One Context7-fetched doc fragment states the `url` parameter "Cannot be combined with `label`, `emoji`, `custom_id`, or `sku_id`" — this is misleading/mis-extracted. The real constraint (verified by direct execution) is that `url` is incompatible with `custom_id` and `sku_id` (a button can't simultaneously be a link button, a callback button, and a store button) — `label` and `emoji` combine with `url` freely, and are in fact required for a usable "Add to Discord" button.

**How to avoid:** Trust the executed-locally verification over the doc snippet:
```python
# Source: executed locally against installed discord.py 2.7.1
b = discord.ui.Button(style=discord.ButtonStyle.link, url="https://discord.com/oauth2/authorize?...", label="Add to Discord")
b.custom_id  # None (correctly — no custom_id needed/settable for a link button)
b.url        # the URL
b.label      # "Add to Discord"
```
[VERIFIED: executed locally, 2026-07-14] This also confirms D-05's premise: a link-style button needs no `custom_id`, dispatches no interaction, and therefore needs none of Phase 7's `timeout=None` + `setup_hook` persistent-view registration. A plain `discord.ui.View()` (default `timeout=180.0`) wrapping the button is sufficient — the view exists only to carry the button on a single response, not to survive a restart.

## Code Examples

### `logic/invite.py` (new)

```python
"""Pure OAuth2 invite-URL builder (Phase 22 / INVITE-01 / D-03).

The ONLY place an invite URL is ever constructed (D-03/D-07) — cogs/invite.py
calls this and never hand-builds a query string. No discord.Client, no I/O.

Mirrors the logic/proactive.py / logic/vision.py pure-seam convention (Phase 10
D-01/D-02): deterministic, side-effect-free, keyword-only where it matters.
"""

from __future__ import annotations

import discord


def build_invite_url(
    *,
    client_id: int,
    permissions_value: int,
    scopes: tuple[str, ...] = ("bot", "applications.commands"),
) -> str:
    """Build the canonical Dexter invite URL.

    Args:
        client_id: Discord application/client ID (public by design, D-04).
        permissions_value: The pre-computed Permissions bitfield integer
            (config.INVITE_PERMISSIONS_VALUE — test-locked by D-02).
        scopes: OAuth2 scopes; defaults to discord.py's own default tuple.

    Returns:
        The literal https://discord.com/oauth2/authorize?... URL string, as
        produced by discord.utils.oauth_url() — no shorteners, no redirects
        (D-07).
    """
    return discord.utils.oauth_url(
        client_id,
        permissions=discord.Permissions(permissions_value),
        scopes=scopes,
    )
```

### `cogs/invite.py` (new — structural template: `cogs/help.py`)

```python
# Source: pattern mirrors cogs/help.py (imports, Cog subclass, app_commands.command, setup())
import discord
from discord import app_commands
from discord.ext import commands

import config
from logic.invite import build_invite_url


class InviteCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="invite", description="Get Dexter's invite link")
    async def invite_command(self, interaction: discord.Interaction) -> None:
        client_id = config.DISCORD_CLIENT_ID or self.bot.application_id  # D-04 fallback
        url = build_invite_url(client_id=client_id, permissions_value=config.INVITE_PERMISSIONS_VALUE)

        embed = discord.Embed(
            description="here. go unleash me on your own server.",  # personality: lowercase, dry, <=1 emoji
            color=0x2C76DD,
        )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(style=discord.ButtonStyle.link, url=url, label="Add to Discord"))
        await interaction.response.send_message(embed=embed, view=view)  # public — no ephemeral=True (D-05)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InviteCog(bot))
```

Note: `/invite` needs no `defer()` — `build_invite_url()` is synchronous and instant; a bare `interaction.response.send_message` is correct and matches D-05's "no cooldown, nothing to rate-limit" discretion note.

### `config.py` additions

```python
# --- Phase 22: Invite Plumbing (INVITE-01/02) ---
# Public by design — visible in every invite link ever handed out (D-04).
# 1492588698364018898 is Dexter's real, already-public application ID
# (previously hand-pasted in dexter-architecture.md's stale invite-url note).
DISCORD_CLIENT_ID = int(os.getenv("DISCORD_CLIENT_ID") or "1492588698364018898")

# D-01/D-02: least-privilege, functional-complete bitfield — test-locked,
# see tests/test_invite_logic.py::test_bitfield_excludes_dangerous_permissions.
# Recompute via discord.Permissions(**kwargs).value if this set ever changes.
INVITE_PERMISSIONS_VALUE = 309240908864  # or 3263552 if thread perms are descoped — see RESEARCH Pitfall 3
INVITE_SCOPES: tuple[str, ...] = ("bot", "applications.commands")
```

### Drift-guard test skeleton

```python
# tests/test_invite_drift_guard.py
import re
import subprocess
from pathlib import Path

import pytest

import config
from logic.invite import build_invite_url

URL_PATTERN = re.compile(r"https://discord\.com/(?:api/)?oauth2/authorize\?[^\s)\"'<>]+")
TEXT_EXTENSIONS = {".md", ".html", ".txt"}


def _repo_root() -> Path:
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True)
    return Path(out.stdout.strip())


def _tracked_doc_files(root: Path) -> list[Path]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=root, check=True)
    files = []
    for rel in out.stdout.splitlines():
        if rel.startswith(".planning/"):  # Pitfall 2: legitimate example/meta URLs live here
            continue
        p = Path(rel)
        if p.suffix in TEXT_EXTENSIONS:
            files.append(root / rel)
    return files


def test_no_doc_contains_a_drifted_invite_url():
    root = _repo_root()
    canonical = build_invite_url(
        client_id=config.DISCORD_CLIENT_ID, permissions_value=config.INVITE_PERMISSIONS_VALUE
    )
    offenders = []
    for path in _tracked_doc_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in URL_PATTERN.findall(text):
            if match.rstrip(").,") != canonical:
                offenders.append((path, match))
    assert offenders == [], f"drifted invite URL(s) found: {offenders}"


def test_drift_guard_actually_detects_a_mismatch(tmp_path, monkeypatch):
    """Positive control (per CONTEXT.md's own ask): proves the scanner isn't a no-op."""
    fake_doc = tmp_path / "fake.md"
    fake_doc.write_text("check out https://discord.com/oauth2/authorize?client_id=999&permissions=0&scope=bot")
    matches = URL_PATTERN.findall(fake_doc.read_text())
    assert matches, "scanner failed to find a URL that is definitely present"
```

Note the positive-control test uses a `tmp_path` fixture rather than a permanently-committed fixture file with a deliberately-wrong URL — avoiding ever having a second, fake, non-matching invite URL sitting in the real tracked corpus (which would itself need yet another exclusion rule).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `oauth_url()` defaulting to `bot`-only scope | Defaults to `('bot', 'applications.commands')` when `scopes` omitted | discord.py 2.0 migration | Irrelevant here since scopes are passed explicitly per D-05/discretion, but confirms explicit scopes and the omitted-default are behaviorally identical if ever simplified later |

**Deprecated/outdated:** None relevant — no discord.py invite-URL API has been deprecated between 2.3 (the requirements.txt floor) and 2.7.1 (installed).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `dexter-architecture.md:820`'s "1492588698364018898- app id" is Dexter's real, current application ID (not a rotated/stale one from an earlier bot registration) | Standard Stack, Code Examples | If the app was ever re-registered with a new client ID, `DISCORD_CLIENT_ID`'s committed default would be wrong; low-cost to verify — compare against the Discord Developer Portal or `bot.application_id` at runtime once, before locking the constant. The env override (D-04) makes this non-fatal even if wrong. |
| A2 | `/autolyrics`'s thread-creation call site (Pitfall 3) is a genuine oversight worth fixing rather than an intentionally-descoped edge case | Common Pitfalls Pitfall 3 | If descoped, `/autolyrics` continues silently no-opping on fresh servers exactly as it does today (Phase 22 wouldn't make this worse) — flagged as a recommendation, not a blocker, precisely because D-01 already established a judgment call is warranted per permission |

## Open Questions

1. **Module placement for `build_invite_url()` — RESOLVED.**
   - What we know: `logic/` already hosts 8 pure decision/derivation modules (`proactive.py`, `vision.py`, `guild_config.py`, etc.), all deterministic, no I/O, following an identical docstring convention citing the Phase 10 D-01/D-02 seam rule. `utils/` hosts mechanical helpers (`embeds.py`, `formatters.py`) that are typically discord-object-aware or side-effecting (e.g. `tasks.py::make_task`).
   - Recommendation: `logic/invite.py`. `build_invite_url()` is a pure function of primitives → string, a perfect fit for the existing `logic/` convention, and keeps discovery consistent (a future engineer looking for "where does Dexter decide X" checks `logic/` first).

2. **Tuple vs. literal-list scopes — RESOLVED.**
   - What we know: `oauth_url()`'s own default is a tuple (`('bot', 'applications.commands')`, per its docstring), and the parameter type is `Optional[Iterable[str]]` (tuple, list, or any iterable all work identically).
   - Recommendation: Pass an explicit tuple (`("bot", "applications.commands")`) as a named `config.INVITE_SCOPES` constant — matches discord.py's own internal representation and gives the planner a single named place to find/change scopes later (mirrors the `config.py`-is-authoritative convention).

3. **`bot.application_id` fallback safety — RESOLVED.**
   - What we know: `Client.application_id` is `Optional[int]`, populated "through the gateway when an event contains the data or after a call to `Client.login()`... usually after `on_connect`." [VERIFIED: installed discord.py 2.7.1 docstring] By the time any slash command (including `/invite`) can fire, the bot has necessarily completed `login()`/`connect()`, so `bot.application_id` is populated in every realistic runtime path.
   - Recommendation: `config.DISCORD_CLIENT_ID or interaction.client.application_id` is safe as the Claude's-Discretion fallback chain (committed constant first, since it's needed by the CI drift-guard which has no running bot; live fallback only for the pathological "constant somehow blanked in a fork" case).

4. **Whether to include `create_public_threads`/`send_messages_in_threads` in the bitfield — NOT resolved by research, flagged for planner/user judgment.**
   - What we know: proven code call site (Pitfall 3), computed bitfield values for both the 8-perm and 10-perm sets are provided above.
   - What's unclear: whether the user considers `/autolyrics`'s current silent-failure acceptable (status quo, zero regression) vs. worth closing now that the permission set is being formalized.
   - Recommendation: Include it (10-perm set, value `309240908864`) — costs nothing, is code-proven, and is exactly the kind of gap D-01's own "worst possible first impression" reasoning was written to catch. Surface this explicitly to the user during planning/discuss rather than silently picking one.

## Environment Availability

Skipped — this phase has no new external dependencies (no new packages, no new services, no new CLI tools). `discord.py` is already installed and verified (2.7.1).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (installed, `requirements.txt`); 1132 tests currently collected, 0 config file beyond `[tool.ruff]` in `pyproject.toml` — pytest uses defaults (no `pytest.ini`/`[tool.pytest.ini_options]` section found) |
| Config file | none — pytest runs on defaults; `tests/conftest.py` exists for shared fixtures (pgvector codec, DB fixtures) |
| Quick run command | `pytest tests/test_invite_logic.py tests/test_invite_drift_guard.py -q` |
| Full suite command | `pytest -q` (CI-equivalent: `.github/workflows/ci.yml` runs `pytest -q` with `TEST_DATABASE_URL` set to a pgvector service container, no other secrets) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INVITE-01 (least-privilege bitfield) | Bitfield excludes `administrator`/`manage_guild`/`manage_roles`/`manage_channels`/`ban_members`/`kick_members`; equals the exact locked value | unit | `pytest tests/test_invite_logic.py::test_bitfield_excludes_dangerous_permissions -x` | ❌ Wave 0 |
| INVITE-01 (scopes) | `build_invite_url()` output contains `scope=bot+applications.commands` | unit | `pytest tests/test_invite_logic.py::test_url_contains_expected_scopes -x` | ❌ Wave 0 |
| INVITE-02 (single source of truth / SC-3) | Every git-tracked, non-`.planning/` text doc's OAuth2 URL literally equals `build_invite_url()`'s output | unit (repo-introspection) | `pytest tests/test_invite_drift_guard.py::test_no_doc_contains_a_drifted_invite_url -x` | ❌ Wave 0 |
| INVITE-02 (drift-guard isn't a no-op) | The scanner regex actually finds a URL when one is present (positive control) | unit | `pytest tests/test_invite_drift_guard.py::test_drift_guard_actually_detects_a_mismatch -x` | ❌ Wave 0 |
| SC-2 (`/invite` returns a working link) | `/invite` command exists, DM-allowed, returns embed+link button whose URL == `build_invite_url()`'s output | unit (cog-level, mock interaction) | `pytest tests/test_invite_cog.py::test_invite_command_sends_correct_url -x` | ❌ Wave 0 |
| SC-2 (live add-to-server proof) | The link, when clicked, actually adds Dexter to a real guild the invoker manages | manual | — | Manual-Only (see below) |
| SC-3 (Dev Portal copy matches) | The Developer Portal install-link field, pasted by hand, equals `/invite`'s output byte-for-byte | manual | — | Manual-Only — **D-08, lands in `22-HUMAN-UAT.md`** |

### Sampling Rate

- **Per task commit:** `pytest tests/test_invite_logic.py tests/test_invite_drift_guard.py tests/test_invite_cog.py -q`
- **Per wave merge:** `pytest -q` (full suite — cheap, ~1132 tests, no live network calls in this phase's own tests)
- **Phase gate:** Full suite green before `/gsd-verify-work`; CI (`.github/workflows/ci.yml`) re-runs the same full suite with zero secrets, which the drift-guard and bitfield tests are specifically designed to pass under (D-04's entire rationale).

### Wave 0 Gaps

- [ ] `tests/test_invite_logic.py` — covers INVITE-01 (bitfield lock + URL/scope shape)
- [ ] `tests/test_invite_drift_guard.py` — covers INVITE-02/SC-3 (drift guard + positive control)
- [ ] `tests/test_invite_cog.py` — covers SC-2 (cog-level, mocked `interaction.response.send_message`)
- [ ] No new fixtures needed in `conftest.py` — this phase touches no DB, no Gemini, no voice; existing bare `pytest` fixtures suffice

**Note on `22-HUMAN-UAT.md`:** D-08 (Developer Portal paste-and-compare) is inherently a human, browser-driven step against a live third-party UI — it cannot be automated in CI. This is the same acknowledged-deferred pattern used since Phase 11; record it there at phase close, not as a code gap.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | no | `/invite` requires no new auth path — reuses the existing `DexterCommandTree.interaction_check` choke point unchanged |
| V3 Session Management | no | No session state introduced |
| V4 Access Control | yes | Least-privilege OAuth2 scope/permission request IS an access-control artifact — this is INVITE-01's entire point. Standard control: explicit `Permissions(**kwargs)` bitfield, test-locked negative assertion (D-02) against `administrator`/`manage_guild`/`manage_roles`/`manage_channels`/`ban_members`/`kick_members` |
| V5 Input Validation | no | `/invite` takes no user input |
| V6 Cryptography | no | No cryptographic operations in this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Over-privileged bot invite (a bot requesting `administrator` "just in case") | Elevation of Privilege | Explicit, minimal `Permissions()` bitfield; D-02's negative-assertion test makes a future silent escalation (e.g. someone adding `manage_guild` for a new feature without updating the test) fail CI instead of shipping unnoticed |
| Invite-link drift (public doc promotes a stale/over-privileged link while the "real" one is tighter, or vice versa) | Tampering (of the promoted artifact, not the code) | D-03's git-doc drift-guard — structural, not discipline-based |
| **Out-of-band finding: committed bot token in `dexter-architecture.md`** | Information Disclosure | Not a Phase-22-introduced risk, but discovered while researching this phase's file-scan target. See Pitfall 0 — token rotation recommended immediately, independent of this phase's requirements |

## Sources

### Primary (HIGH confidence)

- `/websites/discordpy_readthedocs_io_en` (Context7) — `oauth_url()` default-scopes migration note, `Permissions`/`app_commands.default_permissions` semantics, thread permission requirements (`create_public_threads`, `send_messages_in_threads`), user-installable-apps (`allowed_installs`/`guild_install`/`user_install`) as a separate mechanism from `oauth_url()`
- `/rapptz/discord.py` (Context7) — `TextChannel.create_thread`/`archived_threads` permission requirements, `app_commands.default_permissions` decorator source
- `raw.githubusercontent.com/Rapptz/discord.py/v2.7.1/discord/utils.py` — exact `oauth_url()` signature and docstring, fetched directly (version-pinned to the installed release)
- `raw.githubusercontent.com/Rapptz/discord.py/v2.7.1/discord/permissions.py` — full enumeration of `@flag_value`/`@permission_alias` names
- Local execution against the installed `discord.py==2.7.1` package (`python3 -c "import discord; ..."`) — verified `Permissions(**kwargs).value` for both the 8- and 10-permission sets, `Client.application_id` docstring, `discord.ui.Button` construction with `url=`+`label=` combined, `inspect.signature(discord.utils.oauth_url)`
- Direct repo inspection (`git ls-files`, `grep`, `Read`) — `dexter-architecture.md`'s stale invite URL and adjacent secrets, `cogs/music.py`'s `create_thread`/`thread.send` call sites, `config.py`/`cogs/help.py`/`cogs/admin.py`/`logic/guild_config.py`/`logic/proactive.py`/`bot.py`/`.github/workflows/ci.yml` as pattern sources

### Secondary (MEDIUM confidence)

None — every claim above was either executed locally against the actual installed package/repo, or sourced from official discord.py documentation/source via Context7/GitHub raw fetch.

### Tertiary (LOW confidence)

None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies, exact installed version confirmed
- Architecture: HIGH — pattern directly mirrors 8 existing `logic/` modules already in the codebase
- discord.py API surface (`oauth_url`, `Permissions`, `ui.Button`): HIGH — verified by direct execution against the installed 2.7.1 package, not training-data recall
- Pitfalls (missed permission call site, stale doc URL, committed secret): HIGH — all found by direct repo grep/read, not inference
- CI compatibility (D-04's no-secrets constraint): HIGH — `.github/workflows/ci.yml` inspected directly; confirms zero secrets, matches D-04's premise exactly

**Research date:** 2026-07-14
**Valid until:** 30 days (stable API surface; discord.py 2.7.1 is the pinned/installed version and unlikely to change mid-milestone) — but the `dexter-architecture.md` secret-leak finding (Pitfall 0) should be acted on immediately, not treated as having a 30-day validity window.
