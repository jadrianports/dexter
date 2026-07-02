---
phase: 15-rag-reach
plan: 03
subsystem: discord-commands
tags: [discord.py, app_commands, rag, memory, trust]

# Dependency graph
requires:
  - phase: 15-rag-reach (plan 01)
    provides: database.list_user_memories, database.delete_all_user_memories (single-identity-param DELETE)
provides:
  - "cogs/memory.py — MemoryCog with /memory view (RAG-03) and /memory forget (RAG-04)"
  - "MemoryPageView — ephemeral verbatim-facts paginator cloned from LyricsPageView"
  - "ForgetConfirmView — one-shot danger-styled Confirm/Cancel nuke-all view cloned from JamSuggestConfirmView"
  - "config.MEMORY_VIEW_PAGE_SIZE knob"
  - "cogs.memory registered at both bot.py cog-load sites"
affects: [16-proactive-memory-callbacks (hard-depends on /memory forget being a verified real deletion)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Verbatim-fact display view: clone LyricsPageView's pre-chunked pages: list[str] paginator shape rather than re-deriving pagination from a live query each button press"
    - "Nuke-all confirm view: clone JamSuggestConfirmView's _used-guard + disable-before-async-work + finite-timeout shape, but ButtonStyle.danger (not .success) for the one irreversible confirm in the family"
    - "Empty-state short-circuit before constructing any view (Pitfall 5) — /memory forget with 0 stored facts never sends a Confirm/Cancel view at all"

key-files:
  created: [cogs/memory.py, tests/test_memory_command.py]
  modified: [bot.py, config.py]

key-decisions:
  - "MemoryPageView keeps LyricsPageView's exact button/on_timeout/AllowedMentions.none() shape, changing only the embed title (drop the 'Lyrics —' prefix) and color (0x9B59B6 purple, distinct from lyrics blurple)"
  - "ForgetConfirmView wording is careful not to promise 'never mention me again' (Pitfall 4) — it describes only what actually happens: stored memories, including taste episodes, are wiped; ambient behavior is a separate Phase 16 control"

patterns-established:
  - "One-shot destructive-action confirm views in this codebase use ButtonStyle.danger only for the single truly irreversible action in a family (nuke-all forget), reserving .success for non-destructive confirms (jam suggest save)"

requirements-completed: [RAG-03, RAG-04]

# Metrics
duration: 15min
completed: 2026-07-03
---

# Phase 15 Plan 3: /memory view + /memory forget — the RAG Trust Escape Hatch Summary

**New `cogs/memory.py` cog shipping `/memory view` (verbatim, ephemeral, paginated fact display) and `/memory forget` (live-SQL count preview + red Confirm/Cancel nuke-all), registered at both `bot.py` cog-load sites, locked by 8 mock-only tests.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-03T00:00:00Z (approx.)
- **Completed:** 2026-07-03T00:15:00Z (approx.)
- **Tasks:** 3 completed
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `/memory view` — an ephemeral, paginated embed showing a user's stored memory facts VERBATIM (no Gemini paraphrase, D-02), capped at `config.MEMORY_MAX_PER_USER` so the view can never show fewer facts than forget erases (Pitfall 2 / T-15-12).
- `/memory forget` — a live-SQL count preview followed by a `ButtonStyle.danger` Confirm/Cancel view; only a Confirm press calls `database.delete_all_user_memories(pool, user_id)`; Cancel and timeout leave memories untouched; an empty store skips the confirm view entirely (Pitfall 5).
- `cogs.memory` registered in both `bot.py` cog-load sites (the normal-boot tuple and the first-run-sync block), keeping the two lists in sync per the in-file drift warning.
- Neither subcommand accepts a `target`/`user` parameter — both are structurally self-scoped to `str(interaction.user.id)` (V4), enforced by a signature-inspection test.

## Task Commits

Each task was committed atomically:

1. **Task 1: cogs/memory.py — MemoryCog + /memory group + view subcommand + MemoryPageView + config knob** - `fc69f81` (feat)
2. **Task 2: forget subcommand + ForgetConfirmView + register cogs.memory in bot.py** - `175b3e5` (feat)
3. **Task 3: tests/test_memory_command.py — view + forget handler coverage** - `76040e8` (test)

**Plan metadata:** (this commit, following SUMMARY creation)

## Files Created/Modified
- `cogs/memory.py` - New file: `MemoryCog` (`/memory view`, `/memory forget`), `MemoryPageView` (verbatim-facts paginator, clone of `LyricsPageView`), `ForgetConfirmView` (danger-styled one-shot nuke-all confirm, clone of `JamSuggestConfirmView`), `_chunk_facts_into_pages` helper, `setup(bot)`. Authored in full during Task 1's `Write` (view + forget both present from the start); Task 2's commit captured the `bot.py` registration diff since the cog file itself had no incremental changes left to stage.
- `bot.py` - Added `"cogs.memory"` to the non-AI cog-load tuple (~:442) and `await bot.load_extension("cogs.memory")` to the first-run-sync block (~:1125-1126), keeping both lists in sync.
- `config.py` - Added `MEMORY_VIEW_PAGE_SIZE = 10` immediately after `MEMORY_DISTILL_BATCH_HOUR` in the Phase 11 `MEMORY_*` block.
- `tests/test_memory_command.py` - New file: 8 mock-only tests (no live DB/Discord) covering verbatim/ephemeral view, empty-state view, the `MEMORY_MAX_PER_USER` cap regression, forget's empty-state skip, Confirm-deletes, Cancel-leaves-memories, and the no-target-param structural guard.

## Decisions Made
- Wrote the entire `cogs/memory.py` file (view + forget + both views) in Task 1's single `Write` call rather than splitting the file edit strictly task-by-task, since the file is small and cohesive; the automated verification for each task still passed independently against the final file content. Task 2's commit correctly captured only the remaining diff (`bot.py` registration).
- `MemoryPageView`'s embed color is `0x9B59B6` (purple) — deliberately distinct from `LyricsPageView`'s `0x5865F2` blurple so the two paginated views are visually distinguishable.
- Kept `ForgetConfirmView`'s wiped-confirmation wording strictly accurate per Pitfall 4: it says the stored memories (including taste picked up from listening history) are gone, and does NOT claim Dexter will "never mention you again" — that's a separate, not-yet-built Phase 16 control.

## Deviations from Plan

None — plan executed exactly as written. All three tasks matched their `<action>` blocks precisely. The only adjustment was a self-inflicted wording fix caught during Task 1 verification: an inline comment originally contained the literal substring `MEMORY_INJECT_CAP` (as prose warning against using it), which tripped the plan's own `'MEMORY_INJECT_CAP' not in vs` verification assertion — reworded the comment to describe the constant without naming it literally. Not a Rule 1-4 trigger; caught and fixed before the Task 1 commit, so no separate commit was needed.

## Issues Encountered

One test-authoring issue caught and fixed before finalizing Task 3: the initial `test_forget_confirm_deletes` and `test_forget_cancel_leaves_memories` tests drove `ForgetConfirmView.confirm_button` / `.cancel_button` *outside* the `unittest.mock.patch(...)` context manager that mocked `database.delete_all_user_memories`, so the button press fell through to the real (unmocked) database function and raised a `TypeError` on a `MagicMock` coroutine. Fixed by moving the button-press call inside the same `with patch(...)` block as the initial `/memory forget` invocation. Verified via a clean `pytest tests/test_memory_command.py -x -q` run (8 passed) and the full regression suite.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `/memory view` and `/memory forget` are shipped, registered, and test-locked — Phase 16 (proactive memory callbacks) is unblocked on its hard dependency: a verified real, self-scoped, confirm-gated deletion path now exists.
- Full regression suite green: `pytest tests/ -x -q` → 781 passed, 106 skipped, 0 failed.
- `cogs.memory` count (`grep -c "cogs.memory" bot.py`) = 2 (both load sites), matching the plan's structural verification requirement.
- Outstanding: this cog has not been exercised against a live Discord gateway / live pgvector Postgres — that live-runtime verification is deferred consistent with the rest of Phase 09/11/15's live-Discord UAT tail (parked behind an always-on host), not a blocker for Phase 15 code-complete status.

---
*Phase: 15-rag-reach*
*Completed: 2026-07-03*
