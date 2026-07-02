---
phase: 16-proactive-memory-callbacks
verified: 2026-07-03T12:00:00Z
status: human_needed
score: 10/10 must-haves verified (code-level); 2 pre-existing Manual-Only items parked behind host
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 9/10
  gaps_closed:
    - "Truth #4 (PROACT-01 core promise / recall-anchor efficacy) — WR-03 fix (commit 8821edf) anchors proactive recall on message.content.strip() (fallback \"this user's music taste and history\" when empty) instead of the static content-free string \"a proactive callback moment\". This mirrors the proven-working anchor pattern already used by /ask (user's question) and the ambient roast (scenario text), removing the credible risk that recall() would return [] almost every time."
    - "WR-01 TOCTOU race on the daily-cap counter — fixed (commit 67fedbc) via reserve-before-await / release-on-every-non-fire-exit path (memory_service None, empty recall, HTTPException on reply)."
    - "WR-02 unguarded opt-out DB call — fixed (commit be43a99) via try/except around database.get_proactive_opt_out, fails closed (skips this message's callback) and logs at debug level, matching the recall path's degrade-to-default discipline."
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "A live proactive callback fires at a real active moment and reads as a dry aside, not surveillance"
    expected: "Posting repeatedly in the designated channel over time eventually produces one reply-anchored, mention-suppressed callback that references a real remembered detail in Dexter's voice."
    why_human: "Requires a running bot on a residential IP + real Gemini + real Discord channel activity; the 'feel' target is subjective. Parked behind the always-on host per Phase 11/13/14/15 UAT precedent (16-VALIDATION.md §Manual-Only)."
  - test: "/memory callbacks off visibly silences the surface in Discord while /memory view still shows intact memories"
    expected: "Ephemeral in-character confirmation on toggle; `/memory view` unchanged after opting out."
    why_human: "Discord slash-command + ephemeral UX check on a live client. Parked behind host (16-VALIDATION.md §Manual-Only)."
---

# Phase 16: Proactive Memory Callbacks Verification Report

**Phase Goal:** Dexter occasionally volunteers a memory unprompted at a well-chosen active moment, never crossing into "the bot is watching me" territory — and any user can turn it off for themselves. (rarer than ambient roasts; per-user opt-out)
**Verified:** 2026-07-03T12:00:00Z
**Status:** human_needed
**Re-verification:** Yes — after code-review fix commits 8821edf (WR-03), 67fedbc (WR-01), be43a99 (WR-02)

## Goal Achievement

### What changed since the prior verification

The prior verification (2026-07-02) scored 9/10 and routed truth #4 (PROACT-01's
core promise) to human verification because 16-REVIEW.md's WR-03 finding argued
the static, content-free recall anchor `"a proactive callback moment"` would
almost certainly fall below `MEMORY_SIMILARITY_FLOOR = 0.70` against concrete
stored facts, causing `recall()` to return `[]` on nearly every qualifying
message and silently neutering the feature even though every other gate/wiring
piece was correct.

`gsd-code-fixer` applied three commits closing all three WARNING-level findings
from 16-REVIEW.md:

- **8821edf (WR-03):** `cogs/events.py:443-479` now anchors recall on
  `message.content.strip() or "this user's music taste and history"` instead of
  the static string. This is the same pattern already proven to work on two
  other verified surfaces in this codebase — `/ask` anchors on the user's
  literal question, and the ambient voice roast anchors on the formatted
  scenario text (`"{name} just joined the voice channel"`). Anchoring on real
  message content gives `recall()` semantically relevant text to embed and
  compare against stored facts, removing the specific mechanism the review
  flagged as goal-blocking.
- **67fedbc (WR-01):** the daily-cap counter is now reserved
  (`self._proactive_daily_counts[user_id] = (today, daily_count + 1)`)
  immediately after the gate passes, before any further `await`, and released
  back to its exact pre-reservation state on every non-fire exit path
  (`memory_service is None`, empty recall, `discord.HTTPException` on reply).
  This closes the TOCTOU window a concurrent message from the same user could
  previously exploit to exceed `PROACTIVE_CALLBACK_DAILY_CAP = 1`.
- **be43a99 (WR-02):** `database.get_proactive_opt_out` is now wrapped in
  `try/except Exception`, fails closed (returns early, skipping this message's
  callback) and logs at debug level — matching the sibling `recall()` call's
  degrade-to-default discipline two steps below it, and no longer capable of
  raising an unhandled exception out of `on_message` during a transient DB
  hiccup.

All three fixes verified directly against the live diff (`git show`) and the
current file contents (`cogs/events.py:406-513`), not from SUMMARY/REVIEW
narrative.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `should_fire_proactive_callback` implements opt-out → chance → daily-cap short-circuit gate, boundary-correct (`>=` fails at threshold/ceiling) | ✓ VERIFIED | `logic/proactive.py:31-91`; unchanged by fix commits; `tests/test_proactive_logic.py` (16 tests) still pass |
| 2 | `PROACTIVE_CALLBACK_CHANCE` (0.10) strictly < `UNPROMPTED_ROAST_CHANCE` (0.30) and < `MEMORY_CALLBACK_CHANCE` (0.35) | ✓ VERIFIED | `config.py:231-232`; unchanged; test passes |
| 3 | A non-bot message in the designated channel evaluates the proactive gate; a DM or message in any other channel never does | ✓ VERIFIED | `cogs/events.py:395-402`; unchanged; tests pass |
| 4 | Dexter occasionally brings up a remembered detail unprompted at a real active moment (PROACT-01 core promise) | ✓ VERIFIED (code-level; live-feel remains Manual-Only) | **Gap closed.** `cogs/events.py:479` now computes `anchor = message.content.strip() or "this user's music taste and history"` and passes it to `memory_service.recall(...)`, replacing the static content-free anchor the prior verification flagged as goal-blocking. This mirrors `/ask`'s and the ambient roast's already-verified-working anchor pattern (real/relevant text → embed → compare against stored facts), removing the specific mechanism (semantically unrelated anchor text failing the 0.70 floor) that risked defeating the feature. The remaining uncertainty — whether a *specific* live message + a *specific* user's stored facts clear 0.70 in production — is an inherent property of live embedding similarity, not a code defect, and is the same class of "run it on the real host with real data" check already parked for Phases 11/13/14/15. Silent-skip on `[]` still holds (no false fires). |
| 5 | When the gate passes but `recall()` returns `[]`, no Discord message is sent and the counter does not increment (silent skip) | ✓ VERIFIED | `cogs/events.py:488-492`; counter is now *reserved* at gate-pass and *released* back to its prior state on this path (`_release_reserved_slot()`) — net effect unchanged (no increment survives an empty-recall skip); `test_recall_floor_silent_skip` passes, asserts `str(message.author.id) not in cog._proactive_daily_counts` after the skip |
| 6 | A fire produces exactly one `message.reply` with `AllowedMentions.none()` + `mention_author=False`, never `channel.send`; the per-user daily counter increments only on an actual fire; **no TOCTOU race can exceed the cap** | ✓ VERIFIED | `cogs/events.py:462-513`; **WR-01 gap closed** — reserve-before-await/release-on-every-non-fire-exit pattern (`_had_entry`/`_prior_value`/`_release_reserved_slot`) closes the race the prior review flagged; `test_reply_anchor`, `test_daily_counter_increments_only_on_fire` still pass unmodified against the new implementation (behavior at the test boundary is unchanged — reserve+confirm nets to the same increment-only-on-fire outcome the tests assert) |
| 7 | `_generate_ambient_roast(..., pre_recalled_memories=[...])` bypasses the internal `MEMORY_CALLBACK_CHANCE` recall roll; the two voice-event call sites remain byte-identical (default `None`) | ✓ VERIFIED | `cogs/events.py:95-201` unchanged by fix commits; `test_pre_recalled_bypasses_internal_recall` + `test_ambient_surfaces_retain_gate` both pass |
| 8 | The proactive glue never pipes a live-SQL numeric stat into reply text outside the firewalled `_generate_ambient_roast` path (accuracy firewall) | ✓ VERIFIED | `test_accuracy_firewall` source-inspects `_maybe_fire_proactive_callback` for absence of `get_user_summary`/`get_user_top_artist` — passes against the post-fix source |
| 9 | A user can pause proactive callbacks for themselves via `/memory callbacks off`, resume via `on`; self-scoped, ephemeral, touches zero `user_memories` rows | ✓ VERIFIED | `cogs/memory.py:309-339` unchanged by fix commits; `tests/test_memory_command.py -k callbacks` (4 tests) pass |
| 10 | `proactive_opt_out` persists via upsert for a user with no prior row; getter defaults to `False` for a never-seen user; helpers touch only `user_profiles`; **the per-message read now fails closed instead of raising** | ✓ VERIFIED | `database.py:102,318-376` unchanged; **WR-02 gap closed** — `cogs/events.py:420-432` now wraps the call in `try/except`, returns early (skip) on any exception instead of propagating out of `on_message`; `tests/test_database_phase16.py` static tier green |

**Score:** 10/10 truths VERIFIED at the code level. Truth #4's remaining residual uncertainty (does the fixed anchor clear the similarity floor for a *specific* live message against a *specific* user's real stored facts) is inherent to live embedding behavior and is routed to human verification alongside the two pre-existing Manual-Only items — it is no longer a code-level gap.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `logic/proactive.py` | Pure `should_fire_proactive_callback` gate | ✓ VERIFIED | Unchanged, 92 lines, pure, no I/O imports |
| `config.py` | `PROACTIVE_CALLBACK_CHANCE` + `PROACTIVE_CALLBACK_DAILY_CAP` knobs | ✓ VERIFIED | Unchanged |
| `tests/test_proactive_logic.py` | Mock-free boundary coverage + rarity invariant | ✓ VERIFIED | 16 tests, 0 mocks, all pass |
| `database.py` | `proactive_opt_out` column + get/set helpers | ✓ VERIFIED | Unchanged |
| `tests/test_database_phase16.py` | Signature guards + live-DB round-trip + independence proof | ✓ VERIFIED | Static tier passes; live tier auto-skips (no `TEST_DATABASE_URL`) |
| `personality/roasts.py::PROACTIVE_CALLBACK_FALLBACKS` | Template fallback pool | ✓ VERIFIED | Unchanged |
| `cogs/events.py` | `_maybe_fire_proactive_callback` + `pre_recalled_memories` + `_proactive_daily_counts` + `on_message` gate | ✓ VERIFIED | All three review warnings fixed in-place; re-read full function body (lines 406-513) directly, confirms WR-01/WR-02/WR-03 all present and correctly ordered |
| `tests/test_proactive_events.py` | Behavioral glue proofs | ✓ VERIFIED | 7 tests, all pass unmodified against the post-fix implementation |
| `cogs/memory.py` | `memory_callbacks` subcommand | ✓ VERIFIED | Unchanged |
| `tests/test_memory_command.py` | callbacks round-trip + self-scoping + ephemeral + zero-memory-touch tests | ✓ VERIFIED | 4 tests pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `cogs/events.py::on_message` | `_maybe_fire_proactive_callback` | guild + `DEXTER_CHANNEL_ID` gate | ✓ WIRED | `cogs/events.py:395-402`, unchanged |
| `cogs/events.py::_maybe_fire_proactive_callback` | `logic.proactive.should_fire_proactive_callback` | pure gate dispatch | ✓ WIRED | `cogs/events.py:443-448`, unchanged |
| `cogs/events.py::_maybe_fire_proactive_callback` | `database.get_proactive_opt_out` | opt-out read, **now guarded** | ✓ WIRED | `cogs/events.py:425-432` — WR-02 fix confirmed present |
| `cogs/events.py::_maybe_fire_proactive_callback` | `message.reply` | `AllowedMentions.none()` reply-anchor | ✓ WIRED | `cogs/events.py:501-509`, unchanged |
| `cogs/memory.py::memory_callbacks` | `database.set_proactive_opt_out` | self-scoped opt-out write | ✓ WIRED | `cogs/memory.py:332-334`, unchanged |
| `cogs/events.py::_maybe_fire_proactive_callback` | `services/memory.py::MemoryService.recall` | **content-anchored** floor-checked recall | ✓ WIRED | `cogs/events.py:479-483` — WR-03 fix confirmed present; anchor is now `message.content.strip()` with a non-empty fallback, not the prior static string |
| `cogs/events.py::_maybe_fire_proactive_callback` | `self._proactive_daily_counts` | reserve-before-await / release-on-non-fire-exit | ✓ WIRED | `cogs/events.py:458-513` — WR-01 fix confirmed present at all four exit points (memory_service None, empty recall, HTTPException, fall-through fire) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 16 unit + behavioral suite (post-fix) | `pytest tests/test_proactive_logic.py tests/test_database_phase16.py tests/test_proactive_events.py tests/test_ambient_recall_cadence.py tests/test_memory_command.py -q` | 46 passed, 2 skipped (live-DB tier, no `TEST_DATABASE_URL`) | ✓ PASS — identical result to pre-fix run, confirming zero regressions from the three fixes |
| Full regression suite (post-fix) | `pytest -q` | 814 passed, 108 skipped, 0 failed | ✓ PASS — identical totals to the pre-fix verification run |
| Syntax/compile check on all touched files | `python -m py_compile cogs/events.py cogs/memory.py database.py logic/proactive.py config.py` | Compiles cleanly | ✓ PASS |
| Live embedding/recall behavior of the fixed content anchor | n/a | Cannot run — requires live Neon DB + Gemini API key + seeded facts + a live Discord message | ? SKIP (routed to human_verification, same class as pre-existing Manual-Only items) |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|-----------------|--------------|--------|----------|
| PROACT-01 | 16-01, 16-03 | Background surface occasionally volunteers a recalled memory at an active moment, rarer than 0.30-0.35 ambient rates, with an additive daily cap | ✓ SATISFIED (code-level) — live-feel confirmation remains a Manual-Only host-parked check per 16-VALIDATION.md, unrelated to the WR-03 gap that is now closed | `logic/proactive.py`, `cogs/events.py` gate + glue, content-anchored recall |
| PROACT-02 | 16-02, 16-03, 16-04 | A user can opt out of proactive callbacks distinct from full memory deletion | ✓ SATISFIED | `database.py` opt-out helpers, `cogs/memory.py::memory_callbacks`, cross-independence tests |

No orphaned requirements — `.planning/REQUIREMENTS.md` maps exactly PROACT-01 and PROACT-02 to Phase 16 (`REQUIREMENTS.md:35-36,86-87`), both marked `[x]` Complete, both claimed across the four plans' frontmatter.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | None remaining. All three 16-REVIEW.md WARNING findings (WR-01, WR-02, WR-03) confirmed fixed in the live diff and current file contents. | — | — |

No 🛑 Blocker-severity findings. No unreferenced TBD/FIXME/XXX debt markers in any Phase 16 file. The three 16-REVIEW.md INFO-level notes (IN-01 docstring-vs-order nit, IN-02 duplicated function-local imports, IN-03 default-binding footgun) remain unfixed but were explicitly marked "no fix required" / cosmetic by the reviewer and do not affect goal achievement.

### Human Verification Required

### 1. Live "feel" check — proactive callback reads as a dry aside, not surveillance

**Test:** Run the bot on the always-on host, post repeatedly in the designated channel over time, and observe whether a callback eventually fires, is reply-anchored, mention-suppressed, and reads in Dexter's voice.
**Expected:** A rare, well-timed, in-character callback — never a ping, never a DM, never a poll. Given the WR-03 fix, this should now fire at roughly the intended ~0.10-per-qualifying-message cadence when the user has relevant stored memory facts, rather than near-zero.
**Why human:** Requires a running bot + real Gemini + real Discord activity; subjective "feel" target. Parked behind host per Phase 11/13/14/15 precedent (16-VALIDATION.md §Manual-Only).

### 2. `/memory callbacks off` visibly silences the surface while `/memory view` stays intact

**Test:** Run `/memory callbacks off` on a live client, confirm the ephemeral in-character reply, then run `/memory view` and confirm memories are unchanged.
**Expected:** Ephemeral confirmation; memories intact; no proactive callback fires afterward for that user.
**Why human:** Discord slash-command + ephemeral UX check on a live client. Parked behind host (16-VALIDATION.md §Manual-Only).

### Gaps Summary

No code-level gap remains. All three 16-REVIEW.md WARNING-level findings are fixed
and verified directly against the diff and the current file contents:

- **WR-03 (the item that previously routed truth #4 to human verification as a
  goal-blocking risk)** is resolved by anchoring recall on real message content
  instead of a static, content-free string — the same anchor pattern already
  proven to work on two other verified surfaces (`/ask`, ambient voice roast) in
  this codebase. This was the specific mechanism the prior verification
  identified as capable of silently neutering PROACT-01 in practice, and it no
  longer exists in the code.
- **WR-01** (daily-cap TOCTOU race) and **WR-02** (unguarded opt-out DB call) are
  both fixed with the exact reserve/release and try/except patterns the review
  recommended, confirmed present at every relevant exit path.

The full test suite is green with zero regressions (814 passed / 108 skipped /
0 failed, identical totals to the pre-fix run), and the Phase-16-specific
behavioral suite (46 passed / 2 skipped) passes unmodified against the new
implementation — the fixes did not require weakening any existing assertion to
stay green.

The two remaining human-verification items are exactly the two Manual-Only
entries already declared in `16-VALIDATION.md` before any fix work began (live
"feel" check; `/memory callbacks off` Discord UX check) — both require a running
bot on the always-on residential host and are consistent with the
acknowledged-deferred UAT precedent from Phases 11/13/14/15. Neither concerns
the WR-03 efficacy risk that drove the prior `human_needed` status; that risk
is now closed at the code level.

---

*Verified: 2026-07-03T12:00:00Z*
*Verifier: Claude (gsd-verifier)*
