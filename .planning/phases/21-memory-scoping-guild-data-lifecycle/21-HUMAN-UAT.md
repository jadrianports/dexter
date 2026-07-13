---
status: partial
phase: 21-memory-scoping-guild-data-lifecycle
source: [21-VERIFICATION.md]
started: 2026-07-14
updated: 2026-07-14
---

# Phase 21 — Human UAT

All 9 code-level must-haves verified (MEM-01 through MEM-05). The three items below require a live,
always-on Discord host and cannot be machine-observed locally. Each has a proven code-level proxy
(unit test and/or CI-run live-DB test) — only the true end-to-end gateway behavior is deferred, per
the standing Phase 09/11/13–17 precedent (24/7 deploy parked behind the YouTube datacenter-IP block).

## Current Test

[awaiting human testing]

## Tests

### 1. Cross-guild memory leak stays closed
Accumulate memories for a user in Guild A, then trigger an ambient roast or proactive callback for
that same user in Guild B.
expected: No Guild-A-specific memory detail is ever referenced in Guild B.
proxy: `TestGuildScopedOptIns` + `TestSearchMemoriesGuildFilter` (unit); live-DB
`test_guild_scoped_search_excludes_other_guild_includes_null` (CI pgvector).
result: [pending]

### 2. Departed-guild data does not resurface
Kick Dexter from a real guild, then re-invite it.
expected: No prior queue/jam/config/memory context resurfaces for that guild after re-invite.
proxy: `TestOnGuildRemoveWiring` (wiring lock) + live-DB
`test_purge_four_tables_isolated_and_null_survives` (CI pgvector).
result: [pending]

### 3. Owner block survives the purge race
Owner runs `/guilds block` on a test guild; confirm purge + blocklist-insert ordering holds and a
re-invite is refused.
expected: The `guild_blocklist` row survives the concurrent purge triggered by
`guild.leave()` → `on_guild_remove`, and the re-invite is refused.
proxy: structural (purge and blocklist insert touch disjoint tables — no race is possible) + live-DB
`test_purge_survives_blocklist` (CI pgvector).
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
