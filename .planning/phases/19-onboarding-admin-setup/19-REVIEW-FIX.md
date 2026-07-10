---
phase: 19-onboarding-admin-setup
fixed_at: 2026-07-10T12:35:09Z
review_path: .planning/phases/19-onboarding-admin-setup/19-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 19: Code Review Fix Report

**Fixed at:** 2026-07-10T12:35:09Z
**Source review:** .planning/phases/19-onboarding-admin-setup/19-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (CR-01 blocker + WR-01, WR-02, WR-03, WR-04)
- Fixed: 5
- Skipped: 0

Scope was explicitly limited to the Critical + Warning findings; IN-01/IN-02
(stale docstrings) were left untouched per the task's instructions, since
none of the applied warning fixes happened to touch those docstring lines.

## Fixed Issues

### CR-01: `on_guild_join` never refreshes the cache when the guild_config row already exists

**Files modified:** `database.py`, `bot.py`
**Commit:** `b1b0084`
**Applied fix:** Added `database.get_guild_config(pool, *, guild_id)`, a
single-guild fetch mirroring `load_all_guild_configs`'s column list and
`Record` shape (reusing the existing `_GUILD_CONFIG_RETURNING_COLUMNS`
constant). `on_guild_join`'s "row already existed" branch now calls it and
pushes the result into `bot.guild_config._refresh_cache_entry(...)`, so a
guild kicked-and-re-invited while the bot stays running no longer reads as
permanently unconfigured for the rest of the process's uptime.

### WR-01: Boot-backfill summary embed labels guilds as "welcomed" even when the welcome send failed

**Files modified:** `bot.py`
**Commit:** `6378e83`
**Applied fix:** `_welcomed_this_boot` now tracks `(name, guild_id, welcome_posted)`
per guild instead of just `(name, guild_id)`. The owner-facing summary embed
renders an explicit `— welcome posted: yes/no` per line and the title was
changed from "welcomed N guild(s)" to "N new guild(s)" so it no longer
implies every listed guild actually received the welcome message.

### WR-02: `/setup roasts` and `/setup vision` silently no-op (and still report success) when no guild_config row exists

**Files modified:** `services/guild_config.py`, `cogs/admin.py`
**Commit:** `2bb2631`
**Applied fix:** `GuildConfigService.set_ambient_roasts_enabled` /
`set_vision_roasts_enabled` now return `bool` (True if a row existed and was
updated, False if the underlying `UPDATE` affected zero rows) instead of
`None`. `AdminCog.setup_roasts` / `setup_vision` check this return value and
reply `"couldn't save that — try /setup channel first."` instead of a false
`"roasts: on."` / `"vision: on."` success message when the write was a
no-op. Chose the "check-and-tell-admin" option from the review's two
suggested approaches (over upserting) since it keeps the DB write contract
unchanged and only touches the failure-reporting path, matching D-07's
existing "the toggle is independent state, name the gap" philosophy rather
than introducing new upsert semantics for a rare boot-hiccup edge case.

### WR-03: `/setup channel`'s pre-write permission check and the ambient-channel resolver only validate `send_messages`

**Files modified:** `cogs/admin.py`, `services/guild_config.py`
**Commit:** `2fc0999`
**Applied fix:** Both the `setup_channel` D-06 pre-flight refusal check and
`resolve_ambient_channel`'s post-configure guard now require
`perms.send_messages and perms.view_channel` instead of `send_messages`
alone. The existing warning log message in `resolve_ambient_channel` still
contains the substring `"send_messages"` (now `"lost send_messages/
view_channel"`), preserving `tests/test_guild_config_service.py`'s existing
assertion.

### WR-04: `on_guild_join` has no failure isolation around the DB write / welcome / notify chain

**Files modified:** `bot.py`
**Commit:** `7aaabe5`
**Applied fix:** Wrapped the `insert_guild_config_if_absent` call and the
subsequent welcome/cache-refresh branch in `try/except Exception`, matching
the resilience discipline already used by the boot-backfill loop and other
DB call sites in this file (`taste_distill_batch`, `memory_distill_batch`).
On failure, `welcome_posted` stays `False` and a warning is logged, but the
owner join notice (`bot.log_to_discord(...)`) still sends unconditionally
after the try/except — it is no longer lost to an unguarded exception.

## Skipped Issues

None — all 5 in-scope findings were fixed.

## Verification

- Tier 1 (re-read): confirmed for every fix.
- Tier 2 (syntax): `python -c "import ast; ast.parse(...)"` passed for every
  modified file after every edit; `pytest --collect-only` (1054 tests)
  succeeded after each commit.
- Targeted regression runs after each fix:
  `tests/test_database_phase19.py`, `tests/test_guild_config_service.py`,
  `tests/test_guild_config_logic.py` — all passing (no live-DB tests ran,
  since `TEST_DATABASE_URL` is unset in this environment; they skip cleanly).
- Full suite after all 5 fixes: **936 passed, 118 skipped, 0 failed.**
- `ruff check .`: **All checks passed!**
- `ruff format --check .`: **112 files already formatted.**

No logic-classified findings required the "requires human verification" tag
— WR-02's behavior change (return-value contract) and WR-04's failure
isolation are both structural/error-handling fixes with clear, deterministic
pass/fail semantics, not judgment-call algorithm changes.

---

_Fixed: 2026-07-10T12:35:09Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
