---
phase: 10-critical-path-test-coverage
reviewed: 2026-06-27T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - logic/playback.py
  - logic/health.py
  - logic/roasts.py
  - logic/__init__.py
  - cogs/music.py
  - cogs/ai.py
  - cogs/ops.py
  - cogs/events.py
  - services/queue_persistence.py
  - tests/test_playback_logic.py
  - tests/test_health_logic.py
  - tests/test_roast_logic.py
findings:
  critical: 1
  warning: 5
  info: 3
  total: 9
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-06-27
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Phase 10 extracted three decision-function modules (`logic/playback.py`, `logic/health.py`,
`logic/roasts.py`) from cog glue and wired the callers to delegate to them. The pure
functions themselves are well-structured, side-effect-free, and the test suites are
thorough. The `health` and `playback` extractions are clean.

One BLOCKER was found: the scar #2 fix (`should_start_playback`) was correctly applied
to `try_auto_queue` but was not applied to the four `/play` command branches in
`cogs/music.py`. Those branches still gate playback-start on the `queue.is_playing` flag,
which is stale-True after a failed auto-queue sequence — leaving the user's explicit
`/play` silent. This is exactly the CLAUDE.md Phase 6-8 gotcha the extraction was meant
to address.

Five warnings were also found: two are dead-code artifacts left by the `logic/roasts.py`
extraction (`_check_ambient_cooldown` and the UTC `hour` variable in events.py), one is
an unguarded `QueueFullError` in `try_auto_queue`, one is a duplicated skip-logic path in
the `/skip` slash command, and one is inline imports inside a frequent event handler.

---

## Critical Issues

### CR-01: `/play` command paths gate playback-start on `queue.is_playing` (stale flag), not the voice-client ground truth

**File:** `cogs/music.py:1035, 1319-1320, 1370, 1458`

**Issue:** All four `/play` command start-playback branches check `if not queue.is_playing`
to decide whether to call `_play_track`. This violates the CLAUDE.md Phase 6-8 known
gotcha ("Gate playback-start on `voice_client.is_playing()`, never the `queue.is_playing`
flag") and produces the exact scar #2 scenario in the user-invoked path:

1. Queue exhausted — `_on_track_end` dispatches `AUTOQUEUE` action.
2. `queue.is_playing` is intentionally left `True` (the AUTOQUEUE branch never clears it;
   the glue comment reads "auto-queue will handle it").
3. `try_auto_queue` bails — no song history, all suggestions fail, or Gemini returns
   nothing — without touching `queue.is_playing`.
4. `queue.is_playing` is now stale-True; the voice client is idle.
5. User calls `/play "song B"`. The check `if not queue.is_playing` is False, so
   `_play_track` is never invoked. Track B is added to the queue but the bot stays silent.

`should_start_playback` (the fix for scar #2) was correctly applied to `try_auto_queue`
in `cogs/ai.py:317-322` but was not applied to the `/play` command branches.

The four affected lines are structurally identical:

```python
# lines 1035, 1370, 1458 (single-video paths):
if not queue.is_playing:                  # BUG: stale after failed auto-queue
    queue.current_index = len(queue.tracks) - 1
    await self._play_track(interaction.guild, track)

# line 1319-1320 (playlist path):
if not queue.is_playing and first_track:  # same stale-flag bug
    queue.current_index = len(queue.tracks) - count
    await self._play_track(interaction.guild, queue.get_current())
```

**Fix:** Replace the `queue.is_playing` gate with `should_start_playback` exactly as done
in `try_auto_queue`. The voice client is the only ground truth for "audio is flowing":

```python
from logic.playback import should_start_playback

# After queue.add(track) — single-video paths:
voice_client = await self._ensure_voice(interaction)
if not voice_client:
    return

queue.current_index = len(queue.tracks) - 1
if should_start_playback(
    connected=voice_client is not None,
    voice_is_playing=voice_client.is_playing() if voice_client else False,
    voice_is_paused=voice_client.is_paused() if voice_client else False,
    has_track=queue.get_current() is not None,
):
    await self._play_track(interaction.guild, track)
    embed = embeds.now_playing(track, queue)
    view = NowPlayingView(self.bot)
    msg = await interaction.followup.send(embed=embed, view=view, wait=True)
    queue._now_playing_message_id = msg.id
else:
    embed = embeds.song_queued(track, position)
    await interaction.followup.send(embed=embed)
```

Apply the same pattern to the playlist start-playback check at line 1319.

---

## Warnings

### WR-01: `_check_ambient_cooldown` is dead code after Phase 10 extraction

**File:** `cogs/events.py:38-42`

**Issue:** `_check_ambient_cooldown` was the pre-Phase-10 entry point for the per-user
cooldown check. The Phase 10 extraction moved that check inside `decide_ambient_roast`
(which accepts `seconds_since_last_roast` as a primitive). The `on_voice_state_update`
handler now computes `seconds_since_last_roast` inline and passes it directly to
`decide_ambient_roast` — `_check_ambient_cooldown` is never called anywhere in the file.

The method delegates correctly to `cooldown_elapsed`, so it is not wrong, just unreachable.
Dead code accumulates maintenance surface: future callers may discover it and believe it
is the intended interface, bypassing `decide_ambient_roast`.

**Fix:** Remove `_check_ambient_cooldown` from `EventsCog`. Its logic lives in
`logic.roasts.cooldown_elapsed` (imported and tested). If a caller outside
`on_voice_state_update` needs a cooldown check it should call `cooldown_elapsed` directly.

```python
# DELETE these lines from EventsCog:
def _check_ambient_cooldown(self, user_id: int, ceiling_seconds: int) -> bool:
    """Return True if roast is allowed (ceiling_seconds has elapsed since last roast)."""
    now = asyncio.get_event_loop().time()
    last = self._ambient_roast_times.get(user_id, 0.0)
    return cooldown_elapsed(now - last, ceiling_seconds)
```

### WR-02: Unused `hour` variable in `on_voice_state_update`

**File:** `cogs/events.py:194`

**Issue:** Line 194 assigns `hour = discord.utils.utcnow().hour` with the comment "Use
UTC; late-night check uses local hour below." The variable `hour` is never read again.
`local_hour` (computed at lines 198-199 via `ZoneInfo`) is the one passed to
`decide_ambient_roast`. The assignment is a stale remnant from before the TZ-correct
`local_hour` was introduced (D-06 / D-17 fix). Any reader who finds `hour` will be
confused about its relationship to `local_hour`.

**Fix:** Delete line 194.

```python
# DELETE:
hour = discord.utils.utcnow().hour  # Use UTC; late-night check uses local hour below
```

### WR-03: `queue.add(track)` in `try_auto_queue` not guarded for `QueueFullError`

**File:** `cogs/ai.py:299`

**Issue:** `queue.add(track)` can raise `QueueFullError` when the per-guild cap is
reached. The `/play` command catches this explicitly; `try_auto_queue` does not — the
exception propagates to the broad `except Exception as e` at line 343 and is logged as
"Auto-queue unexpected error." Consequences: the round counter is not incremented
(line 335 never executes), the user sees no announce message, and an expected condition
is misrepresented as an unexpected crash.

**Fix:** Catch `QueueFullError` around `queue.add(track)` inside the suggestions loop:

```python
# in cogs/ai.py, inside try_auto_queue suggestion loop:
from models.queue import QueueFullError

try:
    queue.add(track)
except QueueFullError:
    log.info(
        "auto-queue: queue full at %d — stopping (guild %d)",
        config.MAX_QUEUE_SIZE_PER_GUILD, guild.id,
    )
    break  # stop adding; proceed with whatever was queued so far
tracks_added.append(track)
```

### WR-04: `/skip` slash command duplicates `_do_skip` logic instead of delegating to it

**File:** `cogs/music.py:1484-1519`

**Issue:** `_do_skip` was introduced as the single skip-logic source of truth (called by
`NowPlayingView.skip_button`). The `/skip` slash command (lines 1484-1519) does not call
`_do_skip`; it reimplements the same logic inline: `get_current()` → auto-queued check →
`queue.skip()` → `_persist_queue` → `make_task(_play_track)` → `_refresh_now_playing`.

The duplication is not currently behaviorally divergent, but it creates a maintenance trap:
any future fix to `_do_skip` must be mirrored manually in the slash command.

**Fix:** Refactor `/skip` to call `_do_skip` after the initial guard:

```python
@app_commands.command(name="skip", ...)
async def skip(self, interaction: discord.Interaction) -> None:
    queue = self.get_queue(interaction.guild.id)
    voice_client = interaction.guild.voice_client

    if not voice_client or not queue.is_playing:
        return await interaction.response.send_message(
            embed=embeds.error("Nothing is playing."), ephemeral=True
        )

    await interaction.response.defer()
    next_track = await self._do_skip(interaction.guild, queue, voice_client)
    if next_track:
        await interaction.followup.send(f"Skipped to **{next_track.title}**")
    else:
        await interaction.followup.send("End of queue.")
```

### WR-05: `import datetime` and `from zoneinfo import ZoneInfo` inside `on_voice_state_update`

**File:** `cogs/events.py:197-199`

**Issue:**

```python
import datetime as _dt
from zoneinfo import ZoneInfo as _ZoneInfo
local_hour = _dt.datetime.now(tz=_ZoneInfo(config.STREAK_TIMEZONE)).hour
```

These two imports are inside the body of `on_voice_state_update`, which Discord calls on
every voice state change across every guild. Python's module cache prevents repeated I/O,
but the `sys.modules` lookup and alias assignment still execute on every call. More
importantly, placing imports inside a high-frequency listener is non-idiomatic and
obscures the module's actual dependency surface.

**Fix:** Move both imports to the module's top-level import block, alongside the existing
standard-library imports:

```python
# At the top of cogs/events.py, after existing imports:
import datetime
from zoneinfo import ZoneInfo

# Inside on_voice_state_update, replace the inline block with:
local_hour = datetime.datetime.now(tz=ZoneInfo(config.STREAK_TIMEZONE)).hour
```

---

## Info

### IN-01: `decide_on_track_end` `is_playing` parameter is vestigial in the primary caller

**File:** `logic/playback.py:59-95`, `cogs/music.py:763`

**Issue:** `_on_track_end` always passes `is_playing=True` (the early return at line 739
pre-filters the `is_playing=False` case). The `NOOP` branch of `decide_on_track_end`
is reachable only in unit tests, never from the live call site. The parameter is
documented, typed, and tested correctly — but in the primary caller's context it is
a constant.

This is not a bug, but it makes the API slightly misleading: a caller that discovers the
function might legitimately pass `is_playing=False` expecting a different result at a new
call site, not realising the existing glue pre-guards it. A note in the docstring or a
private helper that removes the `is_playing` parameter would reduce confusion.

**Fix (optional):** Add a note to `_on_track_end`'s comment:

```python
action = decide_on_track_end(
    is_playing=True,  # pre-filtered: on_track_end only runs if queue.is_playing was True
    ...
)
```

### IN-02: Implicit operator precedence in two "nothing playing" guards

**File:** `cogs/music.py:376, 1813`

**Issue:** Both guards use the pattern:

```python
if not track or not queue.is_playing and not queue.is_paused:
```

Python evaluates this as `(not track) or ((not queue.is_playing) and (not queue.is_paused))`
which is almost certainly the intent — but without explicit parentheses the precedence
requires mental parsing. A different reader (or a linter) may misread it.

**Fix:** Add explicit parentheses:

```python
if not track or (not queue.is_playing and not queue.is_paused):
```

### IN-03: Playlist import skips `_log_track` for all imported tracks

**File:** `cogs/music.py:1266-1322`

**Issue:** The playlist branch loops `playlist_results`, adds each `Track` to the queue,
and starts playback — but never calls `_log_track`. Song history (`song_history`),
user profiles (`user_profiles`), artist counts (`user_artist_counts`), daily stats, and
streak tracking are all silently skipped for every track imported from a playlist URL.
Direct-URL `/play` and search-pick `/play` both call `_log_track`. This creates an
inconsistency: playlist users accumulate no history and never trigger repeat-song or
milestone roasts via playlist import.

**Fix:** Call `_log_track` for the first track at minimum (the one that starts playing),
or batch-log all imported tracks (accepting that `_log_track` must become more efficient
for bulk use). At a minimum, document the gap:

```python
# After the playlist loop:
if first_track and count > 0:
    # Log the first (auto-played) track; remaining tracks are background-queued
    await self._log_track(interaction, first_track)
```

---

_Reviewed: 2026-06-27_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
