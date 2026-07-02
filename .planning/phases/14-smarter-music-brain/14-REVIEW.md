---
phase: 14-smarter-music-brain
reviewed: 2026-07-03T00:00:00Z
depth: standard
files_reviewed: 19
files_reviewed_list:
  - cogs/ai.py
  - cogs/library.py
  - cogs/music.py
  - config.py
  - database.py
  - logic/autoqueue.py
  - logic/taste.py
  - personality/prompts.py
  - personality/responses.py
  - services/memory.py
  - tests/test_autoqueue_validate.py
  - tests/test_autoqueue_wiring.py
  - tests/test_config.py
  - tests/test_database_phase14.py
  - tests/test_discover.py
  - tests/test_jam_suggest.py
  - tests/test_memory.py
  - tests/test_prompts.py
  - tests/test_taste_logic.py
findings:
  critical: 1
  warning: 3
  info: 4
  total: 8
status: issues_found
---

# Phase 14: Code Review Report

**Reviewed:** 2026-07-03T00:00:00Z
**Depth:** standard
**Files Reviewed:** 19
**Status:** issues_found

## Summary

Phase 14 adds taste-aware auto-queue (BRAIN-01), `/discover` (BRAIN-02), and `/jam suggest` (BRAIN-03) on top of new guild/invoker-scoped aggregate SQL helpers.

Two areas the task flagged for scrutiny hold up well:

- **SQL injection safety:** every new aggregate helper (`get_recently_skipped`, `get_user_top_artist`, `get_artist_cooccurrence`, and the extended `search_memories` kind clause) binds all user/guild/artist values through `$N` positional parameters. The one dynamic fragment in `search_memories` (the `kind_clause`) is a fixed literal string chosen by a `None` check, not interpolated user data, and the `LIMIT $N` index is computed from a param-count integer, not text. No injection path found.
- **Accuracy firewall:** `/discover` correctly queues the SQL-derived `adjacent_artists[0]` (never a Gemini-parsed value) and instructs Gemini to wrap fixed names as commentary only; `build_recommendation_prompt` never interpolates counts; `logic/taste.summarize_taste` emits only number-free templates. The firewall is structurally sound.

The primary defect is behavioral, not security: the `/discover` confirm-to-queue button never joins voice or persists the queue, so pressing "queue it" while the bot is idle silently no-ops after reporting success. Secondary concerns are a timezone-inconsistent co-occurrence bucket and Phase 14's source-assertion-only tests, which cannot catch the queue-button defect.

## Critical Issues

### CR-01: `/discover` "queue it" button never connects to voice — silent failure on the cold path

**File:** `cogs/music.py:514-589` (`DiscoverQueueView.queue_button`)
**Issue:** The button adds a track and gates playback on `should_start_playback(connected=voice_client is not None, ...)`. When the bot is **not already in a voice channel**, `connected=False`, so `should_start_playback` returns `False` — the track is appended to `queue.tracks` but `_play_track` is never called and **the bot never joins voice**. The user still receives `queued **{track.title}**.`, a false success. `/discover` is a standalone discovery command with no precondition that audio is already flowing, so running it while the bot is idle and pressing "queue it" is a completely normal usage, not a rare edge. Every other queue-add site (main `/play` at line 636, `LibraryCog._queue_favorite`, `playlist_load`, `jam_load`) explicitly calls `user_channel.connect()` before playback; this path omits it.

**Fix:** Mirror the connect-then-play pattern used elsewhere. Require the presser to be in voice, connect if needed, then start playback:
```python
guild = self.bot.get_guild(self.guild_id)
member = guild.get_member(interaction.user.id) if guild else None
if member is None or not member.voice or not member.voice.channel:
    await interaction.followup.send("join a voice channel first.", ephemeral=True)
    return
voice_client = guild.voice_client
if voice_client is None:
    try:
        voice_client = await member.voice.channel.connect()
    except Exception as exc:
        log.warning("discover: connect failed: %s", exc)
        await interaction.followup.send("couldn't join your voice channel. try again.", ephemeral=True)
        return
# ... queue.add(track) ...
if should_start_playback(connected=voice_client is not None,
                         voice_is_playing=voice_client.is_playing(),
                         voice_is_paused=voice_client.is_paused(),
                         has_track=len(queue.tracks) > 0):
    queue.current_index = len(queue.tracks) - 1
    await music_cog._play_track(guild, queue.get_current())
```

## Warnings

### WR-01: `get_artist_cooccurrence` buckets by Postgres session timezone, not `STREAK_TIMEZONE`

**File:** `database.py:1443-1459`
**Issue:** Co-occurrence is defined as `date_trunc('day', queued_at)` over `TIMESTAMPTZ` columns. `date_trunc` on a `timestamptz` resolves the day boundary using the Postgres session `TimeZone` GUC (UTC on Neon by default), not `config.STREAK_TIMEZONE`. CLAUDE.md is explicit that community-time/calendar-day logic must use `ZoneInfo(STREAK_TIMEZONE)` because the host runs UTC (gotcha D-06/D-17). Two songs played the same evening but straddling UTC midnight (e.g. 8pm and 1am ET) fall into different "days," fragmenting the co-occurrence signal that drives `/discover`. The result is also environment-dependent (changes if the session tz ever differs).

**Fix:** Bucket in the configured timezone so the day boundary matches the rest of the bot:
```sql
date_trunc('day', queued_at AT TIME ZONE $tz)   -- pass config.STREAK_TIMEZONE as a param
```
(add `tz` as a bound `$N` parameter in both the CTE and the join).

### WR-02: `/discover` queued track is never persisted — lost on restart

**File:** `cogs/music.py:559-574` (`DiscoverQueueView.queue_button`)
**Issue:** After `queue.add(track)` the button never calls `self.bot.queue_persistence.persist(...)`. Every other queue-add entry point persists (`_queue_favorite` at library.py:334-338, `playlist_load` at 590-598, `jam_load` at 924-932, `_persist_state` in music.py). A track queued via `/discover` therefore vanishes on the next restart/smart-rejoin, silently diverging from the persisted-queue invariant the rest of the codebase upholds.

**Fix:** After a successful `queue.add`, persist the queue with the connected voice channel id, matching the sibling paths:
```python
if hasattr(self.bot, "queue_persistence"):
    try:
        await self.bot.queue_persistence.persist(guild, queue, voice_client.channel.id)
    except Exception as exc:
        log.debug("discover: queue persist failed: %s", exc)
```

### WR-03: Phase 14 tests assert source text, not behavior — cannot catch CR-01/WR-02

**File:** `tests/test_discover.py:18-156` (and the same pattern across `tests/test_autoqueue_wiring.py`)
**Issue:** The `/discover` tests are entirely `inspect.getsource(...)` string-containment assertions (e.g. `assert "should_start_playback(" in src`, `assert "queue.add(" in src`). They verify that certain identifiers appear in the source, not that the runtime does the right thing. Precisely because of this, they pass green while CR-01 (missing `connect()`) and WR-02 (missing `persist()`) ship — a behavioral test exercising the "bot idle, press queue" path would have caught both. This gives false confidence for a phase whose whole value is runtime behavior.

**Fix:** Add at least one behavioral test per new interactive surface driving the callback with fakes for the voice client / youtube service, asserting (a) the bot connects when idle and (b) `_play_track` is invoked. If the project's mock-free convention forbids this, at minimum add a source assertion that the connect path exists (e.g. `assert ".connect()" in _discover_view_button_source()`) so the gap is locked.

## Info

### IN-01: Redundant sub-expression in auto-queue `ignored_signal`

**File:** `cogs/ai.py:471`
**Issue:** `ignored_signal = prev["skipped"] > 0 and prev["played"] + prev["skipped"] > 0`. When `prev["skipped"] > 0`, `prev["played"] + prev["skipped"] > 0` is always true, so the second conjunct is dead.
**Fix:** Reduce to `ignored_signal = prev["skipped"] > 0` (or clarify intent if a `played`-based gate was meant).

### IN-02: `taste_episode` bypasses the number backstop via `exempt_numbers`

**File:** `services/memory.py:451-459` and `services/memory.py:507-509`
**Issue:** For `kind == "taste_episode"`, `distill(..., exempt_numbers=True)` skips the `contains_number()` gate. The rationale (digits are artist names like "Blink-182") is documented and the source `raw_text` from `summarize_taste` is number-free, but if Gemini injects a count during distillation it would pass into the `THE ROOM TENDS TO LIKE` block. Risk is low because that block feeds a recommendation prompt (output is song picks, not user-facing stats) and `build_chat_prompt` pins numbers to USER CONTEXT — defense-in-depth holds. Noting for firewall completeness; this is inherited Phase 13 behavior reused by Phase 14.
**Fix:** None required now; if tightening is desired, keep the digit block and whitelist artist-name digit patterns instead of a blanket exemption.

### IN-03: `/discover` confirm button has no ownership/voice gate, unlike sibling views

**File:** `cogs/music.py:514-524`
**Issue:** `DiscoverQueueView` posts a **public** message and its button has no `interaction.user.id` check, while `FavoritesView`, `QueueButton`/`RemoveButton`, and `JamSuggestConfirmView` all gate on the invoker. For a communal music bot this is a defensible design choice, but it is an inconsistency worth a deliberate decision.
**Fix:** If communal queuing is intended, leave as-is and document it; otherwise gate on `self.requested_by`.

### IN-04: `/discover` button misattributes `requested_by` when a different user presses it

**File:** `cogs/music.py:556`
**Issue:** The queued `Track.requested_by=self.requested_by` is the original `/discover` invoker, but any user can press the public button (see IN-03). The "requested by" shown on the now-playing embed will credit the wrong person.
**Fix:** Use `interaction.user.id` in the button callback (the presser), as `JamSuggestConfirmView.confirm_button` already does at library.py:1243.

---

_Reviewed: 2026-07-03T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
