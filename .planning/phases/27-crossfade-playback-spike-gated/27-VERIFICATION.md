---
phase: 27-crossfade-playback-spike-gated
verified: 2026-07-17T00:00:00Z
status: human_needed
score: 3/3 must-haves verified (plus 5/5 plan-level artifact sets verified; 3 unresolved code-review warnings noted)
overrides_applied: 0
human_verification:
  - test: "Re-listen to the shipped crossfade render and judge whether the blend sounds smooth (SC-2, D-08/D-10 — an agent cannot hear)"
    expected: "Two songs overlap and swap over ~4s with no loudness dip and no phasing/underwater artifact; user decides plain-vs-suppressed variant is acceptable"
    why_human: "Audio quality judgment is explicitly out of scope for an agent per RESEARCH's own D-10 ruling — this is the SC-2 bar"
  - test: "Confirm in a real Discord voice channel that /skip mid-crossfade does not glitch, double-play, or leave the bot stuck"
    expected: "Skip cuts the fade cleanly, next track starts normally, no audible artifacts beyond what the spike's harness already proved structurally"
    why_human: "No always-on host; only a fake-voice-client harness has been exercised, not the real Discord gateway/RTP path"
  - test: "D-17.5 — confirm Discord's real audio decoder tolerates the suppressed send_silence end-of-transmission marker without artifacting (if GO/suppressed variant is kept)"
    expected: "No audible glitch or decoder confusion at the fade boundary when the 100ms silence marker is withheld"
    why_human: "Reasoned low-risk in RESEARCH (unbroken RTP sequence, no missing packets) but explicitly unmeasurable offline — parked to 27-HUMAN-UAT.md by RESEARCH itself"
  - test: "Confirm /crossfade on|off in a live guild toggles behavior audibly as expected and the copy pool tone lands correctly"
    expected: "Toggle takes effect on the next transition; reply copy reads naturally, no mention pings"
    why_human: "Live Discord interaction / tone-feel check, not verifiable by static analysis"
---

# Phase 27: Crossfade Playback (Spike-Gated) Verification Report

**Phase Goal:** Track transitions blend smoothly into each other, contingent on a plan-time spike
proving the existing playback engine (generation counter, `/skip`, prefetch) supports it safely.
Spike VERDICT: GO / suppressed (D-17). The fade lives inside the incoming track's own AudioSource
so the per-track `play()` + generation counter are untouched (D-01 not tripped); ships with two
mandatory rails (fail-soft `send_silence` patch install + CI drift guard).

**Verified:** 2026-07-17
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (the three given Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A plan-time spike produced an explicit go/no-go verdict before implementation | ✓ VERIFIED | `27-RESEARCH.md` — `## VERDICT: GO` (line 10), Round 2 amendment upgrading to "GO/suppressed" with real `AudioPlayer`/real `MusicQueue`/real FFmpeg-subprocess attack harness (3 attacks, packet-level RTP forensics), git protocol proof that `spike/crossfade` was created, attacked twice, and deleted with zero tracked source files touched (`git diff --stat -- . ':!.planning' ':!.claude'` empty). |
| 2 | GO path: outgoing tail blends into incoming head; `/skip` mid-crossfade does not double-play, orphan FFmpeg, or desync the generation counter | ✓ VERIFIED (code-level) | `services/audio.py::TruncatingSource`/`CrossfadeSource` implement the exact "fade lives inside the incoming track's source" shape RESEARCH validated (equal-power `audioop` mix, tail dropped at fade end, `cleanup()` owns both children — tail in `try`, head in `finally`). `cogs/music.py::_play_track`/`_on_track_end` wire it at the two RESEARCH-specified integration points. Structural tripwire tests (`tests/test_music_wiring.py::TestCrossfadeEngineWiring`/`TestCrossfadeHandoffWiring`/`TestCrossfadeSkipChokePointUntouched`) assert the generation block order, log-only hard-cut, handoff-before-advance, and zero crossfade references in `_try_skip`/`_do_skip`. Full suite: **1233 passed, 129 skipped, 0 failed** (re-run live, matches SUMMARY claim exactly). The actual audible smoothness is human-only (see Human Verification). |
| 3 | The D-01 engine block and Phase 26's `_do_skip` vote-gate choke point are untouched | ✓ VERIFIED | `grep` + direct reading of `cogs/music.py::_try_skip`/`_do_skip` shows zero `crossfade`/`_xf_` references. `_play_track`'s generation block (`queue._play_generation += 1` → `current_gen` capture → `after_callback` → `queue._play_generation == current_gen` guard → `stop()`/`play()`) is unmodified — the crossfade wrap only replaces the local `source` variable *before* this block, so `voice_client.play()` still receives exactly one `AudioSource`. Locked by `test_play_track_generation_block_intact`, `test_try_skip_has_no_crossfade_references`, `test_do_skip_has_no_crossfade_references` — all passing. |

**Score:** 3/3 given success criteria verified at the code level.

### Required Artifacts (per-plan must_haves)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `logic/crossfade.py` | `FadeVerdict` enum + `decide_crossfade()` + `cut_frame()`, pure/keyword-only, zero `discord` imports | ✓ VERIFIED | Matches RESEARCH §3 signature verbatim; 8-member enum, 7-rung cheapest-gate-first ladder in the exact documented order, `cut_frame` floors at 0. |
| `config.py` knobs | `CROSSFADE_SECONDS=4`, `CROSSFADE_MIN_TRACK_SECONDS=20` | ✓ VERIFIED | Present at `config.py:338,342` with decision-ID comments. |
| `tests/test_crossfade_logic.py` | Mock-free coverage of all 8 ladder rungs | ✓ VERIFIED | 24 tests, `grep -c "Mock\|patch("` == 0 confirmed by test content inspection; all pass. |
| `models/queue.py` state split | `crossfade_enabled` survives `clear()`; `_xf_pending`/`_xf_truncator` nulled by it | ✓ VERIFIED | `crossfade_enabled` at :86 (absent from `clear()`); `_xf_pending`/`_xf_truncator` at :137-138, nulled at :295-296. |
| `personality/responses.py` | `CROSSFADE_ON`/`CROSSFADE_OFF` zero-arg pools | ✓ VERIFIED | Present at :244, :251; `test_crossfade_copy_style` passes. |
| `tests/test_queue_persistence.py` | Guard that the toggle is unpersisted | ✓ VERIFIED | New file; exact key-set-equality behavioral test + structural source scan, both pass. |
| `services/audio.py::TruncatingSource`/`CrossfadeSource` | Two-decoder window inside one `AudioSource`; byte-identical `get_source()` when `crossfade_from` omitted | ✓ VERIFIED | Both classes present, `cleanup()` tail-in-try/head-in-finally confirmed by reading; `get_source`'s opus-passthrough comment/line survives unmodified; `crossfade_from` branch only engages when both cache files exist, else defensive fall-through. |
| `utils/discord_patch.py` | `install_send_silence_suppression()` — fail-soft, idempotent, duck-typed | ✓ VERIFIED | Reads exactly as RESEARCH Round 2 Task 3 specified; wrapped in `try/except Exception`; `send_silence_patch_target_present()` shared by install and drift guard, checks both attribute-exists AND `_do_run` call-site. |
| `tests/test_discord_patch.py` | Drift guard with proven-non-vacuous positive control (both drift shapes) | ✓ VERIFIED | `test_drift_guard_actually_detects_a_mismatch` covers both "attribute gone" and "attribute present but uncalled" shapes, driven through the real shared helper; negative control present; fail-soft install test uses `monkeypatch`; idempotency test present. All pass. |
| `bot.py` | Single install site in `setup_hook`; fade-aware LFU protected set | ✓ VERIFIED (install site) / ⚠️ **PARTIAL** (LFU protection) | `grep -c "install_send_silence_suppression" bot.py` == 1, inside `setup_hook`, before any voice playback. The `cache_cleanup` protected-set addition exists exactly as coded, **but code review (WR-01) found it reads state (`_xf_truncator`/`_xf_pending`) that is already cleared by the time `CrossfadeSource` is actually mid-read in the common (non-chained-fade) case** — the protection window doesn't cover the actual risk window it claims to. Documented by the reviewer as a real correctness gap but a **benign failure mode** (Windows: `unlink` on an in-use file fails and is caught; POSIX: an open fd keeps the file readable after `unlink`), not a crash or playback-audible defect. Unresolved — no `27-REVIEW-FIX.md` exists. |
| `cogs/music.py::/crossfade` command | `/autolyrics` shape, no defer, no cooldown, `AllowedMentions.none()` | ✓ VERIFIED | Confirmed by direct reading at `cogs/music.py:2057-2079`; matches plan exactly. |
| `tests/test_music_wiring.py` | Structural guards: D-01 block intact, `_do_skip` choke point crossfade-free | ✓ VERIFIED | `TestCrossfadeEngineWiring`, `TestCrossfadeHandoffWiring`, `TestCrossfadeSkipChokePointUntouched` all present and passing. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `cogs/music.py::_play_track` | `logic.crossfade.decide_crossfade` | consulted after `get_source`, before `_play_generation` increment | ✓ WIRED | Confirmed by reading and by `test_crossfade_consulted_before_generation_increment` (passes). |
| `cogs/music.py::_on_track_end` | `queue._xf_pending` | set from `truncator.position_seconds` when `cut_short`, before `decide_on_track_end` dispatch | ✓ WIRED | Confirmed by reading and by `test_handoff_precedes_advance` / `test_handoff_reads_position_seconds_not_duration` (both pass). |
| `cogs/music.py::_play_track` | `audio.get_source(crossfade_from=...)` | pending handoff consumed and cleared at source-acquisition time | ✓ WIRED | Confirmed by reading and by `test_xf_pending_cleared_where_consumed` (passes). |
| `utils/discord_patch.py::_patched_send_silence` | `TruncatingSource._suppress_end_silence` | duck-typed `getattr(self.source, ...)`, never an import of `services.audio` | ✓ WIRED | `grep -c "import services"` and `grep -c "isinstance"` both 0 in `utils/discord_patch.py`, confirmed by reading. |

### Behavioral Spot-Checks / Test Execution

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Crossfade-specific test files | `pytest tests/test_crossfade_logic.py tests/test_audio.py tests/test_discord_patch.py tests/test_music_wiring.py tests/test_queue.py tests/test_queue_persistence.py tests/test_responses.py -q` | 175 passed | ✓ PASS |
| Full suite (re-run live by verifier, not trusted from SUMMARY) | `pytest -q` | 1233 passed, 129 skipped, 0 failed (424s) | ✓ PASS — matches 27-05-SUMMARY's claimed baseline exactly |
| Lint | `ruff check .` | All checks passed | ✓ PASS |
| Mandated VALIDATION node-ids (rows 12,13,14,16,17,18 — "do not rename") | `pytest tests/test_audio.py::test_truncating_source tests/test_audio.py::test_suppress_flag_only_on_fade_cut tests/test_audio.py::test_crossfade_source_cleans_both tests/test_audio.py::test_crossfade_tolerates_empty_tail tests/test_audio.py::test_get_source_unchanged_without_crossfade tests/test_discord_patch.py::test_send_silence_patch_target_exists tests/test_discord_patch.py::test_patch_install_fails_soft -v` | All 7 pass as bare module-level node IDs | ✓ PASS |
| Mandated node-ids for rows 1-8 (test_crossfade_logic.py) | `pytest tests/test_crossfade_logic.py::test_fade_when_eligible` etc. | **Not found as bare node IDs** — tests exist but are nested inside one class per Behavior Map row (e.g. `TestFadeWhenEligible::test_fade_when_eligible`) | ℹ️ INFO — cosmetic drift from RESEARCH's suggested Validation Architecture table, not a "do not rename" mandate for this file (unlike rows 12/13/14/16/17/18). All 8 behaviors are still locked and pass; no functional gap. |

### Structural / Untested-by-Design Glue

Per `.planning/codebase/TESTING.md` and the phase's own `<verification>` blocks, `_play_track` /
`_on_track_end` glue is untested-by-design; its safety evidence is RESEARCH's spike attack
artifacts (ffmpeg process counts, stale-callback suppression log lines, monotonic generation
counters), not mock-heavy unit tests. This was honored — no new mocks were added over `_play_track`;
instead `tests/test_music_wiring.py` encodes structural review as source-introspection tests. This
is correct per the phase's design and is **not** treated as a gap.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|--------------|-------------|--------------|--------|----------|
| DJ-03 | 27-01 through 27-05 (all 5 plans) | Crossfade between tracks, spike-gated on engine safety | ✓ SATISFIED (code-level) | All 5 plans' artifacts verified present, wired, and tested; full suite green. **`.planning/REQUIREMENTS.md` traceability table still shows DJ-03 as "Pending (spike-gated)" (line 78) — this is stale documentation, not a code gap.** Recommend updating at phase close. |

No orphaned requirements — DJ-03 is the only requirement ID declared across all 5 plan frontmatters, and it matches the phase's sole roadmap requirement.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `bot.py` | 1060-1076 | WR-01 (code review): LFU-eviction protection for the outgoing track during a fade reads state that's already cleared before the real risk window; the `current_index > 0` guard also drops protection on a loop-QUEUE wraparound | ⚠️ Warning | Documented benign failure mode (Windows: caught `OSError`; POSIX: open-fd keeps file readable) — not a crash or audible defect, but the code's own comment overstates what it actually protects. Unresolved (no `27-REVIEW-FIX.md`). |
| `cogs/music.py` | 734-745, 767-770, 780-783 | WR-02 (code review): `queue._xf_truncator` is nulled only inside `_on_track_end`, not on the hard-cut branch or `_play_track`'s early-return/exception paths reached via `/seek`, `/jump`, `/previous`, `/replay`, `/filter` direct re-entry | ⚠️ Warning | Reviewer's own analysis shows this is currently harmless (a stale truncator's `cut_short` can only flip from its own `read()`, which a stopped/abandoned truncator never gets called again) but the invariant "this field is always live-or-None" doesn't hold unconditionally as documented. Unresolved. |
| `requirements.txt` / `utils/discord_patch.py` | 1 / 4-5 | WR-03 (code review): `discord.py>=2.3.0` is an open lower bound; the patch module's docstring claims "the pinned 2.7.1" | ⚠️ Warning | A future `pip install -U` could silently resolve a discord.py version where the patch target has moved — the runtime drift guard (`tests/test_discord_patch.py`) would catch it in CI, but the docstring's "pinned" claim is factually false against `requirements.txt`. Confirmed live: `pip show discord.py` → 2.7.1 installed, but not pinned in the manifest. Unresolved. |
| `.planning/REQUIREMENTS.md` | 78 | DJ-03 traceability shows "Pending (spike-gated)" despite code-complete status | ℹ️ Info | Documentation drift, not a code gap. |

No `TBD`/`FIXME`/`XXX` unreferenced debt markers found in any file this phase touched.

### Human Verification Required

### 1. Re-listen to the shipped crossfade render (SC-2)

**Test:** Listen to the render(s) referenced in `27-RESEARCH.md` (with-silence / no-silence
variants) or a freshly re-rendered equivalent from the shipped implementation.
**Expected:** Two songs overlap and swap over ~4s with no dip in loudness and no
underwater/phasing artifact; the 100ms boundary (if the plain variant is kept) reads as
acceptable or not.
**Why human:** RESEARCH is explicit — "I cannot hear this file — this is the SC-2 verdict and it
is yours" (D-10). This is the one item the plan itself gates phase close on ("Before
`/gsd-verify-work`: the user re-listens to the shipped implementation's render").

### 2. Live-Discord `/skip` mid-crossfade confirmation

**Test:** In a real guild voice channel, start a crossfade-eligible transition and fire `/skip`
partway through the fade.
**Expected:** Clean cut, no glitch/double-audio, next track starts normally — matching what the
spike's fake-voice-client harness already proved structurally.
**Why human:** No always-on host currently exists; only the spike's `FakeVoiceClient` harness
(real discord.py `AudioPlayer` thread, fake UDP socket) has exercised this path, never the real
Discord gateway/RTP transport.

### 3. D-17.5 — Discord decoder tolerance of the suppressed `send_silence` marker

**Test:** With the suppression patch installed (default per D-17/GO-suppressed), confirm no
audible artifact at a fade boundary in a real Discord client.
**Expected:** No glitch, pop, or decoder confusion at the point where the 100ms marker would
normally have appeared.
**Why human:** RESEARCH reasons this is low-risk (unbroken RTP timestamp/sequence, no missing
packets, PLC triggers only on missing packets) but states plainly it is "unverifiable offline" and
routes it to `27-HUMAN-UAT.md`.

### 4. `/crossfade on|off` live feel check

**Test:** Toggle `/crossfade` on/off in a live guild and observe the reply copy and subsequent
transition behavior.
**Expected:** Toggle takes effect on the next transition; copy pool tone matches the dry/sarcastic
register; no mention pings.
**Why human:** Live Discord interaction and tone-feel judgment, not statically verifiable. (Code-level
wiring — `AllowedMentions.none()`, `pick_random` sourcing, no inline literals — is already verified.)

> Note: `27-HUMAN-UAT.md` does not yet exist in the phase directory. Per this phase's own
> `27-05-SUMMARY.md` and `27-RESEARCH.md`, these items were always intended to be parked there —
> creating/populating it is the standard end-of-phase `human_needed` sink, not a gap introduced by
> this verification.

### Gaps Summary

**No BLOCKER-level gaps.** All three of the phase's explicitly-scoped success criteria (spike
ran with a GO verdict; the GO path is implemented with skip-safety preserved; the D-01 engine
block and Phase 26 choke point are untouched) are verified true in the codebase — not merely
claimed in SUMMARY.md. The full test suite (1233 passed, 0 failed) was re-run live by this
verifier, not trusted from the SUMMARY, and matches exactly. `ruff check .` is clean. Every
artifact and key link named in all 5 plans' frontmatter `must_haves` was independently located and
read in the actual source, not inferred from documentation.

**Three unresolved code-review warnings (WR-01/02/03)** exist with no `27-REVIEW-FIX.md` — real,
specific correctness gaps in the LFU-protection accounting and `_xf_truncator` invariant, both
explicitly assessed by the reviewer as benign-failure-mode (never a crash, never an audible
defect) rather than goal-blocking. WR-03 is a docs/pin mismatch. These are surfaced as WARNINGs
for a human decision — either fix them in a follow-up or explicitly accept them via an override —
not as reasons to fail the phase, since none of them threaten the three given success criteria.

**Audible/live-Discord items are correctly out of scope for code-level PASS/FAIL** and are routed
to Human Verification per this phase's own design (D-09, D-10, D-17.5) — this is why overall
status is `human_needed` rather than `passed`, even though every code-level truth verified clean.

---

*Verified: 2026-07-17*
*Verifier: Claude (gsd-verifier)*
