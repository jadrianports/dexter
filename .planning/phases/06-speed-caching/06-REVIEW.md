---
phase: 06-speed-caching
reviewed: 2026-06-23T20:57:07Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - bot.py
  - cogs/music.py
  - cogs/ops.py
  - config.py
  - database.py
  - models/queue.py
  - services/audio.py
  - services/metrics.py
  - services/youtube.py
  - utils/embeds.py
  - tests/conftest.py
  - tests/test_audio.py
  - tests/test_phase6_perf.py
  - tests/test_youtube.py
findings:
  critical: 1
  warning: 7
  info: 5
  total: 13
status: issues_found
resolved_in: 08c910a
resolved:
  - CR-01  # clear() now keeps _play_generation monotonic
  - WR-01  # cache hit recorded once, only after successful extract
  - WR-03  # eviction unlink guarded; one failure no longer aborts the pass
  - WR-04  # record_ttfa now wired in _play_track (PERF-06)
deferred:
  - WR-02  # prefetch wait_for cancels awaiter but not executor-thread yt-dlp (follow-up)
  - WR-07  # daily-stats UTC vs STREAK_TIMEZONE (pre-existing, out of Phase 6 scope)
---

# Phase 6: Code Review Report

**Reviewed:** 2026-06-23T20:57:07Z
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Phase 6 adds a resolution cache (table + asyncpg helpers + `play()` intercept),
`PerfMetrics`, a SponsorBlock postprocessor chain + codec logging, an
`asyncio.wait_for` download timeout, an LFU `cleanup_cache` rewrite, and a
fire-and-forget generation-guarded `_prefetch_next_track`.

Much of the work is solid: SQL is uniformly parameterized, the LFU protected-set
guard is correctly enforced at both the sort key and the unlink loop, the
download-timeout fallback chain is sound, and `set_resolution_cache` correctly
refreshes TTL on conflict.

One correctness defect rises to BLOCKER: `MusicQueue.clear()` resets
`_play_generation` to `0`, which **breaks the monotonic generation-guard
invariant** that the prefetch task and every after-callback depend on. After a
`/stop` → `/play` cycle a stale prefetch (or a stale after-callback) can collide
on generation `1` and be mistaken for current — the exact double-play / stale
race CLAUDE.md says this counter exists to prevent — and the prefetch `finally`
slot cleanup can then clear a live download's protection.

Seven warnings cover: a double-counted cache-hit metric that corrupts the very
`/stats` numbers Phase 6 exists to optimize, an orphaned-download leak on
prefetch timeout, an unguarded `unlink` that can wedge cache cleanup, a
`record_ttfa` metric with no call site (so `/stats` always shows 0.0s TTFA), a
cache "hit" that still re-extracts (smaller speedup than designed), an
eviction/prefetch snapshot race, and a UTC-vs-`STREAK_TIMEZONE` "today" boundary
mismatch in the daily-stats helpers.

## Critical Issues

### CR-01: `MusicQueue.clear()` resets `_play_generation` to 0, breaking the prefetch + after-callback generation guard

**File:** `models/queue.py:225` (interacts with `cogs/music.py:625-693`, `1489-1490`, `901-902`, `bot.py:505`)
**Issue:**
The entire stale-callback defense in this codebase relies on `_play_generation`
being **monotonically increasing** — `after_callback` (music.py:584) and the
prefetch entry/post-download guards (music.py:642, 672) all compare against a
captured `expected_gen`/`current_gen` and assume a higher live generation means
"this work was superseded, discard it."

`clear()` violates the invariant by resetting the counter to `0`:

```python
def clear(self) -> None:
    ...
    self._play_generation = 0   # ← resets the monotonic invariant
```

Every teardown site does `_play_generation += 1` *then* `clear()`
(music.py:1489-1490 `/stop`, music.py:901-902 `_do_stop`, bot.py:505 idle-leave,
music.py:1884 reconnect-failure), so the increment is immediately discarded and
the counter returns to 0. This re-opens a generation **collision**:

1. Track plays: gen 0 → `_play_track` bumps to 1, `current_gen=1`, spawns prefetch `expected_gen=1`.
2. `/stop`: gen 1 → `+=1` → 2, then `clear()` → **0**.
3. New `/play`: gen 0 → `_play_track` bumps to 1, `current_gen=1`, spawns a *new* prefetch `expected_gen=1`.
4. The OLD in-flight prefetch from step 1 finishes its download. Its post-download
   guard checks `queue._play_generation (1) != expected_gen (1)` → **False** →
   the stale result is accepted as current.
5. The `finally` block (music.py:692) then runs
   `if queue._prefetch_video_id == track.video_id: queue._prefetch_video_id = None`
   — if the new track happens to occupy the slot, the stale task clears the live
   task's protection, re-exposing an in-flight download to LFU eviction.

The same collision lets a stale `after_callback` (still holding `current_gen=1`)
fire `_on_track_end` against the new generation's queue — the double-play /
advance-on-stale-callback race the counter is documented to prevent
(CLAUDE.md "Playback Engine Patterns" and the Phase 1 gotcha on `voice_client.stop()`).

**Fix:** Never reset the generation counter; only ever increment it.

```python
def clear(self) -> None:
    self.tracks.clear()
    self.current_index = 0
    self.is_playing = False
    self.is_paused = False
    self.loop_mode = LoopMode.OFF
    self._now_playing_message_id = None
    self._play_generation += 1   # invalidate, never reset to 0
    self.active_filter = "off"
    self.playback_started_at = None
    self.paused_at = None
    self._prefetch_video_id = None
    self._prefetch_task = None
```

The four teardown sites that already do `_play_generation += 1` before `clear()`
become redundant (harmless) once clear() increments; the invariant is that the
counter is strictly non-decreasing for the lifetime of the queue object.

## Warnings

### WR-01: Resolution-cache result is recorded twice for one `/play`, corrupting the cache-hit-rate metric

**File:** `cogs/music.py:1334-1335`, `1342-1352`, `1408-1409`
**Issue:**
On a cache hit the code records the hit *before* confirming it is usable:

```python
if cached_res is not None:
    if hasattr(self.bot, "perf_metrics"):
        self.bot.perf_metrics.record_cache_result(True)   # line 1335
    ...
    try:
        data = await self.youtube.async_extract(watch_url)
    except ValueError as e:
        cached_res = None        # stale/removed → fall through to search
    except Exception as e:
        cached_res = None        # network/yt-dlp blip → fall through to search
```

When the cached extract raises (stale video, livestream now, transient network
error), `cached_res` is set to `None` and execution falls through to the
"Cache miss" block, which calls `record_cache_result(False)` at line 1409 for the
**same** `/play`. The rolling window therefore receives **two samples** (one
True, one False) from a single command, inflating `samples` and skewing
`cache_hit_rate` — the headline number Phase 6 exists to optimize and surfaces in
`/stats`. (The duration cap / livestream rejection itself is *not* bypassed —
`async_extract` still raises `ValueError` for over-length/live videos, so the cap
holds; the defect is purely metric corruption + a wasted recorded "hit.")

**Fix:** Record the result exactly once, after the outcome is known:

```python
if cached_res is not None:
    try:
        data = await self.youtube.async_extract(watch_url)
    except Exception as e:
        log.info("resolution_cache unusable (%s), treating as miss", e)
        cached_res = None

if cached_res is not None:
    if hasattr(self.bot, "perf_metrics"):
        self.bot.perf_metrics.record_cache_result(True)
    # ... queue cached track ... return

if hasattr(self.bot, "perf_metrics"):
    self.bot.perf_metrics.record_cache_result(False)
# ... run search ...
```

### WR-02: Prefetch timeout does not cancel the underlying yt-dlp download (thread leak / pool starvation)

**File:** `cogs/music.py:658-667`, `services/youtube.py:239-242`
**Issue:**
`asyncio.wait_for(self.youtube.async_download(...), timeout=...)` cancels the
awaiting coroutine on timeout, but `async_download` is
`loop.run_in_executor(None, self.download, ...)`. Cancelling the wrapping future
does **not** interrupt the synchronous `download()` already running in the
default thread-pool — yt-dlp runs to completion, holding a worker thread and
still writing the `.opus`. Repeated prefetch timeouts (45s budget each) can pin
all default-executor workers, stalling the *foreground* `async_search` /
`async_extract` / real-download calls that share that pool. The "timeout" frees
the awaiter, not the resource.

**Fix:** Run downloads on a bounded dedicated `ThreadPoolExecutor` so a stuck
prefetch cannot starve the shared default pool, and/or store the prefetch task
handle (see IN-01) so it can be cancelled on stop/skip. Note: the file landing in
cache post-timeout is acceptable for caching purposes — the leak is the
unreclaimed worker thread.

### WR-03: `cleanup_cache` unlink is unguarded — one failing file aborts the whole eviction pass

**File:** `services/audio.py:176-188`
**Issue:**
The eviction loop calls `f.unlink()` with no `try/except`. If unlink raises
(file already removed by a racing op, permission error, Windows file lock), the
exception propagates out of `cleanup_cache`, aborting the pass mid-way. The cache
stays over cap until the next hourly run, and `total_bytes` is left inconsistent.
On Koyeb's lowered 512MB ephemeral cap (config K-07), a wedged cleanup risks
filling the disk.

**Fix:**

```python
try:
    size = f.stat().st_size
    f.unlink()
    total_bytes -= size
except OSError as exc:
    log.warning("cache evict failed for %s: %s", vid, exc)
    continue
```

### WR-04: `record_ttfa` is never called — `/stats` always reports "avg time-to-first-audio 0.0s"

**File:** `services/metrics.py:52-54`, `utils/embeds.py:266-269` (no call site anywhere)
**Issue:**
`PerfMetrics.record_ttfa` exists and the `/stats` embed renders
"avg time-to-first-audio", but a grep for `record_ttfa` finds zero call sites in
the playback path. The embed will always show `0.0s`. TTFA (queue →
`voice.play`) is the headline Phase 6 latency number and is silently fabricated.

**Fix:** Capture `t0` at `/play` defer and call
`self.bot.perf_metrics.record_ttfa(time.monotonic() - t0)` right after
`voice_client.play(source, ...)` in `_play_track`, or remove the TTFA field until
it is wired so the dashboard does not present a fake 0.0s.

### WR-05: Cache "hit" path still performs a full `async_extract`, so the win is smaller than designed

**File:** `cogs/music.py:1342` (vs comment at `cogs/music.py:930`)
**Issue:**
The cache is described as letting "a repeat of this query skip YouTube re-search
entirely," but a hit still calls `async_extract(watch_url)` — a full yt-dlp
metadata round-trip — to rebuild the `Track`. That extract is most of the
non-search latency, so a "hit" still blocks on the network and is only modestly
faster than a miss. Combined with WR-01, the recorded "hit" does not correspond
to the latency improvement implied.

**Fix:** Persist enough in `resolution_cache` (it already stores `video_id` +
`title`) to build a playable `Track` without re-extract — or accept the extract
cost and align the design notes / TTFA metric so "hit" latency is measured
honestly.

### WR-06: Eviction protected-set is snapshotted non-atomically with concurrent prefetch

**File:** `bot.py:571-585`, `services/audio.py:135-188`
**Issue:**
`cache_cleanup` snapshots `protected_video_ids` from each queue's
`tracks[current_index:]` plus `_prefetch_video_id`, then `await`s
`cleanup_cache`. A prefetch that *starts* after the snapshot but before the
unlink loop sets `_prefetch_video_id` too late to be protected; its
partially-written `.opus` can then be selected for eviction. Together with CR-01's
slot race, an in-flight download can be unlinked mid-write.

**Fix:** Re-read `_prefetch_video_id` inside `cleanup_cache` immediately before
each unlink, or skip eviction of any file whose mtime is within the last
`PREFETCH_TIMEOUT_SECONDS` (recently written ⇒ likely in flight).

### WR-07: Daily-stats helpers key "today" on UTC `date.today()` while streaks use `STREAK_TIMEZONE`

**File:** `database.py:284`, `database.py:364`, `database.py:379`
**Issue:**
CLAUDE.md: "Community-time checks use `ZoneInfo(STREAK_TIMEZONE)`, never naive ...
the host VM runs UTC." `compute_streak` correctly uses `get_local_date(tz_name)`,
but `increment_daily_stat`, `get_daily_command_count`, and `get_daily_stats_row`
all key on `date.today().isoformat()` — which rolls at UTC midnight, not
`America/New_York` midnight. The mood system, `/stats` "today" window (which
Phase 6 adds perf metrics to), and daily reset therefore use a different calendar
boundary than streaks, giving inconsistent "today" semantics across features.

**Fix:** Route every "today" key through
`get_local_date(config.STREAK_TIMEZONE).isoformat()` for a single consistent
community-day boundary.

## Info

### IN-01: `_prefetch_task` field is assigned/reset but never populated

**File:** `models/queue.py:89`, `models/queue.py:232`
**Issue:** `MusicQueue._prefetch_task` is declared and cleared in `clear()` but
never set — prefetch uses fire-and-forget `asyncio.create_task` (music.py:623)
without storing the handle. Dead field, and a missed hook for cancelling an
in-flight prefetch on stop/skip (which would also mitigate WR-02). Either wire it
(`queue._prefetch_task = asyncio.create_task(...)` + `.cancel()` on teardown) or
remove it.

### IN-02: Test `test_prefetch_task_spawned` contains a tautological assertion

**File:** `tests/test_phase6_perf.py:314`
**Issue:** `assert ...["avg_download_s"] > 0.0 or True` always passes and verifies
nothing. Replace with a deterministic check (patch `time.monotonic` to advance,
then assert the recorded value) or assert `len(perf_metrics.download_times) == 1`.

### IN-03: `conftest.py` teardown drops a table the schema never creates

**File:** `tests/conftest.py:55`
**Issue:** Teardown drops `user_playlist_tracks`, which is absent from
`SCHEMA_SQL` (playlists store a JSONB `snapshot`, not a join table). `IF EXISTS`
makes it harmless but signals schema drift from an abandoned design. Remove the
stale name.

### IN-04: `normalize_search_query` output is an unbounded TEXT primary key

**File:** `database.py:754-762`, used at `cogs/music.py:1325`, `935`
**Issue:** The normalized query is the `resolution_cache.query_key` PRIMARY KEY.
It lowercases and collapses whitespace but does not bound length. Low risk
(Discord caps slash-arg length), but truncating to a sane max (~200 chars) before
use as a key improves index hygiene and guards against future callers.

### IN-05: `increment_daily_stat` interpolates `{field}` into SQL (safe today, fragile pattern)

**File:** `database.py:296-302`
**Issue:** The column name is f-string-interpolated into the SQL. It is validated
against an allowlist immediately above (lines 285-293), so it is **not**
injectable today. Flagged only as a maintainability hazard — a future field added
to the allowlist without understanding the interpolation could reintroduce risk.
A `field → static-SQL` dispatch dict would eliminate the f-string. No action
required to ship.

---

_Reviewed: 2026-06-23T20:57:07Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
