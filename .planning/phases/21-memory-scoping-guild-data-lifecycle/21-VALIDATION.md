---
phase: 21
slug: memory-scoping-guild-data-lifecycle
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-14
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `21-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio |
| **Config file** | none — implicit defaults (`.planning/codebase/TESTING.md`) |
| **Quick run command** | `pytest tests/test_memory.py tests/test_memory_taste.py tests/test_ambient_recall_cadence.py tests/test_autoqueue_wiring.py -x` |
| **Full suite command** | `pytest` (CI: `.github/workflows/ci.yml`, `pgvector/pgvector:pg16` service container) |
| **Estimated runtime** | ~30s quick / ~90s full |

Live-DB tests skip locally when `TEST_DATABASE_URL` is unreachable (`tests/conftest.py:34-46`) but
**actually run in CI** — Phase 18 supplies the pgvector service container. Purge and guild-scoped
search integration tests are therefore genuinely gated, not decorative.

---

## Sampling Rate

- **After every task commit:** Run the quick command (no live DB required — SQL-string and
  mocked-recall assertions only)
- **After every plan wave:** Run the full suite (includes live-DB purge + guild-scoped search)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 21-01-* | 01 | 1 | MEM-03 | T-21-02 | `search_memories` emits `(guild_id = $N OR guild_id IS NULL)` as one parenthesized OR-group — never a degenerate `IS NULL`-only clause that would blind all guild recall | unit | `pytest tests/test_memory.py -k guild -x` | ❌ W0 | ⬜ pending |
| 21-01-* | 01 | 1 | MEM-03 | T-21-01 | `user_id = $1` remains present in EVERY guild-scoped SQL output — the guild clause is `AND`-appended, narrowing within the cross-user guard, never `OR`-appended (T-11-03a preserved) | unit | `pytest tests/test_memory.py -k guild -x` | ❌ W0 | ⬜ pending |
| 21-01-* | 01 | 1 | MEM-03 | — | `search_memories(guild_id=None)` emits byte-identical SQL to pre-Phase-21 (all 4 kind×guild combinations asserted; param numbering correct when BOTH optional clauses fire) | unit | `pytest tests/test_memory.py -k guild -x` | ❌ W0 | ⬜ pending |
| 21-01-* | 01 | 1 | MEM-02 | T-21-04 | `MemoryService.recall(guild_scoped=False)` (the default) forwards no guild filter — global recall preserved for non-opting callers | unit | `pytest tests/test_memory.py -k recall -x` | ✅ extend `TestRecallKindParam` | ⬜ pending |
| 21-02-* | 02 | 1 | MEM-04 | T-21-03 | `purge_guild_data` deletes `guild_id = $1` rows from exactly 4 hardcoded tables (`guild_config`, `guild_queues`, `guild_jams`, `user_memories`) — never a dynamic all-tables-with-guild_id introspection | integration (live pgvector) | `pytest tests/test_database_phase21.py -x` | ❌ W0 | ⬜ pending |
| 21-02-* | 02 | 1 | MEM-04 | T-21-03 | A `guild_blocklist` row for the SAME guild_id inserted before the purge **still exists afterward** (OWNER-04 / Phase 20 D-01 invariant) | integration (live pgvector) | `pytest tests/test_database_phase21.py -x` | ❌ W0 | ⬜ pending |
| 21-02-* | 02 | 1 | MEM-04 / MEM-03 | — | `user_memories` rows with `guild_id IS NULL` survive the purge (SQL `=` never matches NULL — the D-01 grandfathered corpus is excluded automatically) | integration (live pgvector) | `pytest tests/test_database_phase21.py -x` | ❌ W0 | ⬜ pending |
| 21-03-* | 03 | 2 | MEM-01 | T-21-04 | `/roast @user`, ambient roast, and proactive callback recalls each pass `guild_scoped=True` | unit | `pytest tests/test_ambient_recall_cadence.py -x` | ✅ extend | ⬜ pending |
| 21-03-* | 03 | 2 | MEM-01 | T-21-04 | music-command memory callback (`cogs/music.py:~1232`) passes `guild_scoped=True` + a real guild_id (no longer `""`) | unit | `pytest tests/test_ambient_recall_cadence.py -x` | ❌ W0 | ⬜ pending |
| 21-03-* | 03 | 2 | MEM-01 | T-21-04 | auto-queue positive-taste-blend recall passes `guild_scoped=True` (reads other voice members' guild-stamped `taste_episode` facts) | unit | `pytest tests/test_autoqueue_wiring.py -x` | ✅ extend | ⬜ pending |
| 21-03-* | 03 | 2 | MEM-02 | T-21-04 | `/ask` recall passes **no** `guild_scoped` kwarg (or explicit `False`) — stays global, invoker-self-scoped, byte-identical | unit | `pytest tests/test_ambient_recall_cadence.py -x` | ✅ extend | ⬜ pending |
| 21-04-* | 04 | 2 | MEM-04 | — | `on_guild_remove` calls the purge wrapped in try/except — a purge failure logs and is swallowed, never crashes the removal (WR-04 discipline) | structural review | N/A — Discord glue, untested-by-design (`TESTING.md`) | N/A | ⬜ pending |
| 21-05-* | 05 | 2 | MEM-05 | — | `remember()`'s dedup search call shape is UNCHANGED — no guild kwarg ever reaches `database.search_memories` from that call site (the CR-13-01 scar path stays byte-identical) | unit | `pytest tests/test_memory_taste.py -k dedup -x` | ❌ W0 | ⬜ pending |
| 21-05-* | 05 | 2 | MEM-05 | — | D-05 `refresh_memory_expiry` matched-row-kind gating semantics unchanged — existing dedup/expiry tests pass UNMODIFIED (regression gate, not new coverage) | unit (regression) | `pytest tests/test_memory_taste.py -x` | ✅ exists | ⬜ pending |
| 21-06-* | 06 | 3 | MEM-01/03/05 | — | PROJECT.md Key Decisions records the memory-scoping path that actually shipped (SC-4 → PORT-04 dependency) | doc assertion | `grep -q "guild" .planning/PROJECT.md` (Key Decisions section names the shipped scoping) | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*Plan/task IDs are indicative — the planner assigns final numbering; the requirement→behavior mapping is the contract.*

---

## Wave 0 Requirements

- [ ] `tests/test_memory.py` — new `TestSearchMemoriesGuildFilter` class mirroring the existing
      `TestSearchMemoriesKindFilter` (fake-pool SQL-string assertions across all 4 kind×guild
      combinations, incl. the param-numbering collision case where BOTH optional clauses fire)
- [ ] `tests/test_memory.py` — new `TestRecallGuildScoped` class mirroring `TestRecallKindParam`
      (asserts `guild_scoped` forwards correctly and defaults to `False`)
- [ ] `tests/test_database_phase21.py` — new live-DB file: guild-scoped search (NULL + matching-guild
      rows returned, other-guild rows excluded) and `purge_guild_data` (4 tables purged,
      `guild_blocklist` survives, NULL memories survive)
- [ ] `tests/test_ambient_recall_cadence.py` — extended assertions for `/roast`, ambient roast,
      proactive callback, music-command callback (`guild_scoped=True`) and `/ask` (NOT scoped)
- [ ] `tests/test_autoqueue_wiring.py` — new assertion for `guild_scoped=True` on the taste-blend recall
- [ ] MEM-05 dedup call-shape regression test — reuses the existing no-`guild_id`-accepted stub shape
      (`tests/test_memory_taste.py:156`), which structurally FAILS if a guild kwarg ever reaches the
      dedup search

*No new test framework/config needed — pytest + pytest-asyncio + the existing pgvector-codec pool
fixture in `conftest.py` cover every test type this phase needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| A user's memory recalled in Guild A genuinely does not surface in an ambient roast/proactive callback in Guild B | MEM-01 | Requires two live Discord guilds with Dexter joined to both, real accumulated memories, and the ambient cadence to actually fire (0.10–0.30 chance) — no automated harness can drive the real gateway | Join Dexter to a 2nd guild; accumulate memories in Guild A; trigger ambient roasts/callbacks in Guild B; confirm no Guild-A-specific detail is ever referenced |
| Purge actually runs on a real kick/leave and leaves no resurfacing context on re-invite | MEM-04 | Requires a real guild removal event over the Discord gateway | Kick Dexter from a test guild; re-invite; confirm no prior queue/jam/config/memory context resurfaces |
| `/guilds block` → purge → blocklist ordering holds under real gateway timing (block survives) | MEM-04 | Real concurrent gateway event timing; the code-level argument (disjoint tables) is proven but the live interleaving is not machine-observable | Owner-run `/guilds block` on a test guild; confirm re-invite is refused (block survived the purge) |

> **Parked, per standing precedent (Phases 09/11/13–17).** This project's host is not always-on
> (24/7 deploy parked behind the YouTube datacenter-IP block), so live-Discord checks are a known
> deferred class. These land in `21-HUMAN-UAT.md` at phase close and are acknowledged-deferred —
> they do NOT gate code completion. Every code-level invariant above has automated coverage.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (the 3 manual items are the known
      live-Discord deferred class, each with an automated code-level proxy)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
