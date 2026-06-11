# Phase 4: Scale - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-12
**Phase:** 4-scale
**Areas discussed:** Scale target & limits, Hosting & deployment, Reclaim hedge, Deployment packaging, PostgreSQL migration, Queue persistence, Backup, Down-detection

---

## Framing — "what does 'scale' mean here?"

User opened by asking what "scale" actually means for this bot. Established: three axes (guild count, concurrency, durability); Discord only *requires* sharding at 2,500 guilds/connection, so `AutoShardedBot` runs 1 shard below that; and for a **music** bot the real ceilings are simultaneous audio streams (host CPU/bandwidth) + the free Gemini 15 RPM quota — neither fixed by sharding/Postgres. This reframed the phase as "durability + don't-fall-over," not "prepare for hundreds."

---

## Scale target & limits

| Option | Description | Selected |
|--------|-------------|----------|
| A few friends' servers | Tens of guilds, future-proofed but lean | ✓ |
| Mostly just my server, 24/7 | 1–2 guilds; scale = durability only | |
| Grow it publicly | Hundreds+ guilds, full hardening | |

**User's choice:** "a few friends' 5-10 servers"
**Notes:** Cascading implications confirmed (not separately asked): AutoShardedBot = 1 shard; Gemini stays global 15 RPM; modest per-guild queue cap; message-buffer TTL eviction; batch the per-`/play` commits; audio CPU/bandwidth doesn't bind at 1–3 streams → host chosen on reliability/cost.

---

## Hosting & deployment

| Option | Description | Selected |
|--------|-------------|----------|
| Cheap VPS (Hetzner) | ~€4–5/mo, rock-solid, you own it, local Postgres | |
| Oracle Cloud free tier | $0, Ampere ARM, but real reclaim/termination risk | ✓ |
| PaaS (Railway / Fly.io) | ~$5/mo, push-to-deploy, managed PG, rug-pull history | |
| Home box / Raspberry Pi | $0 if you have hardware, uptime tied to home | |

**User's choice:** "Oracle Cloud free tier"
**Notes:** $0 is the hard priority (back to the original CLAUDE.md target). Hetzner noted as the documented fallback ("might consider that … vps you mentioned if it starts to get annoying").

---

## Reclaim hedge (Oracle idle-reclaim + inactivity)

| Option | Description | Selected |
|--------|-------------|----------|
| Upgrade to Pay-As-You-Go | $0 within free limits but exempt from reclaim + inactivity | |
| Stay pure-free + keep-alive | No card; synthetic keep-busy task + periodic logins | ✓ |
| Accept risk, make redeploy instant | Don't fight it; lean on deploy automation | |

**User's choice:** "lets stay pure-free + keep alive. but i might consider going with that … vps you mentioned if it starts to get annoying"
**Notes:** Keep-alive to be a cron independent of the bot process. User accepts residual A1-capacity-crunch risk. Hetzner + PAYG both recorded as the escalation path.

---

## Deployment packaging

| Option | Description | Selected |
|--------|-------------|----------|
| Docker Compose | bot + Postgres containers, one-command rebuild on any host | ✓ |
| systemd + venv + apt Postgres | leanest, but least portable | |
| Bare + provision script | lean runtime, portability via setup.sh | |

**User's choice:** "Docker Compose"
**Notes:** Chosen for host-portability (Oracle reclaim recovery + Hetzner fallback). Postgres = local colocated container; persistent volumes for PG data + audio cache + logs; arm64 images.

---

## PostgreSQL migration — data

| Option | Description | Selected |
|--------|-------------|----------|
| Start fresh | New empty Postgres, no migration code | ✓ |
| Migrate existing data | One-time SQLite→PG export/import for 6 tables | |

**User's choice:** "Start fresh"
**Notes:** No real production data exists (local-boot only).

---

## PostgreSQL migration — scope

| Option | Description | Selected |
|--------|-------------|----------|
| Postgres only, everywhere | One dialect, dev/prod parity via local compose | ✓ |
| Dual: SQLite dev / PG prod | Frictionless Windows dev, but abstraction + drift risk | |

**User's choice:** "Postgres only, everywhere"
**Notes:** Rip out aiosqlite; tz-aware streak helpers carry over unchanged; `datetime('now')`/`AUTOINCREMENT`/`BOOLEAN 0`/`?` all retyped; PRAGMA-based streak migration deleted.

---

## Queue persistence — depth

| Option | Description | Selected |
|--------|-------------|----------|
| Queue + index + loop | Restore list/position/loop; current song replays from start | ✓ |
| ...plus mid-song position | Also resume exact second (elapsed tracking + FFmpeg seek) | |

**User's choice:** "Queue + index + loop"
**Notes:** Persist on every mutation (reclaim/crash won't fire shutdown hooks). Mid-song position deferred (overlaps parked position-save work).

---

## Queue persistence — restore behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Smart: rejoin if humans present | Rejoin+resume if old VC still has humans, else silent restore | ✓ |
| Silent restore, wait for a human | Never auto-join; picks up on next /play or /resume | |
| Always auto-rejoin + resume | Reconnect and play regardless (risks empty-channel audio) | |

**User's choice:** "Smart: rejoin if humans present"
**Notes:** Requires persisting the voice-channel id (not on MusicQueue today — read from voice_client at save). Distinct from the parked live voice-reconnect race.

---

## Backup (Postgres durability vs Oracle reclaim)

| Option | Description | Selected |
|--------|-------------|----------|
| Off-Oracle storage | pg_dump off-provider (repo/B2); survives account termination too | |
| Oracle Object Storage | pg_dump to free 20GB; survives instance reclaim, same account | ✓ |
| No backup, accept reset | Reclaim resets streaks/history; zero setup | |

**User's choice:** "Oracle Object Storage"
**Notes:** Survives instance reclaim; accepts that full account termination would also take it. DB is tiny "roast fuel."

---

## Down-detection / monitoring

| Option | Description | Selected |
|--------|-------------|----------|
| Dead-man's switch | Healthchecks.io-style; keep-alive cron pings it; unifies keep-alive + alerting | ✓ |
| Active HTTP pinger | UptimeRobot hits a health endpoint; needs inbound port | |
| None, notice manually | Find out when a friend complains | |

**User's choice:** "Dead-man's switch"
**Notes:** The keep-alive cron (D-09) doubles as the check-in ping — one mechanism, no inbound port.

---

## Claude's Discretion

- Exact config values (queue cap, buffer TTL, keep-alive/ping/backup intervals, pool size).
- Async Postgres driver (asyncpg vs psycopg3) + pool wiring.
- Schema-creation / migration tooling (minimal, since start-fresh).
- Queue-persistence storage shape (`jsonb` blob vs normalized rows).
- Keep-alive mechanism (synthetic CPU vs outbound network) — must double as the dead-man ping.

## Deferred Ideas

- Mid-song position resume on restart (overlaps parked position-save work).
- Pay-As-You-Go Oracle upgrade (reclaim-immunity hedge if pure-free gets annoying).
- Per-guild Gemini rate isolation (only matters at hundreds+ guilds).
- Off-provider backup (Backblaze/private repo) for account-termination durability.
- Active HTTP health endpoint + UptimeRobot.
- Persisting `auto_lyrics` / `lyrics_thread_id` across restart.
- Web config dashboard (PROJECT.md "maybe" only).
- Live voice-reconnect race (`cogs/music.py:~609`) — stays parked for live `/gsd:debug`.
