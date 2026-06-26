---
status: partial
phase: 09-reliability-ops-hardening
source: [09-VERIFICATION.md]
started: 2026-06-27
updated: 2026-06-27
---

## Current Test

[awaiting human testing — requires a live bot with Discord + Neon connected]

## Tests

### 1. /health truthful HTTP 503 end-to-end
expected: Boot bot with MusicCog forced to fail (or DB unreachable); `curl -s -o /dev/null -w '%{http_code}' localhost:<port>/health` returns 503 with degraded JSON body. Set `HEALTH_STRICT_STATUS=false` and confirm 200.
result: [pending]

### 2. Crashing fire-and-forget task surfaces in logs + Discord error channel
expected: Force `_prefetch_next_track`/`_post_auto_lyrics` to raise; one `log.error` per occurrence in dexter.log; one throttled/deduped embed in `ERROR_LOG_CHANNEL_ID` (no flood within 300s cooldown).
result: [pending]

### 3. Startup sync failure: bot comes online, retries in background
expected: Inject slow/failing `bot.tree.sync`; bot reaches ready, warning logged, already-registered slash commands still work, single background retry chain fires.
result: [pending]

### 4. on_ready watchdog fires on hung _initialize_once
expected: Inject a hang into `_initialize_once`; `asyncio.wait_for` watchdog fires after `INIT_WATCHDOG_TIMEOUT_SECONDS=120`; pool cleaned up; `_ready_initializing` resets; next READY retries.
result: [pending]

### 5. Slow DB query hits timeout and shows personality message
expected: Run `/leaderboard`/`/stats` against slow Neon (scale-to-zero wake); user sees "database is being slow…" / "stats are taking too long…"; bot stays responsive.
result: [pending]

### 6. YouTube transient self-heal vs permanent failure
expected: Transient search/extract failure recovers via bounded quick retry (no update on first failures); `ExtractorError(expected=True)` propagates immediately with no retry/update.
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
