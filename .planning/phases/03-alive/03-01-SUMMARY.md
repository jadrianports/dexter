---
phase: 03-alive
plan: "01"
subsystem: personality
tags: [python, config, prompts, roasts, gemini, few-shot, sqlite, tdd]

# Dependency graph
requires:
  - phase: 02-personality
    provides: "DEXTER_SYSTEM_PROMPT in personality/prompts.py, pick_random in personality/responses.py, global Gemini rate limiter"
  - phase: 02.5-hardening
    provides: "Stable bot.py cog loading, yt-dlp self-heal, WAL DB"
provides:
  - "All Phase 3 config constants in config.py (roast chances, cooldowns, milestone thresholds, lyrics/history tuning)"
  - "personality/roasts.py: 11 named template pools + is_late_night() pure helper — shared fallback layer for all Phase 3 ambient roast features"
  - "Rewritten DEXTER_SYSTEM_PROMPT with 6 few-shot USER/DEXTER exemplars and 3 explicitly-stated banned modes (D-06)"
  - "Locked voice standard: reviewed and approved by user on 2026-06-11"
  - "39 personality tests (23 roast, 16 prompt) + 89 pure-Python tests total, all green"
affects:
  - "03-02 (streak/DB helpers — reads MILESTONE_SONG_THRESHOLDS, MILESTONE_STREAK_THRESHOLDS, HISTORY_FETCH_LIMIT)"
  - "03-03 (LyricsService — reads LYRICS_COOLDOWN_SECONDS, LYRICS_PAGE_SIZE)"
  - "03-04 (EventsCog — reads VOICE_JOIN_ROASTS, VOICE_LEAVE_ROASTS, LATE_NIGHT_ROASTS, BOT_MOVED_COMPLAINTS, IDLE_LONELINESS_MESSAGES, UNPROMPTED_ROAST_CHANCE, LATE_NIGHT_ROAST_CHANCE, AMBIENT_ROAST_CEILING_SECONDS; implements Gemini-first-with-template-fallback per the 'Maximize AI' decision below)"
  - "03-05 (MusicCog — reads REPEAT_SONG_ROAST_TEMPLATES, MILESTONE_SONG_TEMPLATES, MILESTONE_STREAK_TEMPLATES, REPEAT_SONG_ROAST_THRESHOLD)"
  - "03-06 (bot.py status/startup/idle — reads STARTUP_MESSAGES, STATUS_LINES, STATUS_ROTATION_INTERVAL_SECONDS, IDLE_LONELINESS_THRESHOLD_SECONDS)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Template-pool module pattern: module-level list[str] pools imported by cogs; pick_random() is a shared utility from personality/responses.py — not redeclared"
    - "is_late_night(hour) pure helper as unit-testable seam for PERS-03 time logic"
    - "TDD RED/GREEN gate for DEXTER_SYSTEM_PROMPT rewrite (D-06): failing test committed before implementation"
    - "Gemini-first-with-template-fallback: ambient roasts attempt a personalized Gemini line first (priority-2), falling back to template pools on >10s wait or error"

key-files:
  created:
    - "personality/roasts.py — 11 named template pools + is_late_night helper"
    - "tests/test_roasts.py — pool non-empty assertions, pick_random behavior, is_late_night unit tests, f-bomb scan, self-deprecation guard"
    - "tests/test_prompts.py — extended with few-shot exemplar count check, banned-mode phrase assertion, placeholder tests"
  modified:
    - "config.py — Phase 3 constants block added after auto-queue section"
    - "personality/prompts.py — DEXTER_SYSTEM_PROMPT rewritten with few-shot exemplars and banned-mode rules (D-06); all other symbols unchanged"

key-decisions:
  - "D-06 implemented: DEXTER_SYSTEM_PROMPT rewritten with 6 few-shot USER/DEXTER exemplars (including canonical 'marcus. back with the drake' formula line) and 3 explicit banned modes"
  - "Voice standard locked and user-approved 2026-06-11: arrogant/outward-contempt register, mild swearing only, no bot-self-awareness, no pop-psych, no self-deprecation"
  - "DECISION 2026-06-11 — 'Maximize AI' for ambient roasts (OVERRIDES D-08 for join/leave/late-night): voice JOIN, LEAVE, and LATE-NIGHT roasts will attempt a priority-2 Gemini-generated personalized line FIRST (using user's tracked taste data), falling back to personality/roasts.py template pools only when the shared 15 RPM limiter would wait >10s or Gemini errors. Channel-move/idle/startup/status remain static template-only. IMPACT: 03-04 must implement the Gemini-first-with-template-fallback path for join/leave/late-night, mirroring the D-08 priority-2 + GeminiRateLimitError fallback pattern already specified for 03-05's repeat-song/milestone roasts, including a per-user taste lookup to feed the few-shot DEXTER voice builder. 03-01's deliverables (the template pools) are unaffected — they serve as the fallback."

patterns-established:
  - "Template pool fallback pattern: cog fires Gemini-first (priority-2) with >10s ceiling → falls back to pick_random(POOL)"
  - "Config-only writes in Wave 1: downstream plans (03-02 through 03-06) READ config, never write it — all Phase 3 constants are owned by 03-01"
  - "TDD gate compliance: RED commit precedes GREEN commit for prompt rewrite (D-06)"

requirements-completed: [PERS-01, PERS-02, PERS-03, PERS-04, PERS-07, PERS-08, PERS-09]

# Metrics
duration: multi-session (Wave 1 foundational — exact minutes not captured)
completed: 2026-06-11
---

# Phase 3 Plan 01: Foundation (Config + Personality + Prompt Rewrite) Summary

**Phase 3 config constants, 11-pool personality/roasts.py module, and DEXTER_SYSTEM_PROMPT rewritten with 6 few-shot exemplars + 3 banned-mode rules; voice standard reviewed and approved by user**

## Performance

- **Duration:** Multi-session (Wave 1 foundational work)
- **Started:** 2026-06-11
- **Completed:** 2026-06-11
- **Tasks:** 4 (3 auto + 1 checkpoint:human-verify — APPROVED)
- **Files modified:** 5

## Accomplishments

- All Phase 3 config constants written to config.py in a single owned block — downstream Wave 1/2/3 plans read only, never write config
- personality/roasts.py created with 11 named template pools covering every Phase 3 ambient-roast scenario; includes is_late_night() pure helper as testable seam for PERS-03
- DEXTER_SYSTEM_PROMPT rewritten per D-06 with 6 few-shot USER/DEXTER exemplars (including the canonical "marcus. back with the drake" formula line), 3 explicitly-stated banned modes, and all 4 format placeholders preserved
- 39 personality tests green (23 in test_roasts.py; 16 in test_prompts.py); 89 pure-Python tests green overall
- Voice standard reviewed and approved by user; "Maximize AI" ambient roast design decision recorded

## Task Commits

Each task was committed atomically:

1. **Task 1: Add all Phase 3 constants to config.py** - `4015bdf` (feat)
2. **Task 2: Create personality/roasts.py template-pool module + is_late_night + tests** - `662b681` (feat)
3. **Task 3 RED: Failing tests for DEXTER_SYSTEM_PROMPT few-shot rewrite (D-06)** - `8333ec7` (test)
4. **Task 3 GREEN: Rewrite DEXTER_SYSTEM_PROMPT with few-shot exemplars (D-06)** - `1d52455` (feat)

_TDD task 3 produced two commits (RED gate then GREEN gate) per the TDD execution protocol._

## Files Created/Modified

- `config.py` — Phase 3 constants block: DEXTER_CHANNEL_ID, STREAK_TIMEZONE, UNPROMPTED_ROAST_CHANCE, LATE_NIGHT_ROAST_CHANCE, AMBIENT_ROAST_CEILING_SECONDS, ROAST_COOLDOWN_SECONDS, REPEAT_SONG_ROAST_THRESHOLD, LATE_NIGHT_HOURS, MILESTONE_SONG_THRESHOLDS, MILESTONE_STREAK_THRESHOLDS, STATUS_ROTATION_INTERVAL_SECONDS, IDLE_LONELINESS_THRESHOLD_SECONDS, LYRICS_COOLDOWN_SECONDS, LYRICS_PAGE_SIZE, HISTORY_PAGE_SIZE, HISTORY_FETCH_LIMIT
- `personality/roasts.py` — New module: VOICE_JOIN_ROASTS, VOICE_LEAVE_ROASTS, LATE_NIGHT_ROASTS, BOT_MOVED_COMPLAINTS, IDLE_LONELINESS_MESSAGES, STARTUP_MESSAGES, STATUS_LINES, REPEAT_SONG_ROAST_TEMPLATES, MILESTONE_SONG_TEMPLATES, MILESTONE_STREAK_TEMPLATES, NO_LYRICS_FOUND pools + is_late_night() helper
- `personality/prompts.py` — DEXTER_SYSTEM_PROMPT rewritten with few-shot exemplars; MUSIC_RECOMMENDATION_PROMPT, MOOD_CONTEXTS, build_chat_prompt, build_recommendation_prompt left byte-for-byte unchanged
- `tests/test_roasts.py` — New: pool non-empty assertions, pick_random membership test, is_late_night boundary tests (hours 0/1/3/5/6/12), f-bomb scan across all pools, self-deprecation guard for STARTUP_MESSAGES
- `tests/test_prompts.py` — Extended: few-shot exemplar count assertion (>=4 DEXTER: markers), banned-mode phrase check, placeholder-fill round-trip (no unfilled {key} after build_chat_prompt call)

## Decisions Made

**D-06 (system prompt few-shot rewrite):** DEXTER_SYSTEM_PROMPT now leads with an identity statement (arrogant/superior/dry/contemptuous; humor from specific recall of tracked behavior), followed by 3 explicitly-stated banned modes (no bot-self-awareness/fourth-wall, no pop-psych, no self-deprecation), language rules, response rules, and 6 few-shot USER/DEXTER exemplar pairs. The canonical formula line "marcus. back with the drake. forty-seven plays last week. one artist, one emotion, zero growth. impressive commitment to being boring." is embedded as an exemplar.

**Voice standard approval:** User reviewed personality/roasts.py and the rewritten DEXTER_SYSTEM_PROMPT on 2026-06-11 and approved the voice register with no wording changes requested. This locks the voice standard for Phase 3.

**"Maximize AI" for ambient roasts (OVERRIDES D-08 for join/leave/late-night):** Voice JOIN, LEAVE, and LATE-NIGHT roasts will attempt a priority-2 Gemini-generated personalized line FIRST — riffing on the user's real tracked data (song history, top artists, play counts) — falling back to the personality/roasts.py template pools only when the shared 15 RPM limiter would wait >10s or Gemini errors. Channel-move, idle, startup, and status rotation remain static template-only. This overrides D-08's "never let ambient roasts touch the live API" disposition for those three triggers. DOWNSTREAM IMPACT: plan 03-04 (EventsCog wiring) must implement the Gemini-first-with-template-fallback path for join/leave/late-night, mirroring the priority-2 + GeminiRateLimitError fallback pattern specified for 03-05's repeat-song/milestone roasts, and must include a per-user taste lookup to supply the few-shot voice builder with real tracked data. 03-01's template pools are unaffected — they serve as the fallback layer.

## TDD Gate Compliance

- RED gate commit: `8333ec7` — `test(03-01): add failing tests for DEXTER_SYSTEM_PROMPT few-shot rewrite (D-06) [RED gate]`
- GREEN gate commit: `1d52455` — `feat(03-01): rewrite DEXTER_SYSTEM_PROMPT with few-shot exemplars (D-06) [GREEN gate]`
- Both gates present in git history in correct order. Compliant.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

**Known environment limitation (pre-existing, not a regression):** Test files that import discord, google-generativeai, aiosqlite, or pytest_asyncio fail at collection in this environment because those packages are not installed. This affects the broader test suite (`cogs/`, `services/`, etc.) but does NOT affect 03-01's pure-Python deliverables. The 39 personality tests (test_roasts.py, test_prompts.py) and 89 total pure-Python tests all pass. This limitation will be relevant to verifying Waves 2 and 3 plans which touch cog/service code.

## User Setup Required

None — no external service configuration required. DEXTER_CHANNEL_ID and STREAK_TIMEZONE are read from environment variables at runtime (defaults: None / "America/New_York").

## Next Phase Readiness

- All Phase 3 config constants are locked and readable by 03-02, 03-03, 03-04, 03-05, 03-06
- personality/roasts.py template pools are the fallback layer for all ambient roast features in 03-04 and 03-05
- Voice standard is approved and locked — downstream plans must match this register
- 03-04 (EventsCog) must implement Gemini-first-with-template-fallback for join/leave/late-night per the "Maximize AI" decision above — this is a binding design constraint, not optional
- 03-02 and 03-03 are unblocked (Wave 1, parallel-capable with each other now that 03-01 is complete)

---
*Phase: 03-alive*
*Completed: 2026-06-11*
