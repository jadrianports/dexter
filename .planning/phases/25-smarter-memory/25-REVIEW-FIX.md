---
phase: 25-smarter-memory
fixed_at: 2026-07-16T10:08:16Z
review_path: .planning/phases/25-smarter-memory/25-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 25: Code Review Fix Report

**Fixed at:** 2026-07-16T10:08:16Z
**Source review:** .planning/phases/25-smarter-memory/25-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 4 (WR-01, WR-02, WR-03, WR-04 — IN-01 explicitly out of scope, left for the record)
- Fixed: 4
- Skipped: 0

## Fixed Issues

### WR-01: `recall()` step 7b shares the same broad try/except that guards fact retrieval

**Files modified:** `services/memory.py`
**Commit:** `33c449b`
**Applied fix:** Wrapped step 7a (`bump_surfaced`) and step 7b (`reinforce_memory_expiry`)
in their own inner `try/except Exception`, logging at DEBUG and continuing rather than
propagating into the outer retrieval-body `except`. A failure in this best-effort
housekeeping write can no longer discard facts that were already successfully retrieved,
floor-filtered, reranked, and capped. The outer catch's existing behavior on a genuine
retrieval failure (steps 1–6) is unchanged.

### WR-02: MEM-07 write also fires for Gemini-transport-fallback template lines

**Files modified:** `cogs/events.py`
**Commit:** `f5a91dc`
**Applied fix:** Added a `line not in roasts.VISION_ROAST_FALLBACKS` guard alongside the
existing `memory_service is not None` check at the write call site in
`_maybe_fire_vision_roast`. This is the least invasive option: it does not change
`_generate_vision_roast`'s `str | None` return contract or signature, so the 5 tests
locking that contract are untouched. The VIS-02 silent-skip behavior (safety-blocked →
`None` → no reply, no write) is unaffected — this only prevents *sent* fallback replies
from being memorialized. Verified: the fallback line is still sent to the user (VIS-02:
transport failure ≠ safety block), only the memory write is skipped.

### WR-03: No fast/mocked test exercises the MEM-07 write's call-site wiring

**Files modified:** `tests/test_vision_events.py`
**Commit:** `b346d0e`
**Applied fix:** Added a `_make_bot_with_memory()` helper (an explicit `AsyncMock`
`distill_and_remember`, not a bare `MagicMock()` — the bare-mock auto-attribute is what
broke `asyncio.create_task` in the first place per the 25-02 SUMMARY, so this solves that
problem properly rather than reintroducing it) plus 5 new tests:
- correct `user_id`/`guild_id`/`raw_text`/`kind`/`base_salience` kwargs + guild stamping
  on the success path,
- no write when `line is None` (VIS-02 silent skip),
- no write when `message.reply` raises `discord.HTTPException`,
- no write for a WR-02 transport-fallback line (regression test tying the two fixes
  together),
- no write / no raise when `memory_service` is absent.

`_make_bot()` (used by all pre-existing tests) is untouched — still `memory_service = None`
— so none of the 17 pre-existing tests changed behavior.

### WR-04: Duplicate `datetime.now(timezone.utc)` bound to `now2`

**Files modified:** `services/memory.py`
**Commit:** `33c449b` (same commit as WR-01 — both touch the same step-7b block)
**Applied fix:** Renamed `now2` to `reinforced_at`, a descriptive name reflecting its
actual use (the clock capture reinforcement's `expires_at + timedelta(days=...)` is
computed from). Did not collapse it into `rerank()`'s earlier `now` capture, since the two
serve genuinely distinct purposes a few lines apart (rerank scoring vs. expiry
reinforcement) and giving each step its own clearly-named capture reads better than
reusing a rerank-scoped variable for a different responsibility three steps later.

## Skipped Issues

None — all 4 in-scope findings were fixed.

_Note: IN-01 (Info severity, test-quality note about `test_reinforce_memory_expiry_never_computes_datetime_in_sql`
asserting against source prose rather than SQL semantics) was explicitly out of scope per
the fix instructions and was not touched._

---

_Fixed: 2026-07-16T10:08:16Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
