---
phase: 11-rag-long-term-memory
plan: "06"
subsystem: memory-injection
tags: [rag, prompt-engineering, recall, roast-surfaces, tdd, personality, mem-06]

# Dependency graph
requires:
  - phase: 11-03
    provides: MemoryService.recall() — embed, ANN, floor, rerank, bump pipeline
  - phase: 11-05
    provides: distill/distill_and_remember write pipeline; number-free atomic facts
provides:
  - personality/prompts.py: build_chat_prompt(memories=...) kwarg + {memory_context} slot
  - cogs/ai.py: recall wired into /ask and /roast (occasional cadence gate)
  - cogs/events.py: recall wired into _generate_ambient_roast
  - cogs/music.py: recall wired into _build_roast_line
affects:
  - 11-07 (memory sweep / expiry — next plan)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TDD commit sequence: RED test commit (e3ce95f) before GREEN implementation (4581654) — test-first for the pure-logic seam"
    - "Backward-compatible kwarg: memories: list[str] | None = None as last param — all 4 existing callers unchanged"
    - "{memory_context} slot: placed as {memory_context}{seasonal_context} in template — empty string is byte-identical, non-empty ends with \\n\\n for blank-line spacing"
    - "Cadence gate: random.random() < MEMORY_CALLBACK_CHANCE (0.35) at all four surfaces — keeps callbacks rare (D-04)"
    - "Getattr guard: getattr(self.bot, 'memory_service', None) at every recall site — graceful degrade when memory_service absent"
    - "Try/except non-fatal: any recall() exception degrades to [] — never raises into roast/ask path"
    - "Accuracy firewall: candidate-ammo block pins all numbers/counts to USER CONTEXT (live SQL), never from memories (D-06 / T-11-06b)"

key-files:
  created: []
  modified:
    - personality/prompts.py (memories= kwarg + {memory_context} slot in DEXTER_SYSTEM_PROMPT)
    - cogs/ai.py (recall in /ask + /roast with cadence gate)
    - cogs/events.py (recall in _generate_ambient_roast)
    - cogs/music.py (import random + recall in _build_roast_line)
    - tests/test_prompts.py (7 new memory tests + 2 updated placeholder tests, 23 total passing)

key-decisions:
  - "memory_context slot uses {memory_context}{seasonal_context} (no extra newline in template) + non-empty block ends with \\n\\n — cleanest byte-identity guarantee for the empty-string fallback"
  - "Cadence gate applied at each surface independently (not centralized) — each roast function rolls independently so recall probability is per-roast not per-session"
  - "_build_roast_line passes guild_id='' to recall — guild_id is reserved in recall() and the ANN only scopes to user_id; personal memories are intentionally cross-server"
  - "All four roast surfaces use memories or None (not memories directly) — coerces empty list to None so the byte-identity path is taken when recall returns []"

# Metrics
duration: 10min
completed: 2026-06-29
---

# Phase 11 Plan 06: Memory Injection into Personality Prompts Summary

**build_chat_prompt(memories=...) backward-compatible kwarg + {memory_context} accuracy-safe slot + recall wired at all four roast surfaces behind an occasional cadence gate — the stat x episode callback can now land**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-06-29T13:39:12Z
- **Completed:** 2026-06-29T13:49:00Z
- **Tasks:** 3 (Task 1 TDD, Task 2 auto, Task 3 auto)
- **Files modified:** 5 (personality/prompts.py, cogs/ai.py, cogs/events.py, cogs/music.py, tests/test_prompts.py)

## Accomplishments

- `personality/prompts.py`: Added `memories: list[str] | None = None` as the last parameter of `build_chat_prompt`. Added `{memory_context}` slot to `DEXTER_SYSTEM_PROMPT` between `{user_context}` and `{seasonal_context}` using the template pattern `{memory_context}{seasonal_context}` — empty string is byte-identical to pre-Phase-11 output (T-11-06d). Non-empty block emits a candidate-ammo sub-block: episodes/opinions header, bulleted facts, and the accuracy firewall instruction ("All numbers/counts come from USER CONTEXT above — never from these memories").
- `cogs/ai.py`: Wired recall into `/ask` (recall anchor = question text, user = invoker) and `/roast` (recall anchor = scenario, user = target). Both surfaces: cadence gate (`random.random() < MEMORY_CALLBACK_CHANCE`), `getattr` guard, try/except non-fatal degrade, `memories=memories or None` passed to `build_chat_prompt`.
- `cogs/events.py`: Wired recall into `_generate_ambient_roast` — cadence gate + `member.id` + formatted scenario as anchor. Same guard/degrade/pass pattern.
- `cogs/music.py`: Added `import random`. Wired recall into `_build_roast_line` — cadence gate + `user_id` + `scenario_content` as anchor. `guild_id=""` passed because recall's ANN scopes to user_id only.
- `tests/test_prompts.py`: Added `TestBuildChatPromptMemories` (7 tests: byte-identity for None, byte-identity for [], fact rendering, USER CONTEXT anchor, never-instruction, no-triple-newline for None, no-triple-newline for block). Updated `test_contains_all_format_placeholders` (5 tokens) and `test_build_chat_prompt_no_unfilled_placeholders` (5 keys). 23 tests pass.

## Task Commits

1. **Task 1 RED** (test file): `e3ce95f` — `test(11-06): add failing tests for build_chat_prompt memories= kwarg (RED)`
2. **Task 1 GREEN** (implementation): `4581654` — `feat(11-06): build_chat_prompt(memories=...) + {memory_context} slot in DEXTER_SYSTEM_PROMPT`
3. **Task 2** (ai.py recall): `bbf27b5` — `feat(11-06): wire recall into /ask and /roast — occasional cadence gate (MEM-06)`
4. **Task 3** (events + music recall): `06f6815` — `feat(11-06): wire recall into ambient roasts and music notable-event roasts (MEM-06)`

## Files Created/Modified

- `personality/prompts.py` — memories= kwarg + {memory_context} slot + candidate-ammo block builder (~30 lines added)
- `cogs/ai.py` — recall in /ask + /roast (~35 lines added)
- `cogs/events.py` — recall in _generate_ambient_roast (~15 lines added)
- `cogs/music.py` — import random + recall in _build_roast_line (~20 lines added)
- `tests/test_prompts.py` — 7 new memory tests + 2 updated tests (~61 lines added, 8 lines updated)

## Decisions Made

- **{memory_context}{seasonal_context} template pattern**: Using `{memory_context}{seasonal_context}` (no newline between slots in the template) with the memory block ending in `\n\n` when non-empty cleanly preserves byte-identity for empty string and avoids triple-newline artifacts in all combinations.
- **Per-surface cadence roll**: Each roast function rolls independently — consistent with the "occasional payoff" design (D-04) and simpler than centralizing the gate.
- **guild_id="" in _build_roast_line**: `_build_roast_line` doesn't receive guild_id; passing "" is safe because recall's ANN scopes to user_id only (guild_id is reserved for future per-guild scoping per 11-03 design).
- **memories or None coercion**: Using `memories or None` (not bare `memories`) ensures the byte-identical path is taken when recall returns [] — no empty candidate-ammo block is emitted.

## Deviations from Plan

None — plan executed exactly as written.

## Threat Mitigations Applied (from threat_model)

| Threat ID | Mitigation | Where |
|-----------|-----------|-------|
| T-11-06a | Candidate-ammo framing in {memory_context} block: "use at most one, only if it genuinely lands; do not invent"; model may NOOP; distiller already constrained facts to atomic third-person (11-05) | `personality/prompts.py:build_chat_prompt` |
| T-11-06b | Accuracy firewall in block: "All numbers/counts come from USER CONTEXT above — never from these memories"; number-free facts guaranteed by 11-05 | `personality/prompts.py:build_chat_prompt` |
| T-11-06c | recall() passes single scoped user_id; search_memories WHERE user_id guard prevents cross-user leakage (11-03 V4) | `services/memory.py:recall`, `database.search_memories` |
| T-11-06d | memories=None renders byte-identical (regression tests: test_memories_none_byte_identical + test_memories_empty_list_byte_identical); all 4 callers compile unchanged | `tests/test_prompts.py` |

## Known Stubs

None — all three tasks fully implemented and verified. The manual live-verification (trigger a roast for a user with stored memories and confirm the stat x episode callback) is tracked in 11-VALIDATION Manual-Only, requires live Neon + stored memories for the target user, and cannot be automated.

## Threat Flags

None — no new network endpoints, auth paths, schema changes, or trust boundaries introduced. All changes are prompt engineering (personality/prompts.py) and existing Gemini chat path wiring (cogs/). The recall() call goes through the already-established MemoryService → GeminiService.embed() → Neon path.

## Self-Check: PASSED
