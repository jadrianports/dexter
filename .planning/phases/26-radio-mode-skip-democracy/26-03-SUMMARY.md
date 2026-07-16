---
phase: 26-radio-mode-skip-democracy
plan: 03
subsystem: music
tags: [radio, dj-01, auto-queue, gemini-prompt, source-assertion-tests]

# Dependency graph
requires:
  - phase: 26-radio-mode-skip-democracy (plan 01)
    provides: "logic/radio.py (should_refill_radio, is_already_played, has_room_for_refill), MusicQueue radio_armed/radio_seed/radio_played state, build_recommendation_prompt(seed=, already_played=) kwargs, RADIO_ALREADY_PLAYED_HINT_CAP"
provides:
  - "AICog.try_auto_queue(guild, *, radio: bool = False) — the radio refill entry point (D-01: same brain, not a fork)"
  - "D-03 independent hard post-filter rejecting session repeats after YouTube resolution"
  - "D-05 ignored-signal announce + memory-write suppression while radio is armed"
  - "Byte-identical-when-disarmed regression guard locking the non-radio path"
affects: [26-05-radio-command]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Keyword-only radio: bool = False param, default renders the path byte-identical (Phase 14/16/21 additive-change convention)"
    - "Hoisted resource-resolution block (music_cog/queue) moved earlier so downstream state (radio_seed/radio_played) is available to the prompt build, with the only non-radio behavioural delta being an earlier bail on a missing MusicCog"
    - "Independent hard post-filter mirroring is_recently_skipped_artist's role as a second gate behind the primary validator (Phase 14 D-02 pattern), now applied to logic.radio.is_already_played"

key-files:
  created: []
  modified:
    - cogs/ai.py
    - tests/test_autoqueue_wiring.py
    - tests/test_hosting_drift_guard.py

key-decisions:
  - "Split the plan's single 'radio: bool = False + both imports' Task 1 action into two independently-lint-clean commits: Task 1 imports only has_room_for_refill (used in Task 1's own code); Task 2 adds the is_already_played import alongside its first use. Both imports land in cogs/ai.py exactly as the plan specifies by the end of the plan — only the commit boundary differs from the plan's literal phrasing, to keep every intermediate commit's own ruff check passing (no F401 unused-import gap)."
  - "Round-counter suppression logs a distinct radio-aware line (queue depth) instead of silently dropping the log.info the plan's action text showed inline with the counter guard — keeps radio refills visible in dexter.log without touching auto_queue_rounds/auto_queue_results."

requirements-completed: [DJ-01]

# Metrics
duration: 40min
completed: 2026-07-16
---

# Phase 26 Plan 03: Radio Auto-Queue Glue Summary

**`try_auto_queue(guild, radio=True)` turns the existing taste-aware auto-queue brain into radio's engine — round cap lifted, prompt anchored on the armed seed, session repeats hard-rejected after YouTube resolution, ignored-signal noise suppressed — while `radio=False` stays byte-identical to pre-Phase-26 behavior, locked by a new regression-guard test class.**

## Performance

- **Duration:** ~40 min (including two full-suite runs, ~415s / ~7min each, dominated by live-DB-skip test overhead)
- **Tasks:** 3 completed
- **Files modified:** 3

## Accomplishments

- `AICog.try_auto_queue` gains a keyword-only `radio: bool = False` param (D-01) — the round-cap check, the "no recent history" bail, the `music_cog`/`queue` resolution, and the prompt build are all reworked around it, with every radio behaviour byte-identical-when-disarmed
- D-03's independent hard post-filter (`is_already_played`) rejects a session repeat immediately after YouTube resolution, using the full uncapped `radio_played` set — the prompt's `already_played=` hint is advisory only, exactly mirroring how `is_recently_skipped_artist` backs up `validate_youtube_match` (Phase 14 D-02)
- D-05's ignored-signal announce + `auto_queue_ignored` memory write are suppressed while radio is armed (a skip during radio is channel-surfing, not a taste verdict); `was_auto_queued=True` is preserved so `/skips` and `song_history` stay accurate
- Radio never touches `auto_queue_rounds`/`auto_queue_results` (Pitfall 2) — post-radio auto-queue resumes with exactly the counters it had before radio started
- `has_room_for_refill` guards the refill before any Gemini spend (T-26-09), and the Gemini call stays `priority=2`/`guild_id=str(guild.id)` — never escalated (D-04, T-26-02)
- New `TestRadioBranchWiring` + `TestAutoQueuePathByteIdenticalWhenRadioDisarmed` classes in `tests/test_autoqueue_wiring.py` lock the wiring and prove the disarmed path is unchanged, including a structural scan asserting every radio-behaviour token is reachable only behind a `radio`-guarded condition

## Task Commits

Each task was committed atomically:

1. **Task 1: Radio branch — cap lift, seed anchor, already-played hint** - `8e679a9` (feat)
2. **Task 2: D-03 hard post-filter, played-set recording, D-05 ignored-signal suppression** - `010d342` (feat)
3. **Task 3: Byte-identical-when-disarmed regression guard + radio wiring assertions** - `7426821` (test)

## Files Created/Modified

- `cogs/ai.py` - `try_auto_queue(guild, *, radio: bool = False)`: round-cap guard, hoisted `music_cog`/`queue` resolution, `radio_seed`/`already_played` locals, `has_room_for_refill` pre-Gemini guard, widened "no recent history" bail, `seed=`/`already_played=` on `build_recommendation_prompt`, D-03 hard post-filter, `queue.radio_played` recording, D-05 announce/memory-write suppression, round-counter suppression
- `tests/test_autoqueue_wiring.py` - `TestRadioBranchWiring` (radio param, prompt kwargs, filter/guard presence, `priority=2` DoS control, D-03 gate ordering, hoisted single `get_queue` call) + `TestAutoQueuePathByteIdenticalWhenRadioDisarmed` (behavioural prompt-identity proof, structural radio-guard-reachability scan, single voice-member-comprehension re-lock)
- `tests/test_hosting_drift_guard.py` - `RENDER_ALLOWLIST` entry `("cogs/ai.py", 327)` added for the new hoist-block docstring's legitimate "renders byte-identically" wording

## Decisions Made

- Split Task 1's `is_already_played`/`has_room_for_refill` import pair across the Task 1 and Task 2 commits (import lands with first use) rather than both in Task 1, so each commit's own `ruff check` stays clean independently — the plan's stated end-state (both imports present) is unchanged by the time all three tasks land
- Round-counter suppression emits a distinct radio-aware log line naming the refill count and resulting queue depth, rather than silently skipping logging while armed — keeps radio activity observable in `dexter.log`/`/stats` context without touching the suppressed counters themselves

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Re-derived Phase 24 hosting drift-guard allowlist after the hoist-block docstring**
- **Found during:** Task 3 (full-suite verification)
- **Issue:** The new hoisted-block comment in `cogs/ai.py` ("radio's seed + played-set live on `MusicQueue` and the prompt needs them... `build_recommendation_prompt` call below renders byte-identically") used the legitimate English word "renders", tripping `tests/test_hosting_drift_guard.py::test_render_hits_are_all_allowlisted` (Phase 24's hardcoded `RENDER_ALLOWLIST` of `(file, line)` pairs) — a test entirely outside this plan's `files_modified` list. Identical class of false positive to the one 26-01 hit and fixed the same way.
- **Fix:** Re-derived via `git grep -niE '\brender[a-z]*\b' -- cogs/ai.py tests/test_autoqueue_wiring.py` (the guard's own stated derivation method) and added `("cogs/ai.py", 327)` to the allowlist — no wording changed, only the allowlist data.
- **Files modified:** `tests/test_hosting_drift_guard.py`
- **Verification:** `pytest tests/test_hosting_drift_guard.py -x` green; full suite subsequently green (1129 passed / 129 skipped / 0 failed)
- **Committed in:** `7426821` (Task 3 commit, bundled with the test-file additions since both touch test infrastructure discovered in the same verification pass)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary to keep the full suite green; no scope creep — the fix touched only allowlist data, not the guard's logic or the docstring wording it reacted to.

## Issues Encountered

Two full-suite runs (`python -m pytest -q`) each took ~415s (~7 min), dominated by a cluster of live-DB integration tests that attempt a real Postgres connection before skipping (129 skipped total, unrelated to this plan). No test failures beyond the drift-guard false positive above; both runs otherwise green from the start.

## Next Phase Readiness

- `try_auto_queue(guild, radio=True)` is now the complete radio refill entry point 26-05 needs — `/radio start`/`/radio stop` (26-05) can call it directly with zero further auto-queue-brain work
- DJ-01's engine half (26-01 pure logic/state + 26-03 glue) is code-complete; only the `/radio` slash command itself (26-05) remains to expose it to users
- No blockers; full suite green at HEAD (1129 passed / 129 skipped / 0 failed)

---
*Phase: 26-radio-mode-skip-democracy*
*Completed: 2026-07-16*
