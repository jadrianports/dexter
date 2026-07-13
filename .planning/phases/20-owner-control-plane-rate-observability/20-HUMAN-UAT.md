---
status: partial
phase: 20-owner-control-plane-rate-observability
source: [20-VERIFICATION.md]
started: 2026-07-14T00:00:00Z
updated: 2026-07-14T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. /guilds list fleet view rendering
expected: /guilds list renders one row per guild (name, `guild_id`, member count, status flags, session AI calls), sorted usage-descending, paginated, ephemeral. Fleet view is readable, highest-usage guild first, no data silently truncated across pages.
result: [pending]

### 2. Non-owner refusal in silenced/blocked guild
expected: A non-owner running any slash command in a guild the owner has silenced or blocked sees the in-persona ephemeral refusal line, never Discord's generic "application did not respond" failure state.
result: [pending]

### 3. /guilds block force-leave + re-invite refusal round trip
expected: /guilds block on a guild Dexter is in causes an immediate force-leave (queue/voice teardown observed); a subsequent owner re-invite triggers an immediate silent leave via on_guild_join with no welcome message.
result: [pending]

### 4. /guilds silence mid-flight (SC-2 timing race)
expected: /guilds silence on a guild with active ambient chatter goes silent on the very next event; a Gemini round-trip already in flight when silence is issued does not produce a stale reply.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
