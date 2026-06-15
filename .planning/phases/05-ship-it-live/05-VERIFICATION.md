---
phase: 05-ship-it-live
verified: 2026-06-15T00:00:00Z
status: human_needed
score: 7/7 code-level must-haves verified
overrides_applied: 0
human_verification:
  - test: "A1 — Koyeb deploy healthy"
    expected: "Koyeb dashboard shows service Healthy; Koyeb logs show 'Dexter is ready.' and startup personality message posts to DEXTER_CHANNEL_ID"
    why_human: "Requires creating Koyeb account, pasting secrets, and triggering a live deploy — cannot be run from dev host"
  - test: "A2 — Koyeb restart + queue-restore-from-Neon survival"
    expected: "Service auto-restarts after manual restart/redeploy; /queue shows queue restored from Neon guild_queues (K-17 #2)"
    why_human: "Requires live Koyeb service and live Neon DB"
  - test: "A3 — Over-cap /play rejection"
    expected: "With MAX_QUEUE_SIZE_PER_GUILD=1 set via Koyeb env var + redeploy, second /play returns personality cap rejection"
    why_human: "Requires live Koyeb service and Discord interaction"
  - test: "A4 — UptimeRobot + Healthchecks.io confirmed active"
    expected: "UptimeRobot shows Dexter health monitor green; Healthchecks.io shows Dexter Keepalive green within its window (DEPLOY-08)"
    why_human: "Requires live service accounts and external HTTP monitors"
  - test: "A5 — Health endpoint alive (curl)"
    expected: "curl https://<service>.koyeb.app/health returns HTTP 200 with body {\"status\":\"ok\"}"
    why_human: "Requires live Koyeb public URL — endpoint is coded and verified structurally but cannot be curled from dev host"
  - test: "A6 — Git auto-deploy"
    expected: "Push a trivial commit to gsd/phase-5-ship-it-live; Koyeb detects push, builds, returns Healthy with no manual step (K-11)"
    why_human: "Requires live Koyeb service tracking the branch"
  - test: "A7 — Postgres integration tests against Neon"
    expected: "pytest tests/test_database_phase4.py -x exits 0 (18 tests) with DATABASE_URL pointed at a Neon branch/throwaway DB"
    why_human: "Requires live Neon endpoint; test_database_phase4.py errors on Windows dev host (no live Postgres)"
  - test: "B1 — Queue persistence round-trip (Koyeb redeploy)"
    expected: "After /play + Koyeb redeploy, /queue shows queue restored from Neon guild_queues; smart-rejoin reconnects only when non-bot human is present (DEPLOY-05)"
    why_human: "Requires live Koyeb + Neon + Discord"
  - test: "B2 — clear_persisted on idle-leave (DEPLOY-06 / P-02)"
    expected: "Bot idles alone 10+ min, auto-leaves, Koyeb restart yields empty /queue (not restored) — confirming P-02 fix at runtime"
    why_human: "Requires 10+ min live Discord/Koyeb session"
  - test: "B3 — Neon scale-to-zero reconnect (K-17 #3)"
    expected: "After 6+ min idle (Neon suspends), /history or /play succeeds with no SSL-EOF/08006/channel_binding error in Koyeb logs"
    why_human: "Requires live Neon scale-to-zero to trigger (5+ min idle) and live Koyeb log inspection"
  - test: "C1 — Voice join roast"
    expected: "Join voice 4-5 times; at least one Gemini-personalized roast appears; template fallback on rate-limit"
    why_human: "Discord live session required"
  - test: "C2 — Late-night roast TZ fix (P-03 live observation)"
    expected: "Late-night roast fires 1-5am America/New_York (not UTC), confirming ZoneInfo fix from P-03 is live"
    why_human: "Requires live Discord at late-night ET hours (or events.py patch)"
  - test: "C3 — Startup message"
    expected: "Koyeb restart/redeploy posts a personality startup message to DEXTER_CHANNEL_ID within ~30s"
    why_human: "Requires live Koyeb service and Discord"
  - test: "C4 — Status rotation"
    expected: "Bot presence cycles through current song / server-count / random line / seasonal over 10-15 min"
    why_human: "Requires 10-15 min live Discord observation"
  - test: "C5 — /lyrics command"
    expected: "After /play on a song with Genius lyrics, /lyrics returns paginated embed; Prev/Next buttons work; disable after 3 min timeout"
    why_human: "Requires live Discord session with GENIUS_TOKEN set"
  - test: "C6 — /history command"
    expected: "/history returns paginated embed of recent songs (title, artist, requester, date); Prev/Next buttons work"
    why_human: "Requires live Discord session with queued songs"
  - test: "C7 — Message reactions"
    expected: "YouTube URL -> 👀; gn/goodnight -> 🫡; bare bot mention -> 😐; mention + 'thanks' -> deflecting text reply"
    why_human: "Requires live Discord message events"
  - test: "C8 — Repeat-song roast"
    expected: "Queuing same song 3 times in one day unconditionally fires a roast"
    why_human: "Requires live Discord session across song plays"
  - test: "C9 — Idle loneliness"
    expected: "After 30+ min no commands with humans in voice, bot posts exactly one idle loneliness message"
    why_human: "Requires 30+ min live Discord session"
  - test: "C10 — Streak and milestone roasts"
    expected: "Streak milestones (7/14/30/60/100 days) and song-count milestones (100/250/500/1000) fire correctly"
    why_human: "Requires consecutive live sessions or threshold manipulation"
  - test: "C11 — DEPLOY-04 reconnect race (live observation)"
    expected: "Live reconnect event shows INFO diagnostic log trail in Koyeb logs; playback resumes if P-01 fix is effective"
    why_human: "Requires live voice disconnect/reconnect and Koyeb log inspection"
  - test: "D1 — Neon PITR restore proof (DEPLOY-07 / K-17 #5)"
    expected: "PITR restore via Neon console succeeds; backup branch auto-created; asyncpg pool reconnects automatically; /history confirms data integrity post-restore"
    why_human: "Requires live Neon console, destructive operation — run LAST after A/B/C pass"
---

# Phase 5: Ship It Live — Verification Report

**Phase Goal:** Dexter is running 24/7 on a free Koyeb WEB service backed by Neon serverless Postgres, and every v1.0 behavioral and deploy check has been validated live (K-17)
**Verified:** 2026-06-15
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Summary

All **7 code-level must-haves** from Plans 01-03 are VERIFIED. The code deliverables are complete and correct:

- Neon DB wiring (sanitizer + pool tuning + health endpoint) — Plan 01
- Deploy packaging (pins, Dockerfile, stdout logging, Oracle scripts archived, deploy doc) — Plan 02
- UAT runbook re-targeted to Koyeb+Neon in place — Plan 03
- Pre-existing code fixes P-01..P-04 confirmed present in codebase

The phase cannot be PASSED from this dev host because **K-17 requires live execution** of the 22-check `05-UAT-RUNBOOK.md` on the actual Koyeb+Neon deployment. Those 22 checks — all of which involve live Discord, live Koyeb, and/or live Neon operations — are listed in the Human Verification Required section below.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | sanitize_database_url strips Neon query string (channel_binding/sslmode) before asyncpg sees it (K-05) | VERIFIED | `config.py:107-119` — pure function; `tests/test_config.py` 6/6 pass (3 class methods + 3 flat aliases); `python -c "import config; print(config.sanitize_database_url(...))"` returns bare DSN |
| 2 | create_pool runs with ssl='require', max_inactive_connection_lifetime=240, statement_cache_size=0, max_size=5 (K-04) | VERIFIED | `bot.py:253-261` — all 4 kwargs present at create_pool call site, each referencing its config constant; AST check passes |
| 3 | Minimal GET /health endpoint answers on 0.0.0.0:8000 (K-02 amended) | VERIFIED | `bot.py:181-204` — `_run_health_server()` defined; binds `'0.0.0.0'` port 8000; returns `{"status":"ok"}`; launched via `asyncio.ensure_future` after background tasks in `_initialize_once` (`bot.py:320`) |
| 4 | init_db() creates schema on fresh Neon with no migration (K-06) | VERIFIED | Schema unchanged (SCHEMA_SQL in database.py); init_db(pool) is the existing idempotent DDL runner — no code change needed and none made |
| 5 | AUDIO_CACHE_MAX_MB is 512 (K-07); yt-dlp floor-pinned; aiohttp explicit dep; stdout logging; Dockerfile de-Oracle'd; Oracle scripts archived | VERIFIED | `config.py:22` = 512; `requirements.txt` has `yt-dlp>=2026.06.09` and `aiohttp>=3.9.0`; `utils/logger.py:42` = `StreamHandler(sys.stdout)`; Dockerfile header = Koyeb comment, no arm64v8/Oracle A1; `scripts/archive/` contains backup.sh, keepalive.sh, deploy.sh, lifecycle-policy.json; `scripts/backup.sh` absent from scripts/ root |
| 6 | UAT runbook re-targeted: no Oracle/OCI/systemctl/pg_dump remnants; Koyeb+Neon+UptimeRobot+PITR+scale-to-zero checks added; Group C 11 behavioral checks preserved; verified-live bar updated (K-18) | VERIFIED | All automated string-gate checks pass (banned terms absent; required terms present; Group C count ≥11; session summary updated to 22 checks on Koyeb+Neon per K-17) |
| 7 | P-01..P-04 code fixes present: reconnect-race guard (music.py), clear_persisted at idle-leave (bot.py:441) and reconnect-failure (music.py:1214), ZoneInfo TZ fix (events.py:197), /sync command | VERIFIED | `cogs/music.py:1199-1214` reconnect retry with _play_generation guard and clear_persisted; `bot.py:441` idle_check fires clear_persisted; `cogs/events.py:197-198` uses ZoneInfo(STREAK_TIMEZONE); `bot.py:393-410` /sync owner command |

**Score:** 7/7 code-level truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `config.py` | sanitize_database_url() + Neon pool constants + cache cap | VERIFIED | `def sanitize_database_url` at line 107; `DB_MAX_INACTIVE_CONN_LIFETIME=240`, `DB_STATEMENT_CACHE_SIZE=0` at lines 103-104; `DB_POOL_MAX=5` at line 91; `AUDIO_CACHE_MAX_MB=512` at line 22 |
| `tests/test_config.py` | Wave-0 unit tests for sanitize_database_url (3+3 cases) | VERIFIED | 6 tests pass (3 class methods + 3 flat-name aliases); imports `from config import sanitize_database_url` |
| `bot.py` | Tuned create_pool call + _run_health_server() background task | VERIFIED | create_pool at lines 253-261 with all 4 Neon kwargs; `_run_health_server` at lines 181-204; launched at line 320 |
| `requirements.txt` | yt-dlp floor pin + explicit aiohttp | VERIFIED | `yt-dlp>=2026.06.09` (line 2); `aiohttp>=3.9.0` (line 13); `asyncpg==0.31.0` intact |
| `Dockerfile` | De-Oracle'd header; Koyeb-targeted; unchanged build steps | VERIFIED | Header comment says "Koyeb builds this Dockerfile directly"; no arm64v8 or Oracle A1 references; `FROM python:3.11-slim-bookworm` (1 occurrence); build steps unchanged |
| `utils/logger.py` | stdout StreamHandler | VERIFIED | `import sys` at line 5; `StreamHandler(sys.stdout)` at line 42 |
| `docs/DEPLOY-KOYEB.md` | Koyeb+Neon+UptimeRobot deploy contract | VERIFIED | Contains Neon, WEB service, /health, UptimeRobot, us-east-2, wdc1, K-14 break-glass, K-10 runner-swap |
| `.env.example` | K-13 secrets contract (both environments; no real secrets) | VERIFIED | All 9 required vars present; DATABASE_URL references Neon for Koyeb; no real secrets in file |
| `scripts/archive/backup.sh` | Retired Oracle script preserved in git | VERIFIED | File exists at scripts/archive/backup.sh; absent from scripts/ root |
| `scripts/archive/keepalive.sh` | Retired Oracle script preserved | VERIFIED | Present in archive |
| `scripts/archive/deploy.sh` | Retired Oracle script preserved | VERIFIED | Present in archive |
| `scripts/archive/lifecycle-policy.json` | Retired OCI lifecycle rule preserved | VERIFIED | Present in archive |
| `scripts/seed_restore_test.py` | Kept in place (optional Neon PITR roast-fuel) | VERIFIED | File exists at scripts/seed_restore_test.py |
| `.planning/phases/05-ship-it-live/05-UAT-RUNBOOK.md` | Re-targeted Koyeb+Neon live-UAT runbook | VERIFIED | Contains "Neon PITR", "scale-to-zero", "Koyeb", no Oracle remnants; 22 total checks; version 2.0 (Koyeb+Neon) |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| bot.py create_pool | config.sanitize_database_url | dsn=config.sanitize_database_url(config.DATABASE_URL) | WIRED | bot.py:254 |
| bot.py create_pool | config.DB_MAX_INACTIVE_CONN_LIFETIME | max_inactive_connection_lifetime=config.DB_MAX_INACTIVE_CONN_LIFETIME | WIRED | bot.py:259 |
| bot.py create_pool | config.DB_STATEMENT_CACHE_SIZE | statement_cache_size=config.DB_STATEMENT_CACHE_SIZE | WIRED | bot.py:260 |
| bot.py _initialize_once | _run_health_server | asyncio.ensure_future(_run_health_server()) | WIRED | bot.py:320 |
| docs/DEPLOY-KOYEB.md | bot.py /health endpoint | references path /health port 8000 | WIRED | DEPLOY-KOYEB.md Section 3 |
| 05-UAT-RUNBOOK.md health check | bot.py /health endpoint | curl https://<service>.koyeb.app/health | WIRED | Runbook A5 |
| 05-UAT-RUNBOOK.md prerequisites | docs/DEPLOY-KOYEB.md | "See docs/DEPLOY-KOYEB.md for full deploy contract" | WIRED | Runbook Prerequisites section |
| Dockerfile | requirements.txt | pip install -r requirements.txt | WIRED | Dockerfile line 15 |

---

### Behavioral Spot-Checks

Step 7b: Runnable checks on this dev host (no live services required):

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| sanitize_database_url strips Neon params | `python -c "import config; print(config.sanitize_database_url('postgresql://u:p@h/d?sslmode=require&channel_binding=require'))"` | `postgresql://u:p@h/d` | PASS |
| config constants have correct Neon values | `python -c "import config; print(config.DB_MAX_INACTIVE_CONN_LIFETIME, config.DB_STATEMENT_CACHE_SIZE, config.DB_POOL_MAX, config.AUDIO_CACHE_MAX_MB)"` | `240 0 5 512` | PASS |
| bot.py parses (no syntax error) | `python -c "import ast; ast.parse(open('bot.py').read()); print('OK')"` | `bot.py parses OK` | PASS |
| Wave-0 unit tests pass | `python -m pytest tests/test_config.py tests/test_streak.py -q` | `18 passed, 1 warning in 0.07s` | PASS |
| bot.py structural assertions (health server + ssl + stmt_cache + 0.0.0.0 + ensure_future) | AST + source grep check | All assertions pass | PASS |
| Packaging assertions (yt-dlp pin, aiohttp, Dockerfile, stdout handler) | Source content check | All assertions pass | PASS |
| Oracle scripts archived | Filesystem checks | All 4 in archive/, none in scripts/ root | PASS |
| UAT runbook Oracle-ban assertions | String search | No Oracle/OCI/systemctl/.pgpass/pg_dump remnants | PASS |

Step 7b live-service checks: SKIPPED — cannot boot bot, hit Neon, or curl Koyeb from Windows dev host. These are captured in the human verification list.

---

### Probe Execution

Step 7c: No probe-*.sh scripts declared or conventional. SKIPPED.

---

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|---------------|-------------|--------|----------|
| DEPLOY-01 | 05-01, 05-02, 05-03 | Dexter runs 24/7 on Koyeb (re-targeted from Oracle A1) via Docker image, surviving a Koyeb restart | PARTIAL — code wired; live pending | Neon pool tuning + sanitizer + health endpoint coded (bot.py, config.py); UAT runbook A1/A2/A5/B3 carry live verification |
| DEPLOY-02 | 05-03 | The 9 Phase-3 behavioral + Phase-4 deploy-equivalent checks executed and passing | DEFERRED TO LIVE UAT | UAT runbook Group A (infra) + Group C (C1-C11 behavioral) carry all checks |
| DEPLOY-03 | 05-03 | The human-UAT scenarios executed and passing | DEFERRED TO LIVE UAT | UAT runbook Group A/B carries Phase-4 equivalent checks; Group C carries behavioral scenarios |
| DEPLOY-04 | 05-01 (P-01 preserved) | Voice playback survives a reconnect without race/double-play | VERIFIED in code | cogs/music.py:1199-1214 — reconnect retry with _play_generation guard, diagnostic logging, clear_persisted on failure |
| DEPLOY-05 | 05-03 | Queue + playback survive a bot restart (persistence + smart-rejoin live) | DEFERRED TO LIVE UAT | UAT runbook B1 — code exists (queue_persistence.py, restore_queues); live redeploy verification needed |
| DEPLOY-06 | 05-01 (P-02 preserved) | clear_persisted fires on idle-leave and reconnect-failure | VERIFIED in code | bot.py:441 idle_check + music.py:1214 reconnect-failure both call clear_persisted() |
| DEPLOY-07 | 05-03 | pg_dump backup runs + restore validated (re-targeted: Neon PITR restore confirmed) | DEFERRED TO LIVE UAT | UAT runbook D1 — Neon PITR console restore procedure, runs LAST |
| DEPLOY-08 | 05-02, 05-03 | Keepalive / dead-man cron confirmed firing in production (re-targeted: UptimeRobot + Healthchecks.io) | DEFERRED TO LIVE UAT | UAT runbook A4 — UptimeRobot monitor green + Healthchecks.io dead-man ping confirmed |

**Note on REQUIREMENTS.md Oracle wording:** REQUIREMENTS.md still uses Oracle A1 phrasing for DEPLOY-01 ("Oracle A1 via Docker Compose") and DEPLOY-07 ("pg_dump backup"). These are superseded by K-01 (Oracle→Koyeb+Neon pivot) documented in 05-CONTEXT.md. The re-targeted equivalents are verified above. REQUIREMENTS.md itself is not updated in this phase (PROJECT.md update deferred to phase/milestone transition per 05-CONTEXT.md canonical_refs note).

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No TBD/FIXME/XXX markers found in phase-05 modified files | — | None |

Scan covered: `config.py`, `bot.py`, `utils/logger.py`, `requirements.txt`, `Dockerfile`, `.env.example`, `docs/DEPLOY-KOYEB.md`, `tests/test_config.py`.

---

### Human Verification Required

The phase's definition of done is K-17: the bot must hold a 24/7 Koyeb worker, survive a redeploy with queue-restore from Neon, survive Neon's 5-min idle scale-to-zero, pass all behavioral UAT, and confirm a Neon PITR restore. All 22 checks in `05-UAT-RUNBOOK.md` (version 2.0, Koyeb+Neon) require live accounts and live Discord interaction.

**Run `.planning/phases/05-ship-it-live/05-UAT-RUNBOOK.md` in order (A → B → C → D). Complete Prerequisites Checklist first.**

#### Setup (Prerequisites)

**Test:** Create Neon project (us-east-2, pooled connection string), Koyeb WEB service (Dockerfile build, gsd/phase-5-ship-it-live branch, wdc1, /health:8000), encrypted secrets + plain env vars per K-13, UptimeRobot monitor, Healthchecks.io dead-man check
**Expected:** All services created and live; Koyeb service builds from git and shows Healthy
**Why human:** Requires creating accounts, pasting secrets, and triggering a live deploy

#### 1. A1 — Koyeb deploy healthy

**Test:** Confirm Koyeb dashboard shows Healthy after first deploy; bot posts startup message to DEXTER_CHANNEL_ID
**Expected:** Service Healthy; "Dexter is ready." in Koyeb logs; personality startup message in Discord
**Why human:** Live Koyeb deploy required

#### 2. A2 — Koyeb restart + queue-restore-from-Neon (DEPLOY-05)

**Test:** Trigger a Koyeb restart/redeploy; after service returns Healthy, run /queue
**Expected:** Queue restored from Neon guild_queues; smart-rejoin reconnects voice only when a non-bot human remains
**Why human:** Live Koyeb + Neon + Discord required

#### 3. A3 — Over-cap /play rejection

**Test:** Add MAX_QUEUE_SIZE_PER_GUILD=1 in Koyeb env vars + redeploy; try /play twice
**Expected:** Second /play returns personality cap rejection; restore to 500 after
**Why human:** Live Koyeb env var and Discord interaction required

#### 4. A4 — UptimeRobot + Healthchecks.io active (DEPLOY-08)

**Test:** Check UptimeRobot dashboard for Dexter health monitor; check Healthchecks.io for Dexter Keepalive check
**Expected:** Both monitors show green with recent timestamps; Discord error-log channel shows UP notification from Healthchecks.io
**Why human:** Requires live external monitoring services running for at least one interval

#### 5. A5 — Health endpoint alive (curl)

**Test:** `curl https://<service>.koyeb.app/health`
**Expected:** HTTP 200; body `{"status":"ok"}`
**Why human:** Requires live Koyeb public URL; endpoint is structurally verified in code but cannot be curled from dev host

#### 6. A6 — Git auto-deploy (K-11)

**Test:** Push a trivial commit to gsd/phase-5-ship-it-live; observe Koyeb dashboard
**Expected:** Koyeb auto-builds and returns Healthy with no manual deploy step
**Why human:** Requires live Koyeb service with git-auto-build configured

#### 7. A7 — Postgres integration tests against Neon

**Test:** With DATABASE_URL set to a Neon branch or throwaway DB, run `pytest tests/test_database_phase4.py -x`
**Expected:** 18 tests pass (TestPostgresSchema, TestBatchTransaction, TestHelpers); confirms K-04/K-05 pool tuning against live Neon
**Why human:** Requires live Neon endpoint

#### 8. B1 — Queue persistence round-trip (DEPLOY-05)

**Test:** /play a song; trigger Koyeb redeploy; run /queue after service returns
**Expected:** Queue restored from Neon; smart-rejoin reconnects voice if human present
**Why human:** Live Koyeb + Neon + Discord session required

#### 9. B2 — clear_persisted on idle-leave (DEPLOY-06, P-02 runtime confirmation)

**Test:** Bot idles alone 10+ min; auto-leaves; trigger Koyeb restart; run /queue
**Expected:** /queue is EMPTY (not restored) — confirms P-02 clear_persisted fired at runtime
**Why human:** Requires 10+ min live Discord session

#### 10. B3 — Neon scale-to-zero reconnect (K-17 #3)

**Test:** Leave bot idle 6+ min (no Discord commands); then run /history or /play
**Expected:** DB query succeeds; no SSL-EOF/08006/channel_binding error in Koyeb logs; confirms K-04/K-05 pool config live
**Why human:** Requires live Neon scale-to-zero to trigger and Koyeb log inspection

#### 11-21. C1-C11 — Behavioral checks (Group C)

**Tests:** Voice join roast (C1), late-night TZ roast at 1-5am ET not UTC (C2/P-03), startup message (C3), status rotation over 10-15 min (C4), /lyrics pagination (C5), /history pagination (C6), message reactions (C7), repeat-song roast (C8), idle loneliness after 30 min (C9), streak/milestone roasts (C10), reconnect race diagnostic log trail (C11/P-01)
**Expected:** All 11 behavioral checks fire as designed; P-03 TZ fix confirms 1-5am ET (not UTC); P-01 reconnect logs visible
**Why human:** All require live Discord session; C2 requires specific time-of-day or code patch; C11 requires intentional disconnect/reconnect

#### 22. D1 — Neon PITR restore proof (DEPLOY-07, K-17 #5) — RUN LAST

**Test:** Seed rows (optional: python scripts/seed_restore_test.py); note timestamp; Neon console PITR restore to a point within the 6-hour window; verify backup branch auto-created; verify asyncpg reconnects; /history shows data consistent with restore point
**Expected:** Restore succeeds; Neon creates {branch}_old_{ts} backup branch; bot DB queries work post-restore; /history data matches restore timestamp
**Why human:** Live Neon console operation; destructive — run only after A/B/C pass

---

### Gaps Summary

No code-level gaps. All 7 code-level must-haves from Plans 01-03 are verified as CORRECT and WIRED.

The only remaining work is the live-UAT gate (K-17): 22 checks in `05-UAT-RUNBOOK.md` that require live Koyeb + Neon + Discord. These are user-only steps by design (K-17, phase asymmetry documented in 05-CONTEXT.md).

**DEPLOY-01 partial note:** The requirement's wording in REQUIREMENTS.md ("Oracle A1 via Docker Compose") is superseded by the K-01 pivot (Koyeb + Neon). The Koyeb-targeted code wiring is complete. The "runs 24/7 surviving restart" clause requires live UAT (A1/A2).

**DEPLOY-07 partial note:** The requirement's wording ("pg_dump backup + restore validated") is superseded by K-08 (Neon-managed PITR). The Neon PITR restore proof is D1 in the runbook, pending live execution.

---

## REQUIREMENTS.md Traceability Note

The REQUIREMENTS.md traceability table marks DEPLOY-01/02/03/05/07/08 as "Pending" and DEPLOY-04/06 as "Complete." This matches the current state: DEPLOY-04 (reconnect race) and DEPLOY-06 (clear_persisted) are code-complete and verified; the remaining six require live UAT execution. Once the user completes `05-UAT-RUNBOOK.md` and reports via `/gsd-verify-work`, those requirements can be marked complete.

---

*Verified: 2026-06-15*
*Verifier: Claude (gsd-verifier)*
