---
phase: 12-richer-music-ux
reviewed: 2026-06-30T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - cogs/ai.py
  - cogs/library.py
  - logic/autoqueue.py
  - logic/skip_stats.py
  - services/lyrics.py
  - tests/conftest.py
  - tests/test_autoqueue_playback.py
  - tests/test_autoqueue_validate.py
  - tests/test_database_phase12.py
  - tests/test_jam_load.py
  - tests/test_lyrics_lrclib.py
  - tests/test_skip_stats.py
findings:
  critical: 0
  warning: 6
  info: 4
  total: 10
status: issues_found
---

# Phase 12: Code Review Report

**Reviewed:** 2026-06-30
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Reviewed the Phase 12 "richer music UX" surface: AI auto-queue rewrite (widened
search + candidate validation), the new `/jam` guild-shared mixtape commands in
`LibraryCog`, the extracted pure logic modules (`logic/autoqueue.py`,
`logic/skip_stats.py`), the LRCLIB lyrics fallback, and their tests.

Security posture is solid: SQL is parameterised through helpers, `build_azlyrics_url`
strips path-traversal/SSRF vectors, the LRCLIB host is hard-coded with URL-encoded
params, and lyrics are sanitized + sent with `allowed_mentions=none()`. No injection,
secret, or auth findings.

The defects are correctness/robustness issues clustered in two areas: (1) the
auto-queue playback-start glue mutates `queue.current_index` unconditionally, and (2)
the favorites/playlist/jam "start playback" paths build a **persistent** now-playing
player on an **ephemeral** message, diverging from the music cog's public-player
contract. A handful of unguarded `voice.connect()` calls and a fire-and-forget
`create_task` pattern round out the warnings.

## Narrative Findings (AI reviewer)

## Warnings

### WR-01: `current_index` mutated unconditionally in auto-queue, even when playback is not started

**File:** `cogs/ai.py:380-387`
**Issue:** The index pointer is reassigned before the playback gate is evaluated:
```python
voice_client = guild.voice_client
queue.current_index = len(queue.tracks) - len(tracks_added)   # always runs
if should_start_playback(...):
    await music_cog._play_track(guild, queue.get_current())
```
When `should_start_playback` returns False because audio is already flowing (the
defensive branch — `voice_is_playing=True`, exercised by
`test_autoqueue_does_not_double_play_when_audio_already_flowing`), `current_index` is
still moved off the currently-playing track onto the first newly-appended track. The
live player keeps playing the old track, but the queue pointer now lies. When
`_on_track_end` next advances the index it will skip tracks. The mutation should happen
only on the branch that actually starts playback.
**Fix:**
```python
voice_client = guild.voice_client
if should_start_playback(
    connected=voice_client is not None,
    voice_is_playing=voice_client.is_playing() if voice_client else False,
    voice_is_paused=voice_client.is_paused() if voice_client else False,
    has_track=len(queue.tracks) > 0,
):
    queue.current_index = len(queue.tracks) - len(tracks_added)
    await music_cog._play_track(guild, queue.get_current())
```

### WR-02: Now-playing player is created on an ephemeral message in favorites/playlist/jam load

**File:** `cogs/library.py:329-336` (`_queue_favorite`), `cogs/library.py:583-601` (`playlist_load`), `cogs/library.py:908-926` (`jam_load`)
**Issue:** These paths `defer(ephemeral=True)` and then send the persistent
now-playing embed + `NowPlayingView` via `interaction.followup.send(..., view=view)`,
storing the id in `queue._now_playing_message_id`. Because the defer was ephemeral the
followup is ephemeral, so:
- Only the invoking user sees the player and its control buttons. The regular `/play`
  path (`cogs/music.py:412` + `:1041`) defers **non-ephemeral**, so its player is
  public — an inconsistent contract for a shared music bot.
- `NowPlayingView` is a persistent view (`timeout=None`, stable custom_ids per
  CLAUDE.md) but ephemeral messages do not survive a restart and cannot be re-bound.
- The music cog's player manager deletes the previous player via
  `channel.fetch_message(queue._now_playing_message_id)` (`cogs/music.py:724-731`).
  An ephemeral message id is not fetchable from the channel → `NotFound`, so the stale
  ephemeral player is orphaned and a duplicate public player is posted on the next song.
**Fix:** For the playback-start branch, post the now-playing player publicly rather than
as an ephemeral followup (e.g. `interaction.channel.send(embed=embed, view=view)` and
store that id, or route through the music cog's existing now-playing helper so all entry
points share one player-management path), and keep only the short text confirmation
ephemeral.

### WR-03: `voice.connect()` failures are swallowed/ignored, then playback is attempted anyway

**File:** `cogs/library.py:586-595` (`playlist_load`), `cogs/library.py:911-920` (`jam_load`), `cogs/library.py:307-308` (`_queue_favorite`)
**Issue:** In `playlist_load`/`jam_load` a failed `connect()` is logged but execution
falls straight through to `music_cog._play_track(guild, first_track)` with no voice
client connected — `_play_track` then runs against an absent voice client.
In `_queue_favorite` the `connect()` call is not wrapped at all:
```python
voice_client = guild.voice_client
if voice_client is None:
    voice_client = await user_channel.connect()   # unguarded
```
If this raises (permissions, already-connecting race, region failure) the exception
propagates out of the button callback unhandled; the interaction was already deferred
ephemeral, so the user is left with a permanent "thinking…" and no error message.
**Fix:** On connect failure, send a user-facing error and `return` before calling
`_play_track`; wrap the `_queue_favorite` connect in the same `try/except` used by the
load paths.

### WR-04: Fire-and-forget `asyncio.create_task` without retaining task references

**File:** `cogs/ai.py:415-425`
**Issue:** The auto-queue-ignored memory writes are spawned with bare
`asyncio.create_task(...)` and the returned tasks are never stored. Per the asyncio
docs the event loop keeps only a weak reference, so a task can be garbage-collected
mid-flight before `distill_and_remember` completes, silently dropping the memory write
(and any exception it raises is never surfaced). One task is spawned per voice member,
compounding the chance.
**Fix:** Retain references and attach a done-callback, e.g. keep a `set()` on the cog:
```python
task = asyncio.create_task(_memory_svc.distill_and_remember(...))
self._bg_tasks.add(task)
task.add_done_callback(self._bg_tasks.discard)
```

### WR-05: `_get_lrclib` assumes the JSON payload is a list; a non-list response mis-iterates

**File:** `services/lyrics.py:385-399`
**Issue:** `results = json.loads(raw)` is iterated directly with `for item in results`.
LRCLIB's documented success shape is an array, but on an error/edge shape (a bare
object, e.g. `{"code":..., "message":...}`, or a JSON string/number) this iterates dict
keys (strings) and calls `item.get(...)` on a `str`, raising `AttributeError`. It is
caught by the broad `except Exception` and degraded to `None`, but the broad catch also
masks genuine bugs and turns a malformed-payload case into a silent miss.
**Fix:** Guard the type before iterating:
```python
results = json.loads(raw)
if not isinstance(results, list):
    log.warning("LRCLIB returned non-list payload for %s / %s", title, artist)
    return None
```

### WR-06: Auto-queue fall-through loop is re-implemented in the test, not exercised against the real code

**File:** `tests/test_autoqueue_validate.py:177-200`
**Issue:** `TestAutoQueueFallThroughLoop._run_loop` is a hand-copied "pure
re-implementation of the loop body from cogs/ai.py try_auto_queue." The D-14
fall-through behavior (the actual concern of these tests) is therefore validated only
against the copy, not `try_auto_queue`. If the real loop in `cogs/ai.py:311-364` drifts
(e.g. the `continue` on `validated is None` is removed), these tests stay green while
the shipped code regresses — false confidence on the exact bug they exist to guard.
`test_autoqueue_playback.py` does drive the real `try_auto_queue`, but only on the
happy path, not the all-candidates-rejected fall-through.
**Fix:** Add at least one case in `test_autoqueue_playback.py` that drives the real
`try_auto_queue` with a first suggestion whose candidates all fail
`validate_youtube_match`, asserting the second suggestion fills the slot.

## Info

### IN-01: Redundant boolean clause in `ignored_signal`

**File:** `cogs/ai.py:393`
**Issue:** `ignored_signal = prev["skipped"] > 0 and prev["played"] + prev["skipped"] > 0`
— the second operand is always true when the first is true (if `skipped > 0` then
`played + skipped > 0`). Dead condition.
**Fix:** `ignored_signal = prev["skipped"] > 0`.

### IN-02: f-string with no placeholders

**File:** `cogs/library.py:864`
**Issue:** `f"that jam is empty."` has no interpolation; the `f` prefix is noise (flagged
by linters such as Ruff F541).
**Fix:** Drop the `f`: `"that jam is empty."`.

### IN-03: `build_genius_search_query` is applied twice on the Genius path

**File:** `services/lyrics.py:268` then `services/lyrics.py:288`
**Issue:** `get_lyrics` cleans the title/artist once (and the docstring claims the clean
happens "ONCE here so ALL three sources use the same normalized query"), but
`_get_genius` re-runs `build_genius_search_query(title, artist)` on the
already-cleaned input. It is effectively idempotent so no wrong result today, but it
contradicts the stated invariant and is wasted work; a future change to the cleaner
could make the double-pass diverge from AZLyrics/LRCLIB.
**Fix:** Pass the pre-cleaned `q_title, q_artist` straight through and drop the second
`build_genius_search_query` call inside `_get_genius`.

### IN-04: `compute_skip_rate` zero-plays branch is unreachable for normal config

**File:** `logic/skip_stats.py:31-35`
**Issue:** `if total_plays == 0: return 0.0` is only reachable when `min_plays <= 0`
(otherwise `total_plays < min_plays` returns `None` first). With the documented
`config.SKIP_STATS_MIN_PLAYS` floor (> 0) the branch is dead. It is correctly defensive
for the `min_plays=0` test, so this is documentation-only.
**Fix:** Add a one-line comment clarifying the branch only fires when `min_plays == 0`.

---

_Reviewed: 2026-06-30_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
