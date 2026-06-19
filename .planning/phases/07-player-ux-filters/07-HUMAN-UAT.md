---
status: partial
phase: 07-player-ux-filters
source: [07-VERIFICATION.md]
started: 2026-06-19T00:00:00Z
updated: 2026-06-19T00:00:00Z
---

# Phase 7: Player UX & Filters — Human UAT

All automated checks passed (13/13 must-haves verified by code inspection). The
items below require a **running bot on a live Discord gateway + live Neon Postgres**
to confirm behavior, matching the v1.1 "Live & Lethal" live-UAT pattern. Run them
once the phase is deployed, then update each `result:` and re-run verification.

## Current Test

[awaiting human testing]

## Tests

### 1. NowPlayingView 5-button controller
expected: Boot the bot, `/play` a song; the now-playing embed shows 5 buttons (Pause, Skip, Loop, Shuffle, Stop). Each button responds without "interaction failed"; embed re-renders in place. Pause toggles to Resume and back; Skip advances; Loop cycles Off→Single→Queue→Off with label update; Shuffle reorders upcoming tracks; Stop clears queue and disconnects.
result: [pending]

### 2. Persistent view survives restart
expected: With a pre-restart now-playing message, restart the bot and press a button on the old message — it still responds (persistent view registered in `setup_hook` survived restart).
result: [pending]

### 3. Non-VC user button refusal
expected: Press a now-playing button while NOT in the bot's voice channel — ephemeral NOT_IN_VOICE refusal; no state change.
result: [pending]

### 4. /seek audio jump + edge cases
expected: `/play` a 3-min song. `/seek 1:30` jumps playback to ~1:30. `/seek 9:99` (invalid) → ephemeral personality error. `/seek` past the track duration → skips to the next track.
result: [pending]

### 5. /previous and /jump navigation
expected: Queue 3+ songs. `/previous` restarts the prior track. `/jump 3` starts the third track. `/jump 99` → ephemeral range error. (No-pop index model; bounds enforced.)
result: [pending]

### 6. /filter audio effect + stickiness
expected: `/filter bassboost` mid-song → bass-boosted audio audible from current position. Queue another song → next track also bass-boosted (sticky). `/filter off` → subsequent tracks return to opus passthrough.
result: [pending]

### 7. active_filter persistence across restart
expected: Restart the bot while a filter is active. `/queue` or `/nowplaying` shows the restored `active_filter` (guild_queues payload round-trip via live Postgres).
result: [pending]

### 8. /favorite cap + dedupe
expected: `/play` a song, `/favorite` → ephemeral "saved". `/favorite` same song again → "already saved" (dedupe). Save 25 songs → 26th attempt shows FAVORITE_CAP_HIT.
result: [pending]

### 9. /favorites pick-list end-to-end
expected: `/favorites` with no saves → ephemeral "empty". With saves → pick-list appears. Select a song + Queue → added to queue and starts if idle. Select a song + Remove → disappears from the list. (Queue/Remove act on the selected entry only.)
result: [pending]

### 10. Favorites are global (cross-server, D-18)
expected: Save a favorite in server A; open `/favorites` in server B → it appears (keyed on user_id, not guild_id).
result: [pending]

### 11. /playlist save + load round-trip
expected: Queue 3 songs. `/playlist save chill`. Clear queue. `/playlist load chill` → all 3 songs appended and playback starts when idle.
result: [pending]

### 12. /playlist upsert + list + delete
expected: `/playlist save chill` again (overwrite) → count stays at 1 (upsert, not a second entry). `/playlist list` → "chill" appears. `/playlist delete chill` → removed. `/playlist load ghostname` → ephemeral PLAYLIST_NOT_FOUND.
result: [pending]

### 13. /playlist load truncation at queue cap
expected: Load a playlist into a near-full queue (close to the 500-track cap) → truncation count is reported in the PLAYLIST_LOADED response (QueueFullError caught).
result: [pending]

## Summary

total: 13
passed: 0
issues: 0
pending: 13
skipped: 0
blocked: 0

## Gaps
