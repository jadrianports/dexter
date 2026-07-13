---
phase: 21-memory-scoping-guild-data-lifecycle
plan: 03
subsystem: memory
tags: [pgvector, rag-memory, guild-scoping, discord-cogs, tdd]

# Dependency graph
requires:
  - phase: 21-memory-scoping-guild-data-lifecycle
    plan: 01
    provides: "database.search_memories() optional guild_id filter + MemoryService.recall() keyword-only guild_scoped opt-in (default False = global)"
provides:
  - "5 recall() call sites opted into guild_scoped=True (or bool(guild_id)): /roast, auto-queue taste blend, ambient voice-join roast, proactive callback, music-command callback"
  - "/ask deliberately left un-scoped (global recall) with an inline comment + two independent regression tests (behavioral + source) locking MEM-02"
  - "cogs/music.py::_build_roast_line no longer passes a bare \"\" placeholder guild_id into recall — real guild_id threaded through"
affects: [21-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Discriminator for guild-scoping opt-in is 'explicit synchronous self-pull stays global; unprompted ambient broadcast to a channel scopes' — NOT 'self vs third party by user_id' (the two events.py surfaces and the music.py callback all recall the SAME user the event is about and would be misclassified as safe under the wrong rule)"
    - "guild_scoped=bool(guild_id) instead of a bare True guards against silently narrowing recall to the NULL corpus when the caller's own guild_id param is unset/empty"

key-files:
  created: []
  modified:
    - cogs/ai.py
    - cogs/events.py
    - cogs/music.py
    - tests/test_ambient_recall_cadence.py
    - tests/test_autoqueue_wiring.py

key-decisions:
  - "guild_scoped=bool(guild_id) (not a bare True) on the music-command callback, because _build_roast_line's guild_id param defaults to None — a bare True with an empty-string guild_id would silently narrow recall to the NULL corpus"
  - "/ask's inline comment explaining why it stays un-scoped deliberately avoids the literal substring 'guild_scoped' — inspect.getsource() includes comments, so a comment containing that literal would fail the MEM-02 source-inspection regression test it's meant to protect"

requirements-completed: [MEM-01, MEM-02]

# Metrics
duration: 18min
completed: 2026-07-14
---

# Phase 21 Plan 03: Memory Read-Path Call-Site Guild-Scoping Wiring Summary

**5 of 6 `recall()` call sites now pass `guild_scoped=True` (or `bool(guild_id)`) — the substrate from plan 21-01 goes live; `/ask` is the sole deliberate exception, proven by two independent regression tests.**

## Performance

- **Duration:** ~18 min
- **Tasks:** 3 completed
- **Files modified:** 3 cog files + 2 test files

## Accomplishments
- `/roast @user` now recalls the target's memories scoped to the current guild — a third party's memories from another server never travel into a roast (`cogs/ai.py::roast`).
- The auto-queue positive-taste blend now recalls other in-voice members' `taste_episode` facts scoped to the current guild, closing a cross-guild taste-bleed path that previously blended a member's Guild-A taste into a Guild-B room recommendation.
- Both `cogs/events.py` ambient/unprompted surfaces (voice-join roast, proactive message callback) now recall guild-scoped memories — the two clearest instances of "the leak MEM-01 names" (an unprompted broadcast into a channel).
- `cogs/music.py::_build_roast_line`'s recall call no longer passes a bare `""` placeholder guild_id — it now threads the function's own real `guild_id` param and opts in via `guild_scoped=bool(guild_id)`, guarding against silently narrowing to the NULL-guild_id corpus if ever called without one.
- `/ask` was proven, not just left alone: two independent regression tests (`test_ask_recall_is_never_guild_scoped` behavioral + `TestGuildScopedOptIns.test_ask_callback_never_mentions_guild_scoped` source-level) both assert the literal string `guild_scoped` never appears in its call or its source — the single most likely silent regression in the phase (a well-meaning "consistency fix") is now caught by two nets, not one.
- Sanity-verified the regression lock actually bites: temporarily deleted `guild_scoped=True` from the `/roast` call, confirmed `pytest tests/test_ambient_recall_cadence.py` failed with the expected assertion, then restored (verified zero diff afterward).

## Task Commits

Each task was committed atomically:

1. **Task 1: cogs/ai.py — /roast and auto-queue opt in; /ask stays global (MEM-01 + MEM-02)** - `077f07e` (feat)
2. **Task 2: cogs/events.py + cogs/music.py — the three ambient recall surfaces opt in (MEM-01)** - `f4bb63e` (feat)
3. **Task 3: per-call-site scoping tests — 5 opt-ins locked True, /ask locked global (MEM-01 / MEM-02)** - `a3278c7` (test)

**Plan metadata:** (this commit) — docs: complete plan

## Files Created/Modified
- `cogs/ai.py` — `/roast` recall call gains `guild_scoped=True`; auto-queue taste-blend recall gains `guild_scoped=True` alongside the existing `kind="taste_episode"`; `/ask` recall call left byte-identical except for a new explanatory comment (deliberately never contains the literal `guild_scoped`).
- `cogs/events.py` — ambient voice-join roast recall (`_generate_ambient_roast`'s internal gated block) gains `guild_scoped=True`; proactive callback recall (`_maybe_fire_proactive_callback`) gains `guild_scoped=True`.
- `cogs/music.py` — `_build_roast_line`'s recall call replaces the `""` placeholder guild_id with the function's own `guild_id` param (`guild_id or ""`) and adds `guild_scoped=bool(guild_id)`; the stale "guild_id reserved" comment is deleted.
- `tests/test_ambient_recall_cadence.py` — extended `test_roast_always_recalls_target_scoped` with a `guild_scoped=True` kwarg assertion; added `test_ask_recall_is_never_guild_scoped` (behavioral MEM-02 lock); added `test_ambient_roast_recall_is_guild_scoped` (behavioral, forces the cadence gate via `patch("cogs.events.random.random", return_value=0.0)`); added `TestGuildScopedOptIns` (3 source-inspection tests: proactive callback, music callback, second `/ask` net).
- `tests/test_autoqueue_wiring.py` — added `TestGuildScopedTasteBlend.test_taste_blend_recall_is_guild_scoped` asserting both `kind="taste_episode"` and `guild_scoped=True` appear in `try_auto_queue`'s source.

## Decisions Made
- The discriminator resolved by research and locked in the plan objective — "explicit synchronous self-pull stays global; unprompted ambient broadcast to a channel scopes" — was followed exactly. It is not "self vs third party by user_id"; under that wrong rule the two `events.py` surfaces and the `music.py` callback (which all recall the SAME user the event is about) would have been misclassified as safe and left un-scoped.
- `guild_scoped=bool(guild_id)` on the music-command callback rather than a bare `True`, per the plan's explicit T-21-08 mitigation — `_build_roast_line`'s `guild_id` param defaults to `None`, so a bare `True` combined with an unset guild_id would have silently narrowed recall to the NULL-guild_id corpus.
- The `/ask` inline comment was worded to avoid the literal substring `guild_scoped` entirely (using "no guild-scoping kwarg" instead) — `inspect.getsource()` captures comments, so a comment containing that literal would have broken the very MEM-02 regression test (`TestGuildScopedOptIns.test_ask_callback_never_mentions_guild_scoped`) it exists to protect. This was caught and fixed during Task 1 execution (see Deviations).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `/ask` explanatory comment accidentally tripped its own MEM-02 regression test**
- **Found during:** Task 1
- **Issue:** The first-draft inline comment at the `/ask` recall call read "deliberately NOT guild_scoped" — since `inspect.getsource()` includes comments, this made `'guild_scoped' in inspect.getsource(cogs.ai.AICog.ask.callback)` evaluate `True`, which is exactly the condition Task 1's own acceptance criteria (and Task 3's later `test_ask_callback_never_mentions_guild_scoped`) forbid.
- **Fix:** Reworded the comment to convey the same intent ("deliberately stays global — no guild-scoping kwarg here... Do not 'fix' this to match /roast's opt-in") without ever using the literal substring `guild_scoped`.
- **Files modified:** `cogs/ai.py`
- **Verification:** `inspect.getsource(cogs.ai.AICog.ask.callback)` re-checked to confirm `'guild_scoped' not in src`; full Task 1 verification suite re-run green.
- **Committed in:** `077f07e` (part of Task 1 commit — caught before commit, not a separate fix commit)

---

**Total deviations:** 1 auto-fixed (1 bug, caught and fixed in-flight before the task commit)
**Impact on plan:** No scope creep — the fix is a comment wording change with zero functional impact, caught by the plan's own acceptance criteria before commit.

## Issues Encountered

None beyond the deviation above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All 5 guild-scoping opt-ins are live and individually regression-locked; `/ask` is provably global via two independent tests. This is the exact artifact set plan 21-04 (guild lifecycle purge wiring) can build on without re-touching the read path.
- Full suite green: `pytest tests/test_ambient_recall_cadence.py tests/test_autoqueue_wiring.py tests/test_roast_command.py tests/test_proactive_events.py tests/test_memory.py -x` (all pass) and the whole-repo `pytest -q` — **1006 passed, 124 skipped, 0 failed**.
- `ruff check cogs/ai.py cogs/events.py cogs/music.py tests/` — clean.
- `grep -n "guild_scoped" cogs/*.py` returns exactly 5 opt-in sites (ai.py x2, events.py x2, music.py x1) and zero hits inside `/ask`'s callback — verified directly, matching the plan's `<verification>` block exactly.
- No blockers for plan 21-04.

---
*Phase: 21-memory-scoping-guild-data-lifecycle*
*Completed: 2026-07-14*
