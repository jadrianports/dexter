# Phase 10: Critical-Path Test Coverage - Context

**Gathered:** 2026-06-27
**Status:** Ready for planning

<domain>
## Phase Boundary

The untested critical-path **decision logic** is extracted into pure importable functions and
unit-tested. This phase adds **no features and changes no behavior** — it carves the existing
decision cores out of their async Discord/DB glue so they can be tested deterministically, then
locks them with passing tests and a green regression gate.

Three extraction targets (TEST-01…TEST-03):

- **MusicCog playback** — queue-from-selection validity guards, next-track/skip selection, and
  queue-persistence restore selection (the auto-queue-vs-stop branch and the `current_index`
  clamp).
- **OpsCog metrics + `/health`** — metrics aggregation and the `degraded_reasons` →
  health-status determination, covering the REL-01 degraded path Phase 9 added.
- **EventsCog ambient roasts** — the trigger/gating decision (chance roll, per-user cooldown,
  late-night eligibility, join/leave/move scenario selection).

Discord/process glue (`interaction.response`, `voice_client.connect/play`, `channel.send`,
`asyncio.create_task`, the live `pool.acquire()` probe) stays **untested-by-design**. The
pure-logic seam established here is explicitly reused by Phase 11 (RAG rerank/dedup functions).

</domain>

<decisions>
## Implementation Decisions

### Seam placement
- **D-01:** Extracted pure functions live in a **new top-level `logic/` package**, one module per
  target: `logic/playback.py`, `logic/health.py`, `logic/roasts.py`. Tests mirror them:
  `tests/test_playback_logic.py`, `tests/test_health_logic.py`, `tests/test_roast_logic.py`.
  - **Why:** a dedicated package is the clearest "pure vs glue" boundary, an obvious import seam,
    and the named home Phase 11 imports from. Preferred over co-locating module-level functions in
    the cog files (the `gather_bot_metrics` precedent) because the phase's whole point is to make
    the testable core visibly separate from Discord glue.

### Refactor approach
- **D-02:** **True extraction** — the live cog method calls the new pure function as its **single
  source of truth**, then a thin glue layer dispatches on the returned decision (e.g.
  `_on_track_end` becomes `action = decide_on_track_end(snapshot)` + a small dispatch on `action`).
  No mirrored/duplicated logic — zero drift risk.
  - **Why:** honors "extracted into pure importable functions" in the roadmap goal, and guarantees
    the tests exercise the code that actually runs. The risk of touching shipped, working playback
    is accepted and **covered by the TEST-04 regression gate** (D-04).

### Test coverage depth
- **D-03:** **Full branch + boundary coverage** for every extracted decision function — not just
  happy-path. Enumerate every branch and boundary, e.g.:
  - `decide_on_track_end`: not-playing → NOOP; next-track exists → PLAY; exhausted + humans +
    AICog → AUTOQUEUE; exhausted + humans + no AICog → STOP; exhausted + no humans → STOP.
  - `determine_health_status`: each critical `degraded_reason` × `HEALTH_STRICT_STATUS` on/off →
    correct (status_code, body) pair; healthy → 200.
  - restore-index clamp: in-range, above-max, negative, non-int, empty-queue.
  - ambient roast: cooldown exactly-at-ceiling vs one-under; chance roll boundaries; late-night
    pass/fail second roll; join vs leave vs move scenario selection.
  - **Why:** pure functions make exhaustive branch testing cheap (no Discord/DB mocking), and this
    phase exists precisely to lock decision logic that has already shipped live bugs — thin
    coverage would leave the exact gaps that bit before.

### Mandatory scar regression tests
- **D-05:** These four previously-untested, live-bug-causing branches **must** have explicit named
  regression tests (on top of the D-03 branch sweep):
  1. **Finished-song replay** — exhausted-queue path returns STOP-and-clear (mirrors `/stop`
     teardown), so the just-finished track is NOT parked on `current_index` and replayed on the
     next restart (v1.1 live-UAT scar; DEPLOY-06 / IN-02).
  2. **Silent auto-queue** — the auto-queue-vs-stop branch selects on the correct ground truth
     (the `is_playing`-flag vs `voice_client.is_playing()` confusion that queued tracks but never
     played them; v1.1 live-UAT scar).
  3. **REL-01 degraded path** — `determine_health_status` returns degraded (503 when strict) for
     each critical reason: MusicCog-not-loaded, DB-unreachable, gateway-not-ready (the path Phase 9
     added).
  4. **Restore index clamp** — a stale / non-int / negative / out-of-range `current_index` is
     clamped into range so it never reaches `get_current()` → `_play_track(None)` (CR-03).

### Regression gate (TEST-04)
- **D-04:** Gate = **full pytest suite green (automated) + a manual bot boot** where the user
  runs `python bot.py`, the bot comes online, and `logs/dexter.log` is eyeballed for new
  ERROR/silent failures. Boot can't be fully automated here (needs the real Discord token + Neon),
  and the bot runs on the user's PC on-demand, so a manual boot check is the pragmatic gate. No new
  silent failures = gate passes.

### Claude's Discretion
- **D-06:** **Input seam shape is the planner's call, per function.** Whether a function takes a
  few primitives + the random roll(s) as float params, or a small frozen snapshot dataclass
  (`PlaybackSnapshot` / `RoastContext`), is decided during planning based on each function's arg
  count and cohesion. **Hard constraint:** decision functions must be **deterministic** — any
  `random.random()` / `time.monotonic()` / `datetime.now()` stays in the cog glue and its result
  is passed IN, so tests need no patching of randomness or clocks.
- **D-07:** Exact pure/glue cut-line per target (which sub-decisions the function owns vs what the
  thin dispatch glue does), exact function names/signatures, and the full per-function edge-case
  list — planner derives these from the branch enumeration in D-03.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope / requirements
- `.planning/ROADMAP.md` § "Phase 10: Critical-Path Test Coverage" — goal, 4 success criteria, the
  4 suggested plan splits (10-01 … 10-04)
- `.planning/REQUIREMENTS.md` — TEST-01 … TEST-04 wording (lines ~26–29)
- `.planning/STATE.md` — accumulated decisions; Phase 10 follows Phase 9 (v1.2)

### Test conventions (locked — follow exactly)
- `.planning/codebase/TESTING.md` — pytest 8.x + pytest-asyncio, `tests/test_*.py`, `Test*`
  classes, `make_track()`-style factories at module top, `unittest.mock` (`MagicMock`/`AsyncMock`/
  `patch`), `pytest.raises(match=...)`, fresh objects per test (no shared state). New logic tests
  follow this exactly; the new files are pure-unit (no async, no mocking needed for the decisions).

### Code the phase extracts FROM (live decision logic + the glue that stays untested)
- `cogs/music.py` — `_on_track_end` (~732, advance/loop/auto-queue-vs-stop + `clear_persisted`
  teardown), `_play_track` validity/`is_playing()` gating (~519/597), and the queue-from-selection
  guards. (TEST-01)
- `cogs/ops.py` — `gather_bot_metrics` (~54, the `degraded_reasons` producer; already module-level)
  and the `degraded_reasons` → HTTP-status mapping currently split into `bot.py`'s `/health`
  handler. (TEST-02)
- `services/queue_persistence.py` — `restore_queues` (~84) `current_index` clamp (~128–135) and
  smart-rejoin selection (the `current` / humans-present gate). (TEST-01 restore selection)
- `cogs/events.py` — `on_voice_state_update` (~166) roast trigger/gating, `_check_ambient_cooldown`
  (~37). `roasts.is_late_night` already pure. (TEST-03)
- `bot.py` — `/health` handler (the `HEALTH_STRICT_STATUS` → 503/200 decision the extracted
  `determine_health_status` will own). (TEST-02)
- `config.py` — thresholds the decisions read: `UNPROMPTED_ROAST_CHANCE`,
  `LATE_NIGHT_ROAST_CHANCE`, `AMBIENT_ROAST_CEILING_SECONDS`, `HEALTH_STRICT_STATUS`,
  `MAX_QUEUE_SIZE_PER_GUILD`.

### Prior context (decisions these tests lock in)
- `.planning/phases/09-reliability-ops-hardening/09-CONTEXT.md` — REL-01 (D-01/D-02 health/degraded
  set) is exactly what TEST-02's degraded-path scar test covers.

### Reference (note: partially stale — verify against live code)
- `.planning/codebase/CONCERNS.md` — dated 2026-06-01 (pre-v1.1); use only as a pointer to fragile
  areas, not current truth.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `models/queue.py` `MusicQueue.advance()` / `.skip()` / `.get_current()` are **already pure and
  already unit-tested** (`tests/test_queue.py`). The new `logic/playback.py` decisions wrap/compose
  these — do NOT re-implement queue mechanics; the new functions decide *what to do with* the
  advance result (play vs auto-queue vs stop-and-clear).
- `gather_bot_metrics` (`cogs/ops.py`) already lives at module level and returns
  `degraded_reasons` — `logic/health.py`'s `determine_health_status` consumes that list (or its
  pure subset) and decides the status; the async DB probe inside `gather_bot_metrics` stays glue.
- `roasts.is_late_night(local_hour)` (`personality/roasts.py`) is already a pure helper the roast
  decision can call.
- `make_track()` factory pattern (`tests/test_queue.py`) — reuse for building playback snapshots.

### Established Patterns
- **Determinism seam:** every "should I roast / what time is it" check already passes an explicit
  `local_hour` computed via `ZoneInfo(config.STREAK_TIMEZONE)` (D-06 scar) — the extracted function
  takes that hour as a param, never calls `datetime.now()` itself. Same discipline for `random` and
  `time.monotonic`.
- **Per-guild fault isolation:** `restore_queues` and `gather_bot_metrics` both `continue`/`pass`
  per guild rather than aborting the loop (CR-01) — the extracted decision is per-guild and pure;
  the loop + error-swallow stays in glue.
- One-assert-ish short tests, scenario-named (`test_<scenario>_<expected>`), per TESTING.md.

### Integration Points
- `logic/playback.py` ← called by `cogs/music.py` `_on_track_end` and the restore path in
  `services/queue_persistence.py`.
- `logic/health.py` ← called by `cogs/ops.py` and `bot.py`'s `/health` handler.
- `logic/roasts.py` ← called by `cogs/events.py` `on_voice_state_update`.
- `logic/` is imported by Phase 11 (RAG rerank/dedup) as the established pure-logic TDD seam.

</code_context>

<specifics>
## Specific Ideas

- User agreed full-branch coverage is the right altitude precisely because this logic has **already
  shipped live bugs** — the phase is a regression lockdown, not a coverage-percentage exercise.
- The four scar tests (D-05) are the emotional core of the phase: each one corresponds to a real
  outage/misbehavior already recorded in CLAUDE.md's "Implementation Gotchas". They must be named
  and findable, not buried in a parametrized sweep.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (Cog/Discord-glue integration tests remain
untested-by-design per the roadmap convention; RAG pure-logic tests are Phase 11, which reuses this
seam.)

</deferred>

---

*Phase: 10-Critical-Path Test Coverage*
*Context gathered: 2026-06-27*
