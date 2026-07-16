---
phase: 26-radio-mode-skip-democracy
reviewed: 2026-07-17T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - config.py
  - cogs/ai.py
  - cogs/music.py
  - logic/radio.py
  - logic/skip_vote.py
  - models/queue.py
  - personality/prompts.py
  - personality/responses.py
  - tests/test_autoqueue_wiring.py
  - tests/test_hosting_drift_guard.py
  - tests/test_music_wiring.py
  - tests/test_prompts.py
  - tests/test_radio_logic.py
  - tests/test_responses.py
  - tests/test_skip_vote_logic.py
findings:
  critical: 1
  warning: 4
  info: 1
  total: 6
status: issues_found
---

# Phase 26: Code Review Report

**Reviewed:** 2026-07-17T00:00:00Z
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

The pure decision seams (`logic/radio.py`, `logic/skip_vote.py`) and the `models/queue.py`
per-track vote/radio state are well-designed, exhaustively unit-tested, and match their own
documented invariants (D-09c majority table, D-17 departed-voter counting, D-11 loop/radio
mutual exclusion, D-07/SC-2 disarm-on-teardown). No bugs were found in those pure modules.

The defect is at the Discord glue layer in `cogs/music.py`: the vote-gated skip choke point
(`_try_skip`) is correctly unified across all three documented entry points (`/skip`, the
`NowPlayingView` skip button, `/seek` past-end — D-15), but two of those three entry points
never verify the caller is actually a listener in the bot's voice channel before their vote is
counted. Only the button enforces that via `_guard_in_voice`. This is the review's one
BLOCKER — it undermines the core premise of DJ-02 ("skip democracy" requires the vote to come
from the room). A second cluster of WARNING-level issues concerns state leakage between radio
and non-radio auto-queue sessions, and a narrow concurrency window that can double-skip an
auto-queued track.

## Critical Issues

### CR-01: `/skip` and `/seek` past-end never verify the voter is in the bot's voice channel — any guild member can inflate the skip-vote tally

**File:** `cogs/music.py:1787-1811` (`/skip`), `cogs/music.py:2075-2093` (`/seek` past-end)

**Issue:** The whole point of DJ-02 is that a skip requires a strict majority of the people
*currently listening* (`config.SKIP_VOTE_MAJORITY_RATIO`, D-09/D-09b — "listeners = every
non-bot member in the voice channel"). `NowPlayingView.skip_button` correctly enforces this: it
calls `self._guard_in_voice(interaction, vc)` before ever reaching `_try_skip` (`cogs/music.py:389`),
which rejects the interaction if the presser isn't in the bot's own voice channel.

The `/skip` slash command has no equivalent check:

```python
async def skip(self, interaction: discord.Interaction) -> None:
    queue = self.get_queue(interaction.guild.id)
    voice_client = interaction.guild.voice_client

    if not voice_client or not queue.is_playing:
        return await interaction.response.send_message(embed=embeds.error("Nothing is playing."), ephemeral=True)

    await interaction.response.defer()
    verdict, next_track, votes, required = await self._try_skip(
        interaction.guild, queue, voice_client, voter_id=interaction.user.id
    )
```

Nor does the `/seek` past-end path, which routes through the exact same `_try_skip` gate
(`cogs/music.py:2079-2081`).

`_try_skip` itself (`cogs/music.py:1075-1078`) computes `listener_ids` fresh from
`voice_client.channel.members`, but this is used ONLY as the denominator passed to
`required_votes` — `decide_skip`'s tally (`logic/skip_vote.py` gate 4) counts `len(new_votes)`
with **no membership check against `listener_ids`** (that's D-17's *intentional* design — a
departed voter's vote must stay counted). The consequence: `decide_skip` trusts the caller to
only ever pass a `voter_id` that belongs to (or once belonged to) the room. `/skip` and `/seek`
break that contract — they pass `interaction.user.id` for literally any guild member with slash
command access, including someone who has never once joined the voice channel.

Concretely, in a 4-listener room requiring 3 votes (D-09c), a single real listener plus two
guild members who are not in voice at all (e.g. alt accounts, or just other server members
running `/skip` from a text channel) reach the threshold and force a skip that only 1 of the 4
actual listeners agreed to. This is a direct defeat of "skip democracy" — the STRIDE register
for T-26-05 (`26-04-PLAN.md`) only considers admin/owner elevation-of-privilege and explicitly
proves the button-vs-`/skip` choke-point unification is closed, but never considers a
non-listener casting a vote at all, so this gap slipped past the phase's own threat model.

**Fix:** Add the same `in the bot's voice channel` guard used by the button (and already used by
`/filter`) to both `/skip` and `/seek`'s past-end branch, before calling `_try_skip`:

```python
@app_commands.command(name="skip", description="Skip to the next song")
@app_commands.checks.cooldown(1, config.SKIP_COOLDOWN_SECONDS)
async def skip(self, interaction: discord.Interaction) -> None:
    queue = self.get_queue(interaction.guild.id)
    voice_client = interaction.guild.voice_client

    if not voice_client or not queue.is_playing:
        return await interaction.response.send_message(embed=embeds.error("Nothing is playing."), ephemeral=True)

    if not interaction.user.voice or interaction.user.voice.channel != voice_client.channel:
        return await interaction.response.send_message(
            embed=embeds.error(pick_random_r(NOT_IN_VOICE)), ephemeral=True
        )

    await interaction.response.defer()
    ...
```

Apply the identical check to `/seek`'s past-end branch before it calls `_try_skip`. This also
closes the gap for `/radio start` (see IN-01 below) if the same helper is reused.

## Warnings

### WR-01: Radio-era auto-queue play/skip counters are only reset by `/radio stop` — a mid-radio `/loop` disarm (D-11) leaks stale counts into the next non-radio auto-queue round

**File:** `cogs/music.py:2375-2400` (`radio_stop`), `cogs/music.py:1880-1901` (`/loop`),
`cogs/music.py:1166-1179` (`_do_loop_cycle`), `models/queue.py:312-331` (`set_loop_mode`)

**Issue:** `cogs/ai.py`'s `try_auto_queue` suppresses the "ignored signal" announce/memory-write
while radio is armed (D-05), but the underlying counters it reads (`server_state.auto_queue_results`)
are still mutated unconditionally on every track: `cogs/music.py:872` (`_on_track_end` increments
`"played"` for any `was_auto_queued` track, radio or not) and `cogs/music.py:1134` (`_do_skip`
increments `"skipped"` the same way). Radio-queued tracks always carry `was_auto_queued=True`, so
an hour-long radio session accumulates real play/skip counts in `server_state.auto_queue_results`.

`radio_stop` is aware of this and explicitly resets the counters as a "lifecycle boundary" fix
(comment at `cogs/music.py:2390-2394`):

```python
# Radio-era play/skip counts must not leak into the first post-radio
# auto-queue's ignored-signal calculation (D-05's spirit at the
# lifecycle boundary) ...
if hasattr(self.bot, "server_states"):
    state = get_server_state(self.bot.server_states, interaction.guild.id)
    state.reset_auto_queue()
```

But radio can also be disarmed **without** going through `/radio stop`: `/loop` (or the
now-playing loop button, `_do_loop_cycle`) disarms radio via the D-11 mutual-exclusion choke
point in `models/queue.py::set_loop_mode`, and neither `MusicCog.loop` nor `_do_loop_cycle` calls
`reset_auto_queue()`. Since setting loop to `SINGLE`/`QUEUE` also means the queue no longer
naturally exhausts, the radio-era counters sit untouched until the user later turns loop back
`off` and the queue eventually exhausts into `TrackEndAction.AUTOQUEUE` with `radio=False` (radio
was already disarmed) — at which point `try_auto_queue`'s ignored-signal check
(`prev["skipped"] > 0 and prev["played"] + prev["skipped"] > 0`, `cogs/ai.py:580-583`) reads the
stale radio-era counts and can fire a bogus "you skipped all my picks last time" message
(`AUTO_QUEUE_IGNORED`) for a genuinely fresh, non-radio auto-queue round nobody has rejected yet.

**Fix:** Call `state.reset_auto_queue()` at every radio-disarm site that doesn't already clear the
whole queue, not just the explicit `/radio stop` command — e.g. thread it through
`MusicQueue.set_loop_mode`'s D-11 disarm branch's caller (`MusicCog.loop` and `_do_loop_cycle`),
mirroring the reset already present in `radio_start`/`radio_stop`:

```python
radio_disarmed = queue.set_loop_mode(LoopMode(mode.value))
if radio_disarmed and hasattr(self.bot, "server_states"):
    from models.server_state import get_server_state
    get_server_state(self.bot.server_states, interaction.guild.id).reset_auto_queue()
```

### WR-02: Narrow race window can double-skip an auto-queued/radio track under concurrent votes

**File:** `cogs/music.py:1122-1149` (`_do_skip`), `cogs/music.py:1043-1120` (`_try_skip`)

**Issue:** `_try_skip`'s vote decision (`decide_skip`) and write-back (`record_skip_votes`) are
synchronous — no `await` between reading the current track and writing the new vote set, so two
concurrent `_try_skip` calls for the same guild can't interleave *there*. But once a verdict is
`SKIP_NOW`, `_try_skip` does `await self._do_skip(...)`, and `_do_skip` only advances the queue
(`next_track = queue.skip()`) *after* an `await` when the current track is auto-queued:

```python
async def _do_skip(self, guild, queue, voice_client) -> Track | None:
    current = queue.get_current()
    if current and current.was_auto_queued:
        ...
        await mark_song_skipped(self.pool, guild_id=str(guild.id), url=current.url)  # <- yields here
        ...
    next_track = queue.skip()   # <- current_index NOT yet advanced during the await above
```

If a second vote-triggering interaction (a different voter, or the same track reaching threshold
via two near-simultaneous `/skip`/button presses) is scheduled by the event loop while the first
`_do_skip` call is suspended at `await mark_song_skipped(...)`, that second task's `_try_skip`
still sees the *same, not-yet-advanced* current track (`queue.get_current()` unchanged) and the
*same* vote key, so it can independently reach `SKIP_NOW` again — since the tally comparison
`len(new_votes) >= needed` stays true for every additional voter once the threshold is already
met, not just the one who crossed it. That second call runs `_do_skip` a second time, double-writing
`mark_song_skipped` and calling `queue.skip()` twice, silently skipping one extra track for what
the room intended as a single skip. Every radio-queued track hits this window (`was_auto_queued`
is always `True` for radio), so this is more reachable in the exact feature this phase ships than
in the pre-existing manual-skip path (where a non-auto-queued current track has no `await` before
`queue.skip()` and is not vulnerable to this specific interleaving).

**Fix:** Move `next_track = queue.skip()` (and ideally the whole "am I already mid-skip"
transition) before the `await mark_song_skipped(...)` call, or guard `_do_skip` with a per-guild
in-flight flag on `MusicQueue` that a second concurrent `SKIP_NOW` checks before re-entering.

### WR-03: `/skip` blocks skipping (and voting) while paused; the NowPlayingView button does not — the three D-15 entry points are not behaviorally equivalent

**File:** `cogs/music.py:1793` (`/skip` guard) vs `cogs/music.py:391` (button guard)

**Issue:** `/skip`'s guard is `if not voice_client or not queue.is_playing:` — while paused,
`queue.is_playing` is `False` (`_do_pause_toggle` sets it), so `/skip` reports "Nothing is
playing." and never reaches `_try_skip` at all. The button's guard is
`if not queue.is_playing and not queue.is_paused:` — it correctly allows skipping/voting while
paused. D-15's whole premise is that all skip entry points route through one gate with identical
behavior; today a paused track is only skippable/votable via the button, not `/skip` or `/seek`.
This guard predates Phase 26, but Phase 26 is the first time it actually blocks a *vote* (not
just an instant skip), so a paused track's vote can silently only ever be cast through one of the
three documented entry points.

**Fix:** Align `/skip`'s (and `/seek`'s) guard with the button's: `if not voice_client or (not queue.is_playing and not queue.is_paused):`.

### WR-04: `/radio start`'s free-text `seed` has no length cap before being echoed into a public reply and repeated in every subsequent Gemini prompt

**File:** `cogs/music.py:2309-2357` (`radio_start`), `personality/prompts.py:245-247` (seed block)

**Issue:** Every other user-supplied free-text field with unbounded reuse in this codebase has an
explicit cap (`PLAYLIST_NAME_MAX_LENGTH = 60`, `FAVORITES_MAX_PER_USER`, etc.). `seed` has none:

```python
@app_commands.describe(seed="An artist or song to start from (optional)")
async def radio_start(self, interaction: discord.Interaction, seed: str | None = None) -> None:
    ...
    seed_stripped = seed.strip() if seed else None
    ...
    message = pick_random_r(RADIO_START).format(seed=effective_seed or "whatever you've been playing")
    ...
    await interaction.response.send_message(message)
```

A long `seed` (Discord's default STRING option max is 6000 characters) embedded verbatim into
`message` can push the rendered reply past Discord's 2000-character message-content limit,
raising an uncaught `discord.HTTPException` from `interaction.response.send_message` — the
command errors out instead of degrading gracefully. The same unbounded `seed` is also re-embedded
into `build_recommendation_prompt`'s `START FROM THIS AND DRIFT NATURALLY` block on every single
radio refill for the life of the session (`cogs/ai.py:328`), needlessly inflating every Gemini
call.

**Fix:** Truncate `seed` to a small cap (e.g. a new `RADIO_SEED_MAX_LENGTH` config knob, or reuse
`PLAYLIST_NAME_MAX_LENGTH`) before storing it via `arm_radio`, mirroring the existing
`PLAYLIST_NAME_MAX_LENGTH` precedent.

## Info

### IN-01: `/radio start` does not require the invoking user to be in the bot's voice channel

**File:** `cogs/music.py:2309-2326`

**Issue:** `radio_start` only checks `voice_client is None` — any guild member (not necessarily
in voice, or in a different voice channel than the bot) can arm radio mode for whatever channel
the bot happens to be in. `/play` and `/filter` both gate on the invoking user's voice presence;
`/radio start` does not. This is lower severity than CR-01 (it's not a vote-rigging hole — radio
is a single action, not a tallied vote), but it's an inconsistency with the rest of the command
surface's permission model.

**Fix:** Add the same `interaction.user.voice.channel == voice_client.channel` check used
elsewhere, or explicitly document why `/radio start` is intentionally open to any guild member.

---

_Reviewed: 2026-07-17T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
