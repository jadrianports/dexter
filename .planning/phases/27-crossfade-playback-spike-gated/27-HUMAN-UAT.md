---
status: partial
phase: 27-crossfade-playback-spike-gated
source: [27-VERIFICATION.md]
started: 2026-07-17
updated: 2026-07-17
---

## Current Test

[awaiting human testing]

## Tests

### 1. Re-listen to the shipped crossfade render and judge blend smoothness (SC-2, D-08/D-10)
expected: Two songs overlap and swap over ~4s with no loudness dip and no phasing/underwater artifact; user decides the plain-vs-suppressed variant is acceptable.
result: [pending]

### 2. Confirm /skip mid-crossfade in a real Discord voice channel does not glitch, double-play, or wedge the bot
expected: Skip cuts the fade cleanly, next track starts normally, no audible artifacts beyond what the spike's harness already proved structurally.
result: [pending]

### 3. D-17.5 — confirm Discord's real decoder tolerates the suppressed send_silence end-of-transmission marker without artifacting
expected: No audible glitch or decoder confusion at the fade boundary when the 100ms silence marker is withheld.
result: [pending]

### 4. Confirm /crossfade on|off in a live guild toggles behavior audibly and the copy pool tone lands
expected: Toggle takes effect on the next transition; reply copy reads naturally, no mention pings.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
