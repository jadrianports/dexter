---
phase: 21-memory-scoping-guild-data-lifecycle
reviewed: 2026-07-14T00:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - bot.py
  - cogs/ai.py
  - cogs/events.py
  - cogs/music.py
  - database.py
  - services/memory.py
  - tests/test_ambient_recall_cadence.py
  - tests/test_autoqueue_wiring.py
  - tests/test_database_phase21.py
  - tests/test_memory.py
findings:
  critical: 0
  warning: 2
  info: 1
  total: 3
status: issues_found
---

# Phase 21: Code Review Report

**Reviewed:** 2026-07-14
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Reviewed the Phase 21 diff since `10d0430` (guild-scoped memory recall + `purge_guild_data`
guild-lifecycle purge) across `bot.py`, `cogs/ai.py`, `cogs/events.py`, `cogs/music.py`,
`database.py`, `services/memory.py`, and the four new/extended test files.

**The core mechanics are correct and well-guarded:**

- `database.search_memories`'s dynamic `$N` param numbering is correct in all four
  shapes (neither/kind-only/guild-only/both) — verified by hand-tracing the SQL and
  confirmed by `TestSearchMemoriesGuildFilter` (all four cases pass, including the
  combined-clause `$3`/`$4` binding order).
- The guild clause is correctly parenthesized — `AND (guild_id = $N OR guild_id IS
  NULL)` — which is the load-bearing detail: without those parens, operator
  precedence would silently rewrite the WHERE clause into `(user_id = $1 AND ...) OR
  (guild_id IS NULL)`, leaking **every user's** NULL-guild memories regardless of
  `user_id`. This was checked carefully since it is exactly the class of bug that
  would reopen the leak MEM-01 exists to close; the code gets it right.
- `MemoryService.recall()`'s `guild_scoped` opt-in is keyword-only, defaults to
  `False`, and forwards no `guild_id` kwarg at all when unset — byte-identical to
  pre-Phase-21 for `/ask` (verified: `/ask` is the only call site with no
  `guild_scoped` kwarg, locked by `test_ask_recall_is_never_guild_scoped` and
  `test_ask_callback_never_mentions_guild_scoped`).
- All five non-`/ask` `recall()` call sites (`/roast`, ambient voice-join/leave
  roast, proactive callback, the music-command earned-roast callback, and the
  auto-queue positive-taste-blend fan-out over voice members) now pass
  `guild_scoped=True` (or `bool(guild_id)` in the one call site where `guild_id` can
  legitimately be absent) — matches the CONTEXT's call-site inventory including both
  "research item" sites it left to planner discretion.
- `remember()`'s k=1 dedup search is untouched — no `guild_id`, no `kind`, no
  `**kwargs` escape hatch threads into the Phase 13 CR-01-scarred path. This is
  locked by a strict-signature stub test (`test_dedup_search_call_shape_is_strict`)
  that would raise `TypeError` if a future edit threaded scoping into dedup, plus a
  source-region assertion and two D-05 `expires_at`-refresh regression tests.
- `database.purge_guild_data` is transactional (all four DELETEs in one
  `conn.transaction()`), hardcodes exactly the four target tables (no
  `information_schema` introspection, no loop), structurally cannot reference
  `guild_blocklist` (locked by a source-string test), and relies on SQL's `=`
  never matching `NULL` to leave the D-01 grandfathered global corpus untouched
  with no extra clause needed. `bot.py::on_guild_remove` is the single call site,
  wrapped in try/except mirroring the existing `on_guild_join` WR-04 discipline, and
  is documented as the only purge site (`cogs/ops.py` force-leave funnels through
  `guild.leave()` → the same event, never a second purge).
- Targeted test files pass (142 passed / 3 skipped — the 3 skips are the live-DB
  integration tests, which correctly skip when `TEST_DATABASE_URL` is unset) and
  `ruff check` is clean on all ten reviewed files.

Two warnings below are about observability/regression-coverage gaps in the new
`bot.py::on_guild_remove` wiring itself (as opposed to the well-tested
`purge_guild_data` helper it calls), plus one informational note about the
documented D-01 residual leak surface.

## Warnings

### WR-01: `on_guild_remove` has no observability on a successful purge

**File:** `bot.py:787-791`
**Issue:** `database.purge_guild_data` returns a `dict[str, int]` of per-table
deleted-row counts specifically so callers/operators can confirm the purge actually
did something. `on_guild_remove` discards that return value entirely — only the
*failure* path is logged (`log.warning` on exception); a successful purge produces
zero log output. For a data-lifecycle/compliance-adjacent operation (this is the
mechanism that guarantees a departed guild's memory data doesn't resurface on
re-invite), this makes it impossible to confirm from production logs whether a
given guild departure actually triggered a purge, or whether it silently no-op'd
(e.g., because the guild had zero rows in all four tables, vs. because `hasattr(bot,
"pool")` was `False` due to a boot race). Every other loop/task-error path in this
file (`_post_loop_error`, `on_guild_join`) logs both outcomes.
**Fix:**
```python
if hasattr(bot, "pool"):
    try:
        counts = await database.purge_guild_data(bot.pool, guild_id=str(guild.id))
        log.info("on_guild_remove: purged guild %s data: %s", guild.id, counts)
    except Exception as exc:
        log.warning("on_guild_remove: guild-data purge failed for guild %s: %s", guild.id, exc)
```

### WR-02: No test locks that `on_guild_remove` actually calls `purge_guild_data`

**File:** `bot.py:762-793` (no covering test in `tests/`)
**Issue:** `database.purge_guild_data` itself is thoroughly tested
(`tests/test_database_phase21.py`), and every other Phase 21 `recall()` call-site
opt-in got either a behavioral test or — for the Discord-heavy surfaces that are
hard to drive behaviorally (the proactive callback, the music-command callback) — a
source-inspection structural test (`tests/test_ambient_recall_cadence.py::
TestGuildScopedOptIns`, `tests/test_autoqueue_wiring.py::
TestGuildScopedTasteBlend`). The single wiring point that actually ties the
well-tested purge helper to a real guild departure — `bot.py::on_guild_remove`
calling `database.purge_guild_data(...)` — has no such lock anywhere. A future edit
that silently drops, comments out, or reorders past a `return` this call would pass
the full test suite. Given the same source-inspection idiom is already established
in this exact phase for comparably "Discord-glue" surfaces, the omission here (on
the highest-blast-radius new code path in the phase — an unconditional data purge)
is a real coverage gap, not just an accepted convention.
**Fix:** Add a structural test mirroring the existing idiom, e.g.:
```python
def test_on_guild_remove_calls_purge_guild_data():
    import inspect
    import bot as bot_module
    src = inspect.getsource(bot_module.on_guild_remove)
    assert "purge_guild_data" in src
    assert "guild_blocklist" not in src
```

## Info

### IN-01: D-01 grandfather rule is a documented, intentional residual cross-guild leak surface

**File:** `database.py:1426-1436`, `services/memory.py:103-107`
**Issue:** Not a defect — flagging for completeness since it's a real (if narrow and
deliberate) exception to MEM-01's stated goal ("a third party's recalled memory
stops leaking across servers"). Any `user_memories` row with `guild_id IS NULL`
(currently only the `daily_batch` distill kind, per the CONTEXT's own scouting)
remains recallable from **every** guild-scoped surface, including `/roast @user`
and ambient roasts triggered by a stranger in an unrelated server. This is the
explicit, user-selected D-01 tradeoff (locked by
`test_guild_scoped_search_excludes_other_guild_includes_null` and the
`purge_guild_data` docstring) and is correctly implemented — just noting it here so
the residual scope is visible in the review record alongside the rest of the
scoping story.
**Fix:** None needed — this is working as designed. Worth a one-line callout in
`PROJECT.md` Key Decisions (already required by this phase's own scope) so PORT-04
(Phase 23) discloses it accurately rather than overstating the scoping guarantee.

---

_Reviewed: 2026-07-14_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
