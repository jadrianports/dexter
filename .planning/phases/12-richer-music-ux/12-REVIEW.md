---
phase: 12-richer-music-ux
reviewed: 2026-06-30T00:00:00Z
depth: standard
files_reviewed: 17
files_reviewed_list:
  - cogs/ai.py
  - cogs/library.py
  - cogs/ops.py
  - config.py
  - database.py
  - logic/autoqueue.py
  - logic/skip_stats.py
  - personality/responses.py
  - services/lyrics.py
  - utils/embeds.py
  - tests/conftest.py
  - tests/test_autoqueue_playback.py
  - tests/test_autoqueue_validate.py
  - tests/test_database_phase12.py
  - tests/test_jam_load.py
  - tests/test_lyrics_lrclib.py
  - tests/test_skip_stats.py
findings:
  critical: 0
  warning: 4
  info: 5
  total: 9
status: issues_found
---

# Phase 12: Code Review Report

**Reviewed:** 2026-06-30
**Depth:** standard
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Reviewed the Phase 12 "richer music UX" surface: guild jams (`cogs/library.py` + `database.py`
helpers), `/skips` + skip-rate logic, auto-queue widened-search/validation (`cogs/ai.py` +
`logic/autoqueue.py`), the LRCLIB lyrics fallback (`services/lyrics.py`), and the supporting
embeds/config/tests.

**Security posture is solid.** Every DB helper is fully `$N`-parameterized — including the new
`guild_jams` helpers and the `get_user_skip_rate` aggregate — and `increment_daily_stat` is the only
helper using string interpolation, gated by a hardcoded allowlist. `services/lyrics.py` correctly
hard-pins the AZLyrics and LRCLIB hosts, builds AZLyrics paths from alphanum-stripped input, and
passes LRCLIB query params via aiohttp's URL-encoding `params=` dict — no SSRF or injection path
found. aiohttp sessions are properly closed via `async with`.

No BLOCKER-class defects found. Four WARNINGs concern robustness (an ineffective DoS size cap, an
unconditional index mutation, an un-referenced background task, and a test-teardown gap) plus five
INFO items.

## Warnings

### WR-01: LRCLIB / AZLyrics response size cap is checked after the full body is already buffered

**File:** `services/lyrics.py:335-339` (AZLyrics) and `services/lyrics.py:380-384` (LRCLIB)
**Issue:** Both fetchers call `await resp.text()` to read the **entire** response into memory and
only *then* check `if len(html) > 500_000`. The docstrings advertise this as a "DoS guard /
500_000-byte cap … prevents memory exhaustion," but by the time the length check runs the whole
(potentially arbitrarily large) body has already been allocated. The cap therefore does not bound
memory at all — it only decides whether to discard an already-buffered payload. Risk is reduced
because both hosts are pinned/trusted, but the guard does not do what it claims.
**Fix:** Enforce the cap during the read instead of after. For example, bound the read and reject
oversized bodies before buffering the whole thing:
```python
MAX_BYTES = 500_000
# Reject on declared length when present...
if (resp.content_length or 0) > MAX_BYTES:
    log.warning("response too large (declared %d bytes)", resp.content_length)
    return None
# ...and hard-cap the actual read so a lying/chunked server can't blow past it:
raw_bytes = await resp.content.read(MAX_BYTES + 1)
if len(raw_bytes) > MAX_BYTES:
    log.warning("response exceeded %d-byte cap", MAX_BYTES)
    return None
raw = raw_bytes.decode("utf-8", errors="replace")
```

### WR-02: `try_auto_queue` mutates `queue.current_index` before the playback-start gate

**File:** `cogs/ai.py:380-387`
**Issue:** `queue.current_index = len(queue.tracks) - len(tracks_added)` is assigned
*unconditionally*, then `should_start_playback(...)` decides whether to call `_play_track`. In the
"audio is already flowing" branch (`should_start_playback` returns False) the index has already been
clobbered to point at the first newly-appended track, abandoning the index of the track that is
actually playing. When that track ends, `_on_track_end` advances from the wrong position and a track
is silently skipped. In the normal natural-exhaustion trigger the voice client is not playing so the
gate fires and the assignment is correct, which is why the existing tests
(`test_autoqueue_does_not_double_play_when_audio_already_flowing` asserts no play but never checks
`current_index`) don't catch it — making this a latent, untested corner.
**Fix:** Only set the index on the branch that actually starts playback:
```python
voice_client = guild.voice_client
if should_start_playback(
    connected=voice_client is not None,
    voice_is_playing=voice_client.is_playing() if voice_client else False,
    voice_is_paused=voice_client.is_paused() if voice_client else False,
    has_track=True,
):
    queue.current_index = len(queue.tracks) - len(tracks_added)
    await music_cog._play_track(guild, queue.get_current())
```

### WR-03: Fire-and-forget `asyncio.create_task` results are never retained

**File:** `cogs/ai.py:415-425`
**Issue:** `asyncio.create_task(_memory_svc.distill_and_remember(...))` is called in a loop with no
reference kept to the returned Task. Per the asyncio docs, the event loop only keeps a *weak*
reference to a task; a pending task with no strong reference can be garbage-collected mid-flight,
silently dropping the memory write (and swallowing any exception it raises). The same pattern is not
guarded by any done-callback, so failures are invisible.
**Fix:** Retain references (and attach an error logger) until completion:
```python
self._bg_tasks: set[asyncio.Task] = getattr(self, "_bg_tasks", set())
task = asyncio.create_task(_memory_svc.distill_and_remember(...))
self._bg_tasks.add(task)
task.add_done_callback(self._bg_tasks.discard)
```
(or route through the existing `make_task(...)` helper used in `bot.py:787`, which already wraps
naming + error handling.)

### WR-04: Test teardown does not drop `user_memories`, leaking rows across runs

**File:** `tests/conftest.py:51-57`
**Issue:** `init_db` creates `user_memories` (schema in `database.py:70`), but the fixture's
teardown `DROP TABLE` list omits it (it does include `user_playlist_tracks`, which is **not** in the
schema — a harmless no-op via `IF EXISTS`, but evidence the list has drifted from the schema). Rows
inserted into `user_memories` by any memory test therefore persist between runs against the same
`dexter_test` DB, which can make per-user cap/eviction/count assertions flaky depending on test
order. Phase 12's own tests don't write memories, but the shared fixture is used project-wide.
**Fix:** Add `user_memories` to the drop list (and drop the stale `user_playlist_tracks`):
```python
"DROP TABLE IF EXISTS guild_queues, song_history,"
" user_artist_counts, image_generation_log,"
" bot_daily_stats, user_profiles,"
" user_favorites, user_playlists, user_memories,"
" resolution_cache, guild_jams CASCADE"
```

## Info

### IN-01: Redundant boolean term in the auto-queue "ignored" signal

**File:** `cogs/ai.py:393`
**Issue:** `ignored_signal = prev["skipped"] > 0 and prev["played"] + prev["skipped"] > 0` — the
second clause is implied by the first (`skipped > 0` already guarantees the sum is `> 0`).
**Fix:** Reduce to `ignored_signal = prev["skipped"] > 0`.

### IN-02: Unreachable duration guard in auto-queue

**File:** `cogs/ai.py:350-351`
**Issue:** `if data["duration"] > config.MAX_SONG_DURATION_SECONDS: continue` can never be True:
`YouTubeService.extract` (reached via `async_extract`) already raises `ValueError` for
`duration is None`, `is_live`, or `duration > MAX_SONG_DURATION_SECONDS`
(`services/youtube.py:148-154`), and that exception is caught by the `except ... continue` directly
above. The check is dead defensive code. Harmless, but misleading — it implies `data["duration"]`
might be `None`/oversized here when it cannot be.
**Fix:** Drop the check, or add a comment noting it's belt-and-suspenders for a contract already
enforced upstream.

### IN-03: `/favorite` reports "cap hit" instead of "duplicate" when at the cap

**File:** `cogs/library.py:376-407`
**Issue:** The cap check (`current_count >= FAVORITES_MAX_PER_USER`) runs before the
insert/duplicate detection. A user who is at 25 favorites and re-favorites a song that is *already*
saved gets `FAVORITE_CAP_HIT` rather than `FAVORITE_DUPLICATE`, even though the action would be a
harmless no-op (`ON CONFLICT DO NOTHING`). Cosmetic only — no data effect.
**Fix:** Short-circuit on the already-saved case before the cap message (e.g. check membership of
`track.video_id` in the user's existing favorites first), or attempt the insert and compare
counts before deciding which message to send.

### IN-04: f-string with no interpolation

**File:** `cogs/library.py:864`
**Issue:** `await interaction.response.send_message(f"that jam is empty.", ephemeral=True)` — the
`f` prefix is unnecessary (no placeholders).
**Fix:** Drop the `f` prefix.

### IN-05: Idle playlist/jam load starts at first newly-added track, skipping pre-existing idle tracks

**File:** `cogs/library.py:592` (`playlist_load`) and `cogs/library.py:917` (`jam_load`)
**Issue:** On the `was_idle and queue.tracks` path, `queue.current_index = len(queue.tracks) - added`
points playback at the first *newly appended* track. If the queue was idle but already held tracks
(e.g. left over, not playing), those pre-existing tracks are skipped over rather than played from the
front. This matches the documented "play the loaded playlist" intent, so it may be deliberate, but
it's worth confirming against the append-semantics described in the module docstring (D-26).
**Fix (if unintended):** Start from the first not-yet-played track (`current_index` of the existing
head) rather than the first appended track.

---

_Reviewed: 2026-06-30_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
