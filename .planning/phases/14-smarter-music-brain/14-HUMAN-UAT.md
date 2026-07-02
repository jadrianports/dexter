---
status: partial
phase: 14-smarter-music-brain
source: [14-VERIFICATION.md]
started: 2026-07-03
updated: 2026-07-03
---

## Current Test

[awaiting human testing — parked behind live Discord + populated Neon host]

## Tests

### 1. BRAIN-01 — auto-queue skip avoidance
expected: Over a real session, auto-queue visibly stops re-suggesting an artist the user just skipped (negative hint + hard post-filter working end-to-end).
result: [pending]

### 2. BRAIN-02 — discovery relevance + timezone bucketing
expected: `/discover` returns genuinely adjacent artists from real listening history; `date_trunc('day', queued_at AT TIME ZONE STREAK_TIMEZONE)` groups cross-midnight co-plays on the correct calendar day (only exercised by live-DB integration tests).
result: [pending]

### 3. BRAIN-02 — discovery playback from idle bot (CR-01 fix)
expected: Pressing `/discover` "queue it" while the bot is NOT already in voice actually joins the presser's voice channel and plays the track — no false "queued" success. Track also survives a restart (persistence).
result: [pending]

### 4. BRAIN-03 — jam suggestion quality
expected: `/jam suggest <name>` produces plausible additions to a real server jam; every suggestion offered has passed YouTube token-set validation before it can be confirmed into the snapshot.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 4

## Gaps

None (code-complete). All four items are blocked on an always-on residential Discord host +
populated Neon DB — the milestone's standing parked live-runtime UAT tail. No code defects
outstanding; the CR-01 blocker and WR-01/02/03 warnings from 14-REVIEW.md were fixed this phase.
