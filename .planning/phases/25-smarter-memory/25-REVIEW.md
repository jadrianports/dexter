---
phase: 25-smarter-memory
reviewed: 2026-07-16T09:40:41Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - cogs/events.py
  - config.py
  - database.py
  - services/memory.py
  - tests/test_database_phase25.py
  - tests/test_memory.py
  - tests/test_vision_events.py
findings:
  critical: 0
  warning: 4
  info: 1
  total: 5
status: issues_found
---

# Phase 25: Code Review Report

**Reviewed:** 2026-07-16T09:40:41Z
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Reviewed the diff since `61a85a9` implementing MEM-06 (expiry reinforcement at the `recall()`
chokepoint) and MEM-07 (`vision_roast` memory kind + fire-and-forget write from
`_maybe_fire_vision_roast`). The core mechanics are sound: `database.reinforce_memory_expiry` is
correctly parameterized (`ANY($1)` array binding, `GREATEST` extend-only, Python-side datetime
arithmetic — confirmed no SQL injection path and no SQL-side date arithmetic), the kind-grouping
in `recall()` step 7b correctly reads `kind` from raw rows via `.get()` (never breaking the
kind-free `MemoryFact` dataclass or pre-existing test fixtures lacking a `kind` key), the
Phase 21 `search_memories` dynamic-`$N` discipline is untouched, the Phase 13 CR-01 cross-kind
`expires_at` scar is not reopened (reinforcement is grouped by *resolved decay-days*, still keyed
off each row's own kind — never a blanket update), and the MEM-07 write is genuinely gated on the
success path (`line is not None` and a successful `message.reply`) with the full
`is_sensitive`/`contains_number` accuracy firewall in force (`exempt_numbers` is never passed, so
it defaults to `False` since `kind != "taste_episode"`) — verified against a live pgvector
container per the plan summaries and locally against the source. `ids` batches into
`reinforce_memory_expiry` are bounded by `MEMORY_INJECT_CAP` (≤3), so the "unbounded batch" concern
does not materialize in practice.

No BLOCKER-level defects found. Four WARNING-level robustness/quality issues and one INFO-level
test-fragility issue are below.

## Warnings

### WR-01: `recall()` step 7b shares the same broad try/except that guards fact retrieval — a housekeeping failure discards already-successful results

**File:** `services/memory.py:128-219` (step 7b added at 190-207, inside the try that starts at 128 and is caught at 216)
**Issue:** The entire retrieval body (ANN search, floor, rerank, cap, step 7a `bump_surfaced`, and
the new step 7b `reinforce_memory_expiry`) lives inside one `try/except Exception: return []`
block. This was already true for step 7a before this phase, but step 7b doubles the number of
best-effort DB writes sharing that fate: if `reinforce_memory_expiry` raises (transient network
blip, pool exhaustion, etc.) *after* the facts were already successfully retrieved, reranked, and
capped, the entire function discards them and returns `[]` — degrading a working `/roast`/`/ask`
grounding call because of a failure in a purely-cosmetic "extend this fact's expiry" side effect.
The docstring's "Degrades gracefully to `[]`" contract is being interpreted more broadly than the
docs describe (embed-failure / no-floor-clearing), and now covers "the housekeeping write also
failed."
**Fix:** Wrap steps 7a/7b in their own inner `try/except`, logging and continuing rather than
propagating into the outer catch, so a reinforcement/bump failure can never erase a
successfully-computed return value:
```python
try:
    await database.bump_surfaced(self._pool, [f.id for f in top])
    kind_by_id = {row["id"]: row.get("kind") for row in rows}
    ...
    for days, ids in groups.items():
        await database.reinforce_memory_expiry(self._pool, ids, now2 + timedelta(days=days))
except Exception as e:
    log.debug(f"memory.recall: step-7 surfacing bookkeeping failed (non-fatal): {e}")

return [f.fact for f in top]
```

### WR-02: The MEM-07 write also fires for generic Gemini-transport-fallback template lines, not just genuinely-generated commentary

**File:** `cogs/events.py:561-609` (`_generate_vision_roast`), `cogs/events.py:696-716` (write gate)
**Issue:** `_generate_vision_roast` returns a non-`None` `str` in two distinct cases: (1) a
genuine Gemini-generated roast, and (2) `pick_random(roasts.VISION_ROAST_FALLBACKS)` on
`GeminiRateLimitError`/`GeminiAPIError` — a canned, image-agnostic line like *"i can see the image.
i just can't currently muster a reaction that does it justice."* The new write gate at
`cogs/events.py:696` treats both as "success" (per the plan's own D-04 definition: "line is not
None AND the reply send succeeded"), so a rate-limit-triggered fallback reply — which the test
suite explicitly confirms reaches this branch (`tests/test_vision_events.py`'s
`test_transport_fallback_replies`, referenced in the 25-02 SUMMARY's deviation note) — gets
distilled and stored as a `vision_roast` memory carrying zero information about the actual image
or user. This is a quality/noise concern (the RAG store accumulates near-identical boilerplate
"memories" whenever Gemini is saturated) rather than an accuracy-firewall or VIS-02 violation
(VIS-02 only prohibits a *visible* fallback for a *safety block*, which this is not).
**Fix:** Track whether the line came from the fallback pool (e.g., have
`_generate_vision_roast` return a tuple/flag, or check membership in
`roasts.VISION_ROAST_FALLBACKS`) and skip the `distill_and_remember` call when it did — a
transport failure is not a "memorable moment" about the user's image.

### WR-03: No fast/mocked test exercises the MEM-07 write's actual call-site wiring

**File:** `tests/test_vision_events.py` (`_make_bot`), `cogs/events.py:706-716`
**Issue:** `_make_bot()` now sets `bot.memory_service = None` unconditionally, so every existing
vision-glue test (cooldown marking, reply anchoring, transport fallback, safety-block skip) fully
bypasses the new `if memory_service is not None:` branch. The only coverage of the actual write
is `tests/test_database_phase25.py::TestVisionRoastMemory`, which calls
`MemoryService.distill_and_remember(...)` **directly** — it never invokes
`_maybe_fire_vision_roast`, so it cannot catch a wiring regression at the call site itself (e.g., a
typo in a kwarg name, passing `message.channel.id` instead of `message.guild.id`, or accidentally
moving the write above the `message.reply` await). Those live-DB tests are also
`TEST_DATABASE_URL`-gated and skip in a default local/CI-less run, so a broken call site could
ship without any red test locally.
**Fix:** Add at least one mocked-glue test with a real `AsyncMock` `memory_service` (not `None`)
that asserts `distill_and_remember` is awaited with the expected `user_id`/`guild_id`/`kind`/
`raw_text`/`base_salience` on the success path, and NOT called when `line is None` or
`message.reply` raises — mirroring the existing `_maybe_fire_proactive_callback` /
`_generate_ambient_roast` write-site tests elsewhere in this file's sibling suites.

### WR-04: Duplicate `datetime.now(timezone.utc)` call with a non-descriptive name (`now2`)

**File:** `services/memory.py:172` and `services/memory.py:197`
**Issue:** `now` is already computed at line 172 for `rerank()`. Step 7b introduces a second,
near-identical call three logical steps later, bound to `now2` — a placeholder name that reads as
an artifact of a quick patch rather than an intentional design choice (the two timestamps differ
by only the time it takes to rerank/cap/bump, i.e. microseconds).
**Fix:** Reuse `now` (rerank's clock capture is fine to reuse for this purpose since the drift is
negligible), or if a fresh capture is intentional, give it a descriptive name:
```python
reinforced_at = datetime.now(timezone.utc)
...
await database.reinforce_memory_expiry(self._pool, ids, reinforced_at + timedelta(days=days))
```

## Info

### IN-01: The "no SQL-side date arithmetic" acceptance test asserts against source-code prose, not SQL semantics

**File:** `tests/test_database_phase25.py:83-88` (`test_reinforce_memory_expiry_never_computes_datetime_in_sql`)
**Issue:** The test's only check is `"interval" not in src`. The 25-01 SUMMARY documents that the
function's own docstring originally tripped this assertion (an English sentence describing the
anti-pattern, not the anti-pattern itself) and had to be reworded to dodge it — a strong signal
this is checking the literal substring rather than the actual SQL shape. A future edit that
introduces real SQL-side date arithmetic under different syntax (e.g. `now() + '30 days'` with no
`interval` keyword, or a multi-line f-string that happens to avoid that token) would pass this test
while violating the intended invariant ("callers control the exact decay-days constant; it is never
computed in SQL").
**Fix:** Assert on the actual SQL body instead of prose — e.g., extract the query string via a
regex/AST check that the `UPDATE` statement's `SET expires_at = ...` expression is exactly
`GREATEST(expires_at, $2)` (no `+`, no `now()`, no string literal), rather than scanning
`inspect.getsource()` for a banned English word.

---

_Reviewed: 2026-07-16T09:40:41Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
