---
phase: 11-rag-long-term-memory
reviewed: 2026-06-29T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - bot.py
  - cogs/ai.py
  - cogs/events.py
  - cogs/music.py
  - config.py
  - database.py
  - models/memory.py
  - personality/prompts.py
  - scripts/memory_spike.py
  - services/gemini.py
  - services/memory.py
  - tests/test_database_phase11.py
  - tests/test_memory.py
  - tests/test_prompts.py
findings:
  critical: 2
  warning: 3
  info: 3
  total: 8
status: issues_found
---

# Phase 11: Code Review Report

**Reviewed:** 2026-06-29
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Phase 11 adds a pgvector-backed RAG long-term memory system: embedding (separate
60 RPM quota), scoped cosine retrieval, distillation with sensitivity/number
safety gates, prompt injection, per-user cap eviction, and a daily decay sweep.

The pure-logic layer (`models/memory.py`) and the DB helper layer
(`database.py`) are well built: every memory query is `$N`-parameterized, the
`user_id = $1` scope guard is present on search/eviction/count, embeddings flow
through the pgvector codec (no SQL-injection path), and the Neon pitfalls
(`statement_cache_size=0`, `ssl='require'`, per-connection `register_vector`
init, extension-first boot) are all honored. The accuracy firewall
(`contains_number`) and rate-limiter separation (`_embed_limiter` vs
`_rate_limiter`) are correctly implemented and well tested.

However, the feature is **not wired into the bot at all** — `bot.memory_service`
is never instantiated, so the entire read/write/sweep loop is dead code at
runtime (CR-01). The unit tests pass because they construct `MemoryService`
directly, giving false confidence. A second, security-relevant defect (CR-02)
lurks behind the wiring: the daily-batch path keys memories by user-controllable
display name, which both makes those memories unrecallable and opens a cross-user
memory-poisoning vector once the service is wired.

## Critical Issues

### CR-01: `bot.memory_service` is never instantiated — the entire Phase 11 feature is dead code

**File:** `bot.py:352-486` (`_initialize_once`)
**Issue:**
Every consumer of the memory system accesses it via
`getattr(self.bot, "memory_service", None)` and silently no-ops when it is
absent (`cogs/ai.py:125`, `cogs/ai.py:373`, `cogs/events.py:243`,
`cogs/music.py:1116,1213,1243,1283`, `bot.py:813`, `bot.py:903`). But
`_initialize_once` never creates the service — there is no
`bot.memory_service = MemoryService(...)` and no `import services.memory`
anywhere in `bot.py` (grep confirms: only `getattr` reads exist; zero
assignments).

The phase's own pattern doc mandates the wiring
(`.planning/phases/11-rag-long-term-memory/11-PATTERNS.md:295`:
`bot.memory_service = MemoryService(bot.pool, bot.gemini_service)`), and
`ARCHITECTURE.md:66` lists it as a required `_initialize_once` modification. It
was not implemented.

Consequences at runtime:
- `recall()` is never invoked (all callbacks guard on `_memory_svc is not None`).
- `distill_and_remember()` is never invoked — nothing is ever stored.
- `memory_distill_batch` (`bot.py:813`) and `memory_sweep` (`bot.py:903`) both
  hit `if memory_service is None: return` and no-op forever.

The feature ships doing nothing. Unit tests (`tests/test_memory.py`) instantiate
`MemoryService` directly so they pass regardless, masking the gap.

**Fix:** Wire the service in `_initialize_once`, after `gemini_service` is
created and before cogs load, guarded on the Gemini key (memory depends on
embeddings):
```python
# Phase 11: long-term memory service (depends on Gemini for embeddings)
if hasattr(bot, "gemini_service"):
    from services.memory import MemoryService
    bot.memory_service = MemoryService(bot.pool, bot.gemini_service)
    log.info("Memory service initialized")
```
Then add an integration assertion (not just direct-construction unit tests) that
`bot.memory_service` exists after init so this cannot silently regress.

### CR-02: Daily-batch memories are keyed by user-controllable display name — cross-user memory poisoning + unrecallable writes

**File:** `bot.py:828-867` (`memory_distill_batch`); `cogs/events.py:353-357`
(buffer feed)
**Issue:**
The message buffer stores `author=message.author.display_name`
(`cogs/events.py:356`). `memory_distill_batch` then uses that display-name
string directly as the memory owner key:
```python
author = msg.get("author", "unknown")
...
await memory_service.distill_and_remember(
    user_id=author,            # <-- display name, NOT a Discord snowflake
    guild_id=None,
    raw_text=raw_text,
    kind="daily_batch",
    ...
)
```
Every recall path keys on the real snowflake (`str(member.id)` /
`str(interaction.user.id)` — `cogs/ai.py:129`, `cogs/events.py:133`,
`cogs/music.py:1120`). Two problems result:

1. **Functional:** daily-batch memories are stored under `user_id="DisplayName"`
   and can never be retrieved (recall queries `WHERE user_id = '<snowflake>'`).
   Every daily-batch embed call and row insert is wasted, and these orphan rows
   consume the table / count toward a phantom owner's cap.

2. **Security (cross-user injection):** display names are attacker-controlled.
   A user who sets their server nickname to a victim's Discord ID
   (e.g. `"123456789012345678"`) gets their banter distilled and stored under
   `user_id="123456789012345678"` — the victim's recall scope. That
   attacker-authored "fact" is then injected as roast ammunition the next time
   the victim is recalled, defeating the per-user `user_id = $1` scope guard that
   the DB layer otherwise enforces. This is a memory-poisoning / cross-user data
   integrity flaw. It is currently latent only because CR-01 leaves the service
   unwired; fixing CR-01 activates it.

**Fix:** Carry the real Discord user ID through the buffer so the batch keys on a
snowflake, or drop the daily-batch write entirely until the buffer records IDs.
Minimum:
```python
# models/message_buffer: store author_id alongside author
self.bot.message_buffer.add(
    channel_id=message.channel.id, role="user",
    author=message.author.display_name,
    author_id=str(message.author.id),   # NEW
    content=message.content,
)
# bot.py memory_distill_batch: key on author_id, never display name
user_id = msg.get("author_id")
if not user_id or not user_id.isdigit():
    continue   # never accept a non-snowflake as an owner key
```

## Warnings

### WR-01: Voice-join memory writes are hardcoded `kind="late_night"` even for ordinary daytime joins

**File:** `cogs/events.py:225-256`
**Issue:** The roast scenario branches on `RoastScenario.LATE_NIGHT` vs a plain
`JOIN`, but the subsequent memory write unconditionally uses
`kind="late_night"` and `base_salience=...["late_night"]` (0.7):
```python
asyncio.create_task(
    memory_service.distill_and_remember(
        ...
        kind="late_night",
        base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS["late_night"],
    )
)
```
A regular daytime join is therefore mislabeled `late_night` and stored at
salience 0.7 — high enough to survive the decay sweep
(`MEMORY_DECAY_SALIENCE_FLOOR = 0.5`), permanently retaining a fact that should
be a low-value event. Impact is partly masked today because the plain-join
`raw_text` ("X just joined the voice channel") usually distills to nothing, but
the kind/salience are still wrong whenever a fact does survive.
**Fix:** Track the kind alongside the scenario:
```python
if scenario_result == RoastScenario.LATE_NIGHT:
    scenario, fallback_pool, mem_kind = "...", roasts.LATE_NIGHT_ROASTS, "late_night"
else:
    scenario, fallback_pool, mem_kind = "...", roasts.VOICE_JOIN_ROASTS, "daily_batch"
...
kind=mem_kind,
base_salience=config.MEMORY_SALIENCE_BASE_WEIGHTS[mem_kind],
```

### WR-02: `is_sensitive` substring matching over-blocks legitimate music facts

**File:** `models/memory.py:368-369` (loop over `_SENSITIVE_KEYWORDS`)
**Issue:** The gate does naive `if kw in text_lower` substring matching against
keywords including `"gay"` and `"rape"`. These match inside common, innocuous
music tokens:
- `"gay"` matches `"marvin gaye"` and `"gayle"` (the artist behind "abcdefu") →
  any fact about those artists is silently dropped.
- `"rape"` matches `"grape"`, `"drape"`, `"scrape"` → e.g. a band/lyric fact
  containing "grape" is dropped.

The gate is intentionally conservative (ambiguous → drop), but substring matches
on short tokens produce false positives that quietly erode the feature's yield
on exactly the music-taste facts it is meant to capture.
**Fix:** Use word-boundary matching for the short/ambiguous keywords:
```python
import re
_SENSITIVE_WORD_RE = re.compile(
    r"\b(?:gay|lesbian|bisexual|rape|...)\b", re.IGNORECASE
)
# keep substring matching only for unambiguous stems like "depress", "suicid"
```
Move single-syllable identity/violence words to the boundary-matched set; keep
clinical stems (`depress`, `suicid`, `schizophren`) as substrings.

### WR-03: `contains_number` backstop silently drops the distiller's own example output pattern

**File:** `models/memory.py:404-406` and `personality/prompts.py:31`
**Issue:** `DISTILL_PROMPT` teaches the model that
`"only listens to early 2000s pop punk"` is good output (line 31), but
`contains_number` rejects any digit (`re.search(r"\d", text)`), so `"2000s"`
fails the backstop and the fact is dropped. The primary gate and the
deterministic backstop disagree: the prompt actively trains the model to emit
facts the backstop then discards, reducing useful yield and wasting embed/insert
work on facts that never persist.
**Fix:** Reconcile the two. Either remove decade/era patterns from the prompt's
positive examples, or narrow `contains_number` to count-like figures (reject
standalone integers and count words, allow era tokens like "2000s"/"90s"):
```python
# allow decade/era tokens, reject bare counts
if re.search(r"\b\d+(?!0s\b)\b", text):   # tune to taste
    return True
```
Pick one source of truth and make the example set consistent with the gate.

## Info

### IN-01: `memory_distill_batch` reaches into `message_buffer._buffers` private state

**File:** `bot.py:819`
**Issue:** `active_channels = list(message_buffer._buffers.keys())` couples the
background task to a private attribute of `MessageBuffer`. A refactor of the
buffer's internals silently breaks the batch with no type/lint signal.
**Fix:** Add a public accessor (e.g. `message_buffer.active_channel_ids()`) and
call that instead.

### IN-02: `recall()` discards an otherwise-good result set when `bump_surfaced` fails

**File:** `services/memory.py:162-177`
**Issue:** The `bump_surfaced` DB write sits inside the broad `try` whose
`except` returns `[]`. If only the bump fails (e.g. transient pool error) the
already-selected, above-floor facts are thrown away and nothing is injected,
even though valid memories were retrieved. The bump is a best-effort novelty
bookkeeping update, not part of producing the answer.
**Fix:** Wrap just the bump in its own try/except so a bump failure logs and
still returns `top`:
```python
try:
    await database.bump_surfaced(self._pool, [f.id for f in top])
except Exception as e:
    log.debug("recall: bump_surfaced failed (non-fatal): %s", e)
return [f.fact for f in top]
```

### IN-03: Inconsistent `guild_id` argument to `recall()` across call sites

**File:** `cogs/music.py:1119-1123` (passes `""`) vs `cogs/ai.py:128-132`,
`cogs/events.py:132-136` (pass `str(guild_id)`)
**Issue:** `recall()` ignores `guild_id` today (ANN scopes to `user_id` only),
so this is harmless, but the music cog passes an empty string while the other
sites pass the real guild ID. If `guild_id` is ever promoted to a real filter
(the docstring reserves it for future per-guild scoping), the music-cog call
will behave differently. Standardize now to avoid a latent bug.
**Fix:** Pass `str(interaction.guild.id)` (or the relevant guild) consistently,
or change the signature to `guild_id: str | None = None` and pass `None`
explicitly where unused.

---

_Reviewed: 2026-06-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
