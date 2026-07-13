---
phase: 21-memory-scoping-guild-data-lifecycle
fixed_at: 2026-07-13T20:13:08Z
review_path: .planning/phases/21-memory-scoping-guild-data-lifecycle/21-REVIEW.md
iteration: 1
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 21: Code Review Fix Report

**Fixed at:** 2026-07-13T20:13:08Z
**Source review:** .planning/phases/21-memory-scoping-guild-data-lifecycle/21-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 2 (both Warning-severity; the 1 Info finding, IN-01, is out of
  scope by design per the fix instructions — the D-01 NULL-guild residual leak is
  intentional and correctly implemented, not a defect)
- Fixed: 2
- Skipped: 0

## Fixed Issues

### WR-01: `on_guild_remove` has no observability on a successful purge

**Files modified:** `bot.py`
**Commit:** `727ad10`
**Applied fix:** `database.purge_guild_data` returns a `dict[str, int]` of per-table
deleted-row counts specifically so callers can confirm a purge actually happened.
`on_guild_remove` was discarding that return value entirely and only logging the
failure path. Captured the return value into `counts` and added
`log.info("on_guild_remove: purged guild %s data: %s", guild.id, counts)`
immediately after the successful await, matching the lowercase, `handler_name: `-prefixed
logging convention used throughout `bot.py` (e.g. `on_guild_join`'s WR-04 warning).
Applied the review's suggested fix as-is — the current source matched what the
reviewer saw exactly, no adaptation needed. Verified the new log message does not
introduce a second literal occurrence of the string `purge_guild_data` in `bot.py`
(the 21-04 plan's own acceptance criterion requires `grep -c "purge_guild_data" bot.py`
to stay at exactly 1, to avoid tripping the source-inspection test in
`database.py::purge_guild_data`'s own docstring-literal-avoidance discipline) —
confirmed post-edit: still 1.

### WR-02: No test locks that `on_guild_remove` actually calls `purge_guild_data`

**Files modified:** `tests/test_database_phase21.py`
**Commit:** `73a67be`
**Applied fix:** Added a new `TestOnGuildRemoveWiring` class immediately after the
existing `TestPurgeGuildDataStructure` class (before the "Live-DB integration tests"
section), mirroring the established source-inspection idiom already used in this
exact phase for comparably Discord-heavy surfaces
(`tests/test_ambient_recall_cadence.py::TestGuildScopedOptIns`,
`tests/test_autoqueue_wiring.py::TestGuildScopedTasteBlend`). Two tests:
- `test_on_guild_remove_calls_purge_guild_data` — asserts `"purge_guild_data"` appears
  in `inspect.getsource(bot.on_guild_remove)`, so a future edit that drops, comments
  out, or reorders past a `return` this call fails the suite instead of passing silently.
- `test_on_guild_remove_purge_is_wrapped_in_try_except` — asserts the handler still
  contains `try:` / `except Exception` and `log.warning`, locking the D-03/WR-04
  best-effort discipline (a purge failure must never crash guild removal).

**Adaptation from the review's literal suggestion:** the review's proposed snippet
also asserted `assert "guild_blocklist" not in src`. I verified this against the
actual `on_guild_remove` source (read before editing, per the mandatory read-first
step) and found the reviewer's own suggested assertion would have failed
immediately — `on_guild_remove`'s docstring *legitimately* documents, in prose, that
`guild_blocklist` is deliberately NOT purged (Phase 20 D-01 / OWNER-04; this is
required documentation per the 21-04 plan's own Task 1 action item, not an
oversight). A blanket "the substring must never appear" assertion would have
contradicted the phase's own required docstring content and been a permanently-red
test. Dropped that assertion from the added test; kept the two assertions that do
hold and that materially close the coverage gap the finding describes (the call
itself, and the try/except-wrapped best-effort discipline). This is exactly the
"adapt the fix suggestion to the actual code" case called out in the fix-strategy
guidance, not a skip — the finding's underlying issue (no lock on the wiring point)
is still fully addressed.

## Skipped Issues

None — both in-scope findings were fixed.

---

_Fixed: 2026-07-13T20:13:08Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
