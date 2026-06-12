---
phase: 05-ship-it-live
verified: 2026-06-12T00:00:00Z
status: human_needed
score: 5/5 code-side must-haves verified (live UAT pending)
overrides_applied: 0
human_verification:
  - test: "A1. Docker clean boot on Oracle A1"
    expected: "docker compose up -d brings up Postgres (healthcheck healthy) and bot; bot posts startup message to Discord; bash scripts/deploy.sh works for subsequent updates"
    why_human: "Requires live Oracle A1 ARM VM with Docker, arm64 image pull, and a valid DISCORD_TOKEN"
  - test: "A2. Reboot survival"
    expected: "systemctl is-enabled docker returns enabled; after sudo reboot the bot posts its startup message automatically within ~90 seconds, no SSH intervention needed"
    why_human: "Requires live VM reboot; not testable on dev machine"
  - test: "A3. Over-cap /play rejection"
    expected: "With MAX_QUEUE_SIZE_PER_GUILD=1, a second /play returns the personality cap rejection message; queue stays at 1 track"
    why_human: "Requires live Discord bot invocation"
  - test: "A4. Keepalive cron and Healthchecks.io"
    expected: "After crontab installs HEALTHCHECK_URL, the Healthchecks.io dashboard shows the check green with a ping within 10 minutes; Discord error-log channel receives the UP notification"
    why_human: "Requires live Oracle VM crontab + Healthchecks.io account + Discord webhook"
  - test: "A5. Backup cron manual run"
    expected: "bash scripts/backup.sh exits 0; a new dexter_YYYYMMDD_HHMMSS.dump object appears in the dexter-backups OCI bucket"
    why_human: "Requires live Oracle VM with oci-cli config, ~/.pgpass, and a running Postgres container"
  - test: "A6. Postgres integration tests"
    expected: "pytest tests/test_database_phase4.py -x exits 0 with 18 tests green against a live dexter_test Postgres"
    why_human: "Requires CREATE DATABASE dexter_test; no Postgres available on this dev machine"
  - test: "B1. Queue persistence round-trip"
    expected: "After /play + docker compose restart bot, /queue shows the restored track; smart-rejoin connects voice and resumes only when a non-bot human is still present"
    why_human: "Requires live Discord + Postgres; asyncpg integration tests pass but not verified against a live DB here"
  - test: "B2. clear_persisted on idle-leave (DEPLOY-06 live check)"
    expected: "Bot idles alone 10+ minutes, auto-leaves, then after docker compose restart bot, /queue is empty (not restored from guild_queues)"
    why_human: "Requires live Oracle VM; confirms the bot.py clear_persisted fix applied at runtime"
  - test: "C1. Voice join roast"
    expected: "Joining voice 4-5 times produces at least one roast in the bot channel; Gemini-personalized when API key live, VOICE_JOIN_ROASTS fallback on rate-limit"
    why_human: "Probabilistic event (30% chance) + Discord gateway + voice state required"
  - test: "C2. Late-night roast TZ fix (DEPLOY-04 C2)"
    expected: "Joining voice between 1-5am America/New_York fires a late-night roast at ~50% chance, NOT between 1-5am UTC (which would be 8-10pm ET). Confirms events.py ZoneInfo fix is live."
    why_human: "Requires live bot at specific wall-clock time; or temporary is_late_night patch on Oracle"
  - test: "C3. Startup message"
    expected: "docker compose restart bot causes a personality startup line to post to DEXTER_CHANNEL_ID within ~30 seconds"
    why_human: "Requires live Discord gateway"
  - test: "C4. Status rotation"
    expected: "Over 10-15 minutes, bot presence cycles through: current song (if playing), server-count line, random STATUS_LINES entry, seasonal line"
    why_human: "Requires live bot observation over time"
  - test: "C5. /lyrics command"
    expected: "After /play on a song with known Genius lyrics, /lyrics returns a paginated embed with Previous/Next buttons; buttons disable after 3-minute timeout"
    why_human: "Requires live bot + voice + playing song + GENIUS_TOKEN"
  - test: "C6. /history command"
    expected: "/history returns a paginated embed showing recently queued songs with title, artist, requester, date"
    why_human: "Requires live bot + prior song history in Postgres"
  - test: "C7. Message reactions"
    expected: "YouTube URL in chat -> bot reacts 👀; 'gn'/'goodnight' -> bot reacts 🫡; bare bot mention -> bot reacts 😐; mentioning bot with 'thanks' -> deflecting text reply"
    why_human: "Requires live Discord gateway and real message events"
  - test: "C8. Repeat-song roast"
    expected: "Queuing the same song 3 times in one day always fires a roast unconditionally"
    why_human: "Requires live bot + repeated play tracking in Postgres"
  - test: "C9. Idle loneliness"
    expected: "After 30+ minutes in voice with no commands, bot posts one IDLE_LONELINESS_MESSAGES line; does not repeat until new activity"
    why_human: "Requires live bot observation over 30+ minutes in a voice session"
  - test: "C10. Streak and milestone roasts"
    expected: "Using the bot on consecutive days triggers streak roasts at milestones (7/14/30/60/100 days); reaching song-count milestones (100/250/500/1000) triggers song-count roasts"
    why_human: "Requires live bot + real usage data accumulation in Postgres; threshold lowering may be needed for quick test"
  - test: "C11. DEPLOY-04 reconnect diagnostic (WR-03 deferred live check)"
    expected: "After a live voice disconnect/reconnect, docker compose logs bot shows: 'reconnect attempt X/3 in guild Y' and 'reconnect: vc.is_connected()=True gen=Z guild=Y'. Playback resumes normally. If playback silently fails with is_connected()=True, escalate to /gsd:debug session."
    why_human: "Requires a live network disruption or bot channel move on Oracle; the generation-counter race (WR-03) is deferred to this session for diagnosis"
  - test: "D1. End-to-end restore proof (DEPLOY-07)"
    expected: "python scripts/seed_restore_test.py on Oracle exits 0 with 'D-15 restore proof PASSED'; row counts match seeded values; dexter_restore_test dropped; seed rows removed from live DB"
    why_human: "Requires live Oracle VM with running Postgres container, OCI Object Storage access, and oci-cli config"
---

# Phase 5: Ship It Live Verification Report

**Phase Goal:** Dexter is running 24/7 on Oracle A1 and every v1.0 behavioral and deploy check has been validated in production
**Verified:** 2026-06-12
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

The phase goal has two components:

1. **Code-side (dev-machine verifiable):** All pre-deploy code fixes, deploy scripts, and the consolidated runbook land correctly and structurally. **Verified — all 5 code-side must-haves pass.**
2. **Live UAT (Oracle-side):** Every v1.0 behavioral and deploy check passes in production on Oracle A1. **Pending — 21 runbook checks require the live VM.**

This is the expected and correct verdict for a deploy phase. The phase is not failed; it is waiting on the user to execute the runbook on Oracle.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | clear_persisted() fires on idle-leave path (bot.py) so a ghost queue cannot resurrect on next boot | VERIFIED | `bot.py:398-403`: `queue._play_generation += 1` before `vc.stop()`, then `await bot.queue_persistence.clear_persisted(guild.id)` after `queue.clear()` — mirrors `/stop` template exactly |
| 2 | clear_persisted() fires on reconnect-failure path (cogs/music.py) so a dead session does not persist | VERIFIED | `cogs/music.py:1211-1214`: same generation increment + `await self.bot.queue_persistence.clear_persisted(member.guild.id)` after 3 failed reconnect attempts |
| 3 | Smart-rejoin guards is_connected() after connect() before calling _play_track (defensive race fix) | VERIFIED | `services/queue_persistence.py:147-151`: `vc = await vc_channel.connect()` captured, INFO log emitted, `if not vc.is_connected(): continue` guard before `_play_track` call; `continue` (not `return`) confirmed — CR-01 fix applied |
| 4 | Late-night roast hour is computed in STREAK_TIMEZONE, not naive host-local time | VERIFIED | `cogs/events.py:197-198`: `from zoneinfo import ZoneInfo as _ZoneInfo` + `local_hour = _dt.datetime.now(tz=_ZoneInfo(config.STREAK_TIMEZONE)).hour`; `datetime.now().hour` (naive) is absent |
| 5 | All deploy scripts and runbook are present, structurally correct, and ready for Oracle execution | VERIFIED | `scripts/deploy.sh` (syntax-clean, `--build bot`, dirty-tree guard, `--ff-only`, `down -v` warning); `scripts/backup.sh` (6h cadence, temp-file dump with size check); `scripts/lifecycle-policy.json` (valid JSON, 14-day DELETE rule for `dexter_` prefix); `scripts/seed_restore_test.py` (CR-02 fix: `_cleanup_seed()` in `finally`; throwaway DB only; `urlsplit` DSN fix); `05-UAT-RUNBOOK.md` (21 checks, A→B→C→D order, `down -v` warning, prereqs, troubleshooting table) |

**Score: 5/5 code-side truths verified**

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `bot.py` | clear_persisted on idle-leave | VERIFIED | Line 403: `await bot.queue_persistence.clear_persisted(guild.id)` present in idle-leave block; generation increment at line 398 before `vc.stop()` |
| `cogs/music.py` | clear_persisted on reconnect-failure + reconnect diagnostic logging + unchanged _play_track stop order | VERIFIED | 2 clear_persisted calls confirmed (`grep -c` = 2); reconnect loop has 2 INFO log calls (attempt + is_connected); `_play_track` has 3 DEBUG log calls; generation increment (347) before stop (365) before play (372) unchanged |
| `cogs/events.py` | TZ-explicit late-night hour via ZoneInfo(config.STREAK_TIMEZONE) | VERIFIED | ZoneInfo import + `_dt.datetime.now(tz=...)` present; naive `datetime.now().hour` absent; `config.STREAK_TIMEZONE` used (not hardcoded) |
| `services/queue_persistence.py` | is_connected() guard after connect() in smart-rejoin | VERIFIED | Guard at line 149-151 uses `continue` (not `return`) — CR-01 fix confirmed; `vc = await connect()` result is captured |
| `tests/test_streak.py` | test_tz_aware_hour_is_integer covering the TZ pattern | VERIFIED | Function present at line 85; 29 total pure tests (test_streak.py + test_seed_restore.py) run and pass in 0.03s |
| `scripts/deploy.sh` | D-13 workflow with down -v guard | VERIFIED | `up -d --build bot` present; `git pull --ff-only` present; dirty-tree guard present; 2x `down -v` warning echoes present; no hardcoded secrets |
| `scripts/backup.sh` | 6-hour cadence + temp-file dump with size guard | VERIFIED | `0 */6 * * *` appears twice; `*/30` absent; temp-file dump pattern with `MIN_DUMP_SIZE_BYTES=1024` guard (WR-01 fix) |
| `scripts/lifecycle-policy.json` | OCI 14-day DELETE rule for dexter_ prefix | VERIFIED | `timeAmount: 14`, `timeUnit: DAYS`, `inclusionPrefixes: ["dexter_"]` all present; valid JSON |
| `scripts/seed_restore_test.py` | D-15 non-destructive restore-verify with cleanup | VERIFIED | `_cleanup_seed()` in `finally` block (CR-02 fix); `THROWAWAY_DB = "dexter_restore_test"` constant; `urlsplit`/`urlunsplit` DSN fix (WR-06); `--no-owner --no-acl` in pg_restore call; `build_seed_rows()` pure/importable |
| `tests/test_seed_restore.py` | Pure seed-shape tests (no asyncpg) | VERIFIED | 15 tests in `TestSeedData` + 2 in `TestTzAwareHour`; no `import asyncpg`; no `pytest.mark.asyncio`; imports `build_seed_rows` from `scripts.seed_restore_test` |
| `.planning/phases/05-ship-it-live/05-UAT-RUNBOOK.md` | Consolidated ordered runbook (21 checks + prereqs + troubleshooting + warning) | VERIFIED | File exists, 270 lines; `grep -c "result:"` = 21; A→B→C→D order confirmed; `grep -c "down -v"` = 3; prereqs contain `timedatectl`, `~/.pgpass`, `lifecycle-policy.json`, `--first-run --guild`, `HEALTHCHECK_URL`; troubleshooting table contains `arm64`, `pool-acquire`, `pg_dump` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| bot.py idle-leave | queue_persistence.clear_persisted | `await` after `queue.clear()` | WIRED | Line 402-403: `hasattr` guard + `await bot.queue_persistence.clear_persisted(guild.id)` |
| cogs/music.py reconnect-failure | queue_persistence.clear_persisted | `await` after 3-attempt failure loop | WIRED | Lines 1213-1214: `hasattr` guard + `await self.bot.queue_persistence.clear_persisted(member.guild.id)` |
| services/queue_persistence.py smart-rejoin | music_cog._play_track | guarded by `vc.is_connected()` after connect() | WIRED | Lines 147-152: `vc = await connect()`, INFO log, `if not vc.is_connected(): continue`, then `_play_track` |
| 05-UAT-RUNBOOK.md group A1 | scripts/deploy.sh + docker-compose.yml | deploy/boot commands reference deploy.sh and `docker compose` | WIRED | Line 69: `bash scripts/deploy.sh` and `docker compose up -d` both present in A1 |
| 05-UAT-RUNBOOK.md group D1 | scripts/seed_restore_test.py | `python scripts/seed_restore_test.py` instruction | WIRED | Line 229: explicit invocation of the Plan-02 script |
| 04-HUMAN-UAT.md / 04-VERIFICATION.md / 03-VERIFICATION.md | 05-UAT-RUNBOOK.md | by-reference banner (D-07) | WIRED | All three source docs contain the Phase 5 consolidation pointer within the first 15 lines after frontmatter; original check bodies preserved |

### Data-Flow Trace (Level 4)

Not applicable. Phase 5 delivers code fixes, shell scripts, and a documentation runbook. No new dynamic-data-rendering component was added. The `build_seed_rows()` pure function has its data shape verified by 15 unit tests.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 29 pure unit tests pass | `python -m pytest tests/test_streak.py tests/test_seed_restore.py -q` | 29 passed, 0 failed in 0.03s | PASS |
| All modified Python modules compile clean | `python -m py_compile bot.py cogs/music.py cogs/events.py services/queue_persistence.py scripts/seed_restore_test.py` | exit 0 | PASS |
| Shell scripts syntax-clean | `bash -n scripts/deploy.sh && bash -n scripts/backup.sh` | exit 0 | PASS |
| lifecycle-policy.json is valid JSON | `python -c "import json; json.load(open('scripts/lifecycle-policy.json'))"` | exit 0 | PASS |
| clear_persisted count in cogs/music.py | `grep -c "clear_persisted" cogs/music.py` | 2 (existing /stop site + new reconnect-failure site) | PASS |
| Naive datetime.now().hour removed from events.py | `grep -n "datetime.now().hour" cogs/events.py` | no output | PASS |
| CR-01 fix: `continue` in restore_queues loop | `grep -n "continue" services/queue_persistence.py` | line 151: `continue  # skip THIS guild only` | PASS |
| 21 result: capture fields in runbook | `grep -c "result:" 05-UAT-RUNBOOK.md` | 21 | PASS |
| down -v warning present in runbook | `grep -c "down -v" 05-UAT-RUNBOOK.md` | 3 | PASS |

### Probe Execution

No phase-declared probe scripts. Phase 5 explicitly defers all live execution to the Oracle UAT session via the runbook. `python -m pytest tests/test_streak.py tests/test_seed_restore.py` serves as the dev-machine probe — 29 tests green (confirmed above).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DEPLOY-01 | 05-02, 05-03 | Dexter runs 24/7 on Oracle A1 via Docker Compose, surviving a host reboot | NEEDS LIVE UAT | scripts/deploy.sh written and syntax-clean; runbook A1/A2 checks defined. Live execution pending. |
| DEPLOY-02 | 05-03 | Standing live-UAT checklist (9 Phase-3 + 6 Phase-4 checks) executed and passing | NEEDS LIVE UAT | All 15 checks consolidated into 05-UAT-RUNBOOK.md C1-C11 + A-group. Execution pending on Oracle. |
| DEPLOY-03 | 05-03 | 6 human-UAT scenarios (04-HUMAN-UAT.md) executed and passing | NEEDS LIVE UAT | De-duped into the consolidated runbook. Execution pending on Oracle. |
| DEPLOY-04 | 05-01 | Voice playback survives a live reconnect without the race causing double-play or silent failure | CODE VERIFIED | `is_connected()` guard in smart-rejoin; diagnostic INFO logs in reconnect loop; 3 DEBUG logs in `_play_track`; test_queue.py confirms generation invariant unregressed. WR-03 (generation bump timing) deferred to live C11 debug session. |
| DEPLOY-05 | 05-03 | Queue + playback position survive a bot restart | NEEDS LIVE UAT | Runbook check B1. restore_queues logic from Phase 4 unchanged; CR-01 (`continue` fix) ensures multi-guild restore is not aborted by one failure. Live validation pending. |
| DEPLOY-06 | 05-01 | clear_persisted() fires correctly on idle-leave and reconnect-failure paths | CODE VERIFIED | Both gap sites confirmed in bot.py (line 403) and cogs/music.py (line 1214). Live confirmation deferred to runbook B2. |
| DEPLOY-07 | 05-02, 05-03 | pg_dump backup runs and a restore is validated end-to-end | CODE VERIFIED (script ready), NEEDS LIVE UAT | scripts/backup.sh and scripts/seed_restore_test.py structurally verified. CR-02 (_cleanup_seed) and WR-06 (urlsplit) fixes confirmed. D1 live execution pending on Oracle. |
| DEPLOY-08 | 05-03 | Keepalive / dead-man cron confirmed firing in production | NEEDS LIVE UAT | Runbook check A4 + prerequisites documented. Execution pending on Oracle with Healthchecks.io account. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `cogs/music.py` | 58 | `placeholder="Pick a song..."` | INFO | Discord select menu placeholder text — not a code stub; this is a UI label for the search-result dropdown. Non-issue. |

No `TBD`, `FIXME`, or `XXX` markers found in any Phase 5 modified files. No unresolved debt markers.

### Code Review Remediation Status

All critical and warning findings from 05-REVIEW.md were resolved before this verification:

| Finding | Severity | Fix Confirmed |
|---------|----------|---------------|
| CR-01: `return` in restore_queues abandoned all remaining guilds | Critical | `continue` at services/queue_persistence.py:151 — confirmed |
| CR-02: seed_restore_test permanently polluted live DB | Critical | `_cleanup_seed()` in `finally` at scripts/seed_restore_test.py:426-430 — confirmed |
| WR-01: backup.sh pipe masked pg_dump failure | Warning | Temp-file dump + size guard (1 KB minimum) at scripts/backup.sh:55-70 — confirmed |
| WR-02: deploy.sh git pull with no clean-tree guard | Warning | Dirty-tree check + `--ff-only` at scripts/deploy.sh:44-52 — confirmed |
| WR-05: dead `result =` binding in _docker_exec_stdin | Warning | `subprocess.run(cmd, input=stdin_bytes, check=True)` — binding removed, confirmed |
| WR-06: _get_pool DSN rewrite broke query params | Warning | `urlsplit`/`urlunsplit` at scripts/seed_restore_test.py:143-144 — confirmed |
| WR-07: bot.owner_id unset; /sync unusable for actual owner | Warning | `owner_id=config.OWNER_ID or None` at bot.py:67; `/sync` uses `await bot.is_owner(interaction.user)` at bot.py:357 — confirmed |

**Deferred (advisory, not blocking):**
- WR-03: Reconnect generation-counter race — intentionally deferred to live C11 debug session; diagnostic logging from Plan 01 provides the trail
- WR-04: Restore path does not re-apply duration cap on persisted tracks — low risk; only bites if config is tightened between sessions
- IN-01 through IN-05: Cosmetic / dedup / determinism nits; no behavioral impact

### Human Verification Required

The 21 runbook checks below require execution on the live Oracle A1 VM. They are enumerated above in the frontmatter `human_verification` list and in `.planning/phases/05-ship-it-live/05-UAT-RUNBOOK.md`.

**Execution instructions:** SSH to Oracle A1, complete the prerequisites checklist in the runbook, then run checks A1 → A6 → B1 → B2 → C1-C11 → D1 in the locked order. Record each `result:` field in the runbook. Phase 5 is verified when all 21 pass.

**Key checks to watch for:**
- **B2** (DEPLOY-06 live): confirms `clear_persisted()` fired on idle-leave at runtime — the most critical Phase 5 bug fix
- **C11** (DEPLOY-04): the reconnect race diagnostic — if WR-03 still fires under real concurrency, the new INFO log trail enables a targeted `/gsd:debug` session
- **D1** (DEPLOY-07): the non-destructive restore proof via `scripts/seed_restore_test.py` — validates the entire backup/restore pipeline end-to-end

### Gaps Summary

No code-side gaps found. All Phase 5 code deliverables are structurally complete, syntax-clean, test-verified, and code-review-remediated.

The only open items are the 21 live Oracle UAT checks — which are by design human-executed and cannot be verified on a Windows dev machine. The `status: human_needed` verdict reflects this correctly: automated checks passed; awaiting human verification.

---

*Verified: 2026-06-12*
*Verifier: Claude (gsd-verifier)*
