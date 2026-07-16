# Phase 27: Crossfade Playback (Spike-Gated) - Context

**Gathered:** 2026-07-17
**Status:** Ready for planning

> **Session note:** The user launched `/gsd:discuss-phase 27`, was presented four phase-specific gray
> areas, **explicitly selected all four**, and **affirmatively chose the recommended option for every
> question** (D-01…D-16) — not an AFK adoption. They chose "More questions" once (spike verdict bar,
> surfacing D-05/D-06/D-07) and "Explore more gray areas" after the four areas closed, which surfaced
> D-13…D-16. One answer arrived as free text ("your recommended yea.. btw should crossfade be
> toggleable on or off hmm?") — the recommendation was locked as D-12 and the toggle question answered
> inline as already-decided by D-08/D-09 (it *is* toggleable, off by default); the user did not
> revise it.
>
> This phase spends **DJ-03** (crossfade) — the milestone's **only spike-gated requirement**, and the
> only phase in v1.5 that may legitimately close having shipped **no feature code at all**.

<domain>
## Phase Boundary

Phase 27 is **a gate first and a feature second.** It delivers exactly one of two outcomes:

- **On a GO verdict:** crossfade — the tail of the outgoing track audibly blends into the head of the
  incoming track — implemented as an **additive, opt-in, off-by-default** behavior over the existing
  playback engine, degrading silently to today's hard cut wherever a fade isn't possible.
- **On a NO-GO verdict:** DJ-03 is formally descoped to **DJ-F2** in Future Requirements with the
  spike's findings recorded, and **the phase closes GREEN with the descope as its deliverable**
  (D-13). This is the standing **Descope Rule** working as designed, not a failure.

**The gate is real, not ceremonial.** A plan-time spike prototypes crossfade against the *actual*
generation-counter / `/skip` / prefetch engine and produces an explicit verdict **before any
implementation plan is written** (D-15). The user personally owns the go/no-go call (D-04).

**In scope:**
- **The spike** (always — this is the phase's first and possibly only work): a throwaway
  `spike/crossfade` branch off `main` (D-16), prototyping against the real in-repo engine (D-05),
  attacking three named failure modes (D-07), producing observable evidence (D-11) + a rendered audio
  file the user listens to (D-08/D-10), then **discarded either way** (D-06).
- **The verdict gate:** an explicit go/no-go in RESEARCH.md surfaced to the user before plans exist
  (D-04/D-15).
- **On a go only:** a `/crossfade on|off` toggle (D-09), off by default (D-08), in-memory per-guild
  state surviving `clear()` (D-12); a pure `logic/crossfade.py` **eligibility** seam (D-14); PCM
  mixing in `services/audio.py` (D-14); a fixed `config.py` fade-length knob (D-12b); silent
  hard-cut fallback (D-10b).
- **On a no-go only:** REQUIREMENTS.md / ROADMAP.md / PROJECT.md updated to move DJ-03 → DJ-F2 with
  findings; phase closes green (D-13).

**Out of scope:**
- **Any change to the per-track `voice_client.play()` + generation-counter engine model.** The spike
  may **not** propose replacing it with a session-long mixer source — **that proposal IS the no-go**
  (D-01). Crossfade is additive or it does not ship.
- **Any new runtime dependency.** `audioop` (stdlib on the pinned 3.11) only; **numpy is rejected**
  (D-02).
- **Any schema change, `guild_config` column, or `/setup` toggle** — Phase 26's D-21 rule holds:
  music commands get global `config.py` knobs and in-memory per-guild state, never per-guild config.
- **Any change to Phase 26's skip-vote machinery.** The `(current_index, video_id)` vote cache and the
  single `_try_skip` → `_do_skip` choke point are untouched (D-12).
- **A user-settable fade length** — rejected (D-12b); fixed knob, planner's discretion.
- **Portfolio finish (PORT-02 / CICD-02 / CICD-03)** → Phase 28.

</domain>

<decisions>
## Implementation Decisions

### The spike's verdict bar

- **D-01 (user-selected): ADDITIVE-ONLY — the engine model is inviolable; a rewrite proposal IS the
  no-go.** The per-track `voice_client.play()` + generation-counter model stays. Crossfade must be an
  additive wrapper around it; if the prototype concludes it needs a session-long mixer source
  replacing per-track `play()`, **that is a no-go verdict, not a design option.** Matches every phase
  since 13 (additive, byte-identical when off) and means a no-go costs **one spike, not a
  destabilized engine**. The surface at risk is the most scarred in the codebase (`logic/playback.py`
  names scar #1 finished-song replay, scar #2 silent auto-queue, scar #4 restore index clamp), it is
  glue that is untested-by-design, and live UAT is parked — so nothing would catch a regression here.
  *(Rejected: **rewrite on the table if invariants hold** — highest ceiling (true gapless crossfade),
  but the proof burden lands on untested glue with no live UAT to catch what review misses. Rejected:
  **rewrite freely, judge on merit** — fewest artificial limits, but with the host parked there is no
  way to feel whether a new engine is sound before it ships.)*

- **D-02 (user-selected): stdlib `audioop` — accept the Python 3.13 dead-end.** `audioop.add`/`mul` is
  stdlib on the pinned 3.11 (verified: `Dockerfile:4` = `python:3.11-slim-bookworm`, `ci.yml` pins
  3.11 at both jobs), zero new dependencies, and is exactly what the prior art
  (`discord-ext-music`, `veloura-audio`) uses. **Accepted cost:** `audioop` is removed in Python 3.13,
  so a future interpreter bump forces a mixer rewrite. Paying a ~40MB dependency now to insure a bump
  that is not scheduled — for a feature that may not even ship — is backwards.
  *(Rejected: **require numpy** — survives the 3.13 removal and is fast, but adds a runtime dep to a
  deliberately tight stack, landing in `requirements.txt` whether or not crossfade proves out.
  Rejected: **pure-Python mixing** — no deps and no cliff, but mixing 3840-byte frames 50×/second in
  the same event loop that runs Discord is the one place this bot has never spent CPU. Rejected:
  **let the spike decide** — hands a dependency call to a subagent rather than the user.)*

- **D-03 (user-selected): a NARROW GO IS A GO — degrade to hard cut.** If crossfade works only under
  some conditions (both tracks cached, no filter active, …), that is a **go**: fade where conditions
  allow, fall back to today's hard cut otherwise. This is the exact grain of the existing engine —
  `cache → download → stream` and `opus-copy → transcode-when-filtered` are both already conditional
  ladders — and **the fallback is literally current behavior, so a degraded transition is never worse
  than what ships today.**
  *(Rejected: **all-or-nothing** — unambiguous, but likely discards a working feature over the rarer
  paths (stream fallback), and "always" is unachievable anyway once `/filter` exists. Rejected:
  **bring the partial verdict to the user at plan time** — stalls the phase on a decision answerable
  now with the same information.)*

- **D-04 (user-selected): the spike PROPOSES; the USER decides at an explicit gate.** The spike writes
  a verdict + evidence into RESEARCH.md; **planning halts and surfaces it to the user as a
  go/descope gate before any implementation plan is written.** Descoping DJ-03 rewrites
  REQUIREMENTS.md/ROADMAP.md and closes out a milestone requirement — that is the user's call, and
  roadmap SC-1 already demands the verdict land "before full implementation starts."
  *(Rejected: **binding verdict, planning auto-routes** — zero human latency and honors the Descope
  Rule mechanically, but lets a subagent unilaterally kill a milestone requirement, and this project's
  agents have a documented over-claiming history (Phase 26 review). Rejected: **advisory verdict, the
  planner weighs it** — blurs the gate SC-1 exists to make sharp; a spike you can plan around is not
  a gate.)*

- **D-05 (user-selected): the spike prototypes against the REAL engine, in-repo.** Import the actual
  `MusicQueue`, `logic/playback.py`, and a real `_play_track` flow; wire the crossfade source into the
  genuine generation-counter path. **The whole named risk is `/skip`-mid-fade racing the generation
  counter — a standalone script cannot race a counter it does not have.** Roadmap SC-1's wording
  ("prototypes crossfade against the real generation-counter/`/skip`/prefetch playback engine")
  demands this. `scripts/memory_spike.py` (Phase 11) is the in-repo spike precedent.
  *(Rejected: **standalone script under `scripts/`** — fast and leaves no debris, but proves the
  mixing math, which was never in doubt; the doubt is the engine interaction. Rejected: **read prior
  art and reason it through** — cheapest, and prior art already establishes feasibility, but a
  reasoned verdict is not a spike.)*

- **D-06 (user-selected): DISCARD the spike code ALWAYS — reimplement clean on a go.** The spike's
  only artifact is the **verdict + findings in RESEARCH.md**; the branch dies either way. On a go,
  implementation is planned and TDD'd fresh from those findings. Spike code is written to answer a
  question fast, not to survive — and this lands on the scar surface, the last place to keep code that
  skipped the pure-logic seam and the test discipline.
  *(Rejected: **salvage the prototype on a go** — saves real duplicated effort, but carries prototype
  shortcuts into the engine and arrives pre-shaped rather than driven by `logic/` + mock-free tests.
  Rejected: **keep it under `scripts/` as reference** — preserves evidence, but `memory_spike.py` was
  a standalone numeric probe; a parked half-crossfade of the engine is a different, staler thing.)*

- **D-07 (user-selected, multi): the spike must actively BREAK three named attacks before a go is
  credible.** All three are required; a go verdict that has not attempted them is not credible.
  1. **`/skip` landing mid-fade** — the named risk in ROADMAP/REQUIREMENTS. Two sources live; a skip
     must not double-play, orphan an FFmpeg process, or desync the generation counter.
  2. **`/stop` + idle-leave mid-fade** — teardown with two live sources. Phase 5's DEPLOY-06 scar was
     exactly a teardown site that failed to mirror the `/stop` template; Phase 26's D-07 disarm hangs
     off the same sites. **Two live sources = two things to clean up; orphan risk doubles.**
  3. **Prefetch racing the fade** — the fade reads the next track while `_prefetch_next_track` is
     generation-guardedly fetching that same track. Unproven collision; Phase 6 spent a whole phase
     making prefetch work.
  *(NOT selected: **rapid consecutive skips** (overlapping/stacked fades) — deferred; load-testing on
  top of attack 1, and a natural next probe only if a single skip proves clean. It does **not** gate
  the verdict.)*

- **D-16 (user-selected): the spike runs on a REAL throwaway git branch off `main`, hard-deleted
  after.** `git checkout -b spike/crossfade` → prototype → capture evidence → return to `main` →
  delete the branch. Real isolation with **no worktree**, which matters because the standing recorded
  gotcha is that Claude Code's `isolation=worktree` forks a **stale `origin/main`** in this repo — a
  worktree spike would prototype against an engine that isn't the current one, **defeating its entire
  purpose.** `main` is never touched, and D-06's "discard always" becomes a branch deletion rather
  than a manual unwind. (`.planning/config.json` already sets `workflow.use_worktrees: false`.)
  *(Rejected: **directly on `main`, revert when done** — matches the sequential-on-main pattern of
  recent phases, but puts experimental engine hacks on the only branch, and "revert when done" is a
  promise rather than a mechanism. Rejected: **`isolation=worktree`** — purpose-built isolation, but
  the stale-`origin/main` gotcha makes it actively wrong here.)*

### The spike's evidence (how SC-2 gets proven with live UAT parked)

- **D-08 (user-selected): RENDER the mixed PCM to a local file and LISTEN to it.** The spike writes a
  real transition's mixed output to a `.wav`/`.opus` the user plays back on their PC. **This needs no
  Discord, no voice connection, and no always-on host — it sidesteps the exact blocker that parked the
  other 33 live items.** It is **the one "audible" criterion in the entire project that does NOT
  require the live bot**, and that asymmetry is why this phase can close when others couldn't.
  *(Rejected: **a real Discord voice test on the user's PC** — highest fidelity (proves Discord's Opus
  encode path too), but costs a manual session per iteration and gates the spike on availability.
  Rejected: **structural + unit proof, listen deferred to the host** — consistent with standing
  precedent and unblocks the phase, but closes DJ-03 having **never heard it**, and "audibly blends"
  is the requirement's literal wording.)*

- **D-09 (user-selected): the RENDER SATISFIES SC-2; a live-Discord listen parks as confirmation.**
  The rendered file proves the blend is audible and correct and **closes the phase**; a live-Discord
  confirmation joins `27-HUMAN-UAT.md` with the other 33 parked items. **The mixer output IS the audio
  Discord encodes** — if the fade is right in the file, the residual risk is Opus encoding and network
  jitter, which crossfade does not change and which the render cannot test anyway. Lets the phase
  close honestly **on evidence the user actually heard**, without making DJ-03 hostage to the parked
  host.
  *(Rejected: **live listen required to close** — strictly more honest end-to-end, but makes DJ-03 the
  only v1.5 requirement gated on the parked host. Rejected: **render only, track no live check** —
  cleanest close, but real voice adds an Opus encode + jitter buffer the file never sees; worth one
  parked line even at low risk.)*

- **D-10 (user-selected): the USER listens; the USER'S EAR is the bar.** The spike renders the file
  and hands it over; the user's judgment is the SC-2 verdict, alongside the D-04 go/no-go gate they
  already own. **An agent cannot hear** — it can only assert that it rendered something, and "a
  subagent claimed the audio was fine" is precisely the class of claim the user's standing
  verify-independently lesson exists for.
  *(Rejected: **agent asserts correctness from the waveform** (envelope crossover, no clipping, no
  silence gap) — no human latency and these are real checkable properties, but it proves the math, not
  the experience; a technically-correct fade can still sound wrong. Rejected: **both — numeric gates +
  a spot-check** — most thorough, but makes numeric checks load-bearing for a property being verified
  by ear anyway.)*

- **D-11 (user-selected): the D-07 attacks are proven by OBSERVABLE EVIDENCE, not narrative.** Each
  attack must produce concrete artifacts pasted into RESEARCH.md: **generation-counter values before/
  after, an FFmpeg process count proving zero orphans, and `dexter.log` showing no stale-callback
  firing.** "No double-play, no orphan, no desync" are all **directly observable** — and Phase 26's
  review found a Critical that a narrative summary would have sailed straight past. The gate must have
  something **falsifiable** in front of it.
  *(Rejected: **narrative findings in RESEARCH.md** — fast and readable, but exactly the shape of
  claim the user's own memory says to distrust; "I tested skip-mid-fade and it was fine" is
  unfalsifiable at the gate. Rejected: **mock-free tests over extracted logic** — durable and matches
  convention, but the races live in Discord/process glue that is untested-by-design; a pure test
  cannot reproduce a real orphaned FFmpeg process.)*

### Crossfade's surface (GO path only)

- **D-08b (user-selected): OPT-IN, OFF BY DEFAULT.** Opus-copy stays the default path for everyone who
  does not ask — **preserving the Phase 6/7 decision rather than overriding it** — so a go verdict
  **structurally cannot regress playback for a room that never wanted this.** Mixing requires decoded
  PCM, so any track that crossfades transcodes, and that CPU is spent on the user's own PC (the
  residential-IP box run on demand). `/filter` set the precedent: an off-by-default opt-in that
  transcodes only for the people who asked, resolving the identical tradeoff.
  *(Rejected: **always-on** — the best version of the feature (nobody configures anything), but it
  makes transcode the default for every track, silently reversing a decision two phases were built
  around, on hardware the user personally hosts. Rejected: **radio-mode only** — naturally scoped and
  the unattended-DJ session is where seamless transitions matter most, but it welds two independent
  features together and denies crossfade to a hand-built queue.)*
  > **User asked mid-discussion** whether crossfade should be toggleable — answered inline: it **is**,
  > per this decision + D-09. The **off** default is deliberate and **reversible** (flipping a default
  > is a one-line change; un-shipping a transcode-by-default regression is not).

- **D-09b (user-selected): a NEW `/crossfade on|off` command — the `/autolyrics` shape.** A per-guild
  in-memory boolean on `MusicQueue`, one choice arg, off by default. **Crossfade is a transition
  behavior, not an `-af` chain over one track:** putting it in `/filter` would make it mutually
  exclusive with `bassboost`, which is arbitrary and wrong.
  *(Rejected: **a value in the `/filter` group** — no new command and honest that both paths
  transcode, but `FFMPEG_FILTERS` maps a name → an `-af` chain applied to a single source; crossfade
  is not that shape, and selecting it would silently disable `nightcore`. Rejected: **a `/setup`
  per-guild toggle** — consistent with v1.4's per-guild philosophy, but Phase 26's D-21 just ruled
  that music commands don't get per-guild surfaces; the `AmbientSurface`/`guild_config` machinery
  gates what Dexter does **unprompted at strangers**, which this is not.)*

- **D-10b (user-selected): a non-fadeable transition is a SILENT HARD CUT — log only.** When crossfade
  is on but this transition cannot fade (stream fallback, cold prefetch, filter active, loop SINGLE),
  fall back to today's transition and log why; **the room sees nothing.** The fallback **IS current
  behavior, so there is nothing to apologize for** — and the engine already degrades silently
  everywhere else (`cache → download → stream`, unavailable-track silent skip).
  *(Rejected: **hard cut + a one-line Dexter comment** — in-character and honest, but it fires
  per-transition on the exact paths that are already degraded, turning a graceful fallback into
  repeated complaining about an internal detail nobody asked about. Rejected: **wait for conditions**
  (hold the transition until the incoming track is cached) — delivers on the toggle's promise, but
  **reintroduces the audible dead air Phase 6 spent an entire phase eliminating**, trading a gapless
  cut for a gap.)*

- **D-12 (user-selected): the toggle SURVIVES `clear()` — a server preference, like `auto_lyrics`.**
  `MusicQueue.clear()` deliberately does **not** reset `queue.auto_lyrics`, because it is a stated
  preference rather than playback state. Crossfade is the same kind of thing: **"we like smooth
  transitions here" should not be silently revoked by `/stop`.** In-memory, so it still dies on
  restart (D-08's honesty from Phase 26: the bot going down IS the session ending).
  *(Rejected: **reset on `clear()` like `loop_mode`/radio** — every teardown returns to a clean
  default, which is exactly the D-07 discipline radio needed; but **radio resets because an armed
  station refilling after `/stop` is an unstoppable bot** — crossfade has no runaway behavior; it does
  nothing until a transition happens. Rejected: **persist to `guild_queues` JSONB** — real durability,
  but adds a field to the scar-heavy restore path (index clamp CR-03, rejoin gate) for a boolean, and
  Phase 26's D-08 just rejected exactly this for radio.)*

### Feature interactions (GO path only)

- **D-11b (user-selected): NO fade under loop SINGLE — hard cut, via the existing D-10b fallback.**
  No new rule and no new copy. Fading a track into its own beginning means **mixing one source with
  itself** — outgoing tail and incoming head are the same file at two positions, needing two decoders
  on one track, and it sounds like a **phasing artifact, not a blend.** The one case where the
  feature's premise does not apply. **Note: loop QUEUE + crossfade is completely coherent and stays
  allowed.**
  *(Rejected: **fade into itself** — no special-casing, and a looped ambient/instrumental track
  genuinely benefits from a seamless wrap; but it's the hardest possible mix (self-overlap, comb
  filtering) for the rarest case, on the phase already carrying the milestone's only spike. Rejected:
  **mutually exclusive with loop, like radio (Phase 26 D-11)** — precedent exists, but radio and loop
  genuinely contradict (a looping queue never exhausts) while crossfade and loop do not; this would
  ban a good combination (loop QUEUE + crossfade) to solve only the SINGLE case.)*

- **D-12c (user-selected): a skip CUTS THE FADE DEAD — immediate hard transition.** Both fading
  sources are torn down and the skipped-to track starts, exactly as a skip does today. **A skip is an
  interrupt:** the room voted this track gone, and "gone" should not take another few seconds of
  politely fading. It is also **the safest teardown** — one code path, no partially-faded state to
  reason about, and Critical Rule 3 (kill FFmpeg explicitly) stays trivially satisfied. It keeps the
  spike's riskiest window (two live sources) as short as possible.
  *(Rejected: **let the fade complete, then apply the skip** — smoothest audio, no abrupt cut ever,
  but a skip visibly does not work for seconds after the room voted, and it keeps two sources alive
  through the exact window the spike says is riskiest. Rejected: **a fast fade into the skipped-to
  track** — arguably best of both, but it's a third transition type to build and test, invented
  **inside the precise race the spike exists to prove safe**.)*

- **D-12d (user-selected): a mid-fade skip vote targets the INCOMING track — queue state is the only
  truth.** During a fade two tracks are audible, but **the fade is a presentation detail**:
  `queue.current_index` has already advanced to the incoming track, so the vote targets it exactly as
  it does today. Phase 26 built the `(current_index, video_id)` single-slot vote cache deliberately;
  **reading voter intent from audio overlap would fork "which track is current" away from the queue,
  and that ambiguity is where scars come from.** Phase 26's skip-vote machinery is untouched.
  *(Rejected: **the outgoing track** — arguably truer to intent (someone reacting to a track they
  dislike is reacting to what they still hear), but it makes the vote target depend on millisecond
  timing within the fade and resurrects votes against a track the queue has already left behind.
  Rejected: **suppress skip voting during a fade** — no ambiguity, but `/skip` silently does nothing
  for a few seconds per transition, and DJ-02's whole point is that skip always belongs to the room.)*
  > *Answered via free text: "your recommended yea.." — recommendation locked, not revised.*

- **D-12b (user-selected): fade length is a FIXED `config.py` knob — planner picks the default.** One
  constant (e.g. `CROSSFADE_SECONDS`), **no user-facing arg.** Matches the standing
  discretion-on-numbers precedent (every phase since 11) and keeps `/crossfade` a clean `on|off` like
  `/autolyrics`. **With live UAT parked there is no way to feel out a "good" length anyway — exposing
  the knob would ship a dial nobody can tune.** The D-08 render gate gives a free revisit: if the
  listen says it feels wrong, change the constant.
  *(Rejected: **`/crossfade [seconds]`** — rooms differ (a DJ set wants a long blend, a comedy-clip
  queue wants none), but it's a second argument on a command whose whole virtue is being a boolean,
  plus validation and a per-guild value to hold, for a number with a sane default. Rejected: **fixed
  but explicitly revisit after the listen** — effectively the chosen option with a ceremony the render
  gate already provides.)*

### Phase shape & the no-go path

- **D-13 (user-selected): a NO-GO closes the phase SUCCESSFULLY, with the descope as its
  deliverable.** DJ-03 moves to Future Requirements as **DJ-F2** carrying the spike's findings;
  REQUIREMENTS.md / ROADMAP.md / PROJECT.md are updated; the phase **closes green** with RESEARCH.md
  as its artifact. This is exactly what roadmap SC-3 already says ("the phase closes clean rather than
  shipping an unstable engine change") — **a spike that correctly says "don't build this" did its
  entire job**, and marking that as failure teaches the wrong lesson.
  *(Rejected: **close as blocked/abandoned** — honest that DJ-03 didn't ship, but reads as failure in
  the milestone record when it is the Descope Rule working as designed, and it muddies v1.5's close.
  Rejected: **bring it back to the user to decide how to close** — the user already owns the go/no-go
  gate itself; how a no-go gets *recorded* is a mechanical consequence of the rule.)*

- **D-14 (user-selected): a pure `logic/` seam covers the ELIGIBILITY DECISION ONLY — not the
  mixing.** `logic/crossfade.py` holds **"should this transition fade?"** (toggle on? both cached?
  filter active? loop SINGLE? enough duration remaining?) — keyword-only, mock-free-testable. **The
  PCM mixing stays in `services/audio.py`** where the FFmpeg/discord objects live. This splits along
  the convention's own line: **the fallback ladder is branching decision logic** (and the seam is
  where every D-10b/D-11b fallback rule gets locked by tests), while the frame math is I/O-adjacent
  mechanics **verified by the user's ear on the render (D-10), not by unit tests.**
  *(Rejected: **seam covers eligibility AND mix math** — mixing frames is arithmetic and pure-testable
  too, but it drags buffer handling into `logic/`, which has no I/O by convention. Rejected: **no seam
  — it's all audio mechanics** — least new structure, but the fallback ladder IS exactly the branching
  logic Phase 10 extracted, and leaving it in glue makes it untested-by-design.)*

- **D-15 (user-selected): the SPIKE RUNS AT PLAN TIME; implementation plans are written ONLY after a
  go.** `/gsd:plan-phase 27` runs the spike as its **research step**, surfaces the verdict to the user
  (D-04), and **writes implementation plans only on a go.** Roadmap SC-1 requires the verdict "before
  full implementation starts", and this is what "plan-time spike" literally means. **On a no-go the
  phase has one artifact (RESEARCH.md) and zero wasted plans.**
  > **The planner MUST treat "terminate with a descope and zero plans" as a VALID, SUCCESSFUL
  > outcome** — not a failure, not an error state.
  *(Rejected: **write all plans now; plan 01 is the spike, later plans abort on no-go** — one planning
  pass and a standard shape, but it writes implementation plans for a feature that may be proven
  impossible, and a plan saying "abort everything after me" inverts how execute-phase waves work.
  Rejected: **split into 27a spike / 27b implementation** — cleanest separation, but splits one
  roadmap phase in two for a decision the plan-time research step is already designed to hold.)*

### The D-04 gate outcome (added 2026-07-17, AFTER the spike — this is the verdict, not a pre-decision)

- **D-17 (user-selected at the D-04 gate): GO — the SUPPRESSED variant.** The spike ran (both
  rounds), the user was presented the verdict + an A/B render pair, and **chose GO with the
  `send_silence` suppression included.** DJ-03 ships. Concretely this means:
  1. **Crossfade is built** — `/crossfade on|off` (D-09b), off by default (D-08b), toggle survives
     `clear()` (D-12), pure `logic/crossfade.py` eligibility seam (D-14), PCM mixing in
     `services/audio.py` (D-14), silent hard-cut fallback (D-10b), no fade under loop SINGLE (D-11b).
  2. **The 100ms boundary silence IS suppressed.** discord.py's `AudioPlayer.send_silence` emits 5
     `OPUS_SILENCE` frames = exactly 100ms, and `voice_client.py:610`'s
     `checked_add('timestamp', SAMPLES_PER_FRAME, …)` sits **outside** the `if encode:` branch, so
     those frames genuinely advance the RTP timeline. Verified in-repo against discord.py 2.7.1.
     Because a fade must start *before* the outgoing track ends, that hole lands **mid-music at
     roughly −9.8 dBFS** (measured: peak 10612/32767 in the window; the with-silence render is a
     hard 0 across it). **Un-suppressed, crossfade sounds worse than the hard cut it replaces** —
     which is why the plain variant was rejected.
  3. **Suppression does NOT trip D-01.** It is source-attribute-gated (`TruncatingSource` sets the
     flag only at the instant it cuts for a fade); per-track `voice_client.play()`, one source per
     track, and the generation counter are all untouched. Attacks 1 & 2 were re-run with the patch
     installed: ffmpeg 2→0, stale callbacks suppressed, generation monotonic — identical to
     unpatched. The off path stays byte-identical (nothing else sets the attribute).
  4. **The patch's guard rails are MANDATORY plan content, not discretion.** It patches an
     undocumented library internal, so it MUST ship (a) wrapped — a `getattr`/`hasattr`-guarded
     install that **degrades to "the 100ms returns" rather than crashing at boot** if the target
     ever moves — and (b) **CI-guarded** by a drift test asserting `AudioPlayer.send_silence` exists
     and `_do_run` still calls it, so a discord.py bump turns the build red instead of surprising
     production.
  5. **Whether Discord's decoder minds the missing end-of-transmission marker is REASONED low-risk,
     NOT measured** — it cannot be measured while the host is parked. This **parks in
     `27-HUMAN-UAT.md`** alongside the D-09 live-Discord confirmation and the other 33 items. The
     risk is bounded by D-08b: crossfade is off by default, so the blast radius is exactly the rooms
     that opted in, on hardware the user personally runs, recoverable with one toggle flip.
  > **Superseded by this decision:** the spike's own Round-1 claim that "the only fix is a
  > session-long mixer, which D-01 defines as the NO-GO" — **withdrawn by the spike itself in
  > Round 2** and struck through in RESEARCH.md. D-01's no-go condition was never reached.
  > **Also settled:** "relocate the boundary somewhere harmless" is **structurally impossible** —
  > equal-power guarantees `max(g_out, g_in) ≥ 0.707` at every instant (the loudest track never
  > drops below −3.01dB), so there is no quiet moment in a crossfade to hide a hole in.
  >
  > *(Rejected at the gate: **GO / plain** — zero fragility, no library patching, but ships a 100ms
  > full stop mid-music at −9.8 dBFS: roughly a 16th note at 150bpm, reading as a CD skip. It makes
  > transitions worse than today's hard cut, so nobody would leave it on. Rejected: **NO-GO /
  > descope to DJ-F2** — a legitimate application of the standing Descope Rule (the only shippable
  > variant needs a library monkeypatch whose real-world safety can't be measured while the host is
  > parked), but the engine objection was withdrawn with observable evidence, the failure mode is
  > survivable and CI-caught, and with the host parked indefinitely behind YouTube's datacenter-IP
  > block, "defer until we can measure it live" is a soft kill.)*

### Claude's / Planner's Discretion (do NOT re-ask the user)

Per the standing Phase 11/13/14/15/16/17/21/25/26 "discretion-on-numbers" precedent:

- **Every numeric knob:** the D-12b **fade length default** (`CROSSFADE_SECONDS` or similar), any
  minimum-track-duration floor below which a fade is skipped, and any tail/head buffer sizing. All new
  knobs go in `config.py` as **global** settings (Phase 26 D-21).
- **The exact fade curve** — linear, equal-power/constant-power, logarithmic. (Equal-power is the
  conventional choice for uncorrelated material because linear dips perceived loudness mid-fade, but
  the user's ear on the D-08 render is the arbiter.)
- **The exact `logic/crossfade.py` module name + signature** for the D-14 eligibility seam — follow
  `logic/playback.py` / `logic/vision.py` / `logic/proactive.py` / `logic/radio.py` convention:
  keyword-only, clock/RNG-injected, no Discord imports, glue **dispatches on the returned value and
  never mirrors the branch logic back** (Phase 10 D-02).
- **Where the D-12 crossfade toggle lives on `MusicQueue`** and its exact attribute name — follow the
  `auto_lyrics` precedent (in-memory, NOT reset by `clear()`, NOT persisted).
- **How the mixed source is expressed in `services/audio.py`** — a custom `discord.AudioSource`
  subclass wrapping two sources, vs. another shape — **subject to D-01: it must not require replacing
  the per-track `voice_client.play()` model.**
- **The exact render format + location** for the D-08 spike artifact (`.wav` vs `.opus`; scratchpad vs
  a gitignored path) — it must be trivially playable by the user and must not be committed.
- **Exact test shape.** Mock-free unit tests for the D-14 eligibility seam (this is where the D-10b /
  D-11b fallback ladder gets locked). Per `TESTING.md`, Discord/process glue stays
  untested-by-design (structural review + clean boot). Add a regression guard that **the playback path
  is byte-identical when crossfade is off** (the standing additive-change discipline).
- **Wording of all new personality copy** (the `/crossfade on|off` confirmations) — lowercase, ≤1
  emoji, accurate-first (CLAUDE.md Critical Rules 7/8).

### Reviewed Todos
None — `todo.match-phase 27` returned zero matches (`todo_count: 0`).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Roadmap / requirements (this phase — the gate's own authority)
- `.planning/ROADMAP.md` §"Phase 27: Crossfade Playback (Spike-Gated)" — the goal + **all three
  success criteria**, including **SC-1** (a plan-time spike prototypes against the real engine and
  produces an explicit go/no-go **before full implementation starts** — the D-15 basis), **SC-2** (the
  tail **audibly** blends; `/skip` mid-crossfade does not double-play, orphan FFmpeg, or desync the
  generation counter — the D-07/D-08 basis), and **SC-3** (**on no-go**, DJ-03 formally moves to
  Future Requirements as DJ-F2 with findings documented and the phase **closes clean** — the D-13
  basis). Also the **"Spike required: yes"** note (prior art `veloura-audio` / `discord-ext-music`;
  crossfade forfeits opus-copy during the fade; the `audioop`→`numpy` Python 3.13 note — D-02).
- `.planning/REQUIREMENTS.md` §"New Music Muscle" — **DJ-03 verbatim** (spike-gated, descope-on-
  instability); §"Future Requirements → Music" — **DJ-F2** is the descope target (D-13); §"Traceability"
  (DJ-03 → Phase 27, "Pending (spike-gated)") — **updated on either verdict**; §"Out of Scope".
- `.planning/PROJECT.md` §"Current Milestone: v1.5 Deep Cuts" — the "New music muscle" framing + the
  **standing Descope Rule** that governs this phase; §"Key Decisions" — the **opus-copy-by-default /
  transcode-only-when-filtered** decision (Phase 6/7) that D-08b preserves; §"Constraints" (music
  limits, the 3s interaction rule, the on-demand residential hosting model).
- `.planning/STATE.md` §"Blockers/Concerns" — the standing `[Watch]` entry on DJ-03's spike gate;
  §"Deferred Items" — the **33 parked live-Discord items** that D-08/D-09 deliberately route around.

### The playback engine — READ BEFORE TOUCHING (the scar surface, D-01's subject)
- `cogs/music.py::_play_track` (`:640`) — **the model D-01 declares inviolable.** Note the exact
  order: resolve filter → `audio.get_source()` → **increment `_play_generation` (`:702`)** → capture
  `current_gen` (`:703`) → define `after_callback` **guarded on `queue._play_generation == current_gen`
  (`:709`)** → `voice_client.stop()` if playing (`:718`) → `voice_client.play(source, after=...)`
  (`:728`) → fire `_prefetch_next_track` with the **in-scope `current_gen`** (`:748`). Also
  `source.cleanup()` on both failure paths (`:721`, `:734`) — **the orphan guard D-07 attack 2 must
  not break.**
- `cogs/music.py::_prefetch_next_track` (`:750`) — generation-guarded at entry (`:767`) **and after
  the download** (`:800`). **D-07 attack 3's subject**; the zero-gap prefetch (Phase 6) crossfade must
  not race.
- `cogs/music.py::_on_track_end` (`:858`) — the natural-advance choke point; dispatches on
  `decide_on_track_end`'s returned `TrackEndAction` and **must keep doing so** (Phase 10 D-02). Phase
  26's D-10 radio lookahead also lives here.
- `cogs/music.py::_try_skip` (`:1043`) → `cogs/music.py::_do_skip` (`:1122`) — **Phase 26's D-15
  single vote-gated choke point: `_do_skip` is called EXACTLY ONCE, from inside `_try_skip`.**
  D-12c/D-12d must not disturb this. Note `_do_skip` was left **completely unmodified** by Phase 26
  (its 26-04 decision) — preserving Critical Rule 3 for free.
- `cogs/music.py` `:1208`, `:1880`, `:2493` — the other `_play_generation += 1` teardown sites
  (`/stop`-template mirrors). **D-07 attack 2's targets**; `:2493` is the idle/voice-empty path.
- `models/queue.py::MusicQueue` — `clear()` (**resets `loop_mode`, monotonically advances
  `_play_generation`, never rewinds** — and deliberately does **NOT** reset `auto_lyrics`, the **D-12
  precedent**); `auto_lyrics` (**the in-memory-server-preference precedent D-12 follows**);
  `upcoming()` (the incoming-track read a fade needs); `skip()`; `advance()`; `mark_started()`;
  `Track.video_id` / `Track.duration_seconds`; the `(current_index, video_id)` **skip-vote single-slot
  cache** (Phase 26 — **D-12d's subject, untouched**).
- `logic/playback.py` — the pure seam (`TrackEndAction`, `decide_on_track_end`,
  `should_start_playback`, `clamp_restore_index`, …). **Read its module docstring for the scar list**
  (scar #1 finished-song replay, scar #2 silent auto-queue, scar #4 restore index clamp) — the reason
  D-01 exists. **The convention D-14's seam follows.** Locked by `tests/test_playback_logic.py`.
- `logic/radio.py` + `logic/skip_vote.py` — the **two most recent** pure seams (Phase 26, D-19); the
  closest structural analogs for `logic/crossfade.py`.

### Audio / the mixing surface (D-02, D-14)
- `services/audio.py::AudioService.get_source` (`:69`) — **the opus-copy-vs-transcode fork D-08b
  preserves.** `use_opts = seek_seconds > 0 or ffmpeg_filter is not None` (`:90`) gates it; the
  `not use_opts` branches (`:96`, `:115`, `:125`) are the **opus-passthrough default path a
  crossfaded track cannot take** (mixing needs decoded PCM). Also the **conditional ladder D-03/D-10b
  mirror**: cache hit (`:93`) → download-with-timeout (`:102`) → **stream fallback** (`:120`).
- `services/audio.py::_build_ffmpeg_opts` (`:24`) — the pure, unit-tested FFmpeg-opts builder; the
  in-file precedent for a pure function beside the I/O.
- `services/audio.py::cleanup_cache` (`:133`) + `protected_video_ids` — LFU eviction that **never
  evicts an in-use track**; a fade holds **two** tracks open, which the planner must keep in mind.
- `config.py:21` `AUDIO_QUALITY = "192"`; `config.py:111` `FFMPEG_FILTERS` + `config.py:125`
  `FILTER_COOLDOWN_SECONDS` — **the `/filter` precedent D-09b explicitly declines to join** (crossfade
  is not an `-af` chain over one source).
- `Dockerfile:4` (`python:3.11-slim-bookworm`) + `.github/workflows/ci.yml:44`,`:80`
  (`python-version: "3.11"`) — **the pin that makes `audioop` available and D-02 viable.** Both must
  move together if 3.13 is ever adopted (which would force the numpy rewrite).
- `requirements.txt` — **no numpy, no audioop entry** (audioop is stdlib). **D-02 adds nothing here.**

### Prior-phase context (conventions inherited)
- `.planning/phases/26-radio-mode-skip-democracy/26-CONTEXT.md` — **the immediately-prior phase, same
  engine surface.** Its **D-21** (no per-guild config for music commands — D-09b follows), **D-08**
  (in-memory state, dies on restart — D-12 follows), **D-15** (one skip choke point — D-12c/D-12d
  respect), **D-17** (vote cache keyed to the current track — D-12d's basis), and **D-19** (both
  features get a pure `logic/` seam — D-14 follows). Its §"Deferred Ideas" already lists
  **"Crossfade (DJ-03) → Phase 27, spike-gated"** and states Phase 26 must not pre-commit the engine
  to any crossfade design — **it didn't; the design space is open.**
- `.planning/phases/14-smarter-music-brain/14-CONTEXT.md` — the optional-param /
  byte-identical-when-unset discipline the "playback path unchanged when crossfade is off" guard
  follows.
- `.planning/phases/10-critical-path-test-coverage/*` — the `logic/` extraction convention + named
  scar regressions D-14's seam follows.

### CLAUDE.md invariants this phase must honor
- §"Critical Rules" **3** (**kill FFmpeg processes explicitly on skip/stop/error — prevent orphans**;
  **two live sources double the orphan surface — D-07 attack 2, D-12c**), **7/8** (≤1 emoji,
  lowercase — the `/crossfade` copy).
- §"Implementation Gotchas → Phase 1" — **never call `voice_client.stop()` before `_play_track()`**
  (the double-play race); the 3s interaction-response rule.
- §"Implementation Gotchas → Phases 6–8" — **opus-copy is the default fast path; transcode ONLY when
  `active_filter` is set per-track — don't remove the opus-copy path for non-filtered tracks
  (PERF-02 / PLAYER-07, D-10/D-12)** — **the invariant D-08b's off-by-default preserves**; **gate
  playback-start on `voice_client.is_playing()`, never `queue.is_playing`** (scar #2).
- §"Implementation Gotchas → Phases 9–12" — `logic/` is the pure seam and **glue dispatches on the
  returned enum/verdict, never mirrors the branch logic** (D-14); **`_play_track`'s create_task calls
  stay bare `asyncio.create_task`** — a `make_task` callback there would double-log (Pitfall 4).
- §"Music Pipeline → Playback Engine Patterns" — the generation counter, channel tracking, silent
  skip, async responses.
- §"Cache Management" — 512MB LFU cap, protects in-use tracks.

### Testing + CI
- `.planning/codebase/TESTING.md` — **"pure logic gets mock-free TDD; Discord/process glue is
  untested-by-design (structural review + clean boot)"** — governs D-14's seam and is **why D-11's
  attack evidence is observable artifacts rather than tests.**
- `tests/test_playback_logic.py` — the mock-free pattern + scar regressions D-14's tests mirror.
- `.github/workflows/ci.yml` — the blocking Ruff + pytest gate (pgvector service container). Suite is
  green at **1175 passed / 129 skipped / 0 failed** as of Phase 26.
- `.planning/config.json` — `workflow.use_worktrees: false` (**the D-16 basis**).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`services/audio.py::AudioService.get_source`** — already forks opus-passthrough vs. transcode on
  `use_opts`; a crossfade path is a **third condition on an existing fork**, not a new concept.
- **`_prefetch_next_track`** — by the time a fade would start, the incoming track is **usually already
  a local opus file**, which is what makes a fade cheap. **But not always** (stream fallback, a cold
  prefetch) — this is precisely the D-03 narrow-go / D-10b fallback territory.
- **`queue.upcoming()`** — the natural read for "what am I fading into".
- **`queue.auto_lyrics`** — **the exact D-12 precedent**: in-memory per-guild preference, deliberately
  NOT reset by `clear()`, not persisted.
- **`logic/playback.py` / `logic/radio.py` / `logic/skip_vote.py`** — the pure-seam convention D-14
  follows; `logic/radio.py` is the most recent analog.
- **`services/audio.py::_build_ffmpeg_opts`** — precedent for a pure, unit-tested function living
  beside the I/O it serves (the D-14 split, in miniature).
- **`scripts/memory_spike.py`** — the **in-repo spike precedent** (Phase 11 tuned RAG numeric defaults
  against live Neon before retrieval shipped). D-05 follows its spirit; **D-06 diverges** — that spike
  was kept, this one is discarded.
- **`Track.duration_seconds`** — already on the model; any minimum-duration eligibility floor is free.

### Established Patterns
- **Opus-copy by default; transcode only when asked** (Phase 6/7): the invariant D-08b preserves by
  making crossfade opt-in and off by default.
- **Conditional degradation ladders, silently** (cache → download → stream; unavailable-track silent
  skip): the shape D-03's narrow-go and D-10b's silent hard cut follow.
- **In-memory per-guild preference, dies on restart** (`auto_lyrics`, Phase 26 radio D-08): D-12.
- **Additive change, byte-identical when off** (Phase 14 `kind`, Phase 16 `pre_recalled_memories`,
  Phase 21 `guild_scoped`, Phase 26 `radio=False`): **the D-01 bar and the regression guard.**
- **ONE choke point, never per-surface checks** (Phase 20 OWNER-05, Phase 26 D-15): D-12c/D-12d must
  not fork the skip path.
- **`logic/` is the pure seam; glue dispatches on the returned value** (Phase 10 D-02): D-14.
- **The generation counter guards every teardown**: D-07 attacks 1 and 2 exist to prove a fade does
  not break this.
- **Numbers are planner's discretion** (Phase 11+): D-12b.

### Integration Points
- `services/audio.py` — the PCM mixing source (D-14's mechanics half); `get_source`'s `use_opts` fork.
- `cogs/music.py::_play_track` — where a fade would be initiated. **D-01: additively, without
  replacing the per-track `play()` model.**
- `cogs/music.py::_try_skip`/`_do_skip` — D-12c (skip cuts the fade) + D-12d (vote target unchanged).
  **Phase 26's machinery is untouched.**
- `cogs/music.py::_on_track_end` — the transition boundary a fade anticipates.
- `models/queue.py::MusicQueue` — the D-12 crossfade toggle attribute (NOT reset by `clear()`).
- `config.py` — new **global** knobs only (fade length; any duration floor) — Phase 26 D-21.
- New: `logic/crossfade.py` (D-14 eligibility seam); a `/crossfade on|off` command in `cogs/music.py`.
- **Regression surface:** `tests/test_playback_logic.py`, every test over `_play_track` /
  `_on_track_end` / `_do_skip` / `_try_skip`, plus the new "byte-identical when crossfade is off"
  guard.

</code_context>

<specifics>
## Specific Ideas

- **"This phase is designed so that shipping nothing is a clean, cheap outcome."** That is the
  through-line. D-01 (additive-only or no-go), D-06 (discard the code always), D-13 (a no-go closes
  green), and D-15 (no plans written until a go) all exist so that a correct "don't build this" costs
  one spike and one document — not a destabilized engine or a wasted planning pass.
- **The mixer rewrite isn't a design option — it's the no-go signal.** D-01 turns the most tempting
  technical direction ("just replace per-track `play()` with a session-long mixer") into the
  phase's explicit failure condition. The scar surface earned that.
- **Crossfade is the one "audible" criterion in the project that doesn't need the live bot.** Every
  other parked check — vision cadence, proactive feel, radio narration — needs Discord. **A PCM mix
  can be rendered to a file and played on the user's PC.** D-08/D-09 spend that asymmetry to close a
  requirement that would otherwise have become the 34th parked item.
- **An agent cannot hear.** D-10 exists because "the fade sounds good" is the one claim no subagent
  can honestly make, on a project whose own memory records agents over-claiming.
- **"No double-play, no orphan, no desync" are all observable.** D-11 refuses narrative evidence for
  facts that have counter values, process counts, and log lines. Phase 26's review caught a Critical
  that prose would have hidden.
- **The fallback is current behavior, so there's nothing to apologize for.** D-10b's silent hard cut
  isn't a degradation to explain — it's literally what the bot does today. Narrating it would be
  complaining about an internal detail nobody asked about.
- **Off by default protects a decision two phases were built around.** Mixing needs PCM; PCM means
  transcode; transcode-by-default would silently reverse Phase 6/7's opus-copy fast path on hardware
  the user personally hosts. `/filter` already resolved this exact tradeoff the same way — and the
  default is one line to flip later, whereas un-shipping a regression is not.
- **The fade is presentation; the queue is truth.** D-12d's reasoning in one line — the moment "which
  track is current" is read from audio overlap rather than `current_index`, this codebase grows a new
  scar.
- **A skip is an interrupt, not a request to fade politely.** D-12c — the room voted it gone; "gone"
  shouldn't take three more seconds. It's also the shortest path out of the two-live-sources window.

</specifics>

<deferred>
## Deferred Ideas

- **Rapid consecutive skips / overlapping-stacked fades as a spike attack** → deliberately not
  selected in D-07. It does **not** gate the verdict; it's the natural next probe **only if** a single
  skip proves clean.
- **numpy migration for the mixer** → forced only by a future Python 3.13 bump (`audioop` removal —
  D-02's accepted cost). Not scheduled; revisit when/if the interpreter pin moves.
- **Always-on crossfade (no toggle)** → rejected (D-08b). Revisit only if the transcode cost proves
  negligible in real use **and** the opus-copy default is consciously re-litigated — it's a one-line
  default flip.
- **A user-settable fade length (`/crossfade [seconds]`)** → rejected (D-12b). Revisit only if the
  fixed default proves wrong for real rooms — which needs the parked live UAT to know.
- **Crossfade into a looping SINGLE track (self-overlap)** → rejected (D-11b). Revisit only if
  seamless-loop-wrap for ambient/instrumental tracks is ever actually wanted; it's the hardest mix for
  the rarest case.
- **A fast fade into the skipped-to track** (instead of D-12c's dead cut) → rejected. Revisit only
  after a go verdict proves the two-source window is genuinely safe under load.
- **Radio-mode-only crossfade** → rejected (D-08b); it welded two independent features together.
  Subsumed by the opt-in toggle, which a radio session can simply turn on.
- **Persisting the crossfade toggle across restart** → rejected (D-12), mirroring Phase 26's D-08.
  Revisit only if the hosting model becomes always-on (DEPLOY-F1).
- **Salvaging the spike prototype into the implementation** → rejected (D-06). Not revisitable within
  this phase by construction — the branch is deleted.
- **`/filter` + crossfade simultaneously** → falls into the D-10b silent-hard-cut fallback for now
  (an already-transcoding track is a narrow-go exclusion). Revisit only if the spike shows the two
  compose cheaply.

### Reviewed Todos (not folded)
None — `todo.match-phase 27` returned zero matches.

</deferred>

---

*Phase: 27-crossfade-playback-spike-gated*
*Context gathered: 2026-07-17*
