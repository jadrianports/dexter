# Phase 5: Ship It Live - Pattern Map

**Mapped:** 2026-06-12
**Files analyzed:** 10 (5 modified Python, 2 modified shell scripts, 3 new files)
**Analogs found:** 10 / 10

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `cogs/music.py` (reconnect path 1194-1210 + _play_track 346-370) | service/controller | event-driven | `cogs/music.py:977-984` (stop command) | exact — same queue/generation pattern |
| `cogs/music.py` (clear_persisted gap at 1206) | service | CRUD | `cogs/music.py:977-984` | exact — template is in the same file |
| `bot.py` (clear_persisted gap at 399) | service | event-driven | `cogs/music.py:977-984` | role-match — same operation, different call site |
| `bot.py` (yt-dlp loop TZ at 467) | config/task | batch | `database.py:19-26` (get_local_date) | role-match — same ZoneInfo pattern |
| `cogs/events.py` (late-night TZ at 197) | service | event-driven | `database.py:19-26` (get_local_date) | exact — same ZoneInfo + STREAK_TIMEZONE pattern |
| `services/queue_persistence.py` (smart-rejoin guard at 147) | service | request-response | `cogs/music.py:311,365` (is_connected guards) | exact — same guard idiom applied to same method |
| `config.py` (any new constants) | config | — | `config.py:57-89` (existing constants block) | exact — single-file constant pattern |
| `scripts/deploy.sh` (new) | utility/script | batch | `scripts/keepalive.sh` + `scripts/backup.sh` | exact — shell conventions, env wiring |
| `scripts/backup.sh` (cadence change only) | utility/script | batch | `scripts/backup.sh` itself | exact — comment + cron expression update |
| `scripts/seed_restore_test.py` (new) | test/utility | CRUD | `tests/test_streak.py` (structure) + `scripts/backup.sh` (pg/docker invocation pattern) | role-match |
| `tests/test_seed_restore.py` (new) | test | transform | `tests/test_streak.py` | exact — class-based pytest, pure functions, no DB fixture |
| Live-UAT runbook (new markdown) | documentation | — | `.planning/phases/04-scale/04-HUMAN-UAT.md` + `04-VERIFICATION.md` | exact — ordered checklist with expected/result fields |

---

## Pattern Assignments

### `cogs/music.py` — reconnect path diagnostic logging (lines 1194-1210)

**Analog:** `cogs/music.py:977-984` (stop command) + existing log calls in the same method

**Current code (lines 1194-1210) — what exists:**
```python
for attempt in range(3):
    try:
        await asyncio.sleep(1)
        vc = await before.channel.connect()
        track = queue.get_current()
        if track:
            await self._play_track(member.guild, track)
            log.info(f"Reconnected and restarted track in guild {member.guild.id}")
        return
    except Exception as e:
        log.error(f"Reconnect attempt {attempt + 1} failed: {e}")

queue.clear()   # <-- MISSING: clear_persisted() and _play_generation increment
```

**What to add / change — D-02 + D-03 + D-05:**
```python
for attempt in range(3):
    try:
        await asyncio.sleep(1)
        log.info("reconnect attempt %d/3 in guild %d", attempt + 1, member.guild.id)
        vc = await before.channel.connect()
        log.info(
            "reconnect: vc.is_connected()=%s gen=%d guild=%d",
            vc.is_connected(), queue._play_generation, member.guild.id
        )
        track = queue.get_current()
        if track:
            await self._play_track(member.guild, track)
            log.info(f"Reconnected and restarted track in guild {member.guild.id}")
        return
    except Exception as e:
        log.error(f"Reconnect attempt {attempt + 1} failed: {e}")

# D-05 fix: mirror the /stop template (cogs/music.py:977-984)
queue._play_generation += 1
queue.clear()
if hasattr(self.bot, "queue_persistence"):
    await self.bot.queue_persistence.clear_persisted(member.guild.id)
```

**CRITICAL constraint from CLAUDE.md gotcha:** Do NOT call `voice_client.stop()` before `_play_track()`. The existing `_play_track` already handles `stop()` internally (line 362-363). Callers must only call `_play_track` — never `stop()` then `_play_track()`. The reconnect path already obeys this (it calls `_play_track` directly); the fix must not change that call order.

**Log level rule (D-03):** Use `log.INFO` on reconnect-path events (low frequency); `log.DEBUG` on hot per-play events (lines 346-370 inside `_play_track`). Do not add INFO-level logs inside `_play_track` — that fires on every song.

---

### `cogs/music.py` — _play_track diagnostic logging (lines 346-375)

**Analog:** Same file — the `after_callback` and `voice_client.play()` block

**Current code (lines 346-375):**
```python
queue._play_generation += 1
current_gen = queue._play_generation

def after_callback(error):
    ...

try:
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
    if not voice_client.is_connected():
        source.cleanup()
        queue.is_playing = False
        return
    voice_client.play(source, after=after_callback)
    log.info(f"Playing '{track.title}' in guild {guild.id}")
```

**Add DEBUG logs (D-03) — DEBUG level only, not INFO:**
```python
log.debug("gen=%d → %d in guild %d", queue._play_generation, queue._play_generation + 1, guild.id)
queue._play_generation += 1
current_gen = queue._play_generation

# ... after_callback unchanged ...

try:
    if voice_client.is_playing() or voice_client.is_paused():
        log.debug("stopping current playback gen=%d in guild %d", queue._play_generation, guild.id)
        voice_client.stop()
    if not voice_client.is_connected():
        source.cleanup()
        queue.is_playing = False
        return
    voice_client.play(source, after=after_callback)
    log.debug(
        "play() called gen=%d connected=%s guild=%d",
        current_gen, voice_client.is_connected(), guild.id
    )
    log.info(f"Playing '{track.title}' in guild {guild.id}")
```

---

### `bot.py` — clear_persisted gap at line 399 (idle-leave path)

**Analog:** `cogs/music.py:977-984` — the already-correct `/stop` template

**Template (analog, lines 977-984):**
```python
queue._play_generation += 1  # invalidate any pending after-callbacks
queue.clear()
if hasattr(self.bot, "queue_persistence"):
    await self.bot.queue_persistence.clear_persisted(interaction.guild.id)
```

**Current code at bot.py:395-403:**
```python
if vc._idle_seconds >= config.IDLE_TIMEOUT_SECONDS:
    log.info(f"Idle timeout in guild {guild.id}, disconnecting")
    vc.stop()
    await vc.disconnect()
    queue.clear()              # <-- gap: clear_persisted missing

    channel = music_cog._get_text_channel(guild)
    if channel:
        await channel.send("Left the voice channel after being alone for too long.")
```

**Fix — insert before `queue.clear()`:**
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

**Scope note:** In `bot.py`'s idle_check task, `bot` is the top-level `commands.Bot` instance (not `self.bot`). `queue_persistence` is set on `bot` in `_initialize_once()` before any task fires. `clear_persisted` is `async` — must be `await`ed.

---

### `bot.py` — yt-dlp tasks.loop TZ at line 467

**Analog:** `database.py:6,19-26` (ZoneInfo import + usage pattern)

**ZoneInfo pattern from database.py:**
```python
from zoneinfo import ZoneInfo
# ...
def get_local_date(tz_name: str) -> date:
    return datetime.now(tz=ZoneInfo(tz_name)).date()
```

**Current code at bot.py:467:**
```python
@tasks.loop(time=datetime.time(hour=4, minute=0))
async def ytdlp_update():
    ...
```

**Fix — make TZ-explicit (D-06, recommended by RESEARCH.md):**
```python
from zoneinfo import ZoneInfo as _ZoneInfo
_ET = _ZoneInfo(config.STREAK_TIMEZONE)

@tasks.loop(time=datetime.time(hour=4, minute=0, tzinfo=_ET))
async def ytdlp_update():
    ...
```

**Why:** discord.py treats naive `datetime.time` as UTC (confirmed via Context7). With VM timezone set to America/New_York, this fires at midnight ET instead of 4am ET. One-line change with zero risk.

---

### `cogs/events.py` — naive late-night time at line 197

**Analog:** `database.py:6,19-26` — the authoritative ZoneInfo + STREAK_TIMEZONE pattern

**Analog code (database.py:6 + 19-26):**
```python
from zoneinfo import ZoneInfo
import config

def get_local_date(tz_name: str) -> date:
    return datetime.now(tz=ZoneInfo(tz_name)).date()
```

**Current code (events.py:193-197):**
```python
hour = discord.utils.utcnow().hour  # Use UTC; late-night check uses local hour below

# Use the member's local guild time via Python's datetime
import datetime as _dt
local_hour = _dt.datetime.now().hour  # local server time for late-night check
```

**Fix:**
```python
import datetime as _dt
from zoneinfo import ZoneInfo as _ZoneInfo
local_hour = _dt.datetime.now(tz=_ZoneInfo(config.STREAK_TIMEZONE)).hour
```

**Convention:** `ZoneInfo` is already imported in `database.py`. In `events.py`, import it with a local alias (`_ZoneInfo`) to match the `_dt` alias style already present in the file. Use `config.STREAK_TIMEZONE` (line 58 of config.py: `"America/New_York"`) — do not hardcode the string.

---

### `services/queue_persistence.py` — smart-rejoin voice race at line 147

**Analog:** `cogs/music.py:311` and `cogs/music.py:365` — the two existing `is_connected()` guards inside `_play_track`

**Analog pattern (music.py:311):**
```python
voice_client = guild.voice_client
if not voice_client or not voice_client.is_connected():
    return
```

**Analog pattern (music.py:365):**
```python
if not voice_client.is_connected():
    source.cleanup()
    queue.is_playing = False
    return
```

**Current code (queue_persistence.py:146-152):**
```python
try:
    await vc_channel.connect()
    await music_cog._play_track(guild, current)
except Exception as exc:
    log.warning(
        "Smart rejoin failed for guild %s: %s", guild_id, exc
    )
```

**Fix — D-02 paranoia guard + D-03 diagnostic log:**
```python
try:
    vc = await vc_channel.connect()
    log.info(
        "smart-rejoin: connected=%s guild=%s", vc.is_connected(), guild_id
    )
    if not vc.is_connected():
        log.warning(
            "Smart rejoin: vc not connected post-connect() guild=%s", guild_id
        )
        return
    await music_cog._play_track(guild, current)
except Exception as exc:
    log.warning(
        "Smart rejoin failed for guild %s: %s", guild_id, exc
    )
```

**Key:** `connect()` returns the `VoiceClient` object — capture it as `vc` (not discarded). The `is_connected()` check after `connect()` is a paranoia guard for the WR-03 race; under normal conditions it is always True immediately post-`await connect()`.

---

### `config.py` — any new constants

**Analog:** `config.py:56-89` — existing constant block with env-var overrides

**Existing pattern (config.py:57-58):**
```python
DEXTER_CHANNEL_ID = int(os.getenv("DEXTER_CHANNEL_ID") or "0") or None
STREAK_TIMEZONE = os.getenv("STREAK_TIMEZONE") or "America/New_York"  # IANA tz; override via env
```

**Convention:**
- Group by feature (comment header like `# --- Phase N: Feature ---`)
- Env-var constants: `NAME = os.getenv("NAME") or "default"`
- Integer env-vars: `NAME = int(os.getenv("NAME") or "0") or None`
- Secrets: always from env, never hardcoded
- Only add a constant when the feature is implemented — no speculative constants

No new constants are required for Phase 5 unless the planner decides to parameterize backup cadence or lifecycle retention. If so, follow the `os.getenv("BACKUP_CADENCE_HOURS") or "6"` pattern.

---

### `scripts/deploy.sh` (new file)

**Analog:** `scripts/keepalive.sh` (shell conventions) + `scripts/backup.sh` (structure, comments, env wiring)

**Shell conventions from both analogs:**
```bash
#!/bin/bash
# scripts/<name>.sh — <purpose> (D-XX)
#
# PURPOSE:
#   ...
#
# DEPLOYMENT:
#   ...
#
# ENVIRONMENT:
#   HEALTHCHECK_URL must be set in the crontab environment...
#
# SECURITY: no secrets are hardcoded here (T-04-05)

set -euo pipefail     # backup.sh uses this; keepalive.sh uses set -uo pipefail
                      # deploy.sh should use set -euo pipefail (abort on any error)
```

**Critical patterns:**
1. `set -euo pipefail` — abort on error, undefined vars, pipeline failures
2. Env vars read from environment (not sourced from `.env`)
3. `|| true` for non-fatal operations (curl healthcheck ping — same as keepalive.sh:31)
4. Loud `WARNING:` echo for the `docker compose down -v` landmine
5. `--build bot` not `--build` — only rebuilds the bot image, never Postgres

**Healthcheck ping pattern (keepalive.sh:31):**
```bash
curl -fsS --max-time 10 "${HEALTHCHECK_URL}" > /dev/null 2>&1 || true
```

---

### `scripts/backup.sh` — cadence change only (D-14)

**This file needs only two edits:**

1. Line 12 comment: change `*/30 * * * *` → `0 */6 * * *`
2. No functional code changes — the pg_dump + OCI upload pipeline is unchanged

**The user also needs to update their crontab** (not in the script itself):
```
# Old:  */30 * * * * /opt/dexter/scripts/backup.sh
# New:   0 */6 * * * /opt/dexter/scripts/backup.sh
```

---

### `scripts/seed_restore_test.py` (new file)

**Analog:** `scripts/backup.sh` for pg/docker invocation style; `tests/test_streak.py` for data shape assertions

**Key patterns from backup.sh:**
- `BUCKET = "dexter-backups"` — literal constant at top of file
- `TIMESTAMP = ...` — `date +%Y%m%d_%H%M%S` style naming (translate to Python `datetime.now().strftime`)
- `docker compose exec postgres` for DB operations inside the container (avoids pg_restore version mismatch)

**Script design (from RESEARCH.md Focus Area 4):**
```python
#!/usr/bin/env python3
"""D-15: Seed known rows → backup → restore into throwaway DB → verify → teardown.
Never touches the live dexter DB during restore; throwaway is dexter_restore_test.
"""
import asyncio
import subprocess
import asyncpg
import config

SEED_USER_ID = "999999999999999999"  # obviously-fake snowflake
THROWAWAY_DB = "dexter_restore_test"

async def seed(conn):
    # INSERT known rows — user_profiles, song_history, user_artist_counts
    ...

async def verify(conn):
    # SELECT COUNT(*) per table, assert == seeded counts
    ...

async def main():
    # 1. connect to live DB, seed
    # 2. subprocess.run(["bash", "scripts/backup.sh"])
    # 3. docker compose exec postgres createdb -U dexter -T template0 dexter_restore_test
    # 4. download latest dump from OCI; pipe into container via stdin
    # 5. docker compose exec -T postgres pg_restore -U dexter -d dexter_restore_test --no-owner
    # 6. connect to throwaway DB, verify row counts
    # 7. docker compose exec postgres dropdb -U dexter dexter_restore_test
```

**LANDMINE:** restore must use `docker compose exec postgres pg_restore` (not host-side pg_restore) to avoid pg_restore version mismatch (Pitfall 4 in RESEARCH.md).

---

### `tests/test_seed_restore.py` (new file — Wave 0 pure tests)

**Analog:** `tests/test_streak.py` — class-based pytest, pure functions, no DB connection, no mocking framework

**Pattern from test_streak.py (lines 1-60):**
```python
"""Tests for <thing>. These tests do NOT use asyncpg — <functions> are
pure functions (no DB, no Discord objects) and must stay that way.
"""
from datetime import timedelta
import pytest
from database import compute_streak, get_local_date

TZ = "America/New_York"

class TestGetLocalDate:
    def test_returns_date_object(self):
        ...
    def test_matches_datetime_now_tz(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        expected = datetime.now(tz=ZoneInfo(TZ)).date()
        result = get_local_date(TZ)
        assert result == expected
```

**Apply to test_seed_restore.py:**
- Class `TestSeedData` — validate shape/structure of the seed row dicts (user_id type, count values, no DB needed)
- Class `TestTzAwareHour` — the Wave 0 gap: `datetime.now(tz=ZoneInfo("America/New_York")).hour in range(0, 24)`
- No `pytest.mark.asyncio` or `asyncpg` fixtures in the pure test file — those belong in the script itself
- Follow the docstring convention: "These tests do NOT use asyncpg..."

**The TZ smoke test (Wave 0 gap, can go in test_streak.py or test_seed_restore.py):**
```python
def test_tz_aware_hour_is_integer():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    hour = datetime.now(tz=ZoneInfo("America/New_York")).hour
    assert isinstance(hour, int)
    assert 0 <= hour <= 23
```

---

### Live-UAT Runbook (new markdown file)

**Analog:** `.planning/phases/04-scale/04-HUMAN-UAT.md` (status frontmatter + ordered test list) + `.planning/phases/04-scale/04-VERIFICATION.md` (expected/result fields per check)

**Frontmatter pattern (from 04-HUMAN-UAT.md):**
```yaml
---
status: partial
phase: 05-ship-it-live
source: [05-CONTEXT.md, 04-VERIFICATION.md, 03-VERIFICATION.md, 04-HUMAN-UAT.md]
started: [fill on execution]
updated: [fill on execution]
---
```

**Check format pattern (from 04-HUMAN-UAT.md):**
```markdown
### N. Check Name
expected: <command/action> → <observable outcome>
result: [pending]
```

**Order (D-07):** A (boot/infra, 6 checks) → B (queue persistence, 2 checks) → C (behavioral/Discord, 9 checks) → D (destructive/backup-restore, 1 check — always last)

**Runbook must include:**
- Red-box `WARNING: NEVER run docker compose down -v in production` at the top
- Troubleshooting table from RESEARCH.md Focus Area 6 (D-11)
- Per-check: command or action, expected output, pass/fail field
- Prerequisites checklist before check A1 (VM timezone set, docker enabled, .env in place, ~./pgpass, ~/.oci/config, crontab set)

**Suggested path (Claude's discretion per D-07):** `.planning/phases/05-ship-it-live/05-UAT-RUNBOOK.md`

---

## Shared Patterns

### ZoneInfo TZ-aware datetime
**Source:** `database.py:6,19-26`
**Apply to:** `cogs/events.py:197`, `bot.py:467`
```python
from zoneinfo import ZoneInfo
import config
# Wall-clock hour (events.py pattern):
local_hour = datetime.now(tz=ZoneInfo(config.STREAK_TIMEZONE)).hour
# tasks.loop at 4am ET (bot.py pattern):
@tasks.loop(time=datetime.time(hour=4, minute=0, tzinfo=ZoneInfo(config.STREAK_TIMEZONE)))
```

### clear_persisted template
**Source:** `cogs/music.py:977-984`
**Apply to:** `bot.py:399`, `cogs/music.py:1206`
```python
queue._play_generation += 1  # invalidate stale after-callbacks
queue.clear()
if hasattr(self.bot, "queue_persistence"):   # use `bot` (not self.bot) in bot.py tasks
    await self.bot.queue_persistence.clear_persisted(guild_or_interaction.guild.id)
```

### is_connected guard
**Source:** `cogs/music.py:311,365`
**Apply to:** `services/queue_persistence.py:147`
```python
vc = await vc_channel.connect()
if not vc.is_connected():
    log.warning("vc not connected post-connect() guild=%s", guild_id)
    return
```

### Shell script conventions
**Source:** `scripts/backup.sh` + `scripts/keepalive.sh`
**Apply to:** `scripts/deploy.sh`
```bash
#!/bin/bash
# scripts/name.sh — purpose (Decision ref)
set -euo pipefail
# Env vars from environment, never hardcoded
# Non-fatal ops: curl ... || true
```

### Pytest pure-function test class
**Source:** `tests/test_streak.py:1-60`
**Apply to:** `tests/test_seed_restore.py`
```python
"""Tests for X. These tests do NOT use asyncpg..."""
import pytest
class TestX:
    def test_y(self):
        assert ...
```

---

## No Analog Found

All files have analogs. No files require falling back to RESEARCH.md-only patterns.

---

## Metadata

**Analog search scope:** `cogs/`, `services/`, `bot.py`, `config.py`, `database.py`, `scripts/`, `tests/`
**Files scanned:** 12 source files read directly; cross-referenced with RESEARCH.md verified locations
**Pattern extraction date:** 2026-06-12

### Line number drift note
CONTEXT.md and RESEARCH.md cite specific line numbers confirmed by direct code inspection in this session:
- `cogs/music.py`: `_play_track` at 305-375 ✓, `/stop` template at 977-984 ✓, reconnect at 1194-1210 ✓
- `bot.py`: idle-leave at 395-403 ✓, yt-dlp loop at 467 ✓
- `cogs/events.py`: late-night at 193-197 ✓ (note: actual line is 197 for `local_hour =`)
- `services/queue_persistence.py`: smart-rejoin at 146-152 ✓
- `config.py`: STREAK_TIMEZONE at 58 ✓
- `database.py`: ZoneInfo import at 6, get_local_date at 19-26 ✓
