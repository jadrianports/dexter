---
phase: 07-player-ux-filters
reviewed: 2026-06-19T00:00:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - bot.py
  - cogs/library.py
  - cogs/music.py
  - config.py
  - database.py
  - models/queue.py
  - personality/responses.py
  - services/audio.py
  - services/queue_persistence.py
  - tests/conftest.py
  - tests/test_audio.py
  - tests/test_database_phase7.py
  - tests/test_formatters.py
  - tests/test_queue.py
  - tests/test_responses.py
  - utils/embeds.py
  - utils/formatters.py
findings:
  critical: 2
  warning: 6
  info: 4
  total: 12
status: issues_found
---

# Phase 7: Code Review Report

**Reviewed:** 2026-06-19
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Phase 7 adds player-UX primitives (elapsed tracking, seek/jump/previous, audio
filters), the `NowPlayingView` button controller, the `LibraryCog` favorites +
playlist groups, and the `user_favorites` / `user_playlists` Postgres helpers.

The asyncpg layer is correctly parameterised throughout — no SQL-injection
surface, and no raw user text reaches FFmpeg (filter presets are resolved from a
fixed `config.FFMPEG_FILTERS` allowlist). The elapsed/jump queue primitives are
clean and well unit-tested. The playback generation-counter discipline from
CLAUDE.md is respected by all new commands (they `await _play_track` directly and
let it manage `voice_client.stop()`).

Two correctness defects stand out: the favorites queue path calls
`QueuePersistenceService.persist()` with the wrong argument shape (an int instead
of a guild object, and a missing required parameter), which raises every time but
is silently swallowed; and a filtered/seeked stream-fallback path passes an
`-af` audio filter to `FFmpegPCMAudio` while *dropping* the stream reconnect
flags, regressing reconnect robustness on the exact path most likely to be a
flaky network stream. Several warning-level robustness gaps round it out.

## Critical Issues

### CR-01: `_queue_favorite` calls `persist()` with wrong/missing arguments — favorites queue state is never persisted

**File:** `cogs/library.py:305-309`
**Issue:** `QueuePersistenceService.persist()` has the signature
`persist(self, guild, queue, voice_channel_id)` (services/queue_persistence.py:31)
and internally does `str(guild.id)`. The favorites path calls it as:

```python
await self.bot.queue_persistence.persist(guild.id, queue)
```

This passes `guild.id` (an `int`) as the `guild` parameter and omits the required
`voice_channel_id` positional argument. The call raises `TypeError: persist()
missing 1 required positional argument: 'voice_channel_id'` before it ever runs —
and even if it didn't, `str(guild.id)` would become `str(int.id)` → `AttributeError`.

Because the call is wrapped in `try/except Exception` and only logged at
`log.debug`, the failure is completely silent: a song queued from `/favorites`
is added to the in-memory queue but **never persisted**, so it is lost on the
next bot restart (the documented Phase 4/5 queue-persistence guarantee). The
correct 3-arg form is already used elsewhere (cogs/library.py:556 in
`playlist_load` and cogs/music.py:713 in `_persist_queue`).

**Fix:**
```python
# Mirror MusicCog._persist_queue: pass the guild object and the live vc id.
if hasattr(self.bot, "queue_persistence"):
    try:
        vc_id = guild.voice_client.channel.id if guild.voice_client else None
        await self.bot.queue_persistence.persist(guild, queue, vc_id)
    except Exception as exc:
        log.debug("favorites: queue persist failed: %s", exc)
```
Better: route through `music_cog._persist_queue(guild, queue)` so the favorites
path can never drift from the canonical persistence call again.

### CR-02: Stream-fallback seek/filter path drops reconnect flags — regresses network resilience

**File:** `services/audio.py:118-119` (via `_build_ffmpeg_opts`, audio.py:24-46)
**Issue:** On the stream-fallback path (download failed → live HTTP stream),
when a seek or filter is active the code does:

```python
opts = _build_ffmpeg_opts(seek_seconds, ffmpeg_filter)
return discord.FFmpegPCMAudio(stream_url, **opts)
```

`_build_ffmpeg_opts` *does* include `_RECONNECT_FLAGS` in `before_options`, but
note the non-seek/non-filter fallback uses `FFMPEG_STREAM_OPTS` which is
identical — so reconnect is preserved there. The real problem is narrower but
still a defect: `_build_ffmpeg_opts` only prepends `-ss` to `before_options`
**after** the reconnect flags. For HTTP seeking, `-ss` placed *after* the input
in ffmpeg semantics is an output-seek (decode-and-discard) rather than an
input-seek; placed in `before_options` it is applied as an input option, but
ffmpeg requires `-reconnect_at_eof`-class flags and `-ss` ordering to interact
correctly. More importantly, a seek on a *PCM live stream* re-transcodes from
byte 0 and the `-ss` input seek against a non-seekable HTTP source can hang up
to `DOWNLOAD_TIMEOUT`-less (there is no timeout on this ffmpeg spawn), producing
a silent/stalled track with no fallback. The cached/downloaded path is fine; the
stream path needs either to reject seek (seek only meaningful on a local file) or
to bound the ffmpeg start.

**Fix:** Only honour `seek_seconds` on the cached/downloaded local-file paths;
for the stream fallback, ignore the offset (or restart from 0) and log it, since
input-seeking a non-seekable HTTP stream is unreliable:
```python
# Stream fallback — seeking a live HTTP source is unreliable; start from 0.
if not use_opts:
    return discord.FFmpegPCMAudio(stream_url, **FFMPEG_STREAM_OPTS)
# keep filter, drop seek on the stream path
opts = _build_ffmpeg_opts(0, ffmpeg_filter)
return discord.FFmpegPCMAudio(stream_url, **opts)
```

## Warnings

### WR-01: `delete_playlist` infers success from a fragile status-string suffix

**File:** `database.py:604-609`
**Issue:** `delete_playlist` returns `result.endswith("1")`. asyncpg's
`execute()` returns a command tag like `"DELETE 1"` / `"DELETE 0"`. Because the
delete is PK-scoped this is safe today, but `endswith("1")` would also be True
for `"DELETE 11"`, `"DELETE 21"`, etc. — any deletion count ending in 1. This is
a latent correctness trap if the WHERE clause is ever broadened.
**Fix:** Parse the count explicitly:
```python
# "DELETE N" → N
deleted_count = int(result.split()[-1]) if result else 0
return deleted_count > 0
```

### WR-02: `favorite` duplicate detection issues two extra COUNT round-trips and is racy

**File:** `cogs/library.py:358-389`
**Issue:** The duplicate check runs `count_favorites` before AND after
`add_favorite`, comparing the two. Under concurrent `/favorite` presses by the
same user (double-click, two clients) the before/after counts can interleave and
misreport DUPLICATE vs SAVED. It also costs three DB queries for one insert.
`ON CONFLICT DO NOTHING` already makes the insert idempotent — the result is
recoverable from the command tag instead.
**Fix:** Have `add_favorite` return whether a row was inserted (asyncpg
`execute` returns `"INSERT 0 1"` on insert, `"INSERT 0 0"` on conflict), and
branch on that. Eliminates the race and two round-trips.

### WR-03: Favorites cap is checked then inserted non-atomically (cap can be exceeded)

**File:** `cogs/library.py:358-377`
**Issue:** `count_favorites` (check `>= 25`) and `add_favorite` run as two
separate statements with no transaction. Two concurrent `/favorite` calls at
count 24 both pass the cap check, both insert distinct video_ids, leaving the
user at 26 — over the documented D-21 cap of 25. Same TOCTOU pattern exists for
playlists (`count_playlists` + `save_playlist`, library.py:478-488).
**Fix:** Enforce the cap inside a single statement/transaction, e.g. an
`INSERT … SELECT … WHERE (SELECT count(*) …) < 25`, or wrap count+insert in
`async with conn.transaction()` with `SELECT … FOR UPDATE` semantics. At minimum,
document the cap as best-effort.

### WR-04: `playlist_load` proceeds to "now playing" even when the voice connect failed

**File:** `cogs/library.py:565-583`
**Issue:** If `user_channel.connect()` raises, the exception is caught and logged
(line 571-572) but `voice_client` stays `None` and execution falls through to
`music_cog._play_track(guild, first_track)`. `_play_track` returns early when
`guild.voice_client` is falsy, so nothing plays — yet the code then sends a
now-playing embed implying playback started. The user sees a "now playing" card
for a silent queue.
**Fix:** After the connect attempt, bail out with an error message if
`guild.voice_client is None`, before sending the now-playing embed:
```python
if voice_client is None and guild.voice_client is None:
    await interaction.followup.send("couldn't join voice. try again.", ephemeral=True)
    return
```

### WR-05: `filter_cmd` un-pauses a paused track as a side effect

**File:** `cogs/music.py:1585-1588`
**Issue:** When a filter is applied while the track is *paused*
(`queue.is_paused` True), the branch `if current and (queue.is_playing or
queue.is_paused)` calls `_play_track(..., offset_seconds=pos)`, which sets
`is_playing=True, is_paused=False` and starts the source. Applying a filter
silently resumes playback the user had deliberately paused — a surprising
side effect.
**Fix:** Preserve pause state: after re-creating the source at `pos`, if the
track was paused before, immediately `voice_client.pause()` + restore
`queue.mark_paused()`, or refuse the filter change while paused with a hint to
resume first.

### WR-06: `seek`/`previous`/`filter` reject a paused track inconsistently

**File:** `cogs/music.py:1459, 1501, 1585`
**Issue:** `seek` guards with `if not track or not queue.is_playing` — so seeking
is impossible while paused, even though there is a valid current track and a
meaningful position to seek to. `previous` allows paused (`is_playing or
is_paused`), and `filter` allows paused. The three navigation commands disagree
on whether "paused" counts as "active," which is an inconsistent contract and
will confuse users (seek silently refused while paused).
**Fix:** Standardise the active-track guard across seek/previous/filter to
`(queue.is_playing or queue.is_paused)` and a non-None current track, then handle
the paused-resume decision uniformly (see WR-05).

## Info

### IN-01: `parse_time` rejects valid `mm:ss` where minutes ≥ 60

**File:** `utils/formatters.py:39`
**Issue:** For `mm:ss` input, `if seconds > 59 or minutes > 59: return None`.
A user entering `75:00` for a 75-minute track (within the conceptual range)
gets a parse failure. Given `MAX_SONG_DURATION_SECONDS` is 900 (15 min) this is
not reachable for real tracks, but the bound is arguably wrong for the format
(`mm:ss` minutes are not inherently capped at 59). Low impact.
**Fix:** Drop the `minutes > 59` check for the two-component form, or document
the intended cap.

### IN-02: `now_playing()` keeps a dead `elapsed` parameter

**File:** `utils/embeds.py:18, 36-37`
**Issue:** The `elapsed: int | None = None` parameter is documented as "kept for
backward compat but ignored" and is genuinely never read — the function always
calls `queue.elapsed_seconds()`. Dead parameter invites mis-use by callers who
think passing it does something.
**Fix:** Remove the parameter (no Phase 7 caller passes it) or assert it is None.

### IN-03: `conftest.py` teardown drops a non-existent table

**File:** `tests/conftest.py:45`
**Issue:** The teardown `DROP TABLE … user_playlist_tracks CASCADE` references
`user_playlist_tracks`, which is not in `SCHEMA_SQL` (the design stores tracks as
a JSONB `snapshot` column on `user_playlists`, not a separate table). `DROP TABLE
IF EXISTS` makes it harmless, but it signals a stale schema assumption left over
from an earlier design.
**Fix:** Remove `user_playlist_tracks` from the DROP list.

### IN-04: `test_audio.py::test_cleanup_removes_oldest` does not actually assert which files were removed

**File:** `tests/test_audio.py:75-91`
**Issue:** The test "touches" files 3 and 4 to make them newest, then only
asserts `total_size <= limit`. It never verifies that the *oldest* files (0,1,2)
were the ones deleted — the cleanup could delete the wrong files and the test
would still pass. Weak coverage for the LRU-by-atime contract.
**Fix:** Assert that `vid3.opus` and `vid4.opus` survive and the older ones are
gone, not just the aggregate size.

---

_Reviewed: 2026-06-19_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
