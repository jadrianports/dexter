---
phase: 11
slug: rag-long-term-memory
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-29
updated: 2026-06-29
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Body derived from `11-RESEARCH.md` § "Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio (async tests use `@pytest.mark.asyncio`) |
| **Config file** | none at root — `python -m pytest tests/` collects as-is (verified: test_prompts.py 16/16 passed). Add minimal config only if collection breaks. |
| **Quick run command** | `python -m pytest tests/test_memory.py tests/test_prompts.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -q` |
| **Estimated runtime** | ~20-40 seconds full suite (31 existing files + new test_memory.py); pure-logic quick run < 5s |

The pure-logic seam is `models/memory.py` (all rerank/recency/novelty/dedup/salience/eviction/decay
math + the sensitivity/number gates). It follows the project convention (`database.py:compute_streak`,
`logic/*`): no I/O, clock-injected via `now=`, unit-tested without DB or Discord mocks. Discord /
process / live-DB glue stays untested-by-design; live-DB round-trips are opt-in integration
(`tests/test_database_phase11.py`, skipped without a real DATABASE_URL, like test_database_phase4/7/8).

---

## Sampling Rate

- **After every task commit:** `python -m pytest tests/test_memory.py tests/test_prompts.py -x -q`
- **After every plan wave:** `python -m pytest tests/ -q` (full suite)
- **Before `/gsd-verify-work`:** full suite green + manual clean-boot check (no new silent failures in
  `dexter.log`, mirroring the Phase 10 TEST-04 regression gate)
- **Max feedback latency:** < 40 seconds (full suite); < 5s (pure-logic quick run)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | MEM-01 | T-11-SC | pgvector install human-gated before install | manual | human-check (pypi.org/project/pgvector) | N/A | ⬜ pending |
| 11-01-02 | 01 | 1 | MEM-01 | T-11-02 | no stale model ref; separate embed limit | unit | `python -c "import config; ..."` + stale-ref grep | ✅ | ⬜ pending |
| 11-01-03 | 01 | 1 | MEM-01 | T-11-01 | extension-first boot ordering (no codec crash) | unit/smoke | schema asserts + `pytest tests/test_memory.py` + `import bot` | ❌ W0 (scaffold) | ⬜ pending |
| 11-02-01 | 02 | 2 | MEM-03 | T-11-02b | spike non-destructive (fake ids + cleanup) | static | `ast.parse` + shape assert | ✅ | ⬜ pending |
| 11-02-02 | 02 | 2 | MEM-03 | T-11-02a | key/DSN never printed | manual | human-check (run spike, review distributions) | N/A | ⬜ pending |
| 11-02-03 | 02 | 2 | MEM-03 | — | constants recorded with spike marker | unit | `python -c "...tuned via 11-02 spike..."` | ✅ | ⬜ pending |
| 11-03-01 | 03 | 3 | MEM-03 | T-11-03c | floor empties below-threshold; rerank ordering | unit | `pytest tests/test_memory.py -k "rerank or floor or recency or novelty"` | ❌ W0 | ⬜ pending |
| 11-03-02 | 03 | 3 | MEM-02 | T-11-03a/b/d | separate _embed_limiter; user-scoped ANN; $N | unit | `pytest -k "embed or limiter"` + embed-limiter static assert | ❌ W0 | ⬜ pending |
| 11-03-03 | 03 | 3 | MEM-03 | T-11-03c | [] when nothing clears the floor | unit | `pytest tests/test_memory.py -k recall` | ❌ W0 | ⬜ pending |
| 11-04-01 | 04 | 4 | MEM-04, MEM-07 | T-11-04a | dedup threshold; salience eviction choice | unit | `pytest -k "dedup or salience or evict"` | ❌ W0 | ⬜ pending |
| 11-04-02 | 04 | 4 | MEM-04 | T-11-04b/c | $N params; user-scoped evict | unit/integration | static helper assert + `pytest tests/test_database_phase11.py` | ❌ W0 | ⬜ pending |
| 11-04-03 | 04 | 4 | MEM-04, MEM-07 | T-11-04a/d | bump vs insert; cap evict; skip on rate-limit | unit | `pytest -k remember` | ❌ W0 | ⬜ pending |
| 11-05-01 | 05 | 5 | MEM-05 | T-11-05a/b/c | sensitive + number-bearing facts dropped (stop-ship) | unit | `pytest -k "sensitive or number or distill"` | ❌ W0 | ⬜ pending |
| 11-05-02 | 05 | 5 | MEM-04 | T-11-05d/e | event hooks via create_task; on_message never writes | unit/static | `pytest -k "per_message or trigger"` + cog static asserts | ❌ W0 | ⬜ pending |
| 11-05-03 | 05 | 5 | MEM-04 | T-11-05d | one batched priority-2 daily distill | smoke | `import bot` + batch-task static assert | ✅ | ⬜ pending |
| 11-06-01 | 06 | 6 | MEM-06 | T-11-06b/d | memories=None byte-identical; numbers-from-SQL block | unit | `pytest tests/test_prompts.py` | ⚠️ extend (test_prompts.py ✅) | ⬜ pending |
| 11-06-02 | 06 | 6 | MEM-06 | T-11-06a/c | candidate-ammo; per-user scoped recall | static/smoke | `import cogs.ai` + recall/cadence static assert | ✅ | ⬜ pending |
| 11-06-03 | 06 | 6 | MEM-06 | T-11-06a/c | ambient/music recall; numbers from SQL | static/smoke | `import cogs.events, cogs.music` + static assert | ✅ | ⬜ pending |
| 11-07-01 | 07 | 6 | MEM-07 | T-11-07b | decay predicate retains high-salience/recent | unit | `pytest -k "decay or expire"` | ❌ W0 | ⬜ pending |
| 11-07-02 | 07 | 6 | MEM-07 | T-11-07a | time-bounded delete; sweep never raises | unit/integration | static assert + `pytest tests/test_database_phase11.py` | ❌ W0 | ⬜ pending |
| 11-07-03 | 07 | 6 | MEM-07 | T-11-07c | daily loop with before_loop/error/cleanup | smoke | `import bot` + sweep-task static assert | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Sampling continuity:** no run of 3 consecutive tasks lacks an automated verify — the two manual
checkpoints (11-01-01 legitimacy gate, 11-02-02 spike run) are each bracketed by automated tasks.

---

## Wave 0 Requirements

- [ ] `tests/test_memory.py` — created as a collectable scaffold in 11-01; pure-logic tests added
      progressively in 11-03 (rerank/floor/recency/novelty), 11-04 (dedup/salience/eviction),
      11-05 (is_sensitive/contains_number/distill gating), 11-07 (decay_predicate)
- [ ] `tests/test_database_phase11.py` — opt-in live-DB integration skeleton created in 11-01;
      insert/search/bump/count/evict round-trips (11-04) + sweep round-trip (11-07); skips without a real DB
- [ ] `tests/test_prompts.py` — already exists ✅; extended in 11-06 (memories=None byte-identity +
      memories=[...] rendering)
- [ ] `scripts/memory_spike.py` — throwaway numeric-defaults spike created in 11-02
- [ ] Framework: confirm `python -m pytest tests/` collects with no root config (it does); add minimal
      config only if collection breaks

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Clean boot on a fresh Neon branch (CREATE EXTENSION ordering + codec registration, no SSL/channel_binding crash) | MEM-01 | No live DB in CI; needs the user's `.env` + Neon | Start the bot on the user's PC; confirm `dexter.log` shows schema init with no `ValueError: unknown type: public.vector` and no SSL-EOF |
| Numeric-defaults spike run + distribution review | MEM-03 | Needs live Gemini embeddings + Neon + human judgment on the floor | `python scripts/memory_spike.py`; pick constants from the printed relevant/irrelevant similarity separation |
| embed runs off the 3s defer critical path | MEM-02 | Timing/behavior under a live interaction | Code review (recall after `defer()`) + manual `/ask` `/roast` confirming no "application did not respond" |
| stat × episode callback lands; empty-memory users see no change | MEM-06 | Subjective roast quality + occasional cadence | On the user's PC, accumulate a few memories then trigger roasts; confirm an occasional callback pairs a SQL stat with a recalled episode, and a memory-less user's prompt is unchanged |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or a declared Wave 0 dependency / manual-only justification
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (test_memory.py, test_database_phase11.py, spike script)
- [x] No watch-mode flags (all commands are one-shot `-q`)
- [x] Feedback latency < 40s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-29 (planning) — `wave_0_complete` flips true once 11-01 creates the scaffolds.
