# Phase 5: Ship It Live — Research

**Researched:** 2026-06-12
**Domain:** Deploy + targeted code fixes + live validation (Oracle A1 ARM64 / Docker Compose / discord.py / asyncpg / Healthchecks.io / OCI Object Storage)
**Confidence:** HIGH (code inspection verified; discord.py via Context7; pg_restore via official Postgres docs; OCI lifecycle via official Oracle docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Phase 5 deliverables from Claude = (a) 3 code fixes with TDD where logic is pure-testable; (b) one consolidated ordered live-UAT runbook; (c) helper scripts (deploy.sh, seed, restore-verify). User executes all live steps on Oracle and reports results; phase is verified when the live checklist passes, not when code lands.
- **D-02:** Defensive fix-by-inspection NOW, limited to invariants provable from reading the code: guard `is_connected()` before `voice_client.play()`; confirm `_play_generation` increments before any `stop()`; make smart-rejoin AWAIT connection before `_play_track` (WR-03 race at `services/queue_persistence.py:147`).
- **D-03:** Instrument the reconnect/rejoin path with diagnostic logging — generation transitions, connection state, play/stop events.
- **D-04:** Verify live, escalate only if needed. If race still bites under live concurrency, open a dedicated `/gsd:debug` session using the new logs.
- **D-05:** Add `clear_persisted()` at `bot.py:399` (idle-leave) and `cogs/music.py:1206` (reconnect-failure), mirroring the already-correct `/stop` path at `cogs/music.py:977-980`.
- **D-06:** Make wall-clock code TZ-explicit. `cogs/events.py:197` late-night check → use `ZoneInfo(STREAK_TIMEZONE)`. `bot.py:467` yt-dlp 04:00 loop → add `tzinfo` for consistency, or accept 4am-UTC (Claude's discretion). Also set VM system timezone to `America/New_York` for log timestamps.
- **D-07:** Consolidate all 21 standing checks into ONE ordered master runbook. Order: deploy/boot → infra crons → behavioral (Discord) → destructive (backup/restore) LAST.
- **D-08:** Per-guild command sync to single community guild via `--first-run --guild <id>` / owner `/sync`. Global sync deferred.
- **D-09:** Reboot survival already handled by `restart: unless-stopped` + named volumes. Runbook adds one check: `systemctl is-enabled docker`.
- **D-10:** Manual `.env` on VM (chmod 600), OCI backup creds via `~/.oci/config`, pg_dump password via `~/.pgpass` (chmod 600). No external secret manager.
- **D-11:** Troubleshooting table (arm64 pull fail, healthcheck timeout, bad token, pool-acquire, volume perms → fix) + fix-forward recovery. Real tagged-image rollback deferred.
- **D-12:** Healthchecks.io alerts → Discord webhook into existing error-log channel + email as independent backup.
- **D-13:** Manual git-pull + rebuild on host, wrapped in `scripts/deploy.sh`: git pull → `docker compose up -d --build bot` → tail logs → ping healthcheck. Loud "never `docker compose down -v` in prod" warning.
- **D-14:** `pg_dump` every 6 hours (4/day) + OCI Object Storage lifecycle rule auto-deleting dumps older than ~14 days.
- **D-15:** Non-destructive restore proof: seed known rows → run backup.sh → download dump → restore into throwaway `dexter_restore_test` DB → verify row counts/values match. Never touch live DB.

### Claude's Discretion
- Exact runbook file location/structure; verbosity of reconnect-path instrumentation logging; seed-data shape/volume.
- Healthchecks.io integration setup specifics.
- OCI bucket/region prerequisites — runbook prereq checklist.
- Exact reboot-test step wording.
- crontab env wiring (HEALTHCHECK_URL, PGPASSWORD/~/.pgpass).
- Whether `bot.py:467` yt-dlp loop gets `tzinfo` or stays 4am-UTC (low-stakes, D-06).
- Any new `config.py` constants.

### Deferred Ideas (OUT OF SCOPE)
- Redis or any new caching layer (Phase 6 at earliest)
- GHCR image pipeline + tagged-image rollback (deferred until redeploys become frequent/annoying)
- Full auto-CD (deferred indefinitely)
- Log-shipping/dashboard stack (Loki + Grafana)
- `bot.py:467` yt-dlp loop tzinfo (low-stakes, may remain 4am-UTC)
- Mid-song position resume on restart; Pay-As-You-Go Oracle reclaim-immunity upgrade; per-guild Gemini rate isolation; off-provider backup; persisting `auto_lyrics`/`lyrics_thread_id` across restart
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEPLOY-01 | Dexter runs 24/7 on Oracle A1 via Docker Compose (bot + Postgres), surviving a host reboot | docker-compose.yml `restart: unless-stopped` + named volumes already deliver this; runbook confirms `systemctl is-enabled docker`; deploy.sh workflow documented |
| DEPLOY-02 | The standing live-UAT checklist (9 Phase-3 behavioral + 6 Phase-4 deploy checks) is executed and passing | All 15 checks enumerated verbatim from 03-VERIFICATION + 04-VERIFICATION; consolidated in runbook order in this research |
| DEPLOY-03 | The 6 human-UAT scenarios (04-HUMAN-UAT.md) are executed and passing | All 6 pending scenarios enumerated; de-duped against 04-VERIFICATION (they overlap); runbook integrates them in one ordered flow |
| DEPLOY-04 | Voice playback survives a reconnect under live concurrency (parked race fixed) | Code inspection identifies exact fixes at `cogs/music.py:1194-1210`, `services/queue_persistence.py:146-148`; discord.py `is_connected()` API confirmed via Context7; fix pattern documented |
| DEPLOY-05 | Queue + playback position survive a bot restart (persistence + smart-rejoin validated live) | SCALE-04 already structurally verified; live confirmation in runbook (step: restart bot, check /queue restores, smart-rejoin connects) |
| DEPLOY-06 | `clear_persisted()` fires correctly on idle-leave and reconnect-failure paths (IN-02 resolved) | Exact insertion points confirmed by code inspection: `bot.py:399`, `cogs/music.py:1206`; template at `cogs/music.py:977-980` documented |
| DEPLOY-07 | Scheduled pg_dump backup runs and a restore is validated end-to-end | backup.sh already written; cadence change to 6h cron documented; OCI lifecycle policy JSON documented; pg_restore flags confirmed via official Postgres docs; seed + restore-verify script pattern documented |
| DEPLOY-08 | Keepalive/dead-man cron confirmed firing in production | keepalive.sh already written; Healthchecks.io setup documented (check creation, ping URL, Discord webhook + email integrations); crontab env wiring documented |
</phase_requirements>

---

## Summary

Phase 5 is an execution phase, not a design phase. Phase 4 produced all the infrastructure: `docker-compose.yml`, `Dockerfile`, `scripts/backup.sh`, `scripts/keepalive.sh`, and the full queue persistence stack. Phase 5 has three narrow code changes plus a deploy runbook plus helper scripts.

**Code changes (net-new code):** (1) Reconnect race defensive fix — guard `is_connected()` at `services/queue_persistence.py:147` before calling `_play_track`, and add diagnostic logging to the reconnect loop at `cogs/music.py:1194-1210`. (2) `clear_persisted()` at two missing call sites — `bot.py:399` and `cogs/music.py:1206`. (3) Timezone-correctness — replace `datetime.datetime.now().hour` at `cogs/events.py:197` with `datetime.now(tz=ZoneInfo(config.STREAK_TIMEZONE)).hour`. All three fixes are narrow, non-regressive, and provable from code inspection alone.

**Infrastructure changes:** `scripts/backup.sh` cron cadence → every 6 hours (crontab expression `0 */6 * * *`). OCI Object Storage lifecycle policy added (14-day auto-delete). New `scripts/deploy.sh` update workflow. New seed + restore-verify scripts for DEPLOY-07.

**Validation:** 21 checks must pass live on Oracle. The dev machine can confirm pure-logic invariants (TZ helper logic, seed/restore-verify pure parts); all Discord/Oracle/Docker checks are live-UAT-only by nature.

**Primary recommendation:** Write the three code fixes first (they are the only blockers to a clean first boot), then write the runbook + scripts so the user has everything ready for one SSH session.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Voice playback reconnect | API/Backend (bot process) | — | discord.py VoiceClient lifecycle lives in the bot process; no other tier involved |
| Queue persistence (clear_persisted) | API/Backend (bot process) | Database (Postgres) | Bot owns the state machine; Postgres is the durable store |
| Timezone-correct wall-clock | API/Backend (bot process) | — | TZ logic is pure Python in the bot process; no external service |
| Docker Compose boot + restart | Infra (Oracle VM / Docker) | — | `restart: unless-stopped` is a Docker daemon concern, not bot code |
| pg_dump backup | Infra (Oracle VM host) | OCI Object Storage | pg_dump runs on the VM host (outside Docker) and pushes to OCI |
| Healthchecks.io dead-man | Infra (Oracle VM host cron) | Healthchecks.io SaaS | keepalive.sh is a host-level cron; Healthchecks.io is the external alerting service |
| Command sync | API/Backend (bot process) | — | discord.py `tree.sync()` registers slash commands with Discord; owner-gated |
| OCI lifecycle policy | OCI Object Storage | — | Pure OCI console/oci-cli configuration; no bot code involved |

---

## Standard Stack

### Core (already in codebase — no new installs)

| Library | Version in repo | Purpose | Note |
|---------|----------------|---------|------|
| discord.py | >=2.3.0 | Bot framework, VoiceClient, tasks.loop | `[VERIFIED: requirements.txt]` |
| asyncpg | 0.31.0 | Postgres driver | `[VERIFIED: requirements.txt]` |
| python-dotenv | (pinned) | .env loading | `[VERIFIED: requirements.txt]` |
| tzdata | (pinned) | IANA tz database for ZoneInfo on Linux | `[VERIFIED: requirements.txt]` — critical: without tzdata, ZoneInfo("America/New_York") fails on alpine/slim Linux images |

### New scripts (bash, no new Python packages)

| Script | Language | Purpose |
|--------|----------|---------|
| `scripts/deploy.sh` | bash | git pull + rebuild bot image + health check |
| `scripts/seed_restore_test.py` | Python (std lib + asyncpg) | Seed known rows; restore-verify against throwaway DB |

**No new Python packages required for Phase 5.**

---

## Package Legitimacy Audit

Phase 5 installs no new packages. All packages already in `requirements.txt` have been in production use since Phase 2–4. Audit is **N/A** for this phase.

---

## Architecture Patterns

### System Architecture Diagram

```
Oracle A1 ARM VM (host)
├── crontab
│   ├── */5  → keepalive.sh → curl hc-ping.com/<uuid> (dead-man ping)
│   └── 0 */6 → backup.sh → pg_dump | oci os object put (dexter-backups bucket)
│                                 ↓
│                         OCI Object Storage
│                         (lifecycle: delete after 14d)
│
└── Docker Compose
    ├── postgres:16-alpine  (postgres_data volume)
    │   └── healthcheck: pg_isready
    └── bot (python:3.11-slim-bookworm)
        ├── on_ready → asyncpg pool → init_db → restore_queues → _post_startup_messages
        ├── Background tasks: idle_check(60s), cache_cleanup(1h), ytdlp_update(04:00), status_rotation(5m)
        └── VoiceClient ↔ Discord Gateway
                           ↓
                    Discord (live guild)

External monitoring:
Healthchecks.io → Discord webhook (error-log channel) + email on missed ping
```

### Recommended Project Structure (unchanged — Phase 5 adds only scripts)

```
scripts/
├── backup.sh          # exists (cadence change only)
├── keepalive.sh       # exists (Healthchecks.io URL wiring)
├── deploy.sh          # NEW: git pull + rebuild workflow
├── seed_restore_test.py  # NEW: D-15 restore proof
```

---

## Focus Area 1: Reconnect Race — DEPLOY-04 (D-02/D-03/D-04)

### What the code actually does (inspected)

**`cogs/music.py:1188-1210` (bot-disconnect handler in `on_voice_state_update`):**

```python
# Fires when: member.id == self.bot.user.id and after.channel is None and before.channel is not None
queue.is_playing = False
queue.is_paused = False

for attempt in range(3):
    try:
        await asyncio.sleep(1)
        vc = await before.channel.connect()   # <-- awaits connection
        track = queue.get_current()
        if track:
            await self._play_track(member.guild, track)   # <-- _play_track has its own guard
            return
    except Exception as e:
        log.error(f"Reconnect attempt {attempt + 1} failed: {e}")

queue.clear()   # <-- MISSING: clear_persisted() call (DEPLOY-06)
```

**`services/queue_persistence.py:139-153` (smart-rejoin on `restore_queues` at boot):**

```python
try:
    await vc_channel.connect()                   # WR-03: no await-confirmation guard
    await music_cog._play_track(guild, current)  # called immediately after connect()
except Exception as exc:
    log.warning("Smart rejoin failed for guild %s: %s", guild_id, exc)
```

**`cogs/music.py:305-375` (`_play_track` itself):**

```python
voice_client = guild.voice_client
if not voice_client or not voice_client.is_connected():
    return   # already guarded at top

# ... get source ...
queue._play_generation += 1      # incremented BEFORE stop()
current_gen = queue._play_generation

# ... after_callback captures current_gen ...
if voice_client.is_playing() or voice_client.is_paused():
    voice_client.stop()           # old after-callback fires but sees stale gen

if not voice_client.is_connected():  # second guard before play()
    source.cleanup()
    return

voice_client.play(source, after=after_callback)
```

### Invariants confirmed by inspection

1. `_play_generation` increments BEFORE `voice_client.stop()` inside `_play_track`. The CLAUDE.md gotcha ("never `voice_client.stop()` before `_play_track()`") is already respected — callers never call `stop()` then `_play_track()`; `_play_track` handles its own stop internally. `[VERIFIED: codebase cogs/music.py:346-363]`

2. `_play_track` has two `is_connected()` guards: one at the top (line 311) and one just before `voice_client.play()` (line 365). These already protect against "connection dropped between get_source and play". `[VERIFIED: codebase cogs/music.py:311, 365]`

3. The smart-rejoin at `queue_persistence.py:147` calls `_play_track` immediately after `await vc_channel.connect()`. The WR-03 race: `vc_channel.connect()` returns a `VoiceClient` but the internal WebSocket handshake for voice may not yet be complete. `_play_track` fetches `guild.voice_client` at its top — which should already be set by `connect()` — and then checks `is_connected()`. The question is: can `is_connected()` return False immediately after `connect()` returns? Per the discord.py pattern, `connect()` is awaited and resolves when the voice WebSocket is established, so `is_connected()` should be True immediately after. **The main risk is a race with concurrent shutdown events**, not a timing issue post-`await`.

4. The `after_callback` generation check (line 353) is the correct stale-callback guard. It is thread-safe via `asyncio.run_coroutine_threadsafe`. `[VERIFIED: codebase cogs/music.py:349-357]`

### discord.py VoiceClient API (confirmed via Context7)

`[VERIFIED: Context7 /websites/discordpy_readthedocs_io_en]`

- `VoiceClient.is_connected()` — returns True if the voice WebSocket connection is active
- `VoiceChannel.connect()` — awaitable; returns VoiceClient when the voice WS handshake is complete
- `VoiceClient.play(source, after=callback)` — starts playback; `after` receives error or None
- `VoiceClient.stop()` — stops current playback, fires the `after` callback with `None`
- `VoiceClient.is_playing()`, `VoiceClient.is_paused()` — synchronous state checks

**The correct guard before calling `_play_track` in smart-rejoin:**

```python
# services/queue_persistence.py:146-148 — the fix
try:
    vc = await vc_channel.connect()
    if not vc.is_connected():   # paranoia guard post-connect
        log.warning("Smart rejoin: vc not connected after connect() for guild %s", guild_id)
        return
    await music_cog._play_track(guild, current)
except Exception as exc:
    log.warning("Smart rejoin failed for guild %s: %s", guild_id, exc)
```

### Diagnostic logging to add (D-03)

Instrument at these points so a future `/gsd:debug` session has a trail:

| Location | Log statement | Level |
|----------|--------------|-------|
| `cogs/music.py:346` (before `_play_generation += 1`) | `log.debug("gen=%d → %d in guild %d", queue._play_generation, queue._play_generation+1, guild.id)` | DEBUG |
| `cogs/music.py:360` (before `voice_client.stop()`) | `log.debug("stopping current playback gen=%d in guild %d", queue._play_generation, guild.id)` | DEBUG |
| `cogs/music.py:370` (after `voice_client.play()`) | `log.debug("play() called gen=%d connected=%s guild=%d", current_gen, voice_client.is_connected(), guild.id)` | DEBUG |
| `cogs/music.py:1196` (each reconnect attempt) | `log.info("reconnect attempt %d/3 in guild %d", attempt+1, guild.id)` | INFO |
| `cogs/music.py:1199` (after `connect()`) | `log.info("reconnect: vc.is_connected()=%s gen=%d guild=%d", vc.is_connected(), queue._play_generation, guild.id)` | INFO |
| `services/queue_persistence.py:147` (smart-rejoin, after connect) | `log.info("smart-rejoin: connected=%s guild=%d", vc.is_connected(), guild_id)` | INFO |

**CRITICAL constraint:** Do not add log.DEBUG calls on the hot playback path (every track start) at INFO level — that would flood the log. Use DEBUG level for per-play events; INFO level for reconnect path events.

### What the race looks like if it still fires live

If after the fix the bot still fails to play on reconnect, the log trail will show: `reconnect: vc.is_connected()=True` but no `play() called` log. That means `_play_track` returned early at the top guard — either `guild.voice_client` was None (means discord.py cleared it between `connect()` returning and `_play_track` reading it) or `is_connected()` returned False. The live `/gsd:debug` session should look for this pattern.

---

## Focus Area 2: clear_persisted Fix — DEPLOY-06 (D-05)

### Template (already correct at `/stop`)

`cogs/music.py:977-980` — the correct pattern: `[VERIFIED: codebase cogs/music.py:977-984]`

```python
queue._play_generation += 1  # invalidate any pending after-callbacks
queue.clear()
if hasattr(self.bot, "queue_persistence"):
    await self.bot.queue_persistence.clear_persisted(interaction.guild.id)
```

### Gap 1: `bot.py:399` (idle-leave path)

**Current code (`bot.py:395-403`):**

```python
if vc._idle_seconds >= config.IDLE_TIMEOUT_SECONDS:
    log.info(f"Idle timeout in guild {guild.id}, disconnecting")
    vc.stop()
    await vc.disconnect()
    queue.clear()           # <-- clear_persisted() is missing here
    channel = music_cog._get_text_channel(guild)
    if channel:
        await channel.send("Left the voice channel after being alone for too long.")
```

**Fix:**

```python
if vc._idle_seconds >= config.IDLE_TIMEOUT_SECONDS:
    log.info(f"Idle timeout in guild {guild.id}, disconnecting")
    queue._play_generation += 1  # invalidate stale after-callbacks (mirrors /stop template)
    vc.stop()
    await vc.disconnect()
    queue.clear()
    if hasattr(bot, "queue_persistence"):
        await bot.queue_persistence.clear_persisted(guild.id)
    channel = music_cog._get_text_channel(guild)
    if channel:
        await channel.send("Left the voice channel after being alone for too long.")
```

Note: `bot` is in scope in `idle_check` (it's a top-level task in `bot.py`). `queue_persistence` is set in `_initialize_once()` before any task can fire. `clear_persisted` is `async` — must be `await`ed. `[VERIFIED: codebase services/queue_persistence.py:64-82]`

### Gap 2: `cogs/music.py:1206` (reconnect-failure path)

**Current code (`cogs/music.py:1204-1209`):**

```python
            log.error(f"Reconnect attempt {attempt + 1} failed: {e}")

    queue.clear()           # <-- clear_persisted() is missing here
    channel = self._get_text_channel(member.guild)
    if channel:
        await channel.send(embed=embeds.error("Lost voice connection. Queue cleared."))
```

**Fix:**

```python
    queue._play_generation += 1  # invalidate stale after-callbacks
    queue.clear()
    if hasattr(self.bot, "queue_persistence"):
        await self.bot.queue_persistence.clear_persisted(member.guild.id)
    channel = self._get_text_channel(member.guild)
    if channel:
        await channel.send(embed=embeds.error("Lost voice connection. Queue cleared."))
```

**Async context check:** `on_voice_state_update` is an `async def` method — `await` is valid here. `[VERIFIED: codebase cogs/music.py:1177-1180]`

### clear_persisted implementation (for reference)

```python
# services/queue_persistence.py:64-82
async def clear_persisted(self, guild_id: int) -> None:
    """Delete the persisted queue for a guild."""
    try:
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM guild_queues WHERE guild_id = $1", str(guild_id))
    except Exception as exc:
        log.warning("Failed to clear persisted queue for guild %s: %s", guild_id, exc)
```

Failures are swallowed — consistent with the "persistence issues must never crash playback" principle. `[VERIFIED: codebase services/queue_persistence.py]`

---

## Focus Area 3: Timezone Correctness — D-06

### Confirmed discord.py behavior (CRITICAL)

`[VERIFIED: Context7 /websites/discordpy_readthedocs_io_en]`

```python
# Official discord.py docs — tasks.loop time parameter:
# "If no tzinfo is given then UTC is assumed."

# This means a naive datetime.time is UTC:
@tasks.loop(time=datetime.time(hour=4, minute=0))   # fires at 04:00 UTC, NOT host local time
async def ytdlp_update():
    ...
```

This diverges from `datetime.datetime.now().hour` (host local time) when the host is not UTC. The Oracle VM defaults to UTC in many configurations, but `config.py:58` establishes the community is America/New_York (UTC-4/UTC-5 depending on DST). If the VM is ever set to America/New_York (as D-06 also recommends for clean log timestamps), the yt-dlp loop fires at 04:00 UTC but `datetime.now().hour` reads Eastern time.

### The fix pattern (TZ-explicit)

**`cogs/events.py:197` — the fix that matters (late-night roasts, DEPLOY-02 behavioral check):**

```python
# Before (uses host local time — naive, inconsistent with streak TZ):
import datetime as _dt
local_hour = _dt.datetime.now().hour

# After (uses configured STREAK_TIMEZONE — consistent with all other TZ-aware code):
from zoneinfo import ZoneInfo
local_hour = datetime.now(tz=ZoneInfo(config.STREAK_TIMEZONE)).hour
```

The `ZoneInfo` import is already present in `database.py` and used in `compute_streak`. The `tzdata` package is already in `requirements.txt` (required for ZoneInfo to work on Linux without system tz data). `[VERIFIED: codebase database.py:6, requirements.txt]`

**`bot.py:467` — yt-dlp loop (low-stakes, Claude's discretion):**

```python
# Option A: Make explicit (fires at 04:00 America/New_York):
from zoneinfo import ZoneInfo
_ET = ZoneInfo(config.STREAK_TIMEZONE)
@tasks.loop(time=datetime.time(hour=4, minute=0, tzinfo=_ET))
async def ytdlp_update():
    ...

# Option B: Leave as UTC (fires at 04:00 UTC = 23:00/00:00 ET — quiet hours but off-spec)
# Acceptable: yt-dlp update is a maintenance task, not a user-visible personality feature.
```

**Recommendation:** Apply Option A for consistency; the tz-explicit form is a one-line change and eliminates the UTC/local ambiguity entirely.

### VM timezone setup (backstop)

```bash
sudo timedatectl set-timezone America/New_York
timedatectl  # verify
```

This does NOT replace code-level TZ fixes (as D-06 notes), but produces clean log timestamps.

### TDD candidate: the TZ helper logic

The fix to `cogs/events.py:197` is a one-liner and doesn't benefit from a standalone test. However, the existing `tests/test_streak.py::test_get_local_date_timezone` (7 tests passing) covers the `get_local_date(tz_name)` function — that is the authoritative test that the ZoneInfo pattern works. The new code in `events.py` uses the same pattern. A smoke test asserting `datetime.now(tz=ZoneInfo("America/New_York")).hour` returns an integer in [0,23] can be written as a pure unit test. `[VERIFIED: codebase tests/test_streak.py]`

---

## Focus Area 4: Backup/Restore Round-Trip — DEPLOY-07 (D-14/D-15)

### Cron cadence change

**Current** (backup.sh line 12 comment): `*/30 * * * *` (48/day — overkill)
**Required** (D-14): every 6 hours = `0 */6 * * *` (4/day)

Update `backup.sh` comment and crontab. The script itself is unchanged.

### pg_dump round-trip (confirmed via official Postgres docs)

`[CITED: https://www.postgresql.org/docs/current/app-pgrestore.html]`

**The backup.sh already uses `--format=custom`** (the `c` in `-Fc`). Custom format is the correct choice: compressed, seekable, supports selective restore. `[VERIFIED: codebase scripts/backup.sh:49]`

**Restore into throwaway DB — correct sequence:**

```bash
# Step 1: Download the dump from OCI Object Storage
oci os object get \
  --namespace-name <namespace> \
  --bucket-name dexter-backups \
  --name <object-name> \
  --file /tmp/dexter_restore.dump

# Step 2: Create the throwaway DB (use template0, not template1)
docker compose exec postgres createdb -U dexter -T template0 dexter_restore_test

# Step 3: Restore (--no-owner so the dexter user owns everything without needing superuser)
docker compose exec -T postgres pg_restore \
  -U dexter \
  -d dexter_restore_test \
  --no-owner \
  --no-acl \
  /tmp/dexter_restore.dump

# Step 4: Row-count verification
docker compose exec postgres psql -U dexter -d dexter_restore_test \
  -c "SELECT 'user_profiles' AS tbl, COUNT(*) FROM user_profiles UNION ALL
      SELECT 'song_history', COUNT(*) FROM song_history UNION ALL
      SELECT 'user_artist_counts', COUNT(*) FROM user_artist_counts;"

# Step 5: Drop throwaway DB
docker compose exec postgres dropdb -U dexter dexter_restore_test
```

**Passing the dump file into the container:** The dump is on the VM host. Two options:
- Option A: Run `pg_dump` → dump to `/tmp/` on host → `pg_restore` from host using `--host=localhost --port=5432` (requires `postgresql-client` on host, which `backup.sh` already requires).
- Option B: Run everything via `docker compose exec` (no extra packages on host needed). The dump piped into the container via stdin: `docker compose exec -T postgres pg_restore -U dexter -d dexter_restore_test --no-owner < /tmp/dexter_restore.dump`.

**Recommendation:** Option B (docker exec) avoids postgresql-client version mismatch between host and container (a documented trap — pg_restore must match pg_dump server version). `[CITED: https://davejansen.com/how-to-dump-and-restore-a-postgresql-database-from-a-docker-container/]`

**LANDMINE — Pipe masks pg_dump failure (WR-07 from 04-VERIFICATION):** The current `backup.sh` uses a pipeline `pg_dump | oci os object put`. In bash, `set -euo pipefail` is set, which means pipeline failures will propagate. But `oci os object put --force` succeeds even if the dump was empty. Recommend the `restore-verify` script check for minimum file size before asserting restore success. `[VERIFIED: codebase scripts/backup.sh:41]`

### OCI Object Storage lifecycle policy — 14-day auto-delete

`[CITED: https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usinglifecyclepolicies.htm]`
`[CITED: https://github.com/oracle/oci-cli/blob/master/services/object_storage/examples_and_test_scripts/write_object_lifecycle_policy.sh]`

**JSON structure** (`scripts/lifecycle-policy.json`):

```json
[
  {
    "name": "delete-old-backups",
    "action": "DELETE",
    "isEnabled": true,
    "timeAmount": 14,
    "timeUnit": "DAYS",
    "objectNameFilter": {
      "inclusionPrefixes": ["dexter_"],
      "inclusionPatterns": [],
      "exclusionPatterns": []
    }
  }
]
```

**Apply via oci-cli:**

```bash
# Get namespace (one-time lookup):
NAMESPACE=$(oci os ns get --query 'data' --raw-output)

oci os object-lifecycle-policy put \
  --namespace-name "${NAMESPACE}" \
  --bucket-name dexter-backups \
  --items file://scripts/lifecycle-policy.json
```

**Notes:**
- `inclusionPrefixes: ["dexter_"]` matches the naming pattern `dexter_YYYYMMDD_HHMMSS.dump`. Empty array would match all objects.
- Policy is applied as a complete replacement — to update, resubmit the full JSON.
- Rules process within ~10 minutes (Oracle best-effort). No cost implication at always-free tier. `[ASSUMED: OCI always-free storage limit of 20GB is not exceeded by 4 dumps/day × 14 days at typical Dexter DB size]`

### Seed + restore-verify script design (D-15)

```python
# scripts/seed_restore_test.py — design sketch
# 1. Connect to live 'dexter' DB via asyncpg
# 2. INSERT known rows:
#    - user_profiles: 1 user with total_songs_queued=5, streak=3
#    - song_history: 3 rows for that user
#    - user_artist_counts: 2 artist entries
# 3. Call backup.sh (subprocess)
# 4. Download latest dump from OCI (oci os object list → get newest)
# 5. createdb dexter_restore_test
# 6. pg_restore into dexter_restore_test
# 7. Connect to dexter_restore_test, query row counts, assert == seeded counts
# 8. dropdb dexter_restore_test
# 9. Optionally clean up the seed rows from the live DB (or leave — they are real data)
```

The script is invoked once manually by the user during the DEPLOY-07 runbook step. It is **not** run as a cron job. The seeding step writes real data to the live (start-fresh) DB — which is fine since the DB is near-empty at first deploy. The verify step uses a dedicated throwaway DB.

---

## Focus Area 5: Dead-Man Alert Routing — DEPLOY-08 (D-12)

### Healthchecks.io setup

`[CITED: https://healthchecks.io/docs/]`
`[CITED: https://johnsturgeon.me/2024/07/01/discord-bot-healthcheck/]`

**Ping URL pattern:**
```
https://hc-ping.com/<uuid>
```
Curling the base URL = success ping. `/fail` suffix = failure signal. `/start` suffix = job started.

**Creating a check:**
1. Sign in to healthchecks.io → "New Project" (name: "Dexter Monitoring")
2. "Add Check" → Name: "Dexter Keepalive" → Simple schedule
3. Period: 10 minutes (2× the 5-min cron period for grace); Grace: 10 minutes
4. Save → copy the ping URL (looks like `https://hc-ping.com/<36-char-uuid>`)

**Discord webhook integration:**
1. In the error-log Discord channel → Channel Settings → Integrations → New Webhook → copy the webhook URL
2. Healthchecks.io → Integrations → "Add Integration" → Discord → Enter the webhook URL
3. Test the integration — it posts a test message to the channel
4. On the check's page → toggle the Discord integration "on"

**Email integration:**
1. Healthchecks.io → Integrations → "Add Integration" → Email → Enter email address
2. Toggle email on for the check — fires when check goes DOWN or returns UP

**`HEALTHCHECK_URL` wiring in crontab:**

```crontab
HEALTHCHECK_URL=https://hc-ping.com/<your-uuid>
*/5 * * * * /opt/dexter/scripts/keepalive.sh >> /var/log/dexter/keepalive.log 2>&1
```

`keepalive.sh` already reads `${HEALTHCHECK_URL}` and is non-fatal on failure (`|| true`). `[VERIFIED: codebase scripts/keepalive.sh:31]`

**Verification:** After crontab is set, wait 10 minutes and check the Healthchecks.io dashboard. A green check with "Last ping: X minutes ago" confirms the cron is firing. The Discord channel should show a "Bot Dexter Keepalive is UP" notification when the integration fires.

---

## Focus Area 6: Deploy Mechanics — DEPLOY-01/03 (D-09/D-11/D-13)

### Command sync (D-08)

**Existing mechanism confirmed:** `bot.py:503-530` (`first_run()`), `bot.py:353-370` (`/sync` owner command). `[VERIFIED: codebase bot.py:503-542]`

**Per-guild first-run sync:**
```bash
python bot.py --first-run --guild <GUILD_ID>
```
This loads all cogs, registers their commands, syncs to the specified guild, and exits. Slash commands appear in Discord within seconds.

**After first deploy, ongoing syncs** via `/sync <guild_id>` (owner only). The `bot.tree.copy_global_to(guild=guild)` call at line 510 copies all registered global commands to the guild before syncing — this is correct for per-guild deployment.

### `docker-compose.yml` reboot survival (D-09)

`restart: unless-stopped` is set on both services. `[VERIFIED: codebase docker-compose.yml:25, 48]`

The only missing piece: Docker itself must be enabled as a systemd service so it starts on VM reboot:

```bash
systemctl is-enabled docker    # should print "enabled"
# If not enabled:
sudo systemctl enable docker
```

### deploy.sh update workflow (D-13)

```bash
#!/bin/bash
# scripts/deploy.sh — update Dexter on Oracle (D-13)
set -euo pipefail

REPO_DIR="/opt/dexter"
cd "${REPO_DIR}"

echo "[deploy.sh] Pulling latest changes..."
git pull

echo "[deploy.sh] Rebuilding bot image (Postgres image is pinned — never rebuilt)..."
docker compose up -d --build bot

echo "[deploy.sh] Tailing logs (Ctrl+C to exit)..."
docker compose logs -f bot --tail=50 &
TAIL_PID=$!
sleep 15
kill ${TAIL_PID} 2>/dev/null || true

# Ping healthcheck to signal deploy complete (optional success signal)
if [ -n "${HEALTHCHECK_URL:-}" ]; then
    curl -fsS --max-time 10 "${HEALTHCHECK_URL}" > /dev/null 2>&1 || true
fi

echo "[deploy.sh] Deploy complete."
echo ""
echo "WARNING: NEVER run 'docker compose down -v' in production."
echo "That wipes the postgres_data, audio_cache, and logs volumes."
```

**Key design constraint confirmed:** `--build bot` rebuilds ONLY the bot service. `postgres:16-alpine` is a pinned image — it is never rebuilt. Named volumes (`postgres_data`, `audio_cache`, `logs`) survive `docker compose down` (without `-v`). Only `docker compose down -v` wipes them. This is the load-bearing safety constraint. `[VERIFIED: codebase docker-compose.yml:50-56]`

### ARM64 build note

`docker-compose.yml` specifies `platform: linux/arm64` for both services. `[VERIFIED: codebase docker-compose.yml:11, 33]`

On the Oracle A1 VM, `docker compose up -d --build bot` builds natively for arm64 — no cross-compilation, no `buildx` needed. This is correct and the recommended approach for Oracle Always-Free A1.

`python:3.11-slim-bookworm` has native arm64 support on Docker Hub. `postgres:16-alpine` has native arm64 support. `[ASSUMED: both images are currently available on Docker Hub for linux/arm64]`

### First-deploy sequence (D-10 secrets contract)

```bash
# On the Oracle VM:
cd /opt/dexter

# 1. Create .env from template
cp .env.example .env
nano .env        # fill in DISCORD_TOKEN, GEMINI_API_KEY, GENIUS_TOKEN, POSTGRES_PASSWORD, etc.
chmod 600 .env

# 2. Create ~/.pgpass for host-side pg_dump
echo "localhost:5432:dexter:dexter:YOUR_POSTGRES_PASSWORD" >> ~/.pgpass
chmod 600 ~/.pgpass

# 3. Configure OCI CLI (for backup.sh)
oci setup config    # interactive; creates ~/.oci/config

# 4. First boot
docker compose up -d

# 5. First-run command sync
python bot.py --first-run --guild <GUILD_ID>

# 6. Set up crontab
crontab -e
# Add:
# HEALTHCHECK_URL=https://hc-ping.com/<your-uuid>
# */5 * * * * /opt/dexter/scripts/keepalive.sh >> /var/log/dexter/keepalive.log 2>&1
# 0 */6 * * * /opt/dexter/scripts/backup.sh >> /var/log/dexter/backup.log 2>&1
```

### Troubleshooting table (D-11)

| Symptom | Probable Cause | Fix |
|---------|---------------|-----|
| `docker compose up` fails: `no matching manifest for linux/arm64` | Image doesn't have arm64 variant | Confirm you're on Oracle A1 (not a dev machine); check `uname -m` (should be `aarch64`) |
| Bot container exits immediately (exit code 1) | Missing or malformed `.env` | `docker compose logs bot` — look for "DISCORD_TOKEN not set" or asyncpg DSN errors |
| `healthcheck: starting` never becomes healthy | `pg_isready` failing inside postgres container | `docker compose logs postgres` — check for storage permissions or volume corruption |
| `pool-acquire timeout` in bot logs | Bot started before Postgres finished init | Already handled by `depends_on: service_healthy` — if it still happens, increase Postgres healthcheck `retries: 5` |
| Volume permission errors in logs | Docker named volume created with wrong ownership | `docker compose down; docker volume rm dexter_audio_cache; docker compose up -d` (audio_cache only — never postgres_data) |
| Slash commands not appearing in Discord | Command sync not run | `python bot.py --first-run --guild <GUILD_ID>` |
| `DISCORD_TOKEN` invalid / 401 | Stale token | Discord Developer Portal → Bot → Reset Token → update `.env` |
| `pg_dump` in backup.sh fails: `password authentication failed` | `~/.pgpass` not set or wrong permissions | `chmod 600 ~/.pgpass`; verify contents `cat ~/.pgpass` |
| `oci os object put` fails: `NotAuthenticated` | `~/.oci/config` not set or instance principal not configured | `oci iam region list` to test; re-run `oci setup config` |

---

## Focus Area 7: Live-UAT Runbook Consolidation — DEPLOY-02/03/05/08 (D-07)

### Source checklists enumerated

The 21 checks come from three source documents. After de-duplication (04-HUMAN-UAT items 2-6 are the same scenarios as 04-VERIFICATION items 1-6), the consolidated count is:

**Group A: Boot + Infra (6 checks)**

| # | Check | Source | Command/Action | Expected |
|---|-------|--------|---------------|----------|
| A1 | Docker clean boot | 04-VERIFICATION HV-1 + 04-HUMAN-UAT 2 | `docker compose up -d && docker compose logs -f bot` | Postgres healthcheck passes; bot logs "Dexter is ready."; startup message posts to guild |
| A2 | Reboot survival | 04-VERIFICATION + DEPLOY-01 | `systemctl is-enabled docker` → `sudo reboot` → wait 90s → check Discord for startup message | Bot comes back automatically; startup message reposted |
| A3 | Over-cap rejection | 04-VERIFICATION HV-3 + 04-HUMAN-UAT 4 | Set `MAX_QUEUE_SIZE_PER_GUILD=1` in .env, restart, `/play` twice | Second `/play` returns personality rejection; queue len stays 1 |
| A4 | Keepalive cron | 04-VERIFICATION HV-5 + 04-HUMAN-UAT 5 | Set crontab, wait 10 min, check Healthchecks.io dashboard | Green; "Last ping: X min ago" |
| A5 | Backup cron (manual run) | 04-VERIFICATION HV-6 + 04-HUMAN-UAT 6 | `bash scripts/backup.sh` | `dexter_YYYYMMDD_HHMMSS.dump` object appears in OCI bucket; exit 0 |
| A6 | Postgres integration tests | 04-VERIFICATION HV-4 | `pytest tests/test_database_phase4.py -x` against live `dexter_test` DB | 18 tests green |

**Group B: Queue persistence (2 checks)**

| # | Check | Source | Command/Action | Expected |
|---|-------|--------|---------------|----------|
| B1 | Queue persistence round-trip | 04-VERIFICATION HV-2 + 04-HUMAN-UAT 3 | `/play` a song; `docker compose restart bot`; `/queue` | Queue restored; smart-rejoin connects voice if humans present |
| B2 | clear_persisted on idle-leave | DEPLOY-06 (IN-02 fix) | Bot idles 10 min alone in voice; bot auto-leaves; restart bot; `/queue` | Queue is empty (not restored) — confirms clear_persisted fired |

**Group C: Behavioral — Discord live session (9 checks)**

| # | Check | Source | Action | Expected |
|---|-------|--------|--------|----------|
| C1 | Voice join roast | 03-VERIFICATION HV-1 | Join voice channel 5× | At least 1 roast fires (~30% chance) |
| C2 | Late-night roast | 03-VERIFICATION HV-1 | Join voice 1–5am (or temporarily patch `is_late_night` to always true for testing) | Roast fires at ~50% with late-night text |
| C3 | Startup message | 03-VERIFICATION HV-2 | `docker compose restart bot` | Personality startup message posts to DEXTER_CHANNEL_ID |
| C4 | Status rotation | 03-VERIFICATION HV-3 | Watch bot presence for 10+ min | Presence cycles through song/server-count/personality/seasonal |
| C5 | /lyrics | 03-VERIFICATION HV-4 | `/play` a popular song; `/lyrics` | Paginated embed with lyrics; buttons work; timeout disables buttons |
| C6 | /history | 03-VERIFICATION HV-5 | `/history` after queueing several songs | Paginated embed with song history |
| C7 | Message reactions | 03-VERIFICATION HV-6 | Post YT URL, type "gn", bare @Dexter, thank Dexter | 👀, 🫡, 😐, deflect text each fire |
| C8 | Repeat-song roast | 03-VERIFICATION HV-7 | Queue same song 3× | Roast fires on 3rd queue |
| C9 | Idle loneliness | 03-VERIFICATION HV-9 | Stay in voice, no commands, 30+ min | One loneliness message; does not repeat |

**Group D: Destructive — backup/restore (1 check, ALWAYS LAST)**

| # | Check | Source | Action | Expected |
|---|-------|--------|--------|----------|
| D1 | End-to-end restore proof | DEPLOY-07 D-15 | `python scripts/seed_restore_test.py` | Seed rows written; backup uploaded; restored into `dexter_restore_test`; row counts match; throwaway DB dropped |

**Runbook order: A → B → C → D**. Destructive (D) is last because a failed restore cannot corrupt A/B/C results (throwaway DB is isolated). The `docker compose down -v` landmine warning must appear prominently at the top of the runbook.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Timezone-aware time | Custom UTC offset math | `ZoneInfo(config.STREAK_TIMEZONE)` + `datetime.now(tz=...)` | Already in codebase; handles DST |
| Queue state restore guard | Custom "is voice ready" polling | `VoiceClient.is_connected()` immediately after `connect()` | discord.py contract: connect() resolves when WS is established |
| Backup file rotation | Custom cleanup cron | OCI Object Storage lifecycle policy | Managed service; zero code; free |
| tasks.loop UTC alignment | Manual UTC conversion | `datetime.time(hour=4, tzinfo=ZoneInfo(...))` | Documented discord.py pattern — naive time = UTC |
| pg_dump version mismatch | Host-side pg_restore | `docker compose exec postgres pg_restore` | Runs pg_restore at the same version as pg_dump server |

---

## Runtime State Inventory

> Phase 5 is not a rename/refactor phase. The only runtime state that matters is: does the live DB survive the deploy unchanged?

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Postgres `guild_queues` table (queue state), `song_history`, `user_profiles`, `user_artist_counts` | None — named volume `postgres_data` survives `docker compose down && up`; only `docker compose down -v` would wipe it (explicitly forbidden) |
| Live service config | Discord slash command registrations (per-guild) | `--first-run --guild <id>` syncs commands once on first deploy |
| OS-registered state | No systemd services for the bot itself (Docker handles restart). `systemctl enable docker` required. | Enable docker service on Oracle VM |
| Secrets/env vars | `.env` on Oracle VM host (not in git); `~/.pgpass`; `~/.oci/config` | Must be created manually on VM per D-10 |
| Build artifacts | Docker images on Oracle VM (not in registry) | First deploy builds fresh from source; subsequent `--build bot` only rebuilds bot layer |

---

## Common Pitfalls

### Pitfall 1: `docker compose down -v` in production

**What goes wrong:** Wipes all three named volumes including `postgres_data` — complete database loss. No recovery unless OCI backup is recent.

**Why it happens:** Developers instinctively run `down -v` to "clean up". In dev it's fine; in prod it's catastrophic.

**How to avoid:** The `deploy.sh` script NEVER calls `docker compose down -v`. Runbook carries a red-box warning at the top. Only `docker compose restart bot` or `docker compose up -d --build bot` for updates.

**Warning signs:** If someone asks "should I run `docker compose down -v`?" — the answer is always NO in production.

### Pitfall 2: tasks.loop(time=) with naive datetime.time fires at UTC, not host local

**What goes wrong:** If the VM timezone is America/New_York, `@tasks.loop(time=datetime.time(hour=4, minute=0))` still fires at 04:00 UTC (11pm/midnight ET) — not 4am ET. For `events.py:197` the equivalent is `datetime.now().hour` returns host local time, not TZ-aware time.

**Why it happens:** discord.py documentation states: "If no tzinfo is given then UTC is assumed." `datetime.datetime.now()` returns naive local time. These two naive calls are semantically different.

**How to avoid:** Always pass `tzinfo=ZoneInfo(config.STREAK_TIMEZONE)` to `datetime.time()` in tasks.loop; use `datetime.now(tz=ZoneInfo(config.STREAK_TIMEZONE)).hour` for wall-clock comparisons.

**Warning signs:** Late-night roasts fire at wrong hours; yt-dlp update fires mid-evening ET.

### Pitfall 3: Smart-rejoin calls `_play_track` before voice WS is ready

**What goes wrong:** `queue_persistence.py` calls `await vc_channel.connect()` then immediately `await music_cog._play_track(guild, current)`. In practice `connect()` awaiting the WS handshake is sufficient, but under load a race is possible where `guild.voice_client` is briefly None or `is_connected()` is False.

**Why it happens:** `connect()` returns a `VoiceClient` but `guild.voice_client` is set by discord.py's internal state machine. If there's a race between this and another concurrent `on_voice_state_update` event, the state may flicker.

**How to avoid:** The fix (D-02) adds `if not vc.is_connected(): return` after `await vc_channel.connect()`. `_play_track` already has its own guard. The diagnostic logging (D-03) will surface this in logs if it still happens.

### Pitfall 4: pg_restore version mismatch (host pg_restore vs container pg_dump)

**What goes wrong:** Running `pg_restore` from the host OS against a dump produced by postgres:16-alpine inside Docker. If the host has a different PostgreSQL client version (common on Ubuntu/Debian with backport PPAs), pg_restore will warn about version mismatch and may fail on format features.

**Why it happens:** `backup.sh` currently requires `postgresql-client` on the host. If the host has postgres 14 client and the container is postgres 16 server, the dump format diverges.

**How to avoid:** Run `pg_restore` inside the container via `docker compose exec postgres pg_restore ...`. This guarantees version parity. The restore-verify script should use this pattern.

### Pitfall 5: Backup pipe masks pg_dump failure (WR-07)

**What goes wrong:** `pg_dump ... | oci os object put --file - --force`. If pg_dump exits with an error but oci-cli still receives partial data and exits 0, `set -e` won't catch the failure. OCI bucket contains a corrupt dump.

**Why it happens:** In bash pipelines, the exit code is that of the last command by default. Even with `set -o pipefail`, if oci-cli returns 0 on partial writes, the error is swallowed.

**How to avoid:** The restore-verify script (D-15) validates the dump by actually restoring it. For routine backup integrity, add `|| exit 1` to the pg_dump side, or dump to a temp file first, check size, then upload.

### Pitfall 6: clear_persisted missing on idle-leave causes ghost queue on restart

**What goes wrong:** Bot idle-leaves; queue is cleared in memory; on next boot, `restore_queues` finds the persisted row in `guild_queues` and restores the queue — including smart-rejoin. Bot rejoins voice and tries to play a track from a "cleared" session.

**Why it happens:** `bot.py:399` calls `queue.clear()` but not `clear_persisted()` (IN-02). This is the exact bug DEPLOY-06 fixes.

**How to avoid:** Apply the D-05 fix. Verify via runbook check B2.

---

## Code Examples

### Pattern: ZoneInfo-aware hour check

```python
# Source: codebase database.py:19-26 (get_local_date pattern) + Context7 discord.py
from zoneinfo import ZoneInfo
import datetime
import config

# Correct — consistent with STREAK_TIMEZONE everywhere:
local_hour = datetime.datetime.now(tz=ZoneInfo(config.STREAK_TIMEZONE)).hour

# Correct — tasks.loop at 4am ET:
utc = datetime.timezone.utc
_ET = ZoneInfo(config.STREAK_TIMEZONE)
@tasks.loop(time=datetime.time(hour=4, minute=0, tzinfo=_ET))
async def ytdlp_update():
    ...
```

### Pattern: clear_persisted on queue clear

```python
# Source: codebase cogs/music.py:977-984 (the correct /stop template)
queue._play_generation += 1  # invalidate stale after-callbacks
queue.clear()
if hasattr(self.bot, "queue_persistence"):
    await self.bot.queue_persistence.clear_persisted(guild.id)
```

### Pattern: is_connected guard in smart-rejoin

```python
# Source: codebase services/queue_persistence.py:146-152 (the fix)
vc = await vc_channel.connect()
if not vc.is_connected():
    log.warning("Smart rejoin: vc not connected post-connect() guild=%s", guild_id)
    return
await music_cog._play_track(guild, current)
```

### Pattern: OCI lifecycle policy apply

```bash
# Source: https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usinglifecyclepolicies.htm
NAMESPACE=$(oci os ns get --query 'data' --raw-output)
oci os object-lifecycle-policy put \
  --namespace-name "${NAMESPACE}" \
  --bucket-name dexter-backups \
  --items '[{"name":"delete-old-backups","action":"DELETE","isEnabled":true,"timeAmount":14,"timeUnit":"DAYS","objectNameFilter":{"inclusionPrefixes":["dexter_"]}}]'
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `datetime.datetime.now()` for host-local TZ | `datetime.now(tz=ZoneInfo(tz_name))` | Python 3.9+ (ZoneInfo stdlib) | Consistent DST-aware timezone; no pytz dependency |
| Naive `time()` in tasks.loop | `datetime.time(hour=H, tzinfo=ZoneInfo(...))` | discord.py >=2.0 (added `time=` parameter) | Fires at correct wall-clock hour in target TZ |
| Host-side pg_restore | `docker compose exec postgres pg_restore` | Docker Compose patterns | Version-matched restore; no extra packages on host |

**Deprecated/outdated:**
- `datetime.timezone.utc` approach for tasks.loop: works, but `ZoneInfo` is cleaner for named timezones
- `*/30 * * * *` backup cadence: superceded by D-14's `0 */6 * * *` — 48/day was overkill

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `python:3.11-slim-bookworm` and `postgres:16-alpine` both have current arm64 Docker Hub images | Deploy Mechanics | Image pull fails on Oracle A1; workaround: use `arm64v8/python:3.11-slim-bookworm` base explicitly |
| A2 | OCI Always-Free 20GB bucket stays under capacity with 4 dumps/day × 14 days | Backup/Restore | If Dexter DB grows unexpectedly, lifecycle rule is safety net; current DB is start-fresh/near-empty |
| A3 | `oci-cli` is already installed on the Oracle VM (Phase 4 prerequisite) | Deploy Mechanics | If not installed: `pip install oci-cli` or Oracle docs install script |
| A4 | Oracle VM is accessible via SSH and has `git`, `docker`, `docker compose` installed | Deploy Mechanics | Phase 4 D-07 established Oracle A1 hosting; these are standard Phase 4 prerequisites |

---

## Open Questions

1. **yt-dlp loop timezone (D-06 Claude's discretion)**
   - What we know: `bot.py:467` uses naive `datetime.time(hour=4, minute=0)` — fires at 04:00 UTC. If VM is set to America/New_York, this is ~11pm–midnight ET — quiet hours, acceptable for a maintenance task.
   - What's unclear: Whether the user wants this to fire at 4am ET (matching the spec) or 4am UTC is fine.
   - Recommendation: Apply `tzinfo=ZoneInfo(config.STREAK_TIMEZONE)` for spec compliance — it's a one-line change with zero risk.

2. **Healthchecks.io check period**
   - What we know: keepalive.sh runs every 5 minutes. Healthchecks.io period should be set to 5 minutes with 10-minute grace.
   - What's unclear: Whether the user's Healthchecks.io free tier supports 5-minute period checks (free tier may limit to 20-minute minimum for some plans).
   - Recommendation: If 5-minute is not available on free tier, set period to 10 minutes and update the cron to `*/10 * * * *` — still satisfies DEPLOY-08.

3. **Oracle VM PostgreSQL client version**
   - What we know: `backup.sh` uses host-side `pg_dump` (not docker exec). The host may not have `postgresql-client-16` — could have an older version.
   - What's unclear: Current state of `postgresql-client` on the Oracle VM.
   - Recommendation: Runbook includes `pg_dump --version` check step; if version < 16, install `postgresql-client-16`: `sudo apt-get install -y postgresql-client-16`.

---

## Environment Availability

| Dependency | Required By | Available (dev machine) | Version | Fallback |
|------------|------------|---------|---------|----------|
| Docker | Deploy mechanics | ✓ | 29.4.3 | — |
| Python 3.12 | Running tests locally | ✓ | 3.12 | — |
| pytest | Unit tests | ✓ | 9.0.3 | — |
| Postgres (live) | test_database_phase4.py + DEPLOY-05 | ✗ | — | Oracle VM only |
| Discord gateway (live) | All behavioral checks | ✗ | — | Oracle VM only |
| Oracle A1 SSH | All deploy checks | ✗ | — | User only |
| oci-cli | backup.sh, lifecycle policy | ✗ | — | Oracle VM (assumed installed from Phase 4) |

**Missing dependencies with no fallback on dev machine:**
- Live Postgres (DEPLOY-05, all behavioral checks requiring DB)
- Discord gateway (all behavioral + roast checks)
- Oracle A1 SSH access (all deploy + infra checks)

All three are user-only steps — this is expected and is the entire rationale for the asymmetric labor split (D-01).

---

## Validation Architecture

> Nyquist validation is ENABLED (`workflow.nyquist_validation` absent from config.json → defaults enabled).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | none (default discovery) |
| Quick run command | `pytest tests/test_queue.py tests/test_streak.py tests/test_roasts.py tests/test_seasonal.py tests/test_message_buffer.py tests/test_formatters.py tests/test_responses.py tests/test_server_state.py tests/test_prompts.py -q` |
| Full suite command | `pytest tests/ -q` (125 pure tests pass; test_database_phase4.py requires live Postgres; test_ytdlp_selfheal.py has pre-existing failure) |

### Phase 5 Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | Notes |
|--------|----------|-----------|-------------------|-------|
| DEPLOY-01 | Bot + Postgres boot on Oracle A1 via Docker Compose; survives reboot | Live-UAT only | N/A | Requires Oracle A1, Docker, real DISCORD_TOKEN — dev machine cannot run |
| DEPLOY-02 | 9 Phase-3 behavioral checks pass | Live-UAT only | N/A | Requires live Discord gateway + voice channels + probabilistic events |
| DEPLOY-03 | 6 Phase-4 human UAT scenarios pass | Live-UAT only | N/A | Requires Oracle A1 + live Discord |
| DEPLOY-04 | Reconnect race fix: `is_connected()` guard at queue_persistence.py:147 | Structural review (provable by inspection) + Live-UAT | `pytest tests/test_queue.py -q` (confirms _play_generation invariant) | The race itself is live-concurrency only; the guard is provable from reading the code |
| DEPLOY-05 | Queue + position survive restart; smart-rejoin works | Live-UAT only | N/A | Requires live Discord bot + Postgres |
| DEPLOY-06 | `clear_persisted()` fires on idle-leave and reconnect-failure | Structural review (code insertion) + Live-UAT (B2) | N/A for pure test; syntax check via `python -m py_compile bot.py cogs/music.py` | Logic is not unit-testable (requires Discord voice state events); B2 runbook check validates live |
| DEPLOY-07 | pg_dump backup runs; restore verified end-to-end | Seed/restore-verify script (partially unit-testable) + Live-UAT | Pure parts: `python -m pytest tests/` (pure helpers); restore script run manually by user on Oracle | The seed row counts and verification logic can be tested with a live Postgres connection; the OCI upload/download cannot |
| DEPLOY-08 | Keepalive cron fires in production; Healthchecks.io shows green | Live-UAT only | N/A | Requires Oracle VM crontab + live Healthchecks.io account |

### What IS unit-testable in Phase 5

| Logic | Test File | Current Status |
|-------|-----------|----------------|
| `ZoneInfo(config.STREAK_TIMEZONE)` hour computation (TZ fix correctness) | `tests/test_streak.py` (existing) | 7 tests pass — covers the pattern |
| `_play_generation` stale-callback invariant | `tests/test_queue.py` (existing) | Covered by queue unit tests (125 pass) |
| New TZ smoke test: `datetime.now(tz=ZoneInfo("America/New_York")).hour in range(0, 24)` | `tests/test_streak.py` (add 1 test) | ✅ Wave 0 gap — trivial to add |
| Seed data shape validation (pure data-construction logic) | `tests/test_seed_restore.py` (new) | ✅ Wave 0 gap — pure Python, no DB needed |

### What is NOT unit-testable (live-UAT only)

- Reconnect race behavior under live Discord concurrency (network, gateway timing)
- Voice channel join/leave events and roast probability
- `clear_persisted()` interaction with actual Postgres `guild_queues` table
- Docker Compose boot sequence on Oracle A1
- pg_dump + OCI Object Storage round-trip
- Healthchecks.io ping reception
- Slash command sync to Discord guild

### Sampling Rate

- **Per task commit (dev machine):** `pytest tests/test_queue.py tests/test_streak.py tests/test_roasts.py tests/test_seasonal.py tests/test_prompts.py -q` (fast subset)
- **Per wave merge:** Full pure-unit suite: `pytest tests/ -q --ignore=tests/test_database_phase4.py` (125+ tests)
- **Phase gate:** Full suite green on dev machine + all 21 live UAT checks passing on Oracle A1 before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_streak.py` — add 1 test: `test_tz_aware_hour_is_integer()` covering `datetime.now(tz=ZoneInfo(STREAK_TIMEZONE)).hour` returns int in [0,23]
- [ ] `tests/test_seed_restore.py` — new file with pure tests for seed data structure (row shapes, no DB connection)

*(All existing test infrastructure is in place; no new framework setup needed)*

---

## Security Domain

> `security_enforcement` not set in config.json → defaults enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Discord token is the auth layer; handled at bot init |
| V3 Session Management | No | Stateless bot; no session cookies |
| V4 Access Control | Yes | Owner-only `/sync` command guarded by `interaction.user.id != bot.owner_id` check `[VERIFIED: bot.py:356]` |
| V5 Input Validation | Yes | `.env` values validated at config import (empty → None); no user-controlled SQL in code changes |
| V6 Cryptography | No | No new crypto; Postgres password stored in `.pgpass` (chmod 600) and Docker env, never logged |

### Known Threat Patterns for this phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Plaintext secrets in `.env` committed to git | Information Disclosure | `.gitignore` excludes `.env`; verified in `.dockerignore` `[VERIFIED: codebase .dockerignore]` |
| Docker image contains secret literals | Information Disclosure | `Dockerfile` has no `ENV TOKEN=...` literals; all secrets via `env_file: .env` at runtime `[VERIFIED: codebase Dockerfile]` |
| `pg_dump` password in shell history / crontab | Information Disclosure | Use `~/.pgpass` (chmod 600); PGPASSWORD in crontab env block (not inline command) |
| Owner `/sync` command accessible to non-owners | Elevation of Privilege | `interaction.user.id != bot.owner_id` guard in place `[VERIFIED: bot.py:356]` |
| OCI backup accessible without auth | Information Disclosure | OCI Object Storage bucket is private by default; auth via `~/.oci/config` API key or instance principal |

---

## Sources

### Primary (HIGH confidence)
- `[VERIFIED: codebase]` — All code inspection findings: `cogs/music.py`, `bot.py`, `services/queue_persistence.py`, `cogs/events.py`, `config.py`, `docker-compose.yml`, `Dockerfile`, `scripts/backup.sh`, `scripts/keepalive.sh`, `.env.example`
- `[VERIFIED: Context7 /websites/discordpy_readthedocs_io_en]` — discord.py VoiceClient API, tasks.loop `time=` UTC behavior, `connect()` semantics
- `[CITED: https://www.postgresql.org/docs/current/app-pgrestore.html]` — pg_restore flags: `--no-owner`, `--no-acl`, `--format`, `-d`, exit codes
- `[CITED: https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usinglifecyclepolicies.htm]` — OCI Object Storage lifecycle policy structure and oci-cli command

### Secondary (MEDIUM confidence)
- `[CITED: https://github.com/oracle/oci-cli/blob/master/services/object_storage/examples_and_test_scripts/write_object_lifecycle_policy.sh]` — OCI lifecycle policy JSON schema example
- `[CITED: https://johnsturgeon.me/2024/07/01/discord-bot-healthcheck/]` — Healthchecks.io setup flow (check creation, period/grace, ping URL format)
- `[CITED: https://healthchecks.io/docs/]` — Ping URL format: `https://hc-ping.com/<uuid>`; integration types including Discord and email

### Tertiary (LOW confidence / ASSUMED)
- `[ASSUMED]` — Docker Hub arm64 image availability for `python:3.11-slim-bookworm` and `postgres:16-alpine` (highly likely given Oracle A1 market share, but not verified via registry API in this session)
- `[ASSUMED]` — `oci-cli` is installed on the Oracle VM from Phase 4 work (backup.sh was written for Phase 4 and requires it)

---

## Metadata

**Confidence breakdown:**
- Reconnect race fix: HIGH — provable from code inspection; discord.py API confirmed via Context7
- clear_persisted fix: HIGH — exact code locations confirmed; template verified; async context verified
- Timezone fix: HIGH — discord.py UTC behavior confirmed via Context7; ZoneInfo pattern verified in existing codebase
- Backup/restore: HIGH — pg_restore flags from official Postgres docs; OCI lifecycle from official Oracle docs; docker exec pattern from community docs
- Healthchecks.io setup: MEDIUM — official docs confirmed ping URL pattern and integration types; step-by-step Discord webhook setup is console-click-through (documented from external guide)
- Deploy mechanics: HIGH — all infra files verified from codebase

**Research date:** 2026-06-12
**Valid until:** 2026-07-12 (stable stack; discord.py and asyncpg APIs rarely change)
