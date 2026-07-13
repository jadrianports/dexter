---
phase: 20-owner-control-plane-rate-observability
plan: 06
subsystem: bot-lifecycle
tags: [discord.py, command-tree, interaction-check, owner-control-plane, guild-blocklist]

# Dependency graph
requires:
  - phase: 20-02
    provides: "pure decide_interaction_allowed predicate (is_owner -> has_guild -> blocked/silenced order, D-13)"
  - phase: 20-04
    provides: "GuildConfigService.is_blocked / is_silenced cache-only reads"
provides:
  - "DexterCommandTree(app_commands.CommandTree) overriding interaction_check as the single slash-command choke point"
  - "tree_cls=DexterCommandTree wired into DexterBot construction in create_bot"
  - "Block-check-first at the top of on_guild_join (leaves a blocklisted re-invite before any onboarding)"
affects: [phase-21-memory-scoping, phase-22-invite-plumbing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Discord/process glue dispatching on a pure logic/ predicate (decide_interaction_allowed) rather than re-deriving branch order inline"
    - "Ephemeral refusal sent from INSIDE interaction_check before return False -- returning False alone is silent and never reaches on_app_command_error"
    - "Service-absent (boot-race) fails OPEN, distinct from a config-row-absent fail-closed case"

key-files:
  created: []
  modified:
    - "bot.py - DexterCommandTree class + tree_cls wiring + on_guild_join block-check-first"

key-decisions:
  - "Ephemeral refusal copy is a plain lowercase one-liner ('i've been muted in this server. not my call.') per Critical Rules 8/6 -- no emoji needed for a functional refusal"
  - "A blocked re-invite sends no owner 'joined' notice -- the log line is the correct and only record, since the guild never actually onboarded"

patterns-established:
  - "Pattern: single choke-point authorization glue computes booleans and dispatches on a pure predicate; never re-implements the branch order"

requirements-completed: [OWNER-04, OWNER-05, OWNER-06, OWNER-02]

# Metrics
duration: 18min
completed: 2026-07-14
---

# Phase 20 Plan 06: DexterCommandTree Choke Point + Re-Invite Refusal Summary

**Single `app_commands.CommandTree` subclass enforces block/silence for every slash command via `interaction_check`, plus a block-check-first in `on_guild_join` that leaves a blocklisted re-invite before any onboarding.**

## Performance

- **Duration:** 18 min
- **Started:** 2026-07-13T23:58:00Z (approx)
- **Completed:** 2026-07-14T00:16:00Z (approx)
- **Tasks:** 2
- **Files modified:** 1 (`bot.py`)

## Accomplishments
- `DexterCommandTree(app_commands.CommandTree)` defined above `create_bot`, overriding `interaction_check` to compute `is_owner`/`has_guild`/`blocked`/`silenced` and dispatch on `decide_interaction_allowed` (20-02's pure predicate)
- Boot-race (`guild_config` service not yet attached) fails OPEN — distinct from D-07's fail-closed "guild has no config row" case — so a startup race never bricks every slash command bot-wide
- The D-12 ephemeral refusal is sent from INSIDE `interaction_check`, guarded by `interaction.response.is_done()`, before `return False` — matches the verified discord.py 2.7.1 mechanic that a bare `return False` never reaches `on_app_command_error`
- `tree_cls=DexterCommandTree` wired into the `DexterBot(...)` constructor call in `create_bot`
- `on_guild_join` now checks `bot.guild_config.is_blocked(str(guild.id))` immediately after the existing boot-race guard and before `insert_guild_config_if_absent` — a blocklisted guild is left via `await guild.leave()` with no config insert, no welcome, and no owner "joined" notice

## Task Commits

Each task was committed atomically:

1. **Task 1: DexterCommandTree.interaction_check + tree_cls wiring** - `19ad3a1` (feat)
2. **Task 2: block-check-first in on_guild_join (OWNER-04 re-invite refusal)** - `cfb9303` (feat)

## Files Created/Modified
- `bot.py` - Added `class DexterCommandTree`, wired `tree_cls=DexterCommandTree` into `create_bot`, added block-check-first at the top of `on_guild_join`

## Decisions Made
- Refusal copy kept to a single lowercase line, no emoji — a functional notice, not a roast, per Critical Rules 8/6
- No owner "joined" notice on a blocked re-invite (the guild never onboarded; the log line is the record)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The verify commands in the plan initially flagged the literal substring `"CheckFailure"` inside the docstring's own explanatory prose (which quoted the exception name to explain what NOT to do) — reworded the docstring to describe the mechanic without repeating the literal class name, keeping the guard's intent (never raise it) unchanged. Not a deviation rule trigger — a wording fix to satisfy the plan's own automated verify script, verified against `python -c` re-run immediately after.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `bot.py` imports clean and `bot.create_bot()` constructs with `DexterCommandTree` as its tree (verified via `python -c "import bot; bot.create_bot()"`)
- Full suite green: 970 passed, 121 skipped, 0 failed (`pytest tests/ -q`)
- OWNER-02/04/05/06 requirements now code-complete for this plan's scope; plan 20-07 (if any) or phase close is next
- Manual live-Discord smoke (non-owner command in a silenced guild shows the in-persona ephemeral line) remains parked behind the residential host, consistent with every prior v1.4 phase's UAT deferral

---
*Phase: 20-owner-control-plane-rate-observability*
*Completed: 2026-07-14*

## Self-Check: PASSED

- FOUND: bot.py
- FOUND: 19ad3a1
- FOUND: cfb9303
