---
phase: 18-per-guild-config-foundation-ci-gate
plan: 04
subsystem: infra
tags: [discord.py, asyncpg, cache, per-guild-config, resolver-seam]

# Dependency graph
requires:
  - phase: 18-02
    provides: database.load_all_guild_configs + database.seed_guild_config_if_absent (guild_config DDL + boot/seed helpers)
  - phase: 18-03
    provides: logic/guild_config.py::decide_ambient_channel + is_ambient_channel (pure D-01 decision seam)
provides:
  - services/guild_config.py::GuildConfigService — the cache-owning I/O tier for per-guild config
  - GuildConfigService.load_all() — one-shot, fail-closed boot cache load (CONFIG-03/D-06/D-07)
  - GuildConfigService.get() — pure cache-only accessor, zero I/O
  - GuildConfigService.seed_home_guild() — idempotent home-guild seed + single-entry cache refresh (CONFIG-05)
  - GuildConfigService.resolve_ambient_channel() — STRICT, synchronous, cache-only resolver (D-01/D-03)
  - GuildConfigService.resolve_announce_channel() — preserved 4-step fallback chain, zero callers this phase (D-02)
affects: [19-onboarding-admin-setup, 20-owner-control-plane-rate-observability, bot.py boot wiring, cogs/events.py ambient dispatch]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cog -> service -> model layering: GuildConfigService constructed unconditionally in bot.py, attached as bot.guild_config, mirroring services/memory.py / services/metrics.py wiring"
    - "Cache-owning service dispatches on a pure logic/ decision function without re-deriving the branch (Phase 10 D-02 convention)"
    - "Two explicitly-named resolvers instead of one function with a boolean flag (D-02) — strict ambient vs best-effort announce"
    - "Fail-closed error handling: any load_all() exception leaves the cache empty and logs, never re-raises into boot"

key-files:
  created:
    - services/guild_config.py
    - tests/test_guild_config_service.py
  modified: []

key-decisions:
  - "resolve_ambient_channel is synchronous (def, not async def) since it is purely a cache read + discord.Guild.get_channel/permissions_for call — no await needed anywhere in its body"
  - "resolve_announce_channel is also synchronous — ported verbatim from the async bot.py/_get_ambient_channel bodies but none of its steps actually await anything (guild.get_channel, permissions_for, and cog/queue attribute lookups are all synchronous), so making it sync matches its real I/O shape and keeps both resolvers symmetric"
  - "Both WARNING branches in resolve_ambient_channel (stale channel, lost send_messages) return None without ever calling _refresh_cache_entry or mutating self._cache — verified explicitly via 'row is before' identity assertions in tests, not just value equality"
  - "load_all()'s except block guards self._bot.log_to_discord behind hasattr(), since the fake-bot test fixture and a genuinely minimal Bot subclass may not have that attribute wired yet at the point GuildConfigService is constructed"

patterns-established:
  - "Spy pool (counts .acquire() calls) as the CONFIG-03 no-round-trip regression test pattern — reusable for any future cache-owning service in this codebase"

requirements-completed: []  # CONFIG-02/03/05 are shared across sibling plans 18-01..18-07; leaving requirement-closure to the phase verifier per environment_notes guidance (conservative to avoid over-claiming a multi-plan requirement)

# Metrics
duration: 16min
completed: 2026-07-10
---

# Phase 18 Plan 04: GuildConfigService Summary

**Built `services/guild_config.py::GuildConfigService` — a boot-loaded, fail-closed, cache-only per-guild config service with two explicitly-named channel resolvers (strict ambient vs. best-effort announce), locked by 9 mock-based tests including a spy-pool no-round-trip regression.**

## Performance

- **Duration:** ~16 min (05:02–05:18 UTC+8, per commit timestamps)
- **Tasks:** 3 (all `type="auto"`, tasks 1-2 marked `tdd="true"`)
- **Files modified:** 2 (both new)

## Accomplishments
- `GuildConfigService(pool, bot)` — cache-owning service constructed unconditionally (no external-key guard), matching the `services/memory.py`/`services/metrics.py` bot-attribute wiring convention.
- `load_all()` fills `self._cache: dict[str, asyncpg.Record]` from `database.load_all_guild_configs` in one round-trip; **fails closed** on any exception — cache stays `{}`, error logs to `dexter.log` + (best-effort) the Discord error channel, boot is never aborted.
- `get(guild_id)` is a pure, zero-I/O cache read.
- `seed_home_guild(*, guild_id, ambient_channel_id)` delegates to `database.seed_guild_config_if_absent` (the `DO NOTHING` idempotent seed) and refreshes exactly that one cache entry via a new `_refresh_cache_entry` push-invalidate helper — the seam Phase 19's `/setup` and Phase 20's kill-switch will reuse.
- `resolve_ambient_channel(guild)` — the STRICT, synchronous resolver (D-01): dispatches on `logic.guild_config.decide_ambient_channel` without re-deriving the `configured` branch; returns `None` silently on a cache miss (no discord lookup at all), and returns `None` + a `log.warning` on a stale/deleted channel or a lost `send_messages` permission (D-03) — **never mutating the cache row** in either skip branch.
- `resolve_announce_channel(guild)` — the preserved 4-step fallback chain (env designation → last-active music channel → system channel → first writable text channel), relocated verbatim from the now-superseded `bot.py::_resolve_dexter_channel` / `cogs/events.py::_get_ambient_channel` duplicates. **Zero production callers added this phase** — confirmed via a repo-wide grep showing the only references are the pure-logic module's docstring and this plan's own service/test files.
- `tests/test_guild_config_service.py` — 9 tests, all passing, no live DB required: a spy-pool (`_SpyPool`) proves `get()`/`resolve_ambient_channel()` never call `.acquire()` again after `load_all()`; two fail-closed tests (acquire-time and fetch-time exceptions) prove `load_all()` never propagates and leaves the cache empty; four resolver-branch tests (miss, resolve, stale, no-perms) using `MagicMock(spec=discord.TextChannel/Guild)` fixtures, with the two skip branches asserting the cache row is the *same object* (`is`) afterward, not just equal; two `resolve_announce_channel` tests exercise the system-channel and first-writable-fallback steps directly.

## Task Commits

Each task was committed atomically:

1. **Task 1: GuildConfigService — cache, load_all (fail-closed), get, seed_home_guild** - `b88ef3e` (feat)
2. **Task 2: Both resolvers — strict ambient (sync) + announce fallback (zero callers)** - `4fd9025` (feat)
3. **Task 3: tests/test_guild_config_service.py — no-round-trip + resolver behavior** - `6db6f2a` (test)

**Plan metadata:** (this commit, following SUMMARY.md write)

## Files Created/Modified
- `services/guild_config.py` - `GuildConfigService` class: cache load/get/seed + both named resolvers
- `tests/test_guild_config_service.py` - 9 mock-based tests covering no-round-trip, fail-closed, and all 4 resolver branches

## Decisions Made
- Both resolvers are synchronous `def` (not `async def`) — `resolve_ambient_channel` per plan spec (cache-only), and `resolve_announce_channel` because its ported body never actually `await`s anything either (all steps are synchronous discord.py attribute/dict lookups), so keeping both resolvers the same calling convention avoids an inconsistent async/sync split between two methods on the same class that callers reach identically.
- `load_all()`'s Discord error-channel notification is guarded by `hasattr(self._bot, "log_to_discord")` rather than assuming it exists, matching the existing `bot.py` idiom (`on_app_command_error`) and letting the test suite's minimal fake-bot fixture skip that branch cleanly.

## Deviations from Plan

None - plan executed exactly as written. `resolve_announce_channel`'s synchronous signature was not explicitly mandated in the plan text (only `resolve_ambient_channel`'s synchronicity was called out), but making it `def` rather than `async def` is consistent with D-02's own note that the relocated fallback-chain body performs no actual `await`-requiring I/O — this is a clarification of an underspecified detail, not a deviation from any stated requirement.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `services/guild_config.py` is ready for `bot.py` boot wiring (construction + `load_all()` + home-guild seed inside `_initialize_once`) and for `cogs/events.py` call-site rewrites — both are out of scope for this plan per the phase's plan-04 boundary (wiring/call-site rewrites belong to sibling plans in this phase's wave structure).
- `resolve_announce_channel` is a pre-built, tested seam with zero production callers, exactly as Phase 19's join-welcome flow (ONBOARD-01) will need it.
- Full suite run: **873 passed, 111 skipped (live-DB, no `TEST_DATABASE_URL` locally), 0 failed** — no regressions introduced.
- `ruff check` + `ruff format --check` both clean on both new files.

---
*Phase: 18-per-guild-config-foundation-ci-gate*
*Completed: 2026-07-10*
