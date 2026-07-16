---
phase: 26
slug: radio-mode-skip-democracy
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-16
---

# Phase 26 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `26-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (existing, `requirements.txt` / `requirements-dev.txt`) |
| **Config file** | none — implicit defaults (unchanged since Phase 1); ruff config lives in `pyproject.toml` |
| **Quick run command** | `pytest tests/test_radio_logic.py tests/test_skip_vote_logic.py -x` |
| **Full suite command** | `pytest` |
| **Estimated runtime** | ~2s quick (mock-free pure logic, no DB/network) · ~60-90s full suite (850+ tests) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_radio_logic.py tests/test_skip_vote_logic.py -x`
- **After every plan wave:** Run `pytest` (full suite)
- **Before `/gsd-verify-work`:** Full suite must be green + clean-boot smoke check confirming `/radio` and `/skip` command registration succeeds
- **Max feedback latency:** ~90 seconds (full suite)

---

## Per-Task Verification Map

> Finalized 2026-07-16 against `26-01`..`26-05-PLAN.md`. Every binding row in the
> requirement→test map below maps to a real task here.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 26-01 T1 | 26-01 | 1 | DJ-01 | T-26-02 | Refill gate refuses when disarmed or when no humans are in voice — no Gemini spend for an empty room | unit | `pytest tests/test_radio_logic.py -k should_refill -x` | ❌ W0 | ⬜ pending |
| 26-01 T1 | 26-01 | 1 | DJ-01 | T-26-09 | `has_room_for_refill` stops a refill fighting `MAX_QUEUE_SIZE_PER_GUILD` | unit | `pytest tests/test_radio_logic.py -k played_set -x` | ❌ W0 | ⬜ pending |
| 26-01 T2 | 26-01 | 1 | DJ-01 | T-26-07 | Played-set resets on `/radio start`, not only on stop — no cross-session inheritance | unit | `pytest tests/test_radio_logic.py -k disarm -x` | ❌ W0 | ⬜ pending |
| 26-01 T2 | 26-01 | 1 | DJ-01 | T-26-13 | `clear()` disarms radio — every teardown site is a disarm site (SC-2) | unit | `pytest tests/test_radio_logic.py -k loop_exclusion -x` | ❌ W0 | ⬜ pending |
| 26-01 T3 | 26-01 | 1 | DJ-01 | T-26-06 | Seed reaches prompt text only; omitted-when-unset keeps auto-queue byte-identical | unit | `pytest tests/test_prompts.py -x` | ✅ extend | ⬜ pending |
| 26-02 T1 | 26-02 | 2 | DJ-02 | T-26-01 | Vote is idempotent per user — a repeat `/skip` never increments the tally twice | unit | `pytest tests/test_skip_vote_logic.py -k idempotent -x` | ❌ W0 | ⬜ pending |
| 26-02 T1 | 26-02 | 2 | DJ-02 | T-26-05 | Only the track's requester bypasses; bot-queued tracks never bypass (no admin override) | unit | `pytest tests/test_skip_vote_logic.py -k requester_bypass -x` | ❌ W0 | ⬜ pending |
| 26-02 T1 | 26-02 | 2 | DJ-02 | T-26-08 | Threshold clamps to listener count — a misconfigured ratio can't wedge the queue | unit | `pytest tests/test_skip_vote_logic.py -k majority -x` | ❌ W0 | ⬜ pending |
| 26-02 T2 | 26-02 | 2 | DJ-02 | T-26-04 | Vote state is per-guild + per-track, reset structurally on track change | unit | `pytest tests/test_skip_vote_logic.py -k reset_on_track_change -x` | ❌ W0 | ⬜ pending |
| 26-02 T3 | 26-02 | 2 | DJ-02 | T-26-12 | Tally is templated with code-interpolated numbers — works when Gemini is rate-limited | unit | `pytest tests/test_responses.py -k skip_vote -x` | ✅ extend | ⬜ pending |
| 26-03 T1/T2 | 26-03 | 2 | DJ-01 | T-26-02, T-26-10 | Refills stay priority-2; ignored-signal announce + memory write suppressed while armed | unit | `pytest tests/test_autoqueue_wiring.py -x` | ✅ extend | ⬜ pending |
| 26-03 T3 | 26-03 | 2 | DJ-01 | T-26-02 | Auto-queue path byte-identical when radio is disarmed | unit | `pytest tests/test_autoqueue_wiring.py -x` | ✅ extend | ⬜ pending |
| 26-04 T1/T2 | 26-04 | 3 | DJ-02 | T-26-05 | Both `/skip` and the `⏭ Skip` button route through the SAME vote gate — no unvoted bypass | structural | `pytest tests/test_music_wiring.py -k skip_choke_point -x` | ❌ W0 | ⬜ pending |
| 26-04 T3 | 26-04 | 3 | DJ-02 | T-26-11 | A vote-skipped track records via the existing `mark_song_skipped` and nothing more | structural | `pytest tests/test_music_wiring.py -k no_new_memory_kind -x` | ❌ W0 | ⬜ pending |
| 26-04 T1/T3 | 26-04 | 3 | DJ-02 | T-26-03 | `listener_ids` denominator read fresh per vote, never memoized | structural | `pytest tests/test_music_wiring.py -x` | ❌ W0 | ⬜ pending |
| 26-05 T2/T3 | 26-05 | 4 | DJ-01 | T-26-13 | `/radio stop`, `/stop`, idle-leave all disarm; `/play` mid-radio only injects | structural + unit | `pytest tests/test_music_wiring.py -x` | ❌ W0 | ⬜ pending |
| 26-05 T2/T3 | 26-05 | 4 | DJ-01 | T-26-14 | `logic/playback.py` byte-identical — radio is an added gate, not a new `TrackEndAction` | structural | `pytest tests/test_playback_logic.py -x` | ✅ exists | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Phase Requirements → Test Map (binding)

| Req ID | Behavior | Test Type | Automated Command | File Exists? | Owning Task |
|--------|----------|-----------|-------------------|-------------|-------------|
| DJ-01 (SC-1) | Radio refills indefinitely off a seed, no manual `/play` needed | unit (pure gate) | `pytest tests/test_radio_logic.py -k should_refill -x` | ❌ Wave 0 | 26-01 T1 |
| DJ-01 (SC-1) | Radio's refill reuses `try_auto_queue`'s pipeline unchanged (byte-identical when disarmed) | unit (wiring/regression) | `pytest tests/test_autoqueue_wiring.py -x` (extended) | ❌ Wave 0 (extend existing) | 26-03 T3 |
| DJ-01 (SC-1) | Session played-set independently rejects a duplicate after YouTube resolution (D-03) | unit (pure gate + hard filter) | `pytest tests/test_radio_logic.py -k played_set -x` | ❌ Wave 0 | 26-01 T1 (gate) + 26-03 T2 (wiring) |
| DJ-01 (SC-2) | `/radio stop`, `/stop`, idle-leave all disarm radio (no leftover auto-refill) | unit (armed-state transitions) | `pytest tests/test_radio_logic.py -k disarm -x` | ❌ Wave 0 | 26-01 T2 + 26-05 T3 |
| DJ-01 (SC-2) | Human `/play` mid-radio injects without disarming | unit (pure gate) | `pytest tests/test_radio_logic.py -k human_play_injects -x` | ❌ Wave 0 | 26-01 T1 + 26-05 T3 |
| DJ-01 | Radio and loop mode are mutually exclusive (D-11) | unit (pure gate) | `pytest tests/test_radio_logic.py -k loop_exclusion -x` | ❌ Wave 0 | 26-01 T2 + 26-05 T2 |
| DJ-02 (SC-3) | Vote threshold = strict majority of non-bot listeners, computed live | unit (D-09c table at n=1,2,3,4) | `pytest tests/test_skip_vote_logic.py -k majority -x` | ❌ Wave 0 | 26-02 T1 |
| DJ-02 (SC-3) | Tally narrates the running count via templated copy | unit (format smoke test) | `pytest tests/test_responses.py -k skip_vote -x` (extended) | ❌ Wave 0 (extend existing) | 26-02 T3 |
| DJ-02 (SC-3) | Both `/skip` and the `⏭ Skip` button route through the SAME vote gate | structural/wiring (source-scan) | `pytest tests/test_music_wiring.py -k skip_choke_point -x` | ❌ Wave 0 | 26-04 T2/T3 |
| DJ-02 (SC-4) | Solo listener's `/skip` skips instantly (regression-locked) | unit (`len(listener_ids) <= 1` branch) | `pytest tests/test_skip_vote_logic.py -k solo -x` | ❌ Wave 0 | 26-02 T1 |
| DJ-02 | Track requester bypasses the vote (D-13a); bot-queued tracks never bypass (D-13b) | unit (pure gate) | `pytest tests/test_skip_vote_logic.py -k requester_bypass -x` | ❌ Wave 0 | 26-02 T1 |
| DJ-02 | Vote is idempotent per user; a repeat `/skip` from the same voter is a no-op (D-14) | unit (pure gate) | `pytest tests/test_skip_vote_logic.py -k idempotent -x` | ❌ Wave 0 | 26-02 T1 |
| DJ-02 | Votes reset on track change (D-17) | unit (state lifecycle) | `pytest tests/test_skip_vote_logic.py -k reset_on_track_change -x` | ❌ Wave 0 | 26-02 T2 |
| DJ-02 | A vote-skipped track records via the existing `mark_song_skipped`, nothing more (D-20) | regression/structural | `pytest tests/test_music_wiring.py -k no_new_memory_kind -x` | ❌ Wave 0 | 26-04 T3 |

---

## Wave 0 Requirements

- [ ] `tests/test_radio_logic.py` — DJ-01 pure refill-gate seam (armed? below-lookahead? played-set filter? loop-mutual-exclusion?)
- [ ] `tests/test_skip_vote_logic.py` — DJ-02 pure vote seam (majority arithmetic at n=1/2/3/4, requester bypass, idempotent re-vote, solo instant-skip)
- [ ] `tests/test_music_wiring.py` — structural source-scan asserting `/skip` AND the `⏭ Skip` button both call the same shared choke-point helper. **This is the concrete regression guard for RESEARCH Pitfall 1** (`/skip`'s inline body does not currently call `_do_skip`). Mirrors `test_autoqueue_wiring.py`'s `src.count(...)` pattern.
- [ ] Extend `tests/test_autoqueue_wiring.py` — regression guard proving the auto-queue path is byte-identical to pre-Phase-26 behavior when radio is disarmed (mirrors the Phase 14/16 "byte-identical when unset" convention)
- [ ] Extend `tests/test_responses.py` — smoke test that the new tally pool's `{votes}`/`{required}` placeholders format without `KeyError` (mirrors the `SKIPS_RATE_ROASTS` `{pct}` pattern)

*No test-framework install gap — pytest/pytest-asyncio already fully wired.*

---

## Manual-Only Verifications

> Per project precedent (Phases 11/13/14/15/16/17), live-Discord checks are parked in a
> `26-HUMAN-UAT.md` at phase close — the 24/7 deploy is PARKED and the bot runs on-demand
> on the owner's PC. These are acknowledged-deferred, not gaps.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Radio cadence *feel* — does the queue refill smoothly with no audible gap or dead air? | DJ-01 (SC-1) | Requires live voice playback + real YouTube resolution timing; the prefetch/refill interaction is not observable in unit tests | Join voice, `/radio start` with a seed, let 4+ tracks play through unattended; confirm no gap, no manual `/play` needed |
| Multi-listener vote tally narration reads naturally and the tally is accurate | DJ-02 (SC-3) | Requires 2+ real humans in a voice channel; tally copy is a personality/feel judgment | With 3 listeners, have 2 issue `/skip`; confirm Dexter narrates the running tally on the 1st vote and the track skips on the 2nd |
| Solo `/skip` still skips instantly with no vote prompt | DJ-02 (SC-4) | Live regression check of the single-listener path | Alone in voice, `/skip` — must skip immediately, no tally message |
| `/radio stop` leaves no leftover auto-refill behavior | DJ-01 (SC-2) | Requires observing the queue over time after disarm | `/radio stop`, let the queue drain to empty; confirm the bot does NOT refill and normal auto-queue/idle behavior resumes |
| Clean-boot smoke: `/radio` + `/skip` register and respond | DJ-01, DJ-02 | Command registration is Discord-gateway-side | `docker compose up`; confirm `/radio start|stop` and `/skip` appear and respond |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies — all 15 tasks across 26-01..26-05 carry an `<automated>` block
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references — the 5 Wave 0 files are created/extended by 26-01 T1/T2, 26-02 T1/T3, 26-03 T3, 26-04 T3
- [x] No watch-mode flags
- [x] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-16 (planner) — every binding row maps to a task; the
`tests/test_music_wiring.py` skip-choke-point row (RESEARCH Pitfall 1's regression guard) is
owned by 26-04 T2/T3, where the `/skip` slash body is explicitly deleted and re-routed.
