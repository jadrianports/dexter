---
status: partial
phase: 19-onboarding-admin-setup
source: [19-VERIFICATION.md]
started: 2026-07-10T00:00:00Z
updated: 2026-07-10T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Native channel dropdown rendering
expected: In a second test guild, `/setup channel` renders a searchable channel dropdown (native picker), not a free-text field.
result: [pending]

### 2. Non-admin ephemeral refusal
expected: With a real second Discord account lacking `manage_guild`, `/setup channel`, `/setup roasts`, and `/setup vision` all refuse ephemerally before any state change.
result: [pending]

### 3. Live join welcome + ambient activation
expected: Inviting Dexter to a fresh guild while running posts the welcome once (naming `/setup channel`); guild stays silent until configured; ambient roasts fire only after `/setup channel`; vision roasts only after `/setup vision on` (D-19).
result: [pending]

### 4. Boot backfill welcomes exactly once
expected: Invite Dexter with the bot stopped, then start — welcome posts. Restart — welcome does NOT post again. Exactly one welcome across both boots.
result: [pending]

### 5. Owner join/remove notices
expected: Join then kick Dexter from a test guild — both embeds arrive in `ERROR_LOG_CHANNEL_ID`, guild id is copy-pasteable text, join embed reports whether the welcome posted.
result: [pending]

### 6. Home-guild regression (D-20 / CONFIG-05)
expected: In the home guild, an image still triggers vision roasts at the pre-Phase-19 cadence; `/setup vision` reports `on` without anyone enabling it. Byte-identical pre/post-Phase-19 home-guild behavior.
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
