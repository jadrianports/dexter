---
status: partial
phase: 08-social-ops
source: [08-VERIFICATION.md]
started: 2026-06-19T08:09:49Z
updated: 2026-06-19T08:09:49Z
---

# Phase 08 — Human UAT (Live Behavioral Verification)

All 12 code-level must-haves passed automated verification (12/12). The items below
require a **deployed bot + live PostgreSQL + live Gemini** and cannot be verified on the
dev machine. Run these once the Phase 8 code is live (Koyeb + Neon), then report results
via `/gsd-verify-work 08`.

## Current Test

[awaiting human testing]

## Tests

### 1. /roast live output quality
expected: `/roast @user` posts a Gemini-personalized roast that references the target's real song history, streak, and top artists — lowercase, dry, ≤1 emoji, on-brand.
result: [pending]

### 2. /roast edge cases (self / bot / no-history)
expected: `/roast @self`, `/roast @Dexter` (the bot), and `/roast` on a user with zero tracked history each return a dedicated special-case line (not an error, not a generic roast).
result: [pending]

### 3. /roast rate-limit fallback
expected: When Gemini is saturated/rate-limited, `/roast` still posts a template fallback line — the command never fails silently or errors out.
result: [pending]

### 4. /leaderboard with populated data
expected: `/leaderboard` shows a 3-section embed (most songs queued, longest active streak, most skipped) ranked from live Postgres, top 5 per section, with on-brand commentary.
result: [pending]

### 5. /leaderboard empty-state
expected: In a fresh server with no history, `/leaderboard` renders the per-section empty-state lines rather than blank/error.
result: [pending]

### 6. /stats owner-only + ephemeral
expected: `/stats` works for the owner and replies ephemerally (only owner sees it); a non-owner invoking `/stats` is refused before any data is shown.
result: [pending]

### 7. /health degraded response (live DB offline)
expected: GET `/health` returns HTTP 200 always; when the DB is unreachable the JSON body reports `status: degraded` with `reasons`. (Code review WR-05/06: current tests exercise the helper, not the real bot.py handler — confirm the deployed endpoint directly.)
result: [pending]

### 8. total_errors accuracy under real errors
expected: The `/stats` "errors logged today" figure tracks actual error-channel error events. (Code review WR-02: increment currently fires on every error-channel send — confirm the live count is meaningful, not inflated by non-error posts.)
result: [pending]

### 9. Healthchecks.io / dead-man switch green
expected: The deployed `/health` endpoint is reachable by the dead-man switch cron and the Healthchecks.io dashboard shows the bot as green.
result: [pending]

## Summary

total: 9
passed: 0
issues: 0
pending: 9
skipped: 0
blocked: 0

## Gaps
