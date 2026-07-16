---
phase: 27
slug: crossfade-playback-spike-gated
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-17
---

# Phase 27 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `27-RESEARCH.md` §"Validation Architecture" (the plan-time spike, both rounds).
> **Gate outcome: GO / suppressed (D-17).** The suppressed-variant rows below are IN SCOPE.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (+ pytest-asyncio) |
| **Config file** | `pyproject.toml` (ruff); pytest via `tests/conftest.py` |
| **Quick run command** | `pytest tests/test_crossfade_logic.py -x -q` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | ~2s quick · full suite baseline **1175 passed / 129 skipped / 0 failed** |

**No new dependency (D-02).** `audioop` is stdlib on the pinned 3.11 (`Dockerfile:4`,
`ci.yml` 3.11 at both jobs). Note: the maintainer's local interpreter is **3.12.10**, where
`audioop` still imports but emits a `DeprecationWarning` — harmless, but do not let a
`-W error` setting creep into the pytest config or the suite will fail locally.

---

## Sampling Rate

- **After every task commit:** `pytest tests/test_crossfade_logic.py -x -q`
- **After every plan wave:** `pytest -q`
- **Before `/gsd-verify-work`:** full suite green (≥1175 passed, 0 failed) **and** the D-08 render
  re-listened by the user
- **Max feedback latency:** ~30s (full suite)

---

## Per-Task Verification Map

*Populated by the planner once task IDs exist. Every row below MUST map to at least one task.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| T-27-01-01 | 27-01 | 1 | DJ-03 | T-27-SC | Global knobs only; zero installs | unit | `python -c "import config; assert config.CROSSFADE_SECONDS == 4"` | ✅ | ⬜ pending |
| T-27-01-02 | 27-01 | 1 | DJ-03 | T-27-01, T-27-03 | Pure seam; no discord import; cut_frame floors at 0 | unit | `pytest tests/test_crossfade_logic.py -x -q` | ❌ W0 | ⬜ pending |
| T-27-01-03 | 27-01 | 1 | DJ-03 | T-27-01 | Rows 1-8: full ladder + precedence, mock-free | unit | `pytest tests/test_crossfade_logic.py -x -q` | ❌ W0 | ⬜ pending |
| T-27-02-01 | 27-02 | 1 | DJ-03 | T-27-05 | D-12 split: preference survives clear, scratch state does not | unit | `pytest tests/test_queue.py -x -q` | ✅ | ⬜ pending |
| T-27-02-02 | 27-02 | 1 | DJ-03 | T-27-06 | Rows 9-10: exact key-set equality on the persist payload | unit | `pytest tests/test_queue.py tests/test_queue_persistence.py -x -q` | ❌ W0 | ⬜ pending |
| T-27-02-03 | 27-02 | 1 | DJ-03 | T-27-08 | Row 15: lowercase, ≤1 emoji, zero-arg pools | unit | `pytest tests/test_responses.py -x -q` | ✅ | ⬜ pending |
| T-27-03-01 | 27-03 | 2 | DJ-03 | T-27-09 | Row 16: suppress flag ONLY on a fade cut (D-17.3) | unit | `pytest tests/test_audio.py -x -q -k "truncating or suppress"` | ✅ | ⬜ pending |
| T-27-03-02 | 27-03 | 2 | DJ-03 | T-27-11, T-27-13 | Rows 13-14: cleanup owns both children (head in finally); empty tail degrades | unit | `pytest tests/test_audio.py -x -q -k "crossfade_source or empty_tail or cleans_both"` | ✅ | ⬜ pending |
| T-27-03-03 | 27-03 | 2 | DJ-03 | T-27-12 | Rows 11-12: byte-identical when off (opus fast path) | unit | `pytest tests/test_audio.py -x -q` | ✅ | ⬜ pending |
| T-27-04-01 | 27-04 | 2 | DJ-03 | **T-27-15, T-27-16** | D-17.4a: wrapped, fail-soft, source-attribute-gated install | unit | `pytest tests/test_discord_patch.py -x -q -k "install or fails_soft"` | ❌ W0 | ⬜ pending |
| T-27-04-02 | 27-04 | 2 | DJ-03 | **T-27-17** | **Rows 17-18: drift guard asserts the CALL SITE + mandatory positive control** | unit | `pytest tests/test_discord_patch.py -x -q` | ❌ W0 | ⬜ pending |
| T-27-04-03 | 27-04 | 2 | DJ-03 | T-27-18, T-27-19 | Single install site; fade-aware LFU protected set | unit | `pytest tests/test_discord_patch.py -x -q` | ❌ W0 | ⬜ pending |
| T-27-05-01 | 27-05 | 3 | DJ-03 | T-27-24, T-27-25 | `/crossfade on\|off`, no defer, no cooldown, AllowedMentions.none() | unit | `pytest tests/test_music_wiring.py -x -q` | ✅ | ⬜ pending |
| T-27-05-02 | 27-05 | 3 | DJ-03 | T-27-21, T-27-22 | D-01 engine block verbatim; D-10b hard cut is log-only | unit | `pytest tests/test_music_wiring.py -x -q` | ✅ | ⬜ pending |
| T-27-05-03 | 27-05 | 3 | DJ-03 | T-27-23, T-27-27 | Phase 26 `_do_skip` choke point + vote cache untouched | unit | `pytest tests/test_music_wiring.py -x -q` | ✅ | ⬜ pending |

> **Row 17/18 file-path deviation (planner, recorded deliberately).** The Behavior Map below names
> `tests/test_audio.py` for rows 17-18. The plans instead put them in **`tests/test_discord_patch.py`**,
> mirroring the module under test (`utils/discord_patch.py`) and following the
> **`tests/test_invite_drift_guard.py` precedent** — the repo's only other "fail the build when an
> external fact drifts" guard, which is its own file. **The BEHAVIOR of rows 17-18 is unchanged and
> non-negotiable**; only the file path moved. Row 16 stays in `tests/test_audio.py` because the flag
> is a `TruncatingSource` property.

### Behavior Map (source of truth — from RESEARCH.md)

| # | Behavior | Decision | Test Type | Automated Command |
|---|----------|----------|-----------|-------------------|
| 1 | `decide_crossfade` returns FADE when every condition allows | D-14 | unit | `pytest tests/test_crossfade_logic.py::test_fade_when_eligible -x` |
| 2 | Toggle off → `NO_TOGGLE` (off-by-default) | D-08b | unit | `pytest tests/test_crossfade_logic.py::test_toggle_off_never_fades -x` |
| 3 | loop SINGLE → `LOOP_SINGLE`; **loop QUEUE still fades** | D-11b | unit | `pytest tests/test_crossfade_logic.py::test_loop_single_hard_cuts -x` |
| 4 | Filter active → `FILTER_ACTIVE` | D-10b | unit | `pytest tests/test_crossfade_logic.py::test_filter_hard_cuts -x` |
| 5 | Either track uncached → `NOT_CACHED` (narrow-go) | D-03 | unit | `pytest tests/test_crossfade_logic.py::test_uncached_hard_cuts -x` |
| 6 | No next track / seeked / too-short → correct verdict | D-10b | unit | `pytest tests/test_crossfade_logic.py::test_remaining_ladder_rungs -x` |
| 7 | Ladder **order** stable (each rung wins over later ones) | D-14 | unit | `pytest tests/test_crossfade_logic.py::test_ladder_precedence -x` |
| 8 | `cut_frame` arithmetic (incl. metadata-vs-file mismatch guard) | D-12b | unit | `pytest tests/test_crossfade_logic.py::test_cut_frame -x` |
| 9 | `crossfade_enabled` survives `clear()`; fade scratch state IS reset by it | D-12 | unit | `pytest tests/test_queue.py::test_crossfade_toggle_survives_clear -x` |
| 10 | Toggle **not** persisted | D-12 | unit | `pytest tests/test_queue_persistence.py::test_crossfade_not_persisted -x` |
| 11 | **Byte-identical when off**: `get_source()` unchanged, opus fast path intact | D-08b | unit | `pytest tests/test_audio.py::test_get_source_unchanged_without_crossfade -x` |
| 12 | `TruncatingSource` exhausts at `max_frames`, delegates `is_opus()`, cleans inner | D-14 | unit | `pytest tests/test_audio.py::test_truncating_source -x` |
| 13 | `CrossfadeSource.cleanup()` cleans **both** children, head via `finally` | **CR-3** | unit | `pytest tests/test_audio.py::test_crossfade_source_cleans_both -x` |
| 14 | Empty tail (short file / bad `-ss`) degrades to fade-in, never raises | D-10b | unit | `pytest tests/test_audio.py::test_crossfade_tolerates_empty_tail -x` |
| 15 | `/crossfade on\|off` copy lowercase, ≤1 emoji | CR-7/8 | unit | `pytest tests/test_responses.py::test_crossfade_copy_style -x` |
| 16 | **Suppression flag set ONLY on a fade cut** — never natural EOF, never pre-cut | **D-17.3** | unit | `pytest tests/test_audio.py::test_suppress_flag_only_on_fade_cut -x` |
| 17 | **discord.py drift guard**: `AudioPlayer.send_silence` exists **and** `_do_run` calls it | **D-17.4** | unit | `pytest tests/test_audio.py::test_send_silence_patch_target_exists -x` |
| 18 | **Patch install degrades gracefully** (no boot crash) if target is gone | **D-17.4** | unit | `pytest tests/test_audio.py::test_patch_install_fails_soft -x` |

Rows **16–18 are non-negotiable** — they are D-17's mandated guard rails, not discretionary polish.
Row 17 is the tripwire that turns a discord.py upgrade into a red build instead of a silent
regression; row 18 is what keeps that same upgrade from crashing the bot at import.

`_play_track` / `_on_track_end` glue stays **untested-by-design** per `.planning/codebase/TESTING.md`
(structural review + clean boot). Its safety evidence is the spike's D-11 attack artifacts
(ffmpeg process counts, generation-counter values, stale-callback log lines) recorded in
`27-RESEARCH.md` §Evidence — **not** unit tests. That is by design, not a gap.

---

## Wave 0 Requirements

- [ ] `tests/test_crossfade_logic.py` — **new file**; covers DJ-03's eligibility ladder (the D-14 seam)
- [ ] `tests/test_audio.py` — **extend (exists)**: `TruncatingSource`, `CrossfadeSource` cleanup /
      empty-tail, byte-identical-when-off guard, and the D-17.3 suppression-flag guard (row 16)
- [ ] `tests/test_discord_patch.py` — **NEW FILE**: rows 17-18 (drift guard + positive control +
      fail-soft), per the `tests/test_invite_drift_guard.py` own-file precedent
- [ ] `tests/test_queue.py` — **extend (exists)**: D-12 `clear()` semantics
- [ ] `tests/test_queue_persistence.py` — **NEW FILE** (corrected: this file does NOT exist; the repo's only
      persistence guard lives in `tests/test_radio_logic.py::test_disarm_never_persisted_in_queue_persistence_payload`): toggle-not-persisted guard
- [ ] `tests/test_responses.py` — **extend (exists)**: copy style
- [ ] Framework install: **none** — pytest present; `audioop` stdlib; **no new dependency** (D-02)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| **SC-2 — the tail audibly blends into the head** | DJ-03 | **An agent cannot hear (D-10).** The user's ear IS the bar. | Play the D-08 render; confirm the blend sounds like a blend, not a phase artifact or a stutter. Already satisfied at the D-04 gate for the spike's render; **re-listen to the shipped implementation's render before `/gsd:verify-work`**. |
| Live-Discord confirmation (Opus encode + jitter buffer) | DJ-03 | Needs the parked always-on host (D-09). | Park in `27-HUMAN-UAT.md`; joins the 33 existing parked items. The render satisfies SC-2 and closes the phase (D-09). |
| **Discord's decoder tolerates the suppressed end-of-transmission marker** | DJ-03 | **Reasoned low-risk, NOT measured (D-17.5)** — unmeasurable while the host is parked. | Park in `27-HUMAN-UAT.md`. Risk bounded by D-08b (off by default → blast radius is opt-in rooms only, one toggle flip to recover). Listen for choppiness/decoder artifacts at fade boundaries once live. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] Behavior-Map rows **16–18** (D-17 guard rails) each map to a real task
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-17 (planner — all 18 Behavior Map rows mapped to tasks across 5 plans / 3 waves)
