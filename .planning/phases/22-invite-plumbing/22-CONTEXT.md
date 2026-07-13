# Phase 22: Invite Plumbing - Context

**Gathered:** 2026-07-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Anyone can invite Dexter to their own server via a correct, least-privilege OAuth2 invite
link — with **one** source of truth, not hand-maintained duplicates.

**Delivers exactly two requirements:**
- **INVITE-01** — a least-privilege OAuth2 invite URL exists (explicit `Permissions()` bitfield,
  no Administrator, no Manage Server/Roles) with `bot` + `applications.commands` scopes.
- **INVITE-02** — an in-bot `/invite` command returns the live invite URL as the single source
  of truth.

**Not in this phase:** the README/landing-page *content* that promotes the link (Phase 23 /
PORT-01, PORT-03 own that). Phase 22 ships the URL, the command, and the machinery that makes
drift impossible when Phase 23 pastes it in. Runtime permission-gap self-diagnostics are
explicitly deferred (see Deferred Ideas).

</domain>

<decisions>
## Implementation Decisions

### Permission bitfield (INVITE-01)

- **D-01: Functional-complete, not bare-minimum.** The bitfield requests exactly the
  permissions the code *provably* uses — nothing aspirational, nothing admin-adjacent. Verified
  against the codebase during discussion:

  | Permission | Why — proven by code |
  |---|---|
  | `view_channel` | prerequisite for every ambient/message surface |
  | `send_messages` | every cog |
  | `embed_links` | 78 `embed=` sends across `cogs/*.py` |
  | `attach_files` | `cogs/imagine.py:69-74` — `discord.File` upload |
  | `add_reactions` | `cogs/events.py:345,355,379` — 👀 / 🫡 / 😐 reactions |
  | `read_message_history` | `cogs/music.py:833` `channel.fetch_message` (now-playing edit); reply-anchored proactive callbacks (Phase 16) |
  | `connect` | `cogs/music.py:526` `member.voice.channel.connect()` |
  | `speak` | voice playback |

  Rejected: bare-minimum (music+chat only), which would let `/imagine` attachments, emoji
  reactions, and now-playing edits *silently fail* on a fresh server — the worst possible first
  impression for a portfolio piece. Also rejected: a forward-looking buffer
  (`send_messages_in_threads`, `use_external_emojis`) — nothing uses them today and they can't be
  justified from the code. Grep confirmed **zero** uses of `manage_messages` or external emojis
  anywhere in the repo.

- **D-02: The bitfield is test-locked with a negative assertion.** A pytest asserts the exact
  bitfield value AND that `administrator`, `manage_guild`, `manage_roles`, `manage_channels`,
  `ban_members`, `kick_members` are all `False`. INVITE-01's "no Administrator" claim becomes a
  regression-locked contract rather than a comment — a future phase cannot quietly add
  `manage_guild`. Follows the mock-free pure-logic test discipline established in Phase 10.

### Single source of truth (INVITE-02 / SC-3)

- **D-03: One pure `build_invite_url()` + a CI drift-guard test.** A single pure builder
  (a `logic/`-style seam, mock-free, keyword-only per the Phase 10 convention) is the **only**
  place an invite URL is ever constructed. `/invite` calls it. A pytest then walks `git ls-files`
  for text docs, regexes any `discord.com/…oauth2/authorize…` URL it finds, and asserts each one
  equals `build_invite_url()`'s output.

  **This test passes vacuously today** (no doc contains a link yet) and **automatically starts
  enforcing the moment Phase 23 pastes a link into the README or `/site`**. Drift becomes
  structurally impossible instead of merely discouraged. Rejected: a generator script with no
  guard (relies on discipline), and "docs just say run `/invite`" (fails SC-2/PORT-01 — a
  recruiter needs a clickable button, not an instruction to already have the bot).

- **D-07: The promoted link must be the literal OAuth2 URL — no shorteners, no vanity
  redirects.** This is the implicit policy D-03's literal-match test encodes, and it is
  deliberate: a redirect is exactly the untestable indirection SC-3 exists to prevent. The
  drift-guard scans **git-tracked files** (not a hardcoded file list), so it auto-covers whatever
  new docs Phase 23 creates — the guarantee doesn't decay as the doc surface grows. Rejected:
  resolving a redirect in-test (needs network in CI, couples the gate to an external service —
  more moving parts than the whole feature).

### Client ID sourcing

- **D-04: Committed public constant in `config.py`, with a `DISCORD_CLIENT_ID` env override.**
  A Discord client ID is **public by design** — it is visible in every invite link ever handed
  out — so committing it leaks nothing. This is load-bearing, not cosmetic:

  - The **Phase 18 CI gate runs on GitHub Actions with no `.env` and no secrets.** If the client
    ID came only from env, the D-03 drift-guard test would have to skip in CI — which quietly
    guts the entire guarantee.
  - Phase 23's static README/landing-page generation runs where no bot process exists and no env
    is set.

  The env override keeps the repo fork-friendly (someone cloning the portfolio piece points it at
  their own app). Follows `config.py`'s established `os.getenv(...) or default` idiom.

### `/invite` command surface

- **D-05: Public reply — embed + link-style button.** A public (non-ephemeral) embed carrying
  Dexter's dry one-liner, plus a `discord.ui.Button(style=link, url=...)` "Add to Discord".
  Public is the *point* — someone else in the channel sees it and can grab it too; an ephemeral
  reply would hide the one command whose entire purpose is spreading the bot. A link-style button
  needs no `custom_id` and no timeout handling, so it sidesteps the persistent-view registration
  requirements of Phase 7's `NowPlayingView` entirely.

- **D-06: DM-allowed, in its own `cogs/invite.py`, listed under Utility in `/help`.** DM support
  needs **zero new plumbing** — verified during discussion that
  `bot.py::DexterCommandTree.interaction_check` already computes `has_guild` and
  `logic/guild_config.py::decide_interaction_allowed` models `has_guild=False` as a first-class
  case. Its own cog matches the one-concern-per-cog convention (`help.py`, `memory.py`) and keeps
  INVITE-02 traceable to a single file.

### Developer Portal (the third copy of the link)

- **D-08: Documented human step + a HUMAN-UAT item.** The Discord Developer Portal's install-link
  field is set by hand in a web UI — it is genuinely not code, and pretending otherwise would be
  dishonest. Phase 22 ships the code and records a human-verifiable step: paste the generated URL
  into the Dev Portal install-link field, then confirm `/invite`'s link matches it byte-for-byte.
  Lands in `22-HUMAN-UAT.md` — the same acknowledged-deferred pattern every phase since 11 has
  used. Rejected: declaring it out of scope, which would leave SC-3's "publicly-promoted link"
  with a third unguarded copy.

### Claude's Discretion

- **`/invite` falls back to `bot.application_id`** if the committed client-ID constant is somehow
  unset (the fork case where someone clones the repo but sets no env). Runtime-only fallback —
  the drift-guard test still relies on the constant.
- **No cooldown on `/invite`.** It returns a static string; there is nothing to rate-limit.
  (Deliberate departure from `/help`'s 5s cooldown — noted so a reviewer doesn't flag it.)
- Exact module placement of `build_invite_url()` (`logic/invite.py` vs a `utils/` home) and the
  precise embed copy are the planner's call, subject to D-03's "only place a URL is constructed"
  constraint.
- Whether the `bot` + `applications.commands` scopes are passed to `discord.utils.oauth_url()`
  as a tuple or built literally — planner's call; the researcher should confirm the current
  discord.py 2.7.1 signature and whether `integration_type` needs to be explicit now that
  user-install apps exist.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase requirements & scope
- `.planning/ROADMAP.md` §"Phase 22: Invite Plumbing" — goal, 3 success criteria, dependency on
  Phase 20 (abuse-mitigation story must be real before promoting the invite)
- `.planning/REQUIREMENTS.md` §"Invite Plumbing (INVITE)" — INVITE-01, INVITE-02 verbatim
- `.planning/ROADMAP.md` §"Phase 23: Portfolio Surface & CI/CD" — the *consumer* of this phase's
  URL (PORT-01 "Add to Discord" button, PORT-03 README invite link). Read it to understand what
  the D-03 drift-guard must protect.

### Code seams this phase touches or depends on
- `config.py` — the `os.getenv(...) or default` idiom D-04 follows; `OWNER_ID:86`,
  `DEXTER_CHANNEL_ID:57` are the closest analogs
- `bot.py:79-120` — `DexterCommandTree.interaction_check`, the Phase 20 choke point `/invite`
  inherits for free; already handles the DM (`has_guild=False`) case
- `logic/guild_config.py:197+` — `decide_interaction_allowed`, the pure predicate that models
  DMs; confirms D-06 needs no new plumbing
- `cogs/help.py` — the smallest existing cog; the structural template for `cogs/invite.py`, and
  the file that gains the `/invite` Utility entry
- `cogs/ops.py:403` — the `default_permissions` precedent: **UI hint ONLY**, never the real
  check (Phase 20 D-06). Same discipline applies to anything `/invite` declares.
- `.github/workflows/` (Phase 18 CI gate) — runs pytest + Ruff with **no secrets**; this is the
  constraint that forces D-04

### Project-level constraints
- `CLAUDE.md` §"Critical Rules" + §"Implementation Gotchas" — the personality rules (lowercase,
  one emoji max, dry) that govern the `/invite` embed copy
- `.planning/PROJECT.md` §"Key Decisions" — the pure-`logic/`-seam decision (Phase 10) that
  `build_invite_url()` follows

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`cogs/help.py`** — a 60-line single-command cog. The direct structural template for
  `cogs/invite.py` (imports, `commands.Cog` subclass, `@app_commands.command`, `async def setup`).
- **`discord.utils.oauth_url()`** — the stdlib-of-discord.py URL builder. `build_invite_url()`
  should wrap it, not hand-concatenate a query string.
- **`discord.ui.Button(style=discord.ButtonStyle.link, url=...)`** — a link button carries no
  `custom_id` and fires no interaction, so it needs none of the Phase 7 persistent-view
  registration (`timeout=None` + stable `custom_id` in `setup_hook`).
- **`bot.application_id`** — available post-login; the discretionary fallback for D-04.

### Established Patterns
- **Pure `logic/` seam (Phase 10 D-02):** decision/derivation logic lives in a pure, mock-free,
  keyword-only module; Discord glue dispatches on its return value and never re-derives it.
  `build_invite_url()` is a textbook fit — a pure function of (client_id, permissions, scopes).
- **`config.py` is the single authoritative settings file.** New knobs go there, nowhere else.
- **`default_permissions` is a UI hint, never an authorization check** (Phase 20 D-06,
  `cogs/ops.py:403`).
- **Test discipline:** mock-free unit tests over pure logic; named scar regressions for anything
  that has bitten before. D-02 and D-03 are both this kind of test.

### Integration Points
- `bot.py` cog-load list — `cogs/invite.py` must be registered alongside the existing cogs.
- `cogs/help.py` — the `/help` Utility section gains an `/invite` line (D-06).
- `.github/workflows/` — the D-03 drift-guard is an ordinary pytest, so the Phase 18 CI gate
  picks it up with **no workflow changes** (this is why D-04's no-secrets property matters).
- **Phase 23 hand-off:** Phase 23 pastes `build_invite_url()`'s output into the README and
  `/site`. The moment it does, the D-03 test starts enforcing SC-3. Phase 23 must **not**
  introduce a second URL constructor or a redirect (D-07).

</code_context>

<specifics>
## Specific Ideas

- The exact 8-permission set is enumerated in D-01 with a code citation per permission. The
  researcher should **re-verify each one against the live code** rather than trusting this table —
  and should flag any permission-requiring call site the discussion scan missed (the scan covered
  reactions, file sends, voice connect, message-history fetch, and embeds).
- The drift-guard's regex must match the URL *wherever* it appears — inside a Markdown link, an
  HTML `href`, or bare — since Phase 23 will use all three forms.
- `/invite`'s embed copy must obey Dexter's personality rules: lowercase, dry, at most one emoji.

</specifics>

<deferred>
## Deferred Ideas

- **Runtime permission-gap self-diagnostic** — if a server admin unticks e.g. `attach_files` at
  invite time, Dexter has no way to notice or report it. A `/permcheck` command, or an
  on-guild-join comparison of granted-vs-requested permissions that DMs the admin what's missing,
  is genuinely useful for a public bot — but it is a **new capability**, not a clarification of
  INVITE-01/02, and it would creep into Phase 19's onboarding surface. Noted for the backlog;
  **not** built in Phase 22.
- **Vanity/short invite link** (e.g. a custom domain redirect) — explicitly ruled out by D-07 for
  this milestone, because it defeats the literal-match drift guard. If a vanity domain is ever
  wanted, the guard needs redesigning first.

</deferred>

---

*Phase: 22-Invite Plumbing*
*Context gathered: 2026-07-14*
