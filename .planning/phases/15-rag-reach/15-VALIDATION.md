---
phase: 15
slug: rag-reach
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-03
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `15-RESEARCH.md` §"Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (`@pytest.mark.asyncio`) |
| **Config file** | none dedicated — directory-wide convention (`pytest tests/`) |
| **Quick run command** | `pytest tests/test_memory_command.py tests/test_ambient_recall_cadence.py tests/test_prompts.py -x` |
| **Full suite command** | `pytest tests/ -x` |
| **Estimated runtime** | ~30–60 seconds (live-DB tests auto-skip when `TEST_DATABASE_URL` unset) |

---

## Sampling Rate

- **After every task commit:** Run the quick command (fast, mock-only, no live DB)
- **After every plan wave:** Run `pytest tests/ -x` (full suite)
- **Before `/gsd-verify-work`:** Full suite must be green **AND** the Success Criterion 4
  integration test (`test_remember_forget_recall_empty`) MUST have run at least once against a
  real pgvector-enabled Postgres — it is the load-bearing proof for RAG-04 and cannot be
  considered verified from a skipped-static-only run.
- **Max feedback latency:** ~60 seconds

---

## Per-Requirement Verification Map

*(Task IDs assigned by gsd-planner; rows below are the requirement-level contract the plans must satisfy.)*

| Requirement | Behavior | Test Type | Automated Command | File Exists |
|-------------|----------|-----------|-------------------|-------------|
| RAG-01 | `/roast @user` recall fires unconditionally (35% gate removed) | unit | `pytest tests/test_roast_command.py::test_roast_recall_always_fires -x` | ❌ W0 |
| RAG-01 | `/roast` recall scoped to `target.id`, never `interaction.user.id` | unit | `pytest tests/test_roast_command.py::test_roast_recall_scoped_to_target -x` | ❌ W0 |
| RAG-02 | `/ask` recall fires unconditionally (35% gate removed) | unit | `pytest tests/test_ask_command.py::test_ask_recall_always_fires -x` | ❌ W0 |
| RAG-02 | Byte-identical prompt when `recall()` returns `[]` | unit | `pytest tests/test_prompts.py -k memory_block -x` | ✅ (pre-existing lock — must stay green) |
| RAG-01/02 regression | Ambient surfaces (`cogs/events.py:128`, `cogs/music.py:1272`) KEEP their 35% gate | unit | `pytest tests/test_ambient_recall_cadence.py -x` | ❌ W0 |
| RAG-03 | `/memory view` shows verbatim facts; empty state in-character; ephemeral | unit | `pytest tests/test_memory_command.py -k memory_view -x` | ❌ W0 |
| RAG-03 | `list_user_memories` scoped to `user_id`, ordered, capped at `MEMORY_MAX_PER_USER` | static-source + live-DB | `pytest tests/test_database_phase15.py -k list_user_memories -x` | ❌ W0 |
| RAG-04 | `/memory forget` count preview + confirm/cancel/timeout (JamSuggestConfirmView shape) | unit | `pytest tests/test_memory_command.py::test_forget_confirm_flow -x` | ❌ W0 |
| RAG-04 | **"Verifiably gone" — rows AND embeddings** (Success Criterion 4) | **live-DB integration** | `pytest tests/test_database_phase15.py::test_remember_forget_recall_empty -x` | ❌ W0 |

---

## Wave 0 Requirements

- [ ] `tests/test_ambient_recall_cadence.py` — NEW. Locks the `MEMORY_CALLBACK_CHANCE` gate:
      ambient call sites (`cogs.events`, `cogs.music`) must NOT call `recall()` when
      `random.random()` is patched above 0.35; explicit call sites (`/ask`, `/roast`) MUST call
      `recall()` regardless. Closes the Open Question 2 gap (no pre-existing gate lock).
- [ ] `tests/test_memory_command.py` — NEW. `/memory view` + `/memory forget` handlers, following
      `tests/test_roast_command.py` fake-bot/fake-interaction convention.
- [ ] `tests/test_database_phase15.py` — NEW. Two halves mirroring `tests/test_database_phase11.py`:
      static source-inspection class (`list_user_memories`/`delete_all_user_memories` exist,
      `user_id`-scoped, bound `$N`, `delete_all_user_memories` has NO second id param) + live-DB
      integration class with the `remember → forget → recall == []` Success Criterion 4 test.
- [ ] Framework install: none — pytest/pytest-asyncio already present.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| In-character feel of `/memory view` intro/outro + `/memory forget` "wounded" acknowledgement | RAG-03 / RAG-04 | Subjective personality feel is not machine-assertable | Run `/memory` then `/memory forget` in Discord; confirm verbatim facts shown, ephemeral, and forget acknowledgement reads in-character (parked behind live host per milestone UAT tail) |

*All load-bearing behaviors have automated verification; only personality feel is manual.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] Success Criterion 4 integration test run once against real pgvector Postgres
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
