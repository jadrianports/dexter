# Phase 6: Speed & Caching - Pattern Map

**Mapped:** 2026-06-24
**Files analyzed:** 9
**Analogs found:** 9 / 9

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `services/youtube.py` | service | batch/transform | self (existing DOWNLOAD_OPTS, download()) | self-extend |
| `services/audio.py` | service | file-I/O | self (existing get_source, cleanup_cache) | self-extend |
| `cogs/music.py` | controller | event-driven | self (existing _play_track, _post_auto_lyrics, try_auto_queue) | self-extend |
| `database.py` | model/utility | CRUD | self (existing SCHEMA_SQL, asyncpg helpers, guild_queues table) | self-extend |
| `config.py` | config | — | self (existing Phase 4/7 constant blocks) | self-extend |
| `models/queue.py` | model | — | self (existing _play_generation, active_filter fields) | self-extend |
| `utils/embeds.py` | utility | — | self (existing stats_embed stubbed lines 255-257) | self-extend |
| `tests/test_audio.py` | test | — | self (existing TestCacheCleanup, TestBuildFfmpegOpts) | self-extend |
| `tests/test_youtube.py` | test | — | self (existing test class + mock pattern) | self-extend |
| `tests/test_phase6_perf.py` | test | — | `tests/test_database_phase4.py` / `tests/test_queue.py` | role-match |

---

## Pattern Assignments

### `services/youtube.py` — DOWNLOAD_OPTS + SponsorBlock PPs + codec hook + download timeout

**Analog:** `services/youtube.py` lines 63-76 (existing DOWNLOAD_OPTS), lines 163-195 (existing download())

**Existing DOWNLOAD_OPTS pattern** (lines 63-76):
```python
DOWNLOAD_OPTS = {
    "format": "bestaudio/best",
    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "opus",
            "preferredquality": config.AUDIO_QUALITY,
        }
    ],
    "outtmpl": str(config.AUDIO_CACHE_DIR / "%(id)s.%(ext)s"),
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
}
```

**Phase 6 change:** Extend the `"postprocessors"` list to add `SponsorBlock` (before `FFmpegExtractAudio`) and `ModifyChapters` (after). Critical ordering: `SponsorBlock` requires `"when": "after_filter"` or segments will not be cut. `FFmpegExtractAudio` must precede `ModifyChapters` in list order within `post_process` stage.

**Existing download() pattern** (lines 163-195) — the function to receive codec-path logging:
```python
def download(self, video_id: str, url: str) -> Path | None:
    cached = config.AUDIO_CACHE_DIR / f"{video_id}.opus"
    if cached.exists():
        return cached

    try:
        with YoutubeDL(DOWNLOAD_OPTS) as ydl:
            ydl.download([url])
        if cached.exists():
            log.info(f"Downloaded {video_id} to cache")
            return cached
        return None
    except Exception as e:
        log.error(f"Download failed for {video_id}: {e}")
        ...
```

**Phase 6 change:** Add a `_codec_path` mutable closure + `_pp_hook` function inside `download()`, then pass `{**DOWNLOAD_OPTS, "postprocessor_hooks": [_pp_hook]}` instead of bare `DOWNLOAD_OPTS`. Log `codec_path=` and `elapsed=` after the download completes. Add a `time.monotonic()` delta around the `ydl.download()` call.

**async_download pattern** (lines 207-210) — unchanged; `asyncio.wait_for` wraps the caller:
```python
async def async_download(self, video_id: str, url: str) -> Path | None:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, self.download, video_id, url)
```

---

### `services/audio.py` — get_source timeout + cleanup_cache LFU rewrite

**Analog:** `services/audio.py` (entire file, 146 lines)

**Existing get_source tier-2 pattern** (lines 103-109) — where `asyncio.wait_for` wraps `async_download`:
```python
# 2. Try downloading to cache
path = await self.youtube_service.async_download(track.video_id, track.url)
if path and path.exists():
    if not use_opts:
        return discord.FFmpegOpusAudio(str(path))
    opts = _build_ffmpeg_opts(seek_seconds, ffmpeg_filter)
    return discord.FFmpegOpusAudio(str(path), **opts)
```

**Phase 6 change:** Replace the bare `await self.youtube_service.async_download(...)` call with `await asyncio.wait_for(..., timeout=config.DOWNLOAD_TIMEOUT_SECONDS)` wrapped in `try/except asyncio.TimeoutError`. On timeout, log a warning and fall through to the existing stream tier (tier 3, lines 112-122).

**Existing cleanup_cache() pattern** (lines 124-145) — the function to rewrite for LFU:
```python
def cleanup_cache(self) -> None:
    files = list(self.cache_dir.glob("*.opus"))
    if not files:
        return

    total_bytes = sum(f.stat().st_size for f in files)
    max_bytes = self.max_cache_mb * 1024 * 1024

    if total_bytes <= max_bytes:
        return

    # Sort by last access time (oldest first)   ← D-12 replaces this
    files.sort(key=lambda f: f.stat().st_atime)

    for f in files:
        if total_bytes <= max_bytes:
            break
        size = f.stat().st_size
        f.unlink()
        total_bytes -= size
        log.info(f"Cache cleanup: deleted {f.name} ({size // 1024}KB)")
```

**Phase 6 change:** Make `cleanup_cache` async (signature becomes `async def cleanup_cache(self, pool, protected_video_ids: set[str]) -> None`). Replace the `st_atime` sort with an asyncpg query against `song_history` to get per-video play counts, then sort by `(play_count ASC, mtime ASC)`. Skip any `video_id` in `protected_video_ids`. Log `play_count=` per evicted file.

---

### `cogs/music.py` — prefetch task + resolution cache intercept in play()

**Analog 1 — fire-and-forget task pattern** (`_post_auto_lyrics` / `try_auto_queue`):

Trigger site (lines 599-600 and 653-654):
```python
# Auto-lyrics (off the playback path): never awaited — must not delay playback.
if queue.auto_lyrics:
    asyncio.create_task(self._post_auto_lyrics(guild, track))

# Auto-queue (off the playback path):
asyncio.create_task(ai_cog.try_auto_queue(guild))
```

Background task shell (`_post_auto_lyrics`, lines 659+):
```python
async def _post_auto_lyrics(self, guild: discord.Guild, track: Track) -> None:
    try:
        ...  # the work
    except Exception as e:
        log.error(...)  # swallow, never crash event loop
```

**Phase 6 prefetch trigger placement:** After `voice_client.play(source, after=after_callback)` (line 589), add:
```python
next_tracks = queue.upcoming()
if next_tracks:
    asyncio.create_task(
        self._prefetch_next_track(guild, next_tracks[0], current_gen)
    )
```

The `_prefetch_next_track` method follows the same `try/except` shell as `_post_auto_lyrics`. Generation guard (`queue._play_generation != expected_gen`) must be checked both at task start and after `wait_for` returns. `queue._prefetch_video_id` is set before download and cleared in `finally`.

**Analog 2 — generation counter guard pattern** (lines 559-571):
```python
queue._play_generation += 1
current_gen = queue._play_generation

def after_callback(error):
    if queue._play_generation == current_gen:
        asyncio.run_coroutine_threadsafe(
            self._on_track_end(guild), self.bot.loop
        )
```

**Phase 6 prefetch generation check** (copy this guard pattern):
```python
async def _prefetch_next_track(self, guild, track, expected_gen):
    queue = self.get_queue(guild.id)
    if queue._play_generation != expected_gen:
        return  # stale before we even start
    ...
    # after wait_for returns:
    if queue._play_generation != expected_gen:
        return  # skip was issued during the 45s download
```

**Analog 3 — play() command search path** (the intercept point for resolution cache). From context `play()` is at ~line 1068. The resolution-cache intercept pattern from RESEARCH.md:
```python
# Only for non-URL queries (direct URLs bypass cache per D-09)
if not self.youtube.is_url(query):
    key = normalize_search_query(query)
    cached_result = await get_resolution_cache(self.bot.pool, query_key=key)
    if cached_result:
        log.info("resolution_cache hit query=%r video_id=%s", key, cached_result["video_id"])
        # build Track from cached_result["video_id"]; skip async_search
    else:
        results = await self.youtube.async_search(query)
        # after user picks: call set_resolution_cache(...)
```

---

### `database.py` — resolution_cache table + helpers

**Analog — SCHEMA_SQL table pattern** (lines 119-148, guild_queues and user_favorites tables):
```python
CREATE TABLE IF NOT EXISTS guild_queues (
    guild_id   TEXT PRIMARY KEY,
    payload    JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_favorites (
    user_id          TEXT NOT NULL,
    video_id         TEXT NOT NULL,
    ...
    added_at         TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (user_id, video_id)
);

CREATE INDEX IF NOT EXISTS idx_favorites_user ON user_favorites(user_id, added_at DESC);
```

**Phase 6 addition to SCHEMA_SQL** — append before closing `"""`:
```sql
CREATE TABLE IF NOT EXISTS resolution_cache (
    query_key   TEXT PRIMARY KEY,
    video_id    TEXT NOT NULL,
    title       TEXT,
    created_at  TIMESTAMPTZ DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rescache_expires ON resolution_cache(expires_at);
```

**Analog — asyncpg helper pattern with ON CONFLICT** (lines 239-252, update_artist_count):
```python
async def update_artist_count(
    pool: asyncpg.Pool, *, user_id: str, artist: str | None
) -> None:
    if artist is None:
        return
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO user_artist_counts (user_id, artist, play_count)"
            " VALUES ($1, $2, 1)"
            " ON CONFLICT (user_id, artist)"
            " DO UPDATE SET play_count = user_artist_counts.play_count + 1",
            user_id, artist,
        )
```

**Phase 6 helpers** follow this exact pattern. `set_resolution_cache` uses `ON CONFLICT (query_key) DO UPDATE SET video_id=..., title=..., expires_at=...` to refresh TTL on re-write. `get_resolution_cache` uses `conn.fetchrow(... WHERE query_key=$1 AND expires_at > now())`. `normalize_search_query` is a pure function (no pool), placed above the async helpers.

**Pitfall to carry forward:** SCHEMA_SQL must contain only DDL with no `$N` params — the TTL value is Python-computed and passed as a `$N` param in the helper, never embedded in the schema string.

---

### `config.py` — new Phase 6 constant block

**Analog — Phase 7 constant block pattern** (lines 107-126):
```python
# --- Phase 7: Player UX & Filters ---
FFMPEG_FILTERS: dict[str, str] = {
    "bassboost": "bass=g=8",
    ...
}

FAVORITES_MAX_PER_USER = 25
...

# Phase 7 cooldowns (seconds)
SEEK_COOLDOWN_SECONDS = 2
FILTER_COOLDOWN_SECONDS = 5
```

**Phase 6 addition** — append a `# --- Phase 6: Speed & Caching ---` block after the Phase 5 block (after line 104):
```python
# --- Phase 6: Speed & Caching ---
PREFETCH_TIMEOUT_SECONDS = 45          # generous budget for background prefetch (D-10)
RES_CACHE_TTL_DAYS = 14               # resolution cache TTL (D-07)
SPONSORBLOCK_CATEGORIES: frozenset[str] = frozenset({
    "sponsor", "selfpromo", "intro", "outro", "interaction", "music_offtopic"
})                                     # D-14 SponsorBlock categories
PERF_ROLLING_WINDOW = 50              # rolling aggregate sample count (D-18)
```

---

### `models/queue.py` — new prefetch state fields

**Analog — existing Phase 7 fields added to `__init__`** (lines 83-85):
```python
self.playback_started_at: float | None = None
self.paused_at: float | None = None
self.active_filter: str = "off"
```

**And `clear()` resets Phase 7 fields** (lines 221-225):
```python
self.active_filter = "off"
self.playback_started_at = None
self.paused_at = None
```

**Phase 6 addition to `__init__`** — append after the Phase 7 fields:
```python
# Phase 6: prefetch state — cleared on queue clear
self._prefetch_video_id: str | None = None   # video_id being prefetched
self._prefetch_task: asyncio.Task | None = None
```

**Phase 6 addition to `clear()`** — append alongside Phase 7 resets:
```python
self._prefetch_video_id = None
self._prefetch_task = None
```

---

### `utils/embeds.py` — uncomment Phase 6 stats fields

**Analog — stubbed lines already present** (lines 255-257):
```python
# Phase-6 hooks (D-29) — left as comments until Phase 6 instruments the pipeline
# embed.add_field(name="cache hit rate", value="(phase 6)", inline=True)
# embed.add_field(name="time to first audio", value="(phase 6)", inline=True)
```

**Phase 6 change:** Uncomment and update the `stats_embed` function signature to accept a `perf_metrics: dict | None = None` parameter. Wire the deque summary into the embed fields:
```python
if perf_metrics:
    embed.add_field(
        name="cache hit rate",
        value=f"{perf_metrics['cache_hit_rate']:.0f}%",
        inline=True,
    )
    embed.add_field(
        name="avg time-to-first-audio",
        value=f"{perf_metrics['avg_ttfa_s']:.1f}s",
        inline=True,
    )
```

The caller in `cogs/ops.py` line 202 (`embeds.stats_embed(daily, rpm, config.GEMINI_RPM_LIMIT, images, metrics)`) must pass `perf_metrics=bot.perf_metrics.summary()` as an additional kwarg.

---

### `PerfMetrics` rolling-aggregate helper (new — no existing file analog)

**Analog for placement:** All existing bot-wide singletons (like `YouTubeService`, `AudioService`) are instantiated in `bot.py` and attached to `self.`. Attach `PerfMetrics` the same way: `self.perf_metrics = PerfMetrics(config.PERF_ROLLING_WINDOW)`.

**Pattern source:** RESEARCH.md Pattern 7 (lines 474-508) is the canonical implementation using `collections.deque(maxlen=N)`. The class is small enough to live either in `services/audio.py` (where most timing is recorded) or as a standalone module — research recommends a singleton in `bot.py` or a new `services/metrics.py`. Copy the `PerfMetrics` class from RESEARCH.md verbatim.

---

### `tests/test_audio.py` — extend for LFU + timeout

**Analog — existing TestCacheCleanup class** (lines 74-97):
```python
class TestCacheCleanup:
    def test_cleanup_removes_oldest(self, audio_service, tmp_cache):
        for i in range(5):
            f = tmp_cache / f"vid{i}.opus"
            f.write_bytes(b"x" * (500 * 1024))
        ...
        audio_service.max_cache_mb = 1
        audio_service.cleanup_cache()
        remaining = list(tmp_cache.glob("*.opus"))
        total_size = sum(f.stat().st_size for f in remaining)
        assert total_size <= 1 * 1024 * 1024
```

**Phase 6 additions:** Rename existing `TestCacheCleanup` tests to `TestCacheCleanupLFU`. The new tests pass a mock `pool` and `protected_video_ids` set. Use `AsyncMock` for `pool.acquire().__aenter__` to return mock rows. Add `TestDownloadTimeout` class using `unittest.mock.patch("asyncio.wait_for", side_effect=asyncio.TimeoutError)` to verify stream fallback is invoked.

---

### `tests/test_youtube.py` — extend for DOWNLOAD_OPTS shape

**Analog — existing test fixture + mock pattern** (lines 1-32):
```python
@pytest.fixture
def yt_service():
    return YouTubeService()

class TestSearch:
    def test_search_returns_results(self, yt_service):
        with patch.object(yt_service, "_extract", return_value=MOCK_SEARCH_RESULT):
            results = yt_service.search("lofi")
            assert len(results) == 2
```

**Phase 6 additions:** Add `TestDownloadOpts` class that imports `DOWNLOAD_OPTS` from `services.youtube` and asserts the new postprocessor structure (SponsorBlock key present, `when='after_filter'`, FFmpegExtractAudio present, ModifyChapters present at correct position). Add `TestCodecLogging` class that mocks `YoutubeDL` and the `postprocessor_hooks` callback to verify `codec_path=copy` and `codec_path=transcode` are logged.

---

### `tests/test_phase6_perf.py` (new file)

**Analog — `tests/test_database_phase4.py` and `tests/test_queue.py`** for the structural pattern: pytest classes grouping related assertions, `@pytest.mark.asyncio` for async helpers, `AsyncMock`/`MagicMock` for pool.

**Structure to copy from `tests/test_queue.py`** (pure unit test pattern — no DB, clock-injectable):
```python
class TestNormalizeQuery:
    def test_strips_whitespace(self):
        ...
    def test_lowercases(self):
        ...

class TestPerfMetrics:
    def test_cache_hit_rate(self):
        m = PerfMetrics(window=10)
        m.record_cache_result(True)
        m.record_cache_result(False)
        assert m.summary()["cache_hit_rate"] == 50.0

class TestResolutionCache:
    @pytest.mark.asyncio
    async def test_hit(self):
        pool = AsyncMock()
        ...
```

---

## Shared Patterns

### asyncpg pool.acquire() + positional params
**Source:** `database.py` lines 186-210 (log_track_batch), lines 239-252 (update_artist_count)
**Apply to:** `get_resolution_cache`, `set_resolution_cache`, LFU play_count query in `cleanup_cache`
```python
async with pool.acquire() as conn:
    row = await conn.fetchrow(
        "SELECT ... FROM table WHERE col = $1 AND ...",
        param1,
    )
```
Never use string interpolation. All user-originated values flow through `$N` positional params.

### Fire-and-forget asyncio.create_task
**Source:** `cogs/music.py` lines 599-600, 653-654
**Apply to:** `_prefetch_next_track` trigger in `_play_track`
```python
asyncio.create_task(self._some_background_method(guild, arg))
# Never await; never let exceptions propagate to the event loop
```

### Generation-counter stale-callback guard
**Source:** `cogs/music.py` lines 559-571
**Apply to:** `_prefetch_next_track` — check `queue._play_generation == expected_gen` at both task-entry and after download completes.

### Structured timing log
**Source:** `services/youtube.py` lines 163-195 (download logs video_id, uses f-strings)
**Apply to:** All Phase 6 timing sites — use `time.monotonic()` delta, log `key=value` pairs for structured grep:
```python
t0 = time.monotonic()
...
elapsed = time.monotonic() - t0
log.info("download complete video_id=%s codec_path=%s elapsed=%.2fs", video_id, codec_path, elapsed)
```

### Error swallowing in background tasks
**Source:** `cogs/music.py` lines 659+ (`_post_auto_lyrics`)
**Apply to:** `_prefetch_next_track` — all exceptions caught and logged with `log.debug()`; never reraised.

---

## No Analog Found

All files in Phase 6 extend existing modules. No file requires patterns from outside the codebase.

The `PerfMetrics` class has no direct codebase analog (there is no existing rolling-aggregate class), but it has no structural complexity — implement it directly from RESEARCH.md Pattern 7 (`collections.deque(maxlen=N)`).

---

## Metadata

**Analog search scope:** `services/`, `cogs/`, `database.py`, `models/`, `config.py`, `utils/embeds.py`, `tests/`
**Files scanned:** 10 source files read directly
**Pattern extraction date:** 2026-06-24
