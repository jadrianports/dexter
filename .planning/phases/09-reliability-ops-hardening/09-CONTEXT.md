# Phase 9: Reliability & Ops Hardening - Context

**Gathered:** 2026-06-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Dexter can no longer fail silently. This phase hardens the existing v1.1 surfaces — it does
**not** add features:

- `/health` tells the truth (degraded status when a critical subsystem is down)
- Fire-and-forget background tasks surface their exceptions instead of vanishing
- Startup command-tree sync recovers instead of hanging; the `on_ready` re-entry guard can never
  permanently wedge
- Slow DB queries hit an enforced timeout instead of blocking the bot
- Transient YouTube search/extract failures self-heal within a bounded retry budget

Covers REL-01 … REL-06. No new commands, no new user-facing capabilities — this is robustness on
top of what Phases 5–8 already shipped. Test extraction of this logic is **Phase 10's** job, not
this phase's (Discord/process glue stays untested-by-design here).

</domain>

<decisions>
## Implementation Decisions

### REL-01 — Truthful `/health`
- **D-01:** `/health` returns a **configurable** HTTP status. Add an env/config flag
  `HEALTH_STRICT_STATUS` (default **`true`**). When strict + degraded → return **HTTP 503** with
  the degraded JSON body; when healthy → 200. When the flag is `false` → restore the legacy
  always-200 behavior (escape hatch for any future kill-on-non-200 host).
  - **Why:** REL-01 literally wants non-200; external monitors (UptimeRobot / a future Pi) only
    catch outages when the *status code* moves, not a body-only flag. The flag preserves the D-28
    scar (Koyeb free-tier treated non-200 as "kill the container" → Neon restart cascade) as a
    one-line fallback. 24/7 cloud is parked, so strict-503 is safe on the PC today.
- **D-02:** The "critical / degraded" set = **MusicCog-failed-to-load + DB-unreachable +
  gateway-not-ready**. DB and gateway checks already exist in `gather_bot_metrics`
  (`cogs/ops.py`); add a MusicCog-load check.
  - **Why:** MusicCog is the only *required* feature cog. AI/Imagine cogs are **excluded** — they
    load conditionally only when `GEMINI_API_KEY` is set (mirrored in both `on_ready` and
    `first_run`), so including them would emit a false "degraded" on a key-less run.

### REL-02 — Background-task failure visibility
- **D-03:** Every fire-and-forget task (`_prefetch_next_track`, `_post_auto_lyrics`, ambient
  roasts, and any other `asyncio.create_task` / `tasks.loop` background work) attaches a
  **done-callback** that logs the exception to `dexter.log` **and** posts it to
  `ERROR_LOG_CHANNEL_ID` (already configured and used for yt-dlp/Gemini failures).
- **D-04:** Discord-channel posting is **rate-limited / deduped** so a recurring failure (e.g.
  prefetch crashing every track) cannot flood the error channel. Logs still record every
  occurrence; only the channel posts are throttled (mirror the existing yt-dlp self-update
  throttle pattern — a monotonic window and/or per-error-signature collapse).

### REL-03 / REL-04 — Startup sync + un-wedgeable `on_ready`
- **D-05:** Command-tree sync (`bot.tree.sync`) is wrapped in a **timeout**. On failure/timeout:
  log it, **come online anyway** (already-registered slash commands keep working — sync only
  refreshes the registered command *set*), then **retry the sync in the background**. The bot is
  never blocked from being usable.
- **D-06:** `_initialize_once()` is wrapped in `asyncio.wait_for` with a generous timeout. On
  timeout it is treated exactly like a raised failure (log → clean up the pool → reset the guard)
  so the next ready event retries. This closes the REL-04 hole: today `_ready_initializing` only
  resets in `finally` on a *raised* exception, so a true *hang* (no exception) would never run
  `finally` and would permanently block all future ready handling.

### REL-05 — DB query timeout
- **D-07:** Enforce a **pool-wide default `command_timeout`** on the asyncpg pool (cheap, covers
  every query as a floor). Any command whose query times out shows a **personality-flavored
  "that took too long, try again" error** rather than hanging — matches the always-respond ethos.
  Per-query timeouts on known-heavy queries are allowed on top if useful, but the pool default is
  the required floor.

### REL-06 — YouTube search/extract self-heal
- **D-08:** On transient `search()`/`extract()` failure: **quick bounded retry first** (1–2x,
  short backoff — most blips are network/transient), and **only if that still fails**, fall back
  to the existing throttled **yt-dlp self-update + retry** path that `download()` already uses.
  - **Why:** fast recovery for network blips without paying the slow update step every time, while
    still self-healing a real yt-dlp breakage the way `download()` does. Reuse
    `update_ytdlp()` + the `_UPDATE_THROTTLE_SECONDS` throttle already in `services/youtube.py`.

### Claude's Discretion
- Exact timeout *values* (sync timeout, `_initialize_once` watchdog, pool `command_timeout`,
  retry backoff) — pick sensible defaults during planning/research; these are tuning knobs, not
  product decisions.
- Exact dedup mechanism for D-04 (time window vs error-signature set vs both).
- Whether REL-05 adds per-query timeouts on top of the pool default (pool default is the floor).
- Per-task choice of done-callback helper shape for D-03 (a shared utility vs inline) — keep it
  DRY.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope / requirements
- `.planning/ROADMAP.md` § "Phase 9: Reliability & Ops Hardening" — goal, success criteria, the
  5 suggested plan splits (09-01 … 09-05)
- `.planning/REQUIREMENTS.md` § "Reliability & Ops Hardening (Phase 9)" — REL-01 … REL-06 wording
- `.planning/STATE.md` — accumulated decisions; Phase 9 is the first v1.2 phase

### Code the phase modifies (existing surfaces to harden)
- `bot.py` — `_run_health_server()` / `health()` handler (~199, the always-200 D-28 logic to make
  configurable); `on_ready()` + `_initialize_once()` (~255–290, the guard + watchdog work);
  `bot.tree.sync` call sites (`_initialize_once` ~472, `first_run` ~638)
- `cogs/ops.py` — `gather_bot_metrics()` (~52, the degraded-reasons producer; add MusicCog-load
  check here so both `/health` and `/stats` see it)
- `cogs/music.py` — `_prefetch_next_track` and other fire-and-forget tasks (done-callbacks)
- `cogs/events.py` — ambient-roast background tasks; `_post_auto_lyrics` (done-callbacks)
- `services/youtube.py` — `search()`/`extract()` (~103/128) self-heal; reuse `update_ytdlp()`
  (~25) + `_UPDATE_THROTTLE_SECONDS` throttle pattern already in `download()` (~203–226)
- `database.py` — asyncpg pool creation site (pool-wide `command_timeout`)
- `config.py` — add `HEALTH_STRICT_STATUS` (and any timeout constants)

### Reference (note: partially stale — verify against live code)
- `.planning/codebase/CONCERNS.md` — dated 2026-06-01 (pre-v1.1); several entries (SQLite/WAL,
  "yt-dlp no auto-update") are **already resolved**. Use only as a pointer to fragile areas, not
  as current truth.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `gather_bot_metrics(bot)` (`cogs/ops.py`): already returns `degraded_reasons` for DB + gateway
  and is already imported at request-time by the `/health` handler. REL-01 extends this dict
  (add MusicCog-load) rather than building a new health path.
- `update_ytdlp()` + `_last_ytdlp_update` / `_UPDATE_THROTTLE_SECONDS` (`services/youtube.py`):
  the throttled self-update + retry-once pattern `download()` uses — REL-06 reuses it as the
  *fallback* tier, and REL-04's throttle ethos informs D-04's channel-post rate limiting.
- `ERROR_LOG_CHANNEL_ID` (config) + existing error-channel posting for yt-dlp/Gemini failures —
  REL-02 reuses this destination.

### Established Patterns
- `on_ready` one-time-init guard: `_ready_done` (set only after success) + `_ready_initializing`
  (reset in `finally`). D-06's watchdog plugs the hang-without-exception gap in this exact pattern.
- Function-scope imports in the `/health` handler avoid circular imports at module load — keep
  this when touching the handler.
- Neon-tuned pool: `ssl='require'`, `statement_cache_size=0`, 240s lifetime (K-04). D-07's
  `command_timeout` is an additive pool kwarg — must not disturb these.
- Personality-first user-facing errors with template fallback — D-07's timeout message follows it.

### Integration Points
- `/health` HTTP status (D-01) is read by external monitors (UptimeRobot / future Pi host).
- Done-callbacks (D-03) connect background tasks → logger + Discord error channel.
- Pool `command_timeout` (D-07) is set once at pool creation, applies to every query helper in
  `database.py`.

</code_context>

<specifics>
## Specific Ideas

- The REL-01 ↔ D-28 tension is the defining decision of this phase: the current `/health` is
  *intentionally* always-200 to survive Koyeb's kill-loop. The flag resolves "be honest now
  (PC/parked)" vs "stay safe if we ever return to a strict cloud health-checker."
- User explicitly wants real-time failure visibility in Discord (not just log-tailing on the PC),
  but not at the cost of channel spam — hence logs-always + throttled-channel-posts.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (Test extraction of this hardening logic is already
scoped as Phase 10; RAG memory as Phase 11; richer music/UX as Phase 12.)

</deferred>

---

*Phase: 9-Reliability & Ops Hardening*
*Context gathered: 2026-06-26*
