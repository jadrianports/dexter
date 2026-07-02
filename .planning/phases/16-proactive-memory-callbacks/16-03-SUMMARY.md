---
phase: 16-proactive-memory-callbacks
plan: 03
subsystem: bot-events
tags: [discord, ambient-personality, rag-memory, proactive-callbacks]

# Dependency graph
requires:
  - phase: 16-proactive-memory-callbacks (plan 01)
    provides: "logic/proactive.py::should_fire_proactive_callback pure gate + PROACTIVE_CALLBACK_* config knobs"
  - phase: 16-proactive-memory-callbacks (plan 02)
    provides: "database.get_proactive_opt_out / set_proactive_opt_out + proactive_opt_out column"
provides:
  - "personality/roasts.py::PROACTIVE_CALLBACK_FALLBACKS template pool"
  - "cogs/events.py::EventsCog._generate_ambient_roast(..., *, pre_recalled_memories=None) — Pitfall-1 bypass"
  - "cogs/events.py::EventsCog._proactive_daily_counts dict + _maybe_fire_proactive_callback"
  - "cogs/events.py::on_message proactive-gate call (designated-channel only, never a DM)"
  - "tests/test_proactive_events.py (7 tests) + tests/test_ambient_recall_cadence.py (1 new test)"
affects: [16-04-memory-callbacks-command]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Gemini-first ambient-roast generator extended with a keyword-only bypass param (pre_recalled_memories) rather than forked — avoids a second recall/Gemini pipeline while keeping the two existing voice-event call sites byte-identical (default None)"
    - "Third ambient cadence (proactive-chat) composed entirely from Phase 3/10/11/15 machinery: pure gate (16-01) + opt-out storage (16-02) + reused roast generator (this plan) — zero new recall/Gemini/DB primitives"

key-files:
  created:
    - tests/test_proactive_events.py
  modified:
    - personality/roasts.py
    - cogs/events.py
    - tests/test_ambient_recall_cadence.py

key-decisions:
  - "pre_recalled_memories bypass implemented as an if/else split around the existing internal recall block (not a separate early-return) — preserves the exact downstream code path (build_chat_prompt/Gemini/fallback) for both branches, satisfying the plan's 'everything downstream is untouched' requirement"
  - "_maybe_fire_proactive_callback reads self.bot.pool directly (not getattr-guarded) per the plan's literal spec, matching database.get_proactive_opt_out's existing call convention elsewhere in the codebase"
  - "Added a symmetric positive test (test_designated_channel_triggers) alongside the plan-required test_non_designated_channel_skips for gate-boundary confidence — not plan-mandated but zero scope risk (pure additive test)"

patterns-established:
  - "Reply-anchored proactive send: message.reply(..., allowed_mentions=discord.AllowedMentions.none(), mention_author=False) — distinct delivery primitive from the channel.send(...) ambient convention, reserved for surfaces that must visibly anchor to a specific triggering message"

requirements-completed: [PROACT-01, PROACT-02]

# Metrics
duration: 13min
completed: 2026-07-03
---

# Phase 16 Plan 03: Proactive Callback Events Glue Summary

**Wired the third, rarest ambient cadence into `cogs/events.py`: a chat-anchored proactive memory callback (opt-out -> chance/cap gate -> recall-floor -> Gemini-framed reply, mentions suppressed) plus the `pre_recalled_memories` bypass that stops the reused ambient-roast generator from triple-gating.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-07-03T04:12:00+08:00 (approx, first read after 16-02 commit)
- **Completed:** 2026-07-03T04:19:18+08:00
- **Tasks:** 3 completed
- **Files modified:** 4 (1 created, 3 modified)

## Accomplishments
- Fixed the research-flagged Pitfall 1: `_generate_ambient_roast` gained a keyword-only `pre_recalled_memories: list[str] | None = None` parameter that, when supplied, skips the internal `MEMORY_CALLBACK_CHANCE`-gated recall entirely — the two voice-event call sites (`on_voice_state_update` join/leave) stay byte-identical by default
- Added `personality/roasts.py::PROACTIVE_CALLBACK_FALLBACKS` — a 6-line, lowercase, contempt-outward template pool with no numeric placeholders, following the file's LOCKED voice-register constraints
- Wired `EventsCog._maybe_fire_proactive_callback`: the full D-02 firing order (opt-out -> pure `should_fire_proactive_callback` gate -> recall-floor silent-skip -> reply-anchored fire with `AllowedMentions.none()` + `mention_author=False`), with the per-user daily counter (`_proactive_daily_counts`) incrementing only after a successful send
- Gated the call from `on_message` behind `message.guild is not None` + `config.DEXTER_CHANNEL_ID` id-equality (Pitfall 2 — a DM or non-designated channel never reaches the gate)
- Locked all of the above with 8 new behavioral/regression tests (7 in the new `tests/test_proactive_events.py`, 1 extending `tests/test_ambient_recall_cadence.py`); full suite green at 810 passed / 108 skipped (up from 802/108), zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Fallback pool + pre_recalled_memories bypass on _generate_ambient_roast (Pitfall 1)** - `33cddc8` (feat)
2. **Task 2: _maybe_fire_proactive_callback glue + on_message gate + daily-counter dict** - `10583d1` (feat)
3. **Task 3: Behavioral glue tests + Pitfall-1 regression lock** - `06a6d99` (test)

**Plan metadata:** (this commit, docs)

## Files Created/Modified
- `personality/roasts.py` - New `PROACTIVE_CALLBACK_FALLBACKS: list[str]` pool (6 lines, ≤120 chars, optional `{name}` placeholder, no numeric placeholders) + added to `__all__`
- `cogs/events.py` - `_generate_ambient_roast` gained the `pre_recalled_memories` keyword-only bypass param; `EventsCog.__init__` gained `self._proactive_daily_counts: dict[str, tuple[str, int]] = {}`; new `_maybe_fire_proactive_callback` method implementing the D-02 order; `on_message` gained the designated-channel gate call after `_handle_message_reactions`; new module imports `database` and `logic.proactive.should_fire_proactive_callback`
- `tests/test_proactive_events.py` - New file: `test_recall_floor_silent_skip`, `test_reply_anchor`, `test_daily_counter_increments_only_on_fire`, `test_opted_out_short_circuits`, `test_non_designated_channel_skips`, `test_designated_channel_triggers` (additive positive-case mirror), `test_accuracy_firewall`
- `tests/test_ambient_recall_cadence.py` - Added `test_pre_recalled_bypasses_internal_recall`; `test_ambient_surfaces_retain_gate` and all prior tests left unmodified and passing

## Decisions Made
- Implemented the Pitfall-1 bypass as an `if pre_recalled_memories is not None: amb_memories = pre_recalled_memories else: <original block unchanged>` split, rather than restructuring into an early return — this was the smallest edit that both keeps the internal `config.MEMORY_CALLBACK_CHANCE` literal present in source (required by the pre-existing `test_ambient_surfaces_retain_gate` regression lock) and leaves every downstream line (`build_chat_prompt`, the priority-2 Gemini call, lowercase/length enforcement, template fallback) completely untouched for both branches
- `_maybe_fire_proactive_callback` calls `database.get_proactive_opt_out(self.bot.pool, user_id)` using `self.bot.pool` directly (not `getattr(self.bot, "pool", None)`), matching the plan's literal action text and the existing convention that `self.bot.pool` is always present once the bot is initialized (unlike `gemini_service`/`memory_service`, which are optionally absent when API keys are unset)
- Added one test beyond the plan's required list (`test_designated_channel_triggers`) as a cheap positive-case mirror to `test_non_designated_channel_skips` — purely additive, no scope risk, increases confidence in the channel-gate boundary

## Deviations from Plan

None - plan executed exactly as written. All three tasks' `<action>`/`<behavior>`/`<verify>` specs matched on the first pass; the only addition beyond the plan's explicit test list was the harmless symmetric positive-case test noted above.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `personality/roasts.py::PROACTIVE_CALLBACK_FALLBACKS`, the `pre_recalled_memories` bypass, and `EventsCog._maybe_fire_proactive_callback` are all ready for plan 16-04 (`/memory callbacks on|off` subcommand, which calls `database.set_proactive_opt_out` — the read side this plan already wired in is fully exercised by `test_opted_out_short_circuits`).
- Full test suite verified green: 810 passed, 108 skipped, 0 failed (additive-only, no regressions). The voice-event `MEMORY_CALLBACK_CHANCE` gate remains intact and locked by both the original `test_ambient_surfaces_retain_gate` and the new `test_pre_recalled_bypasses_internal_recall`.
- No blockers for 16-04.

---
*Phase: 16-proactive-memory-callbacks*
*Completed: 2026-07-03*
