---
phase: 27-crossfade-playback-spike-gated
fixed_at: 2026-07-17T00:00:00Z
review_path: .planning/phases/27-crossfade-playback-spike-gated/27-REVIEW.md
iteration: 1
findings_in_scope: 2
fixed: 2
skipped: 1
status: partial
---

# Phase 27: Code Review Fix Report

**Fixed at:** 2026-07-17
**Source review:** `.planning/phases/27-crossfade-playback-spike-gated/27-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope (per explicit instruction, WR-01 + WR-02 only): 2
- Fixed: 2
- Skipped: 1 (WR-03, explicitly out of scope by user decision — dependency pinning deferred)

## Fixed Issues

### WR-01: `cache_cleanup`'s crossfade "protect the outgoing track" check reads state that is already cleared before the actual eviction-risk window begins

**Files modified:** `models/queue.py`, `cogs/music.py`, `bot.py`
**Commit:** `38539c0`
**Applied fix:** Added `MusicQueue._xf_from_video_id: str | None` — a direct, honestly-scoped
signal for "this video_id's cache file may still be actively re-decoded by a `CrossfadeSource`
tail mix," replacing the dead `_xf_truncator`/`_xf_pending` + `current_index - 1` inference in
`bot.py::cache_cleanup`.

- `models/queue.py`: new field declared in `__init__` beside `_xf_pending`/`_xf_truncator`, nulled
  in `clear()` alongside them (same D-12 playback-state discipline, unpersisted by construction).
- `cogs/music.py::_play_track`: set right after the existing `crossfade_from` (`xf_pending`)
  consumption block — **before** the D-01 generation-increment engine block, never touching it.
  Self-clearing across normal chained `_play_track` calls (recomputed unconditionally every call);
  also explicitly nulled in the two `source.cleanup()` paths (not-connected early return, exception
  handler) and in `_on_track_end`'s unconditional-clear block, for the "no further track plays"
  case.
- `bot.py::cache_cleanup`: replaced the buggy `(queue._xf_truncator is not None or
  queue._xf_pending is not None) and queue.current_index > 0 and queue.current_index - 1 <
  len(queue.tracks)` block with a direct `if queue._xf_from_video_id: protected_video_ids.add(...)`.
  This also fixes the secondary loop-QUEUE-wraparound gap the review flagged (the old
  `current_index > 0` guard silently skipped protection when `current_index` wrapped to `0`).

No changes to the D-01 engine block, `_try_skip`/`_do_skip` (still zero crossfade references), or
the hard-cut log-only invariant.

### WR-02: `queue._xf_truncator` is not reliably nulled on every `_play_track` exit path, only inside `_on_track_end`

**Files modified:** `cogs/music.py`
**Commit:** `0a84fc3`
**Applied fix:** Added `queue._xf_truncator = None` to the three `_play_track` code paths the
review identified as missing it:
- the hard-cut (`else`) branch of the `FadeVerdict` check (mirrors the existing `FADE` branch's
  `queue._xf_truncator = source` assignment),
- the `not voice_client.is_connected()` early-return path, right where `source.cleanup()` already
  runs,
- the `except Exception` handler around `voice_client.play()`, same placement.

These are the same three spots WR-01 already touches for the adjacent `_xf_from_video_id` field, so
the two fixes share code locations but not code lines — verified cleanly separable via `git diff`
between the two commits.

## Skipped Issues

### WR-03: `discord.py` is not pinned, despite `utils/discord_patch.py` documenting the patch against "the pinned 2.7.1"

**File:** `requirements.txt:1`, `utils/discord_patch.py:4-5`
**Reason:** Out of scope by explicit user instruction — dependency pinning deferred. Not attempted.

## Verification

- `pytest tests/test_music_wiring.py tests/test_queue.py tests/test_audio.py -q` → 122 passed (WR-01) /
  123 passed (WR-01+WR-02, `test_queue_persistence.py` added) — 0 failed after each commit.
- Full suite `pytest -q` → **1232 passed, 130 skipped, 0 failed** after both fixes. This is 1 test
  lower on the "passed" count than the `1233 passed` baseline quoted in the task brief; the delta
  is `tests/test_site_drift_guard.py` skipping with "site/dist/ not built (local run, no `npm run
  build`)" — confirmed via a `SKIPPED` diff against a clean `git worktree` run of unmodified `main`,
  which also shows 1233/129. The extra skip is a local-build-artifact environment difference in the
  fresh worktree (`site/dist/` is a gitignored build output, not checked out), unrelated to these
  code changes. Same total test count (1362) both ways, 0 failures either way.
- `ruff check` / `ruff format --check` on all touched files (`bot.py`, `cogs/music.py`,
  `models/queue.py`) — clean after each commit.
- Hard constraints re-verified by reading the diffs and re-running the guard tests: `_play_track`'s
  D-01 engine block untouched (all edits sit before it or inside pre-existing cleanup branches that
  don't touch the four named checkpoints); `_try_skip`/`_do_skip` gained zero crossfade/`_xf_`
  references; the hard-cut branch stays log-only (new `queue._xf_truncator = None` line carries no
  channel/followup/response call); `_xf_pending` is still read-and-cleared in the same block it
  always was.

---

_Fixed: 2026-07-17_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
