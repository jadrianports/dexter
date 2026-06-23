---
phase: 07-player-ux-filters
verified: 2026-06-19T00:00:00Z
uat_passed: 2026-06-24T00:00:00Z
status: passed
uat_outcome: "Live UAT complete (07-HUMAN-UAT.md): 10 passed, 1 issue (stale now-playing buttons on track advance) FIXED in code + 6 regression tests, 2 /seek checks skipped (accepted). User marked passed 2026-06-24. Follow-up: quick live re-confirm of skip->refresh UX on next run."
score: 13/13
overrides_applied: 0
human_verification:
  - test: "Boot the bot, /play a song, confirm the now-playing embed shows 5 buttons (Pause, Skip, Loop, Shuffle, Stop). Press each button. Verify Pause toggles to Resume and back, Skip advances to next track, Loop cycles Off→Single→Queue→Off with label update, Shuffle reorders upcoming tracks, Stop clears queue and disconnects."
    expected: "Each button responds without 'interaction failed'. Embed re-renders in place (silent). State changes are accurate."
    why_human: "Button-click interactions require a live Discord gateway and a running bot; cannot be machine-tested locally."
  - test: "With a pre-restart now-playing message, restart the bot and press a button on the old message."
    expected: "Button still responds (persistent view via setup_hook registration survived restart)."
    why_human: "Requires a live Discord gateway and actual bot restart cycle."
  - test: "Press a now-playing button while NOT in the bot's voice channel."
    expected: "Ephemeral NOT_IN_VOICE refusal message; no state change."
    why_human: "Requires live Discord interaction from a non-VC user."
  - test: "/play a 3-minute song. /seek 1:30 — confirm playback jumps to ~1:30. /seek 9:99 (invalid) — confirm ephemeral error. /seek with a value past the track duration — confirm it skips to the next track."
    expected: "Seek repositions audio; invalid input gives personality error; past-end triggers skip."
    why_human: "Audio seek verification requires a running bot with voice and FFmpeg."
  - test: "Queue 3+ songs. /previous — confirm the prior track restarts. /jump 3 — confirm the third track starts. /jump 99 — confirm ephemeral range error."
    expected: "Navigation uses the no-pop index model; bounds are enforced."
    why_human: "Requires live Discord playback."
  - test: "/filter bassboost mid-song — confirm bass-boosted audio is audible. Queue another song — confirm the next track is also bass-boosted (sticky). /filter off — confirm subsequent tracks return to normal passthrough."
    expected: "Filter applies immediately from current position; is sticky across tracks; off restores opus passthrough."
    why_human: "Audio quality and filter audibility require a live playback session."
  - test: "Restart the bot while a filter is active. Confirm /queue or /nowplaying shows the restored active_filter after restart."
    expected: "active_filter survives restart via guild_queues payload (persistence round-trip)."
    why_human: "Requires a live Postgres (Neon) connection to verify the persistence round-trip."
  - test: "/play a song. /favorite — confirm ephemeral 'saved' response. /favorite the same song again — confirm 'already saved' (duplicate). Save 25 songs — confirm the 26th attempt shows FAVORITE_CAP_HIT."
    expected: "Cap and dedupe are enforced with on-brand ephemeral messages."
    why_human: "Requires a live Postgres connection."
  - test: "/favorites with no saves — confirm ephemeral 'empty' message. With saves, /favorites — confirm the pick-list appears. Select a song, press Queue — confirm it is added to the queue and starts if idle. Select a song, press Remove — confirm it disappears from the list."
    expected: "FavoritesView works end-to-end; Queue/Remove buttons act on the selected entry only."
    why_human: "Requires live Discord interaction and a live Postgres connection."
  - test: "Save a favorite in server A. Open /favorites in server B — confirm it appears (cross-server, D-18)."
    expected: "Favorites are global (keyed on user_id, not guild_id)."
    why_human: "Requires two live Discord guilds and a shared Postgres instance."
  - test: "Queue 3 songs. /playlist save chill. Clear queue. /playlist load chill — confirm all 3 songs are appended and playback starts."
    expected: "Playlist round-trips correctly; append-on-load works; playback starts when idle."
    why_human: "Requires live Postgres and live Discord playback."
  - test: "/playlist save chill again (overwrite) — confirm the count stays at 1 (upsert, not a second entry). /playlist list — confirm 'chill' appears. /playlist delete chill — confirm it is removed. /playlist load ghostname — confirm ephemeral PLAYLIST_NOT_FOUND."
    expected: "Upsert, list, and delete operate correctly with on-brand messages."
    why_human: "Requires a live Postgres connection."
  - test: "Load a playlist into a near-full queue (close to 500-track cap) — confirm truncation count is reported."
    expected: "QueueFullError is caught and the truncation message is included in the PLAYLIST_LOADED response."
    why_human: "Requires a live queue at near-cap size; cannot be machine-tested without a live bot."
---

# Phase 7: Player UX & Filters Verification Report

**Phase Goal:** Users have full interactive control over playback from the now-playing embed and can apply audio effects and save personal favorites.
**Verified:** 2026-06-19T00:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification.

## Goal Achievement

All 13 must-have truths derived from the ROADMAP Success Criteria and 4-plan must_haves frontmatter are VERIFIED against the codebase. The phase is structurally complete. Every remaining gate is a live-Discord or live-Postgres behavioral check that cannot be machine-tested on this local dev environment.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | The now-playing embed carries a persistent 5-button view (play/pause, skip, loop, shuffle, stop) that survives a bot restart via bot.add_view() + stable custom_ids | VERIFIED | `NowPlayingView(timeout=None)` with `custom_id="dex:np:{playpause,skip,loop,shuffle,stop}"` at `cogs/music.py:275–441`; `setup_hook` calls `self.add_view(NowPlayingView(self))` at `bot.py:44–54` |
| 2 | Only a user in the bot's voice channel can drive the buttons; everyone else gets an ephemeral refusal | VERIFIED | `_guard_in_voice()` checks `member.voice.channel != vc.channel` at `cogs/music.py:306–319`; all 5 button callbacks invoke it before any state change |
| 3 | A button press silently re-renders the now-playing embed and is always acked; Discord never shows 'interaction failed' | VERIFIED | All non-skip/stop callbacks call `interaction.response.edit_message(...)`; skip/stop defer first then send ephemeral followup at `cogs/music.py:371–440` |
| 4 | The loop button cycles off→single→queue→off; the stop button mirrors /stop teardown | VERIFIED | `_do_loop_cycle` uses `{OFF:SINGLE, SINGLE:QUEUE, QUEUE:OFF}` dict at `cogs/music.py:755–763`; `_do_stop` does `_play_generation += 1 → clear() → clear_persisted() → stop + disconnect` at `cogs/music.py:771–779` |
| 5 | MusicQueue tracks playback elapsed via a monotonic start-stamp adjusted for pause/resume | VERIFIED | `mark_started/mark_paused/mark_resumed/elapsed_seconds` implemented with clock-injectable `now` param at `models/queue.py:157–196`; 17 pure unit tests pass (79/79 green) |
| 6 | MusicQueue.jump_to(index) validates bounds and moves current_index without popping | VERIFIED | `jump_to(self, index)` bounds-checks `0 <= index < len(self.tracks)` at `models/queue.py:202–211` |
| 7 | parse_time() turns 'mm:ss', 'h:mm:ss', and raw seconds into an int, returning None on garbage | VERIFIED | Implementation at `utils/formatters.py:4–47`; 12 test cases including round-trip with format_duration pass |
| 8 | AudioService.get_source builds -ss seek and -af filter chain on demand; with neither it stays opus-passthrough default | VERIFIED | `_build_ffmpeg_opts` pure helper at `services/audio.py:24–46`; `get_source` branches on `use_opts = seek_seconds > 0 or ffmpeg_filter is not None` at `services/audio.py:71–122`; 5 pure unit tests pass |
| 9 | config exposes the 4 named filter presets + favorites/playlist caps | VERIFIED | `FFMPEG_FILTERS` with exactly `{bassboost, nightcore, slowed+reverb, 8d}` at `config.py:111–116`; `FAVORITES_MAX_PER_USER=25`, `PLAYLISTS_MAX_PER_USER=25`, `PLAYLIST_NAME_MAX_LENGTH=60` at `config.py:119–121` |
| 10 | /seek, /previous, /jump, /filter commands are registered on MusicCog and wired to the engine | VERIFIED | All 4 commands present at `cogs/music.py:1446–1606`; `/seek` uses `parse_time` + `_play_track(offset_seconds=secs)`; `/previous` calls `queue.previous()` + `_play_track`; `/jump` calls `queue.jump_to(index)` + `_play_track`; `/filter` sets `queue.active_filter` + re-plays from `elapsed_seconds()` |
| 11 | active_filter is persisted in the guild_queues payload and restored on restart | VERIFIED | `"active_filter": queue.active_filter` in persist payload at `services/queue_persistence.py:54`; `queue.active_filter = payload.get("active_filter", "off")` in restore at `services/queue_persistence.py:139` |
| 12 | user_favorites + user_playlists tables and helpers exist and are structurally correct | VERIFIED | `CREATE TABLE IF NOT EXISTS user_favorites (PRIMARY KEY (user_id, video_id))` at `database.py:125–137`; `CREATE TABLE IF NOT EXISTS user_playlists (PRIMARY KEY (user_id, name), snapshot JSONB)` at `database.py:139–148`; all 4 favorites helpers + 5 playlist helpers implemented with $N-parameterised asyncpg; 34 live-DB tests collected |
| 13 | LibraryCog with /favorite, /favorites, /playlist group (save/load/list/delete) is registered in bot.py | VERIFIED | `class LibraryCog` at `cogs/library.py:234`; `playlist = app_commands.Group(name="playlist")` at `cogs/library.py:426`; `cogs.library` in the always-on load tuple at `bot.py:324` |

**Score:** 13/13 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `models/queue.py` | elapsed tracking, active_filter, jump_to | VERIFIED | `mark_started/mark_paused/mark_resumed/elapsed_seconds/jump_to/active_filter` all present; `clear()` resets them |
| `utils/formatters.py` | parse_time() | VERIFIED | `def parse_time(text: str) -> int | None` at line 4 |
| `services/audio.py` | _build_ffmpeg_opts + get_source(seek_seconds=, ffmpeg_filter=) | VERIFIED | Both present; default path (no seek/filter) unchanged |
| `config.py` | FFMPEG_FILTERS dict + caps + cooldowns | VERIFIED | 4 preset keys, 25-cap constants, SEEK/FILTER/FAVORITE cooldown constants |
| `personality/responses.py` | 12 Phase 7 response pools | VERIFIED | All 12 pools present: FILTER_APPLIED, FILTER_CLEARED, FAVORITE_SAVED, FAVORITE_DUPLICATE, FAVORITE_CAP_HIT, FAVORITES_EMPTY, PLAYLIST_SAVED, PLAYLIST_LOADED, PLAYLIST_NOT_FOUND, PLAYLIST_CAP_HIT, NOT_IN_VOICE, NOTHING_PLAYING |
| `cogs/music.py` | NowPlayingView + seek/previous/jump/filter + shared _do_* helpers + _play_track offset wiring | VERIFIED | NowPlayingView class with 5 stable custom_id buttons; all 4 commands; _do_skip/_do_pause_toggle/_do_loop_cycle/_do_shuffle/_do_stop; `offset_seconds` param + `mark_started` + filter resolution in `_play_track` |
| `bot.py` | setup_hook registering NowPlayingView | VERIFIED | `async def setup_hook(self)` calls `self.add_view(NowPlayingView(self))` |
| `services/queue_persistence.py` | active_filter in persist + restore | VERIFIED | Persist writes `"active_filter": queue.active_filter`; restore reads it with `"off"` default |
| `utils/embeds.py` | now_playing shows elapsed progress + active_filter field | VERIFIED | `live_elapsed = queue.elapsed_seconds()` used for progress bar; `🎛 Filter` field added when `active_filter != "off"` |
| `database.py` | user_favorites schema + 4 helpers; user_playlists schema + 5 helpers | VERIFIED | Both tables in SCHEMA_SQL; all 9 helpers implemented with ON CONFLICT patterns |
| `cogs/library.py` | LibraryCog with /favorite, /favorites (FavoritesView), /playlist group | VERIFIED | LibraryCog class, FavoritesSelect/QueueButton/RemoveButton/FavoritesView views, playlist app_commands.Group with save/load/list/delete |
| `tests/test_queue.py` | TestElapsedTracking, TestJumpTo, test_clear_resets_filter_and_elapsed | VERIFIED | 17 new tests; 79 total pass |
| `tests/test_formatters.py` | TestParseTime | VERIFIED | 12 new test cases; pass |
| `tests/test_audio.py` | _build_ffmpeg_opts pure unit tests | VERIFIED | 5 new tests; pass |
| `tests/test_responses.py` | Parametrized test for all 12 new pools | VERIFIED | Pass |
| `tests/test_database_phase7.py` | 34 live-DB integration tests for favorites + playlists | VERIFIED (collection) | 34 tests collect cleanly; require live Postgres to execute |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| NowPlayingView buttons | MusicCog._do_* helpers | `cog = bot.get_cog("MusicCog"); cog._do_*(...)` in each callback | VERIFIED | All 5 button callbacks resolve cog and call matching helper |
| _play_track / /filter / /seek | AudioService.get_source(seek_seconds=, ffmpeg_filter=) | `queue.active_filter → config.FFMPEG_FILTERS` chain; `queue.elapsed_seconds()` for position | VERIFIED | `ffmpeg_filter = config.FFMPEG_FILTERS.get(queue.active_filter)` at `cogs/music.py:506–508`; `get_source(track, seek_seconds=offset_seconds, ffmpeg_filter=ffmpeg_filter)` at line 511–515 |
| /favorite | database.add_favorite + current track | `music_cog.get_queue(guild.id).get_current()` then `add_favorite(pool, user_id=..., video_id=track.video_id, ...)` | VERIFIED | `cogs/library.py:349–391` |
| FavoritesView QueueButton | MusicCog queueing path | `get_cog("MusicCog")._play_track` via `_queue_favorite` | VERIFIED | `cogs/library.py:242–323`; persist call now correctly uses `guild` object and `user_channel.id` (CR-01 fix at commit 731946e) |
| /playlist save | database.save_playlist + Track.to_dict | `snapshot=[t.to_dict() for t in queue.tracks]` → `save_playlist(pool, ...)` | VERIFIED | `cogs/library.py:489–497` |
| /playlist load | MusicCog queue + Track.from_dict | `Track.from_dict({**track_dict, "requested_by": user.id})` → `queue.add(track)` | VERIFIED | `cogs/library.py:547–553` |
| active_filter persistence | guild_queues JSONB payload | `"active_filter": queue.active_filter` on persist; `payload.get("active_filter", "off")` on restore | VERIFIED | `services/queue_persistence.py:54` and `:139` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `utils/embeds.py::now_playing` | `live_elapsed` | `queue.elapsed_seconds()` → monotonic clock since `mark_started` | Yes — mark_started called in `_play_track` after `voice_client.play()` | FLOWING |
| `utils/embeds.py::now_playing` | `queue.active_filter` | Set by `/filter` command or restored from `guild_queues` payload | Yes | FLOWING |
| `cogs/library.py::favorites` | `rows` | `get_favorites(pool, user_id=user_id)` — SELECT from user_favorites | Yes (live DB query) | FLOWING |
| `cogs/library.py::playlist_load` | `rows` | `get_playlist(pool, user_id=user_id, name=name)` — SELECT from user_playlists | Yes (live DB query) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| config imports cleanly with correct filter keys | `python -c "import config; assert set(config.FFMPEG_FILTERS)=={'bassboost','nightcore','slowed+reverb','8d'}; assert config.FAVORITES_MAX_PER_USER==25; print('OK')"` | OK | PASS |
| NowPlayingView class exists with timeout=None | AST parse check | class found in ast.walk | PASS |
| seek/previous/jump/filter commands registered | `'name="seek"' in src and 'name="previous"' in src ...` | all found | PASS |
| bot.py setup_hook calls add_view | string check | setup_hook + add_view + NowPlayingView found | PASS |
| database schema contains both new tables | string check | CREATE TABLE IF NOT EXISTS user_favorites + user_playlists found | PASS |
| 34 live-DB tests collect | `pytest tests/test_database_phase7.py --collect-only -q` | 34 tests collected | PASS |
| 79 pure unit tests pass | `pytest tests/test_queue.py tests/test_formatters.py tests/test_audio.py tests/test_responses.py -q` | 79 passed, 1 warning | PASS |
| CR-01 fix verified | git show 731946e | persist(guild, queue, user_channel.id) — 3-arg form confirmed | PASS |
| WR-01 fix verified | git show 731946e | `result.rsplit(" ", 1)[-1] != "0"` replacing fragile endswith("1") | PASS |

### Probe Execution

Step 7c: SKIPPED — no probe scripts exist for Phase 7 (`scripts/` contains only Phase 4/5 ops scripts; no `probe-*.sh` declared in any Phase 7 PLAN).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PLAYER-01 | Plan 02 | Now-playing embed has interactive control buttons | VERIFIED (code) / HUMAN-VERIFY (runtime) | `NowPlayingView` with 5 buttons registered via setup_hook; live click behavior requires human UAT |
| PLAYER-02 | Plans 01+02 | User can /seek within current track | VERIFIED (code) / HUMAN-VERIFY (audio) | `/seek` command uses `parse_time` + `_play_track(offset_seconds=)`; actual audio jump requires human UAT |
| PLAYER-03 | Plan 02 | User can /previous to replay prior track | VERIFIED (code) / HUMAN-VERIFY (runtime) | `/previous` registered at `cogs/music.py:1494`; **NOTE: REQUIREMENTS.md traceability still shows "Pending" — documentation gap only, implementation is present** |
| PLAYER-04 | Plans 01+02 | User can /jump to specific queue slot | VERIFIED (code) / HUMAN-VERIFY (runtime) | `queue.jump_to(index)` + `/jump` command |
| PLAYER-05 | Plans 03 | User can save and replay personal favorites | VERIFIED (code) / HUMAN-VERIFY (DB+runtime) | `user_favorites` schema + LibraryCog `/favorite` + `/favorites`; live Postgres round-trip requires human UAT |
| PLAYER-06 | Plans 04 | User can save and load named playlists | VERIFIED (code) / HUMAN-VERIFY (DB+runtime) | `user_playlists` schema + `/playlist` group; live Postgres round-trip requires human UAT |
| PLAYER-07 | Plans 01+02 | User can apply audio filters via /filter | VERIFIED (code) / HUMAN-VERIFY (audio) | `/filter` with 5 choices; FFMPEG_FILTERS preset map; re-play from elapsed position; audio quality requires human UAT |
| PLAYER-08 | Plans 01+02 | User can clear filters back to normal playback | VERIFIED (code) / HUMAN-VERIFY (audio) | `/filter off` sets `queue.active_filter="off"`; `_play_track` then passes `ffmpeg_filter=None` → opus passthrough; audibility requires human UAT |

**Note on REQUIREMENTS.md tracking:** PLAYER-01 and PLAYER-03 are still marked `[ ]` (Pending) in REQUIREMENTS.md and the traceability table. Both are implemented. The documentation was not updated after code landed. This is a tracking discrepancy, not an implementation gap.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `cogs/music.py` | 1459 | `/seek` rejects paused track: `if not track or not queue.is_playing` — but `queue.is_paused` is not included | WARNING (WR-06) | User cannot seek while paused, while `/previous` and `/filter` allow it. Inconsistent API; not a blocker. |
| `cogs/music.py` | 1585 | `/filter` applied while paused silently resumes playback as a side effect | WARNING (WR-05) | Applying a filter while paused starts playback. Surprising UX; not a blocker. |
| `cogs/library.py` | 358–382 | Duplicate detection uses two COUNT queries around the insert (race window + 3 DB round-trips) | WARNING (WR-02) | Under double-click concurrency may misreport DUPLICATE vs SAVED; at single-user scale this is low-risk. Not a blocker. |
| `cogs/library.py` | 358–377 | Cap check (count >= 25) and insert are non-atomic; concurrent /favorite calls could push a user past 25 | WARNING (WR-03) | TOCTOU cap overshoot possible under concurrent presses; best-effort cap acceptable at this scale. Not a blocker. |
| `cogs/library.py` | 565–583 | `/playlist load` does not bail when `user_channel.connect()` fails; sends now-playing embed for a silent queue | WARNING (WR-04) | UX issue: user sees "now playing" card when voice connect failed. Not a blocker. |
| `utils/formatters.py` | 39 | `parse_time` rejects mm:ss where minutes ≥ 60 (e.g. "75:00") | INFO (IN-01) | Reachable only for >60-min tracks; MAX_SONG_DURATION_SECONDS=900 makes this unreachable in practice. |
| `utils/embeds.py` | 18 | Dead `elapsed: int | None = None` parameter on `now_playing()` | INFO (IN-02) | Parameter is ignored; invites mis-use but causes no errors. |
| `tests/conftest.py` | 45 | `DROP TABLE ... user_playlist_tracks CASCADE` references a non-existent table | INFO (IN-03) | `IF EXISTS` makes it harmless; stale schema assumption from an earlier design. |

No `TBD`, `FIXME`, or `XXX` debt markers found in any Phase 7 modified files.

**Previously critical issues (both fixed in commit 731946e):**
- CR-01: `_queue_favorite` now calls `persist(guild, queue, user_channel.id)` — correct 3-arg form
- WR-01: `delete_playlist` now uses `result.rsplit(" ", 1)[-1] != "0"` — robust count parse

### Human Verification Required

All automated checks pass. The following items require a running bot with live Discord gateway and live Postgres (Neon) to verify. They match the v1.1 milestone's live-UAT pattern established in Phase 5.

#### 1. NowPlayingView — 5-Button Interactive Controller

**Test:** Boot the bot, /play a song, confirm the now-playing embed shows 5 buttons (Pause, Skip, Loop, Shuffle, Stop). Press each button. Verify Pause toggles to Resume and back, Skip advances to next track, Loop cycles Off→Single→Queue→Off with label update, Shuffle reorders upcoming tracks, Stop clears queue and disconnects.
**Expected:** Each button responds without 'interaction failed'. Embed re-renders in place (silent). State changes are accurate.
**Why human:** Button-click interactions require a live Discord gateway and a running bot; cannot be machine-tested locally.

#### 2. Persistent View Survival

**Test:** With a pre-restart now-playing message, restart the bot and press a button on the old message.
**Expected:** Button still responds (persistent view via setup_hook registration survived restart).
**Why human:** Requires a live Discord gateway and actual bot restart cycle.

#### 3. Non-VC User Button Refusal

**Test:** Press a now-playing button while NOT in the bot's voice channel.
**Expected:** Ephemeral NOT_IN_VOICE refusal message; no state change.
**Why human:** Requires live Discord interaction from a non-VC user.

#### 4. /seek Audio Jump

**Test:** /play a 3-minute song. /seek 1:30 — confirm playback jumps to ~1:30. /seek 9:99 (invalid) — confirm ephemeral error. /seek with a value past the track duration — confirm it skips to the next track.
**Expected:** Seek repositions audio; invalid input gives personality error; past-end triggers skip.
**Why human:** Audio seek verification requires a running bot with voice and FFmpeg.

#### 5. /previous and /jump Navigation

**Test:** Queue 3+ songs. /previous — confirm the prior track restarts. /jump 3 — confirm the third track starts. /jump 99 — confirm ephemeral range error.
**Expected:** Navigation uses the no-pop index model; bounds are enforced.
**Why human:** Requires live Discord playback.

#### 6. /filter Audio Effect + Stickiness

**Test:** /filter bassboost mid-song — confirm bass-boosted audio is audible. Queue another song — confirm the next track is also bass-boosted (sticky). /filter off — confirm subsequent tracks return to normal passthrough.
**Expected:** Filter applies immediately from current position; is sticky across tracks; off restores opus passthrough.
**Why human:** Audio quality and filter audibility require a live playback session.

#### 7. active_filter Persistence Across Restart

**Test:** Restart the bot while a filter is active. Confirm /queue or /nowplaying shows the restored active_filter after restart.
**Expected:** active_filter survives restart via guild_queues payload (persistence round-trip).
**Why human:** Requires a live Postgres (Neon) connection to verify the persistence round-trip.

#### 8. /favorite Cap, Dedupe, and Ephemeral Responses

**Test:** /play a song. /favorite — confirm ephemeral 'saved' response. /favorite the same song again — confirm 'already saved' (duplicate). Save 25 songs — confirm the 26th attempt shows FAVORITE_CAP_HIT.
**Expected:** Cap and dedupe are enforced with on-brand ephemeral messages.
**Why human:** Requires a live Postgres connection.

#### 9. /favorites Pick-List End-to-End

**Test:** /favorites with no saves — confirm ephemeral 'empty' message. With saves, /favorites — confirm the pick-list appears. Select a song, press Queue — confirm it is added to the queue and starts if idle. Select a song, press Remove — confirm it disappears from the list.
**Expected:** FavoritesView works end-to-end; Queue/Remove buttons act on the selected entry only.
**Why human:** Requires live Discord interaction and a live Postgres connection.

#### 10. Favorites Cross-Server (D-18)

**Test:** Save a favorite in server A. Open /favorites in server B — confirm it appears.
**Expected:** Favorites are global (keyed on user_id, not guild_id).
**Why human:** Requires two live Discord guilds and a shared Postgres instance.

#### 11. /playlist Round-Trip (save/load/list/delete)

**Test:** Queue 3 songs. /playlist save chill. Clear queue. /playlist load chill — confirm all 3 songs are appended and playback starts. /playlist save chill again (overwrite) — confirm the count stays at 1. /playlist list — confirm 'chill' appears. /playlist delete chill — confirm it is removed. /playlist load ghostname — confirm ephemeral PLAYLIST_NOT_FOUND.
**Expected:** Playlist round-trips correctly; upsert-on-name-clash works; list and delete operate on the invoking user's rows only.
**Why human:** Requires live Postgres and live Discord playback.

#### 12. /playlist load Truncation at Cap

**Test:** Load a playlist into a near-full queue (close to 500-track cap) — confirm truncation count is reported.
**Expected:** QueueFullError is caught and the truncation message is included in the PLAYLIST_LOADED response.
**Why human:** Requires a live queue at near-cap size; cannot be machine-tested without a live bot.

### Gaps Summary

No gaps. All automated verifications passed. Phase goal is structurally achieved in the codebase. Remaining items are live-Discord/live-Postgres behavioral checks (buttons, audio effects, DB round-trips) that match the Phase 5 live-UAT pattern for this milestone.

**Known open warnings (from code review, not blockers):**
- WR-02: Duplicate detection is racy and costs 3 DB queries (best-effort at single-user scale)
- WR-03: Cap check is non-atomic (best-effort TOCTOU)
- WR-04: /playlist load does not gate on connect success before sending now-playing embed
- WR-05: /filter applied while paused silently resumes
- WR-06: /seek rejects paused tracks inconsistently vs /previous and /filter

**REQUIREMENTS.md tracking discrepancy:** PLAYER-01 and PLAYER-03 are marked Pending in the traceability table. Both are implemented. Update REQUIREMENTS.md to mark them Complete after live UAT passes.

---

_Verified: 2026-06-19T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
