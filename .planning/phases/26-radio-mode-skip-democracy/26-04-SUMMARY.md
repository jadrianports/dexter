---
phase: 26-radio-mode-skip-democracy
plan: 04
subsystem: music
tags: [skip-vote, dj-02, discord-cog, choke-point, wiring]

# Dependency graph
requires:
  - phase: 26-02
    provides: "logic/skip_vote.py (SkipVerdict/decide_skip/required_votes), MusicQueue.skip_votes_for_current()/record_skip_votes(), personality.responses.SKIP_VOTE_TALLY"
provides:
  - "MusicCog._try_skip — the single vote-gated skip choke point (D-15)"
  - "/skip and NowPlayingView.skip_button both routed through _try_skip; the /skip slash command's Pitfall-1 duplicated inline body is gone"
  - "/seek's past-end auto-skip also routed through _try_skip, closing a vote-bypass hole discovered during this plan's execution"
  - "tests/test_music_wiring.py — structural regression guard locking the unification"
affects: [26-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Verdict-dispatch glue (Phase 10 D-02): _try_skip calls decide_skip/required_votes and if/elif dispatches on the returned SkipVerdict, mirroring _on_track_end's decide_on_track_end dispatch — never re-derives the majority arithmetic"
    - "Gate-wraps-mechanics shape: _try_skip is a new wrapper: _do_skip stays completely unmodified and is called ONLY on SKIP_NOW, preserving D-20 and Critical Rule 3 (FFmpeg cleanup) for free"
    - "Small-tuple return, caller renders: _try_skip returns (verdict, next_track, votes, required) rather than owning the Discord response, since /skip and the button differ in ack style (public followup vs ephemeral)"

key-files:
  created:
    - tests/test_music_wiring.py
  modified:
    - cogs/music.py
    - tests/test_hosting_drift_guard.py

key-decisions:
  - "Trusted the code over 26-CONTEXT.md's canonical-refs claim that /skip already called _do_skip — verified directly that MusicCog.skip's slash body (pre-task) had a fully duplicated inline skip mechanics block and never called _do_skip at all (26-RESEARCH Pitfall 1, confirmed correct)"
  - "Also routed /seek's past-end auto-skip through _try_skip, beyond the plan's read_first/action prose which only named /skip and the Skip button. The plan's own acceptance criteria and Task 3's structural test both require _do_skip to be called exactly once in the whole module, from inside _try_skip — /seek's pre-existing direct _do_skip call (unrelated to Tasks 1/2's stated scope) would have both failed that literal criterion AND left a genuine vote-bypass hole: any single user could force an unvoted skip via /seek past the track's duration. Closed as Rule 2 (missing critical functionality / security-relevant vote-bypass), not treated as out-of-scope creep, since the plan's own success criteria demanded it."
  - "Fixed tests/test_hosting_drift_guard.py's RENDER_ALLOWLIST — Task 1's import-line insertion shifted the two pre-existing NowPlayingView docstring 'render'/'rendering' hits by +2 lines, and Task 2's deletion of the /skip command's duplicated WR-02 're-render' comment removed the third allowlisted hit outright. Updated the two surviving (file, line) pairs and dropped the stale third entry."

requirements-completed: [DJ-02]

# Metrics
duration: 35min
completed: 2026-07-17
---

# Phase 26 Plan 04: Unified Skip-Vote Choke Point Summary

**A single `MusicCog._try_skip` gate now sits in front of every skip-triggering surface in `cogs/music.py` — `/skip`, the persistent Skip button, and `/seek`'s past-end auto-advance — dispatching on `logic.skip_vote.SkipVerdict` and reaching the unmodified `_do_skip` mechanics only on a majority vote or a requester bypass.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 3 completed
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- New `MusicCog._try_skip(guild, queue, voice_client, *, voter_id)` choke point: reads the live voice-channel listener set fresh on every call (never memoized, D-17/Pitfall 4), computes the requester bypass via a plain `voter_id == current.requested_by` equality (no bot-id special-casing, no admin/owner override, D-13a/D-13b/T-26-05), dispatches on `decide_skip`'s returned `SkipVerdict` (never re-deriving the majority arithmetic, Phase 10 D-02), calls the unchanged `_do_skip` only on `SKIP_NOW`, and posts the `SKIP_VOTE_TALLY` line publicly (code-interpolated numbers, D-16/D-18) on `VOTE_RECORDED`/`ALREADY_VOTED`
- Closed the real Pitfall-1 hole: `/skip`'s slash command had a fully duplicated inline skip body that never called `_do_skip` — deleted it and routed through `_try_skip`; `NowPlayingView.skip_button` swapped its direct `_do_skip` call for `_try_skip` too
- Discovered and closed a second vote-bypass surface not named in the plan's task prose: `/seek`'s past-end auto-skip called `_do_skip` directly, which would have let any single user force an unvoted skip via `/seek 99:99`. Routed through `_try_skip` as well — the plan's own acceptance criteria ("`_do_skip(` called exactly once, from inside `_try_skip`") required this, and closing it is a genuine DJ-02 security fix, not scope creep
- `tests/test_music_wiring.py` (174 lines, 15 tests, 5 classes): source-assertion regression guard cloned from `tests/test_autoqueue_wiring.py`'s shape — locks the choke-point unification, the verdict-dispatch-not-reimplemented rule, the fresh-listener-read invariant, the no-bypass-backdoor invariant, and the no-new-memory-kind invariant, all with comment-stripped `count()`/absence assertions

## Task Commits

Each task was committed atomically:

1. **Task 1: The _try_skip shared vote gate** - `584e60b` (feat)
2. **Task 2: Route /skip, skip button, and /seek past-end through _try_skip** - `cc6a219` (feat)
3. **Task 3: tests/test_music_wiring.py — the D-15 structural regression guard** - `92a2948` (test)

## Files Created/Modified

- `cogs/music.py` - New `_try_skip` choke point above `_do_skip` under the existing SHARED CONTROL HELPERS banner; `/skip`'s duplicated inline body deleted; `NowPlayingView.skip_button` and `/seek`'s past-end branch rewired to `_try_skip`; new imports `logic.skip_vote.{SkipVerdict, decide_skip, required_votes}` and `personality.responses.SKIP_VOTE_TALLY`
- `tests/test_music_wiring.py` - New structural regression guard (`TestSkipChokePointUnification`, `TestVerdictDispatchedNotReimplemented`, `TestFreshListenerRead`, `TestNoBypassBackdoor`, `TestNoNewMemoryKindInSkipPath`)
- `tests/test_hosting_drift_guard.py` - `RENDER_ALLOWLIST` line numbers updated for `cogs/music.py` after Task 1/2 edits shifted them

## Decisions Made

- Verified the real call graph directly rather than trusting 26-CONTEXT.md's canonical-refs summary, per the prior-wave context's explicit warning — confirmed `/skip`'s slash body never called `_do_skip` pre-task, only the button did
- Extended scope to `/seek`'s past-end skip (see key-decisions above) — required by the plan's own acceptance criteria and a real security fix, not an unauthorized architectural change
- Kept `_do_skip` itself byte-identical (untouched) throughout — D-20 and Critical Rule 3 (FFmpeg cleanup) are preserved by construction since only the decision to *reach* the mechanics changed, never the mechanics themselves

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] `/seek`'s past-end auto-skip bypassed the vote gate**
- **Found during:** Task 2 (routing /skip and the Skip button through `_try_skip`)
- **Issue:** `/seek`'s past-end-of-track branch called `MusicCog._do_skip` directly, exactly like the button did pre-task. Left unguarded, any single user could force an instant, unvoted skip via `/seek 99:99` regardless of how many listeners were present — a complete bypass of DJ-02's whole purpose. Not named in the plan's Task 2 `<action>` prose, but required by the plan's own acceptance criteria ("`_do_skip(` is called exactly once... inside `_try_skip`") and Task 3's structural test.
- **Fix:** Routed `/seek`'s past-end branch through `_try_skip` with the same verdict-dispatch pattern as `/skip`, using seek-flavored copy ("seek past the end — skipping to **X**." / "...that counts as a skip vote." / "...you already voted to skip this one.").
- **Files modified:** `cogs/music.py`
- **Verification:** `pytest -q` full suite green (1144 passed); `grep -n "_do_skip(" cogs/music.py` shows exactly one call site, inside `_try_skip`
- **Committed in:** `cc6a219` (Task 2 commit)

**2. [Rule 1 - Bug] Stale line numbers + a stale entry in `RENDER_ALLOWLIST`**
- **Found during:** Full-suite verification after Task 2
- **Issue:** Task 1's new `logic.skip_vote`/`SKIP_VOTE_TALLY` imports shifted two pre-existing `NowPlayingView` docstring "render"/"rendering" hits down by 2 lines (304→306, 315→317); Task 2's deletion of the duplicated inline `/skip` body removed the WR-02 "re-render" comment that the allowlist's third entry (line 1688) pointed at, so that entry became stale/unmatched. `tests/test_hosting_drift_guard.py::test_render_hits_are_all_allowlisted` failed with an un-allowlisted-reference assertion.
- **Fix:** Updated the two surviving `("cogs/music.py", N)` line numbers and removed the now-nonexistent third entry.
- **Files modified:** `tests/test_hosting_drift_guard.py`
- **Verification:** `pytest tests/test_hosting_drift_guard.py -q` green (7 passed); full suite subsequently green
- **Committed in:** `cc6a219` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 missing-critical-functionality/security, 1 bug)
**Impact on plan:** Both fixes were necessary for correctness — the /seek fix closes a real DJ-02 vote-bypass hole the plan's own acceptance criteria demanded be closed; the allowlist fix is a mechanical consequence of the line-number shift, purely maintenance, no logic change. No scope creep beyond what the plan's stated success criteria required.

## Issues Encountered

None beyond the deviations documented above.

## Next Phase Readiness

- `_try_skip` is now the sole vote-gated entry point to `_do_skip` across the entire module (`grep -c "_do_skip(" cogs/music.py` shows one call, one def) — 26-05 can build on top of this without reopening the choke point
- `tests/test_music_wiring.py` locks the unification structurally; a future edit that re-duplicates a skip body, lets a surface bypass the gate, memoizes the listener denominator, re-derives the arithmetic, adds an admin bypass, or bolts a memory write onto the skip path will fail the build
- No blockers; full suite green (1144 passed / 129 skipped / 0 failed) at HEAD

---
*Phase: 26-radio-mode-skip-democracy*
*Completed: 2026-07-17*

## Self-Check: PASSED

- FOUND: tests/test_music_wiring.py
- FOUND: cogs/music.py
- FOUND: .planning/phases/26-radio-mode-skip-democracy/26-04-SUMMARY.md
- FOUND: 584e60b (Task 1 commit)
- FOUND: cc6a219 (Task 2 commit)
- FOUND: 92a2948 (Task 3 commit)
