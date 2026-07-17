---
phase: 27-crossfade-playback-spike-gated
plan: 05
subsystem: music
tags: [discord.py, slash-command, playback-engine, crossfade, structural-guards, pytest]

# Dependency graph
requires:
  - phase: 27-01
    provides: "logic.crossfade.decide_crossfade (FadeVerdict ladder) + cut_frame() + CROSSFADE_SECONDS/CROSSFADE_MIN_TRACK_SECONDS config knobs"
  - phase: 27-02
    provides: "MusicQueue.crossfade_enabled preference (survives clear()) + _xf_pending/_xf_truncator scratch state (nulled by clear()) + CROSSFADE_ON/OFF copy pools"
  - phase: 27-03
    provides: "TruncatingSource / CrossfadeSource in services/audio.py + additive crossfade_from= kwarg on AudioService.get_source"
  - phase: 27-04
    provides: "boot-time send_silence suppression rail + fade-aware LFU protected set"
provides:
  - "cogs/music.py::MusicCog.crossfade — /crossfade on|off slash command (the /autolyrics shape, no defer, no cooldown, AllowedMentions.none())"
  - "cogs/music.py::_play_track — the two integration points: consume queue._xf_pending as crossfade_from= at get_source time; consult decide_crossfade before the generation increment and wrap in TruncatingSource on FADE, log-only hard cut otherwise (D-10b)"
  - "cogs/music.py::_on_track_end — the crossfade handoff: set _xf_pending from truncator.position_seconds when cut_short, clear _xf_truncator unconditionally, ahead of the decide_on_track_end dispatch"
  - "tests/test_music_wiring.py — 12 structural guards locking the D-01 generation block, the log-only hard-cut branch, and the Phase 26 D-15 _do_skip choke point crossfade-free"
affects: ["Phase 27 close — DJ-03 feature-complete at the code level; live-Discord ear check + decoder-tolerance items parked to 27-HUMAN-UAT.md"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive glue over an inviolable engine (D-01): the fade lives inside the incoming track's own AudioSource wrapper; the per-track voice_client.play() + generation-counter block is byte-identical, asserted by a source-introspection tripwire test"
    - "Structural review encoded as tests (the Phase 26 test_music_wiring.py convention) rather than mock-heavy unit tests over untested-by-design glue — safety evidence is the spike's D-11 attack artifacts, not mocks"

key-files:
  created: []
  modified:
    - cogs/music.py
    - tests/test_music_wiring.py

key-decisions:
  - "Task 3's D-12c guard shipped as test_try_skip_has_no_crossfade_references + test_do_skip_has_no_crossfade_references (proving the choke point stayed crossfade-free) rather than duplicating Phase 26's existing single-call-site assertion — same D-15 invariant, no test duplication"
  - "The non-FADE branch is log-only (D-10b): no channel.send / followup / response — a non-fadeable transition silently hard-cuts, the room sees nothing; locked by test_crossfade_hard_cut_is_log_only"
  - "filter_active is fed from the already-resolved ffmpeg_filter local, not a re-derived queue.active_filter != 'off' — locked by test_filter_active_reuses_resolved_local_not_rederived"

patterns-established:
  - "A cross-invocation playback handoff (_xf_pending) is set at one site, consumed-and-cleared at one site, and cleared unconditionally at the boundary — three independent controls guard against a stale fade from a departed track (T-27-26)"

requirements-completed: [DJ-03]

# Metrics
duration: ~45min (incl. crash recovery)
completed: 2026-07-17
---

# Phase 27 Plan 05: Crossfade Feature Wiring Summary

**The `/crossfade on|off` command plus the three glue insertions (`_play_track` handoff-consume + `decide_crossfade`-dispatch, `_on_track_end` handoff-set) that make the prior four plans' inert machinery actually fade — additive over an untouched D-01 engine block and Phase 26's `_do_skip` choke point, both locked by structural tripwire tests.**

## Performance

- **Duration:** ~45 min including a mid-Task-3 session-limit crash and orchestrator-side recovery
- **Completed:** 2026-07-17
- **Tasks:** 3 (all `type="auto"`)
- **Files modified:** 2 (0 created, 2 modified)

## Accomplishments

- `MusicCog.crossfade` — a `/crossfade on|off` slash command in the `/autolyrics` shape: two `app_commands.Choice` literals, **no** `defer()`, **no** cooldown decorator, `AllowedMentions.none()` on both branches, copy sourced from `responses.CROSSFADE_ON`/`CROSSFADE_OFF` via `pick_random` (no inline literals). Toggles the in-memory `queue.crossfade_enabled` server preference; defaults off.
- `_play_track` **integration point 1**: reads `queue._xf_pending` before `get_source`, passes it as `crossfade_from=` when set, and clears it in the same block so it can never be consumed twice. Byte-identical `get_source` call when unset.
- `_play_track` **integration point 2**: consults `decide_crossfade` exactly once, before the `_play_generation += 1` increment, fed from the already-resolved `ffmpeg_filter` local (not a re-derived `active_filter` check). On `FadeVerdict.FADE` it wraps `source` in `TruncatingSource(...)` via `cut_frame(...)` and stashes the truncator on `queue._xf_truncator`; every other verdict logs a hard-cut line and passes `source` through untouched — **D-10b log-only, no user-facing message**.
- `_on_track_end` **handoff**: ahead of the existing `decide_on_track_end` dispatch, sets `queue._xf_pending = (current, truncator.position_seconds)` when the truncator cut short and playback continues, then clears `_xf_truncator` **unconditionally**. The cut position is read from `position_seconds` (the in-process frame count), never from `Track.duration_seconds` (landmine #5 — hostile metadata cannot produce an `-ss` past EOF).
- The D-01 engine block (`_play_generation += 1` → `current_gen` capture → `after_callback` → generation guard → `stop()`/`play()`), `_try_skip`, `_do_skip`, and the skip-vote cache are **provably untouched** — asserted by `test_play_track_generation_block_intact` and the two `*_has_no_crossfade_references` guards.
- `tests/test_music_wiring.py` gained 12 structural guards (source-introspection, not mocks over glue): generation-block-intact, hard-cut-is-log-only, decide_crossfade-called-once, consulted-before-increment, `_xf_pending`-cleared-where-consumed, filter-active-reuses-resolved-local, handoff-reads-position_seconds-not-duration, truncator-cleared-on-every-path, handoff-precedes-advance, `_on_track_end`-still-dispatches-TrackEndAction, and the two `_try_skip`/`_do_skip` crossfade-free guards.

## Task Commits

1. **Task 1: /crossfade on|off command (the /autolyrics shape)** — `42da4cc` (feat)
2. **Task 2: _play_track — consume the handoff + arm this track's fade** — `fcacdb1` (feat)
3. **Task 3: _on_track_end handoff + D-01/D-12c structural guards** — `bbc5894` (feat)

## Files Modified

- `cogs/music.py` — `/crossfade` command; the two `_play_track` integration points; the `_on_track_end` handoff
- `tests/test_music_wiring.py` — 12 structural tripwire guards (155 insertions across the Task 3 commit)

## Decisions Made

- Task 3's D-12c invariant is guarded by proving `_try_skip`/`_do_skip` contain **no** crossfade references (both source-scanned) rather than duplicating Phase 26's existing single-call-site assertion — the D-15 choke point invariant survives this phase without test duplication.
- The non-FADE dispatch branch is strictly log-only — no `channel.send`/`followup`/`response` — so a non-fadeable transition is indistinguishable from current behavior to the room (D-10b), locked by `test_crossfade_hard_cut_is_log_only`.

## Deviations from Plan

None to the code. **Execution deviation (process, not code):** the executor agent hit an API session limit partway through Task 3 — after the code was written, staged, and verified green (`1233 passed`) but before it committed or wrote this SUMMARY. Recovery was performed orchestrator-side per the API-crash-resume protocol: the staged diff was independently verified (correct `_on_track_end` handoff reading `position_seconds`; `_try_skip`/`_do_skip` untouched; all 12 guards present), the wiring suite (58 passed) and ruff (clean) re-run, then Task 3 committed as `bbc5894` and the full suite re-confirmed. No blind redispatch, no double-commit.

## Issues Encountered

- One mid-Task-3 session-limit crash (recovered as above). No code issues.

## Verification

- `pytest tests/test_music_wiring.py -q` → **58 passed**.
- `pytest -q` full suite → **1233 passed, 129 skipped, 0 failed** in 424s (above the 1175 baseline; +12 over 27-04's 1221).
- `ruff check .` → clean repo-wide.
- `git diff` over `_try_skip`, `_do_skip`, the skip-vote cache, and `_play_track`'s generation block is empty (the D-01/D-15 subjects, verbatim) — enforced by the tripwire tests.

## User Setup Required

None — zero new dependencies. `/crossfade` is reachable immediately and defaults off.

## Next Phase Readiness

- **DJ-03 is feature-complete at the code level.** All 18 Behavior Map rows are covered once this glue lands.
- Two live-Discord items are parked to `27-HUMAN-UAT.md` per the plan's SC-2 bar (an agent cannot hear): D-09 the user re-listens to the shipped render to confirm the fade is smooth; D-17.5 confirms the real Discord decoder tolerates the suppressed `send_silence` marker without artifacting.
- Full suite green at **1233 passed, 0 failed**. No blockers to phase 27 close.

---
*Phase: 27-crossfade-playback-spike-gated*
*Completed: 2026-07-17*

## Self-Check: PASSED

Both modified files found on disk; all 3 task commit hashes (42da4cc, fcacdb1, bbc5894) found in git log. Full suite green (1233 passed, 0 failed); ruff clean.
