---
phase: "07-player-ux-filters"
plan: "01"
subsystem: "player-foundations"
tags: [tdd, queue, audio, formatters, config, personality, phase7]
dependency_graph:
  requires: []
  provides:
    - MusicQueue.elapsed_seconds / mark_started / mark_paused / mark_resumed
    - MusicQueue.active_filter
    - MusicQueue.jump_to()
    - utils.formatters.parse_time()
    - services.audio._build_ffmpeg_opts()
    - services.audio.AudioService.get_source(seek_seconds, ffmpeg_filter)
    - config.FFMPEG_FILTERS
    - config.FAVORITES_MAX_PER_USER / PLAYLISTS_MAX_PER_USER / cooldowns
    - personality.responses Phase 7 pools
  affects:
    - models/queue.py
    - utils/formatters.py
    - services/audio.py
    - config.py
    - personality/responses.py
tech_stack:
  added: []
  patterns:
    - clock-injectable elapsed tracking (now: float | None = None)
    - pure FFmpeg opts builder (_build_ffmpeg_opts)
    - TDD RED/GREEN cycle for all testable functions
key_files:
  created: []
  modified:
    - models/queue.py
    - utils/formatters.py
    - services/audio.py
    - config.py
    - personality/responses.py
    - tests/test_queue.py
    - tests/test_formatters.py
    - tests/test_audio.py
    - tests/test_responses.py
decisions:
  - "elapsed_seconds uses injected 'now' float param for full clock isolation in tests"
  - "_build_ffmpeg_opts is a module-level pure function (not a method) so test_audio.py can import and test it without mocking AudioService"
  - "get_source default path (no seek, no filter) is unchanged — passthrough preserved (D-12)"
  - "FFMPEG_FILTERS dict does not include 'off' key — off = absence of filter"
  - "minutes field in mm:ss validated as 0-59 for parse_time (not strictly required by spec, but consistent with h:mm:ss format)"
metrics:
  duration: "~9 min (542 seconds)"
  completed: "2026-06-18"
  tasks_completed: 5
  files_modified: 9
---

# Phase 7 Plan 01: Player UX Foundations Summary

**One-liner:** Clock-injectable elapsed tracking + parse_time + _build_ffmpeg_opts with opus-passthrough default, 4 filter presets, Phase 7 personality pools — all TDD-tested.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Add elapsed tracking, active_filter, jump_to() to MusicQueue | 0c60097 | models/queue.py, tests/test_queue.py |
| 2 | Add parse_time() to formatters | 97d8404 | utils/formatters.py, tests/test_formatters.py |
| 3 | Extend AudioService with seek + filter source options | 3ac19a5 | services/audio.py, tests/test_audio.py |
| 4 | Add filter presets, caps, and cooldowns to config.py | fe5509a | config.py |
| 5 | Add Phase 7 personality response pools | 47e6be1 | personality/responses.py, tests/test_responses.py |

## What Was Built

### Task 1 — MusicQueue elapsed tracking + active_filter + jump_to()
- `mark_started(offset_seconds=0, now=None)`: records virtual start timestamp adjusted for seek offset; clears paused_at
- `mark_paused(now=None)`: freezes the elapsed counter
- `mark_resumed(now=None)`: advances start stamp to exclude the pause gap
- `elapsed_seconds(now=None) -> int`: returns 0 before started; clamps to [0, duration_seconds]
- `active_filter: str = "off"`: guild-level active filter state, reset by clear()
- `jump_to(index) -> Track | None`: bounds-checked index move, returns None without mutating on failure
- `clear()` extended: resets active_filter, playback_started_at, paused_at — but NOT auto_lyrics/lyrics_thread_id
- 17 new tests across TestElapsedTracking, TestJumpTo, test_clear_resets_filter_and_elapsed

### Task 2 — parse_time()
- Accepts raw seconds ("90"), mm:ss ("1:30"), h:mm:ss ("1:01:30")
- Validates seconds/minutes are 0-59; rejects negatives; strips whitespace; returns None on any failure
- 12 test cases including round-trip with format_duration

### Task 3 — AudioService._build_ffmpeg_opts + get_source extension
- `_build_ffmpeg_opts(seek_seconds, ffmpeg_filter)`: pure module-level helper, always includes reconnect flags, prepends -ss only when seek>0, appends -af only when filter set
- `get_source(track, *, seek_seconds=0, ffmpeg_filter=None)`: transcode only when seek/filter active; default path (opus passthrough for cached tracks) unchanged (D-12)
- All three tiers (cache, download, stream fallback) handle both paths
- 5 pure unit tests for _build_ffmpeg_opts

### Task 4 — config.py Phase 7 constants
- `FFMPEG_FILTERS`: bassboost="bass=g=8", nightcore="asetrate=48000*1.25,aresample=48000", slowed+reverb="asetrate=48000*0.85,aresample=48000,aecho=0.8:0.9:1000:0.3", 8d="apulsator=hz=0.09"
- FAVORITES_MAX_PER_USER=25, PLAYLISTS_MAX_PER_USER=25, PLAYLIST_NAME_MAX_LENGTH=60
- SEEK_COOLDOWN_SECONDS=2, FILTER_COOLDOWN_SECONDS=5, FAVORITE_COOLDOWN_SECONDS=2

### Task 5 — Phase 7 personality response pools
- 12 new pools: FILTER_APPLIED, FILTER_CLEARED, FAVORITE_SAVED, FAVORITE_DUPLICATE, FAVORITE_CAP_HIT, FAVORITES_EMPTY, PLAYLIST_SAVED, PLAYLIST_LOADED, PLAYLIST_NOT_FOUND, PLAYLIST_CAP_HIT, NOT_IN_VOICE, NOTHING_PLAYING
- All lowercase, one-emoji-max, Dexter voice (dry, sarcastic)
- Parametrized test covering all 12 pools

## Verification Results

```
pytest tests/test_queue.py tests/test_formatters.py tests/test_audio.py tests/test_responses.py -x -q
79 passed, 1 warning
```

```
python -c "import config, models.queue, utils.formatters, services.audio, personality.responses; print('import OK')"
import OK
```

Pre-existing test failures in tests/test_ai_helpers.py, test_autoqueue_parse.py, test_gemini.py, test_rate_limiter.py, test_youtube.py, test_ytdlp_selfheal.py — all caused by google-genai / yt-dlp not installed in the local Windows dev environment (bot runs in Docker). These failures predate this plan and are unrelated to the changes made here.

## Deviations from Plan

### Minor adaptations (not deviations)
- parse_time also validates minutes field 0-59 (not required by spec but consistent with h:mm:ss semantics)
- _RECONNECT_FLAGS extracted as a module-level constant in audio.py to avoid duplication between FFMPEG_STREAM_OPTS and _build_ffmpeg_opts (clean refactor, no behavior change)

None of the must_haves or artifacts were deviated from. All acceptance criteria met exactly.

## Threat Model Compliance

- **T-07-01-01** (FFmpeg injection via -af): _build_ffmpeg_opts accepts only a pre-resolved chain string (never raw user text). Plan 02 will enforce this via app_commands.Choices — the boundary is documented.
- **T-07-01-02** (seek injection): parse_time returns int or None; Plan 02 validates/clamps before passing to -ss.
- **T-07-01-03** (DoS via re-encode): accepted; bounded by 15-min cap + cooldowns now in config.

## Known Stubs

None — this plan is pure logic/service layer. No Discord commands or UI wired yet (those are Plan 02).

## Self-Check: PASSED
- models/queue.py: contains `def elapsed_seconds`, `def jump_to`, `self.active_filter` — FOUND
- utils/formatters.py: contains `def parse_time` — FOUND
- services/audio.py: contains `_build_ffmpeg_opts` and `get_source(self, track, *, seek_seconds` — FOUND
- config.py: contains `FFMPEG_FILTERS` — FOUND
- personality/responses.py: contains `FILTER_APPLIED`, `FAVORITE_SAVED`, `PLAYLIST_SAVED`, `NOT_IN_VOICE` — FOUND
- Commits 0c60097, 97d8404, 3ac19a5, fe5509a, 47e6be1 — all verified in git log
