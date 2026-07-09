---
phase: 18-per-guild-config-foundation-ci-gate
plan: 05
subsystem: infra
tags: [discord.py, asyncpg, guild-config, boot-sequence]

# Dependency graph
requires:
  - phase: 18-per-guild-config-foundation-ci-gate (plan 18-04)
    provides: "services/guild_config.py::GuildConfigService (load_all, seed_home_guild, resolve_ambient_channel, resolve_announce_channel)"
provides:
  - "bot.guild_config attribute constructed + cache-loaded at boot in _initialize_once"
  - "Idempotent home-guild seed from config.DEXTER_CHANNEL_ID (CONFIG-05)"
  - "bot.py's two ambient call sites (startup message, idle-loneliness) now resolve through the strict, cache-only resolve_ambient_channel"
  - "bot.py::_resolve_dexter_channel deleted — the old 4-step fallback chain no longer lives in bot.py"
affects: [19-onboarding-admin-setup, 20-owner-control-plane-rate-observability]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Unconditional service construction (no external-key guard) mirroring the existing MemoryService wiring shape, inserted right after the log_to_discord helper is defined so fail-closed errors can reach the error channel"
    - "Silent INFO skip on missing/unresolvable bootstrap config, never a raise — same 'boring Dexter over broken Dexter' discipline as Phase 17's vision silent-skip"

key-files:
  created: []
  modified:
    - bot.py

key-decisions:
  - "Boot-seed guard uses getattr(_seed_channel, 'guild', None) rather than a bare .guild access, since bot.get_channel can in principle return a channel type without a .guild attribute — treated identically to a None channel (silent INFO skip)"
  - "CONFIG-02/03/04/05 requirements are shared across sibling plans in this phase; this plan's slice covers only bot.py's two call sites + boot wiring — the phase verifier owns confirming full coverage across cogs/events.py (18-06) before marking these requirements complete"

patterns-established:
  - "Boot-time cache-owning services (GuildConfigService) are constructed and load_all()'d immediately after bot.log_to_discord is wired, before any Gemini-gated service block, so a fail-closed load error can still reach the Discord error channel"

requirements-completed: []  # CONFIG-02/03/04/05 are shared across sibling plans (18-04 built the service; 18-06 covers cogs/events.py) — left for the phase verifier to mark complete once all call sites across the phase are confirmed repointed.

# Metrics
duration: 25min
completed: 2026-07-10
---

# Phase 18 Plan 05: Boot Wiring & bot.py Ambient Call-Site Consolidation Summary

**Wired `GuildConfigService` into `bot.py`'s boot sequence with an idempotent home-guild seed, and deleted `_resolve_dexter_channel` in favor of the strict, cache-only `resolve_ambient_channel` at both of bot.py's ambient call sites.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-07-10T05:20:00+08:00 (approx.)
- **Completed:** 2026-07-10T05:38:36+08:00
- **Tasks:** 2 completed
- **Files modified:** 1 (bot.py)

## Accomplishments
- `bot.guild_config = GuildConfigService(bot.pool, bot)` is constructed and `await bot.guild_config.load_all()` runs inside `_initialize_once`, immediately after `bot.log_to_discord` is wired and before the Gemini-guarded services — so a fail-closed `load_all` error can still reach the Discord error channel via the existing `hasattr(self._bot, "log_to_discord")` check inside the service.
- The home-guild seed reads `config.DEXTER_CHANNEL_ID`, resolves it via `bot.get_channel`, and calls `bot.guild_config.seed_home_guild(guild_id=..., ambient_channel_id=...)` only when the channel resolves to a real guild channel. An unset or unresolvable value is a silent `log.info` skip — never a raise, never a boot refusal.
- `bot.py::_resolve_dexter_channel` (the 4-step fallback chain) is deleted entirely; both of bot.py's ambient call sites (`_post_startup_messages`, `idle_check`'s idle-loneliness branch) now call `bot.guild_config.resolve_ambient_channel(guild)` synchronously (no `await`), inside their pre-existing `try/except Exception: log.warning(...)` blocks, unchanged.
- No second `on_ready` was added and no owner-only setter or second-guild write path was introduced (D-13).

## Task Commits

Each task was committed atomically:

1. **Task 1: Boot wiring — construct service, load cache (fail-closed), seed home guild** - `d7008b0` (feat)
2. **Task 2: Delete _resolve_dexter_channel; repoint bot.py's two ambient sites** - `272d9be` (refactor)

## Files Created/Modified
- `bot.py` - Added `GuildConfigService` construction + `load_all()` + home-guild seed block in `_initialize_once`; deleted `_resolve_dexter_channel`; repointed the startup-message and idle-loneliness call sites at `bot.guild_config.resolve_ambient_channel(guild)`.

## Decisions Made
- Used `getattr(_seed_channel, "guild", None)` instead of a bare `.guild` attribute access after the `None` check, so a channel type without a `.guild` attribute (theoretically possible from `bot.get_channel`) degrades to the same silent-skip path as an unresolvable ID, rather than raising `AttributeError`.
- Inserted the new boot-wiring block between `bot.log_to_discord` assignment and the `QueuePersistenceService` construction (rather than after it) — both insertion points satisfy the plan's "after log_to_discord, before the cog-load loop" constraint; this ordering keeps the guild-config construction visually adjacent to the memory/lyrics/log-channel service-wiring block above it.
- Left `requirements-completed` empty in this SUMMARY per the environment note: CONFIG-02/03/04/05 are shared across sibling plans in Phase 18 (18-04 built the service, this plan and 18-06 cover the two call-site families) — deferring the mark-complete decision to the phase verifier once all call sites are confirmed repointed.

## Deviations from Plan

None — plan executed exactly as written, with one verification-script note below (not a code deviation).

### Verification note (not a deviation, no code change)

The plan's Task 1 automated verify script asserts `src.count('async def on_ready') <= 1`. This assertion fails against the current `bot.py` — but not because of anything this plan added. `git diff` confirms zero `on_ready` definitions were added by either task in this plan; the count of 2 is pre-existing: the main `@bot.event async def on_ready()` at module scope, and a second, unrelated `async def on_ready():` nested inside `first_run()` (the `--first-run` CLI-only command-sync-and-exit path, unrelated to the normal boot flow the plan's Pitfall 4 warns about). The actual acceptance criterion — "no second on_ready was added" — is satisfied; the literal script assertion is a false positive against this repo's pre-existing structure. Confirmed via `git diff --unified=0 bot.py | grep "async def on_ready"` returning no matches for either commit.

## Issues Encountered

None beyond the verification-script false positive documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `bot.guild_config` is live at boot for every guild; the home guild continues to behave exactly as before via the idempotent seed.
- bot.py's ambient surface is fully consolidated onto `resolve_ambient_channel`. `cogs/events.py`'s four call sites and two bare-equality gates are out of this plan's scope (18-06, per the phase's file split) — CONFIG-02's "one code path" claim is only complete once that sibling plan lands.
- Full `pytest -q`: 873 passed, 111 skipped, 0 failed — no regression from this plan's changes.
- `ruff check bot.py` and `ruff format bot.py`: clean, no findings.

---
*Phase: 18-per-guild-config-foundation-ci-gate*
*Completed: 2026-07-10*

## Self-Check: PASSED

- FOUND: bot.py
- FOUND: commit d7008b0 (feat(18-05): wire GuildConfigService into boot sequence)
- FOUND: commit 272d9be (refactor(18-05): repoint bot.py ambient sites at resolve_ambient_channel)
- FOUND: .planning/phases/18-per-guild-config-foundation-ci-gate/18-05-SUMMARY.md
