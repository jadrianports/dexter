---
phase: 20-owner-control-plane-rate-observability
plan: 03
subsystem: api
tags: [gemini, rate-limiting, observability, discord.py]

requires:
  - phase: 20-owner-control-plane-rate-observability (plan 01/02)
    provides: guild_config seam, silenced/blocked reads (unrelated to this plan's counter, but same phase)
provides:
  - "guild_id: str | None = None keyword on GeminiService.chat and GeminiService.generate_image"
  - "GeminiService._guild_usage: dict[str, int] per-guild session counter"
  - "GeminiService.guild_usage(guild_id) -> int read accessor for /guilds list"
  - "guild_id threaded through cogs/ai.py (/ask, /roast, auto-queue), cogs/imagine.py (/imagine), cogs/library.py (/jam suggest), cogs/music.py (_build_roast_line + its 3 callers + /discover commentary)"
  - "services/memory.py daily_batch distill passes guild_id=None explicitly (D-09)"
affects: [20-05-events-glue, 20-07-guilds-list-command]

tech-stack:
  added: []
  patterns:
    - "Per-guild in-memory session counter alongside an existing in-memory rate limiter, incremented right after acquire() succeeds — mirrors the _RateLimiter/rpm_usage idiom already in services/gemini.py"

key-files:
  created: []
  modified:
    - services/gemini.py
    - cogs/ai.py
    - cogs/imagine.py
    - cogs/library.py
    - cogs/music.py
    - services/memory.py
    - tests/test_gemini.py

key-decisions:
  - "Extended the existing tests/test_gemini.py rather than creating a duplicate tests/test_gemini_service.py — the plan's own read_first note instructed grepping for an existing test_gemini*.py first and extending it; test_gemini.py already existed with the exact fake-client mocking idiom needed."

patterns-established:
  - "guild_id kwarg is per-session usage tagging only (RATE-01) — never a gate or quota (D-09); the increment sits after rate_limiter.acquire() succeeds, guarded by `if guild_id is not None`, so it measures budget consumption, not API success."

requirements-completed: [RATE-01]

duration: 15min
completed: 2026-07-13
---

# Phase 20 Plan 03: GeminiService Guild-Usage Observability Summary

**GeminiService now tags and counts guild-attributable chat()/generate_image() calls per session via a `guild_id` kwarg + `_guild_usage` dict, with `guild_usage()` exposed as the read path for the future `/guilds list`; embed() and guild-less calls stay untouched.**

## Performance

- **Duration:** ~15 min (implementation + full suite run)
- **Tasks:** 3/3 completed
- **Files modified:** 6

## Accomplishments
- `GeminiService` gained a `_guild_usage: dict[str, int]` session counter, a `guild_usage(guild_id)` read accessor, and a keyword-only `guild_id: str | None = None` on both `chat()` and `generate_image()`, incrementing only when `guild_id is not None` right after the rate limiter slot is acquired.
- Threaded `guild_id` through every non-events Gemini call site: `/ask` (DM-safe `None`), `/roast`, auto-queue recommendation, `/imagine`, `/jam suggest`, `_build_roast_line` (+ its three callers: repeat-song, milestone, streak), `/discover` commentary. `services/memory.py`'s `daily_batch` distill call passes `guild_id=None` explicitly with a D-09 comment.
- Locked the counting contract with 8 new unit tests in `tests/test_gemini.py`: per-guild increment, guild-less non-counting, independent multi-guild tracking, unseen-guild-returns-0, `generate_image` increments too, and `embed()`'s signature has no `guild_id` param — all with a stubbed `genai` client (zero real network calls).

## Task Commits

Each task was committed atomically:

1. **Task 1: guild_id kwarg + per-guild session counter + accessor on GeminiService** - `72536f3` (feat)
2. **Task 2: thread guild_id through the non-events Gemini call sites** - `29d9aeb` (feat)
3. **Task 3: GeminiService unit test — counting semantics** - `3307ba7` (test)

## Files Created/Modified
- `services/gemini.py` - `_guild_usage` dict, `guild_usage()` accessor, `guild_id` kwarg on `chat()`/`generate_image()`; `embed()` untouched
- `cogs/ai.py` - `/ask`, `/roast`, auto-queue recommendation chat calls now pass `guild_id`
- `cogs/imagine.py` - `/imagine` generate_image call passes `guild_id`
- `cogs/library.py` - `/jam suggest` chat call passes `guild_id`
- `cogs/music.py` - `_build_roast_line` gained keyword-only `guild_id` param forwarded to its chat call; all 3 callers + `/discover` commentary pass `guild_id`
- `services/memory.py` - `daily_batch` distill call passes `guild_id=None` explicitly (D-09)
- `tests/test_gemini.py` - 8 new tests locking the guild_id counting contract

## Decisions Made
- Extended the pre-existing `tests/test_gemini.py` instead of creating `tests/test_gemini_service.py` (which the plan frontmatter listed but the plan's own `read_first` guidance for Task 3 explicitly said to grep for an existing `test_gemini*.py` and extend it rather than duplicate — `test_gemini.py` already existed with the exact `_mock_service_and_generate` fake-client pattern needed).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - file naming] Extended tests/test_gemini.py instead of creating tests/test_gemini_service.py**
- **Found during:** Task 3
- **Issue:** Plan frontmatter's `files_modified` listed `tests/test_gemini_service.py`, but the plan's own Task 3 `read_first` note said "grep for an existing `test_gemini*.py` FIRST ... extend it if present rather than creating a duplicate" — and `tests/test_gemini.py` already existed with a matching mock idiom (`_mock_service_and_generate`).
- **Fix:** Added the new `TestGeminiGuildUsageCounter` class + `_mock_image_response` helper to `tests/test_gemini.py`, reusing the existing patch-`services.gemini.genai` pattern.
- **Files modified:** `tests/test_gemini.py`
- **Verification:** `pytest tests/test_gemini.py -q` — 18 passed (10 pre-existing + 8 new)
- **Committed in:** `3307ba7` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (file-target correction per the plan's own explicit guidance)
**Impact on plan:** No scope creep — same test coverage the plan specified, just placed in the pre-existing file per the plan's own Wave-0 grep instruction. All `must_haves.artifacts` intent (unit coverage: guild_id increments, None not counted, embed untagged) is satisfied.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `GeminiService.guild_usage()` is ready for 20-07's `/guilds list` to read.
- `cogs/events.py:185/565` (the two ambient/vision Gemini call sites) are deliberately left unthreaded here — owned by 20-05 per this plan's scope note, avoiding a file-conflict with that plan's wave.
- Full suite green: `pytest tests/ -q` → 961 passed, 121 skipped, 0 failed.

---
*Phase: 20-owner-control-plane-rate-observability*
*Completed: 2026-07-13*
