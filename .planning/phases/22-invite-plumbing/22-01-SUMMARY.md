---
phase: 22-invite-plumbing
plan: 01
subsystem: infra
tags: [discord.py, oauth2, config, pure-logic-seam, tdd]

requires:
  - phase: 10-critical-path-test-coverage
    provides: "pure logic/ seam convention (mock-free, keyword-only, config-defaulted)"
provides:
  - "config.DISCORD_CLIENT_ID / INVITE_PERMISSIONS_VALUE / INVITE_SCOPES constants"
  - "logic/invite.py::build_invite_url() — the single invite-URL constructor in the codebase"
  - "tests/test_invite_logic.py — bitfield derivation lock + D-02 negative-assertion security lock"
affects: [22-02-invite-plumbing, 22-03-invite-plumbing, 23-portfolio-surface-ci-cd]

tech-stack:
  added: []
  patterns:
    - "logic/ pure-seam convention extended with one documented discord-import exception (logic/invite.py)"

key-files:
  created:
    - logic/invite.py
    - tests/test_invite_logic.py
  modified:
    - config.py
    - logic/__init__.py

key-decisions:
  - "D-09 amendment applied: ten-permission bitfield (309240908864), not the superseded eight-permission value (3263552)"
  - "D-04: DISCORD_CLIENT_ID is a committed public constant with env override — resolves in zero-secret CI"
  - "D-03/D-07: build_invite_url() wraps discord.utils.oauth_url(); no hand-built query string, no integration_type param"
  - "logic/invite.py explicitly documents its deviation from the logic/ no-discord-import convention (offline/deterministic exception)"

requirements-completed: [INVITE-01]

duration: 12min
completed: 2026-07-14
---

# Phase 22 Plan 01: Invite Config + Pure URL Builder Summary

**Ten-permission least-privilege OAuth2 bitfield (309240908864) locked by a CI-enforced negative assertion, plus the single pure `build_invite_url()` function every future invite surface must call.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 2 completed
- **Files modified:** 4 (config.py, logic/invite.py, logic/__init__.py, tests/test_invite_logic.py)

## Accomplishments

- `config.py` gained three new constants: `DISCORD_CLIENT_ID` (public-by-design, env-overridable), `INVITE_PERMISSIONS_VALUE = 309240908864` (the ten-permission least-privilege bitfield per D-01 as amended by D-09), and `INVITE_SCOPES = ("bot", "applications.commands")`.
- `logic/invite.py::build_invite_url()` — the single, pure, keyword-only URL constructor wrapping `discord.utils.oauth_url()`. Verified byte-for-byte against the interface contract's canonical output.
- `tests/test_invite_logic.py` — 10 mock-free tests: bitfield derivation (proves 309240908864 comes from ten named `discord.Permissions` flags, not a bare magic number), the D-02 negative-assertion security lock (no administrator/manage_guild/manage_roles/manage_channels/ban_members/kick_members), the inverse positive-grant lock (no silent capability loss), client-id/scopes shape checks, and URL/scope/determinism checks for `build_invite_url()`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add invite config constants + lock the bitfield with a negative assertion (D-02/D-04/D-09)** - `a9383fa` (feat)
2. **Task 2: Create logic/invite.py::build_invite_url() — the single URL constructor (D-03/D-07)** - `a1ad124` (feat)

_TDD note: both tasks were marked `tdd="true"`; tests were authored alongside/immediately verifying each implementation within the same commit per the plan's task structure (test file built incrementally: Task 1's 5 tests land with the config constants they exercise, Task 2's 5 tests are appended with the module they exercise) — both task commits carry their own passing tests, consistent with the plan's per-task file-append design._

## Files Created/Modified

- `config.py` — appended `# --- Phase 22: Invite Plumbing (INVITE-01/02) ---` block (before `sanitize_database_url`) with `DISCORD_CLIENT_ID`, `INVITE_PERMISSIONS_VALUE`, `INVITE_SCOPES`
- `logic/invite.py` — new module, `build_invite_url(*, client_id, permissions_value, scopes=("bot","applications.commands")) -> str`
- `logic/__init__.py` — package comment amended to name `logic/invite.py` as the one documented exception to the no-discord-import rule
- `tests/test_invite_logic.py` — new test file, 10 tests

## Decisions Made

- Followed D-09's amended ten-permission set (not D-01's original eight) — the locked value is `309240908864`; the superseded `3263552` appears only in a comment explicitly marking it dead.
- `logic/invite.py`'s docstring explicitly calls out and justifies its `import discord` — the one deliberate deviation among all `logic/` modules — per the plan's required Option 1 resolution (RESEARCH.md's own worked example does the same).
- Kept the literal string `discord.utils.oauth_url` to exactly one occurrence in `logic/invite.py` (the real call site) to satisfy the plan's `grep -c` acceptance check; docstring prose refers to it as "discord.py's `oauth_url()` helper" instead of repeating the full dotted path.

## Deviations from Plan

None — plan executed exactly as written. One self-correction during execution (not a deviation from the plan's intent): the first docstring draft repeated the literal substring `discord.utils.oauth_url` three times, which would have failed the plan's explicit `grep -c "discord.utils.oauth_url" logic/invite.py` == 1 acceptance check; reworded the prose (kept the same explanatory content) before committing so the check passes cleanly.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `config.DISCORD_CLIENT_ID`, `config.INVITE_PERMISSIONS_VALUE`, `config.INVITE_SCOPES`, and `logic.invite.build_invite_url()` are all committed, tested, and match the interface contract exactly — ready for plan 22-02 (`cogs/invite.py` / `/invite` command) to consume.
- Plan 22-03's drift-guard can now diff any future doc-embedded invite URL against `build_invite_url()`'s real output.
- Full test suite green (1018 passed, 124 skipped — skips are the standing live-DB integration tests, unrelated to this plan), `ruff check .` clean, no regressions introduced.

---
*Phase: 22-invite-plumbing*
*Completed: 2026-07-14*

## Self-Check: PASSED

All created/modified files found on disk; all three commits (`a9383fa`, `a1ad124`, `b27a10a`) verified present in `git log --oneline --all`.
