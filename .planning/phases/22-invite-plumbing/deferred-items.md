# Deferred Items — Phase 22

## Plan 22-02

- **Pre-existing `ruff format` drift, out of this task's scope.** `ruff format --check .`
  (full-repo check run as part of Task 2 verification) reports 3 files would be
  reformatted: `cogs/events.py`, `tests/test_guild_config_logic.py`,
  `tests/test_memory.py`. None of these files were touched by plan 22-02
  (`cogs/invite.py`, `bot.py`, `cogs/help.py`, `tests/test_invite_cog.py`) —
  the drift predates this plan. Per the executor's scope-boundary rule, not
  fixed here. `ruff check cogs/invite.py tests/test_invite_cog.py` and
  `ruff format --check cogs/invite.py tests/test_invite_cog.py` (the plan's
  actual scoped verification commands) both pass cleanly; the full-repo
  `ruff check .` also passes with 0 lint errors — only the full-repo
  `ruff format --check .` surfaces this pre-existing, unrelated drift.
