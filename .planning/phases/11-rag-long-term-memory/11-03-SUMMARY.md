---
phase: 11-rag-long-term-memory
plan: "03"
subsystem: memory-retrieval
tags: [rag, embeddings, pgvector, gemini-embedding-001, pure-logic, tdd, asyncpg]

# Dependency graph
requires:
  - phase: 11-01
    provides: user_memories table + pgvector extension boot + Phase 11 config constants
  - phase: 11-02
    provides: spike-locked MEMORY_* retrieval constants (floor=0.70, top_k=8, inject_cap=3, rerank weights)
provides:
  - models/memory.py: MemoryFact frozen dataclass + apply_floor/recency_score/novelty_score/rerank pure functions
  - services/gemini.py: GeminiService.embed() + _embed_limiter (separate 60 RPM quota)
  - database.py: search_memories (scoped cosine ANN, user_id WHERE guard) + bump_surfaced
  - services/memory.py: MemoryService + MemoryService.recall() (full RAG read pipeline)
  - tests/test_memory.py: 31 pure-unit tests (23 scoring + 4 embed-limiter + 4 recall)
affects:
  - 11-04 (distill/remember write half — calls gemini.embed, database.insert_memory)
  - 11-05 (injection into personality/prompts.py build_chat_prompt, cogs/ai.py, cogs/events.py)
  - all consumers of MemoryService.recall() (ai.py, events.py, music.py)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TDD pure-logic seam: test file committed RED first (import error), implementation GREEN, no REFACTOR needed"
    - "Clock-injectable pure functions: recency_score(created_at, now) and novelty_score(last_surfaced_at, now) with injected now= parameter — no datetime.now() inside models/memory.py"
    - "Separate embedding limiter: _embed_limiter = _RateLimiter(max_requests=EMBED_RPM_LIMIT) on GeminiService; never acquire _rate_limiter in embed()"
    - "Cosine ANN with user_id scope: WHERE user_id = $1 fires before ORDER BY embedding <=> $2 — cross-user leakage impossible (T-11-03a / V4)"
    - "Graceful degrade chain: any error in recall() returns [] — never raises into roast/ask path (Pitfall 8)"
    - "skipif guard for TestRecallService: services.memory absent until Task 3 — importlib.util.find_spec used to auto-detect"

key-files:
  created:
    - models/memory.py (MemoryFact dataclass + 4 pure scoring functions)
    - services/memory.py (MemoryService with recall() full pipeline)
  modified:
    - services/gemini.py (embed() method + _embed_limiter in __init__)
    - database.py (search_memories + bump_surfaced helpers)
    - tests/test_memory.py (31 unit tests + skip guard + bug fix)

key-decisions:
  - "TDD commit sequence: RED test commit (d98a78c) before GREEN implementation — followed strictly to establish test-first discipline for the pure-logic seam"
  - "novelty_score formula: delta/(delta+1) — just-surfaced=0.0, never-surfaced=1.0, asymptotically recovers; satisfies D-05 anti-repeat constraint without a hard cutoff"
  - "recency_score formula: 1/(1+days) — created-now=1.0, decays hyperbolically; identical pattern to decay_predicate design in RESEARCH.md"
  - "Rule 1 (bug) auto-fix: asyncio.get_event_loop().run_until_complete() replaced with asyncio.run() in test_returns_empty_on_rate_limit_error — old pattern raised RuntimeError on closed loop in full pytest suite"
  - "skipif guard on TestRecallService: importlib.util.find_spec('services.memory') lets the test file collect cleanly across all three task commits without any skip-related noise after Task 3"
  - "guild_id param on recall() is reserved for future per-guild scoping; ANN currently scopes to user_id only — personal memories carry across servers (correct for taste/personality context)"

# Metrics
duration: 35min
completed: 2026-06-29
---

# Phase 11 Plan 03: Embedding + Retrieval Pipeline Summary

**Pure scoring seam (MemoryFact + rerank/recency/novelty/floor), GeminiService.embed() on a separate 60 RPM limiter, scoped cosine ANN DB helpers, and MemoryService.recall() — the complete RAG read half**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-06-29
- **Completed:** 2026-06-29
- **Tasks:** 3 (Task 1 TDD, Task 2 auto, Task 3 auto)
- **Files modified:** 5 (models/memory.py created, services/memory.py created, services/gemini.py, database.py, tests/test_memory.py)

## Accomplishments

- `models/memory.py`: MemoryFact frozen dataclass + `apply_floor`, `recency_score`, `novelty_score`, `rerank` — pure, deterministic, clock-injectable, no I/O anywhere in the module
- `services/gemini.py`: `_embed_limiter = _RateLimiter(EMBED_RPM_LIMIT)` added alongside existing `_rate_limiter`; `embed(texts, *, task_type, priority=2)` acquires exclusively `_embed_limiter` (never the 15 RPM chat budget); error handling mirrors `chat()`
- `database.py`: `search_memories` (cosine ANN scoped to `user_id`, `1-(embedding<=>$2) AS similarity`, `$N` parameterized); `bump_surfaced` (`UPDATE ... SET last_surfaced_at=now(), surface_count+=1 WHERE id=ANY($1)`)
- `services/memory.py`: `MemoryService.recall()` full pipeline — embed at priority=1, scoped ANN, apply_floor, rerank with 11-02 weights, cap to MEMORY_INJECT_CAP, bump_surfaced, return `[]` on any error path
- `tests/test_memory.py`: 31 tests — 23 pure scoring (TestApplyFloor, TestRecencyScore, TestNoveltyScore, TestRerank) + 4 embed-limiter static assertions (TestEmbedLimiter) + 4 recall mocked-service tests (TestRecallService); all 31 green in full suite

## Task Commits

Each task was committed atomically:

1. **Task 1 RED** (test file): `d98a78c` — `test(11-03): add failing tests for MemoryFact + pure scoring + recall`
2. **Task 1 GREEN** (implementation): `3b8a31c` — `feat(11-03): pure scoring seam — MemoryFact + rerank/recency/novelty/floor`
3. **Task 2** (embed + DB helpers): `b581e10` — `feat(11-03): GeminiService.embed() + _embed_limiter + search_memories/bump_surfaced`
4. **Task 3** (recall pipeline): `de0983b` — `feat(11-03): MemoryService.recall() — embed, ANN, floor, rerank, cap, bump surfaced`

## Files Created/Modified

- `models/memory.py` — 100 lines; MemoryFact frozen dataclass + 4 pure scoring functions
- `services/memory.py` — 132 lines; MemoryService with full recall() pipeline
- `services/gemini.py` — added `_embed_limiter` + `embed()` method (~60 lines added)
- `database.py` — added `search_memories` + `bump_surfaced` helpers (~70 lines added)
- `tests/test_memory.py` — expanded from 36 lines (scaffold) to 510 lines; 31 tests

## Decisions Made

- **TDD commit sequence preserved**: RED commit before GREEN commit — validates the test-first discipline for the pure-logic seam
- **novelty_score = delta/(delta+1)**: just-surfaced → 0.0, never-surfaced → 1.0, asymptotic recovery over time; satisfies D-05 without a hard reset cutoff
- **recency_score = 1/(1+days)**: hyperbolic decay; both scoring functions are in [0,1] and monotone — clean composition inside `rerank()`
- **guild_id reserved in recall()**: currently ANN scopes to `user_id` only; guild_id param reserved for future per-guild scoping (personal taste memories carry across servers)
- **skipif guard** on TestRecallService via `importlib.util.find_spec` lets the test file collect cleanly at every task boundary

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed asyncio.get_event_loop().run_until_complete() in test**
- **Found during:** Full test suite run after Task 3 commit (1 failure in 466+)
- **Issue:** `test_returns_empty_on_rate_limit_error` used deprecated `asyncio.get_event_loop().run_until_complete()` conditional — raises `RuntimeError: This event loop is already running` or similar on a closed loop when run after the full suite
- **Fix:** Replaced with `asyncio.run(run())` directly
- **Files modified:** `tests/test_memory.py`
- **Commit:** included in `de0983b`

## Threat Mitigations Applied (from threat_model)

| Threat ID | Mitigation | Where |
|-----------|-----------|-------|
| T-11-03a | `WHERE user_id = $1` before ANN ORDER BY — cross-user leakage impossible | `database.search_memories` |
| T-11-03b | `embed()` acquires `_embed_limiter` only, never `_rate_limiter`; static assert in tests | `services/gemini.py`, `tests/test_memory.py` |
| T-11-03c | `apply_floor` drops below-threshold facts; `recall()` returns `[]` when floor empty (Pitfall 8) | `models/memory.py`, `services/memory.py` |
| T-11-03d | All DB params are `$N` positional; `query_embedding` passed as typed list via pgvector codec | `database.py` |

## Known Stubs

None — all three tasks are fully implemented and tested. The `remember()` and `sweep()` methods are documented in the `services/memory.py` docstring as planned for 11-04 but are not stubs affecting this plan's goal.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced. All surface is internal (pool → Neon, GeminiService → Gemini API embedding endpoint) and covered by the plan's threat model.

## Self-Check: PASSED
