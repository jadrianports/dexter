---
phase: 21-memory-scoping-guild-data-lifecycle
plan: 04
subsystem: database
tags: [discord-events, guild-lifecycle, memory-scoping, documentation]

# Dependency graph
requires:
  - phase: 21-memory-scoping-guild-data-lifecycle
    plan: 02
    provides: "database.purge_guild_data(pool, *, guild_id) -> dict[str, int] — the helper this plan wires in"
  - phase: 21-memory-scoping-guild-data-lifecycle
    plan: 03
    provides: "5 guild-scoped recall() call sites + /ask proven global — the shipped scoping this plan documents"
provides:
  - "bot.py::on_guild_remove calls database.purge_guild_data, wrapped in best-effort try/except (WR-04 discipline)"
  - "PROJECT.md Key Decisions rows recording the shipped hybrid memory-scoping path and the purge invariant (ROADMAP SC-4, Phase 23 PORT-04 dependency)"
  - "CLAUDE.md schema/critical-rules/gotchas narrative synced to Phase 21 shipped behavior"
affects: [23-portfolio-surface-ci-cd]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Best-effort lifecycle hook wrapping: purge_guild_data raises by design, on_guild_remove swallows and logs — mirrors on_guild_join's WR-04 discipline exactly"
    - "Docstring/comment literal-avoidance: neither the docstring nor a comment may contain the exact substring a source-inspection regression test forbids, even in prose"

key-files:
  created: []
  modified:
    - bot.py
    - .planning/PROJECT.md
    - CLAUDE.md

key-decisions:
  - "Docstring rewritten to reference 'the database helper's four tables' rather than the literal substring purge_guild_data, keeping grep -c purge_guild_data bot.py at exactly 1 (the single call) per the plan's own acceptance criteria"
  - "PROJECT.md's scoping row explicitly names /ask as staying global — Phase 23's PORT-04 disclosure depends on this precision"

requirements-completed: [MEM-04, MEM-01, MEM-03, MEM-05]

# Metrics
duration: ~19min
completed: 2026-07-14
---

# Phase 21 Plan 04: Purge Wiring + Shipped-Decision Documentation Summary

**`bot.py::on_guild_remove` now calls `database.purge_guild_data` best-effort (single hook, WR-04 discipline), and PROJECT.md/CLAUDE.md record exactly what shipped — hybrid read-path guild scoping with `/ask` staying global — closing out Phase 21.**

## Performance

- **Duration:** ~19 min
- **Tasks:** 2 completed
- **Files modified:** 3 (bot.py, .planning/PROJECT.md, CLAUDE.md)

## Accomplishments
- `bot.py::on_guild_remove` now purges a departed guild's data (four tables: `guild_config`, `guild_queues`, `guild_jams`, guild-stamped `user_memories`) through the plan 21-02 helper, positioned after the cache-evict and before the owner notice. The call is wrapped in `try/except Exception as exc: log.warning(...)`, mirroring `on_guild_join`'s WR-04 discipline — a purge failure can never crash guild removal.
- The stale `on_guild_remove` docstring ("NO DB write (D-12)", "Phase 21's job") is rewritten to describe the shipped behavior: evict cache → best-effort purge → owner notice, `guild_blocklist` never touched (Phase 20 D-01 / OWNER-04), and this is the SINGLE purge site — `cogs/ops.py` is untouched, since `guild.leave()` already fires this same gateway event for both `/guilds leave` and `/guilds block`.
- `.planning/PROJECT.md` § Key Decisions gains two rows discharging ROADMAP success criterion 4: the shipped hybrid memory-scoping path (explicit per-call-site `guild_scoped` opt-in on ambient/unprompted recall; `/ask` named as staying global and self-scoped; the grandfathered `guild_id IS NULL` corpus) and the guild-data purge invariant (four tables, one transaction, `guild_blocklist` excluded). Both are precise enough for Phase 23's PORT-04 to disclose publicly without re-deriving from code.
- `CLAUDE.md` synced in three places: the Database Schema narrative now describes `purge_guild_data` and the guild-scoped ANN read path; a new Critical Rule 17 states guild-scoping is an explicit opt-in, never inferred from `guild_id` presence; a new "Phases 18–21" Implementation Gotchas subsection documents the `search_memories` dynamic placeholder numbering, `recall()`'s conditional `guild_id` forwarding, the untouched dedup path, and the purge helper's hardcoded four-literal DELETE list + raise-don't-swallow contract.

## Task Commits

Each task was committed atomically:

1. **Task 1: bot.py::on_guild_remove calls the purge, wrapped (MEM-04 / D-03)** - `db75c6d` (feat)
2. **Task 2: record the shipped scoping decision in PROJECT.md + sync CLAUDE.md (ROADMAP SC-4 / PORT-04)** - `b459d24` (docs)

## Files Created/Modified
- `bot.py` - `on_guild_remove` gains a `hasattr(bot, "pool")`-guarded, try/except-wrapped `await database.purge_guild_data(bot.pool, guild_id=str(guild.id))` call between the cache-evict and the owner notice. Docstring rewritten to describe shipped best-effort purge behavior, the `guild_blocklist` exclusion invariant, and the single-purge-site guarantee — deliberately avoids the literal substring `purge_guild_data` in prose so `grep -c purge_guild_data bot.py` stays at exactly 1.
- `.planning/PROJECT.md` - Two new `## Key Decisions` rows: hybrid memory scoping SHIPPED (names `/ask` explicitly as global, names the grandfathered NULL corpus, notes the untouched write path) and the guild-data purge (names all four tables, states `guild_blocklist` is never purged).
- `CLAUDE.md` - Database Schema narrative extended with the shipped `purge_guild_data` + guild-scoped read-path description; Critical Rules gains rule 17 (explicit opt-in, never inferred); new "Phases 18–21" Implementation Gotchas subsection (5 bullets covering placeholder numbering, conditional forwarding, untouched dedup, hardcoded DELETE list, raise-don't-swallow).

## Decisions Made
- The purge-call docstring cannot contain the literal substring `purge_guild_data` anywhere (including prose) because the plan's own verify command (`grep -c "purge_guild_data" bot.py` must return 1) counts every line match, not just code references. First draft used the literal name twice in the docstring and had to be reworded to "the database helper's four tables" / "the helper raises on failure by design" before the acceptance criterion passed. This mirrors the identical discipline plan 21-02 already established for `purge_guild_data`'s own docstring around the `guild_blocklist` identifier.
- PROJECT.md's scoping row was written to be self-sufficient for Phase 23: it names `/ask` explicitly as staying global (not just "some surfaces stay global"), names the NULL-corpus grandfathering by its D-01 origin, and notes the write-path (`remember`/dedup/eviction) was never touched — so a future reader (or Phase 23's PORT-04 disclosure copy) doesn't have to re-read `services/memory.py` to get the nuance right.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Docstring's first draft tripped the plan's own `grep -c purge_guild_data bot.py == 1` acceptance criterion**
- **Found during:** Task 1
- **Issue:** The initial `on_guild_remove` docstring explained the purge by naming `` `database.purge_guild_data` `` and `` `purge_guild_data` `` in prose (two additional lines), which made `grep -c "purge_guild_data" bot.py` return 3 instead of the required 1.
- **Fix:** Reworded the docstring to reference "the database helper's four tables" and "the helper raises on failure by design" instead of the literal function name, preserving full explanatory intent.
- **Files modified:** bot.py
- **Verification:** `grep -c "purge_guild_data" bot.py` re-checked → 1; full acceptance-criteria script re-run → pass.
- **Committed in:** `db75c6d` (part of Task 1 commit — caught and fixed before commit, not a separate fix commit)

---

**Total deviations:** 1 auto-fixed (1 blocking, caught and fixed in-flight before the task commit)
**Impact on plan:** No scope creep — a docstring wording fix with zero functional impact, caught by the plan's own acceptance criteria before commit. Same pattern plan 21-02 and 21-03 each independently hit and resolved for their own literal-identifier constraints.

## Issues Encountered

None beyond the deviation above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 21 is now closed: MEM-01/02/03/04/05 all shipped at the code level. Every guild departure path (natural kick/leave, `/guilds leave`, `/guilds block`) purges that guild's data exactly once, and a purge failure can never crash removal.
- `.planning/PROJECT.md` Key Decisions now carries the exact shipped memory-scoping shape Phase 23's PORT-04 needs to disclose honestly — `/ask` global, ambient surfaces guild-scoped, NULL corpus grandfathered, `guild_blocklist` purge-immune.
- Full suite green: `pytest -q` → **1006 passed, 124 skipped, 0 failed** (no regression from Phase 21's prior plans' 1000/1006 baseline — Task 1's wiring added zero new test failures; existing `tests/test_database_phase21.py` static tests continue to lock the purge helper's shape).
- `ruff check bot.py .planning/PROJECT.md` clean; `python -c "import bot"` imports cleanly.
- `grep -rn "purge_guild_data" cogs/` returns zero matches — confirmed single purge site.
- No blockers for Phase 22 (Invite Plumbing) or Phase 23 (Portfolio Surface & CI/CD).

---
*Phase: 21-memory-scoping-guild-data-lifecycle*
*Completed: 2026-07-14*

## Self-Check: PASSED

- FOUND: bot.py
- FOUND: .planning/PROJECT.md
- FOUND: CLAUDE.md
- FOUND: .planning/phases/21-memory-scoping-guild-data-lifecycle/21-04-SUMMARY.md
- FOUND commit: db75c6d (Task 1)
- FOUND commit: b459d24 (Task 2)
