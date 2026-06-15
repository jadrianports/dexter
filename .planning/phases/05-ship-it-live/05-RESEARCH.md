# Phase 5: Ship It Live — Research (Re-targeted: Koyeb + Neon)

**Researched:** 2026-06-15
**Domain:** Koyeb WEB service + Neon serverless Postgres + asyncpg pool tuning + Discord.py
**Confidence:** MEDIUM-HIGH (Koyeb/Neon platform docs verified via WebFetch from official sources; asyncpg confirmed via Context7 HIGH-reputation official docs)
**Supersedes:** The 2026-06-12 Oracle/OCI research — overwritten entirely.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Pivot framing**
- K-01: Deploy substrate pivots Oracle A1 ARM to Koyeb + Neon serverless Postgres. All Oracle-specific deploy decisions (systemctl, host git-pull, 6h pg_dump OCI cron, OCI lifecycle, OCI Object-Storage restore proof) are superseded. The three code fixes (P-01...P-03), per-guild sync (P-04), the $0/mo hard constraint, single-community target, and the consolidated-runbook approach are preserved.

**Hosting — Koyeb**
- K-02: Deploy as a Koyeb WORKER service (no HTTP port). [SEE CRITICAL RESEARCH FINDING BELOW — this requires amendment.]
- K-10: Runner-swap trigger = stutter OR sleep. Swap runner to Wispbyte/HeavenCloud (same Neon DB, only runner changes) if music stutters (CPU) OR Koyeb can't hold 24/7 gateway.

**Database — Neon**
- K-03: Neon free serverless Postgres, pooled (PgBouncer) connection endpoint.
- K-04: asyncpg pool tuning: max_inactive_connection_lifetime < 300s (e.g. 240s), statement_cache_size=0, DB_POOL_MAX ~5.
- K-05: Sanitize DATABASE_URL at startup: strip channel_binding=require, force sslmode=require, apply pooler flags.
- K-06: Neon starts fresh. init_db() auto-creates schema. No migration from PC Postgres.

**Audio cache**
- K-07: Keep download-first caching, drop AUDIO_CACHE_MAX_MB to disk-safe value (256-512MB pending Koyeb disk confirmation).

**Backups**
- K-08: Neon managed backups / PITR only. backup.sh retired. Seed script optional for UAT roast-fuel.

**Uptime, monitoring**
- K-09: Keep bot-side Healthchecks.io dead-man ping. Drop Oracle host keepalive (keepalive.sh).

**Deploy and branch flow**
- K-11: Koyeb git-driven auto-build from repo Dockerfile, tracking branch gsd/phase-5-ship-it-live. Once UAT green, user merges to main, Koyeb re-pointed at main.
- K-12: docker-compose.yml is local-dev / break-glass only. Koyeb ignores compose, builds Dockerfile directly.

**Secrets**
- K-13: Identical env-var names across both environments. Local: .env. Koyeb: DISCORD_TOKEN / GEMINI_API_KEY / GENIUS_TOKEN / DATABASE_URL as encrypted Koyeb secrets; channel/owner IDs as plain env vars.

**Local fallback**
- K-14: Koyeb is sole normally-running prod. PC compose is break-glass only. Never both at once (gateway conflict).

**yt-dlp and logging**
- K-15: Pin recent yt-dlp in requirements.txt + keep runtime self-heal.
- K-16: Logs to stdout + Koyeb viewer + Discord error channel. /app/logs files ephemeral/best-effort.

**Definition of done**
- K-17: Phase verified when: (1) bot holds 24/7 Koyeb; (2) redeploy auto-reconnects + restores queue from Neon; (3) pool survives Neon 5-min idle scale-to-zero with no SSL-EOF crash; (4) all behavioral UAT passes; (5) Neon restore confirmed.

**Runbook re-targeting**
- K-18: Surgical re-target of 05-UAT-RUNBOOK.md: DROP Oracle/OCI checks, SWAP Postgres refs to Neon, ADD Koyeb worker-alive + git-deploy + Neon scale-to-zero-reconnect + Neon-restore checks, KEEP proven ordered structure.

**Preserved code fixes (already on gsd/phase-5-ship-it-live)**
- P-01: Reconnect-race defensive fix + diagnostic instrumentation. Live-verify under Koyeb.
- P-02: clear_persisted() at idle-leave + reconnect-failure.
- P-03: TZ-correct late-night roast via ZoneInfo(STREAK_TIMEZONE).
- P-04: Per-guild command sync to community guild.

### Claude's Discretion
- Exact AUDIO_CACHE_MAX_MB value (256 vs 512).
- Exact yt-dlp pin version.
- Koyeb region pick (recommend Washington, D.C.).
- stdout log-handler implementation specifics.
- Whether bot.py yt-dlp tasks.loop keeps 4am-UTC or gets tzinfo.
- New config.py constants for Neon/pool/cache settings.
- Whether to keep the seed script for behavioral UAT roast-fuel.

### Deferred Ideas (OUT OF SCOPE)
- HTTP health endpoint / WEB service (Phase-8 Ops).
- Migrating PC local Postgres into Neon (start fresh, K-06).
- Multi-hour soak test as a gate (observed, not gated).
- Off-Neon backup (e.g. GitHub Actions cron pg_dump).
- GHCR image pipeline / pre-built-image deploy.
- Log-shipping / dashboard stack.
- Redis, mid-song position resume, per-guild Gemini rate isolation, persisting auto_lyrics across restart.
- Oracle-specific deferred items (now moot).
</user_constraints>

---

## CRITICAL RESEARCH FINDING: K-02 Requires Amendment

**Koyeb free tier CANNOT run Worker services.** [VERIFIED: koyeb.com/docs/reference/instances]

The official Koyeb documentation states explicitly: "They can't be used as Worker Services." Free instances are WEB services only.

**Implications for the plan:**

1. The Discord bot must be deployed as a **Koyeb WEB service**, not a WORKER.
2. A WEB service requires a **health check endpoint** (TCP or HTTP on port 8000, listening on 0.0.0.0).
3. **WEB services on the free tier scale-to-zero after 1 hour of inactivity** (no incoming HTTP traffic). This means the gateway connection drops after 1 hour idle.
4. **The fix:** Add a minimal HTTP health endpoint to the bot (a ~10-line aiohttp server) + configure UptimeRobot (free) to ping it every 5 minutes. This keeps the WEB service alive indefinitely. [CITED: zenn.dev/saitogo/articles/e763dad351594f — confirmed working approach in production]
5. **K-10 (runner swap) logic is unchanged:** If this health-ping approach fails to maintain 24/7 (e.g. Koyeb enforces deeper sleep despite pings), or music stutters on 0.1 vCPU, swap to HeavenCloud/Wispbyte which are true 24/7 no-sleep Discord bot hosts.
6. **CONTEXT.md Deferred Ideas says "HTTP health endpoint / WEB service — Phase-8 Ops scope."** That deferred a *rich* health endpoint with metrics (OPS-02). The minimal ping endpoint required for Koyeb to even accept the deployment is a deploy prerequisite, not an Ops feature. The planner must add a minimal health endpoint task.

**K-02 amendment for the planner:**
> Deploy as a Koyeb **WEB service** (Koyeb free tier does not offer Worker services). Add a minimal health-check HTTP endpoint (aiohttp, port 8000, single `/health` route returning 200) to satisfy Koyeb's health check requirement and enable UptimeRobot keep-alive pings. UptimeRobot (free tier, 5-minute interval) prevents the 1-hour scale-to-zero sleep.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Re-mapped for Koyeb+Neon | Research Support |
|----|-------------|--------------------------|-----------------|
| DEPLOY-01 | 24/7 run + restart survival | Koyeb WEB service (with health endpoint + UptimeRobot keep-alive) holds gateway 24/7; Koyeb auto-restarts on crash; queue restores from Neon on each redeploy | K-02 amendment + K-11 + queue persistence (smart-rejoin) |
| DEPLOY-02 | Standing live-UAT checklist (9 Phase-3 behavioral + 6 Phase-4 deploy checks) passes | Behaviorally unchanged; runbook re-targeted to Koyeb+Neon (K-18) | K-17, K-18 |
| DEPLOY-03 | 6 human-UAT scenarios pass | Behaviorally unchanged; live environment = Koyeb+Neon | K-17 |
| DEPLOY-04 | Voice playback survives reconnect under live concurrency | P-01 already coded + committed; live-verify under Koyeb | P-01, already done |
| DEPLOY-05 | Queue + playback position survive bot restart | Smart-rejoin restores from Neon guild_queues table on each Koyeb redeploy (K-11, K-17 #2) | queue_persistence.py + guild_queues JSONB |
| DEPLOY-06 | clear_persisted() fires on idle-leave + reconnect-failure | P-02 already coded + committed | P-02, already done |
| DEPLOY-07 | Backup + restore validated end-to-end | Re-mapped: Neon managed PITR (6-hour window on free); UAT check = Neon console branch-restore verified (K-08, K-17 #5) | Neon PITR research below |
| DEPLOY-08 | Keepalive / dead-man cron confirmed firing in production | Bot-side Healthchecks.io outbound ping kept (K-09); UptimeRobot ping doubles as keep-alive + dead-man confirmation | K-09 |
</phase_requirements>

---

## Summary

Phase 5's goal is unchanged: take Dexter from code-complete to running 24/7 in production with every v1.0 behavior validated live. The substrate is now Koyeb + Neon instead of Oracle A1.

The three code fixes (P-01...P-03) are already committed on `gsd/phase-5-ship-it-live`. The remaining net-new work this phase is: (1) asyncpg pool tuning + DATABASE_URL sanitizer, (2) Koyeb WEB service deployment config including a minimal health endpoint, (3) config.py constant updates, (4) logging stdout confirmation, (5) UAT runbook re-targeting, and (6) Oracle script retirement.

**Critical constraint discovered:** Koyeb free tier does not support Worker services. The bot must deploy as a WEB service with a minimal HTTP health endpoint + UptimeRobot keep-alive. This is a net-new code task (~10 lines of aiohttp) not anticipated in CONTEXT.md. The runner-swap (K-10) to HeavenCloud/Wispbyte remains the contingency if Koyeb's WEB service sleep behavior proves unworkable.

**Primary recommendation:** Deploy Koyeb as a WEB service with minimal aiohttp health endpoint on port 8000 + UptimeRobot free-tier ping every 5 minutes to prevent 1-hour scale-to-zero. Tune asyncpg create_pool with max_inactive_connection_lifetime=240 and statement_cache_size=0. Strip channel_binding from DATABASE_URL before passing to asyncpg. AUDIO_CACHE_MAX_MB=512 (generous within 2GB disk; drop to 256 if UAT shows pressure). Washington D.C. region for lowest America/New_York Discord latency.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Discord gateway connection | Koyeb WEB service (bot process) | — | Bot is a long-lived outbound TCP client; Koyeb WEB service keeps it alive with health check |
| HTTP health check / keep-alive | Koyeb WEB service (aiohttp health endpoint) | UptimeRobot (external ping) | Koyeb WEB services require a listening port; UptimeRobot prevents 1-hour sleep |
| Database (bot data) | Neon serverless Postgres | — | Pooled PgBouncer endpoint; asyncpg pool with Neon-tuned params |
| Queue persistence / restore | Neon (guild_queues JSONB table) | asyncpg pool | Smart-rejoin reads from Neon on every Koyeb redeploy |
| Audio cache | Koyeb ephemeral disk (/app/data/cache) | Re-download on cache-miss | 2GB SSD on Koyeb; ephemeral (wiped on redeploy); re-warms within session |
| Logging | Koyeb log viewer (stdout) | Discord error-log channel | Koyeb captures both stdout and stderr; Discord channel for alerts |
| Backups | Neon-managed PITR | Neon branch restore via console | 6-hour history window on free tier |
| Deploy pipeline | Koyeb git-auto-build (Dockerfile) | — | Replaces manual deploy.sh; auto-deploy on push to tracked branch |
| Secrets | Koyeb encrypted secrets | Local .env (dev/break-glass) | DISCORD_TOKEN, GEMINI_API_KEY, GENIUS_TOKEN, DATABASE_URL encrypted in Koyeb |
| Dead-man monitoring | Healthchecks.io (bot-side outbound ping) | UptimeRobot alert on sleep | Bot pings HEALTHCHECK_URL; UptimeRobot alerts if service goes unreachable |

---

## Research Directive 1: asyncpg + Neon Pooled (PgBouncer) Endpoint

### Confirmed Parameters

**`max_inactive_connection_lifetime`** [VERIFIED: Context7 / magicstack.github.io/asyncpg/current]
- Parameter type: `float` (seconds)
- Default: `300.0` (5 minutes)
- Purpose: asyncpg closes pool connections that have been idle longer than this value and opens a fresh one on next acquire.
- **Neon implication:** Neon free tier suspends compute after **5 minutes of idle**. An asyncpg pool connection that has been held open through that suspension will be dead (TCP terminated server-side). Setting `max_inactive_connection_lifetime=240` (4 minutes) ensures the pool recycles connections before Neon's 5-minute timer fires, eliminating SSL-EOF / connection-failure errors on reused dead connections.
- **Confirmed param name and type:** `max_inactive_connection_lifetime` as a keyword float. [VERIFIED: Context7]

**`statement_cache_size=0`** [VERIFIED: asyncpg official FAQ — magicstack.github.io/asyncpg/current/faq.html]
- The asyncpg FAQ explicitly documents that PgBouncer in **transaction pooling mode** (which Neon's pooled endpoint uses) is incompatible with asyncpg's default prepared-statement caching.
- Setting `statement_cache_size=0` disables automatic prepared statement caching. This is the documented fix.
- Also: `Connection.prepare()` must not be called when using PgBouncer transaction mode.
- Neon's pooler uses `pool_mode=transaction`. [CITED: neon.com/docs/connect/connection-pooling]

**SSL handling** [VERIFIED: asyncpg official API docs — magicstack.github.io/asyncpg/current/api/index.html]
- asyncpg `create_pool` accepts an `ssl` keyword argument (via `**connect_kwargs`) accepting: `bool`, `ssl.SSLContext`, or string modes `'prefer'`, `'require'`, `'verify-ca'`, `'verify-full'`.
- Pass `ssl='require'` directly to `create_pool` rather than via the DSN string.

**`channel_binding` parameter** [VERIFIED: asyncpg official API docs]
- asyncpg's recognized DSN parameters: `host, port, user, database/dbname, password, passfile, sslmode, sslcert, sslkey, sslrootcert, sslcrl, sslpassword, ssl_min_protocol_version, ssl_max_protocol_version`.
- `channel_binding` is **NOT in this list**. asyncpg treats unrecognized DSN parameters as PostgreSQL server settings (GUCs). Passing `channel_binding=require` as a GUC may cause a PostgreSQL error: `unrecognized configuration parameter "channel_binding"`.
- Neon's copy-from-console connection strings include `?sslmode=require&channel_binding=require`. [CITED: neon.com/guides/fastapi-async]
- **The sanitizer (K-05) must strip `channel_binding=require` from the DSN before passing to asyncpg.** Pass SSL via explicit `ssl='require'` kwarg instead.

### Concrete create_pool Recipe

```python
# Source: asyncpg official docs (Context7 / magicstack.github.io/asyncpg/current)
# + Neon PgBouncer pooling compatibility (neon.com/docs/connect/connection-pooling)

import re

def sanitize_database_url(dsn: str) -> str:
    """Strip asyncpg-incompatible query params from a Neon connection string.

    Neon's console-copy DSN includes ?sslmode=require&channel_binding=require.
    asyncpg does not recognize channel_binding and may pass it as a Postgres
    GUC, causing an error. sslmode is handled via explicit ssl= kwarg.
    Strips entire query string; safe for non-Neon DSNs (no-op if no ? present).

    Input:  postgresql://user:pass@host-pooler.neon.tech/db?sslmode=require&channel_binding=require
    Output: postgresql://user:pass@host-pooler.neon.tech/db
    """
    return re.sub(r'\?.*$', '', dsn)


# In bot.py _initialize_once(), replace the current asyncpg.create_pool call:
bot.pool = await asyncpg.create_pool(
    dsn=config.sanitize_database_url(config.DATABASE_URL),
    min_size=config.DB_POOL_MIN,                           # keep at 2
    max_size=config.DB_POOL_MAX,                           # lower to 5 for Neon free (K-04)
    command_timeout=30,
    ssl='require',                                          # K-05: explicit ssl, not via DSN string
    max_inactive_connection_lifetime=240,                   # K-04: recycle before Neon 5-min scale-to-zero
    statement_cache_size=0,                                 # K-04: disable prepared stmts for PgBouncer tx-mode
)
```

**Where this lands:** `bot.py` line 223 — the existing `asyncpg.create_pool(...)` call in `_initialize_once()`. The `sanitize_database_url` function belongs in `config.py` (co-located with the URL constant it sanitizes), imported and called in `bot.py`.

### Pooled vs Direct Endpoint

[CITED: neon.com/docs/connect/connection-pooling]

| Endpoint type | Hostname format | Use for |
|--------------|-----------------|---------|
| Direct | `ep-<id>.region.aws.neon.tech` | Migrations, DDL, LISTEN/NOTIFY |
| Pooled (PgBouncer) | `ep-<id>-pooler.region.aws.neon.tech` | Runtime queries (all bot traffic) |

**Use the pooled endpoint for the bot.** Neon console provides the pooled connection string (has `-pooler` in the hostname). Paste that string as `DATABASE_URL` in Koyeb secrets. The sanitizer strips `channel_binding` before it reaches asyncpg.

`init_db()` runs `SCHEMA_SQL` (plain DDL, no `$N` params) via the pool on startup. Plain DDL works through PgBouncer transaction mode because no prepared statement is used. No special handling needed.

---

## Research Directive 2: Koyeb Free Service — Critical Gate Finding

### Free Tier WORKER Restriction

**Koyeb free tier CANNOT run Worker services.** [VERIFIED: koyeb.com/docs/reference/instances]

| Question | Answer |
|----------|--------|
| Free instances can run as Worker services | NO — "They can't be used as Worker Services" |
| Free instances scale-to-zero after inactivity | YES — after 1 hour of no HTTP traffic |
| A Discord bot can run on Koyeb free tier | YES — as a WEB service with health endpoint |
| WEB service on free tier is truly 24/7 without intervention | NO — sleeps after 1h; needs UptimeRobot keep-alive |
| Credit card required for free tier | NO |

### Free Instance Specs [VERIFIED: koyeb.com/docs/reference/instances]

| Resource | Amount |
|----------|--------|
| RAM | 512 MB |
| vCPU | 0.1 (shared) |
| Disk (SSD) | 2 GB ephemeral |
| Network | 100 GB/month |
| Service type | WEB service only |
| Regions | Frankfurt (fra1) or Washington D.C. (wdc1) |
| Volumes (persistent storage) | Not available |
| Custom scaling | Not available |

### AUDIO_CACHE_MAX_MB Decision [Claude's Discretion, K-07]

Koyeb free disk = 2 GB SSD. The bot image (python:3.11-slim + ffmpeg + pip deps) consumes roughly 600-900 MB. Remaining usable disk: ~1.1-1.4 GB.

**Recommendation: `AUDIO_CACHE_MAX_MB = 512`**

Rationale: 512 MB leaves ~600 MB+ headroom. Cache is ephemeral (wiped on redeploy) and re-warms within a session. If disk pressure appears in UAT (cache cleanup logs warnings), drop to 256. [ASSUMED — exact image size not profiled; 512 is the safe midpoint]

### Koyeb WEB Service — Discord Bot Pattern

Since Koyeb requires a WEB service with health check, the bot needs: [CITED: community and official patterns confirmed working]

1. **Minimal HTTP health endpoint** inside the bot process:
   - `aiohttp.web` serves `GET /health` returning `{"status": "ok"}` on port 8000.
   - Runs as an asyncio background task in the same event loop as the Discord bot.
   - Koyeb health check configuration: HTTP, path `/health`, port 8000, interval 60s.
   - Must bind to `0.0.0.0:8000` (not `localhost`) or Koyeb cannot reach it.

2. **UptimeRobot free tier** (external, ~5-minute ping interval):
   - Pings `https://<service-name>.koyeb.app/health` every 5 minutes.
   - Prevents the 1-hour Koyeb sleep-scale-to-zero.
   - Doubles as uptime monitor for Discord alerts if service goes down.

**Relationship to CONTEXT.md deferred "HTTP health endpoint":**
The CONTEXT.md deferred a *rich* health endpoint (OPS-02 in REQUIREMENTS.md) to Phase 8. This minimal endpoint is 10 lines with no metrics, no bot-state exposure, no liveness signaling beyond "process is running" — it is categorically different from the Phase-8 feature. The planner must treat this as a deploy prerequisite, not a Phase-8 item.

### Build-from-Dockerfile + Git Auto-Deploy (K-11) [CITED: koyeb.com/docs/build-and-deploy/build-from-git]

- Connect GitHub repo to Koyeb console.
- Select branch: `gsd/phase-5-ship-it-live` (re-point to `main` post-merge).
- Build method: Dockerfile (not buildpack — the repo has an explicit Dockerfile).
- Koyeb auto-builds and redeploys on every push to the tracked branch.
- After live UAT passes and user merges to main, update Koyeb's tracked branch to `main`.

**Dockerfile adjustment:** Remove or replace the arm64/Oracle comment in line 1. Koyeb free is amd64; `python:3.11-slim-bookworm` is multi-arch and works as-is.

### Secrets + Env Vars (K-13) [VERIFIED: koyeb.com/docs/reference/secrets]

| Value | Type | Mechanism |
|-------|------|-----------|
| DISCORD_TOKEN | Sensitive | Koyeb encrypted Secret, referenced as `@DISCORD_TOKEN` |
| GEMINI_API_KEY | Sensitive | Koyeb encrypted Secret |
| GENIUS_TOKEN | Sensitive | Koyeb encrypted Secret |
| DATABASE_URL | Sensitive (connection string) | Koyeb encrypted Secret |
| DEXTER_CHANNEL_ID | Non-sensitive ID | Plain env var in Koyeb service config |
| ERROR_LOG_CHANNEL_ID | Non-sensitive ID | Plain env var |
| OWNER_ID | Non-sensitive ID | Plain env var |
| HEALTHCHECK_URL | Non-sensitive URL | Plain env var |
| STREAK_TIMEZONE | Config string | Plain env var (default America/New_York already in config.py) |

All env var names are identical to local `.env`. The bot code is unchanged.

### Region Pick [Claude's Discretion]

**Recommend: Washington D.C. (wdc1)**

The community timezone is `America/New_York` (Eastern US). Washington D.C. is geographically closer to Discord's US-East gateway nodes than Frankfurt, reducing voice command latency and reconnect times. Neon project should also be provisioned in the `us-east-2` AWS region for co-location (matching Koyeb wdc1). [ASSUMED — exact Discord gateway topology not verified; US-East is the standard recommendation for North American communities]

### K-10 Runner Swap: HeavenCloud / Wispbyte

If Koyeb proves unworkable (sleep despite UptimeRobot pings, or 0.1 vCPU causes music stutter):

**HeavenCloud (recommended first alternative):** [CITED: heavencloud.in]
- 715 MB RAM, 1 GB disk, 70% CPU, USA location, no sleep mode, no credit card
- Claim via Discord bot at discord.gg/getvps
- Uses a control panel with file manager + console + env var support
- No git-deploy (manual upload); env vars set via panel

**Wispbyte:** [CITED: wispbyte.com]
- 24/7 uptime, Python supported, no credit card, no renewals
- Less documented deployment process

**Runner-swap procedure:** Only the runner changes. Neon DATABASE_URL is identical. Bot code and Dockerfile are unchanged. Set identical env vars in HeavenCloud/Wispbyte panel.

---

## Research Directive 3: Neon Free Tier

### Scale-to-Zero Behavior [CITED: neon.com/docs/introduction/scale-to-zero + neon.com/docs/introduction/plans]

| Property | Value |
|----------|-------|
| Auto-suspend idle timeout | **5 minutes** — cannot be disabled on free tier |
| Cold start time when resuming | ~300-800ms (sub-second; first query may take ~1s total) |
| Effect on existing connections | **All idle connections terminated** when compute suspends |
| PITR / history window (free) | **6 hours**, capped at 1 GB of change history |
| Storage | 0.5 GB per project |
| Compute-hours / month | 100 CU-hours (sufficient for 24/7 at 0.25 CU: 0.25 * 400h = 100h) |
| Automated backup schedules | Not available on free tier |
| Manual snapshots | 1 allowed |
| Credit card required | **No** |

**Connection errors expected after Neon suspend:** [CITED: neon.com/guides/building-resilient-applications-with-postgres]
- `57P01` (admin_shutdown) — server shutting down during suspend
- `08006` (connection_failure) — connection to server lost
- `08003` (connection_does_not_exist) — connection attempt failed

**Why `max_inactive_connection_lifetime=240` prevents these:** asyncpg closes any pool connection idle for 240s and opens a fresh one on next acquire. Neon suspends at 300s. The pool proactively evicts before Neon terminates connections. After the 5-minute suspend, the next acquire opens a new connection to a freshly woken compute — no stale-connection errors.

### Managed Backups + PITR Restore (DEPLOY-07 / K-08 / K-17 #5) [CITED: neon.com/docs/guides/branching-pitr]

**Backup strategy:** Neon automatically tracks WAL history within the 6-hour window. No explicit "start backup" action needed.

**Branch-based restore procedure (the K-17 #5 / DEPLOY-07 UAT check):**

1. Neon console: project dashboard → Branches tab.
2. Select the main branch → "Backup & Restore" page.
3. Optional: Use "Time Travel Assist" — run read-only queries against a historical state to verify the restore point contains expected data (e.g. confirm a song_history row exists).
4. Select restore mode "From history" and choose a timestamp within the 6-hour window.
5. Click "Next" → review pending changes → click "Restore."
6. Neon creates a backup branch automatically (`{branch_name}_old_{head_timestamp}`) before overwriting.
7. Connections to the branch temporarily interrupt during restore; connection details unchanged (same hostname/port). asyncpg pool reconnects automatically on next acquire.
8. **Verify:** `/history` command returns expected data; Neon console shows the backup branch exists.

**Important free-tier limitation:** Only 1 manual snapshot. The 6-hour PITR window is the primary safety net. For the UAT check, the seed script (if kept, K-08) inserts synthetic rows before the restore, giving meaningful data to confirm the restore succeeded.

### Pooled vs Direct Endpoint [CITED: neon.com/docs/connect/connection-pooling + neon.com/docs/connect/choose-connection]

| Connection type | When to use |
|----------------|-------------|
| Pooled (-pooler hostname) | All bot runtime queries. Handles up to 10,000 concurrent clients; returns connections after each transaction. |
| Direct (no -pooler) | Migrations (`init_db()`), `CREATE INDEX CONCURRENTLY`, `LISTEN/NOTIFY` (none of these apply to bot runtime). |

In practice: `init_db()` runs `SCHEMA_SQL` (plain DDL, no prepared statements) via the pooled endpoint on startup. This works fine — PgBouncer in transaction mode only breaks prepared statements, not plain DDL. No separate direct connection needed for schema init.

**The pooled connection string from the Neon console (copy the one with `-pooler` in the host) is the DATABASE_URL that goes into Koyeb secrets.**

---

## Standard Stack

### Core (unchanged — no new packages)
| Library | Version | Purpose | Note |
|---------|---------|---------|------|
| asyncpg | 0.31.0 (pinned) | Postgres async driver | Pool params tuned for Neon (K-04) |
| aiohttp | transitive via discord.py | Minimal health endpoint for Koyeb WEB service | Already installed; no new dep |
| python:3.11-slim-bookworm | 3.11 | Base Docker image | Multi-arch; works on Koyeb amd64 |
| yt-dlp | pin to recent stable (K-15) | YouTube extraction | Pin version in requirements.txt |

### No Net-New pip Dependencies

The Koyeb+Neon re-target adds **zero new pip packages**. `aiohttp` is already a transitive discord.py dependency. The asyncpg tuning is parameter changes only. The health endpoint is ~10 lines using aiohttp's built-in web server.

### Package Legitimacy Audit

No new packages this phase. All existing packages (`asyncpg`, `discord.py`, `aiohttp`, `yt-dlp`, `google-genai`, etc.) were vetted in Phases 1-4. The only requirements.txt change is pinning a `yt-dlp` version — yt-dlp is a well-established package (official repo: github.com/yt-dlp/yt-dlp, millions of weekly downloads, verified legitimate).

---

## Net-New Code Integration Map

### 1. `bot.py` — create_pool call site (K-04 + K-05)

**Location:** `bot.py` line 223, `_initialize_once()` function.

**Current:**
```python
bot.pool = await asyncpg.create_pool(
    dsn=config.DATABASE_URL,
    min_size=config.DB_POOL_MIN,
    max_size=config.DB_POOL_MAX,
    command_timeout=30,
)
```

**Replace with:**
```python
bot.pool = await asyncpg.create_pool(
    dsn=config.sanitize_database_url(config.DATABASE_URL),
    min_size=config.DB_POOL_MIN,
    max_size=config.DB_POOL_MAX,
    command_timeout=30,
    ssl='require',
    max_inactive_connection_lifetime=240,
    statement_cache_size=0,
)
```

### 2. `config.py` — New constants + sanitizer (K-04 + K-05 + K-07)

Add below the Phase 4 DB block:

```python
# --- Phase 5: Neon pool tuning (K-04) ---
DB_MAX_INACTIVE_CONN_LIFETIME = 240   # recycle before Neon 5-min scale-to-zero
DB_STATEMENT_CACHE_SIZE = 0           # disable prepared stmts for PgBouncer tx-mode
AUDIO_CACHE_MAX_MB = 512              # lowered from 2048 for Koyeb 2GB ephemeral disk


def sanitize_database_url(dsn: str) -> str:
    """Strip asyncpg-incompatible query params from a Neon connection string.

    Neon's console DSN includes ?sslmode=require&channel_binding=require.
    asyncpg does not recognize channel_binding and may treat it as a Postgres
    GUC, causing an error. sslmode is handled via explicit ssl= kwarg in
    create_pool. Strips the entire query string; safe for non-Neon DSNs
    (no-op if no ? present).

    Pure function — fully unit-testable (K-05).
    """
    import re
    return re.sub(r'\?.*$', '', dsn)
```

Also update:
```python
DB_POOL_MAX = 5   # was 10; trimmed for Neon free single-worker (K-04)
```

### 3. `bot.py` — Minimal health endpoint (K-02 amendment)

Add before or alongside `_initialize_once()`. Runs as a concurrent asyncio task:

```python
from aiohttp import web as _aio_web

async def _run_health_server() -> None:
    """Minimal HTTP health check endpoint for Koyeb WEB service.

    Koyeb free tier requires a WEB service (not Worker) and performs HTTP
    health checks. Also enables UptimeRobot pings to prevent 1-hour sleep.
    Binds to 0.0.0.0 so Koyeb's health checker can reach it (not localhost).
    Returns the minimal {"status":"ok"} — no internal state exposed.
    """
    async def health(request: _aio_web.Request) -> _aio_web.Response:
        return _aio_web.Response(
            text='{"status":"ok"}',
            content_type='application/json',
        )

    app = _aio_web.Application()
    app.router.add_get('/health', health)
    runner = _aio_web.AppRunner(app)
    await runner.setup()
    site = _aio_web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()
    log.info("Health endpoint listening on 0.0.0.0:8000/health")
    # Runs indefinitely; caller is responsible for cancellation on shutdown.
```

Start it before `bot.run()` in `main()` using `asyncio.ensure_future` or `bot.loop.create_task`, or start it in `_initialize_once()` as a background task.

**Koyeb service config:** Health check type = HTTP, path = `/health`, port = 8000.

### 4. `utils/logger.py` — stdout confirmation (K-16)

**Current state (already adequate):** `utils/logger.py` has `logging.StreamHandler()` (writes to stderr by default). Koyeb captures both stdout and stderr in its log viewer. No functional change is required.

**Optional improvement:** Change to `logging.StreamHandler(sys.stdout)` to follow Docker log convention. Low priority — Koyeb captures stderr too.

**File handler:** `TimedRotatingFileHandler` writing to `/app/logs/dexter.log` still runs. Files are ephemeral (wiped on redeploy) but useful mid-session. No change needed.

### 5. `requirements.txt` — yt-dlp pin (K-15)

Add a pinned minimum version:
```
yt-dlp>=2025.6.9
```

(Planner: verify the latest stable version on PyPI at plan time and use that date. The daily 4am `ytdlp_update` task in `bot.py` continues to self-update after deploy.)

### 6. `Dockerfile` — comment cleanup (K-11/K-12)

Update line 1-4 to remove Oracle/arm64 references:

```dockerfile
# Dexter Discord bot image — multi-arch (amd64 on Koyeb/CI, arm64 on dev machines).
# Koyeb builds this Dockerfile directly from git (K-11); docker-compose.yml is local-dev only (K-12).
# Secrets injected at runtime via env vars — never baked into image layers (T-04-05).
FROM python:3.11-slim-bookworm
```

The rest of the Dockerfile is unchanged (ffmpeg install, pip install, CMD).

### 7. `scripts/` — Retirement (K-08 / K-09 / K-11)

See Oracle Script Disposition section below.

---

## Oracle Script Disposition

| Script | Disposition | Reason |
|--------|-------------|--------|
| `scripts/backup.sh` | **Retire** | OCI pg_dump cron. Neon-managed PITR replaces it. |
| `scripts/keepalive.sh` | **Retire** | Oracle idle-reclaim keepalive. UptimeRobot replaces outbound pings. |
| `scripts/deploy.sh` | **Retire** | Manual VM git-pull + compose rebuild. Koyeb git-auto-build (K-11) replaces. |
| `scripts/lifecycle-policy.json` | **Retire** | OCI Object Storage lifecycle rule. No OCI bucket. |
| `scripts/seed_restore_test.py` | **Keep (optional)** | Inserts roast-fuel rows for behavioral UAT. Planner's discretion: useful for PITR restore verification (insert rows, wait, restore to before-insertion point, verify rows gone). |

**Recommendation:** Move the four retired scripts to `scripts/archive/` (not deleted from git). Keeps history intact; removes them from active working tree.

---

## Runbook Re-Target Plan (K-18)

The existing `05-UAT-RUNBOOK.md` has sections A (Deploy + Boot), B (Infra checks), C (Behavioral), D (Destructive last).

### DROP (remove entirely)
- Oracle A1 / OCI-specific checks: `systemctl is-enabled docker`, `docker compose up -d` on VM, SSH to A1, OCI Object Storage verification, OCI lifecycle policy check.
- Host keepalive cron check (crontab entry).
- `pg_dump` backup cron confirmation.
- Manual `.env` on VM setup steps.
- `pg_isready -U dexter` on host.

### SWAP (re-word in place)
- "Postgres container healthy" → "Neon compute active (console shows running or auto-wakes on first query)"
- "Queue persists across `docker compose restart`" → "Queue restores from Neon on Koyeb redeploy (trigger manual Koyeb redeploy; verify queue reloads via /queue command)"
- "Host reboot survival" → "Koyeb restart + queue-restore-from-Neon survival (stop + restart Koyeb service; bot reconnects; /queue shows restored queue)"
- "Backup restore validated (`pg_restore`)" → "Neon PITR restore confirmed (Neon console branch-restore within 6-hour window; verify data integrity)"
- Any `docker compose exec` or `docker compose logs` command → Koyeb dashboard or `koyeb services logs <service>`

### ADD (new checks)
- **Koyeb deploy confirmation:** Service shows "Healthy" in Koyeb dashboard after first deploy.
- **Git auto-deploy:** Push a trivial commit to `gsd/phase-5-ship-it-live` → Koyeb auto-builds → service comes back up healthy.
- **Health endpoint alive:** `curl https://<service>.koyeb.app/health` returns `{"status":"ok"}`.
- **UptimeRobot active:** Monitor shows green; confirm it pinged `/health` at least once.
- **Neon scale-to-zero reconnect (K-17 #3):** Leave bot idle for 6+ minutes (no Discord commands) → run `/history` or `/play` → DB query succeeds, no crash, no SSL error in logs.
- **Neon PITR restore (DEPLOY-07 / K-17 #5):** Follow branch-restore procedure; verify data integrity post-restore (e.g. use seed rows to confirm restore point).
- **Koyeb log viewer:** `koyeb services logs <service>` or console shows bot startup logs including "Dexter is ready."
- **Healthchecks.io ping confirmed (DEPLOY-08 / K-09):** Healthchecks.io dashboard shows last ping within the expected interval.

### KEEP (unchanged)
- All Section C behavioral checks (9 Phase-3 + 6 Phase-4 Discord-side behaviors) — platform-agnostic.
- Section D destructive-last ordering (Neon PITR restore is the destructive test; stays last).
- Proven A→B→C→D ordered structure.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Connection pool recycling for serverless DB | Custom reconnect-on-error middleware | asyncpg `max_inactive_connection_lifetime` | Pool handles proactive eviction; retry-on-error is the fallback only |
| DSN parameter sanitization | Regex per-param surgery | Strip entire query string (`re.sub(r'\\?.*$', '', dsn)`) | Simpler, safe; all Neon query params are SSL/auth hints not needed by asyncpg |
| Keepalive / uptime monitoring | Custom ping server or OS cron | UptimeRobot free tier | Free, external, no code needed on the bot |

---

## Common Pitfalls

### Pitfall 1: channel_binding in DATABASE_URL crashes asyncpg
**What goes wrong:** User pastes Neon console connection string directly into Koyeb secret. asyncpg passes `channel_binding=require` as a Postgres GUC → PostgreSQL rejects it with `unrecognized configuration parameter "channel_binding"`.
**Why it happens:** `channel_binding` is a libpq-only parameter; asyncpg has its own SSL handling.
**How to avoid:** `sanitize_database_url()` in `config.py` strips all query string params at startup. Transparent to the user — they paste the raw Neon string and the code handles it.
**Warning signs:** `asyncpg.exceptions.PostgresError: unrecognized configuration parameter "channel_binding"` at bot startup.

### Pitfall 2: SSL-EOF after 5-minute Neon idle
**What goes wrong:** Bot quiet for >5 minutes → Neon suspends → next DB query hits dead pool connection → `asyncpg.exceptions.ConnectionFailureError` or `08006`.
**Why it happens:** Default `max_inactive_connection_lifetime=300` matches Neon's suspend timer exactly. Race window: under zero load the default is too slow.
**How to avoid:** `max_inactive_connection_lifetime=240` — asyncpg evicts at 4 min, before Neon's 5-min timer. Fresh connections wake a suspended compute (sub-second cold start).
**Warning signs:** Intermittent DB errors correlating with 5+ minute quiet periods in the logs.

### Pitfall 3: Prepared statement errors with PgBouncer
**What goes wrong:** `asyncpg.exceptions.InvalidSQLStatementNameError: prepared statement "..." does not exist` during normal operation.
**Why it happens:** asyncpg caches prepared statements per-connection; PgBouncer (transaction mode) reassigns connections between transactions, so the prepared statement doesn't exist on the newly assigned connection.
**How to avoid:** `statement_cache_size=0` in `create_pool` disables auto-caching.
**Warning signs:** Random `InvalidSQLStatementNameError` during concurrent commands.

### Pitfall 4: Koyeb WEB service sleeps after 1 hour
**What goes wrong:** No HTTP traffic for 1 hour → Koyeb scales to zero → Discord gateway drops → bot goes offline.
**Why it happens:** Koyeb free WEB services require inbound HTTP traffic to stay alive.
**How to avoid:** UptimeRobot pings `/health` every 5 minutes. Bot never idles from Koyeb's perspective.
**Warning signs:** Bot goes offline after ~1 hour of Discord inactivity. Koyeb dashboard shows "Sleeping."

### Pitfall 5: Health endpoint binds to localhost
**What goes wrong:** `TCPSite(runner, 'localhost', 8000)` → Koyeb health check can't connect → service marked unhealthy → restart loop.
**How to avoid:** Bind to `'0.0.0.0'` (all interfaces).
**Warning signs:** Koyeb shows repeated health check failures; service stuck in "Starting" or "Unhealthy."

### Pitfall 6: Local PC compose + Koyeb running simultaneously
**What goes wrong:** Two bot instances with the same token → gateway conflict → both disconnect in a loop.
**How to avoid:** K-14 rule — PC compose is break-glass only. Always stop PC before Koyeb goes live. Never run both.
**Warning signs:** Bot repeatedly connects then immediately disconnects in both logs.

### Pitfall 7: Neon 6-hour PITR window too narrow for UAT restore test
**What goes wrong:** PITR restore test has no meaningful history to restore to (bot hasn't run long enough, or no data was written).
**How to avoid:** Let the bot run with real Discord commands for at least 30 minutes before the PITR check. Use the seed script to insert synthetic history rows before testing the restore. Restore to 15+ minutes ago to confirm the seed rows appear/disappear as expected.
**Warning signs:** Neon console shows no restore points, or the earliest point is "now."

### Pitfall 8: Deploying to Koyeb on the wrong branch then merging
**What goes wrong:** UAT passes on `gsd/phase-5-ship-it-live`; user merges to `main` without re-pointing Koyeb to `main`. Koyeb continues deploying from the branch, not main.
**How to avoid:** After merge, update Koyeb service config to track `main` instead of the feature branch.
**Warning signs:** New commits to `main` don't trigger Koyeb builds; Koyeb still shows the old branch.

---

## Validation Architecture

> `workflow.nyquist_validation` not set to `false` in config — validation section required.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (existing, tests/ directory) |
| Quick run command | `pytest tests/test_config.py -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements to Test Map

| Req ID | Behavior to Test | Test Type | Automated Command | File Exists? |
|--------|-----------------|-----------|-------------------|-------------|
| K-05 | `sanitize_database_url("...?sslmode=require&channel_binding=require")` returns URL with no query string | unit | `pytest tests/test_config.py::test_sanitize_database_url -x` | No — Wave 0 gap |
| K-05 | `sanitize_database_url("postgresql://user:pass@host/db")` returns input unchanged (no-op) | unit | `pytest tests/test_config.py::test_sanitize_database_url_noop -x` | No — Wave 0 gap |
| K-05 | `sanitize_database_url("...?channel_binding=require&sslmode=require")` (reversed order) strips both | unit | `pytest tests/test_config.py::test_sanitize_database_url_reversed_params -x` | No — Wave 0 gap |
| K-04 | create_pool called with correct ssl, max_inactive_connection_lifetime, statement_cache_size | structural review | Boot + `grep` pool call diff | Inline review |
| K-02 amendment | `/health` returns 200 + `{"status":"ok"}` | structural review + boot | Boot + `curl localhost:8000/health` | Inline review |
| DEPLOY-01 | Bot holds 24/7 gateway on Koyeb | live-UAT-only | 05-UAT-RUNBOOK.md | Human observation |
| DEPLOY-02/03 | All behavioral UAT checks pass | live-UAT-only | 05-UAT-RUNBOOK.md | Human in Discord |
| DEPLOY-05 | Queue restores from Neon on Koyeb redeploy | live-UAT-only | Manual Koyeb redeploy + /queue check | Depends on Neon live |
| DEPLOY-07 | Neon PITR branch-restore succeeds + data verified | live-UAT-only | Neon console + /history check | Depends on Neon live + history |
| DEPLOY-08 | Healthchecks.io ping confirmed firing | live-UAT-only | Healthchecks.io dashboard | Human verification |

### Sampling Rate
- **Per task commit:** `pytest tests/test_config.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green + all live-UAT checks passing before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_config.py` — covers `sanitize_database_url` unit tests (3 cases above). **New file, must be created** in Wave 0.
- [ ] Confirm existing `tests/test_database.py` (streak logic etc.) still passes with asyncpg pool — should be unaffected by the pool param changes.

*(No other unit test gaps — all other phase work is platform integration or live-UAT.)*

---

## Environment Availability

> All accounts are user-created. Code changes can be written before accounts exist; deploy tasks are gated on account creation.

| Dependency | Required By | Available | Notes |
|------------|------------|-----------|-------|
| Koyeb account (free) | K-11 deploy | User must create | No credit card; fra1 or wdc1 region |
| Neon account (free) | K-03 database | User must create | No credit card; us-east-2 recommended |
| UptimeRobot account (free) | K-02 amendment keep-alive | User must create | Free tier: 50 monitors, 5-min interval |
| GitHub repo connected to Koyeb | K-11 git-auto-build | User must connect | Via Koyeb console app integration |
| Healthchecks.io account | K-09 dead-man | User should have | Free tier: 20 checks; pre-existing assumed |
| aiohttp (pip) | Health endpoint | Already installed | Transitive discord.py dep; add explicit entry to requirements.txt as safety |
| asyncpg 0.31.0 | DB pool | Already installed | Pinned in requirements.txt |
| ffmpeg | Audio | In Dockerfile | apt-get in Dockerfile; works on Koyeb amd64 |
| yt-dlp | YouTube | In requirements.txt | Pin version per K-15 |

**Missing with no fallback:**
- Neon account — required for all DB functionality; no workaround (local compose is break-glass, not a Koyeb substitute)

**Missing with fallback:**
- Koyeb: HeavenCloud or Wispbyte as K-10 runner swap
- UptimeRobot: any free HTTP monitor (Better Uptime, Freshping) as substitute

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No (Discord handles auth) | — |
| V3 Session Management | No | — |
| V4 Access Control | Partial (owner-only /sync) | Existing `bot.is_owner()` check unchanged |
| V5 Input Validation | Yes (DATABASE_URL sanitizer) | `sanitize_database_url` strips query params; no user input injected into DSN |
| V6 Cryptography | Yes (SSL to Neon) | `ssl='require'` in create_pool; never `ssl=False` or `ssl='disable'` |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| DSN / token in Koyeb build logs | Info Disclosure | Secrets set as Koyeb encrypted Secrets, not plain env vars; never in Dockerfile |
| Dockerfile ARG/ENV leaking secrets | Info Disclosure | All secrets injected at runtime via Koyeb env; no secrets in image layers (existing T-04-05 pattern) |
| Health endpoint exposing internal state | Info Disclosure | `/health` returns only `{"status":"ok"}` — no DB connection details, no version, no state |
| SQL injection via pool queries | Tampering | All queries use `$N` parameterized placeholders throughout database.py (existing V5 controls) |
| Gateway conflict (two bot instances) | Denial of Service | K-14: never run PC compose + Koyeb simultaneously |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | AUDIO_CACHE_MAX_MB=512 is safe given Koyeb 2GB disk (image estimated 600-900MB) | K-07 / Standard Stack | Disk full during session; cache eviction errors. Mitigation: UAT monitors disk; planner can set 256 as conservative alternative. |
| A2 | Washington D.C. region minimizes Discord voice latency for America/New_York community | Koyeb region pick | Marginally higher latency if wrong. Low risk; either US region acceptable. |
| A3 | aiohttp is already installed as a transitive discord.py dependency | Health endpoint | If not present, `import aiohttp.web` fails. Mitigation: add explicit `aiohttp` to requirements.txt. |
| A4 | Neon free tier signup requires no credit card | Research Directive 3 | User hits paywall. Mitigation: verify at https://neon.com before plan execution. |
| A5 | Koyeb free tier signup requires no credit card | Research Directive 2 | User hits paywall. Mitigation: verify at https://koyeb.com before plan execution. |
| A6 | yt-dlp pin version chosen by planner is the latest stable at plan time | K-15 / requirements.txt | Outdated pin; bot starts with old yt-dlp (self-heal still runs at 4am). Low risk. |
| A7 | asyncpg passes unrecognized DSN params as Postgres GUCs (causing error), not silently ignoring | Pitfall 1 / K-05 | If asyncpg silently ignores channel_binding, the sanitizer is precautionary only (harmless). Risk is only if sanitizer is NOT applied and asyncpg fails. |
| A8 | Koyeb free WEB service sleep is preventable via UptimeRobot pings | K-02 amendment | If Koyeb enforces mandatory sleep regardless of pings (e.g. at infrastructure level), K-10 runner swap to HeavenCloud/Wispbyte is triggered. This is exactly what K-10 guards against. |

---

## Open Questions (RESOLVED)

> All four resolved during planning (2026-06-15); resolutions are implemented in 05-01/05-02-PLAN.md.

1. **Does `aiohttp` need an explicit pin in requirements.txt?** — **RESOLVED:** yes, add `aiohttp>=3.9.0` (Plan 05-02).
   - What we know: It is a transitive dep of discord.py. Modern aiohttp includes `aiohttp.web`.
   - Recommendation: Add `aiohttp` (no pin) to requirements.txt as an explicit dep. Defensive against discord.py ever dropping it.

2. **Does the Neon cold start (~800ms) cause the first asyncpg pool acquire to time out?**
   - What we know: `command_timeout=30` in create_pool gives 30 seconds — more than adequate for an 800ms cold start.
   - Recommendation: No action needed. Document in UAT that the first DB query after a quiet period may take ~1 second.

3. **Should `sanitize_database_url` live in `config.py` or a new `utils/db_utils.py`?**
   - Recommendation: `config.py` — co-located with `DATABASE_URL`, consistent with the file's role as the single config source. No new file needed.

4. **Should the yt-dlp 4am task use `tzinfo=ZoneInfo(config.STREAK_TIMEZONE)` or stay at 4am UTC?**
   - CONTEXT.md marks this as "Claude's Discretion (carried low-stakes item)."
   - Recommendation: Leave at 4am UTC for now. The update time is a maintenance detail, not community-visible. Add the tzinfo in a future low-priority pass.

---

## Sources

### Primary (HIGH confidence)
- Context7 / magicstack.github.io/asyncpg/current — `create_pool` params confirmed: `max_inactive_connection_lifetime` (float, default 300), `statement_cache_size`, `ssl`, full list of recognized DSN parameters
- magicstack.github.io/asyncpg/current/faq.html — PgBouncer transaction mode + `statement_cache_size=0` fix [VERIFIED via WebFetch]
- magicstack.github.io/asyncpg/current/api/index.html — recognized DSN params; `channel_binding` not in list [VERIFIED via WebFetch]
- koyeb.com/docs/reference/instances — free tier specs (512MB RAM, 0.1 vCPU, 2GB SSD), Worker service restriction, 1-hour sleep, regions [VERIFIED via WebFetch]
- koyeb.com/docs/reference/secrets — secrets vs plain env vars, encrypted at rest [VERIFIED via WebFetch]
- neon.com/docs/introduction/plans — free tier: 100 CU-hours, 0.5GB storage, 5-min auto-suspend, 6-hour PITR window [CITED via WebFetch]
- neon.com/docs/connect/connection-pooling — pooled vs direct endpoint; PgBouncer transaction mode; -pooler hostname format [CITED via WebFetch]
- neon.com/docs/guides/branching-pitr — branch-based PITR restore procedure [CITED via WebFetch]
- neon.com/guides/building-resilient-applications-with-postgres — connection error codes on suspend (57P01, 08006, 08003) [CITED via WebFetch]

### Secondary (MEDIUM confidence)
- neon.com/docs/introduction/scale-to-zero — 5-minute auto-suspend; cold start ~300-800ms [CITED via WebFetch, partial content]
- neon.com/guides/fastapi-async — Neon connection string format confirms `channel_binding=require` present [CITED via WebFetch]
- koyeb.com/docs/build-and-deploy/build-from-git — Dockerfile build + git auto-deploy mechanism [CITED via WebFetch]
- koyeb.com/docs/faqs/pricing — free tier: one web service, Washington D.C. or Frankfurt [CITED via WebFetch]
- zenn.dev/saitogo/articles/e763dad351594f — working Discord bot on Koyeb free as WEB service with HTTP health endpoint + external keep-alive [CITED; community-verified]
- heavencloud.in/service/free-discord-bot-hosting — K-10 fallback: 715MB RAM, 1GB disk, 70% CPU, USA, no sleep, no credit card [CITED]
- wispbyte.com — K-10 fallback: free 24/7, Python, no credit card [CITED]

### Tertiary (LOW confidence — flagged)
- One WebSearch result summary claimed "Koyeb's free plan has no sleep mode" — this CONTRADICTS official docs. Official docs are authoritative: free WEB services DO scale-to-zero after 1h. The "no sleep" claim compares Koyeb to Render (Render sleeps at 15 min; Koyeb is 1h). UptimeRobot is still required.

---

## Metadata

**Confidence breakdown:**
- asyncpg params (max_inactive_connection_lifetime, statement_cache_size, ssl, channel_binding): HIGH — Context7 official docs, 555 snippets, High reputation; confirmed via FAQ and API reference WebFetch
- Koyeb free tier constraints (Worker restriction, specs, sleep): HIGH — official Koyeb instances docs confirmed via WebFetch
- Neon free tier specs + PITR: MEDIUM-HIGH — Neon docs fetched; some details required multiple fetches to compile
- Runner swap alternatives (HeavenCloud/Wispbyte): MEDIUM — official marketing pages; not externally stress-tested
- Audio cache sizing: LOW — heuristic image size estimate; verify actual image size in UAT

**Research date:** 2026-06-15
**Valid until:** 2026-07-15 for Koyeb/Neon free tier details (platforms change; re-verify if >30 days before executing)
