---
status: partial
phase: 16-proactive-memory-callbacks
source: [16-VERIFICATION.md]
started: 2026-07-03T12:00:00Z
updated: 2026-07-03T12:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. A live proactive callback fires at a real active moment and reads as a dry aside, not surveillance
expected: Posting repeatedly in the designated channel over time eventually produces one reply-anchored, mention-suppressed callback that references a real remembered detail in Dexter's voice. Recall now anchors on the triggering message content (WR-03 fix), so the surfaced memory should feel relevant to what was just said — never "the bot is watching me."
result: [pending]

### 2. /memory callbacks off visibly silences the surface in Discord while /memory view still shows intact memories
expected: Ephemeral in-character confirmation on toggle; after opting out no further proactive callbacks fire for that user; `/memory view` still shows the user's memories unchanged (opt-out touches zero user_memories rows).
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
