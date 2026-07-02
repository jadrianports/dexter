---
phase: 16-proactive-memory-callbacks
reviewed: 2026-07-03T00:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - cogs/events.py
  - cogs/memory.py
  - config.py
  - database.py
  - logic/proactive.py
  - personality/roasts.py
  - tests/test_ambient_recall_cadence.py
  - tests/test_database_phase16.py
  - tests/test_memory_command.py
  - tests/test_proactive_events.py
  - tests/test_proactive_logic.py
findings:
  critical: 0
  warning: 3
  info: 3
  total: 6
status: issues_found
---

# Phase 16: Code Review Report

**Reviewed:** 2026-07-03T00:00:00Z
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Phase 16 adds a third, rarest ambient "proactive memory callback" cadence: a pure
firing gate (`logic/proactive.py`), an opt-out column + upsert helpers
(`database.py`), the `on_message` glue with the `pre_recalled_memories` bypass
(`cogs/events.py`), and the `/memory callbacks` subcommand (`cogs/memory.py`).

The core mechanics the phase set out to get right are correct:

- **Short-circuit ordering** in `should_fire_proactive_callback` is correct
  (opt-out → chance → daily cap), with the exact `>=`/`<` boundary conventions
  the tests lock.
- **Upsert (not bare UPDATE)** for opt-out persistence is correct: `INSERT ...
  ON CONFLICT (user_id) DO UPDATE SET proactive_opt_out = EXCLUDED...`, with the
  user_id used as a NOT-NULL placeholder username and the conflict branch
  updating only the flag (real username never clobbered).
- **Pitfall-1 byte-identical ambient regression** holds: the
  `pre_recalled_memories` default `None` path is untouched and locked by
  `test_pre_recalled_bypasses_internal_recall`.
- **Self-scoping / ephemeral / mention safety**: `/memory callbacks` is
  self-scoped (no target param), replies `ephemeral=True`, and the proactive
  fire uses `message.reply(..., allowed_mentions=AllowedMentions.none(),
  mention_author=False)`.
- **Daily-cap reset semantics** are correct: the `(date_str, count)` tuple resets
  the count at read time when `last_date != today`, and the write re-stamps
  `today`.

No BLOCKER-severity defects were found. Three WARNING-level issues are worth
fixing before this ships: a TOCTOU race that can exceed the daily cap under
concurrent messages, a missing error-guard on the per-message opt-out DB call,
and a static recall anchor that will likely neuter the feature in practice.

## Warnings

### WR-01: TOCTOU race on the in-memory daily counter can exceed the daily cap

**File:** `cogs/events.py:428-472`
**Issue:** `_maybe_fire_proactive_callback` reads the per-user daily count at
line 428, then performs several `await`s (opt-out DB call, `recall`, Gemini
`chat`, `message.reply`) before writing the incremented count at line 472. Because
`on_message` handlers run concurrently, two messages from the same user that
interleave across those awaits can both read `daily_count = 0`, both pass
`should_fire_proactive_callback` (each rolls its own `random.random()`), both
fire, and both write `(today, 1)`. The stated invariant `PROACTIVE_CALLBACK_DAILY_CAP
= 1` is then violated (two callbacks in one day). Probability is low (each path
must independently roll < 0.10 and clear the recall floor), but it is a genuine
concurrency defect against the cap the phase exists to enforce.
**Fix:** Reserve the slot before the awaited work, or re-check/commit atomically.
Simplest: increment the counter immediately when the gate passes (optimistic
reserve) and roll it back only if the send is abandoned:
```python
if not should_fire_proactive_callback(
    opted_out=opted_out, chance_roll=random.random(), daily_count=daily_count
):
    return
# reserve the slot up front so a concurrent message for the same user
# sees the incremented count and is capped
self._proactive_daily_counts[user_id] = (today, daily_count + 1)
try:
    ... # recall / generate / reply
    if not memories:
        self._proactive_daily_counts[user_id] = (today, daily_count)  # release
        return
except discord.HTTPException:
    self._proactive_daily_counts[user_id] = (today, daily_count)      # release
    return
```
Alternatively hold a short per-user `asyncio.Lock` across the read/modify/write.

### WR-02: Unguarded opt-out DB call in a per-message hot path

**File:** `cogs/events.py:420`
**Issue:** `opted_out = await database.get_proactive_opt_out(self.bot.pool,
user_id)` has no error handling. This runs on **every** message in the
designated channel. The very next external call — `memory_service.recall` at
lines 442-448 — is wrapped in `try/except ... memories = []` and degrades
gracefully, but the opt-out lookup is not. A transient Neon hiccup, pool
exhaustion, or scale-to-zero SSL-EOF here raises straight through
`_maybe_fire_proactive_callback` into `on_message`, producing an unhandled
listener exception on every message for the duration of the outage. The sibling
voice handler guards its DB lookup the same way (`get_user_summary`,
lines 132-135) — this path is inconsistent.
**Fix:** Fail safe (treat a lookup error as "not opted out" or as "skip"),
matching the recall path's degrade-to-default discipline:
```python
try:
    opted_out = await database.get_proactive_opt_out(self.bot.pool, user_id)
except Exception as _err:
    log.debug("proactive callback: opt-out lookup failed (non-fatal): %s", _err)
    return  # or: opted_out = False, if you prefer to continue
```

### WR-03: Static generic recall anchor will likely fail the similarity floor

**File:** `cogs/events.py:443-444`
**Issue:** The proactive recall uses a fixed, content-free anchor string:
`memory_service.recall(user_id, str(message.guild.id), "a proactive callback
moment")`. `MemoryService.recall` embeds this string and drops every fact below
`MEMORY_SIMILARITY_FLOOR = 0.70` (a deliberately high-precision floor per
`config.py:165`). An abstract meta-phrase like "a proactive callback moment" is
semantically unrelated to concrete stored facts (e.g. "user listens to synthwave
at 2am"), so cosine similarity will typically land well below 0.70 and `recall`
returns `[]`. Combined with the `if not memories: return` silent-skip at
lines 450-453, the proactive callback would fire far more rarely than the 0.10
chance implies — potentially almost never — quietly defeating the feature.
Contrast the other surfaces, which anchor recall on meaningful text: `/ask` uses
the user's question, and the ambient roast uses the formatted scenario
(`"{name} just joined the voice channel"`).
**Fix:** Anchor recall on message content or a taste/behaviour-flavored phrase so
it can actually match stored facts, e.g.:
```python
anchor = message.content.strip() or "this user's music taste and history"
memories = await memory_service.recall(user_id, str(message.guild.id), anchor)
```
At minimum, validate against the live memory store that the current constant
clears the 0.70 floor for representative facts before shipping.

## Info

### IN-01: Docstring claims "cheapest-first" but the DB call precedes the chance roll

**File:** `cogs/events.py:406-436`
**Issue:** The method docstring and `logic/proactive.py` both describe a
"short-circuit, cheapest-gate-first" ordering, and the pure gate does check
`opted_out` first. But the glue performs the awaited `get_proactive_opt_out`
DB round-trip (line 420) before the essentially-free `random.random()` chance
roll (line 433). Since the chance gate rejects ~90% of messages, the ordering
inverts the documented intent — the most expensive check runs unconditionally on
every message while the cheap one that would reject most traffic runs second.
(Performance impact itself is out of v1 scope; flagged as a doc/design
inconsistency.)
**Fix:** Either roll the chance gate first and only hit the DB when it passes, or
update the docstring to reflect that opt-out (a durable user preference) is
intentionally checked first.

### IN-02: Repeated function-local imports duplicated into the proactive path

**File:** `cogs/events.py:424-426` (also 235-237)
**Issue:** `import datetime as _dt` / `from zoneinfo import ZoneInfo as _ZoneInfo`
are re-imported inside `_maybe_fire_proactive_callback`, duplicating the identical
in-function imports in `on_voice_state_update`. This matches the file's existing
style but adds a second copy of the same pattern.
**Fix:** Hoist `datetime` and `ZoneInfo` to module-level imports and drop the
in-function copies.

### IN-03: `daily_count`/`chance` gate defaults bind config values at import time

**File:** `logic/proactive.py:36-37`
**Issue:** `chance = config.PROACTIVE_CALLBACK_CHANCE` and
`daily_cap = config.PROACTIVE_CALLBACK_DAILY_CAP` are evaluated once when the
function is defined. The glue calls the gate without passing these, so a runtime
mutation of `config.PROACTIVE_CALLBACK_CHANCE` (e.g. a monkeypatch) would not be
reflected. This is a benign Python default-binding gotcha — production values are
module constants and tests pass explicit overrides — but it is a subtle footgun
if anyone expects config edits to take effect live.
**Fix:** None required. If live-tunability is ever wanted, read
`config.PROACTIVE_CALLBACK_CHANCE` inside the body instead of as a default.

---

_Reviewed: 2026-07-03T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
