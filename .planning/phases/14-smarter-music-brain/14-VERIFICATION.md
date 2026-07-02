---
status: human_needed
phase: 14-smarter-music-brain
verified: 2026-07-03
requirements: [BRAIN-01, BRAIN-02, BRAIN-03]
must_haves_total: 4
must_haves_verified: 4
plans_complete: 5
plans_total: 5
tests: "761 passed / 105 skipped (full suite); 291 passed / 7 skipped (phase files)"
code_review: "14-REVIEW.md — 1 blocker + 3 warnings, all fixed"
---

# Phase 14 — Smarter Music Brain — Verification

**Goal**: Dexter's auto-queue, discovery, and jam features become taste-aware — using the
Phase 13 foundation plus live SQL — a genuinely better DJ, not a bland server-average shuffler.

**Verdict**: All 4 success criteria are structurally satisfied in the codebase and locked by
tests. Status is `human_needed` because the taste-behavior payoff (skip avoidance, adjacency
relevance, jam suggestion quality) and the WR-01 tz-bucketing SQL are only meaningfully
observable against a live Discord + populated Neon DB — consistent with the milestone's parked
live-runtime UAT tail. No code gaps.

## Success Criteria

### 1. BRAIN-01 — Auto-queue stops re-suggesting recently-skipped tracks/artists ✓
- `cogs/ai.py::try_auto_queue`: guild-scoped `get_recently_skipped()` (database.py:1371) is
  fetched and passed as a **negative hint** into the recommendation prompt
  (`recently_skipped=...`, cogs/ai.py:350), degrading to `[]` on failure (non-fatal).
- Independent **hard post-filter**: `is_recently_skipped_artist()` (logic/autoqueue.py) runs as
  a second gate after `validate_youtube_match`, dropping any surviving candidate whose artist
  matches a recently-skipped artist (cogs/ai.py:409–410). Gemini-in-the-loop + SQL, no ML model.
- Locked by `tests/test_autoqueue_wiring.py` (D-01/D-02/D-03 + scar #2 gating guard).

### 2. BRAIN-02 — Discovery grounded in real co-occurrence SQL, never hallucinated ✓
- `/discover` (cogs/music.py:2140): anchor = invoker's guild-scoped top artist via
  `get_user_top_artist()` (Option B); adjacency via `get_artist_cooccurrence()` over
  `song_history`. The queued track is `adjacent_artists[0]` — an **SQL-derived** value; Gemini is
  restricted to voice-only commentary (`build_discover_commentary_prompt`) and is **never parsed**
  into a recommendation (accuracy firewall intact).
- WR-01 fix: co-occurrence day bucket is tz-correct — `date_trunc('day', queued_at AT TIME ZONE
  $4)` with `tz_name` bound as a positional param (database.py:1459/1465), honoring
  `STREAK_TIMEZONE` per the D-06/D-17 calendar-day discipline. No SQL string interpolation.
- CR-01 fix (blocker): `DiscoverQueueView.queue_button` now connects to the presser's voice
  channel on the cold path (cogs/music.py:580) and persists the queue (line 596) before
  `_play_track`, mirroring the primary `/play` path — no more false "queued" success while idle.
- Locked by `tests/test_discover.py` (source-assertions + 5 behavioral tests driving the
  bot-idle connect/persist/play path).

### 3. BRAIN-03 — Jam suggestions pass hallucination validation before queueing ✓
- `/jam suggest <name>` (cogs/library.py:1049): seeds Gemini with the named jam's **existing**
  tracks (`build_jam_suggestion_prompt`), then validates **every** suggestion against real
  YouTube search results via `validate_youtube_match` — the token-set containment validator
  reused verbatim from `logic/autoqueue.py` (no reimplementation). Only survivors are offered;
  a one-shot `JamSuggestConfirmView` writes to the shared snapshot only on explicit Confirm.
- Locked by `tests/test_jam_suggest.py` (28 tests).

### 4. Multi-user safety — aggregate/server-scoped, no cross-user leakage ✓
- `get_artist_cooccurrence` is a guild-WIDE aggregate exposing only artist names, not per-user
  rows. `/jam` reads/writes are keyed on `guild_id` (cross-guild isolation enforced in DB).
  `/discover` anchor is the invoker's own top artist; adjacency is a server aggregate.

## Requirement Traceability
| ID | Status (REQUIREMENTS.md) |
|----|--------------------------|
| BRAIN-01 | Complete |
| BRAIN-02 | Complete |
| BRAIN-03 | Complete |

All PLAN-frontmatter requirement IDs accounted for; no orphans.

## Evidence
- Full suite: **761 passed / 105 skipped** (baseline 754 + 7 new behavioral tests from the fix pass).
- Phase test files: **291 passed / 7 skipped** (live-DB cases skip cleanly with no local Postgres).
- Code review: `14-REVIEW.md` — 1 blocker (CR-01) + 3 warnings (WR-01/02/03) all fixed with atomic
  `fix(14):` commits; 4 INFO findings triaged as design decisions / out of scope.

## Human Verification Needed (parked — live Discord + populated Neon)
1. **BRAIN-01 behavior**: over a real session, auto-queue visibly stops re-suggesting an artist
   the user just skipped.
2. **BRAIN-02 relevance + tz**: `/discover` returns genuinely adjacent artists from real history;
   `AT TIME ZONE` bucketing groups cross-midnight co-plays on the correct `STREAK_TIMEZONE` day
   (only exercised by live-DB integration tests).
3. **BRAIN-02 playback**: `/discover` "queue it" from an **idle** bot actually joins voice and
   plays (CR-01 fix — confirm end-to-end in a real voice channel).
4. **BRAIN-03 quality**: `/jam suggest` produces plausible, validation-surviving additions to a
   real server jam.
