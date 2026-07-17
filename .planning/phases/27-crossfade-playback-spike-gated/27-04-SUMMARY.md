---
phase: 27-crossfade-playback-spike-gated
plan: 04
subsystem: music
tags: [discord.py, monkeypatch, drift-guard, pytest, audio-cache]

# Dependency graph
requires:
  - phase: 27-02
    provides: "MusicQueue._xf_pending / _xf_truncator playback-handoff state, nulled by clear()"
  - phase: 27-03
    provides: "TruncatingSource._suppress_end_silence, set only at the instant read() cuts short for a fade"
provides:
  - "utils/discord_patch.py::install_send_silence_suppression() — wrapped, fail-soft, idempotent monkeypatch install"
  - "utils/discord_patch.py::send_silence_patch_target_present() — shared existence+call-site assertion for the install and the drift guard"
  - "tests/test_discord_patch.py — a proven-non-vacuous CI drift guard (both drift shapes covered) for the AudioPlayer.send_silence patch target"
  - "bot.py::DexterBot.setup_hook — single install site, before any voice playback can start"
  - "bot.py::cache_cleanup — LFU protected-set now also covers the outgoing track during an in-flight crossfade"
affects: ["27-05 (the /crossfade command and cogs/music.py playback-engine integration land the actual fade behavior this rail exists to protect)"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Wrapped, fail-soft monkeypatch of a third-party undocumented internal: existence+call-site check shared between install and drift guard via one helper, install never raises, import never raises"
    - "Drift guard proven non-vacuous by a mandatory positive control covering both failure shapes separately (attribute removed; attribute present but call site gone) — the invite-drift-guard discipline (Phase 22) applied to a second, unrelated fact"

key-files:
  created:
    - utils/discord_patch.py
    - tests/test_discord_patch.py
  modified:
    - bot.py
    - tests/test_hosting_drift_guard.py

key-decisions:
  - "send_silence_patch_target_present(player_cls=AudioPlayer) is parameterizable so the drift guard's positive control drives the exact same code path the real guard uses, rather than a reimplementation"
  - "bot.py imports `from utils import discord_patch` (module import, not a from-import of the function) so `grep -c install_send_silence_suppression bot.py` returns exactly 1 — the plan's literal acceptance criterion — with the call as the only occurrence"
  - "Task 3's setup_hook insertion shifted a pre-existing bot.py comment from line 684 to 696, invalidating tests/test_hosting_drift_guard.py's hardcoded RENDER_ALLOWLIST entry for that line — fixed as a Rule 1 bug directly caused by this task's edit, not new scope"

patterns-established:
  - "A drift guard's positive control must exercise BOTH ways a fact can drift when there are two (attribute gone vs. attribute present-but-unused) — a single missing-attribute check would leave the call-site regression uncaught"

requirements-completed: [DJ-03]

# Metrics
duration: 20min
completed: 2026-07-17
---

# Phase 27 Plan 04: Send-Silence Suppression Guard Rails Summary

**A wrapped, fail-soft `AudioPlayer.send_silence` monkeypatch (`utils/discord_patch.py`) installed once at boot, backed by a CI drift guard that asserts discord.py's `_do_run` still calls the patched method (not just that it exists) and is proven non-vacuous by a two-shape positive control — plus the one-line LFU fix protecting a crossfade's outgoing cache file from eviction.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-17T19:14:05+08:00
- **Completed:** 2026-07-17T19:23:32+08:00
- **Tasks:** 3 (all `type="auto"`, Tasks 1-2 `tdd="true"`)
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments

- `utils/discord_patch.py::send_silence_patch_target_present(player_cls=AudioPlayer)` asserts both that `AudioPlayer.send_silence` is callable AND that `AudioPlayer._do_run`'s source still contains the string `send_silence` (verified against the pinned discord.py 2.7.1: the method at `discord/player.py:892`, called from `_do_run` at `:796`/`:833`) — shared by the install and the drift guard so they can never assert different things.
- `install_send_silence_suppression()` is fail-soft end to end: target absent → `log.warning` + `return False` (the D-17.4a degrade path, "the 100ms comes back"), any exception during install → caught, logged, `return False`. Idempotent via a module-level `_INSTALLED` marker. Importing the module is unconditionally safe (verified live: deleted `AudioPlayer.send_silence` from the real class, then imported and called the installer with no exception).
- The patched `_patched_send_silence` returns early — suppressing the silence burst — only when `getattr(self.source, "_suppress_end_silence", False)` is truthy; every other source (crossfade off, or any non-fade cut) falls through to the original, unchanged method. No `import services.audio`, no `isinstance` check (both asserted at 0 via grep in the plan's acceptance criteria).
- `tests/test_discord_patch.py`: `test_send_silence_patch_target_exists` (VALIDATION row 17) is the real drift guard. `test_drift_guard_actually_detects_a_mismatch` is the mandatory positive control, covering both drift shapes separately — a stand-in class with no `send_silence` at all, and (the shape a naive `hasattr` guard would miss) a stand-in that has `send_silence` but whose `_do_run` never calls it. `test_drift_guard_accepts_the_canonical_target` is the negative control. `test_patch_install_fails_soft` (row 18) uses `monkeypatch.delattr` and asserts a clean `False` return with no exception. `test_install_is_idempotent` locks Task 1's no-double-wrap acceptance criterion. A module-scoped autouse fixture restores the real `AudioPlayer.send_silence` and the install marker after every test so no patch state leaks into the rest of the suite.
- `bot.py::DexterBot.setup_hook` calls `discord_patch.install_send_silence_suppression()` as the single install site, before any voice playback can start, logging the installed-vs-degraded outcome at info.
- `bot.py::cache_cleanup`'s protected-set loop now also protects `queue.tracks[queue.current_index - 1]` when a crossfade is in flight (`_xf_truncator`/`_xf_pending` set) and `current_index > 0` (bounded so it can never go negative or IndexError) — a latent-accounting fix for the outgoing file's LFU eligibility that does not manifest as a failure on either platform today, documented as such in the code comment.

## Task Commits

Each task was committed atomically:

1. **Task 1: utils/discord_patch.py — the wrapped, fail-soft, source-attribute-gated install** - `db5e20a` (feat)
2. **Task 2: tests/test_discord_patch.py — the drift guard + mandatory positive control** - `63d3e03` (test)
3. **Task 3: bot.py — single install site + fade-aware LFU protected set** - `7ad8672` (feat)

## Files Created/Modified

- `utils/discord_patch.py` (new) - `send_silence_patch_target_present()` + `install_send_silence_suppression()`, the D-17 wrapped fail-soft monkeypatch
- `tests/test_discord_patch.py` (new) - Drift guard, mandatory positive control (both drift shapes), negative control, fail-soft install test, idempotency test
- `bot.py` - `setup_hook` install call site; `cache_cleanup` protected-set fade-awareness
- `tests/test_hosting_drift_guard.py` - `RENDER_ALLOWLIST` line number for the pre-existing `bot.py` T-19-02 comment updated 684→696 (shifted by Task 3's insertion above it)

## Decisions Made

- Used `from utils import discord_patch` + `discord_patch.install_send_silence_suppression()` in `bot.py` rather than a `from`-import of the bare function name, so the literal string `install_send_silence_suppression` appears exactly once in the file — satisfying the plan's literal `grep -c` acceptance criterion rather than just its intent.
- `send_silence_patch_target_present` takes an optional `player_cls` parameter (defaulting to the real `AudioPlayer`) specifically so the drift guard's positive control drives the identical code path as the real guard, per the plan's explicit instruction.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `tests/test_hosting_drift_guard.py` RENDER_ALLOWLIST line number shifted by this plan's own edit**
- **Found during:** Task 3 (bot.py wiring) — first full-suite run
- **Issue:** `setup_hook`'s new lines pushed a pre-existing, unrelated `bot.py` comment (`_build_guild_notice_embed`'s T-19-02 docstring, containing the word "rendered") from line 684 to line 696. `tests/test_hosting_drift_guard.py::test_render_hits_are_all_allowlisted` (a Phase 24 hosting-honesty guard) hardcodes `("bot.py", 684)` in its allowlist and failed once the line moved.
- **Fix:** Updated the allowlist tuple to `("bot.py", 696)`.
- **Files modified:** tests/test_hosting_drift_guard.py
- **Verification:** `pytest tests/test_hosting_drift_guard.py -q` → 7 passed; full suite re-run green.
- **Committed in:** `7ad8672` (part of Task 3 commit, since it was caused by that task's edit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug directly caused by this plan's own line insertion into a file another test hardcodes line numbers against)
**Impact on plan:** No scope creep — a one-line fix to an assertion this plan's own change invalidated.

## Issues Encountered

None beyond the deviation above. The full suite run took ~7 minutes each of the two times it was run (423-430s) — well within normal bounds, no live-DB tests execute locally (`TEST_DATABASE_URL` unset, 129 skipped both runs).

## User Setup Required

None - no external service configuration required. Zero new dependencies (`inspect` is stdlib; discord.py is already pinned at 2.7.1).

## Next Phase Readiness

- Both D-17 mandatory guard rails are shipped: the fail-soft install (D-17.4a) and the non-vacuous drift guard (D-17.4b). Plan 27-05 (the `/crossfade` command + `cogs/music.py` playback-engine integration) can now wire `TruncatingSource`/`CrossfadeSource` into real playback with the silence-suppression rail already in place at boot.
- Full suite green at **1221 passed, 129 skipped, 0 failed** (above the 1175 baseline, and above 27-03's 1215 baseline). `ruff check .` clean repo-wide. `ruff format --check .` clean for every file this plan touched (3 pre-existing drift files — `services/memory.py`, `tests/test_database_phase25.py`, `tests/test_vision_events.py` — remain untouched and out of scope, already logged in `deferred-items.md` by plan 27-02).
- `python -c "import utils.discord_patch"` succeeds unconditionally, including with `AudioPlayer.send_silence` deleted (verified live).
- No blockers.

---
*Phase: 27-crossfade-playback-spike-gated*
*Completed: 2026-07-17*

## Self-Check: PASSED

All created/modified files found on disk; all 4 commit hashes (db5e20a, 63d3e03, 7ad8672, 7adc42e) found in git log.
