---
status: partial
phase: 15-rag-reach
source: [15-VERIFICATION.md]
started: 2026-07-03
updated: 2026-07-03
---

## Current Test

[awaiting human testing]

## Tests

### 1. Live-DB remember→forget→recall==[] proof (RAG-04 SC4 — load-bearing)
expected: Run `tests/test_database_phase15.py::test_remember_forget_recall_empty` against a real pgvector-enabled Postgres (set `TEST_DATABASE_URL`, e.g. a Neon branch). insert_memory → search_memories returns 1 row → delete_all_user_memories returns 1 → search_memories returns [] (rows AND embeddings verifiably gone through the real ANN path).
result: [pending]

### 2. /roast @user grounds in target's recalled history
expected: In a live Discord server, `/roast @someone-with-memory` reads as informed by real recalled history for that target (not the invoker); `/roast` on a user with no memory falls back gracefully — no crash/blank response.
result: [pending]

### 3. /memory view — ephemeral, verbatim, paginated
expected: `/memory view` as a user with several memories renders verbatim facts in an ephemeral (invoker-only), in-character embed; empty-state line for a user with nothing stored; Previous/Next pagination works and disables on timeout.
result: [pending]

### 4. /memory forget — irreversible wipe end-to-end
expected: `/memory forget` → Confirm wipes all rows (subsequent `/memory view` / DB check shows them gone; count preview matches actual deleted count); Cancel and timeout leave memories untouched.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
