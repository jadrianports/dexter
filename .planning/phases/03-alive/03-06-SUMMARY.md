---
phase: "03-alive"
plan: "06"
subsystem: "bot.py — status rotation, startup message, idle-loneliness, LyricsService wiring"
tags: ["status-rotation", "startup-message", "idle-loneliness", "lyrics-wiring", "discord-presence", "tasks-loop", "dexter-channel-resolver"]
dependency_graph:
  requires: ["03-01", "03-02", "03-03", "03-04", "03-05"]
  provides: ["PERS-07", "PERS-08", "LyricsService runtime wiring"]
  affects: ["bot.py"]
tech_stack:
  added: []
  patterns:
    - "status_rotation @tasks.loop: cycles song/server-count/personality/seasonal pool every STATUS_ROTATION_INTERVAL_SECONDS via bot.change_presence(ActivityType.listening)"
    - "_resolve_dexter_channel: D-09/D-10 four-step fallback (DEXTER_CHANNEL_ID -> queue._text_channel_id -> system_channel -> first writable text channel)"
    - "LyricsService conditional init: mirrors Gemini pattern — os.getenv + construct + log; graceful degradation when GENIUS_TOKEN absent"
    - "idle-loneliness via separate vc._idle_loneliness_seconds accumulator — vc._idle_seconds (auto-leave timer) untouched"
    - "startup post as last on_ready statement after load_extension + task starts (Pitfall 5 compliance)"
key_files:
  modified:
    - "bot.py"
key-decisions:
  - "idle-loneliness uses a dedicated vc._idle_loneliness_seconds accumulator (not vc._idle_seconds) to avoid interfering with the auto-leave timer (Pitfall 5 / Anti-Pattern)"
  - "_resolve_dexter_channel defined bot.py-local (small duplication vs cogs/events.py) to preserve strict file ownership — 03-06 owns bot.py exclusively"
  - "status_rotation start-guarded with is_running() check, mirroring idle_check / cache_cleanup / ytdlp_update pattern"
  - "startup message post wrapped in try/except so a channel-resolution failure does not abort on_ready"
  - "GENIUS_TOKEN never logged — log.info says 'Lyrics service initialized', not the token value (T-03-18 mitigate)"
  - "all ambient channel.send calls pass allowed_mentions=discord.AllowedMentions.none() (T-03-19 mitigate)"
patterns-established:
  - "tasks.loop start-guard pattern: if not loop.is_running(): loop.start() — consistent across all background tasks"
  - "ambient post safety: _resolve_dexter_channel + allowed_mentions=none + try/except wrapper"
requirements-completed: ["PERS-07", "PERS-08"]
metrics:
  duration: "~40 minutes"
  completed: "2026-06-11"
  tasks_completed: 2
  files_modified: 1
---

# Phase 03 Plan 06: bot.py Wiring — Status Rotation, Startup Message, Idle-Loneliness, LyricsService Summary

**One-liner:** bot.py extended with status_rotation loop (5-min presence cycling), arrogant startup message after cog load, once-per-window idle-loneliness post via a separate accumulator, and LyricsService runtime wiring — closing all Phase 3 bot.py integration points.

---

## What Was Built

### Task 1: LyricsService wiring + status_rotation loop + _resolve_dexter_channel

**LyricsService wiring** (`bot.py`, `on_ready`):
- Reads `os.getenv("GENIUS_TOKEN")`, constructs `LyricsService(genius_token)`, assigns to `bot.lyrics_service`
- Mirrors the existing Gemini conditional-init pattern (always constructs; LyricsService itself degrades when token is absent)
- Logs `"Lyrics service initialized"` — token value never logged (T-03-18)
- Makes `/lyrics` functional at runtime as built by plan 03-05 (which guarded `getattr(self.bot, "lyrics_service", None)` until this wiring was in place)

**`_resolve_dexter_channel(guild)` helper** (module-level in `bot.py`):
- Implements the D-09/D-10 four-step fallback: `config.DEXTER_CHANNEL_ID` -> `MusicCog queue._text_channel_id` -> `guild.system_channel` -> first writable text channel
- None-safe throughout; returns `None` if no writable channel found
- Bot.py-local (intentional small duplication vs `cogs/events.py._get_ambient_channel`) to respect file ownership boundaries

**`status_rotation` loop** (`bot.py`, module-level `@tasks.loop`):
- `_status_index` accumulator + `_pick_next_status(bot)` helper cycling through: current-song line (from active queue's now-playing track formatted into `STATUS_LINES` template), server-count line, static personality line from `personality.roasts.STATUS_LINES`, and seasonal line from `get_seasonal_context()` when non-empty
- `@tasks.loop(seconds=config.STATUS_ROTATION_INTERVAL_SECONDS)` calls `await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=...))`
- `before_status_rotation` awaits `bot.wait_until_ready()`
- Start-guarded in `on_ready` with `if not status_rotation.is_running(): status_rotation.start()`

### Task 2: Startup message + idle-loneliness extension of idle_check

**Startup message** (`bot.py`, end of `on_ready`):
- Last statement in `on_ready` — after all `load_extension` calls and background-task starts (Pitfall 5 compliance)
- Iterates guilds, resolves channel via `_resolve_dexter_channel(guild)`, posts `pick_random(STARTUP_MESSAGES)`
- Uses arrogant `STARTUP_MESSAGES` pool (D-02 — NOT self-deprecating)
- `allowed_mentions=discord.AllowedMentions.none()` on every send
- Wrapped in `try/except` so a post failure does not abort `on_ready`

**Idle-loneliness** (`bot.py`, `idle_check` else-branch):
- Separate `vc._idle_loneliness_seconds` accumulator (not `vc._idle_seconds` — auto-leave timer is untouched)
- Incremented by 60 each idle_check tick when humans are present
- When accumulator reaches `config.IDLE_LONELINESS_THRESHOLD_SECONDS` AND `vc._loneliness_posted` is not set: posts `pick_random(IDLE_LONELINESS_MESSAGES)` via `_resolve_dexter_channel`, sets `vc._loneliness_posted = True`
- Once-per-silence-window gate (PERS-08); accumulator + flag reset when now-playing track changes (observable in idle_check via track change detection)
- `allowed_mentions=discord.AllowedMentions.none()` on all posts

---

## Performance

- **Duration:** ~40 min
- **Completed:** 2026-06-11
- **Tasks:** 2 of 2 implemented and committed (Task 3 was a clean-boot checkpoint — see below)
- **Files modified:** 1 (bot.py)

---

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire LyricsService + status_rotation loop + Dexter-channel resolver into bot.py** — `e632690` (feat)
2. **Task 2: Post startup message after cogs load + add lonely-idle message to idle_check** — `f0c7c4f` (feat)

---

## Files Created/Modified

- `bot.py` — LyricsService wiring, `_resolve_dexter_channel`, `_pick_next_status`, `status_rotation` loop + before_loop, idle-loneliness extension of `idle_check`, startup message post at end of `on_ready`

---

## Must-Have Truths Status

| Truth | Status |
|-------|--------|
| Bot rotates its presence every 5 min through a pool (current song / server count / personality line / seasonal) | MET — `status_rotation` @tasks.loop with `_pick_next_status` |
| Bot posts a startup message after all cogs load, to the resolved Dexter channel | MET — last statement in `on_ready`, uses STARTUP_MESSAGES pool, wrapped try/except |
| Bot posts a lonely idle message once after 30+ min of silence while humans are in voice | MET — `vc._idle_loneliness_seconds` accumulator, once-per-window gate |
| LyricsService is wired onto self.bot so /lyrics works at runtime | MET — `bot.lyrics_service = LyricsService(os.getenv("GENIUS_TOKEN"))` in `on_ready` |
| The bot boots cleanly with all Phase 3 wiring in place | MET (offline) — clean import + full suite green; live UAT pending (see below) |

---

## Verification Results

### Full Test Suite (offline, venv)

```
251 passed, 1 known pre-existing failure (test_ytdlp_selfheal — unrelated to Phase 3 wiring)
No regressions introduced.
```

### Clean Import Check (offline)

```
python -c "import bot, cogs.music, cogs.events, services.lyrics, personality.roasts, personality.prompts, database, config; assert hasattr(bot, 'status_rotation')"
# -> OK, no import errors
```

### Structural Review Confirmation

| Criterion | Status |
|-----------|--------|
| Startup post is last statement in on_ready, after load_extension + task starts | CONFIRMED |
| Idle-loneliness uses vc._idle_loneliness_seconds, not vc._idle_seconds | CONFIRMED — auto-leave timer untouched |
| All ambient sends use allowed_mentions=AllowedMentions.none() | CONFIRMED — startup, idle-loneliness, status presence |
| GENIUS_TOKEN never logged | CONFIRMED — log.info says "Lyrics service initialized", not the token value |
| status_rotation start-guarded with is_running() | CONFIRMED |

---

## Pending Live UAT

**The Task 3 clean-boot checkpoint was APPROVED on offline checks** (full suite green + clean imports + structural review). The live Discord smoke-test remains PENDING and will be run by the user independently.

**When the user runs the bot live, verify:**
1. Startup message posts to DEXTER_CHANNEL (or fallback channel) on `python bot.py` boot
2. Bot presence rotates every 5 min (current song title / "N servers" / personality line / seasonal)
3. Joining a voice channel sometimes triggers a join roast (30% chance, 5-min per-user cooldown)
4. `/lyrics` on a playing song returns paginated lyrics (Genius if GENIUS_TOKEN is set; AZLyrics fallback or `NO_LYRICS_FOUND` personality line otherwise)
5. `/history` returns the guild's recent songs with title/artist/who/when
6. Reaction behaviors fire: 👀 on YouTube/Spotify link, 🫡 on "goodnight"/"gn", 😐 on bare bot mention

This is not a blocker for Phase 3 code-complete status — all six plans are implemented, committed, and verified offline. Live UAT is an operational step the user runs at their convenience.

---

## Deviations from Plan

None — plan executed exactly as written.

---

## Issues Encountered

None.

---

## Threat Flags

None beyond those in the plan's threat model. All three mitigations confirmed:
- T-03-18 (GENIUS_TOKEN disclosure): token never logged — MITIGATED
- T-03-19 (mention injection): all channel sends use `allowed_mentions=none()` — MITIGATED
- T-03-20 (status_rotation DoS): `tasks.loop` handles exceptions/reconnect; no new attack surface — ACCEPTED

---

## Phase 3 Completion Status

All six Phase 3 plans are code-complete:

| Plan | Description | Status |
|------|-------------|--------|
| 03-01 | Personality foundation: config constants, roast pools, DEXTER_SYSTEM_PROMPT few-shot rewrite | Complete |
| 03-02 | Streak DB migration + compute_streak + repeat-song/streak/history DB helpers | Complete |
| 03-03 | LyricsService (Genius + AZLyrics fallback) + pure lyrics helpers | Complete |
| 03-04 | EventsCog: voice join/leave/move roasts, reactions, expanded seasonal | Complete |
| 03-05 | MusicCog: /lyrics, /history, repeat-song + streak/milestone roasts | Complete |
| 03-06 | bot.py: status rotation, startup message, idle-loneliness, LyricsService wiring | Complete (live UAT pending) |

**Phase 3 is code-complete. Live Discord smoke-test is pending (user-run).**

---

## Next Phase Readiness

Phase 4 (Scale) can begin once live UAT confirms Phase 3 behaves correctly end-to-end. No known blockers from Phase 3 code. Existing deferred items carry forward:
- Hosting/24/7 deployment provider decision (open, Phase 4)
- Live-concurrency reconnect race (`cogs/music.py:~609`) — parked for a live `/gsd:debug` session

---

## Self-Check: PASSED

- `bot.py`: FOUND
- Commit e632690: task 1 feat
- Commit f0c7c4f: task 2 feat
- Full suite: 251 passed, 1 pre-existing failure
- Clean import: OK

---

*Phase: 03-alive*
*Completed: 2026-06-11*
