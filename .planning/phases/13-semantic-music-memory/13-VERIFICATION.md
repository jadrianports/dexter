---
phase: 13-semantic-music-memory
verified: 2026-07-02T14:27:42Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
---

# Phase 13: Semantic Music Memory Verification Report

**Phase Goal:** Dexter's listening history becomes a retrievable long-term memory — a new `taste_episode` kind distilled number-free onto the existing `user_memories` vector store — feeding every downstream consumer in this milestone.
**Verified:** 2026-07-02T14:27:42Z
**Status:** passed
**Re-verification:** No — initial verification (post code-review fix pass)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Stored memory for a user includes number-free "taste episode" facts distilled from real listening activity, no raw counts embedded (TASTE-01) | ✓ VERIFIED | `logic/taste.py::summarize_taste` emits only fixed templates (`_PHRASE_TEMPLATES`), never interpolates a count; digit-free firewall test (`test_taste_logic.py::test_no_phrase_contains_a_digit`) passes. `bot.py::taste_distill_batch` builds `raw_text` solely by joining `summarize_taste` phrases (bot.py:1017-1019). `services/memory.py::distill_and_remember` exempts only `contains_number` (not `is_sensitive`) for `kind=="taste_episode"`, and only because summarize_taste's own output is number-free by construction — a digit that survives is a legitimate artist name, not a raw count (WR-13-02 fix confirmed at services/memory.py:492-501). |
| 2 | Taste-episode memories carry their own salience base weight and decay tier, distinct from and tunable separately from Phase 11's general-fact defaults (TASTE-02) | ✓ VERIFIED | `config.MEMORY_SALIENCE_BASE_WEIGHTS["taste_episode"] = 0.4` (below `MEMORY_DECAY_SALIENCE_FLOOR = 0.5`, D-04). `config.MEMORY_DECAY_DAYS_BY_KIND = {"taste_episode": 30}` vs `MEMORY_DECAY_DAYS = 90`. `services/memory.py::remember` insert path calls `resolve_decay_days(kind, default_days=config.MEMORY_DECAY_DAYS, kind_overrides=config.MEMORY_DECAY_DAYS_BY_KIND)` (memory.py:286-292); Phase 11 kinds fall back to 90d unchanged (`.get` semantics), verified live: `python -c "import config; assert config.TASTE_DECAY_DAYS < config.MEMORY_DECAY_DAYS ..."` exits 0. |
| 3 | Taste episodes are written by a background task on its own schedule, distinct from the existing distill-batch/decay-sweep loops, without spiking load on the Neon pool (TASTE-03) | ✓ VERIFIED | `bot.py::taste_distill_batch` is a `@tasks.loop(time=datetime.time(hour=config.TASTE_DISTILL_BATCH_HOUR, minute=0))` (05:00 UTC) — distinct from `cache_cleanup` (hourly), `memory_sweep` (02:30), `memory_distill_batch` (03:00), `ytdlp_update` (04:00). D-08 min-activity gate (`has_min_activity`) bounds fan-out; per-artist query is baseline-bounded and index-aligned (`idx_history_guild`). Registered at all 3 boot sites (see Key Link table). |
| 4 | Existing memory-backed behavior (ambient callback roasts, `/roast`/`/ask` wiring) continues to work unchanged — the new kind is additive, not disruptive (ROADMAP SC4) | ✓ VERIFIED | `services/memory.py::recall()` maps `search_memories` rows to `MemoryFact` by explicit named field access (kind is fetched but not consumed by recall — new `kind` column addition to `search_memories` SELECT is inert for the read path). Full suite: `tests/test_memory.py` + `tests/test_database_phase11.py` — 108 passed, 6 skipped, 0 failed (Phase 11 regression-free). Full project suite: 650 passed, 98 skipped, 0 failed. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `config.py` | TASTE_* knobs, taste_episode salience weight, MEMORY_DECAY_DAYS_BY_KIND | ✓ VERIFIED | `# --- Phase 13: Semantic Music Memory ---` block (config.py:192-209): all 10 TASTE_* constants, extended `MEMORY_SALIENCE_BASE_WEIGHTS["taste_episode"]=0.4`, new `MEMORY_DECAY_DAYS_BY_KIND` map. |
| `logic/taste.py` | has_min_activity, classify_artist, summarize_taste, resolve_decay_days — pure | ✓ VERIFIED | All 4 functions + `TastePattern` enum present; no discord/asyncio/asyncpg/random imports, no `datetime.now()` (grep clean — only docstring mentions). 24 mock-free tests, all pass. |
| `database.py` | get_active_taste_users, get_user_artist_activity, refresh_memory_expiry | ✓ VERIFIED | All 3 helpers present (database.py:1015, 1284, 1312), positional `$N` params only, `get_user_artist_activity` scoped `WHERE guild_id = $1 AND user_id = $2`, `refresh_memory_expiry` is `UPDATE ... SET expires_at = $2 WHERE id = $1` only. |
| `services/memory.py` | kind-aware insert horizon + self-refresh-on-dedup gated on MATCHED row's kind (CR-01 fix) | ✓ VERIFIED | `remember()` step 3 gates refresh on `nearest_kind` (the row returned by `search_memories`, which now selects `kind`), not the incoming write's `kind` (memory.py:256-274). `database.search_memories` SELECT includes `kind` (database.py:934). |
| `bot.py` | taste_distill_batch @tasks.loop + before_loop/error pair + 3-site registration | ✓ VERIFIED | Loop at bot.py:942-1038; `.before_loop`/`.error` at 1041-1049; start-guard at 466-467; `_cleanup_partial_init` stop-list at 285; both "Loops stopped:" docstrings updated (268-269, 282-283). Per-user body fully wrapped in try/except (WR-01 fix, bot.py:998-1036) — DB fetch is no longer outside the guard. |
| `tests/test_taste_logic.py` | mock-free unit tests locking pure logic + number-free firewall | ✓ VERIFIED | 24 tests, 0 failures. |
| `tests/test_database_phase13.py` | live-DB integration tests (skip cleanly without Postgres) | ✓ VERIFIED | 6 source-assertion tests pass; 5 live-DB tests skip cleanly (no local Postgres) — consistent with established project convention (Phase 11/12). |
| `tests/test_memory_taste.py` | regression lock proving taste self-refreshes and Phase 11 kinds unchanged, incl. CR-01 cross-kind leak | ✓ VERIFIED | 11 tests, 0 failures — includes `test_taste_episode_near_duping_daily_batch_does_not_refresh`, which directly reproduces the CR-01 leak scenario (a taste_episode write whose nearest neighbor is a `daily_batch` row) and asserts `refresh_memory_expiry` is never called. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `logic/taste.py::summarize_taste` | number-free output | no digit ever appears in a produced phrase | ✓ WIRED | Fixed templates only; firewall test passes. |
| `config.MEMORY_SALIENCE_BASE_WEIGHTS` | `taste_episode` | new dict key below MEMORY_DECAY_SALIENCE_FLOOR | ✓ WIRED | `0.4 < 0.5` confirmed live. |
| `get_user_artist_activity` | `song_history` | `WHERE guild_id = $1 AND user_id = $2` | ✓ WIRED | Confirmed via source read + `test_no_string_interpolation`. |
| `refresh_memory_expiry` | `user_memories.expires_at` | `UPDATE ... SET expires_at = $2 WHERE id = $1` | ✓ WIRED | Confirmed via source read + `test_refresh_memory_expiry_touches_only_expires_at`. |
| `services/memory.py::remember (insert path)` | `config.MEMORY_DECAY_DAYS_BY_KIND` | `resolve_decay_days(kind, default_days=..., kind_overrides=...)` | ✓ WIRED | memory.py:286-292. |
| `services/memory.py::remember (dedup path)` | `database.refresh_memory_expiry` | gated on **matched row's** kind, `nearest_kind in config.MEMORY_DECAY_DAYS_BY_KIND` | ✓ WIRED | memory.py:270-274 — corrected from the original (incoming-kind-gated) implementation per CR-01. |
| `bot.py::taste_distill_batch` | `database.get_active_taste_users` / `get_user_artist_activity` | structured song_history reads | ✓ WIRED | bot.py:976, 999-1005. |
| `bot.py::taste_distill_batch` | `logic.taste.summarize_taste` / `has_min_activity` | number-free pre-bucketing before any Gemini call | ✓ WIRED | bot.py:988-990, 1008-1013. |
| `bot.py::taste_distill_batch` | `memory_service.distill_and_remember` | `kind='taste_episode'`, base_salience from config | ✓ WIRED | bot.py:1024-1030. |
| `_cleanup_partial_init` | `taste_distill_batch` | stop-list tuple | ✓ WIRED | bot.py:285. |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|----------------|-------------|--------|----------|
| TASTE-01 | 13-01, 13-02, 13-04 | Distills listening activity into number-free taste episode facts, stored as new `kind` in existing `user_memories` store | ✓ SATISFIED | `logic/taste.py` firewall + `bot.py::taste_distill_batch` write path + WR-02 exemption logic. |
| TASTE-02 | 13-01, 13-02, 13-03 | Taste episodes use own salience base weight and decay tier, not inherited from Phase 11 defaults | ✓ SATISFIED | `config.MEMORY_SALIENCE_BASE_WEIGHTS["taste_episode"]`, `MEMORY_DECAY_DAYS_BY_KIND`, `resolve_decay_days` wiring, CR-01-fixed self-refresh. |
| TASTE-03 | 13-02, 13-04 | Background task writes taste episodes on distinct schedule, no thundering-herd, following `@tasks.loop` + failure-surfacing convention | ✓ SATISFIED | `taste_distill_batch` at 05:00 UTC, distinct from all other loops; `.error` routes to `_post_loop_error` (same convention as `memory_distill_batch`). |

No orphaned requirements — REQUIREMENTS.md maps only TASTE-01/02/03 to Phase 13, and all three appear in at least one plan's `requirements:` frontmatter field.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | None found | — | Grep for TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER across all phase-modified files (`config.py`, `logic/taste.py`, `database.py`, `services/memory.py`, `bot.py`, phase-13 test files) returned zero debt markers (two incidental "placeholders" hits were the phrase "positional placeholders" in existing docstrings, not stub markers). |

**Code review (13-REVIEW.md) disposition:** 1 critical (CR-01) + 2 warnings (WR-01, WR-02) + 1 info (IN-01) found. CR-01, WR-01, WR-02 are all confirmed FIXED in the current codebase (commits `3707b5b`, `fbe90a2`, `34e8d33`, `b2f6ff6`) with dedicated regression tests. IN-01 (unused `TASTE_BAND_HEAVY_PLAYS`/`TASTE_BAND_FEW_PLAYS` config constants — dead configuration, not consumed by `summarize_taste`'s fixed-template approach) remains unfixed but is an info-level, non-blocking observation about reserved-for-later knobs, not a functional defect.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Config contract (decay/salience below floor, kind-map) | `python -c "import config; assert config.TASTE_DECAY_DAYS < config.MEMORY_DECAY_DAYS; assert config.MEMORY_SALIENCE_BASE_WEIGHTS['taste_episode'] < config.MEMORY_DECAY_SALIENCE_FLOOR; assert config.MEMORY_DECAY_DAYS_BY_KIND['taste_episode'] == config.TASTE_DECAY_DAYS"` | `ok` | ✓ PASS |
| All modules compile | `python -m py_compile bot.py database.py services/memory.py config.py logic/taste.py` | exit 0 | ✓ PASS |
| logic/taste.py purity | `grep -nE "import (discord\|asyncio\|asyncpg\|random)\|datetime\.now" logic/taste.py` | only a docstring line mentioning the constraint, no real import | ✓ PASS |
| CR-01 cross-kind leak regression | `pytest tests/test_memory_taste.py -k near_duping` | 1 passed | ✓ PASS |
| Full project test suite | `pytest -q` | 650 passed, 98 skipped, 0 failed | ✓ PASS |
| Phase-13-only test suites | `pytest tests/test_taste_logic.py tests/test_database_phase13.py tests/test_memory_taste.py -q` | 41 passed, 5 skipped | ✓ PASS |
| Phase 11 regression check | `pytest tests/test_memory.py tests/test_database_phase11.py -q` | 108 passed, 6 skipped | ✓ PASS |

### Human Verification Required

None. All must-haves are structural/config/logic claims fully verifiable via source inspection and the automated test suite (unit + source-assertion tests; live-DB integration tests skip cleanly without Postgres, consistent with established project convention — see Phase 12's `passed` precedent for the same skip-clean pattern). No visual, real-time, or live-Discord-session behavior is part of this phase's success criteria — it is a pure background-batch/data-plumbing phase.

### Gaps Summary

No gaps. All 4 observable truths (3 phase-specific TASTE-0X + 1 roadmap "additive, not disruptive" regression criterion) are verified against the live codebase, not SUMMARY.md claims. The one critical code-review finding (CR-01: D-05 self-refresh gated on the wrong kind, capable of corrupting Phase 11 decay horizons on a cross-kind dedup hit) was independently confirmed FIXED by reading `services/memory.py`/`database.py` directly and by running the dedicated regression test (`test_taste_episode_near_duping_daily_batch_does_not_refresh`), not by trusting the SUMMARY/REVIEW narrative alone. Both warnings (WR-01 per-user isolation gap, WR-02 contains_number over-blocking numbered artist names) are also confirmed fixed in the source. The one remaining info-level item (IN-01, unused band-threshold config constants) is non-blocking and does not affect goal achievement.

---

*Verified: 2026-07-02T14:27:42Z*
*Verifier: Claude (gsd-verifier)*
