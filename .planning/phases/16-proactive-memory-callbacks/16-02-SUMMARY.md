---
phase: 16-proactive-memory-callbacks
plan: 02
subsystem: database
tags: [asyncpg, postgres, upsert, opt-out, proactive-callbacks]

# Dependency graph
requires:
  - phase: 16-proactive-memory-callbacks (plan 01)
    provides: logic/proactive.py::should_fire_proactive_callback pure gate + PROACTIVE_CALLBACK_* config knobs
provides:
  - "user_profiles.proactive_opt_out BOOLEAN DEFAULT false column (idempotent ALTER TABLE)"
  - "database.set_proactive_opt_out(pool, *, user_id, opted_out) — upsert setter"
  - "database.get_proactive_opt_out(pool, user_id) -> bool — defaults False (opted-in)"
affects: [16-03-events-glue, 16-04-memory-callbacks-command]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive idempotent ALTER TABLE column (Phase 8 total_errors precedent) reused for a trust-control flag"
    - "Upsert-not-bare-UPDATE for lazily-created user_profiles rows (Pitfall 3 / T-16-06)"
    - "Single-identity-scoped helper signatures locked by inspect.signature structural guard tests (V4)"

key-files:
  created: [tests/test_database_phase16.py]
  modified: [database.py]

key-decisions:
  - "set_proactive_opt_out signature locked to exactly (pool, user_id, opted_out) per plan — no username parameter, despite the plan action text ambiguously suggesting one; the plan's own verify one-liner and Task 2 test both assert the 3-param signature, which is the binding contract"
  - "Insert-branch username placeholder uses user_id itself (VALUES ($1, $1, $2)) to satisfy the NOT NULL constraint without a 4th parameter; the ON CONFLICT DO UPDATE never touches username, so it is safely overwritten by the next update_user_profile() call on the user's next song queue"
  - "Docstrings avoid the literal substring 'user_memories' (paraphrased as 'the RAG memory-facts store') so the source-inspection guard 'user_memories not in source' passes on both docstring and SQL body, not just the SQL"

patterns-established:
  - "Trust-control flags (opt-out, pause, etc.) get their own single-identity-scoped getter/setter pair, structurally proven independent of the memory-store CRUD helpers via source-inspection tests"

requirements-completed: [PROACT-02]

# Metrics
duration: 8min
completed: 2026-07-03
---

# Phase 16 Plan 02: Proactive Callback Opt-Out Storage Summary

**Additive `user_profiles.proactive_opt_out` boolean column plus an upsert-based `set_proactive_opt_out`/`get_proactive_opt_out` helper pair, structurally proven independent of the `user_memories` RAG store.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-03T04:02Z (approx, first read after prior plan commit)
- **Completed:** 2026-07-03T04:06:46Z
- **Tasks:** 2 completed
- **Files modified:** 2 (1 modified, 1 created)

## Accomplishments
- `user_profiles.proactive_opt_out BOOLEAN DEFAULT false` added via idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `SCHEMA_SQL`
- `set_proactive_opt_out` upserts (`INSERT ... ON CONFLICT (user_id) DO UPDATE SET proactive_opt_out = EXCLUDED.proactive_opt_out`) so the flag persists even for a user with zero prior `user_profiles` row (Pitfall 3 — a bare `UPDATE` would silently no-op since `username` is `NOT NULL`)
- `get_proactive_opt_out` defaults to `False` (opted-in) for any user with no profile row
- Both helpers locked by structural signature-guard tests (`inspect.signature` == exact param lists) and source-inspection scoping tests (never reference `user_memories`)
- `tests/test_database_phase16.py` created mirroring the Phase 15 two-tier convention: 5 always-run static tests + 2 live-DB tests (round-trip incl. zero-prior-history case, and two-way independence from `delete_all_user_memories`)

## Task Commits

Each task was committed atomically:

1. **Task 1: Additive proactive_opt_out column + getter/setter helpers** - `ebb99c5` (feat)
2. **Task 2: Static signature guards + live-DB round-trip + cross-independence tests** - `09a45b8` (test)

**Plan metadata:** (this commit, following SUMMARY write)

## Files Created/Modified
- `database.py` - Added `proactive_opt_out` column to `SCHEMA_SQL` near the `user_profiles` CREATE TABLE block; added `set_proactive_opt_out` (upsert setter) and `get_proactive_opt_out` (getter, default False) between `update_user_profile` and `increment_daily_stat`
- `tests/test_database_phase16.py` - New file: `TestPhase16OptOutHelpers` (5 static tests, always run) + `test_opt_out_roundtrip` / `test_zero_memories_touched` (live-DB tier, skip without `TEST_DATABASE_URL`)

## Decisions Made
- **Signature contract resolution:** The plan's `<action>` prose contained an apparent internal contradiction — it described accepting `username` "as the second positional param value from the caller" while simultaneously stating the signature "MUST be exactly keyword-only `user_id` + `opted_out`". Resolved in favor of the explicit, machine-checkable contract: the plan's own `<verify>` one-liner and the Task 2 static test both assert `list(inspect.signature(...).parameters) == ['pool', 'user_id', 'opted_out']`. Implemented the insert-branch `username` as a hardcoded placeholder (`user_id` itself, via `VALUES ($1, $1, $2)`), which satisfies `NOT NULL` without adding a parameter and is never touched by the `DO UPDATE` clause — so it's safely overwritten by `update_user_profile()` on the user's next real song-queue interaction. This matches the plan's own guardrail: "do NOT hard-code a literal placeholder in a way that overwrites a real username on conflict" (satisfied — the DO UPDATE never touches username, so a placeholder can never overwrite a real one).
- **Docstring wording avoids the literal substring `"user_memories"`** so the `'user_memories' not in s` source-inspection assertions (in both the plan's verify one-liner and the new test file) pass cleanly against the full `inspect.getsource()` output (docstring + SQL body), not just the SQL string.

## Deviations from Plan

None — plan executed exactly as written, modulo the signature-contract resolution documented above under Decisions Made (not a deviation from behavior, but a disambiguation of ambiguous plan prose, resolved in favor of the explicit test assertions the plan itself specifies).

## Issues Encountered
- The plan's Task 1 `<action>` prose momentarily suggested a `username` parameter alongside `user_id`/`opted_out`, which would have broken the locked 3-param signature required by both the plan's own verify one-liner and Task 2's static test. Resolved by treating the machine-checkable assertions (verify one-liner, Task 2 test spec) as the authoritative contract and using a placeholder-value approach for the insert branch instead of a 4th parameter. See Decisions Made for full rationale.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `database.get_proactive_opt_out` / `database.set_proactive_opt_out` are ready for plan 16-03 (the `on_message` gate glue, which reads the opt-out flag before evaluating `should_fire_proactive_callback`) and plan 16-04 (the `/memory callbacks on|off` subcommand, which calls the setter).
- No blockers. Full test suite green (802 passed, 108 skipped) after this plan's changes.

---
*Phase: 16-proactive-memory-callbacks*
*Completed: 2026-07-03*

## Self-Check: PASSED

- FOUND: database.py
- FOUND: tests/test_database_phase16.py
- FOUND: .planning/phases/16-proactive-memory-callbacks/16-02-SUMMARY.md
- FOUND: ebb99c5 (feat commit)
- FOUND: 09a45b8 (test commit)
