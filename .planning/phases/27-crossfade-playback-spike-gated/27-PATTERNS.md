# Phase 27: Crossfade Playback (Spike-Gated) - Pattern Map

**Mapped:** 2026-07-17
**Files analyzed:** 10 (2 new, 6 modified, 2 new-ish/novel)
**Analogs found:** 9 / 10 (one genuinely novel — see §No Analog Found)
**Gate outcome:** D-17 = **GO / suppressed variant** → implementation files are in play.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `logic/crossfade.py` **(NEW)** | pure logic seam | transform (verdict) | `logic/playback.py` (enum verdict) + `logic/radio.py` (gate ordering) | **exact** |
| `tests/test_crossfade_logic.py` **(NEW)** | test | transform | `tests/test_playback_logic.py` | **exact** |
| `services/audio.py` **(MOD)** | service | streaming / file-I/O | in-file: `get_source`'s `use_opts` fork + `_build_ffmpeg_opts` | **exact (self)** |
| `cogs/music.py` — `/crossfade on\|off` **(MOD)** | controller | request-response | `cogs/music.py::autolyrics` (`:1973-1995`) | **exact** |
| `cogs/music.py` — `_play_track` glue **(MOD)** | glue (untested-by-design) | event-driven | in-file: `_on_track_end`'s `TrackEndAction` dispatch | **exact (self)** |
| `models/queue.py` **(MOD)** | model | state | `MusicQueue.auto_lyrics` (pref) + `radio_armed` (playback state) | **exact** |
| `config.py` **(MOD)** | config | — | `RADIO_LOOKAHEAD_DEPTH` block (`config.py:313-329`) | **exact** |
| `tests/test_audio.py` **(MOD)** | test | file-I/O | in-file: `TestBuildFfmpegOpts` / `TestCacheLookup` | **exact (self)** |
| `tests/test_queue.py`, `tests/test_queue_persistence.py`, `tests/test_responses.py` **(MOD)** | test | state | existing radio/`auto_lyrics` cases in those files | role-match |
| **`send_silence` monkeypatch install** (D-17.4a — wrapped/guarded) | glue / library integration | event-driven | **none** | **NO ANALOG** |
| **`send_silence` CI drift guard** (D-17.4b) | test | transform | `tests/test_invite_drift_guard.py` | **role-match (strong)** |

---

## Pattern Assignments

### `logic/crossfade.py` (NEW — pure logic seam, D-14)

**Analog:** `logic/playback.py` (the enum-verdict convention) + `logic/radio.py` (the most recent seam; gate-ordering docstring style).

**Module docstring pattern** — `logic/radio.py:1-23`. Note it names the purity contract explicitly, names the *sibling* seams it follows, lists what the caller still must do, and names its lock file. Copy this four-part shape:

```python
"""Pure radio refill-gate decision seam (Phase 26 / DJ-01 / D-19).

All functions in this module are deterministic and side-effect-free: no ``discord``,
no ``asyncio``, no ``random``, no ``datetime``, no database access.

Any nondeterministic or I/O-derived value (whether radio is armed, whether humans
are present in voice, how many tracks remain in the queue, the session's played-set)
is computed by the calling cog glue and passed in as a primitive — following the
established seam pattern from ``logic/proactive.py`` (Phase 16) and ``logic/vision.py``
(Phase 17).

This module implements only the DECISION of whether/what to gate. The caller still
must:
    - dispatch the actual ``try_auto_queue(guild, radio=True)`` call when ...

Locked by tests/test_radio_logic.py (mock-free boundary coverage).
"""

from __future__ import annotations

import config
```

> `import config` at module level for knob defaults IS the convention (`logic/radio.py:27`, `logic/skip_vote.py`). It does not violate purity.
> **`logic/crossfade.py` must NOT `import discord`** — `logic/invite.py` is the ONE documented exception in `logic/` and crossfade is not it.

**Enum-verdict pattern** — `logic/playback.py:32-50`. Each member carries a docstring stating *what the glue must do*, not just what happened. RESEARCH §3's `FadeVerdict` should be written this way:

```python
class TrackEndAction(enum.Enum):
    """What the ``_on_track_end`` glue should do after consulting ``decide_on_track_end``."""

    NOOP = "noop"
    """Queue was already stopped manually — do nothing."""

    AUTOQUEUE = "autoqueue"
    """Queue exhausted but humans are present and AICog is loaded — trigger auto-queue.
    The glue must NOT set ``is_playing = False`` on this path; auto-queue will handle it.
    """
```

**Keyword-only gate-ladder pattern** — `logic/radio.py:34-89`. Cheapest gate first, one numbered comment per rung, config default bound in the signature. This is the exact shape for `decide_crossfade`'s 7-rung ladder (RESEARCH "Narrow-go exclusions" table = the rung order):

```python
def should_refill_radio(
    *,
    armed: bool,
    humans_present: bool,
    upcoming_count: int,
    lookahead_depth: int = config.RADIO_LOOKAHEAD_DEPTH,
) -> bool:
    # Gate 1: armed (cheapest check — SC-2/D-07: disarmed never refills)
    if not armed:
        return False

    # Gate 2: humans present (never burn budget refilling an empty room — T-26-02)
    if not humans_present:
        return False

    # Gate 3: runway — refill while tracks remain, trigger at/below the lookahead depth
    if upcoming_count > lookahead_depth:
        return False

    return True
```

**Arithmetic-helper pattern** (for `cut_frame`) — `logic/skip_vote.py`'s `required_votes` docstring makes the "glue must never re-derive this" rule explicit:

```
Glue dispatches on the returned ``SkipVerdict`` and must never re-derive this
arithmetic itself (Phase 10 D-02 rule) — always call ``required_votes`` for
the same number that drives the D-18 tally's ``{required}`` slot.
```

---

### `tests/test_crossfade_logic.py` (NEW — mock-free unit tests)

**Analog:** `tests/test_playback_logic.py`

**Header pattern** (`tests/test_playback_logic.py:1-23`) — states the no-mock contract, states the cut-line test ("if a test needs a mock the cut-line is wrong"), and **names the scar regressions by test name**:

```python
"""Exhaustive pure-unit tests for logic/playback.py (TEST-01 / D-03 / D-05).

No mocks, no clocks, no RNG — all inputs are plain Python primitives.
If a test needs a mock the cut-line in logic/playback.py is wrong (D-06).

Named scar regression tests (D-05):
  - test_finished_song_returns_stop_and_clear   (scar #1: replay, DEPLOY-06 / IN-02)
  - test_autoqueue_selected_on_voice_client_ground_truth  (scar #2: silent auto-queue)
  - test_stale_index_clamped_into_range         (scar #4: restore clamp, CR-03)
"""

import pytest

import config
from logic.playback import (
    TrackEndAction,
    decide_on_track_end,
    ...
)
```

**Class-per-function + one-line-intent-docstring pattern** (`:29-45`):

```python
class TestDecideOnTrackEnd:
    """Full branch coverage for decide_on_track_end (D-03)."""

    def test_not_playing_returns_noop(self):
        """Manual stop: is_playing=False → NOOP, no matter what else is true."""
        result = decide_on_track_end(
            is_playing=False,
            has_next=True,
            connected=True,
            humans_present=True,
            aicog_loaded=True,
        )
        assert result == TrackEndAction.NOOP
```

> For `test_ladder_precedence` (RESEARCH's test map), the `test_not_playing_returns_noop` shape is the direct model: set every *later* rung to its firing value and assert the *earlier* rung still wins.

---

### `services/audio.py` (MODIFY — `TruncatingSource`, `CrossfadeSource`, `crossfade_from=` kwarg)

**Analog:** the file itself. Two in-file precedents.

**1. The pure-function-beside-the-I/O precedent** (`services/audio.py:24-44`) — the D-14 split in miniature. Note the docstring's explicit **"Pure function — fully unit-testable"** claim and the passthrough-equivalence note:

```python
def _build_ffmpeg_opts(seek_seconds: int = 0, ffmpeg_filter: str | None = None) -> dict:
    """Build FFmpeg before_options/options for a seeked or filtered source.

    - Always includes reconnect flags in before_options.
    - Prepends -ss {seek_seconds} only when seek_seconds > 0.
    ...
    - With neither seek nor filter the result is equivalent to FFMPEG_STREAM_OPTS
      (reconnect flags + -vn), so callers can safely pass the result through
      without special-casing the passthrough default.

    Pure function — fully unit-testable (no FFmpeg invocation).
    """
```

**2. The additive-kwarg + conditional-ladder pattern** (`services/audio.py:69-131`) — this is the exact structure the `crossfade_from=` kwarg extends. The `use_opts` fork is computed **once at the top** and each ladder rung re-forks on it. RESEARCH §4's "omitted = byte-identical" discipline maps directly onto the existing `not use_opts` branches:

```python
async def get_source(
    self,
    track: Track,
    *,
    seek_seconds: int = 0,
    ffmpeg_filter: str | None = None,
) -> discord.AudioSource:
    """Get a playable audio source for a track.

    When seek_seconds == 0 and ffmpeg_filter is None the existing
    opus-passthrough behaviour is preserved exactly (D-12): cached tracks
    use FFmpegOpusAudio with no extra options, downloaded tracks likewise.
    A transcode path is taken ONLY when a seek or filter is requested.
    """
    cached = self.cache_path(track.video_id)
    use_opts = seek_seconds > 0 or ffmpeg_filter is not None

    # 1. Cache hit
    if cached.exists():
        log.info(f"Cache hit for {track.video_id}")
        if not use_opts:
            # Opus passthrough — D-12 default path, unchanged
            return discord.FFmpegOpusAudio(str(cached))
        opts = _build_ffmpeg_opts(seek_seconds, ffmpeg_filter)
        return discord.FFmpegOpusAudio(str(cached), **opts)

    # 2. Try downloading to cache (bounded by DOWNLOAD_TIMEOUT_SECONDS — PERF-04 / D-10/D-11)
    ...
    # 3. Stream fallback — re-extract for fresh URL
    log.warning(f"Download failed for {track.video_id}, falling back to stream")
```

> **The `# Opus passthrough — D-12 default path, unchanged` comment at `:96` is the invariant the byte-identical-when-off guard protects.** RESEARCH's ladder evidence (`source=FFmpegOpusAudio` in every non-fading row) is literally this branch still being taken.

**3. Error-tolerance-in-a-loop pattern for `CrossfadeSource.cleanup()`** (`services/audio.py:179-185`) — the in-file precedent for "one failing teardown must not abort the rest". RESEARCH §4 requires the head cleaned in a `finally`; this is the same instinct already in the codebase:

```python
try:
    f.unlink()
except OSError as e:
    # One un-deletable file (locked/in-use on Windows, permissions)
    # must not abort the whole pass and leave the cache over the cap.
    log.warning("cache evict failed video_id=%s: %s", vid, e)
    continue
```

**4. `cleanup_cache` protected-set** (`services/audio.py:133-138`, `:164-169`) — RESEARCH landmine #3 (the outgoing track's file is eviction-eligible during a fade). The protected set is built by the **caller** (`bot.py:1043`), not here; `eviction_key` sorts protected files to `float("inf")`:

```python
def eviction_key(f: Path):
    vid = f.stem
    if vid in protected_video_ids:
        return (float("inf"), 0)
    return (play_counts.get(vid, 0), f.stat().st_mtime)
```

---

### `cogs/music.py` — `/crossfade on|off` (MODIFY — controller, request-response)

**Analog:** `cogs/music.py::autolyrics` (`:1973-1995`) — same shape exactly: one choice arg, in-memory per-guild toggle, no cooldown, `AllowedMentions.none()` on both branches, lowercase copy, no emoji.

**Copy this verbatim and rename** (`:1973-1995`):

```python
@app_commands.command(name="autolyrics", description="Auto-post each song's lyrics to a lyrics thread")
@app_commands.choices(
    mode=[
        app_commands.Choice(name="on", value="on"),
        app_commands.Choice(name="off", value="off"),
    ]
)
async def autolyrics(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
    """Toggle auto-lyrics for this server (in-memory; resets on restart)."""
    queue = self.get_queue(interaction.guild.id)
    none = discord.AllowedMentions.none()
    if mode.value == "on":
        queue.auto_lyrics = True
        await interaction.response.send_message(
            "fine. i'll narrate your questionable taste in a thread. enjoy.",
            allowed_mentions=none,
        )
    else:
        queue.auto_lyrics = False
        await interaction.response.send_message(
            "auto-lyrics off. blessed silence.",
            allowed_mentions=none,
        )
```

Notes for the planner:
- **No `defer()`** — a pure in-memory toggle responds immediately, well inside the 3s rule.
- **No cooldown decorator** — `/autolyrics` has none; `/filter` has `FILTER_COOLDOWN_SECONDS`. Follow `/autolyrics` (D-09b says "the `/autolyrics` shape").
- Copy tone: lowercase, ≤1 emoji, dry. `tests/test_responses.py::test_crossfade_copy_style` locks this.

---

### `cogs/music.py` — `_play_track` / `_on_track_end` glue (MODIFY — untested-by-design)

**Analog:** the file itself. RESEARCH §5 names the two insertion points precisely.

**Integration point 1** — immediately after `get_source`, *before* the generation increment (`cogs/music.py:664-676`):

```python
# Resolve the active audio filter chain (Phase 7, D-10, D-12)
ffmpeg_filter: str | None = None
if queue.active_filter != "off":
    ffmpeg_filter = config.FFMPEG_FILTERS.get(queue.active_filter)

# Time-to-first-audio starts now: from source acquisition (cache/copy or
# cold download + ffmpeg spawn) through to voice_client.play() (PERF-06).
_ttfa_t0 = time.monotonic()
try:
    source = await self.audio.get_source(
        track,
        seek_seconds=offset_seconds,
        ffmpeg_filter=ffmpeg_filter,
```

> `queue.active_filter != "off"` at `:666` is the exact expression `decide_crossfade(filter_active=...)` should be fed. Do **not** re-derive it — reuse the resolved local.

**The block that must stay verbatim** (`cogs/music.py:700-712`) — D-01's subject. Everything here is untouched; the crossfade wrap happens *above* it:

```python
# Increment generation — any old after-callbacks will see a stale generation and bail
log.debug("gen=%d → %d in guild %d", queue._play_generation, queue._play_generation + 1, guild.id)
queue._play_generation += 1
current_gen = queue._play_generation

def after_callback(error):
    if error:
        log.error(f"Playback error in guild {guild.id}: {error}")
    # Only advance if this callback belongs to the current generation
    if queue._play_generation == current_gen:
        asyncio.run_coroutine_threadsafe(self._on_track_end(guild), self.bot.loop)
```

**Dispatch-on-verdict pattern** — `_on_track_end` already consults `decide_on_track_end` and dispatches on `TrackEndAction`. The crossfade glue must do the same with `FadeVerdict`: `if verdict is FadeVerdict.FADE: wrap` / `else: log.info("crossfade: hard cut (%s)", verdict.value)` — **never re-derive a rung** (Phase 10 D-02).

**D-10b log-only fallback**: the `log.warning(f"Download failed for {track.video_id}, falling back to stream")` at `services/audio.py:121` is the tone precedent — a silent degrade with a log line and nothing user-facing.

---

### `models/queue.py` (MODIFY — the D-12 toggle + the `_xf_*` playback state)

**Analog:** `MusicQueue.auto_lyrics` (`:78-80`) for the **preference**, `radio_armed` (`:90-108`) for the **playback state**. RESEARCH §7 needs *both* — this is the one file where two different analogs apply to two different fields.

**Preference pattern** (`models/queue.py:78-80`) — sits **above** the playback-state block, carries a comment explaining why `clear()` skips it:

```python
# Auto-lyrics: per-guild, in-memory. Deliberately NOT reset by clear() —
# it's a server preference, not playback state. Resets only on restart.
self.auto_lyrics: bool = False
```

→ `self.crossfade_enabled: bool = False` goes here, with the same comment shape.

**Playback-state pattern** (`models/queue.py:90-99`) — note the comment explicitly names *why* it's reset and *why* it's unpersisted-by-construction. `_xf_pending` / `_xf_truncator` follow this:

```python
# Phase 26: radio mode state (DJ-01 / A3). Radio is PLAYBACK state, like
# loop_mode — NOT a server preference like auto_lyrics above. That's why
# it's reset by clear() (see clear() below): every existing queue-teardown
# site (/stop, the stop button, idle_check, reconnect-failure) already
# calls clear(), so all four become D-07 disarm sites for free, with zero
# bot.py changes. Never persisted (D-08) — services/queue_persistence.py's
# persist() builds an explicit typed key dict (tracks/current_index/
# loop_mode/text_channel_id/active_filter), never __dict__, so these new
# fields are unpersisted by construction.
self.radio_armed: bool = False
```

**`clear()` pattern** (`models/queue.py:247-273`) — grouped by phase with a comment per group. `crossfade_enabled` is **absent** from this method by design; the `_xf_*` nulls join the playback-state groups:

```python
def clear(self) -> None:
    """Reset the queue to empty state."""
    self.tracks.clear()
    self.current_index = 0
    ...
    # Keep the play-generation counter monotonic — resetting to 0 here would
    # let a stale prefetch/after-callback from before this clear() collide
    # with the next track's generation and fire on it (the exact double-play
    # race the counter exists to prevent — CLAUDE.md). Teardown sites
    # pre-increment, so clear() must only ever advance, never rewind.
    self._play_generation += 1
    # Phase 7 playback state (NOT server preferences like auto_lyrics)
    self.active_filter = "off"
    ...
    # Phase 26 (DJ-01, A3/D-07/D-08): radio is playback state and dies with
    # the queue. This single line is what makes /stop, the stop button's
    # _do_stop, bot.py::idle_check's idle-leave, and the reconnect-failure
    # teardown all disarm radio — every one of them already calls clear(),
    # so SC-2 needs no per-site edit.
    self.disarm_radio()
```

> **The "every teardown site already calls `clear()`, so this needs no per-site edit" property is exactly what `_xf_pending`/`_xf_truncator` inherit for free.** Same reasoning, no new teardown sites.

**`upcoming()`** (`:275-277`) — the incoming-track read a fade needs:

```python
def upcoming(self) -> list[Track]:
    """Return tracks after the current one."""
    return self.tracks[self.current_index + 1 :]
```

---

### `tests/test_queue_persistence.py` (MODIFY — the not-persisted guard)

**Analog:** the typed-key dict at `services/queue_persistence.py:49-56` — the thing the test asserts against. **No new code is needed to make crossfade unpersisted**; the test locks the existing construction:

```python
payload = {
    "tracks": [t.to_dict() for t in queue.tracks],
    "current_index": queue.current_index,
    "loop_mode": queue.loop_mode.value,
    "text_channel_id": queue._text_channel_id,
    "voice_channel_id": voice_channel_id,
    "active_filter": queue.active_filter,  # Phase 7: persist sticky filter (D-10)
}
```

> Test shape: set `queue.crossfade_enabled = True`, persist, assert the key is absent from the payload — i.e. assert **`__dict__` was never used**. Mirror whatever the existing `radio_armed`-not-persisted test in this file does.

---

### `config.py` (MODIFY — global knobs)

**Analog:** the Phase 26 radio block (`config.py:313-329`). Convention: knob + inline `#` comment naming the decision ID and the rejected alternative:

```python
RADIO_LOOKAHEAD_DEPTH = 2  # D-10: refill trigger — tracks remaining after advance
RADIO_ALREADY_PLAYED_HINT_CAP = 25  # D-03: prompt-hint cap; the hard filter is uncapped
...
SKIP_VOTE_MAJORITY_RATIO = 0.5
```

→ RESEARCH §6's `CROSSFADE_SECONDS = 4` / `CROSSFADE_MIN_TRACK_SECONDS = 20` go in this style. Global only — **no `guild_config` column** (Phase 26 D-21).

---

## Shared Patterns

### Purity contract for `logic/`
**Source:** `logic/radio.py:1-10`, `logic/playback.py:1-21`
**Apply to:** `logic/crossfade.py`
Every seam's docstring opens with the same negative assertion. `import config` is allowed; `import discord` is not (`logic/invite.py` is the one exception and it is documented as such).

### Glue dispatches on the verdict, never re-derives it
**Source:** `logic/playback.py:32-50` + `logic/skip_vote.py`'s "must never re-derive this arithmetic itself (Phase 10 D-02 rule)"
**Apply to:** `logic/crossfade.py`, `cogs/music.py::_play_track`

### Additive kwarg, byte-identical when omitted
**Source:** `services/audio.py:78-82` ("the existing opus-passthrough behaviour is preserved exactly (D-12)") + the `# Opus passthrough — D-12 default path, unchanged` comment at `:96`
**Apply to:** `get_source(crossfade_from=...)`, and the `tests/test_audio.py::test_get_source_unchanged_without_crossfade` guard

### Silent conditional degradation + one log line
**Source:** `services/audio.py:108-113`, `:121`
**Apply to:** every non-`FADE` rung (D-10b)

### In-memory per-guild toggle command
**Source:** `cogs/music.py:1973-1995`
**Apply to:** `/crossfade on|off`, `models/queue.py::crossfade_enabled`

---

## No Analog Found

| File / Element | Role | Data Flow | Reason |
|---|---|---|---|
| **The guarded `AudioPlayer.send_silence` monkeypatch install** (D-17.4a) | glue / library integration | event-driven | **Genuinely novel — flagging rather than forcing a match.** I grepped `bot.py`, `cogs/`, `services/`, `utils/`, `logic/` for `hasattr(discord`, `getattr(discord`, `monkeypatch`, `_original_` — **zero hits.** This codebase has never patched, wrapped, or capability-checked a third-party internal in production code. **The closest thing in the repo is not close**: `cogs/music.py::lyrics` uses `hasattr` to guard against *its own* service being unwired at cold start ("guarded with hasattr so a cold-start without the service degrades cleanly" — CLAUDE.md), which is a first-party wiring check, not a library-drift guard. **The planner must treat this as new structure with no house style to copy**, and D-17.4 makes both rails mandatory plan content, not discretion: (a) the install must `getattr`/`hasattr`-guard so a moved target **degrades to "the 100ms returns" rather than crashing at boot** — RESEARCH Round 2's risk table is explicit that a bare `_original_send_silence = AudioPlayer.send_silence` raises `AttributeError` **at import**; (b) the source-attribute gate (`_suppress_end_silence`) is what keeps the off path byte-identical — nothing else sets it. |

**Partial-match note — the CI drift guard (D-17.4b) DOES have a strong analog:** `tests/test_invite_drift_guard.py`. It is the repo's only precedent for a test whose job is "fail the build when an external fact drifts," and its structure transfers directly:

```python
"""Repo-introspection drift guard for Dexter's invite URL (Phase 22 / INVITE-02 ...).

The main guard (``test_no_doc_contains_a_drifted_invite_url``) passes vacuously
today — zero tracked non-``.planning/`` docs currently carry an OAuth2 URL. That
vacuous pass is proven NOT a false green by
``test_drift_guard_actually_detects_a_mismatch``, a mandatory positive control
that feeds a deliberately-wrong URL through the exact same comparison function
the real guard uses.

Tests:
- test_no_doc_contains_a_drifted_invite_url        — THE guard (T-22-02)
- test_drift_guard_actually_detects_a_mismatch      — mandatory positive control (T-22-02a)
- test_drift_guard_accepts_the_canonical_url        — negative control for the positive control
"""
```

> **The load-bearing lesson: the invite guard ships a mandatory positive control proving it is not a no-op.** `test_send_silence_patch_target_exists` should carry the same discipline — assert `AudioPlayer.send_silence` exists *and* that `_do_run`'s source still calls it (RESEARCH cites `discord/player.py:892` for the method, `:833`/`:796` for the call sites), plus a control proving the assertion can actually fail. A guard that only checks `hasattr(AudioPlayer, "send_silence")` would silently pass if discord.py kept the method but stopped calling it — which is exactly the drift that would resurrect the 100ms without anyone noticing.

---

## Metadata

**Analog search scope:** `logic/`, `services/`, `models/`, `cogs/`, `tests/`, `config.py`, `bot.py`, `utils/`
**Files scanned:** 14 (read/grepped); 9 analogs extracted
**Pattern extraction date:** 2026-07-17
</content>
</invoke>
