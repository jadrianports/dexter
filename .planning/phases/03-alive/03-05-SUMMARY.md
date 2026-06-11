---
phase: "03-alive"
plan: "05"
subsystem: "cogs/music.py — /lyrics, /history, earned roast hooks"
tags: ["lyrics", "history", "pagination", "repeat-song-roast", "milestone-roast", "streak", "gemini", "discord-ui"]
dependency_graph:
  requires: ["03-01", "03-02", "03-03"]
  provides: ["LYRIC-01", "HIST-01", "PERS-04", "PERS-09"]
  affects: ["cogs/music.py"]
tech_stack:
  added: []
  patterns:
    - "LyricsPageView/HistoryPageView: list-input pagination views (not MusicQueue-coupled)"
    - "D-08 Gemini priority-2 roast path: build_chat_prompt few-shot voice + GeminiRateLimitError/exception -> template fallback"
    - "D-14 earned roast bypass: no ambient ceiling check for repeat-song or milestones"
    - "update_user_streak per queued song on _log_track path"
    - "allowed_mentions=AllowedMentions.none() on all roast and lyrics sends"
key_files:
  modified:
    - "cogs/music.py"
decisions:
  - "LyricsPageView and HistoryPageView defined as independent view classes with list inputs (not MusicQueue), per Pitfall 8 — avoids queue-state coupling"
  - "LyricsPageView.on_timeout disables buttons and edits stored self.message reference (Open Question 3 resolution)"
  - "HistoryPageView uses guild.get_member() for display name resolution, falls back to raw user_id mention"
  - "_build_roast_line helper mirrors EventsCog._generate_ambient_roast pattern exactly: get_user_summary -> build_chat_prompt('normal') -> gemini_service.chat(priority=2) -> GeminiRateLimitError/Exception -> template fallback"
  - "repeat-song count read AFTER log_song so the current queued song is included in the count (correct threshold trigger)"
  - "total_songs_queued fetched with a SELECT after update_user_profile (which does the UPSERT + increment) since update_user_profile returns None"
metrics:
  duration: "~35 minutes"
  completed: "2026-06-11"
  tasks_completed: 3
  files_modified: 1
---

# Phase 03 Plan 05: /lyrics, /history, Repeat-Song + Milestone Roasts Summary

**One-liner:** Paginated /lyrics (Genius+AZLyrics via LyricsService) + /history (guild-wide, title/artist/who/when) added to MusicCog; _log_track wired with repeat-song (PERS-04) and streak/milestone (PERS-09) earned roasts using the locked few-shot DEXTER voice (D-06) at priority-2 Gemini with guaranteed template fallback.

---

## What Was Built

### Task 1: LyricsPageView + HistoryPageView + /lyrics + /history

**LyricsPageView** (`cogs/music.py`, after QueuePageView):
- Takes `pages: list[str]` + `title: str` (pre-chunked, not MusicQueue-coupled — Pitfall 8)
- Previous/Next buttons with `interaction.response.edit_message(... allowed_mentions=AllowedMentions.none())`
- `on_timeout` disables buttons AND edits `self.message` for visual feedback (Open Question 3)
- Color: `0x5865F2` (Discord blurple), footer shows `Page X/Y`

**HistoryPageView** (`cogs/music.py`):
- Takes `rows: list[dict]` + `guild: discord.Guild` for username resolution
- `HISTORY_PAGE_SIZE` rows per page; each entry: `**title** — artist\n  ↳ who · YYYY-MM-DD`
- Resolves `user_id` via `guild.get_member()`, falls back to `<@user_id>` mention text
- Same Previous/Next + `on_timeout` pattern; `allowed_mentions=AllowedMentions.none()` on all edits

**/lyrics** command:
- Cooldown: `config.LYRICS_COOLDOWN_SECONDS` (10s)
- Returns ephemeral `embeds.error("nothing is playing...")` if queue empty
- `await interaction.response.defer()` before network call (D-15 / Shared Pattern)
- Guards `lyrics_service` with `getattr(self.bot, "lyrics_service", None)` — degrades to NO_LYRICS_FOUND if 03-06 hasn't wired it yet
- Falls back to `pick_random(NO_LYRICS_FOUND)` on absent service, None lyrics, or empty chunks
- Builds `LyricsPageView`, stores `msg` reference, sends with `allowed_mentions=AllowedMentions.none()`

**/history** command:
- Cooldown: 5s
- Calls `get_history_rows(self.db, guild_id=str(...), limit=int(config.HISTORY_FETCH_LIMIT))`
- Returns ephemeral error if no rows
- Builds `HistoryPageView(rows, guild=interaction.guild)`, sends with `allowed_mentions=AllowedMentions.none()`
- Stores `interaction.original_response()` on `view.message` for `on_timeout`

### Tasks 2 & 3: Repeat-Song + Streak/Milestone Roast Hooks in `_log_track`

Three new private helpers added to `MusicCog`:

**`_get_top_artist(user_id)`** — queries `user_artist_counts ORDER BY play_count DESC LIMIT 1`, returns `str | None`

**`_post_music_roast(guild, line)`** — calls `_get_text_channel(guild)`, sends with `allowed_mentions=AllowedMentions.none()`, swallows `HTTPException` (D-11, T-03-14)

**`_build_roast_line(user_id, scenario_content, fallback_pool, fallback_kwargs)`** — D-08 pattern:
1. Prepare template fallback (`pick_random(pool).format(**kwargs)`)
2. Guard `gemini_service = getattr(self.bot, "gemini_service", None)`
3. Call `get_user_summary(db, user_id)` for taste context
4. `build_chat_prompt("normal", user_context, "")` — locked few-shot DEXTER voice (D-06)
5. `gemini_service.chat(system_prompt, conversation, priority=2)` — never priority 1
6. `except GeminiRateLimitError` + `except Exception` → return fallback_line
7. Post-process Gemini output: strip, cap 500 chars, lowercase first char

**`_log_track` additions** (after existing `increment_daily_stat` calls):

```
Fetch new total_songs_queued (SELECT after update_user_profile UPSERT)

PERS-04 (repeat-song):
  count = await get_repeat_song_count(db, guild_id, user_id, title)
  if count >= REPEAT_SONG_ROAST_THRESHOLD:
    scenario = "{name} has queued '{title}' {count} times today [+ top_artist]"
    line = await _build_roast_line(..., REPEAT_SONG_ROAST_TEMPLATES, {name, title, count})
    await _post_music_roast(guild, line)
  wrapped in try/except — never blocks queuing

PERS-09 (song-count milestone):
  if new_total in config.MILESTONE_SONG_THRESHOLDS:  # exact equality, D-21
    scenario = "{name} just queued their {total}th song [+ top_artist]"
    line = await _build_roast_line(..., MILESTONE_SONG_TEMPLATES, {count: new_total})
    await _post_music_roast(guild, line)
  wrapped in try/except

PERS-09 (streak update + streak-day milestone):
  new_streak, longest, streak_milestone = await update_user_streak(db, user_id, STREAK_TIMEZONE)
  if streak_milestone is not None:
    scenario = "{name} just hit a {milestone}-day streak [+ top_artist + longest record]"
    line = await _build_roast_line(..., MILESTONE_STREAK_TEMPLATES, {days: new_streak, record: longest})
    await _post_music_roast(guild, line)
  wrapped in try/except
```

---

## Verification Results

### Import Check
```
.venv/Scripts/python.exe -c "import cogs.music; print('music import ok')"
music import ok
```

### Full Test Suite
```
251 passed, 1 failed (known pre-existing: test_ytdlp_selfheal)
```
No regressions introduced.

### Structural Review Confirmation

| Criterion | Status |
|-----------|--------|
| /lyrics defers before network call | CONFIRMED — `await interaction.response.defer()` on line 965 |
| /history is guild-scoped | CONFIRMED — `guild_id=str(interaction.guild.id)` |
| LyricsPageView takes list[str] not MusicQueue | CONFIRMED |
| HistoryPageView takes list[dict] not MusicQueue | CONFIRMED |
| LyricsPageView.on_timeout disables buttons AND edits message | CONFIRMED |
| All sends use `allowed_mentions=AllowedMentions.none()` | CONFIRMED — lyrics followup, history send, LyricsPageView edits, HistoryPageView edits, _post_music_roast |
| repeat-song roast always fires at threshold (no chance roll) | CONFIRMED — `if count >= config.REPEAT_SONG_ROAST_THRESHOLD:` no random() |
| milestone fires on exact threshold equality (D-21) | CONFIRMED — `if new_total in config.MILESTONE_SONG_THRESHOLDS:` |
| streak update uses config.STREAK_TIMEZONE | CONFIRMED |
| streak-day milestone references longest_streak (D-20) | CONFIRMED — `record=longest` in fallback_kwargs; scenario includes `their record is {longest} days` |
| all Gemini calls use priority=2 | CONFIRMED — `gemini_service.chat(..., priority=2)` |
| GeminiRateLimitError + Exception both fall back to template | CONFIRMED — two except clauses |
| each roast block try/except-guarded | CONFIRMED — repeat-song, song-count milestone, streak — each in separate try/except |
| DEXTER few-shot voice via build_chat_prompt | CONFIRMED — `build_chat_prompt("normal", user_context, "")` |
| lyrics_service guarded with getattr | CONFIRMED — `getattr(self.bot, "lyrics_service", None)` |

---

## Must-Have Truths Status

| Truth | Status |
|-------|--------|
| User can run /lyrics for current song with paginated results and personality error when nothing playing or no lyrics | MET |
| User can run /history to see server-wide songs (title/artist/who/when), paginated | MET |
| Bot always roasts when user plays same song 3+ times in a day | MET — `count >= REPEAT_SONG_ROAST_THRESHOLD`, no chance roll, D-14 |
| Bot updates user's streak and roasts on song-count (100/250/500/1000) and streak-day (7/14/30/60/100) milestone hits | MET |

---

## Deviations from Plan

None — plan executed exactly as written. The `format_duration` import was added and immediately removed (never needed — embeds.py already imports it). The final commit does not include it.

---

## Commits

| Hash | Description |
|------|-------------|
| 244f232 | feat(03-05): /lyrics + /history commands with pagination; repeat-song + streak/milestone roasts in _log_track |

---

## Known Stubs

None. All data paths are wired:
- `/lyrics` consumes real `LyricsService.get_lyrics` (wired by 03-06; guarded with getattr until then)
- `/history` reads real `song_history` rows via `get_history_rows`
- Roasts consume real `user_artist_counts` + `user_profiles` streak data

---

## Threat Flags

None beyond those already in the plan's threat model (T-03-14 through T-03-18 — all mitigated as designed).

---

## Self-Check: PASSED

- cogs/music.py: FOUND
- Commit 244f232: FOUND
