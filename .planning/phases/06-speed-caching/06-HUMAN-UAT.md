---
status: partial
phase: 06-speed-caching
source: [06-VERIFICATION.md]
started: 2026-06-24T00:00:00Z
updated: 2026-06-24T00:00:00Z
---

## Current Test

[awaiting human testing — requires a live bot session: Discord voice + real YouTube + Postgres]

## Tests

### 1. No inter-song gap (PERF-01, prefetch)
expected: Play a song, let it start, then queue a second song. The second track begins immediately after the first ends — no audible pause for download.
result: [pending]

### 2. Resolution cache hit on repeat search (PERF-03)
expected: Run the same non-URL query twice in one session (e.g. `/play lo-fi beats`, let it resolve, then `/play lo-fi beats` again). The second `/play` skips the YouTube search select menu and queues immediately; `/stats` shows an elevated cache-hit-rate.
result: [pending]

### 3. Direct-URL play bypasses the cache (PERF-03 / D-09)
expected: `/play https://www.youtube.com/watch?v=dQw4w9WgXcQ` does NOT write a `resolution_cache` row; the cache-hit-rate in `/stats` does not change.
result: [pending]

### 4. Download timeout → stream fallback (PERF-04)
expected: A download exceeding `DOWNLOAD_TIMEOUT_SECONDS` (10s) falls back to the stream URL instead of hanging; playback continues.
result: [pending]

### 5. LFU cache eviction at 512MB (PERF-05)
expected: With the cache over `AUDIO_CACHE_MAX_MB` (512MB), the hourly cleanup deletes least-played tracks first (lowest `song_history` play_count, not oldest atime); currently-playing and prefetched tracks are never deleted. SponsorBlock segments are silently skipped during YouTube video playback (PERF-07).
result: [pending]

### 6. /stats shows real perf metrics (PERF-06)
expected: After playing 3–5 songs, `/stats` (owner-only) shows `cache hit rate`, `avg time-to-first-audio`, and `avg download` fields with non-zero values.
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
