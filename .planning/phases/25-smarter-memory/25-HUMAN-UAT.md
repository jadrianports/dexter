---
status: partial
phase: 25-smarter-memory
source: [25-VERIFICATION.md]
started: 2026-07-16
updated: 2026-07-16
---

## Current Test

[awaiting human testing]

## Tests

### 1. SC-1 durability "feel" over real Discord traffic

expected: A memory that keeps getting surfaced across real usage (via `/ask`, `/roast`, ambient
roasts, proactive callbacks, or the auto-queue taste blend) stays available noticeably longer than
an equally-old memory that is never recalled again. The daily decay sweep does not silently remove
something Dex just referenced days earlier; a genuinely useful recurring fact should still be
recallable weeks later while forgettable one-offs age out on schedule.

why_human: Requires a live bot process, real Gemini recall traffic, and the real 24-hour sweep
cadence accumulated over multiple days — an isolated pytest run (however faithful) cannot reproduce
that. Parked behind the same residential-host live-Discord UAT tail as every prior memory phase
(11, 13, 15, 16, 17), per established project precedent. Not a code gap.

result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
