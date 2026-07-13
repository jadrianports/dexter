---
phase: 20-owner-control-plane-rate-observability
plan: 05
subsystem: reliability
tags: [discord.py, toctou, rate-observability, ambient-roasts, vision, testing]

# Dependency graph
requires:
  - phase: 20-owner-control-plane-rate-observability
    provides: "20-02's silence-aware is_ambient_channel/decide_ambient_channel (logic/guild_config.py); 20-03's guild_id kwarg on GeminiService.chat/generate_image"
provides:
  - "TOCTOU pre-send re-check in _maybe_fire_proactive_callback and _maybe_fire_vision_roast (D-14 / SC-2)"
  - "guild_id threaded through the two remaining events.py Gemini call sites (RATE-01 complete for cogs/events.py)"
  - "Silenced-mid-flight regression coverage locking the no-stale-response invariant"
affects: [20-06, 20-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pre-send re-check: re-evaluate the same pure predicate (is_ambient_channel) a second time, immediately before the side-effecting send, instead of trusting the entry-point gate for a seconds-long async window"

key-files:
  created: []
  modified:
    - cogs/events.py
    - tests/test_proactive_events.py
    - tests/test_vision_events.py

key-decisions:
  - "Reused is_ambient_channel (the same silence-aware predicate 20-02 built) for the pre-send re-check rather than inventing a second mechanism — a literal second read of the same cache (D-14)"
  - "Fixed tests/test_vision_events.py::_make_bot to mock a real guild_config row (Rule 3 auto-fix) — an un-mocked MagicMock().get(...) is truthy for every key including 'silenced', which made the new pre-send re-check bail on every existing reply-path test"

patterns-established:
  - "Pattern: TOCTOU close via re-invoking the same pure decision function immediately before a side effect, rather than caching the entry-point result across an async gap"

requirements-completed: [OWNER-06, OWNER-02, RATE-01]

# Metrics
duration: 21min
completed: 2026-07-13
---

# Phase 20 Plan 05: TOCTOU Pre-Send Re-Check + guild_id Threading Summary

**Closed the D-14/SC-2 mid-flight-silence window on the two reply-after-Gemini ambient surfaces (proactive callback, vision roast) and completed RATE-01 guild_id tagging on the last two events.py Gemini call sites.**

## Performance

- **Duration:** 21 min
- **Started:** 2026-07-13T23:32:10+08:00
- **Completed:** 2026-07-13T23:53:33+08:00
- **Tasks:** 3
- **Files modified:** 3 (cogs/events.py, tests/test_proactive_events.py, tests/test_vision_events.py)

## Accomplishments
- `_generate_ambient_roast` and `_generate_vision_roast` now pass `guild_id=str(member.guild.id)` on their `gemini_service.chat(...)` calls — RATE-01 usage tagging is now complete across every events.py Gemini site
- `_maybe_fire_proactive_callback` and `_maybe_fire_vision_roast` both re-check the silence-aware `is_ambient_channel` predicate immediately before `message.reply`, closing the TOCTOU window where a `/guilds silence` (or toggle-off/reconfigure) issued during the seconds-long recall/generate awaits would otherwise let a stale response slip through
- The proactive re-check releases the reserved daily-cap slot on bail (no leak); the vision re-check skips the cooldown mark on bail
- New regression coverage locks the silenced-mid-flight behavior for both surfaces plus the always-silenced entry-gate case

## Task Commits

Each task was committed atomically:

1. **Task 1: thread guild_id through the two events.py Gemini call sites (RATE-01)** - `a025ad4` (feat)
2. **Task 2: TOCTOU pre-send re-check in proactive-callback + vision-roast paths (D-14 / SC-2)** - `00b96da` (feat)
3. **Task 3: silenced-mid-flight regression + call-site inventory fix in test_proactive_events.py** - `91cb4cc` (test)

## Files Created/Modified
- `cogs/events.py` - `guild_id` threaded through `_generate_ambient_roast`/`_generate_vision_roast` chat calls; pre-send `is_ambient_channel` re-check added to `_maybe_fire_proactive_callback` and `_maybe_fire_vision_roast`
- `tests/test_proactive_events.py` - documented the default-False `silenced` contract on `_make_bot`; added 3 new tests (proactive silenced-mid-flight, always-silenced entry gate, vision silenced-mid-flight)
- `tests/test_vision_events.py` - `_make_bot` now mocks a configured, non-silenced `guild_config` row (see Deviations)

## Decisions Made
- The pre-send re-check dispatches on `is_ambient_channel` (never re-derives `silenced`/`configured` inline), per the Phase 10 D-02 convention and the plan's explicit instruction — this is a second read of the same cache, not a new mechanism.
- Placed the re-check immediately before each `message.reply` call (after `_generate_ambient_roast`/`_generate_vision_roast` return, before the `try`/`except discord.HTTPException` block) so it covers the full recall+generate async window.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed `tests/test_vision_events.py::_make_bot` missing `guild_config` mock**
- **Found during:** Task 2 (verification run of `pytest tests/test_vision_events.py`)
- **Issue:** `_make_bot()` in `tests/test_vision_events.py` returned a bare `MagicMock()` with no `guild_config` attribute set. Once the pre-send re-check called `self.bot.guild_config.get(message.guild.id)`, the auto-vivified `MagicMock` return value's `.get("configured", False)` and `.get("silenced", False)` calls both returned the *same* auto-generated `MagicMock` object (truthy), which made `decide_ambient_channel` hit the `silenced` branch and return `None` — causing `is_ambient_channel` to be `False` on every call, unconditionally bailing the pre-send re-check for every test in that file that reaches the reply stage. Two pre-existing tests (`test_transport_fallback_replies`, `test_reply_anchor_and_cooldown_mark`) failed as a result.
- **Fix:** Updated `_make_bot()` to mock `bot.guild_config.get` returning a proper configured, non-silenced row (`ambient_channel_id="500"`, both toggles `True`), mirroring the shape already used in `tests/test_proactive_events.py::_make_bot`.
- **Files modified:** `tests/test_vision_events.py`
- **Verification:** `pytest tests/test_proactive_events.py tests/test_vision_events.py -q` → 30 passed; full suite `pytest tests/ -q` → 970 passed, 121 skipped, 0 failed
- **Committed in:** `00b96da` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary to keep the full suite green per the plan's own verification requirement ("Full suite `pytest tests/ -q` green"). No scope creep — the fix is scoped entirely to a test fixture that needed to catch up with the new pre-send re-check this plan introduced.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- SC-2 (no stale in-flight ambient response after a silence) is now true for every ambient surface: the voice-join/leave/move and music-path roasts already resolved `resolve_ambient_channel` at send time (20-02 covers them for free), and the two reply-after-Gemini surfaces (proactive callback, vision roast) now re-check immediately before send.
- RATE-01 guild_id tagging is complete across all `cogs/events.py` Gemini call sites; remaining call sites (if any) are owned by other files/plans per the phase-wide call-site inventory in `20-PATTERNS.md`.
- Full suite green (970 passed, 121 skipped, 0 failed) — no regressions introduced.

---
*Phase: 20-owner-control-plane-rate-observability*
*Completed: 2026-07-13*

## Self-Check: PASSED

- FOUND: cogs/events.py
- FOUND: tests/test_proactive_events.py
- FOUND: tests/test_vision_events.py
- FOUND: .planning/phases/20-owner-control-plane-rate-observability/20-05-SUMMARY.md
- FOUND commit: a025ad4
- FOUND commit: 00b96da
- FOUND commit: 91cb4cc
