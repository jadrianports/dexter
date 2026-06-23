---
phase: "06-speed-caching"
plan: "04"
subsystem: "cogs/music.py + bot.py + utils/embeds.py + cogs/ops.py + tests"
tags: [phase6, perf, prefetch, resolution-cache, perf-metrics, instrumentation, tdd]
dependency_graph:
  requires: ["06-01", "06-02", "06-03"]
  provides:
    - "cogs/music.py _prefetch_next_track: fire-and-forget background prefetch with double generation guard"
    - "cogs/music.py play() text-search branch: resolution cache lookup + miss recording"
    - "cogs/music.py _queue_from_selection: resolution cache write after user pick"
    - "bot.py: bot.perf_metrics = PerfMetrics(PERF_ROLLING_WINDOW) wired on_ready"
    - "bot.py cache_cleanup: updated to async cleanup_cache(pool, protected_video_ids)"
    - "utils/embeds.py stats_embed: perf_metrics param + cache hit rate + avg ttfa fields"
    - "cogs/ops.py /stats: passes bot.perf_metrics.summary() with getattr guard"
    - "tests/test_phase6_perf.py: all 4 xfail placeholders replaced with passing tests"
  affects:
    - "All guild playback: prefetch fires on every track start"
    - "/play text search: resolution cache intercepts repeat queries"
    - "/stats embed: now shows cache hit rate, avg time-to-first-audio, avg download"
tech_stack:
  added: []
  patterns:
    - "asyncio.create_task fire-and-forget pattern (mirrors _post_auto_lyrics)"
    - "double generation guard: entry check + post-download check before recording metrics"
    - "queue._prefetch_video_id as in-use marker for LFU eviction exclusion"
    - "normalize_search_query key for resolution cache lookup + write"
    - "getattr(self.bot, 'perf_metrics', None) guard for backward-compat"
key_files:
  created: []
  modified:
    - cogs/music.py
    - bot.py
    - utils/embeds.py
    - cogs/ops.py
    - tests/test_phase6_perf.py
decisions:
  - "Cache hit routes through async_extract (same duration cap + livestream rejection as URL branch) — not inline Track construction"
  - "Resolution cache fallthrough on stale/removed video (extract raises ValueError) — falls to fresh async_search without recording another miss"
  - "TTL refreshed on cache hit via set_resolution_cache re-write (Pitfall 5 guard)"
  - "SongSelectView gains orig_query param; SongSelect.callback passes it through to _queue_from_selection via getattr"
  - "cache_cleanup protected set built from MusicCog.queues: current + upcoming tracks + _prefetch_video_id per guild"
  - "test helper _make_music_cog uses __get__ to bind MusicCog._prefetch_next_track as an instance method on SimpleNamespace"
metrics:
  duration: "~35 min"
  completed_date: "2026-06-24"
  tasks_completed: 3
  files_created: 0
  files_modified: 5
---

# Phase 06 Plan 04: Controller Wiring (Prefetch + Resolution Cache + Instrumentation) Summary

**One-liner:** Fire-and-forget `_prefetch_next_track` with double generation guard closes the inter-song gap; resolution cache in `play()` skips YouTube re-search on repeat queries; PerfMetrics aggregates surfaced in `/stats` embed.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Prefetch task + PerfMetrics wiring + cleanup call-site update | 20c60af | cogs/music.py, bot.py, tests/test_phase6_perf.py |
| 2 | Resolution cache intercept in play() + write in _queue_from_selection | 2ca22f8 | cogs/music.py, tests/test_phase6_perf.py |
| 3 | Surface perf metrics in /stats embed | d904918 | utils/embeds.py, cogs/ops.py |

## What Was Built

### Task 1 — Prefetch task + PerfMetrics + cleanup rewire

**`cogs/music.py` — `_prefetch_next_track`:**

New fire-and-forget coroutine modeled on `_post_auto_lyrics`:
1. Entry generation guard: returns immediately if `queue._play_generation != expected_gen` (user already skipped).
2. Early exit if `self.audio.is_cached(track.video_id)` — no redundant download.
3. Sets `queue._prefetch_video_id = track.video_id` to protect from LFU eviction during prefetch (D-13).
4. `asyncio.wait_for(self.youtube.async_download(...), timeout=config.PREFETCH_TIMEOUT_SECONDS)` — generous 45s budget (D-10).
5. Post-download generation guard: discards result if generation advanced during download (CLAUDE.md anti-double-play race rule).
6. On success: logs `"prefetch complete video_id=%s elapsed=%.2fs ok=%s"` and calls `self.bot.perf_metrics.record_download(elapsed)`.
7. On `TimeoutError`: logs info, no re-raise.
8. `finally`: clears `queue._prefetch_video_id` only if this task still owns the slot.
9. Outer `except Exception`: swallows all errors (debug log).

**Trigger in `_play_track`:** After the auto-lyrics `create_task` block, reads `queue.upcoming()` and fires `asyncio.create_task(self._prefetch_next_track(guild, next_tracks[0], current_gen))` when upcoming is non-empty. Uses the in-scope `current_gen` captured at generation increment — never re-reads.

**`bot.py` — PerfMetrics and cleanup:**
- Added `from services.metrics import PerfMetrics` import.
- `bot.perf_metrics = PerfMetrics(config.PERF_ROLLING_WINDOW)` set alongside service wiring.
- `cache_cleanup` background task rewritten: builds `protected_video_ids` set by iterating `MusicCog.queues.values()` (current+upcoming tracks + `_prefetch_video_id`), then calls `await bot.audio_service.cleanup_cache(bot.pool, protected_video_ids)`. Old sync no-arg call eliminated.

**`cogs/music.py` — imports added:** `import time`, plus `normalize_search_query`, `get_resolution_cache`, `set_resolution_cache` from `database`.

### Task 2 — Resolution cache + tests

**`play()` text-search `else:` branch:**
- Computes `cache_key = normalize_search_query(query)` and calls `get_resolution_cache(self.bot.pool, query_key=cache_key)`.
- **Cache hit:** records `record_cache_result(True)`, builds `watch_url = f"https://www.youtube.com/watch?v={video_id}"`, calls `async_extract` (full duration cap + livestream guard applied exactly as the URL branch does). On stale/removed video (extract raises), falls through to `async_search` with no extra miss record. Refreshes TTL via `set_resolution_cache` on hit.
- Routes hit through the complete inline single-video queue path (queue.add, _log_track, _ensure_voice, _play_track, now_playing embed) — no shortcuts that would bypass guards.
- **Cache miss:** records `record_cache_result(False)`, `t0=time.monotonic()`, runs `async_search`, records `record_search(elapsed)`, shows `SongSelectView(results, self, orig_query=query)`.
- URL branch (`is_url` arm) is completely untouched — D-09 bypass preserved.

**`SongSelectView`:** New `orig_query: str | None = None` param stored on the view. `SongSelect.callback` reads `getattr(self.view, "orig_query", None)` and passes it to `_queue_from_selection`.

**`_queue_from_selection`:** New `orig_query: str | None = None` param. After successful `async_extract`, if `orig_query is not None and hasattr(self.bot, "pool")`, calls `set_resolution_cache(pool, query_key=normalize_search_query(orig_query), video_id=..., title=..., ttl_days=config.RES_CACHE_TTL_DAYS)`. Errors are caught and logged at debug level (non-fatal).

**Tests — xfail placeholders replaced:**
- `test_prefetch_task_spawned`: verifies `_prefetch_next_track` runs successfully with matching gen, calls `async_download`.
- `test_prefetch_skips_cached`: verifies early return when `is_cached=True`, no `async_download` call.
- `test_prefetch_stale_gen`: verifies entry guard fires when generation=2 but expected=1, no download.
- `test_prefetch_stale_gen_post_download`: verifies post-download guard discards result and doesn't record timing.
- `test_timing_logged`: verifies "elapsed=" in log output and `avg_download_s >= 0.0` in PerfMetrics after a download.

### Task 3 — Perf metrics in /stats embed

**`utils/embeds.py`:** `stats_embed` gains `perf_metrics: dict | None = None` param. When non-None, adds three fields: "cache hit rate" (`{:.0f}%`), "avg time-to-first-audio" (`{:.1f}s`), "avg download" (`{:.1f}s`). No Oracle/CPU label (D-19). Backward-compatible: callers omitting the param see no new fields.

**`cogs/ops.py`:** `/stats` builds `perf_summary = self.bot.perf_metrics.summary() if getattr(self.bot, "perf_metrics", None) is not None else None`, then passes `perf_metrics=perf_summary` as keyword to `stats_embed`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `__get__` binding in `_make_music_cog` test helper — double `self` in call**
- **Found during:** Task 1 first test run (`TypeError: MusicCog._prefetch_next_track() takes 4 positional arguments but 5 were given`)
- **Issue:** Test called `cog._prefetch_next_track(cog, guild_mock, track, 1)` — but `__get__` already binds `self=cog`, so `cog` was passed twice.
- **Fix:** Changed all test call sites to `cog._prefetch_next_track(guild_mock, track, 1)`.
- **Files modified:** `tests/test_phase6_perf.py`
- **Commit:** 20c60af

## Verification Results

```
grep -v '^#' cogs/music.py | grep -c '_prefetch_next_track'
# 2

grep -v '^#' cogs/music.py | grep -c 'get_resolution_cache'
# 2

python -c "import inspect, utils.embeds as e; assert 'perf_metrics' in inspect.signature(e.stats_embed).parameters; print('OK')"
# OK

python -m pytest tests/test_phase6_perf.py -x -q
# 19 passed, 4 skipped, 1 warning in 17.60s

python -m pytest tests/ -q
# 310 passed, 64 skipped, 1 warning in 262.63s
```

## Threat Surface Scan

T-06-07 (resolution cache key from user input): Mitigated. `normalize_search_query` normalizes before cache lookup/write; all DB calls use `$N` params from `database.py` helpers (no string interpolation). URL queries bypass cache entirely (D-09).

T-06-08 (stale prefetch double-play race): Mitigated. `_prefetch_next_track` checks `queue._play_generation == expected_gen` at entry AND after download. Any mismatch discards the result without recording timing or mutating queue state.

T-06-09 (perf metrics in /stats): Accepted. `/stats` is owner-gated (existing ops.py:182-188 check). PerfMetrics contains non-sensitive aggregates only.

No new network endpoints, auth paths, or schema changes introduced.

## Known Stubs

None — all three pipeline integrations are fully wired. Resolution cache lookup, write, and TTL refresh are live; prefetch fires on every track start; `/stats` renders the rolling aggregate.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| cogs/music.py defines `_prefetch_next_track` | FOUND (grep returns 2) |
| cogs/music.py imports `get_resolution_cache` | FOUND |
| cogs/music.py text-search branch calls `get_resolution_cache` | FOUND |
| cogs/music.py URL branch has no `get_resolution_cache` call | VERIFIED |
| `_queue_from_selection` calls `set_resolution_cache` with `ttl_days=config.RES_CACHE_TTL_DAYS` | FOUND |
| bot.py contains `PerfMetrics(config.PERF_ROLLING_WINDOW)` | FOUND |
| bot.py cache_cleanup awaits `cleanup_cache(bot.pool, protected_video_ids)` | FOUND |
| utils/embeds.stats_embed has `perf_metrics` param | FOUND (inspect check OK) |
| utils/embeds.py renders "cache hit rate" field | FOUND |
| cogs/ops.py passes `perf_metrics=` with getattr guard | FOUND |
| tests/test_phase6_perf.py has no `@pytest.mark.xfail` markers | CONFIRMED |
| Commit 20c60af | FOUND |
| Commit 2ca22f8 | FOUND |
| Commit d904918 | FOUND |
| Full suite: 310 passed 64 skipped | PASSED |
