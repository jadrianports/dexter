---
phase: 19-onboarding-admin-setup
plan: 03
subsystem: bot-behavior
tags: [discord-py, guild-lifecycle, ambient-surfaces, guild-config, onboarding]

# Dependency graph
requires:
  - phase: 19-onboarding-admin-setup
    provides: "plan 01 — insert_guild_config_if_absent + configure_guild_first_time/redesignate_guild_channel/set_ambient_roasts_enabled/set_vision_roasts_enabled database.py helpers"
  - phase: 19-onboarding-admin-setup
    provides: "plan 02 — AmbientSurface enum, surface-keyed decide_ambient_channel/resolve_ambient_channel, should_welcome_guild, GuildConfigService.home_guild_id"
provides:
  - "bot.py::on_guild_join — insert-if-absent, welcome iff should_welcome_guild(inserted_row=), always owner-notify (ONBOARD-01/05)"
  - "bot.py::on_guild_remove — owner notice + cache evict, zero DB writes (D-12)"
  - "bot.py::_post_guild_welcome — try/except-wrapped welcome send via resolve_announce_channel, never crashes the join (D-13)"
  - "bot.py::_build_guild_notice_embed — T-19-02-safe join/remove owner-notice embed builder (D-16)"
  - "bot.py boot backfill loop in _initialize_once (after seed_home_guild, before queue-persistence wiring) — welcomes guilds invited while offline exactly once (D-14/D-15)"
  - "bot.py::_post_startup_messages narrowed to home-guild-only (D-23); idle-loneliness resolve declares surface=AmbientSurface.PRESENCE"
  - "\"cogs.admin\" added to the _initialize_once cog-load tuple (file created next in 19-04)"
  - "personality/roasts.py::WELCOME_MESSAGES + WELCOME_SETUP_HINT"
  - "cogs/music.py::_post_music_roast routed through resolve_ambient_channel(surface=AmbientSurface.ROAST) — closes the live CONFIG-04 music-roast hole (Pitfall 1)"
affects: [19-04, 20-owner-control-plane-rate-observability, 21-memory-scoping-guild-data-lifecycle]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "should_welcome_guild(inserted_row=...) as the ONLY welcome-decision signal — never bot.guild_config.get() / a cache-miss check — used identically by on_guild_join and the boot backfill loop"
    - "Boot backfill loop placed as a hard-ordered insertion point (after seed_home_guild, before queue-persistence wiring) so the home guild is never mistakenly welcomed as configured=false"

key-files:
  created: []
  modified:
    - bot.py
    - personality/roasts.py
    - cogs/music.py

key-decisions:
  - "_post_guild_welcome uses resolve_announce_channel (best-effort fallback chain), never resolve_ambient_channel — a brand-new guild has no configured row yet, so the strict resolver would always return None on join"
  - "on_guild_join defensively returns (no insert, no welcome, no notice) when bot.pool/bot.guild_config aren't yet attached — a join racing _initialize_once is picked up by the boot backfill loop on the next successful init pass instead of raising into discord.py's default event-error handler"
  - "The boot backfill's per-guild insert is wrapped in its own try/except with continue (matches the restore_queues per-guild-continue discipline) so one guild's transient insert failure never aborts backfill for the rest of bot.guilds"
  - "\"cogs.admin\" was added to the cog-load tuple now (this plan) even though cogs/admin.py doesn't exist until 19-04 — this is per the plan's explicit sequencing; no test in the current suite actually calls _initialize_once/load_extension against the real module list, so this is a safe, deliberate mid-sequence gap that closes when 19-04 lands"

patterns-established:
  - "Owner-facing lifecycle notice embeds render attacker-influenceable strings (guild.name, owner display name) as PLAIN field values and numeric ids (guild.id/owner_id) in backtick inline-code spans (T-19-02) — the pattern any future guild-lifecycle embed should copy"

requirements-completed: [ONBOARD-01, ONBOARD-05]

# Metrics
duration: 20min
completed: 2026-07-10
---

# Phase 19 Plan 03: Guild Lifecycle Glue Summary

**`on_guild_join`/`on_guild_remove` handlers plus a boot backfill loop that welcomes guilds invited while Dexter was offline exactly once, a home-guild-only startup message, and the live `_post_music_roast` fix that finally closes the CONFIG-04 ambient-roast hole in `cogs/music.py`.**

## Performance

- **Duration:** ~20 min
- **Completed:** 2026-07-10T19:59:27+08:00
- **Tasks:** 3
- **Files modified:** 3 (bot.py, personality/roasts.py, cogs/music.py)

## Accomplishments
- Added `bot.py::on_guild_join` (insert-if-absent, welcome only when `should_welcome_guild(inserted_row=row)` says the insert genuinely inserted, always owner-notify) and `bot.py::on_guild_remove` (owner notice + cache evict, zero DB writes, D-12), backed by two new reusable helpers: `_post_guild_welcome` (try/except-wrapped send via `resolve_announce_channel`, never crashes the join — D-13) and `_build_guild_notice_embed` (T-19-02: `guild.name`/owner tag rendered plain, `guild.id`/`owner_id` backtick-wrapped).
- Added `WELCOME_MESSAGES` (in-persona, no placeholders) and `WELCOME_SETUP_HINT` (plain functional line naming `/setup channel`) to `personality/roasts.py`.
- Inserted a boot backfill loop into `_initialize_once`, hard-ordered strictly after the `seed_home_guild` call and before the queue-persistence wiring (D-14 constraint 1), that walks every `bot.guilds` entry, calls `insert_guild_config_if_absent`, and welcomes only the guilds where `should_welcome_guild` returns true (D-14 constraint 2) — with a per-guild try/except-continue and one owner summary embed naming every guild welcomed (D-15).
- Narrowed `_post_startup_messages` to the home guild only (D-23, via `bot.guild_config.home_guild_id` + `surface=AmbientSurface.PRESENCE`), added the same `surface=` to the idle-loneliness resolve (stays per-guild), and added `"cogs.admin"` to the cog-load tuple.
- Fixed the live CONFIG-04 gap in `cogs/music.py::_post_music_roast`: repeat-song and both milestone roasts now resolve through `resolve_ambient_channel(guild, surface=AmbientSurface.ROAST)` instead of the pre-Phase-18 `_get_text_channel` fallback, so an unconfigured guild stays silent instead of roasting in whatever channel `/play` last ran.

## Task Commits

Each task was committed atomically:

1. **Task 1: on_guild_join / on_guild_remove handlers + welcome copy + owner notice (D-10/12/13/16)** - `70e8fff` (feat)
2. **Task 2: Boot backfill after seed_home_guild + home-guild-only startup + idle PRESENCE + cog registration** - `ea0ae6e` (feat)
3. **Task 3: Close the live CONFIG-04 music-roast hole in _post_music_roast (Pitfall 1)** - `8adee8c` (feat)

## Files Created/Modified
- `bot.py` - `on_guild_join`, `on_guild_remove`, `_post_guild_welcome`, `_build_guild_notice_embed`; boot backfill loop in `_initialize_once`; home-guild-only `_post_startup_messages`; `surface=AmbientSurface.PRESENCE` on idle-loneliness resolve; `"cogs.admin"` added to the cog-load tuple
- `personality/roasts.py` - `WELCOME_MESSAGES`, `WELCOME_SETUP_HINT` (+ `__all__` entries)
- `cogs/music.py` - `AmbientSurface` import; `_post_music_roast` routed through `resolve_ambient_channel(surface=AmbientSurface.ROAST)`

## Decisions Made
- `_post_guild_welcome` deliberately calls `resolve_announce_channel` (the best-effort 4-step fallback), not `resolve_ambient_channel` — a brand-new guild's `guild_config` row is always `configured=false` at the moment of welcome, so the strict resolver would return `None` every time; the best-effort resolver is the one Phase 18 built specifically for this future caller.
- `on_guild_join` defensively no-ops (no insert/welcome/notice) if `bot.pool`/`bot.guild_config` aren't attached yet, trusting the boot backfill loop to pick up that guild on the next successful `_initialize_once` pass rather than adding its own retry logic.
- Added `"cogs.admin"` to the cog-load tuple in this plan even though `cogs/admin.py` isn't created until 19-04 — this is what the plan explicitly specifies; verified no test in the current suite exercises the real `_initialize_once` cog-loading loop (a static string presence check only), so this ordering is safe until 19-04 lands.

## Deviations from Plan

None — plan executed exactly as written. One incidental fix surfaced by the plan's own verification gate: `ruff format --check` flagged two lines in `bot.py` (a wrapped `_build_guild_notice_embed` signature and a wrapped `log.warning` call in `on_guild_join`) that exceeded the configured line width; `ruff format bot.py` reformatted them in place with zero behavior change, folded into the Task 3 commit alongside its own file.

## Issues Encountered
- The `_post_music_roast` docstring initially pushed the `resolve_ambient_channel(...)` call past the plan's 400-character verification window (`s[i:i+400]`); shortened the docstring twice until the automated verify's substring check passed. No functional change — purely a docstring-length adjustment to satisfy the plan's own literal acceptance check.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Plan 04 (`cogs/admin.py` `/setup` command surface) can now load cleanly — its cog-registration entry already exists in `_initialize_once`'s cog-load tuple from this plan, and it can call `GuildConfigService.configure_guild_first_time`/`redesignate_guild_channel`/`set_ambient_roasts_enabled`/`set_vision_roasts_enabled` directly (all four already write-then-invalidate the cache per 19-02).
- Full suite green: 936 passed, 118 skipped, 0 failed (`pytest -q`). `ruff check .` and `ruff format --check .` both clean repo-wide after the Task 3 format fix.
- All three of this plan's must-have truths are satisfied: joining inserts a `configured=false` row and attempts an in-persona welcome that never crashes the join; a guild invited while offline is welcomed exactly once on the next boot, keyed on the insert result; the startup message is home-guild-only while idle-loneliness stays per-guild; repeat-song/milestone roasts route through the config seam; the owner receives a join/remove notice with zero DB writes on remove.
- Untested-by-design per D-26 (Discord/process glue) — verified by structural review, the automated per-task greps, and a green full suite. The 3 live-Discord Manual-Only checks (real join/remove notice appearance, boot-backfill welcome on a genuinely-new guild, home-guild-only startup after a restart) remain parked behind the residential host, matching the precedent set by every prior v1.3/v1.4 phase's Human-UAT deferral.

---
*Phase: 19-onboarding-admin-setup*
*Completed: 2026-07-10*
