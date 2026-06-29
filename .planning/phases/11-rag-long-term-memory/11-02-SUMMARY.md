---
phase: 11-rag-long-term-memory
plan: "02"
subsystem: database
tags: [gemini-embedding-001, pgvector, cosine-similarity, rag, memory-retrieval]

# Dependency graph
requires:
  - phase: 11-01
    provides: user_memories table + pgvector extension boot + Phase 11 config constants (prior values)
provides:
  - scripts/memory_spike.py — throwaway empirical validation script (gemini-embedding-001 @ 768d)
  - config.py MEMORY_* constants locked to spike-validated values with "tuned via 11-02 spike 2026-06-29" annotation
  - keep-768 dimension decision recorded for 11-03
affects:
  - 11-03-retrieval (parameterized by these constants; no pure-logic tests break on constant change)
  - 11-04-distill (MEMORY_DEDUP_THRESHOLD=0.92 used in dedup logic)
  - 11-05-inject (MEMORY_INJECT_CAP=3, MEMORY_CALLBACK_CHANCE=0.35)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Empirical spike-first: numeric retrieval priors validated against live embedding model before retrieval code lands"
    - "Spike cleanup: fake user_ids + DELETE on exit — non-destructive against live Neon store"

key-files:
  created:
    - scripts/memory_spike.py
  modified:
    - config.py

key-decisions:
  - "MEMORY_DEDUP_THRESHOLD raised 0.90 → 0.92: near-dup seed pairs scored 0.937 and 0.955; distinct facts maxed at 0.79 — clean separation justifies a tighter threshold"
  - "MEMORY_SIMILARITY_FLOOR kept at 0.70 (high-precision): gemini-embedding-001 @ 768d compresses scores (relevant mean 0.66, decoys mean 0.59); no clean global separation, so strict floor chosen over recall"
  - "EMBED_DIM = 768 confirmed (keep-768): 768d separation is sufficient for scoped cosine ANN with user_id WHERE clause; no schema change needed for 11-03"
  - "user_memories table + pgvector extension already applied to live Neon during 11-01; spike ran against live infra (orchestrator executed, user reviewed output)"

patterns-established:
  - "Spike-then-lock: throwaway scripts/ script → human reviews live distributions → resume signal locks constants before retrieval code is written"

requirements-completed: [MEM-03]

# Metrics
duration: 17min
completed: 2026-06-29
---

# Phase 11 Plan 02: Numeric-Defaults Validation Spike Summary

**gemini-embedding-001 @ 768d spike run against live Neon — MEMORY_DEDUP_THRESHOLD raised 0.90→0.92, MEMORY_SIMILARITY_FLOOR kept 0.70 (high-precision), keep-768 confirmed**

## Performance

- **Duration:** ~17 min (automated tasks 1 + 3; Task 2 was a human-verify checkpoint)
- **Started:** 2026-06-29T08:48:06Z
- **Completed:** 2026-06-29T09:05:12Z
- **Tasks:** 3 (Task 1: spike script; Task 2: human-verify checkpoint; Task 3: lock constants)
- **Files modified:** 2 (scripts/memory_spike.py created, config.py updated)

## Accomplishments

- Wrote `scripts/memory_spike.py` — a standalone throwaway script that embeds a 12–20 fact seed corpus + 6 irrelevant decoys using `gemini-embedding-001` @ 768d, runs scoped cosine ANN via pgvector `<=>`, prints per-query similarity rankings and the relevant/irrelevant separation gap, and cleans up its fake rows on exit
- Spike was executed by the orchestrator against live Gemini API + live Neon Postgres (Singapore); user reviewed printed distributions and confirmed each constant
- Locked all MEMORY_* retrieval constants into config.py with `# tuned via 11-02 spike 2026-06-29` annotation; only MEMORY_DEDUP_THRESHOLD changed value (0.90 → 0.92)

## Task Commits

Each task was committed atomically:

1. **Task 1: Write the throwaway numeric-defaults spike script** — `ef31c6d` (feat)
2. **Task 2: Run the spike, review distributions, lock the constants** — human-verify checkpoint (no commit; orchestrator executed spike, user reviewed output and provided resume signal)
3. **Task 3: Write the chosen constants into config.py** — `e0e3ed5` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `scripts/memory_spike.py` — Throwaway spike: embeds seed corpus + roast queries at 768d, runs scoped cosine search, prints similarity distributions and relevant/irrelevant gap, cleans up fake rows
- `config.py` — Phase 11 MEMORY_* constants updated from "prior — validate" placeholders to spike-locked values; MEMORY_DEDUP_THRESHOLD raised from 0.90 to 0.92

## Spike Distributions (recorded for 11-03 context)

- **Near-duplicate pairs:** scored 0.937 and 0.955 cosine similarity
- **Distinct facts (max):** 0.79 — clean separation from dup threshold, confirms 0.92 is correct
- **Relevant facts range:** 0.58–0.77, mean 0.66
- **Irrelevant decoys range:** 0.53–0.66, mean 0.59
- **Conclusion:** No clean global floor separation (distributions overlap at low end); user scoping (WHERE user_id = $1) is the primary guard; strict 0.70 floor chosen for high precision

## Decisions Made

- **MEMORY_DEDUP_THRESHOLD = 0.92** (raised from prior 0.90): spike showed near-dup pairs at 0.937/0.955 and distinct facts maxing at 0.79 — raising to 0.92 widens the safe buffer against false dedup while still catching true near-duplicates
- **MEMORY_SIMILARITY_FLOOR = 0.70** (confirmed — high precision): embedding model compresses scores; user chose tight floor to avoid injecting low-confidence memories into Gemini context over recall
- **EMBED_DIM = 768** (keep-768 confirmed): scoped ANN with user_id WHERE clause provides sufficient separation; no schema change needed — 11-03 proceeds with existing `vector(768)` column
- All other priors confirmed unchanged: TOP_K=8, INJECT_CAP=3, MAX_PER_USER=150, DECAY_DAYS=90, four rerank weights, CALLBACK_CHANCE=0.35

## Deviations from Plan

None — plan executed exactly as written. Task 2 was a human-verify checkpoint as designed; the orchestrator ran the spike against live infra and the user provided the resume signal with confirmed values.

## Issues Encountered

None.

## User Setup Required

None — spike ran against already-configured GEMINI_API_KEY + DATABASE_URL. The `user_memories` table and pgvector extension were applied to live Neon during 11-01; this plan only read from/wrote to that existing infra.

## Next Phase Readiness

- **11-03 (Retrieval)** is unblocked: MEMORY_SIMILARITY_FLOOR=0.70, MEMORY_TOP_K=8, MEMORY_DEDUP_THRESHOLD=0.92, MEMORY_INJECT_CAP=3 are all locked and annotated
- **EMBED_DIM = 768 confirmed** — 11-03 uses `vector(768)` column as-is, no schema migration needed
- **Rerank weights confirmed** — 11-03 pure rerank functions are parameterized by these constants; changing a value never breaks a unit test (per plan design)
- The "numeric retrieval defaults are MEDIUM-confidence priors" blocker in STATE.md is resolved

---
*Phase: 11-rag-long-term-memory*
*Completed: 2026-06-29*
