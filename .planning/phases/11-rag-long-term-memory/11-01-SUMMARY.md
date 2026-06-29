---
phase: 11-rag-long-term-memory
plan: 01
subsystem: database
tags: [pgvector, asyncpg, postgres, embeddings, gemini-embedding-001, rag, neon]

# Dependency graph
requires:
  - phase: 9-reliability-ops-hardening
    provides: asyncpg pool wiring with K-04 Neon tuning (ssl, statement_cache_size, max_inactive_connection_lifetime)
  - phase: 4-scale
    provides: init_db, SCHEMA_SQL pattern, asyncpg pool creation pattern in bot.py _initialize_once
provides:
  - pgvector extension-first boot ordering (throwaway connect → CREATE EXTENSION before create_pool(init=_register_vector))
  - user_memories table with vector(768) embedding column + idx_user_memories_user index in SCHEMA_SQL
  - Phase 11 config constants: EMBEDDING_MODEL, EMBED_DIM, EMBED_RPM_LIMIT (separate from 15 RPM chat budget), MEMORY_TOP_K/SIMILARITY_FLOOR/DEDUP_THRESHOLD/INJECT_CAP/MAX_PER_USER/DECAY_DAYS, MEMORY_RERANK_* weights, MEMORY_CALLBACK_CHANCE, MEMORY_DISTILL_BATCH_HOUR
  - pgvector>=0.3.6,<0.5 pinned in requirements.txt (installed 0.4.2)
  - Wave-0 test scaffold: tests/test_memory.py collects and passes; tests/test_database_phase11.py skips cleanly without live DB
  - Corrected stale text-embedding-004 → gemini-embedding-001 @ 768d references
affects:
  - 11-02-spike (validates MEDIUM-confidence retrieval priors against this infrastructure)
  - 11-03 (insert_memory, search_memories DB helpers use user_memories table + vector codec)
  - 11-04 (models/memory.py pure-logic tests land in tests/test_memory.py scaffold)
  - all Phase 11 plans (depend on EMBEDDING_MODEL, EMBED_DIM, EMBED_RPM_LIMIT constants)

# Tech tracking
tech-stack:
  added:
    - pgvector 0.4.2 (pgvector>=0.3.6,<0.5 pin; PyPI maintained by Andrew Kane, github.com/pgvector/pgvector-python)
  patterns:
    - Extension-first boot ordering: throwaway asyncpg.connect() runs CREATE EXTENSION before create_pool(init=) so no pooled connection raises "unknown type: public.vector"
    - Per-connection codec registration via create_pool(init=_register_vector) — compatible with statement_cache_size=0 (codec is set_type_codec, not a prepared statement)
    - EMBED_RPM_LIMIT is a SEPARATE quota constant (60 RPM) never shared with the 15 RPM GEMINI_RPM_LIMIT

key-files:
  created:
    - tests/test_memory.py (Wave-0 pure-logic test scaffold)
    - tests/test_database_phase11.py (opt-in live-DB integration skeleton; stubs for 11-03/11-04)
  modified:
    - requirements.txt (added pgvector>=0.3.6,<0.5)
    - config.py (Phase 11 constants block: EMBEDDING_MODEL through MEMORY_DISTILL_BATCH_HOUR)
    - database.py (SCHEMA_SQL: CREATE EXTENSION vector + user_memories DDL at top)
    - bot.py (register_vector import, _register_vector helper, extension-first boot in _initialize_once)
    - .planning/PROJECT.md (corrected text-embedding-004 → gemini-embedding-001 @ 768d)

key-decisions:
  - "EMBED_RPM_LIMIT=60 is a separate constant from GEMINI_RPM_LIMIT=15 — embeddings use a different Gemini quota bucket and must never be counted against the shared chat RPM (Critical Rule 1 / A2)"
  - "Extension-first: throwaway asyncpg.connect() runs CREATE EXTENSION before create_pool(init=_register_vector) — the only pattern that prevents 'unknown type: public.vector' on the first pool acquire (T-11-01 / Pitfall 1)"
  - "statement_cache_size=0 is compatible with the pgvector codec (per-connection set_type_codec is not a prepared statement) — Pitfall 2 misbelief does not apply"
  - "No HNSW/IVFFlat index on day one — sequential scan is correct for day-1 cardinality; ANN index added when MEMORY_MAX_PER_USER fills (11-RESEARCH recommendation)"
  - "All Phase 11 numeric retrieval constants are annotated 'prior — validate via 11-02 spike' to make their MEDIUM-confidence status explicit and remind executors not to treat them as tuned"

patterns-established:
  - "Extension-first boot: always CREATE EXTENSION on a throwaway connection BEFORE create_pool(init=codec_register) for any asyncpg codec that depends on a Postgres extension"
  - "Separate RPM budgets: each Gemini feature class (chat=15, embeddings=60) gets its own config constant — never share the chat limiter for non-chat calls"

requirements-completed: [MEM-01]

# Metrics
duration: 13min
completed: 2026-06-29
---

# Phase 11 Plan 01: RAG Foundation Summary

**pgvector extension-first boot with user_memories(vector(768)) table, per-connection codec registration via create_pool(init=_register_vector), and Phase 11 config constants (gemini-embedding-001 @ 768d, separate 60 RPM embedding budget)**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-06-29T08:21:14Z
- **Completed:** 2026-06-29T08:34:03Z
- **Tasks:** 2 executed (Task 1 was a checkpoint gate, approved by human; Tasks 2 and 3 auto)
- **Files modified:** 7 (requirements.txt, config.py, database.py, bot.py, .planning/PROJECT.md, tests/test_memory.py [created], tests/test_database_phase11.py [created])

## Accomplishments

- pgvector 0.4.2 installed and pinned; import verified (`pgvector.asyncpg` imports clean)
- user_memories table with `vector(768)` embedding column and all Phase 11 columns (salience, hit_count, last_surfaced_at, surface_count, expires_at) added to SCHEMA_SQL as plain DDL — no $N params (asyncpg multi-statement constraint upheld)
- Extension-first boot ordering in `_initialize_once`: throwaway `asyncpg.connect()` runs `CREATE EXTENSION IF NOT EXISTS vector` before `create_pool(init=_register_vector)` — T-11-01 / Pitfall 1 mitigation implemented
- Phase 11 config constants added (15 constants total); EMBED_RPM_LIMIT=60 is explicitly separate from GEMINI_RPM_LIMIT=15 with annotation
- Stale `text-embedding-004` reference in .planning/PROJECT.md corrected to `gemini-embedding-001 @ 768d` (CLAUDE.md had no stale reference)
- Wave-0 test scaffold: `tests/test_memory.py` collects and passes (1 test); `tests/test_database_phase11.py` skips cleanly without live DB (6 skipped)
- Full suite: 420 passed, 4 skipped — no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1 (checkpoint:human-verify):** pgvector legitimacy gate — approved by human; no commit
2. **Task 2: pgvector dep, Phase 11 config constants, model ref fix** - `ca0da22` (chore)
3. **Task 3: user_memories schema, extension-first boot, Wave-0 scaffold** - `1f51504` (feat)

**Plan metadata:** (see final commit below)

## Files Created/Modified

- `requirements.txt` — added `pgvector>=0.3.6,<0.5` (installed 0.4.2)
- `config.py` — Phase 11 RAG constants block (EMBEDDING_MODEL through MEMORY_DISTILL_BATCH_HOUR, 15 constants)
- `database.py` — `CREATE EXTENSION IF NOT EXISTS vector` + `user_memories` DDL prepended to SCHEMA_SQL
- `bot.py` — `register_vector` import, `_register_vector` per-connection init, extension-first throwaway connect, `init=_register_vector` on create_pool
- `.planning/PROJECT.md` — corrected `text-embedding-004` → `gemini-embedding-001 @ 768d`
- `tests/test_memory.py` — Wave-0 scaffold (created)
- `tests/test_database_phase11.py` — live-DB integration skeleton with skip guard (created)

## Decisions Made

- EMBED_RPM_LIMIT=60 is a separate constant — embeddings use a different Gemini quota bucket, must never consume the shared 15 RPM chat budget (Critical Rule 1 / A2)
- Extension-first boot ordering is the only safe pattern for asyncpg + pgvector: throwaway connect runs CREATE EXTENSION before any pooled connection can try to decode a vector column
- `statement_cache_size=0` is verified compatible with per-connection codec registration (it's `set_type_codec`, not a prepared statement) — Pitfall 2 misbelief confirmed and documented
- No HNSW/IVFFlat index on day one per RESEARCH recommendation (seq scan is fine at initial cardinality)
- All numeric retrieval priors annotated `# prior — validate via 11-02 spike` to make their MEDIUM-confidence status explicit

## Deviations from Plan

None — plan executed exactly as written. The `text-embedding-004` reference was absent from CLAUDE.md (plan said to check both files; only PROJECT.md needed the fix), which is a no-op not a deviation.

## Issues Encountered

None. pgvector 0.4.2 installed cleanly via `python -m pip install` (pip binary had a permission issue in the bash env; python -m pip worked). Full test suite stayed green.

## User Setup Required

**Manual step required before the bot can boot against Neon with the pgvector extension.**

The Neon Postgres database does NOT have the pgvector extension automatically. The bot's extension-first boot ordering (`CREATE EXTENSION IF NOT EXISTS vector` via throwaway connect) will run on startup and enable it — BUT the Neon project must have pgvector available.

On Neon, the `vector` extension is pre-installed on all Postgres 16+ projects (no `apt install` needed). The bot's `CREATE EXTENSION IF NOT EXISTS vector` DDL handles activation automatically on first boot.

**If using a local Postgres:** run `CREATE EXTENSION IF NOT EXISTS vector;` in the database after installing the pgvector Postgres server extension (`apt install postgresql-16-pgvector` or equivalent). The bot boot ordering will not fail gracefully if the server extension is absent — it will raise a `DuplicateObjectError` or `UndefinedFileError` from the DDL.

**This is the MEM-01 boot gate:** the first boot against Neon after this plan confirms success when `dexter.log` shows "pgvector extension ensured" without a `ValueError: unknown type: public.vector`.

## Next Phase Readiness

- 11-02 (spike): MEDIUM-confidence retrieval priors need validation — `MEMORY_SIMILARITY_FLOOR`, `MEMORY_TOP_K`, etc. are all annotated as priors
- 11-03 (MemoryService + DB helpers): `user_memories` table and `_register_vector` boot path are live; `insert_memory`, `search_memories`, `bump_memory_hit`, `bump_surfaced`, `count_user_memories`, `evict_lowest_salience`, `delete_expired_memories` can be added to `database.py` immediately
- All config constants referenced by later plans are present in `config.py`
- `tests/test_memory.py` scaffold is ready for 11-04's pure-logic test additions

## Known Stubs

- `tests/test_memory.py`: `TestMemoryScaffold.test_scaffold_collects` is an intentional placeholder — to be replaced by `TestRerank`, `TestDedup`, etc. in 11-04. Does not block plan goal.
- `tests/test_database_phase11.py`: 4 test stubs (`test_insert_and_search_memories`, `test_bump_hit_and_surface`, `test_evict_lowest_salience`, `test_delete_expired`) are explicitly `@pytest.mark.skip` stubs for 11-03/11-04. Does not block plan goal.

## Self-Check: PASSED

---
*Phase: 11-rag-long-term-memory*
*Completed: 2026-06-29*
