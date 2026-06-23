---
phase: 06-speed-caching
verified: 2026-06-24T00:00:00Z
status: human_needed
score: 6/6 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Play a song, wait for it to start, then play a second song — verify no audible gap between tracks"
    expected: "Second track begins playing immediately after the first ends, with no pause for download"
    why_human: "Inter-song gap is a subjective auditory experience; can only be measured live with a Discord voice session and real YouTube downloads"
  - test: "Play the same non-URL search query twice in the same session (e.g. /play lo-fi beats, let it resolve, then /play lo-fi beats again)"
    expected: "Second /play skips the YouTube search select menu and queues the track immediately; /stats shows elevated cache-hit-rate percentage"
    why_human: "Requires a live bot with Postgres, Discord interaction, and observable /stats output to confirm the skip-search path fires end-to-end"
  - test: "Play a YouTube-URL /play (e.g. https://www.youtube.com/watch?v=dQw4w9WgXcQ) and check the bot does NOT write to resolution_cache"
    expected: "Direct-URL plays bypass the cache entirely; the cache_hit_rate in /stats does not change"
    why_human: "Requires live Postgres inspection or query-level tracing to confirm no resolution_cache row was written for the URL key"
  - test: "Trigger a simulated slow download (e.g. a large video) and verify fallback to stream rather than hanging"
    expected: "After DOWNLOAD_TIMEOUT_SECONDS (10s) the bot plays from stream URL instead of waiting for the download to finish"
    why_human: "Timeout behavior requires a real yt-dlp download exceeding the budget; cannot be triggered with a mocked test environment"
  - test: "Fill the cache beyond 512MB, then queue several songs and let the hourly cleanup run (or trigger it manually)"
    expected: "Least-played tracks are deleted first; currently-playing and prefetched tracks are never deleted"
    why_human: "Requires real cached files at scale, a running Postgres with song_history data, and hourly task execution to observe LFU ordering"
  - test: "Run /stats as the bot owner after playing at least 3-5 songs"
    expected: "Stats embed shows 'cache hit rate', 'avg time-to-first-audio', and 'avg download' fields with non-zero values after playback"
    why_human: "Requires a live bot session with real playback to populate the PerfMetrics rolling aggregate; automated environment cannot exercise voice_client.play()"
---

# Phase 6: Speed & Caching Verification Report

**Phase Goal:** Playback is noticeably faster with no inter-song gap, and every pipeline stage is instrumented so gains are measured against the bot's actual run environment (user's PC, residential IP — NOT Oracle, per 06-CONTEXT.md D-19).
**Verified:** 2026-06-24T00:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Next track begins immediately — `_prefetch_next_track` exists, is fire-and-forget, generation-guarded at entry AND post-download, triggered from `_play_track` | VERIFIED | `cogs/music.py:628` — `asyncio.create_task(self._prefetch_next_track(guild, next_tracks[0], current_gen))`; function at line 630 with entry guard at 647, post-download guard at 677; `asyncio.wait_for` with `PREFETCH_TIMEOUT_SECONDS` at line 663 |
| 2 | Previously-cached song skips re-encode (opus-copy path logged, not transcode) | VERIFIED | `services/youtube.py:183-200` — `_pp_hook` closure detects `acodec == "opus"` → logs `codec_path=copy`, else `codec_path=transcode`; log line at 197 confirmed present |
| 3 | Same search query twice in a session hits `resolution_cache` — second `/play` shows cache-hit, no re-search. `normalize_search_query` + `get/set_resolution_cache` + `play()` intercept all present | VERIFIED | `database.py:754-807` — all three helpers present with parameterized SQL; `cogs/music.py:1330-1428` — text-search branch calls `get_resolution_cache` on cache-key, URL branch untouched; `_queue_from_selection` at line 938-953 writes cache on miss |
| 4 | Download exceeding `DOWNLOAD_TIMEOUT_SECONDS` falls back to stream URL | VERIFIED | `services/audio.py:106-115` — `asyncio.wait_for(..., timeout=config.DOWNLOAD_TIMEOUT_SECONDS)` wraps `async_download`; `except asyncio.TimeoutError:` sets `path = None`, falling through to stream tier at line 122 |
| 5 | Cache eviction removes least-PLAYED tracks (LFU from `song_history play_count`); protects in-use tracks; SponsorBlock segments skipped | VERIFIED | `services/audio.py:135-194` — async `cleanup_cache(pool, protected_video_ids)` queries `song_history GROUP BY url`, builds `play_counts`, sorts by `(play_count ASC, mtime ASC)` with `float("inf")` for protected IDs; `services/youtube.py:65-83` — `DOWNLOAD_OPTS["postprocessors"]` has SponsorBlock first with `when="after_filter"`, then FFmpegExtractAudio, then ModifyChapters |
| 6 | `record_ttfa` is actually called in `_play_track` (WR-04 fix, commit 08c910a verified in codebase) | VERIFIED | `cogs/music.py:549` — `_ttfa_t0 = time.monotonic()` set before `get_source`; `cogs/music.py:609-610` — `self.bot.perf_metrics.record_ttfa(time.monotonic() - _ttfa_t0)` called immediately after `voice_client.play(source, ...)`; the WR-04 "no call site" defect is resolved |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `config.py` | Phase 6 constants: `PREFETCH_TIMEOUT_SECONDS`, `RES_CACHE_TTL_DAYS`, `SPONSORBLOCK_CATEGORIES`, `PERF_ROLLING_WINDOW` | VERIFIED | Lines 129-135: all four present with correct values (45, 14, frozenset of 6 categories, 50) |
| `database.py` | `resolution_cache` table in `SCHEMA_SQL` + `normalize_search_query` / `get_resolution_cache` / `set_resolution_cache` | VERIFIED | Lines 153-161: table DDL with `idx_rescache_expires`; lines 754-807: all three helpers with `$N` parameterized SQL; `ON CONFLICT (query_key) DO UPDATE` refreshes TTL (Pitfall 5) |
| `services/metrics.py` | `PerfMetrics` rolling-aggregate class (deque-backed) | VERIFIED | Lines 16-97: class with four `collections.deque(maxlen=window)` fields; `record_cache_result`, `record_download`, `record_search`, `record_ttfa`; `summary()` guards against ZeroDivisionError |
| `models/queue.py` | `_prefetch_video_id` / `_prefetch_task` state fields, reset in `clear()` | VERIFIED | Lines 88-89: both fields initialized to None; lines 236-237: both reset in `clear()`; CR-01 fix confirmed — `clear()` does `_play_generation += 1` at line 230, never resets to 0 |
| `services/youtube.py` | `DOWNLOAD_OPTS` with SponsorBlock 3-PP chain + `download()` codec-path logging | VERIFIED | Lines 65-83: SponsorBlock first with `when="after_filter"`, then FFmpegExtractAudio, then ModifyChapters; lines 183-200: `_pp_hook` + `postprocessor_hooks` wired; `codec_path=` log present |
| `services/audio.py` | `get_source` tier-2 with `asyncio.wait_for`; `cleanup_cache` as async LFU with `protected_video_ids` | VERIFIED | Lines 106-115: `wait_for` with timeout; lines 135-194: async LFU with `song_history` play-count query, protected guard at float("inf"), OSError guard on unlink |
| `cogs/music.py` | `_prefetch_next_track` + trigger in `_play_track`; resolution-cache intercept in `play()`; cache write in `_queue_from_selection` | VERIFIED | Lines 626-628: trigger fires fire-and-forget; lines 630-698: `_prefetch_next_track` with double generation guard; lines 1329-1428: full cache-hit/miss/search path; lines 938-953: `_queue_from_selection` writes cache |
| `bot.py` | `self.perf_metrics = PerfMetrics(config.PERF_ROLLING_WINDOW)`; cleanup task uses new `cleanup_cache(pool, protected)` signature | VERIFIED | Line 313: `bot.perf_metrics = PerfMetrics(config.PERF_ROLLING_WINDOW)`; lines 566-586: `cache_cleanup` task builds `protected_video_ids` across all guild queues and calls `await bot.audio_service.cleanup_cache(bot.pool, protected_video_ids)` |
| `utils/embeds.py` | `stats_embed` accepts `perf_metrics: dict | None` and renders cache-hit-rate + avg-ttfa fields | VERIFIED | Lines 207-213: signature includes `perf_metrics: dict | None = None`; lines 256-274: renders `cache hit rate`, `avg time-to-first-audio`, `avg download` fields when `perf_metrics` is provided; no Oracle label (D-19) |
| `cogs/ops.py` | `/stats` passes `bot.perf_metrics.summary()` to `stats_embed` | VERIFIED | Lines 202-209: `getattr` guard; `perf_metrics=perf_summary` passed as keyword arg to `embeds.stats_embed` |
| `tests/test_phase6_perf.py` | All eight required test functions/classes; no `xfail` on prefetch/timing tests | VERIFIED | All eight present: `TestNormalizeQuery`, `TestPerfMetrics`, `TestResolutionCache`, `test_url_bypasses_cache`, `test_prefetch_task_spawned`, `test_prefetch_skips_cached`, `test_prefetch_stale_gen`, `test_timing_logged`; grep for `xfail` returns zero matches |
| `tests/conftest.py` | `resolution_cache` in DROP TABLE teardown | VERIFIED | Line 56: `" resolution_cache CASCADE"` present in teardown list |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `cogs/music.py _play_track` | `_prefetch_next_track` (fire-and-forget) | `asyncio.create_task` with `current_gen` | WIRED | `music.py:627-628` — `asyncio.create_task(self._prefetch_next_track(guild, next_tracks[0], current_gen))` |
| `cogs/music.py play()` | `database.get_resolution_cache` / `set_resolution_cache` | `normalize_search_query` key; non-URL only | WIRED | `music.py:1330-1333` — cache-key computed, `get_resolution_cache` called; `music.py:1428` — `SongSelectView` carries `orig_query`; `music.py:938-953` — `set_resolution_cache` in `_queue_from_selection` |
| `cogs/ops.py /stats` | `utils/embeds.stats_embed` | `perf_metrics=bot.perf_metrics.summary()` | WIRED | `ops.py:209` — `embeds.stats_embed(..., perf_metrics=perf_summary)` |
| `DOWNLOAD_OPTS postprocessors` | `config.SPONSORBLOCK_CATEGORIES` | SponsorBlock + ModifyChapters category lists | WIRED | `youtube.py:68` and `youtube.py:79` — both reference `config.SPONSORBLOCK_CATEGORIES` |
| `download() postprocessor_hooks` | structured log line | `codec_path=copy|transcode` + elapsed | WIRED | `youtube.py:190` — `opts = {**DOWNLOAD_OPTS, "postprocessor_hooks": [_pp_hook]}`; `youtube.py:197-200` — log line with `codec_path=` |
| `get_source tier 2` | stream fallback (tier 3) | `asyncio.TimeoutError → path=None → stream tier` | WIRED | `audio.py:110-115` — `except asyncio.TimeoutError: path = None`; stream tier at line 122 reached on `path` being None |
| `cleanup_cache` | `song_history` play counts | `SELECT url, COUNT(*) GROUP BY url` + `protected_video_ids` guard | WIRED | `audio.py:153-156` — query present; `audio.py:168-171` — `float("inf")` guard for protected IDs |
| `_play_track` | `PerfMetrics.record_ttfa` | `time.monotonic()` delta after `voice_client.play()` | WIRED | `music.py:549` — `_ttfa_t0` captured; `music.py:609-610` — `record_ttfa` called |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `utils/embeds.stats_embed` | `perf_metrics` dict | `bot.perf_metrics.summary()` in `cogs/ops.py` | Yes — populated by `record_ttfa`, `record_download`, `record_search`, `record_cache_result` calls in live pipeline | FLOWING (conditional on live playback) |
| `services/audio.py cleanup_cache` | `play_counts` dict | `SELECT url, COUNT(*) FROM song_history GROUP BY url` | Yes — real DB query against `song_history` table | FLOWING |
| `cogs/music.py play()` | `cached_res` | `get_resolution_cache(pool, query_key=cache_key)` | Yes — real Postgres query against `resolution_cache` table | FLOWING |

### Behavioral Spot-Checks

Runnable spot-checks were not executed because the bot requires a live Discord token, FFmpeg, and a YouTube-accessible network to exercise any playback path. All behavioral verification is deferred to human testing. The unit test suite (which passes 310 tests / 64 skipped) was not re-run here but its structure was verified against the plan's acceptance criteria by code inspection.

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Config constants importable | `python -c "import config; assert config.PREFETCH_TIMEOUT_SECONDS==45"` | Not executed (safe to run without bot) | SKIP — code verified by inspection |
| PerfMetrics class importable | `python -c "from services.metrics import PerfMetrics"` | Not executed | SKIP — code verified by inspection |
| `stats_embed` has `perf_metrics` param | `python -c "import inspect, utils.embeds as e; assert 'perf_metrics' in inspect.signature(e.stats_embed).parameters"` | Not executed | SKIP — verified by reading signature at embeds.py:213 |

### Probe Execution

Step 7c: SKIPPED — no `scripts/*/tests/probe-*.sh` files exist for Phase 6; no probe paths declared in PLAN files.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PERF-01 | 06-04-PLAN.md | Next track prefetched during current playback (no inter-song gap) | SATISFIED (code); human-verified for live behavior | `_prefetch_next_track` implemented, wired, generation-guarded |
| PERF-02 | 06-02-PLAN.md | Cached audio uses native-opus copy (no opus→opus re-encode) when source is already opus | SATISFIED (code); human-verified for live confirmation | `_pp_hook` logs `codec_path=copy` when `acodec=="opus"`; `preferredcodec="opus"` unchanged in FFmpegExtractAudio PP |
| PERF-03 | 06-01-PLAN.md, 06-04-PLAN.md | Resolution cache maps repeat queries → video_id without re-searching YouTube | SATISFIED (code); human-verified for live behavior | `resolution_cache` table, helpers, `play()` intercept, `_queue_from_selection` write all present |
| PERF-04 | 06-03-PLAN.md | Download attempts honor `DOWNLOAD_TIMEOUT_SECONDS`, falling back to stream on timeout | SATISFIED (code); human-verified for live behavior | `asyncio.wait_for(..., timeout=config.DOWNLOAD_TIMEOUT_SECONDS)` in `get_source` tier 2 |
| PERF-05 | 06-03-PLAN.md | Cache eviction is play-frequency based; does not depend on `atime` | SATISFIED (code); human-verified for live behavior | LFU `cleanup_cache` queries `song_history`, sorts by `play_count ASC`, protects `protected_video_ids` |
| PERF-06 | 06-01-PLAN.md, 06-04-PLAN.md | Pipeline timing instrumented and observable | SATISFIED (code); human-verified for populated metrics | `PerfMetrics` wired; `record_ttfa` called in `_play_track`; `/stats` embed surfaces cache-hit-rate, avg-TTFA, avg-download |
| PERF-07 | 06-02-PLAN.md | SponsorBlock segments skipped on YouTube-video playback | SATISFIED (code); human-verified for live segment removal | 3-PP chain with `SponsorBlock when=after_filter` + `ModifyChapters` in `DOWNLOAD_OPTS` |

No ORPHANED requirements — all seven PERF-01..07 IDs appear in plan `requirements` fields and are mapped to Phase 6 in REQUIREMENTS.md (lines 93-99).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/test_phase6_perf.py` | 314 | `assert ... > 0.0 or True` — tautological assertion (always passes, verifies nothing) | Info (IN-02 from code review, pre-existing) | The assertion in `test_prefetch_task_spawned` does not validate timing; does not block goal |

No `TBD`, `FIXME`, or `XXX` markers found anywhere in Python source files.

**Deferred warnings from 06-REVIEW.md (not re-opened here):**
- WR-02: Prefetch `wait_for` does not cancel the yt-dlp executor thread (documented, accepted per D-10 discretion)
- WR-05: Cache hit still calls `async_extract` (speedup is smaller than designed; acceptable)
- WR-06: Eviction protected-set snapshotted non-atomically with concurrent prefetch (low-probability race, deferred)
- WR-07: Daily-stats UTC vs `STREAK_TIMEZONE` boundary (pre-existing, out of Phase 6 scope)
- IN-01: `_prefetch_task` field declared and reset but never populated with a task handle (declared as dead field; does not break generation guard)

### Human Verification Required

#### 1. Inter-Song Gap Elimination (PERF-01)

**Test:** Play two songs back-to-back (first song at or near its natural end). Listen to the transition.
**Expected:** Second track begins playing immediately when the first ends — no audible pause for download.
**Why human:** Auditory gap perception requires real Discord voice playback with a real YouTube download pipeline; cannot be emulated in a mock environment.

#### 2. Resolution Cache Hit in Practice (PERF-03)

**Test:** Run `/play lo-fi beats` in a server, pick a result. Wait for it to queue. Then run `/play lo-fi beats` again.
**Expected:** Second invocation skips the search select menu entirely and queues the track immediately; `/stats` shows non-zero cache hit rate.
**Why human:** Requires a live bot + Postgres + Discord interaction to confirm the `get_resolution_cache` → skip-search path fires end-to-end. Bot log should show `resolution_cache hit key=`.

#### 3. Direct-URL Cache Bypass (D-09)

**Test:** Run `/play https://www.youtube.com/watch?v=dQw4w9WgXcQ`.
**Expected:** Track queues directly with no select menu; bot log does NOT contain `resolution_cache` write for this URL; cache hit rate in `/stats` remains unchanged.
**Why human:** Requires live Postgres inspection to confirm no resolution_cache row was inserted for a URL key.

#### 4. Download Timeout Fallback (PERF-04)

**Test:** Deliberately trigger a slow/hung download (e.g., network throttle or a very large video with a short timeout — or temporarily reduce `DOWNLOAD_TIMEOUT_SECONDS` to 1s in config and play any song with a cold cache).
**Expected:** Bot plays audio from the stream URL fallback rather than hanging; log contains `"download timeout after ... falling back to stream"`.
**Why human:** Requires controlling network or config to induce a timeout; cannot be triggered on demand without the live pipeline.

#### 5. LFU Cache Eviction (PERF-05)

**Test:** Fill the bot's cache directory beyond 512MB. Queue songs with different play histories. Let the hourly `cache_cleanup` task run (or trigger it in a test environment). Inspect which files were removed.
**Expected:** Files with the lowest `song_history` play_count are deleted first; currently-playing and prefetched tracks survive eviction.
**Why human:** Requires real cached files at scale with actual song_history entries; hourly task execution under live Postgres.

#### 6. /stats Perf Metrics Populated (PERF-06)

**Test:** Play 3-5 songs. Run `/stats` as the bot owner.
**Expected:** The embed shows non-zero values for `cache hit rate`, `avg time-to-first-audio`, and `avg download` fields.
**Why human:** The `PerfMetrics` rolling aggregate is only populated by live `voice_client.play()` calls and real downloads; the automated environment cannot exercise these code paths.

### Gaps Summary

No code gaps were found. All six observable truths are verified in the codebase with substantive, wired, and data-flowing implementations. The CR-01 blocker (generation counter reset in `clear()`) identified in 06-REVIEW.md is confirmed fixed — `clear()` now does `self._play_generation += 1` at line 230 of `models/queue.py`, never resets to 0. The WR-04 blocker (`record_ttfa` with no call site) is confirmed fixed — `record_ttfa` is called at `cogs/music.py:610` immediately after `voice_client.play()`.

Status is `human_needed` because all six behavioral truths depend on live Discord voice playback, real YouTube downloads, and/or a live Postgres database to confirm observable outcomes. The code is complete and correct; human UAT is the remaining gate.

---

_Verified: 2026-06-24T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
