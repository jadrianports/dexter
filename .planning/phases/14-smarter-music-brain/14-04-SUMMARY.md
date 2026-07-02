---
phase: 14-smarter-music-brain
plan: 04
subsystem: music-brain
tags: [discord-ui-view, gemini, sql-aggregate, discovery, confirm-first]

# Dependency graph
requires:
  - phase: 14-01
    provides: database.get_user_top_artist, database.get_artist_cooccurrence SQL helpers
  - phase: 14-02
    provides: personality.prompts.build_discover_commentary_prompt (D-04 firewall prompt builder)
provides:
  - "cogs/music.py::discover — /discover slash command (BRAIN-02): SQL-derived artist adjacency, Gemini voice-only commentary"
  - "cogs/music.py::DiscoverQueueView — one-shot confirm-to-queue discord.ui.View (D-05 confirm-first)"
  - "personality/responses.py::DISCOVER_NO_HISTORY — in-character cold-start response pool"
affects: [14-05-jam-suggest-command]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "One-shot discord.ui.View (finite timeout, message-ref-for-on_timeout, NOT registered in setup_hook) as the confirm-first UX for a single button action — sibling pattern to LyricsPageView/HistoryPageView's message-tracking idiom, distinct from NowPlayingView's persistent timeout=None controller"
    - "Bare `pick_random` (re-exported personality.roasts -> personality.responses) reused for a new response pool instead of introducing a second import alias, avoiding the pre-existing pick_random_r alias collision in cogs/music.py"

key-files:
  created:
    - tests/test_discover.py
  modified:
    - cogs/music.py
    - personality/responses.py

key-decisions:
  - "Used the existing bare `pick_random` name (imported from personality.roasts, which re-exports personality.responses.pick_random) rather than the file's `pick_random_r` alias, since cogs/music.py already imports both under different names — this keeps DISCOVER_NO_HISTORY calls textually identical across the codebase's two equivalent import paths"
  - "Confirm-to-queue view seeds only the TOP adjacent artist (adjacent_artists[0]) for the queue button, keeping the interaction to a single unambiguous action rather than a per-artist picker (plan's stated one-shot button, not a multi-select)"

patterns-established:
  - "One-shot (non-persistent) confirm view pattern for /discover — reusable template for /jam suggest's propose-and-confirm view (plan 14-05), which needs the same finite-timeout / not-setup_hook-registered shape per 14-PATTERNS.md"

requirements-completed: [BRAIN-02]

# Metrics
duration: 15min
completed: 2026-07-02
---

# Phase 14 Plan 4: /discover Command Summary

**`/discover` slash command surfacing 100%-SQL-derived server artist adjacency (invoker-anchored top artist -> guild-wide same-day co-occurrence) with Gemini restricted to voice-only commentary, plus a one-shot confirm-to-queue button — never a silent auto-queue.**

## Performance

- **Duration:** ~15 min
- **Tasks:** 2 completed
- **Files modified:** 2 (cogs/music.py, personality/responses.py) + 1 created (tests/test_discover.py)

## Accomplishments
- Added `/discover` to `MusicCog`: reads the invoker's guild-scoped top artist via `get_user_top_artist`, then `get_artist_cooccurrence` for same-guild-day adjacent artists — these SQL rows are the recommendation, never Gemini's output
- Gemini (`build_discover_commentary_prompt`) supplies voice-only commentary wrapping the fixed SQL picks; its reply is used as plain text with no JSON/suggestion parsing step (D-04 firewall), with a plain-sentence fallback if Gemini returns nothing
- Two independent cold-start guards (empty anchor rows, empty adjacent rows) both degrade to `pick_random(DISCOVER_NO_HISTORY)`, never raising an error (D-05)
- Added `DiscoverQueueView`, a one-shot `discord.ui.View` (finite timeout, not `timeout=None`, not registered in `setup_hook`) with a single "queue it" button seeded with the top adjacent artist; on press it resolves via `async_search`/`async_extract`, applies the `MAX_SONG_DURATION_SECONDS` cap, builds a `Track`, and starts playback only through `should_start_playback` (scar #2 respected) — attached to the `/discover` follow-up only on the adjacency-hit path, never on cold-start
- `personality/responses.py::DISCOVER_NO_HISTORY` — new 4-line in-character cold-start pool

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the /discover command core (anchor -> adjacency -> commentary -> cold-start)** - `68497e1` (feat)
2. **Task 2: Add the confirm-to-queue view for /discover (D-05)** - `b5e0b78` (feat)

## Files Created/Modified
- `cogs/music.py` - Added `datetime`/`timedelta`/`timezone` and `should_start_playback` imports; added `get_user_top_artist`/`get_artist_cooccurrence` to the `database` import block; added `build_discover_commentary_prompt` and `DISCOVER_NO_HISTORY` imports; added the `discover` slash command method; added the `DiscoverQueueView` class
- `personality/responses.py` - Added `DISCOVER_NO_HISTORY: list[str]` (4 in-character cold-start lines) under a new `# --- Phase 14: /discover cold-start (D-05) ---` section
- `tests/test_discover.py` - Source-assertion test suite (21 tests) mirroring the `tests/test_autoqueue_wiring.py` `inspect.getsource` convention: firewall (`get_user_top_artist(`, `get_artist_cooccurrence(`, `build_discover_commentary_prompt(`, no `parse_suggestions`), cold-start (two distinct guards), and the confirm-to-queue view (finite timeout, not in `setup_hook`, button wiring, no stale `queue.is_playing` gate, view attached only after the adjacency check)

## Decisions Made
- **Alias reuse over new import:** `cogs/music.py` already imports `pick_random` (from `personality.roasts`, which re-exports `personality.responses.pick_random` verbatim) alongside an aliased `pick_random_r` (direct `personality.responses` import) for the existing `NOTHING_PLAYING`/`NOT_IN_VOICE` calls. Since both names resolve to the identical function object, `/discover`'s cold-start guards call the bare `pick_random(DISCOVER_NO_HISTORY)` — functionally identical to `pick_random_r(...)` but matching the plan's literal acceptance-criteria string and avoiding a third import path for the same function.
- **Confirm view seeds only the top pick:** `DiscoverQueueView` is constructed with `adjacent_artists[0]` only (not the full adjacency list) — the plan specifies a single "queue it" button seeded with "the top adjacent artist name," not a multi-select.

## Deviations from Plan

None — plan executed exactly as written. Two self-corrections during test authoring (both caught before commit, not deviations from the plan's required behavior):
- Fixed `inspect.getsource(MusicCog.discover)` -> `MusicCog.discover.callback` (an `app_commands.command`-wrapped method is a `Command` object, not a plain function — the coroutine is reachable via `.callback`).
- Reworded two docstrings (in `discover` and `DiscoverQueueView`) that initially contained the literal substrings `parse_suggestions` / `timeout=None` in prose explaining the firewall/one-shot design — these tripped the corresponding "does NOT contain" source assertions the same way 14-01's `get_artist_cooccurrence` docstring tripped its own `user_id`-absence check. Reworded to convey the same meaning without the literal banned substring, verified by rerunning the tests.

## Issues Encountered

`discord.ui.button`-decorated methods (e.g. `DiscoverQueueView.queue_button`) remain plain functions (unlike `app_commands.command`, which wraps into a `Command` object) — confirmed via a quick interactive check before writing the button-source test helper, so `inspect.getsource(DiscoverQueueView.queue_button)` works directly without a `.callback` indirection.

## User Setup Required

None - no external service configuration required. Zero new dependencies, zero new tables, zero new limiters.

## Verification

```
python -m pytest tests/test_discover.py -q
# 21 passed

python -m pytest tests/ -q
# 726 passed, 105 skipped
```

## Next Phase Readiness
- `/discover` (BRAIN-02) is fully wired and test-covered; ready for the parked live-Discord UAT pass alongside the rest of Phase 14's manual verification items.
- `DiscoverQueueView`'s one-shot confirm pattern (finite timeout, message-ref for `on_timeout`, not `setup_hook`-registered) is directly reusable by plan 14-05's `/jam suggest` propose-and-confirm view — same shape, different action on confirm.
- No blockers for 14-05.

---
*Phase: 14-smarter-music-brain*
*Completed: 2026-07-02*

## Self-Check: PASSED

All created/modified files confirmed present on disk; both task commit hashes
(`68497e1`, `b5e0b78`) confirmed present in git log.
