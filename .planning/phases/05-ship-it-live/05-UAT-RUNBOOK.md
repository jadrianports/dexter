---
status: partial
phase: 05-ship-it-live
source: [05-CONTEXT.md, 05-RESEARCH.md, 04-VERIFICATION.md, 03-VERIFICATION.md, 04-HUMAN-UAT.md]
started: [fill on execution]
updated: [fill on execution]
---

# Dexter Live-UAT Runbook

**Consolidated from:** 03-VERIFICATION.md (9 behavioral checks), 04-VERIFICATION.md (6 deploy checks), 04-HUMAN-UAT.md (6 human scenarios — de-duped with 04-VERIFICATION)

**Run on:** Oracle A1 ARM VM via SSH

**Session flow:** A (boot/infra) → B (queue persistence) → C (behavioral/Discord) → D (destructive/restore, ALWAYS LAST)

---

> **WARNING — CRITICAL**
>
> **NEVER run `docker compose down -v` in production.**
>
> This wipes the `postgres_data`, `audio_cache`, and `logs` named volumes — complete database loss with no recovery unless a very recent OCI backup exists. The word "volumes" is the landmine.
>
> Safe operations:
> - `docker compose restart bot` — restarts bot container only; DB unaffected; volumes intact
> - `docker compose up -d --build bot` — rebuilds and restarts bot only; DB unaffected; volumes intact
> - `docker compose down` (no `-v`) — stops containers; volumes survive; `docker compose up -d` brings them back
>
> `deploy.sh` never calls `down -v`. Do not add it. If someone asks "should I run `docker compose down -v`?" — the answer is NO.

---

## Prerequisites Checklist

Complete every item before running check A1. These are one-time setup steps on the Oracle A1 VM.

- [ ] **VM timezone:** `sudo timedatectl set-timezone America/New_York && timedatectl` — verify "America/New_York"
- [ ] **Docker enabled for reboot:** `systemctl is-enabled docker` — should print `enabled`; if not: `sudo systemctl enable docker`
- [ ] **Environment file:** `cp .env.example .env` → fill in `DISCORD_TOKEN`, `GEMINI_API_KEY`, `GENIUS_TOKEN`, `POSTGRES_PASSWORD`, `OWNER_ID`, `DEXTER_CHANNEL_ID`, `STREAK_TIMEZONE=America/New_York`; then `chmod 600 .env`
- [ ] **pg_dump auth:** `echo "localhost:5432:dexter:dexter:YOUR_POSTGRES_PASSWORD" >> ~/.pgpass && chmod 600 ~/.pgpass` — verify with `cat ~/.pgpass`
- [ ] **OCI CLI config:** `oci setup config` (interactive; creates `~/.oci/config`) — test with `oci iam region list`
- [ ] **OCI lifecycle policy applied:** `NAMESPACE=$(oci os ns get --query 'data' --raw-output) && oci os object-lifecycle-policy put --namespace-name "${NAMESPACE}" --bucket-name dexter-backups --items file://scripts/lifecycle-policy.json`
- [ ] **Crontab entries installed:**

  ```crontab
  HEALTHCHECK_URL=https://hc-ping.com/<your-uuid>
  */5 * * * * /opt/dexter/scripts/keepalive.sh >> /var/log/dexter/keepalive.log 2>&1
  0 */6 * * * /opt/dexter/scripts/backup.sh >> /var/log/dexter/backup.log 2>&1
  ```

  Install with `crontab -e`; verify with `crontab -l`

- [ ] **Host pg_dump version check:** `pg_dump --version` — should print `pg_dump (PostgreSQL) 16.x`; if version is below 16, install: `sudo apt-get install -y postgresql-client-16`. Version parity prevents dump/restore format divergence. (The restore in D1 bypasses this via `docker compose exec`, but host pg_dump produces the backup in A5/D1.)
  result: [pending]

- [ ] **Per-guild command sync (first deploy only):** `python bot.py --first-run --guild <GUILD_ID>` — slash commands appear in Discord within seconds; subsequent syncs via owner `/sync <guild_id>`
- [ ] **Healthchecks.io check created:**
  - Sign in to healthchecks.io → New Project ("Dexter Monitoring") → Add Check → Name: "Dexter Keepalive" → Period: 10 min, Grace: 10 min → Save → copy ping URL (format: `https://hc-ping.com/<36-char-uuid>`)
  - Discord integration: error-log channel → Channel Settings → Integrations → New Webhook → copy URL → Healthchecks.io → Integrations → Add Integration → Discord → paste webhook URL → test it → toggle on for the check
  - Email integration: Healthchecks.io → Integrations → Add Integration → Email → enter email → toggle on for the check

---

## Group A: Boot + Infra

### A1. Docker clean boot

expected: `cd /opt/dexter && docker compose up -d && docker compose logs -f bot` → Postgres healthcheck passes (`healthy`); bot logs `Dexter is ready.`; startup personality message posts to DEXTER_CHANNEL_ID in the guild. For ongoing updates use `bash scripts/deploy.sh` (git pull + `docker compose up -d --build bot`).

result: [pending]

---

### A2. Reboot survival

expected: `systemctl is-enabled docker` returns `enabled`; then `sudo reboot`; wait ~90 seconds; check Discord — the bot posts its startup message automatically without any SSH intervention. Run `/queue` to confirm queue state is restored if a guild_queues row existed.

result: [pending]

---

### A3. Over-cap /play rejection

expected: Set `MAX_QUEUE_SIZE_PER_GUILD=1` in `.env`, run `docker compose restart bot`, then `/play` two different songs. Second `/play` returns the personality cap rejection ("queue's full at 1 track. impressive dedication, wrong bot." or equivalent). Queue length stays at 1. Restore `MAX_QUEUE_SIZE_PER_GUILD` to 500 and restart when done.

result: [pending]

---

### A4. Keepalive cron and Healthchecks.io

expected: After crontab is installed with `HEALTHCHECK_URL` set, wait 10–15 minutes and check the Healthchecks.io dashboard. The "Dexter Keepalive" check shows green with "Last ping: X minutes ago". The Discord error-log channel shows a "Bot Dexter Keepalive is UP" notification when the integration first fires.

result: [pending]

---

### A5. Backup cron (manual run)

expected: `bash scripts/backup.sh` exits 0; a new `dexter_YYYYMMDD_HHMMSS.dump` object appears in the `dexter-backups` OCI bucket (verify with `oci os object list --bucket-name dexter-backups --namespace-name "$(oci os ns get --query 'data' --raw-output)"`).

result: [pending]

---

### A6. Postgres integration tests

expected: `pytest tests/test_database_phase4.py -x` against a live `dexter_test` Postgres database (`CREATE DATABASE dexter_test;` first) exits 0 with 18 tests green (TestPostgresSchema, TestBatchTransaction, TestHelpers).

result: [pending]

---

## Group B: Queue Persistence

### B1. Queue persistence round-trip

expected: `/play` a song in the guild (confirm it appears in `/queue`); `docker compose restart bot`; rejoin voice if a non-bot human was present; `/queue` after restart — the queue is restored from `guild_queues`; smart-rejoin connects voice and resumes playback only when a non-bot human is still in the channel.

result: [pending]

---

### B2. clear_persisted on idle-leave (DEPLOY-06 / IN-02 fix)

expected: Join voice with the bot; let it sit alone for 10+ minutes (no commands, no other humans); bot auto-leaves and posts the idle-leave message; `docker compose restart bot`; `/queue` — queue is **empty** (not restored). This confirms `clear_persisted()` fired on idle-leave (the `bot.py:~396` fix from Plan 01). If the queue restores, the fix did not apply — inspect `docker compose logs bot` for `clear_persisted` calls.

result: [pending]

---

## Group C: Behavioral (Discord live session)

### C1. Voice join roast

expected: Join a voice channel with the bot present. Repeat 4–5 times (roast fires at ~30% chance per join under the 5-minute per-user ambient ceiling). At least one roast should appear in the DEXTER_CHANNEL_ID or the active music channel. Roast text is Gemini-personalized when the API key is live; falls back to VOICE_JOIN_ROASTS templates on rate-limit.

result: [pending]

---

### C2. Late-night roast (DEPLOY-04 TZ fix verification)

expected: Join voice between 1–5am America/New_York (or temporarily patch `cogs/events.py` `is_late_night` to always return `True` for a one-off test). A roast fires at ~50% chance with late-night flavor text. This also confirms the `cogs/events.py` `ZoneInfo(config.STREAK_TIMEZONE)` fix from Plan 01 fires at the correct community hour — not UTC. If it fires at 1–5am ET correctly, the TZ fix is live. If the bot fails to fire during late-night ET hours (fires only at 1–5am UTC = 8–10pm ET), the TZ fix did not apply; escalate to `/gsd:debug` for log inspection.

result: [pending]

---

### C3. Startup message

expected: `docker compose restart bot` → within ~30 seconds a personality startup message (from `personality/roasts.STARTUP_MESSAGES`, e.g. "i'm back. did you miss me. probably not.") posts to DEXTER_CHANNEL_ID.

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

expected: Trigger a live voice disconnect/reconnect (e.g. network blip, or move the bot to another channel and back). Inspect `docker compose logs bot` for the INFO-level reconnect trail: `reconnect attempt X/3 in guild Y` and `reconnect: vc.is_connected()=True gen=Z guild=Y`. If playback resumes after reconnect, the WR-03 defensive fix from Plan 01 is working. If playback silently fails after a reconnect but the log shows `vc.is_connected()=True`, escalate to a dedicated `/gsd:debug` session using the diagnostic log trail — per D-04.

result: [pending]

---

## Group D: Destructive (ALWAYS LAST)

> Run this section only after Groups A, B, and C have passed. Group D uses a throwaway database and never touches the live `dexter` database, but a restore failure cannot corrupt earlier UAT results if it runs last.

### D1. End-to-end restore proof (DEPLOY-07 / D-15)

expected: `python scripts/seed_restore_test.py` from `/opt/dexter`. The script: (1) seeds known rows into the live `dexter` database (1 user_profiles, 3 song_history, 2 user_artist_counts); (2) runs `bash scripts/backup.sh` to produce a fresh dump in OCI; (3) downloads the newest dump from the `dexter-backups` bucket; (4) validates the dump file is larger than 1 KB; (5) creates `dexter_restore_test` via `docker compose exec postgres createdb -U dexter -T template0 dexter_restore_test`; (6) restores via `docker compose exec postgres pg_restore` (version-matched — avoids host pg_restore mismatch); (7) connects to `dexter_restore_test` and asserts row counts match the seeded counts; (8) drops the throwaway database. Script exits 0 with a "restore verified" summary. The live `dexter` database is never passed to `pg_restore` or `dropdb`.

result: [pending]

---

## Troubleshooting Table

| Symptom | Probable Cause | Fix |
|---------|---------------|-----|
| `docker compose up` fails: `no matching manifest for linux/arm64` | Image without arm64 variant | Confirm you are on Oracle A1 (`uname -m` → `aarch64`); if not, this is a dev machine — not the deploy target |
| Bot container exits immediately (exit code 1) | Missing or malformed `.env` | `docker compose logs bot` — look for "DISCORD_TOKEN not set" or asyncpg DSN errors; verify `.env` has all required keys |
| `healthcheck: starting` never becomes `healthy` | `pg_isready` failing inside Postgres container | `docker compose logs postgres` — check for storage permission errors or volume corruption; if audio_cache volume only is corrupted: `docker compose down; docker volume rm dexter_audio_cache; docker compose up -d` (NEVER `down -v`) |
| `pool-acquire timeout` in bot logs | Bot started before Postgres finished init | Handled by `depends_on: service_healthy`; if it still occurs, run `docker compose restart bot` to let Postgres finish initializing; consider increasing `retries: 5` in the postgres healthcheck |
| Volume permission errors in logs | Docker named volume created with wrong ownership | For non-postgres volumes only: `docker compose down; docker volume rm dexter_audio_cache; docker compose up -d`; for postgres_data permission issues, restore from OCI backup |
| Slash commands not appearing in Discord | Command sync not run | `python bot.py --first-run --guild <GUILD_ID>`; then wait ~10 seconds |
| `DISCORD_TOKEN` invalid / bot returns 401 | Stale or regenerated token | Discord Developer Portal → Bot → Reset Token → copy → update `.env`; `docker compose restart bot` |
| `pg_dump` in `backup.sh` fails: `password authentication failed` | `~/.pgpass` not set or wrong permissions | `chmod 600 ~/.pgpass`; verify contents match `localhost:5432:dexter:dexter:<password>`; no trailing whitespace |
| `oci os object put` fails: `NotAuthenticated` | `~/.oci/config` not set or expired key | `oci iam region list` to test; re-run `oci setup config`; if using instance principal, ensure IAM policy grants `manage objects in compartment` |

---

## Session Summary

Run this table at the end of the session.

| Group | Checks | Passed | Failed | Notes |
|-------|--------|--------|--------|-------|
| A — Boot + Infra | A1, A2, A3, A4, A5, A6 | | | |
| B — Queue Persistence | B1, B2 | | | |
| C — Behavioral | C1–C11 | | | |
| D — Destructive | D1 | | | |
| **Total** | **21** | | | |

Phase 5 is verified when all 21 checks pass on Oracle A1. Report results via `/gsd-verify-work`.

---

*Phase: 05-ship-it-live*
*Runbook version: 1.0 (2026-06-12)*
*Source: Plan 05-03-PLAN.md*
