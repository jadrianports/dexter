# Phase 10: Critical-Path Test Coverage - Pattern Map

**Mapped:** 2026-06-27
**Files analyzed:** 6 (3 new `logic/` modules + 3 new test modules)
**Analogs found:** 6 / 6

## Orientation

This phase creates NO new feature surface. It **extracts already-shipped decision logic** out of
async Discord/DB glue into pure, importable functions in a new top-level `logic/` package, then
locks each with exhaustive pure-unit tests. Every analog below is **the live code the new function
is carved from** (the "source of truth" per D-02 true-extraction) plus the **test-style analog**
(`tests/test_queue.py`) every new test file mirrors.

**The single most important pattern — the determinism seam (D-06):**
Every extracted decision function MUST be pure. Any `random.random()`, `time.monotonic()`,
`asyncio.get_event_loop().time()`, or `datetime.now()` stays in the cog glue; its result is passed
**in** as a parameter. The live code already does this for time — replicate that discipline for
`random` and the monotonic clock too. The canonical precedent is `is_late_night(hour: int)` and the
`local_hour = datetime.now(tz=ZoneInfo(config.STREAK_TIMEZONE)).hour` computation in
`cogs/events.py:198` — the hour is computed in glue and handed to the pure helper.

## File Classification

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `logic/playback.py` | logic (pure decision) | transform (decision) | `cogs/music.py` `_on_track_end` (732), `_play_track` gating (519/597); `services/queue_persistence.py` `restore_queues` clamp (128-135) | exact (extraction source) |
| `logic/health.py` | logic (pure decision) | transform (decision) | `cogs/ops.py` `gather_bot_metrics` (54), `bot.py` `/health` handler (217-230) | exact (extraction source) |
| `logic/roasts.py` | logic (pure decision) | transform (decision) | `cogs/events.py` `on_voice_state_update` (165), `_check_ambient_cooldown` (37); `personality/roasts.py` `is_late_night` (211) | exact (extraction source) |
| `tests/test_playback_logic.py` | test | n/a | `tests/test_queue.py` | exact (style) |
| `tests/test_health_logic.py` | test | n/a | `tests/test_queue.py` | exact (style) |
| `tests/test_roast_logic.py` | test | n/a | `tests/test_queue.py` | exact (style) |

---

## Pattern Assignments

### `logic/playback.py` (pure decision)

**Extraction source A — `cogs/music.py` `_on_track_end` (lines 732-780).** This is the exact branch
tree the pure `decide_on_track_end(...)` owns. Glue keeps: `queue.advance()` call, `_persist_queue`,
`_play_track`, `make_task(ai_cog.try_auto_queue)`, `clear_persisted`. The function decides WHICH of
these to do.

```python
async def _on_track_end(self, guild: discord.Guild) -> None:
    queue = self.get_queue(guild.id)
    if not queue.is_playing:               # -> NOOP (manual stop)
        return
    # ... auto-queue "played" bookkeeping ...
    next_track = queue.advance()
    await self._persist_queue(guild, queue)
    if next_track:                          # -> PLAY
        await self._play_track(guild, next_track)
        await self._refresh_now_playing(guild, queue)
    else:
        voice_client = guild.voice_client
        if voice_client and voice_client.channel:
            human_members = [m for m in voice_client.channel.members if not m.bot]
            if human_members:
                ai_cog = self.bot.cogs.get("AICog")
                if ai_cog:
                    make_task(ai_cog.try_auto_queue(guild), ...)
                    return                  # -> AUTOQUEUE (no is_playing=False!)
        queue.is_playing = False            # -> STOP-AND-CLEAR
        if hasattr(self.bot, "queue_persistence"):
            await self.bot.queue_persistence.clear_persisted(guild.id)
```

**Decision branches the pure fn must return (D-03/D-05):**
- `is_playing == False` → **NOOP** (manual stop happened)
- `advance()` returned a track → **PLAY**
- exhausted + humans present + AICog loaded → **AUTOQUEUE** (scar #2: silent auto-queue)
- exhausted + humans present + no AICog → **STOP-AND-CLEAR**
- exhausted + no humans → **STOP-AND-CLEAR**
- exhausted + not connected to voice → **STOP-AND-CLEAR**

**Determinism seam:** the function must NOT call `queue.advance()` itself if advance mutates state and
you want to test the branch independently — pass in the *inputs to the decision* (e.g. `has_next: bool`,
`humans_present: bool`, `aicog_loaded: bool`, `is_playing: bool`, `connected: bool`). Per D-06 the
planner picks primitives-vs-snapshot. Note `voice_client.is_playing()` (ground truth) vs the
`queue.is_playing` flag is the scar #2 confusion — the snapshot must carry the right one.

**Scar #1 (finished-song replay, DEPLOY-06 / IN-02):** STOP-AND-CLEAR must be the returned action for
natural exhaustion so the glue calls `clear_persisted()` — the just-finished track must not stay parked
on `current_index` to be replayed on restart. Named regression test required.

**Extraction source B — `_play_track` validity/gating (lines 519-617).** The validity guards the pure
fn owns: `not voice_client or not voice_client.is_connected()` → bail; unavailable-source → `queue.skip()`
then play-next-or-summarize; the `voice_client.is_playing() or voice_client.is_paused()` stop gate. The
`audio.get_source`, `voice_client.play`, `source.cleanup`, ffmpeg, prefetch all stay glue.

**Extraction source C — `restore_queues` index clamp (`services/queue_persistence.py` lines 128-135).**
This is scar #4. Extract verbatim into a pure `clamp_restore_index(raw_index, track_count) -> int`:

```python
raw_index = payload.get("current_index", 0)
if not isinstance(raw_index, int):
    raw_index = 0
queue.current_index = (
    max(0, min(raw_index, len(queue.tracks) - 1)) if queue.tracks else 0
)
```

Branches (D-03): in-range, above-max, negative, non-int, empty-queue (→ 0). Plus the cap-truncate at
lines 120-125 (`len(restored) > MAX_QUEUE_SIZE_PER_GUILD`) and the smart-rejoin gate at 144-147
(`current is not None and guild.voice_client is None and any(not m.bot for m in members)`) are pure
sub-decisions the loop dispatches on.

**Compose, don't reimplement:** `MusicQueue.advance()/.skip()/.get_current()/.upcoming()`
(`models/queue.py` 103-122, 239-241) are already pure and tested in `tests/test_queue.py`. New logic
decides what to do with their results — never re-implements index math.

---

### `logic/health.py` (pure decision)

**Extraction source — `bot.py` `/health` handler (lines 217-230).** This is the entire body of the
pure `determine_health_status(reasons, strict) -> tuple[int, str]`:

```python
reasons = metrics.get("degraded_reasons", [])
# D-01: HEALTH_STRICT_STATUS (default True) -> 503 when degraded; False -> legacy 200.
# D-27: body exposes ONLY status + generic reason strings (no internals).
if reasons:
    body = json.dumps({"status": "degraded", "reasons": reasons})
    status = 503 if getattr(config, "HEALTH_STRICT_STATUS", True) else 200
else:
    body = '{"status":"ok"}'
    status = 200
```

**Decision matrix the pure fn owns (D-03/D-05 scar #3):**
- `reasons` non-empty + strict → `(503, degraded-body)`
- `reasons` non-empty + not strict → `(200, degraded-body)`
- `reasons` empty → `(200, ok-body)`

**The `degraded_reasons` producer — `cogs/ops.py` `gather_bot_metrics` (lines 95-124).** The async DB
probe (`pool.acquire()` + `SELECT 1` under `asyncio.wait_for`) and `bot.is_ready()`/`_ready_done`
checks stay glue. The **pure subset** the planner may extract is the reason-assembly: given
`(db_ok, pool_present, gateway_ready, ready_done, musiccog_loaded)` → produce the reasons list. The
critical reasons (scar #3, REL-01 / D-02):
- `pool is None` → `"database pool not initialized"`
- DB probe failed → `"database unreachable"`
- `not gateway_ready` → `"discord gateway not ready"`
- `_ready_done and MusicCog is None` → `"MusicCog not loaded"`

Each critical reason × `HEALTH_STRICT_STATUS` on/off must have an explicit test (scar #3). Note this is
a `module-level async function` precedent (no `self`) — but `determine_health_status` is pure/sync.

---

### `logic/roasts.py` (pure decision)

**Extraction source A — `on_voice_state_update` (`cogs/events.py` lines 165-245).** The trigger/gating
nest the pure fn owns. Glue keeps: `_generate_ambient_roast` (Gemini), `_get_ambient_channel`,
`channel.send`, `_mark_ambient_roast`, the bot-move early-return, the `member.bot` guard.

```python
local_hour = datetime.now(tz=ZoneInfo(config.STREAK_TIMEZONE)).hour   # computed in GLUE
# JOIN
if before.channel is None and after.channel is not None:
    if random.random() < config.UNPROMPTED_ROAST_CHANCE:              # roll in GLUE
        if self._check_ambient_cooldown(member.id, AMBIENT_ROAST_CEILING_SECONDS):
            if roasts.is_late_night(local_hour):
                if random.random() < config.LATE_NIGHT_ROAST_CHANCE:  # 2nd roll in GLUE
                    scenario, fallback_pool = "...late night...", roasts.LATE_NIGHT_ROASTS
                else:
                    return                                            # late-night roll failed
            else:
                scenario, fallback_pool = "...joined...", roasts.VOICE_JOIN_ROASTS
            # -> ROAST(scenario, fallback_pool)
```

**Determinism seam (critical):** the two `random.random()` rolls, the `local_hour`, and the monotonic
`now` all stay in glue. The pure `decide_ambient_roast(...)` takes them as params:
`scenario = decide_ambient_roast(event="join"|"leave"|"move", chance_roll: float, late_night_roll: float,
local_hour: int, seconds_since_last_roast: float, ...)` → returns the chosen `(scenario, fallback_pool)`
or a no-roast sentinel. Tests pass floats directly — **no patching of `random` or clocks** (D-06 hard
constraint). Compose `roasts.is_late_night(local_hour)` (already pure, `personality/roasts.py:211`).

**Extraction source B — `_check_ambient_cooldown` (lines 37-41).** Already nearly pure except the clock:

```python
def _check_ambient_cooldown(self, user_id, ceiling_seconds) -> bool:
    now = asyncio.get_event_loop().time()           # CLOCK -> moves to glue
    last = self._ambient_roast_times.get(user_id, 0.0)
    return (now - last) >= ceiling_seconds
```

Extract as `cooldown_elapsed(seconds_since_last: float, ceiling_seconds: int) -> bool`. Branches
(D-03): exactly-at-ceiling (`>=` → True), one-under (False).

**Decision branches (D-03):** join vs leave vs move scenario selection; chance roll pass/fail boundary
(`< UNPROMPTED_ROAST_CHANCE`); cooldown at-ceiling vs one-under; late-night eligible → second roll
pass/fail; late-night-ineligible → normal join pool.

---

### `tests/test_playback_logic.py` / `test_health_logic.py` / `test_roast_logic.py`

**Analog: `tests/test_queue.py` (follow exactly per locked TESTING.md).**

```python
import pytest
import config
from logic.playback import decide_on_track_end  # etc.

def make_track(video_id: str = "abc123", title: str = "Test Song", **kwargs) -> Track:
    defaults = {"video_id": video_id, "title": title, "artist": "Test Artist",
                "url": f"https://youtube.com/watch?v={video_id}", "duration_seconds": 200,
                "requested_by": 12345, "was_auto_queued": False}
    defaults.update(kwargs)
    return Track(**defaults)

class TestDecideOnTrackEnd:
    def test_not_playing_returns_noop(self):
        result = decide_on_track_end(is_playing=False, ...)
        assert result == Action.NOOP
```

**Rules (from TESTING.md, all locked):**
- File `tests/test_*.py`; classes `Test*`; methods `test_<scenario>_<expected>`.
- Factory helper (`make_track()`-style) at module top; reuse the exact one from `test_queue.py` for
  playback snapshots. Add a `make_snapshot()`/`make_roast_context()` factory if the planner picks a
  dataclass seam (D-06).
- Module-level constants for fixed inputs (mirror `MOCK_*` constants in `test_youtube.py`).
- Fresh objects per test, no shared state.
- Plain `assert`; `pytest.raises(match=...)` only if a fn raises.
- **These are pure-unit: NO `@pytest.mark.asyncio`, NO `MagicMock`/`AsyncMock`/`patch`** — the whole
  point of the seam is that determinism is passed in. If a test needs a mock, the cut-line is wrong.
- One-assert-ish, scenario-named, short (5-15 lines).

**Named scar tests required (D-05) — must be findable, not buried in a parametrized sweep:**
1. `test_finished_song_returns_stop_and_clear` (replay scar)
2. `test_autoqueue_selected_on_voice_client_ground_truth` (silent auto-queue scar)
3. `test_degraded_returns_503_when_strict` per critical reason (REL-01)
4. `test_stale_index_clamped_into_range` (non-int / negative / above-max / empty)

---

## Shared Patterns

### Determinism seam (applies to ALL three logic modules)
**Source precedent:** `cogs/events.py:198` + `personality/roasts.py:211`
```python
# GLUE computes the nondeterministic value:
local_hour = datetime.now(tz=ZoneInfo(config.STREAK_TIMEZONE)).hour
# PURE fn receives it:
def is_late_night(hour: int) -> bool: ...
```
Apply identically to `random.random()` rolls and `time.monotonic()` / `get_event_loop().time()`
deltas. Hard constraint (D-06): no pure decision fn calls a clock or RNG.

### True extraction — single source of truth (D-02)
**Apply to:** all three logic modules. The live cog method must CALL the new pure fn and dispatch on
its return — no duplicated/mirrored logic. Zero drift. The TEST-04 regression gate (full pytest green
+ manual `python bot.py` boot) covers the risk of touching shipped playback.

### Per-guild fault isolation stays in glue (CR-01)
**Source:** `restore_queues` `continue` per-guild (line 153), `gather_bot_metrics` `except: pass`
per-guild (line 89). The extracted decision is pure & per-guild; the loop + error-swallow stay glue.

### Config thresholds the decisions read (pass in or import config)
`UNPROMPTED_ROAST_CHANCE` (0.30), `LATE_NIGHT_ROAST_CHANCE` (0.50),
`AMBIENT_ROAST_CEILING_SECONDS` (300), `HEALTH_STRICT_STATUS` (True),
`MAX_QUEUE_SIZE_PER_GUILD` (500), `HEALTH_DB_PROBE_TIMEOUT` (3.0) — all in `config.py`. Comparing
against a config constant is fine inside a pure fn (config is static); only clocks/RNG must be injected.

---

## No Analog Found

None. Every extracted function has an exact in-repo source (the live cog code), and the test style has
an exact analog (`tests/test_queue.py`). The only genuinely new artifact is the `logic/` package
*directory* itself (needs an `__init__.py`) — there is no existing top-level pure-logic package to copy,
but `models/` and `personality/` are structural precedents for a non-cog importable package.

## Metadata

**Analog search scope:** `cogs/`, `services/`, `models/`, `personality/`, `bot.py`, `config.py`, `tests/`
**Files scanned:** 7 (music.py, ops.py, events.py, queue_persistence.py, bot.py, queue.py, roasts.py) + test_queue.py + TESTING.md + config.py
**Pattern extraction date:** 2026-06-27
