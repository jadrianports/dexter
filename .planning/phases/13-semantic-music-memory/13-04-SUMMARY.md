---
phase: 13-semantic-music-memory
plan: 04
subsystem: bot
tags: [discord.py, tasks-loop, taste-memory, background-jobs]

# Dependency graph
requires:
  - phase: 13-semantic-music-memory (plan 01)
    provides: config.TASTE_* knobs, MEMORY_SALIENCE_BASE_WEIGHTS["taste_episode"], logic/taste.py (has_min_activity/summarize_taste)
  - phase: 13-semantic-music-memory (plan 02)
    provides: database.get_active_taste_users, database.get_user_artist_activity
  - phase: 13-semantic-music-memory (plan 03)
    provides: services/memory.py::remember() kind-aware insert horizon + dedup self-refresh for taste_episode
provides:
  - "bot.py::taste_distill_batch — daily @tasks.loop that reads structured song_history, pre-buckets number-free via logic.taste, and writes kind=taste_episode facts via memory_service.distill_and_remember"
  - "taste_distill_batch registered at all three boot sites: start-guard, _cleanup_partial_init stop-list (WR-04), and both 'Loops stopped:' docstrings"
affects: [14-smarter-music-brain]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "taste_distill_batch clones the memory_distill_batch @tasks.loop shape exactly: getattr(bot, ..., None) no-op guard, per-user try/except swallow, paired .before_loop (wait_until_ready) / .error (_post_loop_error) handlers."
    - "The loop is the last composition point of the phase's pure/DB/service seams — logic/taste.py's number-free phrase output is joined directly into raw_text with zero digit interpolation at the call site (Critical Rule 12 enforced structurally, not just by the downstream contains_number() backstop)."

key-files:
  created: []
  modified: [bot.py]

key-decisions:
  - "taste_distill_batch scheduled at config.TASTE_DISTILL_BATCH_HOUR (05:00 UTC) — the only free slot distinct from cache_cleanup (hourly), memory_sweep (02:30), memory_distill_batch (03:00), and ytdlp_update (04:00), per D-06/D-07/T-13-05."
  - "guild_id is carried through to distill_and_remember (unlike daily_batch's None) since taste is guild-scoped listening — matches 13-PATTERNS.md guidance, not an inherited daily_batch convention."
  - "raw_text is built as a single joined string prefixed 'Listening activity this week: ' from summarize_taste's phrases only — no f-string count interpolation anywhere in the loop body (verified by source-read, not just test)."
  - "Added `import database` (module-level, not just `from database import init_db`) and `from logic import taste as logic_taste` to bot.py's import block — bot.py previously had no bare `database.*` call sites, so this is a genuinely new import, not a redundant one."

patterns-established:
  - "This is the third @tasks.loop added under the memory_distill_batch/memory_sweep sibling pattern (Phase 11 established it, Phase 13 extends it) — any future daily batch (e.g. Phase 16 proactive callbacks) should follow the same three-site registration discipline (start-guard, stop-list, docstrings) and the same getattr-guard + per-item try/except shape."

requirements-completed: [TASTE-01, TASTE-03]

# Metrics
duration: 11min
completed: 2026-07-02
---

# Phase 13 Plan 04: Taste Distill Batch Task Summary

**A new daily `bot.py::taste_distill_batch` `@tasks.loop` (05:00 UTC) that reads structured `song_history`, pre-buckets counts to number-free phrases via `logic/taste.py`, and writes `kind="taste_episode"` facts through `memory_service.distill_and_remember`, registered at all three boot-safety sites.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-07-02T10:18:00Z
- **Completed:** 2026-07-02T10:29:00Z
- **Tasks:** 2
- **Files modified:** 1 (bot.py)

## Accomplishments
- Added `taste_distill_batch` as a module-scope `@tasks.loop(time=datetime.time(hour=config.TASTE_DISTILL_BATCH_HOUR, minute=0))`, cloning `memory_distill_batch`'s shape: `getattr(bot, "memory_service"/"pool", None)` no-op guard, per-user try/except swallow (log.debug on failure), and paired `.before_loop`/`.error` handlers.
- Wired the full read → gate → band → write pipeline: `database.get_active_taste_users` → `logic_taste.has_min_activity` (D-08 gate) → `database.get_user_artist_activity` → `logic_taste.summarize_taste` (D-02 number-free pre-bucketing) → `memory_service.distill_and_remember(kind="taste_episode", ...)`.
- Registered the loop at all three boot sites: the start-guard block (`if not taste_distill_batch.is_running(): taste_distill_batch.start()`), the `_cleanup_partial_init` stop-list tuple (the load-bearing WR-04 site — a botched boot must not leave the loop firing against a torn-down pool), and both "Loops stopped:" docstring/comment lists.
- Confirmed zero digit-interpolation in `raw_text` construction — the string is assembled solely from `summarize_taste`'s fixed template phrases (Critical Rule 12 / accuracy firewall).
- Full existing test suite remains green: 649 passed, 98 skipped — no import/boot regression introduced by the new loop or the new `import database` / `from logic import taste as logic_taste` module-level imports.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the taste_distill_batch @tasks.loop (read → band → write) + before_loop/error pair** - `08370ba` (feat)
2. **Task 2: Register taste_distill_batch at all three boot sites** - `bf68a92` (feat)

**Plan metadata:** _pending — added by the final metadata commit step_

## Files Created/Modified
- `bot.py` - Added `import database` and `from logic import taste as logic_taste`; new `taste_distill_batch` `@tasks.loop` + `before_taste_distill_batch` + `on_taste_distill_batch_error`; registered at the start-guard block, the `_cleanup_partial_init` stop-list tuple, and both "Loops stopped:" docstring/comment lists.

## Decisions Made
- Placed the new loop definition immediately after `memory_sweep`'s `.error` handler and before `status_rotation`, keeping the Phase 11 `memory_distill_batch`/`memory_sweep` pair visually together while still living in the same "sibling loop" neighborhood the plan's `read_first` anchors pointed at.
- Used `datetime.datetime.now(datetime.timezone.utc)` (fully qualified through the module-level `import datetime`, since bot.py does not do `from datetime import ...`) rather than adding a second import style — keeps the diff to the import block minimal and consistent with the rest of the file's `datetime.time(...)` usage in the other loop decorators.

## Deviations from Plan

None - plan executed exactly as written. `import database` and `from logic import taste as logic_taste` were added to bot.py's import block per the plan's explicit instruction to "confirm `database` ... [is] already imported" — bot.py only had `from database import init_db` previously (no bare `database.*` call sites existed), so this import was a required, plan-anticipated addition rather than an unplanned deviation.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. Zero new package installs (threat model T-13-SC "accept" disposition confirmed).

## Next Phase Readiness
- Phase 13 (Semantic Music Memory) is now fully wired end-to-end: config knobs (13-01) → pure classification logic (13-01) → DB aggregate helpers (13-02) → kind-aware self-refreshing memory service (13-03) → the daily batch task composing all of it (13-04).
- Phase 14 (Smarter Music Brain) can now rely on `kind="taste_episode"` rows existing in `user_memories` as a retrievable substrate for taste-aware auto-queue (`BRAIN-01`) and discovery (`BRAIN-02`).
- Live-runtime verification that the loop actually fires and writes real rows against Neon is deferred behind the same parked-host constraint as the rest of the Phase 09/11 live-UAT tail (STATE.md Deferred Items) — this plan's scope was code-complete wiring + full-suite-green regression gate, matching the established Discord/process-code verification convention (structural review + clean local boot, not a live Discord session).
- No blockers.

---
*Phase: 13-semantic-music-memory*
*Completed: 2026-07-02*

## Self-Check: PASSED

- FOUND: bot.py
- FOUND: .planning/phases/13-semantic-music-memory/13-04-SUMMARY.md
- FOUND: 08370ba (Task 1 commit)
- FOUND: bf68a92 (Task 2 commit)
- FOUND: 72c77c2 (SUMMARY commit)
