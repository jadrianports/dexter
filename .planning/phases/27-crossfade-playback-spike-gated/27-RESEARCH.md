# Phase 27: Crossfade Playback — Plan-Time Spike (D-15)

**Ran:** 2026-07-17
**Branch:** `spike/crossfade` (off `main`) — prototyped, evidenced, **deleted** (D-06/D-16)
**Requirement:** DJ-03
**Owner of the call:** the user (D-04). This document **proposes**.

---

## VERDICT: GO

**(a narrow GO — D-03. Round 2 removed the caveat's teeth: see [Round 2](#round-2-the-100ms-boundary).)**

> **Round 2 amendment (2026-07-17).** The coordinator challenged the one claim below that
> qualified this verdict — that removing the 100ms boundary silence "requires a session-long mixer
> = D-01 NO-GO". **They were right and I was wrong.** The 100ms **is** real (confirmed, packet by
> packet), but it can be suppressed **additively**, keeping per-track `play()`, one source per
> `play()`, and the generation counter fully intact. **It does not trip D-01.** Two renders now
> exist — with and without — differing by *nothing but* that 100ms. The verdict is **GO either
> way**; what remains for the user is a *choice between two GO variants*, not a no-go. The
> strikethrough text below is preserved as written so the error is on the record.

Crossfade fits the existing engine **additively**, with no change to the per-track
`voice_client.play()` + generation-counter model, and therefore does **not** trip D-01's no-go
condition. The winning shape puts the entire fade *inside the incoming track's own
`discord.AudioSource`*, so the voice client still only ever sees **one source and one `play()` per
track** — the two live FFmpeg decoders exist only *inside* that single source object, where one
`cleanup()` owns both. All three D-07 attacks were run against the real `MusicQueue` /
`logic/playback.py` / `MusicCog._play_track` / `_try_skip` → `_do_skip` path driven by discord.py's
**real `AudioPlayer` thread**, and all three passed with directly observed evidence: **zero orphaned
FFmpeg processes** (measured back to a 0 baseline every time), **no double-play** (the stale
after-callback was observed being suppressed by the generation guard), and **no counter desync**.

**Confidence: HIGH on the engine-safety half** — that half is not an opinion; it is `tasklist`
process counts and printed counter values, reproduced across three attacks.
**Confidence: MEDIUM on the audio-quality half**, for one specific reason stated plainly below.

**The caveat that could flip this to NO-GO — and it is the user's call, not mine (D-10):**
discord.py's `AudioPlayer` emits `send_silence()` — **5 frames = exactly 100ms of silence** — at
*every* source boundary, including a natural source exhaustion. This is not new and not
crossfade's fault: **that same 100ms already sits at every track transition Dexter plays today.**
But because a fade must begin *before* the outgoing track ends, this shape **relocates that 100ms
hole from the track boundary (where a song is changing anyway) into the fade's start (mid-music, at
full volume)**. I measured it at exactly `t=8.00–8.08` in the render and I deliberately captured it
into the file rather than filtering it out. ~~**I cannot hear it. If that dropout is unacceptable to
you, the only way to remove it is a session-long mixer source replacing per-track `play()` — which
D-01 defines as the NO-GO.**~~ ← **WRONG. Refuted in Round 2 — it is removable additively.** So:
the engine says go; the render decides *which variant*.

---

## Evidence

Harness: the **real** `MusicCog` (subclassed; `_play_track` copied verbatim with ~10 marked `+XF`
lines — the generation block, `after_callback` and its guard, the `stop()`/`play()` ordering, both
`source.cleanup()` failure paths and the prefetch dispatch are byte-identical), the **real**
`MusicQueue`, the **real** `logic/playback.py` dispatch, the **real** `AudioService`, the **real**
`_try_skip`/`_do_skip` vote choke point, and **real cached opus files** from `data/cache/`. The only
fake is the UDP socket: a `FakeVoiceClient` that drives discord.py's genuine
`discord.player.AudioPlayer` (its real 20ms cadence, its real
`read()→b''→stop()→_call_after()→source.cleanup()` sequence, its real thread→loop `after_callback`
hop). **The races can therefore actually happen** — these are real threads, real timing and real
FFmpeg subprocesses, so the orphan counts are genuine. `queue_persistence` is stubbed (see
*Landmines* — this makes the reported transition gap an *understatement*, not a flattery).

Fade length used throughout: **4s**, cut at `duration − 4`, `equal_power` curve.
FFmpeg counts are `tasklist /FI "IMAGENAME eq ffmpeg.exe"`.

### Attack 1 — `/skip` landing mid-fade — **PASS**

Queue `[A, B, C]`; A cut at 8s; `/skip` fired ~1.5s into the A→B fade via the real
`_try_skip(voter_id=…)` (1 listener → `SKIP_NOW`).

```
[ATTACK-1 start] ffmpeg_baseline=0 gen=0
Playing 'A' in guild 1
crossfade: mixing tail=vs40MIVf714@8.000s into head=tkbgtVFlyCQ over 4s
Playing 'B' in guild 1
[MID-FADE] ffmpeg=2 gen=2 current_index=1 source=TruncatingSource frames_mixed=-
crossfade: hard cut (no_next_track)
Playing 'C' in guild 1
STALE after_callback suppressed: gen=3 current_gen=2
[AFTER-SKIP] verdict=SKIP_NOW next=C gen=3 current_index=2 ffmpeg=1 playing=True source=FFmpegOpusAudio
[TEARDOWN] ffmpeg=0 baseline=0
```

- **No orphan:** `ffmpeg` 0 → 2 (both fade decoders live) → 1 (both killed, C's spawned) → **0**.
- **No double-play:** `STALE after_callback suppressed: gen=3 current_gen=2` — the fading source's
  callback fired on `stop()`, saw the advanced generation, and bailed. This is the guard working
  *while two decoders were live*.
- **No desync:** `gen` 2→3 and `current_index` 1→2, monotonic, exactly one increment for one skip.
- `source=TruncatingSource` at mid-fade is **correct and load-bearing**: B has a next track (C), so
  B's own fade armed and B's source is `TruncatingSource(CrossfadeSource(tail_A, head_B))`.
  **Chained/consecutive fades nest cleanly** — the fade for the *next* transition arms while the
  *current* fade is still mixing.

### Attack 2 — `/stop` + idle-leave mid-fade — **PASS** (both sites)

Two live decoders at teardown. `/stop` via the real `_do_stop`; idle-leave via a **verbatim mirror
of `bot.py::idle_check`'s teardown template** (`gen += 1` → `vc.stop()` → `disconnect()` →
`clear()` → `clear_persisted()`).

```
[ATTACK-2/stop start] ffmpeg_baseline=0 gen=0
[MID-FADE] ffmpeg=2 gen=2 source=CrossfadeSource frames_mixed=83
STALE after_callback suppressed: gen=4 current_gen=2
[AFTER-stop] ffmpeg=0 baseline=0 gen=4 playing=False connected=False tracks=0

[ATTACK-2/idle-leave start] ffmpeg_baseline=0 gen=0
[MID-FADE] ffmpeg=2 gen=2 source=CrossfadeSource frames_mixed=82
STALE after_callback suppressed: gen=4 current_gen=2
[AFTER-idle-leave] ffmpeg=0 baseline=0 gen=4 playing=False connected=False tracks=0
```

- **The doubled orphan risk did not materialise:** `ffmpeg=2` → **`ffmpeg=0`** at both teardown
  sites. `CrossfadeSource.cleanup()` tears down both children, and the head is cleaned in a
  `finally` so a raising tail cleanup cannot strand it. Critical Rule 3 holds **because the
  two-decoder window is expressible as one `AudioSource`** — the existing teardown template needed
  **no per-site edit**, which is exactly why the DEPLOY-06 scar class does not reopen here.
- `gen` 2→4 (teardown `+1`, then `clear()`'s `+1`) — monotonic, never rewound.

### Attack 3 — prefetch racing the fade — **PASS** (benign; the collision is structurally excluded)

Queue `[A, B(cached), C(NOT cached)]` with a deliberately slow (6s) `async_download`, so a **real
cold prefetch for C is still in flight** while A→B fades.

```
[ATTACK-3 start] ffmpeg_baseline=0 C_cached=False
crossfade: mixing tail=vs40MIVf714@8.000s into head=tkbgtVFlyCQ over 4s
crossfade: hard cut (not_cached)
Playing 'B' in guild 1
[MID-FADE] ffmpeg=2 gen=2 source=CrossfadeSource frames_mixed=81 prefetch_slot=COLDVIDEO01 prefetch_calls=['COLDVIDEO01']
[AFTER-SKIP-DURING-PREFETCH] verdict=SKIP_NOW gen=2 current_index=2 next=C source=CrossfadeSource verdicts=['fade', 'not_cached']
prefetch complete video_id=COLDVIDEO01 elapsed=6.01s ok=False
[AFTER-PREFETCH-LANDS] ffmpeg=1 baseline=0 prefetch_slot=None gen=2
[TEARDOWN] ffmpeg=0 baseline=0
```

- The fade **mixed normally with a cold prefetch in flight** (`frames_mixed=81`,
  `prefetch_slot=COLDVIDEO01`). No interference: prefetch touches only
  `queue._prefetch_video_id`; the fade touches only its own two decoders.
- **The dangerous version of this race is structurally impossible**, which is the real finding:
  the fade *requires* the incoming track to already be cached (`not_cached` → hard cut), and
  `_prefetch_next_track` **early-exits at `if self.audio.is_cached(...)`**. So "the fade reads the
  next track while prefetch is fetching that same track" **cannot happen** — the two are mutually
  exclusive by construction. Observed live: B→C correctly logged `hard cut (not_cached)`.
- `prefetch_slot` correctly released to `None`; **`ffmpeg` back to 0.**

**Honest limitation of this run:** C never actually played (`gen` stayed 2) because the stub
YouTube service can neither download nor stream-fallback C — a harness artifact, not a crossfade
defect. Attack 1 covers skip→play properly. It did surface a real (**pre-existing, not
crossfade-specific**) behaviour: a skip does not stop the outgoing audio until the *next* source is
acquired, so skipping into an uncached track lets the old source keep playing for up to
`DOWNLOAD_TIMEOUT_SECONDS`. With crossfade on, that means the fade audibly continues for a moment
after the skip. This is today's behaviour, unchanged.

### Supporting measurements

| Check | Result |
|---|---|
| `audioop.add` on overflow | **saturates** (`30000+30000 → 32767`), does not wrap — worst case is clipping, never catastrophic distortion |
| Clipping in the real render | **32 samples of 1,647,360 = 0.0019%** — equal-power needs **no headroom gain** |
| `-ss` tail seek alignment | **0ms skew** (best correlation offset against a ground-truth full decode = exactly 0) — the fade seam is time-aligned; the residual is opus decoder state, not a discontinuity |
| Transition gap (`_on_track_end` entry → `play()`) | **0.016s**, of which two FFmpeg spawns = **0.016s** |
| `send_silence()` at the boundary | **5 frames = 100ms**, measured at `t=8.00–8.08` in the render |
| Eligibility ladder through the real engine | all 6 fallbacks fire correctly; source stays `FFmpegOpusAudio` in every non-fading case |

Ladder run (real engine, real sources):

```
  toggle off               -> no_toggle        source=FFmpegOpusAudio
  loop SINGLE              -> loop_single      source=FFmpegOpusAudio
  filter active            -> filter_active    source=FFmpegOpusAudio
  incoming not cached      -> not_cached       source=FFmpegOpusAudio
  last track               -> no_next_track    source=FFmpegOpusAudio
  short track              -> too_short        source=FFmpegOpusAudio
```

`source=FFmpegOpusAudio` in every non-fading row **is** the byte-identical-when-off evidence: with
the toggle off the source object handed to `play()` is the same class, from the same
`get_source()` call, on the same opus fast path as today.

---

## The Render

**Absolute path:**
`C:\Users\James\AppData\Local\Temp\claude\C--Users-James-desktop-projects-dexter\dde3f576-9998-4940-a8cd-d61e2e10b8a4\scratchpad\dexter-crossfade-spike.wav`

| Property | Value |
|---|---|
| Format | WAV, 48kHz, stereo, s16le, 17.16s, ~3.2MB (double-click playable) |
| Material | **REAL music** — two genuinely different cached tracks from `data/cache/` (`vs40MIVf714.opus` → `tkbgtVFlyCQ.opus`). **Not synthetic.** |
| Curve / length | `equal_power` (`cos`/`sin`), **4.0s** — 200 mixed frames, exactly as configured |
| Provenance | Captured from `send_audio_packet()` in the fake voice client — i.e. **the exact PCM discord.py would have handed to the Opus encoder** (D-09's premise, made literal) |
| Structure | `0–8s` outgoing alone → **`8.00–8.10` the 100ms boundary silence** → `8.10–12s` both tracks mixing → `12–17s` incoming alone |

Measured envelope (0.5s RMS windows) — **no mid-fade loudness dip**, which is the constant-power
property working:

```
  7.5  5182 #################  [outgoing alone]
  8.0  5015 ################   <<< 100ms SILENCE then fade begins
  8.5  5241 #################  [both tracks mixing]
  9.5  6677 ######################  [both tracks mixing]
 11.5  5788 ###################  [both tracks mixing]
 12.0  6230 ####################  [incoming alone]
```

**What to listen for** (I cannot hear this file — this is the SC-2 verdict and it is yours, D-10):

1. **At 0:08 — the 100ms dropout.** This is the one thing that matters. Does it read as a glitch,
   or do you not notice it? **This is the whole caveat.** It cannot be removed additively.
2. **0:08–0:12 — the blend itself.** Two songs should overlap and swap over ~4s with no dip in
   loudness and no "underwater"/phasing artifact. Is 4s the right length? (It is one constant —
   D-12b.)
3. **Right at 0:08.1 — a click?** The maths says the tail's `-ss` seek is 0ms-aligned, but a
   sample-level step would be audible where the outgoing is still at full gain.
4. **Whether it's worth it at all** vs. today's hard cut.

**I do not claim it sounds good.** I claim: it mixes for exactly 4.0s, it does not clip
(0.0019%), it does not dip in loudness, the seek is time-aligned, and there is a 100ms hole at
8.00s that I put in the file on purpose so you can judge it.

---

## Findings

*(D-06: the prototype is deleted. This section is the entire handoff — a clean, TDD'd
reimplementation must be driven from here, not from the branch.)*

### 1. The shape that works — "the fade lives inside the incoming track's source"

The key insight, and the reason D-01 is satisfiable:

- The **outgoing** track is wrapped in a `TruncatingSource` that exhausts it `CROSSFADE_SECONDS`
  early. To discord.py this is an **ordinary natural end** → `after_callback` → `_on_track_end`.
  It delegates `is_opus()`, so **the outgoing track keeps the Phase 6/7 opus fast path for its
  entire body** — only the 3–4s tail is ever decoded to PCM.
- The **incoming** track's source is a `CrossfadeSource` that mixes the outgoing track's tail
  (re-decoded from the *cache file* with `-ss <cut>`) against the incoming head, then continues
  with the incoming decoder alone.

Consequences that make this additive:
- **One `play()` per track. One source per `play()`.** The generation counter, `after_callback`,
  the `stop()`/`play()` ordering and prefetch are untouched. Nothing in `logic/playback.py` changes.
- **The two-decoder window is entirely inside one `AudioSource`**, so `cleanup()` is the single
  owner of both. **No teardown site needs editing** — this is why attack 2 passed for free.
- No ownership transfer, no stealing a live process out of a dead player, no session-long mixer.

**Rejected alternative (do not revisit):** keeping the outgoing FFmpeg process alive across the
player boundary and handing it to the next source. It forces the *whole* outgoing track to PCM
(forfeiting opus-copy for every track, not just the tail) **and** breaks the `cleanup()`-owns-its-
children contract, creating exactly the orphan class Critical Rule 3 exists for.

### 2. The 100ms boundary silence — the one honest cost *(amended in Round 2)*

`discord.player.AudioPlayer._do_run` calls `send_silence()` (5 × 20ms pre-encoded silence frames)
whenever the loop exits, **including natural source exhaustion**. Those packets each advance the
VoiceClient's RTP timestamp by 960 samples, so they take real slots in the timeline and **are
heard** (proven packet-by-packet in Round 2). Any shape that starts a fade before a track ends must
cross a player boundary, and every player boundary costs 100ms. Shape B merely moves the same hole
to the fade's *end* — **structurally no better** (Round 2 / Task 4: equal-power guarantees some
track is always ≥ −3dB, so no boundary placement can hide it), and it adds a seek-alignment
dependency on the incoming track.

~~**Eliminating it requires the session-long mixer = D-01 NO-GO.**~~ **WRONG — see Round 2.** It is
removable additively by suppressing `AudioPlayer.send_silence` for the one source that cut short for
a fade, which leaves per-track `play()`, one-source-per-`play()` and the generation counter fully
intact. **Both variants are rendered; the user picks.** If suppression ships, it **must** be
installed defensively (see Round 2's risk table) so a discord.py upgrade degrades to today's
behaviour instead of crashing at import.

### 3. `logic/crossfade.py` — the D-14 pure seam (proposed signature)

Validated shape (all six branches exercised through the real engine). Keyword-only, no Discord
imports, no I/O, no clock, no RNG. Glue **dispatches on the returned member and never re-derives
the ladder** (Phase 10 D-02):

```python
class FadeVerdict(enum.Enum):
    FADE = "fade"
    NO_TOGGLE = "no_toggle"
    NO_NEXT_TRACK = "no_next_track"
    LOOP_SINGLE = "loop_single"       # D-11b
    FILTER_ACTIVE = "filter_active"
    NOT_CACHED = "not_cached"
    TOO_SHORT = "too_short"
    SEEKED = "seeked"

def decide_crossfade(
    *, enabled: bool, has_next: bool, loop_single: bool, filter_active: bool,
    outgoing_cached: bool, incoming_cached: bool, outgoing_duration: int,
    incoming_duration: int, seek_offset: int, fade_seconds: int, min_track_seconds: int,
) -> FadeVerdict: ...

def cut_frame(*, outgoing_duration: int, fade_seconds: int, frame_ms: int = 20) -> int: ...
```

Order matters and **is** the D-10b/D-11b fallback ladder; lock each rung with a mock-free test.
`FadeVerdict` (not a bool) so the D-10b log line can name *why* it hard-cut.

### 4. `services/audio.py` — the mixing half (D-14)

- `TruncatingSource(discord.AudioSource)`: `read()` returns `b""` once `frames_read >= max_frames`;
  **delegates `is_opus()`**; `cleanup()` → inner. Expose `frames_read` / `position_seconds`, and a
  `cut_short` flag distinguishing "cut for a fade" from "file ended early".
- `CrossfadeSource(discord.AudioSource)`: two `FFmpegPCMAudio` children; `is_opus()` → `False`;
  mixes with `audioop.mul` + `audioop.add` (width 2). **`cleanup()` must clean BOTH, with the head
  in a `finally`.** Drop and clean the tail the instant the fade ends — do not hold it for the rest
  of the track.
- `FFmpegPCMAudio` always returns exactly 3840 bytes or `b""`, so `audioop.add`'s equal-length
  requirement is satisfied without padding. Verified.
- Extend `get_source` with an optional `crossfade_from=(prev_track, cut_seconds)` kwarg — **omitted
  = byte-identical to today** (the Phase 14 `kind` / Phase 21 `guild_scoped` discipline).

### 5. Exact integration points in `_play_track`

Only two additions; everything between them stays verbatim:

1. **Immediately after `source = await self.audio.get_source(...)`** (`music.py:673`, *before*
   the `queue._play_generation += 1` at `:702`): consult `decide_crossfade`; on `FADE`, wrap in
   `TruncatingSource(source, cut_frame(...))` and stash the truncator + outgoing `Track` on the
   queue. On anything else, log `crossfade: hard cut (<verdict>)` and pass `source` through
   untouched (D-10b: **log only, the room sees nothing**).
2. **At `get_source` call time**: if a pending fade handoff exists on the queue, build the
   `CrossfadeSource` instead of a plain source, and clear the handoff.

Plus one addition in `_on_track_end`, **before** the existing `decide_on_track_end` dispatch: if the
truncator `cut_short` and `queue.is_playing`, set `queue._xf_pending = (outgoing_track,
truncator.position_seconds)`. Then clear the truncator unconditionally.

**Read the cut position from `frames_read`, never from the planned number.** A file shorter than its
YouTube metadata otherwise produces an `-ss` past EOF. (Handled anyway: an empty tail degrades to a
plain fade-in — `CrossfadeSource` must tolerate `tail == b""` on the first read.)

### 6. Recommended `config.py` knobs (global — Phase 26 D-21)

```python
CROSSFADE_SECONDS = 4                 # fade length; 200 frames. The D-08 render used this.
CROSSFADE_MIN_TRACK_SECONDS = 20      # below this, hard cut (fading a 15s clip is silly)
```

`4s` is a defensible default for uncorrelated pop/rock and is what the render demonstrates —
**if the render feels long or short, change this one constant** (D-12b; that is the whole point of
the knob being fixed). Also require `outgoing_duration > CROSSFADE_SECONDS * 2`.

### 7. `MusicQueue` state (D-12 — the `auto_lyrics` precedent)

```python
self.crossfade_enabled: bool = False   # server preference: NOT reset by clear(), NOT persisted
self._xf_pending: tuple[Track, float] | None = None   # playback state: MUST be reset by clear()
self._xf_truncator = None                             # playback state: MUST be reset by clear()
```

`crossfade_enabled` sits with `auto_lyrics` **above** the `clear()` reset block; the two
`_xf_*` fields are playback state and **must** be nulled in `clear()` — a stale `_xf_pending`
surviving a `/stop` would make the *next* session's first track try to fade in from a track that
is no longer playing. `queue_persistence.persist()` builds an explicit typed key dict, so all three
are unpersisted by construction (same as `radio_armed`).

### 8. Landmines hit (every one of these cost real time)

1. **`send_silence()` = 100ms at every boundary.** Finding #2. My first capture filtered it out
   (it arrives with `encode=False`) and **the render flattered the design**. If you re-render,
   capture `OPUS_SILENCE` as PCM zeros or you are lying to yourself.
2. **The fade arms *while the previous fade is still mixing*** — the source becomes
   `TruncatingSource(CrossfadeSource(...))`. Nesting is correct and required, but any instrumentation
   or `isinstance` check on `vc.source` must expect the wrapper, not the mixer (attack 1's
   `frames_mixed=-`).
3. **The LFU cache does not protect the outgoing track's file during a fade.**
   `bot.py:1043` protects `queue.tracks[queue.current_index:]` + the prefetch slot, but by fade time
   `current_index` has **already advanced to the incoming track**, so the outgoing file — actively
   being read by the tail decoder — is eviction-eligible. Verified verbatim against the real
   construction:
   ```
   protected set during a fade: ['INCOMING_B', 'NEXT_C']
   OUTGOING_A (its file is being read by the fade's tail decoder) protected? False
   ```
   **Benign in practice** (Windows: `unlink` fails and `cleanup_cache` already catches `OSError` and
   continues; Linux/Docker: `unlink` succeeds but the open fd keeps the decode alive — POSIX). But
   the accounting is wrong and it is one line to fix: include `tracks[current_index - 1]` when a
   fade is in flight. Worth doing; **not** a blocker.
4. **`_persist_queue` (a Neon round-trip) sits in the transition path *today***, between
   `_on_track_end` and `play()`. The spike stubbed it, so the measured **0.016s** gap is the
   crossfade's *own* cost (two FFmpeg spawns) and **understates** the real hole, which also carries
   that pre-existing RTT. This is not a regression — it is the same await that runs at every
   transition now — but it lands mid-music with crossfade on. Do not pre-spawn the decoders to
   "fix" this: the cut position isn't known until the truncator actually cuts (landmine #5).
5. **`Track.duration_seconds` (YouTube metadata) ≠ the file's real duration.** Never compute the
   `-ss` from metadata.
6. **`audioop` emits a `DeprecationWarning` on 3.12** (local) and is **gone in 3.13**. Harmless on
   the pinned 3.11 (`Dockerfile:4`, `ci.yml`). D-02's accepted cost, unchanged.
7. **`_do_skip`'s `make_task(self._play_track(...))` is async** — the fade keeps playing until the
   next source is acquired. Pre-existing; visible with crossfade on. Do **not** "fix" it inside this
   phase (D-12c is about tearing the fade down, and `stop()` inside `_play_track` already does it).

---

## Round 2: the 100ms boundary

**Ran:** 2026-07-17, second `spike/crossfade` branch off `main` (recovered from the round-1
commit object, re-attacked, deleted again). **Prompted by:** the coordinator refusing my claim that
removing the boundary silence requires the D-01 mixer rewrite.

**Outcome: my claim was wrong. The coordinator's reading of `discord/player.py` was correct.**
The 100ms is real, and it is removable additively.

### Task 2 — Is the 100ms real, or a modelling artifact? → **REAL. Confirmed twice.**

I *did* model it into the round-1 render (my source never produces it; the player injects it into
the packet stream), so this needed proving rather than asserting. Two independent confirmations:

**(a) Source reading — `VoiceClient.send_audio_packet` (discord.py 2.7.1):**

```python
self.checked_add('sequence', 1, 65535)
if encode:
    encoded_data = self.encoder.encode(data, self.encoder.SAMPLES_PER_FRAME)
else:
    encoded_data = data                       # <- the OPUS_SILENCE path
packet = self._get_voice_packet(encoded_data)
...
self.checked_add('timestamp', opus.Encoder.SAMPLES_PER_FRAME, 4294967295)   # UNCONDITIONAL
```

The timestamp advance is **outside** the `if encode:` branch — a silence packet advances the RTP
timeline by 960 samples (20ms) exactly like a music packet. **The 5 unpaced packets do not
collapse**: pacing affects *arrival* time, but the decoder plays out by RTP timestamp, so they
occupy 100ms of the timeline regardless of how fast they were sent. `timestamp`/`sequence` also
live on the **`VoiceClient`, not the `AudioPlayer`**, so they persist across `play()` calls.

**(b) Runtime forensics** — the fake client now mirrors that bookkeeping verbatim and logs every
packet. Across the fade boundary:

```
  RTP packets across the fade boundary (seq, timestamp, encode):
    seq=399   ts=382080   t=  7.960s encode=True
    seq=400   ts=383040   t=  7.980s encode=True
    seq=401   ts=384000   t=  8.000s encode=False  <-- SILENCE (advances timeline 20ms)
    seq=402   ts=384960   t=  8.020s encode=False  <-- SILENCE (advances timeline 20ms)
    seq=403   ts=385920   t=  8.040s encode=False  <-- SILENCE (advances timeline 20ms)
    seq=404   ts=386880   t=  8.060s encode=False  <-- SILENCE (advances timeline 20ms)
    seq=405   ts=387840   t=  8.080s encode=False  <-- SILENCE (advances timeline 20ms)
    seq=406   ts=388800   t=  8.100s encode=True
  RTP timestamp deltas: all 960 samples(20ms)? True  anomalies=[]
```

**A genuine 100ms hole at `t=8.000–8.100`.** So the round-1 render was honest.

**A bonus finding this produced — the transition gap is NOT an audio hole at all.** Because the
timestamp lives on the client and every delta is exactly 960, the next player's first packet
carries `ts = old + 960`. **The 0.016s wall-clock gap (and the pre-existing Neon `_persist_queue`
RTT) inserts *no silence into the decoded timeline*** — it only costs jitter-buffer depth. Landmine
#4's framing in round 1 was pessimistic: the *only* real hole is the injected silence. (A long
enough stall could still underrun Discord's jitter buffer — unverifiable offline.)

### Task 3 — Is suppression achievable additively? → **YES, and it does not trip D-01.**

`send_silence` is a method on **`AudioPlayer`** (`discord/player.py:892`), called from `_do_run` at
`:833` (loop end) and `:796` (pause). Suppressing it changes **nothing** about the engine model:
per-track `play()`, one source per `play()`, the generation counter and `after_callback` are all
untouched. **D-01 forbids replacing the engine model; it does not forbid declining a library's
injected gap.** My conflation of the two was the error.

The mechanism that works — **opt-in via a source attribute**, so the off path is untouched:

```python
_original_send_silence = AudioPlayer.send_silence

def _patched_send_silence(self, count: int = 5) -> None:
    if getattr(self.source, "_suppress_end_silence", False):
        return
    return _original_send_silence(self, count)
```

`TruncatingSource` sets `_suppress_end_silence = True` **at the exact moment it cuts short for a
fade** — not at construction, and never on a natural early EOF (a real end of transmission *does*
want the marker). Observed, in one run:

```
[RENDER/SUPPRESSED] silence_at_fade_boundary=0  patch_suppressed=1  patch_passed_through=1
  no silence packets at the fade boundary — timeline is continuous
  RTP timestamp deltas: all 960 samples(20ms)? True  anomalies=[]
```

`patch_suppressed=1, patch_passed_through=1` is the precision proof: **the fade boundary's marker
was suppressed and the genuine end-of-playback marker still fired.** Scoping properties:

| Property | Result |
|---|---|
| Off path byte-identical? | **Yes.** No other source sets the attribute → `getattr` → `False` → the original method, unchanged. |
| Scoped to fades only? | **Yes.** Only a `TruncatingSource` that actually cut short for a fade sets it. |
| `/pause` mid-track? | **Safe.** The flag is False until the cut; after the cut the player has already left the loop, so the pause path can never observe it set. |
| Engine model touched? | **No.** Verified by re-running the attacks (below). |

**Re-ran attacks 1 and 2 with suppression installed — identical, still clean:**

```
=== ATTACK 1 WITH SUPPRESSION ===
[MID-FADE]  ffmpeg=2 gen=2 current_index=1
STALE after_callback suppressed: gen=3 current_gen=2
[AFTER-SKIP] verdict=SKIP_NOW gen=3 current_index=2 ffmpeg=1 playing=True
[TEARDOWN]  ffmpeg=0 baseline=0

=== ATTACK 2 WITH SUPPRESSION ===
[MID-FADE]     ffmpeg=2 gen=2 source=CrossfadeSource frames_mixed=83
STALE after_callback suppressed: gen=4 current_gen=2
[AFTER-stop]   ffmpeg=0 baseline=0 gen=4 playing=False connected=False tracks=0
[AFTER-idle-leave] ffmpeg=0 baseline=0 gen=4 playing=False connected=False tracks=0
```

**Honest risk assessment of suppression** — this is the tradeoff, stated plainly:

1. **It monkeypatches a library internal.** `AudioPlayer.send_silence` is undocumented API. A
   discord.py upgrade that renames it makes `_original_send_silence = AudioPlayer.send_silence`
   raise `AttributeError` **at import — a boot crash, not a graceful degrade.** If this ships,
   the install **must** be wrapped so a failure degrades to today's behaviour, plus a CI guard test
   asserting the attribute exists and `_do_run` still calls it. With that, the failure mode becomes
   "the 100ms comes back" — i.e. exactly the other render.
2. **Whether Discord's decoder minds the missing marker is unverifiable offline.** Reasoned: the
   marker exists to tell the decoder transmission *ended* so it stops interpolating; we are
   continuing with an unbroken, gap-free sequence/timestamp series, which is indistinguishable from
   ordinary continuous playback. PLC triggers on *missing* packets and none are missing. **Low
   risk, but reasoned — not measured.** → `27-HUMAN-UAT.md`.
3. **The `speak(none)` → `speak(voice)` websocket toggle still happens** at the boundary. **Not
   new** — it fires at every track change today. Suppression neither adds nor removes it.

### Task 1 — The two renders (the decisive experiment)

Same tracks, same 4s equal-power fade, same code path. **Verified to differ by nothing else:**

```
with-silence: 17.160s   no-silence: 17.060s
difference  : 100 ms  (5 frames of 20ms)
with-silence == no-silence + 100ms zeros spliced at t=8.0 ?  True
  -> the two renders are otherwise IDENTICAL sample-for-sample
  with-silence  silent frames at t=8.0-8.1: [8.0, 8.02, 8.04, 8.06, 8.08]
  no-silence    silent frames at t=8.0-8.1: []
```

| File | Absolute path |
|---|---|
| **With silence** (today's engine behaviour, unpatched) | `C:\Users\James\AppData\Local\Temp\claude\C--Users-James-desktop-projects-dexter\dde3f576-9998-4940-a8cd-d61e2e10b8a4\scratchpad\dexter-crossfade-with-silence.wav` |
| **No silence** (suppression installed) | `C:\Users\James\AppData\Local\Temp\claude\C--Users-James-desktop-projects-dexter\dde3f576-9998-4940-a8cd-d61e2e10b8a4\scratchpad\dexter-crossfade-no-silence.wav` |

*(The round-1 `dexter-crossfade-spike.wav` is still there and is identical to the with-silence one.)*

**Listen at 0:08 in each.** That is the only difference between the two files — a 100ms hole,
present in one and absent in the other. **I cannot hear either and I am not telling you which is
better** (D-10). If they sound the same to you, take the with-silence variant: it needs no
monkeypatch and carries zero library-fragility. If the hole is audible, suppression is available
and costs one guarded patch.

### Task 4 — "Relocate the boundary" → **REFUTED. Structurally hopeless. The coordinator was right.**

Equal-power means `g_out² + g_in² = 1`, so `max(g_out, g_in) ≥ 1/√2` **at every instant**:

```
 t      g_out   g_in    max(g)   max in dBFS
  0.0   1.000   0.000   1.000     0.00 dB
  0.5   0.707   0.707   0.707    -3.01 dB      <- the quietest it EVER gets
  1.0   0.000   1.000   1.000     0.00 dB

 QUIETEST the loudest track EVER gets during the fade: 0.707 = -3.01 dBFS (at the midpoint)
```

**There is no instant in a crossfade where both tracks are quiet** — that is the definition of a
constant-power fade. So a player boundary placed *anywhere* inside the fade lands on audio at worst
3dB down. Shape A puts it at `t=0` (outgoing at 0.0dB); shape B puts it at `t=1` (incoming at
0.0dB); the theoretical best (the midpoint) is still only 3dB down and would require *two* boundaries.
**Relocation cannot hide the hole — it can only choose which track it damages.** This is a
structural property of crossfading, not of this design. It is also why suppression (Task 3) is the
*only* real mitigation, and why it mattered enough to be worth a second round.

### What this changes

- **Verdict: unchanged at GO**, and now **unqualified at the engine level** — the caveat that
  qualified it has a proven additive fix.
- **The user's D-04 decision is no longer "GO vs NO-GO over a dropout".** It is: **GO/plain**
  (accept a 100ms hole that already exists at every transition today, zero fragility) or
  **GO/suppressed** (gapless, one guarded monkeypatch + one parked live check). Both are GO.
- **A NO-GO on these findings would now be a taste decision, not an engineering one.** That is
  legitimate and still entirely the user's call (D-04/D-13) — but it should be made knowing the
  engine objection has been withdrawn.

---

## Narrow-go exclusions

Crossfade **must silently hard-cut** (today's behaviour + one log line — D-10b; the room sees
nothing) when **any** of:

| Condition | `FadeVerdict` | Why |
|---|---|---|
| `/crossfade` off | `NO_TOGGLE` | D-08b — off by default; opus fast path preserved |
| No next track | `NO_NEXT_TRACK` | Nothing to fade into |
| `loop_mode == SINGLE` | `LOOP_SINGLE` | D-11b — self-overlap is phasing, not a blend. **loop QUEUE stays allowed** |
| `active_filter != "off"` | `FILTER_ACTIVE` | Already transcoding an `-af` chain; composing the two is out of scope |
| Either track not cached (stream fallback / cold prefetch) | `NOT_CACHED` | The tail needs a **seekable local file**. Verified live in attack 3 |
| `offset_seconds > 0` (`/seek`, resume-with-offset) | `SEEKED` | Cut arithmetic assumes playback started at 0 |
| Either track `< CROSSFADE_MIN_TRACK_SECONDS`, or outgoing `<= 2 × CROSSFADE_SECONDS` | `TOO_SHORT` | Fading a short clip is mostly fade |

Per D-03 **this is a GO, not a partial failure**: the fallback *is* current behaviour, so a
non-fadeable transition is never worse than what ships today. In the common case (cached queue, no
filter) it fades.

---

## Git protocol proof (D-16)

Spike ran on `spike/crossfade` off `main` — **twice**. Round 2 recovered the round-1 commit from
the object store (`git checkout -b spike/crossfade d11ff70`, still unreachable-but-not-gc'd),
re-attacked, and deleted the branch again (`was d86a3df`). Only explicit `_spike/*.py` paths were
ever staged (`git add -A`/`git add .` never used; nothing under `.planning/`, `.claude/` or `docs/`
ever committed). **`main` was never touched** — zero tracked source files modified. Proof below is
from **after round 2's cleanup**:

```
$ git branch --show-current
main

$ git rev-parse --verify spike/crossfade
fatal: Needed a single revision                 # branch gone (was d11ff70)

$ test -e _spike && echo PRESENT || echo absent
absent                                          # spike code discarded (D-06)

$ git diff --stat -- . ':!.planning' ':!.claude'
                                                # empty — zero tracked source files modified

$ git status --short
 M .claude/settings.local.json                  # ── pre-existing, intact
 M .planning/STATE.md                           # ── pre-existing, intact
?? .claude/.gsd-profile
?? .claude/agents/
?? .claude/commands/
?? .claude/get-shit-done/
?? .claude/gsd-file-manifest.json
?? .claude/gsd-install-state.json
?? .claude/hooks/
?? .claude/package.json
?? .claude/settings.json
?? .planning/phases/25-smarter-memory/25-01-SUMMARY.md
?? .planning/phases/25-smarter-memory/25-02-SUMMARY.md
?? .planning/phases/25-smarter-memory/25-HUMAN-UAT.md
?? .planning/phases/25-smarter-memory/25-REVIEW-FIX.md
?? .planning/phases/25-smarter-memory/25-REVIEW.md
?? .planning/phases/25-smarter-memory/25-VERIFICATION.md
?? .planning/phases/27-crossfade-playback-spike-gated/
?? docs/superpowers/plans/2026-06-02-dexter-phase2.5-hardening.md
?? docs/superpowers/plans/2026-06-11-auto-lyrics.md
?? docs/superpowers/specs/2026-06-02-dexter-phase2.5-hardening-design.md
?? docs/superpowers/specs/2026-06-11-auto-lyrics-design.md
```

Identical to the pre-spike dirty list — nothing lost, nothing extra committed. The only durable
artifacts are **this document** and the **render** (in the scratchpad, outside the repo,
uncommittable by construction).

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x (+ pytest-asyncio) |
| Config file | `pyproject.toml` (ruff config; pytest via `tests/conftest.py`) |
| Quick run command | `pytest tests/test_crossfade_logic.py -x -q` |
| Full suite command | `pytest -q` (baseline: **1175 passed / 129 skipped / 0 failed**) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| DJ-03 | `decide_crossfade` returns `FADE` when every condition allows | unit | `pytest tests/test_crossfade_logic.py::test_fade_when_eligible -x` | ❌ Wave 0 |
| DJ-03 | Toggle off → `NO_TOGGLE` (off-by-default, D-08b) | unit | `pytest tests/test_crossfade_logic.py::test_toggle_off_never_fades -x` | ❌ Wave 0 |
| DJ-03 | `loop SINGLE` → `LOOP_SINGLE`; **loop QUEUE still fades** (D-11b) | unit | `pytest tests/test_crossfade_logic.py::test_loop_single_hard_cuts -x` | ❌ Wave 0 |
| DJ-03 | Filter active → `FILTER_ACTIVE` (D-10b) | unit | `pytest tests/test_crossfade_logic.py::test_filter_hard_cuts -x` | ❌ Wave 0 |
| DJ-03 | Either track uncached → `NOT_CACHED` (D-03 narrow-go) | unit | `pytest tests/test_crossfade_logic.py::test_uncached_hard_cuts -x` | ❌ Wave 0 |
| DJ-03 | No next track / seeked / too-short → correct verdict | unit | `pytest tests/test_crossfade_logic.py::test_remaining_ladder_rungs -x` | ❌ Wave 0 |
| DJ-03 | Ladder **order** is stable (each rung wins over later ones) | unit | `pytest tests/test_crossfade_logic.py::test_ladder_precedence -x` | ❌ Wave 0 |
| DJ-03 | `cut_frame` arithmetic (incl. metadata-vs-file mismatch guard) | unit | `pytest tests/test_crossfade_logic.py::test_cut_frame -x` | ❌ Wave 0 |
| DJ-03 | `crossfade_enabled` survives `clear()`; `_xf_pending`/`_xf_truncator` are reset by it (D-12) | unit | `pytest tests/test_queue.py::test_crossfade_toggle_survives_clear -x` | ❌ Wave 0 |
| DJ-03 | Toggle is **not** persisted (typed-key dict guard) | unit | `pytest tests/test_queue_persistence.py::test_crossfade_not_persisted -x` | ❌ Wave 0 |
| DJ-03 | **Byte-identical when off**: `get_source()` with no `crossfade_from` is unchanged (opus fast path) | unit | `pytest tests/test_audio.py::test_get_source_unchanged_without_crossfade -x` | ❌ Wave 0 |
| DJ-03 | `TruncatingSource` exhausts at `max_frames`, delegates `is_opus()`, cleans inner | unit | `pytest tests/test_audio.py::test_truncating_source -x` | ❌ Wave 0 |
| DJ-03 | `CrossfadeSource.cleanup()` cleans **both** children, head via `finally` (Critical Rule 3) | unit | `pytest tests/test_audio.py::test_crossfade_source_cleans_both -x` | ❌ Wave 0 |
| DJ-03 | Empty tail (short file / bad `-ss`) degrades to fade-in, never raises | unit | `pytest tests/test_audio.py::test_crossfade_tolerates_empty_tail -x` | ❌ Wave 0 |
| DJ-03 | `/crossfade on\|off` copy is lowercase, ≤1 emoji (Critical Rules 7/8) | unit | `pytest tests/test_responses.py::test_crossfade_copy_style -x` | ❌ Wave 0 |
| DJ-03 | *(suppressed variant only)* `TruncatingSource` sets `_suppress_end_silence` **only** on a fade cut — never on natural EOF, never before the cut | unit | `pytest tests/test_audio.py::test_suppress_flag_only_on_fade_cut -x` | ❌ Wave 0 |
| DJ-03 | *(suppressed variant only)* **discord.py drift guard**: `AudioPlayer.send_silence` exists and `_do_run` still calls it — fails the build on a library upgrade that moves it | unit | `pytest tests/test_audio.py::test_send_silence_patch_target_exists -x` | ❌ Wave 0 |
| DJ-03 | *(suppressed variant only)* patch install degrades gracefully (no boot crash) if the target is gone | unit | `pytest tests/test_audio.py::test_patch_install_fails_soft -x` | ❌ Wave 0 |
| DJ-03 | **SC-2 (audible blend)** — the D-08 render | **manual** | — *(user's ear; D-10)* | n/a |
| DJ-03 | Live-Discord confirmation (Opus encode + jitter) | **manual, parked** | — *(D-09 → `27-HUMAN-UAT.md`, joins the 33 parked items)* | n/a |

`_play_track` / `_on_track_end` glue stays **untested-by-design** per `TESTING.md` (structural
review + clean boot); its safety evidence is this spike's attack artifacts, not unit tests — which
is exactly why D-11 demanded observable artifacts.

### Sampling Rate

- **Per task commit:** `pytest tests/test_crossfade_logic.py -x -q`
- **Per wave merge:** `pytest -q`
- **Phase gate:** full suite green (≥1175 passed, 0 failed) + the D-08 render re-listened before
  `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_crossfade_logic.py` — covers DJ-03's eligibility ladder (the D-14 seam). **New file.**
- [ ] `tests/test_audio.py` — **extend** (exists): `TruncatingSource`, `CrossfadeSource` cleanup/empty-tail, byte-identical-when-off guard
- [ ] `tests/test_queue.py` — **extend** (exists): D-12 `clear()` semantics
- [ ] Framework install: none needed — pytest + `audioop` (stdlib on 3.11) already present; **no new dependency** (D-02)

---

## Open Questions

1. **~~Is the 100ms boundary dropout at the fade start acceptable? If no → NO-GO.~~** —
   **REFRAMED in Round 2. It no longer gates the phase.** The dropout is real, but it is removable
   additively without tripping D-01. The question is now: **which GO variant** —
   **plain** (100ms hole, identical to today's transitions, zero library fragility) or
   **suppressed** (gapless, one guarded monkeypatch + one parked live check)? Compare
   `dexter-crossfade-with-silence.wav` vs `dexter-crossfade-no-silence.wav` at 0:08 — they differ
   by nothing else. *(Still unresolvable by me — D-10: an agent cannot hear. But it is now a
   variant choice, not a no-go trigger.)*
2. **Is `CROSSFADE_SECONDS = 4` right?** — the render demonstrates 4s. One constant; change on the
   listen (D-12b). *(Deferred to the user's ear; planner's discretion otherwise.)*
3. **(RESOLVED)** Does crossfade require replacing per-track `play()`? — **No.** Shape A is fully
   additive; D-01 is satisfied. Proven by all three attacks.
4. **(RESOLVED)** Curve? — **equal-power**. Measured: no mid-fade RMS dip, 0.0019% clipping, no
   headroom gain needed.
5. **(RESOLVED)** Does the fade collide with prefetch? — **No, structurally.** A fade requires the
   incoming cached; prefetch early-exits when cached. Mutually exclusive.
6. **(RESOLVED)** Does `-ss` on opus mis-seek and click? — **No.** 0ms skew measured.
7. **(RESOLVED)** Does `audioop` wrap on overflow? — **No, it saturates.**
8. **Should the LFU protected set include the outgoing track during a fade?** — landmine #3.
   Benign on both platforms, one line to fix. **Recommend yes**; planner's call whether it lands in
   this phase or a follow-up.
9. **(RESOLVED — Round 2)** Is the 100ms a modelling artifact? — **No, it is real.** The RTP
   timestamp advances 960 samples per silence packet, unconditionally; captured packet-by-packet.
10. **(RESOLVED — Round 2)** Can it be suppressed additively? — **Yes.** Source-attribute-gated
    patch of `AudioPlayer.send_silence`; off path byte-identical; attacks 1 & 2 re-run clean.
    **D-01 is not tripped** — my round-1 claim to the contrary was wrong.
11. **(RESOLVED — Round 2)** Does relocating the boundary (shape B) help? — **No, structurally.**
    Equal-power guarantees `max(g) ≥ −3dB` at every instant; no boundary placement hides a hole.
12. **(RESOLVED — Round 2)** Does the wall-clock transition gap (16ms + Neon RTT) insert silence?
    — **No.** The RTP timestamp lives on the VoiceClient and continues across `play()`, so the
    decoded timeline is unbroken. It costs jitter-buffer depth only.
13. **If suppression ships: does Discord's decoder mind the missing end-of-transmission marker?** —
    reasoned low-risk (no packets are missing; the stream is continuous), but **unverifiable
    offline**. → `27-HUMAN-UAT.md`, alongside the D-09 live-Discord confirmation.

---

*Phase: 27-crossfade-playback-spike-gated*
*Spike ran: 2026-07-17 — branch `spike/crossfade` created, attacked, and deleted (D-06/D-16)*
