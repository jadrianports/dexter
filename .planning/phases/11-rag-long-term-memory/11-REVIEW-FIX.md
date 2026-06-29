---
phase: 11-rag-long-term-memory
fixed_at: 2026-06-29T22:25:00Z
review_path: .planning/phases/11-rag-long-term-memory/11-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 11: Code Review Fix Report

**Fixed at:** 2026-06-29
**Source review:** `.planning/phases/11-rag-long-term-memory/11-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope (Critical + Warning): 5
- Fixed: 5
- Skipped: 0

All 2 Critical and 3 Warning findings were fixed. Info findings (IN-01, IN-02,
IN-03) were out of scope (`fix_scope: critical_warning`) and not addressed.

**Test suite:** `./.venv/Scripts/python.exe -m pytest -q` → **551 passed, 70
skipped** (the 70 skips are the live-DB / pgvector integration tests, which skip
without a Postgres+pgvector instance — expected). No regressions. Note: when run
inside the isolated worktree the suite reports one extra failure
(`test_memory_sweep_task_defined_in_bot`) solely because `bot.py` calls
`sys.exit(1)` at import when `DISCORD_TOKEN` is unset and the git-ignored `.env`
is not present in the worktree; with a token in the environment that test passes.
This is an environment artifact, not a code regression.

## Fixed Issues

### CR-01: `bot.memory_service` is never instantiated — entire Phase 11 feature was dead code

**Files modified:** `bot.py`
**Commit:** 8a8f24a
**Status:** fixed
**Applied fix:** Added the memory-service wiring in `_initialize_once`,
immediately after the Gemini service block and before cogs load, guarded on
`hasattr(bot, "gemini_service")`:
`bot.memory_service = MemoryService(bot.pool, bot.gemini_service)`. Verified the
`MemoryService.__init__(self, pool, gemini_service)` signature in
`services/memory.py` and wired it with the real dependencies (the asyncpg pool —
which already has the pgvector codec registered via `init=_register_vector` and
`statement_cache_size=0` per the Neon/K-04 conventions — and the GeminiService
instance). This activates `recall()`, `distill_and_remember()`, the
`memory_distill_batch` loop, the `memory_sweep` loop, and all cog hooks, which
previously no-op'd on `getattr(bot, "memory_service", None) is None`.

### CR-02: Daily-batch memories keyed by user-controllable display name (cross-user poisoning + unrecallable writes)

**Files modified:** `models/message_buffer.py`, `cogs/events.py`, `bot.py`
**Commit:** 96e155c
**Status:** fixed: requires human verification
**Applied fix:** Carried the real Discord snowflake through the message buffer
and re-keyed the daily batch on it:
- `MessageBuffer.add()` gained an `author_id: str | None = None` parameter, stored
  in each buffered message dict (backward-compatible default `None`).
- `cogs/events.py:on_message` now passes `author_id=str(message.author.id)`.
- `memory_distill_batch` keys per-user grouping on `msg["author_id"]` and skips
  any message whose `author_id` is missing or not all-digits
  (`if not user_id or not user_id.isdigit(): continue`). The display name is still
  carried into `raw_text` purely as distiller context, never as the owner key.

Recall (`cogs/ai.py`, `cogs/events.py`, `cogs/music.py` all use
`str(<user>.id)`) and the batch write now use the same snowflake key type. Flagged
for human verification because this is a security-relevant change to the memory
ownership key — confirm the recall scope and batch-write scope remain aligned on
snowflakes across all call sites.

### WR-01: Voice-join memory writes hardcoded `kind="late_night"` even for daytime joins

**Files modified:** `cogs/events.py`
**Commit:** a2d297c
**Status:** fixed: requires human verification
**Applied fix:** Track `mem_kind` alongside the roast scenario in
`on_voice_state_update`: late-night joins keep `kind="late_night"`, ordinary
daytime joins now use `kind="daily_batch"`. The memory write uses
`kind=mem_kind` and `base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS[mem_kind]`.
Previously every join was stored as `late_night` at salience 0.7 (above the
`MEMORY_DECAY_SALIENCE_FLOOR` of 0.5), permanently retaining mislabeled
low-value daytime joins. Flagged for human verification (state/labeling logic) —
confirm `daily_batch` is the desired kind/salience tier for a plain daytime join.

### WR-02: `is_sensitive` substring matching over-blocks legitimate music facts

**Files modified:** `models/memory.py`
**Commit:** f2a4545
**Status:** fixed: requires human verification
**Applied fix:** Moved the two short/ambiguous terms `"gay"` and `"rape"` out of
the substring-matched `_SENSITIVE_KEYWORDS` frozenset into a new word-boundary
regex `_SENSITIVE_WORD_RE = re.compile(r"\b(?:gay|rape)\b", re.IGNORECASE)`,
checked in `is_sensitive()`. Longer unambiguous stems (`depress`, `suicid`,
`schizophren`, etc.) remain substring-matched. Verified with explicit checks:
`"marvin gaye"`, `"gayle"`, `"grape soda"` now pass (False) while standalone
`"is gay"` / `"mentions rape"` and clinical stems still block (True); the full
`tests/test_memory.py` suite (93 tests) passes. Flagged for human verification
because this alters a safety/PII gate's matching semantics.

### WR-03: `contains_number` backstop silently drops the distiller's own example pattern

**Files modified:** `personality/prompts.py`
**Commit:** 3de66db
**Status:** fixed
**Applied fix:** Chose the strict number-free backstop as the single source of
truth (it enforces the accuracy firewall — Critical Rule 5: all numbers come from
SQL, never from memories) and reconciled the prompt to it. Replaced the
era-bearing positive example `"only listens to early 2000s pop punk"` (which the
`contains_number` digit check always rejected) with a number-free equivalent
`"only listens to nostalgic pop punk and calls it taste"`. Verified the new
example passes `contains_number()` (returns False). The `contains_number` gate was
intentionally left strict to preserve the accuracy firewall rather than loosened
to admit era tokens.

## Skipped Issues

None — all in-scope findings were fixed.

---

_Fixed: 2026-06-29_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
