---
status: passed
phase: 12-richer-music-ux
verified: 2026-06-30
requirements: [UX-01, UX-02, UX-03, UX-04]
summary:
  total_criteria: 4
  passed: 4
  failed: 0
  human_needed: 0
test_suite: "608 passed, 93 skipped, 0 failed"
code_review: "0 blocker, 4 warning, 5 info (advisory, non-blocking)"
---

# Phase 12: Richer Music/UX — Verification

**Goal:** Round out the music experience — per-server shared playlists, visible
skip-rate analytics, a third lyrics fallback, and hallucination-validated
auto-queue — so the existing v1.1 playback/social surfaces get noticeably richer
and more trustworthy.

**Verdict: PASSED** — all 4 success criteria are implemented in the live codebase
(not just claimed in summaries), the full test suite is green, and code review
surfaced no blockers.

## Success Criteria

### 1. Guild-scoped shared playlists ("jams"), distinct from global favorites — UX-01 ✓
- `guild_jams` table added to `SCHEMA_SQL` in `database.py` (PK on `guild_id`+`name`,
  JSONB snapshot, `idx_jams_guild` index) — separate table from user favorites.
- 5 async helpers in `database.py` (`save_jam`/`get_jam`/`list_jams`/`delete_jam`/
  `count_jams`, lines 785–881), all `$N`-parameterized and keyed on `guild_id`.
- `/jam` `app_commands.Group` in `cogs/library.py:673` with save/add/load/list/delete
  subcommands — explicitly guild-scoped vs the user-global `/playlist` group (D-01).
- Cross-guild isolation asserted in `tests/test_database_phase12.py`.

### 2. Skip-rate analytics surfaced to users — UX-02 ✓
- `compute_skip_rate()` pure logic in `logic/skip_stats.py:13` with min-plays floor
  and 0/0 guard.
- `get_user_skip_rate` DB helper (parameterized) + dedicated public `/skips` command
  in `cogs/ops.py:200` rendering a server most-skipped list + personal skip-rate
  footer via `skips_embed` in `utils/embeds.py`.

### 3. /lyrics third fallback source — UX-03 ✓
- Three-source chain Genius → AZLyrics → LRCLIB in `services/lyrics.py`
  (`_get_lrclib` at line 350, wired into `get_lyrics` at line 277).
- `strip_lrc_headers()` (line 86) removes LRC metadata before sanitize; LRCLIB host
  hard-pinned (`_LRCLIB_BASE`), params URL-encoded via aiohttp `params=`, body cap +
  `async with` session cleanup.

### 4. Auto-queue validates Gemini suggestions against real YouTube results — UX-04 ✓
- `validate_youtube_match()` pure validator in `logic/autoqueue.py:64` (token-subset
  match, noise/stop-word stripping).
- `cogs/ai.py:327` validates each widened search candidate and falls through to the
  next Gemini suggestion when none pass, rejecting hallucinated tracks before queueing.

## Requirement Traceability
All four phase requirement IDs (UX-01..UX-04) map 1:1 to plans 12-01..12-04, each
with a committed SUMMARY.md and marked complete in REQUIREMENTS.md / ROADMAP.md.

## Evidence
- Full test suite: **608 passed, 93 skipped, 0 failed** (regression gate, all prior
  phases included).
- Schema drift gate: clean (idempotent `SCHEMA_SQL` applied at `init_db()`; no ORM
  push step to drift).
- Code review (`12-REVIEW.md`): 0 blocker, 4 warning, 5 info.

## Non-blocking follow-ups (from code review — not phase blockers)
- **WR-01** `services/lyrics.py` — 500 KB body guard runs after `await resp.text()`
  has already buffered; doesn't bound memory as the docstring claims (trusted hosts).
- **WR-02** `cogs/ai.py:380` — `queue.current_index` mutated before the
  `should_start_playback` gate; latent in the "audio already flowing" branch, untested.
- **WR-03** `cogs/ai.py:415` — fire-and-forget `create_task` with no retained ref can
  be GC'd, silently dropping the memory write.
- **WR-04** `tests/conftest.py` — teardown omits `user_memories`, leaking rows.

These are recorded for a future polish/hardening pass and do not affect the phase
goal verdict.
