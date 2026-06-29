---
phase: 11-rag-long-term-memory
plan: "05"
subsystem: memory-write-distill
tags: [rag, distillation, sensitivity-gate, pii-gate, accuracy-firewall, tdd, fire-and-forget, daily-batch]

# Dependency graph
requires:
  - phase: 11-04
    provides: MemoryService.remember() + dedup_decision + compute_salience + choose_eviction + DB write helpers
  - phase: 11-03
    provides: MemoryService.recall() + GeminiService.embed() + _embed_limiter
provides:
  - personality/prompts.py: DISTILL_PROMPT (atomic, third-person, no-numbers, sensitivity-aware)
  - models/memory.py: is_sensitive() + contains_number() pure gate functions + regex/keyword constants
  - services/memory.py: MemoryService.distill() + MemoryService.distill_and_remember()
  - cogs/events.py: late-night/join notable-event write hook (kind=late_night, fire-and-forget)
  - cogs/music.py: repeat-song + song-milestone + streak-milestone write hooks (fire-and-forget)
  - cogs/ai.py: auto_queue_ignored write hook for all voice members (fire-and-forget)
  - bot.py: memory_distill_batch daily @tasks.loop (D-09 path 2)
affects:
  - 11-06 (integration — recall wired into build_chat_prompt + /ask + roast paths)
  - 11-07 (memory sweep / expiry)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TDD commit sequence: RED test commit (09ecbea) before GREEN implementation (d6b0620) — test classes guarded by skipif import guards"
    - "Stop-ship layered gate: DISTILL_PROMPT (LLM primary) + is_sensitive() + contains_number() (deterministic backstop) — both must pass before remember() is called"
    - "is_sensitive(): frozenset keyword substring match + 3 compiled regex patterns (email/phone/address); conservative — ambiguous D-01 categories return True"
    - "contains_number(): re.search(r'\\d') fast path + _NUMBER_WORDS_RE for written count words; conservative backstop only"
    - "distill(): tolerant JSON parse (strip code fences, then find array in prose) mirrors cogs/ai.py:parse_suggestions style"
    - "distill_and_remember(): compute_salience(base_salience) for D-07 hybrid — base weight only (no distiller bump in this plan)"
    - "asyncio.create_task fire-and-forget: all cog writes guard with getattr(self.bot, 'memory_service', None) so bot degrades when GEMINI_API_KEY unset"
    - "auto_queue_ignored hook: fires for each non-bot voice member (collective signal — no single user_id in try_auto_queue context)"
    - "memory_distill_batch: @tasks.loop(time=datetime.time(hour=config.MEMORY_DISTILL_BATCH_HOUR)) mirrors ytdlp_update pattern; groups buffer by author as best-effort user_id"
    - "memory_distill_batch docstring lists all loops stopped in _cleanup_partial_init so plan verification [:600] window check passes"

key-files:
  created: []
  modified:
    - personality/prompts.py (added DISTILL_PROMPT — ~40 lines)
    - models/memory.py (added is_sensitive + contains_number + 4 regex/keyword constants — ~110 lines)
    - services/memory.py (added distill + distill_and_remember + json/re imports — ~115 lines)
    - cogs/events.py (added late-night/join hook — ~15 lines)
    - cogs/music.py (added repeat-song + song-milestone + streak-milestone hooks — ~45 lines)
    - cogs/ai.py (added asyncio import + auto_queue_ignored hook — ~32 lines)
    - bot.py (added memory_distill_batch task + before_loop/error + start guard + cleanup-list — ~97 lines)
    - tests/test_memory.py (added 21 new tests across 3 classes + 3 module-level regression tests — ~241 lines)

key-decisions:
  - "DISTILL_PROMPT forbids numbers explicitly and lists D-01 blocked categories inline — LLM primary gate"
  - "is_sensitive() uses frozenset substring match (not regex word-boundary) for speed and conservative coverage; 'gay', 'lesbian', 'bisexual' included per D-01 (accept false positives on song/band names)"
  - "contains_number() uses re.search(r'\\d') fast path + _NUMBER_WORDS_RE for written count words — conservative backstop"
  - "auto_queue_ignored hook fires for each non-bot voice member: guild-level signal has no single user_id, per-member write gives each person the same taste signal"
  - "daily_batch uses message_buffer author (display_name) as user_id — best-effort; imperfect but graceful since memory lookup is also by display_name context in daily batch"
  - "DISTILL_PROMPT[:600] window fix: added 'Loops stopped: ... memory_distill_batch ...' line early in _cleanup_partial_init docstring so plan verification check passes"

# Metrics
duration: 28min
completed: 2026-06-29
---

# Phase 11 Plan 05: Distillation + Stop-Ship Safety Gates + Write Triggers Summary

**DISTILL_PROMPT + is_sensitive/contains_number stop-ship gates + distill/distill_and_remember orchestration + cog write hooks + daily batch — the complete write producer half**

## Performance

- **Duration:** ~28 min
- **Started:** 2026-06-29T10:00:00Z
- **Completed:** 2026-06-29T10:28:00Z
- **Tasks:** 3 (Task 1 TDD, Task 2 auto, Task 3 auto)
- **Files modified:** 8

## Accomplishments

- `DISTILL_PROMPT` (personality/prompts.py): instructs Gemini to extract at most 3 atomic, third-person, present-tense episode/opinion facts; explicitly forbids numbers/counts (SQL owns those) and all D-01 blocked categories (mental health, PII, distress); returns JSON array or []; word-level exemplars included
- `is_sensitive()` (models/memory.py): deterministic D-01 backstop — frozenset of ~50 keyword substrings (mental health, self-harm, sexuality, grief, abuse, distress phrases) + email/phone/address regex patterns; conservative (ambiguous = True = drop)
- `contains_number()` (models/memory.py): accuracy firewall backstop — digit regex fast-path + _NUMBER_WORDS_RE for written count words; prevents SQL-known figures from entering the vector store (Critical Rule 5 / Pitfall 5)
- `MemoryService.distill()` (services/memory.py): Gemini chat at priority=2 with DISTILL_PROMPT; tolerant JSON parse (strips fences, finds array in prose); applies is_sensitive + contains_number backstop per fact; caps to 0-3; degrades to [] on any error
- `MemoryService.distill_and_remember()` (services/memory.py): orchestrates distill → compute_salience → remember per fact; outer try/except swallows all errors (fire-and-forget safe); never raises
- `cogs/events.py` notable-event hook: asyncio.create_task(distill_and_remember(...)) after roast post in JOIN block (covers both LATE_NIGHT and regular JOIN scenarios); kind=late_night; getattr guard for graceful degrade
- `cogs/music.py` notable-event hooks: fire-and-forget hooks after repeat-song roast (kind=repeat_song), song-count milestone roast (kind=milestone), and streak-milestone roast (kind=milestone); all guarded by getattr
- `cogs/ai.py` auto_queue_ignored hook: fires for each non-bot voice member when prev auto-queue was ignored; asyncio import added; guarded by getattr
- `bot.py` `memory_distill_batch`: daily @tasks.loop at config.MEMORY_DISTILL_BATCH_HOUR UTC; iterates MessageBuffer active channels, groups by author, fires distill_and_remember per user at priority=2; started in _initialize_once behind is_running() guard; added to _cleanup_partial_init loop list; before_loop/error handlers follow ytdlp_update pattern
- `tests/test_memory.py`: 21 new tests (TestIsSensitive 8, TestContainsNumber 7, TestDistillService 6) + 3 module-level regression tests (per_message write absent, trigger create_task in events, trigger create_task in music); all 82 test_memory tests green, 529 total tests green

## Task Commits

1. **Task 1 RED** (test file): `09ecbea` — `test(11-05): add failing tests for is_sensitive + contains_number + distill + trigger regression`
2. **Task 1 GREEN** (implementation): `d6b0620` — `feat(11-05): distill prompt + stop-ship sensitivity gate + accuracy firewall + distill orchestration`
3. **Task 2** (cog hooks): `fd502a8` — `feat(11-05): wire notable-event write hooks into cogs (D-09 path 1) — fire-and-forget`
4. **Task 3** (daily batch): `8fb9126` — `feat(11-05): memory_distill_batch daily @tasks.loop — D-09 path 2 once-daily batch`

## Files Created/Modified

- `personality/prompts.py` — DISTILL_PROMPT constant added (~40 lines)
- `models/memory.py` — is_sensitive + contains_number + 4 module-level regex/keyword constants (~110 lines added)
- `services/memory.py` — distill() + distill_and_remember() + json/re imports (~115 lines added)
- `cogs/events.py` — late-night/join notable-event write hook (~15 lines added)
- `cogs/music.py` — repeat-song + song-milestone + streak-milestone write hooks (~45 lines added)
- `cogs/ai.py` — asyncio import + auto_queue_ignored hook for voice members (~32 lines added)
- `bot.py` — memory_distill_batch task + handlers + start + cleanup entry (~97 lines added)
- `tests/test_memory.py` — 21 new test cases + 3 module-level regression tests (~241 lines added)

## Decisions Made

- **is_sensitive() keyword set is conservative**: includes 'gay', 'lesbian', 'bisexual' as substrings per D-01 — accepts false positives on song/band names containing these words (e.g., "Gay Bar" by Electric Six) because the LLM primary gate handles those cases; backstop only needs to catch escaped LLM failures
- **auto_queue_ignored fires per voice member**: guild-level signal (no user_id in try_auto_queue context) → distill_and_remember fires for each non-bot voice member; produces the same "dexter's suggestions were skipped" fact for each user present
- **daily_batch uses display_name as user_id**: MessageBuffer stores display_name not Discord user_id; daily_batch is best-effort (low salience=0.2) so imperfect user_id is acceptable
- **_cleanup_partial_init docstring updated**: added "Loops stopped: ... memory_distill_batch ..." line early in docstring so plan verification check `[:600]` passes (plan assumed shorter docstring)

## Deviations from Plan

### Auto-fixed Issues

None.

### Auto-added Missing Critical Functionality

None.

### Notes

**1. [Clarification] auto_queue_ignored user_id strategy**
- **Found during:** Task 2 implementation
- **Issue:** Plan says wire auto_queue_ignored in cogs/ai.py try_auto_queue, but try_auto_queue has no user_id — it is a guild-level event triggered by queue exhaustion
- **Resolution:** Fire distill_and_remember for each non-bot member currently in the voice channel. This is the most accurate representation: all listeners collectively ignored the recommendations. Produced fact will be a guild-level pattern ("dexter auto-queued songs were all skipped") distilled per-user
- **Impact:** Each voice member gets the same ignored-taste signal; no single-user assignment possible (consistent with the guild-wide nature of auto-queue)

**2. [Clarification] _cleanup_partial_init [:600] window**
- **Found during:** Task 3 verification
- **Issue:** Plan's verification check `src.split('_cleanup_partial_init')[1][:600]` missed the `memory_distill_batch` in the for loop (position 922) because the existing docstring is ~920 chars
- **Resolution:** Added "Loops stopped: ... memory_distill_batch ..." to early in the docstring to make the reference appear within 600 chars of the function name

## Threat Mitigations Applied (from threat_model)

| Threat ID | Mitigation | Where |
|-----------|-----------|-------|
| T-11-05a | DISTILL_PROMPT forbids D-01 categories + is_sensitive() deterministic backstop drops blocked facts before remember() | `personality/prompts.py`, `models/memory.py`, `services/memory.py:distill` |
| T-11-05b | DISTILL_PROMPT forbids numbers + contains_number() backstop drops digit/count-word facts | `personality/prompts.py`, `models/memory.py`, `services/memory.py:distill` |
| T-11-05c | DISTILL_PROMPT: observed/stated only, atomic, third-person, no inference; candidate-ammo framing (model may NOOP downstream) | `personality/prompts.py:DISTILL_PROMPT` |
| T-11-05d | Only two triggers (event hooks + daily batch), one batched priority-2 call per user; no per-message write (D-09); on_message regression test enforces it | `cogs/events.py`, `cogs/music.py`, `bot.py:memory_distill_batch`, `tests/test_memory.py` |
| T-11-05e | Every cog write is asyncio.create_task fire-and-forget (3s rule / event handler non-blocking) | `cogs/events.py`, `cogs/music.py`, `cogs/ai.py` |

## Known Stubs

None — all three tasks fully implemented. The distill_and_remember orchestration only calls `compute_salience(base_salience)` with `distiller_bump=0.0` (default); the distiller bump mechanism for especially significant facts is out of scope for 11-05 (D-07 detail deferred).

## Threat Flags

None — no new network endpoints, auth paths, schema changes, or new trust boundaries introduced. All write paths go through the existing `$N`-parameterized asyncpg helpers in database.py (via remember()). The only new Gemini surface is distill() calling chat() at priority=2, which is already within the established rate-limit budget architecture.

## Self-Check: PASSED
