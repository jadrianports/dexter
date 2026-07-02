---
phase: 15-rag-reach
verified: 2026-07-03T03:00:00Z
status: human_needed
score: 4/4 must-haves verified (code-level); 1 live-DB proof + Discord-runtime items require human execution
overrides_applied: 0
gaps: []
human_verification:
  - test: "Run tests/test_database_phase15.py::test_remember_forget_recall_empty against a real pgvector-enabled Postgres (set TEST_DATABASE_URL, e.g. a Neon branch)"
    expected: "insert_memory -> search_memories returns 1 row -> delete_all_user_memories returns 1 -> search_memories returns [] (rows AND embeddings verifiably gone through the real ANN path)"
    why_human: "No TEST_DATABASE_URL / live pgvector Postgres is available in this verification environment (consistent with the existing Phase 11 live-DB test pattern, which also skips here). The test is structurally sound (correct helper calls, correct assertions, mirrors the proven Phase 11 shape) but has never actually executed successfully against a real database. This is RAG-04's Success Criterion 4 — the load-bearing proof."
  - test: "In a live Discord server, run /roast @someone-with-memory and confirm the roast is flavored by episodes recalled from that user's history (not the invoker's), and run /roast on a user with no memory to confirm graceful fallback"
    expected: "Roast reads as informed by real recalled history when memory exists; no crash/blank response when memory is empty"
    why_human: "Requires a live Gemini call + a live Discord gateway + pre-existing memory rows for a real user; cannot be exercised by unit mocks alone."
  - test: "Run /memory view as a user with several stored memories, and again as a user with zero. Confirm the embed renders verbatim facts, is ephemeral (only visible to the invoker), and paginates correctly with Previous/Next."
    expected: "Ephemeral, verbatim, in-character intro; empty-state line for a user with nothing stored; pagination buttons work and disable on timeout."
    why_human: "Ephemeral visibility, embed rendering, and button interaction timing are Discord-gateway behaviors that cannot be verified by mocks."
  - test: "Run /memory forget, press Confirm, and verify a subsequent /memory view (or direct DB check) shows the memories are actually gone. Also test Cancel and timeout paths leave memories intact."
    expected: "Confirm wipes all rows; Cancel and timeout leave memories untouched; count preview matches actual deleted count."
    why_human: "End-to-end Discord button-interaction flow against a live bot + live DB; the unit tests mock the DB layer, so this validates the real wiring end-to-end."
---

# Phase 15: RAG Reach Verification Report

**Phase Goal:** Long-term memory becomes directly visible and controllable — /roast and /ask are grounded in real recalled history, and a user can view and irreversibly erase what Dexter remembers about them.
**Verified:** 2026-07-03
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `/roast @user` grounds its roast in the target's own recalled history — never the invoker's — alongside the existing live SQL stat (RAG-01) | VERIFIED | `cogs/ai.py:210-220` — `roast_memories = await _memory_svc.recall(str(target.id), str(interaction.guild_id), scenario)`, unconditional (no cadence gate); `tests/test_ambient_recall_cadence.py::test_roast_always_recalls_target_scoped` asserts `call_args[0] == str(target.id)` and `!= str(interaction.user.id)`. Test passes. |
| 2 | `/ask` answers reflect the invoker's recalled memory when relevant, and produce a byte-identical prompt when no memory clears the floor (RAG-02) | VERIFIED | `cogs/ai.py:131-141` — `memories = await _memory_svc.recall(str(interaction.user.id), ...)`, unconditional; `personality/prompts.py:159-172` — `memory_context = ""` when `memories` is falsy (byte-identical guarantee unchanged from Phase 11). `tests/test_ambient_recall_cadence.py::test_ask_always_recalls_invoker_scoped` and `tests/test_prompts.py -k memory_block` (3 passed) both green. |
| 3 | A user can run `/memory` to see an in-character, read-only view of what Dexter remembers about them (RAG-03) | VERIFIED (code-level) | `cogs/memory.py::MemoryCog.memory_view` — verbatim facts (`facts = [row["fact"] for row in rows]`, no paraphrase), ephemeral (`ephemeral=True`), in-character intro, empty-state line, `MEMORY_MAX_PER_USER` cap (never `MEMORY_INJECT_CAP`), no target param. `tests/test_memory_command.py` (7 relevant tests) pass. Discord-rendering behavior (ephemeral visibility, pagination UX) needs a human/live check — see Human Verification. |
| 4 | A user can run `/memory forget` to delete their stored memories, and the rows AND embeddings are verifiably gone — later recall no longer returns them (RAG-04) | VERIFIED (code-level) / UNPROVEN live | `database.delete_all_user_memories` — real hard `DELETE FROM user_memories WHERE user_id = $1`, single-identity-param signature locked by `inspect.signature` test; `cogs/memory.py::ForgetConfirmView` — count preview, danger-styled Confirm/Cancel, `_used` guard, empty-state skip. `tests/test_memory_command.py` (confirm-deletes / cancel-leaves-intact) pass with mocked DB. The load-bearing **live-DB** proof (`test_remember_forget_recall_empty`, re-querying via the real `search_memories` ANN path) is structurally correct but SKIPPED in this environment (`TEST_DATABASE_URL` unset) — it has never actually run against a real pgvector Postgres. Per phase-close note in `15-01-PLAN.md`/`15-01-SUMMARY.md`, this is an acknowledged outstanding item, not a code gap. |

**Score:** 4/4 truths verified at the code level; 1 of them (RAG-04) has an unexecuted live-DB proof that must be run before the phase can be considered fully closed.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `database.py::list_user_memories` | display-ordered, user-scoped SELECT, `LIMIT $2` | VERIFIED | `WHERE user_id = $1`, `ORDER BY salience DESC, created_at DESC`, bound params only. |
| `database.py::delete_all_user_memories` | single-param nuke-all DELETE, returns rows-deleted int | VERIFIED | `DELETE FROM user_memories WHERE user_id = $1`; signature `(pool, user_id)` exactly, locked by test. |
| `tests/test_database_phase15.py` | static + live-DB proof | VERIFIED (static) / SKIPPED (live) | 6 static tests pass; live test skips cleanly (no `TEST_DATABASE_URL`), never executed against real pgvector. |
| `cogs/ai.py` (`/ask`, `/roast`) | cadence gate removed, scoping unchanged | VERIFIED | Exactly 2 remaining `MEMORY_CALLBACK_CHANCE` refs in `cogs/` (events.py, music.py only); `cogs/ai.py` has neither the gate nor `import random`. |
| `tests/test_ambient_recall_cadence.py` | four-site regression lock | VERIFIED | 5 tests, all pass (source-inspection + behavioral). |
| `cogs/memory.py` | `MemoryCog`, `MemoryPageView`, `ForgetConfirmView` | VERIFIED (exists, substantive, wired) | See Data-Flow Trace below; also see Anti-Patterns for 3 unresolved code-review warnings. |
| `bot.py` cog registration | `cogs.memory` at both load sites | VERIFIED | `grep -c "cogs.memory" bot.py` = 2 (line 442 tuple, line 1126 first-run load). |
| `config.py::MEMORY_VIEW_PAGE_SIZE` | new knob, default 10 | VERIFIED | Present at config.py:177, beside the Phase 11 MEMORY_* block; no other new knob added. |
| `tests/test_memory_command.py` | view + forget handler coverage | VERIFIED | 8 tests, all pass. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `cogs/ai.py` `/roast` | `memory_service.recall` | `recall(str(target.id), ...)` unconditional | WIRED | Confirmed by source read + passing behavioral test. |
| `cogs/ai.py` `/ask` | `memory_service.recall` | `recall(str(interaction.user.id), ...)` unconditional | WIRED | Confirmed by source read + passing behavioral test. |
| `cogs/events.py` / `cogs/music.py` | `config.MEMORY_CALLBACK_CHANCE` | retained random gate | WIRED (unchanged) | `git diff` for this phase touches neither file; grep confirms exactly 2 remaining refs, both here. |
| `MemoryCog.memory_view` | `database.list_user_memories` | `limit=config.MEMORY_MAX_PER_USER` | WIRED | Source + test (`test_memory_view_uses_max_per_user_cap`) confirm the cap argument. |
| `ForgetConfirmView.confirm_button` | `database.delete_all_user_memories` | `delete_all_user_memories(self.bot.pool, self.user_id)` | WIRED | Source + test (`test_forget_confirm_deletes`) confirm call with `(bot.pool, user_id)`. |
| `bot.py` | `cogs.memory` | `load_extension` at both sites | WIRED | Confirmed at bot.py:442 and bot.py:1126. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `MemoryPageView` (`/memory view`) | `facts` / `pages` | `database.list_user_memories(pool, user_id=..., limit=MEMORY_MAX_PER_USER)` → real `SELECT ... FROM user_memories` | Yes — plain SQL SELECT, not a static stub | FLOWING |
| `ForgetConfirmView` count preview | `count` | `database.count_user_memories(pool, user_id)` → real SQL count | Yes | FLOWING |
| `ForgetConfirmView.confirm_button` deletion | `deleted` | `database.delete_all_user_memories(pool, user_id)` → real `DELETE ... WHERE user_id = $1` | Yes | FLOWING |
| `/ask` / `/roast` `memories` | `memories` / `roast_memories` | `MemoryService.recall(...)` → real ANN `search_memories` against `user_memories` | Yes (code path); not exercised against a live model/DB in this verification pass | FLOWING (code); UNVERIFIED live |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full regression suite green | `pytest tests/ -q` | 781 passed, 106 skipped, 0 failed | PASS |
| Phase-15 test files green | `pytest tests/test_database_phase15.py tests/test_ambient_recall_cadence.py tests/test_memory_command.py -q` | 20 passed, 1 skipped (live-DB) | PASS |
| RAG-02 byte-identical guarantee unchanged | `pytest tests/test_prompts.py -k memory_block -q` | 3 passed | PASS |
| Cog imports cleanly | `python -c "import cogs.memory; import bot; import cogs.ai"` | No output / exit 0 | PASS |

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` probes exist for this phase; none declared in PLAN/SUMMARY. SKIPPED (no runnable probes for this phase type).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| RAG-01 | 15-02 | `/roast` grounds in target's recalled history, never invoker's | SATISFIED | `cogs/ai.py:210-220` + `test_roast_always_recalls_target_scoped` |
| RAG-02 | 15-02 | `/ask` incorporates invoker's recalled memory; byte-identical when floor not cleared | SATISFIED | `cogs/ai.py:131-141`, `personality/prompts.py:159-172`, `test_ask_always_recalls_invoker_scoped`, `test_prompts.py -k memory_block` |
| RAG-03 | 15-01, 15-03 | `/memory` view, in-character, read-only | SATISFIED (code) / NEEDS HUMAN (live UX) | `cogs/memory.py::memory_view`, `tests/test_memory_command.py` |
| RAG-04 | 15-01, 15-03 | `/memory forget` deletes rows + embeddings, verified | SATISFIED (code) / NEEDS HUMAN (live-DB SC4 proof unexecuted) | `database.delete_all_user_memories`, `cogs/memory.py::ForgetConfirmView`, `tests/test_database_phase15.py::test_remember_forget_recall_empty` (skipped locally) |

No orphaned requirements — REQUIREMENTS.md maps exactly RAG-01..04 to Phase 15, and all four appear across the three plans' `requirements:` frontmatter.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `cogs/memory.py` | 143-164 (`ForgetConfirmView.confirm_button`) | No `try/except` around `database.delete_all_user_memories` after `interaction.response.defer()` | WARNING (WR-01, from 15-REVIEW.md, unresolved) | If the DELETE raises (pool exhaustion, Neon cold-start), the deferred interaction never gets a followup — the user sees a permanently "thinking..." state with no confirmation of whether their data was wiped. This is the single feature branded as "the trust escape hatch," so a silent failure mode here undercuts the goal's trust intent. |
| `cogs/memory.py` | 236-241 (`memory_view`'s initial `send_message`) | Missing `allowed_mentions=discord.AllowedMentions.none()` on the first-page send (present only on `prev_button`/`next_button` edits) | WARNING (WR-02, from 15-REVIEW.md, unresolved) | The module docstring claims T-15-11 ("`MemoryPageView` edits use `AllowedMentions.none()` as defense-in-depth") is fully mitigated, but the very first page — the one every user sees by default — lacks it. Documentation/threat-model claim is broader than what the code actually does. |
| `cogs/memory.py` | 44-56 (`_chunk_facts_into_pages`) | Pagination chunks by fact **count** (`MEMORY_VIEW_PAGE_SIZE=10`), not character budget, unlike the analog `LyricsPageView`/`chunk_lyrics` it's explicitly modeled on | WARNING (WR-03, from 15-REVIEW.md, unresolved) | Nothing in code enforces a max fact length (only a soft LLM instruction in `DISTILL_PROMPT`); an unusually long fact set could exceed Discord's 4096-char embed limit and raise `discord.HTTPException`, breaking `/memory view` for that page. |
| — | — | `ForgetConfirmView.count` stored but never read (`IN-01`, info-level, from 15-REVIEW.md) | INFO | Dead attribute; cosmetic only. |

**Debt-marker gate:** No `TBD`/`FIXME`/`XXX` found in any Phase 15 file — clean.

All three WARNING items were identified by this phase's own code review (`15-REVIEW.md`, `status: issues_found`, committed at `0476206`) and **remain unfixed** — `git log` shows no commit after the review that touches `cogs/memory.py`. The SUMMARY.md files do not mention these outstanding warnings at all; they were only surfaced by reading `15-REVIEW.md` directly, which is exactly the kind of gap this verification process exists to catch. None of them are severe enough to invalidate the phase's core observable truths (the happy path for view/forget genuinely works and is test-locked), but they represent known, documented, unaddressed quality debt in the exact command family the phase goal is built around ("trust escape hatch").

### Human Verification Required

### 1. Live-DB RAG-04 Success Criterion 4 proof

**Test:** Set `TEST_DATABASE_URL` to a pgvector-enabled Postgres (e.g., a Neon branch) and run `pytest tests/test_database_phase15.py -x -q`.
**Expected:** `test_remember_forget_recall_empty` passes — insert, confirm via `search_memories` (1 row), delete, re-confirm via `search_memories` (`[]`).
**Why human:** No live pgvector database is reachable in this verification environment; the test has never actually executed to completion (only collected/skipped). This is the specific proof RAG-04 and Phase 16 hard-depend on.

### 2. Live Discord `/roast` grounding check

**Test:** In a live server, `/roast` a user with existing memory rows, and separately a user with none.
**Expected:** Roast is visibly informed by recalled episodes when present; no crash or blank output when absent.
**Why human:** Requires live Gemini + live Discord gateway + real seeded memory data.

### 3. Live Discord `/memory view` UX check

**Test:** Run `/memory view` as users with many facts, few facts, and zero facts.
**Expected:** Ephemeral, verbatim, correctly paginated, in-character empty state.
**Why human:** Ephemeral visibility and Discord embed/button rendering cannot be verified by mocks.

### 4. Live Discord `/memory forget` end-to-end check

**Test:** Run `/memory forget`, test Confirm, Cancel, and timeout paths; verify actual deletion afterward.
**Expected:** Confirm truly deletes; Cancel/timeout leave data untouched; count preview matches reality.
**Why human:** Full button-interaction round trip against a live bot + live DB.

### Gaps Summary

No must-have truth outright FAILED — all four RAG requirements have working, tested code, and no requirement is orphaned. The phase is withheld from a clean `passed` status for two reasons:

1. **RAG-04's load-bearing live-DB proof has never actually run against a real pgvector database** in any environment so far (per the phase's own SUMMARY, this was known and deferred at plan-close, consistent with the Phase 11 precedent). This is the single most important proof in the phase (Phase 16 hard-depends on it) and must be executed before the phase is truly closed, not just written.
2. **Three code-review WARNINGs (WR-01, WR-02, WR-03) from `15-REVIEW.md` remain unresolved** in the exact "/memory forget" trust-escape-hatch code path. None of them break the happy path, but WR-01 (no failure handling on the irreversible delete) is a meaningful robustness gap for a feature whose entire purpose is giving users confident, verifiable control over their data. These were not mentioned in any SUMMARY.md and would have been missed without reading `15-REVIEW.md` directly.

Recommendation: run the live-DB test against a real pgvector instance, and either fix WR-01/WR-02/WR-03 (small, well-scoped patches already drafted in `15-REVIEW.md`) or explicitly override them with a documented reason before closing the phase.

---

_Verified: 2026-07-03_
_Verifier: Claude (gsd-verifier)_
