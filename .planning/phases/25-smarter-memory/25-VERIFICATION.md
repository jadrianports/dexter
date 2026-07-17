---
phase: 25-smarter-memory
verified: 2026-07-16T00:00:00Z
status: human_needed
score: 3/3 must-haves verified
overrides_applied: 0
human_verification:
  - test: "SC-1 durability 'feel' over real Discord traffic — confirm a genuinely-recalled memory (via real /ask, /roast, ambient roasts, proactive callbacks, or the auto-queue taste blend over several days) visibly outlives a one-off memory in practice, not just in the isolated live-DB unit test."
    expected: "A memory that keeps getting surfaced across real usage stays available noticeably longer than an equally-old memory that is never recalled again; the daily decay sweep does not silently remove something Dex just referenced."
    why_human: "Requires a live bot process + real Gemini recall traffic accumulated over multiple days against the daily sweep's real 24h cadence — cannot be produced by an isolated pytest run. Parked behind the residential-host live-Discord UAT tail per Phase 11/13/17 precedent."
---

# Phase 25: Smarter Memory Verification Report

**Phase Goal:** Dexter's long-term memory gets more durable and richer — memories that keep proving relevant survive the daily decay sweep longer, and a vision roast now leaves behind a lasting memory of its own.
**Verified:** 2026-07-16
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC-1: A memory recalled/surfaced multiple times shows measurably reinforced expiry vs. an equally-old never-surfaced memory — the daily decay sweep evicts the unsurfaced one first | ✓ VERIFIED | `database.reinforce_memory_expiry` (database.py:1579) does a parameterized, extend-only `UPDATE ... SET expires_at = GREATEST(expires_at, $2) WHERE id = ANY($1)`. Wired at `services/memory.py::recall()` step 7b (:197-217), grouped by each fact's own resolved decay-days via `resolve_decay_days`. Traced end-to-end into the real eviction path: `delete_expired_memories` (database.py:1798) deletes only rows where `expires_at < now AND salience < MEMORY_DECAY_SALIENCE_FLOOR (0.5)`. Independently re-ran `tests/test_database_phase25.py::test_reinforced_fact_survives_sweep_unreinforced_does_not` against a **freshly-spun pgvector/pgvector:pg16 container I started myself** (not reusing the executor's claim) — inserts two equal-age, equal-salience (`daily_batch`=0.2, sweep-eligible) facts both past-expiry, reinforces only one via the real helper, runs the real `delete_expired_memories`, and asserts the reinforced row survives while the unreinforced one is gone. PASSED. |
| 2 | SC-3 (MEM-06 half): Reinforcement is expiry-only — `recall()` never mutates salience/hit_count/last_seen_at; `bump_surfaced`/`refresh_memory_expiry`/`MemoryFact` stay byte-unchanged | ✓ VERIFIED | `git diff 61a85a9 -- models/memory.py` is **empty** (byte-unchanged). `git diff 61a85a9 -- database.py` shows `bump_surfaced` and `refresh_memory_expiry` untouched — only the new sibling function and new prose-comments referencing them were added. Independently re-ran `tests/test_database_phase25.py::test_recall_does_not_mutate_salience_or_hit_count` against my own fresh container — inserts a `milestone` (salience 1.0) fact, runs the real `bump_surfaced` + `reinforce_memory_expiry` (the two real recall step-7 calls), re-reads the row, asserts salience/hit_count/last_seen_at byte-identical and only expires_at/last_surfaced_at/surface_count changed. PASSED. |
| 3 | SC-2: A vision roast persists a distilled, number-free fact into `user_memories` under its own kind, gated by the full sensitivity/PII + accuracy-firewall (no raw numbers/SQL-known counts embedded) | ✓ VERIFIED | `config.py` registers `vision_roast` additively (`MEMORY_SALIENCE_BASE_WEIGHTS["vision_roast"]=0.4` < 0.5 floor; `MEMORY_DECAY_DAYS_BY_KIND["vision_roast"]=TASTE_DECAY_DAYS`=30d) — `git diff 61a85a9 -- config.py` shows only these two added lines. `cogs/events.py::_maybe_fire_vision_roast` fires `distill_and_remember(kind="vision_roast", raw_text=line, ...)` strictly after a successful `message.reply` (line is guaranteed non-None by the prior early-return, reply guaranteed successful by the prior except-return), guild-stamped `str(message.guild.id)`. `distill_and_remember` (services/memory.py:536) computes `exempt_numbers=(kind == "taste_episode")` internally — `vision_roast != taste_episode` so the caller cannot bypass the full `is_sensitive`+`contains_number` firewall (models/memory.py). Independently re-ran all 3 `TestVisionRoastMemory` tests against my own fresh container: a safe line produces exactly one `kind='vision_roast'` row with salience<0.5 and ~30d horizon; a number-bearing line ("47 replies") produces ZERO rows; a sensitive line ("mental health struggles") produces ZERO rows. All 3 PASSED. |

**Score:** 3/3 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `database.py::reinforce_memory_expiry` | Batched, extend-only expiry UPDATE (ANY($1)+GREATEST) | ✓ VERIFIED | Exists at :1579; parameterized; source contains `ANY($1)` and `GREATEST(expires_at, $2)`, no SQL-side date arithmetic; no-op guard on empty ids |
| `services/memory.py::recall` step 7b | Kind-grouped expiry reinforcement at the single chokepoint | ✓ VERIFIED | :190-217 (after the WR-01 fix, wrapped in its own inner try/except separate from the outer retrieval-body catch — so a reinforcement failure can no longer discard already-successful facts) |
| `tests/test_database_phase25.py` | Source-inspection + live-DB SC-1/SC-3/SC-2 coverage | ✓ VERIFIED, WIRED, DATA FLOWS | 10 tests, all independently re-run against a fresh pgvector container: 5 source-inspection (always run) + 2 live-DB MEM-06 (SC-1/SC-3) + 3 live-DB MEM-07 (SC-2). All 10 PASSED |
| `tests/test_memory.py` extensions | Grouping unit test + Pitfall-2 monkeypatch fix | ✓ VERIFIED | `test_reinforces_expiry_grouped_by_kind` present; `test_returns_capped_facts_when_some_clear_floor`'s monkeypatch extended to stub `reinforce_memory_expiry` (confirmed passing as part of the full-suite run) |
| `config.py` vision_roast entries | Additive dict entries, zero DDL | ✓ VERIFIED | `git diff` shows exactly 2 added lines; `python -c` import assertion confirmed |
| `cogs/events.py::_maybe_fire_vision_roast` write | Fire-and-forget, success-gated, guild-stamped write | ✓ VERIFIED, WIRED | :696-726; guarded by `memory_service is not None and line not in roasts.VISION_ROAST_FALLBACKS` (WR-02 fix confirmed present) |
| `tests/test_vision_events.py` WR-03 tests | Mocked call-site wiring coverage | ✓ VERIFIED | 5 new tests present (`_make_bot_with_memory`, kwargs assertion, line-is-None skip, reply-fails skip, transport-fallback skip, memory_service-absent no-crash) — all passed in the full suite run |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `recall()` step 7b | `database.reinforce_memory_expiry` | one call per `resolve_decay_days` group | ✓ WIRED | Confirmed by direct code read + passing grouping test |
| `reinforce_memory_expiry` | `user_memories.expires_at` | `GREATEST(expires_at, $2)` UPDATE | ✓ WIRED | Confirmed via live-DB SC-1 test against a real Postgres instance |
| `_maybe_fire_vision_roast` success tail | `memory_service.distill_and_remember(kind="vision_roast")` | `asyncio.create_task` post-reply | ✓ WIRED | Confirmed by direct code read (`cogs/events.py:716-726`) + 5 mocked wiring tests |
| `distill_and_remember(kind="vision_roast")` | `MEMORY_SALIENCE_BASE_WEIGHTS`/`MEMORY_DECAY_DAYS_BY_KIND["vision_roast"]` | base_salience lookup + resolve_decay_days | ✓ WIRED | Confirmed via live-DB `TestVisionRoastMemory` — stored row's salience/expires_at match the config values |
| `delete_expired_memories` (daily sweep) | reinforced/unreinforced rows | `expires_at < now AND salience < 0.5` | ✓ WIRED, DATA FLOWS | This is the actual eviction chokepoint MEM-06 must connect to — confirmed connected and correctly ordered by the SC-1 test |

### Data-Flow Trace (Level 4)

Not applicable in the traditional UI-rendering sense (this phase is pure backend/DB logic with no
rendering component), but the equivalent trace — reinforcement write → real sweep query → real
eviction outcome — was performed directly against a live Postgres instance (see Truth #1 evidence)
rather than trusting a mocked pool. This is the harder SC-1 claim and it holds end-to-end.

### Behavioral Spot-Checks / Probe Execution

N/A — this phase has no CLI/runnable entry point or documented probe script; verification instead
ran the phase's own live-DB integration test suite against a freshly-provisioned instance (see
above), which is the equivalent rigor for this kind of backend change.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|--------------|-------------|--------------|--------|----------|
| MEM-06 | 25-01-PLAN.md | Memories that get surfaced/hit gain durability (expiry reinforcement) | ✓ SATISFIED | `reinforce_memory_expiry` + recall() step 7b + SC-1/SC-3 live-DB tests, all independently confirmed passing |
| MEM-07 | 25-02-PLAN.md | A vision roast persists a distilled, number-free fact into long-term memory, subject to the accuracy/PII firewall | ✓ SATISFIED | `vision_roast` kind + fire-and-forget write + full firewall + SC-2 live-DB tests, all independently confirmed passing |

Both requirement IDs from PLAN frontmatter match REQUIREMENTS.md exactly (lines 19-20, 74-75) —
no orphaned requirements for this phase.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | None found in phase-modified files (database.py, services/memory.py, config.py, cogs/events.py, tests/test_database_phase25.py, tests/test_memory.py, tests/test_vision_events.py) | — | A code review (`25-REVIEW.md`) found 0 critical, 4 warning, 1 info issues. All 4 warnings were fixed and independently confirmed present in the current code: WR-01 (step-7 bookkeeping isolated from outer retrieval catch), WR-02 (VISION_ROAST_FALLBACKS excluded from memory write), WR-03 (5 new mocked call-site wiring tests added), WR-04 (`now2` renamed to `reinforced_at`). The 1 info-level item (IN-01, source-prose assertion fragility in a test) was explicitly left unfixed by design — non-blocking, test-quality note only. |

No TBD/FIXME/XXX debt markers found in any phase-modified file. Pre-existing `not yet implemented`
skip-reasons in `tests/test_memory.py` are Phase 11-era TDD RED-phase markers unrelated to this
phase (all reference already-shipped Phase 11 features and were not touched by Phase 25).

### Regression Checks (flagged in verification focus)

- **Critical Rule 15 / VIS-02** (safety-blocked vision reaction = silent skip, no template): confirmed
  intact. `_generate_vision_roast`'s `str|None` contract is unchanged; the new memory write sits
  strictly downstream of the pre-existing `line is None` early-return and the pre-existing
  `message.reply` except-return, so a safety-blocked or failed-send case still writes nothing and
  the 5 original vision-glue tests (safety-block, reply-failure paths) are unaffected.
- **Critical Rule 17 / MEM-02** (guild_scoped is an explicit per-call-site opt-in; `/ask` stays global):
  confirmed untouched. `git diff` of `services/memory.py` shows the only change is the additive
  step-7b block after the existing step-6 cap; the `guild_scoped`/`search_memories` call in steps
  2-6 is byte-identical.
  - Phase 13 CR-01 cross-kind `expires_at` corruption scar: not reopened. Step 7b groups strictly
    by each fact's own row-level `kind` (via `resolve_decay_days`), never applies a blanket
    cross-kind expiry update.

### Human Verification Required

### 1. SC-1 durability "feel" over real Discord traffic

**Test:** Run the live bot for several days of real usage; confirm a memory that Dex keeps
recalling (via `/ask`, `/roast`, ambient roasts, proactive callbacks, or the auto-queue taste blend)
visibly persists longer than a one-off memory that's never recalled again.
**Expected:** The daily decay sweep does not silently remove something Dex just referenced days
earlier; a genuinely useful recurring fact should still be recallable weeks later while forgettable
one-offs age out on schedule.
**Why human:** Requires a live bot process, real Gemini recall traffic, and the real 24-hour sweep
cadence accumulated over multiple days — an isolated pytest run (however faithful) cannot reproduce
that. This is parked behind the same residential-host live-Discord UAT tail as every prior memory
phase (11, 13, 15, 16, 17), per established project precedent, not a code gap.

### Gaps Summary

No code-level gaps. Both success criteria (SC-1 durability reinforcement, SC-2 vision-memory
write-through-firewall) and the SC-3 byte-identical regression guard are verified directly against
the actual codebase and an independently-provisioned live Postgres instance (not merely re-trusting
the executor's SUMMARY.md claims). All 4 code-review warnings were fixed and the fixes are present
in the current code. The single remaining item is a live-Discord "feel" check that no prior memory
phase in this project's history has been able to verify automatically either — it is surfaced here
for the human, not treated as a blocker.

---

_Verified: 2026-07-16_
_Verifier: Claude (gsd-verifier)_
