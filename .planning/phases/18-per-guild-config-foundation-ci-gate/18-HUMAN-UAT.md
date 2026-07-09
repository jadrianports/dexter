---
status: partial
phase: 18-per-guild-config-foundation-ci-gate
source: [18-VERIFICATION.md]
started: 2026-07-10
updated: 2026-07-10
---

## Current Test

[awaiting human testing]

## Tests

### 1. First real GitHub Actions run (CICD-01)
expected: Push the branch and confirm the `CI` check appears, runs `ruff check` + `ruff format --check` + `pytest` against the pgvector service container, that the previously-skipped live-DB tests actually RUN (not skip), and that a deliberately-broken commit turns the check red.
why_human: A workflow YAML's correctness is only observable from GitHub's runner. Nothing has been pushed yet.
watch_for: The first `pip install` may fail on `davey`/`PyNaCl` native builds (RESEARCH Pitfall 7). If so, add `apt-get install -y build-essential libsodium-dev` before the install step.
result: [pending]

### 2. Home guild behaves identically after the refactor (CONFIG-05 / SC-2)
expected: Boot against the real Discord token and the real home guild (`config.DEXTER_CHANNEL_ID`); the startup message posts to the same channel as before, and a voice-join roast still fires there.
why_human: Requires a live Discord connection; the 24/7 host is parked behind the YouTube datacenter-IP block.
result: [pending]

### 3. A fresh second guild stays completely ambient-silent (CONFIG-04 / SC-1)
expected: Invite Dexter to a second guild with no `guild_config` row. `/play` works immediately. Join voice, post an image, chat in any channel → zero unprompted output, clean `dexter.log`.
why_human: Requires inviting the bot to a second live guild — not observable from unit/mock tests alone.
result: [pending]

### 4. Stale/unwritable channel → silent skip, row intact (D-03)
expected: Revoke `send_messages` on the configured ambient channel in a live guild; trigger a voice-join roast. No message posts, exactly one WARNING lands in `dexter.log`, and the `guild_config` row's `configured` column is still `true`.
why_human: Requires manipulating real Discord channel permissions live. The unit test `test_resolve_ambient_channel_no_send_perms_returns_none_row_intact` proves the code path but not the live Discord permission-check integration.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
