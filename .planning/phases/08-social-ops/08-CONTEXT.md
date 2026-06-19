# Phase 8: Social & Ops - Context

**Gathered:** 2026-06-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 8 delivers two surfaces, both built on data Dexter **already collects** — no new
data-collection pipelines:

1. **Social**
   - `/roast @user` (SOCIAL-01) — a Gemini-personalized roast of a target user, generated from
     their tracked song history / top artists / streak, with a guaranteed template fallback.
   - `/leaderboard` (SOCIAL-02) — a per-server ranking (most songs queued, longest streak,
     most-skipped songs).
2. **Ops**
   - `/stats` (OPS-01) — an owner-only Discord dashboard (today's commands, songs, AI queries,
     images, errors) **+ folded-in Gemini quota** (OPS-03).
   - Rich health/observability (OPS-02) — degraded-state on the existing public `/health`, with the
     **rich bot-state metrics surfaced in `/stats`** (not the public endpoint).

It does NOT add: a web config dashboard (locked Out of Scope — `/stats` covers the owner need),
new audio/AI capabilities, RAG/Vision, or new data-collection. It clarifies HOW to build the five
SOCIAL/OPS requirements; it does not expand them.

> **⚠ Two roadmap-staleness flags carried into planning (do not treat ROADMAP success criteria
> literally):**
> 1. **Hosting pivoted** Oracle A1 → **Koyeb + Neon** in Phase 5 (05-CONTEXT.md K-01). ROADMAP
>    Phase-8 success criterion #5 still says "**Oracle** CPU/memory" — re-interpret as Koyeb/Neon
>    (resolved by D-30: link the platform dashboard, don't scrape host metrics).
> 2. **Phase 6 (instrumentation) is NOT built.** ROADMAP criterion #4 implies the health endpoint
>    reports Phase-6 pipeline metrics (cache-hit rate, time-to-first-audio). Those don't exist yet —
>    build OPS-02/03 with state available today and leave hooks (D-29). Same call Phase 7 made on its
>    parked deps; Phase 8 does NOT block on Phase 5 (PARKED) or Phase 6 (not started).

</domain>

<decisions>
## Implementation Decisions

### `/roast @user` (SOCIAL-01)
- **D-01:** Output is **public** — everyone in the channel sees the roast; public shaming is the point.
- **D-02:** **Anyone is targetable — Dex adapts** to the edge cases:
  - self-roast → a special "roasting yourself, bleak" line;
  - the bot / other bots → Dex turns it around;
  - a **zero-history target** → a "who even are you" no-data roast (does NOT error/decline).
- **D-03:** Roast data is **global per-user** (across all servers) — reuse `get_user_summary()` as-is.
  Matches the Phase-7 favorites/playlists global-per-user precedent (07-CONTEXT D-18/D-24).
- **D-04:** **30s per-user cooldown** (per invoker) — protects the shared 15-RPM Gemini budget without
  feeling stingy. (No per-target limit — see Deferred.)
- **D-05:** Gemini call at **priority-1** (user command, waits ≤60s) with the **guaranteed template
  fallback** — never let a rate limit block the roast (PROJECT.md Gemini-first-with-fallback rule).
- **D-06:** **Tone = harsher than ambient, with guardrails.** It was explicitly asked for, so it hits
  harder than a random voice-join roast, but stays about the target's **music behavior** — no slurs,
  no protected-class content, nothing genuinely cruel. The CLAUDE.md "dial back for serious/emotional"
  rule still overrides.
- **D-07:** **Prompt = reuse `DEXTER_SYSTEM_PROMPT` + a "roast this user" scenario** (the
  `cogs/events.py:92 _generate_ambient_roast` path), passing the target's `get_user_summary()` as
  context. Keeps the voice consistent and respects `MAX_AI_RESPONSE_LENGTH=500`. (Not a separate
  dedicated prompt — see Deferred.)
- **D-08:** `/roast` **respects the mood system** (normal → tired → exhausted → fumes) like `/ask` —
  reuse the existing mood injection so a tired Dex roasts shorter/lazier.
- **D-09:** `/roast` lives in **`cogs/ai.py`** — it's a Gemini slash command like `/ask` (cooldown +
  mood + `gemini_service` already wired there).

### `/leaderboard` (SOCIAL-02)
- **D-10:** Ranking is **per-server (guild-scoped)** — matches the success criterion "server ranking."
- **D-11:** **One embed, three sections:** most songs queued · longest streak · most-skipped songs.
- **D-12:** **"Most-skipped" = songs (titles)** — rank tracks by skip count via
  `song_history.was_skipped` grouped by title, guild-scoped. (The roadmap wording "most-skipped songs.")
- **D-13:** **Top 5 per section + one dry Dexter commentary line** (lowercase, on-brand — roast the
  leader / pity the bottom).
- **D-14:** **Data source = per-guild aggregates from `song_history` (filtered by `guild_id`).** The
  GLOBAL `user_profiles.total_songs_queued` counter CANNOT be used for a per-guild "most queued" board —
  songs/skips must be aggregated from `song_history`. **New aggregate queries are required.**
- **D-15:** **Streak-section wrinkle (resolved):** streaks live GLOBALLY on `user_profiles`
  (`current_streak`/`longest_streak`) and are **not guild-attributable**. Resolution: the streak section
  ranks **users who are active in this guild** by their **global** streak. (Optionally note the
  global-streak caveat in the embed/commentary.)
- **D-16:** **Ties → secondary sort by earliest-achieved** (oldest `first_seen_at`) — the OG ranks higher.
- **D-17:** **Empty / brand-new server → a dry personality empty-state line** ("nobody's done anything
  worth ranking yet"), not an empty embed.
- **D-18:** **Exclude zeros** — need ≥1 queued song to rank; the most-skipped board needs ≥1 skip. Keeps
  the board meaningful, not padded with inactive users.
- **D-19:** Output is **public** (shareable / competitive / screenshot-worthy).
- **D-20:** `/leaderboard` lives in **`cogs/ops.py`** (new cog).

### `/stats` (OPS-01) + Gemini quota (OPS-03)
- **D-21:** **Owner-only**, via the inline `await bot.is_owner(interaction.user)` check (the `/sync`
  pattern at `bot.py:434`). No app_commands decorator exists.
- **D-22:** **Today-only window** — today's `bot_daily_stats` row (commands, songs, AI queries, images,
  errors). (Not a 7-day trend — see Deferred.)
- **D-23:** **Add a `total_errors` column to `bot_daily_stats`** and increment it at the existing
  error-log site (`utils/logger.py log_to_discord` / exception handlers), surfaced as "recent errors."
  This is the **only net-new persistence** this phase — mirror the `increment_daily_stat()` upsert.
- **D-24:** **Quota folded into the `/stats` embed** (one owner dashboard, per success criterion "via the
  `/stats` embed"): **Gemini RPM headroom** (current requests-in-window `X/15` from the limiter) **+
  today's image-cap usage** (`image_generation_log` vs `MAX_IMAGES_PER_USER_PER_DAY`). Needs a small
  **public getter on the rate limiter** (its `_timestamps` deque is private today).
- **D-25:** `/stats` is **bot-wide / global** (today's `bot_daily_stats` is keyed by date globally) — an
  owner dashboard, not per-guild.
- **D-26:** `/stats` lives in **`cogs/ops.py`**.

### Rich health & observability (OPS-02)
- **D-27:** **Public `/health` stays minimal.** The rich bot-state metrics (shard status, guild count,
  voice/queue counts, uptime, DB pool) live **only in the owner-only `/stats` embed**, NOT on the public
  HTTP endpoint. This honors the Phase-5 K-02 security decision (no internal state exposed publicly).
- **D-28:** **`/health` gains a degraded-state body but stays HTTP 200.** Return
  `{"status":"degraded","reasons":[...]}` when the DB is unreachable / the gateway isn't ready, but never
  return non-200 — that would risk Koyeb kill-looping the container (and Neon's 5-min scale-to-zero could
  trip it). Healthchecks.io / UptimeRobot can alert on the body; the bot self-heals.
- **D-29:** **Build OPS-02/03 with state that exists today** (shards, guilds, queues, uptime, DB pool,
  Gemini RPM, daily stats). Leave clean hooks so **Phase-6 pipeline metrics** (cache-hit rate,
  time-to-first-audio) slot in later. Does NOT block on Phase 6.
- **D-30:** **Host CPU/mem via a linked Koyeb/Neon dashboard** — no in-process `psutil` scraping. Matches
  the success criterion "or a linked external dashboard" and avoids fragile self-measurement on a tiny
  worker. (Resolves the stale "Oracle CPU/memory" wording.)
- **D-31:** A **shared metrics-gatherer helper** feeds both `/stats` and the `/health` degraded check
  (single source of truth for bot-state). Exact home/signature → planning (likely in `cogs/ops.py` or a
  small util).

### Cross-cutting — personality & error states
- **D-32:** All new user-facing text uses **Dexter's voice** — lowercase, dry, one-emoji-max — via
  `personality/responses.py` / `roasts.py` template pools with a guaranteed fallback (Phase-3 pattern).
- **D-33:** **Error / empty / no-op responses are ephemeral** (only the actor sees them); successful
  public actions (`/roast`, `/leaderboard`) stay public. (Consistent with 07-CONTEXT D-30.)

### Claude's Discretion
Left to research/planning, consistent with the decisions above:
- Exact `total_errors` column definition + any new index for the leaderboard aggregates (D-23/D-14).
- Exact SQL for the per-guild leaderboard aggregates (most-queued, most-skipped) and the guild-active
  global-streak ranking query (D-14/D-15).
- The rate-limiter public getter signature (e.g. `rpm_usage()` / `rpm_headroom()`) (D-24).
- Embed field layout / ordering for `/stats` and `/leaderboard`; `COLOR_*` choices.
- Slash-command names/parameters; whether `/roast` aliases or `@user` is required.
- Roast scenario wording + the self / bot / zero-history special-case lines (D-02/D-07).
- The shared metrics-gatherer helper's exact home + signature (D-31).
- Whether ties need a tertiary sort beyond `first_seen_at` (D-16).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` §"Phase 8: Social & Ops" — goal + 5 success criteria. ⚠ Criterion #4 assumes
  Phase-6 instrumented health metrics (not built → D-29) and #5 says "**Oracle** CPU/memory" (hosting is
  now Koyeb+Neon → D-30). Re-interpret accordingly.
- `.planning/REQUIREMENTS.md` — **SOCIAL-01, SOCIAL-02, OPS-01, OPS-02, OPS-03** (the 5 testable
  statements) + Out-of-Scope (web config dashboard deferred; `/stats` covers the owner need).
- `CLAUDE.md` — personality rules (lowercase / one-emoji-max / accuracy-first / dial-back-for-serious),
  mood system, global Gemini 15-RPM limiter + priority tiers, `bot_daily_stats` schema, slash-only +
  3s-defer convention, owner-only convention, embed conventions.

### Prior context (decisions Phase 8 inherits)
- `.planning/phases/05-ship-it-live/05-CONTEXT.md` — **K-02** (the minimal `/health` rationale +
  security; the **rich** health endpoint was explicitly deferred to *this* phase), **K-09**
  (Healthchecks.io dead-man ping, `HEALTHCHECK_URL`), **K-01** (Koyeb+Neon substrate — supersedes the
  PROJECT.md "Oracle" hosting decision).
- `.planning/phases/07-player-ux-filters/07-CONTEXT.md` — per-user **global** data precedent
  (favorites/playlists D-18/D-24), ephemeral-error / public-success pattern (D-30), `LibraryCog` + cog
  conventions.
- `.planning/PROJECT.md` — Key Decisions (Gemini-first with template fallback; global rate limiter with
  priority tiers; current_index no-pop queue). ⚠ Its "Hosting → Oracle A1" row is SUPERSEDED by Phase-5
  K-01 (Koyeb+Neon).
- `.planning/STATE.md` — accumulated decisions; Phase 5 live-deploy **PARKED**; no pending todos.

### Code Phase 8 builds on
- `personality/roasts.py` — roast template pools (voice-join/leave, late-night, repeat-song, milestone);
  add `/roast` lines incl. the self / bot / zero-history special cases.
- `personality/prompts.py` — `DEXTER_SYSTEM_PROMPT` + `build_chat_prompt()` (reused for the roast
  scenario, D-07).
- `personality/responses.py` — templated response pools (home for new `/stats`, `/leaderboard`, and
  empty-state lines).
- `cogs/events.py:92` `_generate_ambient_roast` — the Gemini + template-fallback pattern `/roast`
  mirrors (but at priority-1, user-invoked).
- `cogs/ai.py` — **home for `/roast`** (D-09); reuse its `/ask` cooldown + mood + `gemini_service` wiring.
- `cogs/music.py:835` `_get_top_artist`, `:862` `_build_roast_line`, `:956` repeat-song + milestone
  checks — existing roast-data helpers and the song-stats increment sites.
- `models/user_profile.py:8` `get_user_summary()` — the target's taste summary (top 5 artists +
  most-repeated song) for `/roast`.
- `database.py` — `bot_daily_stats` (`:111` schema, `:269` `increment_daily_stat`, `:348`
  `get_daily_command_count`); `user_profiles` / `song_history` (`idx_history_guild`) /
  `user_artist_counts`; existing aggregate helpers. **ADD** the `total_errors` column (D-23) + the new
  per-guild leaderboard aggregate queries (D-14/D-15).
- `services/gemini.py:34` `_RateLimiter` (sliding-window deque) — **ADD** a public RPM-usage/headroom
  getter (D-24); `chat()` is the `/roast` call path.
- `bot.py:197` `_run_health_server` — enrich with the degraded body (still 200) per D-28; `:434` `/sync`
  owner-check pattern (D-21); `:80` `owner_id` wiring.
- `utils/embeds.py` — embed builders + `COLOR_*` constants; **ADD** `/leaderboard` and `/stats` embeds.
- `utils/logger.py` `log_to_discord` — the error-log site where `total_errors` increments (D-23).
- `config.py` — single-file constants; add roast cooldown, leaderboard top-N, any thresholds.

> **Staleness note:** `.planning/codebase/*.md` maps are dated ~2026-06-01 and predate the Phase-4
> SQLite→Postgres migration and the Phase-5 Koyeb+Neon pivot. Treat `CLAUDE.md` + actual source as
> authoritative on persistence (asyncpg) and hosting (Koyeb+Neon).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Ambient-roast machinery** (`cogs/events.py:92` + `cogs/music.py:862`) — Gemini call + scenario +
  `get_user_summary()` + guaranteed template fallback. `/roast` is the same shape, just user-invoked at
  priority-1 (D-05/D-07).
- **`get_user_summary()`** (`models/user_profile.py:8`) — already returns total songs + top 5 artists +
  most-repeated song; the exact context `/roast` needs (D-03).
- **`bot_daily_stats` + `increment_daily_stat()`** (`database.py:111/269`) — the upsert pattern to mirror
  for `total_errors` (D-23) and the source for `/stats` (D-22).
- **`_RateLimiter`** (`services/gemini.py:34`) — `len(_timestamps)` already encodes current RPM; only a
  public getter is missing (D-24).
- **Minimal `/health` server** (`bot.py:197`) — extend with degraded logic (D-28); shares a metrics
  helper with `/stats` (D-31).
- **Owner-only check** (`bot.py:434` `/sync`) — `await bot.is_owner(...)` inline pattern for `/stats`
  (D-21).
- **`song_history` + `idx_history_guild(guild_id, queued_at)`** — indexed for the per-guild leaderboard
  aggregates (D-14).
- **Embed builders + `COLOR_*`** (`utils/embeds.py`) — add `/leaderboard` + `/stats` embeds alongside.

### Established Patterns
- All commands are `app_commands` slash commands; cogs reach services via `self.bot.*`; settings live in
  `config.py`; new persistence goes in `SCHEMA_SQL` with async helpers (asyncpg, `CREATE TABLE/ALTER ...
  IF NOT EXISTS`-style idempotency).
- Personality output = Gemini-first with a guaranteed template fallback; lowercase, one-emoji-max.
- Owner-only = inline `bot.is_owner()` (no decorator); 3s-defer for any AI/IO command.

### Integration Points
- **`/roast`** → `cogs/ai.py` (Gemini + cooldown + mood); reads target via `get_user_summary()`.
- **`/leaderboard` + `/stats`** → new `cogs/ops.py`; new per-guild aggregate queries + `total_errors`
  column in `database.py`; embeds in `utils/embeds.py`.
- **Rich health** → `bot.py _run_health_server` (degraded body) + a shared metrics gatherer also used by
  `/stats`.
- **Quota** → public getter on `services/gemini.py _RateLimiter` + `image_generation_log` read; rendered
  in the `/stats` embed.
- **`total_errors`** → increment at `utils/logger.py log_to_discord` / exception handlers.

</code_context>

<specifics>
## Specific Ideas

- `/roast` **deliberately mirrors the events.py ambient-roast machinery** (system prompt + scenario +
  `get_user_summary()` + template fallback) — just user-invoked at priority-1 with a 30s/user cooldown.
- The **"rich health" requirement is satisfied via Discord `/stats`** (owner-only) while the public HTTP
  `/health` stays minimal + degraded — a deliberate security continuation of Phase-5 K-02, not a gap.
- **`total_errors` is the only net-new persistence** this phase; everything else reads existing tables.
- The leaderboard's **per-guild song/skip aggregates** are genuinely new SQL; the **streak board reuses
  global streaks filtered to guild-active users** (D-15) because streaks aren't guild-attributable.

</specifics>

<deferred>
## Deferred Ideas

Considered during discussion, intentionally out of this phase:

- **Most-skipped USERS board** (biggest skippers) — chose songs (D-12).
- **`/stats` 7-day trend / sparkline** — chose today-only (D-22).
- **Rich metrics on the public HTTP endpoint / token-gated `/metrics`** — chose Discord-only (D-27).
- **Non-200 degraded health (platform auto-restart)** — chose 200 + degraded body (D-28).
- **In-process `psutil` host metrics** — chose linked dashboard (D-30).
- **Phase-6-instrumented pipeline metrics** (cache-hit rate, time-to-first-audio) in `/stats`/`/health` —
  hooks left, deferred to after Phase 6 (D-29).
- **Per-target roast cooldown / anti-harassment limit** — chose per-user 30s only (D-04).
- **Maximum-savage roast / dedicated roast prompt** — chose harsher-with-guardrails + reuse the existing
  system prompt (D-06/D-07).
- **Switchable leaderboard category view (dropdown/buttons)** — chose a single 3-section embed (D-11).

None of these are roadmap items — capture for a future milestone if desired.

### Sequencing note (for the planner)
Phase 8's ROADMAP dependencies are Phase 5 (live deploy — **PARKED**) and Phase 6 (instrumentation —
**NOT started**). **Neither blocks Phase 8 implementation:** every command queries existing Postgres data
and reuses existing roast/Gemini infra, and the health/quota surfaces are built from state available today
(D-29). Button/interaction testing isn't needed (no new persistent views). Build now; slot Phase-6
metrics in later.

None — discussion stayed within phase scope (the two staleness flags are re-interpretations of the same
scope, not additions).

</deferred>

---

*Phase: 8-Social & Ops*
*Context gathered: 2026-06-19*
