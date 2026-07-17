---
phase: 27-crossfade-playback-spike-gated
reviewed: 2026-07-17T00:00:00Z
depth: standard
files_reviewed: 15
files_reviewed_list:
  - bot.py
  - cogs/music.py
  - config.py
  - logic/crossfade.py
  - models/queue.py
  - personality/responses.py
  - services/audio.py
  - utils/discord_patch.py
  - tests/test_audio.py
  - tests/test_crossfade_logic.py
  - tests/test_discord_patch.py
  - tests/test_hosting_drift_guard.py
  - tests/test_music_wiring.py
  - tests/test_queue.py
  - tests/test_queue_persistence.py
  - tests/test_responses.py
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 27: Code Review Report

**Reviewed:** 2026-07-17
**Depth:** standard
**Files Reviewed:** 15
**Status:** issues_found

## Summary

Reviewed the crossfade playback feature: `logic/crossfade.py` (pure eligibility
ladder), `services/audio.py` (`TruncatingSource`/`CrossfadeSource`), the
`utils/discord_patch.py` `send_silence` suppression patch + its drift guard,
and the `cogs/music.py` / `models/queue.py` glue that arms/consumes the
outgoing→incoming handoff.

The invariants called out in the review brief all hold under direct
inspection and are locked by tests:

- **D-01** (the `_play_track` generation-counter engine block): still exactly
  one `voice_client.play()` call per track; the fade is applied by wrapping
  the `AudioSource`, not by touching the generation/stop/play sequence
  (`tests/test_music_wiring.py::TestCrossfadeEngineWiring`).
- **Phase 26 D-15** (`_try_skip → _do_skip` choke point / vote cache): zero
  crossfade references anywhere in `_try_skip`/`_do_skip`, confirmed by both
  reading the code and `TestCrossfadeSkipChokePointUntouched`.
- **Critical Rule 3** (FFmpeg cleanup on skip/stop/error): `CrossfadeSource.cleanup()`
  owns both the tail and head decoders (tail in a `try`, head in a `finally`,
  idempotent), and `TruncatingSource.cleanup()` delegates to its inner source.
- **D-10b** (hard cut is silent/log-only): the non-FADE branch in `_play_track`
  only calls `log.info(...)`, never a channel send — confirmed structurally
  and by `test_crossfade_hard_cut_is_log_only`.
- **-ss / cut-position safety**: the `-ss` fed to the tail re-decode in
  `AudioService.get_source` comes from `TruncatingSource.position_seconds`
  (an in-process frame count), never from `Track.duration_seconds`. The one
  place `Track.duration_seconds` IS used (`cut_frame()`'s floor arithmetic)
  is documented and tested to floor at 0, and a mismatch there degrades to a
  natural early EOF on the `TruncatingSource`, not a negative `-ss`.

The three issues below are all in the surrounding glue/ops code, not the
core mixing math, and none of them are crash-level — but they are real
correctness/robustness gaps worth fixing.

## Warnings

### WR-01: `cache_cleanup`'s crossfade "protect the outgoing track" check reads state that is already cleared before the actual eviction-risk window begins

**File:** `bot.py:1060-1076` (also `cogs/music.py:678-679, 930-932`)

**Issue:** The hourly `cache_cleanup` task tries to keep the just-faded-from
track's cache file out of LFU eviction while `CrossfadeSource` is re-decoding
it:

```python
if (
    (queue._xf_truncator is not None or queue._xf_pending is not None)
    and queue.current_index > 0
    and queue.current_index - 1 < len(queue.tracks)
):
    protected_video_ids.add(queue.tracks[queue.current_index - 1].video_id)
```

Trace the actual lifetime of both flags:

1. `_on_track_end` sets `queue._xf_pending = (current, position_seconds)`
   at line 931, then unconditionally nulls `queue._xf_truncator` at line 932.
2. `_on_track_end` awaits `_persist_queue` (line 935) — this is the *only*
   window during which another coroutine could observe `_xf_pending` still
   set.
3. `_on_track_end` then calls `await self._play_track(guild, next_track)`
   synchronously (no further `await` in between).
4. The very first statements inside `_play_track` (lines 678-679) read
   `queue._xf_pending` into a local and immediately set
   `queue._xf_pending = None` — **before** `get_source()` is even called,
   i.e. before the `CrossfadeSource` (which actually holds the open tail
   decoder) is constructed, and long before `voice_client.play()` starts the
   multi-second read window that is the actual risk period.

So by the time `CrossfadeSource` is really being read (during
`voice_client.play()`, which returns almost immediately and lets the
background `AudioPlayer` thread drive the reads for the next several
seconds), `_xf_pending` is already `None`. `_xf_truncator` is `None` too
*unless* the just-started incoming track's own **next** transition also
happens to verdict `FADE` (in which case `_play_track` re-wraps the very
`CrossfadeSource` it just built in a new `TruncatingSource` and stores that
in `queue._xf_truncator` — an incidental, not intentional, protection).
Whenever two fades don't chain back-to-back (no further next track, next
track uncached, filter active, etc. — a common case, e.g. the last
crossfade of a session), the outgoing file sits completely unprotected for
the whole `CROSSFADE_SECONDS` mixing window.

A secondary gap in the same block: on a loop-QUEUE wraparound (the track
that just ended was the last track and `current_index` wraps to `0`), the
guard `queue.current_index > 0` is `False`, so the just-finished (now
last-and-first) track is never added to `protected_video_ids` even if the
flags happened to be set.

The failure mode is documented as benign (Windows: `unlink` on an in-use
file fails and is caught in `cleanup_cache`'s `except OSError`; Linux:
`unlink` on an open fd is POSIX-safe and playback continues) — so this is
not a crash risk. But the code's own comment claims this block *is* the fix
for exactly this race, and it does not actually cover the window it says it
covers. There is also no test anywhere (`bot.py` has none of the phase's
test files) exercising this specific accounting, so the gap is currently
unverified either way.

**Fix:** Either widen the protected window to actually span the mixing
window (e.g. have `CrossfadeSource` itself expose the outgoing `video_id`
and register/deregister it against a small in-flight set that `_play_track`
sets right before `voice_client.play()` and clears on the track's own
natural end / cleanup), or accept the documented benign-failure analysis
explicitly and drop the misleading "protects the outgoing file" framing
down to "best-effort, narrow window" in the comment. Either way, fix the
`current_index - 1 test` to not depend on `current_index > 0` (compute the
outgoing index directly, e.g. carry it alongside `_xf_pending` instead of
inferring it from `current_index - 1`), and add a test asserting the
protected set actually contains the outgoing video_id at the moment
`CrossfadeSource` is playing.

---

### WR-02: `queue._xf_truncator` is not reliably nulled on every `_play_track` exit path, only inside `_on_track_end`

**File:** `cogs/music.py:734-745, 767-770, 780-783`

**Issue:** `queue._xf_truncator` is set to the newly-constructed
`TruncatingSource` **only** on the `FadeVerdict.FADE` branch (line 737).
There is no corresponding `else: queue._xf_truncator = None` on the hard-cut
branch (line 744-745), and none of `_play_track`'s early-return paths that
run *after* line 737 reset it either:

- `if not voice_client.is_connected(): source.cleanup(); queue.is_playing = False; return`
  (lines 767-770) cleans up the very `TruncatingSource` that
  `queue._xf_truncator` still points to, but leaves the (now already
  cleaned-up) reference sitting in the field.
- `except Exception: source.cleanup(); queue.is_playing = False; raise`
  (lines 780-783) around `voice_client.play()` has the same gap.

The only place `_xf_truncator` is ever reset to `None` is `_on_track_end`'s
unconditional clear (`cogs/music.py:932`). But `/seek`, `/jump`,
`/previous`, `/replay`, and `/filter`'s re-play-from-current-position path
all call `_play_track` **directly**, bypassing `_on_track_end` entirely (by
design — a manual re-entry is not a natural track end). If any of those
commands fires while a `FADE`-verdict track is mid-playback, the previous
track's stale `TruncatingSource` reference lingers in `_xf_truncator` until
either a later `_on_track_end` call clears it or a later `FADE` verdict
overwrites it.

Today this is harmless in practice: `TruncatingSource.cut_short` can only
become `True` from inside the object's own `read()` reaching `max_frames`,
and a stale/abandoned truncator that was cut off early by
`voice_client.stop()` never gets `read()` called again, so
`_on_track_end`'s `queue._xf_truncator.cut_short` check on a stale object
always evaluates `False` and no bad handoff is armed from it. But this
relies on that invariant holding forever, and it is also exactly the field
`bot.py`'s `cache_cleanup` (WR-01) treats as a meaningful "crossfade in
flight" signal — a lingering stale reference there makes that check
over-broad in a way that happens to be harmless only by the same accident.

**Fix:** Add an explicit `queue._xf_truncator = None` on the non-FADE
branch (mirroring the `else: log.info(...)` at line 744-745), and reset it
in the two early-return paths above right where `source.cleanup()` is
already called, so the field's invariant ("this is the currently-armed
live truncator, or `None`") holds unconditionally rather than "usually
holds, and is harmless when it doesn't."

---

### WR-03: `discord.py` is not pinned, despite `utils/discord_patch.py` documenting the patch against "the pinned 2.7.1"

**File:** `requirements.txt:1`, `utils/discord_patch.py:4-5`

**Issue:** `utils/discord_patch.py`'s module docstring states:

> **This patches an undocumented discord.py internal**
> (`AudioPlayer.send_silence`, `discord/player.py:892` in the pinned 2.7.1)

but `requirements.txt` specifies `discord.py>=2.3.0` — an open lower bound,
never actually pinned to `2.7.1` or any exact version. There is no lock
file (`Dockerfile` runs a bare `pip install -r requirements.txt`), so a
fresh `docker build` months from now (or any local `pip install -U`) can
silently resolve a newer discord.py whose `AudioPlayer._do_run`/
`send_silence` internals have moved. `send_silence_patch_target_present()`'s
source-inspection guard is a real and useful runtime safety net (it fails
soft, logs a warning, and CI's `tests/test_discord_patch.py` would catch
the drift against whatever version CI happens to resolve) — but "pinned
2.7.1" in the docstring is simply false against the actual dependency
spec, and an unpinned private-API dependency means the CI environment and
a later production rebuild can silently diverge on discord.py version,
undermining the reproducibility this patch's whole design assumes.

**Fix:** Either pin `discord.py==2.7.1` in `requirements.txt` (matching
what the docstring already claims), or soften the docstring to describe
the version range actually tested/supported and rely purely on the
runtime drift guard.

## Info

### IN-01: Crossfade tail re-decode passes streaming reconnect flags to a local file

**File:** `services/audio.py:251-254`

**Issue:** The tail decoder for a crossfade re-decodes an already-cached
local `.opus` file, but reuses `_RECONNECT_FLAGS` (`-reconnect 1
-reconnect_streamed 1 -reconnect_delay_max 5`), which exist to handle
network hiccups on a streamed URL. FFmpeg will simply ignore these flags on
a local file, so this is not a bug, just leftover copy-paste from the
existing streaming-source helper that adds noise to the constructed
`before_options` string.

**Fix:** Build a minimal `before_options=f"-ss {cut_seconds}"` for the
local-file tail re-decode instead of reusing the streaming constant.

### IN-02: `/crossfade` slash command itself has no direct test coverage

**File:** `cogs/music.py:2057-2079`

**Issue:** `logic/crossfade.py`'s decision ladder, `TruncatingSource`/
`CrossfadeSource`, and the `_play_track`/`_on_track_end` wiring are all
well covered. The `/crossfade` command handler that flips
`queue.crossfade_enabled` and replies with `CROSSFADE_ON`/`CROSSFADE_OFF`
has no test exercising the command itself (that it actually sets the flag
on the right queue, uses `AllowedMentions.none()`, etc.) — only the
response-pool content is tested (`tests/test_responses.py`) and the field's
survival-through-`clear()` is tested at the model layer
(`tests/test_queue.py`).

**Fix:** Add a thin command-level test mirroring the existing `/autolyrics`
coverage pattern, if one exists, or accept this as intentionally covered
indirectly (model + response pool) per the project's existing testing
style for other simple toggle commands.

### IN-03: No test coverage for `bot.py`'s crossfade cache-protection block

**File:** `bot.py:1041-1078`

**Issue:** This is the flip side of WR-01 — none of the phase's test files
touch `cache_cleanup`'s `protected_video_ids` construction at all, so the
gap identified in WR-01 was not caught by the test suite and a fix would
not be locked against regression without new coverage.

**Fix:** Add a test that constructs a `MusicQueue` with `_xf_truncator`
set to a live (unclosed) `TruncatingSource` and asserts the outgoing
track's `video_id` is present in `protected_video_ids`, then a second test
that reproduces the WR-01 timing (flags already cleared, as they are
during real `CrossfadeSource` playback) and documents the current gap
until WR-01 is fixed.

---

_Reviewed: 2026-07-17_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
