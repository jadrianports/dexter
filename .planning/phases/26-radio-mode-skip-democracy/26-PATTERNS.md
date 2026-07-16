# Phase 26: Radio Mode & Skip Democracy - Pattern Map

**Mapped:** 2026-07-16
**Files analyzed:** 12 (2 new logic modules, 3 new test files, 7 modified files)
**Analogs found:** 12 / 12

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `logic/radio.py` (NEW) | pure decision seam | request-response (sync gate) | `logic/proactive.py::should_fire_proactive_callback` | exact |
| `logic/skip_vote.py` (NEW) | pure decision seam | request-response (sync gate, enum verdict) | `logic/playback.py::decide_on_track_end` (enum) + `logic/vision.py` (gate style) | exact |
| `tests/test_radio_logic.py` (NEW) | test | unit/pure | `tests/test_proactive_logic.py` (referenced, same convention as `logic/proactive.py` docstring) | role-match |
| `tests/test_skip_vote_logic.py` (NEW) | test | unit/pure | `tests/test_playback_logic.py` (enum-verdict pure tests) | role-match |
| `tests/test_music_wiring.py` (NEW, or extend existing) | test | structural/source-scan | `tests/test_autoqueue_wiring.py` | exact |
| `cogs/music.py` (MODIFIED) | controller (Discord cog) | request-response + event-driven | itself (existing `_do_skip`/`skip`/`skip_button`/`_on_track_end`) | n/a — modified in place |
| `cogs/ai.py` (MODIFIED) | controller/service (Discord cog) | request-response (Gemini call) | itself (`try_auto_queue`) | n/a — modified in place |
| `models/queue.py` (MODIFIED) | model | CRUD (in-memory state) | itself (`auto_lyrics` precedent) | n/a — modified in place |
| `models/server_state.py` (MODIFIED) | model | CRUD (in-memory state) | itself (`auto_queue_rounds`/`reset_auto_queue`) | n/a — modified in place |
| `cogs/library.py` pattern reuse (READ-ONLY analog) | controller (subcommand group) | request-response | `playlist = app_commands.Group(...)` | exact (for `/radio` group shape) |
| `personality/responses.py` (MODIFIED) | config/data (response pools) | transform (template + format) | itself (`SKIPS_RATE_ROASTS`, `AUTO_QUEUE_ANNOUNCE`) | exact |
| `config.py` (MODIFIED) | config | n/a | itself (`AUTO_QUEUE_*` knob block) | exact |

## Pattern Assignments

### `logic/radio.py` (pure decision seam, NEW)

**Analog:** `logic/proactive.py::should_fire_proactive_callback` (also read `logic/vision.py` for the alternate gate-with-default-config-kwarg shape)

**Module docstring pattern** (mirror `logic/proactive.py:1-19`):
```python
"""Pure radio refill-gate decision seam (Phase 26 / DJ-01 / D-19).

All functions in this module are deterministic and side-effect-free: no ``random``,
no ``asyncio``, no ``datetime``, no ``discord``.

Any nondeterministic value (voice-client state, the live queue depth, the
session played-set) is computed by the calling cog glue and passed in as a
primitive — following the established seam pattern from ``logic/proactive.py``
/ ``logic/vision.py`` (Phase 16/17 convention).

Locked by tests/test_radio_logic.py (mock-free boundary coverage).
"""

from __future__ import annotations

import config
```

**Core gate pattern — cheapest-gate-first, keyword-only** (mirror `logic/proactive.py:30-90`):
```python
def should_refill_radio(
    *,
    armed: bool,
    upcoming_count: int,
    lookahead_depth: int = config.RADIO_LOOKAHEAD_DEPTH,
) -> bool:
    """Decide whether _on_track_end should trigger a radio refill.

    1. Armed gate: not armed -> False immediately (cheapest check).
    2. Lookahead gate: upcoming_count > lookahead_depth -> False (still enough
       runway; Phase 6 prefetch has what it needs).
    3. Both gates passed -> True.
    """
    if not armed:
        return False
    if upcoming_count > lookahead_depth:
        return False
    return True
```

**Session played-set filter** (independent hard gate — mirror `logic/autoqueue.py::is_recently_skipped_artist`'s shape, a simple pure membership check):
```python
def is_already_played(video_id: str, played_set: frozenset[str]) -> bool:
    """D-03 independent hard post-filter — reject a duplicate after YouTube
    resolution, mirroring is_recently_skipped_artist's role in try_auto_queue."""
    return video_id in played_set
```

**Note on scope (from RESEARCH):** async I/O (the actual `try_auto_queue` Gemini/YouTube call, the seed-anchor prompt build) stays in `cogs/ai.py` glue — this module only holds the synchronous armed/lookahead/played-set boolean logic, exactly as `logic/proactive.py` explicitly defers its D-02 step 4 recall-floor check to glue (see its docstring lines 10-18).

---

### `logic/skip_vote.py` (pure decision seam, NEW)

**Analog:** enum-verdict convention from `logic/playback.py::TrackEndAction`/`decide_on_track_end`, combined with the keyword-only gate style of `logic/vision.py`/`logic/proactive.py`.

**Enum + module docstring pattern** (mirror `logic/playback.py:1-51`):
```python
"""Pure skip-vote decision seam (Phase 26 / DJ-02 / D-19).

All functions in this module are deterministic and side-effect-free: no Discord
imports, no asyncio, no database calls, no random, no datetime.now().

Any nondeterministic value (live voice-channel membership, the in-memory
per-track vote set) is computed by the calling cog glue and passed in as a
primitive — following logic/playback.py's TrackEndAction dispatch convention.

Locked by tests/test_skip_vote_logic.py (mock-free boundary coverage,
especially the D-09c strict-majority arithmetic at n=1/2/3/4 listeners).
"""

from __future__ import annotations

import enum


class SkipVerdict(enum.Enum):
    """What the shared skip choke point should do after consulting decide_skip."""

    SKIP_NOW = "skip_now"
    """Solo listener, requester bypass, or the vote just reached majority — skip immediately."""

    VOTE_RECORDED = "vote_recorded"
    """A new, valid vote was recorded; majority not yet reached."""

    ALREADY_VOTED = "already_voted"
    """Idempotent re-vote from the same user (D-14) — no state change."""
```

**Core decision function — strict majority arithmetic (D-09c)**:
```python
def decide_skip(
    *,
    voter_id: int,
    is_requester: bool,
    listener_ids: frozenset[int],
    existing_votes: frozenset[int],
) -> tuple[SkipVerdict, frozenset[int]]:
    """Mirrors decide_on_track_end's branch-tree-as-pure-function shape
    (logic/playback.py:58-94). Returns (verdict, updated_votes_set); glue
    dispatches on the verdict and never re-branches (Phase 10 D-02 rule).

    D-13a: track requester always bypasses (single equality, no special-case
    for bot.user.id — D-13b falls out for free).
    SC-4: a solo listener (<=1 non-bot member) always skips instantly.
    D-09c: strict majority = len(listener_ids) // 2 + 1.
    D-14: a repeat vote from the same voter_id is idempotent (ALREADY_VOTED).
    """
    if is_requester:
        return SkipVerdict.SKIP_NOW, existing_votes
    if len(listener_ids) <= 1:
        return SkipVerdict.SKIP_NOW, existing_votes
    if voter_id in existing_votes:
        return SkipVerdict.ALREADY_VOTED, existing_votes
    new_votes = existing_votes | {voter_id}
    required = len(listener_ids) // 2 + 1
    if len(new_votes & listener_ids) >= required:
        return SkipVerdict.SKIP_NOW, new_votes
    return SkipVerdict.VOTE_RECORDED, new_votes
```

**Dispatch convention glue must follow** (mirror `cogs/music.py::_on_track_end` dispatching on `TrackEndAction`, lines 868-886): the new shared skip helper computes `voter_id`/`is_requester`/`listener_ids` (fresh `[m for m in vc.channel.members if not m.bot]` per Pitfall 4 — never memoized), calls `decide_skip`, and does an `if/elif` on the returned `SkipVerdict` — never re-implementing the majority math in the cog.

---

### `tests/test_radio_logic.py` / `tests/test_skip_vote_logic.py` (NEW)

**Analog:** `tests/test_playback_logic.py` (mock-free, pure, class-per-function convention) — this is the file `logic/playback.py`'s docstring names as its lock. Also mirror the boundary-testing style visible in `logic/vision.py`'s docstring (exactly-at-threshold fails, one-under passes) when writing chance/threshold tests.

**Structure to copy** (pattern, no chance/random involved in skip_vote so this is pure input/output):
```python
import pytest
from logic.skip_vote import SkipVerdict, decide_skip


class TestStrictMajorityArithmetic:
    """D-09c: n // 2 + 1 at n=1,2,3,4 (SC-3/SC-4 lock)."""

    def test_two_listeners_needs_two(self):
        verdict, votes = decide_skip(
            voter_id=1, is_requester=False,
            listener_ids=frozenset({1, 2}), existing_votes=frozenset(),
        )
        assert verdict == SkipVerdict.VOTE_RECORDED
        # second vote reaches majority
        verdict2, votes2 = decide_skip(
            voter_id=2, is_requester=False,
            listener_ids=frozenset({1, 2}), existing_votes=votes,
        )
        assert verdict2 == SkipVerdict.SKIP_NOW

    def test_solo_listener_skips_instantly(self):
        verdict, _ = decide_skip(
            voter_id=1, is_requester=False,
            listener_ids=frozenset({1}), existing_votes=frozenset(),
        )
        assert verdict == SkipVerdict.SKIP_NOW
```

---

### `tests/test_music_wiring.py` (NEW or extend an existing wiring file)

**Analog:** `tests/test_autoqueue_wiring.py` — the EXACT source-scan pattern to clone (already read in full).

**Pattern to copy verbatim in shape** (from `tests/test_autoqueue_wiring.py:1-137`):
```python
"""Source-assertion regression tests for Phase 26 skip-vote choke-point unification
(DJ-02 / D-15) — closes the Pitfall 1 gap: /skip's slash body must route through
the SAME shared vote-gated helper as NowPlayingView.skip_button.

Uses inspect.getsource to assert wiring exists, without a live Discord path.
"""

from __future__ import annotations

import inspect

import cogs.music as music_module
from cogs.music import MusicCog, NowPlayingView


def _skip_command_source() -> str:
    return inspect.getsource(MusicCog.skip)  # or the renamed unified command


def _skip_button_source() -> str:
    return inspect.getsource(NowPlayingView.skip_button)


class TestSkipChokePointUnification:
    def test_slash_skip_calls_shared_vote_gate(self):
        """The /skip slash body must call the SAME shared helper the button
        calls — not its own duplicated inline body (Pitfall 1)."""
        src = _skip_command_source()
        assert "_try_skip(" in src  # or whatever name the planner picks

    def test_button_calls_shared_vote_gate(self):
        src = _skip_button_source()
        assert "_try_skip(" in src

    def test_decide_skip_dispatched_not_reimplemented(self):
        """Glue must dispatch on SkipVerdict, never re-implement the
        majority-arithmetic branch (Phase 10 D-02 rule)."""
        src = inspect.getsource(music_module)
        assert "decide_skip(" in src
        assert "// 2 + 1" not in src  # the arithmetic lives ONLY in logic/skip_vote.py
```

Also extend `tests/test_autoqueue_wiring.py`-style regression: assert `try_auto_queue`'s source is byte-identical-when-radio-disarmed by asserting the existing single-occurrence `"for m in vc.channel.members if not m.bot"` count stays `== 1` even after the radio branch is added (the exact assertion at line 61-69 of the existing file — re-run it, don't duplicate the enumeration).

---

### `cogs/music.py` (MODIFIED — the phase's main scar risk)

**Current state, BOTH skip bodies side by side (verified by direct read, confirms RESEARCH Pitfall 1):**

`NowPlayingView.skip_button` (`:376-393`) — calls the shared helper:
```python
@discord.ui.button(label="⏭ Skip", style=discord.ButtonStyle.secondary, custom_id="dex:np:skip")
async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
    cog, queue, vc = self._resolve_cog_queue_vc(interaction)
    if cog is None or queue is None:
        await interaction.response.send_message(embed=embeds.error("bot isn't ready yet."), ephemeral=True)
        return
    if not await self._guard_in_voice(interaction, vc):
        return
    if not queue.is_playing and not queue.is_paused:
        await interaction.response.send_message(embed=embeds.error(pick_random_r(NOTHING_PLAYING)), ephemeral=True)
        return
    await interaction.response.defer()
    next_track = await cog._do_skip(interaction.guild, queue, vc)
    if next_track:
        await interaction.followup.send(f"skipped. now playing **{next_track.title}**.", ephemeral=True)
    else:
        ...
```

`MusicCog.skip` slash command (`:1661-1695`) — **does NOT call `_do_skip`, fully duplicated inline body**:
```python
@app_commands.command(name="skip", description="Skip to the next song")
@app_commands.checks.cooldown(1, config.SKIP_COOLDOWN_SECONDS)
async def skip(self, interaction: discord.Interaction) -> None:
    queue = self.get_queue(interaction.guild.id)
    voice_client = interaction.guild.voice_client
    if not voice_client or not queue.is_playing:
        return await interaction.response.send_message(embed=embeds.error("Nothing is playing."), ephemeral=True)
    current = queue.get_current()
    if current and current.was_auto_queued:
        from models.server_state import get_server_state
        await mark_song_skipped(self.bot.pool, guild_id=str(interaction.guild.id), url=current.url)
        if hasattr(self.bot, "server_states"):
            state = get_server_state(self.bot.server_states, interaction.guild.id)
            state.auto_queue_results["skipped"] += 1
    next_track = queue.skip()
    await self._persist_queue(interaction.guild, queue)
    if next_track:
        await interaction.response.send_message(f"Skipped to **{next_track.title}**")
        make_task(self._play_track(interaction.guild, next_track), name="play-after-skip", bot=self.bot)
        await self._refresh_now_playing(interaction.guild, queue)
    else:
        queue.is_playing = False
        voice_client.stop()
        await interaction.response.send_message("End of queue.")
```

`_do_skip` — the SHARED CONTROL HELPER comment block precedent (`:1002-1033`, Phase 7):
```python
# ──────────────────────────── SHARED CONTROL HELPERS ────────────────────────────
# These are called by both slash commands AND NowPlayingView button callbacks
# so that logic lives in one place (Task 1 — plan 07-02).

async def _do_skip(
    self, guild: discord.Guild, queue: MusicQueue, voice_client: discord.VoiceClient
) -> Track | None:
    """Skip to the next track. Returns the new track, or None if queue exhausted."""
    current = queue.get_current()
    if current and current.was_auto_queued:
        from models.server_state import get_server_state
        await mark_song_skipped(self.pool, guild_id=str(guild.id), url=current.url)
        if hasattr(self.bot, "server_states"):
            state = get_server_state(self.bot.server_states, guild.id)
            state.auto_queue_results["skipped"] += 1
    next_track = queue.skip()
    await self._persist_queue(guild, queue)
    if next_track:
        make_task(self._play_track(guild, next_track), name="play-after-skip", bot=self.bot)
        await self._refresh_now_playing(guild, queue)
    else:
        queue.is_playing = False
        voice_client.stop()
    return next_track
```

**What D-15 requires (planner action, not just pattern-copy):** create a new shared async helper (e.g. `_try_skip(guild, queue, voice_client, *, voter, is_requester)`) that BOTH the `/skip` command body (`:1663`) and `NowPlayingView.skip_button` (`:389`) call. It must:
1. Gather `listener_ids` fresh via `[m for m in vc.channel.members if not m.bot]` (the `bot.py:951`/`cogs/ai.py:335` idiom).
2. Call `logic.skip_vote.decide_skip(...)`.
3. Dispatch on `SkipVerdict`: `SKIP_NOW` → fall through to the existing `_do_skip` mechanics (queue.skip(), mark_song_skipped, _persist_queue, make_task play-after-skip, _refresh_now_playing) exactly as today; `VOTE_RECORDED`/`ALREADY_VOTED` → post the D-18 templated tally line instead, no skip mechanics.
4. `/skip`'s inline body must be DELETED and replaced with a call into this shared helper — this is the concrete Pitfall 1 fix.

**`_on_track_end` — the D-10 lookahead trigger insertion point** (`:842-886`, already fully read):
```python
async def _on_track_end(self, guild: discord.Guild) -> None:
    queue = self.get_queue(guild.id)
    if not queue.is_playing:
        return
    current = queue.get_current()
    if current and current.was_auto_queued and hasattr(self.bot, "server_states"):
        from models.server_state import get_server_state
        state = get_server_state(self.bot.server_states, guild.id)
        state.auto_queue_results["played"] += 1
    next_track = queue.advance()
    await self._persist_queue(guild, queue)
    voice_client = guild.voice_client
    connected = bool(voice_client and voice_client.channel)
    humans_present = any(not m.bot for m in voice_client.channel.members) if connected else False
    ai_cog = self.bot.cogs.get("AICog")
    aicog_loaded = ai_cog is not None
    action = decide_on_track_end(
        is_playing=True, has_next=next_track is not None,
        connected=connected, humans_present=humans_present, aicog_loaded=aicog_loaded,
    )
    if action == TrackEndAction.NOOP:
        return
    elif action == TrackEndAction.PLAY:
        await self._play_track(guild, next_track)
        await self._refresh_now_playing(guild, queue)
    elif action == TrackEndAction.AUTOQUEUE:
        ...
```
D-10's `should_refill_radio(...)` check should be inserted here (e.g. right after `await self._persist_queue`, using `len(queue.upcoming())` as `upcoming_count`), dispatching a radio refill call via `make_task` similarly to how AUTOQUEUE already dispatches — do NOT fold it into `decide_on_track_end`'s existing enum (that enum is locked/tested by `tests/test_playback_logic.py`); treat the radio refill check as an independent, additional gate consulted alongside the existing dispatch, not a new `TrackEndAction` member (keeps `logic/playback.py` byte-identical per the additive-only discipline).

---

### `cogs/ai.py::try_auto_queue` (MODIFIED)

**Analog:** itself — full source already read (`:273-513`+). Key excerpt already captured above (round-cap check `:283`, voice-member enumeration `:334-335`, prompt build `:359-363`, chat call `:364-372`, hallucination+hard-filter loop `:389-454`, `should_start_playback` gate `:473-485`, ignored-signal announce+memory write `:487-513`).

**D-05 suppression pattern (planner action):** wrap the `:487-513` announce+memory-write block behind an `if not radio_armed:` guard (or equivalent), reusing the exact same optional-param/byte-identical-when-unset discipline as `personality/prompts.py`'s `recently_skipped`/`positive_taste` kwargs — i.e. `try_auto_queue` gains a `radio_armed: bool = False`-style signal (read from `queue`/`server_state`, planner's discretion per CONTEXT.md) that changes NOTHING when False.

**D-02 seed anchor insertion point:** the `build_recommendation_prompt(...)` call at `:359-363` gains a third optional kwarg `seed=` alongside `recently_skipped=`/`positive_taste=`, following the exact same "add a kwarg, omit the block when None" pattern documented in the Prompt-builder analog below.

**Voice-member enumeration reuse warning (CRITICAL, locked by test):** the `:335` comprehension `[m for m in vc.channel.members if not m.bot]` must appear EXACTLY ONCE in `try_auto_queue`'s source — `tests/test_autoqueue_wiring.py::test_voice_member_enumeration_is_a_single_reused_comprehension` already asserts this with a literal `src.count(...) == 1` check. Any radio-branch code inside `try_auto_queue` MUST reuse `voice_members` (the existing local), never recompute a second list comprehension of the same shape, or this existing test breaks.

---

### `personality/prompts.py::build_recommendation_prompt` (MODIFIED — the D-02 seed anchor)

**Analog:** itself — the existing optional-param pattern (verified via CONTEXT.md canonical refs + `cogs/ai.py` call site at `:359-363`; not independently re-read in full since the call-site + CONTEXT.md excerpt already gives the exact shape):
```python
def build_recommendation_prompt(
    recent_songs: list[dict],
    *,
    recently_skipped: list[dict] | None = None,
    positive_taste: list[str] | None = None,
    # NEW: seed: str | None = None,
) -> str:
    ...
    skip_block = ""
    if recently_skipped:
        skip_block = "\n\nAVOID these...\n" + ...
    taste_block = ""
    if positive_taste:
        taste_block = "\n\nTHE ROOM TENDS TO LIKE:\n" + ...
    # NEW: seed_block = "" ; if seed: seed_block = "\n\nSTART FROM THIS SEED:\n" + seed
    return MUSIC_RECOMMENDATION_PROMPT.format(...) + skip_block + taste_block  # + seed_block
```
Add the seed anchor as a third optional kwarg following this exact shape — omitted from the prompt when `None`, keeping the auto-queue (non-radio) path byte-identical.

---

### `models/queue.py::MusicQueue` (MODIFIED — likely home for radio armed-state / session played-set / vote state)

**Analog:** itself — `auto_lyrics` (`:78-80`) is the explicit precedent CONTEXT.md names for in-memory per-guild state that survives `clear()`:
```python
# Auto-lyrics: per-guild, in-memory. Deliberately NOT reset by clear() —
# it's a server preference, not playback state. Resets only on restart.
self.auto_lyrics: bool = False
```
Contrast with `clear()` (`:213-233`), which DOES reset `loop_mode` to `OFF` and advances `_play_generation` monotonically — never rewinds. If radio armed-state lives on `MusicQueue`, `/radio start`/`/radio stop`/`/stop`/idle-leave must all explicitly touch it (per D-07/D-08's "explicit disarm at teardown" spirit) — do NOT rely on `clear()` to silently disarm it unless that's an explicit, documented decision, since `clear()`'s current reset list does not include `auto_lyrics`-style fields by default.

**Skip-vote per-track state (new field, e.g. `self._skip_votes: set[int] = set()`) reset points:** must be cleared on `_advance()` (both `skip()` and `advance()` call this internal method at `:121-137`) — the natural single choke point for "track changed" (D-17), mirroring how `_play_generation` increments happen at the same natural boundaries.

**`upcoming()` (`:235-237`)** — the exact D-10 lookahead read:
```python
def upcoming(self) -> list[Track]:
    """Return tracks after the current one."""
    return self.tracks[self.current_index + 1 :]
```
`len(queue.upcoming())` at `_on_track_end`, post-`advance()`, is the lookahead-depth comparison input.

**`Track.requested_by`** (`:33`) — already on the dataclass, no change needed; this is the D-13a bypass key (`voter_id == track.requested_by`).

---

### `models/server_state.py::ServerState` (MODIFIED — alternative home for radio state)

**Analog:** itself:
```python
@dataclass
class ServerState:
    guild_id: int
    auto_queue_rounds: int = 0
    auto_queue_results: dict = field(default_factory=lambda: {"played": 0, "skipped": 0})

    def reset_auto_queue(self) -> None:
        self.auto_queue_rounds = 0
        self.auto_queue_results = {"played": 0, "skipped": 0}
```
If radio armed-state lives here instead of `MusicQueue`, follow this exact `@dataclass` + explicit-reset-method shape (e.g. a `radio_armed: bool = False`, `radio_seed: str | None = None`, `radio_played_set: set = field(default_factory=set)`, with a `disarm_radio()` method mirroring `reset_auto_queue()`'s explicit-method convention rather than folding into `reset_auto_queue()` itself — Pitfall 2 explicitly recommends radio NOT touch `auto_queue_rounds`/`auto_queue_results` at all).

---

### `cogs/library.py` (READ-ONLY analog for `/radio start|stop` group shape)

**Analog:** `playlist = app_commands.Group(...)` (`:417-420`) — the exact subcommand-group declaration + individual `@playlist.command(...)` pattern:
```python
playlist = app_commands.Group(
    name="playlist",
    description="Save and load named playlists",
)

@playlist.command(name="save", description="Save the current queue as a named playlist")
@app_commands.describe(name="Name for the playlist (max 60 chars)")
async def playlist_save(self, interaction: discord.Interaction, name: str) -> None:
    ...
```
`/radio start [seed]` + `/radio stop` should follow this exact shape:
```python
radio = app_commands.Group(name="radio", description="...")

@radio.command(name="start", description="Start endless radio mode, optionally seeded")
@app_commands.describe(seed="Optional artist or song to start from")
async def radio_start(self, interaction: discord.Interaction, seed: str | None = None) -> None:
    ...

@radio.command(name="stop", description="Stop radio mode")
async def radio_stop(self, interaction: discord.Interaction) -> None:
    ...
```
Note `library.py`'s group lives on `LibraryCog` (`:242`) as a class attribute — if `/radio` is added to `MusicCog` (likely, given it shares queue/voice state), follow the same class-attribute-group pattern there instead of a new cog, unless the planner decides a dedicated `cogs/radio.py` is cleaner (RESEARCH's structure sketch shows it folded into `cogs/music.py`).

---

### `personality/responses.py` (MODIFIED — D-18 tally pool + radio lifecycle copy)

**Analog:** `SKIPS_RATE_ROASTS` (`:178-183`, positional `{pct}` interpolation) and `AUTO_QUEUE_ANNOUNCE`/`AUTO_QUEUE_CAP_REACHED`/`AUTO_QUEUE_IGNORED` (`:21-38`, zero-arg lifecycle pools):
```python
SKIPS_RATE_ROASTS: list[str] = [
    "you skip {pct}% of what you queue. bold of you to keep going.",
    ...
]
```
```python
AUTO_QUEUE_ANNOUNCE: list[str] = [
    "fine. since nobody else is stepping up, here's what i picked.",
    ...
]
```
`pick_random()` (`:9-11`) is the sole selector — `random.choice(pool)`. New pools follow this exact shape:
```python
SKIP_VOTE_TALLY: list[str] = [
    "{votes} of {required}. one more and this track's gone.",
    "{votes}/{required} votes to skip. make your case or make your move.",
]

RADIO_START: list[str] = [
    "radio mode. i'm picking now, forever, until you tell me to stop.",
    ...
]

RADIO_STOP: list[str] = [
    "radio's off. back to you people picking songs. good luck.",
    ...
]

RADIO_LOOP_CONFLICT: list[str] = [
    "radio and loop don't mix. picking one for you.",
    ...
]
```
Called via `pick_random(SKIP_VOTE_TALLY).format(votes=n, required=required)` at the cog layer — mirrors `SKIPS_RATE_ROASTS`'s `.format(pct=pct)` call-site convention exactly (not independently re-read at the call site, but the format-kwarg shape is unambiguous from the `{pct}` placeholder and CONTEXT.md D-18's explicit statement that this mirrors `_build_roast_line`'s `fallback_kwargs` handling).

---

### `config.py` (MODIFIED — additive global knobs only, D-21)

**Analog:** the existing `AUTO_QUEUE_*` knob block (`:53-54`, `:145`, `:234-236`) — the exact naming/comment convention new knobs should follow:
```python
AUTO_QUEUE_MAX_ROUNDS = 3
AUTO_QUEUE_SONGS_PER_ROUND = 3
...
AUTO_QUEUE_SEARCH_CANDIDATES = 3  # YouTube candidates per auto-queue suggestion (D-13)
...
AUTO_QUEUE_SKIP_LOOKBACK_DAYS = 7  # D-01: recently-skipped window, days
AUTO_QUEUE_SKIP_HINT_CAP = 15  # D-01: max rows in the negative-hint block
AUTO_QUEUE_POSITIVE_TASTE_CAP = 4  # D-03: max injected taste_episode facts
```
New Phase 26 knobs follow this bare-assignment + trailing `# D-xx: purpose` comment convention:
```python
# Phase 26: radio mode + skip democracy (DJ-01/DJ-02)
RADIO_LOOKAHEAD_DEPTH = 2       # D-10: refill trigger — tracks remaining
RADIO_SONGS_PER_REFILL = config.AUTO_QUEUE_SONGS_PER_ROUND  # or a dedicated knob
RADIO_PLAYED_SET_CAP = 200      # D-03: session played-set bound (planner discretion)
SKIP_VOTE_MAJORITY_RATIO = 0.5  # D-09: strict majority — n // 2 + 1 regardless of ratio value
```
Also unchanged, reused as-is: `SKIP_COOLDOWN_SECONDS = 2` (`:33`, the D-14 anti-spam guard) and `MAX_QUEUE_SIZE_PER_GUILD = 500` (`:94`, the `QueueFullError` cap radio refills must respect).

## Shared Patterns

### Pure `logic/` seam convention (D-19)
**Source:** `logic/proactive.py`, `logic/vision.py`, `logic/playback.py`
**Apply to:** `logic/radio.py`, `logic/skip_vote.py`
- Module docstring stating no Discord/asyncio/database/random/datetime imports.
- Every public function `*`-keyword-only.
- Cheapest-gate-first ordering with early returns.
- Enum verdicts (`SkipVerdict`, mirroring `TrackEndAction`) when glue must dispatch on multiple outcomes; plain bool return when it's a single yes/no gate (`should_refill_radio`, mirroring `should_fire_proactive_callback`/`should_fire_vision_roast`).
- Glue dispatches on the returned value, never mirrors the branch logic back (Phase 10 D-02 rule) — locked by the new `test_music_wiring.py`'s `"// 2 + 1" not in src` style assertion.

### Optional-param, omitted-clause, byte-identical-when-unset
**Source:** `personality/prompts.py::build_recommendation_prompt` (`recently_skipped`/`positive_taste`), `logic/proactive.py`'s deferred-to-glue async step
**Apply to:** the D-02 seed anchor kwarg, the D-05 `radio_armed` suppression guard inside `try_auto_queue`

### Voice-member enumeration idiom — ONE definition, reused not recomputed
**Source:** `cogs/ai.py:335`, `bot.py:951`, `cogs/music.py:864` — `[m for m in vc.channel.members if not m.bot]` (or the `any(not m.bot for m in ...)` boolean variant at `:864`)
**Apply to:** `logic/skip_vote.py`'s glue-side `listener_ids` computation (D-09b), radio's positive-taste fan-out (already existing, unchanged)
**Locked by:** `tests/test_autoqueue_wiring.py::test_voice_member_enumeration_is_a_single_reused_comprehension` — any new radio-branch code inside `try_auto_queue` must NOT add a second occurrence of this comprehension shape.

### Shared control helper (Phase 7 precedent)
**Source:** `cogs/music.py::_do_skip` (`:1002-1004` comment block: "These are called by both slash commands AND NowPlayingView button callbacks so that logic lives in one place")
**Apply to:** the new `_try_skip`-style D-15 unification helper — but note the CURRENT `/skip` slash command violates this precedent (Pitfall 1); the phase's job is to actually enforce it for skip, not just cite it.

### Templated response pool + `pick_random`
**Source:** `personality/responses.py` (`AUTO_QUEUE_ANNOUNCE`, `SKIPS_RATE_ROASTS`, `DISCOVER_NO_HISTORY`)
**Apply to:** `SKIP_VOTE_TALLY` (D-18), `RADIO_START`/`RADIO_STOP`/`RADIO_LOOP_CONFLICT` lifecycle copy — never a Gemini call for these (Critical Rule 12).

### `app_commands.Group` subcommand pattern
**Source:** `cogs/library.py::playlist`/`jam` groups
**Apply to:** `/radio start|stop` (D-06b)

## No Analog Found

None — every file in the known scope has a direct, verified in-repo analog. This phase is explicitly a composition-of-existing-primitives phase (confirmed by RESEARCH.md's "Don't Hand-Roll" table); nothing requires an external pattern.

## Metadata

**Analog search scope:** `logic/`, `cogs/music.py`, `cogs/ai.py`, `cogs/library.py`, `models/queue.py`, `models/server_state.py`, `personality/prompts.py`, `personality/responses.py`, `config.py`, `bot.py`, `tests/test_autoqueue_wiring.py`, `tests/test_playback_logic.py` (referenced)
**Files scanned:** 12 read directly (full or targeted), 2 referenced via CONTEXT.md/RESEARCH.md excerpts (`personality/prompts.py` call-site only, `tests/test_proactive_logic.py`/`tests/test_playback_logic.py` referenced by name/docstring)
**Pattern extraction date:** 2026-07-16
