#!/usr/bin/env python3
"""scripts/memory_spike.py — THROWAWAY numeric-defaults validation spike.

Validates MEDIUM-confidence retrieval constants before 11-03 retrieval lands.
NOT imported by the bot. Run once manually:

    python scripts/memory_spike.py

What it does:
    1. Seeds a representative corpus of ~12 distilled music-personality facts
       for two fake user_ids, plus near-duplicate pairs and ~6 irrelevant decoys.
    2. Embeds each fact at 768d (RETRIEVAL_DOCUMENT) and inserts into user_memories.
    3. Embeds ~8 realistic roast queries (RETRIEVAL_QUERY) at 768d.
    4. Runs scoped cosine ANN search (embedding <=> operator) for each query.
    5. Prints per-query similarity rankings, the relevant/decoy separation gap
       (floor signal), and near-duplicate pair similarities (dedup-threshold signal).
    6. Proposes adjusted values for each retrieval constant based on distributions.
    7. Cleans up all spike rows in a finally block (non-destructive).

Security:
    T-11-02a: API key and DSN are never printed — read from env/config only.
              Only similarity scores + fact text appear in the output.
    T-11-02b: Fake Discord snowflake user_ids; cleanup deletes all rows by
              these ids unconditionally (even if the script errors partway).
"""

from __future__ import annotations

import asyncio
import math
import os
import sys

import asyncpg
from google import genai
from google.genai import types
from pgvector.asyncpg import register_vector

# Add project root to sys.path so `import config` resolves from scripts/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402

# ── Fake IDs (never real Discord snowflakes) ─────────────────────────────────
SPIKE_USER_A = "999999999999999001"  # main corpus: relevant facts + near-dups + decoys
SPIKE_USER_B = "999999999999999002"  # secondary corpus: verifies user-scoping
SPIKE_GUILD = "999999999999999099"  # fake guild id
SPIKE_USERS = (SPIKE_USER_A, SPIKE_USER_B)

# ── User A corpus: relevant facts ────────────────────────────────────────────
# Episode-style, third-person, NO numbers (Pitfall 5: numeric facts never stored).
USER_A_FACTS = [
    "swore he was done with the killers but kept coming back to play their songs",
    "confessed that melancholy indie rock genuinely helps him through rough patches",
    "queues the same heartbreak playlist every friday night without fail",
    "admitted he cried during a pixies song but immediately acted like it was ironic",
    "always skips the top search result and picks the second one out of stubbornness",
    "has a soft spot for early arctic monkeys that he actively pretends not to have",
    "called pop music braindead then let the bot auto-queue taylor swift for ages",
    "gets weirdly territorial when others request songs while he is already listening",
    "claims to have diverse taste but only ever queues sad indie and classic rock",
    "told someone they had bad taste in music then secretly queued nickelback",
    "gets unusually intense about songs nobody else in the server has ever heard of",
    "plays ten-minute progressive rock tracks and acts confused when people lose interest",
]

# Near-duplicate pairs — semantically close to originals; dedup should fire at >= threshold.
# Format: (near_dup_text, original_text, original_index_in_USER_A_FACTS)
USER_A_NEAR_DUPS = [
    (
        "swore he was done listening to the killers and was moving on with his life",
        USER_A_FACTS[0],
        0,
    ),
    (
        "always queues the same breakup playlist on friday evenings without exception",
        USER_A_FACTS[2],
        2,
    ),
]

# Irrelevant decoys in User A's corpus — should score low on music roast queries,
# providing the floor signal.
USER_A_DECOYS = [
    "regularly wakes up before dawn to go running and logs every workout meticulously",
    "has an extremely organized folder system for all digital files and documents",
    "spends most weekends cooking elaborate meals from scratch for friends",
    "collects vintage board games and hosts a game night once a month",
    "prefers cold weather and openly complains whenever the temperature gets too warm",
    "has been quietly learning a new programming language over the past several months",
]

# ── User B corpus ─────────────────────────────────────────────────────────────
# Different user — must never surface in User A queries (scoping integrity test).
USER_B_FACTS = [
    "only queues music when feeling reflective or in a melancholy mood",
    "has a playlist for every emotional state but refuses to discuss the sad one",
    "took over the queue once and played nothing but ambient electronic music for an hour",
    "skips any song that charted on a mainstream music list in the past year",
    "insists on playing full albums in order and gets visibly annoyed when tracks are skipped",
]

# ── Roast queries ─────────────────────────────────────────────────────────────
# Realistic context strings the bot would pass to recall() at a roast moment.
ROAST_QUERIES = [
    "what music does this person keep coming back to despite claiming not to like it",
    "does this person have genuine music taste or just performative ironic bad taste",
    "what embarrassing soft spot does this person have for a particular band or artist",
    "how does this person react when others request songs in voice channels",
    "does this person show vulnerability or emotion through their music choices",
    "what does this person actually queue when nobody is paying close attention",
    "does this person claim to have broad taste while actually being very narrow",
    "how does this person behave when their music opinions are challenged",
]


# ── Embedding helpers ─────────────────────────────────────────────────────────


async def embed_batch(
    client: genai.Client,
    texts: list[str],
    task_type: str,
) -> list[list[float]]:
    """Embed a batch of texts at config.EMBED_DIM using gemini-embedding-001.

    Uses RETRIEVAL_DOCUMENT on write and RETRIEVAL_QUERY on read — mismatching
    task_type degrades recall (11-RESEARCH Pitfall ~12 / RESEARCH.md task_type note).

    T-11-02a: API key is held inside `client`, never logged here.
    output_dimensionality must match vector(768) column (Pitfall 3: dim mismatch).
    """
    resp = await client.aio.models.embed_content(
        model=config.EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(
            output_dimensionality=config.EMBED_DIM,
            task_type=task_type,
        ),
    )
    return [e.values for e in resp.embeddings]


# ── Pool creation ─────────────────────────────────────────────────────────────


async def _register_vec(conn: asyncpg.Connection) -> None:
    """Per-connection init callback for create_pool (mirrors bot.py pattern)."""
    await register_vector(conn)


async def create_spike_pool() -> asyncpg.Pool:
    """Extension-first pool creation (Pattern 3 from 11-RESEARCH / 11-01).

    Ensures `CREATE EXTENSION IF NOT EXISTS vector` runs on a throwaway connection
    BEFORE the codec-registering pool is built. Prevents the boot crash where
    `init=_register_vec` fires before the `vector` type exists (Pitfall 1).

    T-11-02a: DSN sanitized via config.sanitize_database_url; never printed.
    """
    dsn = config.sanitize_database_url(config.DATABASE_URL)

    # Step 1: throwaway connection — ensure the extension exists.
    boot = await asyncpg.connect(dsn=dsn, ssl="require", statement_cache_size=0)
    try:
        await boot.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    finally:
        await boot.close()

    # Step 2: long-lived pool with codec registered on every connection.
    return await asyncpg.create_pool(
        dsn=dsn,
        min_size=1,
        max_size=3,
        ssl="require",
        statement_cache_size=0,  # K-04: Neon/PgBouncer compatibility
        max_inactive_connection_lifetime=config.DB_MAX_INACTIVE_CONN_LIFETIME,
        init=_register_vec,
    )


# ── DB operations ─────────────────────────────────────────────────────────────


async def insert_facts(
    pool: asyncpg.Pool,
    user_id: str,
    facts: list[str],
    embeddings: list[list[float]],
    kind: str,
) -> None:
    """Insert pre-embedded facts into user_memories for a spike user_id."""
    async with pool.acquire() as conn:
        for fact, emb in zip(facts, embeddings):
            await conn.execute(
                "INSERT INTO user_memories "
                "  (user_id, guild_id, kind, fact, embedding, salience) "
                "VALUES ($1, $2, $3, $4, $5, $6)",
                user_id,
                SPIKE_GUILD,
                kind,
                fact,
                emb,
                0.5,
            )


async def search_memories(
    pool: asyncpg.Pool,
    user_id: str,
    query_emb: list[float],
    k: int,
) -> list[dict]:
    """Scoped cosine ANN search using the embedding <=> cosine-distance operator.

    Returns top-k results ordered by ascending cosine distance (most similar first).
    similarity = 1 - cosine_distance = 1 - (embedding <=> query).
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT fact, kind, salience, "
            "       1 - (embedding <=> $2) AS similarity "
            "FROM user_memories "
            "WHERE user_id = $1 "
            "ORDER BY embedding <=> $2 "
            "LIMIT $3",
            user_id,
            query_emb,
            k,
        )
    return [
        {
            "fact": r["fact"],
            "kind": r["kind"],
            "similarity": float(r["similarity"]),
        }
        for r in rows
    ]


async def cleanup_spike(pool: asyncpg.Pool) -> None:
    """Delete all rows inserted by this spike (T-11-02b: non-destructive).

    Uses the fake SPIKE_USER_IDS to scope deletes — can never touch real data.
    """
    async with pool.acquire() as conn:
        for uid in SPIKE_USERS:
            await conn.execute("DELETE FROM user_memories WHERE user_id = $1", uid)
    print(f"[spike] Cleanup done — rows deleted for user_ids {SPIKE_USERS}")


# ── Pure analysis helpers ─────────────────────────────────────────────────────


def cosine_sim(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two float lists (pure Python, no numpy)."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def section(title: str) -> None:
    """Print a formatted section separator."""
    print(f"\n{'═' * 72}")
    print(f"  {title}")
    print(f"{'═' * 72}")


# ── Main ──────────────────────────────────────────────────────────────────────


async def main() -> None:
    # T-11-02a: key never printed; held inside genai.Client
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[spike] ERROR: GEMINI_API_KEY not set in environment.", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    print("[spike] Creating DB pool (extension-first bootstrap)...")
    pool = await create_spike_pool()

    try:
        # ── 1. Embed all seed facts ───────────────────────────────────────────
        nd_texts = [nd for nd, _orig, _idx in USER_A_NEAR_DUPS]

        print(
            f"[spike] Embedding User A relevant facts ({len(USER_A_FACTS)}) + "
            f"near-dups ({len(nd_texts)}) — RETRIEVAL_DOCUMENT..."
        )
        a_rel_all = USER_A_FACTS + nd_texts
        a_rel_all_embs = await embed_batch(client, a_rel_all, "RETRIEVAL_DOCUMENT")
        a_fact_embs = a_rel_all_embs[: len(USER_A_FACTS)]
        a_nd_embs = a_rel_all_embs[len(USER_A_FACTS) :]

        print(f"[spike] Embedding User A decoys ({len(USER_A_DECOYS)}) — RETRIEVAL_DOCUMENT...")
        a_decoy_embs = await embed_batch(client, USER_A_DECOYS, "RETRIEVAL_DOCUMENT")

        print(f"[spike] Embedding User B facts ({len(USER_B_FACTS)}) — RETRIEVAL_DOCUMENT...")
        b_embs = await embed_batch(client, USER_B_FACTS, "RETRIEVAL_DOCUMENT")

        print(f"[spike] Embedding roast queries ({len(ROAST_QUERIES)}) — RETRIEVAL_QUERY...")
        q_embs = await embed_batch(client, ROAST_QUERIES, "RETRIEVAL_QUERY")

        print(f"[spike] All embeddings done @ output_dimensionality={config.EMBED_DIM}d")

        # ── 2. Insert into user_memories ──────────────────────────────────────
        print("[spike] Inserting seed rows into user_memories...")
        await insert_facts(pool, SPIKE_USER_A, USER_A_FACTS, a_fact_embs, "spike_relevant")
        await insert_facts(pool, SPIKE_USER_A, nd_texts, a_nd_embs, "spike_near_dup")
        await insert_facts(pool, SPIKE_USER_A, USER_A_DECOYS, a_decoy_embs, "spike_decoy")
        await insert_facts(pool, SPIKE_USER_B, USER_B_FACTS, b_embs, "spike_b")
        total_rows = len(USER_A_FACTS) + len(nd_texts) + len(USER_A_DECOYS) + len(USER_B_FACTS)
        print(f"[spike] Inserted {total_rows} rows total.")

        # ── 3. Per-query similarity rankings ──────────────────────────────────
        section("PER-QUERY SIMILARITY RANKINGS  (User A corpus, scoped by user_id)")
        print(
            f"\n  Prior MEMORY_SIMILARITY_FLOOR = {config.MEMORY_SIMILARITY_FLOOR}  "
            f"MEMORY_TOP_K = {config.MEMORY_TOP_K}\n"
            f"  Full User A corpus returned (beyond top-k) to see the complete distribution."
        )

        decoy_fact_set = set(USER_A_DECOYS)
        nd_fact_set = set(nd_texts)

        # Fetch the full User A corpus per query (over-fetch) to see all similarities.
        fetch_k = len(USER_A_FACTS) + len(nd_texts) + len(USER_A_DECOYS) + 5

        all_rel_sims: list[float] = []
        all_decoy_sims: list[float] = []

        for qi, (query, q_emb) in enumerate(zip(ROAST_QUERIES, q_embs)):
            results = await search_memories(pool, SPIKE_USER_A, q_emb, fetch_k)
            print(f'\nQ{qi + 1}: "{query}"')
            print(f"  {'Rank':<5} {'Sim':>6}  {'Kind':<13}  Fact")
            print(f"  {'─' * 4}  {'─' * 6}  {'─' * 13}  {'─' * 50}")

            q_rel: list[float] = []
            q_decoy: list[float] = []

            for rank, r in enumerate(results, 1):
                f = r["fact"]
                if f in decoy_fact_set:
                    kind_label = "DECOY ◄"
                    q_decoy.append(r["similarity"])
                    all_decoy_sims.append(r["similarity"])
                elif f in nd_fact_set:
                    kind_label = "near-dup"
                    q_rel.append(r["similarity"])
                    all_rel_sims.append(r["similarity"])
                else:
                    kind_label = "relevant"
                    q_rel.append(r["similarity"])
                    all_rel_sims.append(r["similarity"])

                trunc = f[:58] + ("…" if len(f) > 58 else "")
                above_floor = " *" if r["similarity"] >= config.MEMORY_SIMILARITY_FLOOR else ""
                print(f"  {rank:<5} {r['similarity']:>6.4f}  {kind_label:<13}  {trunc}{above_floor}")

            if q_rel and q_decoy:
                gap = min(q_rel) - max(q_decoy)
                print(
                    f"\n  Floor signal: min(relevant)={min(q_rel):.4f}  "
                    f"max(decoy)={max(q_decoy):.4f}  "
                    f"gap={gap:+.4f}  "
                    f"({'clean sep' if gap > 0 else 'NO separation — decoys intrude!'})"
                )
            else:
                print("  (insufficient relevant or decoy results for this query)")

        # ── 4. Dedup-threshold signal ─────────────────────────────────────────
        section("DEDUP-THRESHOLD SIGNAL  (near-duplicate pairs vs their originals)")
        print(f"\n  Prior MEMORY_DEDUP_THRESHOLD = {config.MEMORY_DEDUP_THRESHOLD}")
        print("  Dedup fires when similarity >= threshold → bump hit_count, skip insert.\n")

        dedup_sims: list[float] = []
        for (nd_text, orig_text, orig_idx), nd_emb in zip(USER_A_NEAR_DUPS, a_nd_embs):
            orig_emb = a_fact_embs[orig_idx]
            sim = cosine_sim(orig_emb, nd_emb)
            dedup_sims.append(sim)
            fires = sim >= config.MEMORY_DEDUP_THRESHOLD
            verdict = (
                "DEDUP FIRES (bump hit_count, skip insert)"
                if fires
                else "INSERT (below threshold — treated as distinct)"
            )
            print(f'  Original : "{orig_text[:72]}"')
            print(f'  Near-dup : "{nd_text[:72]}"')
            print(f"  Sim      : {sim:.4f}  → {verdict}")
            print()

        # Sanity: clearly different facts must NOT dedup.
        print("  Sanity check — clearly different facts (should NOT trigger dedup):")
        distinct_pairs = [(0, 5), (2, 7), (3, 10), (1, 9)]
        for i, j in distinct_pairs:
            sim = cosine_sim(a_fact_embs[i], a_fact_embs[j])
            fires = sim >= config.MEMORY_DEDUP_THRESHOLD
            verdict = "DEDUP FIRES — threshold too loose!" if fires else "distinct (correct)"
            print(f"    fact[{i}] vs fact[{j}]: {sim:.4f}  → {verdict}")

        # ── 5. User-scoping integrity check ──────────────────────────────────
        section("USER-SCOPING CHECK  (User B facts must NOT surface in User A search)")
        a_results = await search_memories(pool, SPIKE_USER_A, q_embs[0], fetch_k)
        a_fact_texts = {r["fact"] for r in a_results}
        b_leaked = [f for f in USER_B_FACTS if f in a_fact_texts]
        if b_leaked:
            print(f"\n  FAIL: User B facts appeared in User A search ({len(b_leaked)} items):")
            for f in b_leaked:
                print(f"    - {f[:72]}")
        else:
            print("\n  PASS: No User B facts appeared in User A results (scoping correct)")

        # ── 6. Aggregate distributions and proposed values ────────────────────
        section("AGGREGATE DISTRIBUTIONS + PROPOSED CONSTANT VALUES")

        if all_rel_sims and all_decoy_sims:
            min_rel = min(all_rel_sims)
            max_rel = max(all_rel_sims)
            mean_rel = sum(all_rel_sims) / len(all_rel_sims)
            min_dec = min(all_decoy_sims)
            max_dec = max(all_decoy_sims)
            mean_dec = sum(all_decoy_sims) / len(all_decoy_sims)
            gap = min_rel - max_dec

            print(f"\n  Distributions across {len(ROAST_QUERIES)} queries, User A corpus:")
            print(
                f"    Relevant ({len(all_rel_sims):3d} sims): min={min_rel:.4f}  max={max_rel:.4f}  mean={mean_rel:.4f}"
            )
            print(
                f"    Decoys   ({len(all_decoy_sims):3d} sims): "
                f"min={min_dec:.4f}  max={max_dec:.4f}  mean={mean_dec:.4f}"
            )
            print(f"    Gap (min_relevant - max_decoy): {gap:+.4f}")

            if gap > 0:
                proposed_floor = round((min_rel + max_dec) / 2, 2)
                dim_decision = "keep-768 (clean separation detected)"
                print(f"\n  Clean separation. Proposed MEMORY_SIMILARITY_FLOOR = {proposed_floor}")
                print(f"  (midpoint: ({min_rel:.4f} + {max_dec:.4f}) / 2 = {proposed_floor})")
            else:
                proposed_floor = config.MEMORY_SIMILARITY_FLOOR
                dim_decision = "consider bump-1536 (no clean separation)"
                print(f"\n  WARNING: No clean relevant/decoy separation (gap={gap:.4f}).")
                print("  Options:")
                print("    1. Keep MEMORY_SIMILARITY_FLOOR at prior (0.70) and rely on reranking.")
                print("    2. Bump EMBED_DIM from 768 to 1536 and re-run the spike.")
                print("       (requires recreating vector(768) column as vector(1536))")
        else:
            proposed_floor = config.MEMORY_SIMILARITY_FLOOR
            dim_decision = "keep-768 (insufficient data)"

        if dedup_sims:
            # Propose dedup threshold slightly below the observed near-dup similarity
            proposed_dedup = round(min(dedup_sims) - 0.02, 2)
            proposed_dedup = max(0.80, min(0.97, proposed_dedup))
        else:
            proposed_dedup = config.MEMORY_DEDUP_THRESHOLD

        print(f"""
  ┌──────────────────────────────────────────────────────────────────────┐
  │  RETRIEVAL CONSTANT PROPOSALS  (confirm or override each for Task 3) │
  ├────────────────────────────────────────┬─────────────────────────────┤
  │  Constant                              │  Prior → Proposed           │
  ├────────────────────────────────────────┼─────────────────────────────┤
  │  MEMORY_SIMILARITY_FLOOR               │  {config.MEMORY_SIMILARITY_FLOOR} → {proposed_floor:<25}│
  │  MEMORY_DEDUP_THRESHOLD                │  {config.MEMORY_DEDUP_THRESHOLD} → {proposed_dedup:<25}│
  │  MEMORY_TOP_K                          │  {config.MEMORY_TOP_K} → confirm (or adjust)       │
  │  MEMORY_INJECT_CAP  (must be 1-3)      │  {config.MEMORY_INJECT_CAP} → confirm                  │
  │  MEMORY_MAX_PER_USER                   │  {config.MEMORY_MAX_PER_USER} → confirm              │
  │  MEMORY_DECAY_DAYS                     │  {config.MEMORY_DECAY_DAYS} → confirm               │
  │  MEMORY_RERANK_RELEVANCE_WEIGHT        │  {config.MEMORY_RERANK_RELEVANCE_WEIGHT} → confirm                  │
  │  MEMORY_RERANK_RECENCY_WEIGHT          │  {config.MEMORY_RERANK_RECENCY_WEIGHT} → confirm                  │
  │  MEMORY_RERANK_SALIENCE_WEIGHT         │  {config.MEMORY_RERANK_SALIENCE_WEIGHT} → confirm                  │
  │  MEMORY_RERANK_NOVELTY_WEIGHT          │  {config.MEMORY_RERANK_NOVELTY_WEIGHT} → confirm                 │
  │  MEMORY_CALLBACK_CHANCE                │  {config.MEMORY_CALLBACK_CHANCE} → confirm                  │
  │  EMBED_DIM decision                    │  {dim_decision:<29}│
  └────────────────────────────────────────┴─────────────────────────────┘

  Resume signal for Task 3 (provide to /gsd-execute-phase resume):
    "use proposed"          — accept proposed_floor + proposed_dedup + all priors
    "MEMORY_SIMILARITY_FLOOR=X.XX, MEMORY_DEDUP_THRESHOLD=X.XX, keep-768"
    (or bump-1536 if no clean separation was observed)
""")

    finally:
        # T-11-02b: always clean up spike rows, even if a step above failed.
        print("[spike] Cleaning up spike rows...")
        try:
            await cleanup_spike(pool)
        except Exception as exc:
            print(f"[spike] WARNING: cleanup failed ({exc})", file=sys.stderr)
            print(
                f"[spike] Manual cleanup:\n"
                f"  DELETE FROM user_memories "
                f"WHERE user_id IN ('{SPIKE_USER_A}', '{SPIKE_USER_B}');",
                file=sys.stderr,
            )
        finally:
            await pool.close()
            print("[spike] Pool closed.")


if __name__ == "__main__":
    asyncio.run(main())
