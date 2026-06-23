# Phase 6: Speed & Caching - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-24
**Phase:** 6-Speed & Caching
**Areas discussed:** Cache codec strategy, Prefetch, Resolution cache, SponsorBlock, Download timeout, Eviction, Instrumentation surfacing

---

## Cache Codec Strategy (PERF-02)

| Option | Description | Selected |
|--------|-------------|----------|
| Copy-when-opus | Stream-copy bytes when source is already opus; transcode only non-opus. Lossless, ~½ CPU, smaller files, keeps playback passthrough valid. | ✓ |
| Always copy raw bestaudio | Never re-encode; keep whatever YT gives. Breaks `FFmpegOpusAudio` passthrough for non-opus → transcode every play. | |
| Keep 192k re-encode | Current behavior; uniform files but lossy-on-lossy waste of CPU + quality. | |

**User's choice:** Copy-when-opus
**Notes:** Explicitly framed as the "Pied Piper / Richard Hendricks middle-out, lossless" goal — kill the wasteful opus→opus re-encode.

---

## Prefetch (PERF-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Next-1, on track start | Background-download the next track the moment the current starts. Minimal disk/bandwidth, kills the gap. | ✓ |
| Next-3, on track start | Buffer next 3; more resilient to slow downloads but 3× disk/bandwidth + waste on heavy-skip. | |
| Next-1, at 50% played | Lazier; less waste but risky on short tracks. | |

**User's choice:** Next-1, on track start
**Notes:** Pre-resolve may look 1 further ahead than pre-download so a slow download doesn't stall the swap.

---

## Resolution Cache (PERF-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Postgres + TTL | Persist query→video_id in Postgres w/ expiry (~14d). Survives restart, shared across shards. | ✓ |
| In-memory dict, TTL | Fast, no DB write, but cold on every restart + per-shard. | |
| In-memory, session-only | Bare minimum to meet the success criterion. | |

**User's choice:** Postgres + TTL
**Notes:** Chosen because the bot restarts often (on-demand local run, deploy parked) — in-memory would be cold most sessions.

---

## SponsorBlock (PERF-07)

| Option | Description | Selected |
|--------|-------------|----------|
| Download-time removal | yt-dlp bakes a clean file into cache (sponsor/selfpromo/intro/outro/interaction/music_offtopic). Playback stays passthrough; only segmented tracks re-encode, once. Silent. | ✓ |
| Runtime seek-skip | Store timestamps, skip live; keeps full-length cache but breaks passthrough at cut points. | |
| Sponsor-only, download-time | Cut only 'sponsor', leave intros/outros. | |

**User's choice:** Download-time removal
**Notes:** Couples with the codec decision — a cut track re-encodes even if opus (acceptable, one-time, during background prefetch).

---

## Download Timeout (PERF-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Split budgets | On-demand 10s→stream (user waiting); prefetch ~45s (nobody blocked, finished = gapless). | ✓ |
| Single 10s both | Uniform/simplest; prefetch that can't finish in 10s streams at play time. | |
| 10s fg, no bg limit | On-demand bounded; prefetch always runs to completion. | |

**User's choice:** Split budgets
**Notes:** Research gotcha flagged — Python can't truly kill the yt-dlp worker thread on `wait_for`; cleanup needs verifying.

---

## Cache Eviction (PERF-05)

| Option | Description | Selected |
|--------|-------------|----------|
| LFU + protect in-use | Evict lowest lifetime `play_count` (from `song_history`), tie-break oldest, never evict playing/queued/prefetched. | ✓ |
| LFU + recency aging | Blend play_count with recency; more nuanced, more tuning. | |
| Pure LFU | Lowest count wins, no protection; can evict a freshly-prefetched track. | |

**User's choice:** LFU + protect in-use
**Notes:** Prevents the self-defeating "evict the song I just prefetched" bug. Replaces current `atime` sort.

---

## Instrumentation Surfacing (PERF-06)

| Option | Description | Selected |
|--------|-------------|----------|
| Logs + /stats rolling | Per-event logs always; rolling in-memory aggregate (cache-hit %, avg TTFA, avg download) in the existing owner `/stats` embed. No schema change. | ✓ |
| Logs + bot_daily_stats | Also persist perf to DB for day-over-day trends. Heavier. | |
| Logs only | No /stats surfacing. | |

**User's choice:** Logs + /stats rolling
**Notes:** Reuses the Phase-8 `/stats` embed; "observable" satisfied without DB schema change.

---

## Claude's Discretion

- yt-dlp invocation for copy-when-opus (remux vs postprocessor args) + reliable "source is opus" detection.
- Whether the orphaned yt-dlp worker thread on a `wait_for` timeout needs explicit cleanup.
- Resolution-cache table/column names, indexes, normalization rules, TTL value.
- Prefetch task plumbing/lifecycle inside `_play_track` / `_on_track_end`; avoiding a stale-callback/double-play race.
- Rolling-aggregate window size and `/stats` perf-section layout.
- New config constants (prefetch timeout, res-cache TTL, SponsorBlock categories, prefetch depth).

## Deferred Ideas

- LFU-with-recency-aging eviction.
- Persisting perf metrics to `bot_daily_stats` for historical trends.
- Runtime SponsorBlock seek-skipping.
- Deeper prefetch (next-3 buffer).

## Note carried to verifier

- ROADMAP Phase-6 goal text says "live Oracle numbers" — Oracle is dead (Phase 5 → Koyeb/Neon, deploy parked,
  runs on user PC). Instrumentation baselines against the actual run environment, not Oracle (CONTEXT D-19).
