---
phase: 20-owner-control-plane-rate-observability
plan: 07
subsystem: owner-control-plane
tags: [discord.py, app_commands.Group, owner-kill-switch, pagination]

# Dependency graph
requires:
  - phase: 20-03
    provides: GeminiService per-guild session usage counter (guild_usage) + guild_id kwarg threading
  - phase: 20-04
    provides: GuildConfigService silence_guild/unsilence_guild/block_guild/unblock_guild/is_silenced/is_blocked
provides:
  - "/guilds app_commands.Group in cogs/ops.py with 6 subcommands (list/silence/unsilence/leave/block/unblock)"
  - GuildListPageView + _chunk_guild_rows_into_pages char-budget pagination
  - _parse_guild_id owner-input guard + shared _force_leave_teardown helper
  - config.GUILDS_LIST_PAGE_SIZE knob
affects: [21-memory-scoping-guild-data-lifecycle, 23-portfolio-surface-ci-cd]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Owner control surface as a single app_commands.Group with inline is_owner()-first gate per subcommand (default_permissions is a UI hint only)"
    - "Char-budget pagination view clone (GuildListPageView from MemoryPageView) for owner-facing fleet listings"
    - "Force-leave teardown resolved via bot.get_guild(int(guild_id)), never interaction.guild, when acting on a guild the invoker is not currently in"

key-files:
  created:
    - tests/test_guilds_group.py
  modified:
    - cogs/ops.py
    - config.py

key-decisions:
  - "Guild names render as plain text with backtick-wrapped ids in /guilds list rows (anti-injection, mirrors bot.py::_build_guild_notice_embed); silence/leave/block echoes use AllowedMentions.none() as defense-in-depth"
  - "/guilds block runs the shared teardown THEN the blacklist insert (D-11 order); a guild already absent (bot.get_guild returns None) still gets blacklisted, teardown skipped"
  - "silence/unsilence honor the service's False (no-row) return honestly — no false-success reply"

patterns-established:
  - "OWNER-06 inline is_owner()-first discipline extended from /stats to all 6 /guilds subcommands"

requirements-completed: [OWNER-01, OWNER-02, OWNER-03, OWNER-04, OWNER-06, RATE-01]

# Metrics
duration: 25min
completed: 2026-07-14
---

# Phase 20 Plan 07: Owner Control Plane (/guilds group) Summary

**Single `/guilds` app_commands.Group in cogs/ops.py shipping the full reactive kill-switch UX — list/silence/unsilence/leave/block/unblock — all gated by an inline is_owner() check and backed by Phase 20-03/20-04's usage counter and blocklist service.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-07-13T16:09:32Z (STATE stopped_at baseline)
- **Completed:** 2026-07-14
- **Tasks:** 3/3 completed
- **Files modified:** 3 (cogs/ops.py, config.py, tests/test_guilds_group.py)

## Accomplishments
- `/guilds list` renders every guild Dexter is in — name, backtick-wrapped copy-pasteable `guild_id`, member count, status flags (configured/silenced/blocked), and this-session Gemini call count — sorted usage-descending (budget hog first), paginated via a char-budget view, fully ephemeral.
- `/guilds silence` / `/guilds unsilence` flip `guild_config.silenced` immediately with an in-persona ephemeral echo and no confirm step; a no-config-row target is reported honestly rather than a false success.
- `/guilds leave` / `/guilds block` / `/guilds unblock` implement the OWNER-03/OWNER-04 kill-switch: a shared `_force_leave_teardown` mirrors `/stop`'s exact template (bump `_play_generation` → `queue.clear()` → `clear_persisted` → stop+disconnect voice → `guild.leave()`), resolved via `bot.get_guild(int(guild_id))` — never `interaction.guild` — since the owner invokes these against a guild they are not necessarily present in. `block` runs the teardown then inserts into the blocklist (teardown-then-blacklist order, D-11), and still blacklists a guild the bot has already left. `unblock` deletes the blocklist row without rejoining.

## Task Commits

Each task was committed atomically:

1. **Task 1: /guilds group + /guilds list + GuildListPageView + config knob** - `b976c21` (feat)
2. **Task 2: /guilds silence + /guilds unsilence** - `2afde69` (feat)
3. **Task 3: /guilds leave + /guilds block + /guilds unblock + structural tests** - `28d89d9` (feat)

**Plan metadata:** (this commit) `docs(20-07): complete plan`

## Files Created/Modified
- `cogs/ops.py` - `/guilds` app_commands.Group (6 subcommands), `GuildListPageView`, `_chunk_guild_rows_into_pages`, `OpsCog._parse_guild_id`, `OpsCog._force_leave_teardown`
- `config.py` - `GUILDS_LIST_PAGE_SIZE = 1800`
- `tests/test_guilds_group.py` - structural review: six-subcommand set, inline is_owner-first gate on every subcommand, `_parse_guild_id` never-raise contract, `get_guild`/teardown-token source invariants, teardown-then-blacklist ordering, block-still-blacklists-absent-guild

## Decisions Made
- Followed plan's D-04…D-14 verbatim; no new architectural decisions this plan (all load-bearing decisions — blocklist's own table, D-04/D-05 group placement, D-06 default_permissions-as-UI-hint, D-07 no-confirm, D-08/D-09 session usage counter, D-10 sort/paginate, D-11 block=teardown+blacklist, D-13/D-14 choke points — were made in 20-CONTEXT.md and already implemented by 20-01…20-06).
- Added `AttributeError` to `_parse_guild_id`'s except clause (alongside the plan's `TypeError, ValueError`) as defense-in-depth against a non-string input reaching `.strip()` — belt-and-suspenders beyond the plan's literal text, no behavior change for the documented str-input contract.

## Deviations from Plan

None — plan executed exactly as written. One minor robustness addition (see Decisions Made) falls under Rule 2 (auto-add missing critical functionality: an untyped call site could otherwise raise `AttributeError` instead of returning `None`), verified via `tests/test_guilds_group.py::test_parse_guild_id_never_raises_on_malformed_input`.

## Issues Encountered
None.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- All 3 tasks' acceptance criteria met: `config.GUILDS_LIST_PAGE_SIZE` exists; `guilds` group has `default_permissions=discord.Permissions(administrator=True)`; every subcommand opens with the inline `is_owner` gate; list sorts by usage descending with backtick-wrapped ids; `GuildListPageView` edits with `AllowedMentions.none()`; `_parse_guild_id` never raises; `_force_leave_teardown` mirrors the `/stop` sequence and resolves via `get_guild`; `block` runs teardown-then-blacklist and still blacklists an absent guild; `unblock` never rejoins.
- `pytest tests/test_guilds_group.py -q` — 12 passed.
- Full suite `pytest tests/ -q` — 982 passed, 121 skipped (live-DB tests requiring `TEST_DATABASE_URL`, pre-existing skip condition), 0 failed.
- `ruff check` / `ruff format --check` clean on all 3 touched files.
- This was the last plan in Phase 20 (7 of 7) — Phase 20 "Owner Control Plane & Rate Observability" is now code-complete. Remaining work is the parked live-Discord manual smoke test (`/guilds list` renders sorted rows; `/guilds block` leaves + refuses re-invite), consistent with every prior v1.4/v1.3 phase's deferred-UAT precedent.

---
*Phase: 20-owner-control-plane-rate-observability*
*Completed: 2026-07-14*

## Self-Check: PASSED

All claimed files found on disk (`cogs/ops.py`, `config.py`, `tests/test_guilds_group.py`,
this SUMMARY.md). All claimed commits (`b976c21`, `2afde69`, `28d89d9`) found in git log.
