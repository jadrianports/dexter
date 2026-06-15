# Phase 5: Ship It Live - Context

**Gathered:** 2026-06-12 (Oracle target) · **Re-targeted:** 2026-06-15 (Koyeb + Neon)
**Status:** Ready for replanning

> **This is a re-target, not a new phase.** Phase 5's goal is unchanged — take Dexter
> from code-complete to **running 24/7 in production, with every v1.0 behavior validated
> live**. What changed is the **substrate**: Oracle A1 ARM → **Koyeb WORKER service**, and
> colocated Docker Postgres → **Neon serverless Postgres**. The original Oracle was abandoned
> (no credit card, A1 capacity lottery, networking hell). The three code fixes, helper scripts,
> and consolidated runbook already executed on branch `gsd/phase-5-ship-it-live` still stand;
> this pivot supersedes the Oracle **deploy/backup/keepalive** decisions only. The existing
> `05-01/02/03-PLAN.md` are Oracle-shaped and **must be replanned** for the new target.

<domain>
## Phase Boundary

Phase 5 takes Dexter from **proven-in-local-Docker** (running right now on the Windows PC —
Dexter#2172, Postgres healthy, 17 commands synced) to **running 24/7 for real on free,
no-credit-card infra**, with every v1.0 behavior and the deploy/restart/restore mechanism
validated in production.

Concretely, after the pivot this phase delivers:
- **DB-layer code wiring** (the only material net-new code): asyncpg pool tuned for Neon's
  pooled endpoint + 5-min scale-to-zero, and a startup-time `DATABASE_URL` sanitizer. See K-03…K-06.
- **Koyeb deployment config** — the repo deployed as a WORKER, git-auto-built from the Dockerfile.
- **A re-targeted live-UAT runbook** — surgical edit of `05-UAT-RUNBOOK.md` from Oracle → Koyeb+Neon.
- **Retirement/adaptation of the Oracle ops scripts** (`backup.sh`, `keepalive.sh`, `deploy.sh`,
  OCI lifecycle, pg_dump restore-verify) — replaced by Neon-managed backups + Koyeb git-deploy.

**The asymmetry that shapes this phase (unchanged):** only the user can create the Neon/Koyeb
accounts, paste secrets, and drive live Discord. Claude produces the code wiring + deploy config +
re-targeted runbook (everything **ready-to-deploy**); the user executes the live steps and reports
back via `/gsd:verify-work`. **The phase is verified when the live checklist passes on Koyeb+Neon
(K-17), not when code lands.**

**The fallback that bounds risk:** the local PC Docker stack remains a **break-glass** instance —
never run alongside Koyeb on the same Discord token (gateway conflict). See K-14.

**Out of scope (clarifies, does not expand):** the **rich** health endpoint with metrics/bot-state
(OPS-02) stays future Phase-8 Ops — *only the minimal `{"status":"ok"}` deploy-prereq endpoint is in
scope here (K-02 amended, forced by Koyeb free = WEB-only)*; migrating the PC's local DB into Neon
(start fresh, K-06); a multi-hour soak as a *gate* (observed, not gated, K-17); any Phase 6/7/8
feature work. Swapping the *runner* (Koyeb → Wispbyte/HeavenCloud) is in scope **as a contingency**
(K-10), not a parallel deploy.
</domain>

<decisions>
## Implementation Decisions

> **Numbering:** `K-##` = new/changed by the Koyeb+Neon pivot (2026-06-15).
> `P-##` = **preserved** from the original Oracle CONTEXT, unchanged and already on the branch.

### Pivot framing — what supersedes Oracle
- **K-01:** Deploy substrate pivots **Oracle A1 ARM → Koyeb WORKER + Neon serverless Postgres**.
  This **supersedes** the prior Oracle-specific decisions: reboot-survival via `systemctl`,
  manual `.env` on a VM, host git-pull `deploy.sh`, 6h `pg_dump`→OCI cron + OCI lifecycle, and
  the OCI Object-Storage restore proof. **Preserved unchanged:** the 3 code fixes (P-01…P-03),
  per-guild sync (P-04), the `$0/mo` hard constraint, single-community target, and the
  consolidated-runbook *approach* (re-targeted, not rebuilt — K-18).

### Hosting — Koyeb worker
- **K-02 [AMENDED 2026-06-15 after research]:** Deploy as a Koyeb **WEB** service. *(Original intent
  was a WORKER with no HTTP port, but the Koyeb free tier does NOT offer Worker services — verified
  koyeb.com/docs/reference/instances, "They can't be used as Worker Services". Free = WEB only.)*
  Add a **minimal aiohttp `/health` endpoint** (returns `{"status":"ok"}` on `0.0.0.0:8000`, no
  internal state) to satisfy Koyeb's HTTP health check, **plus a free external HTTP pinger**
  (UptimeRobot/Freshping, ~5-min interval) to defeat Koyeb free's **1-hour idle scale-to-zero**.
  This minimal endpoint is a **deploy prerequisite, NOT** the rich metrics/state health endpoint
  (OPS-02) — that stays **deferred to Phase-8 Ops**. Koyeb auto-restarts the service on crash.
  Region: Claude's discretion, recommend **US-East (Washington D.C. / `wdc1`)** to match the
  `America/New_York` community + low Discord latency; provision Neon in `us-east-2` to co-locate.
  K-10 (HeavenCloud/Wispbyte runner-swap) remains the fallback if the pinger can't hold 24/7 or the
  0.1 vCPU stutters.

### Database — Neon
- **K-03:** **Neon free serverless Postgres, pooled (PgBouncer) connection endpoint.**
- **K-04:** asyncpg pool tuning for Neon (researcher **MUST context7 the exact asyncpg+Neon recipe**
  to confirm params/syntax):
  - `max_inactive_connection_lifetime` **< 300s** (e.g. 240s) — recycles connections before Neon's
    5-min idle **scale-to-zero**, avoiding the **SSL EOF** error on reused dead connections.
  - `statement_cache_size=0` — Neon's pooled endpoint runs PgBouncer in **transaction mode**, which
    breaks asyncpg's default prepared statements; disabling the statement cache is the fix.
  - Trim `DB_POOL_MAX` (~5) — single small worker; the pool need not be large.
- **K-05:** **Sanitize `DATABASE_URL` in code at startup** (in `config.py`/`database.py` before
  `create_pool`): strip `channel_binding=require` (asyncpg can't parse it), force `sslmode=require`,
  apply the pooler flags. Lets the user paste Neon's **raw** string into Koyeb verbatim — no
  hand-editing, survives credential rotation.
- **K-06:** **Neon starts fresh.** `init_db()` auto-creates the schema on first connect; **no
  migration** of the PC's local Postgres (treated as dev/test roast-fuel). Real community history
  accumulates from go-live — matches the original start-fresh assumption.

### Audio cache — ephemeral, low-spec worker
- **K-07:** **Keep download-first caching, shrink the cap.** Drop `AUDIO_CACHE_MAX_MB` to a
  disk-safe value (target **~256–512MB**; exact value Claude's discretion pending Koyeb free disk
  size — researcher to confirm). Plays from disk = **opus copy, low CPU** → best fit for the
  ~512MB-RAM / low-CPU **stutter** concern. Cache goes **cold on redeploy** (ephemeral disk) and
  re-warms within a session — accepted. **NOT stream-only** (network-FFmpeg is more stutter-prone).

### Backups — Neon-managed
- **K-08:** **Neon managed backups / PITR only.** A Koyeb worker has no host cron, so the Oracle
  6h `pg_dump`→Object-Storage job and the OCI lifecycle rule are **retired entirely**. The D-15
  restore-proof becomes a **UAT check** — "verify a Neon restore/branch recovers the data" — not a
  self-managed dump+restore script. (`scripts/backup.sh` retired; the seed script may be kept
  *optionally* to give behavioral UAT real roast-fuel — Claude's discretion.)

### Uptime, monitoring & runner-swap
- **K-09:** **Keep the bot-side Healthchecks.io dead-man ping** (`HEALTHCHECK_URL`, outbound +
  platform-agnostic — survives a runner swap). **Drop the Oracle host keepalive** (`scripts/keepalive.sh`
  idle-nudge — Koyeb-irrelevant). Dead-man **alert routing preserved** (prior D-12): Discord webhook
  into the error-log channel + email as an independent backup.
- **K-10:** **Runner-swap trigger = stutter OR sleep.** Swap the runner to **Wispbyte/HeavenCloud**
  (pointed at the **same Neon DB** — only the runner changes) if **either** music stutters (CPU)
  **or** Koyeb can't hold a 24/7 gateway connection (scale-to-zero/sleep). Uptime is the whole point,
  so either failure triggers the swap. **Researcher MUST confirm whether Koyeb free WORKER services
  scale-to-zero/sleep** — this gates whether the swap is needed at all.

### Deploy & branch flow
- **K-11:** **Koyeb git-driven auto-build** from the repo **Dockerfile**, tracking branch
  **`gsd/phase-5-ship-it-live`**. Run live UAT on the branch; once green, **the user merges → main**
  (user owns the merge) and re-points Koyeb at `main`. This is the free CI/CD that was deferred on
  Oracle — it **retires the manual `scripts/deploy.sh`**. **Auto-deploy-on-push accepted** (push
  deliberately / batch fixes; Discord's ~1000 IDENTIFY/day is ample; the queue restores from Neon on
  each reconnect via the existing smart-rejoin).
- **K-12:** **`docker-compose.yml` is the LOCAL-dev / break-glass config only** (local Postgres).
  Koyeb **ignores compose** and builds the `Dockerfile` directly. `DATABASE_URL` is the env switch
  between local-PG and Neon. (Working tree already partly de-Oracle'd — the arm64 `platform` pin was
  removed; uncommitted.)

### Secrets — two environments
- **K-13:** **Identical env-var names across both environments.** Local: `.env` (git-ignored) with
  the local-Postgres URL. Koyeb: `DISCORD_TOKEN` / `GEMINI_API_KEY` / `GENIUS_TOKEN` / `DATABASE_URL`
  as encrypted **Koyeb secrets**; channel + owner IDs as plain env vars. `DATABASE_URL` is the only
  value that differs between envs. No external secret manager.

### Local fallback coexistence
- **K-14:** **Koyeb is the sole normally-running prod.** The PC compose is **break-glass only** —
  fire it up **only** when Koyeb is confirmed down, stop it when Koyeb's back; **NEVER both at once**
  (same Discord token → gateway conflict / flapping). The PC stays on **local Postgres** so the
  fallback survives even a Neon outage. Break-glass data divergence is accepted (low-stakes roast-fuel).

### yt-dlp & logging — ephemeral container
- **K-15:** **yt-dlp: pin recent + keep runtime self-heal.** Pin a known-good recent `yt-dlp` in
  `requirements.txt` (each Koyeb redeploy starts from a solid base) **and** keep the existing
  daily-04:00 / on-failure runtime auto-update. Fresh base + self-heal between deploys.
- **K-16:** **Logs → stdout + Koyeb viewer + Discord error channel.** Ensure logging streams to
  stdout (Koyeb captures it in its log viewer/CLI); keep the Discord error-log channel for alerts;
  treat `/app/logs` files as **ephemeral/best-effort** (wiped each redeploy). No persistent log store
  (consistent with the rejected log-shipping stack). May need a small stdout-handler tweak in
  `utils/logger`.

### Definition of done — live verification bar (K-17)
- **K-17:** Phase 5 is **verified-live** when **all** hold:
  1. the bot holds a **24/7 Koyeb worker**;
  2. a **redeploy** auto-reconnects to Discord **and restores the queue from Neon**;
  3. the pool **survives Neon's 5-min idle scale-to-zero** with **no SSL-EOF crash**;
  4. **all behavioral UAT passes**;
  5. a **Neon restore is confirmed**.
  (A multi-hour soak is **observed, not gated**.)

### Runbook re-targeting (K-18)
- **K-18:** **Surgical re-target of `05-UAT-RUNBOOK.md` in place:**
  - **DROP:** OCI/Oracle/host-cron/backup-cron checks and `systemctl is-enabled docker`.
  - **SWAP:** every Postgres reference → Neon.
  - **ADD:** Koyeb worker-alive + git-deploy + Neon **scale-to-zero-reconnect** + Neon-**restore** checks.
  - **KEEP** the proven ordered structure: deploy/boot → infra → behavioral (Discord) → destructive **last**.
  - **"Reboot survival" check → "Koyeb restart + queue-restore-from-Neon survival."**

### Preserved code-fix decisions (already on `gsd/phase-5-ship-it-live`, unchanged by pivot)
- **P-01 (was D-02…D-04, DEPLOY-04):** reconnect-race **defensive fix by inspection** + diagnostic
  instrumentation. Live-verify under Koyeb; escalate to a live `/gsd:debug` **only if it still races**.
- **P-02 (was D-05, DEPLOY-06):** `clear_persisted()` at idle-leave (`bot.py:399`) + reconnect-failure
  (`cogs/music.py:1206`), mirroring the `/stop` template — closes the ghost-queue-on-restart bug.
- **P-03 (was D-06):** TZ-correct late-night roast via `ZoneInfo(STREAK_TIMEZONE)` at `cogs/events.py:197`.
- **P-04 (was D-08):** **Per-guild command sync** to the community guild (`--first-run --guild` / owner
  `/sync`) — instant; global sync still deferred.

### Claude's Discretion
- Exact `AUDIO_CACHE_MAX_MB` value (256 vs 512), pending Koyeb free disk size.
- Exact `yt-dlp` pin version in `requirements.txt`.
- Koyeb region pick (recommend US-East).
- stdout log-handler implementation specifics in `utils/logger`.
- Whether the `bot.py` yt-dlp `tasks.loop` keeps 4am-UTC or gets `tzinfo` (carried low-stakes item).
- New `config.py` constants for Neon/pool/cache settings — consistent with existing constant patterns.
- Whether to keep the seed script (optional roast-fuel for behavioral UAT) now that backups are Neon-managed.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements / project decisions
- `.planning/ROADMAP.md` §"Phase 5: Ship It Live" — goal + success criteria (re-interpret for Koyeb+Neon).
- `.planning/REQUIREMENTS.md` — **DEPLOY-01…08** (the testable statements; re-map the Oracle-specific
  ones to Koyeb+Neon — backup/cron checks become Neon-managed, host-reboot becomes Koyeb-restart).
- `.planning/PROJECT.md` — Key Decisions & Constraints. ⚠ **Its "Hosting → Oracle A1" decision is now
  SUPERSEDED by K-01** (Koyeb+Neon) — PROJECT.md will need an evolution update at phase/milestone transition.
- `.planning/STATE.md` — Deferred Items + Blockers (the Oracle reclamation risk is now moot; the parked
  reconnect race → DEPLOY-04 / P-01 still stands).

### Research directives this phase opens (researcher MUST fetch current docs)
- **asyncpg + Neon connection recipe** — `mcp__context7__*` (asyncpg `create_pool`,
  `max_inactive_connection_lifetime`, `statement_cache_size`, `ssl`) — confirm K-04/K-05 syntax.
- **Koyeb WORKER services** — does the free tier scale-to-zero/sleep? build-from-Dockerfile + git
  auto-deploy + secrets + env vars + free instance specs (RAM/disk/CPU). Gates K-07, K-10, K-11.
- **Neon free tier** — scale-to-zero behavior + managed backup/PITR/branch restore (gates K-08, K-17),
  pooled vs direct endpoint semantics.

### Prior context — code fixes built here, deploy substrate now changed
- `.planning/phases/04-scale/04-CONTEXT.md` — queue persistence + smart-rejoin (D-18…D-22, the
  restore-from-DB mechanism that now restores from **Neon**), and the parked reconnect race (D-22 →
  P-01). ⚠ Its Oracle/colocated-Postgres deploy decisions (D-07/D-10…D-14) are **superseded by K-01**.
- `.planning/phases/03-alive/03-CONTEXT.md` — `STREAK_TIMEZONE` (relevant to P-03 TZ fix).

### Standing UAT / verification checklists (the source for the re-targeted runbook, K-18)
- `.planning/phases/05-ship-it-live/05-UAT-RUNBOOK.md` — **the doc K-18 surgically re-targets.**
- `.planning/phases/05-ship-it-live/05-HUMAN-UAT.md` — the live items captured for `/gsd:verify-work`.
- `.planning/phases/04-scale/04-VERIFICATION.md` — IN-02 (→ P-02) + WR-03 (→ P-01) origins.
- `.planning/phases/03-alive/03-VERIFICATION.md` — the 9 behavioral checks + the `cogs/events.py:197`
  naive-time anti-pattern (→ P-03).

### Build spec / codebase maps
- `CLAUDE.md` — Background Tasks, Edge Cases (disconnect/reconnect), Logging, Implementation Gotchas
  (Postgres + deploy pitfalls; "never `voice_client.stop()` before `_play_track()`" → P-01).
- `.planning/codebase/INTEGRATIONS.md`, `ARCHITECTURE.md`, `STACK.md`, `CONCERNS.md` — ⚠ dated; treat
  Postgres (now **Neon**) as current truth.

### Infra files (this phase retires/adapts under the pivot)
- `docker-compose.yml` — now **local-dev/break-glass only** (K-12); Koyeb builds the Dockerfile.
- `Dockerfile` — `python:3.11-slim-bookworm` + ffmpeg; **Koyeb's git-auto-build target** (K-11).
  Note: drop arm64 assumptions (Koyeb is x86).
- `scripts/backup.sh`, `scripts/keepalive.sh`, `scripts/deploy.sh`, `scripts/lifecycle-policy.json`,
  `scripts/seed_restore_test.py` — **retired/adapted** (K-08/K-09/K-11/K-18).
- `.env.example` — env-var template (the K-13 secrets contract; update for `DATABASE_URL`=Neon).

### Code integration targets (this phase modifies)
- `database.py` — `init_db(pool)` seam; the **`create_pool` call site** (find it — likely `bot.py`)
  gets K-04/K-05 tuning + URL sanitizing.
- `config.py` — `DATABASE_URL` (89), `DB_POOL_MAX` (91), `AUDIO_CACHE_MAX_MB` (22), `HEALTHCHECK_URL`
  (100); add Neon/pool/cache constants.
- `requirements.txt` — pin `yt-dlp` (K-15).
- `utils/logger.py` — ensure stdout streaming (K-16).
- (P-01…P-03 code targets already modified on the branch.)
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`init_db(pool)` + `asyncpg` pool** — `database.py:127`; `init_db` takes an already-created pool,
  so the Neon tuning (K-04) + URL sanitizing (K-05) land at the **`create_pool` call site** (find it,
  likely `bot.py`). The schema (`SCHEMA_SQL`) is plain DDL and unchanged.
- **`get_local_date` / `compute_streak` + `ZoneInfo(STREAK_TIMEZONE)`** — `database.py:19-59`; the
  already-tz-aware seam (P-03 extends the same pattern in `cogs/events.py`).
- **Queue persistence + smart-rejoin** (`services/queue_persistence.py`, `guild_queues` table) — the
  restore-on-restart mechanism that now restores from **Neon** on every Koyeb redeploy (K-11, K-17).
- **Healthchecks.io dead-man ping** (`HEALTHCHECK_URL`) — bot-side outbound; keep as-is (K-09).
- **`docker-compose.yml` + `Dockerfile`** — compose demoted to local-only (K-12); Dockerfile becomes
  Koyeb's build target (K-11).
- **The 3 code fixes (P-01…P-03)** — already committed on `gsd/phase-5-ship-it-live`; reviewed (7 fixed).

### Established Patterns
- **Testing convention** (PROJECT.md): pure logic → TDD; Discord/process/infra → structural review +
  clean boot. The **`DATABASE_URL` sanitizer (K-05)** is pure/testable (parse → cleaned URL); the
  asyncpg tuning + Koyeb deploy are live-UAT-only.
- **`config.py` single-file constants + `.env` secrets** — add Neon/pool/cache settings as needed.
- **Gemini-first with template fallback** — unchanged; behavioral UAT only.

### Integration Points
- DB tuning + URL sanitize → `create_pool` call site + `config.py`/`database.py`.
- Cache cap → `config.AUDIO_CACHE_MAX_MB` (22).
- Logging → `utils/logger` stdout handler.
- Deploy/validate → Koyeb (Dockerfile build) + Neon + the re-targeted runbook.
</code_context>

<specifics>
## Specific Ideas

- **`$0/mo`, no-credit-card is the hard constraint** that drove the whole pivot (Oracle needed a card +
  lost the A1 lottery). Koyeb free + Neon free both satisfy it. Every K-decision preserves it.
- **The bot is proven working right now** in local Docker (Dexter#2172, Postgres healthy, 17 commands
  synced) — that's the break-glass baseline (K-14) and de-risks "does the image even run."
- **asyncpg + Neon pooled endpoint** has two well-known gotchas the user pre-identified: SSL-EOF on
  reused connections after scale-to-zero (→ `max_inactive_connection_lifetime` < 300s) and
  `channel_binding=require` being unparseable (→ strip it). PgBouncer transaction-mode + prepared
  statements is the third (→ `statement_cache_size=0`). All three are **K-04/K-05**; researcher
  confirms exact syntax via context7.
- **`STREAK_TIMEZONE = "America/New_York"`** — the community is US Eastern; informs the Koyeb region pick.
- **Koyeb git-auto-build is the CI/CD that was deferred on Oracle** — the pivot turns a deferred idea
  into a free built-in (K-11), retiring `deploy.sh`.
</specifics>

<deferred>
## Deferred Ideas

- **RICH HTTP health endpoint (metrics / bot-state, OPS-02)** — stays **Phase-8 Ops** scope. *(The
  minimal `{"status":"ok"}` endpoint is now IN scope as a Koyeb-WEB deploy prerequisite — K-02
  amended 2026-06-15 after research found Koyeb free offers no Worker services. UptimeRobot/Freshping
  as the external keep-alive pinger is also newly in scope under K-02.)*
- **Migrating the PC's local Postgres into Neon** — considered, decided against (K-06, start fresh).
  Revisit only if real accumulated history on the PC turns out to be worth preserving.
- **Multi-hour soak test as a gate** — observed, not gated (K-17). Promote to a gate later if uptime
  proves flaky.
- **Off-Neon / off-provider backup** (e.g. GitHub Actions cron `pg_dump`) — rejected for now (K-08,
  Neon-managed is enough for roast-fuel). Revisit if the data becomes valuable.
- **GHCR image pipeline / pre-built-image deploy** — Koyeb git-build (K-11) covers the need; a
  pre-built-image path is the upgrade if build times or registry control ever matter.
- **Log-shipping / dashboard stack** — still rejected (K-16); Koyeb log viewer + Discord channel suffice.
- **(Carried from Phase 4, still deferred):** Redis (→ Phase 6 at most); mid-song position resume on
  restart; per-guild Gemini rate isolation; persisting `auto_lyrics`/`lyrics_thread_id` across restart.
- **Oracle-specific deferred items now MOOT:** Pay-As-You-Go Oracle reclaim-immunity upgrade; OCI
  bucket/lifecycle ops — dropped with the platform.

*All discussion stayed within the deploy-and-validate phase scope. The substrate pivot (Oracle→Koyeb+Neon)
re-targets the same Phase-5 goal; it does not add new product capability.*
</deferred>

---

*Phase: 5-ship-it-live*
*Context gathered: 2026-06-12 (Oracle) · Re-targeted: 2026-06-15 (Koyeb + Neon)*
