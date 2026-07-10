---
phase: 19-onboarding-admin-setup
plan: 04
subsystem: bot-behavior
tags: [discord-py, app-commands-group, guild-config, admin-surface, onboarding]

# Dependency graph
requires:
  - phase: 19-onboarding-admin-setup
    provides: "plan 01 — configure_guild_first_time/redesignate_guild_channel/set_ambient_roasts_enabled/set_vision_roasts_enabled database.py helpers"
  - phase: 19-onboarding-admin-setup
    provides: "plan 02 — GuildConfigService write-then-push-invalidate methods (configure_guild_first_time, redesignate_guild_channel, set_ambient_roasts_enabled, set_vision_roasts_enabled) plus AmbientSurface enum"
  - phase: 19-onboarding-admin-setup
    provides: "plan 03 — cogs.admin already added to the _initialize_once cog-load tuple"
provides:
  - "cogs/admin.py::AdminCog — the /setup app_commands.Group (channel|roasts|vision), guild_only + default_permissions Group-level only"
  - "AdminCog._require_guild_admin — shared inline manage_guild gate (D-08/D-09), first statement of every subcommand"
  - "AdminCog._config_echo — full post-write config echo (channel/roasts/vision) for D-05"
  - "/setup channel — native typed-channel dropdown, D-06 send_messages validation before write, first-configure vs re-designate branch on cached configured flag"
  - "/setup roasts on|off, /setup vision on|off — independent toggle subcommands with D-07 no-channel-yet gap note"
  - "cogs/help.py::ADMIN_COMMANDS_INFO + /help Admin embed field (D-25)"
affects: [20-owner-control-plane-rate-observability]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shared _require_guild_admin(interaction) helper as the first statement of every /setup subcommand — mirrors cogs/ops.py's owner-check-first discipline with a different permission"
    - "Cache-only _config_echo read after a service write (the service methods already push-invalidated the cache before the echo runs)"

key-files:
  created:
    - cogs/admin.py
  modified:
    - cogs/help.py

key-decisions:
  - "setup_channel branches first-configure (configure_guild_first_time) vs re-designate (redesignate_guild_channel) on `cached is None or not cached['configured']`, read BEFORE either write, so the old-channel-id is still available for the re-designate reply's old->new phrasing"
  - "setup_channel's send_messages check runs BEFORE any DB read/write and returns immediately with a specific ephemeral refusal naming channel.mention — the one deliberate loud-failure exception in this subsystem (D-06)"
  - "setup_roasts / setup_vision share the identical shape (Choice-constrained on|off, admin gate first, gap note, D-05 echo) — no shared toggle-subcommand factory was introduced since discord.py's decorator-based command registration doesn't compose cleanly through a shared coroutine wrapper without losing the Choice/describe metadata"

patterns-established:
  - "cogs/admin.py as the dedicated guild-admin (manage_guild) surface, structurally separate from cogs/ops.py's owner (is_owner) surface — D-04"

requirements-completed: [ONBOARD-02, ONBOARD-03, ONBOARD-04]

# Metrics
duration: 15min
completed: 2026-07-10
---

# Phase 19 Plan 04: /setup Admin Command Surface Summary

**New `cogs/admin.py` shipping the `/setup channel|roasts|vision` app_commands.Group — inline `manage_guild` gate, native typed-channel dropdown with write-time send-permission validation, first-configure-vs-re-designate branching, and a full-config echo on every write — plus a `/help` Admin section.**

## Performance

- **Duration:** ~15 min
- **Completed:** 2026-07-10T12:13:53Z
- **Tasks:** 3
- **Files modified:** 2 (1 new: cogs/admin.py)

## Accomplishments
- Created `cogs/admin.py`: `AdminCog` declaring `setup_group = app_commands.Group(..., guild_only=True, default_permissions=discord.Permissions(manage_guild=True))` as a class attribute — `guild_only`/`default_permissions` live on the Group only, never repeated as a subcommand decorator (verified by grep: zero `@app_commands.guild_only()` occurrences). Added `_require_guild_admin` (the shared inline `manage_guild` gate, D-08/D-09) and `_config_echo` (the D-05 full-config echo reading the post-write cached row).
- `/setup channel`: the typed `discord.TextChannel` parameter is the native searchable dropdown (ONBOARD-03/D-02); validates `channel.permissions_for(interaction.guild.me).send_messages` **before** any write and refuses loudly, naming the channel, if it fails (D-06); branches `configure_guild_first_time` (turns vision off, D-19/D-20) vs `redesignate_guild_channel` (channel-only, D-03) on the cached `configured` flag, read before either write so the re-designate reply can phrase old→new.
- `/setup roasts on|off` and `/setup vision on|off`: `app_commands.Choice`-constrained on/off toggles calling `set_ambient_roasts_enabled`/`set_vision_roasts_enabled` respectively, each gated by the same admin check, each appending the D-07 "no channel yet" gap note when `configured` is still false, each ending with the D-05 full-config echo.
- Added `ADMIN_COMMANDS_INFO` to `cogs/help.py` and an additive `"Admin"` embed field in `help_command`, naming all three `/setup` subcommands as "(admin only)" (D-25) — the existing `COMMANDS_INFO` "Commands" field is untouched.

## Task Commits

Each task was committed atomically:

1. **Task 1: AdminCog + /setup group + /setup channel (D-01/02/03/05/06/08/09)** - `80d162c` (feat)
2. **Task 2: /setup roasts + /setup vision toggle subcommands (D-05/07/19)** - `863dcbb` (feat)
3. **Task 3: /help admin section (D-25)** - `dde6a8b` (feat)

## Files Created/Modified
- `cogs/admin.py` - New file: `AdminCog`, `setup_group`, `_require_guild_admin`, `_config_echo`, `setup_channel`, `setup_roasts`, `setup_vision`, `setup(bot)`
- `cogs/help.py` - `ADMIN_COMMANDS_INFO` list + additive `"Admin"` embed field in `help_command`

## Decisions Made
- `setup_channel` reads the cached row once, before branching, so the same `cached` value drives both the first-configure/re-designate decision AND (for re-designate) the old→new channel phrasing — avoiding a second cache read after the write that would already reflect the new channel.
- `setup_roasts`/`setup_vision` intentionally duplicate their shape rather than sharing a generic toggle-subcommand helper — `app_commands` command registration is decorator-driven per method, and factoring the body into a shared coroutine would not reduce real duplication (the `@app_commands.choices`/`@app_commands.describe` decorators and distinct service-method calls still need to be per-subcommand) while adding an indirection layer to a file that is untested-by-design (D-26) and reviewed structurally.
- No `set_ambient_roasts_enabled`/`set_vision_roasts_enabled` failure path was added for a missing row (`cached is None` at write time) beyond the existing D-07 gap note, since every guild reaching this cog already has a `guild_config` row from `on_guild_join`/boot backfill (19-03) or the home-guild seed — the service methods already no-op safely (`if row is not None: self._refresh_cache_entry(row)`) if a write somehow affects zero rows.

## Deviations from Plan

None — plan executed exactly as written. All three tasks' acceptance criteria (grep-based structural checks, `ruff check`, `pytest -q`) passed on the first attempt with no auto-fixes required.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 19 is now feature-complete across all 4 requirements (ONBOARD-01 through 05, this plan closing ONBOARD-02/03/04): the join/backfill welcome flow (19-03) points admins at `/setup`, and `/setup` (this plan) is the self-service surface that flow names.
- Full suite green: 936 passed, 118 skipped, 0 failed (`pytest -q`). `ruff check .` and `ruff format --check cogs/admin.py cogs/help.py` both clean.
- Untested-by-design per D-26 (Discord/process glue) — verified by structural review (every acceptance-criteria grep passed), the automated per-task verify commands, and a green full suite. The 4 Manual-Only checks in `19-VALIDATION.md` (non-admin ephemeral refusal via a real second account, the client rendering the native channel dropdown, ambient activation after `/setup channel`, vision firing only after `/setup vision on`) remain parked behind the residential host, matching every prior v1.3/v1.4 phase's Human-UAT deferral precedent.
- This was the last plan of Phase 19 (wave 3 of 3) — ready for `/gsd-verify-phase 19` / phase close.

---
*Phase: 19-onboarding-admin-setup*
*Completed: 2026-07-10*
