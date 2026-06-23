# Phase 6: Speed & Caching - Research

**Researched:** 2026-06-24
**Domain:** yt-dlp audio pipeline optimization, Postgres TTL cache, asyncio prefetch, LFU eviction
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Cache Codec Strategy (PERF-02):**
- D-01: Copy-when-opus. Stream-copy when YouTube's source is already opus (`-c:a copy`); transcode only for non-opus sources.
- D-02: Every cache file must be opus so `FFmpegOpusAudio` passthrough always holds. No raw non-opus storage.
- D-03: Codec path (copy vs transcode) MUST be logged for every download.

**Prefetch (PERF-01):**
- D-04: Next-1, on track start. Prefetch the next queue entry the moment a track begins playing.
- D-05: Pre-resolve may look 1 track further ahead than pre-download.
- D-06: Prefetch runs the full pipeline (codec + SponsorBlock) in background — fire-and-forget like `_post_auto_lyrics`.

**Resolution Cache (PERF-03):**
- D-07: Postgres + TTL (~14 days). New table via `SCHEMA_SQL` `CREATE TABLE IF NOT EXISTS`.
- D-08: Postgres chosen over in-memory because the bot restarts often.
- D-09: Normalized query (casing/whitespace/trim) as key. Direct-URL `/play` bypasses cache.

**Download Timeout (PERF-04):**
- D-10: Split budgets — on-demand `/play` keeps 10s (`DOWNLOAD_TIMEOUT_SECONDS`) + stream fallback; prefetch gets ~45s (`PREFETCH_TIMEOUT_SECONDS`).
- D-11: On timeout, on-demand path falls back to stream URL.

**Cache Eviction (PERF-05):**
- D-12: LFU + protect in-use. Evict lowest lifetime `play_count` from `song_history`, tie-break oldest. NEVER evict currently-playing, queued, or prefetched tracks.
- D-13: Freshly-downloaded tracks with `play_count` 0 are protected by in-use guard while in queue.

**SponsorBlock (PERF-07):**
- D-14: Download-time removal, categories: `sponsor`, `selfpromo`, `intro`, `outro`, `interaction`, `music_offtopic`.
- D-15: Silently skipped, no user notification.
- D-16: Tracks with cut segments re-encode even if source was opus (cutting precludes stream-copy). Copy-fast-path only for opus tracks with no segments to cut.

**Instrumentation (PERF-06):**
- D-17: Structured per-event logs always — search time, download time, transcode time, time-to-first-audio, cache hit/miss.
- D-18: Rolling in-memory aggregate surfaced in existing `/stats` embed (no DB schema change). Already stubbed in `utils/embeds.py` lines 255-257.

**Goal-text correction:**
- D-19: Oracle is dead. Instrument against actual run environment (user's PC residential IP), not Oracle.

### Claude's Discretion

- Exact yt-dlp invocation for copy-when-opus and codec detection method.
- asyncio.wait_for + run_in_executor orphan thread behavior on prefetch timeout.
- Resolution-cache table/column names, indexes, normalization rules, TTL value.
- Prefetch trigger plumbing inside `_play_track` / `_on_track_end` and prefetch task lifecycle.
- Rolling-aggregate window size and `/stats` embed layout for perf section.
- New config constants.

### Deferred Ideas (OUT OF SCOPE)

- LFU-with-recency-aging eviction.
- Persisting perf metrics to `bot_daily_stats` for day-over-day trends.
- Runtime SponsorBlock seek-skipping.
- Deeper prefetch (next-3 buffer).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PERF-01 | Next track prefetched into cache during current playback (no inter-song download gap) | Prefetch trigger at `_play_track` after `voice_client.play()`, fire-and-forget task with generation guard |
| PERF-02 | Cached audio uses native-opus copy (no opus→opus re-encode) when source is already opus | `FFmpegExtractAudioPP` already handles copy-when-opus natively; add `postprocessor_hooks` for D-03 logging |
| PERF-03 | Resolution cache maps repeat queries → `video_id` without re-searching YouTube | Postgres `resolution_cache` table with TTL, normalized key, asyncpg pattern |
| PERF-04 | Download attempts honor `DOWNLOAD_TIMEOUT_SECONDS`, falling back to stream on timeout | `asyncio.wait_for` wrapping `async_download`; orphan thread drains harmlessly |
| PERF-05 | Cache eviction is play-frequency based and does not depend on filesystem `atime` | Rewrite `cleanup_cache()` with LFU using `song_history` play counts + in-use protection |
| PERF-06 | Pipeline timing instrumented and observable in `/stats` | `time.monotonic()` deltas logged per event; `collections.deque` rolling aggregate; stubbed embed fields in `utils/embeds.py` |
| PERF-07 | SponsorBlock segments silently skipped on YouTube-video playback | Two-PP pattern: `SponsorBlock` (after_filter) + `ModifyChapters` (post_process) in `DOWNLOAD_OPTS` |
</phase_requirements>

---

## Summary

Phase 6 instruments and optimizes the audio pipeline across seven measurable dimensions. The codebase already contains much of the necessary infrastructure: `FFmpegExtractAudioPP` with `preferredcodec='opus'` already performs copy-when-opus natively (no re-encode when source codec equals target), the `async_download` executor pattern is ready for `asyncio.wait_for` wrapping, `song_history` already records every play for LFU eviction, and `utils/embeds.py` has Phase-6 stats fields stubbed out at lines 255-257. The primary implementation work is: adding SponsorBlock postprocessors to `DOWNLOAD_OPTS`, adding codec-path logging via `postprocessor_hooks`, adding the prefetch task at `_play_track`, adding the Postgres resolution-cache table, rewriting `cleanup_cache()` for LFU, wiring the download timeout, and wiring perf metrics into the `/stats` embed.

The yt-dlp SponsorBlock integration requires exactly two postprocessors in sequence: `SponsorBlock` (with `when='after_filter'`) to fetch segment data, and `ModifyChapters` (default `post_process`) to perform the actual cuts. D-16 is confirmed: `ModifyChapters` uses FFmpeg concat cuts which require re-encoding, so the opus copy-fast-path only applies to tracks where no SponsorBlock segments are found.

The asyncio timeout orphan thread behavior is a non-issue: when `asyncio.wait_for` cancels, the underlying `run_in_executor` thread continues until yt-dlp completes (Python threads are not cancellable), but setting a result on a cancelled future is silently discarded by asyncio. The thread drains harmlessly and may even warm the cache as a side effect.

**Primary recommendation:** Implement the seven PERF features as three waves: (W1) SponsorBlock + codec logging; (W2) prefetch + timeout; (W3) resolution cache + LFU eviction + instrumentation aggregation.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Codec copy vs transcode decision | `services/youtube.py` (download) | — | Decision happens at download time via `FFmpegExtractAudioPP`; `audio.py` only plays what's already cached |
| SponsorBlock segment removal | `services/youtube.py` (download) | — | Download-time removal; `DOWNLOAD_OPTS` postprocessors |
| Prefetch trigger | `cogs/music.py` (`_play_track`) | `services/audio.py` (get_source) | Trigger in playback engine; execution in audio/download pipeline |
| Resolution cache lookup + write | `cogs/music.py` (`play()`) | `database.py` | Intercept in `/play` command before `async_search`; persist via asyncpg helper |
| Download timeout enforcement | `services/audio.py` (`get_source`) | — | `asyncio.wait_for` wraps `async_download` in get_source tier 2 |
| LFU eviction | `services/audio.py` (`cleanup_cache()`) | `database.py` | Replacement of atime sort; reads `song_history` play counts |
| Perf metrics collection | `services/audio.py` + `cogs/music.py` | `services/youtube.py` | Timing at each pipeline stage |
| Perf metrics surfacing | `cogs/ops.py` (`/stats`) | `utils/embeds.py` | Existing `/stats` command + already-stubbed embed fields |

---

## Standard Stack

### Core (all already installed in project)

| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| yt-dlp | 2026.6.9 [VERIFIED: pip registry] | Download, codec handling, SponsorBlock postprocessors | Installed |
| asyncpg | 0.31.0 [VERIFIED: pip registry] | Postgres async driver for resolution cache | Installed |
| discord.py | 2.7.1 [VERIFIED: pip registry] | `FFmpegOpusAudio` passthrough playback | Installed |
| Python asyncio | stdlib (3.12.10) | `asyncio.wait_for`, `asyncio.create_task` for prefetch + timeout | Installed |
| FFmpeg | 2026-05-21 [VERIFIED: binary present] | Audio decode/encode, SponsorBlock segment cuts | Installed |

### No New Packages Required

Phase 6 uses exclusively existing project dependencies. No new packages to install.

---

## Package Legitimacy Audit

No new packages are installed in Phase 6. All pipeline libraries (`yt-dlp`, `asyncpg`, `discord.py`, FFmpeg) are already part of the project's dependency stack and were vetted in previous phases.

**Packages removed due to slopcheck:** none
**Packages flagged as suspicious:** none

---

## Architecture Patterns

### System Architecture Diagram

```
/play <query>
  ├─ is_url? NO ─→ [resolution_cache lookup]
  │                    HIT: skip async_search, use cached video_id
  │                    MISS: async_search (timed) → cache write → video_id
  └─ is_url? YES ─→ skip resolution cache
         ↓
  get_source(track) [tier 1: cache check]
         ↓ MISS
  async_download (asyncio.wait_for, 10s on-demand)
         ├─ TIMEOUT → stream fallback (tier 3)
         └─ SUCCESS → cache write (.opus file)
                  ├─ SponsorBlock PP (fetches segments from sponsor.ajay.app)
                  ├─ FFmpegExtractAudioPP (copy if opus, transcode if not)
                  └─ ModifyChaptersPP (cuts segments, forces re-encode if any)
         ↓
  voice_client.play(FFmpegOpusAudio(cached.opus))
  + asyncio.create_task(_prefetch_next_track)  [fire-and-forget]
         ↓ PREFETCH (45s budget, background)
  async_download next track (same pipeline, but PREFETCH_TIMEOUT_SECONDS)
  + codec path logged [D-03]
  + perf timing logged [D-17]
         ↓
  cleanup_cache() [hourly, LFU-sorted, in-use protection]
  /stats embed [cache_hit_rate, avg_ttfa, avg_download]
```

### Recommended Project Structure (no new files except new test file)

```
services/
├── youtube.py          # MODIFY: DOWNLOAD_OPTS + SponsorBlock PPs, codec logging hooks, DOWNLOAD_OPTS_PREFETCH variant
├── audio.py            # MODIFY: get_source adds asyncio.wait_for; cleanup_cache() LFU rewrite; timing logging
cogs/
├── music.py            # MODIFY: _play_track adds prefetch task; play() adds resolution cache intercept
├── ops.py              # MODIFY: /stats passes perf_metrics to embed
database.py             # MODIFY: SCHEMA_SQL adds resolution_cache table; add lookup/write helpers
config.py               # MODIFY: add PREFETCH_TIMEOUT_SECONDS, RES_CACHE_TTL_DAYS, SPONSORBLOCK_CATEGORIES, PERF_ROLLING_WINDOW
models/queue.py         # MODIFY: add _prefetch_video_id and _prefetch_task fields; clear() clears them
utils/embeds.py         # MODIFY: uncomment Phase-6 stats fields, add perf_metrics param to stats_embed
tests/
├── test_audio.py       # MODIFY: update cleanup_cache tests for LFU; add timeout tests
├── test_youtube.py     # MODIFY: add codec path detection tests
└── test_phase6_perf.py # CREATE: resolution cache helpers, LFU eviction, normalization
```

### Pattern 1: SponsorBlock + Codec Postprocessors in DOWNLOAD_OPTS

**What:** Two-postprocessor sequence added to `DOWNLOAD_OPTS` for segment removal.
**When to use:** Every audio download in `services/youtube.py`.

```python
# Source: Verified via Python introspection of yt_dlp postprocessor module + yt-dlp/__init__.py source
# SponsorBlock categories (D-14) — configured in config.py
SPONSORBLOCK_CATEGORIES = frozenset({
    "sponsor", "selfpromo", "intro", "outro", "interaction", "music_offtopic"
})

DOWNLOAD_OPTS = {
    "format": "bestaudio/best",
    "postprocessors": [
        {
            "key": "SponsorBlock",
            "categories": config.SPONSORBLOCK_CATEGORIES,
            "when": "after_filter",    # REQUIRED: populates chapters before ModifyChapters runs
        },
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "opus",
            "preferredquality": config.AUDIO_QUALITY,   # unchanged; no effect on copy path
        },
        {
            "key": "ModifyChapters",
            "remove_chapters_patterns": [],
            "remove_sponsor_segments": config.SPONSORBLOCK_CATEGORIES,
            "remove_ranges": [],
            "force_keyframes": False,
        },
    ],
    "outtmpl": str(config.AUDIO_CACHE_DIR / "%(id)s.%(ext)s"),
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
}
```

**Critical ordering:** `SponsorBlock` must have `when='after_filter'`; it runs before `post_process` stage. `FFmpegExtractAudio` and `ModifyChapters` are both `post_process` and run in list order. If `ModifyChapters` runs before `FFmpegExtractAudio`, it operates on raw video — always add `FFmpegExtractAudio` before `ModifyChapters` in the list.

### Pattern 2: Codec Path Detection via postprocessor_hooks (D-03)

**What:** Add a closure-based hook to capture the codec path yt-dlp chose.
**When to use:** In `download()` in `services/youtube.py`.

```python
# Source: Verified via yt_dlp.YoutubeDL source introspection (postprocessor_hooks key confirmed)
def download(self, video_id: str, url: str) -> Path | None:
    cached = config.AUDIO_CACHE_DIR / f"{video_id}.opus"
    if cached.exists():
        log.info("cache_path=hit video_id=%s", video_id)
        return cached

    _codec_path = {"value": "unknown"}   # mutable closure for hook

    def _pp_hook(d):
        if d.get("postprocessor") == "FFmpegExtractAudio" and d.get("status") == "finished":
            acodec = (d.get("info_dict") or {}).get("acodec", "unknown")
            _codec_path["value"] = "copy" if acodec == "opus" else "transcode"

    opts = {**DOWNLOAD_OPTS, "postprocessor_hooks": [_pp_hook]}
    t0 = time.monotonic()
    with YoutubeDL(opts) as ydl:
        ydl.download([url])
    elapsed = time.monotonic() - t0

    if cached.exists():
        log.info(
            "download complete video_id=%s codec_path=%s elapsed=%.2fs",
            video_id, _codec_path["value"], elapsed,
        )
        return cached
    return None
```

### Pattern 3: Prefetch Fire-and-Forget (D-04/D-06)

**What:** Non-blocking prefetch triggered immediately after `voice_client.play()`.
**When to use:** Inside `_play_track` in `cogs/music.py`, after the play call.

```python
# Source: Mirrors existing _post_auto_lyrics pattern in cogs/music.py
# After voice_client.play(source, after=after_callback):
next_tracks = queue.upcoming()
if next_tracks:
    asyncio.create_task(
        self._prefetch_next_track(guild, next_tracks[0], current_gen)
    )

async def _prefetch_next_track(
    self,
    guild: discord.Guild,
    track: Track,
    expected_gen: int,
) -> None:
    """Background prefetch — must not block or error-crash the event loop."""
    queue = self.get_queue(guild.id)
    if queue._play_generation != expected_gen:
        return   # stale; track was skipped before prefetch started
    if self.audio.is_cached(track.video_id):
        log.debug("prefetch skip (already cached) video_id=%s", track.video_id)
        return
    try:
        queue._prefetch_video_id = track.video_id
        t0 = time.monotonic()
        # Uses PREFETCH_TIMEOUT_SECONDS (45s) — generous budget since nobody is waiting
        path = await asyncio.wait_for(
            self.youtube.async_download(track.video_id, track.url),
            timeout=config.PREFETCH_TIMEOUT_SECONDS,
        )
        elapsed = time.monotonic() - t0
        # Re-check generation: if user skipped during the 45s download, discard
        if queue._play_generation != expected_gen:
            log.debug("prefetch result discarded (generation changed) video_id=%s", track.video_id)
            return
        log.info("prefetch complete video_id=%s elapsed=%.2fs ok=%s", track.video_id, elapsed, path is not None)
    except asyncio.TimeoutError:
        log.info("prefetch timeout video_id=%s (will download on-demand)", track.video_id)
    except Exception as exc:
        log.debug("prefetch error video_id=%s: %s", track.video_id, exc)
    finally:
        if queue._prefetch_video_id == track.video_id:
            queue._prefetch_video_id = None
```

### Pattern 4: asyncio.wait_for Wrapping async_download (D-10/D-11)

**What:** Wire the existing `DOWNLOAD_TIMEOUT_SECONDS` constant into `get_source`.
**When to use:** Tier 2 (download) in `services/audio.py:get_source`.

```python
# Source: Python stdlib asyncio docs — asyncio.wait_for cancels the Task on timeout
# The underlying run_in_executor thread continues but asyncio does not block
try:
    path = await asyncio.wait_for(
        self.youtube_service.async_download(track.video_id, track.url),
        timeout=config.DOWNLOAD_TIMEOUT_SECONDS,
    )
except asyncio.TimeoutError:
    log.warning(
        "download timeout after %ss video_id=%s, falling back to stream",
        config.DOWNLOAD_TIMEOUT_SECONDS, track.video_id,
    )
    path = None
```

### Pattern 5: LFU Eviction via song_history (D-12)

**What:** Replace `st_atime` sort in `cleanup_cache()` with play-count from `song_history`.
**When to use:** In `services/audio.py:cleanup_cache()`.

```python
# Source: asyncpg query pattern from database.py; song_history schema already has url field
# video_id extracted from url via url.split("v=")[-1].split("&")[0]
async def cleanup_cache(self, pool, protected_video_ids: set[str]) -> None:
    files = list(self.cache_dir.glob("*.opus"))
    if not files:
        return
    total_bytes = sum(f.stat().st_size for f in files)
    max_bytes = self.max_cache_mb * 1024 * 1024
    if total_bytes <= max_bytes:
        return

    # Fetch play counts for all cached files
    all_ids = [f.stem for f in files]  # stem = video_id (filename without .opus)
    # Build play_count dict from song_history
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT url, COUNT(*) AS plays FROM song_history GROUP BY url"
        )
    play_counts = {}
    for row in rows:
        url = row["url"]
        # Extract video_id from YouTube URL
        if "v=" in url:
            vid = url.split("v=")[-1].split("&")[0]
            play_counts[vid] = row["plays"]

    # Sort: lowest play_count first, tie-break oldest mtime
    def eviction_key(f: Path):
        vid = f.stem
        if vid in protected_video_ids:
            return (float("inf"), 0)   # never evict
        return (play_counts.get(vid, 0), f.stat().st_mtime)

    files.sort(key=eviction_key)
    for f in files:
        if total_bytes <= max_bytes:
            break
        vid = f.stem
        if vid in protected_video_ids:
            continue
        size = f.stat().st_size
        f.unlink()
        total_bytes -= size
        log.info("cache evict video_id=%s play_count=%d size=%dKB", vid, play_counts.get(vid, 0), size // 1024)
```

**Protected set construction (called from `cogs/music.py` cleanup task):**
```python
# All video_ids currently in queue (playing + queued + prefetched)
protected = {t.video_id for t in queue.tracks[queue.current_index:]}
if queue._prefetch_video_id:
    protected.add(queue._prefetch_video_id)
```

### Pattern 6: Resolution Cache Table + Helpers (D-07/D-09)

**What:** Postgres table + asyncpg helpers for normalized-query → video_id caching.
**When to use:** Added to `database.py` SCHEMA_SQL and query helpers.

```python
# Source: asyncpg pattern from existing database.py (guild_queues, user_favorites)
# Added to SCHEMA_SQL:
"""
CREATE TABLE IF NOT EXISTS resolution_cache (
    query_key   TEXT PRIMARY KEY,
    video_id    TEXT NOT NULL,
    title       TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rescache_expires ON resolution_cache(expires_at);
"""

# Normalization function (pure, testable):
def normalize_search_query(q: str) -> str:
    """strip + lower + collapse whitespace."""
    import re
    return re.sub(r'\s+', ' ', q.strip().lower())

# Lookup helper:
async def get_resolution_cache(pool, *, query_key: str) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT video_id, title FROM resolution_cache"
            " WHERE query_key = $1 AND expires_at > now()",
            query_key,
        )
    return dict(row) if row else None

# Write helper:
async def set_resolution_cache(
    pool, *, query_key: str, video_id: str, title: str | None, ttl_days: int
) -> None:
    from datetime import datetime, timezone, timedelta
    expires = datetime.now(timezone.utc) + timedelta(days=ttl_days)
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO resolution_cache (query_key, video_id, title, expires_at)"
            " VALUES ($1, $2, $3, $4)"
            " ON CONFLICT (query_key) DO UPDATE SET"
            "  video_id = EXCLUDED.video_id,"
            "  title = EXCLUDED.title,"
            "  expires_at = EXCLUDED.expires_at",
            query_key, video_id, title, expires,
        )
```

**Integration in `play()` command (`cogs/music.py`):**
```python
# Only for non-URL queries (direct URLs bypass cache — D-09)
if not self.youtube.is_url(query):
    key = normalize_search_query(query)
    cached_result = await get_resolution_cache(self.bot.pool, query_key=key)
    if cached_result:
        log.info("resolution_cache hit query=%r video_id=%s", key, cached_result["video_id"])
        # skip async_search, build Track from cached video_id
        # ... then set_resolution_cache to refresh TTL
    else:
        results = await self.youtube.async_search(query)
        # after user picks: write to resolution cache
```

### Pattern 7: Rolling Perf Metrics Aggregate (D-17/D-18)

**What:** Bot-level in-memory rolling aggregate using `collections.deque`.
**When to use:** Created in `bot.py` (or as a singleton in a new `services/metrics.py`); surfaced in `/stats`.

```python
# Source: Python stdlib collections.deque with maxlen
import collections
import time

class PerfMetrics:
    """Rolling in-memory aggregate for pipeline timing (D-17/D-18). Thread-safe reads."""

    def __init__(self, window: int = 50):
        self.cache_hits: collections.deque[bool] = collections.deque(maxlen=window)
        self.download_times: collections.deque[float] = collections.deque(maxlen=window)
        self.search_times: collections.deque[float] = collections.deque(maxlen=window)
        self.ttfa_times: collections.deque[float] = collections.deque(maxlen=window)

    def record_cache_result(self, hit: bool) -> None:
        self.cache_hits.append(hit)

    def record_download(self, elapsed: float) -> None:
        self.download_times.append(elapsed)

    def record_search(self, elapsed: float) -> None:
        self.search_times.append(elapsed)

    def record_ttfa(self, elapsed: float) -> None:
        self.ttfa_times.append(elapsed)

    def summary(self) -> dict:
        """Returns dict for /stats embed."""
        hit_rate = (sum(self.cache_hits) / len(self.cache_hits) * 100) if self.cache_hits else 0.0
        avg_dl = (sum(self.download_times) / len(self.download_times)) if self.download_times else 0.0
        avg_ttfa = (sum(self.ttfa_times) / len(self.ttfa_times)) if self.ttfa_times else 0.0
        avg_search = (sum(self.search_times) / len(self.search_times)) if self.search_times else 0.0
        return {
            "cache_hit_rate": hit_rate,
            "avg_download_s": avg_dl,
            "avg_ttfa_s": avg_ttfa,
            "avg_search_s": avg_search,
            "samples": len(self.cache_hits),
        }
```

**stats_embed integration** — already stubbed in `utils/embeds.py:255-257`:
```python
# Uncomment and wire:
embed.add_field(name="cache hit rate", value=f"{perf['cache_hit_rate']:.0f}%", inline=True)
embed.add_field(name="avg time-to-first-audio", value=f"{perf['avg_ttfa_s']:.1f}s", inline=True)
```

### Anti-Patterns to Avoid

- **Blocking download in `_play_track`:** Always fire prefetch as `asyncio.create_task`; never await it.
- **SponsorBlock without `when='after_filter'`:** Without the `when` key, `SponsorBlockPP` runs at `post_process` stage, potentially after `ModifyChaptersPP` has already run — chapters will not exist yet.
- **ModifyChapters before FFmpegExtractAudio:** ModifyChapters must run AFTER FFmpegExtractAudio in the postprocessors list (list order matters within `post_process` stage).
- **Evicting the prefetched track:** Always include `queue._prefetch_video_id` in the protected set before calling `cleanup_cache()`.
- **Resolution cache on URL queries:** `is_url()` must gate cache lookup — direct URLs must bypass it.
- **Using `date.today()` for TTL expires_at:** Use `datetime.now(timezone.utc)` to get a timezone-aware datetime for asyncpg `TIMESTAMPTZ` columns.
- **Stale prefetch on skip:** Pass `current_gen` to the prefetch task and gate the download start AND result handling behind a `queue._play_generation == expected_gen` check.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Opus passthrough at playback | Custom FFmpeg process manager | `discord.FFmpegOpusAudio` (already in `audio.py`) | Already implemented in D-12 Phase 7; just keep it |
| Segment removal from audio | Custom FFmpeg filter graph | `ModifyChaptersPP` via yt-dlp postprocessors | Handles overlapping segments, concat filter, keyframe forcing |
| Codec detection | Parse ffprobe output manually | `FFmpegExtractAudioPP` + `postprocessor_hooks` | yt-dlp already runs ffprobe internally; hooks expose the result |
| YouTube format selection | Manual HTTP requests | yt-dlp `format: 'bestaudio/best'` | Handles all YouTube variants, CDN selection, and fallbacks |
| SponsorBlock API client | Direct requests to sponsor.ajay.app | `SponsorBlockPP` postprocessor | Already handles hashed video_id, category filtering, API retries |
| Rolling time average | Custom circular buffer | `collections.deque(maxlen=N)` | stdlib, O(1) append/pop, thread-safe reads |

**Key insight:** yt-dlp's postprocessor pipeline already handles the entire download-time audio transformation stack. Adding SponsorBlock is a matter of configuring the existing postprocessor system, not writing custom FFmpeg code.

---

## Critical Findings: Copy-When-Opus is Already Implemented

**This is the most important research finding for planning.**

`FFmpegExtractAudioPP` with `preferredcodec='opus'` already performs copy-when-opus — this is not a new behavior to implement. From the source code (verified via introspection):

```python
# FFmpegExtractAudioPP.run() logic (simplified):
filecodec = get_audio_codec(path)   # runs ffprobe
target_format = 'opus'              # from preferredcodec='opus'

if target_format == filecodec:      # both opus → copy path
    acodec = 'copy'
    # quality args NOT applied when acodec == 'copy'
    log.info('Not converting audio; file is already in target format opus')
else:
    acodec = 'libopus'
    more_opts = quality_args(acodec)   # -b:a 192k
```

**Implication for D-01/D-02:** The existing `DOWNLOAD_OPTS` with `preferredcodec='opus'` already avoids the wasteful re-encode when YouTube delivers an opus stream. `preferredquality='192'` has zero effect on the copy path (quality args are skipped). The D-01 work is therefore:
1. **Add codec-path logging** (D-03) via `postprocessor_hooks` — the real missing piece
2. **Add SponsorBlock postprocessors** (D-14) which introduce the D-16 interaction
3. **Verify** the copy path is taken for YouTube opus sources in testing

The `FORMAT='bestaudio/best'` selection already prefers opus streams from YouTube, so the copy path is the common case.

---

## Common Pitfalls

### Pitfall 1: SponsorBlock `when=` key is mandatory

**What goes wrong:** Without `'when': 'after_filter'` on the `SponsorBlock` PP entry, yt-dlp registers it as `post_process`. Both `SponsorBlockPP` and `ModifyChaptersPP` then run in `post_process` stage in list order, but `ModifyChaptersPP` checks `info['sponsorblock_chapters']` which hasn't been populated yet — it exits with no cuts.
**Why it happens:** yt-dlp's `__init__.py` explicitly sets `when='after_filter'` for SponsorBlock when converting CLI options to postprocessors. The Python API does not set it automatically.
**How to avoid:** Always include `'when': 'after_filter'` in the SponsorBlock PP dict.
**Warning signs:** No segments cut even for videos known to have sponsor segments.

### Pitfall 2: ModifyChapters cuts always force re-encode (D-16)

**What goes wrong:** Planning assumes SponsorBlock + copy-when-opus are fully compatible — but `ModifyChaptersPP` uses FFmpeg concat filter to remove segments, which requires re-encoding the output.
**Why it happens:** Audio stream copy is only valid when the output is a single contiguous stream. After a cut, FFmpeg must re-encode to produce a valid opus file.
**How to avoid:** Accept this behavior (D-16 confirms it is expected). Only tracks with zero SponsorBlock segments get the copy-fast-path. Log accordingly.
**Warning signs:** Transcode logs on opus sources that should be copies — check if those tracks had sponsor segments.

### Pitfall 3: asyncio.wait_for does not cancel the thread

**What goes wrong:** Developer assumes `asyncio.wait_for(async_download(...), timeout=10)` kills the yt-dlp download thread on timeout.
**Why it happens:** `run_in_executor` submits work to a `ThreadPoolExecutor`. Python threads cannot be cancelled from outside. `wait_for` only cancels the awaitable (the `Future` wrapping the thread result). The thread runs to completion in the background.
**How to avoid:** This behavior is acceptable (D-10 discretion item — confirmed harmless). The thread either completes and warms the cache, or yt-dlp errors internally. No explicit cleanup needed.
**Warning signs:** Many consecutive prefetch timeouts will accumulate threads until they complete. Monitor thread count in debug sessions if this becomes a concern.

### Pitfall 4: Prefetch stale-generation race

**What goes wrong:** User skips while a prefetch is in flight. The prefetch completes and overwrites queue state or triggers playback.
**Why it happens:** Prefetch reads "next track" from queue at task-spawn time; by the time the download finishes, the queue may have advanced multiple positions.
**How to avoid:** Pass `current_gen` to the prefetch task. Check `queue._play_generation == expected_gen` both at task start AND after download completes before doing anything with the result.
**Warning signs:** Double-advance or wrong-track-plays after rapid skips.

### Pitfall 5: Resolution cache does not refresh TTL on hit

**What goes wrong:** A frequently-used query expires and must be re-looked-up on every session.
**Why it happens:** INSERT with ON CONFLICT only updates if explicitly told to update `expires_at`.
**How to avoid:** The `set_resolution_cache` ON CONFLICT clause must update `expires_at` as well as `video_id` and `title`. This makes a cache hit also bump the TTL.
**Warning signs:** Resolution cache misses on queries used daily.

### Pitfall 6: Evicting queued or prefetched tracks

**What goes wrong:** `cleanup_cache()` runs during playback and deletes the file that `_prefetch_next_track` just wrote, causing `get_source` cache miss on the next track.
**Why it happens:** Cleanup runs on a background task; prefetch is also background. Both can run concurrently.
**How to avoid:** Build the `protected_video_ids` set from ALL current queue entries (not just playing) plus `queue._prefetch_video_id`. Pass this set to `cleanup_cache()`.
**Warning signs:** Unexpected download on a song that "should have been prefetched."

### Pitfall 7: SCHEMA_SQL multi-statement DDL with parameters

**What goes wrong:** Adding `$N` parameters to the resolution_cache table definition breaks the `conn.execute(SCHEMA_SQL)` call.
**Why it happens:** asyncpg's multi-statement DDL execution path does not support positional parameters — it's documented in CLAUDE.md as Pitfall 1.
**How to avoid:** `SCHEMA_SQL` must contain ONLY DDL with no `$N` params. TTL values are computed in Python and passed as parameters in the `set_resolution_cache` helper, not in the schema.

---

## Runtime State Inventory

Phase 6 is not a rename/refactor phase. The resolution_cache table is NEW (no existing data to migrate). The `cleanup_cache()` rewrite changes behavior going forward (atime → LFU) but does not require migrating existing cache files. No runtime state migration is required.

**None — verified:** No stored data needs migration. Resolution cache is a new table populated from zero. Existing `song_history` records are read-only inputs to LFU; no writes needed beyond normal operation.

---

## New Config Constants Required

These must be added to `config.py` under a `# --- Phase 6: Speed & Caching ---` block:

| Constant | Value | Purpose |
|----------|-------|---------|
| `PREFETCH_TIMEOUT_SECONDS` | `45` | Generous budget for background prefetch (D-10) |
| `RES_CACHE_TTL_DAYS` | `14` | Resolution cache TTL (D-07) |
| `SPONSORBLOCK_CATEGORIES` | `frozenset({"sponsor","selfpromo","intro","outro","interaction","music_offtopic"})` | D-14 categories as config constant |
| `PERF_ROLLING_WINDOW` | `50` | Rolling aggregate sample count (D-18 discretion) |

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (already installed) |
| Config file | `pytest.ini` or `pyproject.toml` (existing) |
| Quick run command | `pytest tests/test_phase6_perf.py tests/test_audio.py tests/test_youtube.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PERF-01 | Prefetch task spawned when next track exists in queue | unit | `pytest tests/test_phase6_perf.py::test_prefetch_task_spawned -x` | Wave 0 |
| PERF-01 | Prefetch skips already-cached tracks | unit | `pytest tests/test_phase6_perf.py::test_prefetch_skips_cached -x` | Wave 0 |
| PERF-01 | Prefetch generation guard: stale task discards result | unit | `pytest tests/test_phase6_perf.py::test_prefetch_stale_gen -x` | Wave 0 |
| PERF-02 | Codec path logging: copy path logged for opus source | unit | `pytest tests/test_youtube.py::TestCodecLogging -x` | Wave 0 |
| PERF-02 | Codec path logging: transcode logged for non-opus | unit | `pytest tests/test_youtube.py::TestCodecLogging::test_transcode_logged -x` | Wave 0 |
| PERF-03 | `normalize_search_query`: casing/whitespace normalization | unit | `pytest tests/test_phase6_perf.py::TestNormalizeQuery -x` | Wave 0 |
| PERF-03 | Resolution cache lookup returns hit on known key | integration (live DB) | `pytest tests/test_phase6_perf.py::TestResolutionCache -x` | Wave 0 |
| PERF-03 | Resolution cache miss on expired TTL | integration (live DB) | `pytest tests/test_phase6_perf.py::TestResolutionCache::test_expired_ttl_miss -x` | Wave 0 |
| PERF-03 | URL queries bypass resolution cache | unit | `pytest tests/test_phase6_perf.py::test_url_bypasses_cache -x` | Wave 0 |
| PERF-04 | `get_source` raises TimeoutError → falls back to stream | unit | `pytest tests/test_audio.py::TestDownloadTimeout -x` | Wave 0 |
| PERF-05 | `cleanup_cache` evicts lowest-play-count file first | unit | `pytest tests/test_audio.py::TestLFUEviction -x` | Wave 0 |
| PERF-05 | `cleanup_cache` never evicts protected video_ids | unit | `pytest tests/test_audio.py::TestLFUEviction::test_protected_not_evicted -x` | Wave 0 |
| PERF-05 | `cleanup_cache` tie-breaks by oldest mtime | unit | `pytest tests/test_audio.py::TestLFUEviction::test_tiebreak_oldest -x` | Wave 0 |
| PERF-06 | `PerfMetrics.summary()` returns correct hit rate | unit | `pytest tests/test_phase6_perf.py::TestPerfMetrics -x` | Wave 0 |
| PERF-06 | Timing logged per download event | unit (log capture) | `pytest tests/test_phase6_perf.py::test_timing_logged -x` | Wave 0 |
| PERF-07 | `DOWNLOAD_OPTS` contains SponsorBlock and ModifyChapters keys | unit | `pytest tests/test_youtube.py::TestDownloadOpts -x` | Wave 0 |
| PERF-07 | SponsorBlock PP has `when='after_filter'` | unit | `pytest tests/test_youtube.py::TestDownloadOpts::test_sponsorblock_when -x` | Wave 0 |

**Manual/integration-only items (cannot be automated without live YouTube + Discord):**
- Confirming actual copy-path taken by real YouTube opus stream (requires live yt-dlp run)
- End-to-end gapless playback verification (requires voice channel)
- SponsorBlock segment actually removed from a known-segmented video (requires live yt-dlp)

### Sampling Rate

- **Per task commit:** `pytest tests/test_phase6_perf.py tests/test_audio.py tests/test_youtube.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_phase6_perf.py` — covers PERF-01 (prefetch), PERF-03 (resolution cache), PERF-05 (LFU), PERF-06 (metrics)
- [ ] `tests/test_audio.py` — update `TestCacheCleanup` for LFU; add `TestDownloadTimeout`
- [ ] `tests/test_youtube.py` — add `TestDownloadOpts`, `TestCodecLogging`
- [ ] `database.py` helpers: `get_resolution_cache`, `set_resolution_cache`, `normalize_search_query`
- [ ] `conftest.py`: update `DROP TABLE` teardown to include `resolution_cache`

---

## Security Domain

Phase 6 adds a new Postgres table (`resolution_cache`) and external API calls (SponsorBlock). ASVS V5 (input validation) applies to the resolution cache key; V4 (access control) is not affected (no new commands). The SponsorBlock API call is made by yt-dlp internally with a hashed video_id prefix — no user-controlled input reaches the API.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | No new slash commands |
| V5 Input Validation | yes | `normalize_search_query` sanitizes before DB write; query key stored as TEXT with `$N` param (no interpolation) |
| V6 Cryptography | no | — |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via query cache key | Tampering | `$N` positional params in all resolution_cache queries |
| Cache poisoning (malicious query→wrong video_id) | Tampering | TTL expiry (14 days); user-controlled only by their own query input; no cross-user cache key collision possible from normalized queries |
| SponsorBlock API timeout causing download hang | DoS | yt-dlp has internal timeout on the SponsorBlock fetch; download proceeds with no segments if API is unreachable |

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| yt-dlp | SponsorBlock, download | ✓ | 2026.6.9 | — |
| FFmpeg | SponsorBlock cuts, codec | ✓ | 2026-05-21 | — |
| asyncpg + Postgres | Resolution cache | ✓ | asyncpg 0.31.0 | — |
| Python asyncio | wait_for, create_task | ✓ | 3.12.10 stdlib | — |
| SponsorBlock API (sponsor.ajay.app) | PERF-07 | not probed | external | yt-dlp proceeds with no segments on API failure |

**Missing dependencies with no fallback:** none
**Missing dependencies with fallback:** SponsorBlock API is external; yt-dlp handles its own API errors silently.

---

## State of the Art

| Old Approach | Current Approach | Relevant Change | Impact |
|--------------|------------------|-----------------|--------|
| `FFmpegExtractAudio` always re-encodes | `FFmpegExtractAudio` performs copy when `filecodec == target_format` | yt-dlp long-standing behavior | No code change needed for D-01/D-02; just add logging |
| `--sponsorblock-remove` CLI only | Python API via `postprocessors` dicts with `key='SponsorBlock'` + `key='ModifyChapters'` | Stable since yt-dlp integrated SponsorBlock | Two-PP dict pattern is the canonical Python API |
| `atime`-based cache eviction | LFU from `song_history` | Phase 6 work | Prevents evicting recently-played songs |
| No download timeout wired | `asyncio.wait_for(DOWNLOAD_TIMEOUT_SECONDS)` | Phase 6 work | Prevents silent hang on slow downloads |

**Deprecated/outdated:**
- `cleanup_cache()` `st_atime` sort: replaced by LFU. Note: `st_atime` is unreliable on many filesystems anyway (noatime mount option).
- `AUDIO_CACHE_MAX_MB = 2048` in CLAUDE.md spec: actual `config.py` has `512` (K-07 Koyeb disk cap). The 2GB figure in CLAUDE.md is stale. Phase 6 uses the `config.AUDIO_CACHE_MAX_MB` constant (512) as authoritative.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | YouTube's `bestaudio/best` format selection returns an opus stream in the majority of cases | Copy-When-Opus | If YT changes default audio formats, more downloads would transcode. Low risk — YT has offered opus for years and yt-dlp prefers it. |
| A2 | `postprocessor_hooks` key fires with `d['postprocessor'] == 'FFmpegExtractAudio'` and `d['info_dict']['acodec']` is populated | Codec Detection | If the hook payload structure differs, codec logging would show 'unknown'. Risk: medium — hook structure confirmed via source but not live-tested. |
| A3 | SponsorBlock `when='after_filter'` causes it to fire before `post_process` PPs | SponsorBlock Ordering | If ordering is wrong, ModifyChapters runs with no chapter data. Verified via yt-dlp `__init__.py` source — LOW risk. |
| A4 | The orphan `run_in_executor` thread on `wait_for` timeout drains harmlessly and does not cause `asyncio` event loop errors | Timeout Behavior | Confirmed via Python asyncio docs and yt-dlp thread-safety analysis. LOW risk. |

---

## Open Questions

1. **Codec detection hook payload field names**
   - What we know: `postprocessor_hooks` key is supported, fires per PP event
   - What's unclear: exact field names in the hook dict `d` at `status='finished'` for `FFmpegExtractAudio`
   - Recommendation: Add a debug-only log of the full `d` dict in a test run to confirm field names, then assert against `d.get('postprocessor') == 'FFmpegExtractAudio'` and `d.get('info_dict', {}).get('acodec')`

2. **Prefetch + filter interaction (Phase 7 compatibility)**
   - What we know: Phase 7 introduced `active_filter` which forces FFmpeg re-encode. Prefetch downloads with the standard DOWNLOAD_OPTS (no filter).
   - What's unclear: if a user applies a filter MID-prefetch, the prefetched file is still a raw .opus — `get_source` will re-apply the filter at playback time anyway. This is correct behavior.
   - Recommendation: No special handling needed. The prefetched file is always the "clean" version; filters are applied at playback time by `get_source`.

---

## Sources

### Primary (HIGH confidence)
- `/yt-dlp/yt-dlp` (Context7) — SponsorBlock postprocessor categories, `FFmpegExtractAudio` configuration
- Python introspection of `yt_dlp.postprocessor.sponsorblock.SponsorBlockPP` + `ModifyChaptersPP` — constructor signatures, `NON_SKIPPABLE_CATEGORIES`, `CATEGORIES` confirmed [VERIFIED: live introspection on installed yt-dlp 2026.6.9]
- Python introspection of `yt_dlp.postprocessor.ffmpeg.FFmpegExtractAudioPP` — copy-when-opus logic, `ACODECS` mapping [VERIFIED: live introspection]
- `yt_dlp.YoutubeDL.__init__` source — `postprocessor_hooks` key confirmed [VERIFIED: live introspection]
- `yt_dlp.__init__.get_postprocessors()` source — two-PP dict structure (`SponsorBlock` + `ModifyChapters`) confirmed [VERIFIED: WebFetch of github.com/yt-dlp/yt-dlp]
- Python asyncio stdlib docs — `asyncio.wait_for` + `run_in_executor` thread behavior [CITED: docs.python.org/3/library/asyncio-task]
- Existing project source files: `services/audio.py`, `services/youtube.py`, `cogs/music.py`, `models/queue.py`, `database.py`, `config.py`, `cogs/ops.py`, `utils/embeds.py` [VERIFIED: direct file reads]

### Secondary (MEDIUM confidence)
- github.com/yt-dlp/yt-dlp/issues/9186 — SponsorBlock Python API category format (list not string) [CITED]
- github.com/yt-dlp/yt-dlp/issues/1555 — SponsorBlock Python API structure confirmation [CITED]
- deepwiki.com/yt-dlp/yt-dlp/2.5-post-processing-pipeline — SponsorBlock + ModifyChapters pipeline flow [CITED]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages installed and introspected live
- Copy-when-opus behavior: HIGH — verified via live yt-dlp source introspection
- SponsorBlock postprocessor API: HIGH — verified via yt-dlp `__init__.py` source + live introspection of PP classes
- Prefetch pattern: HIGH — directly mirrors existing `_post_auto_lyrics` fire-and-forget pattern
- asyncio timeout behavior: HIGH — stdlib behavior, well-documented
- LFU eviction approach: HIGH — uses existing `song_history` schema
- Resolution cache schema: HIGH — follows exact asyncpg patterns already in `database.py`
- Codec hook payload fields: MEDIUM — hook key confirmed, exact field names assumed from source reading

**Research date:** 2026-06-24
**Valid until:** 2026-09-24 (yt-dlp updates frequently; re-verify SponsorBlock API if > 90 days old)
