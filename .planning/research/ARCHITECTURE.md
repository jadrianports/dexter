# Architecture Research — v1.4 "Open House" (Multi-Tenancy + Owner Control Plane + Portfolio)

**Domain:** Retrofitting multi-tenancy onto an existing single-community discord.py bot (layered cog → service → model → pure `logic/` seam)
**Researched:** 2026-07-10
**Confidence:** HIGH (all claims grounded in the actual codebase; one MEDIUM-confidence discord.py API detail flagged explicitly)

This is not greenfield ecosystem research — it is an integration map for retrofitting v1.4 onto Dexter's existing, code-complete v1.3 architecture. Every claim below is anchored to a real file/function in the current repo.

---

## 1. Current State: The Single-Guild Assumption, Audited

Grep across the repo for `DEXTER_CHANNEL_ID|OWNER_ID|is_owner|ERROR_LOG_CHANNEL_ID` returns exactly 7 files. Two of them (`ERROR_LOG_CHANNEL_ID` in `utils/logger.py`, `utils/tasks.py`) are **owner-operational and correctly global** — do not touch them (see §6 Anti-Patterns). The real single-guild coupling lives in three places:

| File : Function | What it does today | Why it breaks multi-tenancy |
|---|---|---|
| `config.py:57` `DEXTER_CHANNEL_ID = int(os.getenv(...)) or None` | One process-wide channel ID from `.env` | A single env var cannot represent "guild A's channel" vs "guild B's channel" |
| `bot.py:103-143` `_resolve_dexter_channel(guild)` | 4-step fallback: explicit `config.DEXTER_CHANNEL_ID` → last active music channel → `guild.system_channel` → first writable text channel. Used by `_post_startup_messages` (line 515) and `idle_check`'s loneliness post (line 739). | Step 1 reads the **global** config value for every guild, so all guilds resolve to the *same* channel ID (which usually doesn't even exist in a new guild) before falling through |
| `cogs/events.py:98-137` `EventsCog._get_ambient_channel(guild)` | **Byte-identical duplicate** of the function above (the code comment at `bot.py:112` admits this: *"Mirrors EventsCog._get_ambient_channel exactly; kept local to bot.py to preserve file-ownership boundaries (duplication is acceptable per plan)"*) | Same problem, and it's duplicated — two places to fix instead of one |
| `cogs/events.py:443-447` proactive-callback gate | `if message.guild is not None and config.DEXTER_CHANNEL_ID and message.channel.id == config.DEXTER_CHANNEL_ID:` | This is **not** the fallback-chain resolver at all — it's a bare equality check against the global config value. A guild that never set `DEXTER_CHANNEL_ID` gets **zero** proactive callbacks, ever, regardless of which channel it uses |
| `cogs/events.py:454-458` vision-roast gate | Identical bare-equality pattern, duplicated a second time | Same bug, same fix needed twice |

**Key finding:** there are three *structurally different* single-guild couplings (a fallback-chain resolver duplicated twice, and a bare-equality gate duplicated twice), not one. Any plan that only "adds a `guild_config` table" without touching all five call sites above will leave the proactive-callback and vision-roast cadences permanently dead on every guild except the owner's original one.

**Also confirmed, not a problem:** `OWNER_ID` (owner-only `/stats`, `/sync`) and `ERROR_LOG_CHANNEL_ID` (private ops channel via `bot.get_channel()`, works across guilds by channel-ID lookup regardless of which guild the channel lives in) are **correctly** global today and must **stay** global in v1.4 — they represent the owner's identity and private ops surface, not per-guild UX. Do not fold these into `guild_config`.

---

## 2. Recommended New Components

### 2.1 The per-guild config seam (foundation — everything else depends on this)

Mirrors the existing `logic/` + `services/` convention used by every prior phase (e.g. `logic/proactive.py` pure gate + `cogs/events.py` glue; `logic/health.py` pure decision + `bot.py`'s async DB probe glue).

**New table** — `database.py` `SCHEMA_SQL`, following the existing `TEXT`-keyed-snowflake convention (`guild_jams.guild_id`, `song_history.guild_id` are all `TEXT`, never `BIGINT`):

```sql
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id            TEXT PRIMARY KEY,
    ambient_channel_id  TEXT,              -- set via /setup; NULL = fallback chain
    is_blocked          BOOLEAN DEFAULT false,
    blocked_reason      TEXT,
    joined_at           TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);
```

**New pure logic module** — `logic/guild_config.py` (mock-free, TDD seam, same pattern as `logic/proactive.py`/`logic/vision.py`):

```python
def resolve_ambient_channel_id(
    *,
    is_blocked: bool,
    explicit_channel_id: int | None,
    explicit_channel_valid: bool,   # glue already confirmed the channel exists + bot can send
    fallback_channel_id: int | None,
) -> int | None:
    """Single source of truth for 'which channel gets ambient posts, if any.'

    Block check lives HERE, not scattered across call sites — a blocked guild
    always resolves to None regardless of any configured channel, and every
    ambient call site already does `if channel: await channel.send(...)`, so
    folding the block check into this pure function makes it the de facto
    ambient choke point for free (see §3).
    """
    if is_blocked:
        return None
    if explicit_channel_id is not None and explicit_channel_valid:
        return explicit_channel_id
    return fallback_channel_id
```

This is deliberately narrow and pure — it takes plain values, not `discord.Guild`, exactly like `logic/proactive.py::should_fire_proactive_callback` takes `opted_out`/`chance_roll`/`daily_count` rather than a `discord.Member`. The Discord-side glue (permission checks, `guild.get_channel`, `guild.system_channel`, `guild.text_channels` iteration) stays untested-by-design in the service layer below, matching the project's stated testing convention ("pure logic gets TDD; Discord/process code is untested-by-design, verified by structural review + clean local boot").

**New service** — `services/guild_config.py`:

```python
class GuildConfigService:
    """Per-guild config cache + resolver. Wraps guild_config table reads/writes."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._cache: dict[str, dict] = {}   # guild_id -> row, loaded once at boot

    async def load_all(self) -> None: ...        # bulk-load at boot (mirrors bot.server_states pattern)
    async def ensure_row(self, guild_id: str) -> None: ...   # on_guild_join seed
    async def set_ambient_channel(self, guild_id: str, channel_id: int) -> None: ...  # /setup
    async def set_blocked(self, guild_id: str, blocked: bool, reason: str | None) -> None: ...
    def is_blocked(self, guild_id: str) -> bool: ...          # sync, cache-only — hot path
    async def get_ambient_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """Replaces BOTH bot.py::_resolve_dexter_channel and events.py::_get_ambient_channel.
        Does the discord-side glue (permission checks, fallback candidates), then
        calls logic.guild_config.resolve_ambient_channel_id to decide, honoring is_blocked.
        """
```

Wired in `bot.py:_initialize_once` in the same spot as `bot.memory_service`/`bot.queue_persistence` are wired today (right after the pool is created, before cogs load) — `bot.guild_config_service = GuildConfigService(bot.pool)`, then `await bot.guild_config_service.load_all()`.

**Why an in-memory full-table cache, not per-call DB reads:** `on_message` fires on every non-bot message in every guild; `interaction_check` fires on every slash command. A per-event Neon round-trip is both slow (Neon can be mid scale-to-zero) and unnecessary at "modest scale" (a handful of guilds). This mirrors the existing `bot.server_states: dict[int, ServerState]` and `MessageBuffer` in-memory patterns already used for per-guild runtime state — no new caching idiom introduced. `AutoShardedBot` runs all shards in one asyncio process (not multi-process), so there is no cross-shard cache-coherency problem to solve.

**Migration for the owner's existing guild (no regression):** at boot, if `config.DEXTER_CHANNEL_ID` is set and no `guild_config` row exists yet for a guild containing that channel, seed `ambient_channel_id` from it once. This preserves the owner's current behavior with zero manual `/setup` step, and is the *only* remaining live read of `config.DEXTER_CHANNEL_ID` after the retrofit — everywhere else switches to `guild_config_service`.

### 2.2 Owner control plane + guild lifecycle — new `cogs/admin.py`

**New cog**, not folded into `events.py` or `ops.py`. Rationale: every existing cog owns one bounded concern (`events.py` = ambient personality listeners, `ops.py` = bot-wide observability, `memory.py` = the Phase 15 precedent for "a new cross-cutting concern gets its own cog rather than being crammed into an existing one"). Guild lifecycle + owner kill-switch is a third, distinct concern.

Contents:
- `on_guild_join(guild)` — check `guild_config_service.is_blocked(guild.id)` **first**; if already blocked (a force-left guild re-inviting the bot), immediately `await guild.leave()` and return — no onboarding message, no new row. Otherwise: `ensure_row()`, then post an onboarding message to the best-guess channel using the *same* fallback-chain glue as `get_ambient_channel` (no explicit channel configured yet, so it lands on `system_channel`/first-writable), telling admins to run `/setup`.
- `on_guild_remove(guild)` — **no-op by design.** The `guild_config` row persists (including `is_blocked`). This is the load-bearing decision that makes force-leave actually work as an abuse deterrent: if a leave also deleted the row, a blocked guild could simply re-invite the bot to reset its block status. Document this as an explicit decision, not an oversight.
- `/setup` — guild-admin-gated (`@app_commands.checks.has_permissions(manage_guild=True)` or `default_member_permissions`, NOT owner-only — any server admin should be able to designate their own channel), writes `ambient_channel_id` via the service.
- `/admin servers` — owner-only (inline `await bot.is_owner(interaction.user)` check FIRST, mirroring the exact `cogs/ops.py` `/stats` pattern at line 262-265 — no decorator, ephemeral refusal, consistent with the codebase's established owner-gate idiom), lists guilds + block status.
- `/admin block <guild_id> [reason]` / `/admin unblock <guild_id>` — owner-only, flips `is_blocked`.
- `/admin leave <guild_id>` — owner-only, force-leave: `set_blocked(True)` **then** `guild.leave()` (block-then-leave order matters — if the bot crashes between the two calls, being blocked-but-still-present is safe; being left-but-not-blocked is the reset-by-reinvite hole above).

### 2.3 The single block-enforcement choke point

Discord's API mechanically splits "a slash command fires" from "a gateway event fires" — there is no single literal hook spanning both. The correct architecture is therefore **one source of truth** (`GuildConfigService.is_blocked()`, backed by the one cached table) wired at **exactly two** call sites, each the natural Discord-API-mandated entry point for its category:

1. **Commands:** subclass `app_commands.CommandTree` and override `interaction_check`, wired via the `tree_cls` constructor kwarg on `commands.AutoShardedBot` (discord.py's documented pattern for global command gating — confirmed via Context7 for the analogous `Cog.interaction_check` on `GroupCog`; the exact `AutoShardedBot(tree_cls=...)` kwarg name should be double-checked against the installed discord.py version at implementation time — **MEDIUM confidence** on that one signature detail, HIGH confidence on the overall pattern):

   ```python
   class DexterCommandTree(app_commands.CommandTree):
       async def interaction_check(self, interaction: discord.Interaction) -> bool:
           if interaction.guild_id is not None and self.client.guild_config_service.is_blocked(str(interaction.guild_id)):
               await interaction.response.send_message("this server has been silenced.", ephemeral=True)
               return False
           return True
   ```

   This is the ONE place every single slash command (`/play`, `/ask`, `/imagine`, everything) gets gated — no per-cog checks to remember to add.

2. **Ambient/gateway events:** folded directly into the `logic/guild_config.py::resolve_ambient_channel_id` pure function (§2.1) — a blocked guild's channel always resolves to `None`, and **every existing ambient call site already null-checks the resolver's return value** (`if channel: await channel.send(...)` — this pattern already exists at `bot.py:517`, `events.py:267`, `events.py:311`, `events.py:357`, `events.py:741`). Consolidating the two duplicated resolvers into one service call therefore closes the ambient block-hole *as a side effect of removing duplication*, not as a separate new check bolted on top. The two hardcoded-equality gates in `on_message` (proactive callback, vision roast) must switch from `message.channel.id == config.DEXTER_CHANNEL_ID` to `message.channel.id == await bot.guild_config_service.get_ambient_channel_id(message.guild)` — which also inherits the block behavior for free once that call goes through the same resolver.

Two mechanically-necessary entry points, one shared decision function and one shared cache — not "scattered."

---

## 3. Data Flow

### New guild joins
```
Discord → on_guild_join(guild)
    → guild_config_service.is_blocked(guild.id)?
        yes → guild.leave() [re-invite-proofing]  → STOP
        no  → ensure_row(guild.id)  [INSERT default row: ambient_channel_id=NULL, is_blocked=false]
            → resolve best-guess onboarding channel (fallback chain, no explicit channel yet)
            → post "run /setup" onboarding message
```

### Every slash command
```
Discord interaction → DexterCommandTree.interaction_check(interaction)
    → guild_config_service.is_blocked(guild_id)?  [cache read, no I/O]
        yes → ephemeral "silenced" reply, command never dispatches
        no  → normal dispatch to the cog's command handler (unchanged)
```

### Every ambient post (voice-join roast, proactive callback, vision roast, idle-loneliness, startup message)
```
event fires → guild_config_service.get_ambient_channel(guild)
    → logic.guild_config.resolve_ambient_channel_id(is_blocked=..., explicit=..., fallback=...)
        blocked        → None → existing `if channel:` guard skips the post (unchanged code)
        has /setup     → explicit ambient_channel_id
        no /setup yet  → same D-09/D-10 fallback chain as today (last music channel → system → first writable)
```

---

## 4. Memory / Privacy Across Guilds — Analysis and Recommendation

**Current state (verified in code):** `services/memory.py::recall()` and `database.py::search_memories()` scope **only** by `user_id`. The `recall()` docstring says this explicitly: *"guild_id: reserved for future per-guild memory scoping; currently the ANN scopes to user_id only (cross-server personal facts are desirable: the same user uses the bot on multiple servers and their taste/history is personal)."* `user_memories.guild_id` is stored on every row but never used as a filter anywhere in the retrieval path. `remember()`'s dedup search (`database.search_memories(..., k=1)`, no `kind`/no `guild_id` filter) is likewise user-scoped only. The per-user eviction cap (`MEMORY_MAX_PER_USER`) and dedup threshold operate per-user, not per-(user, guild).

**What changes once Dexter is genuinely multi-tenant:** today "cross-server personal facts are desirable" is true because all of a user's guilds are the *same friend group's* alt servers. Once strangers on unrelated guilds share the bot, a `taste_episode`/`daily_batch`/`late_night` fact distilled in Guild A (say, a coworker's server) can surface as roast ammo in Guild B (a completely different community) — a real content-leak, not just a cosmetic issue, given the "full-savage everywhere" personality decision already locked for v1.4.

**Recommendation: OUT OF SCOPE for v1.4.** Rationale:

1. **PROJECT.md's own v1.4 framing already names the mitigation for this exact risk** — the owner kill-switch (§2.2) is the *stated* abuse/ToS mitigation for full-savage roasting on public servers, not per-guild memory isolation. Scale target is explicitly "modest... NOT engineered for 100+ servers." At owner-monitored, few-guild scale, the blast radius of a cross-guild memory reference is low and owner-correctable in real time (block/leave the guild).
2. **This is a real design surface, not a config flag.** Guild-scoping `recall()` touches: `search_memories`'s WHERE clause (needs an `OR guild_id IS NULL` branch for backward-compat with existing rows written with `guild_id=None`, e.g. `daily_batch` facts from `memory_distill_batch` which passes `guild_id=None` today — see `bot.py:885`), `remember()`'s dedup search (same scoping question), and potentially the per-user eviction cap semantics (does a 150-memory cap become per-user-per-guild, tripling storage pressure, or stay global with a guild filter only at read time?). This is exactly the kind of decision that deserves its own Context/Decision record in a future phase, not a silent scope-creep bundled into the `guild_config` table work.
3. **It is already flagged as future-facing in the existing code**, not new information — formalizing that comment into a deferred milestone candidate is the correct move, matching the precedent of "Salience reinforcement" and "Vision → RAG memory (MEM-R2)" already carried forward as named-but-deferred items in `PROJECT.md`.

**Action:** add "Guild-scoped RAG memory" to `PROJECT.md`'s deferred-candidate-directions list for a future milestone, to be picked up if/when Dexter is actually invited to a meaningful number of unrelated servers. No code change to `services/memory.py` or `database.py`'s memory helpers in v1.4.

---

## 5. Portfolio Surface (Landing Page + README Case Study)

**Where it lives:** a new top-level `/site` directory, **not** `/docs`. The existing `docs/` folder already holds internal-audience content (`docs/DEPLOY-KOYEB.md` ops runbook, `docs/superpowers/plans|specs` planning artifacts) — GitHub Pages' own convention of serving a `/docs` folder would make all of that unrelatedly public, and mixing a recruiter-facing static site with internal ops docs pollutes both. Deploy `/site` via a GitHub Actions Pages workflow (`actions/deploy-pages` or equivalent) rather than relying on the `/docs`-folder convention — this keeps `docs/` untouched and gives `/site` a clean, single-purpose home.

**Relationship to the README case study:** two audiences, two artifacts, one link between them.
- `README.md` (repo root) = the technical case study read *on GitHub* — architecture diagram, phase history, key decisions, the layered cog/service/model/logic story. This is what a recruiter reads to evaluate engineering judgment.
- `/site` = the deployed marketing surface — feature showcase + "Add to Discord" OAuth2 invite button. Links back to the GitHub repo/README for the deep dive; does not duplicate the technical narrative.

**Staying in sync with features:** manual sync, not auto-generated — appropriate for this project's scale. Add a line item to the existing milestone-close ritual (`PROJECT.md`'s "Evolution" section already has a phase-transition/milestone-close checklist) to update `/site`'s feature list alongside the existing `CLAUDE.md`/`PROJECT.md`/README sync steps that already happen at milestone close (see the v1.3 close commits: `668f480 docs: sync CLAUDE.md + PROJECT.md to v1.3 reality`). No new tooling needed.

**Invite plumbing:** a computed OAuth2 URL (`bot` + `applications.commands` scopes, permission integer matching the bot's real needs — Send Messages, Embed Links, Attach Files for `/imagine` output, Connect + Speak for voice, Add Reactions, Read Message History) belongs in the README and the `/site` invite button. This is low-architectural-risk plumbing, not a new component — sequence it after the control plane exists (§ Build Order) so the "abuse mitigation" story is real before the bot is actively promoted for invites to unknown servers.

---

## 6. Anti-Patterns to Avoid

### Anti-Pattern 1: Fixing the resolver duplication without fixing the hardcoded-equality gates
`bot.py::_resolve_dexter_channel` and `events.py::_get_ambient_channel` look like "the" single-guild coupling, but the two `message.channel.id == config.DEXTER_CHANNEL_ID` equality checks in `on_message` (proactive callback, vision roast) are a *different* bug shape and are easy to miss if the fix is scoped only to "replace the fallback-chain functions." Both patterns must be swapped to the new service.

### Anti-Pattern 2: Treating `ERROR_LOG_CHANNEL_ID` as another instance of the same problem
It looks structurally identical to `DEXTER_CHANNEL_ID` (a hardcoded env-configured channel ID), but it is the owner's private, cross-guild ops channel (`utils/logger.py::log_to_discord` does `bot.get_channel(config.ERROR_LOG_CHANNEL_ID)`, which works regardless of which guild the channel belongs to). It must **stay** global. Folding it into `guild_config` would be a regression — the owner needs one ops channel across all guilds, not one per guild.

### Anti-Pattern 3: Per-event DB round-trips for the block check
Given `on_message` fires per-message and `interaction_check` fires per-command, querying `guild_config` from Postgres on every event would add avoidable Neon latency (including scale-to-zero cold starts) to the hottest paths in the bot. Use the in-memory full-table cache pattern already established by `bot.server_states`/`MessageBuffer` — load once at boot, update the cache on every write (`/setup`, `/admin block`, `on_guild_join`), never re-read from Postgres on the hot path.

### Anti-Pattern 4: Quietly bundling guild-scoped memory into this milestone
As detailed in §4 — it's tempting to "just add a guild_id filter" alongside the `guild_config` table work since both touch guild identity, but it is a materially larger, cross-cutting change to the Phase 11/13/15/16 RAG pipeline's read/write/dedup/eviction semantics. Keep it explicitly out of scope and named as a deferred candidate, not silently absorbed.

### Anti-Pattern 5: Scattering the block check across every cog
Because there is no single Discord-API hook spanning both interactions and gateway events, there is a temptation to add an `if is_blocked: return` guard at the top of every command handler and every listener individually. Don't — use the two choke points in §3 (CommandTree subclass, resolver fold-in) backed by the one shared cache. Anything that finds itself adding a third `is_blocked` check somewhere is a sign the seam is being bypassed rather than reused.

---

## 7. Build Order (Dependency-Ordered)

1. **`guild_config` schema + `logic/guild_config.py` + `services/guild_config.py`, wired in `bot.py:_initialize_once`.** Includes the one-time migration seed from `config.DEXTER_CHANNEL_ID` for the owner's existing guild. This is the foundation — every other item below reads from `GuildConfigService`.
2. **Resolver consolidation.** Delete `events.py::_get_ambient_channel`; rewrite `bot.py::_resolve_dexter_channel` as (or move its logic into) `GuildConfigService.get_ambient_channel`. Swap all 5 call sites enumerated in §1 (`_post_startup_messages`, `idle_check`, the two voice-roast sites in `on_voice_state_update`, and the two hardcoded-equality gates in `on_message`). This alone fixes the ambient-blocking hole as a side effect (§2.3).
3. **`cogs/admin.py`** — `on_guild_join`/`on_guild_remove` lifecycle + `/setup` + owner control-plane commands (`/admin servers|block|unblock|leave`). Depends on step 1's service existing.
4. **`DexterCommandTree.interaction_check`** — the command-side block choke point. Can be built alongside step 3, but functionally depends on step 1.
5. **Regression pass.** Run the full existing suite (`test_ambient_recall_cadence.py`, `test_proactive_events.py`, vision/proactive `logic/` unit tests). None of `logic/roasts.py`, `logic/proactive.py`, `logic/vision.py` should need to change — guild-scoping lives entirely in the new resolver layer *above* those pure gates (chance/cooldown/cap logic stays guild-agnostic). If any of those pure modules need edits, that's a signal the seam was drawn in the wrong place.
6. **Invite plumbing** (OAuth2 URL/scopes/permissions) — low-risk, sequence after the control plane exists so the abuse-mitigation story is real before actively promoting invites.
7. **Portfolio surface** (`/site` + README case study) — purely additive, no runtime coupling; write last so it accurately describes the finished multi-tenancy + control-plane feature set.

Steps 1–2 are strictly sequential and blocking for everything else. Steps 3–4 can run in parallel with each other (both depend only on step 1) but both must land before step 5. Steps 6–7 have no code dependency on 1–5 and could theoretically run earlier, but sequencing them last produces a more accurate/complete artifact and a more honest abuse-mitigation story.

---

## Sources

- `C:\Users\James\desktop\projects\dexter\.planning\PROJECT.md` — v1.4 milestone framing, scale target, kill-switch-as-mitigation decision, deferred-candidates precedent
- `C:\Users\James\desktop\projects\dexter\CLAUDE.md` — project structure, schema, background tasks, slash command tables
- `C:\Users\James\desktop\projects\dexter\bot.py` — `_resolve_dexter_channel`, `_initialize_once` service-wiring pattern, `_post_startup_messages`, `idle_check`, background task registration
- `C:\Users\James\desktop\projects\dexter\cogs\events.py` — `_get_ambient_channel`, `on_voice_state_update`, `on_message` (proactive + vision gates), `_maybe_fire_proactive_callback`, `_maybe_fire_vision_roast`
- `C:\Users\James\desktop\projects\dexter\cogs\ops.py` — existing inline `is_owner` owner-gate idiom (`/stats`), `gather_bot_metrics` shared-source-of-truth pattern
- `C:\Users\James\desktop\projects\dexter\config.py` — `DEXTER_CHANNEL_ID`/`ERROR_LOG_CHANNEL_ID`/`OWNER_ID` definitions
- `C:\Users\James\desktop\projects\dexter\database.py` — `SCHEMA_SQL` conventions (TEXT-keyed guild_id, per-guild helper patterns like `guild_jams`), `search_memories`
- `C:\Users\James\desktop\projects\dexter\services\memory.py` — `recall()`/`remember()` user_id-only scoping, the "reserved for future per-guild scoping" docstring
- `C:\Users\James\desktop\projects\dexter\utils\logger.py`, `utils\tasks.py` — confirms `ERROR_LOG_CHANNEL_ID` is correctly global/cross-guild
- Context7 `/rapptz/discord.py` — confirmed `Cog.interaction_check` override pattern for `GroupCog`; `CommandTree` global-check pattern for app commands (MEDIUM confidence on exact `tree_cls` constructor kwarg name on `AutoShardedBot` — verify against installed discord.py version at implementation time)

---
*Architecture research for: Dexter v1.4 "Open House" multi-tenancy retrofit*
*Researched: 2026-07-10*
