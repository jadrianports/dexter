---
phase: 05-ship-it-live
reviewed: 2026-06-12T00:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - bot.py
  - cogs/events.py
  - cogs/music.py
  - scripts/__init__.py
  - scripts/backup.sh
  - scripts/deploy.sh
  - scripts/lifecycle-policy.json
  - scripts/seed_restore_test.py
  - services/queue_persistence.py
  - tests/test_seed_restore.py
  - tests/test_streak.py
findings:
  critical: 2
  warning: 7
  info: 5
  total: 14
status: remediated
remediated: "7 of 14 fixed (CR-01, CR-02, WR-01, WR-02, WR-05, WR-06, WR-07); WR-03/WR-04 + IN-01..05 deferred as advisory"
---

# Phase 5: Code Review Report

**Reviewed:** 2026-06-12
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Reviewed the Phase 5 "Ship It Live" changes: the `clear_persisted()` gap closures on the idle-leave and reconnect-failure paths, the reconnect-race `is_connected()` guard plus diagnostic logging, the ZoneInfo TZ-correctness fix, and the new deploy/backup/restore shell scripts + seed-restore test.

The TZ fix (`cogs/events.py:198`) and the `clear_persisted()` additions on the idle-leave (`bot.py:401-402`) and reconnect-failure (`cogs/music.py:1213-1214`) paths are correct. However two genuine defects exist: a `return`-instead-of-`continue` bug in the queue-restore loop that abandons every remaining guild's restore on a single smart-rejoin hiccup, and a data-hygiene defect in the seed-restore test that permanently pollutes the live production database with fake seed rows. The shell scripts are guarded reasonably well against the obvious data-loss footguns, but `backup.sh` has a silent-failure gap and the seed test has a destructive-on-live-DB side effect that the script's own docstring claims it avoids.

## Critical Issues

### CR-01: `restore_queues` aborts ALL remaining guild restores on one smart-rejoin failure

**File:** `services/queue_persistence.py:149-151`
**Issue:** Inside the `for row in rows:` loop, the smart-rejoin block returns from the entire method when a single guild's voice client reports not-connected:

```python
vc = await vc_channel.connect()
log.info("smart-rejoin: connected=%s guild=%s", vc.is_connected(), guild_id)
if not vc.is_connected():
    log.warning("Smart rejoin: vc not connected post-connect() guild=%s", guild_id)
    return   # <-- exits restore_queues entirely, abandoning all remaining guilds
await music_cog._play_track(guild, current)
```

`return` exits `restore_queues`, so every guild whose row has not yet been processed in the iteration is silently never restored. On a multi-server bot (this is `AutoShardedBot`, Phase 4 explicitly hardened for multi-server), one flaky reconnect on boot drops queue restoration for all subsequent guilds. The in-memory `queue.tracks` for those guilds is also never populated, so `/resume`/`/nowplaying` show nothing despite a persisted row existing.

**Fix:** Use `continue` (or just let the block fall through — there is no code after it in the loop body) so the loop proceeds to the next guild:
```python
        if not vc.is_connected():
            log.warning("Smart rejoin: vc not connected post-connect() guild=%s", guild_id)
            continue
        await music_cog._play_track(guild, current)
```

### CR-02: seed_restore_test permanently pollutes the LIVE production database

**File:** `scripts/seed_restore_test.py:142-182, 334-345`
**Issue:** The module docstring claims (line 19-21) "restore/createdb/dropdb target ONLY 'dexter_restore_test'. The live 'dexter' DB is read (for seeding) but never passed to pg_restore, createdb, or dropdb." This is technically true for the destructive DDL ops, but `_seed()` runs `INSERT` statements against the **live** `dexter` DB (`_get_pool("dexter")` at line 341, then `_seed(live_pool, rows)` at 343) and **never deletes them**. After the test runs, the production DB permanently contains:
- a `user_profiles` row for fake snowflake `999999999999999999` with `total_songs_queued=3`, `current_streak=2`, `longest_streak=5`
- 3 fake `song_history` rows (which surface in `/history` output for guild `111111111111111111`)
- 2 fake `user_artist_counts` rows

There is no teardown of the seeded live rows anywhere in `main()`. The `finally` blocks only drop the throwaway DB and the temp dump file. This is a data-integrity / data-pollution defect on the production database that the script's own security note implies does not happen. The fake `song_history` rows will also corrupt `/history`, milestone counts, and top-artist roast logic for any real interaction that reads those tables unfiltered.

**Fix:** Wrap the seed in a transaction that is rolled back after the backup is taken, OR add an explicit teardown step that deletes exactly the seeded rows by `SEED_USER_ID` against the live DB in a `finally` block:
```python
async def _unseed(pool, rows):
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM song_history WHERE user_id = $1", SEED_USER_ID)
            await conn.execute("DELETE FROM user_artist_counts WHERE user_id = $1", SEED_USER_ID)
            await conn.execute("DELETE FROM user_profiles WHERE user_id = $1", SEED_USER_ID)
```
Call it in a `finally` against a fresh live pool after the backup/restore cycle. Note: the dump captured in step 2 will still contain the seed rows, which is acceptable for the restore proof — but the live DB must be cleaned.

## Warnings

### WR-01: `backup.sh` pipe can mask `pg_dump` failure despite `pipefail`

**File:** `scripts/backup.sh:41,49-59`
**Issue:** `set -o pipefail` makes the pipeline return the rightmost non-zero exit, but `oci os object put --force` reads stdin and will happily upload a truncated/empty object if `pg_dump` dies mid-stream while `oci` still exits 0. `pipefail` catches a non-zero `pg_dump` exit, but a `pg_dump` that emits a partial dump then errors, or an `oci` that succeeds on a 0-byte stream, can still produce a "successful" backup that is corrupt. The seed-restore test guards against this with `MIN_DUMP_SIZE_BYTES`, but `backup.sh` itself (the thing cron runs unattended every 6h) has no post-upload size/integrity verification.

**Fix:** Dump to a temp file first, verify size, then upload — so a failed dump never reaches the bucket:
```bash
TMP_DUMP=$(mktemp)
trap 'rm -f "$TMP_DUMP"' EXIT
pg_dump --host=localhost --username=dexter --no-password --format=custom dexter > "$TMP_DUMP"
if [ "$(stat -c%s "$TMP_DUMP")" -lt 1024 ]; then
  echo "[backup.sh] Dump suspiciously small — aborting upload." >&2; exit 1
fi
oci os object put --bucket-name "$BUCKET" --name "$OBJECT_NAME" --file "$TMP_DUMP" --force
```

### WR-02: `deploy.sh` `git pull` with no clean-tree / branch guard

**File:** `scripts/deploy.sh:44-45`
**Issue:** `git pull` runs unconditionally in `/opt/dexter`. If the production checkout has local modifications (e.g. an edited `docker-compose.yml`, a hotfix, or a dirty `.env` tracked by accident), `git pull` either fails (aborting deploy mid-way after `set -e`) or, with a configured merge, silently merges and can produce a non-deterministic tree. There is also no check that the checkout is on the expected branch — a `git pull` on a detached HEAD or a feature branch deploys the wrong code. For a script that immediately rebuilds and restarts the live bot, this is a correctness/safety gap.

**Fix:** Guard before pulling:
```bash
if [ -n "$(git status --porcelain)" ]; then
  echo "[deploy.sh] Working tree dirty — refusing to deploy." >&2; exit 1
fi
git fetch origin
git checkout main
git pull --ff-only origin main
```

### WR-03: `_play_track` reconnect path can double-start playback (race window)

**File:** `cogs/music.py:1192-1207`
**Issue:** On bot disconnect, the handler loops up to 3 times calling `await before.channel.connect()` then `await self._play_track(...)`. `_play_track` increments `queue._play_generation` and calls `voice_client.play()`. But the reconnect handler does **not** increment the generation before reconnecting, and `_on_track_end`'s after-callback from the *previous* connection may still be in flight. The `is_connected()` guard added in `_play_track` (line 311, 367) helps, but the generation counter is the actual race guard per the CLAUDE.md gotcha ("Never call `voice_client.stop()` before `_play_track()`"). Here a stale after-callback from the dropped connection could fire `_on_track_end` → `advance()` → `_play_track` concurrently with the reconnect's `_play_track`, advancing the queue by an extra track. The generation increment inside `_play_track` partially mitigates, but the ordering relative to the old callback is not guaranteed.

**Fix:** Bump the generation counter at the top of the disconnect branch (before the reconnect loop), mirroring the `/stop` and failure-path template already used at line 1211:
```python
queue.is_playing = False
queue.is_paused = False
queue._play_generation += 1   # invalidate the dropped connection's after-callback up front
for attempt in range(3):
    ...
```

### WR-04: Restore path does not enforce livestream / duration cap on persisted tracks

**File:** `services/queue_persistence.py:118-125`
**Issue:** `restore_queues` rebuilds `Track.from_dict(t)` for every persisted track and only truncates on `MAX_QUEUE_SIZE_PER_GUILD`. It does not re-validate `duration_seconds` against `MAX_SONG_DURATION_SECONDS` or reject livestreams. The persisted payload is bot-controlled, so this is low-risk, but if a config tightening lowers `MAX_SONG_DURATION_SECONDS` between sessions, previously-queued over-length tracks silently bypass the cap on restore and `_play_track` will attempt to stream them.

**Fix:** Filter restored tracks by the current duration cap before assigning, e.g. `restored = [t for t in restored if not t.duration_seconds or t.duration_seconds <= config.MAX_SONG_DURATION_SECONDS]`.

### WR-05: `_docker_exec_stdin` assigns `result` but never checks it; misleading

**File:** `scripts/seed_restore_test.py:290-293`
**Issue:** `result = subprocess.run(cmd, input=stdin_bytes, check=True)` binds `result` and never uses it. `check=True` already raises on non-zero, so the binding is dead. More importantly, `pg_restore` frequently exits non-zero on benign warnings (e.g. "role does not exist" even with `--no-owner`), which `check=True` will treat as a hard failure and abort the restore proof — the opposite of robust. The unused `result` suggests the author intended to inspect return code/stderr but did not.

**Fix:** Drop the unused binding, and consider tolerating pg_restore's non-fatal warnings:
```python
subprocess.run(cmd, input=stdin_bytes, check=True)
```
If pg_restore warning exits become a problem, capture output and assert on row counts (already done in `_verify`) rather than on exit code.

### WR-06: `_get_pool` DSN rewrite breaks on DSNs with query params or trailing slash

**File:** `scripts/seed_restore_test.py:131-139`
**Issue:** `prefix, _, _ = base_url.rpartition("/")` then `dsn = f"{prefix}/{db_name}"`. If `DATABASE_URL` contains a query string (`postgresql://u:p@h:5432/dexter?sslmode=require`) the `rpartition("/")` keeps the `?sslmode=...` attached to the original db segment incorrectly, and the resulting DSN drops or mangles the params — the throwaway-DB pool then connects with different TLS/connection settings than the live pool, or fails. A trailing slash in the URL also yields an empty db segment producing `prefix//db_name`.

**Fix:** Parse with `urllib.parse.urlsplit`, replace only the path component, and preserve query/fragment:
```python
from urllib.parse import urlsplit, urlunsplit
parts = urlsplit(base_url)
dsn = urlunsplit(parts._replace(path=f"/{db_name}"))
```

### WR-07: Owner check uses `bot.owner_id` which may be unset

**File:** `bot.py:356`
**Issue:** `if interaction.user.id != bot.owner_id:` — `bot.owner_id` is only populated by discord.py if `owner_id`/`owner_ids` was passed to the constructor or after an `application_info()` fetch. `create_bot()` (lines 61-67) does not pass `owner_id`, and nothing calls `is_owner()`/`application_info()` at startup, so `bot.owner_id` is likely `None`. If `None`, the guard `interaction.user.id != None` is always True, meaning **every** non-owner is correctly rejected — but so is the actual owner, making `/sync` unusable. Worse, `config.OWNER_ID` (the env-configured owner) is never wired into the bot, so the intended owner authorization is not enforced via the configured value at all.

**Fix:** Pass the configured owner explicitly and check against it:
```python
bot = DexterBot(..., owner_id=config.OWNER_ID or None)
```
and/or compare directly: `if interaction.user.id != config.OWNER_ID:`.

## Info

### IN-01: `clear_persisted` parameter type is inconsistent across call sites

**File:** `services/queue_persistence.py:68`; `bot.py:402`; `cogs/music.py:983,1214`
**Issue:** `clear_persisted(self, guild_id: int)` is annotated `int` and casts `str(guild_id)` internally. Callers pass `guild.id` (int) and `interaction.guild.id` (int) consistently, so this is fine in practice, but the `persist()` method takes a `guild` object and does `str(guild.id)` — the asymmetry (one takes an id, one takes a guild) is an easy source of future misuse. Consider making both take the same shape.

### IN-02: Duplicated `_resolve_dexter_channel` / `_get_ambient_channel` logic

**File:** `bot.py:82-122` and `cogs/events.py:49-88`
**Issue:** The four-step channel fallback chain is duplicated verbatim between `bot.py` and `cogs/events.py` (the bot.py docstring even acknowledges this). Duplicated logic drifts; a fix to one (e.g. a permission edge case) will silently miss the other. The "file-ownership boundaries" rationale is weak justification for copy-pasted control flow.

**Fix:** Extract to a shared helper (e.g. `utils/channels.py:resolve_ambient_channel(guild)`) and call from both.

### IN-03: `idle_check` accumulates idle time in 60s steps that can overshoot/undershoot

**File:** `bot.py:393-395`
**Issue:** `vc._idle_seconds += 60` then compares `>= IDLE_TIMEOUT_SECONDS`. Because the loop fires every 60s but the accumulator is incremented by a hardcoded 60 (not the actual elapsed time), drift between the loop's real cadence and the assumed 60s makes the effective timeout approximate. Minor for a 10-minute timeout, but the magic `60` appears twice (lines 393, 434) and should match `idle_check`'s `seconds=60` via a named constant.

### IN-04: `_pick_next_status` global mutable index without lock

**File:** `bot.py:79,139-140,173`
**Issue:** `_status_index` is a module global mutated in `_pick_next_status`. It is only called from the single `status_rotation` task loop so there is no real concurrency, but the global-mutation pattern plus `pool[_status_index % len(pool)]` where `pool` length varies per tick means the rotation order is not stable/predictable (index 5 maps to different slots depending on whether the current-song and seasonal slots were appended this tick). Functionally harmless, just non-deterministic rotation.

### IN-05: `lifecycle-policy.json` retention (14 days) may undercut backup cadence assumptions

**File:** `scripts/lifecycle-policy.json:7`
**Issue:** The lifecycle rule deletes objects older than 14 days matching prefix `dexter_`. With a 6-hour backup cadence that retains ~56 backups, which is reasonable. No defect, but note the `exclusionPatterns` is empty — there is no protection for a manually-pinned "known-good" backup; any object matching `dexter_` older than 14 days is deleted unconditionally, including a backup an operator might want to keep long-term. Consider an exclusion prefix (e.g. `dexter_keep_`) for pinned backups.

---

## Remediation (applied 2026-06-12, post-review)

Fixed on branch `gsd/phase-5-ship-it-live` before phase verification:

| Finding | Severity | Commit | Fix |
|---------|----------|--------|-----|
| CR-01 | Critical | `253713d` | `return` → `continue` in `restore_queues` loop — one guild's rejoin failure no longer abandons all remaining guilds |
| CR-02 | Critical | `803815b` | `_cleanup_seed()` added + called in `main()` `finally`; seed rows now deleted from the live DB whether the proof passes or raises |
| WR-01 | Warning | `32d0971` | `backup.sh` dumps to a temp file and size-checks (≥1 KB) before upload; corrupt/truncated dumps never reach the bucket |
| WR-02 | Warning | `09cbd72` | `deploy.sh` refuses a dirty working tree and uses `git fetch` + `git pull --ff-only` |
| WR-05 | Warning | `803815b` | dropped dead `result =` binding in `_docker_exec_stdin` |
| WR-06 | Warning | `803815b` | `_get_pool` rewritten with `urlsplit`/`urlunsplit` to preserve query params (e.g. `?sslmode=require`) |
| WR-07 | Warning | `795f5dd` | `owner_id=config.OWNER_ID or None` wired into the bot + `/sync` now gates on `await bot.is_owner(...)` |

**Deferred (advisory — not fixed):**

- **WR-03** (reconnect generation-counter race) — this is precisely the DEPLOY-04 live-`/gsd:debug` item; the diagnostic logging added this phase exists to diagnose it on Oracle under real concurrency. Patching the generation bump blind, without reproducing the race, risks a worse race. Tracked for the live debug session.
- **WR-04** (restore path doesn't re-apply duration cap) — only bites if `MAX_SONG_DURATION_SECONDS` is tightened between sessions; low risk.
- **IN-01..IN-05** — cosmetic / dedup / determinism nits; no behavioral impact.

Verification (post-fix): `python -m py_compile` clean on all edited modules, `bash -n` clean on both scripts, 29 pure unit tests green.

---

_Reviewed: 2026-06-12_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
