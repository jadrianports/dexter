# Project Research Summary

**Project:** Dexter — v1.4 "Open House"
**Domain:** Retrofitting multi-tenancy + a public invite/onboarding/kill-switch/portfolio layer onto an existing, code-complete single-community discord.py bot
**Researched:** 2026-07-10
**Confidence:** HIGH

## Executive Summary

Dexter is a code-complete, personality-driven Discord music/AI bot (v1.0–v1.3 shipped) that was built and hardened for exactly one community. v1.4 "Open House" does not add a new capability domain — it retrofits the existing bot to be safely and pleasantly invitable to arbitrary servers at modest scale (single-digit to low-dozens of guilds, explicitly not pursuing Discord's 100-guild verification wall). All four research tracks converge on the same finding: **the single-guild coupling is the one foundational refactor everything else depends on**, and it is structurally worse than it looks — it is not one hardcoded env var, but a duplicated ambient-channel fallback resolver (byte-identical copies in `bot.py` and `cogs/events.py`) *plus* two separate bare-equality gates (`message.channel.id == config.DEXTER_CHANNEL_ID`) in `events.py`'s proactive-callback and vision-roast dispatch. A plan that only adds a `guild_config` table without touching all five call sites will ship a bot that looks multi-tenant but silently keeps two ambient surfaces dead everywhere except the owner's original guild.

The recommended approach requires zero new dependencies and zero new infrastructure: one new `guild_config` Postgres table (mirroring the existing `guild_jams`/`user_favorites` idiom exactly), discord.py's already-installed APIs (`oauth_url`, `on_guild_join`/`on_guild_remove`, `Guild.leave()`, `CommandTree.interaction_check`), and a plain static HTML/CSS page on GitHub Pages for the portfolio surface. The build order that emerges from all four documents is consistent: consolidate the resolver into one per-guild-aware seam first (config table + pure `logic/guild_config.py` + `services/guild_config.py` cache), then layer onboarding (`/setup`, `on_guild_join`, default-OFF ambient until configured) on top of it, then the owner control plane (list/silence/leave, gated by `bot.is_owner()` inline — never `default_permissions` alone), then invite plumbing (independent, low-risk), and finally the portfolio surface (which needs a real second-guild proof to be honest, so it must come last).

The key risks are: (1) a TOCTOU-shaped kill-switch bug — Dexter has already suffered this exact bug class once (Phase 16's daily-cap race, fixed via reserve-before-await) and the same shape recurs at guild scope unless the silence check is the first line of every ambient handler and re-checked immediately before the final send; (2) the shared 15 RPM Gemini limiter has zero guild dimension, so one chatty guild can silently starve every other guild's AI features into template-fallback — mitigate with observability, not a full quota system; (3) cross-guild RAG memory recall (`user_id`-only by design, correct for one community, a privacy leak once strangers share the bot) is an explicit product decision to surface in the roadmap discussion, not a silent code change bundled into the config work; and (4) full-savage personality + unprompted vision-roasting of strangers' photos is a real Discord Community Guidelines exposure whose only stated mitigation (owner kill-switch) is reactive, not preventive — this should be disclosed honestly in the portfolio case study as a deliberate, named tradeoff rather than solved or hidden.

## Key Findings

### Recommended Stack

Every capability needed this milestone is already present in the installed stack — discord.py ≥2.3 (2.7.1 current on PyPI) covers `oauth_url()`, `on_guild_join`/`on_guild_remove`, `Guild.leave()`, and `CommandTree.interaction_check`/`tree_cls`; asyncpg 0.31.0 on the existing Neon pool covers the new table. No new libraries, no invite-tracking packages, no web-dashboard framework, no JS build pipeline.

**Core technologies:**
- `guild_config` Postgres table (`guild_id TEXT PRIMARY KEY`, `ambient_channel_id`, `is_blocked`/`silenced`, `joined_at`, `updated_at`) — mirrors `guild_jams`/`resolution_cache` idiom exactly, added to `SCHEMA_SQL`, no ORM/migration tool
- `discord.utils.oauth_url()` + Developer Portal "Install Link" (Discord Provided Link) — the two-track invite approach: Portal-hosted link for the public button (auto-reflects permission changes), in-code `oauth_url()` for an owner-only `/invite` convenience command
- `app_commands.CommandTree` subclass overriding `interaction_check`, wired via `tree_cls` on `AutoShardedBot` — the single command-side block choke point (exact kwarg signature should be double-checked against the installed discord.py version — MEDIUM confidence on that one detail only)
- Plain static HTML/CSS on GitHub Pages, served from a new `/site` directory (not `/docs`, which already holds internal ops runbooks) via a GitHub Actions Pages deploy

### Expected Features

**Must have (table stakes):**
- `guild_config`/`guild_settings` table + per-guild ambient-channel resolver (the "big rock" — nothing else is possible without it)
- Admin-gated `/setup` (channel picker) — `has_permissions(manage_guild=True)` as an inline runtime check, `default_permissions` only as a UI hint
- `on_guild_join` welcome/setup-nudge message, wrapped in try/except (no handler exists today — total silence on join otherwise)
- Pre-`/setup` graceful default: core commands (`/play`, `/ask`, etc.) work immediately; ambient/unprompted surfaces (roasts, proactive callbacks, vision, idle messages, startup message) stay silent until `/setup` runs — default OFF, not a fallback-chain guess
- Per-guild ambient/vision toggle (silence), owner-only list/silence/force-leave + a persisted blacklist so force-leave isn't trivially bypassed by re-invite — this is the stated abuse mitigation, not optional
- Least-privilege OAuth2 invite URL (explicit `Permissions()`, no Administrator, no Manage Server/Roles)
- README rewrite: tagline, feature list, tech-stack badges, working invite link, architecture summary

**Should have (differentiators):**
- Owner join/leave push notification to the existing `ERROR_LOG_CHANNEL_ID` channel (zero new infra)
- Dynamic in-bot `/invite` command as a single source of truth vs. a hardcoded README link
- Channel-select UI component for `/setup` instead of a raw argument
- Standalone static landing page + a short demo GIF of the personality landing

**Defer (v2+ / explicitly out of scope):**
- Full web-based per-guild settings dashboard (conflicts with the no-always-on-host constraint; already parked since Phase 4)
- Per-guild persona intensity dial (directly conflicts with the locked "full-savage everywhere" decision)
- Per-channel (not per-guild) ambient config, automated abuse-detection heuristics, i18n, premium tiers, bot-list submissions, multi-owner RBAC, user-installable app context — all rejected as over-engineering for stated modest scale or as conflicting with locked decisions

### Architecture Approach

This is a retrofit, not greenfield design: consolidate the two duplicated fallback-chain resolvers and the two bare-equality gates into one `GuildConfigService` (in-memory full-table cache loaded at boot, mirroring the existing `bot.server_states`/`MessageBuffer` pattern — never a per-event DB round-trip against Neon), backed by one pure `logic/guild_config.py::resolve_ambient_channel_id` function that folds the block/silence check in as its first branch. This makes the block check a side effect of removing duplication rather than a bolted-on third check.

**Major components:**
1. `guild_config` table + `logic/guild_config.py` (pure resolver/gate) + `services/guild_config.py` (cache + DB glue) — the foundation seam, wired in `bot.py:_initialize_once` alongside existing services
2. `cogs/admin.py` (new cog, following the Phase 15 `cogs/memory.py` precedent of "new cross-cutting concern gets its own cog") — `on_guild_join`/`on_guild_remove` lifecycle, `/setup`, and owner-only `/admin servers|block|unblock|leave`
3. `DexterCommandTree(app_commands.CommandTree)` overriding `interaction_check` — the one command-side block choke point covering every slash command with no per-cog checks to remember
4. `/site` static portfolio directory (separate from `/docs`'s internal ops content) — deployed via GitHub Actions Pages, linking back to the README case study rather than duplicating it

`OWNER_ID` and `ERROR_LOG_CHANNEL_ID` are correctly global today (owner identity, cross-guild private ops channel) and must **stay** global — do not fold them into `guild_config`.

### Critical Pitfalls

1. **Duplicated ambient-channel resolver + two hardcoded-equality gates** — consolidate `bot.py::_resolve_dexter_channel` and `events.py::_get_ambient_channel` into one shared function FIRST, and swap the proactive/vision `on_message` equality checks to route through the same resolver; write an import-identity regression test so they can't re-fork.
2. **Kill-switch TOCTOU** (same shape as the fixed Phase 16 daily-cap bug) — check "is this guild silenced?" before any `await` in every ambient entry point and re-check immediately before the final send; push-invalidate the cache on `/admin block`/`leave`, never rely on a poll interval. Force-leave must mirror the existing `clear_persisted()` teardown discipline (bump `_play_generation`, clear queue/voice state) or ghost state resurrects on re-invite.
3. **`app_commands.default_permissions` is a Discord-side UI hint, not an enforced check** (Context7-confirmed: no error handler fires, a guild admin can reconfigure it, and it silently does nothing on subcommands) — every new admin/owner command needs an inline `bot.is_owner()` or `guild_permissions.manage_guild` check as the real gate, reusing the exact pattern already in `cogs/ops.py`'s `/stats`.
4. **Cross-guild RAG memory recall is `user_id`-only by design** — correct for one community, a real privacy/embarrassment surface once strangers share the bot (a `/roast` in a new public server can surface a fact from the user's home guild). This is an explicit product decision to record (Option A: disclose + rely on existing `/memory forget`; Option B: per-user cross-guild-sharing opt-in), not a silent scope-creep bundled into the config work.
5. **Ambient behavior must default OFF until `/setup` runs** — the existing fallback chain (system channel → first writable) means roasts/vision-roasts of strangers can fire in an arbitrary channel within minutes of an uninvited-feeling invite, which is precisely the abuse surface the milestone's kill-switch is meant to mitigate, except reactively and after the fact.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Per-Guild Config Foundation
**Rationale:** Every other item in this milestone reads from this seam; research unanimously flags it as the single blocking dependency, and it is also where the resolver-duplication fix (Pitfall 1) must land to avoid doing the refactor twice.
**Delivers:** `guild_config` schema (SCHEMA_SQL addition), `logic/guild_config.py` pure resolver (folds in the block/silence check), `services/guild_config.py` cache service wired in `bot.py:_initialize_once`, consolidation of `bot.py::_resolve_dexter_channel` + `events.py::_get_ambient_channel` into one call, migration seed from the existing `config.DEXTER_CHANNEL_ID` for the owner's home guild, and a per-guild "configured" flag defaulting to False (ambient suppressed until `/setup`).
**Addresses:** `guild_settings` table + resolver (FEATURES P1); default-OFF ambient (Pitfall 7).
**Avoids:** Pitfall 1 (duplicated resolver), Pitfall 7 (pre-setup ambient firing).

### Phase 2: Onboarding & Admin Setup
**Rationale:** Depends only on Phase 1; delivers the actual "just works" first-run experience and is the natural pairing of `on_guild_join` + `/setup` (each makes the other discoverable).
**Delivers:** `on_guild_join` welcome/nudge message (try/except-wrapped, reusing the Phase 1 resolver for its best-guess channel), `on_guild_remove` no-op-by-design handler, admin-gated `/setup` (`has_permissions(manage_guild=True)` inline check + `default_permissions` hint), per-guild ambient/vision toggle exposed via `/setup` or a subcommand.
**Uses:** `services/guild_config.py` from Phase 1.
**Implements:** the "configured gate" data flow from ARCHITECTURE §3.

### Phase 3: Owner Control Plane (Kill-Switch)
**Rationale:** Depends on Phase 1's cache; can build in parallel with Phase 2 in principle but sequenced after onboarding since it's the "reactive" half of safety (Phase 2 is the "preventive" half via default-OFF).
**Delivers:** new `cogs/admin.py` owner commands (`/admin servers|block|unblock|leave`, inline `bot.is_owner()` check, never `default_permissions` alone), persisted blacklist (re-invite-proofing via `on_guild_join` block-check-first), `DexterCommandTree.interaction_check` as the command-side block choke point, force-leave teardown discipline (mirror `clear_persisted()`), and the silence-check-before-every-await / re-check-before-send invariant.
**Implements:** ARCHITECTURE §2.2/§2.3 (the two mechanically-necessary choke points).
**Avoids:** Pitfall 3 (`default_permissions` isn't enforcement), Pitfall 5 (kill-switch TOCTOU + ghost state).

### Phase 4: Invite Plumbing
**Rationale:** Low architectural risk, no code dependency on Phases 1–3, but sequenced after the control plane exists so the abuse-mitigation story is real before actively promoting the invite link.
**Delivers:** enumerated least-privilege `Permissions()` in `config.py`, Developer Portal Install Link configured (Discord Provided Link for the public button), optional in-bot `/invite` command via `discord.utils.oauth_url()`.
**Uses:** discord.py's already-installed `oauth_url()` default `scopes=('bot','applications.commands')`.

### Phase 5: Portfolio Surface
**Rationale:** Sequenced last because a landing page or README claiming "invite me to any server" is not credible without having actually walked a real second guild through `/setup`, toggles, and the kill-switch — this phase needs the proof, not just the code.
**Delivers:** `/site` static landing page (GitHub Pages via Actions, separate from `/docs`), README rewrite (tagline, feature list, badges, architecture summary, working invite link), explicit documented scope boundaries (100-guild verification wall, on-demand hosting UX caveat, the full-savage/reactive-kill-switch tradeoff stated honestly rather than hidden). Also delivers an explicit product decision + disclosure on cross-guild memory recall scope (Pitfall 4/Pitfall 3 in PITFALLS.md), recorded even if the resolution is "leave as-is, document it" — must not be silently skipped.

### Phase Ordering Rationale

- Phases 1→2→3 are strictly dependency-ordered (config seam blocks everything); Phases 2 and 3 could theoretically run in parallel since both depend only on Phase 1, but sequencing onboarding first establishes the default-OFF safety net before the kill-switch commands even matter.
- Phase 4 (invite plumbing) and the bulk of Phase 5 (static page scaffolding) have no code dependency on 1–3 and could start earlier, but finalizing/publishing them before the control plane exists would mean actively promoting invites to unknown servers without the stated abuse mitigation in place — a reputational and correctness risk research flags explicitly.
- The cross-guild memory decision (Pitfall 3/4) is deliberately NOT its own phase — it's a decision-point that should be resolved during Phase 1 or Phase 5 discussion (a `discuss-phase`-style checkpoint), not a silent code change; whichever phase touches `MemoryService.recall()` call sites should carry the explicit decision record.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (Owner Control Plane):** the exact `tree_cls` constructor kwarg name/signature on `AutoShardedBot` for `CommandTree.interaction_check` is MEDIUM confidence per STACK/ARCHITECTURE research — verify against the installed discord.py version before implementation.
- **Phase 1 or Phase 5 (cross-guild memory decision):** this is a genuine open product decision (Option A vs B in PITFALLS.md Pitfall 3), not a research gap — flag for an explicit `discuss-phase` checkpoint rather than research-phase.

Phases with standard patterns (skip research-phase):
- **Phase 2 (Onboarding):** `on_guild_join`/`on_guild_remove` and permission-check patterns are HIGH-confidence, Context7-verified, and already have an in-codebase precedent (`cogs/ops.py`'s `/stats` inline owner-check).
- **Phase 4 (Invite Plumbing):** `oauth_url()` signature and Developer Portal mechanism are HIGH-confidence, well-documented, zero ambiguity.
- **Phase 5 (Portfolio Surface):** plain static HTML/CSS + GitHub Pages is a zero-ambiguity, zero-dependency choice per STACK.md.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Every recommendation is either an already-installed discord.py API (Context7-verified) or a Postgres schema addition matching the exact existing idiom; only the `tree_cls` kwarg signature is flagged MEDIUM |
| Features | HIGH for discord.py mechanics (Context7-verified); MEDIUM for ecosystem conventions (WebSearch, cross-checked against multiple bot-dashboard/portfolio-README sources) |
| Architecture | HIGH — every claim is grounded in specific file/function reads from the actual codebase (`bot.py`, `cogs/events.py`, `services/memory.py`, `cogs/ops.py`), not generic pattern advice |
| Pitfalls | HIGH for codebase-verified pitfalls (resolver duplication, rate limiter, memory scoping, TOCTOU precedent); MEDIUM on Discord platform policy specifics (100-guild wall, 10k-user intent threshold — summarized via search snippets, one direct fetch 403'd) |

**Overall confidence:** HIGH

### Gaps to Address

- **`tree_cls` kwarg name/signature on `AutoShardedBot`** — verify against the installed discord.py version (2.3+ installed, 2.7.1 current) at implementation time in Phase 3; do not assume the Context7-cited pattern's exact constructor kwarg without a quick doc check.
- **Cross-guild RAG memory privacy (Pitfall 3/4)** — deliberately left as an open decision by all four research tracks; the roadmap should surface this explicitly (e.g., in a Phase 1 or Phase 5 `discuss-phase` checkpoint) rather than let it default silently to "no change." Whichever option is chosen touches 4+ call sites (`/ask`, `/roast`, ambient roasts, proactive callbacks) and should be implemented in the same phase that edits `MemoryService.recall()`.
- **Per-guild Gemini rate-limiter fairness** — research recommends observability-only (log `guild_id` per `acquire()` call, surface in `/admin servers`) rather than a real per-guild quota, given "modest scale" framing; if the milestone timeline allows, a soft per-guild ceiling on priority-2 (background) calls only is optional polish, not required — flag as a documented known-limitation if deferred.
- **Discord Developer Policy specifics (100-guild verification wall, 10k-user privileged-intent threshold)** — sourced via WebSearch snippets, one direct fetch 403'd; MEDIUM confidence overall but cross-checked across two independent sources agreeing on both figures. No code changes needed this milestone — document as an explicit, honest scope boundary in the Phase 5 README/case-study.

## Sources

### Primary (HIGH confidence)
- Context7 `/rapptz/discord.py` — `discord.utils.oauth_url` signature/default-scopes, `on_guild_join`/`on_guild_remove` event contracts, `app_commands.default_permissions` (confirmed server-side-hint-only, not an enforced check), `CommandTree`/`Cog.interaction_check` patterns, `Guild.leave()`, `Client.guilds`, `Guild.system_channel`, `TextChannel.permissions_for()`
- Existing codebase — `bot.py` (`_resolve_dexter_channel`, `_initialize_once`), `cogs/events.py` (`_get_ambient_channel`, `on_message` proactive/vision gates), `cogs/ops.py` (owner-check idiom), `config.py`, `database.py` (`SCHEMA_SQL` conventions), `services/gemini.py` (`_RateLimiter`), `services/memory.py` (`recall()` user_id-only scoping + its own "reserved for future per-guild scoping" docstring), `utils/logger.py`/`utils/tasks.py`, `.planning/PROJECT.md`, `CLAUDE.md`

### Secondary (MEDIUM confidence)
- Discord Permissions Calculator (discordapi.com) — least-privilege scope conventions
- Discord Developer Portal — Application Resource docs — Install Link mechanism, WebSearch-summarized
- What are Privileged Intents? / How Do I Get My App Verified? — Discord Developers — 100-guild verification wall, 10k-user intent threshold (search-snippet summarized, one direct fetch 403'd, cross-checked across two independent search results)
- Discord Developer Policy / Community Guidelines — harassment/abuse prohibitions applying to bot-generated content
- WebSearch: MEE6/Carl-bot/Dyno dashboard conventions, GitHub-as-portfolio README/architecture-diagram conventions, Discord bot landing-page templates

### Tertiary (LOW confidence)
- Multi-Server Discord Bots: Architecture (space-node.net) — generic multi-tenant scale framing only, not used for any Dexter-specific claim
- Discord Privileged Gateway Intents and MESSAGE_CONTENT in 2026 (space-node.net) — third-party summary, cross-checked against the official support-dev article for the 10k-user figure

---
*Research completed: 2026-07-10*
*Ready for roadmap: yes*
