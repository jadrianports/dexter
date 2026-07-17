---
phase: 27-crossfade-playback-spike-gated
plan: 03
subsystem: music
tags: [audio-source, ffmpeg, audioop, discord-audiosource, crossfade, tdd]

# Dependency graph
requires:
  - phase: 27-crossfade-playback-spike-gated
    provides: "27-01's pure logic/crossfade.py eligibility seam (FadeVerdict, decide_crossfade, cut_frame) and the CROSSFADE_SECONDS/CROSSFADE_MIN_TRACK_SECONDS config knobs this plan's fade_frames arithmetic consumes"
provides:
  - "services/audio.py::TruncatingSource — wraps a source and exhausts it early at a fixed frame count, delegating is_opus() and setting the D-17.3 _suppress_end_silence flag only on a fade cut"
  - "services/audio.py::CrossfadeSource — equal-power audioop mixer over two FFmpegPCMAudio children, one cleanup() owning both (Critical Rule 3)"
  - "services/audio.py::AudioService.get_source(crossfade_from=...) — additive, byte-identical-when-omitted kwarg that builds a CrossfadeSource when both files are cached"
affects: ["27-04 (utils/discord_patch.py's send_silence suppression reads TruncatingSource._suppress_end_silence duck-typed via getattr)", "any future cogs/music.py _play_track/_on_track_end glue that wires this mixing half into the real playback engine"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-decoder window expressed as ONE discord.AudioSource so one cleanup() owns both children (Critical Rule 3) — no existing teardown site needs editing"
    - "Additive kwarg, byte-identical when omitted (Phase 14 kind / Phase 21 guild_scoped / Phase 26 radio= discipline), locked by a behavioral (not source-scan) regression test"
    - "A source-attribute flag set ONLY at the exact instant of a specific event (D-17.3: _suppress_end_silence set on a fade cut, never at construction, never on a natural EOF)"

key-files:
  created: []
  modified:
    - services/audio.py
    - tests/test_audio.py

key-decisions:
  - "cleanup() cleans the tail in a try and the head in a finally, so a raising tail cleanup can never strand the head decoder — matches the plan's key_links pattern exactly."
  - "frames_per_second is derived as 1000 // 20 (the 20ms Discord frame duration) rather than hardcoding 50 as a second magic number, per the task's explicit instruction."
  - "An empty tail (short file / -ss seek past EOF) degrades to a plain fade-in via audioop.mul(head, 2, g_in) rather than raising, satisfying FFmpegPCMAudio's exactly-3840-bytes-or-b'' contract with no padding."

patterns-established:
  - "The five mandated VALIDATION-row test names (test_truncating_source, test_suppress_flag_only_on_fade_cut, test_crossfade_source_cleans_both, test_crossfade_tolerates_empty_tail, test_get_source_unchanged_without_crossfade) are all module-level functions (not nested in a class), matching VALIDATION's exact bare node-id pytest commands."

requirements-completed: [DJ-03]

# Metrics
duration: 35min
completed: 2026-07-17
---

# Phase 27 Plan 03: Crossfade Mixing Half (TruncatingSource + CrossfadeSource + crossfade_from=) Summary

**Two new `discord.AudioSource` subclasses in `services/audio.py` — `TruncatingSource` (early exhaustion + the D-17.3 suppression flag) and `CrossfadeSource` (equal-power `audioop` mixing, one `cleanup()` owning both children) — plus an additive `crossfade_from=` kwarg on `get_source`, locked by 5 VALIDATION-mandated tests plus supporting coverage.**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-07-17T10:35:00Z
- **Completed:** 2026-07-17T11:04:18Z
- **Tasks:** 3 completed
- **Files modified:** 2 (`services/audio.py`, `tests/test_audio.py`)

## Accomplishments
- `TruncatingSource(discord.AudioSource)`: exhausts the inner source at a fixed `max_frames`, delegating `is_opus()` so the outgoing track keeps the opus fast path for its entire body — only the last few seconds read through this wrapper are ever PCM. `_suppress_end_silence` is set to `True` ONLY at the instant `read()` cuts short for a fade, never at construction and never on a natural early EOF (D-17.3) — the flag `utils/discord_patch.py` (plan 27-04) will read `getattr`-duck-typed.
- `CrossfadeSource(discord.AudioSource)`: mixes an outgoing tail into an incoming head with `audioop.mul`/`audioop.add` (width 2, equal-power curve, **no headroom gain** per RESEARCH's 0.0019% clipping measurement). Drops and cleans the tail the instant the fade window ends. `cleanup()` cleans the tail in a `try` and the head in a `finally` — the entire surface of Critical Rule 3 for this feature, since the two-live-decoder window is expressible as ONE `AudioSource`.
- `AudioService.get_source(crossfade_from=(outgoing_track, cut_seconds))`: additive keyword-only kwarg. Omitted → not one existing line of the opus-passthrough/download/stream ladder changes. Set + both files cached → returns a `CrossfadeSource`. Set + outgoing file missing → defensive fall-through to the ordinary ladder, never raises.
- 9 new tests in `tests/test_audio.py`: the 5 VALIDATION-mandated names (`test_truncating_source`, `test_suppress_flag_only_on_fade_cut`, `test_crossfade_source_cleans_both`, `test_crossfade_tolerates_empty_tail`, `test_get_source_unchanged_without_crossfade`) all as module-level functions matching VALIDATION's bare node-id commands, plus 4 supporting tests (`TestCrossfadeSourceMixing` mix-window/equal-power coverage, `TestGetSourceCrossfadeFrom` both-cached/outgoing-missing coverage).
- Zero new dependencies: `import audioop` / `import math` at module top, both stdlib on the pinned Python 3.11 (D-02). `grep -c numpy services/audio.py` == 0.
- Full suite: **1215 passed, 0 failed** (>= 1175 baseline required by plan).

## Task Commits

Each task was committed atomically:

1. **Task 1: TruncatingSource — early exhaustion, is_opus delegation, and the D-17.3 suppression flag** - `4d9d189` (feat)
2. **Task 2: CrossfadeSource — equal-power audioop mixing with both children owned by one cleanup** - `0d99a81` (feat)
3. **Task 3: The additive crossfade_from= kwarg + the byte-identical-when-off regression guard** - `f736a86` (feat)

## Files Created/Modified
- `services/audio.py` - Added `TruncatingSource`, `CrossfadeSource`, and the `crossfade_from=` kwarg on `AudioService.get_source`; added `import audioop` / `import math`.
- `tests/test_audio.py` - Added `_FakeAudioSource` stub, the 5 VALIDATION-mandated tests, and 4 supporting test classes/functions.

## Decisions Made
- `cleanup()`'s tail-in-try/head-in-finally structure exactly matches the plan's frontmatter `key_links` pattern (`services/audio.py::CrossfadeSource.cleanup -> both child sources via "tail cleanup in try, head cleanup in finally"`) — no deviation.
- `frames_per_second = 1000 // 20` derives the 50-frames/sec constant from the frame duration rather than hardcoding it a second time, per the task action's explicit instruction.
- The 5 mandated test names are module-level functions (not class methods), matching VALIDATION's exact `pytest tests/test_audio.py::test_name -x` node-id commands — a class-nested method would have produced a different node id and silently broken the validation contract.

## Deviations from Plan

None - plan executed exactly as written. All acceptance criteria for all three tasks were met on first implementation; no auto-fixes were needed.

## Issues Encountered

None. The three-task split was implemented as one combined change and verified together first (all 25 `test_audio.py` tests + the full 1215-test suite passing), then reconstructed into three atomic per-task commits by writing intermediate file states — required because this is a sequential (non-worktree) executor where each task must land as its own commit.

## User Setup Required

None - no external service configuration required. Zero new dependencies (D-02: `audioop`/`math` are stdlib on the pinned Python 3.11).

## Next Phase Readiness
- The mixing half (`TruncatingSource`, `CrossfadeSource`, `crossfade_from=`) is ready for plan 27-04 to wire in the `send_silence` suppression patch (D-17 GO/suppressed variant) and for a later plan to integrate both into `cogs/music.py::_play_track`/`_on_track_end` per RESEARCH §5's two integration points.
- `_suppress_end_silence` is already present and correctly gated (D-17.3) — plan 27-04 can read it via `getattr(self.source, "_suppress_end_silence", False)` with no further changes to this plan's classes.
- No blockers. Full suite green (1215 passed, 0 failed), ruff clean on both modified files, `# Opus passthrough — D-12 default path, unchanged` marker survives unmodified.

---
*Phase: 27-crossfade-playback-spike-gated*
*Completed: 2026-07-17*
