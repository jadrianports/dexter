---
status: partial
phase: 08-social-ops
source: [08-VERIFICATION.md]
started: 2026-06-19T08:09:49Z
updated: 2026-06-24T00:00:00Z
---

# Phase 08 — Human UAT (Live Behavioral Verification)

All 12 code-level must-haves passed automated verification (12/12). The items below
require a **deployed bot + live PostgreSQL + live Gemini** and cannot be verified on the
dev machine. Run these once the Phase 8 code is live (Koyeb + Neon), then report results
via `/gsd-verify-work 08`.

## Current Test
<!-- OVERWRITE each test - shows where we are -->

[testing paused — 1 item outstanding (Test 9 blocked: needs a public deployment)]

## Tests

### 1. /roast live output quality
expected: `/roast @user` posts a Gemini-personalized roast that references the target's real song history, streak, and top artists — lowercase, dry, ≤1 emoji, on-brand.
result: skipped
reason: "Solo server (only owner + bot) — the personalized-roast-of-another-user path is unreachable: self-mention always takes the self branch, and there is no other member to target. User accepted automated coverage: tests/test_roast_command.py exercises the personalized path, and the self/bot sibling branches of the same edge-dispatch + Gemini-call+fallback machinery were confirmed live in Test 2. Re-run live if a second member with history ever joins."

### 2. /roast edge cases (self / bot / no-history)
expected: `/roast @self`, `/roast @Dexter` (the bot), and `/roast` on a user with zero tracked history each return a dedicated special-case line (not an error, not a generic roast).
result: pass
note: "self ✓ and bot ✓ confirmed live — on-brand self-roast ('you're inside roasting yourself on a summer day…') and bot-turnaround ('your roast was about as compelling as the 17th lo-fi beats playlist…'), both lowercase/dry/seasonal. no-history sub-case NOT live-reproducible in a solo server (self-mention always takes the self branch; no other member to target) — covered by tests/test_roast_command.py and rides the same edge-dispatch+fallback machinery confirmed live by self/bot. BONUS: 30s per-invoker cooldown (D-04) observed working — ephemeral 'slow down. try again in 8s.'"

### 3. /roast rate-limit fallback
expected: When Gemini is saturated/rate-limited, `/roast` still posts a template fallback line — the command never fails silently or errors out.
result: pass

### 4. /leaderboard with populated data
expected: `/leaderboard` shows a 3-section embed (most songs queued, longest active streak, most skipped) ranked from live Postgres, top 5 per section, with on-brand commentary.
result: pass

### 5. /leaderboard empty-state
expected: In a fresh server with no history, `/leaderboard` renders the per-section empty-state lines rather than blank/error.
result: pass

### 6. /stats owner-only + ephemeral
expected: `/stats` works for the owner and replies ephemerally (only owner sees it); a non-owner invoking `/stats` is refused before any data is shown.
result: pass
note: "Owner-case ✓ live — ephemeral ('only i can see it'), 13-field embed with accurate live data: commands today 2 / ai queries 2 (== the 2 successful roasts; cooldowned 3rd correctly not counted), database: ok (Neon healthy end-to-end), gateway: ready, uptime 18m, guilds 1, shards 1. Non-owner refusal NOT solo-reproducible — gated by bot.is_owner(), unit-covered. COSMETIC FINDING: stats_embed footer links 'koyeb dashboard' but project pivoted off Koyeb to PC+Neon — see Gaps (cosmetic)."

### 7. /health degraded response (live DB offline)
expected: GET `/health` returns HTTP 200 always; when the DB is unreachable the JSON body reports `status: degraded` with `reasons`. (Code review WR-05/06: current tests exercise the helper, not the real bot.py handler — confirm the deployed endpoint directly.)
result: pass

### 8. total_errors accuracy under real errors
expected: The `/stats` "errors logged today" figure tracks actual error-channel error events. (Code review WR-02: increment currently fires on every error-channel send — confirm the live count is meaningful, not inflated by non-error posts.)
result: pass

### 9. Healthchecks.io / dead-man switch green
expected: The deployed `/health` endpoint is reachable by the dead-man switch cron and the Healthchecks.io dashboard shows the bot as green.
result: blocked
blocked_by: release-build
reason: "Requires a publicly-reachable deployed /health endpoint. Koyeb deploy is blocked by the YouTube datacenter-IP block; the PC + Neon local run is not externally reachable by an external dead-man-switch cron / Healthchecks.io. Re-test if/when a public deployment exists."

## Summary

total: 9
passed: 7
issues: 0
pending: 0
skipped: 1
blocked: 1

## Gaps

- truth: "User-visible host links in /stats reflect the actual deployment"
  status: resolved
  reason: "stats_embed footer links 'koyeb dashboard | neon console', but the project pivoted off Koyeb (YouTube datacenter-IP block) to self-host on PC + Neon. The Koyeb link is stale/misleading; only 'neon console' is valid."
  severity: cosmetic
  test: 6
  root_cause: "utils/embeds.py stats_embed footer hardcoded for the pre-pivot Koyeb+Neon hosting model"
  artifacts:
    - path: "utils/embeds.py"
      issue: "stats_embed footer references a dead Koyeb dashboard"
  missing:
    - "Drop the Koyeb dashboard link from the stats_embed footer (and optionally scrub other Koyeb references: docker-compose.yml comments, .env.example) now that hosting is PC + Neon"
  resolution: "Fixed 2026-06-24 — footer now reads 'host metrics: neon console' (Koyeb link removed). No tests asserted on footer text. Broader Koyeb-reference scrub (bot.py, config.py, Dockerfile, .env.example, utils/logger.py, docs/DEPLOY-KOYEB.md) deferred — pending decision on whether Koyeb is abandoned or parked."
  debug_session: ""
