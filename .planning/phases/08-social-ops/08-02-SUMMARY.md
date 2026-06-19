---
phase: 08-social-ops
plan: 02
subsystem: ai-commands
tags: [discord, slash-command, gemini, personality, roast, tdd]

# Dependency graph
requires:
  - phase: 08-01
    provides: ROAST_COOLDOWN_SECONDS=30, GeminiService.rpm_usage/rpm_headroom, increment_daily_stat("total_errors") allowlist
  - phase: 03-alive
    provides: _generate_ambient_roast pattern, build_chat_prompt, pick_random, personality pools structure
  - phase: 02-personality
    provides: get_mood, get_user_summary, GeminiService.chat(priority=)
provides:
  - /roast slash command (cogs/ai.py AICog.roast)
  - ROAST_COMMAND_LINES pool (6 lines, {name} placeholder, harsher music-behavior)
  - ROAST_SELF_LINES pool (4 lines, self-roast bleak tone)
  - ROAST_BOT_LINES pool (4 lines, turns roast back on invoker)
  - ROAST_NO_HISTORY_LINES pool (4 lines, {name} placeholder, no-data tone)
  - tests/test_roast_command.py (4 unit tests)
affects: [cogs/ai.py, personality/roasts.py, tests/test_roast_command.py]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "app_commands.Command.callback pattern for testing decorated slash commands without Discord gateway"
    - "priority=1 Gemini call pattern for user-invoked slash commands vs priority=2 for background tasks"
    - "AllowedMentions.none() on every public roast send (T-08-04 mention-spoof mitigation)"

key-files:
  created:
    - tests/test_roast_command.py
  modified:
    - personality/roasts.py
    - cogs/ai.py

key-decisions:
  - "/roast resolves edge cases (bot/self/zero-history) BEFORE mood/Gemini setup — fallback pool is always set before async DB calls"
  - "Tests call cog.roast.callback(cog, interaction, target) — discord.py @app_commands.command wraps the method in a Command object, not directly awaitable"
  - "user_summary is explicitly initialized to None before edge-case branching so build_chat_prompt(mood, None, seasonal) is always valid"

# Metrics
duration: 12min
completed: 2026-06-19
---

# Phase 08 Plan 02: /roast Command Summary

**`/roast @user` slash command with Gemini-personalized roast from tracked music history, priority-1 call, mood + seasonal injection, guaranteed template fallback, and AllowedMentions.none() public send**

## Performance

- **Duration:** 12 min
- **Started:** 2026-06-19T07:30:00Z
- **Completed:** 2026-06-19T07:42:00Z
- **Tasks:** 2 (Task 1: roast pools; Task 2: /roast command + tests, TDD)
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- `personality/roasts.py` extended with 4 new template pools (ROAST_COMMAND_LINES × 6, ROAST_SELF_LINES × 4, ROAST_BOT_LINES × 4, ROAST_NO_HISTORY_LINES × 4) — all lowercase, ≤500 chars, ≤1 emoji, exported via `__all__`
- `/roast` slash command added to `AICog` in `cogs/ai.py`: edge-case branching (bot/self/zero-history), mood + seasonal injection, priority-1 Gemini call with personality-voice enforcement, guaranteed fallback on rate-limit or error, AllowedMentions.none() on every public send, daily stat increments
- `tests/test_roast_command.py` created with 4 unit tests covering fallback, edge cases, priority enforcement, and mention-spoof guard — all 4 green

## Task Commits

1. **Task 1: personality/roasts.py pools** - `1365de9` (feat)
2. **Task 2: TDD RED — failing tests** - `7db08ed` (test)
3. **Task 2: TDD GREEN — /roast implementation** - `6f4c9f1` (feat)

## TDD Gate Compliance

- RED gate: `7db08ed` — `test(08-02)` commit with 4 failing tests (AttributeError: no roast attribute) ✓
- GREEN gate: `6f4c9f1` — `feat(08-02)` commit with implementation; all 4 tests pass ✓
- REFACTOR: Not needed — implementation is clean as written

## Files Created/Modified

- `personality/roasts.py` — 4 new pools + 4 entries added to `__all__`
- `cogs/ai.py` — ROAST_* imports added; `/roast` app_command added to AICog (56 lines)
- `tests/test_roast_command.py` — 4 unit tests (new file, 278 lines)

## Decisions Made

- Edge cases resolved before mood/Gemini setup: `user_summary` initialized to `None` at the top of the function so `build_chat_prompt(mood, None, seasonal)` is always safe regardless of which branch is taken.
- Test invocation pattern: `cog.roast.callback(cog, interaction, target)` — discord.py's `@app_commands.command` wraps the coroutine in a `Command` object; tests must use `.callback` to reach the raw coroutine. This is the correct pattern for unit-testing decorated slash commands without a live gateway.
- `ROAST_COMMAND_LINES` contains 6 lines (within the spec's 4-6 range); more variety reduces repetition in high-traffic servers.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test _invoke_roast used direct cog method call instead of .callback**
- **Found during:** Task 2 GREEN phase (first pytest run)
- **Issue:** `await cog.roast(interaction, target)` raised `TypeError: 'Command' object is not callable` because `@app_commands.command` wraps the coroutine in a `discord.app_commands.Command` object. The test assumed the method remained directly awaitable.
- **Fix:** Changed `_invoke_roast` to `await cog.roast.callback(cog, interaction, target)` — the `.callback` attribute holds the raw underlying coroutine; `cog` must be passed explicitly as `self`.
- **Files modified:** `tests/test_roast_command.py`
- **Verification:** All 4 tests pass after fix
- **Committed in:** `6f4c9f1` (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — test invocation bug, no behavioral change)

## Known Stubs

None — the `/roast` command is fully wired: Gemini is called, fallback pools are populated with real on-brand lines, and all edge cases return real responses.

## Threat Flags

None — no new network endpoints or auth paths introduced beyond the slash command itself. T-08-04 (mention-spoof via target string) is mitigated by `AllowedMentions.none()` on every public send, verified by `test_roast_no_mass_mention`.

## Self-Check: PASSED

- `personality/roasts.py` exists with 4 new pools ✓
- `cogs/ai.py` contains `name="roast"`, `target: discord.Member`, `priority=1`, `AllowedMentions.none()` ✓
- `tests/test_roast_command.py` exists with 4 tests ✓
- `08-02-SUMMARY.md` exists ✓
- All 4 roast unit tests pass: `python -m pytest tests/test_roast_command.py -q` ✓
- Commit hashes verified: 1365de9, 7db08ed, 6f4c9f1 ✓
