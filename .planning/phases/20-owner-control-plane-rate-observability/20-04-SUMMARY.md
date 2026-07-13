---
phase: 20-owner-control-plane-rate-observability
plan: 04
subsystem: infra
tags: [guild-config, blocklist, silence, cache, asyncpg]

# Dependency graph
requires:
  - phase: 20-01
    provides: guild_blocklist table + load_blocklist/insert_blocklist/delete_blocklist/set_silenced DB helpers
provides:
  - "GuildConfigService._blocked: set[str] boot-loaded independently of the config cache"
  - "block_guild/unblock_guild/is_blocked write-then-invalidate + O(1) hot-path read"
  - "silence_guild/unsilence_guild/is_silenced write-then-invalidate + cache-only hot-path read"
affects: [20-05, 20-06, 20-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Independent try/except per boot-load concern inside one load_all() (fail-open on blocklist, fail-closed on config, each subsystem keeps its own direction)"
    - "Write-then-mutate/invalidate: DB write always precedes the in-memory set/cache mutation"

key-files:
  created: []
  modified:
    - services/guild_config.py
    - tests/test_guild_config_service.py

key-decisions:
  - "load_all() restructured from try/except-with-early-return to try/except/else so the new blocklist load always runs regardless of whether the config-cache load succeeded or failed (full independence both directions, matching D-02/D-03/T-20-12)"
  - "block_guild/unblock_guild deliberately do NOT touch _cache/_refresh_cache_entry -- the blocklist is its own table and its own set (D-03), kept structurally separate from the config cache"
  - "silence_guild/unsilence_guild mirror set_ambient_roasts_enabled's exact write-then-push-invalidate + 'row existed?' boolean contract"

patterns-established:
  - "GuildConfigService now owns three independent in-memory read surfaces (config cache, blocked set, silenced-via-cache) all boot-loaded in one load_all() call, all zero-round-trip on the hot path"

requirements-completed: [OWNER-04, OWNER-02]

# Metrics
duration: 20min
completed: 2026-07-13
---

# Phase 20 Plan 04: GuildConfigService Blocked-Set + Silence Methods Summary

**GuildConfigService gained an O(1) `_blocked` set (independently boot-loaded from `guild_blocklist`) plus write-then-invalidate `block_guild`/`unblock_guild`/`silence_guild`/`unsilence_guild` setters and cache-only `is_blocked`/`is_silenced` readers -- zero Neon round-trips on either hot path.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-13T22:56:00+08:00 (approx)
- **Completed:** 2026-07-13T23:23:21+08:00
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `GuildConfigService.__init__` now initializes `self._blocked: set[str] = set()`.
- `load_all()` restructured (try/except/else instead of try/except-with-early-return) so the config-cache load and the new blocklist load are fully independent in BOTH directions -- a blocklist-load failure never blanks the config cache, and a config-cache-load failure no longer prevents the blocklist load from running.
- `block_guild`/`unblock_guild`/`is_blocked` added: write-DB-then-mutate-set (D-02), O(1) synchronous membership test, never touching the config cache (D-03).
- `silence_guild`/`unsilence_guild`/`is_silenced` added: mirrors `set_ambient_roasts_enabled`'s write-then-push-invalidate + "row existed?" boolean contract exactly; `is_silenced` is a cache-only read via `self.get()`.
- 8 new service-level tests added (blocked-set load/round-trip, block/unblock flip, independent fail-open, silence/unsilence write-through, silence no-op-on-missing-row), plus a new `_MultiTableConn`/`_MultiTableSpyPool` fake-pool pair that discriminates fetch results by SQL substring (`guild_blocklist` vs. config) so `load_all()`'s dual-query behavior can be exercised in one call.
- Existing `test_no_round_trip_after_load_all` updated: `acquire_count` assertion changed from `1` to `2` since `load_all()` now issues a second (blocklist) fetch -- still proves zero *extra* round-trips after boot.

## Task Commits

Each task was committed atomically:

1. **Task 1: `_blocked` set + block/unblock/is_blocked + silence/unsilence/is_silenced on GuildConfigService** - `f0c2d4f` (feat)
2. **Task 2: service tests -- blocked-set load/push-invalidate + silence write-through + fail-open** - `b31a40a` (test)

**Plan metadata:** (this commit, docs)

## Files Created/Modified
- `services/guild_config.py` - `_blocked` set field, restructured `load_all()` (independent config-cache vs. blocklist try/except), `block_guild`/`unblock_guild`/`is_blocked`, `silence_guild`/`unsilence_guild`/`is_silenced`
- `tests/test_guild_config_service.py` - `_MultiTableConn`/`_MultiTableSpyPool` fakes, 8 new tests, one existing assertion updated (`acquire_count` 1→2)

## Decisions Made
- Restructured `load_all()`'s control flow (try/except/else, no early `return`) rather than leaving the blocklist load nested inside the config-load's happy path -- this was necessary to satisfy the plan's "vice-versa" independence requirement (a config-cache load failure must not block the blocklist load from running). This is a structural refactor of existing code, not new logic, and is covered by the existing fail-closed tests plus the new independence test.
- Chose `monkeypatch.setattr("services.guild_config.database.set_silenced", ...)` over extending the shared fake-conn's `fetchrow` dispatch, per the plan's explicit suggestion ("mirroring how the file already fakes the pool") -- keeps the silence tests' return-value control (row vs. `None`) simple and independent of the `_FakeConn`/`_SpyPool` trio used elsewhere.

## Deviations from Plan

None - plan executed exactly as written. The `load_all()` restructuring (try/except/else) was explicitly directed by the plan's action text ("so a blocklist-load failure does NOT blank the config cache and vice-versa") and is not an unplanned deviation.

## Issues Encountered

Running the pre-existing `test_no_round_trip_after_load_all` test immediately after Task 1 revealed its `acquire_count == 1` assertion no longer held (now `2`, since `load_all()` performs a second fetch for the blocklist). This was an expected, plan-anticipated consequence of extending `load_all()` -- fixed as part of Task 2's test work, not treated as a regression.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `GuildConfigService.is_blocked`/`is_silenced` are ready for `interaction_check` and `on_guild_join` (20-06) and ambient resolution (20-05) to call.
- `block_guild`/`unblock_guild`/`silence_guild`/`unsilence_guild` are ready for `/guilds` (20-07) to drive.
- Full suite green: 967 passed, 121 skipped, 0 failed (`pytest tests/ -q`).

---
*Phase: 20-owner-control-plane-rate-observability*
*Completed: 2026-07-13*
