---
phase: 26-radio-mode-skip-democracy
fixed_at: 2026-07-17T00:00:00Z
review_path: .planning/phases/26-radio-mode-skip-democracy/26-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 26: Code Review Fix Report

**Fixed at:** 2026-07-17T00:00:00Z
**Source review:** .planning/phases/26-radio-mode-skip-democracy/26-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (CR-01, WR-01, WR-02, WR-03, WR-04)
- Fixed: 5
- Skipped: 0
- Out of scope (not attempted, per instructions): IN-01

## Fixed Issues

### CR-01: `/skip` and `/seek` past-end never verify the voter is in the bot's voice channel

**Files modified:** `cogs/music.py`, `tests/test_music_wiring.py`
**Commit:** `2264173`
**Applied fix:** Added the same voice-membership guard the button (`_guard_in_voice`) and
`/filter` already use to both `/skip` (before `interaction.response.defer()`) and `/seek`'s
past-end auto-skip branch (using `interaction.followup.send` there since the response was
already deferred at that point). Both guards run strictly before `_try_skip` is ever called, so
no vote can be cast by a non-listener. New `TestVoiceMembershipGateOnSkipEntryPoints` in
`tests/test_music_wiring.py` (4 tests) locks that both entry points check
`interaction.user.voice`/`voice_client.channel` and that the check precedes the `_try_skip(`
call site — matching this file's existing structural-source-assertion convention (Discord glue
is untested-by-design per `.planning/codebase/TESTING.md`).

`logic/skip_vote.py::decide_skip` was left untouched, per the fix_scope's explicit instruction —
D-17 (a departed voter's vote stays counted) is correct and remains correct; the fix is entirely
at the glue layer, closing the gap the review identified (voice-membership gating is the
caller's responsibility).

### WR-01: Radio-era auto-queue counters only reset by `/radio stop`, not by a mid-radio `/loop` disarm

**Files modified:** `cogs/music.py`, `tests/test_music_wiring.py`
**Commit:** `a352263`
**Applied fix:** Both D-11 loop-disarm sites (`MusicCog.loop` and `MusicCog._do_loop_cycle`, the
button's helper) now call `state.reset_auto_queue()` whenever `MusicQueue.set_loop_mode` reports
`radio_disarmed=True`, mirroring the existing `radio_start`/`radio_stop` lifecycle-boundary
reset exactly (same `hasattr(self.bot, "server_states")` guard + inline
`from models.server_state import get_server_state` import pattern). `_do_loop_cycle` is a plain
sync method with only `queue: MusicQueue` as a parameter (no `guild`/`interaction`), so it reads
`queue.guild_id` — already stored on the model — rather than needing a new parameter threaded
through the button call site. New tests
`test_loop_command_resets_auto_queue_on_radio_disarm` / `test_loop_cycle_resets_auto_queue_on_radio_disarm`
lock both sites structurally.

### WR-02: Narrow race window can double-skip an auto-queued/radio track under concurrent votes

**Files modified:** `cogs/music.py`, `tests/test_music_wiring.py`
**Commit:** `caab5de`
**Applied fix:** Moved `next_track = queue.skip()` in `MusicCog._do_skip` to run before the first
`await` (`mark_song_skipped`), rather than after it. Since `_try_skip`'s own vote-decision
section (`decide_skip`/`record_skip_votes`) has no `await` in it, the whole "decide `SKIP_NOW` ->
advance the queue" sequence is now one atomic synchronous block with no yield point in between —
a second concurrent `_try_skip` call can only ever observe the queue already advanced (and,
because `skip_votes_for_current()` auto-resets on the `(current_index, video_id)` key change, a
freshly-reset vote set), closing the double-skip window the review described. This is the first
of the review's two suggested fixes (reorder `queue.skip()`); the alternative (an in-flight flag
on `MusicQueue`) was not needed once the reorder was verified to fully close the window.
`current` is captured as a local variable before `queue.skip()` runs, so `current.url` /
`current.was_auto_queued` used afterward are unaffected by the index having already advanced.
New `TestDoSkipAdvancesBeforeFirstAwait` (2 tests) locks the ordering and that no new `await` was
introduced ahead of `queue.skip()` itself, comment-stripped so an explanatory comment mentioning
"await" in prose can't false-positive the assertion (caught and fixed during this pass — my
first draft of the second test had exactly that false positive).

**Logic-risk note:** this is a concurrency-ordering fix, not a pure syntax change — verified by
re-reading the full call graph (`_try_skip`'s synchronous section, `decide_skip`'s synchronous
body, `_do_skip`'s new ordering) to confirm no `await` remains between the vote decision and the
queue advance. Full suite green after the change; flagging here per the verification protocol's
logic-bug caveat so this can get a second human look if desired, though the structural tests and
full-suite pass both support the fix being correct.

### WR-03: `/skip` blocks skipping (and voting) while paused; the button does not

**Files modified:** `cogs/music.py`, `tests/test_music_wiring.py`
**Commit:** `7b628d5`
**Applied fix:** Changed `/skip`'s guard from `not voice_client or not queue.is_playing` to
`not voice_client or (not queue.is_playing and not queue.is_paused)`, and `/seek`'s initial guard
from `not track or not queue.is_playing` to `not track or (not queue.is_playing and not queue.is_paused)`
— both now match `NowPlayingView.skip_button`'s existing `not is_playing and not is_paused` shape
exactly, per the review's suggested fix. New `TestPausedTrackSkippableAtEveryEntryPoint` (3
tests) locks both commands' guards and anchors the assertion to the button's own guard text, so
a future drift in the reference shape is caught rather than silently invalidating the other two
entry points' fix.

### WR-04: `/radio start`'s free-text `seed` has no length cap

**Files modified:** `cogs/music.py`, `config.py`, `tests/test_music_wiring.py`
**Commit:** `9a2357d`
**Applied fix:** Added `config.RADIO_SEED_MAX_LENGTH = 100` (Phase 26 config section, alongside
the other radio knobs, mirroring the existing `PLAYLIST_NAME_MAX_LENGTH` precedent per the
review's suggestion) and truncate `seed` to that cap once, at arm time in `radio_start`, before
it is stored via `arm_radio`. Because `cogs/ai.py::try_auto_queue` reads `queue.radio_seed`
fresh on every refill and `personality/prompts.py::build_recommendation_prompt` embeds it
verbatim into the `START FROM THIS AND DRIFT NATURALLY` block, capping once at the single write
site is sufficient — no separate truncation needed at either downstream read site. New
`test_radio_start_truncates_seed_before_arming` locks that the truncation runs before
`arm_radio(` is called; `test_radio_seed_max_length_is_a_sane_positive_cap` sanity-bounds the
knob itself (`0 < RADIO_SEED_MAX_LENGTH <= 500`).

## Skipped Issues

None — all 5 in-scope findings (CR-01, WR-01, WR-02, WR-03, WR-04) were fixed. IN-01 was
out of scope for this pass per the fix instructions and was not attempted.

## Verification Summary

- Scoped suite (`tests/test_music_wiring.py tests/test_skip_vote_logic.py
  tests/test_autoqueue_wiring.py tests/test_radio_logic.py`) re-run after every individual fix,
  green throughout: 123 -> 127 (CR-01) -> 129 (WR-01) -> 131 (WR-02) -> 134 (WR-03) -> 136
  (WR-04) passed, 0 failed at every step.
- `tests/test_hosting_drift_guard.py` re-run after every fix — stayed green throughout (7
  passed each time). No `RENDER_ALLOWLIST` line-number drift occurred because every edit landed
  below the two allowlisted lines (`cogs/music.py:311`, `cogs/music.py:322`).
- Full suite (`python -m pytest -q`), run twice independently for reproducibility:
  **1174 passed / 130 skipped / 0 failed** both times (up from the pre-fix baseline of 1162
  passed / 129 skipped / 0 failed — net +13 tests added across the 5 fixes, with one
  environment-dependent skip appearing in both post-fix runs that is unrelated to any file this
  pass touched).
- `python -m ruff check .` — all checks passed, zero new violations.
- `python -m ruff format --check .` — exactly the 3 known pre-existing offenders
  (`services/memory.py`, `tests/test_database_phase25.py`, `tests/test_vision_events.py`), left
  untouched per instructions; no new offenders introduced by this pass.

## Not-a-Defect Findings

None. All 5 in-scope findings were confirmed real and fixed as described.

---

_Fixed: 2026-07-17T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
