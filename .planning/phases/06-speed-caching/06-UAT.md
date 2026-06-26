---
status: complete
phase: 06-speed-caching
source: [06-01-SUMMARY.md, 06-02-SUMMARY.md, 06-03-SUMMARY.md, 06-04-SUMMARY.md]
started: 2026-06-24T00:00:00Z
updated: 2026-06-26T08:05:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Stop the bot, start it fresh. Boots without errors, connects to Neon, resolution_cache table created on schema init, cache-cleanup task starts without crashing on the new async signature, bot comes online and commands respond.
result: pass
note: "Initially FAILED with a blocker (SSL-vs-local-Postgres config mismatch — see Gaps). Fixed in-session by removing the Oracle-era colocated Postgres from docker-compose.yml so the bot connects to Neon directly. Re-verified: clean boot — 'Database schema initialized', 'Cache cleanup check completed (protected=0)', 'Dexter is ready.', queue smart-rejoin + playback resumed."

### 2. No inter-song gap (prefetch, PERF-01)
expected: Play a song, let it start, then queue a second song. When the first ends, the second begins immediately — no audible pause for download between tracks.
result: pass
note: "User confirmed no audible pause for downloading between tracks. (Separately requested a Now Playing UX change — repost embed at bottom of chat on song change — captured as a new enhancement, not a Phase 6 gap.)"

### 3. Resolution cache hit on repeat search (PERF-03)
expected: Run the same non-URL search twice in one session (e.g. `/play lo-fi beats`, let it resolve, then `/play lo-fi beats` again). The second `/play` skips the YouTube search select menu and queues immediately; `/stats` shows a non-zero / elevated cache-hit-rate.
result: pass

### 4. Direct-URL play bypasses the cache (PERF-03 / D-09)
expected: `/play https://www.youtube.com/watch?v=dQw4w9WgXcQ` plays normally but does NOT count as a cache hit/miss — the `/stats` cache-hit-rate is unaffected by URL plays (URL branch bypasses the resolution cache).
result: pass

### 5. Download timeout → stream fallback (PERF-04)
expected: A download that exceeds `DOWNLOAD_TIMEOUT_SECONDS` (10s) falls back to the stream URL instead of hanging; playback still starts and continues. (Hard to force on demand — skip if you can't trigger a slow download.)
result: skipped
reason: "Hard to force a slow download on demand — user couldn't trigger the timeout path."

### 6. LFU cache eviction + SponsorBlock (PERF-05 / PERF-07)
expected: With the cache over `AUDIO_CACHE_MAX_MB` (512MB), the hourly cleanup deletes least-PLAYED tracks first (lowest play_count, not oldest) and never deletes the currently-playing/prefetched track — visible in the eviction log lines. SponsorBlock segments (intros/sponsors) are silently skipped during YouTube video playback. (Needs a full cache to observe eviction — skip the eviction half if not reproducible.)
result: skipped
reason: "Needs a 512MB+ full cache (eviction) and a sponsor-segment video to observe — not reproducible on demand this session."

### 7. /stats shows real perf metrics (PERF-06)
expected: After playing 3–5 songs, `/stats` (owner-only) shows `cache hit rate`, `avg time-to-first-audio`, and `avg download` fields with non-zero values (not a fabricated 0.0s).
result: pass

## Summary

total: 7
passed: 5
issues: 0
pending: 0
skipped: 2
blocked: 0
notes: 1 blocker found and fixed in-session (Test 1 — see Gaps, status resolved). 1 enhancement request captured (Now Playing repost-on-song-change — see Enhancements).

## Gaps

- truth: "Bot cold-starts cleanly, connects to its database, registers slash commands, and /play works."
  status: resolved
  resolution: "docker-compose.yml rewritten to drop the colocated postgres:16-alpine service + DATABASE_URL override (Oracle-era legacy). Bot now inherits the Neon DSN from .env via env_file, matching bot.py's ssl='require'. Re-verified clean boot + playback in-session 2026-06-26."

## Enhancements (net-new, not Phase 6 gaps)

- request: "Now Playing embed (Pause/Skip/Shuffle/Stop controls) should move to the BOTTOM of the channel on song change — i.e. when the next queued song starts, re-post the Now Playing message as the most recent chat message instead of editing the old one in place up in scroll history."
  raised_by_test: 2
  area: player-ux (relates to Phase 7)
  status: implemented
  implementation: "cogs/music.py _refresh_now_playing() now deletes the previous now-playing message and sends a fresh one at the bottom on song change (natural advance + skip), keeping exactly one live player at the bottom of the chat. In-song toggles (pause/resume/loop/shuffle) still edit in place via NowPlayingView and do not move the message. Updated tests/test_now_playing_refresh.py (6 passed). Container rebuilt + restarted."
  reason: "User reported: /play returned the bot's generic error and didn't work. Logs show on_ready init crashed: asyncpg pool creation against postgres:5432 raised 'ConnectionError: PostgreSQL server rejected SSL upgrade'. Init never completed so the command tree never synced ('Application command play not found')."
  severity: blocker
  test: 1
  root_cause: "Config-architecture mismatch. bot.py:302 hardcodes ssl='require' on asyncpg.create_pool (K-05, intended for Neon which mandates SSL). But docker-compose.yml overrides DATABASE_URL (line 37) to the colocated postgres:16-alpine container (postgres:5432), which has no SSL. Connection requires SSL, local Postgres refuses it, pool creation raises, _initialize_once() aborts before init_db/cog-sync. The colocated-postgres override is legacy from the parked Oracle deploy; the project's go-forward DB is Neon Singapore (already correct in .env)."
  artifacts:
    - path: "docker-compose.yml"
      issue: "bot service overrides DATABASE_URL to local postgres:5432 (line 37) + spins up colocated postgres service (lines 9-24); both are Oracle-era legacy, conflict with Neon + ssl='require'."
    - path: "bot.py"
      issue: "Line 302 ssl='require' is unconditional; breaks any non-SSL Postgres (the local container)."
  missing:
    - "Point the bot at Neon for runtime (drop the compose DATABASE_URL override so it inherits .env's Neon DSN), OR make ssl conditional on the DSN so local Postgres works without SSL."
  debug_session: ""
