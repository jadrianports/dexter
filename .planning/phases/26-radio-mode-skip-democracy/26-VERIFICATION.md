---
phase: 26-radio-mode-skip-democracy
verified: 2026-07-16T18:17:21Z
status: human_needed
score: 11/11 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Radio cadence feel"
    expected: "Queue refills smoothly with no audible gap/dead air across 4+ tracks"
    why_human: "Requires live voice playback + real YouTube resolution timing"
  - test: "Multi-listener vote tally narration"
    expected: "With 3 real listeners, Dexter narrates the running tally on vote 1, skips on vote 2"
    why_human: "Requires 2+ real humans in a live voice channel; tally copy is a personality/feel judgment"
  - test: "Solo /skip live regression"
    expected: "Alone in voice, /skip skips immediately with no tally message"
    why_human: "Live regression check of the single-listener path"
  - test: "/radio stop leaves no leftover auto-refill"
    expected: "After /radio stop, queue drains to empty with no refill; normal auto-queue/idle behavior resumes"
    why_human: "Requires observing the queue over real time after disarm"
  - test: "Clean-boot command registration"
    expected: "/radio start|stop and /skip register and respond in a live Discord client"
    why_human: "Command registration is Discord-gateway-side, not observable in unit tests"
---

# Phase 26: Radio Mode & Skip Democracy Verification Report

**Phase Goal:** Dexter can DJ a room indefinitely off the taste brain, and skipping a track stops being one user's unilateral call.
**Verified:** 2026-07-16T18:17:21Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A user can start radio/endless mode seeded from a track or artist, and the queue keeps refilling off the taste brain — no manual `/play` needed — until stopped (SC-1) | VERIFIED | `cogs/music.py::radio_start` (`:2361-2426`) arms via `MusicQueue.arm_radio`, kicks the first refill through `should_refill_radio`; `_on_track_end` (`:901-915`) consults `should_refill_radio` on every `PLAY` branch and `try_auto_queue(guild, radio=True)` (`cogs/ai.py:274`) lifts the round cap, anchors the seed, and rejects session repeats via `is_already_played` after YouTube resolution (`cogs/ai.py:509`). Full test coverage in `tests/test_radio_logic.py`, `tests/test_autoqueue_wiring.py`, `tests/test_music_wiring.py::TestRadioLookaheadWiring/TestRadioLifecycleWiring` — all green. |
| 2 | Stopping radio mode returns the bot to normal manual queueing with no leftover auto-refill behavior (SC-2) | VERIFIED | `radio_stop` (`cogs/music.py:2429-2453`) calls `queue.disarm_radio()`; `should_refill_radio`'s gate 1 (`not armed -> False`) makes a disarmed radio structurally unable to refill. `MusicQueue.clear()` (`:247-273`) also calls `disarm_radio()`, covering `/stop`, the stop button's `_do_stop`, `bot.py::idle_check`, and reconnect-failure teardown for free — all four independently locked by `tests/test_music_wiring.py::TestRadioDisarmsAtEveryTeardown` (behavioural: `arm_radio()`+`clear()` -> `radio_armed is False`; structural: all four sites still call `clear()`). |
| 3 | With more than one listener in voice, `/skip` requires reaching a configurable vote threshold before the track actually skips, and Dexter narrates the running tally on each vote (SC-3) | VERIFIED | `logic/skip_vote.py::decide_skip`/`required_votes` implement `floor(n*ratio)+1` clamped to `n` (D-09c table 1→1,2→2,3→2,4→3, config-honouring, unit-locked). `cogs/music.py::_try_skip` (`:1043-1120`) is the single choke point reached by `/skip` (`:1808`), the `⏭ Skip` button (`:384`), and `/seek`'s past-end branch (`:2094`) — all three verified by direct code read and `tests/test_music_wiring.py::TestSkipChokePointUnification`/`TestVerdictDispatchedNotReimplemented`. The tally posts via `SKIP_VOTE_TALLY.format(votes=, required=)` (code-interpolated, D-18) on `VOTE_RECORDED`/`ALREADY_VOTED`. |
| 4 | A solo listener's `/skip` still skips instantly — vote-gating doesn't regress the single-listener case (SC-4) | VERIFIED | `decide_skip` gate 2: `len(listener_ids) <= 1 -> SKIP_NOW`, locked by `tests/test_skip_vote_logic.py -k solo`. |

### Plan-Level Must-Haves (26-01 .. 26-05 frontmatter, superset of roadmap SC)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 5 | A disarmed radio never refills (SC-2 arithmetic lock) | VERIFIED | `should_refill_radio` gate 1; `tests/test_radio_logic.py -k disarm` |
| 6 | Radio and loop mode are mutually exclusive; each says so (D-11) | VERIFIED | `MusicQueue.set_loop_mode` (`:312-331`) is the single choke point both `/loop` (`:1930`) and `_do_loop_cycle` (`:1189`) route through; `RADIO_LOOP_CONFLICT` copy appended on disarm. `tests/test_music_wiring.py::TestLoopRadioMutualExclusionWiring` — no direct `queue.loop_mode =` assignment remains outside `models/queue.py`. |
| 7 | A track already played this radio session is rejected after YouTube resolution, not merely discouraged (D-03) | VERIFIED | `cogs/ai.py:509` — `is_already_played(video_id=data["video_id"], played_ids=frozenset(queue.radio_played))` runs after `async_extract`, independent of the (capped, advisory) prompt hint. |
| 8 | The vote denominator is read fresh from voice on every single vote, never memoized (D-17/Pitfall 4) | VERIFIED | `_try_skip` computes `listener_ids` synchronously from `voice_client.channel.members` on every call, no cached attribute exists (`tests/test_music_wiring.py::TestFreshListenerRead`). |
| 9 | A vote-skipped track records via the existing `mark_song_skipped` and nothing more (D-20) | VERIFIED | `_do_skip` unmodified in mechanics (only reordered pre-await, see WR-02 below); no new memory kind/`distill_and_remember` call in the skip path (`TestNoNewMemoryKindInSkipPath`). |
| 10 | The `/skip` slash command and the Skip button both go through ONE vote gate — no unvoted bypass (D-15, closing RESEARCH Pitfall 1) | VERIFIED | `/skip`'s previously-duplicated inline body is gone; `grep -c "_do_skip(" cogs/music.py` shows exactly one call site (inside `_try_skip`). `/seek`'s past-end branch — an undocumented third bypass surface discovered during execution — was also closed. |
| 11 | Only the requester bypasses the vote; no admin/owner override exists (D-13a/D-13b/T-26-05) | VERIFIED | `is_requester = voter_id == current.requested_by`, no `bot.user.id` special-case, no `manage_guild`/`is_owner` branch (`TestNoBypassBackdoor`). |

**Score:** 11/11 must-haves verified (0 failed, 0 overridden)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `logic/radio.py` | Pure refill-gate seam (`should_refill_radio`, `is_already_played`, `has_room_for_refill`) | VERIFIED | 154 lines, zero discord/asyncio/random/datetime imports (`grep` confirms 0), all keyword-only. |
| `logic/skip_vote.py` | Pure verdict seam (`SkipVerdict`, `required_votes`, `decide_skip`) | VERIFIED | 199 lines, zero disallowed imports, arithmetic matches D-09c table exactly, `len(new_votes)` counting (no `& listener_ids` present anywhere). |
| `models/queue.py` | Radio armed-state + skip-vote state, `clear()` disarms | VERIFIED | `radio_armed`/`radio_seed`/`radio_played`, `arm_radio`/`disarm_radio`/`set_loop_mode`, `_skip_votes`/`_skip_votes_key`, `skip_votes_for_current`/`record_skip_votes` all present and match spec; `clear()` calls `disarm_radio()`. |
| `personality/prompts.py` | `seed=`/`already_played=` kwargs, byte-identical when unset | VERIFIED | Confirmed via `tests/test_prompts.py` byte-identical regression test, passing. |
| `personality/responses.py` | `SKIP_VOTE_TALLY`/`RADIO_START`/`RADIO_STOP`/`RADIO_LOOP_CONFLICT`/`RADIO_NOT_ARMED` pools | VERIFIED | All 5 pools present, real in-voice lowercase copy (not placeholder text), format-smoke-tested. |
| `cogs/ai.py` | `try_auto_queue(guild, *, radio: bool = False)` radio branch | VERIFIED | Cap lift, hoisted resolution, seed/already-played locals, D-03 hard filter, D-05 suppression, `priority=2` preserved — all present, matching plan spec line-for-line. |
| `cogs/music.py` | `_try_skip` choke point, `/radio start|stop` group, D-10/D-11 wiring | VERIFIED | All present, all three skip entry points route through `_try_skip`, `/radio` group follows `cogs/library.py`'s shape. |
| `tests/test_radio_logic.py`, `tests/test_skip_vote_logic.py`, `tests/test_music_wiring.py` | Mock-free locks for DJ-01/DJ-02 | VERIFIED | All pass in isolation and as part of the full suite. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `logic/radio.py` | `config.RADIO_LOOKAHEAD_DEPTH` | keyword-only default | VERIFIED | Confirmed in source. |
| `models/queue.py::clear` | `disarm_radio` | explicit teardown reset | VERIFIED | `self.disarm_radio()` present in `clear()`. |
| `cogs/ai.py::try_auto_queue` | `logic.radio.is_already_played` | independent hard post-filter | VERIFIED | `cogs/ai.py:509`. |
| `cogs/ai.py::try_auto_queue` | `build_recommendation_prompt(seed=...)` | D-02 seed anchor | VERIFIED | `cogs/ai.py:426`. |
| `cogs/music.py::skip` | `_try_skip` | slash command routes through shared gate | VERIFIED | `cogs/music.py:1833`. |
| `cogs/music.py::NowPlayingView.skip_button` | `_try_skip` | button routes through same shared gate | VERIFIED | `cogs/music.py:398`. |
| `cogs/music.py::_try_skip` | `logic.skip_vote.decide_skip` | verdict dispatch, never re-derived | VERIFIED | `cogs/music.py:1089`. |
| `cogs/music.py::_on_track_end` | `logic.radio.should_refill_radio` | lookahead gate alongside `TrackEndAction` dispatch | VERIFIED | `cogs/music.py:910`. |
| `cogs/music.py::radio_start` | `MusicQueue.arm_radio` | arms + resets played-set | VERIFIED | `cogs/music.py:2394`. |
| `cogs/music.py::loop` | `MusicQueue.set_loop_mode` | D-11 mutual exclusion | VERIFIED | `cogs/music.py:1930`; also `_do_loop_cycle` at `:1189`. |

### Data-Flow Trace (Level 4)

Not applicable in the standard sense (this phase has no rendered-UI data source) — the closest
analogue is the vote tally's numeric source, verified directly: `_try_skip` computes `required =
required_votes(listener_count=len(listener_ids))` from a **live** `voice_client.channel.members`
read on every call (never a cached/stale snapshot — `TestFreshListenerRead`), and `votes =
len(new_votes)` from the just-updated vote set — both flow from real state, not hardcoded/static
values.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| D-09c majority table honours the config ratio | `required_votes(listener_count=1..4)` → 1,2,2,3; `majority_ratio=1.0, n=3` → 3 (clamped) | Confirmed by direct source read + passing unit tests | PASS |
| `should_refill_radio` boundary (exactly-at-depth refills, one-above does not) | `should_refill_radio(armed=True, humans_present=True, upcoming_count=2)`→True; `upcoming_count=3`→False | Confirmed by direct source read + passing unit tests | PASS |
| Full phase-relevant test subset | `pytest tests/test_radio_logic.py tests/test_skip_vote_logic.py tests/test_music_wiring.py tests/test_autoqueue_wiring.py tests/test_responses.py tests/test_prompts.py tests/test_queue.py -q` | 233 passed, 0 failed | PASS |
| Full repository suite | `pytest -q` | 1175 passed / 129 skipped / 0 failed (424.85s) | PASS |
| Lint | `ruff check .` | All checks passed | PASS |
| Format | `ruff format --check .` | 3 pre-existing Phase-25 offenders only (`services/memory.py`, `tests/test_database_phase25.py`, `tests/test_vision_events.py`) — logged in `deferred-items.md`, confirmed last touched by Phase 25 commits, zero new offenders from Phase 26 | PASS |
| `logic/playback.py` / `bot.py` byte-identical claim | `git log --oneline -1 -- logic/playback.py bot.py` | Last touched at `8353d3f` (Phase 18) / `0795509` (Phase 24) respectively — no Phase 26 commit touches either file | PASS |

### Probe Execution

Not applicable — this phase has no `scripts/*/tests/probe-*.sh` and none are referenced in the PLAN/SUMMARY files. SKIPPED (no runnable entry points beyond the pytest suite already exercised above).

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|--------------|----------------|--------------|--------|----------|
| DJ-01 | 26-01, 26-03, 26-05 | Radio / endless mode — seed a track/artist, queue refills indefinitely off the taste brain until stopped | SATISFIED | Code-verified per truths 1, 2, 5, 6, 7 above. REQUIREMENTS.md marks this "Complete" — the orchestrator's noted over-marking concern (DJ-01 marked complete after only 26-01 landed) is now moot: the code at HEAD genuinely satisfies DJ-01 end-to-end (engine in 26-03, surface in 26-05, both independently verified in this pass). |
| DJ-02 | 26-02, 26-04 | Skip-voting / queue democracy — configurable vote threshold, requester bypass, tally narration | SATISFIED | Code-verified per truths 3, 4, 8, 9, 10, 11 above, including the post-review CR-01 fix (voice-membership gating on `/skip`/`/seek`) that was necessary for DJ-02's core premise to actually hold. |

No orphaned requirements — `.planning/REQUIREMENTS.md` maps only DJ-01 and DJ-02 to Phase 26, and both appear in the plans' `requirements:` frontmatter.

### Anti-Patterns Found

None. Scanned `logic/radio.py`, `logic/skip_vote.py`, `models/queue.py`, `cogs/music.py`,
`cogs/ai.py`, `personality/prompts.py`, `personality/responses.py`, `config.py` for
`TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER` and placeholder-language patterns — zero matches. Response
pool copy is genuine in-voice content, not stub text. No empty-implementation patterns
(`return None`/`return {}`/`=> {}`) found in the phase's core logic paths.

### Code Review Cycle (informational — already resolved)

A code review (`26-REVIEW.md`) found 1 Critical (CR-01: `/skip`/`/seek` counted votes from
non-listeners, defeating DJ-02's core premise) + 4 Warnings (WR-01 stale auto-queue counters on
mid-radio `/loop` disarm; WR-02 a narrow double-skip race; WR-03 `/skip`/`/seek` inconsistently
blocked paused tracks; WR-04 unbounded seed length) + 1 deferred Info (IN-01: `/radio start` does
not gate on the invoker's own voice presence, lower severity, not a vote-rigging hole). All 5
in-scope findings were fixed and independently re-verified in this pass by direct source read
(commits `2264173`, `a352263`, `caab5de`, `7b628d5`, `9a2357d`) — CR-01 in particular was
essential: without it, `/skip` and `/seek`'s past-end branch could be vote-rigged by any guild
member not actually present in voice, which would have made SC-3 ("skip democracy") false as
shipped. IN-01 remains open by design (out of scope per the fix pass) — it is a permission-model
inconsistency (any guild member, not necessarily in voice, can arm radio), not a vote-tampering
hole, and does not affect any roadmap Success Criterion or plan must-have.

### Human Verification Required

Per this project's long-standing precedent (Phases 03–25: the 24/7 live deploy is parked behind a
residential-host requirement), the following behaviors cannot be verified without a live Discord
session and are deferred to `26-HUMAN-UAT.md` at phase close. These are acknowledged-deferred, not
code gaps — every one of them is backed by passing structural/unit tests proving the underlying
logic is correct; what remains is the live-runtime *feel* and Discord-gateway command registration.

### 1. Radio cadence feel

**Test:** Join voice, `/radio start` with a seed, let 4+ tracks play through unattended.
**Expected:** No audible gap or dead air between tracks; no manual `/play` needed.
**Why human:** Requires live voice playback + real YouTube resolution timing; the prefetch/refill interaction is not observable in unit tests.

### 2. Multi-listener vote tally narration

**Test:** With 3 real listeners in voice, have 2 issue `/skip`.
**Expected:** Dexter narrates the running tally on the 1st vote, the track skips on the 2nd.
**Why human:** Requires 2+ real humans in a live voice channel; tally copy quality is a personality/feel judgment, not a structural assertion.

### 3. Solo `/skip` live regression

**Test:** Alone in voice, run `/skip`.
**Expected:** Skips immediately, no tally message.
**Why human:** Live regression check of the single-listener path end-to-end through the real Discord client.

### 4. `/radio stop` leaves no leftover auto-refill

**Test:** `/radio stop`, let the queue drain to empty.
**Expected:** The bot does NOT refill; normal auto-queue/idle behavior resumes.
**Why human:** Requires observing the queue over real elapsed time after disarm.

### 5. Clean-boot command registration

**Test:** `docker compose up`, confirm `/radio start|stop` and `/skip` appear and respond.
**Expected:** Both command surfaces register correctly with Discord's gateway.
**Why human:** Command registration is Discord-gateway-side and cannot be exercised by the unit-test suite.

### Gaps Summary

No code-level gaps. All 11 must-haves (4 roadmap Success Criteria + 7 plan-level truths spanning
DJ-01/DJ-02) are VERIFIED against the actual codebase at HEAD, not SUMMARY.md claims — every
plan's stated artifact/key-link was independently confirmed by direct source reads (not just
grep-for-existence), the full 1175-test suite is green, ruff is clean, and the pre-execution
review's 1 Critical + 4 Warnings are all independently confirmed fixed by re-reading the resulting
code (not by trusting `26-REVIEW-FIX.md`'s narrative). The orchestrator's flagged
over-marking concern (DJ-01 marked "Complete" in REQUIREMENTS.md after only the 26-01
pure-logic-and-state plan landed) was investigated and found to be resolved by execution's end —
26-03 (engine) and 26-05 (surface) both landed and are independently verified here, so the
checkbox is not a false positive at the current HEAD, even though it was marked prematurely
mid-phase.

Status is `human_needed` rather than `passed` solely because 5 live-Discord/runtime checks remain
open per this project's established precedent — not because any code-level truth failed.

---

_Verified: 2026-07-16T18:17:21Z_
_Verifier: Claude (gsd-verifier)_
