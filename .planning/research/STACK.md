# Stack Research

**Domain:** RAG long-term memory (pgvector-on-Neon + Gemini embeddings) bolted onto an existing discord.py + asyncpg + google-genai bot
**Researched:** 2026-06-26
**Confidence:** HIGH (pgvector/asyncpg integration + Gemini embeddings API verified via Context7; free-tier limits + text-embedding-004 deprecation verified via Google docs/blog)

> **Scope:** This is a *stack-addition* research for milestone v1.2 / Phase 11. The existing stack
> (Python 3.11, discord.py, asyncpg→Neon, google-genai, the shared 15 RPM `_RateLimiter`) is fixed and
> NOT re-evaluated here. The only goal: store roast-worthy user facts as vectors in the **existing Neon
> Postgres** via `pgvector`, embed them with the **existing Gemini API key**, and retrieve the most
> semantically-relevant ones at roast time. Zero new infrastructure, zero new monthly cost.

## Headline Decisions (read this first)

1. **Embedding model = `gemini-embedding-001`, NOT `text-embedding-004`.** `text-embedding-004` reached
   its deprecation date on **2026-01-14** (already past as of today, 2026-06-26). The milestone brief and
   PROJECT.md still name `text-embedding-004` — that is stale and must be corrected to `gemini-embedding-001`.
2. **Embed at 768 dimensions** (via `output_dimensionality=768`), not the default 3072. 768 is the
   pgvector *indexable* sweet spot (the `vector` type can only be indexed up to 2000 dims) and is the
   smallest of Google's three "high-quality" MRL tiers. Storing at 3072 would block HNSW/IVFFlat entirely.
3. **One new pip dependency only: `pgvector`** (the Python package, for the asyncpg vector codec + `Vector`
   helper). Everything else (asyncpg, google-genai) is already installed.
4. **Do NOT route embedding calls through the existing shared 15 RPM `_RateLimiter`.** Embeddings have a
   *separate* 100 RPM free-tier quota at Google's end; sharing the chat limiter would needlessly starve
   `/ask`. Give embeddings their own small limiter (or batch them so the call count is trivial).

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `pgvector` Postgres extension | **0.8.x** (Neon-provided) | Adds the `vector` column type + ANN index types + distance operators to the existing Neon Postgres | Zero new infra — it's an extension on the DB already in use. Neon ships pgvector on all plans (incl. free); enable per-database with `CREATE EXTENSION`. |
| `pgvector` Python package | **0.4.x** (current; pin `>=0.3.6,<0.5`) | `from pgvector.asyncpg import register_vector` (type codec) + `from pgvector import Vector` (binary-safe wrapper) | The canonical, maintained asyncpg integration. Registers the `vector` codec so you pass/receive Python lists instead of hand-serialising `'[1,2,3]'` strings. |
| `gemini-embedding-001` (Gemini API) | GA model | Turns fact text + query text into 768-d float vectors via the existing `google-genai` client | Current GA embedding model; uses Matryoshka (MRL) so you can truncate to 768/1536/3072. Free tier (100 RPM) covers a single-community bot easily. Replaces the deprecated `text-embedding-004`. |
| `asyncpg` | **0.31.0** (already installed) | Pool + per-connection `init=` callback that registers the vector codec | Already the project's driver; its `create_pool(init=...)` hook is exactly where `register_vector` must run. No version bump needed. |
| `google-genai` | already installed (≥1.x) | `client.aio.models.embed_content(...)` async embeddings | Same SDK and same `genai.Client` already wired in `services/gemini.py`. No new SDK. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none required) | — | — | The RAG feature needs **only** the `pgvector` pip package. No `numpy`, no LangChain, no vector-DB client. |
| `numpy` (optional) | any | L2-normalise 768-d vectors before storage if you choose cosine-equivalent inner-product indexing | Only if you go the `<#>` (inner-product) route. With the recommended cosine (`<=>`) route, normalisation is unnecessary — skip numpy. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `psql` against Neon | One-time `CREATE EXTENSION` + sanity-check index | `CREATE EXTENSION IF NOT EXISTS vector;` is idempotent and belongs in `SCHEMA_SQL` (it's plain DDL, no `$N` params — fits the existing asyncpg multi-statement constraint). |
| `EXPLAIN ANALYZE` | Confirm the ANN index is actually used (or confirm seq-scan is fine at this scale) | At a few thousand rows a seq scan is sub-ms; don't cargo-cult an index you can't measure. |

## Installation

```bash
# The ONLY new dependency
pip install "pgvector>=0.3.6,<0.5"     # add to requirements.txt

# Already present — listed for completeness, do NOT reinstall/bump:
#   asyncpg==0.31.0
#   google-genai
```

```sql
-- One-time, idempotent; add to database.py SCHEMA_SQL (plain DDL, no $N params).
-- Must run BEFORE the pool's init= callback registers the vector codec (see Gotchas).
CREATE EXTENSION IF NOT EXISTS vector;
```

## The asyncpg + pgvector + Neon integration (the load-bearing part)

This is the piece the brief flagged as "must not be hand-waved." Concrete pattern:

### 1. Register the codec in the pool `init=` callback

```python
from pgvector.asyncpg import register_vector

async def _init_connection(conn: asyncpg.Connection) -> None:
    # Runs ONCE per physical connection as the pool creates it.
    await register_vector(conn)   # registers the vector / halfvec / sparsevec codecs

pool = await asyncpg.create_pool(
    sanitize_database_url(config.DATABASE_URL),
    ssl="require",                              # existing Neon requirement (K-04)
    statement_cache_size=0,                     # existing Neon/PgBouncer requirement (K-04)
    max_inactive_connection_lifetime=240,       # existing Neon scale-to-zero guard (K-04)
    min_size=config.DB_POOL_MIN,
    max_size=config.DB_POOL_MAX,
    init=_init_connection,                      # <-- the only new line
)
```

After `register_vector`, you pass/receive plain Python lists:

```python
# write a fact embedding (768 floats as a list)
await conn.execute(
    "INSERT INTO user_facts (user_id, fact, embedding) VALUES ($1, $2, $3)",
    user_id, fact_text, embedding_list,          # embedding_list: list[float] len 768
)

# retrieve top-K most relevant facts for a user (cosine distance)
rows = await conn.fetch(
    "SELECT fact FROM user_facts"
    " WHERE user_id = $1"
    " ORDER BY embedding <=> $2"
    " LIMIT $3",
    user_id, query_embedding_list, k,
)
```

### 2. How `statement_cache_size=0` interacts with `register_vector` — VERIFIED NON-ISSUE

- `register_vector` works by introspecting the `vector` type's OID once and calling
  `conn.set_type_codec(...)`. This is a **per-connection codec registration**, not a prepared statement,
  so the existing `statement_cache_size=0` (set for Neon's PgBouncer transaction mode) does **not**
  break it. The `init=` callback fires once per physical connection at creation, which is exactly the
  right granularity — every pooled connection ends up with the codec.
- This is the standard, documented pgvector-python asyncpg pattern (Context7 `/pgvector/pgvector-python`).
  No special handling beyond putting `register_vector` in `init=`.

### 3. Neon-specific ordering gotcha (the one real trap)

- `register_vector` **raises `ValueError` if the `vector` type does not yet exist** when the codec is
  registered. Because the `init=` callback fires on *every* connection at pool-creation time, the
  `CREATE EXTENSION vector` must have already run. **Order of operations:**
  1. Acquire a bootstrap connection (or run `SCHEMA_SQL` which now contains `CREATE EXTENSION IF NOT EXISTS vector;`) **before** the long-lived pool is created with the `init=` callback, **or**
  2. Make the pool's `init=` tolerant on first boot.
  Cleanest fit for this codebase: keep one-time `CREATE EXTENSION` at the very top of `SCHEMA_SQL`,
  and make sure `init_db()` (which runs `SCHEMA_SQL`) executes against a connection created **before**
  the codec-registering pool — or run the extension DDL on a throwaway `asyncpg.connect()` prior to
  `create_pool(init=...)`.
- Neon's `vector` type OID is stable per database; no per-request OID churn. With `min_size>=2` the
  codec is registered on the warm connections at startup.

## Vector index choice (HNSW vs IVFFlat) — justified for THIS scale

| | HNSW | IVFFlat | No index (seq scan) |
|---|---|---|---|
| Build needs data first? | No | **Yes** (needs representative rows to train centroids) | n/a |
| Recall | Highest | Good if `lists`/`probes` tuned | Exact (100%) |
| Build/memory cost | Higher | Lower | None |
| Good at < ~10k rows? | Overkill but fine | Awkward (centroids on tiny data are poor) | **Perfectly fine, sub-ms** |

**Recommendation for a single-community bot:**
- The fact corpus is realistically **hundreds to low-thousands of rows**. At that size a **sequential
  scan over 768-d vectors is sub-millisecond** — an ANN index is not strictly necessary on day one.
- When you do add an index (cheap insurance, and harmless), use **HNSW**, not IVFFlat. HNSW needs no
  training data, so it works from row zero; IVFFlat's centroids are garbage on a tiny/empty table and
  would need a rebuild once data lands.
- **Operator class:** `vector_cosine_ops`; **query operator:** `<=>` (cosine distance). Gemini
  embeddings are semantic-similarity vectors and cosine is the conventional, robust choice.

```sql
-- Add when/if the corpus grows; HNSW works even on an empty table.
CREATE INDEX IF NOT EXISTS idx_user_facts_embedding
    ON user_facts USING hnsw (embedding vector_cosine_ops);
```

> Note: index this only at **768 dims**. The `vector` type's ANN indexes (HNSW/IVFFlat) cap at **2000
> dimensions** — the default 3072-d `gemini-embedding-001` output would be *unindexable* without
> switching to the `halfvec` type. Embedding at 768 sidesteps this entirely.

## Gemini embeddings — exact call + quota integration

```python
from google.genai import types

# WRITE side (storing a fact) — task_type tunes the vector for being a stored document
resp = await client.aio.models.embed_content(
    model="gemini-embedding-001",
    contents=[fact_text],                      # accepts a LIST → batch many facts in one call
    config=types.EmbedContentConfig(
        output_dimensionality=768,             # MRL truncation; 768 is indexable + cheap
        task_type="RETRIEVAL_DOCUMENT",
    ),
)
vec = resp.embeddings[0].values                # list[float], length 768

# READ side (retrieving for a roast) — different task_type for the query
resp = await client.aio.models.embed_content(
    model="gemini-embedding-001",
    contents=[roast_context_text],
    config=types.EmbedContentConfig(
        output_dimensionality=768,
        task_type="RETRIEVAL_QUERY",
    ),
)
query_vec = resp.embeddings[0].values
```

Key facts (verified):
- **Model name:** `gemini-embedding-001`. **Dimensions:** default 3072; supports MRL truncation to
  **768 / 1536 / 3072** (Google's three recommended quality tiers). Use **768**.
- **Normalization:** at 3072 the output is already normalised; at **768 you must L2-normalise yourself**
  *if* you later switch to inner-product (`<#>`) indexing. With the recommended **cosine (`<=>`)**
  operator, normalisation is irrelevant (cosine is scale-invariant) — so you can skip it. (This is why
  the cosine route avoids the optional numpy dependency.)
- **task_type matters:** use `RETRIEVAL_DOCUMENT` when embedding facts for storage and `RETRIEVAL_QUERY`
  when embedding the roast context for lookup. Mismatching them measurably degrades retrieval quality.
- **Response shape:** `response.embeddings` is a list of `ContentEmbedding`; each has `.values`
  (`list[float]`). For a single input, use `response.embeddings[0].values`.
- **Free-tier rate limit:** ~**100 RPM** for `gemini-embedding-001` — a **separate quota** from the
  `gemini-2.x-flash` generation budget.

### Integration with the existing shared 15 RPM `_RateLimiter`

- The existing `_RateLimiter` in `services/gemini.py` is **one shared 15 RPM counter for all generation
  features** (chat + image). Embeddings hit a **different Google quota (100 RPM)**, so feeding them
  through the same 15-slot window would needlessly contend with `/ask` and starve user commands for no
  real benefit.
- **Recommendation:** give embeddings a **separate `_RateLimiter` instance** sized conservatively
  (e.g. 60 RPM, well under the 100 RPM ceiling), or — better — make the call count trivial via batching:
  - `embed_content(contents=[...])` accepts a **list**, so a fact-extraction pass can embed many facts in
    **one** request. Storing N facts ≈ 1 API call.
  - Retrieval embeds **one** query string per roast → 1 call. Gate it to *callback* roasts only (not
    every ambient roast) to keep call volume negligible.
- **Priority:** fact-storage embeddings are background → treat as **priority 2** (reject/skip if the
  limiter is saturated; a missed fact-write is harmless). Retrieval at roast time is user-facing-ish but
  has a guaranteed template fallback, so it can also degrade gracefully.

## Proposed schema addition (fits existing `SCHEMA_SQL` conventions)

```sql
CREATE EXTENSION IF NOT EXISTS vector;          -- top of SCHEMA_SQL, runs before codec registration

CREATE TABLE IF NOT EXISTS user_facts (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    guild_id    TEXT,
    fact        TEXT NOT NULL,
    embedding   vector(768) NOT NULL,           -- 768-d gemini-embedding-001 output
    created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_facts_user ON user_facts(user_id, created_at DESC);
-- HNSW ANN index optional at this scale; add when corpus grows:
-- CREATE INDEX IF NOT EXISTS idx_user_facts_embedding
--     ON user_facts USING hnsw (embedding vector_cosine_ops);
```

All consistent with the existing idempotent `CREATE TABLE IF NOT EXISTS` + plain-DDL pattern (no `$N`
params, so it stays inside one `conn.execute(SCHEMA_SQL)`).

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `gemini-embedding-001` @ 768d | `text-embedding-004` | **Never** — deprecated 2026-01-14, already past. Listed only to flag the stale reference in the brief. |
| Embed at **768** dims | 3072 (default) or 1536 | Only if retrieval quality at 768 proves insufficient — but 3072 forces `halfvec` to stay indexable and 4× the storage. Bump to 1536 before 3072. |
| **HNSW** index (or none) | IVFFlat | Only at large, stable corpora (≫10k rows) where build time/memory matters and you can train centroids on representative data. Not this bot. |
| Cosine `<=>` (`vector_cosine_ops`) | Inner product `<#>` (`vector_ip_ops`) | Marginally faster *if* you pre-normalise vectors. Not worth the extra normalisation step + numpy dep at this scale. |
| `pgvector` pip package | Hand-rolled `'[1,2,3]'` string serialisation | Never — error-prone, no binary protocol, no type safety. The package is one dependency and removes a whole class of bugs. |
| pgvector on existing Neon | Dedicated vector DB (Pinecone, Qdrant, Chroma, Redis) | Never for this milestone — violates the zero-new-infra / zero-cost constraint. The whole point is reusing Neon. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `text-embedding-004` | Deprecated 2026-01-14 (past). API calls will be rejected/sunset. | `gemini-embedding-001` |
| `google-generativeai` (old SDK) for embeddings | Deprecated SDK; project already standardised on `google-genai` | Existing `genai.Client(...).aio.models.embed_content` |
| Routing embeddings through the shared 15 RPM chat limiter | Embeddings have a separate 100 RPM quota; sharing starves `/ask` | Separate embedding limiter (~60 RPM) + batched writes |
| 3072-d vectors with an ANN index | `vector` ANN indexes cap at 2000 dims → 3072 is unindexable without `halfvec` | 768-d `vector(768)` |
| IVFFlat on a small/empty table | Centroid training needs representative data; poor recall on tiny corpora, needs rebuild | HNSW (works from row zero) or no index |
| LangChain / vecs / a vector-DB client | Heavy dependency for one table + two SQL queries; nothing here needs an abstraction layer | Raw asyncpg + `pgvector` codec |
| Forgetting `register_vector` in `init=` | Without it you must serialise vectors as strings and asyncpg returns text, not lists | `init=_init_connection` with `register_vector(conn)` |

## Stack Patterns by Variant

**If the fact corpus stays in the hundreds–low-thousands (expected):**
- Skip the ANN index entirely; a seq scan with `ORDER BY embedding <=> $1 LIMIT k` is sub-ms.
- Batch fact-storage embeddings (one `embed_content` call per extraction pass).

**If retrieval quality at 768d feels weak:**
- Bump `output_dimensionality` to 1536 (still indexable under the 2000-dim cap), re-embed existing rows.
- Do NOT jump to 3072 unless you switch the column to `halfvec(3072)` for index support.

**If the corpus unexpectedly grows past ~10k rows:**
- Add the HNSW index (`vector_cosine_ops`). Still no IVFFlat — HNSW's no-training property keeps ops simple.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `pgvector` (py) 0.3.6–0.4.x | `asyncpg` 0.31.0 | `pgvector.asyncpg.register_vector` targets asyncpg's `set_type_codec`; stable across these versions. |
| `pgvector` (py) | pgvector ext 0.5+ | `halfvec`/`sparsevec` codecs need ext ≥0.7; `vector` codec works on any modern ext. Neon ships 0.8.x. |
| `register_vector` + `statement_cache_size=0` | Neon/PgBouncer tx mode | Verified compatible — codec registration is per-connection, not a prepared statement. |
| `vector(d)` ANN index | `d <= 2000` | Embed at 768 (or ≤2000) to keep HNSW/IVFFlat usable; else use `halfvec` (≤4000). |
| `gemini-embedding-001` `output_dimensionality` | newer models only | Not supported on legacy `models/embedding-001`; supported on `gemini-embedding-001` / `text-embedding-004`. |

## Sources

- `/pgvector/pgvector-python` (Context7) — `register_vector(conn, schema)` signature, asyncpg pool `init=` pattern, `Vector` helper, HNSW `vector_cosine_ops`, `<=>`/`<->` operators, `OpClass` literals — HIGH
- `/googleapis/python-genai` (Context7, v1.33.0) — `embed_content(*, model, contents, config)`, async `aio.models.embed_content`, `EmbedContentConfig(output_dimensionality=, task_type=)`, `gemini-embedding-001` usage — HIGH
- [Gemini Embedding GA — Google Developers Blog](https://developers.googleblog.com/gemini-embedding-available-gemini-api/) — model GA status, MRL dimensions — HIGH
- [Embeddings | Gemini API docs](https://ai.google.dev/gemini-api/docs/embeddings) — `gemini-embedding-001`, 3072 default, 768/1536/3072 recommended tiers, manual normalization for non-3072 dims — HIGH
- [gemini-embedding-001 Dimensions & Pricing Guide 2026 — TokenMix](https://tokenmix.ai/blog/gemini-embedding-001-dimensions-pricing-guide-2026) — free-tier 100 RPM, dimension tiers — MEDIUM
- text-embedding-004 deprecation date 2026-01-14 (Google deprecation notice, corroborated by [n8n community thread](https://community.n8n.io/t/google-deprecating-text-embedding-004-but-gemini-embedding-001-doesnt-work/262008)) — MEDIUM
- Existing code: `services/gemini.py` (`genai.Client`, `_RateLimiter`), `database.py` (`SCHEMA_SQL`, asyncpg pool helpers), `config.py` (Neon pool tuning K-04) — HIGH

---
*Stack research for: pgvector-on-Neon + Gemini embeddings RAG memory (Dexter v1.2 / Phase 11)*
*Researched: 2026-06-26*
