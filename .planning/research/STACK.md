# Stack Research

**Domain:** Making a single-community Discord bot publicly invitable and multi-tenant (v1.4 "Open House")
**Researched:** 2026-07-10
**Confidence:** HIGH

## Scope Note

This is a **subsequent-milestone, additive** stack document. The existing stack (Python 3.11+,
discord.py ≥2.3 `AutoShardedBot`, yt-dlp+FFmpeg, `google-genai`, asyncpg 0.31.0 on Neon Postgres,
pgvector, aiohttp `/health`, Docker) is fixed and NOT re-evaluated here. Every recommendation below
is either (a) an API already present in the installed discord.py version — zero new dependency —
or (b) a Postgres schema addition using the exact idiom already in `database.py`, or (c) a
zero-backend static landing page. **No new services, queues, or databases are introduced.**

## Recommended Stack

### Core Technologies (already installed — confirmed current)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| discord.py | ≥2.3.0 installed; **2.7.1 is current on PyPI (2026-03-03)** | Guild lifecycle events, invite URL generation, permission modeling | All four new-feature needs (invite URL, `on_guild_join`/`on_guild_remove`, `guild.leave()`, channel resolution) are core APIs already present in 2.3+; no version bump required. `discord.utils.oauth_url()` has defaulted to `scopes=('bot', 'applications.commands')` since 2.0, which is exactly the scope pair this milestone needs. |
| asyncpg | 0.31.0 (pinned) | `guild_config` table access | Same pool, same `SCHEMA_SQL` idempotent-DDL pattern, same `init=_register_vector` pool — zero new infra. |

### New Additions

| Addition | Type | Purpose | Why Recommended |
|----------|------|---------|-----------------|
| `guild_config` table | Postgres schema (existing DB) | Per-guild ambient channel + owner kill-switch state | Mirrors the exact `guild_jams`/`user_favorites` idiom already in `SCHEMA_SQL` — `guild_id TEXT PRIMARY KEY`, upsert via `INSERT ... ON CONFLICT DO UPDATE`. No new table category, no ORM, no migration tool. |
| `discord.utils.oauth_url()` | discord.py stdlib function | Generate the canonical "Add to Discord" URL | Purpose-built for this exact task; takes a `client_id`, a `discord.Permissions` object, and a `scopes` tuple and returns a ready-to-use URL. No manual query-string building, no separate OAuth library. |
| Discord Developer Portal "Install Link" (Default Install Settings) | Portal configuration, zero code | The URL actually put on buttons/README | Discord's own recommended mechanism since the 2023 Installation-page redesign — set once in the Portal, Discord hosts the authorize flow, and it auto-reflects if you ever add scopes later. Cheaper than hand-rolling `oauth_url()` for the *public-facing* link; keep `oauth_url()` in-code only for an owner-only `/invite` utility command that prints the same link for convenience. |
| Static HTML/CSS (no framework) on **GitHub Pages** | Landing page hosting | Portfolio surface: feature showcase + invite button | Zero build step, zero server, free, and the repo is already on GitHub — enabling Pages is a Settings toggle, not new infra. A solo dev shipping one page with a hero, a feature list, and a button does not need React/Next.js/Astro; those add a build pipeline, a `package.json`, and a deploy target for a page that will not out-grow single-file HTML+CSS this milestone. |

### Supporting Libraries

**None required.** Every capability in this milestone's scope (per-guild config, invite URL, guild join/leave, owner control plane, landing page) is covered by discord.py's existing API surface, the existing asyncpg pool, and plain HTML/CSS. Do not add `discord-ext-*` invite-management packages (e.g. third-party "invite tracker" cogs) — they solve a different problem (tracking *which invite link* brought a *member* in) and are irrelevant to bot-installation OAuth.

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| GitHub Pages (repo Settings → Pages) | Serve the static landing page | Point it at a `docs/` folder or a `gh-pages` branch off `main`; no Actions workflow needed for plain HTML (Pages serves static files directly — only add a build Action if you later introduce a bundler, which is not recommended here). |
| Discord Developer Portal → OAuth2 → Installation | Configure the public invite link | Set "Install Link" = Discord Provided Link; under Default Install Settings, add scopes `bot` + `applications.commands` and check the bot permissions this milestone needs (see Permissions table below). This is also where the numeric Application (Client) ID lives — copy it once into the landing page's hardcoded href and into `.env` as `DISCORD_CLIENT_ID` for the owner `/invite` command. |

## Per-Guild Configuration: `guild_config` Schema

Mirrors the existing `guild_jams` / `resolution_cache` idiom in `database.py::SCHEMA_SQL` exactly —
`CREATE TABLE IF NOT EXISTS`, `TEXT` guild-id keys (matching every other table's convention),
`TIMESTAMPTZ DEFAULT now()`, no ORM:

```sql
-- v1.4: per-guild configuration, replacing the single hardcoded DEXTER_CHANNEL_ID.
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id            TEXT PRIMARY KEY,
    ambient_channel_id  TEXT,               -- set via /setup; NULL = fall back to resolution chain
    silenced            BOOLEAN DEFAULT false,  -- owner kill-switch: mutes ambient/proactive/vision
                                                 -- output for this guild WITHOUT leaving (abuse mitigation)
    joined_at           TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);
```

**Why this shape, not more:**
- **`ambient_channel_id` nullable, not NOT NULL** — a freshly-joined guild has no row yet (or a row
  with `NULL`), and the existing `_resolve_dexter_channel()` fallback chain (system channel → first
  writable channel) already handles that gracefully. `/setup` just upserts this one column.
- **`silenced` as a boolean column, not a separate table** — matches the `user_profiles.proactive_opt_out`
  precedent (Phase 16): a single additive flag, upsert-only, queried by the same ambient-output gate
  functions that already check cooldowns/chances (`logic/roasts.py`, `logic/proactive.py`,
  `logic/vision.py`). Silencing is a **guild-scoped** analog of the per-user opt-out — it should be
  checked at the same call sites, one extra `AND NOT silenced` condition (or an async pool read),
  not a new subsystem.
- **No per-guild `error_log_channel_id` or `owner_id` column** — `ERROR_LOG_CHANNEL_ID` and `OWNER_ID`
  stay single global env vars. The error log is the *bot owner's* private diagnostics channel across
  every guild, not a per-tenant setting; multi-tenant error routing is out of scope (the owner already
  has `/stats` and the error channel bot-wide).
- **`updated_at` for cheap "last touched" ops visibility**, consistent with every other Phase 4/7/12
  table (`guild_jams`, `user_playlists`).

**Upsert pattern (mirrors `set_proactive_opt_out` / `save_jam` exactly):**

```python
async def set_ambient_channel(pool: asyncpg.Pool, *, guild_id: str, channel_id: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO guild_config (guild_id, ambient_channel_id, updated_at)"
            " VALUES ($1, $2, now())"
            " ON CONFLICT (guild_id) DO UPDATE SET"
            "   ambient_channel_id = EXCLUDED.ambient_channel_id, updated_at = now()",
            guild_id, channel_id,
        )

async def set_guild_silenced(pool: asyncpg.Pool, *, guild_id: str, silenced: bool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO guild_config (guild_id, silenced, updated_at)"
            " VALUES ($1, $2, now())"
            " ON CONFLICT (guild_id) DO UPDATE SET"
            "   silenced = EXCLUDED.silenced, updated_at = now()",
            guild_id, silenced,
        )

async def get_guild_config(pool: asyncpg.Pool, *, guild_id: str) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT ambient_channel_id, silenced, joined_at"
            " FROM guild_config WHERE guild_id = $1",
            guild_id,
        )
```

**Integration point — `_resolve_dexter_channel()` in `bot.py`:** step 1 currently checks the single
global `config.DEXTER_CHANNEL_ID`. Replace it with a per-guild lookup against `guild_config`, keeping
steps 2–4 (last active music channel → system channel → first writable channel) as the unchanged
fallback for guilds that never ran `/setup`. Because this function is called from hot paths
(`status_rotation` every 5 min, ambient roast dispatch), cache the resolved `ambient_channel_id`
in-memory per guild (e.g. on the existing per-guild `ServerState` object, populated on `/setup` and
on `on_guild_join`) rather than issuing a DB round-trip on every ambient event — this is an
architecture/roadmap decision, not a stack change, but it constrains how `guild_config` is read.

## OAuth2 Invite / "Add to Discord" Plumbing

### The two-track approach (do both, they are not mutually exclusive)

**Track 1 — Discord Provided Link (recommended for the public-facing button).**
In the Developer Portal → your app → **OAuth2 → General → Installation**, set "Install Link" to
"Discord Provided Link", then under **Default Install Settings** add:
- Scopes: `bot`, `applications.commands`
- Bot Permissions: the set below

Discord then hosts a stable authorize URL for you
(`https://discord.com/oauth2/authorize?client_id=<APP_ID>`) that always reflects your current
Default Install Settings — you never hand-encode a permissions integer into a URL that could later
drift from what the bot actually requests in code. **Use this URL as the landing-page button's
`href` and in the README** — it needs no runtime code at all, which is exactly the "static page,
zero backend" constraint.

**Track 2 — `discord.utils.oauth_url()` (recommended for an owner-only `/invite` utility command).**
```python
import discord

def build_invite_url(client_id: int) -> str:
    permissions = discord.Permissions(
        view_channel=True,
        send_messages=True,
        embed_links=True,
        attach_files=True,
        read_message_history=True,
        add_reactions=True,
        use_external_emojis=True,
        connect=True,
        speak=True,
        use_voice_activation=True,
    )
    return discord.utils.oauth_url(
        client_id,
        permissions=permissions,
        scopes=("bot", "applications.commands"),  # this is the discord.py 2.x DEFAULT already
    )
```
Since `discord.py` 2.0, `oauth_url()`'s `scopes` kwarg **defaults to `('bot', 'applications.commands')`
when omitted** — so even calling `discord.utils.oauth_url(client_id, permissions=permissions)` with
no `scopes=` argument gets the right pair. Passing it explicitly (as above) is just self-documenting.

**Permissions to request (reasoning per flag):**

| Permission | Why Dexter needs it |
|------------|----------------------|
| `view_channel`, `send_messages`, `embed_links` | Now-playing embeds, `/ask`/`/roast` replies, `/help` |
| `attach_files` | `/imagine` image posts |
| `read_message_history` | `/history`, lyrics pagination edits |
| `add_reactions` | Ambient emoji reactions (YouTube/Spotify links, "gn", etc.) |
| `use_external_emojis` | Personality flourishes if any custom emoji is ever used |
| `connect`, `speak` | Voice playback — the whole music pipeline |
| `use_voice_activation` | Standard for any voice bot; avoids push-to-talk friction for the inviting server |

Deliberately **not requested**: `administrator` (never — a music/roast bot has no reason to hold
guild-wide admin, and requesting it would spook any recruiter/security-conscious server owner
evaluating the invite), `manage_messages`/`manage_channels`/`kick_members`/`ban_members` (nothing
in the current feature set needs them — the owner kill-switch operates via `guild.leave()`, which
needs no elevated permission at all).

**Client/Application ID for the static page:** copy the numeric Application ID once from
Developer Portal → General Information, and hardcode it into the landing page's button `href`
(a static page cannot make a runtime Discord API call to look this up, nor should it). The
in-bot `/invite` command can instead read `bot.application_id` (a discord.py `Client` property
populated after login) or an env var `DISCORD_CLIENT_ID`, whichever is already-known — either is
fine since this is a convenience command, not the canonical link.

## discord.py Multi-Tenancy APIs

| API | Signature | Use in v1.4 |
|-----|-----------|--------------|
| `on_guild_join(guild)` | event handler on the bot instance/cog, requires `Intents.guilds` (already enabled) | Fires when Dexter is added to a new server. Upsert a `guild_config` row (`joined_at=now()`), resolve a channel via the existing fallback chain (system channel → first writable — `ambient_channel_id` is still NULL at this point), and post a short onboarding message pointing the server at `/setup`. |
| `on_guild_remove(guild)` | same event contract as above | Fires on kick/ban/self-leave/guild-deletion. Best-effort: log it, optionally leave the `guild_config` row in place (harmless orphan, or a small cleanup deletes it) — no action required for correctness since every per-guild query is already scoped by `guild_id` and a re-add just re-upserts. |
| `bot.guilds` | `Sequence[Guild]` property on any `Client`/`Bot` | Owner control-plane listing command (`/servers list` or similar) iterates this directly — no DB query needed to enumerate what Dexter is currently in; join `guild_config` only for the `silenced` flag per guild. |
| `Guild.leave()` | `await guild.leave()` — coroutine, no special permission required (it's the bot's own membership) | The force-leave half of the owner kill-switch (`/servers leave <guild_id>`). Resolve the target via `bot.get_guild(int(guild_id))` (must be in `bot.guilds`) before calling `.leave()`; guard with the owner-only check already used by `/sync` and `/stats` (`await bot.is_owner(interaction.user)`). |
| `Guild.system_channel` / `TextChannel.permissions_for(guild.me)` | existing pattern, already used in `_resolve_dexter_channel()` and `_post_startup_messages()` | Reused verbatim for the join-time onboarding message and as the fallback tier when `guild_config.ambient_channel_id` is unset. |

**Owner control-plane summary (no new library, pure discord.py + `guild_config`):**
- `/servers list` (owner-only) — iterate `bot.guilds`, left-join `guild_config.silenced`, format as an
  embed/paginated list (same pagination idiom as `/memory view` / `/history`).
- `/servers silence <guild_id>` / `/servers unsilence <guild_id>` (owner-only) — toggles
  `guild_config.silenced`; ambient roast/proactive/vision gate functions add one additional check.
- `/servers leave <guild_id>` (owner-only, danger-confirm button per the `/memory forget` /
  `/jam suggest` confirm-button precedent) — resolves via `bot.get_guild()`, calls `guild.leave()`.

## Portfolio Landing Page

### Recommendation: plain static HTML + CSS on GitHub Pages. No framework, no build step.

**Why not a framework (Next.js/Astro/Vite+React/etc.):** the actual deliverable is one page — a
hero section, a short feature list (music/AI/personality/RAG memory), one "Add to Discord" button
(the static Track-1 URL above), and a link to the README/architecture case study. That is
well within what a single `index.html` + one `style.css` (+ optionally a few lines of vanilla JS for
a mobile nav toggle or a copy-to-clipboard) can express. Introducing a JS framework means a
`package.json`, a `node_modules`, a build command, and a CI step purely to ship less HTML than the
framework's own boilerplate — pure overhead for a solo dev's one-page portfolio surface, and it adds
a second toolchain (Node) to a project that is otherwise 100% Python.

**Hosting: GitHub Pages** (free, the repo already lives on GitHub):
- Simplest form: a `docs/` folder at repo root (or `gh-pages` branch) containing `index.html` +
  `style.css` + any screenshots/assets; enable via Settings → Pages → "Deploy from a branch" →
  select folder. Zero YAML, zero Actions run, updates on every push to `main`.
- If richer authoring is wanted later (templating, Markdown → HTML), the next-smallest step is a
  static-site generator with **zero client-side JS framework**, e.g. plain Jekyll (GitHub Pages'
  native built-in generator — no separate build step needed, GitHub runs it for you) — this is a
  reasonable escalation path but is **not necessary for this milestone's scope** (a single feature
  showcase page).
- Alternative equally-free static hosts (Netlify, Vercel, Cloudflare Pages) are equivalent in cost
  and friction; GitHub Pages is recommended specifically because the repo is already there — no new
  account, no new connected service.

**What goes on the page:**
- Feature showcase: music (yt-dlp/FFmpeg, filters, favorites/playlists/jams), AI chat/roasts
  (Gemini 2.5, RAG long-term memory, taste-aware DJ), vision roasting, the "alive" ambient
  personality layer — pulled straight from `CLAUDE.md`'s existing feature list, no new content
  strategy needed.
- The "Add to Discord" button — static `href` to the Track-1 Discord Provided Link.
- A link to the GitHub repo / README (the architecture case study lives there, not duplicated on
  the page).

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|--------------|-------------|--------------------------|
| Single `guild_config` table, columns added ad hoc as new settings emerge | A generic `JSONB settings` blob column instead of typed columns | Only if the number of per-guild settings is expected to grow rapidly and unpredictably; for two settings (`ambient_channel_id`, `silenced`) typed columns are simpler to query/index and match every existing table's style — do not reach for JSONB prematurely here. |
| Discord Developer Portal "Install Link" (Discord Provided Link) for the public button | Hand-built `oauth_url()` link baked into the HTML at "build time" | Only if you need a *non-default* permission set for a *specific* audience (e.g. a stripped-down read-only demo invite) — not needed here since there's only one bot persona and one permission set. |
| `Guild.leave()` for the kill-switch | `Guild.ban()`/kicking members, or revoking the bot token | Overkill/wrong tool — leaving is the correct, permission-free, instantly-reversible (re-invite) action; token revocation is a nuclear option that also breaks the owner's own usage. |
| Plain static HTML/CSS on GitHub Pages | Next.js/Astro static export | Only if the portfolio surface grows into a multi-page site with routing, a blog, or dynamic data-fetching (e.g. live server count from the bot's `/health` or a stats API) — none of which is in this milestone's scope. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|--------------|
| A generic third-party "Discord bot dashboard" framework (e.g. self-hosted web panels, OAuth-login admin UIs) | Explicitly out of scope per `PROJECT.md` ("Web config dashboard — deferred") and this milestone's modest-scale framing; adds a whole new web app + session/auth surface for a single owner who already has `/stats`/`/servers` in-Discord | Owner-only slash commands (`/servers list|silence|leave`), consistent with every other admin surface in the bot (`/stats`, `/sync`) |
| `discord.ext.commands` prefix/hybrid commands for the new owner commands | Project is pure `app_commands` slash commands by design (CLAUDE.md Out-of-Scope) | `@bot.tree.command(...)` app_commands, owner-gated via `bot.is_owner()`, same pattern as `/sync` |
| A dedicated invite-tracking library (tracks *which* invite link brought *which member*) | Solves a different problem (member-acquisition attribution), irrelevant to bot-installation OAuth | `discord.utils.oauth_url()` / Developer Portal Install Link |
| Requesting `Administrator` in the bot's permission set | Massive unnecessary trust ask for a public invite; a security-aware recruiter will notice and it is not needed for any current feature | The itemized permission list above |
| A JS framework / bundler for the landing page | One static page does not need a build pipeline; adds Node tooling to an otherwise pure-Python repo | Plain HTML + CSS on GitHub Pages |
| Alembic or any migration framework for `guild_config` | Project convention (Phase 4 decision, still valid) is raw idempotent `CREATE TABLE IF NOT EXISTS` in `SCHEMA_SQL` — a fresh-start schema philosophy that has held through 17 phases | Add the table to `SCHEMA_SQL` exactly like `guild_jams`/`resolution_cache` were added in Phases 6/12 |

## Stack Patterns by Variant

**If a guild silences Dexter but the owner wants music to keep working there:**
- Scope `silenced` to ambient/ownerless output only (roasts, proactive callbacks, vision roasts,
  idle-loneliness messages) — never gate `/play`, `/ask`, `/imagine`, or any explicit slash command.
  This matches the stated milestone goal ("cut off abuse" of unprompted roasting/vision, not disable
  the bot's core utility) and mirrors the existing per-user `proactive_opt_out` precedent (an opt-out
  silences one *surface*, not the whole bot).

**If a guild never runs `/setup`:**
- `guild_config.ambient_channel_id` stays NULL forever; `_resolve_dexter_channel()`'s existing
  steps 2–4 (last active music channel → system channel → first writable channel) already cover
  this gracefully — this is exactly the "no hardcoded single channel, but no dead ambient behavior
  either" requirement, and it requires no new fallback logic beyond what's already shipped.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|------------------|-------|
| discord.py ≥2.3.0 (installed) | `discord.utils.oauth_url(scopes=('bot','applications.commands'))` default | This default has been in place since discord.py 2.0 — no version bump needed for any API in this document. |
| asyncpg 0.31.0 (pinned) | `guild_config` DDL below `CREATE EXTENSION IF NOT EXISTS vector;` in `SCHEMA_SQL` | No `$N` params in the new DDL block, so it stays inside the existing single multi-statement `conn.execute(SCHEMA_SQL)` call (Pitfall 1 precedent already documented in CLAUDE.md). |
| GitHub Pages | Any static HTML5/CSS3 | No Python/Node version coupling — it is a fully separate artifact from the bot's runtime, cannot break the bot's deploy. |

## Sources

- Context7 `/rapptz/discord.py` — `discord.utils.oauth_url` signature and default-scopes changelog, `on_guild_join`/`on_guild_remove` event contracts, `app_commands.default_permissions`, `setup_hook` pattern. HIGH confidence (official docs/API reference + migration guide).
- [discord.py PyPI page](https://pypi.org/project/discord.py/) — current release 2.7.1 (2026-03-03), confirms compatibility with the project's `discord.py>=2.3.0` pin. MEDIUM-HIGH confidence (WebSearch-sourced, cross-checked against PyPI metadata conventions).
- [Discord Developer Portal — Application Resource docs](https://docs.discord.com/developers/resources/application) — Install Link / Default Install Settings mechanism. MEDIUM confidence (WebSearch summary of official docs; recommend a final visual confirmation in the Portal UI before shipping, since Portal UI text can shift between releases).
- `discord.py` core API for `Guild.leave()`, `Client.guilds`, `Guild.system_channel`, `TextChannel.permissions_for()` — HIGH confidence: stable, multi-year-unchanged core API already exercised elsewhere in this codebase (`bot.py::_resolve_dexter_channel`, `_post_startup_messages`).
- Existing codebase (`database.py`, `config.py`, `bot.py`, `CLAUDE.md`) — ground truth for the schema idiom, upsert patterns, and fallback-chain logic this milestone extends. HIGH confidence (first-party source).

---
*Stack research for: Discord bot public-invite / multi-tenancy / portfolio landing page (v1.4 "Open House")*
*Researched: 2026-07-10*
