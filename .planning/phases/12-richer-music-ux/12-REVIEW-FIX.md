---
phase: 12-richer-music-ux
fixed_at: 2026-06-30T14:02:17Z
review_path: .planning/phases/12-richer-music-ux/12-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 12: Code Review Fix Report

**Fixed at:** 2026-06-30T14:02:17Z
**Source review:** .planning/phases/12-richer-music-ux/12-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (all Warnings; Info findings IN-01..IN-04 out of scope for `critical_warning`)
- Fixed: 6
- Skipped: 0

## Fixed Issues

### WR-01: `current_index` mutated unconditionally in auto-queue, even when playback is not started

**Files modified:** `cogs/ai.py`
**Commit:** 258ab16
**Applied fix:** Moved `queue.current_index = len(queue.tracks) - len(tracks_added)` inside the
`should_start_playback(...)` branch so the queue pointer is only advanced onto the first
newly-appended track when playback actually starts. Changed the `has_track` gate input from
`queue.get_current() is not None` to `len(queue.tracks) > 0` (per the review) so the gate no
longer depends on the pre-mutation index. Both branches are covered by tests in
`tests/test_autoqueue_playback.py` (the already-flowing branch asserts `_play_track` is not
awaited; the new WR-06 test asserts `current_index == 1` on the start branch) — they pass.

### WR-02: Now-playing player is created on an ephemeral message in favorites/playlist/jam load

**Files modified:** `cogs/library.py`
**Commit:** b18e2f0
**Applied fix:** For the playback-start branch in `_queue_favorite`, `playlist_load`, and
`jam_load`, replaced the ephemeral `interaction.followup.send(embed=..., view=NowPlayingView)`
with a route through the music cog's existing shared helper
`music_cog._refresh_now_playing(guild, queue)`, which posts the public now-playing player and
manages `queue._now_playing_message_id` the same way `/play` does. Set
`queue._text_channel_id = interaction.channel.id` first so the shared helper (and subsequent
song-change refreshes) post into the loader's channel. The loader now gets a short ephemeral
text confirmation; the persistent public player is the single player-management path for all
entry points, fixing the orphaned-ephemeral-player + duplicate-player behavior on the next song.

### WR-03: `voice.connect()` failures are swallowed/ignored, then playback is attempted anyway

**Files modified:** `cogs/library.py`
**Commit:** cd372c0
**Applied fix:** Wrapped the previously-unguarded `_queue_favorite` connect in `try/except`, and
in `playlist_load` / `jam_load` added a user-facing error followup + `return` on connect failure
so execution no longer falls through to `music_cog._play_track(...)` with no voice client
connected. Each handler now resolves the deferred-ephemeral interaction with
"couldn't join your voice channel. try again." instead of leaving a permanent "thinking…".

### WR-04: Fire-and-forget `asyncio.create_task` without retaining task references

**Files modified:** `cogs/ai.py`
**Commit:** ad87583
**Applied fix:** Replaced the bare `asyncio.create_task(...)` for the auto-queue-ignored memory
writes with the project's standard `make_task(..., name="auto-queue-memory", bot=self.bot)`
helper (`utils/tasks.py`), which holds a strong reference in a module-level set until completion
(asyncio GC guard) and surfaces any raised exception to the logs / error channel. This matches
how `cogs/music.py` already routes its background tasks. Removed the now-unused `import asyncio`
and added `from utils.tasks import make_task`.

### WR-05: `_get_lrclib` assumes the JSON payload is a list; a non-list response mis-iterates

**Files modified:** `services/lyrics.py`
**Commit:** 0feb6de
**Applied fix:** Added an `isinstance(results, list)` guard immediately after `json.loads(raw)`;
a non-list payload (bare object / string / number) now logs a warning and returns `None` instead
of iterating dict keys / characters and raising `AttributeError` masked by the broad `except`.

### WR-06: Auto-queue fall-through loop is re-implemented in the test, not exercised against the real code

**Files modified:** `tests/test_autoqueue_playback.py`
**Commit:** a68c503
**Applied fix:** Added `test_autoqueue_falls_through_when_first_suggestion_candidates_all_rejected`,
which drives the real `AICog.try_auto_queue` with a first suggestion whose YouTube candidates all
fail `validate_youtube_match` (run for real, not patched) and a second suggestion with a matching
candidate. Asserts both suggestions were searched, `async_extract` ran exactly once, the single
appended track came from the second suggestion (`video_id == "new2"`), and playback started on it.
This guards the D-14 `continue`-on-`validated is None` behavior against the shipped loop rather
than a hand-copied re-implementation. Full file (3 tests) passes; 49 related tests across
`test_autoqueue_validate.py`, `test_lyrics_lrclib.py`, `test_jam_load.py` still pass.

---

_Fixed: 2026-06-30T14:02:17Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
