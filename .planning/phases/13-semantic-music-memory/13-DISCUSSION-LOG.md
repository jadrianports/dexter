# Phase 13: Semantic Music Memory - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-02
**Phase:** 13-semantic-music-memory
**Areas discussed:** What is a taste episode, Staleness / decay tier, Distill cadence & window, One taste kind or two

> **Session note:** User selected all four areas, answered the taste-episode-trigger question,
> then went idle. Remaining decisions were made by Claude on the user's behalf (best judgment,
> grounded in Phase 11 precedent + v1.3 research pitfalls) and flagged for review in CONTEXT.md.

---

## Area selection

| Option | Description | Selected |
|--------|-------------|----------|
| What is a taste episode | Trigger + narrative shape + number→narrative bridge | ✓ |
| Staleness / decay tier | Faster decay + salience weight vs Phase 11 defaults | ✓ |
| Distill cadence & window | Schedule, lookback window, min-activity threshold | ✓ |
| One taste kind or two | taste_episode only vs + distinct taste_shift | ✓ |

**User's choice:** All four.

---

## What is a taste episode — Trigger (answered by user)

| Option | Description | Selected |
|--------|-------------|----------|
| Artist obsessions / binges | Burst of repeated plays of one artist | ✓ |
| New-artist arrivals | Artist/genre showing up meaningfully first time | ✓ |
| Steady favorites | Durable long-run preferences | ✓ |
| Late-night listening character | Time-of-day taste patterns | (dropped — redundant with existing `late_night` kind) |

**User's choice:** Obsessions + new arrivals + steady favorites; deliberately dropped late-night.
**Notes:** Good instinct — `late_night` already exists as a Phase 11 memory kind.

## What is a taste episode — Number→narrative bridge (decided on user's behalf)

| Option | Description | Selected |
|--------|-------------|----------|
| Pre-bucket into qualitative bands | Convert counts to words before Gemini sees them | ✓ |
| Feed raw counts, trust the gate | Pass counts, rely on distiller + contains_number() | |
| You decide | Claude chooses during planning | |

**Choice:** Pre-bucket (D-02). Rationale: accuracy firewall is a hard constraint; keep numbers
structurally out of the pipe rather than one-gate-deep. User did not answer; Claude decided.

---

## Staleness / decay tier (decided on user's behalf)

**Choice:** Taste decays faster than the 90-day default (~30d `TASTE_DECAY_DAYS`, D-03); own
salience base weight set *below* the 0.5 sweep floor (~0.4, D-04) so taste is eligible for expiry;
durable "steady favorites" survive via re-write/self-refresh, not high salience (D-05).
**Notes:** Directly mitigates research Pitfall 5 (stale taste surfaced as current). Numbers are
directional/spike-tunable. Flagged an open planner question: confirm dedup (0.92) doesn't block the
self-refresh timestamp reset for still-true tastes.

---

## Distill cadence & window (decided on user's behalf)

**Choice:** Daily module-scope `@tasks.loop` `taste_distill_batch` at a distinct UTC hour (~05:00,
clear of 02:30/03:00/04:00 loops, D-06); rolling ~7-day lookback over `song_history` only, never the
message buffer (D-07); ~5–8 track min-activity threshold to skip light users (D-08).
**Notes:** Follows the exact bot.py loop convention (before_loop/error/getattr guards).

---

## One taste kind or two (decided on user's behalf)

**Choice:** One kind — `taste_episode` only (D-09). Distinct `taste_shift` deferred; pivots
expressed inside the narrative.
**Notes:** Keeps the foundation phase lean.

---

## Claude's Discretion

- All numeric values (decay days, salience weight, schedule hour, lookback window, min-activity
  threshold, band boundaries, detection thresholds) — directional priors, spike/observation-tuned
  per the Phase 11 precedent.
- SQL aggregate helper shape and the raw_text distiller template — planning-time detail.

## Deferred Ideas

- Distinct `taste_shift` memory kind (D-09) — revisit if pivot-roasts feel underpowered.
- Late-night listening as a taste kind — rejected (redundant with `late_night`).
- Salience reinforcement (MEM-R1) — already out of scope → v1.4.
