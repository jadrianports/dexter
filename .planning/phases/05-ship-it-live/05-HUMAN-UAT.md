---
status: partial
phase: 05-ship-it-live
source: [05-VERIFICATION.md, 05-UAT-RUNBOOK.md]
started: "2026-06-12T11:27:55Z"
updated: "2026-06-12T11:27:55Z"
---

# Phase 05 — Human UAT (Live Oracle A1)

Phase 5's goal is inherently live: *"Dexter is running 24/7 on Oracle A1 and every
v1.0 behavioral and deploy check has been validated in production."* All code-side
must-haves are verified (see `05-VERIFICATION.md`, status `human_needed`, 5/5). What
remains can only be confirmed on the running Oracle A1 VM with Postgres + Discord.

**Run these against `05-UAT-RUNBOOK.md`** — that runbook holds the full ordered steps,
prerequisites, `down -v` warnings, and troubleshooting table. Execute checks in order
(A → B → C → D); D1 is destructive-adjacent and always runs last. Record each result
here as you go, then run `/gsd-verify-work 05` to fold results back in.

## Current Test

[awaiting human testing on Oracle A1]

## Tests

### 1. A1. Docker clean boot
expected: `docker compose up -d` brings up Postgres (healthcheck healthy) + bot; bot posts startup message; `bash scripts/deploy.sh` works for subsequent updates
result: [pending]

### 2. A2. Reboot survival
expected: `systemctl is-enabled docker` = enabled; after `sudo reboot` bot reposts startup message within ~90s, no SSH needed
result: [pending]

### 3. A3. Over-cap /play rejection
expected: with `MAX_QUEUE_SIZE_PER_GUILD=1`, a second `/play` returns the personality cap rejection; queue stays at 1
result: [pending]

### 4. A4. Keepalive cron + Healthchecks.io
expected: Healthchecks.io dashboard shows the check green within 10 min; Discord error-log channel receives the UP notification
result: [pending]

### 5. A5. Backup cron (manual run)
expected: `bash scripts/backup.sh` exits 0; a new `dexter_YYYYMMDD_HHMMSS.dump` appears in the `dexter-backups` OCI bucket (now via temp-file + size guard — WR-01)
result: [pending]

### 6. A6. Postgres integration tests
expected: `pytest tests/test_database_phase4.py -x` green (18 tests) against a live `dexter_test` Postgres
result: [pending]

### 7. B1. Queue persistence round-trip
expected: after `/play` + `docker compose restart bot`, `/queue` shows the restored track; smart-rejoin connects + resumes only when a non-bot human is still present
result: [pending]

### 8. B2. clear_persisted on idle-leave (DEPLOY-06 / IN-02 fix)
expected: bot idles alone 10+ min, auto-leaves, then after `docker compose restart bot`, `/queue` is empty (not restored) — confirms the bot.py fix at runtime
result: [pending]

### 9. C1. Voice join roast
expected: joining voice 4-5 times produces ≥1 roast; Gemini-personalized when API live, template fallback on rate-limit
result: [pending]

### 10. C2. Late-night roast TZ fix (DEPLOY-04 / D-06)
expected: late-night roast fires for 1-5am `America/New_York`, NOT 1-5am UTC — confirms the events.py ZoneInfo fix is live
result: [pending]

### 11. C3. Startup message
expected: `docker compose restart bot` posts a personality startup line to `DEXTER_CHANNEL_ID` within ~30s
result: [pending]

### 12. C4. Status rotation
expected: over 10-15 min, presence cycles through current song / server-count / random line / seasonal line
result: [pending]

### 13. C5. /lyrics command
expected: after `/play` on a song with Genius lyrics, `/lyrics` returns a paginated embed with Prev/Next; buttons disable after 3-min timeout
result: [pending]

### 14. C6. /history command
expected: `/history` returns a paginated embed of recent songs (title, artist, requester, date)
result: [pending]

### 15. C7. Message reactions
expected: YouTube URL → 👀; `gn`/`goodnight` → 🫡; bare bot mention → 😐; mention + "thanks" → deflecting text reply
result: [pending]

### 16. C8. Repeat-song roast
expected: queuing the same song 3× in one day always fires a roast
result: [pending]

### 17. C9. Idle loneliness
expected: after 30+ min no commands with humans in voice, bot posts exactly one lonely message (not repeated until next activity)
result: [pending]

### 18. C10. Streak and milestone roasts
expected: consecutive-day streak tracking + milestone roasts fire at the documented thresholds (03-VERIFICATION HV-8)
result: [pending]

### 19. C11. DEPLOY-04 diagnostic (reconnect race, live observation)
expected: observe a reconnect; the new INFO diagnostic log trail is present so a targeted `/gsd:debug` session can resolve the WR-03 race if it fires
result: [pending]

### 20. D1. End-to-end restore proof (DEPLOY-07 / D-15)
expected: `python scripts/seed_restore_test.py` seeds → backup → restores into the throwaway DB → asserts row counts → drops throwaway DB → removes seed rows from the live DB (CR-02 cleanup); exits "PASSED"
result: [pending]

## Summary

total: 20
passed: 0
issues: 0
pending: 20
skipped: 0
blocked: 0

## Gaps

None recorded yet — populate from live runs.
