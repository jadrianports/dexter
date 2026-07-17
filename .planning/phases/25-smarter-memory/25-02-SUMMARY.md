---
phase: 25-smarter-memory
plan: 02
subsystem: database
tags: [pgvector, rag-memory, gemini, accuracy-firewall, vision]

# Dependency graph
requires:
  - phase: 25-smarter-memory
    provides: "25-01's database.reinforce_memory_expiry + recall() step 7b (this plan's vision_roast rows compose with that reinforcement on future recall)"
  - phase: 17-vision-multimodal-roasting
    provides: "_maybe_fire_vision_roast, _generate_vision_roast (str|None), build_vision_prompt's appearance conduct clause"
  - phase: 13-semantic-music-memory
    provides: "the new-kind-not-new-table precedent (taste_episode) this plan's vision_roast kind mirrors exactly"
provides:
  - "config.MEMORY_SALIENCE_BASE_WEIGHTS['vision_roast'] = 0.4 + config.MEMORY_DECAY_DAYS_BY_KIND['vision_roast'] = TASTE_DECAY_DAYS — two additive dict entries, zero DDL"
  - "cogs/events.py::_maybe_fire_vision_roast fire-and-forget distill_and_remember(kind='vision_roast') write on the success path"
  - "tests/test_database_phase25.py::TestVisionRoastMemory — live-DB write-through-firewall round-trip coverage"
affects: [future-memory-phases, 26-dj-radio-mode]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fake-Gemini + real-pool live-DB test split: MemoryService(pool, fake_gemini) where fake_gemini stubs chat()/embed() deterministically, letting distill_and_remember's real insert/dedup/cap SQL run against a genuine Postgres round-trip"

key-files:
  created: []
  modified:
    - config.py
    - cogs/events.py
    - tests/test_vision_events.py
    - tests/test_database_phase25.py

key-decisions:
  - "raw_text=line is the roast LINE _generate_vision_roast already produced — no second AI/vision call (D-03); appearance safety is inherited from Phase 17's build_vision_prompt conduct clause, not re-implemented here"
  - "exempt_numbers is never passed by the caller — distill_and_remember computes it internally as (kind == 'taste_episode'), so vision_roast automatically gets the FULL is_sensitive + contains_number firewall (D-04)"
  - "bare asyncio.create_task (not make_task) to match this file's own local convention at the existing ambient fire-and-forget site, not cogs/ai.py's different idiom"
  - "tests/test_vision_events.py::_make_bot() now sets memory_service=None explicitly, isolating the reply/cooldown-focused glue tests from the new write side-effect; the write itself is covered live-DB-side by TestVisionRoastMemory, consistent with the Phase 16/17 'Discord glue is untested-by-design' precedent"

patterns-established:
  - "Pattern: fake-Gemini-service + real-pool live-DB integration test for any future MemoryService write-path feature needing a genuine Postgres round-trip without a real Gemini API key"

requirements-completed: [MEM-07]

# Metrics
duration: 35min
completed: 2026-07-16
---

# Phase 25 Plan 02: MEM-07 Vision → RAG Memory Summary

**A successful vision roast now leaves behind its own low-salience, short-decay `vision_roast` memory — distilled from the roast line Dex already said, run through the full accuracy/PII firewall, with zero new tables and zero second AI call.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 2/2 completed
- **Files modified:** 4 (config.py, cogs/events.py, tests/test_vision_events.py, tests/test_database_phase25.py)

## Accomplishments
- `vision_roast` registered as a new memory kind via two additive `config.py` dict entries (salience 0.4 — below the 0.5 sweep floor — and decay `TASTE_DECAY_DAYS`), the exact Phase 13 `taste_episode` new-kind-not-new-table precedent. Zero DDL.
- `cogs/events.py::_maybe_fire_vision_roast` fires a guild-stamped, fire-and-forget `distill_and_remember(kind="vision_roast")` write strictly after a successful `message.reply` (never on `line is None`, never pre-send) — `raw_text` is the roast line itself, not the image, so the write inherits Phase 17's appearance conduct clause without a second vision call.
- Live-DB `TestVisionRoastMemory` (3 new tests) proves the full round-trip: a safe line stores exactly one `vision_roast` row with the correct low salience and ~30-day horizon; a number-bearing line and a sensitive line are each firewalled to zero rows — locking in that `exempt_numbers=False` (the full firewall) is genuinely in force for this kind.
- Verified against a real `pgvector/pgvector:pg16` container (not just mocked): all 10 `tests/test_database_phase25.py` tests pass, and the full suite (1164 tests) is green with the live DB wired, confirming SC-3 (every pre-existing kind stays byte-identical).

## Task Commits

Each task was committed atomically:

1. **Task 1: Register vision_roast kind + wire the fire-and-forget write** - `9412c45` (feat) — includes the `tests/test_vision_events.py::_make_bot()` fix required to keep the pre-existing reply/cooldown glue tests passing (see Deviations).
2. **Task 2: Add TestVisionRoastMemory** - `73d2648` (test)

**Plan metadata:** (this commit, docs — skipped per `commit_docs: false`, see below)

## Files Created/Modified
- `config.py` - two additive dict entries: `MEMORY_SALIENCE_BASE_WEIGHTS["vision_roast"] = 0.4`, `MEMORY_DECAY_DAYS_BY_KIND["vision_roast"] = TASTE_DECAY_DAYS`
- `cogs/events.py` - `_maybe_fire_vision_roast` gains a fire-and-forget `distill_and_remember(kind="vision_roast", ...)` call after the cooldown-mark line, guarded by `getattr(self.bot, "memory_service", None)`
- `tests/test_vision_events.py` - `_make_bot()` now sets `memory_service = None` explicitly (was implicitly a truthy `MagicMock()` auto-attribute, which broke `asyncio.create_task` once the new write call landed)
- `tests/test_database_phase25.py` - new `TestVisionRoastMemory` class (3 live-DB tests) + a `_fake_gemini()` helper, appended after the 25-01 `test_recall_does_not_mutate_salience_or_hit_count` test

## Decisions Made
- Followed the plan's/research's exact recommended shape: bare `asyncio.create_task` (not `make_task`), `raw_text=line` (never the image), no `exempt_numbers` kwarg at the call site (it isn't a parameter of `distill_and_remember` — the full firewall applies automatically because `kind != "taste_episode"`).
- Test isolation choice: rather than making `test_vision_events.py`'s glue tests also assert on the new fire-and-forget write (which would require awaiting/flushing a background task and reaching into a real or heavily-mocked `MemoryService`), the write path is fully covered by the live-DB `TestVisionRoastMemory` round-trip instead — matching the existing Phase 16/17 "Discord glue is untested-by-design; pure/service logic is" split documented in `TESTING.md`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `tests/test_vision_events.py`'s pre-existing reply-path tests broke once the new write call landed**
- **Found during:** Task 1 verification (`pytest tests/ -k "vision or memory or config"`)
- **Issue:** `_make_bot()` constructs `bot = MagicMock()` without an explicit `memory_service` attribute. `getattr(self.bot, "memory_service", None)` on a bare `MagicMock()` auto-generates a truthy child `MagicMock`, not `None` — so the new `if memory_service is not None:` branch in `_maybe_fire_vision_roast` now evaluated True during `test_transport_fallback_replies` and `test_reply_anchor_and_cooldown_mark`, and `asyncio.create_task(memory_service.distill_and_remember(...))` raised `TypeError: a coroutine was expected` because a plain `MagicMock()` call returns another `MagicMock`, not an awaitable.
- **Fix:** Set `bot.memory_service = None` explicitly in `_make_bot()`, with a docstring note explaining why (isolates these reply/cooldown-focused tests from the new MEM-07 write side-effect; the write itself is covered by the live-DB `TestVisionRoastMemory` added in Task 2).
- **Files modified:** tests/test_vision_events.py
- **Verification:** `pytest tests/ -k "vision or memory or config" -q` → 284 passed, 9 skipped (was 2 failed beforehand).
- **Committed in:** 9412c45 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (bug — pre-existing test broke by a load-bearing new code path, directly caused by this task's own change)
**Impact on plan:** Necessary fix for the plan's own acceptance criterion ("full suite green") to hold non-vacuously. No scope creep — the fix is scoped to the exact mock gap the new code path exposed.

## Issues Encountered
None beyond the test-mock fix above. To positively verify the live-DB SC-2 path (rather than trust the logic alone), a temporary local `pgvector/pgvector:pg16` Docker container was spun up and torn down for this session only (not part of the repo/CI config) — all 10 `tests/test_database_phase25.py` tests and the full 1164-test suite passed against it.

## User Setup Required
None - no external service configuration required. The three new live-DB tests skip locally (no `TEST_DATABASE_URL` set) and run in CI's `pgvector/pgvector:pg16` service container, per the existing `_SKIP_LIVE` guard from 25-01.

## Next Phase Readiness
- MEM-07 is fully shipped: `vision_roast` is a genuine new kind (two additive config entries, zero DDL), written only on a successful roast, guild-stamped, and subject to the full accuracy/PII firewall — composes with 25-01's MEM-06 reinforcement (a vision moment Dex keeps recalling has its expiry pushed out and survives; a one-off decays on the 30-day horizon).
- Phase 25 "Smarter Memory" is now code-complete: both MEM-06 (25-01) and MEM-07 (25-02) are shipped, full suite green (1164 passed / 0 failed verified against a live pgvector container), zero new tables/limiters/schema forks, the kind-agnostic `MemoryService` API untouched.
- Note on doc commits: this project's `commit_docs: false` config means this SUMMARY.md, STATE.md, and ROADMAP.md updates will not be force-committed via the SDK's `commit` verb (expected `skipped_commit_docs_false` outcome) — they are written to disk per the configured behavior.

---
*Phase: 25-smarter-memory*
*Completed: 2026-07-16*

## Self-Check: PASSED

All created/modified files confirmed present (config.py, cogs/events.py, tests/test_vision_events.py, tests/test_database_phase25.py, this SUMMARY.md). Both task commit hashes (9412c45, 73d2648) confirmed present in git log.
