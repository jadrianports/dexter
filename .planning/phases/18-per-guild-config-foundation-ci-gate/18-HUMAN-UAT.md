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
result: PASSED (2026-07-09, executed during phase close)
  - Run 1 (29055644537) — RED: 8 failed / 980 passed / 0 skipped. Proves the gate blocks.
  - Run 2 (29056570511) — GREEN: 1017 passed / 0 skipped / 0 failed, after both root causes fixed.
  - Live-DB tests RUN, not skip: 0 skips on the runner (local 906 passed + 111 skipped = 1017). The
    BL-01 presence-check fix is validated end-to-end against a real `pgvector/pgvector:pg16` container.
  - Pitfall 7 did NOT bite: `pip install` of `davey`/`PyNaCl` succeeded on `ubuntu-latest` with no
    `apt-get` build-deps step. No preemptive step needed.
  - The "turns red" half was demonstrated by Run 1 failing on genuine defects rather than a
    deliberately-broken commit; the gate blocked as designed.
  - Two latent bugs found by the gate on its first run, both pre-existing (NOT Phase 18 regressions),
    both fixed in `be0da7d` / `e99a678` and locked by `tests/test_fresh_boot_regressions.py` (`e935bd5`):
      1. `bot.py` called `sys.exit(1)` at import time when `DISCORD_TOKEN` was unset (CI holds zero
         secrets), killing any test that did `import bot`.
      2. A `0.0` "never happened" sentinel was compared against boot-relative monotonic clocks. On a
         host with uptime below the window this reads as "just now" — so after a reboot Dexter would
         refuse to vision-roast for 10 min and refuse to self-heal yt-dlp for 1 hour. A real
         production bug, invisible on a long-uptime host.

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
passed: 1
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps

Items 2-4 remain pending: all three require a live Discord connection, which is blocked on the
parked 24/7 residential host (YouTube datacenter-IP block). Same acknowledged-deferred posture as
Phases 11/13/14/15/16/17. Item 1 is closed — CI is green on `main`.
