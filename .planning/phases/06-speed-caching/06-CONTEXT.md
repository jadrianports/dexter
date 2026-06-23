# Phase 6: Speed & Caching - Context

**Gathered:** 2026-06-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 6 makes Dexter's playback **noticeably faster with no inter-song gap**, and instruments
every pipeline stage so gains are measurable. It clarifies HOW to implement the seven PERF-*
requirements; it does not add new capabilities.

Delivered:
1. **Prefetch** the next track during current playback — no inter-song download gap (PERF-01)
2. **Native opus-copy at download** when the source is already opus — no opus→opus re-encode (PERF-02)
3. **Resolution cache** (query → `video_id`) so repeat queries skip the YouTube re-search (PERF-03)
4. **Real download timeout** honoring `DOWNLOAD_TIMEOUT_SECONDS`, falling back to stream (PERF-04)
5. **Play-frequency cache eviction** (LFU), not filesystem `atime` (PERF-05)
6. **Pipeline instrumentation** — search / download / transcode / time-to-first-audio / cache-hit rate (PERF-06)
7. **SponsorBlock** segment skipping on YouTube-video playback (PERF-07)

It does NOT add audio sources, change the queue model, or touch player UX (Phase 7, already complete).

</domain>

<decisions>
## Implementation Decisions

### Cache Codec Strategy — "middle-out" (PERF-02)
- **D-01:** **Copy-when-opus.** When YouTube's source stream is already opus (the common case),
  stream-copy the bytes at download time (`-c:a copy` / remux to `.opus` container) — zero re-encode,
  lossless, ~half the CPU, smaller files. **Transcode to opus ONLY when the source is not opus.**
- **D-02:** This guarantees **every cache file is opus**, so the existing playback passthrough
  (`FFmpegOpusAudio` with no opts, `services/audio.py` `get_source`) always holds. Do NOT store raw
  non-opus bestaudio (that would break passthrough → transcode-on-every-play). Do NOT keep the current
  blanket 192k re-encode (that is the lossy-on-lossy waste being removed).
- **D-03:** The download-time codec path (copy vs transcode) MUST be logged so PERF-02's success
  criterion ("logs confirm an opus-copy path rather than a transcode path") is verifiable.

### Prefetch (PERF-01)
- **D-04:** **Next-1, on track start.** The moment a track begins playing, background-download the
  **next** queue entry into cache. Minimal disk/bandwidth, kills the gap.
- **D-05:** **Pre-resolve may look 1 further ahead than pre-download** — cheap metadata extraction
  for the track after next, so a slow/failed download doesn't stall the swap.
- **D-06:** Prefetch runs the **full download pipeline** in the background — codec copy-when-opus (D-01)
  **and** SponsorBlock removal (D-13) happen during prefetch, so the cached file is play-ready and the
  swap is instant. Prefetch must not block or delay current playback (fire-and-forget task, like the
  existing `_post_auto_lyrics` pattern).

### Resolution Cache (PERF-03)
- **D-07:** **Postgres + TTL.** Persist `normalized-query → video_id` in Postgres with an expiry
  (default ~14 days, since videos get removed/blocked). Survives restart, shared across shards,
  cheap indexed lookup. New table via `SCHEMA_SQL` `CREATE TABLE IF NOT EXISTS` (asyncpg pattern).
- **D-08:** Chosen over in-memory specifically because the bot **restarts often** (on-demand local
  run, deploy parked) — an in-memory cache would be cold most sessions. (In-memory would satisfy the
  literal "within a session" criterion, but persistence is strictly better here for ~no cost.)
- **D-09:** Query normalization (casing/whitespace/trim) is the cache key. Exact normalization rules →
  research/planning. Direct-URL `/play` bypasses the resolution cache (no search to skip).

### Download Timeout (PERF-04)
- **D-10:** **Split budgets.** On-demand `/play` keeps the **10s** (`DOWNLOAD_TIMEOUT_SECONDS`) → stream
  fallback so a waiting user is never stuck. **Prefetch gets a generous budget (~45s)** — nobody is
  blocked and a completed prefetch means a gapless swap. (New config constant for the prefetch budget,
  e.g. `PREFETCH_TIMEOUT_SECONDS`.)
- **D-11:** On timeout, the on-demand path **falls back to the stream URL** and playback continues
  (existing 3-tier `get_source` already has the stream tier — wire the timeout in front of it).

### Cache Eviction (PERF-05)
- **D-12:** **LFU + protect in-use.** Evict tracks with the **lowest lifetime `play_count`** (sourced
  from `song_history`, which already records every play), tie-break **oldest** — but **NEVER evict a
  track that is currently playing, queued, or prefetched.** This prevents the self-defeating
  "evict the song I just prefetched" bug. Replaces the current `st_atime` sort in `cleanup_cache()`.
- **D-13** *(eviction signal detail)*: a freshly-downloaded track with `play_count` 0 is protected by
  the in-use guard while it sits in the queue, so low count alone never evicts an about-to-play track.

### SponsorBlock (PERF-07)
- **D-14:** **Download-time removal.** yt-dlp bakes a clean, segment-free file into the cache
  (categories: `sponsor`, `selfpromo`, `intro`, `outro`, `interaction`, `music_offtopic`). Playback
  stays pure passthrough. Only tracks that **actually contain** flagged segments get re-encoded, once.
- **D-15:** Segments are **silently skipped** — no user notification (matches the success criterion).
- **D-16** *(codec interaction)*: a track whose segments are cut **re-encodes at download even if the
  source was opus** (cutting precludes a pure stream-copy). This is acceptable — one-time, at download,
  background during prefetch. So the copy-fast-path (D-01) applies to opus tracks **with no segments to
  cut**; everything else transcodes once.

### Instrumentation Surfacing (PERF-06)
- **D-17:** **Structured per-event logs always** — search time, download time, transcode time,
  time-to-first-audio, and cache hit/miss for every relevant operation.
- **D-18:** **Rolling in-memory aggregate surfaced in the existing owner `/stats` embed** (Phase 8) —
  cache-hit %, avg time-to-first-audio, avg download time, as a new perf section. **No DB schema
  change** (no new `bot_daily_stats` columns) — in-memory rolling window is enough to be "observable."

### Goal-text correction (carry to verifier)
- **D-19:** The ROADMAP Phase-6 goal says instrument "against live Oracle numbers." **Oracle is dead** —
  Phase 5 re-targeted to Koyeb/Neon and the live deploy is PARKED; the bot runs **on the user's PC**
  (residential IP) on demand. Instrumentation baselines against the **actual run environment**, NOT
  Oracle. The verifier must not block Phase 6 on Oracle numbers that cannot exist.

### Claude's Discretion
Left to research/planning, consistent with the decisions above:
- Exact yt-dlp invocation for copy-when-opus (remux vs `--audio-format`/postprocessor args) and how to
  detect "source is already opus" reliably (D-01).
- Whether the Python-thread-orphan on a `wait_for` timeout (yt-dlp worker can't be killed) needs explicit
  cleanup, or if the executor thread draining harmlessly is acceptable (D-10 gotcha).
- Resolution-cache table/column names, indexes, normalization rules, and TTL value (D-07/D-09).
- The prefetch trigger plumbing inside `_play_track` / `_on_track_end` and the new prefetch task lifecycle.
- Rolling-aggregate window size and the exact `/stats` embed layout for the perf section (D-18).
- New config constants (prefetch timeout, resolution-cache TTL, SponsorBlock category list, prefetch depth).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` — Phase 6 entry: goal + the 5 success criteria. **Note the stale "live Oracle
  numbers" phrasing — superseded by D-19.** Also the Phase 7 **filter-vs-opus-copy design note** (opus-copy
  default, transcode only when filtered) which Phase 6's codec path must not break.
- `.planning/REQUIREMENTS.md` — **PERF-01 … PERF-07** (the 7 requirements this phase satisfies) + the
  locked Out-of-Scope list (`/volume`, non-YouTube sources).
- `CLAUDE.md` — build spec: cache management (2GB cap, eviction), `AUDIO_QUALITY`/`DOWNLOAD_TIMEOUT_SECONDS`,
  yt-dlp gotchas (`extract_flat` only for playlists; `webpage_url` not `url`), FFmpeg orphan cleanup,
  asyncpg `SCHEMA_SQL` pattern, the playback-engine patterns (generation counter, silent skip).

### Code Phase 6 modifies / builds on
- `services/audio.py` — `AudioService`: `get_source` (3-tier cache→download→stream + opus passthrough via
  `FFmpegOpusAudio`; `_build_ffmpeg_opts`), and **`cleanup_cache()` (currently `atime`-sorted — D-12 replaces
  this with LFU)**. The codec/copy and SponsorBlock decisions attach to the download path.
- `services/youtube.py` — `YouTubeService`: `DOWNLOAD_OPTS` (the `FFmpegExtractAudio → opus@192k`
  postprocessor that D-01 changes to copy-when-opus + D-14 adds SponsorBlock to), `download()`/`async_download()`
  (where D-10/D-11 timeout wires in), `search()`/`async_search()` (what the D-07 resolution cache fronts).
- `cogs/music.py` — playback engine: `_play_track` (~502), `_on_track_end` (~626), `after_callback`
  generation counter — the **prefetch trigger (D-04/D-06)** plumbs in here; `play()` (~1068) is where the
  resolution cache (D-07) intercepts a search.
- `models/queue.py` — `MusicQueue` (`current_index`, upcoming entries) — prefetch reads "next track" and
  eviction reads "queued tracks" (in-use protection, D-12) from here.
- `database.py` — `SCHEMA_SQL` + asyncpg helpers for the new resolution-cache table (D-07); `song_history`
  is the `play_count` source for LFU eviction (D-12).
- `config.py` — existing `AUDIO_QUALITY`, `AUDIO_CACHE_MAX_MB` (2GB), `DOWNLOAD_TIMEOUT_SECONDS` (10, unused —
  D-11 wires it). New constants land here (prefetch timeout, res-cache TTL, SponsorBlock categories, prefetch depth).
- `cogs/` `/stats` command (Phase 8, OPS-01) + `bot_daily_stats` — D-18 adds a perf section to the existing
  `/stats` embed; instrumentation aggregates feed it.
- `utils/logger.py` — structured logging target for D-17 per-event timing logs.

> **Staleness note:** `.planning/codebase/*.md` maps predate the Phase-4 SQLite→PostgreSQL migration.
> Treat `CLAUDE.md` + actual source as authoritative on persistence (asyncpg, not aiosqlite).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`AudioService.get_source` opus passthrough** already exists (`FFmpegOpusAudio` with no opts on cache
  hits) — PERF-02 at *playback* time is already won (Phase 7 D-12). Phase 6's PERF-02 work is at *download*
  time: stop re-encoding opus→opus.
- **`song_history` table** already records every play → the LFU `play_count` signal needs no new tracking.
- **`async_download` executor pattern** (`run_in_executor`) → prefetch and the timeout (`asyncio.wait_for`)
  layer on top of this directly.
- **`SCHEMA_SQL` + asyncpg helper pattern** (used for `guild_queues`, `user_favorites`, `user_playlists`) →
  the resolution-cache table follows it exactly.
- **Fire-and-forget `asyncio.create_task` pattern** (`_post_auto_lyrics`, `try_auto_queue`) → the model for
  the non-blocking prefetch task.
- **`/stats` owner embed** (Phase 8) already exists → the perf metrics section attaches there; no new command.

### Established Patterns
- All settings in `config.py`; new persistence via `SCHEMA_SQL` `CREATE TABLE IF NOT EXISTS` with async helpers.
- yt-dlp options are module-level dicts in `services/youtube.py` (`SEARCH_OPTS`, `DOWNLOAD_OPTS`, …).
- The generation counter (`queue._play_generation`) guards against stale after-callbacks — prefetch must not
  introduce a new stale-callback / double-play race (CLAUDE.md gotcha).

### Integration Points
- **Codec copy + SponsorBlock** → `DOWNLOAD_OPTS` / `download()` in `services/youtube.py`.
- **Download timeout** → `asyncio.wait_for` around `async_download`, in front of the stream tier in `get_source`.
- **Prefetch trigger** → `_play_track` / `_on_track_end` in `cogs/music.py`, reading "next" from `MusicQueue`.
- **Resolution cache** → intercept in `play()` (`cogs/music.py`) before calling `async_search`; persist in Postgres.
- **LFU eviction** → rewrite `cleanup_cache()` in `services/audio.py` to read `play_count` + protect in-use tracks.
- **Instrumentation** → timing logs via `utils/logger.py`; rolling aggregate surfaced in the `/stats` embed.

</code_context>

<specifics>
## Specific Ideas

- The user's framing: **"Pied Piper / Richard Hendricks middle-out, lossless"** — the codec decision (D-01)
  is explicitly motivated by killing the wasteful opus→opus re-encode and preserving source quality at
  smaller size. Copy-when-opus is the literal "lossless" path; transcode is the fallback only for non-opus.
- The user's framing: **"there's gotta be some algorithm"** for the search→download→playback feedback loop —
  answered by prefetch (D-04) + resolution cache (D-07) + the instrumentation that proves the gains (D-17/18).
- Prefetch, codec-copy, and SponsorBlock are **deliberately coupled**: prefetch runs the whole pipeline so the
  cached file is fully play-ready (D-06). Plan them as one pipeline, not three isolated features.

</specifics>

<deferred>
## Deferred Ideas

Considered during discussion, intentionally out of this phase:
- **LFU-with-recency-aging** eviction (chose pure LFU + in-use protection; aging is more tuning than warranted now).
- **Persisting perf metrics to `bot_daily_stats`** for day-over-day historical trends (chose rolling in-memory
  + `/stats`; revisit if long-term perf trending becomes valuable).
- **Runtime SponsorBlock seek-skipping** (chose download-time removal; runtime skip breaks passthrough at cut points).
- **Deeper prefetch (next-3 buffer)** (chose next-1 + 1-ahead pre-resolve; revisit if slow downloads still gap).

None of these are roadmap items — capture for a future milestone if desired.

</deferred>

---

*Phase: 6-Speed & Caching*
*Context gathered: 2026-06-24*
