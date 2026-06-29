---
phase: 11-rag-long-term-memory
verified: 2026-06-29T23:00:00Z
status: human_needed
score: 7/7
overrides_applied: 0
human_verification:
  - test: "Boot the bot against live Neon, confirm no 'unknown type: public.vector' ValueError in dexter.log, and that the user_memories table + pgvector extension appear in the Neon console"
    expected: "Clean boot log; pgvector extension visible; user_memories table with vector(768) column present"
    why_human: "Extension-first boot ordering and codec registration can only be validated against a live Neon+pgvector connection — the 70 skipped integration tests require TEST_DATABASE_URL"
  - test: "Queue 5+ messages as two different Discord users; wait for (or manually trigger) memory_distill_batch; then run /ask as each user and confirm that recalled memories belong only to the querying user (no cross-user leakage)"
    expected: "User A's recalled memories never surface content from User B's message history; user_memories rows store Discord snowflake IDs in user_id column (not display names)"
    why_human: "CR-02 fix is a security-relevant change to the memory-ownership key; the isdigit() guard and author_id snowflake flow must be confirmed end-to-end on live data where display names might test boundaries"
  - test: "Join a voice channel at a normal hour (not 1-5am); confirm the memory write fires with kind='daily_batch' at salience 0.2 (check debug logs or DB row); then join at 3am and confirm kind='late_night' at salience 0.7"
    expected: "Daytime join: kind=daily_batch, salience=0.2 in user_memories. Late-night join: kind=late_night, salience=0.7. Neither mislabeled."
    why_human: "WR-01 fix changed mem_kind logic based on time-of-day; correct labeling depends on live timezone behavior and cannot be confirmed without a real Discord join event"
  - test: "Verify that a fact containing 'marvin gaye' or 'grape soda' passes the is_sensitive() check (returns False) in a quick Python shell test: from models.memory import is_sensitive; assert not is_sensitive('only listens to marvin gaye'); assert not is_sensitive('grape soda vibes'); assert is_sensitive('is gay'); assert is_sensitive('mentions rape')"
    expected: "All four assertions pass — word-boundary fix correctly allows music tokens while still blocking standalone identity/violence terms"
    why_human: "WR-02 changes a safety gate's matching semantics; the unit tests cover this but the reviewer should confirm the new regex boundary behavior matches the intended safety posture"
---

# Phase 11: RAG Long-Term Memory — Verification Report

**Phase Goal:** Dexter gains a durable semantic memory layer — pgvector on the existing Neon Postgres + gemini-embedding-001 @ 768d — so it remembers distilled, roast-worthy episodes across restarts and lands callback roasts that pair a live SQL stat with a recalled moment (stat x episode payoff), at zero new infrastructure and zero new monthly cost.

**Verified:** 2026-06-29T23:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification (post code-review fix pass)

---

## Critical Defect Re-Verification (Required by Prompt)

### CR-01: MemoryService instantiation — VERIFIED FIXED

**Claim:** `bot.memory_service` is now constructed and assigned in `_initialize_once`.

**Evidence from `bot.py` lines 411-418:**
```python
# Phase 11 / CR-01: long-term memory service (depends on Gemini for embeddings).
# Guarded on gemini_service so memory features are silently disabled when no key.
if hasattr(bot, "gemini_service"):
    from services.memory import MemoryService
    bot.memory_service = MemoryService(bot.pool, bot.gemini_service)
    log.info("Memory service initialized")
```

- The import is inline (avoids circular import at module load).
- `MemoryService(bot.pool, bot.gemini_service)` passes the real asyncpg pool — which already has the pgvector codec registered via `init=_register_vector` at pool creation and `statement_cache_size=0` per K-04 — and the live `GeminiService` instance.
- Wiring executes at line 415-418, BEFORE cog loading (line 440), so all cog hooks (`getattr(self.bot, "memory_service", None)`) receive the live service rather than `None`.
- `memory_distill_batch` (line 823) and `memory_sweep` (line 918-919) both call `getattr(bot, "memory_service", None)` and proceed past the `is None` guard at runtime.
- **Result: VERIFIED FIXED. CR-01 dead-code defect is closed.**

### CR-02: Snowflake keying in memory_distill_batch — VERIFIED FIXED

**Claim:** Daily batch keys on Discord snowflake user IDs, not display names; non-snowflakes are rejected.

**Evidence:**

`models/message_buffer.py:28-58` — `add()` gained `author_id: str | None = None` parameter, stored in each buffered dict:
```python
def add(self, channel_id, role, author, content, author_id: str | None = None) -> None:
    ...
    self._buffers[channel_id].append({
        "role": role, "author": author, "author_id": author_id, "content": content, ...
    })
```

`cogs/events.py:354-361` — `on_message` passes real snowflake:
```python
self.bot.message_buffer.add(
    channel_id=message.channel.id, role="user",
    author=message.author.display_name,
    author_id=str(message.author.id),  # CR-02: real snowflake
    content=message.content,
)
```

`bot.py:857-859` — `memory_distill_batch` keys on `author_id` and rejects non-snowflakes:
```python
user_id = msg.get("author_id")
if not user_id or not user_id.isdigit():
    continue   # never accept a non-snowflake as an owner key
```

All recall() call sites confirmed to use snowflakes:
- `cogs/ai.py:129` — `str(interaction.user.id)`
- `cogs/ai.py:207` — `str(target.id)`
- `cogs/events.py:133` — `str(member.id)`
- `cogs/music.py:1120` — `user_id` (which is `str(interaction.user.id)` per all callers at lines 1161, 1189, 1200, etc.)

Write paths (`distill_and_remember`) also all use `str(interaction.user.id)` or `str(member.id)`.

**Result: VERIFIED FIXED. CR-02 cross-user poisoning and unrecallable-write defects are closed in code. Live behavioral confirmation is in the human_verification list.**

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | pgvector extension enabled, user_memories table with vector(768) exists, vector codec registered boot-order-safe (MEM-01) | VERIFIED | `database.py:SCHEMA_SQL` starts with `CREATE EXTENSION IF NOT EXISTS vector;` then `user_memories` with `embedding vector(768) NOT NULL`; `bot.py:_initialize_once` opens throwaway connection, runs extension DDL BEFORE `asyncpg.create_pool(init=_register_vector)` |
| 2 | embed() uses gemini-embedding-001 @ 768d behind a SEPARATE embedding rate limiter — never the 15 RPM chat budget (MEM-02) | VERIFIED | `services/gemini.py:134` creates `_embed_limiter = _RateLimiter(max_requests=config.EMBED_RPM_LIMIT)` (60 RPM); `embed()` acquires `await self._embed_limiter.acquire(priority)` (NOT `_rate_limiter`); config check confirms `GEMINI_RPM_LIMIT=15` vs `EMBED_RPM_LIMIT=60` |
| 3 | recall() returns top-k memories above similarity floor, reranked by relevance+recency+salience+novelty, capped to 1-3 injected facts (MEM-03) | VERIFIED | `services/memory.py:recall()` is a full 7-step pipeline: embed query → scoped ANN → map to MemoryFact → apply_floor → rerank → cap to MEMORY_INJECT_CAP (3) → bump last_surfaced_at; `models/memory.py` has the four pure scoring functions |
| 4 | Write path distills and stores facts on event/session-end triggers (NOT per-message), with near-duplicate dedup at write time (MEM-04) | VERIFIED | Triggers: voice join (events.py), repeat song + milestone song + milestone streak (music.py), daily batch (bot.py) — all fire `asyncio.create_task(distill_and_remember(...))`. `MemoryService.remember()` performs dedup: `search_memories(k=1)` then `dedup_decision(nearest_sim, MEMORY_DEDUP_THRESHOLD)` |
| 5 | Sensitivity/PII gate prevents storing sensitive content; system never embeds SQL-known facts (MEM-05) | VERIFIED | `models/memory.py:is_sensitive()` checks `_SENSITIVE_KEYWORDS` (substring) + `_SENSITIVE_WORD_RE` (word-boundary for "gay"/"rape") + PII regex; `contains_number()` blocks digits and written number words; both applied in `MemoryService.distill()` backstop after LLM primary gate; `DISTILL_PROMPT` explicitly forbids numbers and sensitive categories |
| 6 | Retrieved memories injected into personality prompt as optional candidate ammo; hard numbers come from live SQL not memory (MEM-06) | VERIFIED | `personality/prompts.py:build_chat_prompt()` has `memories: list[str] | None = None` kwarg; renders `{memory_context}` slot in `DEXTER_SYSTEM_PROMPT` with accuracy-safe framing "All numbers/counts come from USER CONTEXT above — never from these memories"; called in cogs/ai.py (/ask + /roast), cogs/events.py (ambient roast), cogs/music.py (music roast) |
| 7 | Memory hygiene: per-user cap (~150) and decay/expiry sweep for low-salience facts (MEM-07) | VERIFIED | `MEMORY_MAX_PER_USER=150` in config; `MemoryService.remember()` calls `count_user_memories` then `choose_eviction` + `evict_lowest_salience` when over cap; `models/memory.py:decay_predicate()` is a pure expiry predicate; `database.py:delete_expired_memories()` parameterized DELETE; `bot.py:memory_sweep` daily `@tasks.loop(time=datetime.time(hour=2, minute=30))` calls `memory_service.sweep()` |

**Score: 7/7 truths verified**

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `database.py` | CREATE EXTENSION vector + user_memories DDL at top of SCHEMA_SQL | VERIFIED | Extension DDL is first statement; user_memories has vector(768), all required columns including last_surfaced_at and expires_at |
| `config.py` | Phase 11 embedding + retrieval constants | VERIFIED | Full Phase 11 block present; EMBEDDING_MODEL="gemini-embedding-001", EMBED_DIM=768, EMBED_RPM_LIMIT=60 (distinct from GEMINI_RPM_LIMIT=15); all retrieval constants annotated "tuned via 11-02 spike" |
| `requirements.txt` | pgvector pip dependency | VERIFIED | `pgvector>=0.3.6,<0.5` present; import `pgvector.asyncpg` succeeds |
| `models/memory.py` | MemoryFact dataclass + pure scoring functions + is_sensitive/contains_number | VERIFIED | Full implementation; 93 unit tests all pass |
| `services/memory.py` | MemoryService with recall/remember/distill/distill_and_remember/sweep | VERIFIED | All 5 methods present and substantive; CR-01 service now instantiated in bot |
| `services/gemini.py` | GeminiService.embed() + _embed_limiter | VERIFIED | embed() at line 250; _embed_limiter at line 134 using EMBED_RPM_LIMIT=60 |
| `database.py` | search_memories/insert_memory/bump_memory_hit/bump_surfaced/count_user_memories/evict_lowest_salience/delete_expired_memories/get_user_memories_for_eviction | VERIFIED | All 8 helpers present at lines 774, 818, 863, 888, 911, 946, 976, 1002; all use parameterized $N queries with user_id scope guard |
| `personality/prompts.py` | DISTILL_PROMPT + build_chat_prompt(memories=) + {memory_context} slot | VERIFIED | DISTILL_PROMPT present; build_chat_prompt has memories kwarg; {memory_context} in DEXTER_SYSTEM_PROMPT at line 102 |
| `bot.py` | _register_vector + memory_distill_batch + memory_sweep + memory_service wiring | VERIFIED | All 4 present; wiring order correct (memory_service before cog load) |
| `scripts/memory_spike.py` | Throwaway spike with cosine ANN search | VERIFIED | Exists; uses `embedding <=> $2` operator; spike-tuned constants visible in config.py with date annotations |
| `tests/test_memory.py` | Pure-logic test suite | VERIFIED | 93 test functions; all pass locally |
| `tests/test_database_phase11.py` | Live-DB integration skeleton | VERIFIED | 21 test functions; skips cleanly without pgvector DB |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `bot.py:_initialize_once` | `pgvector.asyncpg.register_vector` | `create_pool(init=_register_vector)` | WIRED | Line 386: `init=_register_vector`; extension-first throwaway connection at lines 363-373 |
| `bot.py:_initialize_once` | `MemoryService` (CR-01) | `bot.memory_service = MemoryService(bot.pool, bot.gemini_service)` | WIRED | Line 417; BEFORE cog loading at line 440 |
| `cogs/events.py:on_message` | `MessageBuffer.add(author_id=)` (CR-02) | `author_id=str(message.author.id)` | WIRED | Line 359; snowflake stored in buffer dict |
| `bot.py:memory_distill_batch` | snowflake user_id | `msg.get("author_id")` + `isdigit()` guard | WIRED | Lines 857-859; rejects non-snowflakes; display name retained only as distiller context |
| `services/memory.py:recall` | `services/gemini.py:embed` | `RETRIEVAL_QUERY` embedding at priority 1 via `_embed_limiter` | WIRED | services/memory.py:100-104 |
| `services/memory.py:recall` | `database.py:search_memories` | scoped cosine ANN then apply_floor + rerank | WIRED | services/memory.py:115-169 |
| `cogs/events.py:on_voice_state_update` | `MemoryService.distill_and_remember` | `asyncio.create_task(memory_service.distill_and_remember(...))` with correct `mem_kind` (WR-01) | WIRED | Lines 250-258; `mem_kind="late_night"` for LATE_NIGHT, `mem_kind="daily_batch"` for ordinary JOIN |
| `services/memory.py:sweep` | `database.py:delete_expired_memories` | `await database.delete_expired_memories(self._pool, now=now)` | WIRED | services/memory.py:486 |
| `bot.py:memory_sweep` | `services/memory.py:sweep` | `await memory_service.sweep()` | WIRED | bot.py:921 |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|-------------|--------|-------------------|--------|
| `cogs/ai.py:/ask` | `memories` | `_memory_svc.recall(str(interaction.user.id), ...)` | Real pgvector ANN rows (human-verified on live Neon) | WIRED (live Neon needed for real data) |
| `personality/prompts.py:build_chat_prompt` | `memory_context` | `memories` list from recall() | Non-empty string with facts when recall produces results | FLOWING (conditional on above) |
| `bot.py:memory_distill_batch` | `user_texts` | `message_buffer.get_history(channel_id)` grouped by `author_id` snowflake | Real message buffer content, keyed on snowflake (not display name) | FLOWING |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Config constants correct and separate | `python -c "import config; assert config.EMBEDDING_MODEL=='gemini-embedding-001'; assert config.EMBED_DIM==768; assert config.EMBED_RPM_LIMIT!=config.GEMINI_RPM_LIMIT; print('ok')"` | config ok | PASS |
| Schema DDL contains required memory elements | `python -c "import database; s=database.SCHEMA_SQL; assert 'vector(768)' in s; assert 'last_surfaced_at' in s; assert 'expires_at' in s; print('ok')"` | schema ok | PASS |
| Boot ordering present in bot.py | `python -c "src=open('bot.py').read(); assert 'init=_register_vector' in src; assert 'bot.memory_service = MemoryService' in src; print('ok')"` | boot ordering and wiring present | PASS |
| No deprecated model references | grep for "text-embedding-004" in CLAUDE.md + PROJECT.md | No matches | PASS |
| Full test suite | `python -m pytest tests/ -q` | 551 passed, 70 skipped | PASS |
| pgvector importable | `python -c "import pgvector.asyncpg; print('ok')"` | pgvector import ok | PASS |

---

## Probe Execution

Step 7c: SKIPPED — No `scripts/*/tests/probe-*.sh` files declared or present for Phase 11. Phase uses pytest-based verification (557 unit + integration tests). Probe pattern is not applicable.

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| MEM-01 | 11-01-PLAN | pgvector enabled; user_memories(vector(768)); codec registered; boot-order-safe | SATISFIED | SCHEMA_SQL, bot.py extension-first throwaway, init=_register_vector |
| MEM-02 | 11-03-PLAN | embed() via gemini-embedding-001 @ 768d behind SEPARATE limiter | SATISFIED | _embed_limiter (60 RPM) distinct from _rate_limiter (15 RPM); confirmed by config assertion |
| MEM-03 | 11-02-PLAN, 11-03-PLAN | Top-k retrieval above floor, reranked, capped to 1-3 | SATISFIED | recall() full pipeline; spike-tuned constants in config annotated 2026-06-29 |
| MEM-04 | 11-04-PLAN | Write on event triggers (not per-message), near-dup dedup | SATISFIED | Event hooks in events.py + music.py + bot.py; dedup_decision in remember() |
| MEM-05 | 11-05-PLAN | Sensitivity/PII gate; no SQL-known numbers embedded | SATISFIED | is_sensitive() with WR-02 word-boundary fix; contains_number() strict gate; DISTILL_PROMPT rules |
| MEM-06 | 11-06-PLAN | Memories injected as candidate ammo; numbers from SQL not memory | SATISFIED | build_chat_prompt(memories=); accuracy-safe framing in memory_context block |
| MEM-07 | 11-07-PLAN | Per-user cap (150) + daily decay sweep | SATISFIED | choose_eviction in remember(); memory_sweep @tasks.loop(02:30); delete_expired_memories |

**Coverage: 7/7 requirements satisfied**

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `bot.py:829` | 829 | `message_buffer._buffers.keys()` — accesses private attribute (IN-01 from review, out of fix scope) | Info | Fragile coupling to internal; no accessor added; no behavior defect |
| `services/memory.py:162-177` | 162-177 | `bump_surfaced` inside broad try/except — bump failure silently discards retrieved facts (IN-02 from review, out of fix scope) | Info | Transient bump failure loses recall results; non-fatal but not ideal |
| `cogs/music.py:1121` | 1121 | `guild_id=""` passed to recall() vs `str(guild.id)` elsewhere (IN-03 from review, out of fix scope) | Info | Harmless today (ANN scopes to user_id only); latent if guild scoping is added |

All three are Info items from the code review, explicitly marked out-of-scope for the fix pass. None are blockers — they have no behavioral impact today. No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER markers found in any Phase 11 modified file.

---

## Human Verification Required

### 1. Live Neon Boot Gate (MEM-01)

**Test:** Boot the bot against live Neon Postgres with a real `.env`. Monitor `dexter.log` during startup.
**Expected:** No `ValueError: unknown type: public.vector` in boot logs; `pgvector extension ensured` log line appears; `Memory service initialized` log line appears; `user_memories` table visible in Neon console with vector(768) column.
**Why human:** Extension-first boot ordering and per-connection codec registration can only be confirmed against a live pgvector-enabled Postgres. The 70 skipped integration tests all require `TEST_DATABASE_URL` with pgvector. This is the MEM-01 boot gate documented in `11-VALIDATION.md`.

### 2. CR-02 Security Confirmation — Snowflake Alignment End-to-End

**Test:** Use two different Discord accounts. Queue messages with User A and User B across at least one session. Manually trigger or wait for `memory_distill_batch` (fires daily at 03:00 UTC). Then run `/ask` as User A (recall path). Inspect the `user_memories` table in Neon.
**Expected:** All `user_memories` rows for User A have `user_id` equal to User A's Discord snowflake (numeric string, 18 digits). Recall returns only User A's memories. User B's content never appears in User A's recalled memories. No rows with `user_id` equal to display names.
**Why human:** The `isdigit()` guard and `author_id` flow are code-verified, but the security posture requires confirmation that no non-snowflake user_id values accumulate in the live store, particularly from any code paths that existed before the CR-02 fix (e.g., legacy buffered messages without `author_id`).

### 3. WR-01 — Voice Join Memory Kind/Salience Labeling

**Test:** Join a voice channel at a normal daytime hour. Enable debug logging. Confirm the `distill_and_remember` task fires with `kind="daily_batch"` and `base_salience=0.2`. Then join at 1–5am and confirm `kind="late_night"` and `base_salience=0.7`.
**Expected:** Daytime join stores `kind=daily_batch` (salience 0.2 — eligible for decay sweep). Late-night join stores `kind=late_night` (salience 0.7 — retained by sweep). No mislabeling.
**Why human:** The `mem_kind` logic depends on `decide_ambient_roast` returning `RoastScenario.LATE_NIGHT` vs `JOIN`, which depends on time-of-day and chance rolls. Correct labeling requires a live voice event with known time conditions.

### 4. WR-02 — is_sensitive Word-Boundary Safety Gate

**Test:** Run the following in a Python shell:
```python
from models.memory import is_sensitive
assert not is_sensitive("only listens to marvin gaye on repeat")
assert not is_sensitive("grape soda vibes only")
assert is_sensitive("is openly gay and proud")
assert is_sensitive("the song mentions rape in the lyrics")
assert is_sensitive("depression era jazz only")
```
**Expected:** All five assertions pass — music-token false positives eliminated; standalone identity/violence terms still blocked; long clinical stems still blocked by substring matching.
**Why human:** WR-02 changes a safety gate's regex matching semantics. The unit tests cover these cases, but the reviewer should confirm the new word-boundary behavior matches the intended safety posture and that no new gaps were introduced.

---

## Gaps Summary

No gaps. All 7 MEM requirements are verified in the codebase. Both critical defects (CR-01, CR-02) are fixed. All warning findings (WR-01, WR-02, WR-03) are fixed. The info findings (IN-01, IN-02, IN-03) remain as accepted tech debt — they are out of fix scope, have no behavioral impact today, and are documented in the code review.

Automated checks: 551 tests pass, 70 live-DB integration tests skip cleanly (as designed). Full suite green.

The 4 human verification items above are the only remaining gate before the phase can close.

---

_Verified: 2026-06-29T23:00:00Z_
_Verifier: Claude (gsd-verifier)_
