---
status: partial
phase: 11-rag-long-term-memory
source: [11-VERIFICATION.md]
started: 2026-06-29
updated: 2026-06-29
---

## Current Test

[awaiting human testing]

## Tests

### 1. Live Neon boot gate (MEM-01)
expected: Bot boots against live Neon with no `ValueError: unknown type: public.vector`; the `Memory service initialized` (and `Database schema initialized`) log lines appear; `memory_distill_batch` and `memory_sweep` @tasks.loop start without error.
result: [pending]

### 2. CR-02 cross-user isolation (security)
expected: Under a two-account test, every `user_memories` row on live Neon carries only an 18-digit Discord snowflake `user_id`; a memory distilled for account A never surfaces in account B's recall. A user renaming their nickname to another user's ID does not plant facts into that user's scope.
result: [pending]

### 3. WR-01 voice-join kind/salience
expected: A daytime voice join stores a memory with `kind=daily_batch` (salience 0.2, below the 0.5 decay floor → eligible for decay); a late-night (1–5am) join stores `kind=late_night` (salience 0.7, survives decay).
result: [pending]

### 4. WR-02 is_sensitive word-boundary backstop
expected: `"marvin gaye"` and `"grape soda"` are NOT blocked (is_sensitive → False), while `"is gay"` and `"mentions rape"` ARE blocked (is_sensitive → True) via the new word-boundary regex.
result: passed — verified locally 2026-06-29 (pure function): marvin gaye/grape soda/gayle → False; "is gay"/"mentions rape" → True.

## Summary

total: 4
passed: 1
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
