# Dexter — Koyeb + Neon Deploy Contract

**Status:** Live deploy guide for Phase 5 (v1.1 "Live & Lethal")
**Environment:** Koyeb free WEB service + Neon serverless Postgres + UptimeRobot keep-alive
**Cost:** $0/mo, no credit card required
**Archived Oracle scripts:** see `scripts/archive/` (backup.sh, keepalive.sh, deploy.sh, lifecycle-policy.json retired by Neon PITR + UptimeRobot + Koyeb git-deploy)

---

## 1. Substrate Overview

| Component | Provider | Purpose |
|-----------|----------|---------|
| Bot process (24/7) | Koyeb free WEB service | Runs the Discord gateway + audio pipeline |
| Database | Neon free serverless Postgres | Persistent bot data; pooled PgBouncer endpoint |
| Keep-alive ping | UptimeRobot free (5-min interval) | Prevents Koyeb's 1-hour scale-to-zero sleep |
| Dead-man monitoring | Healthchecks.io (bot-side outbound ping) | Alerts if the bot process stops pinging |

All three services have free tiers that require no credit card. The bot costs $0/mo to run.

---

## 2. Neon Setup

### Create the Neon project

1. Sign up at https://neon.com (no credit card required).
2. Create a new project. **Select region `us-east-2` (AWS US East)** — co-located with Koyeb wdc1 for lowest latency.
3. The default `main` branch is your production database.

### Get the connection string

1. In the Neon console, go to **Connection Details**.
2. Select **Pooled connection** (the host contains `-pooler` in the hostname, e.g. `ep-<id>-pooler.us-east-2.aws.neon.tech`).
3. Copy the full connection string. It looks like:
   ```
   postgresql://user:pass@ep-<id>-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require
   ```
4. Paste it as the `DATABASE_URL` Koyeb encrypted secret (see Section 4).

### Schema initialization

The bot's `init_db()` runs `SCHEMA_SQL` on startup and auto-creates all tables. **No manual migration needed.** Neon starts fresh (K-06); there is no migration from a local Postgres instance.

The bot code strips the `?sslmode=require&channel_binding=require` query string at startup via `config.sanitize_database_url()` before passing the DSN to asyncpg. Paste the raw Neon string — the code handles it.

---

## 3. Koyeb Service Setup

### Create a WEB service (not Worker)

Koyeb free tier only supports **WEB services** (Worker services are not available on free). The bot runs as a WEB service with a minimal `/health` endpoint (port 8000) that Koyeb's health checker pings.

1. Sign up at https://koyeb.com (no credit card required).
2. **Create Service → GitHub.**
3. Connect your GitHub repository (authorize the Koyeb GitHub app if prompted).
4. Configuration:
   - **Branch:** `gsd/phase-5-ship-it-live` (re-point to `main` after you merge and UAT passes)
   - **Build method:** Dockerfile
   - **Region:** Washington D.C. (`wdc1`) — closest US-East Discord gateway node
   - **Instance type:** Free (512 MB RAM / 0.1 vCPU / 2 GB ephemeral SSD)
   - **Health check:** HTTP, path `/health`, port `8000`
5. Add environment variables (see Section 4).
6. Click **Deploy**.

Koyeb auto-builds and redeploys on every push to the tracked branch. No manual deploy needed after the initial setup.

### After merging to main

Once live UAT passes and you merge `gsd/phase-5-ship-it-live` into `main`:

1. In the Koyeb service settings, update the tracked branch from `gsd/phase-5-ship-it-live` to `main`.
2. Future commits to `main` trigger automatic rebuilds.

---

## 4. Secrets vs Environment Variables (K-13)

**Identical variable names across local `.env` and Koyeb.** The bot code is unchanged between environments.

| Variable | Koyeb mechanism | Why |
|----------|----------------|-----|
| `DISCORD_TOKEN` | Encrypted Secret | Sensitive — never visible in build logs |
| `GEMINI_API_KEY` | Encrypted Secret | Sensitive |
| `GENIUS_TOKEN` | Encrypted Secret | Sensitive |
| `DATABASE_URL` | Encrypted Secret | Contains Neon credentials — use the POOLED string |
| `DEXTER_CHANNEL_ID` | Plain env var | Non-sensitive Discord channel ID |
| `ERROR_LOG_CHANNEL_ID` | Plain env var | Non-sensitive Discord channel ID |
| `OWNER_ID` | Plain env var | Non-sensitive Discord user ID |
| `HEALTHCHECK_URL` | Plain env var | Non-sensitive Healthchecks.io ping URL |
| `STREAK_TIMEZONE` | Plain env var | Config string (default `America/New_York`) |

**Never bake secrets into the Dockerfile or image layers** (T-04-05). Koyeb encrypted Secrets are injected at container runtime only — they never appear in build logs.

To add a Koyeb secret: **Service settings → Environment → + Add variable → toggle "Secret".**

---

## 5. UptimeRobot Keep-Alive (K-02 amendment)

Koyeb free WEB services scale to zero after **1 hour of no inbound HTTP traffic**. When the bot goes to sleep, the Discord gateway drops and the bot goes offline.

**Fix:** UptimeRobot pings `/health` every 5 minutes, keeping Koyeb awake indefinitely.

### Setup

1. Sign up at https://uptimerobot.com (free tier: 50 monitors, 5-minute interval).
2. **Add New Monitor:**
   - Type: `HTTP(s)`
   - Friendly name: `Dexter health`
   - URL: `https://<your-service-name>.koyeb.app/health`
   - Monitoring interval: `5 minutes`
3. Click **Create Monitor**.

The health endpoint returns `{"status":"ok"}` (HTTP 200). UptimeRobot also alerts you if the service goes down, doubling as an uptime monitor.

Replace `<your-service-name>` with your Koyeb service's actual subdomain (visible in the Koyeb service dashboard under "Public URL").

---

## 6. Dead-Man Monitoring (K-09)

The bot sends outbound pings to Healthchecks.io at regular intervals. If the bot process crashes or stalls, Healthchecks.io alerts you because it stops receiving pings.

Set `HEALTHCHECK_URL` to your Healthchecks.io ping URL as a plain env var in Koyeb (e.g. `https://hc-ping.com/your-uuid-here`). If left blank, the feature is silently disabled.

Sign up at https://healthchecks.io (free tier: 20 checks).

---

## 7. K-14 Break-Glass Rule

**Never run the local PC `docker compose` stack and the Koyeb service simultaneously on the same Discord token.**

Two bot instances on one token triggers a gateway conflict: both instances disconnect repeatedly in a loop. Neither works.

- **Normal operation:** Koyeb is the sole running instance.
- **Break-glass / local debugging:** Stop the Koyeb service first, then bring up `docker compose` locally.
- **Local compose:** Uses a local Postgres container (see `docker-compose.yml`). Set `DATABASE_URL` to the local Postgres URL in your `.env`.

---

## 8. K-10 Runner-Swap Contingency

If Koyeb proves unworkable — music stutters on 0.1 vCPU, or the service falls asleep despite UptimeRobot pings — swap the **runner only**. The Neon database and all bot data stay unchanged.

**Recommended first alternative: HeavenCloud**
- 715 MB RAM, 1 GB disk, 70% CPU, USA location
- No sleep mode, no credit card required
- Claim via Discord at discord.gg/getvps
- Manual upload (no git-deploy); set env vars via panel

**Second alternative: Wispbyte**
- 24/7 uptime, Python supported, no credit card
- Less documented; use if HeavenCloud is unavailable

**Swap procedure:**
1. Stop the Koyeb service.
2. Upload the bot to HeavenCloud/Wispbyte.
3. Set identical env vars (same `DATABASE_URL` pointing at Neon, same token, same channel IDs).
4. Start the bot on the new runner.

Only the runner changes. Neon, bot code, and Discord config are all unchanged.

---

## 9. Archived Oracle Scripts

The following scripts from the original Oracle A1 deploy are preserved in `scripts/archive/` for reference. They are **not used** in the Koyeb+Neon deployment:

| Script | Was used for | Replaced by |
|--------|-------------|-------------|
| `scripts/archive/backup.sh` | pg_dump cron to OCI Object Storage | Neon-managed PITR (6-hour window) |
| `scripts/archive/keepalive.sh` | Oracle host idle-reclaim keepalive | UptimeRobot external ping |
| `scripts/archive/deploy.sh` | Manual VM git-pull + compose rebuild | Koyeb git-auto-build (K-11) |
| `scripts/archive/lifecycle-policy.json` | OCI Object Storage lifecycle rule | No OCI bucket in Koyeb stack |

`scripts/seed_restore_test.py` is kept at `scripts/` — it inserts synthetic rows into the DB and is useful for verifying a Neon PITR restore worked (insert rows, wait, restore to before-insert, confirm rows are gone).
