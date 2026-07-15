---
phase: 25
slug: smarter-memory
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-15
---

# Phase 25 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `25-RESEARCH.md` §"Validation Architecture" + §"Security Domain".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (existing, `requirements.txt` / `requirements-dev.txt`) |
| **Config file** | none — implicit defaults (per `.planning/codebase/TESTING.md`) |
| **Quick run command** | `pytest tests/test_memory.py tests/test_database_phase25.py -v` |
| **Full suite command** | `pytest` |
| **Estimated runtime** | ~90 seconds full suite (live-DB tests skip when `TEST_DATABASE_URL` unset locally; run in CI's pgvector container) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_memory.py tests/test_database_phase25.py -v`
- **After every plan wave:** Run `pytest` (full suite)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~90 seconds

---

## Per-Task Verification Map

> Task IDs are bound at planning (planner-assigned). Rows below map each phase requirement/success-criterion
> to its concrete automated (or code-review) verification, per RESEARCH.md §"Phase Requirements → Test Map".

| Task (planner-assigned) | Req / SC | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-------------------------|----------|------------|-----------------|-----------|-------------------|-------------|--------|
| MEM-06 helper | MEM-06 | T-25-SQLI | Parameterized `UPDATE`, `id = ANY($1)`, `GREATEST(expires_at, $2)`; no `user_id` scope but ids only ever from `recall()`'s own scoped result | unit (source-inspection, mirrors `TestWriteHelpersExist` at `tests/test_database_phase11.py:50`) | `pytest tests/test_database_phase25.py::TestReinforceMemoryExpiryExists -x` | ❌ W0 | ⬜ pending |
| MEM-06 recall wiring | MEM-06 | T-25-IDOR | `recall()` groups top-k by resolved decay-days, calls new helper once per group (mocked) | unit (mocked, extends `TestRecallService` in `tests/test_memory.py`) | `pytest tests/test_memory.py::TestRecallService -x` | ❌ W0 (new method) | ⬜ pending |
| MEM-06 regression | MEM-06 / SC-3 | — | Existing `test_returns_capped_facts_when_some_clear_floor` still green after new unconditional DB call added (monkeypatch list extended — Pitfall 2, use `row.get("kind")`) | regression (existing test edited) | `pytest tests/test_memory.py::TestRecallService::test_returns_capped_facts_when_some_clear_floor -x` | ✅ needs edit | ⬜ pending |
| MEM-06 sweep round-trip | SC-1 | — | Two equal-age sweep-eligible-kind facts; surface only one via `recall()`; run `sweep()`; surfaced survives, unsurfaced evicted | integration (live-DB, `pool` fixture, CI pgvector) | `pytest tests/test_database_phase25.py::test_reinforced_fact_survives_sweep_unreinforced_does_not -x` | ❌ W0 | ⬜ pending |
| MEM-06 non-mutation | SC-3 | — | A salience ≥ 0.5 fact's `salience`/`hit_count`/`last_seen_at` byte-identical after `recall()` surface (only `expires_at`/`last_surfaced_at`/`surface_count` may change) | integration (live-DB) | `pytest tests/test_database_phase25.py::test_recall_does_not_mutate_salience_or_hit_count -x` | ❌ W0 | ⬜ pending |
| MEM-07 write-through-firewall | SC-2 | T-25-PII | `distill_and_remember(kind="vision_roast", exempt_numbers=False, ...)`: safe line → row with `kind='vision_roast'`, `salience < 0.5`, correct horizon; sensitive/number-bearing line → ZERO rows | integration (live-DB, extends existing `distill`/`remember` live pattern) | `pytest tests/test_database_phase25.py::TestVisionRoastMemory -x` | ❌ W0 | ⬜ pending |
| MEM-07 success-gate | MEM-07 | — | `_maybe_fire_vision_roast` spawns memory-write task ONLY when `line is not None` and reply succeeded; guild-stamped; fire-and-forget crash-proof | manual/structural review (Discord glue "untested-by-design" per TESTING.md; Phase 16/17 precedent) | N/A — code-review acceptance criterion | — | ⬜ pending |
| Additive-idle gate | SC-3 | — | Full existing suite green with new paths present-but-idle (no pre-existing test writes `vision_roast` or observes a changed `expires_at` on a non-target fact) | regression (gate) | `pytest` (full suite) | N/A — gate | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_database_phase25.py` — new file; uses the existing live-DB `pool` fixture from `tests/conftest.py` (its `DROP TABLE ... user_memories CASCADE` teardown already covers this phase's writes — **no `conftest.py` edit needed**).
- [ ] `tests/test_memory.py` — extend `TestRecallService` with the new grouped-reinforcement mock test(s); edit `test_returns_capped_facts_when_some_clear_floor`'s monkeypatch block to add the new DB call (Pitfall 2 — use `row.get("kind")`, never `row["kind"]`, or the `_DictRecord` fixtures `KeyError`).
- [ ] No new pytest fixtures, no framework install — `pytest` / `pytest-asyncio` / `pgvector/pgvector:pg16` CI service container are all already wired (`.github/workflows/ci.yml`).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `_maybe_fire_vision_roast` fires the memory write only on the success path, never crashing the roast | MEM-07 | Discord/process glue is untested-by-design (structural review + clean boot) per `.planning/codebase/TESTING.md`; consistent with Phase 16/17 glue precedent | Code review: confirm the `asyncio.create_task(distill_and_remember(...))` is inside the `line is not None` success branch after the successful `message.reply`, guild-stamped with `str(message.guild.id)`, and that `distill_and_remember` swallows all errors |
| SC-1 durability *feel* over real Discord (a genuinely recalled memory outliving a one-off) | MEM-06 | Requires a live bot + real recall traffic over days; parked behind the residential host like all prior live-Discord UAT | Deferred to phase HUMAN-UAT (live-Discord tail), acknowledged per Phase 11/13/17 precedent |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (`tests/test_database_phase25.py`, `tests/test_memory.py` edits)
- [x] No watch-mode flags
- [x] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-15 (plan-checker VERIFICATION PASSED, first pass; `wave_0_complete` flips at execution)
