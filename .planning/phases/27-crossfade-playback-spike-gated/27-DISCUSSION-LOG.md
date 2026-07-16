# Phase 27: Crossfade Playback (Spike-Gated) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-17
**Phase:** 27-crossfade-playback-spike-gated
**Areas discussed:** Spike verdict bar, Spike evidence, Crossfade surface, Feature interactions, plus
four follow-on gray areas surfaced by "Explore more gray areas" (no-go path, logic/ seam, phase shape,
spike isolation)

**Session shape:** User selected **all four** offered gray areas, chose **"More questions"** once (on
the verdict bar), and **"Explore more gray areas"** after the four closed. The user affirmatively
selected the **recommended option on every question** — this was not an AFK adoption. One answer
arrived as free text (see Feature interactions, vote-target question).

---

## Spike verdict bar

### Q1: How much of the playback engine is the spike allowed to propose changing?

| Option | Description | Selected |
|--------|-------------|----------|
| Additive-only — engine model inviolable | Per-track `voice_client.play()` + generation-counter model stays; a mixer-rewrite conclusion IS the no-go. A no-go costs one spike, not a broken engine. | ✓ |
| Rewrite on the table, invariants must hold | Spike may propose a session-long mixer source but must prove counter/`_on_track_end`/prefetch invariants hold. Proof burden lands on untested glue with no live UAT. | |
| Rewrite freely — spike judges on merit | No structural constraint; judged on prototype quality alone. No way to feel whether a new engine is sound with the host parked. | |

**User's choice:** Additive-only — engine model inviolable
**Notes:** Grounded in `logic/playback.py`'s named scars (#1 finished-song replay, #2 silent
auto-queue, #4 restore index clamp) — glue that is untested-by-design, with live UAT parked.

### Q2: Which mixing backend is the spike allowed to build on?

| Option | Description | Selected |
|--------|-------------|----------|
| stdlib `audioop` — accept the 3.13 dead-end | Stdlib on the pinned 3.11, zero deps, what the prior art uses. Removed in Python 3.13 → future rewrite. | ✓ |
| Require numpy — future-proof, new dep | Survives 3.13 and is fast, but a ~40MB runtime dep for one feature that may not ship. | |
| Pure-Python mixing — no deps, no dead-end | No dep, no cliff; but mixing 3840-byte frames 50×/s in the Discord event loop. | |
| Spike decides on merit | Prototype picks and reports back — hands a dependency call to a subagent. | |

**User's choice:** stdlib `audioop` — accept the 3.13 dead-end
**Notes:** Verified during scouting: `Dockerfile:4` = `python:3.11-slim-bookworm`; `ci.yml` pins 3.11
at both jobs. `requirements.txt` has no numpy. The 3.13 bump is not scheduled.

### Q3: Is a partial/conditional success a go or a no-go?

| Option | Description | Selected |
|--------|-------------|----------|
| Narrow go IS a go — degrade to hard cut | Fade where conditions allow, hard cut otherwise. Matches existing conditional ladders; the fallback is current behavior. | ✓ |
| All-or-nothing — narrow means no-go | Unambiguous, but discards a working feature over rarer paths; "always" is unachievable once `/filter` exists. | |
| Bring the verdict to me at plan time | Most informed, but stalls on a decision answerable now. | |

**User's choice:** Narrow go IS a go — degrade to hard cut

### Q4: Who declares the go/no-go, and how binding is it?

| Option | Description | Selected |
|--------|-------------|----------|
| Spike proposes, you decide at a gate | Verdict + evidence in RESEARCH.md; planning halts and surfaces it before any plan is written. Descoping rewrites REQUIREMENTS/ROADMAP — the user's call. | ✓ |
| Spike's verdict is binding, planning auto-routes | Zero latency, honors the rule mechanically, but lets a subagent kill a milestone requirement. | |
| Verdict is advisory — planner weighs it | Keeps one pipeline, but a spike you can plan around isn't a gate. | |

**User's choice:** Spike proposes, you decide at a gate
**Notes:** Reinforced by the user's standing "verify agent claims independently" lesson and Phase 26's
over-claiming executors.

### Q5 (after "More questions"): What must the spike prototype against?

| Option | Description | Selected |
|--------|-------------|----------|
| The real engine, in-repo, on a throwaway branch | Import real `MusicQueue`/`logic/playback.py`/`_play_track`; a standalone script cannot race a counter it doesn't have. | ✓ |
| Standalone script under `scripts/` | Fast, no debris, but proves mixing math — which was never in doubt. | |
| Read prior art + reason it through, no code | Cheapest, but a reasoned verdict is not a spike. | |

**User's choice:** The real engine, in-repo, on a throwaway branch
**Notes:** Roadmap SC-1's wording demands prototyping against "the real generation-counter/`/skip`/
prefetch playback engine."

### Q6: What happens to the spike code afterward?

| Option | Description | Selected |
|--------|-------------|----------|
| Discard always — reimplement clean if go | Only artifact is the verdict + findings; branch dies either way. | ✓ |
| Salvage on go — promote the prototype | Saves duplicated effort, but carries prototype shortcuts onto the scar surface. | |
| Keep it under `scripts/` as a reference | Preserves evidence, but a parked half-crossfade of the engine goes stale. | |

**User's choice:** Discard always — reimplement clean if go

### Q7 (multi-select): What must the spike actively try to break?

| Option | Description | Selected |
|--------|-------------|----------|
| `/skip` landing mid-fade | The named roadmap risk: no double-play, no orphan, no counter desync. | ✓ |
| `/stop` + idle-leave mid-fade | Teardown with two live sources; DEPLOY-06 scar territory, orphan risk doubles. | ✓ |
| Prefetch racing the fade | Fade reads the next track while `_prefetch_next_track` fetches it. | ✓ |
| Rapid consecutive skips | Overlapping/stacked fades — load-testing on top of attack 1. | |

**User's choice:** The first three; rapid consecutive skips deliberately excluded
**Notes:** Excluded item recorded as a deferred idea — a natural next probe only if a single skip
proves clean. It does not gate the verdict.

---

## Spike evidence

### Q1: How does "the tail audibly blends" get proven with live UAT parked?

| Option | Description | Selected |
|--------|-------------|----------|
| Render the mix to a local file and listen | Spike writes mixed PCM of a real transition to a file played on the user's PC. No Discord, no host — sidesteps the blocker that parked 33 items. | ✓ |
| Run a real Discord voice test on your PC | Highest fidelity (proves the Opus encode path), but costs a manual session per iteration. | |
| Structural + unit proof, listen deferred to the host | Consistent with precedent, but closes DJ-03 having never heard it. | |

**User's choice:** Render the mix to a local file and listen
**Notes:** Identified as the one "audible" criterion in the project that does not require the live bot.

### Q2: Does the render SATISFY SC-2, or is a live listen required to close?

| Option | Description | Selected |
|--------|-------------|----------|
| Render satisfies SC-2; live listen is a parked confirmation | Mixer output IS what Discord encodes; residual risk is Opus + jitter, which crossfade doesn't change. | ✓ |
| Live Discord listen required — render is a pre-check | More honest end-to-end, but makes DJ-03 the only v1.5 req gated on the parked host. | |
| Render satisfies it, no live check tracked at all | Cleanest close, but real voice adds an encode + jitter buffer the file never sees. | |

**User's choice:** Render satisfies SC-2; live listen is a parked confirmation

### Q3: Who judges the rendered fade?

| Option | Description | Selected |
|--------|-------------|----------|
| You listen; your ear is the bar | An agent cannot hear — it can only assert it rendered something. | ✓ |
| Agent asserts correctness from the waveform | Proves the math, not the experience; a correct fade can still sound wrong. | |
| Both — numeric assertions gate, you spot-check | Thorough, but makes numeric checks load-bearing for a property verified by ear anyway. | |

**User's choice:** You listen; your ear is the bar

### Q4: What counts as proof for the safety attacks?

| Option | Description | Selected |
|--------|-------------|----------|
| Observable evidence — logs, process counts, counter values | Counter values before/after, FFmpeg process count (zero orphans), `dexter.log` with no stale-callback firing, pasted into RESEARCH.md. | ✓ |
| Narrative findings in RESEARCH.md | Fast and readable, but unfalsifiable at the gate. | |
| Mock-free tests over the extracted logic | Durable, but a pure test cannot reproduce a real orphaned FFmpeg process. | |

**User's choice:** Observable evidence — logs, process counts, counter values
**Notes:** Motivated by Phase 26's review catching a Critical that a narrative summary would have missed.

---

## Crossfade surface

### Q1: Where does crossfade apply?

| Option | Description | Selected |
|--------|-------------|----------|
| Opt-in toggle, off by default | Opus-copy stays default for anyone who doesn't ask; mirrors how `/filter` resolved the identical transcode tradeoff. | ✓ |
| Always-on — every transition fades | Best version of the feature, but makes transcode the default, reversing a two-phase decision on self-hosted hardware. | |
| Radio-mode only | Naturally scoped, but welds two independent features together. | |

**User's choice:** Opt-in toggle, off by default

### Q2: What's the command surface?

| Option | Description | Selected |
|--------|-------------|----------|
| New `/crossfade on|off` | Mirrors `/autolyrics`; crossfade is a transition behavior, not an `-af` chain. | ✓ |
| A value in the existing `/filter` group | No new command, but would make crossfade mutually exclusive with bassboost — arbitrary. | |
| A `/setup` per-guild toggle | Consistent with v1.4, but Phase 26's D-21 rules music commands don't get per-guild surfaces. | |

**User's choice:** New `/crossfade on|off`

### Q3: What happens when a transition can't fade?

| Option | Description | Selected |
|--------|-------------|----------|
| Silent hard cut — log only | The fallback IS current behavior; the engine already degrades silently everywhere else. | ✓ |
| Hard cut + a one-line Dexter comment | Honest, but fires per-transition on already-degraded paths — repeated complaining. | |
| Wait for conditions — delay the next track | Delivers on the promise, but reintroduces the dead air Phase 6 eliminated. | |

**User's choice:** Silent hard cut — log only

### Q4: Does the toggle survive `/stop` and teardown?

| Option | Description | Selected |
|--------|-------------|----------|
| Survives — a server preference, like `auto_lyrics` | `clear()` deliberately doesn't reset `auto_lyrics`; crossfade is the same kind of stated preference. In-memory, dies on restart. | ✓ |
| Resets on `clear()` — like `loop_mode` and radio | Radio resets because an armed station is a runaway; crossfade has no runaway behavior. | |
| Persist to `guild_queues` JSONB across restart | Real durability, but adds a field to the scar-heavy restore path for a boolean. | |

**User's choice:** Survives — a server preference, like `auto_lyrics`

---

## Feature interactions

### Q1: Does loop SINGLE crossfade into itself?

| Option | Description | Selected |
|--------|-------------|----------|
| No fade under loop SINGLE — hard cut | Falls into the existing fallback; self-overlap is a phasing artifact, not a blend. | ✓ |
| Fade into itself — treat it like any transition | No special-casing, but the hardest mix for the rarest case. | |
| Mutually exclusive — like radio and loop (D-11) | Precedent exists, but would ban loop QUEUE + crossfade, which is coherent. | |

**User's choice:** No fade under loop SINGLE — hard cut

### Q2: A skip fires mid-fade — what does the listener hear?

| Option | Description | Selected |
|--------|-------------|----------|
| Skip cuts the fade dead — immediate hard transition | A skip is an interrupt; also the safest teardown, one code path, shortest two-source window. | ✓ |
| Fade completes, then the skip applies | Smoothest audio, but the skip visibly doesn't work for seconds after the room voted. | |
| Fade out fast into the skipped-to track | Best of both, but invents a third transition type inside the race the spike exists to prove safe. | |

**User's choice:** Skip cuts the fade dead — immediate hard transition

### Q3: During a fade, which track does a `/skip` vote target?

| Option | Description | Selected |
|--------|-------------|----------|
| The incoming track — queue state is the only truth | `current_index` has already advanced; Phase 26's `(current_index, video_id)` cache keeps working. | ✓ |
| The outgoing track — it's what they still hear | Truer to intent, but makes the target depend on millisecond timing within the fade. | |
| Suppress skip voting during a fade | No ambiguity, but `/skip` silently does nothing for seconds per transition. | |

**User's choice:** *(free text)* "your recommended yea.. btw should crossfade be toggleable on or off hmm?"
**Notes:** Recommendation locked as the answer. The trailing question was answered inline as
already-decided by the Crossfade surface area (it **is** toggleable — `/crossfade on|off`, off by
default). Claude's stated view: **off** is right (preserves the Phase 6/7 opus-copy fast path;
transcode CPU lands on the user's own PC), and the default is reversible in one line whereas
un-shipping a transcode-by-default regression is not. **The user did not revise it.**

### Q4: Fade length — fixed or user-settable?

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed config knob — planner picks the default | Matches discretion-on-numbers precedent; with live UAT parked, an exposed dial is one nobody can tune. | ✓ |
| `/crossfade [seconds]` — user-settable | Rooms differ, but it's a second arg on a command whose virtue is being a boolean. | |
| Fixed, but revisit after you've heard it | Effectively option 1 with ceremony the render gate already provides. | |

**User's choice:** Fixed config knob — planner picks the default

---

## Follow-on gray areas (surfaced by "Explore more gray areas")

### A: On a no-go, what concretely happens?

| Option | Description | Selected |
|--------|-------------|----------|
| Phase completes SUCCESSFULLY with the descope as its deliverable | DJ-03 → DJ-F2 with findings; docs updated; phase closes green with RESEARCH.md as artifact. Exactly what SC-3 says. | ✓ |
| Phase closes as blocked/abandoned | Honest that DJ-03 didn't ship, but reads as failure when it's the Descope Rule working. | |
| Bring it back to me to decide how to close | The user already owns the go/no-go; how a no-go is recorded is mechanical. | |

**User's choice:** Phase completes SUCCESSFULLY with the descope as its deliverable

### B: Does crossfade get a pure `logic/` seam?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — the eligibility decision only, not the mixing | `logic/crossfade.py` holds "should this transition fade?"; PCM mixing stays in `services/audio.py`. | ✓ |
| Yes — seam covers eligibility AND the mix math | Pure-testable too, but drags buffer handling into `logic/`, which has no I/O by convention. | |
| No seam — it's all audio mechanics | Least structure, but the fallback ladder IS branching decision logic. | |

**User's choice:** Yes — the eligibility decision only, not the mixing

### C: How does the spike gate fit the plan→execute pipeline?

| Option | Description | Selected |
|--------|-------------|----------|
| Spike runs at plan time; implementation plans written only after a go | `/gsd:plan-phase 27` runs the spike as research, surfaces the verdict, writes plans only on a go. On a no-go: one artifact, zero wasted plans. | ✓ |
| Write all plans now; plan 01 is the spike, later plans abort on no-go | One pass, standard shape, but writes plans for a possibly-impossible feature. | |
| Spike as its own mini-phase (27a), implementation as 27b | Clean separation, but splits one roadmap phase for a decision research already holds. | |

**User's choice:** Spike runs at plan time; implementation plans written only after a go
**Notes:** Consequence recorded in CONTEXT.md — the planner must treat "terminate with a descope and
zero plans" as a valid, successful outcome.

### D: Where does the spike run, given worktrees are off?

| Option | Description | Selected |
|--------|-------------|----------|
| A real throwaway git branch off `main`, hard-deleted after | Real isolation, no worktree — the standing gotcha is that `isolation=worktree` forks a stale `origin/main` here, which would defeat the spike's purpose. | ✓ |
| Directly on `main`, revert when done | Matches recent sequential-on-main pattern, but "revert when done" is a promise, not a mechanism. | |
| `isolation=worktree` on the spike agent | Purpose-built, but the stale-`origin/main` gotcha makes it actively wrong here. | |

**User's choice:** A real throwaway git branch off `main`, hard-deleted after

---

## Claude's Discretion

Per the standing Phase 11/13/14/15/16/17/21/25/26 "discretion-on-numbers" precedent, the user was
**not** asked about (and must not be re-asked):

- Every numeric knob: the fade-length default, any minimum-track-duration floor, tail/head buffer
  sizing. All go in `config.py` as global settings (Phase 26 D-21).
- The exact fade curve (linear vs equal-power vs logarithmic) — the user's ear on the render is the
  arbiter.
- The exact `logic/crossfade.py` module name + signature for the eligibility seam.
- Where the crossfade toggle attribute lives on `MusicQueue` and its name (follow `auto_lyrics`).
- How the mixed source is expressed in `services/audio.py` — subject to the additive-only bar.
- The render artifact's format + location (must be trivially playable, must not be committed).
- Exact test shape, including the "byte-identical when crossfade is off" regression guard.
- Wording of all new personality copy (lowercase, ≤1 emoji, accurate-first).

## Deferred Ideas

- Rapid consecutive skips / overlapping-stacked fades as a spike attack — does not gate the verdict.
- numpy migration for the mixer — forced only by a future Python 3.13 bump. Not scheduled.
- Always-on crossfade (no toggle) — one-line default flip if ever re-litigated.
- A user-settable fade length (`/crossfade [seconds]`).
- Crossfade into a looping SINGLE track (self-overlap).
- A fast fade into the skipped-to track instead of a dead cut.
- Radio-mode-only crossfade — subsumed by the opt-in toggle.
- Persisting the crossfade toggle across restart — revisit only if hosting becomes always-on.
- Salvaging the spike prototype into the implementation — not revisitable by construction.
- `/filter` + crossfade simultaneously — currently a narrow-go exclusion.
