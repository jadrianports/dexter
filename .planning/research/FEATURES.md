# Feature Research

**Domain:** Publicly-invitable, multi-tenant Discord bot (modest scale, owner-run, portfolio piece) — v1.4 "Open House"
**Researched:** 2026-07-10
**Confidence:** HIGH for discord.py mechanics (Context7-verified against `/rapptz/discord.py`); MEDIUM for ecosystem conventions (WebSearch, cross-checked against multiple sources: MEE6/Carl-bot/Dyno dashboard patterns, bot-listing/landing-page templates, permissions-calculator tooling)

## Feature Landscape

Four feature areas per the milestone brief: **(A) Onboarding & Per-Guild Config**, **(B) Owner Control Plane**, **(C) Invite Plumbing**, **(D) Portfolio Surface**.

### Table Stakes (Users/Admins Expect These)

| Feature | Area | Why Expected | Complexity | Notes |
|---------|------|--------------|------------|-------|
| `on_guild_join` welcome/setup-nudge post | A | Every reputable public bot posts *something* on join telling the admin what to do next — silence reads as broken or abandoned | LOW | Post to `guild.system_channel` if postable, else the first channel where the bot has `send_messages`; if neither, DM the guild owner as last resort. Message = who Dexter is + "an admin should run `/setup`". discord.py: `on_guild_join(guild)` fires on `Intents.guilds` (already enabled) |
| Admin-only `/setup` command to pick ambient channel | A | This is the single blocking gap — Dexter's ambient/roast/vision/proactive layer is hardcoded to one `DEXTER_CHANNEL_ID` today; a second guild has nowhere for it to post | MEDIUM | Gate with `app_commands.checks.has_permissions(manage_guild=True)` (real, enforced check) **and** `app_commands.default_permissions(manage_guild=True)` (Discord-side UI hint, not itself enforced — Context7-confirmed: "This is sent to Discord server side, and is not a check. Error handlers are not called"). Use both — hint for discoverability, real check for security |
| Per-guild config table (`guild_settings`, `guild_id` PK) | A | Backing store for the above; without it, `/setup` has nothing to write to | LOW-MEDIUM | Standard, verified pattern: single shared Postgres table keyed on `guild_id`, all reads/writes guild-scoped. At Dexter's modest scale (single-digit to low-dozens of guilds) no caching layer (Redis) is needed — direct query per ambient event is fine, matches existing `asyncpg` pool usage |
| Graceful pre-setup default (ambient silently no-ops, core commands unaffected) | A | A bot that crashes, spams a random channel, or refuses `/play` before an admin remembers to run `/setup` fails the "just works" bar from PROJECT.md | LOW | Music/`/ask`/`/imagine`/favorites/jams already respond in the invoking channel — zero dependency on ambient config, work immediately. Only the *unprompted* surfaces (voice-join roasts, milestone/streak roasts, idle loneliness, startup message, proactive callbacks, vision roasting, status rotation content) need a resolved channel; each of these call sites must fall back to "do nothing" (not crash, not guess a channel) when `guild_settings.ambient_channel_id IS NULL` |
| Per-guild ambient/feature toggles (disable roasts, disable vision) | A | An admin who doesn't want their server roasted or auto-scanned for vision jokes needs an off switch — without one, the personality-is-the-product bet becomes a liability the first time an admin gets annoyed | MEDIUM | Boolean columns on `guild_settings` (`ambient_enabled`, `vision_enabled` at minimum); each ambient/vision call site checks the flag before firing. This is the per-guild mirror of Phase 16's per-*user* `proactive_opt_out` — same shape, one level up |
| Owner-only "list servers" | B | The owner has zero visibility today beyond `/stats` (global aggregate) — once the bot is on N guilds, "which guilds, how big, how long" is baseline operational awareness | LOW | Extend the existing owner-only `/stats` pattern (already `commands.is_owner()`-gated) with a `guilds` subcommand: `bot.guilds` iteration → name, id, member_count, joined_at, ambient-enabled flag. No new permission model needed, reuses `OWNER_ID` |
| Owner-only silence-a-guild | B | The stated abuse mitigation in PROJECT.md ("owner kill-switch is the mitigation for the ToS/abuse surface of roasting strangers") — this is not optional, it's the safety valve the milestone goal explicitly depends on | LOW-MEDIUM | Sets `guild_settings.ambient_enabled/vision_enabled = false` for a target guild without leaving — softer than force-leave, reversible, good for "someone's annoyed, calm down" without nuking the whole relationship |
| Owner-only force-leave a guild | B | The hard version of the same kill-switch — for genuinely abusive/ToS-risk servers, silencing isn't enough; the bot needs to physically exit | LOW | `await guild.leave()` (discord.py, Context7-confirmed via `on_guild_remove` docs — leaving is a first-class client operation). Should also blacklist the guild ID (see below) or a booted admin just re-invites |
| Guild blacklist (persisted refusal to rejoin) | B | Force-leave without a blacklist is a no-op against a determined bad actor who just re-invites — this is the missing half of the kill-switch | LOW-MEDIUM | `blacklisted_guild_ids` table or column; check in `on_guild_join` — if blacklisted, immediately `guild.leave()` again (or reject before doing anything else) and log it. Small addition once force-leave exists |
| Least-privilege OAuth2 invite URL (no Administrator) | C | Server admins (and any recruiter who inspects the invite link or reads the code) are increasingly wary of bots requesting `Administrator` "to be safe" — it's a well-documented red flag, and it's also just bad practice for a portfolio piece meant to demonstrate security awareness | LOW | Build via `discord.utils.oauth_url(client_id, permissions=Permissions(...), scopes=['bot','applications.commands'])` (Context7-confirmed API). Enumerate the actual permission bits Dexter needs: View Channels, Send Messages, Embed Links, Attach Files, Add Reactions, Read Message History, Connect, Speak, Use Slash Commands (covered by the `applications.commands` scope, not a permission bit) — NOT Administrator, NOT Manage Server, NOT Manage Roles |
| Correct/declared Discord intents matching actual feature use | C | `message_content`, `voice_states`, `members`, `guilds` are already required per CLAUDE.md — these must stay correctly toggled in the Developer Portal for the invite to actually work on a second server, and `members`/`message_content` are privileged intents subject to Developer Portal toggles regardless of guild count | LOW | No new intents needed vs current CLAUDE.md list; this is a "don't regress" checkpoint during the multi-tenancy refactor, not new work |
| `default_permissions` hint on admin-only commands (`/setup`, owner control-plane commands) | C | Discord's own command permission UI shows/hides commands per-role based on this — without it, every server member sees `/setup` in the command picker even though only admins can run it, which reads as sloppy | LOW | `app_commands.default_permissions(manage_guild=True)` on `/setup`; owner-only commands (list/silence/leave) should have **no** guild permission surface at all — reserve them to the owner via `is_owner()`/`OWNER_ID` check only, don't expose as guild-visible commands other admins can even attempt |
| README with tagline, feature list, tech-stack badges, invite link | D | This is the absolute floor for "a recruiter can evaluate this in under two minutes" — every credible portfolio-repo guide (and GitHub's own recruiter-facing conventions) lists this as non-negotiable | LOW | Dexter already has a rich CLAUDE.md/architecture doc; the gap is a recruiter-facing *front door* — most of this is a rewrite/repackage of existing docs, not new engineering |
| Architecture section/diagram in the README or a linked doc | D | Recruiters evaluating a backend/bot project explicitly look for system-design signal (API design, data model, testing strategy) over "it's a Discord bot" — Dexter's cog→service→model layering + RAG memory pipeline is the actual differentiator worth surfacing | LOW-MEDIUM | Content already exists in CLAUDE.md/`.planning/`; this is curation (pick the 3–4 most impressive design decisions: global rate-limiter priority tiers, RAG accuracy firewall, generation-guarded prefetch, kind-agnostic memory) not new research |

### Differentiators (Competitive Advantage)

| Feature | Area | Value Proposition | Complexity | Notes |
|---------|------|-------------------|------------|-------|
| Guided `/setup` (channel-select component, not a raw ID/mention arg) | A | A select-menu channel picker feels like a "real" product's onboarding rather than a slash-command afterthought — small UX bump that costs little given discord.py's existing `discord.ui.ChannelSelect` | LOW-MEDIUM | Optional polish over "`/setup #channel`" — same underlying write to `guild_settings` |
| Owner DM/log-channel notification on every new guild join/leave | B | Zero-new-infra visibility (reuses the existing `ERROR_LOG_CHANNEL_ID` pattern) — critical at modest scale precisely because there's no web dashboard to check | LOW | Post "joined guild X (owner: Y, N members)" / "left guild X" to the existing owner error/log channel. Directly mirrors the Phase 9-era "surface, don't vanish" philosophy already baked into the codebase |
| Audit trail of silence/leave/blacklist actions (who did it, when, why) | B | Cheap given Postgres is already there; useful if the owner ever needs to explain/justify a moderation action, and reads as more disciplined engineering in a portfolio review | LOW | One small table or JSONB log column; not required for function, adds credibility |
| In-bot `/invite` command generating the URL dynamically | C | Keeps the invite link's permission set perpetually in sync with the bot's actual `Intents`/permission needs — a hardcoded README link silently drifts as features are added/removed | LOW | `discord.utils.oauth_url()` called at runtime with the bot's live `client_id` + a maintained `Permissions` object in `config.py`; single source of truth instead of two (README + code) |
| Standalone static landing page (GitHub Pages) separate from the README | D | A dedicated one-scroll page with a hero, feature showcase, and an invite button reads as more "shipped product" than a markdown wall — common convention among portfolio Discord bots that separate the recruiter-facing surface from the technical README | MEDIUM | No backend needed — static HTML/Tailwind is the ecosystem norm for bot landing pages; can literally be a GitHub Pages deploy off the same repo |
| Short demo GIF/clip of personality landing (a roast + a music session) | D | For a personality-driven bot, this is the single highest-signal artifact — screenshots of embeds don't convey "sarcastic and funny," a recorded exchange does | LOW-MEDIUM | Capture once the multi-guild refactor is stable; costs nothing but the owner's time to record on the residential-host bring-up |
| "Honest on-demand hosting" framing on the invite/landing page | D | Given the hosting model is genuinely on-demand (not 24/7 SaaS), stating this upfront turns a limitation into a deliberate, explained engineering tradeoff — recruiters respect an honest constraint more than a bot that just appears offline with no explanation | LOW | One sentence + maybe a `/health`-derived "currently online" badge if easy; otherwise just a clear caveat in the README/landing copy |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Full web-based per-guild settings dashboard (MEE6/Carl-bot/Dyno-style) | "Every big bot has one, it looks professional" | Real infra, auth, hosting, and maintenance burden that conflicts directly with the "no always-on cloud host" constraint and the "modest scale, not SaaS" milestone framing; this was already explicitly parked as "maybe since Phase 4, never committed" in PROJECT.md's Out of Scope | In-Discord `/setup` + owner-only slash commands; `/stats` already covers the owner's operational need per the existing decision log |
| Per-guild persona intensity dial ("tone down the sarcasm for this server") | Feels like a natural per-guild config knob alongside ambient toggles | Directly contradicts the locked milestone decision that "personality stays full-savage everywhere" — the differentiator IS the unmodulated sarcasm; diluting it per-guild undermines the product identity and multiplies prompt-engineering surface area for no validated demand | Per-guild on/off toggles for ambient/vision (binary), never a dial. If a guild doesn't want savage, they disable the surface, not soften it |
| Granular role-based permission picker for who can trigger commands per-guild | Looks like a natural extension of `/setup` | Discord already solved this natively via the command's own Integration/Permission management UI (server admins can restrict any command to any role from Discord's own settings, once `default_permissions` gives it a sane default) — rebuilding this in-bot duplicates a platform feature and adds a whole config surface with no unique value | Ship one sane `default_permissions` hint per admin command and let Discord's native per-command permission UI handle the rest |
| Multi-language/i18n localization | "A public bot should support other languages" | No evidence of demand at modest scale (single-owner, portfolio-first); discord.py's locale/i18n plumbing (`app_commands.locale_str`) is real work with no validated user; personality (lowercase, dry English sarcasm) is itself culturally/linguistically specific and doesn't translate cleanly | English-only; revisit only if a specific non-English server actually asks |
| Per-channel (not per-guild) ambient configuration | "More flexible, why limit to one channel per server?" | Over-engineering for the stated scale — CLAUDE.md's whole ambient model (roasts, callbacks, vision, status) is designed around a single designated channel; multiplying to N channels/guild multiplies every ambient call site's lookup logic for a need nobody has asked for | One `ambient_channel_id` per guild, matching the existing single-channel design, just moved from a global env var to a per-guild DB column |
| Automated abuse-detection / auto-silence heuristics (e.g., flag guilds with high vision-safety-block rates) | Feels like a natural evolution of the manual kill-switch | Real complexity (thresholds, false positives, an actual detection model) for a bot the owner personally monitors at modest scale — the manual owner kill-switch is explicitly the milestone's stated mitigation, not an automated system | Manual `/admin silence` / `/admin leave`, informed by the join/leave notification differentiator above so the owner actually sees new guilds arrive |
| Premium tiers / paywalled features | "Public bots often monetize to fund hosting" | Explicitly contradicts the portfolio-piece framing (this is a demonstration of engineering, not a business) and adds billing/entitlement complexity nobody asked for | None — the bot is free, on-demand, and its value is the demo/portfolio artifact itself |
| Submitting to top.gg / other public bot-list directories | "How else will people discover it?" | Bot-list submission pushes toward the Discord verification track (100+ guild threshold, additional privileged-intent approval) that the milestone explicitly says NOT to chase this round | Direct invite link on the README/landing page is sufficient — discovery is via the portfolio, not organic bot-list traffic |
| Multi-owner / staff RBAC for the control plane | "A real product would have a team" | Solo-developer project with a single `OWNER_ID` — building a permission tier system for a team that doesn't exist is speculative generality | Keep `OWNER_ID`-gated owner commands exactly as they are today; revisit only if a second trusted operator is actually added |
| User-installable "app" context (discord.py 2.4+ `integration_types` user-install) | Newer discord.py capability, looks modern | Dexter's core value (voice/music playback) fundamentally requires a guild installation — a user-install context can't join voice channels, so supporting it adds a whole secondary install path for features that mostly can't work there anyway | Guild-install only; don't enable user-install integration types |

## Feature Dependencies

```
[guild_settings DB table (guild_id PK)]
    └──requires nothing new──> builds on existing asyncpg/Postgres pool (Phase 4 pattern)

[Admin /setup command] ──requires──> [guild_settings table]
                        ──requires──> [has_permissions(manage_guild=True) check + default_permissions hint]

[Per-guild ambient channel resolution] ──requires──> [guild_settings table]
    └──touches EVERY ambient/unprompted call site: voice-join roasts, late-night roasts,
       repeat-song/milestone roasts, idle-loneliness messages, startup message,
       proactive callbacks (Phase 16), vision roasting (Phase 17), status rotation content
    └──this is the single largest cross-cutting refactor in the milestone

[Per-guild ambient/vision toggles] ──requires──> [guild_settings table]
                                   ──enhances──> [Owner "silence a guild"] (silence = force these flags false remotely)

[Owner "list servers"] ──requires nothing new──> reuses existing OWNER_ID / is_owner() pattern from /stats

[Owner "silence a guild"] ──requires──> [guild_settings ambient/vision toggle columns]
                          ──requires──> [OWNER_ID-gated command, NOT default_permissions-hinted
                                          (must not appear as a guild-visible command to other admins)]

[Owner "force-leave a guild"] ──requires──> [guild.leave() — no new infra]
                              ──enhances──> [Guild blacklist] (leave alone is trivially bypassed by re-invite)

[Guild blacklist] ──requires──> [small persisted table/column, checked in on_guild_join]
                  ──conflicts with──> nothing; purely additive safety net

[on_guild_join welcome/setup-nudge] ──requires nothing new──> Intents.guilds already enabled
                                    ──enhances──> [Admin /setup] (nudge tells the admin it exists)

[Owner join/leave notification] ──enhances──> [Owner "list servers"] (passive awareness vs active query)
                                ──requires nothing new──> reuses existing ERROR_LOG_CHANNEL_ID pattern

[Least-privilege OAuth2 invite URL] ──requires──> [enumerated Permissions() bitfield in config.py]
                                    ──enhances──> [Portfolio surface] (the invite link IS the CTA)

[In-bot /invite command] ──requires──> [Least-privilege OAuth2 invite URL logic]
                          ──enhances──> [Portfolio surface] (single source of truth vs hardcoded README link)

[Portfolio README/landing page] ──requires──> [working invite link] (a dead/wrong-permission invite kills credibility)
                                ──requires──> [at least one second guild successfully onboarded via /setup]
                                              (screenshots/demo need real multi-guild behavior, not just claims)

[Per-guild persona dial] ──conflicts with──> [locked "personality stays full-savage everywhere" decision] — DO NOT BUILD
[Per-channel ambient config] ──conflicts with──> [existing single-designated-channel ambient design] — DO NOT BUILD
[Web dashboard] ──conflicts with──> [on-demand owner-run hosting constraint, no always-on host] — DO NOT BUILD
```

### Dependency Notes

- **Per-guild ambient channel resolution requires `guild_settings` and touches every ambient surface:** this is the true "big rock" of the milestone. Every place `config.DEXTER_CHANNEL_ID` is read today in `cogs/events.py`, `cogs/music.py` (auto-lyrics/auto-queue announcements), and the status-rotation task needs to become a per-guild lookup. Sequencing the DB table + resolver helper *before* touching any individual ambient call site avoids doing the refactor twice.
- **Owner control-plane commands must NOT carry `default_permissions` hints:** unlike `/setup` (which should be admin-discoverable), the owner-only list/silence/leave commands should be invisible to guild admins entirely — gate purely on `OWNER_ID`/`is_owner()`, the same pattern already used for `/stats`. Giving them a guild permission surface would let a curious server admin see (even if they can't run) an owner control command, which is an unnecessary information leak about the bot's operational model.
- **Force-leave enhances (but does not replace) the blacklist:** leaving without recording the guild ID solves nothing against a determined bad actor who just re-invites the bot five minutes later — treat these as one feature pair, not two independently optional ones.
- **The join/leave owner notification enhances "list servers":** listing is pull (owner has to ask), notification is push (owner finds out immediately). Given the owner is the sole operator with no dashboard, the push notification is arguably higher-value per unit of effort — reuses the existing `ERROR_LOG_CHANNEL_ID` channel with zero new infrastructure, same "zero new infra" spirit as Phase 11/13.
- **Portfolio surface is sequenced last because it depends on real multi-guild proof:** a landing page or README claiming "invite me to any server" is not credible without having actually walked a second test guild through `/setup` and confirmed ambient behavior/toggles/kill-switch work. Build the static page/copy in parallel if desired, but don't finalize screenshots/demo content until the onboarding + control-plane work is verified.
- **Per-guild persona dial and per-channel ambient config directly conflict with existing locked decisions** (full-savage-everywhere; single designated channel) — these are explicitly flagged so a future "wouldn't it be nice if" doesn't quietly reopen them mid-milestone.

## MVP Definition

### Launch With (v1.4 "Open House")

Minimum viable product — what's needed to make the bot genuinely, safely invitable to a second server.

- [ ] `guild_settings` table + per-guild ambient-channel resolver — without this nothing else in the milestone is possible
- [ ] Admin-only `/setup` (channel picker, `has_permissions(manage_guild=True)` + `default_permissions` hint)
- [ ] `on_guild_join` welcome/setup-nudge message
- [ ] Pre-setup graceful default (ambient no-ops silently; core commands unaffected)
- [ ] Per-guild ambient/vision toggle + admin-facing way to flip it (could be `/setup` subcommand)
- [ ] Owner-only list-servers, silence-a-guild, force-leave-a-guild, and a persisted blacklist — this is the ToS/abuse mitigation the milestone goal explicitly depends on; not optional
- [ ] Least-privilege OAuth2 invite URL (explicit `Permissions()`, `bot`+`applications.commands` scopes, no Administrator)
- [ ] README rewrite: tagline, feature list, tech-stack badges, working invite link, architecture summary

### Add After Validation (v1.4 polish, still in-milestone if time allows)

- [ ] Owner join/leave notification to the existing error/log channel
- [ ] `/invite` command generating the URL dynamically instead of a hardcoded README link
- [ ] Channel-select UI component for `/setup` instead of a raw argument
- [ ] Standalone static landing page (GitHub Pages) with a demo GIF

### Future Consideration (v2+, explicitly deferred)

- [ ] Audit trail of owner moderation actions (silence/leave/blacklist history) — nice, not required for the milestone goal
- [ ] Resume the parked 24/7 deploy (host-gated, tracked separately in PROJECT.md carried-forward items)
- [ ] Any move toward Discord bot verification / 100+ guild scale — explicitly out of this milestone

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|----------------------|----------|
| `guild_settings` table + ambient resolver | HIGH | MEDIUM | P1 |
| Admin `/setup` | HIGH | LOW-MEDIUM | P1 |
| `on_guild_join` nudge message | HIGH | LOW | P1 |
| Pre-setup graceful default | HIGH | LOW | P1 |
| Per-guild ambient/vision toggle | HIGH | LOW-MEDIUM | P1 |
| Owner list/silence/leave/blacklist | HIGH | LOW-MEDIUM | P1 |
| Least-privilege invite URL | HIGH | LOW | P1 |
| README/portfolio rewrite | HIGH | LOW-MEDIUM | P1 |
| Owner join/leave notification | MEDIUM | LOW | P2 |
| Dynamic `/invite` command | MEDIUM | LOW | P2 |
| Channel-select `/setup` UI | LOW-MEDIUM | LOW-MEDIUM | P2 |
| Static landing page + demo GIF | MEDIUM | MEDIUM | P2 |
| Audit trail of owner actions | LOW | LOW | P3 |
| Per-guild persona dial | — | — | REJECTED (conflicts with locked decision) |
| Web dashboard | — | — | REJECTED (conflicts with hosting constraint) |

**Priority key:**
- P1: Must have — the milestone goal ("recruiter can invite it to any server and it just works," "owner kill-switch for abuse") is unmet without these
- P2: Should have — meaningfully strengthens the portfolio/ops story, add if time allows within v1.4
- P3: Nice to have — genuinely deferrable to a future milestone with no loss to this one's goal

## Competitor / Reference Pattern Analysis

| Concern | MEE6 / Carl-bot / Dyno (large public bots) | Dexter's approach |
|---------|---------------------------------------------|--------------------|
| Per-guild configuration | Full web dashboard (OAuth login, plugin toggles) | In-Discord `/setup` + owner-gated toggles — no dashboard, matches the on-demand/no-cloud-host constraint and the existing "web dashboard deferred" decision |
| Owner/operator visibility | Internal to the bot vendor's own ops tooling (not user-facing) | Owner-only Discord commands (`/stats`-style) + a log-channel notification on join/leave — zero new infra, reuses Phase 9's "surface, don't vanish" philosophy |
| Invite permission scope | Historically criticized for over-requesting broad permissions; better-regarded bots have trimmed to task-specific scopes | Explicit enumerated `Permissions()`, no Administrator — deliberately the *opposite* of the historical over-ask pattern, and a genuine differentiator to call out in the portfolio README |
| Scale | Tens of thousands of guilds, sharded, verified, monetized | Explicitly modest scale (single-digit to low-dozens of guilds), unverified, free, owner-run — none of the large-bot infra patterns (Redis settings cache, sharding-for-scale, premium tiers) are warranted here, and building them would be a portfolio red flag (over-engineering for the stated scale), not a green one |

## Sources

- discord.py official docs via Context7 (`/rapptz/discord.py`) — `on_guild_join`/`on_guild_remove` events, `discord.utils.oauth_url`, `app_commands.default_permissions` (confirmed: server-side hint only, not an enforced check), `app_commands.checks.has_permissions`, guild-restricted command registration (FAQ) — HIGH confidence, current docs
- [Discord Permissions Calculator (discordapi.com)](https://discordapi.com/permissions.html) and related calculator tools — least-privilege scope/permission conventions — MEDIUM confidence
- [Community Onboarding FAQ – Discord](https://support.discord.com/hc/en-us/articles/11074987197975-Community-Onboarding-FAQ) — general onboarding UX conventions — MEDIUM confidence
- WebSearch: MEE6 Wiki (Dashboard/Settings pages), Carl-bot (carl.gg), Dyno — large-bot per-guild dashboard conventions, cited as the pattern Dexter deliberately does NOT replicate at this scale — MEDIUM confidence
- WebSearch: multi-guild database pattern discussion (guild_settings table, guild-scoped queries, when sharding/caching actually becomes necessary by guild count) — MEDIUM confidence, cross-checked against Dexter's existing `asyncpg`/Postgres architecture which already fits the "under 100 servers" tier described
- WebSearch: GitHub-as-portfolio conventions (README structure, architecture diagrams, recruiter expectations) and an existing "architecture case study" Discord bot portfolio repo pattern (EdShakie/Discord-Bot) — MEDIUM confidence
- WebSearch: Discord bot landing page templates/conventions (hero + invite CTA + feature showcase) — LOW-MEDIUM confidence (marketing-template sources, not authoritative, but consistent across multiple independent examples)
- Project-internal: `.planning/PROJECT.md` (v1.4 milestone goal, scale target, locked decisions: personality stays full-savage, hosting stays on-demand/owner-run, web dashboard previously deferred) and `CLAUDE.md` (existing single-channel/single-owner architecture, ambient surfaces list, Phase 16 `proactive_opt_out` precedent for per-user toggles) — HIGH confidence, ground truth for what exists today

---
*Feature research for: publicly-invitable multi-tenant Discord bot, modest scale, portfolio-grade*
*Researched: 2026-07-10*
