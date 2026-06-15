# Phase 5: Ship It Live - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

> **Two sessions.** The current **re-target session (2026-06-15, Koyeb + Neon)** is first; the
> original **Oracle-target session (2026-06-12)** is preserved below it as superseded history.

---

# ═══ Re-target session — Koyeb + Neon (2026-06-15) ═══

**Date:** 2026-06-15
**Phase:** 05-ship-it-live
**Areas discussed:** Audio cache, Backups under Neon, Deploy & branch strategy, Uptime & runner-swap, Connection-string handling, Neon pooler, Definition of done, Runbook re-targeting, Redeploy control, Secrets layout, yt-dlp pinning, Logging, Local fallback coexistence, Neon data (fresh vs migrate)

> Context: Phase 5 was already executed against Oracle A1 (code done, reviewed, verified human_needed
> on branch `gsd/phase-5-ship-it-live`). Oracle was abandoned (no card + A1 capacity + networking).
> This session re-targets the same goal to **Koyeb (WORKER) + Neon (free Postgres)**. Every question
> below resolved on the recommended option.

---

## Audio cache strategy (Koyeb ~512MB RAM + ephemeral disk)

| Option | Description | Selected |
|--------|-------------|----------|
| Shrink cap, keep cache | Keep download-first; drop `AUDIO_CACHE_MAX_MB` to 256–512MB. Disk playback = low CPU. | ✓ |
| Stream-only, no cache | No download; stream from yt-dlp. More stutter-prone on a low-spec box. | |
| Keep 2GB cap as-is | Risks filling the small ephemeral disk. | |

**User's choice:** Shrink cap, keep cache.
**Notes:** Best fit for the stated 512MB/low-CPU stutter worry; cold-on-redeploy accepted.

---

## Backups under Neon (no host cron on a worker)

| Option | Description | Selected |
|--------|-------------|----------|
| Neon managed only | Lean on Neon backups/PITR; retire `backup.sh` + OCI lifecycle. | ✓ |
| Neon + manual dump before risky ops | Routine managed + occasional manual `pg_dump`. | |
| External scheduled dump too | Off-Neon dump via PC/scheduler for full off-provider safety. | |

**User's choice:** Neon managed only.
**Notes:** D-15 restore-proof becomes a "Neon restore/branch works" UAT check.

---

## Deploy & branch strategy (Koyeb git-auto-build)

| Option | Description | Selected |
|--------|-------------|----------|
| Branch first, merge when live-green | Point Koyeb at `gsd/phase-5-ship-it-live`; UAT there; user merges → main once green. | ✓ |
| Merge to main now, deploy main | Merge reviewed branch immediately; UAT against main. | |
| Pre-built image deploy | Build+push image; deploy that (no git-build). | |

**User's choice:** Branch first, merge when live-green.
**Notes:** Matches "verified only when live passes"; Koyeb git-build retires `deploy.sh`.

---

## Uptime & runner-swap trigger

| Option | Description | Selected |
|--------|-------------|----------|
| Swap on stutter OR sleep | Jump to Wispbyte/HeavenCloud (same Neon DB) if CPU stutter OR Koyeb sleeps. | ✓ |
| Swap only on CPU stutter | Assumes Koyeb never sleeps. | |
| Fight sleep, stay on Koyeb | Add keepalive/self-ping to prevent scale-to-zero. | |

**User's choice:** Swap on stutter OR sleep.
**Notes:** Bot-side Healthchecks.io dead-man ping kept regardless. Researcher confirms whether Koyeb free workers sleep.

---

## Connection-string handling (`channel_binding` / `sslmode`)

| Option | Description | Selected |
|--------|-------------|----------|
| Sanitize in code at startup | Strip `channel_binding`, force `sslmode=require`, apply pooler flags before `create_pool`. Paste Neon's raw string. | ✓ |
| Clean by contract (pre-edit) | Hand-edit the Neon string before pasting into Koyeb. | |

**User's choice:** Sanitize in code at startup.
**Notes:** No footguns on credential rotation / runner swap.

---

## Neon pooler (PgBouncer transaction mode + asyncpg)

| Option | Description | Selected |
|--------|-------------|----------|
| Pooled + disable statement cache | Keep pooled string; `statement_cache_size=0`; trim `DB_POOL_MAX` (~5). | ✓ |
| Use Neon's direct endpoint instead | Full asyncpg features, ~100-conn cap, still scales to zero. | |
| Let researcher decide via context7 | Defer pooled-vs-direct to the doc check. | |

**User's choice:** Pooled + disable statement cache.
**Notes:** Researcher confirms exact asyncpg+Neon recipe via context7.

---

## Definition of done (live verification bar)

| Option | Description | Selected |
|--------|-------------|----------|
| Online + redeploy + scale-to-zero + UAT | 24/7 worker; redeploy auto-reconnect + queue-restore; survives scale-to-zero; behavioral UAT; Neon restore confirmed. | ✓ |
| Add an explicit multi-hour soak test | Above + 6–12h continuous-uptime observation as a gate. | |
| Minimal: online + behavioral UAT | Resilience treated as best-effort, not a gate. | |

**User's choice:** Online + redeploy + scale-to-zero + UAT.
**Notes:** Soak observed, not gated.

---

## Runbook re-targeting

| Option | Description | Selected |
|--------|-------------|----------|
| Surgical re-target in place | Edit `05-UAT-RUNBOOK.md`: drop Oracle/OCI/host-cron, swap Postgres→Neon, add Koyeb+Neon checks; keep ordering. | ✓ |
| Clean rewrite | Fresh Koyeb+Neon runbook; archive Oracle one. | |
| Existing + addendum | Leave Oracle runbook, add a delta section. | |

**User's choice:** Surgical re-target in place.
**Notes:** "Reboot survival" → "Koyeb restart + queue-restore-from-Neon survival."

---

## Redeploy control (Koyeb auto-deploy on push)

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-deploy, push deliberately | Accept auto-deploy; batch fixes. ~1000 IDENTIFY/day is ample. | ✓ |
| Manual deploy trigger | Disable auto-deploy; click Deploy when ready. | |
| Dedicated deploy branch | Koyeb tracks a branch you only push to deliberately. | |

**User's choice:** Auto-deploy, push deliberately.
**Notes:** Queue restores from Neon on each reconnect.

---

## Secrets layout (local `.env` vs Koyeb env)

| Option | Description | Selected |
|--------|-------------|----------|
| Same names; tokens as Koyeb secrets | Identical var names; tokens + DATABASE_URL as encrypted Koyeb secrets, IDs plain. | ✓ |
| All plain env vars | Everything as plain Koyeb env (tokens in plaintext). | |
| You decide | Claude picks the split. | |

**User's choice:** Same names; tokens as Koyeb secrets.
**Notes:** `DATABASE_URL` is the only value differing between envs.

---

## yt-dlp pinning (ephemeral container)

| Option | Description | Selected |
|--------|-------------|----------|
| Pin recent + keep runtime self-heal | Pin known-good `yt-dlp` in requirements + keep daily/on-failure update. | ✓ |
| Unpinned (latest at each build) | Always newest at build; risk a bad release with no pin fallback. | |
| Pin only, drop runtime update | Update only by redeploy. | |

**User's choice:** Pin recent + keep runtime self-heal.

---

## Logging (ephemeral `/app/logs`)

| Option | Description | Selected |
|--------|-------------|----------|
| Stdout + Koyeb viewer + Discord channel | Stream to stdout; Discord error channel for alerts; files best-effort. | ✓ |
| Add external log drain | Ship logs to a free external sink. | |
| Keep file logs, accept loss | Files reset each redeploy; lean on Discord channel. | |

**User's choice:** Stdout + Koyeb viewer + Discord channel.
**Notes:** May need a small stdout-handler tweak in `utils/logger`.

---

## Local fallback coexistence (PC compose vs Koyeb)

| Option | Description | Selected |
|--------|-------------|----------|
| Koyeb sole prod; PC = break-glass on local PG | Run PC only when Koyeb is down; never both (token conflict); PC stays on local PG. | ✓ |
| PC fallback also points at Neon | Unified data; fallback dies if Neon is the outage. | |
| Separate token for the PC fallback | Distinct bot identity; avoids conflict; more to manage. | |

**User's choice:** Koyeb sole prod; PC = break-glass on local PG.
**Notes:** Break-glass data divergence accepted (low-stakes roast-fuel).

---

## Neon data (fresh vs migrate)

| Option | Description | Selected |
|--------|-------------|----------|
| Start Neon fresh | `init_db()` auto-creates schema; no migration. | ✓ |
| Migrate local PC data into Neon | `pg_dump` local → restore into Neon before go-live. | |

**User's choice:** Start Neon fresh.
**Notes:** PC local data treated as dev/test; real history accumulates from go-live.

---

## Claude's Discretion (re-target session)

- Exact `AUDIO_CACHE_MAX_MB` value (256 vs 512), pending Koyeb free disk size.
- Exact `yt-dlp` pin version; Koyeb region (recommend US-East); stdout log-handler specifics.
- Whether `bot.py` yt-dlp loop keeps 4am-UTC or gets `tzinfo` (carried low-stakes).
- New `config.py` Neon/pool/cache constants; whether to keep the optional seed script.

## Deferred Ideas (re-target session)

- HTTP health endpoint / WEB service (Phase-8 Ops); migrating PC data to Neon; multi-hour soak as a gate;
  off-Neon/off-provider backup; GHCR/pre-built-image deploy; log-shipping stack.
- Oracle-specific items now moot: PAYG reclaim-immunity upgrade, OCI bucket/lifecycle ops.
- Carried from Phase 4: Redis (→ Phase 6), mid-song resume, per-guild Gemini isolation, persist auto_lyrics.

---
---

# ═══ Original session — Oracle A1 target (2026-06-12, SUPERSEDED) ═══

> Preserved for audit. The deploy/backup/keepalive decisions below were superseded by the
> Koyeb + Neon re-target above (CONTEXT.md K-01). The code-fix decisions (reconnect race, TZ,
> clear_persisted, per-guild sync) carried forward unchanged.

**Date:** 2026-06-12
**Phase:** 5-ship-it-live
**Areas discussed:** Labor split & deliverables, Reconnect race (DEPLOY-04), Live-UAT runbook, Backup/restore proof, Secrets-on-host, Command sync, Deploy-failure recovery, Dead-man alert routing, Code update workflow (CI/CD), Timezone correctness, Backup cadence/retention, Prod log visibility, (+ Redis — raised, deferred)

User asked for a recommendation on every area; recommendations were given and accepted in all cases.

---

## Labor split & deliverables

| Option | Description | Selected |
|--------|-------------|----------|
| Runbook + fixes + scripts | 2 (→3) code fixes + one consolidated deploy+UAT runbook + helper scripts; moderate Oracle/Docker familiarity assumed; user runs live, capture via verify-work | ✓ |
| Add OCI click-throughs | Same, but with step-by-step OCI console walkthroughs | |
| Code fixes only | Just the code fixes; user handles deploy from own knowledge | |

**User's choice:** Runbook + fixes + scripts
**Notes:** Phase verified when the live checklist passes, not when code lands.

---

## Reconnect race (DEPLOY-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Defensive fix now + verify | Harden provable invariants by inspection (is_connected guards, generation ordering, rejoin awaits connection), verify live, escalate to /gsd:debug if it still races | ✓ |
| Hold for live repro | Touch nothing until reproduced in a live /gsd:debug session | |
| Full rewrite now | Complete rewrite of the reconnect/rejoin path from inspection | |

**User's choice:** Defensive fix now + verify
**Notes:** User added "log it in case it still races" → instrument the path with diagnostic logging so a live race leaves a trail for /gsd:debug. Resolves the tension with the project's "don't fix blind" rule. *(Carried forward → CONTEXT.md P-01.)*

---

## Live-UAT runbook (DEPLOY-02/03)

| Option | Description | Selected |
|--------|-------------|----------|
| One ordered runbook | Consolidate all 21 checks (deploy→cron→behavioral→destructive last), de-dup overlap, command+expected+capture each, source docs by reference; per-guild sync during UAT | ✓ |
| Keep 3 docs separate | Update 03/04-VERIFICATION + 04-HUMAN-UAT in place | |
| Consolidated + global sync | One runbook but global command sync from the start | |

**User's choice:** One ordered runbook *(re-targeted → CONTEXT.md K-18.)*

---

## Backup/restore proof (DEPLOY-07)

| Option | Description | Selected |
|--------|-------------|----------|
| Seed → scratch-DB restore | Seed known rows → backup.sh → restore into throwaway dexter_restore_test → verify counts/values; non-destructive; Claude writes seed + verify scripts | ✓ |
| Destructive round-trip | Restore over the live DB | |
| Just confirm upload | Only verify a .dump lands in the bucket | |

**User's choice:** Seed → scratch-DB restore *(superseded → Neon-managed backups, CONTEXT.md K-08.)*

---

## Secrets-on-host

| Option | Description | Selected |
|--------|-------------|----------|
| Manual .env + oci/pgpass | Manual .env (chmod 600) + ~/.oci/config + ~/.pgpass; no secret manager | ✓ |
| Secret manager / OCI Vault | Store secrets in OCI Vault, pull at runtime | |
| Off-box deploy script | Bake secrets into a private off-box provisioning script | |

**User's choice:** Manual .env + oci/pgpass *(superseded → Koyeb secrets, CONTEXT.md K-13.)*

---

## Command sync (first deploy)

| Option | Description | Selected |
|--------|-------------|----------|
| Per-guild (single community) | Sync per-guild to the one community guild (+ optional test guild); global deferred | ✓ |
| Global now | Global sync from the start (~1hr propagation) | |
| Both (test then global) | Per-guild during UAT, then global for final state | |

**User's choice:** Per-guild (single community) *(carried forward → CONTEXT.md P-04.)*

---

## Deploy-failure recovery

| Option | Description | Selected |
|--------|-------------|----------|
| Troubleshoot + fix-forward | Troubleshooting table + fix-forward (down && up --build); tagged-image rollback noted as a later redeploy practice | ✓ |
| Build rollback now | Tagged last-good images + documented rollback this phase | |
| Happy-path only | Just the working runbook; debug ad hoc | |

**User's choice:** Troubleshoot + fix-forward *(superseded → Koyeb redeploy/rollback, CONTEXT.md K-11.)*

---

## Dead-man alert routing (DEPLOY-08)

| Option | Description | Selected |
|--------|-------------|----------|
| Discord + email | Webhook into the error-log channel + email backup | ✓ |
| Email only | Just email | |
| Phone push | Pushover/ntfy paging | |

**User's choice:** Discord + email *(carried forward → CONTEXT.md K-09.)*

---

## Code update workflow (CI/CD)

| Option | Description | Selected |
|--------|-------------|----------|
| Git-pull + rebuild (deploy.sh) | Manual git pull → docker compose up -d --build bot → tail logs → ping healthcheck; DB volume untouched; GHCR pipeline + rollback deferred with a trigger; full auto-CD deferred indefinitely | ✓ |
| GHCR image pipeline now | GitHub Actions builds arm64 → GHCR; host pulls; enables tagged rollback | |
| Full auto-deploy now | Actions builds AND deploys to Oracle on merge (SSH/pull-agent) | |

**User's choice:** Git-pull + rebuild (deploy.sh)
**Notes:** *(superseded → Koyeb git-auto-build is the now-free CI/CD, CONTEXT.md K-11; deploy.sh retired.)*

---

## Timezone correctness

| Option | Description | Selected |
|--------|-------------|----------|
| Make code TZ-explicit | events.py:197 → ZoneInfo(STREAK_TIMEZONE); bot.py:467 → tzinfo (or accept 4am-UTC); set VM tz too; correct regardless of host | ✓ |
| Just set VM timezone | Set VM tz only — half-fix (yt-dlp loop is UTC-anchored per discord.py) | |
| Leave UTC | No change; late-night roasts fire at wrong local hour | |

**User's choice:** Make code TZ-explicit
**Notes:** discord.py official docs confirmed (via Context7): naive `tasks.loop(time=)` is assumed UTC, while `datetime.now()` is host-local. *(Carried forward → CONTEXT.md P-03.)*

---

## Backup cadence + retention (DEPLOY-07)

| Option | Description | Selected |
|--------|-------------|----------|
| Every 6h + 14d lifecycle | pg_dump every 6h + OCI lifecycle rule deletes dumps >14 days | ✓ |
| Keep */30 + prune | Every 30 min (as scripts document) + retention prune | |
| Daily + retention | Once a day + retention | |

**User's choice:** Every 6h + 14d lifecycle *(superseded → Neon-managed, CONTEXT.md K-08.)*

---

## Prod log visibility

| Option | Description | Selected |
|--------|-------------|----------|
| docker logs + Discord errors | docker compose logs -f bot + confirm ERROR_LOG_CHANNEL_ID set in prod + volume files on demand; no shipping stack | ✓ |
| Add Loki/Grafana stack | Centralized log-shipping + dashboard | |
| Files-only | docker exec / volume files; no Discord error channel | |

**User's choice:** docker logs + Discord errors *(re-targeted → Koyeb log viewer + Discord, CONTEXT.md K-16.)*

---

## Claude's Discretion (Oracle session)

- Exact runbook location/structure; reconnect-path log verbosity/format; seed-data shape; Healthchecks.io setup specifics.
- OCI bucket/region prereqs; exact reboot-test wording; crontab env wiring.
- Whether `bot.py:467` yt-dlp loop gets `tzinfo` or stays 4am-UTC (low-stakes).
- Reboot survival confirmed already handled in code (`restart: unless-stopped` + named volumes) — runbook just checks `systemctl is-enabled docker`.
- DEPLOY-06 `clear_persisted` fix accepted as a clear-cut 2-line change (mirror the `/stop` path).

## Deferred Ideas (Oracle session)

- **Redis / new caching layer** — raised by the user; redirected to Phase 6 (resolution cache) at most; revisit only if Dexter goes multi-node.
- **GHCR image pipeline + tagged-image rollback** — deferred with trigger (redeploys get frequent).
- **Full auto-CD** (build+deploy on merge) — deferred indefinitely (security/ops surface).
- **Log-shipping/dashboard stack** — rejected; docker logs + Discord error channel suffices.
- Carried from Phase 4: mid-song resume, Pay-As-You-Go Oracle, per-guild Gemini isolation, off-provider backup.
