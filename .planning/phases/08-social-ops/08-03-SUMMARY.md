---
phase: 08-social-ops
plan: 03
subsystem: ops
tags: [leaderboard, stats, health, ops, discord-embed, ops-02, ops-03, social-02]

# Dependency graph
requires:
  - phase: 08-01
    provides: get_leaderboard_songs, get_leaderboard_skips, get_leaderboard_streaks, get_daily_stats_row, get_images_today_global, increment_daily_stat (total_errors), GeminiService.rpm_usage, LEADERBOARD_TOP_N
  - phase: 08-02
    provides: /roast command (same cog module pattern)
provides:
  - cogs/ops.py: OpsCog with /leaderboard + /stats slash commands + gather_bot_metrics helper
  - utils/embeds.py: leaderboard_embed, stats_embed, COLOR_LEADERBOARD, COLOR_STATS
  - personality/responses.py: LEADERBOARD_SONGS_COMMENTARY, LEADERBOARD_STREAK_COMMENTARY, LEADERBOARD_SKIPS_COMMENTARY, LEADERBOARD_EMPTY
  - bot.py: degraded /health body (always HTTP 200), cogs.ops registration, bot._start_monotonic
  - utils/logger.py: total_errors increment at central log_to_discord site with recursion guard
  - tests/test_health_endpoint.py: test_health_ok, test_health_degraded_db, test_health_always_200
affects: [cogs/ops.py, utils/embeds.py, personality/responses.py, bot.py, utils/logger.py]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Function-scope import (from cogs.ops import gather_bot_metrics inside health handler) to avoid circular import at module load — same pattern as restore_queues in bot.py"
    - "Inner try/except pass recursion guard on total_errors increment in log_to_discord — DB failure never re-enters the logger"
    - "Inline await bot.is_owner() before any data access in /stats — no decorator pattern, consistent with bot.py /sync owner check"
    - "gather_bot_metrics shared helper pattern — single source of truth for both /stats embed and /health degraded check (D-31)"

key-files:
  created:
    - cogs/ops.py
    - tests/test_health_endpoint.py
  modified:
    - utils/embeds.py
    - personality/responses.py
    - bot.py
    - utils/logger.py

key-decisions:
  - "gather_bot_metrics lives in cogs/ops.py (not utils/) — it references bot.cogs.get('MusicCog') so it is cog-layer, not utility-layer; function-scope import from health handler sidesteps circular import (A1 from RESEARCH)"
  - "stats_embed has 13 fields (not 14 as stated in plan prose) — the research code spec #6 yields 13 fields; plan prose was off by one; 13 is well under Discord's 25-field limit"
  - "bot._start_monotonic set after restore_queues in _initialize_once — uptime measures time since fully-ready state, not module load"
  - "import json added at module scope in bot.py — needed by the degraded health handler body"

# Metrics
duration: 18min
completed: 2026-06-19
---

# Phase 08 Plan 03: Social & Ops Surface Summary

**Ops cog with /leaderboard (3-section guild-scoped embed), /stats (owner-only ephemeral), degraded-but-always-200 /health (via shared gather_bot_metrics), and total_errors tracking at the central error-log site**

## Performance

- **Duration:** 18 min
- **Started:** 2026-06-19T07:30:00Z
- **Completed:** 2026-06-19T07:52:00Z
- **Tasks:** 3
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments

- `cogs/ops.py` (new): `gather_bot_metrics` shared helper (DB probe, gateway check, queue count, uptime via `_start_monotonic`), `OpsCog` with `/leaderboard` (public defer, guild-scoped Plan-01 helpers, T-08-10 parameterized) and `/stats` (inline `is_owner` gate FIRST before any data access, ephemeral defer, T-08-09)
- `utils/embeds.py`: `leaderboard_embed` (3 sections: songs/streak/skips, top-5 + dry commentary per section, per-section empty-state D-17), `stats_embed` (13 inline fields: today activity + Gemini RPM + image cap + bot-state + Koyeb/Neon footer), `COLOR_LEADERBOARD` + `COLOR_STATS`
- `personality/responses.py`: 4 new pools — `LEADERBOARD_SONGS_COMMENTARY`, `LEADERBOARD_STREAK_COMMENTARY`, `LEADERBOARD_SKIPS_COMMENTARY`, `LEADERBOARD_EMPTY` (all lowercase, dry, D-32)
- `bot.py`: `import json` added; health handler upgraded to degraded-aware body via function-scope `gather_bot_metrics` import (Pitfall 6 fallback); `cogs.ops` added to cog-load tuple; `bot._start_monotonic` set at end of `_initialize_once`
- `utils/logger.py`: `log_to_discord` now increments `total_errors` after successful `channel.send`; inner `try/except Exception: pass` is the recursion guard (T-08-12/Pitfall 5)
- `tests/test_health_endpoint.py` (new): 3 tests — `test_health_ok`, `test_health_degraded_db`, `test_health_always_200` — all green

## Task Commits

1. **Task 1: leaderboard/stats embeds + commentary pools** — `c5e0c98` (feat)
2. **Task 2: cogs/ops.py + bot.py registration** — `1401572` (feat)
3. **Task 3: degraded /health + total_errors + tests** — `8794761` (feat)

## Files Created/Modified

- `cogs/ops.py` — OpsCog (/leaderboard + /stats) + gather_bot_metrics module-level helper
- `tests/test_health_endpoint.py` — 3 health endpoint tests (all green)
- `utils/embeds.py` — leaderboard_embed, stats_embed, COLOR_LEADERBOARD, COLOR_STATS; personality pool imports
- `personality/responses.py` — 4 leaderboard commentary/empty pools
- `bot.py` — json import, degraded health handler, cogs.ops registration, _start_monotonic
- `utils/logger.py` — total_errors increment with recursion guard in log_to_discord

## Decisions Made

- `stats_embed` produces 13 fields (not 14): the plan prose stated "14 inline fields" but the authoritative research code spec #6 yields 13 fields (5 today-activity + 2 quota + 4 bot-state + 2 health). 13 is well within Discord's 25-field limit; no functional impact.
- `gather_bot_metrics` stays in `cogs/ops.py` (not `utils/`): it accesses `bot.cogs.get("MusicCog")` and is cog-layer logic; function-scope `from cogs.ops import gather_bot_metrics` inside the health handler sidesteps the circular-import risk (RESEARCH A1 assumption was LOW risk, confirmed correct).
- `import time as _time` inside `_initialize_once` to set `bot._start_monotonic`: avoids name clash with any future `time` usage at module scope; `_time.monotonic()` is idiomatic for this scoped alias.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] stats_embed field count: 13, not 14**
- **Found during:** Task 1 verification
- **Issue:** The plan prose says "14 inline fields" but counting the research code spec #6 fields yields 13: 5 (today activity) + 2 (quota) + 4 (bot-state) + 2 (health) = 13. The plan prose count was off by one.
- **Fix:** Implemented exactly 13 fields matching the research code spec; updated SUMMARY docs to reflect 13.
- **Files modified:** `utils/embeds.py`
- **Committed in:** `c5e0c98` (Task 1 commit)
- **Impact:** None — 13 fields is within Discord's 25-field limit and matches the research-specified layout exactly.

---

**Total deviations:** 1 auto-corrected (Rule 1 — spec inconsistency resolved in favour of research code)

## Known Stubs

None — all embed builders use real data parameters; no hardcoded placeholders.

## Threat Flags

None — no new network endpoints beyond the existing /health route, no new auth paths. The /health degraded body strictly follows D-27 (no internal state keys in response body).

## Self-Check

### Files Exist
- `cogs/ops.py` — created in this plan
- `tests/test_health_endpoint.py` — created in this plan
- `utils/embeds.py` — modified (COLOR_LEADERBOARD, COLOR_STATS, leaderboard_embed, stats_embed present)
- `personality/responses.py` — modified (4 new pools present)
- `bot.py` — modified (degraded health handler, cogs.ops in tuple, _start_monotonic)
- `utils/logger.py` — modified (total_errors increment)

### Commits Exist
- c5e0c98 ✓
- 1401572 ✓
- 8794761 ✓

### Tests
- `python -m pytest tests/test_health_endpoint.py -x` → 3 passed

## Self-Check: PASSED
