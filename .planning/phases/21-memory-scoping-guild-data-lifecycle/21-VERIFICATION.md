---
phase: 21-memory-scoping-guild-data-lifecycle
verified: 2026-07-14T00:00:00Z
status: human_needed
score: 9/9 must-haves verified (code-level)
overrides_applied: 0
human_verification:
  - test: "Accumulate memories for a user in Guild A, then trigger an ambient roast or proactive callback for that same user in Guild B"
    expected: "No Guild-A-specific memory detail is ever referenced in Guild B — third-party/cross-guild memory leak stays closed"
    why_human: "Requires two live Discord guilds with Dexter joined to both, real accumulated memories, and the ambient cadence (0.10-0.30 chance) to actually fire over the real gateway — no automated harness can drive this. 24/7 deploy is parked (YouTube datacenter-IP block), so this is deferred per standing Phase 09/11/13-17 precedent."
  - test: "Kick Dexter from a real guild, then re-invite it"
    expected: "No prior queue/jam/config/memory context resurfaces for that guild after re-invite"
    why_human: "Requires a real guild removal event over the Discord gateway (on_guild_remove firing for real, not via unit test). Code-level purge is fully proven via tests/test_database_phase21.py's live-DB tests (which run in CI's pgvector container) plus the bot.py wiring lock (TestOnGuildRemoveWiring); the end-to-end gateway trigger itself is not machine-observable locally."
  - test: "Owner runs /guilds block on a test guild, confirm purge + blocklist-insert ordering holds and re-invite is refused"
    expected: "The guild_blocklist row survives the concurrent purge triggered by guild.leave() -> on_guild_remove, and a re-invite attempt is refused"
    why_human: "Real concurrent gateway-event timing cannot be simulated locally; the code-level argument (purge and blocklist insert touch completely disjoint tables, so no race exists) is proven structurally and by the live-DB test_purge_survives_blocklist test, but live interleaving under real Discord timing is not machine-observable."
---

# Phase 21: Memory Scoping & Guild Data Lifecycle Verification Report

**Phase Goal:** A third party's recalled memory stops leaking across servers, and a departed guild's
data can't resurface — without assuming the ideal scoping ships, since the standing Descope Rule
applies with particular force here.
**Verified:** 2026-07-14
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

**Descope gate check first:** ROADMAP.md explicitly records "Descope gate (D-04): NOT triggered.
Plan-time research evaluated all three REQUIREMENTS.md tripwires against the literal code — none
fire. The full hybrid scoping is planned; the 'keep memory global + disclose' fallback is NOT being
built." Verified this is what actually shipped — the full hybrid (not the fallback) is in the code.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | MEM-02: `/ask` continues to recall the invoker's own memory globally, unaffected by guild-scoping | VERIFIED | `cogs/ai.py:130-140` — `/ask`'s `recall()` call has NO `guild_scoped` kwarg (confirmed by direct read + `grep -n guild_scoped cogs/ai.py` returning zero hits inside `ask`). `MemoryService.recall()` defaults `guild_scoped=False` and forwards no `guild_id` kwarg to `database.search_memories` on that path (`services/memory.py:141-149`). Locked by `tests/test_ambient_recall_cadence.py::test_ask_recall_is_never_guild_scoped` + `TestGuildScopedOptIns::test_ask_callback_never_mentions_guild_scoped` (both pass). |
| 2 | MEM-04: departed-guild data is purged across `guild_config`, `guild_queues`, `guild_jams`, guild-scoped `user_memories` | VERIFIED | `database.py:738-796` `purge_guild_data()` — exactly 4 hardcoded `DELETE FROM ... WHERE guild_id = $1` statements inside one `conn.transaction()`. Wired at `bot.py:787-792` inside `on_guild_remove`, positioned after cache-evict and before the owner notice, `hasattr(bot, "pool")`-guarded. Live-DB proof in `tests/test_database_phase21.py::test_purge_four_tables_isolated_and_null_survives` (skips locally without `TEST_DATABASE_URL`, runs in CI's pgvector service container per `.github/workflows/ci.yml`). |
| 3a | MEM-01: `/roast @user`, ambient roasts, and proactive callbacks recall only guild-scoped memories | VERIFIED | 5 call sites carry `guild_scoped=True` (or `bool(guild_id)`): `cogs/ai.py:229` (`/roast`), `cogs/ai.py:347` (auto-queue taste blend), `cogs/events.py:167` (ambient voice-join roast), `cogs/events.py:516` (proactive callback), `cogs/music.py:1238` (music-command earned-roast callback, `guild_scoped=bool(guild_id)`). `grep -n guild_scoped cogs/ai.py cogs/events.py cogs/music.py` returns exactly these 5 lines — matches the plan's declared call-site inventory exactly. |
| 3b | MEM-03: legacy `guild_id = NULL` corpus (`daily_batch`) handled by an explicit, tested backward-compat rule, not silently blinded | VERIFIED | `database.py::search_memories` (`:1455-1462`) emits `AND (guild_id = $N OR guild_id IS NULL)` when `guild_id` is provided — the D-01 grandfather rule, verbatim. Unit-locked by `TestSearchMemoriesGuildFilter` (4 kind x guild combos) in `tests/test_memory.py`; live-DB proven by `tests/test_database_phase21.py::test_guild_scoped_search_excludes_other_guild_includes_null` and `test_purge_four_tables_isolated_and_null_survives` (NULL memory survives purge). |
| 3c | MEM-05: guild-scoped search does not corrupt cross-kind dedup or `expires_at` semantics (Phase 13 CR-01 scar) | VERIFIED | `services/memory.py:265-270` — `remember()`'s k=1 dedup `search_memories` call is byte-identical to pre-Phase-21 (`user_id`, `query_embedding`, `k` only — no `guild_id`, no `kind`). Structurally locked by `TestRememberDedupCallShapeUnchanged` (strict-signature stub with no `guild_id`/`kind`/`**kwargs` escape hatch — a `TypeError` on any future leak) plus a D-05 `expires_at` regression test (`taste_episode` refreshes, `daily_batch` does not). `tests/test_memory_taste.py` verified unmodified (`git diff --stat` empty). |
| 4 | Whichever path is taken, the decision + rationale is recorded in PROJECT.md Key Decisions before phase close (SC-4 / PORT-04) | VERIFIED | `.planning/PROJECT.md` Key Decisions table gained 2 rows (lines 215-216): the shipped hybrid scoping row explicitly names `/ask` as staying global and the NULL-corpus grandfather rule; the purge row explicitly states `guild_blocklist` is never purged. `CLAUDE.md` synced in 3 places (Database Schema narrative, Critical Rule 17, Implementation Gotchas "Phases 13-17" section) — confirmed via grep. |

**Score:** 9/9 code-level must-haves verified (MEM-01 through MEM-05, all sub-truths). 3 items require
live-Discord/live-gateway human verification (see below) — this does not change the code-level score,
per the acknowledged-deferred precedent from Phases 09/11/13-17.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `database.py::search_memories` | optional `guild_id` kwarg + dynamic `$N` numbering | VERIFIED | Contains `OR guild_id IS NULL`; no hardcoded `$3` literal remains; `WHERE user_id = $1` present verbatim; docstring updated (:1395-1462). |
| `services/memory.py::MemoryService.recall` | keyword-only `guild_scoped: bool = False` opt-in | VERIFIED | Signature at `:60-67` confirms `guild_scoped: bool = False` behind bare `*`; forwards `guild_id` via conditional dict-splat only when opted in (:141-149). |
| `database.py::purge_guild_data` | one transaction, 4 hardcoded DELETEs, never `guild_blocklist` | VERIFIED | `:738-796`. Source contains zero occurrences of `guild_blocklist`; exactly 4 `DELETE FROM`; `conn.transaction()` present; no `information_schema`, no loop. |
| `bot.py::on_guild_remove` | calls `purge_guild_data`, wrapped try/except, single hook | VERIFIED | `:762-794`. `try/except Exception as exc: log.warning(...)`; also logs `log.info` with per-table counts on success (WR-01 fix, commit `727ad10`). `grep -rn purge_guild_data cogs/` returns zero — confirmed single call site. |
| `tests/test_database_phase21.py` | static + live-DB integration proof | VERIFIED | 334 lines; static `TestPurgeGuildDataStructure` + `TestOnGuildRemoveWiring` (WR-02 fix, commit `73a67be`) run unconditionally; 3 live-DB tests skip locally (no `TEST_DATABASE_URL`) and run in CI (pgvector service container in `.github/workflows/ci.yml`). |
| `tests/test_memory.py` | `TestSearchMemoriesGuildFilter`, `TestRecallGuildScoped`, `TestRememberDedupCallShapeUnchanged` | VERIFIED | All 3 classes present and passing; pre-existing `TestSearchMemoriesKindFilter`, `TestRecallKindParam`, `TestRememberService` untouched. |
| `.planning/PROJECT.md` | Key Decisions rows for shipped scoping + purge | VERIFIED | 2 rows present, both name `/ask` global and `guild_blocklist` exclusion explicitly. |
| `CLAUDE.md` | schema/critical-rules/gotchas narrative updated | VERIFIED | `purge_guild_data`, `guild_scoped` both present; Critical Rule 17 added; Implementation Gotchas gained 5 Phase-21 bullets. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `cogs/ai.py::roast` | `MemoryService.recall` | `guild_scoped=True` | WIRED | `cogs/ai.py:229`, confirmed by direct read + passing `test_roast_always_recalls_target_scoped` kwarg assertion. |
| `cogs/ai.py::ask` | `MemoryService.recall` | NO `guild_scoped` kwarg | WIRED (intentionally not scoped) | Confirmed absent; two independent regression tests lock it. |
| `cogs/ai.py::try_auto_queue` | `MemoryService.recall` | `kind="taste_episode"` + `guild_scoped=True` | WIRED | `cogs/ai.py:341-347`. |
| `cogs/events.py::_generate_ambient_roast` | `MemoryService.recall` | `guild_scoped=True` | WIRED | `cogs/events.py:167`, inside the `MEMORY_CALLBACK_CHANCE` gate, `pre_recalled_memories` bypass preserved. |
| `cogs/events.py::_maybe_fire_proactive_callback` | `MemoryService.recall` | `guild_scoped=True` | WIRED | `cogs/events.py:516`. |
| `cogs/music.py::_build_roast_line` | `MemoryService.recall` | `guild_scoped=bool(guild_id)` | WIRED | `cogs/music.py:1238`, `""` placeholder replaced with real `guild_id or ""`. |
| `services/memory.py::recall` | `database.search_memories` | conditional `guild_id` kwarg splat | WIRED | `services/memory.py:137-149`. |
| `services/memory.py::remember` (dedup) | `database.search_memories` | UNCHANGED — no `guild_id`/`kind` | WIRED (deliberately unmodified) | `services/memory.py:265-270`, byte-identical to pre-Phase-21. |
| `bot.py::on_guild_remove` | `database.purge_guild_data` | awaited in try/except | WIRED | `bot.py:789`, plus regression test `TestOnGuildRemoveWiring::test_on_guild_remove_calls_purge_guild_data`. |
| `database.purge_guild_data` | `guild_blocklist` | NO LINK (must never appear) | CONFIRMED ABSENT | `guild_blocklist` does not appear in `purge_guild_data`'s source; live-DB test `test_purge_survives_blocklist` proves survival. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase-scoped test suite green | `pytest tests/test_memory.py tests/test_memory_taste.py tests/test_ambient_recall_cadence.py tests/test_autoqueue_wiring.py tests/test_database_phase21.py tests/test_roast_command.py -q` | 159 passed, 3 skipped (live-DB, no TEST_DATABASE_URL locally) | PASS |
| Full repo suite green (independently re-run, not just trusting SUMMARY/orchestrator claim) | `pytest -q` | 1008 passed, 124 skipped, 0 failed, 419.68s | PASS |
| Lint clean on all phase-touched files | `ruff check database.py services/memory.py cogs/ai.py cogs/events.py cogs/music.py bot.py tests/test_memory.py tests/test_database_phase21.py tests/test_ambient_recall_cadence.py tests/test_autoqueue_wiring.py` | All checks passed | PASS |
| No debt markers in phase-touched files | `grep -n -E "TBD\|FIXME\|XXX"` across all 10 files | zero matches | PASS |
| Single purge call site (no second site in cogs/) | `grep -rn purge_guild_data cogs/` | zero matches | PASS |
| Exactly 5 guild_scoped opt-in call sites, none inside `/ask` | `grep -n guild_scoped cogs/ai.py cogs/events.py cogs/music.py` | 5 lines, all outside `ask()` | PASS |
| Commits referenced in SUMMARY/REVIEW-FIX exist on `main` | `git log --oneline -1 727ad10` / `73a67be` | both found | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| MEM-01 | 21-03, 21-04 | `/roast`, ambient roasts, proactive callbacks recall only guild-scoped memories | SATISFIED | 5 call sites carry `guild_scoped=True`/`bool(guild_id)`, confirmed above. |
| MEM-02 | 21-01, 21-03 | `/ask` recalls invoker's own memory globally, unaffected | SATISFIED | No `guild_scoped` kwarg on `/ask`'s call; 2 regression tests lock it. |
| MEM-03 | 21-01, 21-02, 21-04 | Legacy `guild_id = NULL` corpus handled by explicit tested backward-compat rule | SATISFIED | D-01 grandfather `(guild_id = $N OR guild_id IS NULL)` clause + unit + live-DB tests. |
| MEM-04 | 21-02, 21-04 | Departed-guild data purged (4 tables), stale context can't resurface | SATISFIED | `purge_guild_data` + `on_guild_remove` wiring + live-DB isolation/survival tests. |
| MEM-05 | 21-01, 21-04 | Guild-scoped search doesn't corrupt cross-kind dedup / `expires_at` (CR-01 scar) | SATISFIED | `remember()` dedup path byte-identical, structurally locked by strict-signature test. |

No orphaned requirements — `.planning/REQUIREMENTS.md` maps exactly MEM-01..05 to Phase 21, and all 5 appear in the union of the 4 plans' `requirements:` frontmatter fields.

### Anti-Patterns Found

None. No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers, no empty stub implementations, no
hardcoded-empty data flowing to output in any of the 10 phase-touched files. `ruff check` clean on
all of them.

### Code Review Findings (21-REVIEW.md + 21-REVIEW-FIX.md)

0 critical / 2 warning / 1 info. Both warnings fixed and independently re-verified in this pass:
- WR-01 (no success-path observability in `on_guild_remove`) — fixed by commit `727ad10`; confirmed
  `log.info("on_guild_remove: purged guild %s data: %s", guild.id, counts)` present in current source.
- WR-02 (no test locks `on_guild_remove` -> `purge_guild_data` wiring) — fixed by commit `73a67be`;
  confirmed `TestOnGuildRemoveWiring` class exists in `tests/test_database_phase21.py` with 2 passing
  tests.
- IN-01 (D-01 NULL-corpus grandfather is a documented, intentional residual cross-guild leak surface)
  — not a defect; correctly disclosed in PROJECT.md Key Decisions per the review's own recommendation.

### Human Verification Required

Three items are genuinely un-verifiable without a live, always-on Discord deployment and a real
gateway — consistent with the standing precedent from Phases 09/11/13/14/15/16/17 (this project's
24/7 deploy is parked behind the YouTube datacenter-IP block; the bot runs on the user's residential
PC on demand). Every one of these has a proven code-level proxy (unit test and/or CI-run live-DB
integration test); only the true end-to-end Discord-gateway behavior is deferred. See frontmatter
`human_verification` for the structured form.

1. **Cross-guild memory leak closure (MEM-01), live-Discord**
   Test: accumulate memories for a user in Guild A, trigger an ambient roast/proactive callback for
   that user in Guild B.
   Expected: no Guild-A-specific detail is ever referenced in Guild B.
   Why human: needs two live guilds + real gateway cadence firing; no automated harness reaches this.

2. **Purge actually fires on real guild removal (MEM-04), live-Discord**
   Test: kick Dexter from a test guild, then re-invite it.
   Expected: no prior queue/jam/config/memory context resurfaces.
   Why human: `on_guild_remove` firing for real over the gateway is not machine-observable locally;
   the DB-level purge behavior itself is already proven by CI's live-DB tests.

3. **`/guilds block` purge/blocklist-insert ordering under real gateway timing (MEM-04)**
   Test: owner runs `/guilds block` on a test guild; confirm the block survives and re-invite is
   refused.
   Expected: `guild_blocklist` row survives; re-invite is refused.
   Why human: real concurrent gateway-event timing; the disjoint-tables argument is proven
   structurally and by `test_purge_survives_blocklist`, but live interleaving isn't locally testable.

### Gaps Summary

No code-level gaps found. All 5 requirements (MEM-01 through MEM-05) are implemented exactly as
specified in the 4 plans, matching the locked CONTEXT.md decisions (D-01 grandfather rule, D-02
read-path-only scoping, D-03 single purge hook, D-04 full-hybrid-attempted-and-shipped). The
Descope Rule's fallback was NOT invoked — verified this against the actual code, not just the
ROADMAP's claim. Both code-review warnings were fixed and independently re-confirmed in this pass.
The full test suite was independently re-run in this verification (not just trusted from the
orchestrator's or SUMMARY's claim) and reproduced the same 1008 passed / 124 skipped / 0 failed
result. The only open items are the 3 live-Discord/live-gateway checks that this project has
consistently and explicitly deferred since Phase 09 — acknowledged-deferred, not a gap, per the
task's own framing and the project's established precedent.

---

*Verified: 2026-07-14*
*Verifier: Claude (gsd-verifier)*
