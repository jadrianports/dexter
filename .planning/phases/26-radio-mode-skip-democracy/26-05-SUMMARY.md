---
phase: 26-radio-mode-skip-democracy
plan: 05
subsystem: music
tags: [discord.py, app_commands, radio, auto-queue, loop-mode]

# Dependency graph
requires:
  - phase: 26-01
    provides: "logic/radio.py should_refill_radio gate; MusicQueue.arm_radio/disarm_radio/set_loop_mode/radio_armed"
  - phase: 26-02
    provides: "personality/responses.py RADIO_START/RADIO_STOP/RADIO_LOOP_CONFLICT/RADIO_NOT_ARMED pools"
  - phase: 26-03
    provides: "AICog.try_auto_queue(guild, radio=True) refill entry point"
  - phase: 26-04
    provides: "tests/test_music_wiring.py structural-regression-guard scaffold"
provides:
  - "/radio start [seed] and /radio stop slash command group on MusicCog"
  - "D-10 lookahead refill trigger in _on_track_end, consulted alongside decide_on_track_end"
  - "D-11 loop/radio mutual exclusion routed through MusicQueue.set_loop_mode at both loop surfaces"
  - "tests/test_music_wiring.py radio + loop wiring guard classes (SC-2 structural proof)"
affects: [27-crossfade-playback, 28-portfolio-finish]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "app_commands.Group class attribute + @group.command(...) subcommand shape (matches cogs/library.py's playlist/jam groups)"
    - "Additional independent gate consulted alongside a pure-logic dispatch, never folded into the enum (should_refill_radio next to decide_on_track_end/TrackEndAction)"
    - "One model choke point for mutually-exclusive state (MusicQueue.set_loop_mode) reached from both the slash command and the button handler"

key-files:
  created: []
  modified:
    - cogs/music.py
    - tests/test_music_wiring.py
    - tests/test_hosting_drift_guard.py

key-decisions:
  - "/radio requires the bot already be in voice — it DJs a room, it does not join one; re-implementing /play's join logic was explicitly out of scope"
  - "No seed parsing whatsoever — Gemini interprets free text, validate_youtube_match still gates every queued track"
  - "/radio start kicks its first refill through the same should_refill_radio gate as the lookahead, giving D-12 non-destructive takeover with no special 'starting' case"
  - "/radio start and /radio stop both call reset_auto_queue() so radio-era play/skip counts never leak into the next auto-queue session's ignored-signal calculation"

patterns-established:
  - "Pure-logic gate + Discord glue: should_refill_radio is consulted from two call sites (radio_start and _on_track_end) with the same three keyword args, no logic duplicated"
  - "Structural regression guards via inspect.getsource + comment-stripped source scans (tests/test_music_wiring.py) prove wiring invariants without mocking Discord objects"

requirements-completed: [DJ-01]

# Metrics
duration: 38min
completed: 2026-07-17
---

# Phase 26 Plan 05: Radio's User-Facing Surface Summary

**`/radio start|stop` command group, D-10 lookahead refill trigger, and D-11 loop/radio mutual exclusion — radio is now reachable and, critically, stoppable.**

## Performance

- **Duration:** 38 min (across two sessions — a prior executor completed Tasks 1-2 and started Task 3 before an API connection error; this session verified Tasks 1-2, completed and committed Task 3, and closed out the plan)
- **Started:** 2026-07-17T00:28:42+08:00 (first commit)
- **Completed:** 2026-07-17T00:56:06+08:00 (last task commit; plan closed same session)
- **Tasks:** 3/3 completed
- **Files modified:** 3 (`cogs/music.py`, `tests/test_music_wiring.py`, `tests/test_hosting_drift_guard.py`)

## Accomplishments
- `/radio start [seed]` and `/radio stop` shipped as an `app_commands.Group` on `MusicCog`, following `cogs/library.py`'s `playlist`/`jam` shape (D-06b: a group, not a single command, so a seed of "off" can never collide with the disarm action)
- D-10 lookahead refill: `_on_track_end` consults `should_refill_radio` as an independent gate alongside the untouched `decide_on_track_end` dispatch — refills fire while tracks remain, never on empty, keeping Phase 6's zero-gap prefetch intact
- D-11 loop/radio mutual exclusion: both `/loop` and the now-playing loop button's `_do_loop_cycle` route through `MusicQueue.set_loop_mode`, so neither surface can silently leave radio armed while looping
- SC-2 proven structurally: `tests/test_music_wiring.py::TestRadioDisarmsAtEveryTeardown` shows behaviourally that `arm_radio()` + `clear()` leaves `radio_armed is False`, plus asserts `/stop`, `_do_stop`, and `bot.py::idle_check` all still call `queue.clear()` so a future edit cannot silently drop the disarm
- 33 tests in `tests/test_music_wiring.py` pass; full suite 1162 passed / 129 skipped / 0 failed; `ruff check .` and `ruff format --check` clean on all files this plan touched

## Task Commits

Each task was committed atomically:

1. **Task 1: /radio start|stop command group** - `b06471b` (feat) — committed by the prior (crashed) executor; verified against plan spec this session, no rework needed
2. **Task 2: D-10 lookahead refill trigger + D-11 loop mutual exclusion** - `3818cb3` (feat) — committed by the prior (crashed) executor; verified against plan spec this session, no rework needed
3. **Task 3: Radio wiring guards + SC-2 teardown proof** - `62b7dba` (test) — uncommitted at session start, verified complete against the plan's Task 3 spec, then committed as-is

**Plan metadata:** committed as part of this SUMMARY commit (docs: complete plan)

## Files Created/Modified
- `cogs/music.py` - `radio` group + `radio_start`/`radio_stop`; D-10 lookahead gate in `_on_track_end`; AUTOQUEUE branch forwards `radio=radio_armed`; `/loop` and `_do_loop_cycle` route through `set_loop_mode`
- `tests/test_music_wiring.py` - `TestRadioLookaheadWiring`, `TestRadioLifecycleWiring`, `TestRadioDisarmsAtEveryTeardown`, `TestLoopRadioMutualExclusionWiring` (33 tests total in file, all passing)
- `tests/test_hosting_drift_guard.py` - `RENDER_ALLOWLIST` line numbers for `cogs/music.py` bumped to match the new imports/radio group inserted above them (Rule 3 auto-fix, done by the prior executor as part of Task 2's commit)

## Decisions Made
No new decisions this session — all locked decisions (D-06a/b, D-07, D-10, D-11, D-12) were already implemented correctly by the prior executor's Task 1/2 commits. This session's role was verification (confirming the committed code actually satisfies every acceptance criterion in the plan) plus completing and committing the in-progress Task 3 test suite.

## Deviations from Plan

None beyond what the prior executor already applied and documented in its own commit messages:

**1. [Rule 3 - Blocking] Fixed `tests/test_hosting_drift_guard.py` RENDER_ALLOWLIST line numbers**
- **Found during:** Task 2 (by the prior executor, before this session started)
- **Issue:** New imports and the `radio` group declaration in `cogs/music.py` shifted the line numbers of two allowlisted `Render` mentions the drift guard checks by exact `(file, line)` tuples
- **Fix:** Updated the two `("cogs/music.py", N)` tuples in `RENDER_ALLOWLIST` to their new line numbers (306→311, 317→322)
- **Files modified:** `tests/test_hosting_drift_guard.py`
- **Verification:** Full suite green, including `test_hosting_drift_guard.py`
- **Committed in:** `3818cb3` (part of Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking, applied by the prior executor)
**Impact on plan:** Necessary line-number correction with zero scope creep — not a `files_modified` violation since the plan's `files_modified` list only tracks the primary implementation files, and this was a required drift-guard maintenance fix caused directly by Task 2's own edits.

## Issues Encountered
- The previous executor session died mid-Task-3 from an API connection error, after committing Tasks 1-2 and writing (but not committing) ~170 lines of Task 3 test code. This session verified all prior work against the plan's acceptance criteria by reading the committed source directly (`inspect`-equivalent manual grep/read), confirmed the uncommitted Task 3 tests fully covered the plan's Task 3 spec with no gaps, and committed them without modification.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- DJ-01 (radio mode) and DJ-02 (skip democracy) are both now fully code-complete across Phases 26-01 through 26-05
- `logic/playback.py` and `bot.py` remain byte-identical since before Phase 26 started (verified via `git diff --stat` against the pre-Phase-26 commit) — the phase's stated non-goal held
- Phase 26 is code-complete; the `26-HUMAN-UAT.md` parked item (clean-boot `/radio start|stop` command registration in a live Discord client) remains for whenever the residential-host live-Discord tail resumes, consistent with every prior phase's precedent
- Phase 27 (Crossfade Playback, spike-gated) can proceed — it depends on the playback engine, which this plan left untouched

---
*Phase: 26-radio-mode-skip-democracy*
*Completed: 2026-07-17*
