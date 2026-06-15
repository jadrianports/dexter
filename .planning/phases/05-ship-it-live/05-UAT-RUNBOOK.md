---
status: partial
phase: 05-ship-it-live
source: [05-CONTEXT.md, 05-RESEARCH.md, 04-VERIFICATION.md, 03-VERIFICATION.md, 04-HUMAN-UAT.md]
target: Koyeb WEB service + Neon serverless Postgres (re-targeted 2026-06-15, K-18)
started: [fill on execution]
updated: [fill on execution]
---

# Dexter Live-UAT Runbook

**Consolidated from:** 03-VERIFICATION.md (9 behavioral checks), 04-VERIFICATION.md (6 deploy checks), 04-HUMAN-UAT.md (6 human scenarios — de-duped with 04-VERIFICATION)

**Run on:** Koyeb WEB service (git-auto-built) + Neon serverless Postgres

**Session flow:** A (boot/infra) → B (queue persistence) → C (behavioral/Discord) → D (destructive/restore, ALWAYS LAST)

---

> **WARNING — CRITICAL**
>
> **Group D (Neon PITR restore) is DESTRUCTIVE and runs LAST.** Never run Group D until Groups A, B, and C have all passed.
>
> The Neon PITR restore in D1 temporarily interrupts the asyncpg pool's connections and overwrites the live Neon branch history within the restore window. Before clicking "Restore" in the Neon console, always confirm the timestamp and verify the restore point via Time-Travel Assist first.
>
> **Never point `pg_restore` or `dropdb` at the live Neon branch.** The PITR restore is a Neon console UI operation, not a local database command.
>
> **K-14 break-glass rule:** Never run the local PC `docker compose` stack and the Koyeb service simultaneously on the same Discord token. Two instances on one token cause a gateway conflict loop. Stop PC compose before Koyeb goes live; start it only when Koyeb is confirmed down.

---

## Prerequisites Checklist

Complete every item before running check A1. These are one-time setup steps for the Koyeb+Neon deployment. See `docs/DEPLOY-KOYEB.md` for the full deploy contract.

- [ ] **Neon project created:** Sign up at https://neon.com (no credit card). Create a new project in region `us-east-2`. In Connection Details, select the **Pooled connection** (hostname contains `-pooler`). Copy the full connection string — it looks like `postgresql://user:pass@ep-<id>-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require`.
- [ ] **Koyeb WEB service created:** Sign up at https://koyeb.com (no credit card). Create Service → GitHub → connect the repo. Configuration: Branch `gsd/phase-5-ship-it-live`, Build method Dockerfile, Region Washington D.C. (`wdc1`), Instance type Free (512 MB / 0.1 vCPU / 2 GB SSD), Health check HTTP path `/health` port `8000`. See `docs/DEPLOY-KOYEB.md` §3 for step-by-step.
- [ ] **Koyeb secrets + env vars set (K-13):** Four encrypted Koyeb Secrets: `DISCORD_TOKEN`, `GEMINI_API_KEY`, `GENIUS_TOKEN`, `DATABASE_URL` (use the Neon pooled connection string — the bot's `sanitize_database_url()` strips the `channel_binding` query param automatically). Plain env vars: `DEXTER_CHANNEL_ID`, `ERROR_LOG_CHANNEL_ID`, `OWNER_ID`, `HEALTHCHECK_URL`, `STREAK_TIMEZONE=America/New_York`. See `docs/DEPLOY-KOYEB.md` §4.
- [ ] **UptimeRobot HTTP monitor set up:** Sign up at https://uptimerobot.com (free tier, no credit card). Add New Monitor: Type `HTTP(s)`, URL `https://<your-service-name>.koyeb.app/health`, Interval 5 minutes. This prevents Koyeb's 1-hour scale-to-zero sleep. See `docs/DEPLOY-KOYEB.md` §5.
- [ ] **Healthchecks.io check created:**
  - Sign in to healthchecks.io → New Project ("Dexter Monitoring") → Add Check → Name: "Dexter Keepalive" → Period: 10 min, Grace: 10 min → Save → copy ping URL (format: `https://hc-ping.com/<36-char-uuid>`)
  - Discord integration: error-log channel → Channel Settings → Integrations → New Webhook → copy URL → Healthchecks.io → Integrations → Add Integration → Discord → paste webhook URL → test it → toggle on for the check
  - Email integration: Healthchecks.io → Integrations → Add Integration → Email → enter email → toggle on for the check
  - Set `HEALTHCHECK_URL` to the ping URL in Koyeb plain env vars (K-09, DEPLOY-08).
- [ ] **Per-guild command sync (first deploy only):** `python bot.py --first-run --guild <GUILD_ID>` — slash commands appear in Discord within seconds; subsequent syncs via owner `/sync <guild_id>` (P-04).

---

## Group A: Boot + Infra

### A1. Koyeb deploy healthy

expected: After clicking Deploy in the Koyeb console (or after the first push to the tracked branch triggers a build), the Koyeb dashboard shows the service status as **Healthy**. Koyeb logs (via the console log viewer or `koyeb services logs <service>`) show `Dexter is ready.` and the startup personality message (`i'm back. did you miss me. probably not.` or similar) posts to `DEXTER_CHANNEL_ID` in the guild.

result: [pending]

---

### A2. Koyeb restart + queue-restore-from-Neon survival

expected: In the Koyeb service dashboard, trigger a manual restart or redeploy (Service → Redeploy / Restart). The service comes back up Healthy automatically with no manual intervention. The bot posts its startup personality message to `DEXTER_CHANNEL_ID`. Run `/queue` — if a `guild_queues` row existed for the guild (i.e. a queue was active before restart), the queue is restored from Neon. Smart-rejoin re-connects voice and resumes playback only when a non-bot human remains in the channel (DEPLOY-05, K-17 #2).

result: [pending]

---

### A3. Over-cap /play rejection

expected: In the Koyeb service dashboard → Environment, add `MAX_QUEUE_SIZE_PER_GUILD=1` as a plain env var and trigger a redeploy. Then `/play` two different songs. The second `/play` returns the personality cap rejection ("queue's full at 1 track. impressive dedication, wrong bot." or equivalent). Queue length stays at 1. Remove the override env var and redeploy to restore `MAX_QUEUE_SIZE_PER_GUILD` to 500 when done.

result: [pending]

---

### A4. UptimeRobot + Healthchecks.io confirmed active

expected: (a) UptimeRobot dashboard shows the "Dexter health" monitor green with "Last check: X minutes ago" — confirms the external HTTP pinger is reaching `/health` and Koyeb is not sleeping (DEPLOY-08 / K-02 amendment). (b) Healthchecks.io dashboard shows the "Dexter Keepalive" check green with a last-ping timestamp within the expected period — confirms the bot-side outbound dead-man ping is firing (DEPLOY-08 / K-09). The Discord error-log channel receives a "Bot Dexter Keepalive is UP" notification when the integration first fires.

result: [pending]

---

### A5. Health endpoint alive

expected: `curl https://<your-service-name>.koyeb.app/health` returns HTTP 200 with body `{"status":"ok"}`. This confirms the Plan-01 minimal aiohttp endpoint is bound to `0.0.0.0:8000` and reachable through Koyeb's public domain (K-02 amendment).

result: [pending]

---

### A6. Git auto-deploy

expected: Push a trivial commit to the `gsd/phase-5-ship-it-live` branch (e.g. add a comment to `README.md`). Koyeb detects the push automatically, starts a new build, and the service returns to Healthy status. No manual deploy step is needed. This confirms the K-11 git-auto-build pipeline is wired (replaces the retired `scripts/deploy.sh`). After live UAT passes, update Koyeb's tracked branch to `main` before merging.

result: [pending]

---

### A7. Postgres integration tests (Neon)

expected: With `DATABASE_URL` pointed at a throwaway Neon database or branch (create a `dexter_test` branch in the Neon console, or use the main DB — `init_db()` is idempotent), run `pytest tests/test_database_phase4.py -x`. Exits 0 with 18 tests green (TestPostgresSchema, TestBatchTransaction, TestHelpers). This confirms asyncpg pool tuning (K-04: `max_inactive_connection_lifetime=240`, `statement_cache_size=0`) and the `sanitize_database_url` sanitizer (K-05) work against a live Neon endpoint.

result: [pending]

---

## Group B: Queue Persistence

### B1. Queue persistence round-trip

expected: `/play` a song in the guild (confirm it appears in `/queue`). Trigger a Koyeb service redeploy or restart (via the Koyeb dashboard — NOT `docker compose restart bot`). After the service returns Healthy, run `/queue` — the queue is restored from Neon `guild_queues`. Smart-rejoin re-connects voice and resumes playback only when a non-bot human is still in the channel (DEPLOY-05, K-17 #2). Inspect logs via the Koyeb console or `koyeb services logs <service>` for the restore log line.

result: [pending]

---

### B2. clear_persisted on idle-leave (DEPLOY-06 / P-02 fix)

expected: Join voice with the bot; let it sit alone for 10+ minutes (no commands, no other humans); bot auto-leaves and posts the idle-leave message; trigger a Koyeb redeploy or restart; run `/queue` — queue is **empty** (not restored). This confirms `clear_persisted()` fired on idle-leave (the `bot.py:~399` fix from P-02). If the queue restores, the fix did not apply — inspect Koyeb logs (console or `koyeb services logs <service>`) for `clear_persisted` calls.

result: [pending]

---

### B3. Neon scale-to-zero reconnect

expected: Leave the bot idle for 6+ minutes with no Discord commands (so Neon's compute suspends after its 5-minute scale-to-zero). Then run `/history` or `/play`. The DB query succeeds with no crash and no SSL-EOF / `08006` / `channel_binding` error in the Koyeb logs. This confirms that `max_inactive_connection_lifetime=240` recycles stale pool connections before Neon terminates them, `statement_cache_size=0` avoids prepared-statement errors through PgBouncer, and the sanitizer strips `channel_binding` correctly (DEPLOY-01, K-17 #3, K-04/K-05).

result: [pending]

---

## Group C: Behavioral (Discord live session)

### C1. Voice join roast

expected: Join a voice channel with the bot present. Repeat 4–5 times (roast fires at ~30% chance per join under the 5-minute per-user ambient ceiling). At least one roast should appear in the DEXTER_CHANNEL_ID or the active music channel. Roast text is Gemini-personalized when the API key is live; falls back to VOICE_JOIN_ROASTS templates on rate-limit.

result: [pending]

---

### C2. Late-night roast (P-03 TZ fix verification)

expected: Join voice between 1–5am America/New_York (or temporarily patch `cogs/events.py` `is_late_night` to always return `True` for a one-off test). A roast fires at ~50% chance with late-night flavor text. This also confirms the `cogs/events.py` `ZoneInfo(config.STREAK_TIMEZONE)` fix from P-03 fires at the correct community hour — not UTC. If it fires at 1–5am ET correctly, the TZ fix is live. If the bot fails to fire during late-night ET hours (fires only at 1–5am UTC = 8–10pm ET), the TZ fix did not apply; escalate to `/gsd:debug` for log inspection.

result: [pending]

---

### C3. Startup message

expected: Trigger a Koyeb restart or redeploy → within ~30 seconds a personality startup message (from `personality/roasts.STARTUP_MESSAGES`, e.g. "i'm back. did you miss me. probably not.") posts to DEXTER_CHANNEL_ID. Check Koyeb logs (console or `koyeb services logs <service>`) for `Dexter is ready.` to confirm the startup sequence completed.

result: [pending]

---

### C4. Status rotation

expected: Watch the bot's Discord presence for 10–15 minutes. The presence cycles through: current playing song (if any), server-count personality line ("N servers that don't deserve me"), a random STATUS_LINES entry, and a seasonal line when applicable. Each cycle is ~5 minutes.

result: [pending]

---

### C5. /lyrics command

expected: `/play` a popular song with known Genius lyrics; after playback starts, `/lyrics`. If `GENIUS_TOKEN` is set: paginated embed with lyrics appears; Previous/Next buttons work; buttons disable after 3-minute timeout. If `GENIUS_TOKEN` is absent: AZLyrics fallback fires or `NO_LYRICS_FOUND` personality line appears.

result: [pending]

---

### C6. /history command

expected: After queuing several songs, `/history` returns a paginated embed showing recently queued songs with title, artist, requester display name, and date. Previous/Next buttons work.

result: [pending]

---

### C7. Message reactions

expected: In a channel the bot can see: (a) paste a YouTube URL → bot reacts 👀; (b) type "gn" or "goodnight" → bot reacts 🫡; (c) mention the bot with no other text → bot reacts 😐; (d) mention the bot and include "thanks" → bot replies with deflecting warmth ("...you're welcome. don't get used to it." or similar).

result: [pending]

---

### C8. Repeat-song roast

expected: Queue the same song 3 times in one day. On the 3rd queue, a roast fires unconditionally (no probability roll) to the music channel. Gemini-personalized when available; REPEAT_SONG_ROAST_TEMPLATES fallback otherwise.

result: [pending]

---

### C9. Idle loneliness

expected: Stay in voice with no commands for 30+ minutes. Bot posts one `IDLE_LONELINESS_MESSAGES` line to the channel. It does not repeat until new activity. The bot does NOT leave early (auto-leave timer is separate and unaffected).

result: [pending]

---

### C10. Streak and milestone roasts

expected: Use the bot on consecutive days to build a streak; queue songs until a milestone count (100/250/500/1000) is reached. At streak milestones (7/14/30/60/100 days), a streak roast fires referencing `longest_streak`. At song-count milestones, a song-count roast fires. Both attempt a Gemini-personalized line with MILESTONE_ROAST_TEMPLATES fallback. (Testing tip: temporarily lower a threshold in config to trigger quickly.)

result: [pending]

---

### C11. DEPLOY-04 diagnostic (reconnect race, live observation)

expected: Trigger a live voice disconnect/reconnect (e.g. network blip, or move the bot to another channel and back). Inspect Koyeb logs (console or `koyeb services logs <service>`) for the INFO-level reconnect trail: `reconnect attempt X/3 in guild Y` and `reconnect: vc.is_connected()=True gen=Z guild=Y`. If playback resumes after reconnect, the P-01 defensive fix is working. If playback silently fails after a reconnect but the log shows `vc.is_connected()=True`, escalate to a dedicated `/gsd:debug` session using the diagnostic log trail — per D-04.

result: [pending]

---

## Group D: Destructive (ALWAYS LAST)

> Run this section only after Groups A, B, and C have passed. The Neon PITR restore in D1 temporarily interrupts connections and overwrites live branch history within the restore window — it cannot corrupt earlier UAT results if it runs last.

### D1. Neon PITR restore proof (DEPLOY-07 / K-08 / K-17 #5)

expected:

1. **(Optional but recommended) Seed roast-fuel rows:** Run `python scripts/seed_restore_test.py` to insert known rows into the live Neon database (1 user_profiles, 3 song_history, 2 user_artist_counts), or alternatively queue real songs and run `/history` to confirm meaningful song_history rows exist. Note the current timestamp.

2. **Confirm restore point:** In the Neon console → Project → Branches → select the main branch → "Backup & Restore". Click "Time Travel Assist" and run a read-only query against a timestamp 15–30 minutes in the past — confirm expected rows (e.g. recent song_history entries) are visible at that point.

3. **Trigger the PITR restore:** Select restore mode "From history", choose a timestamp within the 6-hour PITR window (at least 15 minutes in the past so meaningful data is visible). Click "Next" → review the pending changes → click "Restore."

4. **Verify the backup branch was created:** Neon automatically creates a `{branch_name}_old_{head_timestamp}` branch before overwriting. Confirm it appears in the Branches list.

5. **Confirm automatic reconnect:** Connections to the branch temporarily interrupt during the restore. The asyncpg pool reconnects automatically on the next query (same hostname and port). No bot restart needed.

6. **Verify data integrity post-restore:** Run `/history` in Discord — it should return song_history rows consistent with the restore timestamp (seed rows inserted after the restore point will be gone; rows that existed before it will be present). This confirms DEPLOY-07 and K-17 #5.

The live Neon branch is the only target. Never run `pg_restore`, `dropdb`, or any destructive local command against the live Neon database.

result: [pending]

---

## Troubleshooting Table

| Symptom | Probable Cause | Fix |
|---------|---------------|-----|
| Koyeb service stuck "Unhealthy" or restarting in a loop | Health endpoint not binding to `0.0.0.0:8000` | Confirm `TCPSite(runner, '0.0.0.0', 8000)` in `bot.py` — binding to `'localhost'` is unreachable by Koyeb's health checker (Pitfall 5). Check Koyeb logs for startup errors. |
| Bot goes offline after ~1 hour of Discord inactivity | UptimeRobot not pinging, or monitor not set up | Check UptimeRobot dashboard — monitor should show green. Confirm URL is `https://<service>.koyeb.app/health`. Koyeb free WEB services sleep after 1h without inbound HTTP traffic (Pitfall 4). |
| `asyncpg.exceptions.PostgresError: unrecognized configuration parameter "channel_binding"` at startup | `sanitize_database_url()` not applied, or `channel_binding=require` reaching asyncpg | Verify `config.sanitize_database_url(config.DATABASE_URL)` is called before passing DSN to `create_pool`. The function strips the entire query string (Pitfall 1). |
| Intermittent DB errors / SSL-EOF after quiet periods (5+ min idle) | `max_inactive_connection_lifetime` not set below 300s | Confirm `max_inactive_connection_lifetime=240` in the `create_pool` call in `bot.py`. Neon suspends after 5 min; the pool must evict at 4 min (Pitfall 2). |
| `asyncpg.exceptions.InvalidSQLStatementNameError: prepared statement "..." does not exist` | `statement_cache_size` not set to 0 | Confirm `statement_cache_size=0` in `create_pool`. Neon's PgBouncer in transaction mode is incompatible with asyncpg's default prepared-statement caching (Pitfall 3). |
| New commits to `main` not triggering Koyeb builds after merge | Koyeb still tracking the feature branch after merge | In Koyeb service settings, update the tracked branch from `gsd/phase-5-ship-it-live` to `main` after the merge (Pitfall 8). |
| Slash commands not appearing in Discord | Command sync not run | `python bot.py --first-run --guild <GUILD_ID>`; then wait ~10 seconds |
| `DISCORD_TOKEN` invalid / bot returns 401 | Stale or regenerated token | Discord Developer Portal → Bot → Reset Token → copy → update Koyeb encrypted secret `DISCORD_TOKEN`; trigger a redeploy. |

---

## Session Summary

Run this table at the end of the session.

| Group | Checks | Passed | Failed | Notes |
|-------|--------|--------|--------|-------|
| A — Boot + Infra | A1, A2, A3, A4, A5, A6, A7 | | | |
| B — Queue Persistence | B1, B2, B3 (scale-to-zero) | | | |
| C — Behavioral | C1–C11 | | | |
| D — Destructive | D1 (Neon PITR) | | | |
| **Total** | **22** | | | |

Phase 5 is verified-live when all 22 checks pass on Koyeb+Neon per K-17. Report results via `/gsd-verify-work`.

---

*Phase: 05-ship-it-live*
*Runbook version: 2.0 (Koyeb+Neon) — re-targeted 2026-06-15 per K-18*
*Source: Plan 05-03-PLAN.md*
