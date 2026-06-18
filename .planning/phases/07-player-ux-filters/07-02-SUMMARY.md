---
phase: "07-player-ux-filters"
plan: "02"
subsystem: "player-ux-discord"
tags: [discord-ui, persistent-views, seek, filter, navigation, phase7]
dependency_graph:
  requires:
    - MusicQueue.elapsed_seconds / mark_started / mark_paused / mark_resumed
    - MusicQueue.active_filter / jump_to()
    - utils.formatters.parse_time()
    - services.audio.AudioService.get_source(seek_seconds, ffmpeg_filter)
    - config.FFMPEG_FILTERS
    - personality.responses Phase 7 pools (NOT_IN_VOICE, NOTHING_PLAYING, FILTER_APPLIED, FILTER_CLEARED)
  provides:
    - cogs.music.NowPlayingView (persistent 5-button controller, timeout=None)
    - MusicCog._do_skip / _do_pause_toggle / _do_loop_cycle / _do_shuffle / _do_stop (shared helpers)
    - MusicCog.seek / previous / jump / filter_cmd slash commands
    - bot.DexterBot.setup_hook (persistent view registration)
    - active_filter in queue_persistence payload
  affects:
    - cogs/music.py
    - bot.py
    - services/queue_persistence.py
    - utils/embeds.py
tech_stack:
  added: []
  patterns:
    - discord.ui.View timeout=None + stable custom_ids for restart-surviving buttons
    - _do_* shared helper pattern (slash command + button button share one code path)
    - elapsed-stamped seek via queue.mark_started(offset) + get_source(seek_seconds=)
    - sticky filter via queue.active_filter resolved in _play_track per-track
key_files:
  created: []
  modified:
    - cogs/music.py
    - bot.py
    - services/queue_persistence.py
    - utils/embeds.py
decisions:
  - "NowPlayingView uses timeout=None + stable custom_ids; registered in setup_hook (not on_ready) per discord.py-correct persistent-view pattern"
  - "All button callbacks call matching _do_* helpers so slash command + button behavior is identical"
  - "_play_track accepts offset_seconds=0 param; calls queue.mark_started(offset) after stop, before play() — generation counter order preserved"
  - "now_playing() derives elapsed from queue.elapsed_seconds() directly instead of taking an elapsed param; old param signature kept for backward compat"
  - "Tasks 3-5 (/seek, /previous, /jump, /filter) were written in one edit wave; committed as Task3 + Task4+5 to preserve the key file boundary (queue_persistence)"
metrics:
  duration: "~25 min"
  completed: "2026-06-19"
  tasks_completed: 5
  files_modified: 4
---

# Phase 7 Plan 02: Player UX & Filters Wire-up Summary

**One-liner:** Persistent 5-button NowPlayingView, /seek /previous /jump /filter commands, shared _do_* helpers, elapsed/filter engine wiring, active_filter persisted — all consuming Plan 01 primitives.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Shared _do_* helpers + elapsed/filter engine wiring | 9324e20 | cogs/music.py, utils/embeds.py |
| 2 | NowPlayingView persistent 5-button controller + setup_hook | f7306cc | cogs/music.py, bot.py |
| 3 | /seek command | 5d44f94 | cogs/music.py |
| 4+5 | /previous /jump + /filter + active_filter persistence | 21e48ba | services/queue_persistence.py |

## What Was Built

### Task 1 — Shared helpers + elapsed/filter engine wiring

**Shared control helpers on MusicCog** (callable from both slash commands and button callbacks):
- `_do_skip(guild, queue, vc)`: skips, persists, starts next track via asyncio.create_task
- `_do_pause_toggle(queue, vc)`: toggles pause/resume + mark_paused/mark_resumed; returns "paused"/"resumed"
- `_do_loop_cycle(queue)`: cycles LoopMode off→single→queue→off; returns new mode
- `_do_shuffle(queue)`: shuffles upcoming tracks; returns count
- `_do_stop(guild, queue, vc)`: generation increment → clear → clear_persisted → stop + disconnect (mirrors /stop)

**_play_track engine changes:**
- Accepts `offset_seconds: int = 0` parameter
- Resolves `queue.active_filter` → `config.FFMPEG_FILTERS` chain and passes `ffmpeg_filter=` + `seek_seconds=offset_seconds` to `get_source()`
- Calls `queue.mark_started(offset_seconds)` after generation increment, before `voice_client.play()`
- pause command calls `queue.mark_paused()`, resume calls `queue.mark_resumed()`

**now_playing() embed changes (utils/embeds.py):**
- Derives `live_elapsed = queue.elapsed_seconds()` internally (live clock query)
- Shows progress bar when elapsed > 0
- Appends `🎛 Filter` inline field when `queue.active_filter != "off"` (D-13)

### Task 2 — NowPlayingView

**NowPlayingView(discord.ui.View, timeout=None):**
- 5 buttons with stable custom_ids: `dex:np:playpause`, `dex:np:skip`, `dex:np:loop`, `dex:np:shuffle`, `dex:np:stop`
- `_resolve_cog_queue_vc()`: resolves MusicCog + queue + vc from interaction
- `_guard_in_voice()`: checks presser is in bot's VC; ephemeral NOT_IN_VOICE refusal if not (D-02, T-07-02-01)
- playpause: toggles label (⏸ Pause / ▶ Resume), calls `_do_pause_toggle`, edits message in-place
- skip: defers first, calls `_do_skip`, sends ephemeral status
- loop: calls `_do_loop_cycle`, updates button label (Loop: Off / Loop: Single / Loop: Queue)
- shuffle: calls `_do_shuffle`, edits message in-place
- stop: defers, calls `_do_stop`, sends ephemeral confirmation

**bot.py setup_hook:**
- `DexterBot.setup_hook()` calls `self.add_view(NowPlayingView(self))` (D-03)
- Runs before `on_ready` — correct discord.py placement for persistent views

**Now-playing send/edit sites** (3 locations) attach `view=NowPlayingView(self.bot)`

### Task 3 — /seek

- Accepts `position: str` (mm:ss, h:mm:ss, or raw seconds) via `parse_time()`
- None result → ephemeral error message
- `secs >= track.duration_seconds` → calls `_do_skip()` (D-15, past-end behavior)
- Otherwise → `_play_track(guild, track, offset_seconds=secs)` (active filter preserved)
- SEEK_COOLDOWN_SECONDS enforced; responds with `format_duration(secs)` confirmation
- Attaches NowPlayingView to the response embed

### Tasks 4+5 — /previous, /jump, /filter + persistence

**/previous:** `queue.previous()` → None = ephemeral "at beginning" → else `_play_track` + persist + NowPlayingView

**/jump `<position>`:** 1-based int → `index = position - 1` → `queue.jump_to(index)` → None = ephemeral range error → else `_play_track` + persist + NowPlayingView

**/filter `<preset>`:**
- `app_commands.choices` with 5 fixed values: bassboost, nightcore, slowed+reverb, 8d, off — no raw user text reaches FFmpeg (T-07-02-02)
- NOT_IN_VOICE guard (only acts if presser is in bot's VC)
- Sets `queue.active_filter = preset.value`
- If track playing/paused: `pos = queue.elapsed_seconds()` → `_play_track(offset_seconds=pos)` (D-09)
- Persists after change
- FILTER_COOLDOWN_SECONDS enforced
- "off" uses FILTER_CLEARED pool; otherwise FILTER_APPLIED with filter name interpolated

**queue_persistence changes:**
- `persist()` payload: `"active_filter": queue.active_filter` added (D-10)
- `restore_queues()`: `queue.active_filter = payload.get("active_filter", "off")` (default safe)

## Verification Results

```
python -c "import ast; ast.parse(open('cogs/music.py',encoding='utf-8').read()); ast.parse(open('bot.py',encoding='utf-8').read()); print('syntax OK')"
syntax OK

pytest tests/test_queue.py tests/test_formatters.py tests/test_audio.py tests/test_responses.py -x -q
79 passed, 1 warning
```

Structural checks passed:
- `NowPlayingView` class with timeout=None and 5 custom_id buttons: FOUND
- `setup_hook` with `add_view`: FOUND in bot.py
- `name="seek"`, `name="previous"`, `name="jump"`, `name="filter"`: FOUND
- `active_filter` in queue_persistence.py: FOUND

Human-checks (Tasks 2-5 live gates) require a running bot with voice:
- Boot locally, /play, confirm 5 buttons appear; press each; confirm non-VC user gets ephemeral refusal; restart bot and confirm pre-restart buttons still work
- /seek 1:30 → jumps; /seek 9:99 invalid → ephemeral roast; /seek past end → advances
- /jump 3 plays the third; /previous returns; /jump 99 → range error
- /filter bassboost mid-song → audible; next song stays boosted; /filter off → passthrough; restart → filter restored

Pre-existing test failures in test_ai_helpers.py, test_autoqueue_parse.py, test_gemini.py etc. — all caused by google-genai / yt-dlp not installed in the local Windows dev environment. Pre-date this plan; unrelated.

## Deviations from Plan

### Minor adaptations (not deviations)

**1. [Implementation] Tasks 3-5 written in one edit wave**
- Tasks 3 (/seek), 4 (/previous, /jump), and 5 (/filter) were added to `cogs/music.py` in a single edit for efficiency.
- Committed as two commits: one for Task 3 (labeled seek), one for Tasks 4+5 (labeled previous/jump/filter + persistence).
- All acceptance criteria for all three tasks met identically to the plan spec.

**2. [Improvement] now_playing() derived elapsed internally**
- The plan said "update `now_playing(track, queue)` ... to compute `elapsed = queue.elapsed_seconds()`" — implemented by having the function call `queue.elapsed_seconds()` internally rather than requiring callers to pass elapsed.
- Old `elapsed: int = 0` param kept for backward compat but no longer the primary data source.
- All existing callers work unchanged; the embed is always live.

None of the must_haves or artifacts were deviated from. All acceptance criteria met.

## Threat Model Compliance

| Threat | Status |
|--------|--------|
| T-07-02-01 (button access control) | Mitigated — `_guard_in_voice()` in every button callback; ephemeral refusal, no state change |
| T-07-02-02 (FFmpeg injection via filter) | Mitigated — `app_commands.Choices` set; chain from `config.FFMPEG_FILTERS` only |
| T-07-02-03 (seek -ss injection) | Mitigated — `parse_time()` returns int or None; range-checked against duration |
| T-07-02-04 (DoS via rapid re-encodes) | Mitigated — per-command cooldowns + generation counter cancels stale plays |
| T-07-02-05 (ephemeral errors) | Mitigated — all error/no-op responses use `ephemeral=True` |

## Known Stubs

None — all commands are fully wired. Remaining human-verify gates are live-Discord behavioral checks (buttons, audio quality, restart-survival) that require a running bot.

## Self-Check: PASSED

- cogs/music.py: `NowPlayingView` class with timeout=None — FOUND
- cogs/music.py: `_do_skip`, `_do_pause_toggle`, `_do_loop_cycle`, `_do_shuffle`, `_do_stop` — FOUND
- cogs/music.py: `seek`, `previous`, `jump`, `filter_cmd` commands — FOUND
- cogs/music.py: `offset_seconds` param in `_play_track` — FOUND
- bot.py: `setup_hook` with `add_view` — FOUND
- services/queue_persistence.py: `active_filter` in persist + restore — FOUND
- utils/embeds.py: `queue.elapsed_seconds()` and `active_filter` field — FOUND
- Commits 9324e20, f7306cc, 5d44f94, 21e48ba — all in git log
