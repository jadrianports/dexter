---
phase: 04-scale
reviewed: 2026-06-12T00:00:00Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - bot.py
  - cogs/ai.py
  - cogs/events.py
  - cogs/imagine.py
  - cogs/music.py
  - config.py
  - database.py
  - models/message_buffer.py
  - models/queue.py
  - models/server_state.py
  - models/user_profile.py
  - services/queue_persistence.py
  - Dockerfile
  - docker-compose.yml
  - scripts/backup.sh
  - scripts/keepalive.sh
  - .env.example
  - .dockerignore
  - tests/conftest.py
  - tests/test_database_phase4.py
findings:
  critical: 3
  warning: 7
  info: 4
  total: 14
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-06-12
**Depth:** standard
**Files Reviewed:** 20
**Status:** issues_found

## Summary

Phase 4 migrates Dexter from aiosqlite to asyncpg/Postgres, adds AutoShardedBot
sharding, queue persistence, and a Docker/Oracle hosting stack. The asyncpg layer
is generally clean: every user-facing query uses `$N` positional parameters (no
string interpolation of user data), `increment_daily_stat` validates its dynamic
column name against an allowlist before f-string interpolation, transactions in
`log_track_batch` are correctly scoped, and pool acquire/release uses `async with`
throughout — no connection leaks found. Secrets are placeholders in `.env.example`
and `.dockerignore`/docker-compose handle them correctly.

However, three correctness defects will bite in production: (1) the pool teardown
hooks the non-existent `on_close` event, so the pool is never closed on shutdown;
(2) `HistoryPageView` treats the `queued_at` value (now a `datetime` from
TIMESTAMPTZ, not a string) as a string and will raise `TypeError`, breaking
`/history`; and (3) the queue-persistence smart-rejoin restore path has a
voice-client race and ignores the documented `MAX_QUEUE_SIZE_PER_GUILD` /
truncation contract, allowing unbounded restore. Several warnings concern
timezone inconsistency between writes and reads, the `_ready_once` guard not being
reset when the early-return path is taken before it is set, and restore not
re-persisting corrected state.

## Critical Issues

### CR-01: Pool teardown never runs — `on_close` is not a discord.py event

**File:** `bot.py:262-266`
**Issue:** The shutdown handler is registered as `@bot.event` / `async def
on_close()`. discord.py has no `on_close` event — the connection-teardown event is
`on_disconnect` (per-disconnect, not final) and there is no "bot is shutting down"
event at all. As written, `on_close` is silently registered as a custom event that
is never dispatched, so `bot.pool.close()` is never called. On every restart the
asyncpg pool (and its server-side connections) are abandoned rather than drained.
Under the Docker `restart: unless-stopped` policy this leaks Postgres connections
on each cycle and can exhaust `max_connections`. The phase context explicitly calls
out "pool teardown on close" as a required behavior.
**Fix:** Override `close()` on a bot subclass, or close the pool in the `main()`
finally path. Example using a subclass:
```python
class DexterBot(commands.AutoShardedBot):
    async def close(self) -> None:
        if hasattr(self, "pool"):
            await self.pool.close()
        await super().close()
```
Then remove the `on_close` handler.

### CR-02: `/history` crashes — `queued_at` is a datetime, sliced as a string

**File:** `cogs/music.py:209,216`
**Issue:** `queued_at` now comes from a `TIMESTAMPTZ` column (`database.py:86`,
`get_history_rows` selects `queued_at`). asyncpg decodes `TIMESTAMPTZ` to a Python
`datetime`, not a string. The view does:
```python
queued_at = row.get("queued_at") or ""
when = queued_at[:10] if len(queued_at) >= 10 else queued_at
```
`len(datetime)` raises `TypeError: object of type 'datetime.datetime' has no len()`,
and `datetime[:10]` is also invalid. `_build_embed` runs inside the `/history`
command response, so the command raises and the user gets the generic
"something broke" error. This is a real regression from the SQLite era where
`queued_at` was TEXT. The existing test `test_get_history_rows_returns_required_keys`
only checks key presence, not type, so it does not catch this.
**Fix:** Format the datetime explicitly:
```python
queued_at = row.get("queued_at")
when = queued_at.strftime("%Y-%m-%d") if queued_at else ""
```

### CR-03: Queue restore bypasses size cap and races the voice client

**File:** `services/queue_persistence.py:115-131`
**Issue:** Two problems in the restore/rejoin path:
1. **No size cap on restore.** `queue.tracks = [Track.from_dict(t) for t in
   payload.get("tracks", [])]` assigns directly to the list, bypassing
   `MusicQueue.add()` and its `MAX_QUEUE_SIZE_PER_GUILD` guard. A persisted payload
   (which could have grown via auto-queue rounds across a long session) is restored
   in full with no truncation, violating the documented 500-track cap.
2. **Voice-client race.** Smart rejoin does `await vc_channel.connect()` then
   immediately `await music_cog._play_track(guild, queue.get_current())`.
   `_play_track` reads `guild.voice_client` and returns early if it is not yet
   `is_connected()`. Because `voice_client` state can lag the `connect()` return
   during boot, playback may silently no-op, leaving a "restored" queue that is
   marked in-memory but never starts. The `connect()` return value is also
   discarded rather than used. Additionally `current_index` is restored verbatim
   (`payload.get("current_index", 0)`) with no bounds check against the restored
   (possibly truncated) track list — `get_current()` can then return `None` and
   `_play_track(guild, None)` will raise on `track.title`.
**Fix:** Bound the restored list to `config.MAX_QUEUE_SIZE_PER_GUILD`, clamp
`current_index` into `[0, len(tracks)-1]`, capture the connected client from
`connect()` and confirm `is_connected()` before calling `_play_track`, and guard
`get_current()` against `None`:
```python
tracks = [Track.from_dict(t) for t in payload.get("tracks", [])]
queue.tracks = tracks[: config.MAX_QUEUE_SIZE_PER_GUILD]
idx = payload.get("current_index", 0)
queue.current_index = min(max(idx, 0), max(len(queue.tracks) - 1, 0))
...
current = queue.get_current()
if current is not None:
    vc = await vc_channel.connect()
    await music_cog._play_track(guild, current)
```

## Warnings

### WR-01: `_ready_once` guard can be defeated by a failure before it is set

**File:** `bot.py:169-242`
**Issue:** The one-time-init guard sets `bot._ready_once = True` at line 171, but
all of pool creation, cog loading, and queue restore happen *after* that line. If
any awaited call between lines 176–242 raises (e.g. `asyncpg.create_pool` fails on
a cold Postgres, or a `load_extension` raises), `on_ready` aborts — but
`_ready_once` is already `True`, so the next `on_ready` (AutoShardedBot fires it
per-shard and on every reconnect) early-returns at line 169 and never retries init.
The bot then runs permanently with no pool/cogs. Setting the flag before the work
it is meant to guard means a transient boot failure becomes a permanent dead state.
**Fix:** Set `bot._ready_once = True` only after init has fully succeeded (move it
just before `log.info("Dexter is ready.")`), or wrap the init block in try/except
that resets the flag on failure so a later shard/reconnect retries.

### WR-02: Timezone mismatch between daily-stat writes and reads

**File:** `database.py:246,325` vs `database.py:317,346`
**Issue:** `increment_daily_stat` and `get_daily_command_count` key the
`bot_daily_stats` row on `date.today().isoformat()` — the *server's local* date
(naive, process-local). But `get_images_today` and `get_repeat_song_count` filter
on `generated_at::date = CURRENT_DATE` / `queued_at::date = CURRENT_DATE`, where
`CURRENT_DATE` is the *Postgres session* date (typically UTC in a container). When
the host TZ and Postgres TZ differ across a midnight boundary, the mood-system
command count and the image daily-cap / repeat-song counts roll over on different
clocks — the cap and repeat-roast can fire a day early/late relative to the mood
counter. The streak system deliberately uses `config.STREAK_TIMEZONE` to avoid
exactly this; daily stats should be consistent too.
**Fix:** Pick one clock. Either compute the date with
`get_local_date(config.STREAK_TIMEZONE)` everywhere, or use
`(now() AT TIME ZONE '<tz>')::date` in the SQL `CURRENT_DATE` comparisons so all
daily boundaries agree.

### WR-03: Restore does not re-persist truncated/clamped state

**File:** `services/queue_persistence.py:112-132`
**Issue:** After restore mutates `queue.tracks` / `current_index` / `loop_mode`,
nothing calls `persist()` again. If restore truncated the queue (per CR-03 fix) or
the smart-rejoin advanced playback, the persisted row in `guild_queues` is now
stale relative to the live queue. The next mutation will re-persist, but if the bot
crashes again before any mutation, the *original oversized/stale* payload is
restored a second time. Restore should be self-correcting.
**Fix:** After a successful restore + rejoin, call
`await self.persist(guild, queue, vc_id)` to write back the normalized state.

### WR-04: `_play_track` recursion on long unavailable runs can exhaust the stack / spam

**File:** `cogs/music.py:315-331`
**Issue:** When a track is unavailable, `_play_track` calls
`queue.skip()` then recurses: `await self._play_track(guild, next_track, _skipped)`.
A persisted queue restored from Postgres (CR-03) where many cached URLs have expired
could chain hundreds of unavailable tracks into deep recursion before hitting the
500-cap. While 500 frames will not hard-crash CPython, this is fragile and the
recursion also re-runs `_persist_queue` on each hop (line 321), issuing one DB
UPSERT per skipped track in a tight loop.
**Fix:** Convert the skip-chain to an iterative loop that advances until a playable
track is found or the queue is exhausted, persisting once at the end.

### WR-05: `change_presence` on AutoShardedBot only updates one shard

**File:** `bot.py:442-447`
**Issue:** `status_rotation` calls `bot.change_presence(activity=...)` without a
`shard_id`. On `AutoShardedBot`, `change_presence` without `shard_id` updates the
presence on every shard but constructs the payload once; more importantly the
module-level `_status_index` and the dynamically-built pool are global, so with
multiple shards/guilds the "current song" slot reflects whichever guild is found
first in `bot.guilds` iteration — not per-shard state. For a single-shard
deployment this is harmless, but the phase explicitly targets multi-server
sharding; presence will not be meaningful per shard.
**Fix:** Either accept global presence explicitly (document it) or iterate
`bot.shards` and call `change_presence(shard_id=sid, ...)` per shard.

### WR-06: `_get_text_channel` fallback can return an unwritable system channel

**File:** `cogs/music.py:482-495`
**Issue:** Unlike `_get_ambient_channel` (events.py:77-80) and
`_resolve_dexter_channel` (bot.py:93-96), which check
`permissions_for(guild.me).send_messages` before returning `guild.system_channel`,
`MusicCog._get_text_channel` returns `guild.system_channel` unconditionally
(line 490-491) without a send-permission check. If the bot lacks send permission
there, every `channel.send(...)` from the playback engine (now-playing edits, skip
summaries, idle messages) raises `discord.Forbidden`, some of which are not
wrapped in try/except (e.g. `_on_track_end` line 406).
**Fix:** Mirror the other two resolvers — gate the system-channel branch on
`guild.system_channel.permissions_for(guild.me).send_messages`.

### WR-07: backup.sh `pg_dump | oci` pipe masks pg_dump failure under pipefail nuance

**File:** `scripts/backup.sh:49-59`
**Issue:** The script sets `set -euo pipefail` (good), but the success `echo` on
line 61 reports "Backup complete" based only on the pipeline exit. With `pipefail`
a `pg_dump` failure will fail the pipeline, which is correct — however `oci os
object put --file -` will happily upload a *truncated/empty* dump if `pg_dump`
writes a partial stream then errors mid-way after some bytes, and depending on oci
buffering the object may be created before pg_dump's non-zero exit propagates.
There is no post-upload size/integrity check, so a corrupt backup can be silently
stored and later relied upon for restore.
**Fix:** Dump to a temp file first, check `pg_dump` exit and file size, then upload
the verified file; or add `oci os object head` + size assertion after upload.

## Info

### IN-01: Unused / dead imports and fields

**File:** `database.py:8`, `models/queue.py:6`, `models/server_state.py:5`
**Issue:** `database.py` imports `asyncpg` and `json` where `json` is annotated
`# noqa: F401 — used by callers` but is not used in this module (callers import
their own `json`); `models/queue.py` imports `field` from dataclasses but never
uses it; `models/server_state.py` imports `field` (used) but the comment-noise
import patterns are inconsistent. Minor cleanup.
**Fix:** Remove genuinely unused imports (`field` in queue.py, the `json` re-export
in database.py if callers do not actually import it from there).

### IN-02: `clear()` does not reset `current_index`-adjacent persistence

**File:** `models/queue.py:147-155`
**Issue:** `clear()` resets playback state but `auto_lyrics` and `lyrics_thread_id`
are deliberately preserved (documented). However `clear()` is called from the idle
disconnect path (`bot.py:356`) without calling
`queue_persistence.clear_persisted()`, so an idle-timeout-cleared queue is still
restored from Postgres on next boot. Only `/stop` clears the persisted row
(music.py:973-974). This is a behavioral inconsistency, not a crash.
**Fix:** Call `clear_persisted(guild_id)` from the idle-disconnect cleanup too, or
document that idle-cleared queues intentionally restore.

### IN-03: `local_hour` uses naive `datetime.now()` for late-night check

**File:** `cogs/events.py:196-197`
**Issue:** `local_hour = _dt.datetime.now().hour` uses the process-local TZ for the
1–5am late-night roast, while the streak system uses `config.STREAK_TIMEZONE`. In a
UTC container the "late night" window will be UTC, not the users' local time, so
late-night roasts fire at the wrong hours. Consistency nit aligned with WR-02.
**Fix:** Use `datetime.now(ZoneInfo(config.STREAK_TIMEZONE)).hour`.

### IN-04: `_status_index` integer grows unbounded

**File:** `bot.py:61,121-122,155`
**Issue:** `_status_index` increments forever and is only ever used via
`% len(pool)`. Functionally correct, but it is an ever-growing global int. Harmless
in practice (Python ints are arbitrary precision) — noted only for completeness.
**Fix:** Optional: `_status_index = (_status_index + 1) % 1_000_000` or reset
periodically.

---

_Reviewed: 2026-06-12_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
